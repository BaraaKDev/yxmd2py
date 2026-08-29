"""Sort: multi-key ascending/descending.

Assumed config shape:
    <SortInfo><Field field="A" order="Ascending" /><Field field="B" order="Descending" /></SortInfo>

mergesort keeps the sort stable, matching Alteryx. Null placement is a documented
convention, not a guarantee: pandas puts NaN last regardless of direction.
"""

from __future__ import annotations

from ..errors import ConfigUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, attr, cfg_findall, pystr


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    src = ctx.sole_input()
    out = ctx.var("Output")

    field_els = cfg_findall(node, "SortInfo/Field")
    if not field_els:
        raise ConfigUnsupported("Sort has no <SortInfo> fields")

    keys, ascending = [], []
    for el in field_els:
        keys.append(attr(el, "field"))
        order = el.get("order", "Ascending")
        ascending.append(order != "Descending")

    by = ", ".join(pystr(k) for k in keys)
    asc = ", ".join(str(a) for a in ascending)
    lines = [
        f"{out} = {src}.sort_values(by=[{by}], ascending=[{asc}], kind='mergesort', ignore_index=True)",
        "# NOTE(yxmd2py): pandas places nulls last in either direction; Alteryx may differ.",
    ]
    return Emission(lines=lines, outputs={"Output": out})


SPEC = ToolSpec(
    kind="sort", in_ports=("Input",), out_ports=("Output",),
    translate=_translate, label="Sort",
)
