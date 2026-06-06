# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                     tokenizer.py                                        #
# ========================================================================================#
"""
Template tokenizer for the Obsidize template engine.
Converts template strings into a stream of tokens for parsing.

Ported from obsidian-clipper/src/utils/tokenizer.ts

This tokenizer handles:
- Text content
- Variable tags: {{ variable|filter }} (preserves whitespace)
  - Trim markers: {{- and -}} strip adjacent whitespace
- Logic tags: {% if condition %}, {% for item in array %}, etc.
  - Trim markers: {%- and -%} strip adjacent whitespace
- Expressions: strings, numbers, booleans, null, identifiers, operators
- CSS selectors via selector: / selectorHtml: prefixes
- Error recovery for malformed templates
"""

from __future__ import annotations

from .types import Token, TokenizerError, TokenizerResult, TokenType

# ============================================================================
# Keywords
# ============================================================================

KEYWORDS: dict[str, str] = {
    "if": TokenType.KEYWORD_IF,
    "elseif": TokenType.KEYWORD_ELSEIF,
    "else": TokenType.KEYWORD_ELSE,
    "endif": TokenType.KEYWORD_ENDIF,
    "for": TokenType.KEYWORD_FOR,
    "in": TokenType.KEYWORD_IN,
    "endfor": TokenType.KEYWORD_ENDFOR,
    "set": TokenType.KEYWORD_SET,
    "and": TokenType.OP_AND,
    "or": TokenType.OP_OR,
    "not": TokenType.OP_NOT,
    "contains": TokenType.OP_CONTAINS,
    "true": TokenType.BOOLEAN,
    "false": TokenType.BOOLEAN,
    "null": TokenType.NULL,
}

# ============================================================================
# Tokenizer State
# ============================================================================


class _TokenizerState:
    """Mutable state carried through the tokenization pass."""

    __slots__ = ("input", "pos", "line", "column", "mode", "tokens", "errors")

    def __init__(self, input: str) -> None:
        self.input: str = input
        self.pos: int = 0
        self.line: int = 1
        self.column: int = 1
        self.mode: str = "text"  # "text" | "variable" | "tag"
        self.tokens: list[Token] = []
        self.errors: list[TokenizerError] = []


# ============================================================================
# Main Tokenizer Function
# ============================================================================


def tokenize(input: str) -> TokenizerResult:
    """Tokenize a template string into a stream of tokens.

    Returns a TokenizerResult containing the token list and any errors
    encountered during tokenization.
    """
    state = _TokenizerState(input)

    while state.pos < len(state.input):
        if state.mode == "text":
            _tokenize_text(state)
        elif state.mode == "variable":
            _tokenize_variable(state)
        elif state.mode == "tag":
            _tokenize_tag(state)

    # Detect unclosed variable / tag at end of input
    if state.mode == "variable":
        state.errors.append(
            TokenizerError(
                message="Unclosed variable - missing '}}'",
                line=state.line,
                column=state.column,
            )
        )
    elif state.mode == "tag":
        state.errors.append(
            TokenizerError(
                message="Unclosed tag - missing '%}'",
                line=state.line,
                column=state.column,
            )
        )

    # Append EOF sentinel
    state.tokens.append(
        Token(type=TokenType.EOF, value="", line=state.line, column=state.column)
    )

    return TokenizerResult(tokens=state.tokens, errors=state.errors)


# ============================================================================
# Text Mode Tokenization
# ============================================================================


def _tokenize_text(state: _TokenizerState) -> None:
    start_pos = state.pos
    start_line = state.line
    start_column = state.column

    while state.pos < len(state.input):
        # ---- Variable start: {{ (or {{- for trim) ----
        if _look_ahead(state, "{{"):
            # Emit any accumulated plain text
            if state.pos > start_pos:
                state.tokens.append(
                    Token(
                        type=TokenType.TEXT,
                        value=state.input[start_pos : state.pos],
                        line=start_line,
                        column=start_column,
                    )
                )

            _advance(state, 2)

            # Check for trim marker {{-
            trim_left = False
            if state.pos < len(state.input) and state.input[state.pos] == "-":
                trim_left = True
                _advance_char(state)

            state.tokens.append(
                Token(
                    type=TokenType.VARIABLE_START,
                    value="{{-" if trim_left else "{{",
                    line=state.line if not trim_left else state.line,
                    column=state.column - (3 if trim_left else 2),
                    trim_left=trim_left,
                )
            )
            state.mode = "variable"
            return

        # ---- Tag start: {% (or {%- for trim) ----
        if _look_ahead(state, "{%"):
            # Emit any accumulated plain text
            if state.pos > start_pos:
                state.tokens.append(
                    Token(
                        type=TokenType.TEXT,
                        value=state.input[start_pos : state.pos],
                        line=start_line,
                        column=start_column,
                    )
                )

            _advance(state, 2)

            # Check for trim marker {%-
            trim_left = False
            if state.pos < len(state.input) and state.input[state.pos] == "-":
                trim_left = True
                _advance_char(state)

            state.tokens.append(
                Token(
                    type=TokenType.TAG_START,
                    value="{%-" if trim_left else "{%",
                    line=state.line if not trim_left else state.line,
                    column=state.column - (3 if trim_left else 2),
                    trim_left=trim_left,
                )
            )
            state.mode = "tag"
            return

        # Regular character
        _advance_char(state)

    # End of input – emit remaining text
    if state.pos > start_pos:
        state.tokens.append(
            Token(
                type=TokenType.TEXT,
                value=state.input[start_pos : state.pos],
                line=start_line,
                column=start_column,
            )
        )


# ============================================================================
# Variable Mode Tokenization (inside {{ }})
# ============================================================================


def _tokenize_variable(state: _TokenizerState) -> None:
    _skip_whitespace(state)

    # ---- Trim marker: -}} ----
    if _look_ahead(state, "-}}"):
        state.tokens.append(
            Token(
                type=TokenType.VARIABLE_END,
                value="-}}",
                line=state.line,
                column=state.column,
                trim_right=True,
            )
        )
        _advance(state, 3)
        state.mode = "text"
        return

    # ---- Normal variable end: }} ----
    if _look_ahead(state, "}}"):
        state.tokens.append(
            Token(
                type=TokenType.VARIABLE_END,
                value="}}",
                line=state.line,
                column=state.column,
                trim_right=False,
            )
        )
        _advance(state, 2)
        state.mode = "text"
        return

    # ---- Malformed variable end: lone } ----
    # A single } that is NOT followed by } might be a typo.
    # However, allow } when followed by expression-safe characters
    # (e.g. }| for object literal + filter, }, as property separator).
    if state.pos < len(state.input) and state.input[state.pos] == "}":
        next_char = state.input[state.pos + 1] if state.pos + 1 < len(state.input) else ""
        valid_after_brace = ("|", ",", ")", "]", " ", "\t", "\n", "\r")
        if next_char not in valid_after_brace:
            state.errors.append(
                TokenizerError(
                    message="Malformed variable: expected '}}' but found '}'. "
                    "Did you forget a '}'?",
                    line=state.line,
                    column=state.column,
                )
            )
            # Emit a variable_end to prevent cascading errors
            state.tokens.append(
                Token(
                    type=TokenType.VARIABLE_END,
                    value="}",
                    line=state.line,
                    column=state.column,
                    trim_right=False,
                )
            )
            _advance_char(state)
            state.mode = "text"
            return

    # ---- Unclosed variable: new tag/variable starting ----
    if _look_ahead(state, "{%") or _look_ahead(state, "{{"):
        var_start_idx = _find_last_token_index(state.tokens, TokenType.VARIABLE_START)
        var_start = state.tokens[var_start_idx] if var_start_idx is not None else None
        start_line = var_start.line if var_start else state.line
        start_col = var_start.column if var_start else state.column
        state.errors.append(
            TokenizerError(
                message="Missing closing '}}' for variable",
                line=start_line,
                column=start_col,
            )
        )
        if var_start_idx is not None:
            # Remove the variable_start and everything after it
            del state.tokens[var_start_idx:]
        state.mode = "text"
        return

    # ---- Expression content ----
    _tokenize_expression(state, "variable")


# ============================================================================
# Tag Mode Tokenization (inside {% %})
# ============================================================================


def _tokenize_tag(state: _TokenizerState) -> None:
    _skip_whitespace(state)

    # ---- Tag end: %} ----
    if _look_ahead(state, "%}"):
        state.tokens.append(
            Token(
                type=TokenType.TAG_END,
                value="%",
                line=state.line,
                column=state.column,
                trim_right=True,
            )
        )
        _advance(state, 2)
        state.mode = "text"
        return

    # ---- Trim marker: -%} ----
    if _look_ahead(state, "-%}"):
        state.tokens.append(
            Token(
                type=TokenType.TAG_END,
                value="-%}",
                line=state.line,
                column=state.column,
                trim_right=True,
            )
        )
        _advance(state, 3)
        state.mode = "text"
        return

    # ---- Malformed tag end: lone } ----
    if (
        state.pos < len(state.input)
        and state.input[state.pos] == "}"
        and state.pos > 0
        and state.input[state.pos - 1] != "%"
    ):
        state.errors.append(
            TokenizerError(
                message="Malformed tag: expected '%}' but found '}'. "
                "Did you forget the '%'?",
                line=state.line,
                column=state.column,
            )
        )
        state.tokens.append(
            Token(
                type=TokenType.TAG_END,
                value="}",
                line=state.line,
                column=state.column,
                trim_right=True,
            )
        )
        _advance_char(state)
        state.mode = "text"
        return

    # ---- Unclosed tag: new tag/variable starting ----
    if _look_ahead(state, "{%") or _look_ahead(state, "{{"):
        tag_start_idx = _find_last_token_index(state.tokens, TokenType.TAG_START)
        tag_start = state.tokens[tag_start_idx] if tag_start_idx is not None else None
        start_line = tag_start.line if tag_start else state.line
        start_col = tag_start.column if tag_start else state.column
        state.errors.append(
            TokenizerError(
                message="Missing closing '%}' for tag",
                line=start_line,
                column=start_col,
            )
        )
        if tag_start_idx is not None:
            del state.tokens[tag_start_idx:]
        state.mode = "text"
        return

    # ---- Expression content ----
    _tokenize_expression(state, "tag")


# ============================================================================
# Expression Tokenization (shared between variable and tag modes)
# ============================================================================


def _tokenize_expression(state: _TokenizerState, mode: str) -> None:
    _skip_whitespace(state)

    if state.pos >= len(state.input):
        state.errors.append(
            TokenizerError(
                message="Unclosed variable - missing '}}'"
                if mode == "variable"
                else "Unclosed tag - missing '%}'",
                line=state.line,
                column=state.column,
            )
        )
        return

    char = state.input[state.pos]
    start_line = state.line
    start_column = state.column

    # ---- String literal ----
    if char in ("'", '"'):
        _tokenize_string(state)
        return

    # ---- Number literal ----
    if _is_digit(char) or (
        char == "-"
        and state.pos + 1 < len(state.input)
        and _is_digit(state.input[state.pos + 1])
    ):
        _tokenize_number(state)
        return

    # ---- Multi-character operators (check before single-char) ----
    if _look_ahead(state, "=="):
        state.tokens.append(Token(type=TokenType.OP_EQ, value="==", line=start_line, column=start_column))
        _advance(state, 2)
        return
    if _look_ahead(state, "!="):
        state.tokens.append(Token(type=TokenType.OP_NEQ, value="!=", line=start_line, column=start_column))
        _advance(state, 2)
        return
    if _look_ahead(state, ">="):
        state.tokens.append(Token(type=TokenType.OP_GTE, value=">=", line=start_line, column=start_column))
        _advance(state, 2)
        return
    if _look_ahead(state, "<="):
        state.tokens.append(Token(type=TokenType.OP_LTE, value="<=", line=start_line, column=start_column))
        _advance(state, 2)
        return
    if _look_ahead(state, "&&"):
        state.tokens.append(Token(type=TokenType.OP_AND, value="&&", line=start_line, column=start_column))
        _advance(state, 2)
        return
    if _look_ahead(state, "||"):
        state.tokens.append(Token(type=TokenType.OP_OR, value="||", line=start_line, column=start_column))
        _advance(state, 2)
        return
    if _look_ahead(state, "??"):
        state.tokens.append(Token(type=TokenType.OP_NULLISH, value="??", line=start_line, column=start_column))
        _advance(state, 2)
        return
    if _look_ahead(state, "=>"):
        state.tokens.append(Token(type=TokenType.ARROW, value="=>", line=start_line, column=start_column))
        _advance(state, 2)
        return

    # ---- Single-character operators and punctuation ----
    _SINGLE_CHAR_TOKENS: dict[str, tuple[str, str]] = {
        ">": (TokenType.OP_GT, ">"),
        "<": (TokenType.OP_LT, "<"),
        "!": (TokenType.OP_NOT, "!"),
        "=": (TokenType.OP_ASSIGN, "="),
        "|": (TokenType.PIPE, "|"),
        "(": (TokenType.LPAREN, "("),
        ")": (TokenType.RPAREN, ")"),
        "[": (TokenType.LBRACKET, "["),
        "]": (TokenType.RBRACKET, "]"),
        ":": (TokenType.COLON, ":"),
        ",": (TokenType.COMMA, ","),
        ".": (TokenType.DOT, "."),
        "*": (TokenType.STAR, "*"),
        "/": (TokenType.SLASH, "/"),
        "{": (TokenType.LBRACE, "{"),
        "}": (TokenType.RBRACE, "}"),
        "$": (TokenType.DOLLAR, "$"),
    }

    if char in _SINGLE_CHAR_TOKENS:
        token_type, token_value = _SINGLE_CHAR_TOKENS[char]
        state.tokens.append(
            Token(type=token_type, value=token_value, line=start_line, column=start_column)
        )
        _advance_char(state)
        return

    # ---- Identifier or keyword ----
    if _is_identifier_start(char):
        _tokenize_identifier(state)
        return

    # ---- Backslash-escaped argument ----
    if char == "\\":
        _tokenize_escaped_argument(state)
        return

    # ---- Unknown character – skip and report error ----
    state.errors.append(
        TokenizerError(
            message=f"Unexpected character '{char}' in template",
            line=state.line,
            column=state.column,
        )
    )
    _advance_char(state)


# ============================================================================
# Literal Tokenization
# ============================================================================


def _tokenize_string(state: _TokenizerState) -> None:
    quote = state.input[state.pos]
    start_line = state.line
    start_column = state.column
    value: list[str] = []

    _advance_char(state)  # Skip opening quote

    while state.pos < len(state.input):
        char = state.input[state.pos]
        next_char = state.input[state.pos + 1] if state.pos + 1 < len(state.input) else ""

        # Closing quote
        if char == quote:
            _advance_char(state)
            state.tokens.append(
                Token(type=TokenType.STRING, value="".join(value), line=start_line, column=start_column)
            )
            return

        # Likely a missing closing quote before }} or %}
        if (char == "}" and next_char == "}") or (char == "%" and next_char == "}"):
            state.errors.append(
                TokenizerError(
                    message=f"Unclosed string - missing {quote} before {char}{next_char}",
                    line=start_line,
                    column=start_column,
                )
            )
            state.tokens.append(
                Token(type=TokenType.STRING, value="".join(value), line=start_line, column=start_column)
            )
            return

        # Escape sequence
        if char == "\\" and state.pos + 1 < len(state.input):
            _advance_char(state)
            escaped = state.input[state.pos]
            escape_map = {
                "n": "\n",
                "t": "\t",
                "r": "\r",
                "\\": "\\",
                '"': '"',
                "'": "'",
            }
            value.append(escape_map.get(escaped, escaped))
            _advance_char(state)
            continue

        value.append(char)
        _advance_char(state)

    # Unterminated string
    state.errors.append(
        TokenizerError(
            message=f"Unclosed string - missing closing {quote}",
            line=start_line,
            column=start_column,
        )
    )
    state.tokens.append(
        Token(type=TokenType.STRING, value="".join(value), line=start_line, column=start_column)
    )


def _tokenize_number(state: _TokenizerState) -> None:
    start_line = state.line
    start_column = state.column
    value: list[str] = []

    # Optional negative sign
    if state.input[state.pos] == "-":
        value.append("-")
        _advance_char(state)

    # Integer part
    while state.pos < len(state.input) and _is_digit(state.input[state.pos]):
        value.append(state.input[state.pos])
        _advance_char(state)

    # Decimal part
    if state.pos < len(state.input) and state.input[state.pos] == ".":
        value.append(".")
        _advance_char(state)
        while state.pos < len(state.input) and _is_digit(state.input[state.pos]):
            value.append(state.input[state.pos])
            _advance_char(state)

    state.tokens.append(
        Token(type=TokenType.NUMBER, value="".join(value), line=start_line, column=start_column)
    )


def _tokenize_identifier(state: _TokenizerState) -> None:
    start_line = state.line
    start_column = state.column
    value: list[str] = []

    while state.pos < len(state.input) and _is_identifier_char(state.input[state.pos]):
        value.append(state.input[state.pos])
        _advance_char(state)

    text = "".join(value)

    # Special handling for CSS selectors (selector: and selectorHtml: prefixes)
    if text in ("selector", "selectorHtml") and state.pos < len(state.input) and state.input[state.pos] == ":":
        text += ":"
        _advance_char(state)
        text = _tokenize_css_selector(state, text)

    # Check if it is a keyword
    lower = text.lower()
    keyword_type = KEYWORDS.get(lower)

    if keyword_type is not None:
        state.tokens.append(
            Token(type=keyword_type, value=text, line=start_line, column=start_column)
        )
    else:
        state.tokens.append(
            Token(type=TokenType.IDENTIFIER, value=text, line=start_line, column=start_column)
        )


def _tokenize_escaped_argument(state: _TokenizerState) -> None:
    """Tokenize a backslash-escaped argument (e.g. \\\" in filter arguments).

    These start with a backslash and continue until a delimiter (|, }}, %}).
    Escape sequences are processed: \\\\ → \\, \\\\\\\" → \", etc.
    """
    start_line = state.line
    start_column = state.column
    value: list[str] = []

    while state.pos < len(state.input):
        char = state.input[state.pos]
        next_char = state.input[state.pos + 1] if state.pos + 1 < len(state.input) else ""

        # Stop at end delimiters (not escaped)
        if char in ("|", "%", "}", ")"):
            break
        if char == "+" and next_char in ("%", "}"):
            break

        # Handle escape sequences
        if char == "\\" and state.pos + 1 < len(state.input):
            escaped = state.input[state.pos + 1]
            escape_map = {
                '"': '"',
                "'": "'",
                "\\": "\\",
                "n": "\n",
                "t": "\t",
                "r": "\r",
                ",": ",",
                "|": "|",
            }
            value.append(escape_map.get(escaped, escaped))
            _advance_char(state)
            _advance_char(state)
            continue

        value.append(char)
        _advance_char(state)

    state.tokens.append(
        Token(type=TokenType.STRING, value="".join(value), line=start_line, column=start_column)
    )


def _tokenize_css_selector(state: _TokenizerState, value: str) -> str:
    """Continue tokenizing a CSS selector after the selector: / selectorHtml: prefix.

    CSS selectors can contain spaces, combinators (+, >, ~), brackets,
    parentheses, and quotes. We only stop at actual template delimiters:
    |, }}, %}, -}}, -%}.
    """
    bracket_depth = 0
    paren_depth = 0
    in_string: str | None = None

    while state.pos < len(state.input):
        char = state.input[state.pos]
        next_char = state.input[state.pos + 1] if state.pos + 1 < len(state.input) else ""

        # Check for end of tag/variable (but not inside brackets/parens/strings)
        if not in_string and bracket_depth == 0 and paren_depth == 0:
            if char == "|":
                break
            if char == "%" and next_char == "}":
                break
            if char == "}" and next_char == "}":
                break
            if char == "-" and next_char == "%":
                break
            if char == "-" and next_char == "}":
                break
            # Lone } (likely malformed tag ending)
            if char == "}" and next_char != "}":
                break

        # Detect unclosed brackets/parens/strings at end delimiters
        if (char == "}" and next_char == "}") or (char == "%" and next_char == "}"):
            if in_string:
                state.errors.append(
                    TokenizerError(
                        message=f"Unclosed string in selector - missing closing {in_string}",
                        line=state.line,
                        column=state.column,
                    )
                )
                break
            if bracket_depth > 0:
                state.errors.append(
                    TokenizerError(
                        message="Unclosed '[' in selector - missing ']'",
                        line=state.line,
                        column=state.column,
                    )
                )
                break
            if paren_depth > 0:
                state.errors.append(
                    TokenizerError(
                        message="Unclosed '(' in selector - missing ')'",
                        line=state.line,
                        column=state.column,
                    )
                )
                break

        # Escaped quotes outside strings (e.g. [attr=\\\"value\\\"])
        if not in_string and char == "\\" and next_char in ('"', "'"):
            value += char
            _advance_char(state)
            value += state.input[state.pos]
            _advance_char(state)
            continue

        # String quotes in CSS attribute selectors
        if not in_string and char in ('"', "'"):
            in_string = char
            value += char
            _advance_char(state)
            continue

        if in_string and char == in_string:
            in_string = None
            value += char
            _advance_char(state)
            continue

        # Escape sequences inside strings
        if in_string and char == "\\" and state.pos + 1 < len(state.input):
            value += char
            _advance_char(state)
            value += state.input[state.pos]
            _advance_char(state)
            continue

        # Track bracket / paren depth (not inside strings)
        if not in_string:
            if char == "[":
                bracket_depth += 1
            elif char == "]":
                bracket_depth -= 1
                if bracket_depth < 0:
                    state.errors.append(
                        TokenizerError(
                            message="Extra ']' in selector - no matching '['",
                            line=state.line,
                            column=state.column,
                        )
                    )
                    bracket_depth = 0
            elif char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth -= 1
                if paren_depth < 0:
                    state.errors.append(
                        TokenizerError(
                            message="Extra ')' in selector - no matching '('",
                            line=state.line,
                            column=state.column,
                        )
                    )
                    paren_depth = 0

        value += char
        _advance_char(state)

    return value.rstrip()


# ============================================================================
# Helper Functions
# ============================================================================


def _look_ahead(state: _TokenizerState, text: str) -> bool:
    """Return True if *text* appears at the current position."""
    return state.input[state.pos : state.pos + len(text)] == text


def _advance(state: _TokenizerState, count: int) -> None:
    """Advance the position by *count* characters, updating line/column."""
    for _ in range(count):
        _advance_char(state)


def _advance_char(state: _TokenizerState) -> None:
    """Advance the position by one character, updating line/column."""
    if state.pos < len(state.input):
        if state.input[state.pos] == "\n":
            state.line += 1
            state.column = 1
        else:
            state.column += 1
        state.pos += 1


def _skip_whitespace(state: _TokenizerState) -> None:
    """Skip over whitespace characters."""
    while state.pos < len(state.input) and _is_whitespace(state.input[state.pos]):
        _advance_char(state)


def _is_whitespace(ch: str) -> bool:
    return ch in (" ", "\t", "\n", "\r")


def _is_digit(ch: str) -> bool:
    return "0" <= ch <= "9"


def _is_identifier_start(ch: str) -> bool:
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z") or ch == "_" or ch == "@"


def _is_identifier_char(ch: str) -> bool:
    return _is_identifier_start(ch) or _is_digit(ch) or ch == "-" or ch == "."


def _find_last_token_index(tokens: list[Token], token_type: str) -> int | None:
    """Find the index of the last token with the given type, or None."""
    for i in range(len(tokens) - 1, -1, -1):
        if tokens[i].type == token_type:
            return i
    return None


# ============================================================================
# Utility Functions for Consumers
# ============================================================================


def format_token(token: Token) -> str:
    """Format a token for debugging / display."""
    pos = f"{token.line}:{token.column}"
    if token.value:
        return f"{token.type}({token.value!r}) at {pos}"
    return f"{token.type} at {pos}"


def format_error(error: TokenizerError) -> str:
    """Format an error message with position."""
    return f"Error at line {error.line}, column {error.column}: {error.message}"
