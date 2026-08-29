"""AST -> vectorized pandas code.

Boolean logic becomes &, |, ~ with every operand parenthesized (their precedence in
python would otherwise bind tighter than comparisons). IF chains become np.select,
which stays flat and readable where nested np.where would not.
"""

from __future__ import annotations

from ..errors import ExprUnsupported
from .ast import BinOp, FieldRef, Func, IfExpr, Lit, UnaryOp
from .functions import emit_call
from .parser import parse

_BOOL_OPS = {"and": "&", "or": "|"}


def translate_expression(text: str, df_var: str) -> str:
    """Alteryx expression -> pandas code against df_var, or ExprUnsupported."""
    return _emit(parse(text), df_var)


def _emit(node, df: str) -> str:
    if isinstance(node, FieldRef):
        return f"{df}[{node.name!r}]"
    if isinstance(node, Lit):
        return repr(node.value)
    if isinstance(node, UnaryOp):
        inner = _emit(node.operand, df)
        return f"~({inner})" if node.op == "not" else f"-({inner})"
    if isinstance(node, BinOp):
        left, right = _emit(node.left, df), _emit(node.right, df)
        if node.op in _BOOL_OPS:
            return f"({left}) {_BOOL_OPS[node.op]} ({right})"
        return f"{left} {node.op} {right}"
    if isinstance(node, Func):
        return emit_call(node.name, [_emit(a, df) for a in node.args])
    if isinstance(node, IfExpr):
        conds = ", ".join(f"({_emit(c, df)})" for c, _ in node.pairs)
        vals = ", ".join(_emit(v, df) for _, v in node.pairs)
        default = _emit(node.default, df) if node.default is not None else "pd.NA"
        if len(node.pairs) == 1:
            return f"np.where({conds}, {vals}, {default})"
        return f"np.select([{conds}], [{vals}], default={default})"
    raise ExprUnsupported(f"cannot emit {type(node).__name__}")
