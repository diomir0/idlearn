# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                              filters/obsidian_filters.py                                #
# ========================================================================================#
"""
Obsidian-specific formatting filter functions.
Ported from obsidize/src/filters/callout.ts, blockquote.ts, wikilink.ts,
link.ts, image.ts, footnote.ts, fragment_link.ts, list.ts, table.ts,
markdown.ts.

Each filter has signature ``(value: str, params: str) -> str | list``.
"""

import json
import re
import builtins
from typing import Any
from urllib.parse import quote as url_quote

_blist = builtins.list  # save reference before shadowing with function name

__all__ = [
    "callout", "blockquote", "wikilink", "link", "image",
    "footnote", "fragment_link", "list", "table", "markdown",
]


# ---------------------------------------------------------------------------#
# Helpers                                                                     #
# ---------------------------------------------------------------------------#

def _strip_outer_quotes(s: str) -> str:
    return re.sub(r"^(['\"])([\s\S]*)\1$", r"\2", s)


def _strip_outer_parens(s: str) -> str:
    return re.sub(r"^\((.*)\)$", r"\1", s)


def _split_params(param: str) ->_blist[str]:
    """Split a comma-separated param string respecting quotes."""
    param = _strip_outer_parens(param)
    parts = re.split(r',(?=(?:(?:[^"\']*["\'][^"\']*["\'])*[^"\']*$))', param)
    return [_strip_outer_quotes(p.strip()) for p in parts]


def _escape_markdown(s: str) -> str:
    """Escape Markdown special characters ``[`` and ``]``."""
    return s.replace("[", r"\[").replace("]", r"\]")


def _strip_md(s: str) -> str:
    """Strip Markdown formatting from a string.

    Ported from obsidize ``strip_md`` filter.
    """
    # Remove images
    s = re.sub(r'!\[([^\]]*)\]\([^\)]+\)', '', s)
    s = re.sub(r'!\[\[([^\]]+)\]\]', '', s)
    # Remove links, keep text
    s = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', s)
    # Remove remaining URLs
    s = re.sub(r'https?://\S+', '', s)
    # Bold / italic / highlight / strikethrough
    s = re.sub(r'(\*\*|__)(.*?)\1', r'\2', s)
    s = re.sub(r'(\*|_)(.*?)\1', r'\2', s)
    s = re.sub(r'==(.*?)==', r'\1', s)
    s = re.sub(r'~~(.*?)~~', r'\1', s)
    # Headers
    s = re.sub(r'^#+\s+', '', s, flags=re.MULTILINE)
    # Inline code
    s = re.sub(r'`([^`]+)`', r'\1', s)
    # Code blocks
    s = re.sub(r'```[\s\S]*?```', '', s)
    # Task lists / list items
    s = re.sub(r'^[-*+] (\[[x ]\] )?', '', s, flags=re.MULTILINE)
    # Horizontal rules
    s = re.sub(r'^([-*_]){3,}\s*$', '', s, flags=re.MULTILINE)
    # Blockquotes
    s = re.sub(r'^>\s+', '', s, flags=re.MULTILINE)
    # Tables
    s = re.sub(r'\|.*\|', '', s)
    # Sub/superscript
    s = re.sub(r'([~^])(\w+)\1', r'\2', s)
    # Emoji shortcodes
    s = re.sub(r':[a-z_]+:', '', s)
    # HTML tags
    s = re.sub(r'<[^>]+>', '', s)
    # Empty brackets
    s = re.sub(r'\[\s*\]', '', s)
    # Footnote references
    s = re.sub(r'\[\^[^\]]+\]', '', s)
    # Abbreviations
    s = re.sub(r'^\*\[[^\]]+\]:.+$', '', s, flags=re.MULTILINE)
    # Wikilinks
    s = re.sub(r'\[\[([^\]|]+)\|?([^\]]*)\]\]', lambda m: m.group(2) or m.group(1), s)
    # Multiple newlines
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()


# ---------------------------------------------------------------------------#
# callout                                                                     #
# ---------------------------------------------------------------------------#

def callout(value: str, params: str = "") -> str:
    """Format *value* as an Obsidian callout.

    ``params`` can be ``"type"`` or ``"type,title"`` or
    ``"type,title,foldState"``.
    """
    callout_type = "info"
    title = ""
    fold_state: str | None = None

    if params:
        parts = _split_params(params)
        if len(parts) > 0 and parts[0]:
            callout_type = parts[0]
        if len(parts) > 1:
            title = parts[1]
        if len(parts) > 2:
            if parts[2].lower() == "true":
                fold_state = "-"
            elif parts[2].lower() == "false":
                fold_state = "+"

    header = f"> [!{callout_type}]"
    if fold_state:
        header += fold_state
    if title:
        header += f" {title}"

    lines = value.split("\n")
    body = "\n".join(f"> {line}" for line in lines)
    return f"{header}\n{body}"


# ---------------------------------------------------------------------------#
# blockquote                                                                  #
# ---------------------------------------------------------------------------#

def blockquote(value: str, params: str = "") -> str:
    """Format *value* as a blockquote (``>`` prefix)."""
    def _quote(s: str, depth: int = 1) -> str:
        prefix = "> " * depth
        return "\n".join(f"{prefix}{line}" for line in s.split("\n"))

    def _quote_array(arr: _blist, depth: int = 1) -> str:
        lines: _blist[str] = []
        for item in arr:
            if isinstance(item, _blist):
                lines.append(_quote_array(item, depth + 1))
            else:
                lines.append(_quote(str(item), depth))
        return "\n".join(lines)

    try:
        parsed = json.loads(value)
        if isinstance(parsed, _blist):
            return _quote_array(parsed)
        if isinstance(parsed, dict):
            return _quote(json.dumps(parsed, indent=2))
        return _quote(str(parsed))
    except (json.JSONDecodeError, ValueError):
        return _quote(value)


# ---------------------------------------------------------------------------#
# wikilink                                                                    #
# ---------------------------------------------------------------------------#

def wikilink(value: str, params: str = "") -> str:
    """Format *value* as an Obsidian wikilink ``[[link]]`` or ``[[link|alias]]``."""
    if not value.strip():
        return value

    alias = ""
    if params:
        param = _strip_outer_parens(params)
        alias = _strip_outer_quotes(param)

    def _process_object(obj: Any) ->_blist[str]:
        results: _blist[str] = []
        for k, v in obj.items():
            if isinstance(v, dict):
                results.extend(_process_object(v))
            else:
                results.append(f"[[{k}|{v}]]")
        return results

    try:
        data = json.loads(value)
        if isinstance(data, _blist):
            result = []
            for item in data:
                if isinstance(item, dict):
                    result.extend(_process_object(item))
                else:
                    result.append(
                        f"[[{item}|{alias}]]" if alias and item else
                        (f"[[{item}]]" if item else "")
                    )
            return json.dumps(result)
        if isinstance(data, dict):
            return json.dumps(_process_object(data))
    except (json.JSONDecodeError, ValueError):
        return f"[[{value}|{alias}]]" if alias else f"[[{value}]]"

    return value


# ---------------------------------------------------------------------------#
# link                                                                        #
# ---------------------------------------------------------------------------#

def link(value: str, params: str = "") -> str:
    """Format *value* as a Markdown link ``[text](url)``."""
    if not value.strip():
        return value

    link_text = "link"
    if params:
        param = _strip_outer_parens(params)
        link_text = _strip_outer_quotes(param)

    def _encode_url(url: str) -> str:
        return url.replace(" ", "%20")

    def _process_object(obj: Any) ->_blist[str]:
        results: _blist[str] = []
        for k, v in obj.items():
            if isinstance(v, dict):
                results.extend(_process_object(v))
            else:
                results.append(f"[{_escape_markdown(str(v))}]({_encode_url(_escape_markdown(k))})")
        return results

    try:
        data = json.loads(value)
        if isinstance(data, _blist):
            result = []
            for item in data:
                if isinstance(item, dict):
                    result.extend(_process_object(item))
                else:
                    result.append(
                        f"[{link_text}]({_encode_url(_escape_markdown(str(item)))})" if item else ""
                    )
            return "\n".join(result)
        if isinstance(data, dict):
            return "\n".join(_process_object(data))
    except (json.JSONDecodeError, ValueError):
        return f"[{link_text}]({_encode_url(_escape_markdown(value))})"

    return value


# ---------------------------------------------------------------------------#
# image                                                                       #
# ---------------------------------------------------------------------------#

def image(value: str, params: str = "") -> str | list:
    """Format *value* as a Markdown image ``![alt](url)``."""
    if not value.strip():
        return value

    alt_text = ""
    if params:
        param = _strip_outer_parens(params)
        alt_text = _strip_outer_quotes(param)

    def _process_object(obj: Any) ->_blist[str]:
        results: _blist[str] = []
        for k, v in obj.items():
            if isinstance(v, dict):
                results.extend(_process_object(v))
            else:
                results.append(f"![{_escape_markdown(str(v))}]({_escape_markdown(k)})")
        return results

    try:
        data = json.loads(value)
        if isinstance(data, _blist):
            result = []
            for item in data:
                if isinstance(item, dict):
                    result.extend(_process_object(item))
                else:
                    result.append(
                        f"![{alt_text}]({_escape_markdown(str(item))})" if item else ""
                    )
            return result if len(result) != 1 else result
        if isinstance(data, dict):
            return _process_object(data)
    except (json.JSONDecodeError, ValueError):
        return f"![{alt_text}]({_escape_markdown(value)})"

    return value


# ---------------------------------------------------------------------------#
# footnote                                                                    #
# ---------------------------------------------------------------------------#

def footnote(value: str, params: str = "") -> str:
    """Format *value* as Markdown footnotes ``[^id]: content``."""
    if value == "":
        return value

    try:
        data = json.loads(value)
        if isinstance(data, _blist):
            return "\n\n".join(f"[^{i + 1}]: {item}" for i, item in enumerate(data))
        if isinstance(data, dict):
            lines = []
            for k, v in data.items():
                fid = re.sub(r'([a-z])([A-Z])', r'\1-\2', k)
                fid = re.sub(r'[\s_]+', '-', fid).lower()
                lines.append(f"[^{fid}]: {v}")
            return "\n\n".join(lines)
    except (json.JSONDecodeError, ValueError):
        pass
    return value


# ---------------------------------------------------------------------------#
# fragment_link                                                               #
# ---------------------------------------------------------------------------#

def fragment_link(value: str, params: str = "") -> str | list:
    """Format *value* as a text-fragment link ``[text](url#:~:text=...)``.

    The ``params`` string may include a URL component after a colon,
    e.g. ``"link:https://example.com"``.
    """
    if not params or not value.strip():
        return value

    # Parse link text and URL from params
    url_match = re.match(r'^(.*?):?((https?://|file://).*$)', params)
    linktext = url_match.group(1).strip().strip("'\"") if url_match else "link"
    current_url = url_match.group(2) if url_match else params

    def _extract_text_fragment_parts(text: str) -> dict[str, str | None]:
        clean = _strip_md(text)
        words = clean.split()
        words = [w for w in words if w]
        if len(words) > 10:
            return {"start": " ".join(words[:5]), "end": " ".join(words[-5:])}
        return {"start": " ".join(words), "end": None}

    def _create_fragment_url(text: str) -> str:
        parts = _extract_text_fragment_parts(text)
        encoded_start = url_quote(parts["start"] or "")
        fragment = f"#:~:text={encoded_start}"
        if parts["end"]:
            fragment += f",{url_quote(parts['end'] or '')}"
        return fragment

    try:
        data = json.loads(value)
        if isinstance(data, _blist):
            results = []
            for item in data:
                if isinstance(item, dict) and "text" in item:
                    results.append({
                        **item,
                        "text": f"{item['text']} [{linktext}]({current_url}{_create_fragment_url(item['text'])})",
                    })
                else:
                    results.append(
                        f"{item} [{linktext}]({current_url}{_create_fragment_url(str(item))})"
                    )
            return results
        if isinstance(data, dict):
            return [
                f"{v} [{linktext}]({current_url}{_create_fragment_url(str(v))})"
                for v in data.values()
            ]
    except (json.JSONDecodeError, ValueError):
        pass

    return [f"{value} [{linktext}]({current_url}{_create_fragment_url(value)})"]


# ---------------------------------------------------------------------------#
# list                                                                        #
# ---------------------------------------------------------------------------#

def list(value: str, params: str = "") -> str:
    """Format *value* as a Markdown list (bullet, numbered, task, or numbered-task)."""
    if value == "":
        return value

    def _process_item(item: Any, list_type: str, depth: int = 0) -> str:
        indent = "\t" * depth
        if list_type == "numbered":
            prefix = "1. "
        elif list_type == "task":
            prefix = "- [ ] "
        elif list_type == "numbered-task":
            prefix = "1. [ ] "
        else:
            prefix = "- "

        if isinstance(item, _blist):
            return _process_array(item, list_type, depth + 1)
        return f"{indent}{prefix}{item}"

    def _process_array(arr: _blist, list_type: str, depth: int = 0) -> str:
        lines: _blist[str] = []
        for idx, item in enumerate(arr):
            if list_type == "numbered" or list_type == "numbered-task":
                line = _process_item(item, list_type, depth)
                line = re.sub(r'^(\d+)\.', str(idx + 1), line, count=1)
                lines.append(line)
            else:
                lines.append(_process_item(item, list_type, depth))
        return "\n".join(lines)

    def _determine_type(p: str | None) -> str:
        if p == "numbered":
            return "numbered"
        if p == "task":
            return "task"
        if p == "numbered-task":
            return "numbered-task"
        return "bullet"

    try:
        parsed = json.loads(value)
        if isinstance(parsed, _blist):
            return _process_array(parsed, _determine_type(params))
        return _process_array([parsed], _determine_type(params))
    except (json.JSONDecodeError, ValueError):
        return _process_item(value, _determine_type(params))


# ---------------------------------------------------------------------------#
# table                                                                       #
# ---------------------------------------------------------------------------#

def table(value: str, params: str = "") -> str:
    """Format *value* as a Markdown table."""
    if not value or value in ("undefined", "null"):
        return value

    def _escape_cell(cell: str) -> str:
        return cell.replace("|", "\\|")

    try:
        data = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value

    custom_headers: _blist[str] = []
    if params:
        header_str = _strip_outer_parens(params)
        custom_headers = [_strip_outer_quotes(h.strip()) for h in header_str.split(",")]

    # Single object → key | value table
    if isinstance(data, dict) and not isinstance(data, _blist):
        entries = _blist(data.items())
        if not entries:
            return value
        first_key, first_val = entries[0]
        lines = [f"| {_escape_cell(first_key)} | {_escape_cell(str(first_val))} |",
                 "| - | - |"]
        for k, v in entries[1:]:
            lines.append(f"| {_escape_cell(k)} | {_escape_cell(str(v))} |")
        return "\n".join(lines)

    # Array of objects
    if isinstance(data, _blist) and len(data) > 0 and isinstance(data[0], dict):
        headers = custom_headers if custom_headers else _blist(data[0].keys())
        lines = [f"| {' | '.join(headers)} |",
                 f"| {' | '.join('-' for _ in headers)} |"]
        for row in data:
            lines.append(f"| {' | '.join(_escape_cell(str(row.get(h, ''))) for h in headers)} |")
        return "\n".join(lines)

    # Array of arrays
    if isinstance(data, _blist) and len(data) > 0 and isinstance(data[0], _blist):
        max_cols = max(len(row) for row in data)
        headers = custom_headers if custom_headers else [""] * max_cols
        lines = [f"| {' | '.join(headers)} |",
                 f"| {' | '.join('-' for _ in headers)} |"]
        for row in data:
            padded = _blist(row) + [""] * (max_cols - len(row))
            lines.append(f"| {' | '.join(_escape_cell(str(c)) for c in padded)} |")
        return "\n".join(lines)

    # Simple array
    if isinstance(data, _blist):
        if custom_headers:
            num_cols = len(custom_headers)
            lines = [f"| {' | '.join(custom_headers)} |",
                     f"| {' | '.join('-' for _ in custom_headers)} |"]
            for i in range(0, len(data), num_cols):
                row = data[i:i + num_cols]
                padded = _blist(row) + [""] * (num_cols - len(row))
                lines.append(f"| {' | '.join(_escape_cell(str(c)) for c in padded)} |")
            return "\n".join(lines)

        lines = ["| Value |", "| - |"]
        for item in data:
            lines.append(f"| {_escape_cell(str(item))} |")
        return "\n".join(lines)

    return value


# ---------------------------------------------------------------------------#
# markdown                                                                    #
# ---------------------------------------------------------------------------#

def markdown(value: str, params: str = "") -> str:
    """Pass-through for Markdown text. If the input looks like HTML, strip tags."""
    if "<" in value and ">" in value:
        text = value
        text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'</p>', '\n\n', text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&#039;", "'")
        text = text.replace("&nbsp;", " ")
        return text.strip()
    return value
