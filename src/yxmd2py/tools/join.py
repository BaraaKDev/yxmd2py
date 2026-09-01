"""Join: one input pair -> three outputs (J = matched, L/R = unmatched sides).

Assumed config shape:
    <JoinInfo connection="Left"><Field field="CustId" /></JoinInfo>
    <JoinInfo connection="Right"><Field field="Customer" /></JoinInfo>
    <SelectConfiguration><Configuration outputConnection="Join">...</Configuration></SelectConfiguration>

Null-key semantics are pinned to Alteryx: a null key never matches anything, so
null-keyed rows go straight to the L/R legs. pandas merge would match NaN keys to
each other, hence the explicit non-null filtering.

The embedded Select's drops and renames are applied to the J output, with right-side
names resolved at runtime (a right column is name_Right only when it collided).
Retypes and unprefixed fields are reported as TODOs rather than guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

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


@dataclass
class _EmbeddedSelect:
    """What the Join's embedded Select does to the J output.

    Left columns keep their names in the merged frame, so left drops/renames use
    the bare name. A right column's merged name depends on whether it collided
    (name vs name_Right), so right entries are resolved at runtime.
    """

    left_drops: list[str] = field(default_factory=list)
    right_drops: list[str] = field(default_factory=list)
    left_renames: dict[str, str] = field(default_factory=dict)
    right_renames: dict[str, str] = field(default_factory=dict)
    todos: list[str] = field(default_factory=list)

    def any_work(self) -> bool:
        return bool(self.left_drops or self.right_drops or self.left_renames or self.right_renames)


def _embedded_select(node: Node, rkeys: list[str], same_keys: bool) -> _EmbeddedSelect:
    sel = _EmbeddedSelect()
    cfg = cfg_root(node).find("SelectConfiguration/Configuration")
    if cfg is None:
        return sel
    for el in cfg.findall("SelectFields/SelectField"):
        name = el.get("field", "")
        selected = el.get("selected", "True") == "True"
        rename = el.get("rename")
        if name == "*Unknown":
            if not selected:
                sel.todos.append("embedded Select deselects *Unknown - J output keeps all columns instead")
            continue
        if name.startswith("Left_"):
            side, bare = "left", name[len("Left_"):]
        elif name.startswith("Right_"):
            side, bare = "right", name[len("Right_"):]
        else:
            if not selected or (rename and rename != name):
                sel.todos.append(
                    f"embedded Select field '{name}' has no Left_/Right_ prefix - not applied"
                )
            continue
        if el.get("type"):
            sel.todos.append(f"embedded Select retypes '{name}' - retype not applied")
        if not selected:
            # Same-named keys already merged into ONE column via on=; deselecting
            # the right key is therefore already satisfied.
            if side == "right" and bare in rkeys and same_keys:
                continue
            (sel.left_drops if side == "left" else sel.right_drops).append(bare)
        elif rename and rename != bare:
            (sel.left_renames if side == "left" else sel.right_renames)[bare] = rename
    return sel


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
        sel = _embedded_select(node, rkeys, same_keys=(lkeys == rkeys))
        todos += [f"Join (ToolID {tid}): {t}" for t in sel.todos]
        if sel.any_work():
            lines.append("# apply the Join's embedded Select (drops and renames)")
        if sel.left_drops or sel.right_drops:
            parts = []
            if sel.left_drops:
                parts.append(f"[{', '.join(pystr(c) for c in sel.left_drops)}]")
            if sel.right_drops:
                rlist = ", ".join(pystr(c) for c in sel.right_drops)
                parts.append(
                    f"[c + '_Right' if c + '_Right' in {var}.columns else c for c in [{rlist}]]"
                )
            lines.append(f"_jdrops{tid} = {' + '.join(parts)}")
            # errors='ignore' because Alteryx select configs remember fields that
            # no longer exist upstream, and Alteryx itself ignores those.
            lines.append(f"{var} = {var}.drop(columns=_jdrops{tid}, errors='ignore')")
        if sel.left_renames or sel.right_renames:
            ren = f"_jrenames{tid}"
            lpairs = ", ".join(f"{pystr(k)}: {pystr(v)}" for k, v in sel.left_renames.items())
            lines.append(f"{ren} = {{{lpairs}}}")
            if sel.right_renames:
                rpairs = ", ".join(f"({pystr(k)}, {pystr(v)})" for k, v in sel.right_renames.items())
                lines.append(
                    f"{ren}.update({{(c + '_Right' if c + '_Right' in {var}.columns else c): n"
                    f" for c, n in [{rpairs}]}})"
                )
            lines.append(f"{var} = {var}.rename(columns={ren})")
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
