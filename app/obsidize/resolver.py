# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                     resolver.py                                        #
# ========================================================================================#
"""
Variable resolution for the Obsidize template engine.
Ported from obsidize/src/utils/resolver.ts.
"""

from typing import Any


def resolve_variable(name: str, variables: dict[str, Any]) -> Any:
    """
    Resolve a variable name to its value from the variables context.

    Handles:
    - Simple variables: "title" → variables["{{title}}"] or variables["title"]
    - Nested paths: "author.name" → variables.author.name
    - Array access: "items[0]" → variables.items[0]
    - Literals: "string", 123, true/false, null
    """
    trimmed = name.strip()

    # String literal
    if (trimmed.startswith('"') and trimmed.endswith('"')) or \
       (trimmed.startswith("'") and trimmed.endswith("'")):
        return trimmed[1:-1].replace('\\(', '(')

    # Number literal
    try:
        if trimmed.startswith('-') or trimmed[0].isdigit():
            if '.' in trimmed:
                return float(trimmed)
            return int(trimmed)
    except (ValueError, IndexError):
        pass

    # Boolean literals
    if trimmed == 'true':
        return True
    if trimmed == 'false':
        return False

    # Null/undefined literals
    if trimmed in ('null', 'undefined', 'none'):
        return None

    # Simple key (no dots or brackets) - try {{name}} wrapper first
    if '.' not in trimmed and '[' not in trimmed:
        wrapped_value = variables.get(f"{{{{{trimmed}}}}}")
        if wrapped_value is not None:
            return wrapped_value
        # Fall back to plain key (for locally set variables)
        if trimmed in variables:
            return variables[trimmed]

    # Nested path - try resolving from variables object
    return _get_nested_value(variables, trimmed)


def _get_nested_value(obj: Any, path: str) -> Any:
    """
    Get a nested value from an object using dot notation and bracket notation.
    Examples:
        "author.name" → obj.author.name
        "items[0]" → obj.items[0]
        "items[0].title" → obj.items[0].title
    """
    if not path or obj is None:
        return None

    keys = path.split('.')
    current = obj

    for key in keys:
        if current is None:
            return None

        # Handle bracket notation for array access: items[0]
        if '[' in key and key.endswith(']'):
            bracket_match_start = key.index('[')
            array_key = key[:bracket_match_start]
            bracket_content = key[bracket_match_start + 1:-1]

            # First resolve the array_key if present
            if array_key:
                if isinstance(current, dict):
                    current = current.get(array_key)
                elif isinstance(current, list):
                    try:
                        current = current[int(array_key)]
                    except (ValueError, IndexError):
                        return None
                else:
                    return None

            if current is None:
                return None

            # Then resolve the bracket index
            # Remove quotes from string keys: items["key"]
            bracket_key = bracket_content.strip('"').strip("'")

            if isinstance(current, list):
                try:
                    current = current[int(bracket_key)]
                except (ValueError, IndexError):
                    return None
            elif isinstance(current, dict):
                current = current.get(bracket_key)
            else:
                return None
        else:
            # Simple key access
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list):
                try:
                    current = current[int(key)]
                except (ValueError, IndexError):
                    return None
            else:
                return None

    return current


def value_to_string(value: Any) -> str:
    """Convert any value to a string for template output."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (list, dict)):
        import json
        return json.dumps(value)
    return str(value)


def resolve_schema_variable(schema_key: str, variables: dict[str, Any]) -> Any:
    """Resolve a schema variable (schema:key format)."""
    # Try direct lookup: {{schema:@type}}
    value = variables.get(f"{{{{{schema_key}}}}}")
    if value is not None:
        return value

    # Try shorthand notation
    short_key = schema_key.replace('schema:', '', 1)
    if '@' not in short_key:
        for key in variables:
            if '@' in key and key.endswith(f':{short_key}}}'):
                return variables[key]

    return None
