# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                  string_filters.py                                      #
# ========================================================================================#
"""
String-related filter functions for the Obsidize template engine.
Ported from obsidize/src/filters/*.ts.

Each filter takes (value: str, params: str) -> str | list.
"""

import json
import re
import urllib.parse
from typing import Any


# ---------------------------------------------------------------------------
# Helper: parser state for the replace filter's param splitter
# ---------------------------------------------------------------------------

class _ParserState:
    """Tracks quoting, regex, and nesting state while parsing replace params."""

    __slots__ = ("current", "in_quote", "quote_type", "in_regex",
                 "curly_depth", "paren_depth", "escape_next")

    def __init__(self) -> None:
        self.current: str = ""
        self.in_quote: bool = False
        self.quote_type: str = ""
        self.in_regex: bool = False
        self.curly_depth: int = 0
        self.paren_depth: int = 0
        self.escape_next: bool = False


def _process_character(char: str, state: _ParserState) -> None:
    """Process a single character and update parser state."""
    if state.escape_next:
        state.current += char
        state.escape_next = False
        return

    if char == "\\":
        state.current += char
        if not state.in_regex:
            state.escape_next = True
        return

    if char in ('"', "'") and not state.in_regex:
        state.in_quote = not state.in_quote
        state.quote_type = char if state.in_quote else ""
        state.current += char
        return

    if char == "/" and not state.in_quote and not state.in_regex and (
        state.current.endswith(":") or state.current.endswith(",")
    ):
        state.in_regex = True
        state.current += char
        return

    if char == "/" and state.in_regex and not state.escape_next:
        state.in_regex = False
        state.current += char
        return

    if char == "{":
        state.curly_depth += 1
        state.current += char
        return

    if char == "}":
        state.curly_depth -= 1
        state.current += char
        return

    if char == "(" and not state.in_quote:
        state.paren_depth += 1
        state.current += char
        return

    if char == ")" and not state.in_quote:
        state.paren_depth -= 1
        state.current += char
        return

    state.current += char


def _parse_regex_pattern(pattern: str) -> tuple[str, str] | None:
    """Parse a /pattern/flags regex string. Returns (pattern, flags) or None."""
    match = re.match(r"^/(.+)/([gimsuy]*)$", pattern, re.DOTALL)
    if not match:
        return None
    return match.group(1), match.group(2)


def _process_escaped_characters(s: str) -> str:
    """Process \\n, \\r, \\t and other escape sequences in a replacement string."""
    def _replace(m: re.Match) -> str:
        char = m.group(1)
        if char == "n":
            return "\n"
        elif char == "r":
            return "\r"
        elif char == "t":
            return "\t"
        return char

    return re.sub(r"\\(.|\n)", _replace, s)


def _strip_outer_quotes(s: str) -> str:
    """Remove surrounding single or double quotes and unescape internal ones."""
    s = re.sub(r"""^(['"])([\s\S]*)\1$""", r"\2", s)
    s = re.sub(r"""\\(['"])""", r"\1", s)
    return s


def _strip_outer_parens(s: str) -> str:
    """Remove outer parentheses if they wrap the entire string."""
    return re.sub(r"^\((.*)\)$", r"\1", s, count=1)


# ---------------------------------------------------------------------------
# String transform filters
# ---------------------------------------------------------------------------

def lower(value: str, params: str = "") -> str:
    """Convert value to lowercase."""
    return value.lower()


def upper(value: str, params: str = "") -> str:
    """Convert value to uppercase."""
    return value.upper()


def capitalize(value: str, params: str = "") -> str:
    """Capitalize the first character of the value (and lowercase the rest)."""
    def _capitalize_string(s: str) -> str:
        if not s:
            return s
        return s[0].upper() + s[1:].lower()

    def _capitalize_value(v: Any) -> Any:
        if isinstance(v, str):
            return _capitalize_string(v)
        elif isinstance(v, list):
            return [_capitalize_value(item) for item in v]
        elif isinstance(v, dict):
            return {_capitalize_string(k): _capitalize_value(val) for k, val in v.items()}
        return v

    try:
        parsed = json.loads(value)
        capitalized = _capitalize_value(parsed)
        return json.dumps(capitalized)
    except (json.JSONDecodeError, ValueError):
        return _capitalize_string(value)


def title(value: str, params: str = "") -> str:
    """Convert value to title case, keeping short articles/prepositions lowercase."""
    _lowercase_words = frozenset([
        "a", "an", "the", "and", "but", "or", "for", "nor",
        "on", "at", "to", "from", "by", "in", "of",
    ])

    def _title_case(s: str) -> str:
        words = re.split(r"(\s+)", s)
        result = []
        word_idx = 0
        for token in words:
            if token.strip():  # actual word
                if word_idx != 0 and token.lower() in _lowercase_words:
                    result.append(token.lower())
                else:
                    result.append(token[0].upper() + token[1:].lower() if token else token)
                word_idx += 1
            else:
                result.append(token)
        return "".join(result)

    def _process_value(v: Any) -> Any:
        if isinstance(v, str):
            return _title_case(v)
        elif isinstance(v, list):
            return [_process_value(item) for item in v]
        elif isinstance(v, dict):
            return {_title_case(k): _process_value(val) for k, val in v.items()}
        return v

    try:
        parsed = json.loads(value)
        result = _process_value(parsed)
        return json.dumps(result)
    except (json.JSONDecodeError, ValueError):
        result = _process_value(value)
        return result if isinstance(result, str) else json.dumps(result)


def trim(value: str, params: str = "") -> str:
    """Strip leading/trailing whitespace."""
    return value.strip()


# ---------------------------------------------------------------------------
# Replace filter (complex param parsing)
# ---------------------------------------------------------------------------

def replace(value: str, params: str = "") -> str:
    """
    Replace occurrences in *value*.

    Param format: ``"old":"new"``  or  ``/regex/flags:"new"``
    Multiple replacements separated by commas.
    """
    if not params:
        return value

    params = _strip_outer_parens(params)

    # Split on commas respecting quotes / regex / nesting
    replacements: list[str] = []
    state = _ParserState()
    for ch in params:
        if (
            ch == ","
            and not state.in_quote
            and not state.in_regex
            and state.curly_depth == 0
            and state.paren_depth == 0
        ):
            replacements.append(state.current.strip())
            state = _ParserState()
        else:
            _process_character(ch, state)
    if state.current:
        replacements.append(state.current.strip())

    # Apply each replacement in sequence
    result = value
    for repl in replacements:
        # Split on the colon that separates search from replacement
        # (only unescaped quote-adjacent colons)
        parts = re.split(r"""(?<=[^\\]["']):(?=["'])""", repl, maxsplit=1)
        if len(parts) == 2:
            search = parts[0].strip()
            replace_str = parts[1].strip()
        else:
            search = parts[0].strip()
            replace_str = ""

        # Remove surrounding quotes
        search = re.sub(r"""^["']|["']$""", "", search)
        replace_str = re.sub(r"""^["']|["']$""", "", replace_str)

        # Regex pattern?
        regex_info = _parse_regex_pattern(search)
        if regex_info:
            try:
                replace_str = _process_escaped_characters(replace_str)
                py_flags = 0
                pattern, flags = regex_info
                if "i" in flags:
                    py_flags |= re.IGNORECASE
                if "m" in flags:
                    py_flags |= re.MULTILINE
                if "s" in flags:
                    py_flags |= re.DOTALL
                rx = re.compile(pattern, py_flags)
                result = rx.sub(replace_str, result)
            except re.error:
                pass
            continue

        search = _process_escaped_characters(search)
        replace_str = _process_escaped_characters(replace_str)

        # For pipe/colon separators, use split/join (like TS)
        if search in ("|", ":"):
            result = replace_str.join(result.split(search))
            continue

        # For literal newlines/tabs, use split/join
        if "\n" in search or "\r" in search or "\t" in search:
            result = replace_str.join(result.split(search))
            continue

        # Literal string replacement — escape regex specials for global replace
        escaped = re.escape(search)
        result = re.sub(escaped, replace_str, result)

    return result


# ---------------------------------------------------------------------------
# Replace-tags filter
# ---------------------------------------------------------------------------

def replace_tags(value: str, params: str = "") -> str:
    """
    Replace HTML tags (e.g., ``<b>`` → ``<strong>``).

    Param format: ``"tag1":"tag2"`` or ``"tag1":"tag2","tag3":"tag4"``
    """
    params = _strip_outer_parens(params)
    params = _strip_outer_quotes(params)

    # Split on commas respecting quotes
    transformations = re.split(
        r""",(?=(?:(?:[^"']*["'][^"']*["'])*[^"']*$))""",
        params,
    )
    transformations = [t.strip() for t in transformations if t.strip()]

    if not transformations:
        return value

    result = value
    for transform in transformations:
        # Split on unescaped :""  pattern
        parts = re.split(r"""(?<!\\)":"/""", transform)
        source_target = [p.strip() for p in parts]

        # Alternative: split on : between quoted strings
        if len(source_target) < 2:
            source_target = re.split(r"""(?<=[^\\]["']):(?=["'])""", transform)
            source_target = [p.strip() for p in source_target]

        if len(source_target) < 1:
            continue

        source = source_target[0].strip().strip("\"'").replace("\\", "")
        target = source_target[1].strip().strip("\"'").replace("\\", "") if len(source_target) > 1 else ""

        if not source:
            continue

        # Replace opening and closing tags
        opening_pattern = re.compile(rf"<{re.escape(source)}(\s+[^>]*?)?>", re.IGNORECASE)
        closing_pattern = re.compile(rf"</{re.escape(source)}>", re.IGNORECASE)

        result = opening_pattern.sub(
            lambda m: f"<{target}{m.group(1) or ''}>" if target else "",
            result,
        )
        result = closing_pattern.sub(
            f"</{target}>" if target else "",
            result,
        )

    return result


# ---------------------------------------------------------------------------
# Strip Markdown filter
# ---------------------------------------------------------------------------

def strip_md(value: str, params: str = "") -> str:
    """Remove Markdown formatting characters, keeping plain text."""
    s = value

    # Remove images first
    s = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", "", s)
    s = re.sub(r"!\[\[([^\]]+)\]\]", "", s)

    # Remove links, keep text
    s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)

    # Remove any remaining URL-like strings
    s = re.sub(r"https?://\S+", "", s)

    # Bold
    s = re.sub(r"(\*\*|__)(.*?)\1", r"\2", s)
    # Italic
    s = re.sub(r"(\*|_)(.*?)\1", r"\2", s)
    # Highlights
    s = re.sub(r"==(.*?)==", r"\1", s)
    # Headers
    s = re.sub(r"^#+\s+", "", s, flags=re.MULTILINE)
    # Inline code
    s = re.sub(r"`([^`]+)`", r"\1", s)
    # Code blocks
    s = re.sub(r"```[\s\S]*?```", "", s)
    # Strikethrough
    s = re.sub(r"~~(.*?)~~", r"\1", s)
    # Task lists and list items
    s = re.sub(r"^[-*+] (\[[x ]\] )?", "", s, flags=re.MULTILINE)
    # Horizontal rules
    s = re.sub(r"^([-*_]){3,}\s*$", "", s, flags=re.MULTILINE)
    # Blockquotes
    s = re.sub(r"^>\s+", "", s, flags=re.MULTILINE)
    # Tables (removed entirely)
    s = re.sub(r"\|.*\|", "", s)
    # Subscript and superscript
    s = re.sub(r"([~^])(\w+)\1", r"\2", s)
    # Emoji shortcodes
    s = re.sub(r":[a-z_]+:", "", s)
    # HTML tags
    s = re.sub(r"<[^>]+>", "", s)
    # Empty square brackets
    s = re.sub(r"\[\s*\]", "", s)
    # Footnote references
    s = re.sub(r"\[\^[^\]]+\]", "", s)
    # Abbreviations
    s = re.sub(r"^\*\[[^\]]+\]:.+$", "", s, flags=re.MULTILINE)
    # Wikilinks
    s = re.sub(
        r"\[\[([^\]|]+)\|?([^\]]*)\]\]",
        lambda m: m.group(2) or m.group(1),
        s,
    )

    # Final cleanup
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = s.strip()

    return s


# ---------------------------------------------------------------------------
# Strip attributes filter
# ---------------------------------------------------------------------------

def strip_attr(value: str, params: str = "") -> str:
    """
    Remove HTML attributes from tags, keeping only those listed in *params*.

    Param format: ``"attr1,attr2"`` or plain ``attr1,attr2``
    """
    params = _strip_outer_parens(params)
    params = _strip_outer_quotes(params)

    keep_list = [a.strip() for a in params.split(",") if a.strip()]

    def _replace_tag(m: re.Match) -> str:
        tag = m.group(1)
        full_match = m.group(0)

        if not keep_list:
            return f"<{tag}>"

        kept_attrs: list[str] = []
        for attr in keep_list:
            escaped_attr = re.escape(attr)
            attr_rx = re.compile(rf"\s{escaped_attr}\s*=\s*(\"[^\"]*\"|'[^']*')", re.IGNORECASE)
            attr_m = attr_rx.search(full_match)
            if attr_m:
                kept_attrs.append(attr_m.group(0).strip())

        if kept_attrs:
            return f"<{tag} {' '.join(kept_attrs)}>"
        return f"<{tag}>"

    return re.sub(r"<(\w+)\s+(?:[^>]*?)>", _replace_tag, value)


# ---------------------------------------------------------------------------
# Strip tags filter
# ---------------------------------------------------------------------------

def strip_tags(value: str, params: str = "") -> str:
    """
    Remove HTML tags from *value*.

    If *params* lists specific tags, only those tags are removed (content kept).
    If *params* is empty, ALL tags are removed.
    HTML entities are decoded in the result.
    """
    params = _strip_outer_parens(params)
    params = _strip_outer_quotes(params)

    keep_list = [t.strip() for t in params.split(",") if t.strip()]

    if not keep_list:
        # Remove all tags
        result = re.sub(r"</?[^>]+(>|$)", "", value)
    else:
        # Remove only the specified tags (keep others)
        escaped = "|".join(re.escape(t) for t in keep_list)
        rx = re.compile(rf"<(?!/?(?:{escaped})\b)[^>]+>", re.IGNORECASE)
        result = rx.sub("", value)

    # Decode common HTML entities
    result = result.replace("&nbsp;", " ")
    result = result.replace("&amp;", "&")
    result = result.replace("&lt;", "<")
    result = result.replace("&gt;", ">")
    result = result.replace("&quot;", '"')
    result = result.replace("&#39;", "'")
    result = result.replace("&ldquo;", "\u201c")
    result = result.replace("&rdquo;", "\u201d")
    result = result.replace("&lsquo;", "\u2018")
    result = result.replace("&rsquo;", "\u2019")
    result = result.replace("&mdash;", "\u2014")
    result = result.replace("&ndash;", "\u2013")
    result = result.replace("&hellip;", "\u2026")

    # Decode numeric HTML entities
    result = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), result)
    result = re.sub(r"&#x([0-9A-Fa-f]+);", lambda m: chr(int(m.group(1), 16)), result)

    # Collapse excess newlines
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


# ---------------------------------------------------------------------------
# Remove HTML filter
# ---------------------------------------------------------------------------

def _escape_regex(s: str) -> str:
    """Escape special regex characters in *s*."""
    return re.escape(s)


def remove_html(value: str, params: str = "") -> str:
    """
    Remove HTML elements (tag + content) from *value*.

    Supports tag selectors, ``.class`` selectors, and ``#id`` selectors.
    Multiple selectors separated by commas.
    """
    params = _strip_outer_parens(params)
    params = _strip_outer_quotes(params)

    elements = re.split(
        r""",(?=(?:(?:[^"']*["'][^"']*["'])*[^"']*$))""",
        params,
    )
    elements = [e.strip() for e in elements if e.strip()]

    if not elements:
        return value

    result = value
    for elem in elements:
        if elem.startswith("."):
            # Class selector
            class_name = elem[1:]
            class_rx = re.compile(
                rf"<([a-z][a-z0-9]*)[^>]*class\s*=\s*[\"'][^\"']*\b"
                rf"{_escape_regex(class_name)}\b[^\"']*[\"'][^>]*>"
                rf"[\s\S]*?<\/\1>",
                re.IGNORECASE,
            )
            result = class_rx.sub("", result)
        elif elem.startswith("#"):
            # ID selector
            id_name = elem[1:]
            id_rx = re.compile(
                rf"<([a-z][a-z0-9]*)[^>]*id\s*=\s*[\"']"
                rf"{_escape_regex(id_name)}[\"'][^>]*>"
                rf"[\s\S]*?<\/\1>",
                re.IGNORECASE,
            )
            result = id_rx.sub("", result)
        else:
            # Tag selector — remove element and content
            tag_rx = re.compile(
                rf"<{_escape_regex(elem)}[^>]*>[\s\S]*?<\/{_escape_regex(elem)}>",
                re.IGNORECASE,
            )
            result = tag_rx.sub("", result)
            # Also remove self-closing tags
            self_close_rx = re.compile(
                rf"<{_escape_regex(elem)}[^>]*\/?>",
                re.IGNORECASE,
            )
            result = self_close_rx.sub("", result)

    return result


# ---------------------------------------------------------------------------
# Remove tags filter (removes tag markers, keeps content)
# ---------------------------------------------------------------------------

def remove_tags(value: str, params: str = "") -> str:
    """
    Remove specific HTML tag markers from *value* but keep their content.

    Param format: ``"tag1,tag2"`` or plain ``tag1,tag2``
    """
    if not params:
        return value

    params = _strip_outer_parens(params)
    params = _strip_outer_quotes(params)

    tags = [t.strip() for t in params.split(",") if t.strip()]

    if not tags:
        return value

    escaped = "|".join(re.escape(t) for t in tags)
    rx = re.compile(rf"<\/?(?:{escaped})\b[^>]*>", re.IGNORECASE)
    return rx.sub("", value)


# ---------------------------------------------------------------------------
# Remove attributes filter
# ---------------------------------------------------------------------------

def remove_attr(value: str, params: str = "") -> str:
    """
    Remove specific HTML attributes from tags in *value*.

    Param format: ``"attr1,attr2"`` or plain ``attr1,attr2``
    """
    if not params:
        return value

    params = _strip_outer_parens(params)
    params = _strip_outer_quotes(params)

    remove_list = [a.strip().lower() for a in params.split(",") if a.strip()]

    if not remove_list:
        return value

    attr_or_slash_rx = re.compile(
        r"([a-zA-Z0-9_:-]+(?:\s*=\s*(?:\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|[^'\"\s>]+))?)"
        r"|(\s*\/?\s*$)"
    )
    attr_name_rx = re.compile(r"^([a-zA-Z0-9_:-]+)")

    def _replace_tag(m: re.Match) -> str:
        tag = m.group(1)
        attributes_str = m.group(2)

        if not attributes_str or not attributes_str.strip():
            return m.group(0)

        kept: list[str] = []
        for am in attr_or_slash_rx.finditer(attributes_str):
            full_text = am.group(0)
            attr_part = am.group(1)
            slash_part = am.group(2)

            if attr_part:
                name_m = attr_name_rx.match(attr_part)
                if name_m:
                    attr_name = name_m.group(0)
                    if attr_name.lower() not in remove_list:
                        kept.append(attr_part)
                else:
                    kept.append(attr_part)
            elif slash_part and full_text and "/" in full_text:
                kept.append(full_text.strip())

        cleaned = " ".join(kept).strip()
        return f"<{tag} {cleaned}>" if cleaned else f"<{tag}>"

    return re.sub(r"<(\w+)\s+([^>]*?)>", _replace_tag, value)


# ---------------------------------------------------------------------------
# Unescape filter
# ---------------------------------------------------------------------------

def unescape(value: str, params: str = "") -> str:
    r"""Unescape common escape sequences: ``\"`` → ``"``, ``\n`` → newline."""
    return value.replace('\\"', '"').replace("\\n", "\n")


# ---------------------------------------------------------------------------
# Decode URI filter
# ---------------------------------------------------------------------------

def decode_uri(value: str, params: str = "") -> str:
    """URL-decode the value. Returns the original string on failure."""
    try:
        return urllib.parse.unquote(value)
    except Exception:
        return value


# ---------------------------------------------------------------------------
# Safe name filter
# ---------------------------------------------------------------------------

def safe_name(value: str, params: str = "") -> str:
    """
    Sanitize *value* for use as a filename.

    Optional param: ``windows``, ``mac``, or ``linux`` for OS-specific rules.
    Defaults to the most conservative (combination) when omitted.
    """
    os_type = params.lower().strip() if params else "default"

    sanitized = value

    # Remove Obsidian-specific characters (always)
    sanitized = re.sub(r"[#|\^[\]]", "", sanitized)

    if os_type == "windows":
        sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", sanitized)
        sanitized = re.sub(
            r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$",
            r"_\1\2",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(r"[\s.]+$", "", sanitized)
    elif os_type == "mac":
        sanitized = re.sub(r"[/:\x00-\x1F]", "", sanitized)
        sanitized = re.sub(r"^\.", "_", sanitized)
    elif os_type == "linux":
        sanitized = re.sub(r"[/\x00-\x1F]", "", sanitized)
        sanitized = re.sub(r"^\.", "_", sanitized)
    else:
        # Most conservative (combination of all rules)
        sanitized = re.sub(r'[<>:"/\\|?*:\x00-\x1F]', "", sanitized)
        sanitized = re.sub(
            r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])(\..*)?$",
            r"_\1\2",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(r"[\s.]+$", "", sanitized)
        sanitized = re.sub(r"^\.", "_", sanitized)

    # Common operations for all platforms
    sanitized = re.sub(r"^\.+", "", sanitized)
    sanitized = sanitized[:245]  # Leave room for ' 1.md'

    if not sanitized:
        sanitized = "Untitled"

    return sanitized
