# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                  filters/__init__.py                                    #
# ========================================================================================#
"""
Template filter registry for the Obsidize template engine.
Ported from obsidize/src/filters/index.ts.
"""

import json
import re
from typing import Any

from .string_filters import (
    lower, upper, capitalize, title, trim, replace, replace_tags,
    strip_md, strip_attr, strip_tags, remove_html, remove_tags, remove_attr,
    unescape, decode_uri, safe_name,
)
from .case_filters import camel, kebab, snake, pascal, uncamel
from .date_filters import date, date_modify, duration
from .collection_filters import (
    split, join, first, last, length, slice, nth, reverse, unique, map as map_filter, merge,
)
from .obsidian_filters import (
    callout, blockquote, wikilink, link, image, footnote, fragment_link, list as list_filter, table, markdown as markdown_filter,
)
from .math_filters import calc, round as round_filter, number_format
from .format_filters import object as object_filter, template as template_filter


# ---------------------------------------------------------------------------
# Filter metadata for validation
# ---------------------------------------------------------------------------

def _validate_calc_params(param: str | None) -> tuple[bool, str | None]:
    if not param:
        return False, "calc filter requires a parameter"
    return True, None

def _validate_date_modify_params(param: str | None) -> tuple[bool, str | None]:
    if not param:
        return False, "date_modify filter requires a parameter"
    return True, None

def _validate_map_params(param: str | None) -> tuple[bool, str | None]:
    if not param:
        return False, "map filter requires a parameter"
    return True, None

def _validate_replace_params(param: str | None) -> tuple[bool, str | None]:
    if not param:
        return False, "replace filter requires a parameter"
    return True, None

def _validate_slice_params(param: str | None) -> tuple[bool, str | None]:
    if not param:
        return False, "slice filter requires a parameter"
    return True, None

def _validate_list_params(param: str | None) -> tuple[bool, str | None]:
    return True, None

def _validate_nth_params(param: str | None) -> tuple[bool, str | None]:
    if not param:
        return False, "nth filter requires a parameter"
    return True, None

def _validate_object_params(param: str | None) -> tuple[bool, str | None]:
    return True, None

def _validate_round_params(param: str | None) -> tuple[bool, str | None]:
    return True, None

def _validate_safe_name_params(param: str | None) -> tuple[bool, str | None]:
    return True, None

def _validate_template_params(param: str | None) -> tuple[bool, str | None]:
    if not param:
        return False, "template filter requires a parameter"
    return True, None


FILTER_REGISTRY: dict[str, Any] = {
    # String transforms
    "lower": lower,
    "upper": upper,
    "capitalize": capitalize,
    "title": title,
    "trim": trim,
    "replace": replace,
    "replace_tags": replace_tags,
    "strip_md": strip_md,
    "strip_attr": strip_attr,
    "strip_tags": strip_tags,
    "remove_html": remove_html,
    "remove_tags": remove_tags,
    "remove_attr": remove_attr,
    "unescape": unescape,
    "decode_uri": decode_uri,
    "safe_name": safe_name,
    "stripmd": strip_md,  # alias

    # Case transforms
    "camel": camel,
    "kebab": kebab,
    "snake": snake,
    "pascal": pascal,
    "uncamel": uncamel,

    # Date/time
    "date": date,
    "date_modify": date_modify,
    "duration": duration,

    # Collections
    "split": split,
    "join": join,
    "first": first,
    "last": last,
    "length": length,
    "slice": slice,
    "nth": nth,
    "reverse": reverse,
    "unique": unique,
    "map": map_filter,
    "merge": merge,

    # Obsidian-specific
    "callout": callout,
    "blockquote": blockquote,
    "wikilink": wikilink,
    "link": link,
    "image": image,
    "footnote": footnote,
    "fragment_link": fragment_link,
    "list": list_filter,
    "table": table,
    "markdown": markdown_filter,

    # Math
    "calc": calc,
    "round": round_filter,
    "number_format": number_format,

    # Format
    "object": object_filter,
    "template": template_filter,
}

VALID_FILTER_NAMES = set(FILTER_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Filter application
# ---------------------------------------------------------------------------

def apply_filter_direct(
    value: Any,
    filter_name: str,
    param_string: str | None = None,
    current_url: str = "",
) -> str:
    """
    Apply a single filter by name with a pre-formatted parameter string.
    This is the main entry point used by the renderer.
    """
    filter_fn = FILTER_REGISTRY.get(filter_name)
    if filter_fn is None:
        # Unknown filter — return value unchanged
        return str(value) if not isinstance(value, str) else value

    # Convert input to string if needed
    string_input = str(value) if not isinstance(value, str) else value

    # Build params
    params = param_string if param_string is not None else ""

    # Special case: markdown filter uses current_url if no params
    if filter_name == "markdown" and not param_string and current_url:
        params = current_url

    # Special case: fragment_link appends current_url
    if filter_name == "fragment_link" and current_url:
        params = f"{params}:{current_url}" if params else current_url

    # Apply the filter
    output = filter_fn(string_input, params)

    # If output looks like JSON, normalize it
    if isinstance(output, str) and (output.startswith('[') or output.startswith('{')):
        try:
            parsed = json.loads(output)
            return json.dumps(parsed)
        except (json.JSONDecodeError, ValueError):
            pass

    return str(output) if not isinstance(output, str) else output


def apply_filters(value: Any, filter_string: str, current_url: str = "") -> str:
    """
    Apply a pipe-separated filter string to a value.
    e.g., "lower|replace:\"old\":\"new\"|capitalize"
    """
    if not filter_string:
        return str(value) if not isinstance(value, str) else value

    result = value
    filter_names = _split_filter_string(filter_string)

    for f in filter_names:
        name, params = _parse_filter_string(f)
        filter_fn = FILTER_REGISTRY.get(name)
        if filter_fn:
            string_input = str(result) if not isinstance(result, str) else result

            # Special cases
            param_str = ":".join(params) if params else ""
            if name == "markdown" and not param_str and current_url:
                param_str = current_url
            if name == "fragment_link" and current_url:
                param_str = f"{param_str}:{current_url}" if param_str else current_url

            output = filter_fn(string_input, param_str)
            if isinstance(output, str) and (output.startswith('[') or output.startswith('{')):
                try:
                    result = json.loads(output)
                except (json.JSONDecodeError, ValueError):
                    result = output
            else:
                result = output
        else:
            # Unknown filter — skip
            pass

    return str(result) if not isinstance(result, str) else result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _split_filter_string(filter_string: str) -> list[str]:
    """Split a pipe-separated filter string, respecting quotes and parens."""
    filters_list = []
    current = ""
    in_quote = False
    quote_char = ""
    paren_depth = 0

    # Remove spaces around pipes that are not within quotes or parentheses
    # Simple approach: iterate character by character
    i = 0
    while i < len(filter_string):
        c = filter_string[i]
        if c in ('"', "'") and not in_quote:
            in_quote = True
            quote_char = c
            current += c
        elif c == quote_char and in_quote:
            in_quote = False
            quote_char = ""
            current += c
        elif c == '(' and not in_quote:
            paren_depth += 1
            current += c
        elif c == ')' and not in_quote and paren_depth > 0:
            paren_depth -= 1
            current += c
        elif c == '|' and not in_quote and paren_depth == 0:
            filters_list.append(current.strip())
            current = ""
        else:
            current += c
        i += 1

    if current.strip():
        filters_list.append(current.strip())

    return filters_list


def _parse_filter_string(filter_string: str) -> tuple[str, list[str]]:
    """Parse a filter string like 'replace:"old":"new"' into (name, [params])."""
    parts = []
    current = ""
    in_quote = False
    quote_char = ""

    for c in filter_string:
        if c in ('"', "'") and not in_quote:
            in_quote = True
            quote_char = c
            current += c
        elif c == quote_char and in_quote:
            in_quote = False
            quote_char = ""
            current += c
        elif c == ':' and not in_quote and not parts:
            parts.append(current.strip())
            current = ""
        else:
            current += c

    if current.strip():
        parts.append(current.strip())

    name = parts[0] if parts else filter_string
    params = parts[1:] if len(parts) > 1 else []

    return name, params
