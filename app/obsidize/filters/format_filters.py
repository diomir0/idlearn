# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                filters/format_filters.py                                #
# ========================================================================================#
"""
Formatting filter functions.
Ported from obsidize/src/filters/object.ts, template.ts.

Each filter has signature ``(value: str, params: str) -> str | list``.
"""

import json
import re
from typing import Any

__all__ = ["object", "template"]


# ---------------------------------------------------------------------------#
# Helpers                                                                     #
# ---------------------------------------------------------------------------#

def _strip_outer_quotes(s: str) -> str:
    return re.sub(r"^(['\"])([\s\S]*)\1$", r"\2", s)


def _strip_outer_parens(s: str) -> str:
    return re.sub(r"^\((.*)\)$", r"\1", s)


def _get_nested(obj: Any, path: str) -> Any:
    """Traverse nested properties using a dot-separated path string."""
    current = obj
    for key in path.split("."):
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and key.isdigit():
            idx = int(key)
            current = current[idx] if idx < len(current) else None
        else:
            return None
    return current


# ---------------------------------------------------------------------------#
# object                                                                      #
# ---------------------------------------------------------------------------#

def object(value: str, params: str = "") -> str:
    """Extract keys, values, or entries from a JSON object.

    ``params`` must be ``"array"``, ``"keys"``, or ``"values"``.
    """
    try:
        obj = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        return value

    if not isinstance(obj, dict):
        return value

    if params == "array":
        return json.dumps(list(obj.items()))
    if params == "keys":
        return json.dumps(list(obj.keys()))
    if params == "values":
        return json.dumps(list(obj.values()))

    return value


# ---------------------------------------------------------------------------#
# template                                                                    #
# ---------------------------------------------------------------------------#

def template(value: str, params: str = "") -> str:
    """Simple template interpolation.

    ``params`` is a template string like ``"${name} is ${age}"``
    where ``${...}`` placeholders are replaced with properties from
    the JSON-parsed *value*.
    """
    if not params:
        return value if isinstance(value, str) else json.dumps(value)

    tmpl = _strip_outer_parens(params)
    tmpl = _strip_outer_quotes(tmpl)

    # Normalise \n escape sequences in the template
    tmpl = tmpl.replace("\\n", "\n")

    # Parse input as an array (or wrap in one)
    try:
        obj = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        obj = [value]

    if not isinstance(obj, list):
        obj = [obj]

    results: list[str] = []
    for item in obj:
        # If item is a plain string, make it available as ${str}
        if isinstance(item, str):
            try:
                parsed = json.loads(item)
                if isinstance(parsed, dict):
                    parsed["str"] = parsed.get("str", item)
                else:
                    parsed = {"str": item}
                item = parsed
            except (json.JSONDecodeError, ValueError):
                item = {"str": item}
        elif isinstance(item, dict):
            pass
        else:
            item = {"str": str(item)}

        result = _replace_template_variables(item, tmpl)
        # Remove empty lines caused by undefined values
        result = "\n".join(line for line in result.split("\n") if line.strip() != "")
        results.append(result.strip())

    return "\n\n".join(results)


def _replace_template_variables(obj: dict, template: str) -> str:
    """Replace ``${path}`` placeholders in *template* with values from *obj*."""
    def _replacer(m: re.Match) -> str:
        path = m.group(1)
        val = _get_nested(obj, path)
        if val is not None and val != "undefined":
            return str(val)
        return ""

    return re.sub(r'\$\{([\w.]+)\}', _replacer, template)
