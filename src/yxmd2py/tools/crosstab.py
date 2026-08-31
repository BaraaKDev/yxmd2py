"""Cross Tab: tall to wide - one field's values become column headers.

Assumed config shape:
    <GroupFields><Field field="Region" /></GroupFields>
    <HeaderField>Month</HeaderField>
    <DataField>Amount</DataField>
    <Methods><Method>Sum</Method></Methods>

One aggregation method is supported per tool (Alteryx allows several at once,
suffixing the column names - that variant degrades to a stub rather than
guessing the suffix scheme). Two pinned semantics: Count counts records
('size'), and cells with no contributing rows stay null rather than 0.

Header VALUES become column names verbatim; Alteryx would sanitize them
(spaces and specials to '_'), noted in the emitted code.
"""

from __future__ import annotations

from ..errors import ConfigUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, attr, cfg_findall, cfg_text, pystr

_METHODS: dict[str, str] = {
    "Sum": "'sum'",
    "Avg": "'mean'",
    "Min": "'min'",
    "Max": "'max'",
    "Count": "'size'",
    "First": "lambda s: s.iloc[0]",
    "Last": "lambda s: s.iloc[-1]",
    "Concat": "lambda s: ','.join(s.astype(str))",
}


def _translate(node: Node, ctx: TranslationContext) -> Emission:
    src = ctx.sole_input()
    out = ctx.var("Output")

    groups = [attr(el, "field") for el in cfg_findall(node, "GroupFields/Field")]
    header = cfg_text(node, "HeaderField").strip()
    data = cfg_text(node, "DataField").strip()
    methods = [el.text.strip() for el in cfg_findall(node, "Methods/Method") if el.text and el.text.strip()]
    if not methods:
        raise ConfigUnsupported("Cross Tab has no aggregation <Method>")
    if len(methods) > 1:
        raise ConfigUnsupported(
            f"Cross Tab with multiple methods ({', '.join(methods)}) is not supported - split into one tool per method"
        )
    if methods[0] not in _METHODS:
        raise ConfigUnsupported(f"Cross Tab method '{methods[0]}' is not supported")
    if not groups:
        raise ConfigUnsupported("Cross Tab without group fields is not supported")

    group_list = ", ".join(pystr(g) for g in groups)
    lines = [
        f"{out} = {src}.pivot_table(index=[{group_list}], columns={pystr(header)},",
        f"    values={pystr(data)}, aggfunc={_METHODS[methods[0]]}).reset_index()",
        f"{out}.columns.name = None",
        "# NOTE(yxmd2py): empty cells stay null (Alteryx: empty), and header values are",
        "# used as column names verbatim - Alteryx would rewrite specials/spaces to '_'.",
    ]
    return Emission(lines=lines, outputs={"Output": out})


SPEC = ToolSpec(
    kind="crosstab", in_ports=("Input",), out_ports=("Output",),
    translate=_translate, label="Cross Tab",
)
