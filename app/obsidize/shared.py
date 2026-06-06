# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                      shared.py                                          #
# ========================================================================================#
"""
Shared pure functions for building template variables and generating frontmatter.
Ported from obsidize/src/utils/shared.ts and obsidize/src/utils/string-utils.ts.
"""

import json
import re
from datetime import datetime, timezone
from typing import Any

from .types import Property, PdfContent, PdfMetadata


# ---------------------------------------------------------------------------
# File name sanitization
# ---------------------------------------------------------------------------

def sanitize_file_name(name: str) -> str:
    """Sanitize a string for use as a file name (Obsidian-safe)."""
    # Remove Obsidian-specific characters
    sanitized = re.sub(r'[#|\^[\]]', '', name)
    # Remove filesystem-unsafe characters
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1F]', '', sanitized)
    # Remove leading dots
    sanitized = re.sub(r'^\.+', '', sanitized)
    sanitized = sanitized.strip()
    # Truncate to 245 chars
    sanitized = sanitized[:245]
    if not sanitized:
        sanitized = 'Untitled'
    return sanitized


def escape_double_quotes(s: str) -> str:
    """Escape double quotes in a string."""
    return s.replace('"', '\\"')


def format_file_size(num_bytes: int) -> str:
    """Format a byte count as a human-readable file size."""
    if num_bytes == 0:
        return '0 B'
    units = ['B', 'KB', 'MB', 'GB']
    i = 0
    size = float(num_bytes)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.1f} {units[i]}" if i > 0 else f"{int(size)} {units[i]}"


# ---------------------------------------------------------------------------
# PDF date formatting
# ---------------------------------------------------------------------------

def format_pdf_date(pdf_date: str) -> str:
    """
    Format PDF metadata dates into ISO 8601 format.
    PDF dates are typically D:YYYYMMDDHHmmSSZ or D:YYYYMMDDHHmmSS+HH'mm'
    """
    if not pdf_date:
        return ''

    # Remove the D: prefix if present
    cleaned = re.sub(r'^D:', '', pdf_date)

    # Extract date digits and optional timezone
    match = re.match(r'^(\d{4,14})(Z|[+-]\d{2}?\'?\d{2}\'?)?$', cleaned)
    if not match:
        return cleaned

    date_digits = match.group(1)
    tz_raw = match.group(2) or ''

    year = date_digits[0:4]
    month = date_digits[4:6] if len(date_digits) >= 6 else None
    day = date_digits[6:8] if len(date_digits) >= 8 else None
    hour = date_digits[8:10] if len(date_digits) >= 10 else None
    minute = date_digits[10:12] if len(date_digits) >= 12 else None
    second = date_digits[12:14] if len(date_digits) >= 14 else None

    result = year
    if month and day:
        result += f"-{month}-{day}"
    elif month:
        result += f"-{month}"

    if hour and minute:
        result += f"T{hour}:{minute}"
        if second:
            result += f":{second}"

    # Normalize timezone suffix
    if tz_raw:
        if tz_raw == 'Z':
            result += 'Z'
        else:
            tz_match = re.match(r'^([+-])(\d{2})\'?(\d{2})\'?$', tz_raw)
            if tz_match:
                sign, tz_hour, tz_min = tz_match.groups()
                result += f"{sign}{tz_hour}:{tz_min}"
            else:
                result += tz_raw

    return result


# ---------------------------------------------------------------------------
# PDF text cleanup
# ---------------------------------------------------------------------------

def clean_pdf_text(raw_text: str) -> str:
    """Clean up raw PDF text extraction output."""
    text = raw_text
    # Remove null bytes
    text = text.replace('\0', '')
    # Normalize various Unicode spaces to regular spaces
    text = re.sub(r'[\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]', ' ', text)
    # Collapse multiple spaces into one (but preserve intentional indentation)
    text = re.sub(r' {2,}', ' ', text)
    # Remove trailing whitespace on each line
    text = re.sub(r'[ \t]+$', '', text, flags=re.MULTILINE)
    # Collapse 3+ consecutive blank lines into 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ---------------------------------------------------------------------------
# Variable building
# ---------------------------------------------------------------------------

def build_pdf_variables(
    title: str = "",
    author: str = "",
    content: str = "",
    file_name: str = "",
    file_path: str = "",
    file_size: int = 0,
    page_count: int = 0,
    subject: str = "",
    keywords: str = "",
    creator: str = "",
    producer: str = "",
    creation_date: str = "",
    modification_date: str = "",
    pages: list[dict] | None = None,
) -> dict[str, Any]:
    """Build the template variable dictionary from extracted PDF data."""
    # Derive a meaningful title
    derived_title = (title or "").strip() or re.sub(r'\.[^.]+$', '', file_name).replace('_', ' ').replace('-', ' ')
    note_name = sanitize_file_name(derived_title)

    # Normalize PDF dates to ISO 8601 so template filters (|date:) can parse them
    creation_date_iso = format_pdf_date(creation_date)
    modification_date_iso = format_pdf_date(modification_date)

    # Clean extracted text
    cleaned_content = clean_pdf_text(content) if content else ""

    # Current timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S%z")

    variables: dict[str, Any] = {
        "{{title}}": derived_title,
        "{{author}}": (author or "").strip(),
        "{{content}}": cleaned_content,
        "{{date}}": timestamp,
        "{{time}}": timestamp,
        "{{fileName}}": file_name,
        "{{filePath}}": file_path,
        "{{fileSize}}": str(file_size or 0),
        "{{pageCount}}": str(page_count or 0),
        "{{subject}}": (subject or "").strip(),
        "{{keywords}}": (keywords or "").strip(),
        "{{creator}}": (creator or "").strip(),
        "{{producer}}": (producer or "").strip(),
        "{{creationDate}}": creation_date_iso,
        "{{modificationDate}}": modification_date_iso,
        "{{noteName}}": note_name.strip(),
    }

    # Add page variables if available
    if pages:
        for page in pages:
            page_num = page.get("pageNumber", page.get("page_number", 0))
            page_text = page.get("text", "")
            variables[f"{{{{page_{page_num}}}}}"] = page_text

    return variables


def build_pdf_variables_from_content(pdf_content: PdfContent) -> dict[str, Any]:
    """Convenience: build variables from a PdfContent dataclass."""
    meta = pdf_content.metadata
    pages = [{"pageNumber": p.page_number, "text": p.text} for p in pdf_content.pages]

    return build_pdf_variables(
        title=meta.title,
        author=meta.author,
        content=pdf_content.text,
        file_name=pdf_content.file_name,
        file_path=pdf_content.file_path,
        file_size=pdf_content.file_size,
        page_count=pdf_content.page_count,
        subject=meta.subject,
        keywords=meta.keywords,
        creator=meta.creator,
        producer=meta.producer,
        creation_date=meta.creation_date,
        modification_date=meta.mod_date,
        pages=pages,
    )


# ---------------------------------------------------------------------------
# Frontmatter generation
# ---------------------------------------------------------------------------

def generate_frontmatter(
    properties: list[Property],
    property_types: dict[str, str] | None = None,
) -> str:
    """Generate YAML frontmatter from compiled properties."""
    if property_types is None:
        property_types = {}

    lines = ["---"]
    has_properties = False

    for prop in properties:
        has_properties = True
        trimmed_name = prop.name.strip()

        # Determine if the key needs quoting
        needs_quotes = (
            bool(re.search(r'[:\s{}\[\],&*#?|<>=!%@\\-]', trimmed_name))
            or trimmed_name.isdigit()
            or trimmed_name.lower() in ('true', 'false', 'null', 'yes', 'no', 'on', 'off')
        )

        if needs_quotes:
            if '"' in prop.name:
                escaped = prop.name.replace("'", "''")
                key = f"'{escaped}'"
            else:
                key = f'"{prop.name}"'
        else:
            key = prop.name

        prop_type = property_types.get(prop.name, prop.type or "text")

        if prop_type == "multitext":
            # Parse as list
            items = _parse_multitext_value(prop.value)
            if items:
                lines.append(f"{key}:")
                for item in items:
                    lines.append(f'  - "{escape_double_quotes(item)}"')
            else:
                lines.append(f"{key}:")
        elif prop_type == "number":
            numeric = re.sub(r'[^\d.-]', '', prop.value)
            lines.append(f"{key}: {float(numeric)}" if numeric else f"{key}:")
        elif prop_type == "checkbox":
            is_checked = prop.value.lower() == 'true' or prop.value == '1'
            lines.append(f"{key}: {str(is_checked).lower()}")
        elif prop_type in ("date", "datetime"):
            lines.append(f"{key}: {prop.value}" if prop.value.strip() else f"{key}:")
        else:  # text
            if prop.value.strip():
                lines.append(f'{key}: "{escape_double_quotes(prop.value)}"')
            else:
                lines.append(f"{key}:")

    lines.append("---")

    if not has_properties:
        return ""

    result = "\n".join(lines)
    # Check for empty frontmatter
    if result.strip() == "---\n---":
        return ""
    return result + "\n"


def _parse_multitext_value(value: str) -> list[str]:
    """Parse a multitext property value into a list of strings."""
    value = value.strip()
    # Try JSON parse
    if value.startswith('["') and value.endswith('"]'):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            pass
    # Fall back to comma-separated
    return [item.strip() for item in value.split(',') if item.strip()]


# ---------------------------------------------------------------------------
# Property type formatting
# ---------------------------------------------------------------------------

def format_property_value(value: str, prop_type: str, template_value: str = "") -> str:
    """Apply type-aware formatting to a compiled property value."""
    if prop_type == "number":
        numeric = re.sub(r'[^\d.-]', '', value)
        return str(float(numeric)) if numeric else value
    elif prop_type == "checkbox":
        return str(value.lower() == 'true' or value == '1').lower()
    elif prop_type in ("date", "datetime"):
        if "|date:" not in template_value:
            try:
                from dateutil import parser as dateutil_parser
                dt = dateutil_parser.parse(value)
                if dt is not None:
                    fmt = "%Y-%m-%dT%H:%M:%S%z" if prop_type == "datetime" else "%Y-%m-%d"
                    return dt.strftime(fmt)
            except Exception:
                pass
        return value
    else:
        return value
