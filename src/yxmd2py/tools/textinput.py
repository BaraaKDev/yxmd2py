"""Text Input: inline data typed into the canvas -> an inline pd.DataFrame literal.

Assumed config shape (documented in tests/fixtures/README.md):
    <Fields><Field name="A"/><Field name="B"/></Fields>
    <Data><r><c>1</c><c>x</c></r> ... </Data>

All values are emitted as strings — Alteryx types Text Input data in a later Select,
and guessing types here would diverge from the canvas.
"""

from __future__ import annotations

from ..errors import ConfigUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, attr, cfg_findall, pystr


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    field_els = cfg_findall(node, "Fields/Field")
    if not field_els:
        raise ConfigUnsupported("Text Input has no <Fields>")
    names = [attr(el, "name") for el in field_els]

    rows: list[list[str | None]] = []
    for r_el in cfg_findall(node, "Data/r"):
        cells = [c.text if c.text is not None else "" for c in r_el.findall("c")]
        # Short rows pad with None (null), long rows are a config we don't understand.
        if len(cells) > len(names):
            raise ConfigUnsupported("Text Input row has more cells than fields")
        cells += [None] * (len(names) - len(cells))
        rows.append(cells)

    var = ctx.var("Output")
    lines = [f"{var} = pd.DataFrame({{"]
    for i, name in enumerate(names):
        values = ", ".join("None" if row[i] is None else pystr(row[i]) for row in rows)
        lines.append(f"    {pystr(name)}: [{values}],")
    lines.append("})")
    lines.append(f"# NOTE(yxmd2py): Text Input values are strings; retype downstream as the canvas did.")
    return Emission(lines=lines, outputs={"Output": var})


SPEC = ToolSpec(
    kind="textinput", in_ports=(), out_ports=("Output",),
    translate=_translate, label="Text Input",
)
