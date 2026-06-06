# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                               filters/collection_filters.py                             #
# ========================================================================================#
"""
Collection / array filter functions.
Ported from obsidize/src/filters/split.ts, join.ts, first.ts, last.ts,
length.ts, slice.ts, nth.ts, reverse.ts, unique.ts, map.ts, merge.ts.

Each filter has signature ``(value: str, params: str) -> str | list``.
"""

import json
import re
from typing import Any

__all__ = [
    "split", "join", "first", "last", "length",
    "slice", "nth", "reverse", "unique",
    "map", "merge",
]


# ---------------------------------------------------------------------------#
# Helpers                                                                     #
# ---------------------------------------------------------------------------#

def _strip_outer_quotes(s: str) -> str:
    """Remove surrounding single or double quotes from *s*."""
    return re.sub(r"^(['\"])([\s\S]*)\1$", r"\2", s)


def _strip_outer_parens(s: str) -> str:
    """Remove outer parentheses wrapping the string, if present."""
    return re.sub(r"^\((.*)\)$", r"\1", s)


def _try_parse_json(s: str) -> tuple[Any, bool]:
    """Attempt to parse *s* as JSON.

    Returns ``(parsed_value, True)`` on success, ``(s, False)`` on failure.
    """
    try:
        return json.loads(s), True
    except (json.JSONDecodeError, ValueError):
        return s, False


# ---------------------------------------------------------------------------#
# split                                                                       #
# ---------------------------------------------------------------------------#

def split(value: str, params: str = "") -> str:
    """Split *value* by a delimiter.

    If *params* is empty, split into individual characters.
    Otherwise *params* is used as the separator (single char or regex).
    """
    if not params or params == "":
        return json.dumps(list(value))

    param = _strip_outer_parens(params)
    param = _strip_outer_quotes(param)

    if len(param) == 1:
        result = value.split(param)
    else:
        result = re.split(param, value)

    return json.dumps(result)


# ---------------------------------------------------------------------------#
# join                                                                         #
# ---------------------------------------------------------------------------#

def join(value: str, params: str = "") -> str:
    """Join a JSON array by *params* (default ``","``)."""
    if not value or value in ("undefined", "null"):
        return ""

    try:
        array = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value

    if not isinstance(array, list):
        return value

    separator = ","
    if params:
        separator = _strip_outer_quotes(params)
        separator = separator.replace("\\n", "\n")

    return separator.join(str(item) for item in array)


# ---------------------------------------------------------------------------#
# first                                                                       #
# ---------------------------------------------------------------------------#

def first(value: str, params: str = "") -> str:
    """Return the first element of a JSON array."""
    if value == "":
        return value

    try:
        array = json.loads(value)
        if isinstance(array, list) and len(array) > 0:
            return str(array[0])
    except (json.JSONDecodeError, ValueError):
        pass
    return value


# ---------------------------------------------------------------------------#
# last                                                                        #
# ---------------------------------------------------------------------------#

def last(value: str, params: str = "") -> str:
    """Return the last element of a JSON array."""
    if value == "":
        return value

    try:
        array = json.loads(value)
        if isinstance(array, list) and len(array) > 0:
            return str(array[-1])
    except (json.JSONDecodeError, ValueError):
        pass
    return value


# ---------------------------------------------------------------------------#
# length                                                                      #
# ---------------------------------------------------------------------------#

def length(value: str, params: str = "") -> str:
    """Return the length of a string, array, or object."""
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return str(len(parsed))
        if isinstance(parsed, dict):
            return str(len(parsed))
    except (json.JSONDecodeError, ValueError):
        pass
    return str(len(value))


# ---------------------------------------------------------------------------#
# slice                                                                        #
# ---------------------------------------------------------------------------#

def slice(value: str, params: str = "") -> str:
    """Slice a string or JSON array.

    ``params`` is ``"start,end"`` or just ``"start"``.
    """
    if not params:
        return value
    if value == "":
        return value

    parts = params.split(",")
    start = int(float(parts[0].strip())) if parts[0].strip() else None
    end = int(float(parts[1].strip())) if len(parts) > 1 and parts[1].strip() else None

    # Clamp None-ish values
    start = start if start is not None and not (isinstance(start, float) and start != start) else None
    end = end if end is not None and not (isinstance(end, float) and end != end) else None

    parsed, ok = _try_parse_json(value)
    if ok and isinstance(parsed, list):
        sliced = parsed[start:end]
        if len(sliced) == 1:
            return str(sliced[0])
        return json.dumps(sliced)
    else:
        s = value[start:end]
        return s


# ---------------------------------------------------------------------------#
# nth                                                                         #
# ---------------------------------------------------------------------------#

def nth(value: str, params: str = "") -> str:
    """Get elements from a JSON array at positions matching CSS-style ``nth`` expressions.

    Supports:
    - Simple number (e.g. ``"2"``) → 1-based position
    - Multiplier (e.g. ``"5n"``) → every Nth element
    - Offset (e.g. ``"n+7"``) → elements at position >= offset
    - Basis (e.g. ``"1,2,3:7"``) → modular positions
    """
    if not value or value in ("undefined", "null"):
        return value

    try:
        data = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value

    if not isinstance(data, list):
        return value

    # No params → return all items
    if not params:
        return json.dumps(data)

    # Basis pattern: "1,2,3:7"
    if ":" in params:
        positions_str, basis_str = params.split(":", 1)
        nth_values = [
            int(n.strip()) for n in positions_str.split(",")
            if n.strip().isdigit() and int(n.strip()) > 0
        ]
        try:
            basis_size = int(basis_str.strip())
        except ValueError:
            return json.dumps(data)

        return json.dumps([
            item for idx, item in enumerate(data)
            if (idx % basis_size + 1) in nth_values
        ])

    expr = params.strip()

    # Simple number
    if re.match(r'^\d+$', expr):
        position = int(expr)
        return json.dumps([item for idx, item in enumerate(data) if idx + 1 == position])

    # Multiplier: "5n"
    if re.match(r'^\d+n$', expr):
        multiplier = int(expr.replace("n", ""))
        return json.dumps([
            item for idx, item in enumerate(data)
            if (idx + 1) % multiplier == 0
        ])

    # Offset: "n+7"
    offset_match = re.match(r'^n\+(\d+)$', expr)
    if offset_match:
        offset = int(offset_match.group(1))
        return json.dumps([
            item for idx, item in enumerate(data)
            if (idx + 1) >= offset
        ])

    return value


# ---------------------------------------------------------------------------#
# reverse                                                                     #
# ---------------------------------------------------------------------------#

def reverse(value: str, params: str = "") -> str:
    """Reverse a string, array, or object."""
    if not value or value in ("undefined", "null"):
        return ""

    parsed, ok = _try_parse_json(value)
    if ok:
        if isinstance(parsed, list):
            return json.dumps(list(reversed(parsed)))
        if isinstance(parsed, dict):
            reversed_obj = dict(reversed(list(parsed.items())))
            return json.dumps(reversed_obj)
    # Plain string
    return value[::-1]


# ---------------------------------------------------------------------------#
# unique                                                                      #
# ---------------------------------------------------------------------------#

def unique(value: str, params: str = "") -> str:
    """Remove duplicates from a JSON array or object values."""
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value

    if isinstance(parsed, list):
        # For arrays of primitives, use set
        if all(not isinstance(item, (dict, list)) for item in parsed):
            seen: set = set()
            result = []
            for item in parsed:
                key = (type(item).__name__, item)
                if key not in seen:
                    seen.add(key)
                    result.append(item)
            return json.dumps(result)

        # For arrays of objects, compare stringified versions
        seen_str: set = set()
        result = []
        for item in parsed:
            s = json.dumps(item, sort_keys=True)
            if s not in seen_str:
                seen_str.add(s)
                result.append(item)
        return json.dumps(result)

    if isinstance(parsed, dict):
        # Remove duplicate values keeping last occurrence's key
        reversed_entries = list(reversed(list(parsed.items())))
        seen_val: set = set()
        unique_entries = []
        for k, v in reversed_entries:
            vs = json.dumps(v, sort_keys=True)
            if vs not in seen_val:
                seen_val.add(vs)
                unique_entries.append((k, v))
        return json.dumps(dict(reversed(unique_entries)))

    return value


# ---------------------------------------------------------------------------#
# map                                                                         #
# ---------------------------------------------------------------------------#

def map(value: str, params: str = "") -> str:
    """Map a JSON array using a simple arrow-function expression.

    ``params`` should be like ``"x => x.name"`` or ``"x => ({key: x.prop})"``.
    """
    try:
        array = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        array = [value]

    if not isinstance(array, list) or not params:
        return value

    # Parse arrow function: "x => expression"
    arrow_match = re.match(r'^\s*(\w+)\s*=>\s*(.+)$', params, re.DOTALL)
    if not arrow_match:
        return value

    arg_name = arrow_match.group(1)
    expression = arrow_match.group(2).strip()

    # Strip outer parens from expression
    if expression.startswith("(") and expression.endswith(")"):
        expression = expression[1:-1].strip()

    result = [_evaluate_map_expr(item, arg_name, expression) for item in array]
    return json.dumps(result)


def _evaluate_map_expr(item: Any, arg_name: str, expression: str) -> Any:
    """Evaluate a simple map expression for a single *item*."""
    # Object literal: "{key: x.prop}"
    if expression.startswith("{") and expression.endswith("}"):
        inner = expression[1:-1].strip()
        mapped: dict[str, Any] = {}
        for assignment in _split_object_assignments(inner):
            key, value_expr = assignment.split(":", 1)
            key = _strip_outer_quotes(key.strip())
            mapped[key] = _resolve_value(item, arg_name, value_expr.strip())
        return mapped

    # String literal: "${x}"
    if (expression.startswith('"') and expression.endswith('"')) or \
       (expression.startswith("'") and expression.endswith("'")):
        template = expression[1:-1]
        return template.replace(f"${{{arg_name}}}", str(item))

    # Simple property access or the arg itself
    return _resolve_value(item, arg_name, expression)


def _resolve_value(item: Any, arg_name: str, expr: str) -> Any:
    """Resolve a property path like ``x.name`` or ``x.items[0].title``."""
    if isinstance(item, str):
        return item

    # Replace arg_name.property chains
    pattern = re.compile(rf'{re.escape(arg_name)}\.([\w.\[\]]+)')

    def _getter(m: re.Match) -> str:
        path = m.group(1)
        val = _get_nested(item, path)
        return json.dumps(val) if isinstance(val, (dict, list)) else str(val) if val is not None else ""

    result = pattern.sub(_getter, expr)
    # If the entire expression was just a property path, try to parse the result
    try:
        return json.loads(result)
    except (json.JSONDecodeError, ValueError):
        # Strip surrounding quotes if present
        return re.sub(r'^["\'](.+)["\']$', r'\1', result)


def _get_nested(obj: Any, path: str) -> Any:
    """Traverse nested properties using a dot/bracket path string."""
    keys = [k for k in re.split(r'[\.\[\]]', path) if k]
    current = obj
    for key in keys:
        if current is None:
            return None
        if isinstance(current, list) and key.isdigit():
            idx = int(key)
            current = current[idx] if idx < len(current) else None
        elif isinstance(current, dict):
            current = current.get(key)
        else:
            return None
    return current


def _split_object_assignments(s: str) -> list[str]:
    """Split ``{key: value, key2: value2}`` inner text by commas,
    respecting nested structures.
    """
    parts: list[str] = []
    depth = 0
    current = ""
    for ch in s:
        if ch in ("(", "{", "["):
            depth += 1
            current += ch
        elif ch in (")", "}", "]"):
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())
    return parts


# ---------------------------------------------------------------------------#
# merge                                                                       #
# ---------------------------------------------------------------------------#

def merge(value: str, params: str = "") -> str:
    """Merge a JSON array with additional items from *params*."""
    if not value or value in ("undefined", "null"):
        return "[]"

    try:
        array = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        array = [value]

    if not isinstance(array, list):
        array = [value]

    if not params:
        return json.dumps(array)

    param = _strip_outer_parens(params)

    # Split by commas respecting quotes
    additional_items = re.findall(r'(?:[^,"\']+|"[^"]*"|\'[^\']*\')+', param)
    processed = []
    for item in additional_items:
        item = item.strip()
        item = _strip_outer_quotes(item)
        processed.append(item)

    return json.dumps(array + processed)
