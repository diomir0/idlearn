# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                      __init__.py                                        #
# ========================================================================================#
"""
Obsidize — Obsidian template engine for IDLEARN.

This module provides the Obsidize add-on, which converts PDF content into
structured Obsidian notes using Obsidian Web Clipper-compatible templates.

Main entry points:
    - compile_template()  — Compile a template string with variables
    - clip_pdf()          — Process PDF content with a template
    - load_template()     — Load a template from a JSON file
    - load_template_from_string() — Load a template from JSON string

Example usage::

    from app.obsidize import clip_pdf, load_template, PdfContent, PdfMetadata

    # Load a template
    template = load_template("academic")

    # Build PDF content from idlearn's extraction
    pdf_content = PdfContent(
        text="Full extracted text...",
        metadata=PdfMetadata(title="My Paper", author="Author"),
        file_name="paper.pdf",
        page_count=10,
    )

    # Clip with template
    result = clip_pdf(pdf_content, template)
    print(result.full_content)  # Complete Obsidian note with frontmatter
"""

from .types import (
    Template,
    Property,
    PdfContent,
    PdfMetadata,
    PdfPage,
    ClipPdfResult,
)
from .engine import (
    compile_template,
    clip_pdf,
    clip_pdf_with_dict,
    load_template,
    load_template_from_string,
    resolve_template_name,
    list_templates,
    clear_template_cache,
    template_cache_stats,
)
from .shared import (
    build_pdf_variables,
    build_pdf_variables_from_content,
    generate_frontmatter,
    format_property_value,
    sanitize_file_name,
    clean_pdf_text,
    format_pdf_date,
)
from .renderer import RenderContext, render_template, render_ast

__all__ = [
    # Types
    "Template",
    "Property",
    "PdfContent",
    "PdfMetadata",
    "PdfPage",
    "ClipPdfResult",
    # Engine
    "compile_template",
    "clip_pdf",
    "clip_pdf_with_dict",
    "load_template",
    "load_template_from_string",
    "resolve_template_name",
    "list_templates",
    "clear_template_cache",
    "template_cache_stats",
    # Shared utilities
    "build_pdf_variables",
    "build_pdf_variables_from_content",
    "generate_frontmatter",
    "format_property_value",
    "sanitize_file_name",
    "clean_pdf_text",
    "format_pdf_date",
    # Renderer
    "RenderContext",
    "render_template",
    "render_ast",
]
