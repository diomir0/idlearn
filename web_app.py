import streamlit as st
import os
import tempfile
import traceback
from app.pipeline import Pipeline
from app.utils import get_toc, flatten_text

# Page configuration for a wide, professional layout
st.set_page_config(
    page_title="IDLEARN - Web Interface",
    page_icon="📚",
    layout="wide"
)

# Custom CSS for a cleaner interface and better readability
st.markdown("""
    <style>
    .main .block-container {
        padding-top: 2rem;
    }
    .stMarkdown {
        font-family: 'Inter', sans-serif;
    }
    .copy-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #ddd;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Session State Management ---
# We store results in session state to prevent data loss during Streamlit reruns
if 'results' not in st.session_state:
    st.session_state.results = None
if 'pipeline' not in st.session_state:
    st.session_state.pipeline = None

# --- Sidebar: Control Panel ---
st.sidebar.title("⚙️ IDLEARN Controls")
st.sidebar.markdown("Configure your extraction and summarization settings.")

# 1. File Upload
uploaded_file = st.sidebar.file_uploader("Upload PDF or EPUB", type=["pdf", "epub"])

# 2. Destination Folder
output_folder = st.sidebar.text_input(
    "Output Folder Path",
    value="./output",
    help="Enter the full path where markdown and Anki files will be saved."
)

st.sidebar.markdown("---")

# 3. Options
summarize_toggle = st.sidebar.checkbox("Summarize Selected Sections", value=True)
anki_toggle = st.sidebar.checkbox("Generate Anki Cards", value=False)

# 4. LLM Provider Settings (shown below summarization)
if summarize_toggle:
    st.sidebar.markdown("#### 🤖 LLM Provider")
    api_type = st.sidebar.radio(
        "Select Provider",
        ("Ollama (Local/Cloud)", "OpenAI (Cloud)"),
        index=0
    )

    # Convert radio selection to api_type string
    llm_api_type = "ollama" if "Ollama" in api_type else "openai"

    if llm_api_type == "ollama":
        llm_base_url = st.sidebar.text_input(
            "Ollama Host URL",
            value="http://localhost:11434",
            help="URL of your Ollama instance (local or cloud, e.g., https://ollama.com)"
        )
        llm_api_key = st.sidebar.text_input(
            "API Key (Optional)",
            type="password",
            help="Required for Ollama Cloud. Leave empty for local instances."
        )
        llm_model = st.sidebar.text_input(
            "Model Name",
            value="mistral:7B-instruct",
            help="e.g., mistral:7B-instruct, gemma4:31b:cloud"
        )
    else:
        llm_base_url = st.sidebar.text_input(
            "API Base URL",
            value="https://api.openai.com/v1",
            help="e.g., https://api.openai.com/v1"
        )
        llm_api_key = st.sidebar.text_input(
            "API Key",
            type="password",
            help="Your OpenAI or compatible API key."
        )
        llm_model = st.sidebar.text_input(
            "Model Name",
            value="gpt-3.5-turbo",
            help="e.g., gpt-3.5-turbo, gpt-4o"
        )
else:
    llm_api_type = "ollama"
    llm_base_url = None
    llm_api_key = None
    llm_model = None

# Handle File Upload and Pipeline Initialization
if uploaded_file:
    # Save uploaded file to a temporary location to satisfy Pipeline's path requirement
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    # Initialize or update Pipeline in session state
    st.session_state.pipeline = Pipeline(
        tmp_path,
        output_folder,
        cards=anki_toggle,
        api_type=llm_api_type,
        model=llm_model,
        base_url=llm_base_url,
        api_key=llm_api_key
    )
    pipeline = st.session_state.pipeline

    # Extract TOC for section selection
    toc = get_toc(pipeline.doc)

    st.sidebar.markdown("### 📖 Select Sections")
    selected_sections = []
    # Dynamically generate checkboxes with column-based indentation to shift the widget
    for sec in toc:
        # sec format: (level, title, start_page, end_page)
        level = sec[0]
        label = f"{sec[1]} (p.{sec[2]})"

        # Use columns to push the checkbox to the right based on hierarchy level
        spacer_width = 0.12 * (level - 1)
        if spacer_width > 0:
            col1, col2 = st.sidebar.columns([spacer_width, 1 - spacer_width])
            with col2:
                if st.checkbox(label, key=f"cb_{sec[1]}"):
                    selected_sections.append(sec)
        else:
            if st.sidebar.checkbox(label, key=f"cb_{sec[1]}"):
                selected_sections.append(sec)

    st.sidebar.markdown("---")

    # Process Button
    if st.sidebar.button("🚀 Start Processing", use_container_width=True):
        with st.spinner("Processing document... This may take a while for large files."):
            try:
                # Run the pipeline
                # returns: (dtext_selected, dtext_summarized, dsum, dqa)
                results = pipeline.run(selected_sections, summarize=summarize_toggle)
                st.session_state.results = results
                st.success("Processing complete! Files have been saved to the output folder.")
            except Exception as e:
                st.error(f"An error occurred during processing: {e}")
                st.code(traceback.format_exc(), language="python")

# --- Main Content Area ---
if st.session_state.results:
    dtext_selected, dtext_summarized, dsum, dqa = st.session_state.results

    if not summarize_toggle:
        # LAYOUT: [Control Panel] [Selected Text Display]
        st.subheader("📄 Selected Sections Extraction")
        if dtext_selected:
            st.info("The formatted text of the selected sections has been extracted and is displayed below.")

            # Convert dictionary structure to a clean markdown string for display
            selected_text_md = ""
            for key, value in dtext_selected.items():
                selected_text_md += f"## {key}\n\n{flatten_text(value)}\n\n"

            st.markdown(selected_text_md)
        else:
            st.warning("No sections were selected for extraction.")
    else:
        # LAYOUT: [Control Panel] [Selected Text (Center)] [Summary (Right)]
        st.subheader("📝 Extraction & AI Summarization")

        col_text, col_sum = st.columns([2, 1])

        with col_text:
            st.markdown("### 📖 Selected Content")
            if dtext_summarized:
                selected_md = ""
                for key, value in dtext_summarized.items():
                    selected_md += f"#### {key}\n\n{flatten_text(value)}\n\n"
                st.markdown(selected_md)
            else:
                st.warning("No sections were selected for extraction.")

        with col_sum:
            st.markdown("### ⚡ AI Summary")
            if dsum:
                summaries_md = ""
                for key, summary in dsum.items():
                    summaries_md += f"**{key}**\n\n{summary}\n\n---\n\n"
                st.markdown(summaries_md)
            else:
                st.info("No summaries generated.")
else:
    # Default state when no file has been processed
    st.markdown("""
    <div style="text-align: center; margin-top: 5rem;">
        <h1>Welcome to IDLEARN</h1>
        <p style="font-size: 1.2rem; color: gray;">
            Upload a PDF or EPUB file in the sidebar, select the sections you're interested in,
            and click <b>'Start Processing'</b> to generate formatted text and AI summaries.
        </p>
    </div>
    """, unsafe_allow_html=True)
