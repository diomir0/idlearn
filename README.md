# IDLEARN

**IDLEARN** is an open-source educational tool that helps students and researchers learn more efficiently from long-form documents like PDFs and EPUBs. It automatically extracts content and images, generates comprehensive summaries using multimodal LLMs, creates question-answer pairs, and builds Anki flashcard decks — so you can focus on learning instead of manual note-taking.

All processing can happen locally on your machine using [Ollama](https://ollama.com/), meaning your documents never leave your computer. You can also connect to OpenAI-compatible cloud APIs if you prefer.

---

## 🎯 What IDLEARN Does

1. **Extracts text and images** from PDF and EPUB files, using the document's Table of Contents (ToC) to structure content into sections. Filters out watermarks, footnotes, title pages, and running headers/footers. Extracts relevant figures for multimodal summarization.
2. **Generates comprehensive summaries** using a multimodal LLM that can process both text and images. Summaries capture all nuances, key concepts, and figure descriptions — not just brief bullet points.
3. **Creates question-answer pairs** (5 per section) for active recall practice.
4. **Builds Anki decks** (`.apkg` files) with both Basic and Cloze card models, choosing the appropriate type based on whether the answer contains quantitative data.
5. **Exports Obsidian notes** focused on the summary digest with figure references, saved to `~/Documents/obsidian/` by default.
6. **Caches results** so that previously processed sections are not re-generated, saving time and API calls.
7. **Knowledge graph** *(planned)* — Extracts concepts and their relationships from summaries into a structured graph exportable to Mermaid, Obsidian Canvas, and GraphML.

---

## 🛠️ How It Works

IDLEARN is built around a modular pipeline (`app/pipeline.py`):

| Step | Module | Description |
|------|--------|-------------|
| **Text Extraction** | `app/text_extractor.py` | Uses PyMuPDF to extract structured text from PDFs/EPUBs, guided by the ToC. Filters out watermarks, footnotes, title pages, and running headers/footers. |
| **Image Extraction** | `app/text_extractor.py` | Extracts relevant images from PDF pages for each section, filtering out watermarks, logos, and tiny decorative images. |
| **ToC Extraction** | `app/toc_extractor.py` | Extracts or infers the Table of Contents from PDFs and EPUBs. Falls back to font-analysis heuristics when no built-in ToC exists. |
| **Tokenization** | `app/tokenizer.py` | A `SmartTokenizer` splits long texts at semantic boundaries (paragraphs, sentence ends) rather than arbitrary character limits, preserving context. |
| **Multimodal Summarization** | `app/pipeline.py` → `recursive_summarize()` | Texts exceeding ~3 000 tokens are segmented, summarized individually, and recursively combined. Extracted images are included for multimodal models. |
| **LLM Integration** | `app/llmmodel.py` | Interfaces with multimodal LLMs via Ollama (local or cloud) or any OpenAI-compatible API. Supports vision models (e.g., `gemma3:4b`, `llava`). |
| **Card Generation** | `app/cg.py` | Uses `genanki` to create Anki decks, automatically choosing between Basic and Cloze card models. |
| **Output Formatting** | `app/utils.py` | Writes structured Markdown files with summaries, key concepts, figures, and Q&A. |
| **Caching** | `app/utils.py` → `IdlearnCache` | Persists summaries and Q&A to `.cache/cache.json` so they survive restarts. |

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **Ollama** (for local LLM inference): [Download and install Ollama](https://ollama.com/), then pull a multimodal model:
  ```bash
  ollama pull gemma3:4b
  ```
  For better quality (at the cost of more resources), you can use `gemma3:12b` or `llava:13b`.
- **Conda** (recommended): [Miniconda](https://docs.conda.io/en/latest/miniconda.html) or [Anaconda](https://www.anaconda.com/)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/diomir0/idlearn.git
   cd idlearn
   ```

2. **Create and activate the Conda environment:**
   ```bash
   conda env create -f environment.yml
   conda activate idlearn
   ```

   Or, if you prefer `pip`:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

IDLEARN offers two interfaces:

#### Desktop GUI (customtkinter)

```bash
python main.py
```

A dark-themed window will open. Here's how to use it:

1. **Choose file** — Click the button and select a PDF or EPUB file.
2. **Choose destination folder** — Select where the output files will be saved.
3. **Select sections** — The "File Metadata" pane on the right shows the document's Table of Contents. Check the boxes next to the sections you want to process.
4. **Toggle options**:
   - **Summarize** (on by default) — Enables LLM-based summarization and Q&A generation. Turn it off if you only want the full-text Markdown export.
   - **Anki cards** — When enabled, an `.apkg` deck is generated alongside the Markdown output.
5. **Click Run** — Processing runs in a background thread so the GUI stays responsive. Results are saved to your chosen output folder.

#### Web Interface (Streamlit)

```bash
streamlit run web_app.py
```

This opens a browser-based interface where you can:

1. **Upload a PDF or EPUB** via the sidebar.
2. **Set the output folder** path.
3. **Choose LLM provider** — Ollama (local/cloud) or OpenAI-compatible API, and configure the model name, host URL, and optional API key.
4. **Toggle summarization and Anki card generation**.
5. **Select sections** from the dynamically generated ToC checkboxes.
6. **Click "Start Processing"** — Summaries and Q&A appear in the main panel; files are saved to the output folder.

---

## ⚙️ LLM Configuration

IDLEARN supports two LLM backends:

| Provider | Default Model | Default URL | Notes |
|----------|--------------|-------------|-------|
| **Ollama** | `gemma3:4b` | `http://localhost:11434` | Runs locally. No API key needed for local instances. Supports multimodal (vision) models for figure-aware summarization. |
| **OpenAI** | `gpt-4o` | `https://api.openai.com/v1` | Requires an API key. Supports vision models for multimodal summarization. Compatible with any OpenAI-style endpoint (e.g., Azure OpenAI, Together AI). |

In the **GUI**, these are configured when creating the `Pipeline` object (the model defaults to Ollama with `gemma3:4b`, a multimodal model).

In the **Web app**, you can select the provider and enter credentials directly in the sidebar.

---

## 📁 Project Structure

```
idlearn/
├── main.py              # Desktop GUI entry point
├── web_app.py           # Streamlit web interface
├── environment.yml      # Conda environment specification
├── requirements.txt      # pip dependencies
├── README.md
├── app/
│   ├── __init__.py      # Version info
│   ├── config.py        # Global configuration (deck_id)
│   ├── pipeline.py      # Main processing pipeline
│   ├── text_extractor.py # Structured text extraction from PDFs/EPUBs
│   ├── toc_extractor.py  # Automatic ToC extraction & inference
│   ├── tokenizer.py     # SmartTokenizer, TokenEstimator, HierarchicalSegmenter
│   ├── formatter.py     # TextFormatter for Markdown output
│   ├── llmmodel.py      # LLM interface (Ollama + OpenAI)
│   ├── cg.py            # Anki card generation
│   ├── gui.py           # customtkinter GUI
│   ├── knowledge_graph.py # Knowledge graph data structures and stubs (planned)
│   ├── utils.py          # Caching, ToC helpers, Markdown writers
│   ├── logger.py        # Logging configuration
│   └── obsidize/        # Obsidian export add-on (template engine)
│       ├── __init__.py      # Public API
│       ├── engine.py        # clip_pdf(), compile_template(), load_template()
│       ├── types.py        # Dataclasses (Template, PdfContent, etc.)
│       ├── tokenizer.py    # Template string → Token stream
│       ├── parser.py       # Token stream → AST
│       ├── renderer.py     # AST → rendered string
│       ├── resolver.py     # Variable resolution
│       ├── shared.py       # Frontmatter, variable building, sanitization
│       ├── filters/        # 51 template filters
│       └── templates/      # Built-in Obsidian templates
├── templates/              # User Obsidian templates (optional, for custom templates)
├── old/                 # Archived prototype scripts and notebooks
├── cache/               # Runtime cache (auto-created)
└── logs/                # Log files (auto-created)
```

---

## 📝 Obsidian Export

IDLEARN includes **Obsidize**, a built-in Obsidian export engine that converts extracted PDF content into structured Obsidian notes using templates compatible with the [Obsidian Web Clipper](https://github.com/obsidianmd/obsidian-clipper) format.

### Quick Start

```python
from app.pipeline import Pipeline

p = Pipeline("paper.pdf", "./output", cards=False)
result = p.run(p.text_extractor.toc, summarize=True)
# Export the summary digest to Obsidian (default template: idlearn-summary)
obs_result = p.export_obsidian(template="idlearn-summary")
print(obs_result.full_content)  # Comprehensive digest with figures
```

### Built-in Templates

| Template | ID | Description |
|----------|----|-------------|
| **Summary Digest (IDLEARN)** | `idlearn-summary` | Comprehensive summary digest with key concepts, figures, and Q&A. Best for multimodal summarization. **(Default)** |
| Study Notes (IDLEARN) | `idlearn-study-notes` | Full study notes with sections, summaries, and Q&A from idlearn processing |
| Flashcard Review (IDLEARN) | `idlearn-flashcard-review` | Compact review with summary tips and Q&A callouts for self-testing |
| Academic Paper (IDLEARN) | `idlearn-academic` | Academic paper with structured idlearn content extraction |
| Academic Paper | `academic` | Academic paper with metadata callout and full content |
| Default PDF Note | `default` | Simple note with title and content |

> **Tip:** The `idlearn-summary` template is the recommended default for exporting multimodal summaries. It focuses on the comprehensive digest rather than the full extracted text, and includes figure references from extracted images.

> **Tip:** Templates with **(IDLEARN)** in the name use the `{{sections}}`, `{{summaries}}`, and `{{qa_pairs}}` variables, and produce the richest output when summarization is enabled.

### IDLEARN-Specific Template Variables

In addition to standard variables (`{{title}}`, `{{author}}`, `{{content}}`, etc.), the export provides:

| Variable | Type | Description |
|----------|------|-------------|
| `{{sections}}` | JSON array | Extracted sections: `[{title, content, index}]` |
| `{{summaries}}` | JSON array | LLM summaries: `[{title, summary, index}]` |
| `{{qa_pairs}}` | JSON array | Q\u0026A pairs: `[{title, qa, index}]` |

Use these in templates with `{% for section in sections %}` loops.

### Custom Templates

Place `.json` template files in either:
- `~/.config/idlearn/templates/`
- `./templates/` (in the project root)

Templates use the [Obsidian Web Clipper format](https://help.obsidian.md/web-clipper/templates) with full filter support (51 filters including `date`, `split`, `join`, `callout`, `wikilink`, etc.).

You can also add a `"description"` field to your template JSON to show a short description in the UI template selector.

### Obsidian Vault Integration

Both the desktop GUI and Streamlit web app support saving exported notes directly into an Obsidian vault:

- **Desktop GUI**: Check "Export to Obsidian", then use the "Vault" field (type or browse) to set your vault folder path.
- **Streamlit**: Enter your vault path in the "Obsidian Vault Path" field in the sidebar.

When a vault path is set, the exported `.md` file is written there instead of the default output folder.

### Template Preview and Upload (Streamlit)

In the Streamlit web app:
- **Template Preview**: Expand the \U0001f50d Template Preview section to see the template's properties and content format before exporting.
- **Upload Custom Template**: Upload a `.json` template file directly from the sidebar. The uploaded template is used for the current session only.

### Programmatic API

```python
from app.obsidize import compile_template, clip_pdf, load_template, PdfContent, PdfMetadata

# Compile a template string
result = compile_template('Hello {{name|upper}}!', {'{{name}}': 'world'})
# → "Hello WORLD!"

# Load a template and clip PDF content
template = load_template('academic')
pdf = PdfContent(text='...', metadata=PdfMetadata(title='My Paper', author='Author'), ...)
result = clip_pdf(pdf, template)
```

---

## ⚠️ Limitations

- **ToC dependency**: Text extraction relies on the document's Table of Contents to identify sections. While IDLEARN can automatically infer a ToC from heading patterns and font sizes when none is embedded, the results may be imperfect for documents with unusual formatting.
- **PDF layout sensitivity**: Complex multi-column layouts, interleaved tables, or unusual font arrangements can cause fragmented or out-of-order text extraction.
- **EPUB support**: EPUB extraction parses the navigation file (NCX/NAV) or falls back to HTML heading analysis. Not all EPUBs use well-structured navigation markup.
- **Hardware requirements**: Local LLM inference with Ollama requires sufficient RAM and, ideally, a GPU. Models like `mistral:7B-instruct` need roughly 5–8 GB of memory. Performance will be slow on CPU-only systems.
- **Processing time**: Nested summarization means long sections may require multiple LLM passes. A 20-page section can take several minutes on consumer hardware.
- **LLM output quality**: Summaries and Q&A quality depend on the model used. Smaller models may produce less accurate or less concise results.
- **Anki Cloze cards**: When a Q&A pair is classified as quantitative, the card is created with `genanki.CLOZE_MODEL`, but the Cloze deletion fields are currently left as `[None, None]`. This means Cloze cards will need manual editing in Anki to be useful. Future versions will improve automatic Cloze generation.
- **No progress indicator in GUI**: The desktop GUI does not currently show a progress bar during processing — only console logs indicate progress.

---

## 📜 License

Open-source. Feel free to contribute!