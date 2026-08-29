"""Union: stack inputs by field name or by position.

Assumed config shape:
    <Mode>ByName|ByPos|Manual</Mode>
    <ByName_OutputMode>All|Common</ByName_OutputMode>     (ByName only)

Inputs arrive on numbered ports ("#1", "#2", ...) and are stacked in that order.
ByName + All matches pandas concat exactly: align on names, NaN-fill the gaps.
Manual mode encodes a hand-drawn column mapping we don't reconstruct -> stub.
"""

from __future__ import annotations

from ..errors import ConfigUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, cfg_root, cfg_text


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    if len(ctx.ordered_inputs) < 2:
        raise ConfigUnsupported(
            f"Union expects 2+ inputs, found {len(ctx.ordered_inputs)}"
        )
    frames = [var for _, var in ctx.ordered_inputs]
    out = ctx.var("Output")
    mode = cfg_root(node).findtext("Mode", default="ByName").strip() or "ByName"

    flist = f"_frames_{node.tool_id}"
    lines = [f"{flist} = [{', '.join(frames)}]"]

    if mode == "ByName":
        output_mode = cfg_text(node, "ByName_OutputMode", default="All").strip() or "All"
        if output_mode == "All":
            lines.append(
                f"{out} = pd.concat({flist}, ignore_index=True)"
                "  # aligns by name, fills missing columns with NaN"
            )
        elif output_mode == "Common":
            common = f"_common_{node.tool_id}"
            lines.append(
                f"{common} = [c for c in {flist}[0].columns"
                f" if all(c in f.columns for f in {flist})]"
            )
            lines.append(f"{out} = pd.concat([f[{common}] for f in {flist}], ignore_index=True)")
        else:
            raise ConfigUnsupported(f"Union ByName output mode '{output_mode}' is not supported")
    elif mode == "ByPos":
        cols = f"_cols_{node.tool_id}"
        lines.append(f"{cols} = list({flist}[0].columns)")
        lines.append(
            f"{out} = pd.concat([f.set_axis({cols}, axis=1) for f in {flist}], ignore_index=True)"
        )
        lines.append("# NOTE(yxmd2py): ByPos assumes every input has the same column count.")
    else:
        raise ConfigUnsupported(f"Union mode '{mode}' is not supported")

    return Emission(lines=lines, outputs={"Output": out})


SPEC = ToolSpec(
    kind="union", in_ports=("#1", "#2"), out_ports=("Output",),
    translate=_translate, label="Union",
)
