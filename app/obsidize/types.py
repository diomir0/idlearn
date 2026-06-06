# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                      types.py                                          #
# ========================================================================================#
"""
Core type definitions for the Obsidize template engine.
Ported from the Obsidian Web Clipper template engine (TypeScript).
"""

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Template types
# ---------------------------------------------------------------------------

@dataclass
class Property:
    """A single Obsidian property (frontmatter field)."""
    name: str
    value: str
    type: str = "text"  # text, number, checkbox, date, datetime, multitext


@dataclass
class Template:
    """An Obsidian Web Clipper-compatible template definition."""
    id: str
    name: str
    behavior: str = "create"  # create, append-specific, append-daily, prepend-specific, prepend-daily, overwrite
    note_name_format: str = "{{title}}"
    path: str = ""
    note_content_format: str = "{{content}}"
    properties: list[Property] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    vault: str = ""


# ---------------------------------------------------------------------------
# PDF content types
# ---------------------------------------------------------------------------

@dataclass
class PdfMetadata:
    """Metadata extracted from a PDF document."""
    title: str = ""
    author: str = ""
    subject: str = ""
    keywords: str = ""
    creator: str = ""
    producer: str = ""
    creation_date: str = ""
    mod_date: str = ""


@dataclass
class PdfPage:
    """A single page's text content."""
    page_number: int = 0
    text: str = ""
    images: list[str] = field(default_factory=list)  # list of image file paths on this page


@dataclass
class PdfContent:
    """Full extracted PDF content."""
    text: str = ""
    pages: list[PdfPage] = field(default_factory=list)
    page_count: int = 0
    metadata: PdfMetadata = field(default_factory=PdfMetadata)
    file_name: str = ""
    file_path: str = ""
    file_size: int = 0
    images: list[str] = field(default_factory=list)  # list of all extracted image paths


# ---------------------------------------------------------------------------
# Clip result
# ---------------------------------------------------------------------------

@dataclass
class ClipPdfResult:
    """Result of clipping a PDF with a template."""
    note_name: str = ""
    frontmatter: str = ""
    content: str = ""
    full_content: str = ""
    properties: list[Property] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Template engine AST types
# ---------------------------------------------------------------------------

class ASTNodeType:
    TEXT = "text"
    VARIABLE = "variable"
    IF = "if"
    FOR = "for"
    SET = "set"


class ExpressionType:
    LITERAL = "literal"
    IDENTIFIER = "identifier"
    BINARY = "binary"
    UNARY = "unary"
    FILTER = "filter"
    GROUP = "group"
    MEMBER = "member"


@dataclass
class ASTNode:
    """Base class for AST nodes."""
    type: str
    line: int = 0
    column: int = 0


@dataclass
class TextNode(ASTNode):
    value: str = ""


@dataclass
class VariableNode(ASTNode):
    expression: Any = None  # Expression
    trim_left: bool = False
    trim_right: bool = False


@dataclass
class ElseIfBranch:
    condition: Any = None  # Expression
    body: list[ASTNode] = field(default_factory=list)


@dataclass
class IfNode(ASTNode):
    condition: Any = None  # Expression
    consequent: list[ASTNode] = field(default_factory=list)
    elseifs: list[ElseIfBranch] = field(default_factory=list)
    alternate: Optional[list[ASTNode]] = None
    trim_left: bool = False
    trim_right: bool = False


@dataclass
class ForNode(ASTNode):
    iterator: str = ""
    iterable: Any = None  # Expression
    body: list[ASTNode] = field(default_factory=list)
    trim_left: bool = False
    trim_right: bool = False


@dataclass
class SetNode(ASTNode):
    variable: str = ""
    value: Any = None  # Expression
    trim_left: bool = False
    trim_right: bool = False


# ---------------------------------------------------------------------------
# Expression types
# ---------------------------------------------------------------------------

@dataclass
class LiteralExpression:
    type: str = ExpressionType.LITERAL
    value: Any = None
    raw: str = ""
    line: int = 0
    column: int = 0


@dataclass
class IdentifierExpression:
    type: str = ExpressionType.IDENTIFIER
    name: str = ""
    line: int = 0
    column: int = 0


@dataclass
class BinaryExpression:
    type: str = ExpressionType.BINARY
    operator: str = ""
    left: Any = None  # Expression
    right: Any = None  # Expression
    line: int = 0
    column: int = 0


@dataclass
class UnaryExpression:
    type: str = ExpressionType.UNARY
    operator: str = ""
    argument: Any = None  # Expression
    line: int = 0
    column: int = 0


@dataclass
class FilterExpression:
    type: str = ExpressionType.FILTER
    value: Any = None  # Expression
    name: str = ""
    args: list[Any] = field(default_factory=list)  # list[Expression]
    line: int = 0
    column: int = 0


@dataclass
class GroupExpression:
    type: str = ExpressionType.GROUP
    expression: Any = None  # Expression
    line: int = 0
    column: int = 0


@dataclass
class MemberExpression:
    type: str = ExpressionType.MEMBER
    object: Any = None  # Expression
    property: Any = None  # Expression
    computed: bool = True
    line: int = 0
    column: int = 0


# ---------------------------------------------------------------------------
# Tokenizer types
# ---------------------------------------------------------------------------

class TokenType:
    # Structural
    TEXT = "text"
    VARIABLE_START = "variable_start"
    VARIABLE_END = "variable_end"
    TAG_START = "tag_start"
    TAG_END = "tag_end"

    # Keywords
    KEYWORD_IF = "keyword_if"
    KEYWORD_ELSEIF = "keyword_elseif"
    KEYWORD_ELSE = "keyword_else"
    KEYWORD_ENDIF = "keyword_endif"
    KEYWORD_FOR = "keyword_for"
    KEYWORD_IN = "keyword_in"
    KEYWORD_ENDFOR = "keyword_endfor"
    KEYWORD_SET = "keyword_set"

    # Operators
    OP_EQ = "op_eq"
    OP_NEQ = "op_neq"
    OP_GTE = "op_gte"
    OP_LTE = "op_lte"
    OP_GT = "op_gt"
    OP_LT = "op_lt"
    OP_AND = "op_and"
    OP_OR = "op_or"
    OP_NOT = "op_not"
    OP_CONTAINS = "op_contains"
    OP_NULLISH = "op_nullish"
    OP_ASSIGN = "op_assign"

    # Literals and identifiers
    IDENTIFIER = "identifier"
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    NULL = "null"

    # Punctuation
    PIPE = "pipe"
    LPAREN = "lparen"
    RPAREN = "rparen"
    LBRACKET = "lbracket"
    RBRACKET = "rbracket"
    LBRACE = "lbrace"
    RBRACE = "rbrace"
    COLON = "colon"
    COMMA = "comma"
    DOT = "dot"
    STAR = "star"
    SLASH = "slash"
    ARROW = "arrow"
    DOLLAR = "dollar"

    # Special
    EOF = "eof"


@dataclass
class Token:
    """A single token from the tokenizer."""
    type: str
    value: str
    line: int = 0
    column: int = 0
    trim_left: bool = False
    trim_right: bool = False


@dataclass
class TokenizerError:
    message: str
    line: int = 0
    column: int = 0


@dataclass
class TokenizerResult:
    tokens: list[Token] = field(default_factory=list)
    errors: list[TokenizerError] = field(default_factory=list)


@dataclass
class ParserError:
    message: str
    line: int = 0
    column: int = 0


@dataclass
class ParserResult:
    ast: list[ASTNode] = field(default_factory=list)
    errors: list[ParserError] = field(default_factory=list)


@dataclass
class RenderError:
    message: str
    line: int = 0
    column: int = 0


@dataclass
class RenderResult:
    output: str = ""
    errors: list[RenderError] = field(default_factory=list)
    has_deferred_variables: bool = False


# ---------------------------------------------------------------------------
# Filter type
# ---------------------------------------------------------------------------

FilterFunction = Any  # Callable[[str, str], str]
