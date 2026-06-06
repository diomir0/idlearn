# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                  filters/date_filters.py                                #
# ========================================================================================#
"""
Date/time filter functions.
Ported from obsidize/src/filters/date.ts, date_modify.ts, duration.ts.

Each filter has signature ``(value: str, params: str) -> str | list``.
"""

import re
from datetime import datetime, timedelta
from dateutil import parser as dateutil_parser

__all__ = ["date", "date_modify", "duration"]


# ---------------------------------------------------------------------------#
# Helpers                                                                     #
# ---------------------------------------------------------------------------#

# Mapping from dayjs format tokens to Python ``strftime`` tokens.
# Keys are dayjs tokens ordered longest-first so the regex replaces
# the most specific match first.
DAYJS_TO_STRFTIME: list[tuple[str, str]] = [
    # Must be ordered longest-first to avoid partial replacement
    # (e.g., YYYY before YY, MMMM before MMM before MM before M)
    # Compound / dayjs advanced format tokens
    ("YYYY", "%Y"),
    ("YY", "%y"),
    ("MMMM", "%B"),
    ("MMM", "%b"),
    ("MM", "%m"),
    ("M", "%-m"),   # month no zero-pad
    ("DDDD", "%j"),  # day of year
    ("DDD", "%-j"),  # day of year no-pad
    ("DD", "%d"),
    ("D", "%-d"),    # day no zero-pad
    ("HH", "%H"),
    ("H", "%-H"),    # hour 24h no-pad
    ("hh", "%I"),
    ("h", "%-I"),    # hour 12h no-pad
    ("mm", "%M"),    # minutes (dayjs mm = strftime %M)
    ("m", "%-M"),    # minutes no-pad (dayjs m = strftime %-M)
    ("ss", "%S"),
    ("s", "%-S"),     # seconds no-pad
    ("A", "%p"),
    ("a", "%p"),      # lowercase am/pm mapped to same
    ("ZZ", "%z"),
    ("Z", "%z"),
    ("ww", "%V"),
    ("w", "%-V"),
    ("dddd", "%A"),
    ("ddd", "%a"),
]


def _dayjs_to_strftime(fmt: str) -> str:
    """Convert a dayjs-style format string to a Python ``strftime`` format string.

    Uses a placeholder approach to avoid partial replacement conflicts
    (e.g., MM being replaced as two M tokens, or % being re-matched).
    """
    # Sort tokens by length (longest first) to avoid partial matches
    sorted_tokens = sorted(DAYJS_TO_STRFTIME, key=lambda x: len(x[0]), reverse=True)

    # Phase 1: Replace dayjs tokens with unique placeholders
    result = fmt
    placeholders = {}
    for i, (token, strftime_token) in enumerate(sorted_tokens):
        placeholder = f"\x00{i}\x00"
        placeholders[placeholder] = strftime_token
        result = result.replace(token, placeholder)

    # Phase 2: Replace placeholders with strftime tokens
    for placeholder, strftime_token in placeholders.items():
        result = result.replace(placeholder, strftime_token)

    return result


def _parse_duration_string(param: str) -> tuple[str, int, str]:
    """Parse a duration param like ``"+1 day"`` or ``"-2 hours"``.

    Returns ``(sign, amount, unit)`` where *sign* is ``"+"`` or ``"-"``,
    *amount* is an int, and *unit* is a normalised singular form
    (``"year"``, ``"month"``, ``"week"``, ``"day"``, ``"hour"``,
    ``"minute"``, ``"second"``).
    """
    # Strip outer parentheses / quotes
    param = re.sub(r'^\((.*)\)$', r'\1', param)
    param = re.sub(r"^(['\"])([\s\S]*)\1$", r'\2', param).strip()

    match = re.match(r'^([+-])\s*(\d+)\s*(\w+)s?$', param)
    if not match:
        raise ValueError(f"Invalid duration format: {param!r}")

    sign = match.group(1)
    amount = int(match.group(2))
    unit = match.group(3).lower().rstrip("s")  # normalise to singular

    valid_units = {"year", "month", "week", "day", "hour", "minute", "second"}
    if unit not in valid_units:
        raise ValueError(f"Invalid unit: {unit!r}")

    return sign, amount, unit


def _add_duration(dt: datetime, sign: str, amount: int, unit: str) -> datetime:
    """Add or subtract a duration from a ``datetime``."""
    delta = amount if sign == "+" else -amount
    mapping = {
        "year": "years",
        "month": "months",
        "week": "weeks",
        "day": "days",
        "hour": "hours",
        "minute": "minutes",
        "second": "seconds",
    }
    from dateutil.relativedelta import relativedelta

    kwarg = mapping[unit]
    if unit in ("year", "month"):
        return dt + relativedelta(**{kwarg: delta})
    else:
        return dt + timedelta(**{kwarg: delta})


# ---------------------------------------------------------------------------#
# date                                                                        #
# ---------------------------------------------------------------------------#

def date(value: str, params: str = "") -> str:
    """Format a date string using a dayjs-compatible format.

    ``params`` may be:
    - empty       → default format ``YYYY-MM-DD``
    - ``"YYYY-MM-DD"`` → output format only
    - ``"YYYY-MM-DD, DD/MM/YYYY"`` → output format, input format

    The input ``"now"`` is replaced with the current date/time.
    """
    if value == "":
        return value

    input_date_str = datetime.now().isoformat() if value == "now" else value

    if not params:
        return datetime.fromisoformat(
            _ensure_iso(input_date_str)
        ).strftime("%Y-%m-%d")

    # Strip outer parens
    params = re.sub(r'^\((.*)\)$', r'\1', params)

    # Split by commas respecting quoted strings
    parts = _split_respecting_quotes(params)
    parts = [re.sub(r"^(['\"])([\s\S]*)\1$", r'\2', p.strip()) for p in parts]

    output_format = parts[0] if len(parts) >= 1 else "YYYY-MM-DD"
    input_format = parts[1] if len(parts) >= 2 else None

    dt: datetime | None = None
    try:
        if input_format:
            input_strftime = _dayjs_to_strftime(input_format)
            dt = datetime.strptime(input_date_str, input_strftime)
        else:
            dt = datetime.fromisoformat(_ensure_iso(input_date_str))
    except (ValueError, OverflowError):
        # Fallback: try dateutil parser
        try:
            dt = dateutil_parser.parse(input_date_str)  # type: ignore[assignment]
        except (ValueError, OverflowError):
            return value

    if dt is None:
        return value

    output_strftime = _dayjs_to_strftime(output_format)
    return dt.strftime(output_strftime)


def _ensure_iso(s: str) -> str:
    """Best-effort normalisation of a date string to ISO-8601.

    Python's ``datetime.fromisoformat`` is strict; this helper prepends
    a date portion when the string looks like a time-only value and handles
    a few other common patterns.
    """
    s = s.strip()
    if re.match(r'^\d{1,2}:\d{2}', s):
        s = f"1970-01-01 {s}"
    return s


def _split_respecting_quotes(s: str) -> list[str]:
    """Split *s* by commas, respecting single/double-quoted regions."""
    parts: list[str] = []
    current = ""
    in_quote: str | None = None
    for ch in s:
        if ch in ('"', "'") and in_quote is None:
            in_quote = ch
            current += ch
        elif ch == in_quote:
            in_quote = None
            current += ch
        elif ch == ',' and in_quote is None:
            parts.append(current)
            current = ""
        else:
            current += ch
    if current:
        parts.append(current)
    return parts


# ---------------------------------------------------------------------------#
# date_modify                                                                 #
# ---------------------------------------------------------------------------#

def date_modify(value: str, params: str = "") -> str:
    """Add or subtract a duration from a date string.

    ``params`` is a duration string like ``"+1 day"`` or ``"-2 hours"``.
    """
    if not params:
        return value

    if value == "":
        return value

    dt: datetime | None = None
    try:
        dt = datetime.fromisoformat(_ensure_iso(value))
    except (ValueError, OverflowError):
        try:
            dt = dateutil_parser.parse(value)  # type: ignore[assignment]
        except (ValueError, OverflowError):
            return value

    if dt is None:
        return value

    try:
        sign, amount, unit = _parse_duration_string(params)
    except ValueError:
        return value

    dt = _add_duration(dt, sign, amount, unit)
    return dt.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------#
# duration                                                                    #
# ---------------------------------------------------------------------------#

def duration(value: str, params: str = "") -> str:
    """Format a duration (in seconds or ISO 8601) as a human-readable string.

    ``params`` may be a format string like ``"HH:mm:ss"`` using dayjs-style
    tokens (``HH``, ``H``, ``mm``, ``m``, ``ss``, ``s``).
    """
    if not value:
        return value

    # Strip outer quotes
    value = re.sub(r'^["\'](.*)["\']$', r'\1', value)

    # Try ISO 8601 duration first
    iso_match = re.match(
        r'^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?'
        r'(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$',
        value,
    )
    if iso_match:
        years = int(iso_match.group(1) or 0)
        months = int(iso_match.group(2) or 0)
        days = int(iso_match.group(3) or 0)
        hours = int(iso_match.group(4) or 0)
        minutes = int(iso_match.group(5) or 0)
        seconds = int(iso_match.group(6) or 0)

        total_seconds = (
            years * 365 * 24 * 3600
            + months * 30 * 24 * 3600
            + days * 24 * 3600
            + hours * 3600
            + minutes * 60
            + seconds
        )
    else:
        # Try plain number (seconds)
        try:
            total_seconds = int(value)
        except ValueError:
            return value

    return _format_duration(total_seconds, params)


def _format_duration(total_seconds: int, fmt: str | None = None) -> str:
    """Format *total_seconds* according to a dayjs-style duration format string."""
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if not fmt:
        fmt = "HH:mm:ss" if hours >= 1 else "mm:ss"

    # Strip outer quotes / parens
    fmt = re.sub(r'^["\(](.*)["\)]$', r'\1', fmt)

    parts: dict[str, str] = {
        "HH": f"{hours:02d}",
        "H": str(hours),
        "mm": f"{minutes:02d}",
        "m": str(minutes),
        "ss": f"{seconds:02d}",
        "s": str(seconds),
    }

    # Replace longest tokens first
    result = fmt
    for token in ("HH", "H", "mm", "m", "ss", "s"):
        result = result.replace(token, parts[token])
    return result
