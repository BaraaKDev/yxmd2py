"""Formula: sequential computed columns.

Assumed config shape:
    <FormulaFields>
      <FormulaField expression="..." field="New" type="Double" size="8" />
    </FormulaFields>

Fields are applied IN ORDER on a copy of the input, because a later formula may
reference an earlier one's output — so every expression is translated against the
output frame, not the input. A formula the engine can't translate becomes a pd.NA
column carrying the verbatim expression in a TODO; one bad formula marks the tool
partial instead of stubbing the whole thing.
"""

from __future__ import annotations

from ..errors import ConfigUnsupported, ExprUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, attr, cfg_findall, pystr


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    src = ctx.sole_input()
    out = ctx.var("Output")
    field_els = cfg_findall(node, "FormulaFields/FormulaField")
    if not field_els:
        raise ConfigUnsupported("Formula has no <FormulaFields>")
    if ctx.translate_expression is None:
        raise ConfigUnsupported("formula expressions need the expression engine")

    lines = [f"{out} = {src}.copy()"]
    todos: list[str] = []
    for el in field_els:
        target = attr(el, "field")
        expression = attr(el, "expression")
        try:
            code = ctx.translate_expression(expression, out)
            lines.append(f"{out}[{pystr(target)}] = {code}")
        except ExprUnsupported as exc:
            lines.append(f"# TODO(yxmd2py): untranslated formula for '{target}' ({exc})")
            lines.append(f"# Original expression: {expression}")
            lines.append(f"{out}[{pystr(target)}] = pd.NA")
            todos.append(
                f"Formula (ToolID {node.tool_id}): field '{target}' - {exc} - expression kept verbatim in the script"
            )

    return Emission(
        lines=lines,
        outputs={"Output": out},
        status="partial" if todos else "ok",
        todos=todos,
    )


SPEC = ToolSpec(
    kind="formula", in_ports=("Input",), out_ports=("Output",),
    translate=_translate, label="Formula",
)
