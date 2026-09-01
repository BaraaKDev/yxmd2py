"""AST -> vectorized pandas code.

Boolean logic becomes &, |, ~ with every operand parenthesized (their precedence in
python would otherwise bind tighter than comparisons). IF chains become np.select,
which stays flat and readable where nested np.where would not.

[Row±N:Field] references emit shift() and are only legal inside a Multi-Row
Formula, which supplies the RowContext (grouping and boundary fill); anywhere else
they raise ExprUnsupported.
"""

from __future__ import annotations

from ..errors import ExprUnsupported
from .ast import BinOp, FieldRef, Func, IfExpr, Lit, RowContext, RowRef, UnaryOp
from .functions import emit_call
from .parser import parse

_BOOL_OPS = {"and": "&", "or": "|"}

# Arithmetic/comparison precedence, used to re-parenthesize operands: the parser
# discards source parentheses, so (a-b)/(c-d) must not emit as a - b / c - d.
_PREC = {
    "==": 3, "!=": 3, "<": 3, "<=": 3, ">": 3, ">=": 3,
    "+": 4, "-": 4,
    "*": 5, "/": 5,
}


def translate_expression(text: str, df_var: str, row_context: RowContext | None = None) -> str:
    """Alteryx expression -> pandas code against df_var, or ExprUnsupported."""
    return _emit(parse(text), df_var, row_context)


def _emit(node, df: str, row: RowContext | None) -> str:
    if isinstance(node, FieldRef):
        return f"{df}[{node.name!r}]"
    if isinstance(node, RowRef):
        return _emit_row_ref(node, df, row)
    if isinstance(node, Lit):
        return repr(node.value)
    if isinstance(node, UnaryOp):
        inner = _emit(node.operand, df, row)
        return f"~({inner})" if node.op == "not" else f"-({inner})"
    if isinstance(node, BinOp):
        if node.op in _BOOL_OPS:
            left, right = _emit(node.left, df, row), _emit(node.right, df, row)
            return f"({left}) {_BOOL_OPS[node.op]} ({right})"
        prec = _PREC[node.op]
        left = _emit_operand(node.left, df, row, prec, is_right=False)
        right = _emit_operand(node.right, df, row, prec, is_right=True)
        return f"{left} {node.op} {right}"
    if isinstance(node, Func):
        return emit_call(node.name, [_emit(a, df, row) for a in node.args])
    if isinstance(node, IfExpr):
        conds = ", ".join(f"({_emit(c, df, row)})" for c, _ in node.pairs)
        vals = ", ".join(_emit(v, df, row) for _, v in node.pairs)
        default = _emit(node.default, df, row) if node.default is not None else "pd.NA"
        if len(node.pairs) == 1:
            return f"np.where({conds}, {vals}, {default})"
        return f"np.select([{conds}], [{vals}], default={default})"
    raise ExprUnsupported(f"cannot emit {type(node).__name__}")


def _emit_operand(child, df: str, row: RowContext | None, parent_prec: int, is_right: bool) -> str:
    """Emit a binary operand, parenthesized when python's precedence would rebind it.

    A lower-precedence child always needs parens; an equal-precedence RIGHT child
    does too (the parser is left-associative, so such a child can only come from
    explicit source parens: a - (b - c)).
    """
    code = _emit(child, df, row)
    if isinstance(child, BinOp) and child.op in _PREC:
        child_prec = _PREC[child.op]
        if child_prec < parent_prec or (is_right and child_prec == parent_prec):
            return f"({code})"
    return code


def _emit_row_ref(node: RowRef, df: str, row: RowContext | None) -> str:
    if row is None:
        raise ExprUnsupported(
            f"[Row{node.offset:+d}:{node.name}] is only valid in a Multi-Row Formula"
        )
    # [Row-1:X] means the PREVIOUS row's X on the current row -> shift(1).
    shift = -node.offset
    fill = ", fill_value=0" if row.zero_fill else ""
    if row.group_cols:
        gcols = ", ".join(repr(g) for g in row.group_cols)
        return f"{df}.groupby([{gcols}], sort=False)[{node.name!r}].shift({shift}{fill})"
    return f"{df}[{node.name!r}].shift({shift}{fill})"
