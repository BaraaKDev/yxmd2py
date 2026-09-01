"""Filter: split one input into True and False legs.

Assumed config shape:
    <Expression>[Score] &gt; 50</Expression>
    <Mode>Simple|Custom</Mode>
    <Simple>
      <Operator>&gt;</Operator>
      <Field>Score</Field>
      <Operands><Operand>50</Operand></Operands>
    </Simple>

Alteryx sends rows whose expression evaluates to null to the FALSE leg, hence
mask.fillna(False). Custom mode routes through the expression translator once it
exists (ctx.translate_expression); until then it degrades to a stub carrying the
verbatim expression.
"""

from __future__ import annotations

from ..errors import ConfigUnsupported, ExprUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, cfg_text, col, pystr

_COMPARE_OPS = {"=": "==", "!=": "!=", "<>": "!=", ">": ">", ">=": ">=", "<": "<", "<=": "<="}


def _operand_literal(raw: str) -> str:
    """Numbers stay numbers; everything else becomes a string literal.

    Numeric text is re-emitted through int()/float() rather than echoed: a real
    workflow filtered on a FIPS code operand of 095, and a leading-zero integer
    literal is a SyntaxError in python source.
    """
    text = raw.strip()
    try:
        return repr(int(text))
    except ValueError:
        pass
    try:
        return repr(float(text))
    except ValueError:
        return pystr(text)


def _simple_mask(node: Node, src: str) -> list[str]:
    """Lines computing the boolean mask for Simple mode (last line defines `mask`)."""
    op = cfg_text(node, "Simple/Operator").strip()
    field = cfg_text(node, "Simple/Field").strip()
    target = col(src, field)

    if op in _COMPARE_OPS:
        operand = _operand_literal(cfg_text(node, "Simple/Operands/Operand"))
        return [f"mask = {target} {_COMPARE_OPS[op]} {operand}"]
    if op in ("Contains", "NotContains"):
        operand = pystr(cfg_text(node, "Simple/Operands/Operand").strip())
        expr = f"{target}.str.contains({operand}, case=False, regex=False)"
        note = "  # NOTE(yxmd2py): Alteryx Contains is case-insensitive"
        return [f"mask = {'~' if op == 'NotContains' else ''}({expr}){note}"]
    if op in ("IsNull", "NotNull"):
        expr = f"{target}.isna()"
        return [f"mask = {'~' if op == 'NotNull' else ''}{expr}"]
    if op in ("IsEmpty", "NotEmpty"):
        expr = f"({target}.isna() | ({target} == ''))"
        return [f"mask = {'~' if op == 'NotEmpty' else ''}{expr}"]
    raise ConfigUnsupported(f"Filter simple operator '{op}' is not supported")


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    src = ctx.sole_input()
    mode = cfg_text(node, "Mode", default="Custom").strip()
    mask = f"mask_{node.tool_id}"

    if mode == "Simple":
        mask_lines = [line.replace("mask =", f"{mask} =", 1) for line in _simple_mask(node, src)]
    else:
        expression = cfg_text(node, "Expression", default="").strip()
        if ctx.translate_expression is None:
            raise ConfigUnsupported(f"custom filter expression: {expression!r}")
        try:
            code = ctx.translate_expression(expression, src)
        except ExprUnsupported as exc:
            raise ConfigUnsupported(
                f"custom filter expression {expression!r} ({exc})"
            ) from exc
        mask_lines = [f"{mask} = {code}"]

    lines = mask_lines + [
        f"{mask} = {mask}.fillna(False)  # Alteryx: null comparisons go to the False leg"
    ]
    outputs: dict[str, str] = {}
    if "True" in ctx.consumed or not ctx.consumed:
        var = ctx.var("True")
        lines.append(f"{var} = {src}[{mask}]")
        outputs["True"] = var
    if "False" in ctx.consumed:
        var = ctx.var("False")
        lines.append(f"{var} = {src}[~{mask}]")
        outputs["False"] = var

    return Emission(lines=lines, outputs=outputs)


SPEC = ToolSpec(
    kind="filter", in_ports=("Input",), out_ports=("True", "False"),
    translate=_translate, label="Filter",
)
