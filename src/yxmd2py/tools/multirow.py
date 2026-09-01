"""Multi-Row Formula: expressions that read other rows via [Row-1:Field] refs.

Config shape, verbatim from a genuine Designer export (CubicSpline):
    <UpdateField value="False" />
    <UpdateField_Name>T</UpdateField_Name>          (target when updating)
    <CreateField_Name>__weight__</CreateField_Name> (target when creating)
    <CreateField_Type>Double</CreateField_Type>
    <OtherRows>NULL</OtherRows>                     (boundary value: NULL or 0)
    <NumRows value="1" />
    <Expression>([Row-1:__diff__] - [__diff__])</Expression>
    <GroupByFields />                               (<Field field=.../> children when grouped)

The supported subset is what real workflows actually use: [Row±N:] references to
OTHER fields, which vectorize as shift(). An expression that reads ITS OWN target
field's prior value (a running total) is sequential, does not vectorize, and is
refused with the verbatim expression - a wrong shift() would look plausible and
be silently incorrect, the exact failure mode this project exists to avoid.
"""

from __future__ import annotations

import re

from ..errors import ConfigUnsupported, ExprUnsupported
from ..exprlang import translate_expression
from ..exprlang.ast import RowContext
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, attr, cfg_findall, cfg_root, cfg_text, pystr


def _self_reference(expression: str, target: str) -> bool:
    """Does the expression read the target field's value from another row?"""
    pattern = r"\[\s*row[+-]\d+\s*:\s*" + re.escape(target) + r"\s*\]"
    return re.search(pattern, expression, re.IGNORECASE) is not None


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    src = ctx.sole_input()
    out = ctx.var("Output")

    update_el = cfg_root(node).find("UpdateField")
    updating = update_el is not None and (
        update_el.get("value") == "True" or (update_el.text or "").strip() == "True"
    )

    if updating:
        target = cfg_text(node, "UpdateField_Name").strip()
    else:
        target = cfg_text(node, "CreateField_Name").strip()
    if not target:
        raise ConfigUnsupported("Multi-Row Formula names no target field")

    expression = cfg_text(node, "Expression")

    if _self_reference(expression, target):
        raise ConfigUnsupported(
            f"expression reads its own prior output ({expression!r}) - a running "
            "calculation is sequential and cannot become a shift(); translate by hand "
            "(itertools.accumulate or a python loop)"
        )

    other_rows = cfg_text(node, "OtherRows", default="NULL").strip().upper()
    if other_rows in ("NULL", ""):
        zero_fill = False
    elif other_rows in ("0", "ZERO"):
        zero_fill = True
    else:
        raise ConfigUnsupported(
            f"OtherRows value '{other_rows}' is not supported (NULL and 0 are)"
        )

    groups = tuple(attr(el, "field") for el in cfg_findall(node, "GroupByFields/Field"))

    row_ctx = RowContext(group_cols=groups, zero_fill=zero_fill)
    lines = [f"{out} = {src}.copy()"]
    try:
        code = translate_expression(expression, out, row_context=row_ctx)
    except ExprUnsupported as exc:
        raise ConfigUnsupported(f"expression {expression!r} ({exc})") from exc
    lines.append(f"{out}[{pystr(target)}] = {code}")

    return Emission(lines=lines, outputs={"Output": out})


SPEC = ToolSpec(
    kind="multirow", in_ports=("Input",), out_ports=("Output",),
    translate=_translate, label="Multi-Row Formula",
)
