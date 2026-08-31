"""Text To Columns: split one field on delimiter characters.

Assumed config shape:
    <Field>Tags</Field>
    <Delimeters value="," />          (each CHARACTER is a delimiter, like Alteryx;
                                       and yes, the misspelling is the element name)
    <NumFields value="3" />           (columns mode)
    <RootName>Tag</RootName>          (new columns Tag1..TagN)
    <SplitRows value="False" />       (True = split to rows: one row per part)

Columns mode keeps any extra text in the LAST column (Alteryx's "leave extra in
last column" option; its default of dropping extra with a warning loses data, so
the more conservative behavior is emitted with a NOTE). Split-to-rows becomes
explode(), replacing the field like Alteryx does.
"""

from __future__ import annotations

import re

from ..errors import ConfigUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, cfg_find, cfg_root, cfg_text, pystr


def _split_args(delims: str) -> str:
    """split() arguments for one or many single-character delimiters."""
    if len(delims) == 1:
        return f"{pystr(delims)}, regex=False"
    return f"{pystr('[' + re.escape(delims) + ']')}, regex=True"


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    src = ctx.sole_input()
    out = ctx.var("Output")
    tid = node.tool_id
    field = cfg_text(node, "Field").strip()
    delims = cfg_find(node, "Delimeters").get("value") or ","
    # Accept both observed value shapes: <SplitRows value="True"/> and text content.
    sr_el = cfg_root(node).find("SplitRows")
    split_rows = sr_el is not None and (
        sr_el.get("value") == "True" or (sr_el.text or "").strip() == "True"
    )

    if split_rows:
        lines = [
            f"{out} = {src}.copy()",
            f"{out}[{pystr(field)}] = {out}[{pystr(field)}].str.split({_split_args(delims)})",
            f"{out} = {out}.explode({pystr(field)}, ignore_index=True)",
        ]
        return Emission(lines=lines, outputs={"Output": out})

    num_raw = cfg_find(node, "NumFields").get("value") or ""
    try:
        num = int(num_raw)
    except ValueError:
        raise ConfigUnsupported(f"Text To Columns NumFields is not an integer: {num_raw!r}") from None
    if num < 1:
        raise ConfigUnsupported("Text To Columns needs NumFields >= 1")
    root = cfg_text(node, "RootName", default=field).strip() or field
    new_cols = ", ".join(pystr(f"{root}{i}") for i in range(1, num + 1))

    parts = f"_parts_{tid}"
    lines = [
        # n=num-1 caps the splits so extra text stays in the last column; reindex
        # pads with null columns when no row has that many parts.
        f"{parts} = {src}[{pystr(field)}].str.split({_split_args(delims)}, n={num - 1}, expand=True)",
        f"{parts} = {parts}.reindex(columns=range({num}))",
        f"{parts}.columns = [{new_cols}]",
        f"{out} = pd.concat([{src}, {parts}], axis=1)",
        "# NOTE(yxmd2py): extra text beyond the last column is KEPT there; Alteryx's",
        "# default drops it with a warning - trim the last column if you need that.",
    ]
    return Emission(lines=lines, outputs={"Output": out})


SPEC = ToolSpec(
    kind="texttocolumns", in_ports=("Input",), out_ports=("Output",),
    translate=_translate, label="Text To Columns",
)
