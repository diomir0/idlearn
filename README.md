# IDLEARN

**IDLEARN** is an open-source educational tool that helps students and researchers learn more efficiently from long-form documents like PDFs and EPUBs. It automatically extracts content, generates concise summaries with key concepts, creates question-answer pairs, and builds Anki flashcard decks — so you can focus on learning instead of manual note-taking.

All processing can happen locally on your machine using [Ollama](https://ollama.com/), meaning your documents never leave your computer. You can also connect to OpenAI-compatible cloud APIs if you prefer.

---

## 🎯 What IDLEARN Does

1. **Extracts text** from PDF and EPUB files, using the document's Table of Contents (ToC) to structure content into sections. If no ToC is found, it automatically infers one from font sizes and heading patterns.
2. **Generates summaries** with key-concept bullet points for each section you select, using a nested summarization strategy that prevents hallucinations on long texts.
3. **Creates question-answer pairs** (5 per section) for active recall practice.
4. **Builds Anki decks** (`.apkg` files) with both Basic and Cloze (fill-in-the-blank) card models, choosing the appropriate type based on whether the answer contains quantitative data.
5. **Exports Markdown files**: one with the full extracted text, and another with summaries, key concepts, and Q&A organized by section.
6. **Caches results** so that previously processed sections are not re-generated, saving time and API calls.

---

## 🛠️ How It Works

IDLEARN is built around a modular pipeline (`app/pipeline.py`):

| Step | Module | Description |
|------|--------|-------------|
| **Text Extraction** | `app/text_extractor.py` | Uses PyMuPDF to extract structured text from PDFs/EPUBs, guided by the ToC. |
| **ToC Extraction** | `app/toc_extractor.py` | Extracts or infers the Table of Contents from PDFs and EPUBs. Falls back to font-analysis heuristics when no built-in ToC exists. |
| **Tokenization** | `app/tokenizer.py` | A `SmartTokenizer` splits long texts at semantic boundaries (paragraphs, sentence ends) rather than arbitrary character limits, preserving context. |
| **Nested Summarization** | `app/pipeline.py` → `recursive_summarize()` | Texts exceeding ~3 000 tokens are segmented, summarized individually, and those summaries are recursively combined until a final concise version is reached. |
| **LLM Integration** | `app/llmmodel.py` | Interfaces with LLMs via Ollama (local or cloud) or any OpenAI-compatible API. |
| **Card Generation** | `app/cg.py` | Uses `genanki` to create Anki decks, automatically choosing between Basic and Cloze card models. |
| **Output Formatting** | `app/utils.py` | Writes structured Markdown files with summaries, key concepts, and Q&A. |
| **Caching** | `app/utils.py` → `IdlearnCache` | Persists summaries and Q&A to `.cache/cache.json` so they survive restarts. |

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **Ollama** (for local LLM inference): [Download and install Ollama](https://ollama.com/), then pull a model:
  ```bash
  ollama pull mistral:7B-instruct
  ```
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
   pip install pymupdf customtkinter genanki streamlit ollama requests numpy
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
| **Ollama** | `mistral:7B-instruct` | `http://localhost:11434` | Runs locally. No API key needed for local instances. Set a custom URL for cloud-hosted Ollama. |
| **OpenAI** | `gpt-3.5-turbo` | `https://api.openai.com/v1` | Requires an API key. Compatible with any OpenAI-style endpoint (e.g., Azure OpenAI, Together AI). |

In the **GUI**, these are configured when creating the `Pipeline` object (the model defaults to Ollama with `mistral:7B-instruct`).

In the **Web app**, you can select the provider and enter credentials directly in the sidebar.

---

## 📁 Project Structure

```
idlearn/
├── main.py              # Desktop GUI entry point
├── web_app.py           # Streamlit web interface
├── environment.yml      # Conda environment specification
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
│   ├── utils.py         # Caching, ToC helpers, Markdown writers
│   └── logger.py        # Logging configuration
├── old/                 # Archived prototype scripts and notebooks
├── cache/               # Runtime cache (auto-created)
└── logs/                # Log files (auto-created)
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