# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                  filters/math_filters.py                                #
# ========================================================================================#
"""
Math filter functions.
Ported from obsidize/src/filters/calc.ts, round.ts, number_format.ts.

Each filter has signature ``(value: str, params: str) -> str | list``.
"""

import builtins
import json
import re
from typing import Any

__all__ = ["calc", "round", "number_format"]


# ---------------------------------------------------------------------------#
# calc                                                                        #
# ---------------------------------------------------------------------------#

def calc(value: str, params: str = "") -> str:
    """Perform simple arithmetic on a numeric *value*.

    ``params`` is an operation string like ``"+10"``, ``"*2"``, ``"**3"``,
    ``"^2"``, ``"/3"``.
    """
    if not params:
        return value

    try:
        num = float(value)
    except (ValueError, TypeError):
        return value

    # Strip outer quotes
    operation = re.sub(r'^["\'](.*)["\']$', r'\1', params).strip()

    # Determine operator (check ** before single-char)
    operator = "**" if operation.startswith("**") else operation[0]
    value_str = operation[len(operator):]

    try:
        operand = float(value_str)
    except (ValueError, TypeError):
        return value

    if operator == "+":
        result = num + operand
    elif operator == "-":
        result = num - operand
    elif operator == "*":
        result = num * operand
    elif operator == "/":
        result = num / operand
    elif operator in ("**", "^"):
        result = num ** operand
    else:
        return value

    # Mirror TS: Number(result.toFixed(10)).toString()
    # Format to 10 decimal places, then strip trailing zeros
    fixed = f"{result:.10f}".rstrip("0").rstrip(".")
    return fixed


# ---------------------------------------------------------------------------#
# round                                                                       #
# ---------------------------------------------------------------------------#

def round(value: str, params: str = "") -> str:
    """Round a number, array of numbers, or numeric values in an object.

    ``params`` is the number of decimal places (default: 0 / integer).
    """
    def _round_number(num: float, decimal_places: int | None = None) -> float | int:
        if decimal_places is None:
            return builtins.round(num)
        factor = 10 ** decimal_places
        return builtins.round(num * factor) / factor

    def _process(val: Any, dp: int | None = None) -> Any:
        if isinstance(val, (int, float)):
            return _round_number(val, dp)
        if isinstance(val, str):
            try:
                n = float(val)
            except (ValueError, TypeError):
                return val
            result = _round_number(n, dp)
            return str(result)
        if isinstance(val, list):
            return [_process(item, dp) for item in val]
        if isinstance(val, dict):
            return {k: _process(v, dp) for k, v in val.items()}
        return val

    decimal_places: int | None = None
    if params:
        try:
            decimal_places = int(params)
        except (ValueError, TypeError):
            return value

    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        parsed = value

    result = _process(parsed, decimal_places)
    if isinstance(result, str):
        return result
    return json.dumps(result)


# ---------------------------------------------------------------------------#
# number_format                                                               #
# ---------------------------------------------------------------------------#

def number_format(value: str, params: str = "") -> str:
    """Format a number with configurable decimal places, decimal point and
    thousands separator.

    ``params`` may be ``"2"``, ``"2,."``, or ``"2,.,,"`` (decimals, dec_point,
    thousands_sep).
    """
    def _format_number(num: float, decimals: int, dec_point: str, thousands_sep: str) -> str:
        fixed = f"{num:.{decimals}f}"
        if "." in fixed:
            int_part, frac_part = fixed.split(".", 1)
        else:
            int_part, frac_part = fixed, ""
        # Add thousands separator
        int_part = re.sub(r'\B(?=(\d{3})+(?!\d))', thousands_sep, int_part)
        if frac_part:
            return f"{int_part}{dec_point}{frac_part}"
        return int_part

    def _process(val: Any, decimals: int, dec_point: str, thousands_sep: str) -> Any:
        if isinstance(val, (int, float)):
            return _format_number(float(val), decimals, dec_point, thousands_sep)
        if isinstance(val, str):
            try:
                n = float(val)
            except (ValueError, TypeError):
                return val
            return _format_number(n, decimals, dec_point, thousands_sep)
        if isinstance(val, list):
            return [_process(item, decimals, dec_point, thousands_sep) for item in val]
        if isinstance(val, dict):
            return {k: _process(v, decimals, dec_point, thousands_sep) for k, v in val.items()}
        return val

    def _unescape(s: str) -> str:
        return re.sub(r'\\(.)', r'\1', s)

    # Parse parameters
    decimals = 0
    dec_point = "."
    thousands_sep = ","

    if params:
        clean = re.sub(r'^\((.*)\)$', r'\1', params)

        # Split respecting quotes and escapes
        parts: list[str] = []
        current = ""
        in_quote = False
        escape_next = False

        for ch in clean:
            if escape_next:
                current += ch
                escape_next = False
            elif ch == "\\":
                current += ch
                escape_next = True
            elif ch == '"' and not in_quote:
                in_quote = True
                current += ch
            elif ch == '"' and in_quote:
                in_quote = False
                current += ch
            elif ch == "," and not in_quote:
                parts.append(current.strip())
                current = ""
            else:
                current += ch
        if current:
            parts.append(current.strip())

        if len(parts) >= 1:
            try:
                decimals = int(parts[0])
            except (ValueError, TypeError):
                decimals = 0
        if len(parts) >= 2:
            dec_point = _unescape(re.sub(r'^["\'](.*)["\']$', r'\1', parts[1]))
        if len(parts) >= 3:
            thousands_sep = _unescape(re.sub(r'^["\'](.*)["\']$', r'\1', parts[2]))

    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        parsed = value

    result = _process(parsed, decimals, dec_point, thousands_sep)
    if isinstance(result, str):
        return result
    return json.dumps(result)
