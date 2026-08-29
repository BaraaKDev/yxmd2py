"""Select: drop/keep, rename, retype, reorder.

Assumed config shape:
    <OrderChanged value="True|False" />
    <SelectFields>
      <SelectField field="X" selected="True" rename="Y" type="Int64" />
      <SelectField field="*Unknown" selected="True|False" />
    </SelectFields>

*Unknown selected (the default) keeps fields the Select doesn't list; deselected, only
the listed selected fields survive. Retypes touch only fields carrying a type attr.
"""

from __future__ import annotations

from ..errors import ConfigUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, attr, cfg_findall, cfg_root, pystr

_INT = {"Byte", "Int16", "Int32", "Int64"}
_FLOAT = {"Float", "Double", "FixedDecimal"}
_STR = {"String", "V_String", "WString", "V_WString"}
_DATE = {"Date", "DateTime"}


def retype_line(df_var: str, column: str, alteryx_type: str) -> tuple[str | None, str | None]:
    """(code_line_or_None, todo_or_None) for one field's declared type."""
    target = f"{df_var}[{pystr(column)}]"
    if alteryx_type in _INT:
        return f"{target} = pd.to_numeric({target}).astype('Int64')", None
    if alteryx_type in _FLOAT:
        return f"{target} = pd.to_numeric({target})", None
    if alteryx_type in _STR:
        return f"{target} = {target}.astype('string')", None
    if alteryx_type in _DATE:
        return f"{target} = pd.to_datetime({target})", None
    if alteryx_type == "Bool":
        return (
            f"{target} = {target}.astype('boolean')  "
            "# NOTE(yxmd2py): fails on string input - map values first if needed",
            None,
        )
    return None, f"field '{column}': unhandled Alteryx type '{alteryx_type}'"


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    src = ctx.sole_input()
    out = ctx.var("Output")

    field_els = cfg_findall(node, "SelectFields/SelectField")
    if not field_els:
        raise ConfigUnsupported("Select has no <SelectFields>")

    order_el = cfg_root(node).find("OrderChanged")
    order_changed = order_el is not None and order_el.get("value") == "True"

    unknown_selected = True
    kept: list[tuple[str, str | None, str | None]] = []  # (field, rename, type)
    dropped: list[str] = []
    for el in field_els:
        name = attr(el, "field")
        selected = el.get("selected", "True") == "True"
        if name == "*Unknown":
            unknown_selected = selected
            continue
        if not selected:
            dropped.append(name)
            continue
        kept.append((name, el.get("rename"), el.get("type")))

    lines: list[str] = []
    todos: list[str] = []

    if not unknown_selected:
        cols = ", ".join(pystr(f) for f, _, _ in kept)
        lines.append(f"{out} = {src}[[{cols}]].copy()")
    elif dropped:
        cols = ", ".join(pystr(f) for f in dropped)
        lines.append(f"{out} = {src}.drop(columns=[{cols}])")
    else:
        lines.append(f"{out} = {src}.copy()")

    renames = {f: r for f, r, _ in kept if r and r != f}
    if renames:
        pairs = ", ".join(f"{pystr(k)}: {pystr(v)}" for k, v in renames.items())
        lines.append(f"{out} = {out}.rename(columns={{{pairs}}})")

    for f, r, typ in kept:
        if not typ:
            continue
        final_name = renames.get(f, f)
        code, todo = retype_line(out, final_name, typ)
        if code:
            lines.append(code)
        if todo:
            lines.append(f"# TODO(yxmd2py): {todo}")
            todos.append(f"Select (ToolID {node.tool_id}): {todo}")

    if order_changed:
        final_names = [renames.get(f, f) for f, _, _ in kept]
        listed = ", ".join(pystr(n) for n in final_names)
        lines.append(f"_order = [{listed}]")
        lines.append(f"{out} = {out}[_order + [c for c in {out}.columns if c not in _order]]")

    return Emission(
        lines=lines,
        outputs={"Output": out},
        status="partial" if todos else "ok",
        todos=todos,
    )


SPEC = ToolSpec(
    kind="select", in_ports=("Input",), out_ports=("Output",),
    translate=_translate, label="Select",
)
