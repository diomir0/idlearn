#========================================================================================#
#                                       IDLEARN                                          #
#                                        ui.py                                           #
#========================================================================================#

"""
IDLEARN UI — Theme definitions, CSS generation, and rendering helpers.

Provides two themes:
  - Ink & Amber   (dark, warm, scholarly, premium)
  - Brutalist     (light, raw, architectural, confrontational)

Fonts are loaded from static/fonts/ and embedded as base64 for offline use.
"""

import base64
import html as _html
from pathlib import Path
from typing import Optional

import streamlit.components.v1 as components

# ─── Font Loading ───────────────────────────────────────────────────────────────

_FONTS_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
_FONTS_CSS_CACHE: Optional[str] = None


def _load_font_css() -> str:
    """Load local font files and generate base64-embedded @font-face declarations."""
    global _FONTS_CSS_CACHE
    if _FONTS_CSS_CACHE is not None:
        return _FONTS_CSS_CACHE

    fonts = [
        ("Playfair Display", 700, "normal", "PlayfairDisplay-Bold.ttf"),
        ("Playfair Display", 800, "normal", "PlayfairDisplay-ExtraBold.ttf"),
        ("Sora", 400, "normal", "Sora-Regular.ttf"),
        ("Sora", 500, "normal", "Sora-Medium.ttf"),
        ("Sora", 600, "normal", "Sora-SemiBold.ttf"),
        ("Sora", 700, "normal", "Sora-Bold.ttf"),
    ]

    parts = []
    for family, weight, style, filename in fonts:
        filepath = _FONTS_DIR / filename
        if filepath.exists():
            data = base64.b64encode(filepath.read_bytes()).decode("ascii")
            parts.append(
                f"@font-face {{\n"
                f"  font-family: '{family}';\n"
                f"  font-style: {style};\n"
                f"  font-weight: {weight};\n"
                f"  font-display: swap;\n"
                f"  src: url(data:font/truetype;base64,{data}) format('truetype');\n"
                f"}}"
            )

    _FONTS_CSS_CACHE = "\n".join(parts)
    return _FONTS_CSS_CACHE


# ─── Theme Definitions ──────────────────────────────────────────────────────────

THEMES = {
    "ink_amber": {
        "name": "Ink & Amber",
        "description": "Warm scholarly dark theme with amber accents",
        "icon": "🌙",
        "--bg-primary":       "#0f1117",
        "--bg-secondary":     "#1a1d2e",
        "--bg-tertiary":      "#252838",
        "--bg-card":          "#1e1e2e",
        "--bg-card-hover":    "#262640",
        "--bg-sidebar":       "#13141f",
        "--bg-input":         "#1e2030",
        "--text-primary":     "#e8e6e3",
        "--text-secondary":   "#a0a0b8",
        "--text-muted":       "#6b6b8a",
        "--text-inverse":     "#0f1117",
        "--accent":           "#f0a500",
        "--accent-hover":     "#ffc233",
        "--accent-dim":       "rgba(240, 165, 0, 0.12)",
        "--accent-glow":      "rgba(240, 165, 0, 0.25)",
        "--accent-text":      "#0f1117",
        "--border":           "#2d2d44",
        "--border-light":     "#3a3a55",
        "--success":          "#6ee7b7",
        "--success-bg":       "rgba(110, 231, 183, 0.1)",
        "--error":            "#f87171",
        "--error-bg":         "rgba(248, 113, 113, 0.1)",
        "--info":             "#93c5fd",
        "--info-bg":          "rgba(147, 197, 253, 0.1)",
        "--shadow":           "0 4px 24px rgba(0, 0, 0, 0.4)",
        "--shadow-sm":        "0 2px 8px rgba(0, 0, 0, 0.3)",
        "--radius":           "12px",
        "--radius-sm":        "8px",
        "--radius-xs":        "4px",
        "--font-heading":     "'Playfair Display', Georgia, 'Times New Roman', serif",
        "--font-body":        "'Sora', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "--font-mono":        "'Sora', ui-monospace, 'Cascadia Code', 'Fira Code', monospace",
        "--heading-transform":  "none",
        "--heading-weight":    "700",
        "--heading-spacing":   "0",
        "--card-border-width": "1px",
        "--card-border-style": "solid",
    },
    "brutalist": {
        "name": "Brutalist",
        "description": "Raw architectural light theme — thick borders, no curves",
        "icon": "▪️",
        "--bg-primary":       "#f5f0e8",
        "--bg-secondary":     "#ffffff",
        "--bg-tertiary":      "#ebe5d9",
        "--bg-card":          "#ffffff",
        "--bg-card-hover":    "#faf6ef",
        "--bg-sidebar":       "#ffffff",
        "--bg-input":         "#ffffff",
        "--text-primary":     "#0a0a0a",
        "--text-secondary":   "#4a4a4a",
        "--text-muted":       "#8a8a8a",
        "--text-inverse":     "#ffffff",
        "--accent":           "#d4380d",
        "--accent-hover":     "#cf1322",
        "--accent-dim":       "rgba(212, 56, 13, 0.08)",
        "--accent-glow":      "rgba(212, 56, 13, 0.15)",
        "--accent-text":      "#ffffff",
        "--border":           "#0a0a0a",
        "--border-light":     "#cccccc",
        "--success":          "#237a32",
        "--success-bg":       "rgba(35, 122, 50, 0.08)",
        "--error":            "#d4380d",
        "--error-bg":         "rgba(212, 56, 13, 0.08)",
        "--info":             "#1d4ed8",
        "--info-bg":          "rgba(29, 78, 216, 0.08)",
        "--shadow":           "4px 4px 0 #0a0a0a",
        "--shadow-sm":        "2px 2px 0 #0a0a0a",
        "--radius":           "0px",
        "--radius-sm":        "0px",
        "--radius-xs":        "0px",
        "--font-heading":     "'Playfair Display', Georgia, 'Times New Roman', serif",
        "--font-body":        "'Sora', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        "--font-mono":        "'Sora', ui-monospace, 'Cascadia Code', 'Fira Code', monospace",
        "--heading-transform":  "uppercase",
        "--heading-weight":    "800",
        "--heading-spacing":   "0.08em",
        "--card-border-width": "3px",
        "--card-border-style": "solid",
    },
}


# ─── CSS Generation ─────────────────────────────────────────────────────────────

def _build_css_vars(theme: dict) -> str:
    """Build CSS custom property declarations from a theme dict."""
    lines = []
    for k, v in theme.items():
        if k.startswith("--"):
            lines.append(f"  {k}: {v};")
    return "\n".join(lines)


def generate_theme_css(theme_key: str) -> str:
    """Generate the full theme CSS for injection into Streamlit."""
    theme = THEMES[theme_key]
    fonts_css = _load_font_css()
    vars_css = _build_css_vars(theme)
    is_brutalist = theme_key == "brutalist"

    # ── Brutalist-specific overrides ──
    brutalist_extras = ""
    if is_brutalist:
        brutalist_extras = """
/* ── Brutalist-specific: hard shadows on cards ── */
.anki-card,
.il-section-card,
.il-feature-card {
    box-shadow: var(--shadow) !important;
}
.anki-card:hover {
    box-shadow: 6px 6px 0 #0a0a0a !important;
    transform: translate(-2px, -2px);
}
.il-feature-card:hover {
    box-shadow: 4px 4px 0 #d4380d !important;
    transform: translate(-2px, -2px);
}
/* ── Brutalist: no italic, all uppercase labels ── */
.il-card-type-badge {
    text-transform: uppercase !important;
    letter-spacing: 0.15em !important;
    font-family: var(--font-mono) !important;
}
"""

    css = f"""
{fonts_css}

/* ═══════════════════════════════════════════════════════════════════════════
   IDLEARN Theme: {theme['name']}
   ═════════════════════════════════════════════════════════════════════════ */

:root {{
{vars_css}
}}

/* ── Global Resets & Base ─────────────────────────────────────────────── */
.stApp {{
    background: var(--bg-primary) !important;
    color: var(--text-primary) !important;
    font-family: var(--font-body) !important;
}}

/* Main content area — wider layout */
.stApp > .main .block-container {{
    padding-top: 2rem;
    max-width: 1200px;
}}

/* Top header bar — blend with background, keep behind sidebar */
[data-testid="stHeader"] {{
    background: var(--bg-primary) !important;
    z-index: 998 !important;
}}
header[data-testid="stHeader"] {{
    background: var(--bg-primary) !important;
    z-index: 998 !important;
}}

/* Footer hide */
.stApp > footer {{
    display: none;
}}

/* ── Checkbox / Toggle SVG ─────────────────────────────────────────────── */
.stCheckbox svg,
.stToggle svg {{
    fill: var(--accent) !important;
}}

/* ── Sidebar close / open button ───────────────────────────────────────── */
[data-testid="stSidebar"] button[kind="header"] {{
    color: var(--text-muted) !important;
    z-index: 1001 !important;
}}
/* Sidebar toggle button in header */
[data-testid="stSidebarToggleButton"] {{
    z-index: 1001 !important;
}}
button[kind="header"] {{
    z-index: 1001 !important;
}}

/* ── Horizontal rule ───────────────────────────────────────────────────── */
hr {{
    border-color: var(--border) !important;
}}

/* ── Strong / bold text ─────────────────────────────────────────────────── */
strong, b {{
    color: var(--text-primary) !important;
}}

/* ── Links ─────────────────────────────────────────────────────────────── */
a {{
    color: var(--accent) !important;
    text-decoration: none;
}}
a:hover {{
    color: var(--accent-hover) !important;
    text-decoration: underline;
}}

/* ── Tooltip ────────────────────────────────────────────────────────────── */
.stTooltip {{
    background: var(--bg-tertiary) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
}}

/* ── Progress bar ──────────────────────────────────────────────────────── */
.stProgress > div > div > div > div {{
    background: var(--accent) !important;
}}

/* ── Typography ────────────────────────────────────────────────────────── */
h1, h2, h3, h4, h5, h6 {{
    font-family: var(--font-heading) !important;
    color: var(--text-primary) !important;
    text-transform: var(--heading-transform) !important;
    letter-spacing: var(--heading-spacing) !important;
    font-weight: var(--heading-weight) !important;
}}

h1 {{ font-size: 2.4rem !important; margin-bottom: 0.4em !important; }}
h2 {{ font-size: 1.8rem !important; margin-bottom: 0.3em !important; }}
h3 {{ font-size: 1.4rem !important; margin-bottom: 0.25em !important; }}

p, span, label, li, .stMarkdown {{
    color: var(--text-secondary) !important;
}}
/* ── Body font for text paragraphs and list items (not spans/labels — those carry icons and custom HTML) ── */
.stMarkdown p, .stMarkdown li {{
    font-family: var(--font-body) !important;
}}
/* ── Preserve icon fonts in Streamlit widgets ─────────────────────── */
[data-testid] svg,
.stButton svg,
.stFileUploader svg,
.stSelectbox svg,
.stCheckbox svg,
.stRadio svg,
.stTooltip svg {{
    font-family: unset !important;
}}
.material-symbols-outlined,
.material-symbols-rounded,
.material-icons {{
    font-family: 'Material Symbols Outlined', 'Material Symbols Rounded', 'Material Icons', sans-serif !important;
}}
/* ── Buttons: preserve text color inside buttons ─────────────────────── */
.stButton p, .stButton span,
.stButton > button p, .stButton > button span {{
    color: inherit !important;
}}

/* ── Sidebar ───────────────────────────────────────────────────────────── */
/* Overlay mode: sidebar floats above content instead of pushing it */
[data-testid="stSidebar"] {{
    background: var(--bg-sidebar) !important;
    border-right: var(--card-border-width) var(--card-border-style) var(--border) !important;
    position: fixed !important;
    z-index: 999 !important;
    height: 100vh !important;
    top: 0;
    left: 0;
    box-shadow: 6px 0 24px rgba(0, 0, 0, 0.25) !important;
}}
[data-testid="stSidebar"] > div:first-child {{
    background: var(--bg-sidebar) !important;
    height: 100vh !important;
    overflow-y: auto !important;
}}
[data-testid="stSidebar"] .stMarkdown {{
    color: var(--text-secondary) !important;
}}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {{
    color: var(--text-primary) !important;
}}
/* Sidebar section dividers */
[data-testid="stSidebar"] hr {{
    border-color: var(--border) !important;
}}

/* ── Buttons ───────────────────────────────────────────────────────────── */
.stButton > button {{
    background: var(--accent) !important;
    color: var(--accent-text) !important;
    border: 1px solid var(--accent) !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em !important;
    transition: all 0.2s ease !important;
    box-shadow: none !important;
    padding: 0.4rem 1rem !important;
    line-height: 1.4 !important;
}}
/* Button text uses body font, icons keep their own font */
.stButton > button p {{
    font-family: var(--font-body) !important;
}}
.stButton > button:hover {{
    background: var(--accent-hover) !important;
    border-color: var(--accent-hover) !important;
    transform: translateY(-1px);
    box-shadow: var(--shadow-sm) !important;
}}
.stButton > button:active {{
    transform: translateY(0);
}}
/* ── Download buttons: outlined style ─────────────────────────────────── */
.stDownloadButton > button {{
    background: transparent !important;
    color: var(--accent) !important;
    border: 2px solid var(--accent) !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 600 !important;
    padding: 0.4rem 1rem !important;
    line-height: 1.4 !important;
}}
.stDownloadButton > button p {{
    font-family: var(--font-body) !important;
}}
.stDownloadButton > button:hover {{
    background: var(--accent-dim) !important;
    color: var(--accent-hover) !important;
}}
.stDownloadButton > button p,
.stDownloadButton > button span {{
    color: inherit !important;
}}

/* ── Inputs & Selects ─────────────────────────────────────────────────── */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {{
    background: var(--bg-input) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-xs) !important;
    font-family: var(--font-body) !important;
}}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {{
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 1px var(--accent) !important;
}}
/* Input labels */
.stTextInput label,
.stTextArea label,
.stSelectbox label {{
    color: var(--text-secondary) !important;
    font-family: var(--font-body) !important;
}}

/* ── Checkboxes & Radio ────────────────────────────────────────────────── */
.stCheckbox label, .stRadio label {{
    color: var(--text-secondary) !important;
    font-family: var(--font-body) !important;
}}
.stCheckbox label:hover, .stRadio label:hover {{
    color: var(--text-primary) !important;
}}

/* ── Selectbox ─────────────────────────────────────────────────────────── */
.stSelectbox > div > div,
[data-baseweb="select"] > div {{
    background: var(--bg-input) !important;
    color: var(--text-primary) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-xs) !important;
}}
/* Selectbox text styling */
.stSelectbox label p {{
    font-family: var(--font-body) !important;
}}
/* Selectbox dropdown */
[data-baseweb="popover"] {{
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
}}
/* Selectbox dropdown items */
[data-baseweb="popover"] li {{
    color: var(--text-primary) !important;
    background: var(--bg-secondary) !important;
}}
[data-baseweb="popover"] li:hover {{
    background: var(--accent-dim) !important;
    color: var(--accent) !important;
}}

/* ── Radio buttons ─────────────────────────────────────────────────────── */
.stRadio > div {{
    color: var(--text-secondary) !important;
}}
.stRadio > div [role="radiogroup"] {{
    gap: 0.3rem !important;
}}

/* ── File Uploader ─────────────────────────────────────────────────────── */
.stFileUploader,
[data-testid="stFileUploader"] {{
    background: var(--bg-tertiary) !important;
    border: 2px dashed var(--border-light) !important;
    border-radius: var(--radius) !important;
}}
.stFileUploader:hover,
[data-testid="stFileUploader"]:hover {{
    border-color: var(--accent) !important;
}}
/* File uploader inner elements */
.stFileUploader section,
[data-testid="stFileUploader"] section,
.stFileUploader [data-testid="stFileUploaderDropzone"] {{
    background: transparent !important;
    color: var(--text-secondary) !important;
}}
.stFileUploader button,
[data-testid="stFileUploader"] button {{
    background: var(--accent) !important;
    color: var(--accent-text) !important;
    border: 1px solid var(--accent) !important;
    border-radius: var(--radius-xs) !important;
}}
/* Preserve icon fonts inside file uploader buttons — do NOT set font-family on spans */
.stFileUploader small,
.stFileUploader [data-testid="stFileUploaderDropzone"] small,
.stFileUploader [data-testid="stFileUploaderDropzone"] p {{
    color: var(--text-muted) !important;
    font-family: var(--font-body) !important;
}}
.stFileUploader p,
.stFileUploader label {{
    color: var(--text-secondary) !important;
}}
.stFileUploader [data-testid="stFileUploaderFile"] {{
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-xs) !important;
}}

/* ── Tabs ──────────────────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {{
    gap: 0 !important;
    border-bottom: 2px solid var(--border) !important;
}}
.stTabs [data-baseweb="tab"] {{
    font-family: var(--font-body) !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    border-radius: 0 !important;
    padding: 0.6rem 1.2rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    font-size: 0.85rem !important;
}}
.stTabs [aria-selected="true"] {{
    color: var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
}}
.stTabs [data-baseweb="tab"]:hover {{
    color: var(--text-primary) !important;
}}

/* ── Expanders (section cards) ─────────────────────────────────────────── */
.streamlit-expanderHeader {{
    font-family: var(--font-body) !important;
    font-weight: 600 !important;
    color: var(--text-primary) !important;
    border-radius: var(--radius-sm) !important;
}}
.streamlit-expander {{
    border: var(--card-border-width) var(--card-border-style) var(--border) !important;
    border-radius: var(--radius) !important;
    background: var(--bg-card) !important;
    overflow: hidden;
    margin-bottom: 0.8rem !important;
}}
.streamlit-expander:hover {{
    border-color: var(--accent) !important;
    box-shadow: var(--shadow-sm) !important;
}}

/* ── Alert / Status Messages ───────────────────────────────────────────── */
.stSuccess {{
    background: var(--success-bg) !important;
    color: var(--success) !important;
    border: 1px solid var(--success) !important;
    border-radius: var(--radius-sm) !important;
}}
.stError {{
    background: var(--error-bg) !important;
    color: var(--error) !important;
    border: 1px solid var(--error) !important;
    border-radius: var(--radius-sm) !important;
}}
.stInfo {{
    background: var(--info-bg) !important;
    color: var(--info) !important;
    border: 1px solid var(--info) !important;
    border-radius: var(--radius-sm) !important;
}}
.stWarning {{
    background: rgba(250, 204, 21, 0.08) !important;
    color: #facc15 !important;
    border: 1px solid #facc15 !important;
    border-radius: var(--radius-sm) !important;
}}

/* ── Dataframe ─────────────────────────────────────────────────────────── */
.stDataFrame {{
    border: var(--card-border-width) var(--card-border-style) var(--border) !important;
    border-radius: var(--radius-sm) !important;
}}

/* ── Spinner ───────────────────────────────────────────────────────────── */
.stSpinner > div {{
    border-color: var(--accent) !important;
}}

/* ── Metric ────────────────────────────────────────────────────────────── */
.stMetric {{
    background: var(--bg-card) !important;
    border: var(--card-border-width) var(--card-border-style) var(--border) !important;
    border-radius: var(--radius-sm) !important;
    padding: 0.8rem 1rem !important;
}}
.stMetric > label {{
    color: var(--text-muted) !important;
    font-family: var(--font-body) !important;
}}
.stMetric > div {{
    color: var(--accent) !important;
    font-family: var(--font-heading) !important;
}}

/* ── (Download button styles moved above with other button styles) ── */

/* ── Scrollbar ────────────────────────────────────────────────────────── */
::-webkit-scrollbar {{
    width: 8px;
    height: 8px;
}}
::-webkit-scrollbar-track {{
    background: var(--bg-secondary);
}}
::-webkit-scrollbar-thumb {{
    background: var(--border-light);
    border-radius: var(--radius-xs);
}}
::-webkit-scrollbar-thumb:hover {{
    background: var(--text-muted);
}}

/* ── Code blocks ──────────────────────────────────────────────────────── */
.stCode {{
    background: var(--bg-tertiary) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
}}
code {{
    font-family: var(--font-mono) !important;
}}

/* ═════════════════════════════════════════════════════════════════════════
   CUSTOM COMPONENTS
   ═════════════════════════════════════════════════════════════════════════ */

/* ── Welcome Screen ───────────────────────────────────────────────────── */
.il-welcome {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 70vh;
    padding: 3rem 2rem;
    position: relative;
    overflow: hidden;
}}

.il-welcome-bg {{
    position: absolute;
    inset: 0;
    z-index: 0;
    overflow: hidden;
    opacity: 0.35;
}}

.il-network-bg {{
    width: 100%;
    height: 100%;
    position: absolute;
    top: 0;
    left: 0;
}}

.il-welcome-content {{
    position: relative;
    z-index: 1;
    text-align: center;
    max-width: 720px;
}}

.il-welcome-title {{
    font-family: var(--font-heading) !important;
    font-size: 4.5rem !important;
    font-weight: 800 !important;
    color: var(--text-primary) !important;
    margin: 0 0 0.2em 0 !important;
    letter-spacing: -0.02em !important;
    text-transform: none !important;
    line-height: 1 !important;
}}

.il-welcome-accent {{
    color: var(--accent) !important;
}}

.il-welcome-subtitle {{
    font-family: var(--font-body) !important;
    font-size: 1.2rem !important;
    font-weight: 400 !important;
    color: var(--text-secondary) !important;
    margin: 0.5em 0 2.5em 0 !important;
    line-height: 1.6 !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
}}

.il-features {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1.2rem;
    width: 100%;
    max-width: 680px;
    margin: 0 auto;
}}

.il-feature-card {{
    background: var(--bg-card);
    border: var(--card-border-width) var(--card-border-style) var(--border);
    border-radius: var(--radius);
    padding: 1.6rem 1.2rem;
    text-align: center;
    transition: all 0.25s ease;
    position: relative;
    overflow: hidden;
}}
.il-feature-card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--accent);
    transform: scaleX(0);
    transition: transform 0.3s ease;
}}
.il-feature-card:hover {{
    border-color: var(--accent);
    background: var(--bg-card-hover);
    box-shadow: var(--shadow-sm);
}}
.il-feature-card:hover::before {{
    transform: scaleX(1);
}}

.il-feature-icon {{
    font-size: 2rem;
    margin-bottom: 0.5rem;
    display: block;
}}

.il-feature-title {{
    font-family: var(--font-body) !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    color: var(--text-primary) !important;
    margin-bottom: 0.3rem !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
}}

.il-feature-desc {{
    font-family: var(--font-body) !important;
    font-weight: 400 !important;
    font-size: 0.8rem !important;
    color: var(--text-muted) !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
}}

/* ── Section Cards (Summaries) ─────────────────────────────────────────── */
.il-section-card {{
    background: var(--bg-card);
    border: var(--card-border-width) var(--card-border-style) var(--border);
    border-radius: var(--radius);
    padding: 1.5rem;
    margin-bottom: 1rem;
    transition: all 0.2s ease;
    border-left: 4px solid var(--accent);
}}
.il-section-card:hover {{
    border-color: var(--accent);
    box-shadow: var(--shadow-sm);
}}

.il-section-title {{
    font-family: var(--font-heading) !important;
    font-size: 1.3rem !important;
    font-weight: 700 !important;
    color: var(--text-primary) !important;
    margin-bottom: 0.8rem !important;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border);
    text-transform: none !important;
    letter-spacing: 0 !important;
}}

.il-section-body {{
    color: var(--text-secondary);
    line-height: 1.7;
    font-size: 0.95rem;
}}

/* ── Anki Card ────────────────────────────────────────────────────────── */
.anki-card {{
    background: var(--bg-card);
    border: var(--card-border-width) var(--card-border-style) var(--border);
    border-radius: var(--radius);
    padding: 2.5rem 2.5rem 2rem 2.5rem;
    min-height: 280px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    position: relative;
    transition: all 0.3s ease;
    box-shadow: var(--shadow-sm);
    border-left: 4px solid var(--accent);
}}
.anki-card:hover {{
    box-shadow: var(--shadow);
    border-color: var(--accent);
}}

.anki-card-num {{
    position: absolute;
    top: 14px; left: 20px;
    font-size: 0.75rem;
    color: var(--text-muted);
    font-weight: 600;
    letter-spacing: 0.05em;
    font-family: var(--font-mono);
}}

.il-card-type-badge {{
    position: absolute;
    top: 14px; right: 18px;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    padding: 3px 12px;
    border-radius: var(--radius-xs);
    font-weight: 700;
    font-family: var(--font-body);
}}

.type-basic {{
    background: rgba(110, 231, 183, 0.15);
    color: var(--success);
    border: 1px solid var(--success);
}}
.type-cloze {{
    background: rgba(196, 181, 253, 0.15);
    color: #c4b5fd;
    border: 1px solid #c4b5fd;
}}

.anki-question {{
    font-family: var(--font-heading);
    font-size: 1.2rem;
    color: var(--text-primary);
    font-weight: 600;
    line-height: 1.6;
    margin-top: 0.5rem;
}}

.anki-answer {{
    margin-top: 1.2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--border);
    font-family: var(--font-body);
    font-size: 1.05rem;
    color: var(--success);
    line-height: 1.6;
}}

.anki-empty {{
    text-align: center;
    color: var(--text-muted);
    padding: 3rem;
    font-size: 1rem;
}}

/* ── Anki Navigation ──────────────────────────────────────────────────── */
.il-card-nav {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    margin: 1rem 0;
}}

.il-card-counter {{
    font-family: var(--font-body);
    font-weight: 600;
    font-size: 0.9rem;
    color: var(--text-secondary);
}}

/* ── Brand Header ──────────────────────────────────────────────────────── */
.il-brand {{
    display: flex;
    align-items: baseline;
    gap: 0.6rem;
    margin-bottom: 0.3rem;
}}
.il-brand-name {{
    font-family: var(--font-heading) !important;
    font-size: 2rem !important;
    font-weight: 800 !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.02em !important;
    text-transform: none !important;
    line-height: 1 !important;
}}
.il-brand-dot {{
    font-family: var(--font-heading) !important;
    font-size: 2rem !important;
    font-weight: 800 !important;
    color: var(--accent) !important;
    letter-spacing: -0.02em !important;
    text-transform: none !important;
    line-height: 1 !important;
}}
.il-brand-tagline {{
    font-family: var(--font-body) !important;
    font-size: 0.75rem !important;
    color: var(--text-muted) !important;
    font-weight: 400 !important;
    letter-spacing: 0.05em !important;
    text-transform: uppercase !important;
    margin-bottom: 1.5rem !important;
}}

/* ── Sidebar Section Headers ──────────────────────────────────────────── */
.il-sidebar-section {{
    font-family: var(--font-body) !important;
    font-size: 0.7rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.12em !important;
    color: var(--accent) !important;
    margin-top: 1.2rem !important;
    margin-bottom: 0.3rem !important;
    padding-bottom: 0.3rem !important;
    border-bottom: 1px solid var(--border) !important;
}}

/* ── Theme Switcher ────────────────────────────────────────────────────── */
.il-theme-row {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
}}
.il-theme-label {{
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text-muted);
}}

/* ── Section Image Grid ────────────────────────────────────────────────── */
.il-img-grid {{
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 1rem;
    margin-top: 1rem;
}}
.il-img-cell {{
    border: var(--card-border-width) var(--card-border-style) var(--border);
    border-radius: var(--radius-sm);
    overflow: hidden;
    background: var(--bg-tertiary);
}}
.il-img-caption {{
    padding: 0.5rem 0.8rem;
    font-size: 0.8rem;
    color: var(--text-muted);
    font-family: var(--font-body);
    border-top: 1px solid var(--border);
}}

/* ── Knowledge Graph ───────────────────────────────────────────────────── */
.il-kg-header {{
    font-family: var(--font-heading) !important;
    font-size: 1.5rem !important;
    color: var(--text-primary) !important;
    text-transform: none !important;
    letter-spacing: 0 !important;
}}
.il-kg-stats {{
    display: flex;
    gap: 1.5rem;
    margin-bottom: 1.5rem;
}}
.il-kg-stat {{
    background: var(--bg-card);
    border: var(--card-border-width) var(--card-border-style) var(--border);
    border-radius: var(--radius-sm);
    padding: 1rem 1.5rem;
    text-align: center;
}}
.il-kg-stat-value {{
    font-family: var(--font-heading);
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--accent);
}}
.il-kg-stat-label {{
    font-size: 0.75rem;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.1em;
}}

{brutalist_extras}
"""
    return css


# ─── Rendering Helpers ───────────────────────────────────────────────────────────

def render_welcome_screen() -> str:
    """Return the HTML for the welcome/empty-state screen."""
    return """
<div class="il-welcome">
    <div class="il-welcome-bg">
        <svg viewBox="0 0 800 600" xmlns="http://www.w3.org/2000/svg" class="il-network-bg">
            <defs>
                <radialGradient id="nodeGrad" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.6"/>
                    <stop offset="100%" stop-color="var(--accent)" stop-opacity="0.1"/>
                </radialGradient>
            </defs>
            <!-- connections -->
            <line x1="120" y1="80" x2="260" y2="170" stroke="var(--accent)" stroke-opacity="0.12" stroke-width="1"/>
            <line x1="260" y1="170" x2="420" y2="110" stroke="var(--accent)" stroke-opacity="0.10" stroke-width="1"/>
            <line x1="260" y1="170" x2="380" y2="290" stroke="var(--accent)" stroke-opacity="0.14" stroke-width="1"/>
            <line x1="420" y1="110" x2="560" y2="190" stroke="var(--accent)" stroke-opacity="0.11" stroke-width="1"/>
            <line x1="380" y1="290" x2="560" y2="190" stroke="var(--accent)" stroke-opacity="0.13" stroke-width="1"/>
            <line x1="380" y1="290" x2="260" y2="420" stroke="var(--accent)" stroke-opacity="0.09" stroke-width="1"/>
            <line x1="560" y1="190" x2="700" y2="130" stroke="var(--accent)" stroke-opacity="0.10" stroke-width="1"/>
            <line x1="560" y1="190" x2="650" y2="350" stroke="var(--accent)" stroke-opacity="0.12" stroke-width="1"/>
            <line x1="120" y1="80" x2="80" y2="250" stroke="var(--accent)" stroke-opacity="0.08" stroke-width="1"/>
            <line x1="80" y1="250" x2="260" y2="420" stroke="var(--accent)" stroke-opacity="0.10" stroke-width="1"/>
            <line x1="260" y1="420" x2="450" y2="480" stroke="var(--accent)" stroke-opacity="0.11" stroke-width="1"/>
            <line x1="650" y1="350" x2="450" y2="480" stroke="var(--accent)" stroke-opacity="0.09" stroke-width="1"/>
            <line x1="700" y1="130" x2="740" y2="320" stroke="var(--accent)" stroke-opacity="0.07" stroke-width="1"/>
            <line x1="740" y1="320" x2="650" y2="350" stroke="var(--accent)" stroke-opacity="0.08" stroke-width="1"/>
            <line x1="420" y1="110" x2="380" y2="290" stroke="var(--accent)" stroke-opacity="0.10" stroke-width="1"/>
            <line x1="80" y1="250" x2="260" y2="170" stroke="var(--accent)" stroke-opacity="0.09" stroke-width="1"/>
            <!-- nodes -->
            <circle cx="120" cy="80" r="6" fill="url(#nodeGrad)"/>
            <circle cx="260" cy="170" r="8" fill="url(#nodeGrad)"/>
            <circle cx="420" cy="110" r="5" fill="url(#nodeGrad)"/>
            <circle cx="380" cy="290" r="7" fill="url(#nodeGrad)"/>
            <circle cx="560" cy="190" r="9" fill="url(#nodeGrad)"/>
            <circle cx="700" cy="130" r="5" fill="url(#nodeGrad)"/>
            <circle cx="650" cy="350" r="6" fill="url(#nodeGrad)"/>
            <circle cx="260" cy="420" r="7" fill="url(#nodeGrad)"/>
            <circle cx="450" cy="480" r="5" fill="url(#nodeGrad)"/>
            <circle cx="80" cy="250" r="4" fill="url(#nodeGrad)"/>
            <circle cx="740" cy="320" r="4" fill="url(#nodeGrad)"/>
        </svg>
    </div>
    <div class="il-welcome-content">
        <h1 class="il-welcome-title">idlearn<span class="il-welcome-accent">.</span></h1>
        <p class="il-welcome-subtitle">
            Transform your documents into structured knowledge.<br>
            Summaries, flashcards, and concept maps — powered by local AI.
        </p>
        <div class="il-features">
            <div class="il-feature-card">
                <span class="il-feature-icon">📋</span>
                <div class="il-feature-title">Summarize</div>
                <div class="il-feature-desc">Multimodal LLM summaries with figure understanding</div>
            </div>
            <div class="il-feature-card">
                <span class="il-feature-icon">🃏</span>
                <div class="il-feature-title">Flashcards</div>
                <div class="il-feature-desc">Auto-generated Anki decks for active recall</div>
            </div>
            <div class="il-feature-card">
                <span class="il-feature-icon">🕸️</span>
                <div class="il-feature-title">Knowledge Graph</div>
                <div class="il-feature-desc">Concept maps and relationships from your text</div>
            </div>
        </div>
    </div>
</div>
"""


def render_anki_card_html(card: dict, index: int, total: int, show_answer: bool) -> str:
    """Render a single Anki card as styled HTML."""
    card_type_label = "Cloze" if card["is_cloze"] else "Basic"
    card_type_class = "type-cloze" if card["is_cloze"] else "type-basic"

    answer_html = ""
    if show_answer:
        answer_html = f'<div class="anki-answer">{card["answer"]}</div>'

    return f"""
    <div class="anki-card">
        <span class="anki-card-num">Card {index + 1} / {total} — {card["section"]}</span>
        <span class="il-card-type-badge {card_type_class}">{card_type_label}</span>
        <div class="anki-question">{card["question"]}</div>
        {answer_html}
    </div>
    """


def render_mermaid(mermaid_code: str, height: int = 500) -> None:
    """Render a Mermaid diagram as an interactive HTML component.

    The Mermaid source is injected via JavaScript (json.dumps) instead
    of HTML-escaping into a <pre> tag.  This avoids double-encoding:
    html.escape() would turn Mermaid syntax chars like ">" (in -->)
    and '"' (in ["label"]) into HTML entities that may not be
    reliably decoded before Mermaid parses the element.

    Uses htmlLabels: false because htmlLabels: true triggers dagre's
    "Could not find a suitable point for the given distance" error
    on many graph topologies due to bounding-box miscalculation.

    Includes error handling so a layout failure falls back to a
    text-based concept/relationship view.
    """
    import json as _json
    js_code = _json.dumps(mermaid_code)  # safe JS string literal
    html_doc = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
  <style>
    body {{
      margin: 0; padding: 1rem;
      background: transparent;
      font-family: 'Sora', sans-serif;
    }}
    .mermaid {{
      display: flex;
      justify-content: center;
    }}
    .mermaid-fallback {{
      font-family: 'Sora', sans-serif;
      font-size: 0.9rem;
      line-height: 1.6;
      padding: 1rem;
    }}
    .mermaid-fallback h3 {{
      margin: 0 0 0.5rem 0;
      font-size: 1rem;
    }}
    .mermaid-fallback ul {{
      margin: 0.25rem 0;
      padding-left: 1.5rem;
    }}
    .mermaid-fallback li {{
      margin: 0.15rem 0;
    }}
    .mermaid-fallback .edge {{
      color: #888;
    }}
    .mermaid-fallback .edge-arrow {{
      color: var(--accent, #f0a500);
    }}
  </style>
</head>
<body>
  <pre class="mermaid" id="mermaid-graph"></pre>
  <script>
    document.getElementById('mermaid-graph').textContent = {js_code};
    mermaid.initialize({{
      startOnLoad: false,
      securityLevel: 'loose',
      flowchart: {{
        useMaxWidth: true,
        htmlLabels: false,
        curve: 'basis',
        padding: 20,
        nodeSpacing: 30,
        rankSpacing: 50
      }}
    }});
    mermaid.run().catch(function(err) {{
      // dagre can throw layout errors ("Could not find a suitable point…")
      // on certain graph topologies.  Fall back to a text view.
      var container = document.getElementById('mermaid-graph');
      container.textContent = '';
      container.className = 'mermaid-fallback';
      // Parse the Mermaid source into a simple text graph view
      var src = {js_code};
      var nodes = [];
      var edges = [];
      src.split('\\n').forEach(function(line) {{
        var m;
        if ((m = line.match(/^\\s*(\\S+)\\["(.+?)"\\]\\s*$/))) {{
          nodes.push({{id: m[1], label: m[2]}});
        }} else if ((m = line.match(/^\\s*(\\S+)\\s*--\\>\\|(.+?)\\|\\s*(\\S+)/))) {{
          edges.push({{from: m[1], label: m[2], to: m[3]}});
        }} else if ((m = line.match(/^\\s*(\\S+)\\s*--\\>\\s*(\\S+)/))) {{
          edges.push({{from: m[1], label: '', to: m[2]}});
        }}
      }});
      var nodeMap = {{}};
      nodes.forEach(function(n) {{ nodeMap[n.id] = n.label; }});
      var html = '<h3>\u26A1 Graph visualization could not be rendered</h3>'
        + '<p style="color:#888">Showing text view instead.</p>';
      nodes.forEach(function(n) {{
        html += '<div style="margin:0.5rem 0"><strong>' + n.label + '</strong></div>';
      }});
      if (edges.length) {{
        html += '<hr style="border:none;border-top:1px solid #444;margin:1rem 0">';
        edges.forEach(function(e) {{
          var fromLabel = nodeMap[e.from] || e.from;
          var toLabel = nodeMap[e.to] || e.to;
          html += '<div class="edge"><span class="edge-arrow">\u2192</span> '
            + fromLabel
            + (e.label ? ' \u2014 <em>' + e.label + '</em> \u2192 ' : ' \u2192 ')
            + toLabel + '</div>';
        }});
      }}
      container.innerHTML = html;
    }});
  </script>
</body>
</html>"""
    components.html(html_doc, height=height, scrolling=True)


def render_kg_stats(concepts_count: int, relations_count: int, title: str = "") -> str:
    """Render the knowledge graph stats row."""
    title_html = f'<span>{title}</span>' if title else ''
    return f"""
<div class="il-kg-stats">
    <div class="il-kg-stat">
        <div class="il-kg-stat-value">{concepts_count}</div>
        <div class="il-kg-stat-label">Concepts</div>
    </div>
    <div class="il-kg-stat">
        <div class="il-kg-stat-value">{relations_count}</div>
        <div class="il-kg-stat-label">Relationships</div>
    </div>
</div>
    """


def section_card_html(title: str, body_html: str) -> str:
    """Render a section summary as a styled card."""
    return f"""
<div class="il-section-card">
    <div class="il-section-title">{title}</div>
    <div class="il-section-body">{body_html}</div>
</div>
    """
