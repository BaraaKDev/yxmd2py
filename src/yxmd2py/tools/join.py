"""Join: one input pair -> three outputs (J = matched, L/R = unmatched sides).

Assumed config shape:
    <JoinInfo connection="Left"><Field field="CustId" /></JoinInfo>
    <JoinInfo connection="Right"><Field field="Customer" /></JoinInfo>
    <SelectConfiguration><Configuration outputConnection="Join">...</Configuration></SelectConfiguration>

Null-key semantics are pinned to Alteryx: a null key never matches anything, so
null-keyed rows go straight to the L/R legs. pandas merge would match NaN keys to
each other, hence the explicit non-null filtering.

The embedded Select is translated only for its overwhelmingly common default: the
right key columns deselected. Anything else it deselects or renames is reported as
a TODO and the J output keeps all columns.
"""

from __future__ import annotations

from ..errors import ConfigUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, attr, cfg_findall, cfg_root, pystr


def _key_list(node: Node, side: str) -> list[str]:
    for info in cfg_findall(node, "JoinInfo"):
        if info.get("connection") == side:
            keys = [attr(f, "field") for f in info.findall("Field")]
            if keys:
                return keys
    raise ConfigUnsupported(f"Join has no {side} key fields")


def _embedded_select(node: Node, rkeys: list[str]) -> tuple[list[str], list[str]]:
    """(right_key_names_to_drop_from_J, todos) from the embedded Select config."""
    cfg = cfg_root(node).find("SelectConfiguration/Configuration")
    if cfg is None:
        return [], []
    drops: list[str] = []
    todos: list[str] = []
    for el in cfg.findall("SelectFields/SelectField"):
        name = el.get("field", "")
        selected = el.get("selected", "True") == "True"
        rename = el.get("rename")
        if name == "*Unknown":
            if not selected:
                todos.append("embedded Select deselects *Unknown - J output keeps all columns instead")
            continue
        if selected and (not rename or rename == name.split("_", 1)[-1]):
            continue
        if not selected and name.startswith("Right_") and name[len("Right_"):] in rkeys:
            drops.append(name[len("Right_"):])
            continue
        what = "renames" if selected else "deselects"
        todos.append(f"embedded Select {what} '{name}' - not applied, J output keeps all columns")
    return drops, todos


def _join_by_pos(node: Node) -> bool:
    """Both observed forms: an attr on Configuration, or a <JoinByRecordPos value/> child."""
    root = cfg_root(node)
    if root.get("joinByRecordPos", "False") == "True":
        return True
    el = root.find("JoinByRecordPos")
    return el is not None and el.get("value") == "True"


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    if _join_by_pos(node):
        raise ConfigUnsupported("join by record position is not supported")

    left = ctx.inputs.get("Left")
    right = ctx.inputs.get("Right")
    if not left or not right:
        raise ConfigUnsupported("Join needs both a Left and a Right input connection")

    lkeys = _key_list(node, "Left")
    rkeys = _key_list(node, "Right")
    if len(lkeys) != len(rkeys):
        raise ConfigUnsupported("Join key lists differ in length")

    tid = node.tool_id
    lk = f"_lkeys{tid}"
    rk = f"_rkeys{tid}"
    lines = [
        f"{lk} = [{', '.join(pystr(k) for k in lkeys)}]",
        f"{rk} = [{', '.join(pystr(k) for k in rkeys)}]",
        f"# Alteryx never matches null keys; pandas would, so null-keyed rows are kept out of J.",
        f"_lnull{tid} = {left}[{lk}].isna().any(axis=1)",
        f"_rnull{tid} = {right}[{rk}].isna().any(axis=1)",
    ]
    outputs: dict[str, str] = {}
    consumed = ctx.consumed or {"Join"}
    todos: list[str] = []

    if "Join" in consumed:
        var = ctx.var("Join")
        if lkeys == rkeys:
            # Same-named keys: on= yields ONE key column, which is exactly the
            # Alteryx default (embedded Select deselects the redundant right key).
            lines.append(
                f"{var} = {left}[~_lnull{tid}].merge({right}[~_rnull{tid}], "
                f"on={lk}, how='inner', suffixes=('', '_Right'))"
            )
        else:
            lines.append(
                f"{var} = {left}[~_lnull{tid}].merge({right}[~_rnull{tid}], "
                f"left_on={lk}, right_on={rk}, how='inner', suffixes=('', '_Right'))"
            )
        drops, sel_todos = _embedded_select(node, rkeys)
        todos += [f"Join (ToolID {tid}): {t}" for t in sel_todos]
        if drops and lkeys != rkeys:
            cols = ", ".join(pystr(d) for d in drops)
            lines.append(f"{var} = {var}.drop(columns=[{cols}])  # right key(s), redundant with left")
        # Same-named deselected right keys need nothing: on= already emits one column.
        outputs["Join"] = var

    if "Left" in consumed:
        var = ctx.var("Left")
        lines.append(
            f"_lmatch{tid} = {left}.set_index({lk}).index.isin("
            f"{right}[~_rnull{tid}].set_index({rk}).index)"
        )
        lines.append(f"{var} = {left}[~_lmatch{tid}]")
        outputs["Left"] = var

    if "Right" in consumed:
        var = ctx.var("Right")
        lines.append(
            f"_rmatch{tid} = {right}.set_index({rk}).index.isin("
            f"{left}[~_lnull{tid}].set_index({lk}).index)"
        )
        lines.append(f"{var} = {right}[~_rmatch{tid}]")
        outputs["Right"] = var

    return Emission(
        lines=lines,
        outputs=outputs,
        status="partial" if todos else "ok",
        todos=todos,
    )


SPEC = ToolSpec(
    kind="join", in_ports=("Left", "Right"), out_ports=("Left", "Join", "Right"),
    translate=_translate, label="Join",
)
