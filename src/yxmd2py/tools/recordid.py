"""RecordID: number the rows.

Assumed config shape:
    <FieldName>RecordID</FieldName>
    <StartValue>1</StartValue>
    <Position>0</Position>        (0 = first column, anything else = last)
"""

from __future__ import annotations

from ..errors import ConfigUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, cfg_text, pystr


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    src = ctx.sole_input()
    out = ctx.var("Output")
    field = cfg_text(node, "FieldName", default="RecordID").strip() or "RecordID"
    start_raw = cfg_text(node, "StartValue", default="1").strip() or "1"
    try:
        start = int(start_raw)
    except ValueError:
        raise ConfigUnsupported(f"RecordID start value is not an integer: {start_raw!r}") from None
    first = cfg_text(node, "Position", default="0").strip() == "0"

    lines = [f"{out} = {src}.copy()"]
    if first:
        lines.append(f"{out}.insert(0, {pystr(field)}, range({start}, {start} + len({out})))")
    else:
        lines.append(f"{out}[{pystr(field)}] = range({start}, {start} + len({out}))")
    return Emission(lines=lines, outputs={"Output": out})


SPEC = ToolSpec(
    kind="recordid", in_ports=("Input",), out_ports=("Output",),
    translate=_translate, label="Record ID",
)
