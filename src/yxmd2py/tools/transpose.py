"""Transpose: wide to tall - key columns stay, data columns become Name/Value rows.

Assumed config shape:
    <KeyFields><Field field="Id" /></KeyFields>
    <DataFields>
      <Field field="Jan" selected="True" />
      <Field field="*Unknown" selected="False" />
    </DataFields>

pandas melt orders column-major (all of Jan, then all of Feb); Alteryx emits
record-major (each record's fields together). The stable sort on the original
index reproduces Alteryx's order exactly.
"""

from __future__ import annotations

from ..errors import ConfigUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, attr, cfg_findall, pystr


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    src = ctx.sole_input()
    out = ctx.var("Output")

    keys = [attr(el, "field") for el in cfg_findall(node, "KeyFields/Field")]
    data = [
        attr(el, "field")
        for el in cfg_findall(node, "DataFields/Field")
        if attr(el, "field") != "*Unknown" and el.get("selected", "True") == "True"
    ]
    if not data:
        raise ConfigUnsupported("Transpose has no selected data fields")

    key_list = ", ".join(pystr(k) for k in keys)
    data_list = ", ".join(pystr(d) for d in data)
    lines = [
        f"{out} = {src}.melt(id_vars=[{key_list}], value_vars=[{data_list}],",
        f"    var_name='Name', value_name='Value', ignore_index=False)",
        f"{out} = {out}.sort_index(kind='mergesort').reset_index(drop=True)  # record-major, like Alteryx",
    ]
    return Emission(lines=lines, outputs={"Output": out})


SPEC = ToolSpec(
    kind="transpose", in_ports=("Input",), out_ports=("Output",),
    translate=_translate, label="Transpose",
)
