import os
import re
import streamlit as st
import tempfile
import traceback
from app.pipeline import Pipeline
from app.utils import get_toc, flatten_text
from app.obsidize import list_templates, load_template, load_template_from_string
from app.ui import (
    THEMES,
    generate_theme_css,
    render_welcome_screen,
    render_anki_card_html,
    render_mermaid,
    render_kg_stats,
    section_card_html,
)

# ──────────────────────────────────────────────────────────────────────────────
# Page configuration (must be first Streamlit call)
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="IDLEARN — Study Smarter",
    page_icon="🧠",
    layout="wide",
)

# ──────────────────────────────────────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────────────────────────────────────
if "results" not in st.session_state:
    st.session_state.results = None
if "pipeline" not in st.session_state:
    st.session_state.pipeline = None
if "card_index" not in st.session_state:
    st.session_state.card_index = 0
if "show_answer" not in st.session_state:
    st.session_state.show_answer = False
if "knowledge_graph" not in st.session_state:
    st.session_state.knowledge_graph = None
if "section_images" not in st.session_state:
    st.session_state.section_images = {}
if "theme" not in st.session_state:
    st.session_state.theme = "ink_amber"

# ──────────────────────────────────────────────────────────────────────────────
# Theme injection — regenerate CSS on every rerun so theme switches take effect
# ──────────────────────────────────────────────────────────────────────────────
theme_css = generate_theme_css(st.session_state.theme)
st.markdown(f"<style>{theme_css}</style>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers (data processing only — rendering is in app/ui.py)
# ──────────────────────────────────────────────────────────────────────────────

def parse_qa_pairs(dqa: dict) -> list[dict]:
    """Parse raw Q&A text from the LLM into structured card dicts."""
    cards = []
    for section, qa_text in dqa.items():
        questions = re.findall(r"Q:\s.*?(?=\nA:|\Z)", qa_text, re.DOTALL)
        answers = re.findall(r"A:\s.*?(?=\n+Q:|\Z)", qa_text, re.DOTALL)

        if not questions or not answers:
            continue

        for i in range(min(len(questions), len(answers))):
            q = questions[i].strip()
            a = answers[i].strip()
            q_text = q[3:].strip() if q.startswith("Q: ") else q.strip()
            a_text = a[3:].strip() if a.startswith("A: ") else a.strip()

            is_cloze = "{{c" in a_text or "______" in q_text
            cards.append({
                "section": section,
                "question": q_text,
                "answer": a_text,
                "is_cloze": is_cloze,
            })
    return cards


def split_summary_and_figures(summary_text: str) -> tuple[str, list[str]]:
    """Split summary text into main content and figure descriptions."""
    parts = re.split(r"^#{1,4}\s+Figures?\s*$", summary_text, flags=re.MULTILINE)
    main_text = parts[0].rstrip()

    figure_captions = []
    if len(parts) > 1:
        figures_section = parts[1]
        for line in figures_section.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            cleaned = re.sub(r"^[-*]\s+\*\*[^*]*\*\*\s*:?\s*", "", line)
            if cleaned:
                figure_captions.append(cleaned)

    return main_text, figure_captions


def build_toc_tree(toc: list) -> list[dict]:
    """Convert a flat ToC list into a nested tree structure."""
    tree = []
    stack = []

    for sec in toc:
        level, title, start_page, end_page = sec
        node = {"section": sec, "level": level, "children": []}

        while stack and stack[-1][0] >= level:
            stack.pop()

        if stack:
            stack[-1][1]["children"].append(node)
        else:
            tree.append(node)

        stack.append((level, node))

    return tree


# ──────────────────────────────────────────────────────────────────────────────
# Sidebar — brand, theme, controls
# ──────────────────────────────────────────────────────────────────────────────

# ── Brand header ──
theme = THEMES[st.session_state.theme]
st.sidebar.markdown(
    f"""
    <div class="il-brand">
        <span class="il-brand-name">idlearn</span><span class="il-brand-dot">.</span>
    </div>
    <div class="il-brand-tagline">Study Smarter, Not Harder</div>
    """,
    unsafe_allow_html=True,
)

# ── Theme switcher ──
theme_options = list(THEMES.keys())
theme_labels = [f"{THEMES[k]['icon']} {THEMES[k]['name']}" for k in theme_options]
selected_idx = theme_options.index(st.session_state.theme)
selected_label = st.sidebar.selectbox(
    "Theme",
    options=theme_labels,
    index=selected_idx,
    key="theme_selector",
)
# Update session state if theme changed
new_theme_key = theme_options[theme_labels.index(selected_label)]
if new_theme_key != st.session_state.theme:
    st.session_state.theme = new_theme_key
    st.rerun()

# ── Section: File ──
st.sidebar.markdown('<div class="il-sidebar-section">File</div>', unsafe_allow_html=True)

uploaded_file = st.sidebar.file_uploader("Upload PDF or EPUB", type=["pdf", "epub"])

output_folder = st.sidebar.text_input(
    "Output Folder Path",
    value="./output",
    help="Enter the full path where markdown and Anki files will be saved.",
)

st.sidebar.markdown("---")

# ── Section: Processing ──
st.sidebar.markdown('<div class="il-sidebar-section">Processing</div>', unsafe_allow_html=True)

summarize_toggle = st.sidebar.checkbox("Summarize Selected Sections", value=True)
anki_toggle = st.sidebar.checkbox("Generate Anki Cards", value=False)
obsidian_toggle = st.sidebar.checkbox("Export to Obsidian", value=False)

# ── Obsidian settings ──
obsidian_template = None
obsidian_vault_path = None
if obsidian_toggle:
    st.sidebar.markdown("#### 📝 Obsidian Export")

    vault_input = st.sidebar.text_input(
        "Obsidian Vault Path",
        value=os.path.expanduser("~/Documents/obsidian"),
        help="Path to your Obsidian vault.",
    )
    obsidian_vault_path = vault_input.strip() if vault_input.strip() else None

    available_templates = list_templates()
    template_display = []
    for t in available_templates:
        desc = f" — {t['description']}" if t.get("description") else ""
        label = f"{t['name']} ({t['source']}){desc}"
        template_display.append({"label": label, "id": t["id"], "name": t["name"]})

    default_index = 0
    for i, t in enumerate(template_display):
        if t["id"] == "idlearn-summary":
            default_index = i
            break

    selected_idx = st.sidebar.selectbox(
        "Obsidian Template",
        options=range(len(template_display)),
        format_func=lambda i: template_display[i]["label"],
        index=default_index,
    )
    obsidian_template = template_display[selected_idx]["id"]

    with st.sidebar.expander("🔍 Template Preview"):
        try:
            tmpl = load_template(obsidian_template)
            st.markdown(f"**{tmpl.name}** (`{tmpl.id}`)")
            st.markdown(f"**Path:** `{tmpl.path or '(root)'}`")
            st.markdown("**Properties:**")
            for p in tmpl.properties:
                st.text(f"  {p.name} ({p.type}): {p.value}")
            st.markdown("**Content template:**")
            st.code(tmpl.note_content_format[:500], language="jinja2")
            if len(tmpl.note_content_format) > 500:
                st.info(f"... ({len(tmpl.note_content_format) - 500} more characters)")
        except Exception as e:
            st.warning(f"Could not load template preview: {e}")

    st.sidebar.markdown("---")
    uploaded_template = st.sidebar.file_uploader(
        "📤 Upload Custom Template",
        type=["json"],
        key="obsidian_template_upload",
    )
    if uploaded_template is not None:
        try:
            template_json_str = uploaded_template.read().decode("utf-8")
            custom_tmpl = load_template_from_string(template_json_str)
            st.sidebar.success(f"Loaded custom template: **{custom_tmpl.name}**")
            obsidian_template = custom_tmpl
        except Exception as e:
            st.sidebar.error(f"Invalid template: {e}")

# ── Section: LLM ──
if summarize_toggle:
    st.sidebar.markdown('<div class="il-sidebar-section">LLM Provider</div>', unsafe_allow_html=True)
    api_type = st.sidebar.radio(
        "Select Provider",
        ("Ollama (Local/Cloud)", "OpenAI (Cloud)"),
        index=0,
    )
    llm_api_type = "ollama" if "Ollama" in api_type else "openai"

    if llm_api_type == "ollama":
        llm_base_url = st.sidebar.text_input("Ollama Host URL", value="https://ollama.com")
        llm_api_key = st.sidebar.text_input("API Key (Optional)", type="password")
        llm_model = st.sidebar.text_input("Model Name", value="gemma4:31b:cloud")
    else:
        llm_base_url = st.sidebar.text_input("API Base URL", value="https://api.openai.com/v1")
        llm_api_key = st.sidebar.text_input("API Key", type="password")
        llm_model = st.sidebar.text_input("Model Name", value="gpt-4o")
else:
    llm_api_type = "ollama"
    llm_base_url = None
    llm_api_key = None
    llm_model = None

# ──────────────────────────────────────────────────────────────────────────────
# File upload & section selection
# ──────────────────────────────────────────────────────────────────────────────
if uploaded_file:
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=os.path.splitext(uploaded_file.name)[1]
    ) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    if st.session_state.pipeline is None:
        st.session_state.pipeline = Pipeline(
            tmp_path,
            output_folder,
            cards=anki_toggle,
            api_type=llm_api_type,
            model=llm_model,
            base_url=llm_base_url,
            api_key=llm_api_key,
        )
    pipeline = st.session_state.pipeline

    toc = get_toc(pipeline.doc)

    # ── ToC section selection ──
    st.sidebar.markdown('<div class="il-sidebar-section">Sections</div>', unsafe_allow_html=True)
    selected_sections = []
    toc_tree = build_toc_tree(toc)

    for node in toc_tree:
        sec = node["section"]
        level, title, start_page, end_page = sec
        has_children = len(node["children"]) > 0

        if has_children:
            with st.sidebar.expander(f"{title} (p.{start_page})", expanded=False):
                if st.checkbox(f"Include all of **{title}**", key=f"cb_parent_{start_page}_{title}"):
                    selected_sections.append(sec)
                for child in node["children"]:
                    csec = child["section"]
                    clabel = f"{csec[1]} (p.{csec[2]})"
                    if st.checkbox(clabel, key=f"cb_{csec[2]}_{csec[1]}"):
                        selected_sections.append(csec)
        else:
            label = f"{title} (p.{start_page})"
            if st.sidebar.checkbox(label, key=f"cb_{start_page}_{title}"):
                selected_sections.append(sec)

    st.sidebar.markdown("---")

    if st.sidebar.button("🚀 Start Processing", use_container_width=True):
        st.session_state.card_index = 0
        st.session_state.show_answer = False
        with st.spinner("Processing document… This may take a while for large files."):
            try:
                results = pipeline.run(selected_sections, summarize=summarize_toggle)
                st.session_state.results = results
                if hasattr(pipeline, "knowledge_graph") and pipeline.knowledge_graph:
                    st.session_state.knowledge_graph = pipeline.knowledge_graph
                if hasattr(pipeline, "section_images"):
                    st.session_state.section_images = pipeline.section_images
                st.success("Processing complete!")

                if obsidian_toggle and obsidian_template:
                    try:
                        obs_output_folder = obsidian_vault_path or output_folder
                        obs_result = pipeline.export_obsidian(
                            template=obsidian_template,
                            dtext=results[0] if results else None,
                            dsum=results[2] if results else None,
                            dqa=results[3] if results else None,
                            output_folder=obs_output_folder,
                        )
                        st.success(f"Obsidian note exported: `{obs_result.note_name}.md`")
                        with st.expander("📖 Obsidian Note Preview"):
                            st.code(obs_result.full_content[:4000], language="markdown")
                            if len(obs_result.full_content) > 4000:
                                st.info(f"... ({len(obs_result.full_content) - 4000} more characters)")
                            st.download_button(
                                label="📥 Download .md file",
                                data=obs_result.full_content,
                                file_name=f"{obs_result.note_name}.md",
                                mime="text/markdown",
                            )
                    except Exception as e:
                        st.error(f"Error exporting to Obsidian: {e}")
                        st.code(traceback.format_exc(), language="python")
            except Exception as e:
                st.error(f"An error occurred: {e}")
                st.code(traceback.format_exc(), language="python")

# ──────────────────────────────────────────────────────────────────────────────
# Main content area
# ──────────────────────────────────────────────────────────────────────────────
if st.session_state.results:
    dtext_selected, dtext, dsum, dqa = st.session_state.results
    pipeline = st.session_state.pipeline
    section_images = st.session_state.section_images

    # ── Tabs: Summary | Anki Cards | Knowledge Graph ──
    tab_summary, tab_cards, tab_graph = st.tabs(
        ["📋 Summary", "🃏 Anki Cards", "🕸️ Knowledge Graph"]
    )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TAB 1 — Summary (with inline images)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with tab_summary:
        if dsum:
            for section_title, summary_text in dsum.items():
                with st.expander(f"📋 {section_title}", expanded=True):
                    main_text, figure_captions = split_summary_and_figures(summary_text)
                    st.markdown(main_text)
                    imgs = section_images.get(section_title, [])
                    if imgs:
                        for i in range(0, len(imgs), 2):
                            cols = st.columns(2)
                            for col_idx in range(2):
                                img_idx = i + col_idx
                                with cols[col_idx]:
                                    if img_idx < len(imgs):
                                        caption = figure_captions[img_idx] if img_idx < len(figure_captions) else None
                                        if os.path.isfile(imgs[img_idx]):
                                            st.image(imgs[img_idx], caption=caption)
                                        else:
                                            st.caption(f"⚠️ Image not found: {os.path.basename(imgs[img_idx])}")
                        leftover = figure_captions[len(imgs):]
                        if leftover:
                            st.markdown("**Additional figure notes:**")
                            for desc in leftover:
                                st.markdown(f"- {desc}")
        else:
            st.info("No summaries generated. Enable summarization in the sidebar.")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TAB 2 — Anki Card Viewer
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with tab_cards:
        cards = parse_qa_pairs(dqa) if dqa else []

        if not cards:
            st.info(
                "No Anki cards generated. Enable **Generate Anki Cards** in the sidebar "
                "and process the document again."
            )
        else:
            # ── Navigation controls ──
            nav_cols = st.columns([1, 3, 1])
            with nav_cols[0]:
                if st.button("◀ Prev", use_container_width=True):
                    st.session_state.card_index = max(0, st.session_state.card_index - 1)
                    st.session_state.show_answer = False
            with nav_cols[1]:
                st.markdown(
                    f"<div style='text-align:center; padding-top:8px;'>"
                    f"Card <b>{st.session_state.card_index + 1}</b> of <b>{len(cards)}</b>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
            with nav_cols[2]:
                if st.button("Next ▶", use_container_width=True):
                    st.session_state.card_index = min(
                        len(cards) - 1, st.session_state.card_index + 1
                    )
                    st.session_state.show_answer = False

            # ── Card display ──
            idx = st.session_state.card_index
            card = cards[idx]
            card_html = render_anki_card_html(
                card, idx, len(cards), st.session_state.show_answer
            )
            st.markdown(card_html, unsafe_allow_html=True)

            # ── Reveal / Hide answer ──
            if not st.session_state.show_answer:
                if st.button("👁️ Show Answer", use_container_width=True):
                    st.session_state.show_answer = True
                    st.rerun()
            else:
                if st.button("🙈 Hide Answer", use_container_width=True):
                    st.session_state.show_answer = False
                    st.rerun()

            # ── Section filter ──
            sections = sorted(set(c["section"] for c in cards))
            if len(sections) > 1:
                st.markdown("---")
                filter_col1, filter_col2 = st.columns(2)
                with filter_col1:
                    filter_section = st.selectbox(
                        "Filter by section", ["All sections"] + sections,
                        key="card_filter_section",
                    )
                with filter_col2:
                    if filter_section != "All sections":
                        filtered = [c for c in cards if c["section"] == filter_section]
                        st.metric("Cards in section", len(filtered))

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # TAB 3 — Knowledge Graph
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with tab_graph:
        kg = st.session_state.knowledge_graph

        if kg and kg.concepts:
            st.markdown(
                render_kg_stats(len(kg.concepts), len(kg.relations), kg.title or "Knowledge Graph"),
                unsafe_allow_html=True,
            )

            # ── Mermaid visualization ──
            st.markdown("### Graph Visualization")
            render_mermaid(kg.to_mermaid())

            # ── Concept table ──
            st.markdown("### Concepts")
            concept_data = [
                {
                    "ID": c.id,
                    "Label": c.label,
                    "Category": c.category,
                    "Section": c.section,
                    "Definition": c.definition,
                }
                for c in kg.concepts
            ]
            st.dataframe(concept_data, use_container_width=True, hide_index=True)

            # ── Relationships table ──
            if kg.relations:
                st.markdown("### Relationships")
                rel_data = [
                    {
                        "Source": r.source,
                        "→": "→",
                        "Target": r.target,
                        "Label": r.label,
                        "Weight": f"{r.weight:.2f}",
                    }
                    for r in kg.relations
                ]
                st.dataframe(rel_data, use_container_width=True, hide_index=True)

            # ── Export buttons ──
            st.markdown("---")
            col_json, col_canvas = st.columns(2)
            with col_json:
                st.download_button(
                    "📥 Download JSON",
                    data=kg.to_json(),
                    file_name="knowledge_graph.json",
                    mime="application/json",
                )
            with col_canvas:
                st.download_button(
                    "📥 Download Obsidian Canvas",
                    data=kg.to_obsidian_canvas(),
                    file_name="knowledge_graph.canvas",
                    mime="application/json",
                )
        else:
            st.info(
                "No knowledge graph available. Knowledge graph extraction happens "
                "automatically when summarization is enabled. Make sure to enable "
                "**Summarize Selected Sections** and process the document."
            )

else:
    # ── Empty state: welcome screen ──
    st.markdown(render_welcome_screen(), unsafe_allow_html=True)
