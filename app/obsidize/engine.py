# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                      engine.py                                         #
# ========================================================================================#
"""
Public API for the Obsidize template engine.
Ported from obsidize/src/api.ts.

This module provides the main entry points:
- compile_template() — Compile a template string with variables
- clip_pdf() — Process a PDF with a template to produce an Obsidian note
"""

import json
import os
from typing import Any

from .types import (
    Template, Property, PdfContent, ClipPdfResult,
)
from .shared import (
    build_pdf_variables, build_pdf_variables_from_content,
    generate_frontmatter, format_property_value, sanitize_file_name,
    clean_pdf_text,
)
from .renderer import render_template


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------

def load_template(template_path: str) -> Template:
    """
    Load a template from a JSON file.

    Args:
        template_path: Path to a JSON template file (Obsidian Web Clipper format)

    Returns:
        Template dataclass

    Raises:
        FileNotFoundError: If the template file doesn't exist
        ValueError: If the template JSON is invalid
    """
    # If template_path looks like a name (no path separators, no .json extension), resolve it
    if os.path.sep not in template_path and '/' not in template_path and not template_path.endswith('.json'):
        template_path = resolve_template_name(template_path)

    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Template file not found: {template_path}")

    with open(template_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return _parse_template_data(data)


def load_template_from_string(template_json: str) -> Template:
    """
    Load a template from a JSON string.

    Args:
        template_json: JSON string in Obsidian Web Clipper template format

    Returns:
        Template dataclass
    """
    data = json.loads(template_json)
    return _parse_template_data(data)


def _parse_template_data(data: dict) -> Template:
    """Parse a template dictionary into a Template dataclass."""
    properties = []
    for prop_data in data.get("properties", []):
        properties.append(Property(
            name=prop_data.get("name", ""),
            value=prop_data.get("value", ""),
            type=prop_data.get("type", "text"),
        ))

    return Template(
        id=data.get("id", ""),
        name=data.get("name", ""),
        behavior=data.get("behavior", "create"),
        note_name_format=data.get("noteNameFormat", "{{title}}"),
        path=data.get("path", ""),
        note_content_format=data.get("noteContentFormat", "{{content}}"),
        properties=properties,
        triggers=data.get("triggers", []),
        vault=data.get("vault", ""),
    )


# ---------------------------------------------------------------------------
# Built-in template resolution
# ---------------------------------------------------------------------------

_BUILTIN_TEMPLATES = {
    "default": "default.json",
    "academic": "academic.json",
    "idlearn-academic": "idlearn-academic.json",
    "idlearn-study-notes": "idlearn-study-notes.json",
    "idlearn-flashcard-review": "idlearn-flashcard-review.json",
    "idlearn-summary": "idlearn-summary.json",
}

# Reverse mapping: template "id" field (from JSON) → built-in key
# This allows load_template("default-pdf") to resolve just like load_template("default")
_BUILTIN_ID_TO_KEY = {}
_templates_dir = os.path.join(os.path.dirname(__file__), "templates")
for _key, _fname in _BUILTIN_TEMPLATES.items():
    _fpath = os.path.join(_templates_dir, _fname)
    if os.path.exists(_fpath):
        try:
            with open(_fpath, 'r', encoding='utf-8') as _f:
                _data = json.load(_f)
            _tid = _data.get('id', '')
            if _tid and _tid != _key:
                _BUILTIN_ID_TO_KEY[_tid] = _key
        except (json.JSONDecodeError, OSError):
            pass

del _templates_dir, _key, _fname, _fpath, _f, _data, _tid

# User template directories (checked in order)
_USER_TEMPLATE_DIRS = [
    os.path.join(os.getcwd(), "templates"),
]


def resolve_template_name(name: str) -> str:
    """Resolve a template name to a file path.

    Resolution order:
    1. User template directories (~/.config/idlearn/templates/, ./templates/)
    2. Built-in templates by key name (e.g. "academic") or by id (e.g. "academic-pdf")
    3. Treat as a file path
    """
    filename = f"{name}.json" if not name.endswith('.json') else name

    # 1. Check user template directories
    for user_dir in _USER_TEMPLATE_DIRS:
        user_path = os.path.join(user_dir, filename)
        if os.path.exists(user_path):
            return user_path

    # 2. Check built-in templates (by key or by id)
    lookup_name = name
    if name not in _BUILTIN_TEMPLATES and name in _BUILTIN_ID_TO_KEY:
        lookup_name = _BUILTIN_ID_TO_KEY[name]
    if lookup_name in _BUILTIN_TEMPLATES:
        templates_dir = os.path.join(os.path.dirname(__file__), "templates")
        return os.path.join(templates_dir, _BUILTIN_TEMPLATES[lookup_name])

    # 3. Treat as a file path
    return os.path.abspath(name)


def _read_template_metadata(filepath: str) -> dict[str, str]:
    """Read lightweight metadata from a template JSON file.

    Returns a dict with 'name', 'id', and 'description' keys.
    Falls back to filename-derived values if the file can't be read.
    """
    basename = os.path.basename(filepath)
    fallback_name = basename[:-5] if basename.endswith('.json') else basename
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {
            "name": data.get("name", fallback_name),
            "id": data.get("id", fallback_name),
            "description": data.get("description", ""),
        }
    except (json.JSONDecodeError, OSError):
        return {
            "name": fallback_name,
            "id": fallback_name,
            "description": "",
        }


def list_templates() -> list[dict[str, str]]:
    """List all available templates (built-in and user).

    Returns a list of dicts with keys:
        - name: display name of the template
        - id: template identifier
        - path: full path to the template file
        - source: "builtin" or "user"
        - description: short description of the template (may be empty)
    """
    templates = []

    # Built-in templates
    builtin_dir = os.path.join(os.path.dirname(__file__), "templates")
    for name, filename in _BUILTIN_TEMPLATES.items():
        filepath = os.path.join(builtin_dir, filename)
        meta = _read_template_metadata(filepath)
        templates.append({
            "name": meta["name"],
            "id": meta["id"],
            "description": meta["description"],
            "path": filepath,
            "source": "builtin",
        })

    # User templates from user directories
    for user_dir in _USER_TEMPLATE_DIRS:
        if os.path.isdir(user_dir):
            for filename in os.listdir(user_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(user_dir, filename)
                    meta = _read_template_metadata(filepath)
                    # Avoid duplicating built-in names
                    if meta["id"] not in {t["id"] for t in templates}:
                        templates.append({
                            "name": meta["name"],
                            "id": meta["id"],
                            "description": meta["description"],
                            "path": filepath,
                            "source": "user",
                        })

    return templates


# ---------------------------------------------------------------------------
# Core compilation function
# ---------------------------------------------------------------------------

def compile_template(
    template_text: str,
    variables: dict[str, Any],
    current_url: str = "",
) -> str:
    """
    Compile a template string with the given variables.

    This is the core function that processes template syntax including:
    - Variable interpolation: {{title}}, {{author|lower}}, etc.
    - Filters: {{title|capitalize}}, {{keywords|split:","}}, etc.
    - Logic blocks: {% if %}, {% for %}, {% set %}

    Args:
        template_text: The template string to compile
        variables: Dictionary of template variables (with {{name}} keys)
        current_url: Optional URL for filter processing

    Returns:
        Compiled template string
    """
    return render_template(template_text, variables, current_url)


# ---------------------------------------------------------------------------
# PDF clipping function
# ---------------------------------------------------------------------------

def clip_pdf(
    pdf_content: PdfContent,
    template: Template,
    property_types: dict[str, str] | None = None,
    extra_variables: dict[str, Any] | None = None,
) -> ClipPdfResult:
    """
    Process a PDF with a template to produce an Obsidian note.

    Args:
        pdf_content: Extracted PDF content dataclass
        template: Template to apply
        property_types: Optional property type overrides
        extra_variables: Additional template variables (e.g., sections, summaries from idlearn)

    Returns:
        ClipPdfResult with note_name, content, frontmatter, and full_content
    """
    # Build template variables from PDF content
    variables = build_pdf_variables_from_content(pdf_content)

    # Merge extra variables (e.g., idlearn sections, summaries)
    if extra_variables:
        variables.update(extra_variables)

    # Derive title
    title = (pdf_content.metadata.title or "").strip()
    if not title:
        title = pdf_content.file_name.replace('.pdf', '').replace('.PDF', '').replace('_', ' ').replace('-', ' ')

    # Compile function
    def _compile(text: str) -> str:
        return compile_template(text, variables)

    # Compile note name
    compiled_note_name = _compile(template.note_name_format)
    note_name = sanitize_file_name(compiled_note_name) or "Untitled"

    # Compile and format each property
    compiled_properties: list[Property] = []
    type_map: dict[str, str] = {}

    for prop in template.properties:
        compiled_value = _compile(prop.value)
        prop_type = prop.type or "text"
        compiled_value = format_property_value(compiled_value, prop_type, prop.value)
        compiled_properties.append(Property(
            name=prop.name,
            value=compiled_value,
            type=prop_type,
        ))
        if prop_type:
            type_map[prop.name] = prop_type

    # Merge property type overrides
    if property_types:
        type_map.update(property_types)

    # Generate frontmatter
    frontmatter = generate_frontmatter(compiled_properties, type_map)

    # Compile note content
    content = _compile(template.note_content_format)

    # Assemble full content
    full_content = frontmatter + content if frontmatter else content

    return ClipPdfResult(
        note_name=note_name,
        frontmatter=frontmatter,
        content=content,
        full_content=full_content,
        properties=compiled_properties,
        variables=variables,
    )


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

def clear_template_cache():
    """Clear the parsed template AST cache."""
    from .cache import _default_cache
    _default_cache.clear()


def template_cache_stats():
    """Return cache statistics (hits, misses, size)."""
    from .cache import _default_cache
    return _default_cache.stats()


def clip_pdf_with_dict(
    pdf_data: dict[str, Any],
    template: Template,
    property_types: dict[str, str] | None = None,
    extra_variables: dict[str, Any] | None = None,
) -> ClipPdfResult:
    """
    Convenience function: process a PDF with a template using a dict instead of PdfContent.

    The pdf_data dict should have keys matching PdfContent fields:
    text, pages, page_count, metadata (dict with title, author, etc.),
    file_name, file_path, file_size

    Args:
        pdf_data: Dictionary with PDF content data
        template: Template to apply
        property_types: Optional property type overrides
        extra_variables: Additional template variables

    Returns:
        ClipPdfResult
    """
    meta = pdf_data.get("metadata", {})
    from .types import PdfMetadata, PdfPage
    metadata_obj = PdfMetadata()  # default

    if isinstance(meta, dict) and meta:
        metadata_obj = PdfMetadata(
            title=meta.get("title", ""),
            author=meta.get("author", ""),
            subject=meta.get("subject", ""),
            keywords=meta.get("keywords", ""),
            creator=meta.get("creator", ""),
            producer=meta.get("producer", ""),
            creation_date=meta.get("creationDate", meta.get("creation_date", "")),
            mod_date=meta.get("modDate", meta.get("modification_date", meta.get("mod_date", ""))),
        )

    pages = []
    for p in pdf_data.get("pages", []):
        if isinstance(p, dict):
            pages.append(PdfPage(
                page_number=p.get("pageNumber", p.get("page_number", 0)),
                text=p.get("text", ""),
            ))
        else:
            pages.append(p)

    pdf_content = PdfContent(
        text=pdf_data.get("text", ""),
        pages=pages,
        page_count=pdf_data.get("page_count", pdf_data.get("pageCount", len(pages))),
        metadata=metadata_obj or PdfMetadata(),
        file_name=pdf_data.get("file_name", pdf_data.get("fileName", "")),
        file_path=pdf_data.get("file_path", pdf_data.get("filePath", "")),
        file_size=pdf_data.get("file_size", pdf_data.get("fileSize", 0)),
    )

    return clip_pdf(pdf_content, template, property_types, extra_variables)
