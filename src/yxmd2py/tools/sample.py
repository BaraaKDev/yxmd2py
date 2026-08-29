"""Sample: First/Last/Skip/1-in-N rows, optionally per group.

Assumed config shape:
    <Mode>First|Last|Skip|OneInN</Mode>
    <N>10</N>                       (element text; a value attr is accepted too)
    <GroupFields><Field field="G" /></GroupFields>     (optional)

Grouped variants use cumcount() comparisons so all four modes share one shape.
Random-percent sampling is a different tool (RandomRecords) and lands later.
"""

from __future__ import annotations

from ..errors import ConfigUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, attr, cfg_findall, cfg_root, pystr


def _read_n(node: Node) -> int:
    el = cfg_root(node).find("N")
    raw = None
    if el is not None:
        raw = el.text if el.text and el.text.strip() else el.get("value")
    if raw is None:
        raise ConfigUnsupported("Sample has no <N>")
    try:
        return int(raw.strip())
    except ValueError:
        raise ConfigUnsupported(f"Sample <N> is not an integer: {raw!r}") from None


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    src = ctx.sole_input()
    out = ctx.var("Output")
    mode = cfg_root(node).findtext("Mode", default="First").strip()
    n = _read_n(node)
    groups = [attr(el, "field") for el in cfg_findall(node, "GroupFields/Field")]

    if groups:
        gb = f"{src}.groupby([{', '.join(pystr(g) for g in groups)}], sort=False)"
        per_mode = {
            "First": f"{out} = {src}[{gb}.cumcount() < {n}]",
            "Last": f"{out} = {src}[{gb}.cumcount(ascending=False) < {n}]",
            "Skip": f"{out} = {src}[{gb}.cumcount() >= {n}]",
            "OneInN": f"{out} = {src}[{gb}.cumcount() % {n} == 0]",
        }
    else:
        per_mode = {
            "First": f"{out} = {src}.head({n})",
            "Last": f"{out} = {src}.tail({n})",
            "Skip": f"{out} = {src}.iloc[{n}:]",
            "OneInN": f"{out} = {src}.iloc[::{n}]",
        }

    if mode not in per_mode:
        raise ConfigUnsupported(f"Sample mode '{mode}' is not supported")

    return Emission(lines=[per_mode[mode]], outputs={"Output": out})


SPEC = ToolSpec(
    kind="sample", in_ports=("Input",), out_ports=("Output",),
    translate=_translate, label="Sample",
)
