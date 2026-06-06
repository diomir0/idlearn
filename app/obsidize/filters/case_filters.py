# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                  filters/case_filters.py                                #
# ========================================================================================#
"""
Case-transform filter functions.
Ported from obsidize/src/filters/camel.ts, kebab.ts, snake.ts, pascal.ts, uncamel.ts.

Each filter has signature ``(value: str, params: str) -> str | list``.
"""

import re

__all__ = ["camel", "kebab", "snake", "pascal", "uncamel"]


# ---------------------------------------------------------------------------#
# camel                                                                      #
# ---------------------------------------------------------------------------#

def camel(value: str, params: str = "") -> str:
    """Convert *value* to camelCase.

    Mirrors the TypeScript implementation:
      1. Capitalise the first letter of each word boundary (start of string,
         after whitespace, underscore, hyphen).
      2. Lowercase the very first character.
      3. Remove all whitespace, underscores and hyphens.
    """
    def _upper_match(m: re.Match) -> str:
        idx = m.start()
        return m.group(0).upper() if idx != 0 else m.group(0).lower()

    result = re.sub(r'(?:^\w|[A-Z]|\b\w)', _upper_match, value)
    result = re.sub(r'[\s_-]+', '', result)
    return result


# ---------------------------------------------------------------------------#
# kebab                                                                       #
# ---------------------------------------------------------------------------#

def kebab(value: str, params: str = "") -> str:
    """Convert *value* to kebab-case."""
    result = re.sub(r'([a-z])([A-Z])', r'\1-\2', value)
    result = re.sub(r'[\s_]+', '-', result)
    return result.lower()


# ---------------------------------------------------------------------------#
# snake                                                                       #
# ---------------------------------------------------------------------------#

def snake(value: str, params: str = "") -> str:
    """Convert *value* to snake_case."""
    result = re.sub(r'([a-z])([A-Z])', r'\1_\2', value)
    result = re.sub(r'[\s-]+', '_', result)
    return result.lower()


# ---------------------------------------------------------------------------#
# pascal                                                                      #
# ---------------------------------------------------------------------------#

def pascal(value: str, params: str = "") -> str:
    """Convert *value* to PascalCase."""
    result = re.sub(r'[\s_-]+(.)', lambda m: m.group(1).upper(), value)
    result = re.sub(r'^(.)', lambda m: m.group(1).upper(), result)
    return result


# ---------------------------------------------------------------------------#
# uncamel                                                                     #
# ---------------------------------------------------------------------------#

def uncamel(value: str, params: str = "") -> str:
    """Convert a camelCase string to space-separated lowercase words.

    Mirrors the TypeScript implementation:
      1. Insert a space before any uppercase letter that follows a lowercase
         letter or digit.
      2. Insert a space before an uppercase letter that follows another
         uppercase letter and is followed by a lowercase letter.
      3. Lowercase the result.
    """
    result = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', value)
    result = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', result)
    return result.lower()
