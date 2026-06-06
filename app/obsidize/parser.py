# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                      parser.py                                         #
# ========================================================================================#
"""
Template parser for the Obsidize template engine.
Converts a token stream into an Abstract Syntax Tree (AST).

Ported from obsidian-clipper/src/utils/parser.ts

The parser handles:
- Text content
- Variable interpolation with filters
- Logic tags: if/elseif/else/endif, for/endfor, set
- Expressions with operators and literals
"""

from typing import Any, Optional, Union

from .types import (
    Token,
    TokenType,
    ParserError,
    ParserResult,
    ASTNode,
    ASTNodeType,
    TextNode,
    VariableNode,
    IfNode,
    ForNode,
    SetNode,
    ElseIfBranch,
    LiteralExpression,
    IdentifierExpression,
    BinaryExpression,
    UnaryExpression,
    FilterExpression,
    GroupExpression,
    MemberExpression,
    ExpressionType,
)

# Optional: import tokenizer so parse() can tokenize+parse in one call.
try:
    from .tokenizer import tokenize as _tokenize  # type: ignore[import-untyped]
except ImportError:
    _tokenize = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Expression type alias
# ---------------------------------------------------------------------------

Expression = Union[
    LiteralExpression,
    IdentifierExpression,
    BinaryExpression,
    UnaryExpression,
    FilterExpression,
    GroupExpression,
    MemberExpression,
]


# ---------------------------------------------------------------------------
# Parser state
# ---------------------------------------------------------------------------

class _ParserState:
    """Mutable state carried through the recursive-descent parse."""

    __slots__ = ("tokens", "pos", "errors")

    def __init__(self, tokens: list[Token], errors: Optional[list[ParserError]] = None):
        self.tokens: list[Token] = tokens
        self.pos: int = 0
        self.errors: list[ParserError] = errors if errors is not None else []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(input: str) -> ParserResult:
    """Tokenize *input* and parse the resulting token stream into an AST."""
    if _tokenize is None:
        raise NotImplementedError(
            "The tokenizer module is not available. "
            "Use parse_tokens() with a pre-built token list instead."
        )
    tokenizer_result = _tokenize(input)

    # Convert tokenizer errors to parser errors
    errors: list[ParserError] = [
        ParserError(message=e.message, line=e.line, column=e.column)
        for e in tokenizer_result.errors
    ]

    state = _ParserState(tokens=tokenizer_result.tokens, errors=errors)
    ast = _parse_template(state)
    return ParserResult(ast=ast, errors=state.errors)


def parse_tokens(tokens: list[Token]) -> ParserResult:
    """Parse pre-tokenized input into an AST."""
    state = _ParserState(tokens=tokens)
    ast = _parse_template(state)
    return ParserResult(ast=ast, errors=state.errors)


# ---------------------------------------------------------------------------
# Template parsing
# ---------------------------------------------------------------------------

def _parse_template(state: _ParserState) -> list[ASTNode]:
    nodes: list[ASTNode] = []
    while not _is_at_end(state):
        node = _parse_node(state)
        if node is not None:
            nodes.append(node)
    return nodes


def _parse_node(state: _ParserState) -> Optional[ASTNode]:
    token = _peek(state)
    if token.type == TokenType.TEXT:
        return _parse_text(state)
    if token.type == TokenType.VARIABLE_START:
        return _parse_variable(state)
    if token.type == TokenType.TAG_START:
        return _parse_tag(state)
    if token.type == TokenType.EOF:
        _advance(state)
        return None
    # Unexpected token
    state.errors.append(
        ParserError(
            message=f'Unexpected "{token.value}" in template',
            line=token.line,
            column=token.column,
        )
    )
    _advance(state)
    return None


# ---------------------------------------------------------------------------
# Text node
# ---------------------------------------------------------------------------

def _parse_text(state: _ParserState) -> TextNode:
    token = _advance(state)
    return TextNode(
        type=ASTNodeType.TEXT,
        value=token.value,
        line=token.line,
        column=token.column,
    )


# ---------------------------------------------------------------------------
# Variable node  {{expression}}
# ---------------------------------------------------------------------------

def _parse_variable(state: _ParserState) -> Optional[VariableNode]:
    start_token = _advance(state)  # consume variable_start
    trim_left = start_token.trim_left

    expression = _parse_expression(state)
    if expression is None:
        state.errors.append(
            ParserError(
                message="Empty variable - add a variable name between {{ and }}",
                line=start_token.line,
                column=start_token.column,
            )
        )
        _skip_to_end_of_variable(state)
        return None

    # Check for multiple consecutive identifiers (likely an unquoted prompt)
    if _check(state, TokenType.IDENTIFIER):
        extra_words = 0
        saved_pos = state.pos
        while _check(state, TokenType.IDENTIFIER) and extra_words < 10:
            _advance(state)
            extra_words += 1
        state.pos = saved_pos

        if extra_words > 0:
            state.errors.append(
                ParserError(
                    message='Unknown variable. If this is a prompt, wrap it in quotes: {{"your prompt here"}}',
                    line=start_token.line,
                    column=start_token.column,
                )
            )
            _skip_to_end_of_variable(state)
            return None

    # Consume variable_end
    trim_right = False
    if _check(state, TokenType.VARIABLE_END):
        end_token = _advance(state)
        trim_right = end_token.trim_right
    else:
        state.errors.append(
            ParserError(
                message="Missing closing }}",
                line=_peek(state).line,
                column=_peek(state).column,
            )
        )

    return VariableNode(
        type=ASTNodeType.VARIABLE,
        expression=expression,
        trim_left=trim_left,
        trim_right=trim_right,
        line=start_token.line,
        column=start_token.column,
    )


# ---------------------------------------------------------------------------
# Tag dispatch
# ---------------------------------------------------------------------------

def _parse_tag(state: _ParserState) -> Optional[ASTNode]:
    start_token = _advance(state)  # consume tag_start
    trim_left = start_token.trim_left

    keyword_token = _peek(state)

    if keyword_token.type == TokenType.KEYWORD_IF:
        return _parse_if_statement(state, start_token, trim_left)
    if keyword_token.type == TokenType.KEYWORD_FOR:
        return _parse_for_statement(state, start_token, trim_left)
    if keyword_token.type == TokenType.KEYWORD_SET:
        return _parse_set_statement(state, start_token, trim_left)

    # Closing / out-of-place tags
    if keyword_token.type in (
        TokenType.KEYWORD_ELSE,
        TokenType.KEYWORD_ELSEIF,
        TokenType.KEYWORD_ENDIF,
        TokenType.KEYWORD_ENDFOR,
    ):
        state.errors.append(
            ParserError(
                message=f"Unexpected {{% {keyword_token.value} %}} - no matching opening tag",
                line=keyword_token.line,
                column=keyword_token.column,
            )
        )
        _skip_to_end_of_tag(state)
        return None

    state.errors.append(
        ParserError(
            message=f"Unknown tag: {{% {keyword_token.value} %}}",
            line=keyword_token.line,
            column=keyword_token.column,
        )
    )
    _skip_to_end_of_tag(state)
    return None


# ---------------------------------------------------------------------------
# If statement  {% if %}...{% elseif %}...{% else %}...{% endif %}
# ---------------------------------------------------------------------------

def _parse_if_statement(
    state: _ParserState,
    start_token: Token,
    trim_left: bool,
) -> Optional[IfNode]:
    _advance(state)  # consume 'if'

    condition = _parse_expression(state)
    if condition is None:
        state.errors.append(
            ParserError(
                message="{% if %} requires a condition",
                line=start_token.line,
                column=start_token.column,
            )
        )
        _skip_to_end_of_tag(state)
        return None

    # Consume tag_end
    trim_right = False
    if _check(state, TokenType.TAG_END):
        trim_right = _advance(state).trim_right
    else:
        state.errors.append(
            ParserError(
                message="Missing %} to close {% if %}",
                line=_peek(state).line,
                column=_peek(state).column,
            )
        )

    # Parse consequent body
    consequent = _parse_body(
        state,
        [TokenType.KEYWORD_ELSEIF, TokenType.KEYWORD_ELSE, TokenType.KEYWORD_ENDIF],
    )

    # Parse elseif chains
    elseifs: list[ElseIfBranch] = []
    while _check_tag_keyword(state, TokenType.KEYWORD_ELSEIF):
        _consume_tag_start(state)
        _advance(state)  # consume 'elseif'

        elseif_condition = _parse_expression(state)
        if elseif_condition is None:
            state.errors.append(
                ParserError(
                    message="{% elseif %} requires a condition",
                    line=_peek(state).line,
                    column=_peek(state).column,
                )
            )
            _skip_to_end_of_tag(state)
            continue

        _consume_tag_end(state)
        elseif_body = _parse_body(
            state,
            [TokenType.KEYWORD_ELSEIF, TokenType.KEYWORD_ELSE, TokenType.KEYWORD_ENDIF],
        )
        elseifs.append(ElseIfBranch(condition=elseif_condition, body=elseif_body))

    # Parse else branch
    alternate: Optional[list[ASTNode]] = None
    if _check_tag_keyword(state, TokenType.KEYWORD_ELSE):
        _consume_tag_start(state)
        _advance(state)  # consume 'else'
        _consume_tag_end(state)
        alternate = _parse_body(state, [TokenType.KEYWORD_ENDIF])

    # Consume endif
    if _check_tag_keyword(state, TokenType.KEYWORD_ENDIF):
        _consume_tag_start(state)
        _advance(state)  # consume 'endif'
        _consume_tag_end(state)
    else:
        state.errors.append(
            ParserError(
                message="Missing {% endif %} to close {% if %}",
                line=_peek(state).line,
                column=_peek(state).column,
            )
        )

    return IfNode(
        type=ASTNodeType.IF,
        condition=condition,
        consequent=consequent,
        elseifs=elseifs,
        alternate=alternate,
        trim_left=trim_left,
        trim_right=trim_right,
        line=start_token.line,
        column=start_token.column,
    )


# ---------------------------------------------------------------------------
# For statement  {% for item in iterable %}...{% endfor %}
# ---------------------------------------------------------------------------

def _parse_for_statement(
    state: _ParserState,
    start_token: Token,
    trim_left: bool,
) -> Optional[ForNode]:
    _advance(state)  # consume 'for'

    # Parse iterator name
    if not _check(state, TokenType.IDENTIFIER):
        state.errors.append(
            ParserError(
                message='{% for %} requires a variable name, e.g. {% for item in items %}',
                line=_peek(state).line,
                column=_peek(state).column,
            )
        )
        _skip_to_end_of_tag(state)
        return None
    iterator = _advance(state).value

    # Parse 'in' keyword
    if not _check(state, TokenType.KEYWORD_IN):
        state.errors.append(
            ParserError(
                message='{% for %} requires "in" keyword, e.g. {% for item in items %}',
                line=_peek(state).line,
                column=_peek(state).column,
            )
        )
        _skip_to_end_of_tag(state)
        return None
    _advance(state)  # consume 'in'

    # Parse iterable expression
    iterable = _parse_expression(state)
    if iterable is None:
        state.errors.append(
            ParserError(
                message='{% for %} requires something to loop over after "in"',
                line=_peek(state).line,
                column=_peek(state).column,
            )
        )
        _skip_to_end_of_tag(state)
        return None

    # Consume tag_end
    trim_right = False
    if _check(state, TokenType.TAG_END):
        trim_right = _advance(state).trim_right
    else:
        state.errors.append(
            ParserError(
                message="Missing %} to close {% for %}",
                line=_peek(state).line,
                column=_peek(state).column,
            )
        )

    # Parse body
    body = _parse_body(state, [TokenType.KEYWORD_ENDFOR])

    # Consume endfor
    if _check_tag_keyword(state, TokenType.KEYWORD_ENDFOR):
        _consume_tag_start(state)
        _advance(state)  # consume 'endfor'
        _consume_tag_end(state)
    else:
        state.errors.append(
            ParserError(
                message="Missing {% endfor %} to close {% for %}",
                line=_peek(state).line,
                column=_peek(state).column,
            )
        )

    return ForNode(
        type=ASTNodeType.FOR,
        iterator=iterator,
        iterable=iterable,
        body=body,
        trim_left=trim_left,
        trim_right=trim_right,
        line=start_token.line,
        column=start_token.column,
    )


# ---------------------------------------------------------------------------
# Set statement  {% set var = expression %}
# ---------------------------------------------------------------------------

def _parse_set_statement(
    state: _ParserState,
    start_token: Token,
    trim_left: bool,
) -> Optional[SetNode]:
    _advance(state)  # consume 'set'

    # Parse variable name
    if not _check(state, TokenType.IDENTIFIER):
        state.errors.append(
            ParserError(
                message='{% set %} requires a variable name, e.g. {% set name = value %}',
                line=_peek(state).line,
                column=_peek(state).column,
            )
        )
        _skip_to_end_of_tag(state)
        return None
    variable = _advance(state).value

    # Parse '=' operator
    if not _check(state, TokenType.OP_ASSIGN):
        state.errors.append(
            ParserError(
                message='{% set %} requires "=" after variable name',
                line=_peek(state).line,
                column=_peek(state).column,
            )
        )
        _skip_to_end_of_tag(state)
        return None
    _advance(state)  # consume '='

    # Parse value expression
    value = _parse_expression(state)
    if value is None:
        state.errors.append(
            ParserError(
                message='{% set %} requires a value after "="',
                line=_peek(state).line,
                column=_peek(state).column,
            )
        )
        _skip_to_end_of_tag(state)
        return None

    # Consume tag_end
    trim_right = False
    if _check(state, TokenType.TAG_END):
        trim_right = _advance(state).trim_right
    else:
        state.errors.append(
            ParserError(
                message="Missing %} to close {% set %}",
                line=_peek(state).line,
                column=_peek(state).column,
            )
        )

    return SetNode(
        type=ASTNodeType.SET,
        variable=variable,
        value=value,
        trim_left=trim_left,
        trim_right=trim_right,
        line=start_token.line,
        column=start_token.column,
    )


# ---------------------------------------------------------------------------
# Body parsing (content between tags)
# ---------------------------------------------------------------------------

def _parse_body(state: _ParserState, stop_keywords: list[str]) -> list[ASTNode]:
    """Parse template nodes until a tag matching one of *stop_keywords* is seen."""
    nodes: list[ASTNode] = []
    while not _is_at_end(state):
        if _check_tag_keyword(state, *stop_keywords):
            break
        node = _parse_node(state)
        if node is not None:
            nodes.append(node)
    return nodes


# ===================================================================
# Expression parsing — precedence climbing
# ===================================================================
#
# Precedence (lowest → highest):
#   1. nullish coalescing  ??
#   2. filter pipe         |
#   3. or
#   4. and
#   5. comparison          == != > < >= <= contains
#   6. addition            + -       (reserved; no operators yet)
#   7. multiplication       * /       (reserved; no operators yet)
#   8. unary               not !
#   9. member access        [index]
#  10. primary             literals, identifiers, (grouped)

def _parse_expression(state: _ParserState) -> Optional[Expression]:
    """Top-level expression entry point."""
    return _parse_nullish(state)


# ---- 1. Nullish coalescing  ?? ----

def _parse_nullish(state: _ParserState) -> Optional[Expression]:
    left = _parse_filter(state)
    if left is None:
        return None

    while _check(state, TokenType.OP_NULLISH):
        op_token = _advance(state)
        right = _parse_filter(state)
        if right is None:
            state.errors.append(
                ParserError(
                    message="Missing fallback value after ??",
                    line=op_token.line,
                    column=op_token.column,
                )
            )
            break
        left = BinaryExpression(
            type=ExpressionType.BINARY,
            operator="??",
            left=left,
            right=right,
            line=op_token.line,
            column=op_token.column,
        )

    return left


# ---- 2. Filter pipe  | ----

def _parse_filter(state: _ParserState) -> Optional[Expression]:
    left = _parse_or(state)
    if left is None:
        return None

    while _check(state, TokenType.PIPE):
        _advance(state)  # consume '|'

        if not _check(state, TokenType.IDENTIFIER):
            state.errors.append(
                ParserError(
                    message="Missing filter name after |",
                    line=_peek(state).line,
                    column=_peek(state).column,
                )
            )
            break

        filter_token = _advance(state)
        args: list[Expression] = []

        # Parse filter arguments: filter:arg or filter:arg1,arg2 or filter:(arg1, arg2)
        if _check(state, TokenType.COLON):
            _advance(state)  # consume ':'

            # Check for parenthesized arguments
            if _check(state, TokenType.LPAREN):
                _advance(state)  # consume '('
                while not _check(state, TokenType.RPAREN) and not _is_at_end(state):
                    arg = _parse_or(state)
                    if arg is None:
                        break

                    # Chain string:string pairs into a single arg
                    # e.g. replace:("old":"new","foo":"bar")
                    if (
                        isinstance(arg, LiteralExpression)
                        and isinstance(arg.value, str)
                        and _check(state, TokenType.COLON)
                    ):
                        combined = f'"{arg.value}"'
                        while _check(state, TokenType.COLON):
                            _advance(state)  # consume ':'
                            next_arg = _parse_or(state)
                            if (
                                next_arg is not None
                                and isinstance(next_arg, LiteralExpression)
                                and isinstance(next_arg.value, str)
                            ):
                                combined += ':' + f'"{next_arg.value}"'
                            else:
                                break
                        args.append(
                            LiteralExpression(
                                type=ExpressionType.LITERAL,
                                value=combined,
                                raw=combined,
                                line=arg.line,
                                column=arg.column,
                            )
                        )
                    else:
                        args.append(arg)

                    if _check(state, TokenType.COMMA):
                        _advance(state)
                    else:
                        break

                if _check(state, TokenType.RPAREN):
                    _advance(state)  # consume ')'
            else:
                # Arguments without parentheses
                arg = _parse_filter_argument(state)
                if arg is not None:
                    args.append(arg)
                while _check(state, TokenType.COMMA):
                    _advance(state)  # consume ','
                    next_arg = _parse_filter_argument(state)
                    if next_arg is not None:
                        args.append(next_arg)

        left = FilterExpression(
            type=ExpressionType.FILTER,
            value=left,
            name=filter_token.value,
            args=args,
            line=filter_token.line,
            column=filter_token.column,
        )

    return left


# ---- 3. Or ----

def _parse_or(state: _ParserState) -> Optional[Expression]:
    left = _parse_and(state)
    if left is None:
        return None

    while _check(state, TokenType.OP_OR):
        op_token = _advance(state)
        right = _parse_and(state)
        if right is None:
            state.errors.append(
                ParserError(
                    message='Missing value after "or"',
                    line=op_token.line,
                    column=op_token.column,
                )
            )
            break
        left = BinaryExpression(
            type=ExpressionType.BINARY,
            operator="or",
            left=left,
            right=right,
            line=op_token.line,
            column=op_token.column,
        )

    return left


# ---- 4. And ----

def _parse_and(state: _ParserState) -> Optional[Expression]:
    left = _parse_comparison(state)
    if left is None:
        return None

    while _check(state, TokenType.OP_AND):
        op_token = _advance(state)
        right = _parse_comparison(state)
        if right is None:
            state.errors.append(
                ParserError(
                    message='Missing value after "and"',
                    line=op_token.line,
                    column=op_token.column,
                )
            )
            break
        left = BinaryExpression(
            type=ExpressionType.BINARY,
            operator="and",
            left=left,
            right=right,
            line=op_token.line,
            column=op_token.column,
        )

    return left


# ---- 5. Comparison  == != > < >= <= contains ----

def _parse_comparison(state: _ParserState) -> Optional[Expression]:
    left = _parse_addition(state)
    if left is None:
        return None

    comparison_ops = {
        TokenType.OP_EQ,
        TokenType.OP_NEQ,
        TokenType.OP_GT,
        TokenType.OP_LT,
        TokenType.OP_GTE,
        TokenType.OP_LTE,
        TokenType.OP_CONTAINS,
    }

    if _peek(state).type in comparison_ops:
        op_token = _advance(state)
        right = _parse_addition(state)
        if right is None:
            state.errors.append(
                ParserError(
                    message=f'Missing value after "{op_token.value}"',
                    line=op_token.line,
                    column=op_token.column,
                )
            )
            return left

        operator_map = {
            TokenType.OP_EQ: "==",
            TokenType.OP_NEQ: "!=",
            TokenType.OP_GT: ">",
            TokenType.OP_LT: "<",
            TokenType.OP_GTE: ">=",
            TokenType.OP_LTE: "<=",
            TokenType.OP_CONTAINS: "contains",
        }
        operator = operator_map.get(op_token.type, op_token.value)

        return BinaryExpression(
            type=ExpressionType.BINARY,
            operator=operator,
            left=left,
            right=right,
            line=op_token.line,
            column=op_token.column,
        )

    return left


# ---- 6. Addition  + -  (reserved — no operators yet) ----

def _parse_addition(state: _ParserState) -> Optional[Expression]:
    """Addition/subtraction level. Currently a pass-through (no +/- operators)."""
    return _parse_multiplication(state)


# ---- 7. Multiplication  * /  (reserved — no operators yet) ----

def _parse_multiplication(state: _ParserState) -> Optional[Expression]:
    """Multiplication/division level. Currently a pass-through (no */÷ operators)."""
    return _parse_unary(state)


# ---- 8. Unary  not ! ----

def _parse_unary(state: _ParserState) -> Optional[Expression]:
    if _check(state, TokenType.OP_NOT):
        op_token = _advance(state)
        argument = _parse_unary(state)
        if argument is None:
            state.errors.append(
                ParserError(
                    message='Missing value after "not"',
                    line=op_token.line,
                    column=op_token.column,
                )
            )
            return None
        return UnaryExpression(
            type=ExpressionType.UNARY,
            operator="not",
            argument=argument,
            line=op_token.line,
            column=op_token.column,
        )

    return _parse_member(state)


# ---- 9. Member access  expr[index] ----

def _parse_member(state: _ParserState) -> Optional[Expression]:
    left = _parse_primary(state)
    if left is None:
        return None

    # Handle bracket notation: expr[index]
    while _check(state, TokenType.LBRACKET):
        bracket_token = _advance(state)  # consume '['

        property_expr = _parse_or(state)
        if property_expr is None:
            state.errors.append(
                ParserError(
                    message="Empty brackets [] - add an index or key",
                    line=bracket_token.line,
                    column=bracket_token.column,
                )
            )
            break

        if _check(state, TokenType.RBRACKET):
            _advance(state)  # consume ']'
        else:
            state.errors.append(
                ParserError(
                    message="Missing closing ]",
                    line=_peek(state).line,
                    column=_peek(state).column,
                )
            )

        left = MemberExpression(
            type=ExpressionType.MEMBER,
            object=left,
            property=property_expr,
            computed=True,
            line=bracket_token.line,
            column=bracket_token.column,
        )

    return left


# ---- 10. Primary  literals, identifiers, (grouped) ----

def _parse_primary(state: _ParserState) -> Optional[Expression]:
    token = _peek(state)

    # Grouped expression: (expr)
    if _check(state, TokenType.LPAREN):
        _advance(state)  # consume '('
        expr = _parse_or(state)
        if expr is None:
            state.errors.append(
                ParserError(
                    message="Empty parentheses () - add an expression",
                    line=token.line,
                    column=token.column,
                )
            )
            return None
        if _check(state, TokenType.RPAREN):
            _advance(state)  # consume ')'
        else:
            state.errors.append(
                ParserError(
                    message="Missing closing )",
                    line=_peek(state).line,
                    column=_peek(state).column,
                )
            )
        return GroupExpression(
            type=ExpressionType.GROUP,
            expression=expr,
            line=token.line,
            column=token.column,
        )

    # String literal
    if _check(state, TokenType.STRING):
        str_token = _advance(state)
        return LiteralExpression(
            type=ExpressionType.LITERAL,
            value=str_token.value,
            raw=str_token.value,
            line=str_token.line,
            column=str_token.column,
        )

    # Number literal
    if _check(state, TokenType.NUMBER):
        num_token = _advance(state)
        return LiteralExpression(
            type=ExpressionType.LITERAL,
            value=float(num_token.value),
            raw=num_token.value,
            line=num_token.line,
            column=num_token.column,
        )

    # Boolean literal
    if _check(state, TokenType.BOOLEAN):
        bool_token = _advance(state)
        return LiteralExpression(
            type=ExpressionType.LITERAL,
            value=bool_token.value.lower() == "true",
            raw=bool_token.value,
            line=bool_token.line,
            column=bool_token.column,
        )

    # Null literal
    if _check(state, TokenType.NULL):
        null_token = _advance(state)
        return LiteralExpression(
            type=ExpressionType.LITERAL,
            value=None,
            raw="null",
            line=null_token.line,
            column=null_token.column,
        )

    # Identifier (may include property access via dots / colon prefixes)
    if _check(state, TokenType.IDENTIFIER):
        id_token = _advance(state)
        name = id_token.value

        # Handle special prefixes that use colons: selector:, schema:, selectorHtml:
        if _check(state, TokenType.COLON):
            _advance(state)  # consume ':'

            # Build the full identifier including the prefix
            # e.g. schema:[0].prop, selector:div.class, schema:director[*].name
            rest = ""
            while _check(state, TokenType.IDENTIFIER) or _check(state, TokenType.DOT) or \
                    _check(state, TokenType.COLON) or _check(state, TokenType.LBRACKET) or \
                    _check(state, TokenType.RBRACKET) or _check(state, TokenType.NUMBER) or \
                    _check(state, TokenType.STRING) or _check(state, TokenType.STAR):
                rest += _advance(state).value
            name = name + ':' + rest

        return IdentifierExpression(
            type=ExpressionType.IDENTIFIER,
            name=name,
            line=id_token.line,
            column=id_token.column,
        )

    # No valid primary expression found
    return None


# ---------------------------------------------------------------------------
# Filter argument parsing (complex — supports ranges, arrow functions, etc.)
# ---------------------------------------------------------------------------

def _parse_filter_argument(state: _ParserState) -> Optional[Expression]:
    """Parse a single filter argument, which may contain colon-separated parts."""
    start_token = _peek(state)

    # Handle simple delimiter tokens that can be used as filter arguments
    # e.g. split:/ or split:-
    if _check(state, TokenType.SLASH) or _check(state, TokenType.STAR):
        token = _advance(state)
        return LiteralExpression(
            type=ExpressionType.LITERAL,
            value=token.value,
            raw=token.value,
            line=token.line,
            column=token.column,
        )

    # Handle bracket patterns like [0-9] as literal regex character classes
    if _check(state, TokenType.LBRACKET):
        value = ""
        bracket_depth = 0
        start_line = _peek(state).line
        start_column = _peek(state).column

        while not _is_at_end(state):
            token = _peek(state)
            if token.type == TokenType.LBRACKET:
                bracket_depth += 1
            elif token.type == TokenType.RBRACKET:
                bracket_depth -= 1
                if bracket_depth == 0:
                    value += token.value
                    _advance(state)
                    break

            # Stop if we hit pipe or variable_end without an open bracket
            if bracket_depth == 0 and token.type in (
                TokenType.PIPE,
                TokenType.VARIABLE_END,
                TokenType.COMMA,
            ):
                break

            value += token.value
            _advance(state)

        return LiteralExpression(
            type=ExpressionType.LITERAL,
            value=value,
            raw=value,
            line=start_line,
            column=start_column,
        )

    # Check for arrow function: identifier => expression
    if _check(state, TokenType.IDENTIFIER):
        saved_pos = state.pos
        id_token = _advance(state)

        if _check(state, TokenType.ARROW):
            # This is an arrow function — consume everything until | or }}
            value = id_token.value + " "
            value += _advance(state).value + " "  # consume '=>'

            # Consume everything until pipe or variable_end, tracking brace/paren depth
            brace_depth = 0
            paren_depth = 0

            while not _is_at_end(state):
                token = _peek(state)

                # Stop at pipe or variable_end when not inside braces/parens
                if brace_depth == 0 and paren_depth == 0:
                    if token.type in (TokenType.PIPE, TokenType.VARIABLE_END, TokenType.TAG_END):
                        break

                if token.type in (TokenType.LBRACE, TokenType.LPAREN):
                    if token.type == TokenType.LBRACE:
                        brace_depth += 1
                    else:
                        paren_depth += 1
                elif token.type in (TokenType.RBRACE, TokenType.RPAREN):
                    if token.type == TokenType.RBRACE:
                        brace_depth -= 1
                    else:
                        paren_depth -= 1
                    if brace_depth < 0 or paren_depth < 0:
                        break

                # Preserve quotes around string tokens
                if token.type == TokenType.STRING:
                    value += f'"{token.value}"'
                else:
                    value += token.value
                _advance(state)

            trimmed = value.strip()
            return LiteralExpression(
                type=ExpressionType.LITERAL,
                value=trimmed,
                raw=trimmed,
                line=start_token.line,
                column=start_token.column,
            )

        # Not an arrow function — restore position
        state.pos = saved_pos

    # Parse the first part
    first = _parse_primary(state)
    if first is None:
        return None

    # For quoted strings, chain together :string patterns as a single argument
    if isinstance(first, LiteralExpression) and start_token.type == TokenType.STRING:
        def _fmt_str(val: Any) -> str:
            return f'"{val}"'

        combined = _fmt_str(first.value)

        # Check if followed by :string pattern — chain them together
        while _check(state, TokenType.COLON):
            saved_pos = state.pos
            _advance(state)  # consume ':'

            if _check(state, TokenType.STRING):
                next_expr = _parse_primary(state)
                if next_expr is not None and isinstance(next_expr, LiteralExpression):
                    combined += ':' + _fmt_str(next_expr.value)
                else:
                    # Not a string after colon — restore position
                    state.pos = saved_pos
                    break
            else:
                state.pos = saved_pos
                break

        return LiteralExpression(
            type=ExpressionType.LITERAL,
            value=combined,
            raw=combined,
            line=first.line,
            column=first.column,
        )

    # For unquoted values, handle number+identifier like "2n" for nth filter
    if (
        isinstance(first, LiteralExpression)
        and start_token.type == TokenType.NUMBER
        and _check(state, TokenType.IDENTIFIER)
    ):
        id_token = _peek(state)
        if len(id_token.value) == 1 and id_token.value.isalpha():
            _advance(state)
            combined = str(first.value) + id_token.value
            return LiteralExpression(
                type=ExpressionType.LITERAL,
                value=combined,
                raw=combined,
                line=first.line,
                column=first.column,
            )

    # If there's no colon following, return the original expression to preserve its type
    if not _check(state, TokenType.COLON):
        return first

    # Build a string value for colon-separated range notation
    value = ""
    if isinstance(first, LiteralExpression):
        value = str(first.value)
    elif isinstance(first, IdentifierExpression):
        value = first.name
    else:
        return first  # Return as-is for other types

    # Consume colons for range notation like 5:7
    while _check(state, TokenType.COLON) and not _is_at_end(state):
        _advance(state)  # consume ':'
        value += ':'

        next_part = _parse_primary(state)
        if next_part is not None:
            if isinstance(next_part, LiteralExpression):
                value += str(next_part.value)
            elif isinstance(next_part, IdentifierExpression):
                value += next_part.name
        else:
            break

    return LiteralExpression(
        type=ExpressionType.LITERAL,
        value=value,
        raw=value,
        line=start_token.line,
        column=start_token.column,
    )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _peek(state: _ParserState) -> Token:
    """Return the current token without advancing."""
    if state.pos < len(state.tokens):
        return state.tokens[state.pos]
    return Token(type=TokenType.EOF, value="", line=0, column=0)


def _advance(state: _ParserState) -> Token:
    """Consume and return the current token."""
    token = _peek(state)
    if not _is_at_end(state):
        state.pos += 1
    return token


def _check(state: _ParserState, token_type: str) -> bool:
    """Return True if the current token matches *token_type*."""
    return _peek(state).type == token_type


def _is_at_end(state: _ParserState) -> bool:
    """Return True if the current token is EOF."""
    return _peek(state).type == TokenType.EOF


def _check_tag_keyword(state: _ParserState, *keywords: str) -> bool:
    """Check if we are at a tag_start followed by one of *keywords*."""
    if not _check(state, TokenType.TAG_START):
        return False
    next_pos = state.pos + 1
    if next_pos >= len(state.tokens):
        return False
    return state.tokens[next_pos].type in keywords


def _consume_tag_start(state: _ParserState) -> Optional[Token]:
    """Consume a tag_start token if present."""
    if _check(state, TokenType.TAG_START):
        return _advance(state)
    return None


def _consume_tag_end(state: _ParserState) -> Optional[Token]:
    """Consume a tag_end token; report an error if missing."""
    if _check(state, TokenType.TAG_END):
        return _advance(state)
    state.errors.append(
        ParserError(
            message="Missing closing %}",
            line=_peek(state).line,
            column=_peek(state).column,
        )
    )
    return None


def _skip_to_end_of_tag(state: _ParserState) -> None:
    """Skip tokens until the next tag_end (inclusive)."""
    while not _is_at_end(state) and not _check(state, TokenType.TAG_END):
        _advance(state)
    if _check(state, TokenType.TAG_END):
        _advance(state)


def _skip_to_end_of_variable(state: _ParserState) -> None:
    """Skip tokens until the next variable_end (inclusive)."""
    while not _is_at_end(state) and not _check(state, TokenType.VARIABLE_END):
        _advance(state)
    if _check(state, TokenType.VARIABLE_END):
        _advance(state)


# ---------------------------------------------------------------------------
# AST formatting (for debugging)
# ---------------------------------------------------------------------------

def format_ast(nodes: list[ASTNode], indent: int = 0) -> str:
    """Format an AST node list for debugging."""
    pad = "  " * indent
    result = ""

    for node in nodes:
        if node.type == ASTNodeType.TEXT:
            node_text: TextNode = node  # type: ignore[assignment]
            result += f"{pad}Text: {node_text.value!r}\n"

        elif node.type == ASTNodeType.VARIABLE:
            node_var: VariableNode = node  # type: ignore[assignment]
            result += f"{pad}Variable:\n"
            result += _format_expression(node_var.expression, indent + 1)

        elif node.type == ASTNodeType.IF:
            node_if: IfNode = node  # type: ignore[assignment]
            result += f"{pad}If:\n"
            result += f"{pad}  Condition:\n"
            result += _format_expression(node_if.condition, indent + 2)
            result += f"{pad}  Then:\n"
            result += format_ast(node_if.consequent, indent + 2)
            for elseif in node_if.elseifs:
                result += f"{pad}  ElseIf:\n"
                result += _format_expression(elseif.condition, indent + 2)
                result += format_ast(elseif.body, indent + 2)
            if node_if.alternate is not None:
                result += f"{pad}  Else:\n"
                result += format_ast(node_if.alternate, indent + 2)

        elif node.type == ASTNodeType.FOR:
            node_for: ForNode = node  # type: ignore[assignment]
            result += f"{pad}For: {node_for.iterator} in\n"
            result += _format_expression(node_for.iterable, indent + 1)
            result += f"{pad}  Body:\n"
            result += format_ast(node_for.body, indent + 2)

        elif node.type == ASTNodeType.SET:
            node_set: SetNode = node  # type: ignore[assignment]
            result += f"{pad}Set: {node_set.variable} =\n"
            result += _format_expression(node_set.value, indent + 1)

    return result


def _format_expression(expr: Expression, indent: int) -> str:
    """Format an expression for debugging."""
    pad = "  " * indent

    if isinstance(expr, LiteralExpression):
        return f"{pad}Literal: {expr.value!r}\n"

    if isinstance(expr, IdentifierExpression):
        return f"{pad}Identifier: {expr.name}\n"

    if isinstance(expr, BinaryExpression):
        return (
            f"{pad}Binary: {expr.operator}\n"
            + _format_expression(expr.left, indent + 1)
            + _format_expression(expr.right, indent + 1)
        )

    if isinstance(expr, UnaryExpression):
        return (
            f"{pad}Unary: {expr.operator}\n"
            + _format_expression(expr.argument, indent + 1)
        )

    if isinstance(expr, FilterExpression):
        result = f"{pad}Filter: {expr.name}\n"
        result += f"{pad}  Value:\n"
        result += _format_expression(expr.value, indent + 2)
        if expr.args:
            result += f"{pad}  Args:\n"
            for arg in expr.args:
                result += _format_expression(arg, indent + 2)
        return result

    if isinstance(expr, GroupExpression):
        return f"{pad}Group:\n" + _format_expression(expr.expression, indent + 1)

    if isinstance(expr, MemberExpression):
        return (
            f"{pad}Member:\n"
            + _format_expression(expr.object, indent + 1)
            + _format_expression(expr.property, indent + 1)
        )

    return f"{pad}Unknown expression\n"


def format_parser_error(error: ParserError) -> str:
    """Format a parser error with position information."""
    return f"Error at line {error.line}, column {error.column}: {error.message}"
