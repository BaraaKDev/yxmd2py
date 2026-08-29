"""Summarize: group-by plus aggregation actions.

Assumed config shape:
    <SummarizeFields>
      <SummarizeField field="Customer" action="GroupBy" rename="Customer" />
      <SummarizeField field="Amount" action="Sum" rename="Total" />
    </SummarizeFields>

Semantics pinned deliberately:
- Alteryx Count counts records including nulls -> pandas 'size', never 'count'.
- Null group keys are real groups -> groupby(dropna=False).
- Alteryx First/Last take the row's value even when null -> iloc, not pandas
  'first'/'last' (which skip nulls).
An action we don't know skips that one column (partial + TODO), not the whole tool.
"""

from __future__ import annotations

from ..errors import ConfigUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, attr, cfg_findall, pystr

# action -> (groupby agg spec, whole-frame scalar template)
_ACTIONS: dict[str, tuple[str, str]] = {
    "Sum": ("'sum'", "{col}.sum()"),
    "Count": ("'size'", "len({df})"),
    "CountDistinct": ("'nunique'", "{col}.nunique()"),
    "Min": ("'min'", "{col}.min()"),
    "Max": ("'max'", "{col}.max()"),
    "Avg": ("'mean'", "{col}.mean()"),
    "First": ("lambda s: s.iloc[0]", "{col}.iloc[0]"),
    "Last": ("lambda s: s.iloc[-1]", "{col}.iloc[-1]"),
}


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    src = ctx.sole_input()
    out = ctx.var("Output")

    field_els = cfg_findall(node, "SummarizeFields/SummarizeField")
    if not field_els:
        raise ConfigUnsupported("Summarize has no <SummarizeFields>")

    group_keys: list[tuple[str, str]] = []  # (field, rename)
    aggs: list[tuple[str, str, str]] = []  # (rename, field, agg spec for groupby mode)
    scalars: list[tuple[str, str]] = []  # (rename, scalar expression) for no-group mode
    todos: list[str] = []

    for el in field_els:
        field = attr(el, "field")
        action = attr(el, "action")
        rename = el.get("rename") or f"{action}_{field}"

        if action == "GroupBy":
            group_keys.append((field, rename))
            continue
        if action == "Concat":
            sep_el = el.find("SummarizeField_Concat_Separator")
            sep = (sep_el.get("value") if sep_el is not None else None) or ","
            spec = f"lambda s: {pystr(sep)}.join(s.astype(str))"
            aggs.append((rename, field, spec))
            scalars.append((rename, f"{pystr(sep)}.join({{col}}.astype(str))".replace("{col}", f"{src}[{pystr(field)}]")))
            continue
        if action not in _ACTIONS:
            todos.append(f"Summarize (ToolID {node.tool_id}): action '{action}' on '{field}' is not supported")
            continue
        agg_spec, scalar_tpl = _ACTIONS[action]
        aggs.append((rename, field, agg_spec))
        scalars.append((rename, scalar_tpl.format(col=f"{src}[{pystr(field)}]", df=src)))

    lines: list[str] = []
    if group_keys:
        keys = ", ".join(pystr(f) for f, _ in group_keys)
        lines.append(f"{out} = {src}.groupby([{keys}], dropna=False, as_index=False).agg(**{{")
        for rename, field, spec in aggs:
            lines.append(f"    {pystr(rename)}: ({pystr(field)}, {spec}),")
        lines.append("})")
        key_renames = {f: r for f, r in group_keys if r and r != f}
        if key_renames:
            pairs = ", ".join(f"{pystr(k)}: {pystr(v)}" for k, v in key_renames.items())
            lines.append(f"{out} = {out}.rename(columns={{{pairs}}})")
        lines.append("# NOTE(yxmd2py): dropna=False keeps null group keys, size counts null rows - both match Alteryx.")
    else:
        if not scalars:
            raise ConfigUnsupported("Summarize has no aggregation actions")
        lines.append(f"{out} = pd.DataFrame([{{")
        for rename, expr in scalars:
            lines.append(f"    {pystr(rename)}: {expr},")
        lines.append("}])")

    for todo in todos:
        lines.append(f"# TODO(yxmd2py): {todo.split(': ', 1)[1]}")

    return Emission(
        lines=lines,
        outputs={"Output": out},
        status="partial" if todos else "ok",
        todos=todos,
    )


SPEC = ToolSpec(
    kind="summarize", in_ports=("Input",), out_ports=("Output",),
    translate=_translate, label="Summarize",
)
