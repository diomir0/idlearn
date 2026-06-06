# ========================================================================================#
#                                    IDLEARN - OBSIDIZE                                   #
#                                      renderer.py                                       #
# ========================================================================================#
"""
Template renderer for the Obsidize template engine.
Evaluates an AST and produces string output.

Ported from obsidize/src/utils/renderer.ts.

The renderer handles:
- Variable interpolation with filters
- Conditional logic (if/elseif/else)
- Loops (for)
- Variable assignment (set)
- Whitespace control (trimLeft/trimRight)
- Prompt/deferred variable preservation
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .types import (
    ASTNode,
    ASTNodeType,
    BinaryExpression,
    ElseIfBranch,
    ExpressionType,
    FilterExpression,
    ForNode,
    GroupExpression,
    IdentifierExpression,
    IfNode,
    LiteralExpression,
    MemberExpression,
    RenderError,
    RenderResult,
    SetNode,
    TextNode,
    UnaryExpression,
    VariableNode,
)
from .resolver import resolve_schema_variable, resolve_variable, value_to_string
from .filters import apply_filter_direct
from .parser import parse


# ============================================================================
# Render Context
# ============================================================================


@dataclass
class RenderContext:
    """Context for rendering templates."""

    variables: dict[str, Any]
    current_url: str = ""


# ============================================================================
# Internal Render State
# ============================================================================


@dataclass
class _RenderState:
    """Mutable state tracked during rendering."""

    context: RenderContext
    errors: list[RenderError] = field(default_factory=list)
    pending_trim_right: bool = False
    has_deferred_variables: bool = False


# ============================================================================
# Main Render Functions
# ============================================================================


def render(template: str, context: RenderContext) -> RenderResult:
    """Render a template string with the given context.

    Parses the template first, then renders the resulting AST.
    Returns a RenderResult with output text and any errors encountered.
    """
    from .cache import _default_cache

    parse_result = _default_cache.get(template)
    if parse_result is None:
        parse_result = parse(template)
        if not parse_result.errors:
            _default_cache.put(template, parse_result)

    if parse_result.errors:
        return RenderResult(
            output="",
            errors=[
                RenderError(message=e.message, line=e.line, column=e.column)
                for e in parse_result.errors
            ],
            has_deferred_variables=False,
        )

    return render_ast(parse_result.ast, context)


def render_ast(
    ast: list[ASTNode],
    context: RenderContext,
    *,
    trim_output: bool = False,
) -> RenderResult:
    """Render a pre-parsed AST with the given context.

    Args:
        ast: List of AST nodes to render.
        context: Render context with variables and URL.
        trim_output: If True, trim leading/trailing whitespace from output.

    Returns:
        RenderResult with output text and any errors encountered.
    """
    errors: list[RenderError] = []
    state = _RenderState(context=context, errors=errors)

    output = ""
    for node in ast:
        node_output = _render_node(node, state)
        output = _append_node_output(output, node_output, node, state)

    if trim_output:
        output = output.strip()

    return RenderResult(
        output=output,
        errors=errors,
        has_deferred_variables=state.has_deferred_variables,
    )


# ============================================================================
# Node Rendering
# ============================================================================


def _render_node(node: ASTNode, state: _RenderState) -> str:
    """Render a single AST node to a string."""
    if node.type == ASTNodeType.TEXT:
        return _render_text(node, state)
    elif node.type == ASTNodeType.VARIABLE:
        return _render_variable(node, state)
    elif node.type == ASTNodeType.IF:
        return _render_if(node, state)
    elif node.type == ASTNodeType.FOR:
        return _render_for(node, state)
    elif node.type == ASTNodeType.SET:
        return _render_set(node, state)
    else:
        state.errors.append(
            RenderError(message=f"Unknown node type: {node.type}")
        )
        return ""


def _render_text(node: TextNode, state: _RenderState) -> str:
    """Render a text node."""
    text = node.value

    # If previous node had trimRight, trim leading whitespace/newlines
    if state.pending_trim_right:
        text = _trim_leading_whitespace(text)
        state.pending_trim_right = False

    return text


def _render_variable(node: VariableNode, state: _RenderState) -> str:
    """Render a variable node ({{ expression }})."""
    try:
        # Special case: string literals (prompts) need to be preserved
        # for post-processing. This includes filter chains where the base
        # value is a string literal.
        prompt_info = _get_prompt_base(node.expression)
        if prompt_info is not None:
            if node.trim_right:
                state.pending_trim_right = True
            state.has_deferred_variables = True
            return _reconstruct_prompt_template(node.expression)

        value = _evaluate_expression(node.expression, state)
        result = _value_to_string(value)

        if node.trim_right:
            state.pending_trim_right = True

        return result
    except Exception as error:
        state.errors.append(
            RenderError(
                message=f"Error evaluating variable: {error}",
                line=node.line,
                column=node.column,
            )
        )
        return ""


def _render_if(node: IfNode, state: _RenderState) -> str:
    """Render an if/elseif/else conditional node."""
    try:
        # Evaluate main condition
        condition_value = _evaluate_expression(node.condition, state)

        if _is_truthy(condition_value):
            result = _render_nodes(node.consequent, state)
            if node.trim_right:
                state.pending_trim_right = True
            return result

        # Check elseif conditions
        for elseif in node.elseifs:
            elseif_value = _evaluate_expression(elseif.condition, state)
            if _is_truthy(elseif_value):
                return _render_nodes(elseif.body, state)

        # Fall back to else
        if node.alternate is not None:
            return _render_nodes(node.alternate, state)

        # No branch taken
        if node.trim_right:
            state.pending_trim_right = True

        return ""
    except Exception as error:
        state.errors.append(
            RenderError(
                message=f"Error evaluating if condition: {error}",
                line=node.line,
                column=node.column,
            )
        )
        return ""


def _render_for(node: ForNode, state: _RenderState) -> str:
    """Render a for loop node."""
    try:
        iterable_value = _evaluate_expression(node.iterable, state)

        # Silently handle None/null — expected when optional data doesn't exist
        if iterable_value is None:
            if node.trim_right:
                state.pending_trim_right = True
            return ""

        # If the iterable is a JSON string (e.g. from split filter), try to parse it
        if isinstance(iterable_value, str):
            try:
                parsed = json.loads(iterable_value)
                if isinstance(parsed, list):
                    iterable_value = parsed
            except (json.JSONDecodeError, ValueError):
                # Not valid JSON — will be caught by the array check below
                pass

        if not isinstance(iterable_value, list):
            state.errors.append(
                RenderError(
                    message=f"For loop iterable is not an array: "
                    f"{type(iterable_value).__name__}",
                    line=node.line,
                    column=node.column,
                )
            )
            if node.trim_right:
                state.pending_trim_right = True
            return ""

        results: list[str] = []
        length = len(iterable_value)

        for i, item in enumerate(iterable_value):
            # Twig-compatible loop object
            loop = {
                "index": i + 1,  # 1-indexed
                "index0": i,  # 0-indexed
                "first": i == 0,
                "last": i == length - 1,
                "length": length,
            }

            # Create new context with loop variables (inherits parent scope)
            loop_variables = {
                **state.context.variables,
                node.iterator: item,
                f"{node.iterator}_index": i,  # Backwards compatibility
                "loop": loop,
            }

            loop_context = RenderContext(
                variables=loop_variables,
                current_url=state.context.current_url,
            )

            loop_state = _RenderState(
                context=loop_context,
                errors=state.errors,  # Shared — errors accumulate globally
                pending_trim_right=False,
                has_deferred_variables=state.has_deferred_variables,
            )

            item_result = _render_nodes(node.body, loop_state)
            results.append(item_result.strip())

            # Propagate deferred-variables flag back to parent state
            state.has_deferred_variables = (
                state.has_deferred_variables
                or loop_state.has_deferred_variables
            )

        if node.trim_right:
            state.pending_trim_right = True

        return "\n".join(results)
    except Exception as error:
        state.errors.append(
            RenderError(
                message=f"Error in for loop: {error}",
                line=node.line,
                column=node.column,
            )
        )
        return ""


def _render_set(node: SetNode, state: _RenderState) -> str:
    """Render a set-assignment node (produces no output)."""
    try:
        value = _evaluate_expression(node.value, state)

        # Mutate the context variables
        state.context.variables[node.variable] = value

        if node.trim_right:
            state.pending_trim_right = True

        return ""
    except Exception as error:
        state.errors.append(
            RenderError(
                message=f"Error in set: {error}",
                line=node.line,
                column=node.column,
            )
        )
        return ""


def _render_nodes(nodes: list[ASTNode], state: _RenderState) -> str:
    """Render a sequence of AST nodes, handling whitespace trimming between them."""
    output = ""
    for node in nodes:
        node_output = _render_node(node, state)
        output = _append_node_output(output, node_output, node, state)
    return output


def _append_node_output(
    output: str,
    node_output: str,
    node: ASTNode,
    state: _RenderState,
) -> str:
    """Append a node's rendered output to the accumulated string,
    applying whitespace trimming for trimLeft / trimRight.

    - trimLeft on the *current* node: trim trailing whitespace from previous output.
    - trimRight from a *previous* node: trim leading whitespace from current output.
    """
    # Handle trimLeft — trim trailing whitespace/newline from previous output
    if hasattr(node, "trim_left") and node.trim_left and len(output) > 0:
        output = _trim_trailing_whitespace(output)

    # Handle pending trimRight — trim leading whitespace/newline from this output
    if state.pending_trim_right and len(node_output) > 0:
        output += _trim_leading_whitespace(node_output)
        state.pending_trim_right = False
    else:
        output += node_output

    return output


# ============================================================================
# Expression Evaluation
# ============================================================================


def _evaluate_expression(expr: Any, state: _RenderState) -> Any:
    """Evaluate an expression AST node and return its value."""
    expr_type = expr.type

    if expr_type == ExpressionType.LITERAL:
        return _evaluate_literal(expr)
    elif expr_type == ExpressionType.IDENTIFIER:
        return _evaluate_identifier(expr, state)
    elif expr_type == ExpressionType.BINARY:
        return _evaluate_binary(expr, state)
    elif expr_type == ExpressionType.UNARY:
        return _evaluate_unary(expr, state)
    elif expr_type == ExpressionType.FILTER:
        return _evaluate_filter(expr, state)
    elif expr_type == ExpressionType.GROUP:
        return _evaluate_expression(expr.expression, state)
    elif expr_type == ExpressionType.MEMBER:
        return _evaluate_member(expr, state)
    else:
        raise ValueError(f"Unknown expression type: {expr_type}")


def _evaluate_literal(expr: LiteralExpression) -> Any:
    """Evaluate a literal expression (number, string, boolean, null)."""
    return expr.value


def _evaluate_identifier(expr: IdentifierExpression, state: _RenderState) -> Any:
    """Evaluate an identifier expression (variable lookup)."""
    name = expr.name

    # Schema variables — resolve with shorthand support
    if name.startswith("schema:"):
        return resolve_schema_variable(name, state.context.variables)

    # Prompt variables — preserve for post-processing
    if name.startswith("prompt:") or name.startswith('"'):
        state.has_deferred_variables = True
        return "{{" + name + "}}"

    # Regular variable lookup
    return resolve_variable(name, state.context.variables)


def _evaluate_binary(expr: BinaryExpression, state: _RenderState) -> Any:
    """Evaluate a binary expression (comparison, logical, contains, ??)."""
    # Nullish coalescing uses short-circuit evaluation
    if expr.operator == "??":
        left = _evaluate_expression(expr.left, state)
        if _is_truthy(left):
            return left
        return _evaluate_expression(expr.right, state)

    left = _evaluate_expression(expr.left, state)
    right = _evaluate_expression(expr.right, state)

    if expr.operator == "==":
        return left == right
    elif expr.operator == "!=":
        return left != right
    elif expr.operator == ">":
        return left > right  # type: ignore[operator]
    elif expr.operator == "<":
        return left < right  # type: ignore[operator]
    elif expr.operator == ">=":
        return left >= right  # type: ignore[operator]
    elif expr.operator == "<=":
        return left <= right  # type: ignore[operator]
    elif expr.operator in ("and", "&&"):
        return _is_truthy(left) and _is_truthy(right)
    elif expr.operator in ("or", "||"):
        return _is_truthy(left) or _is_truthy(right)
    elif expr.operator == "contains":
        return _evaluate_contains(left, right)
    else:
        raise ValueError(f"Unknown binary operator: {expr.operator}")


def _evaluate_unary(expr: UnaryExpression, state: _RenderState) -> Any:
    """Evaluate a unary expression (not, !, -)."""
    argument = _evaluate_expression(expr.argument, state)

    if expr.operator in ("not", "!"):
        return not _is_truthy(argument)
    elif expr.operator == "-":
        if isinstance(argument, (int, float)):
            return -argument
        return 0
    else:
        raise ValueError(f"Unknown unary operator: {expr.operator}")


def _evaluate_filter(expr: FilterExpression, state: _RenderState) -> Any:
    """Evaluate a filter expression (value | filterName:args)."""
    value = _evaluate_expression(expr.value, state)

    # Evaluate filter arguments
    args: list[Any] = []
    for arg in expr.args:
        arg_value = _evaluate_expression(arg, state)
        # If a filter argument is an identifier that resolved to None,
        # treat it as a string literal (e.g. date:YYYY-MM-DD, callout:info)
        if arg_value is None and arg.type == ExpressionType.IDENTIFIER:
            arg_value = arg.name
        args.append(arg_value)

    string_value = _value_to_string(value)

    # Build parameter string from already-parsed args
    param_string: str | None = None
    if args:
        formatted_args: list[str] = []
        for a in args:
            if isinstance(a, str):
                if _is_quoted_string(a):
                    formatted_args.append(a)
                elif re.match(r"\s*\w+\s*=>", a):
                    # Arrow function expressions (e.g. map:item => item.name)
                    formatted_args.append(a)
                elif re.match(r"^[\w.:+\-*/]+$", a):
                    # Simple values that don't need quoting
                    formatted_args.append(a)
                else:
                    formatted_args.append(f'"{a}"')
            else:
                formatted_args.append(str(a))

        if len(formatted_args) > 1:
            param_string = ",".join(formatted_args)
        else:
            param_string = formatted_args[0] if formatted_args else ""

    return apply_filter_direct(
        string_value, expr.name, param_string, state.context.current_url
    )


def _evaluate_member(expr: MemberExpression, state: _RenderState) -> Any:
    """Evaluate a member-access expression (obj.property or obj[index])."""
    obj = _evaluate_expression(expr.object, state)
    prop = _evaluate_expression(expr.property, state)

    if obj is None:
        return None

    # Array access with numeric index
    if isinstance(obj, list) and isinstance(prop, (int, float)):
        idx = int(prop)
        return obj[idx] if 0 <= idx < len(obj) else None

    # Array access with string that's a number
    if isinstance(obj, list) and isinstance(prop, str) and re.match(r"^\d+$", prop):
        idx = int(prop)
        return obj[idx] if 0 <= idx < len(obj) else None

    # Dict / object property access
    if isinstance(obj, dict) and prop is not None:
        return obj.get(prop)

    return None


def _evaluate_contains(left: Any, right: Any) -> bool:
    """Evaluate a 'contains' binary expression.

    - For arrays: case-insensitive string comparison, or loose equality.
    - For strings: case-insensitive substring check.
    """
    if left is None or right is None:
        return False

    # Array contains
    if isinstance(left, list):
        for item in left:
            if isinstance(item, str) and isinstance(right, str):
                if item.lower() == right.lower():
                    return True
            elif item == right:
                return True
        return False

    # String contains (case-insensitive)
    if isinstance(left, str):
        search_value = right if isinstance(right, str) else str(right)
        return search_value.lower() in left.lower()

    return False


# ============================================================================
# Prompt Handling
# ============================================================================


def _get_prompt_base(expr: Any) -> str | None:
    """Check if an expression is a prompt (string literal or filter chain
    whose base is a string literal).  Returns the prompt text if found,
    or None.
    """
    if expr.type == ExpressionType.LITERAL and isinstance(expr.value, str):
        return expr.value
    if expr.type == ExpressionType.FILTER:
        return _get_prompt_base(expr.value)
    return None


def _reconstruct_prompt_template(expr: Any) -> str:
    """Reconstruct template syntax for a prompt expression,
    e.g. FilterExpression(name='title', value=Literal("prompt"))
         -> {{"prompt"|title}}
    """
    return "{{" + _reconstruct_prompt_template_inner(expr) + "}}"


def _reconstruct_prompt_template_inner(expr: Any) -> str:
    """Inner helper for prompt template reconstruction."""
    if expr.type == ExpressionType.LITERAL:
        value = expr.value
        return f'"{value}"' if isinstance(value, str) else str(value)
    if expr.type == ExpressionType.FILTER:
        inner = _reconstruct_prompt_template_inner(expr.value)
        filter_str = f"{inner}|{expr.name}"
        if expr.args:
            filter_str += ":" + _format_filter_args(expr.args)
        return filter_str
    return str(expr)


def _format_filter_args(args: list[Any]) -> str:
    """Format filter arguments as a colon-separated parameter string."""
    formatted: list[str] = []
    for arg in args:
        if arg.type == ExpressionType.LITERAL:
            val = arg.value
            if isinstance(val, str):
                if re.match(r"^['\"].*['\"]$", val) or '":"' in val or "':'" in val:
                    formatted.append(val)
                else:
                    formatted.append(f'"{val}"')
            else:
                formatted.append(str(val))
        else:
            formatted.append(str(getattr(arg, "value", getattr(arg, "name", ""))))

    if len(formatted) > 1:
        return f"({','.join(formatted)})"
    return formatted[0] if formatted else ""


# ============================================================================
# Utility Functions
# ============================================================================


def _is_truthy(value: Any) -> bool:
    """Check if a value is truthy for template conditionals.

    Falsy values: None, "", 0, False, [], {}
    Everything else is truthy.
    """
    if value is None:
        return False
    if value is False:
        return False
    if value is True:
        return True
    if isinstance(value, (list, dict)):
        return len(value) > 0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value != ""
    return True


def _value_to_string(value: Any) -> str:
    """Convert any value to a string for template output.

    Handles single-element array unwrapping and delegates to the
    resolver's value_to_string for everything else.
    """
    if value is None:
        return ""
    # Single-element array of a non-object scalar: unwrap
    if (
        isinstance(value, list)
        and len(value) == 1
        and not isinstance(value[0], (dict, list))
    ):
        return str(value[0])
    return value_to_string(value)


def _trim_trailing_whitespace(s: str) -> str:
    """Trim trailing tabs/spaces and an optional newline.

    Used for trimLeft handling — removes whitespace at the end of
    the previous node's output.
    """
    return re.sub(r"[\t ]*\r?\n?$", "", s)


def _trim_leading_whitespace(s: str) -> str:
    """Trim leading tabs/spaces and an optional newline.

    Used for trimRight handling — removes whitespace at the start
    of the current node's output.
    """
    return re.sub(r"^[\t ]*\r?\n?", "", s)


def _is_quoted_string(s: str) -> bool:
    """Check if a string is already quoted or contains quoted pairs.

    Used to avoid double-quoting filter arguments.
    Examples: "value", 'value', "old":"new"
    """
    return (
        bool(re.match(r"^['\"].*['\"]$", s)) or '":"' in s or "':'" in s
    )


# ============================================================================
# Convenience Function
# ============================================================================


def render_template(
    template: str,
    variables: dict[str, Any],
    current_url: str = "",
) -> str:
    """Simple render function for basic usage.

    Returns the rendered output string. Prints errors to stderr
    if any are encountered.
    """
    result = render(template, RenderContext(variables=variables, current_url=current_url))
    if result.errors:
        import sys

        print(f"Template render errors: {result.errors}", file=sys.stderr)
    return result.output
