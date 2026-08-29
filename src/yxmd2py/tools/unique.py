"""Unique: first occurrence per key -> Unique leg, the rest -> Dup leg.

Assumed config shape:
    <UniqueFields><Field field="A" /><Field field="B" /></UniqueFields>

pandas treats NaN keys as equal to each other (so a second null-keyed row is a
duplicate), which matches how Alteryx groups nulls here.
"""

from __future__ import annotations

from ..errors import ConfigUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, attr, cfg_findall, pystr


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    src = ctx.sole_input()
    field_els = cfg_findall(node, "UniqueFields/Field")
    if not field_els:
        raise ConfigUnsupported("Unique has no <UniqueFields>")
    keys = ", ".join(pystr(attr(el, "field")) for el in field_els)

    mask = f"_dup_{node.tool_id}"
    lines = [f"{mask} = {src}.duplicated(subset=[{keys}], keep='first')"]
    outputs: dict[str, str] = {}

    if "Unique" in ctx.consumed or not ctx.consumed:
        var = ctx.var("Unique")
        lines.append(f"{var} = {src}[~{mask}]")
        outputs["Unique"] = var
    if "Dup" in ctx.consumed:
        var = ctx.var("Dup")
        lines.append(f"{var} = {src}[{mask}]")
        outputs["Dup"] = var

    return Emission(lines=lines, outputs=outputs)


SPEC = ToolSpec(
    kind="unique", in_ports=("Input",), out_ports=("Unique", "Dup"),
    translate=_translate, label="Unique",
)
