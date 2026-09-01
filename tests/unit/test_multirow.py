"""Multi-Row Formula: the corners the golden fixture can't reach, above all the
refusal of self-referential (running) calculations, plus the expression-language
additions it drove: [Row±N:] refs and bare field identifiers."""

from __future__ import annotations

from pathlib import Path

import pytest

from yxmd2py import codegen, parser
from yxmd2py.errors import ExprUnsupported
from yxmd2py.exprlang import translate_expression
from yxmd2py.exprlang.ast import RowContext

WRAP = """<?xml version="1.0"?>
<AlteryxDocument yxmdVer="2023.1">
  <Nodes>{nodes}</Nodes>
  <Connections>
    <Connection>
      <Origin ToolID="1" Connection="Output" />
      <Destination ToolID="2" Connection="Input" />
    </Connection>
  </Connections>
</AlteryxDocument>
"""

TEXTINPUT = """
<Node ToolID="1">
  <GuiSettings Plugin="AlteryxBasePluginsGui.TextInput.TextInput" />
  <Properties><Configuration>
    <Fields><Field name="V" /></Fields>
    <Data><r><c>1</c></r></Data>
  </Configuration></Properties>
</Node>
"""


def _mrf(config: str) -> str:
    return f"""
    <Node ToolID="2">
      <GuiSettings Plugin="AlteryxBasePluginsGui.MultiRowFormula.MultiRowFormula" />
      <Properties><Configuration>{config}</Configuration></Properties>
    </Node>
    """


def _generate(tmp_path: Path, nodes: str) -> codegen.GeneratedScript:
    p = tmp_path / "wf.yxmd"
    p.write_text(WRAP.format(nodes=nodes), encoding="utf-8")
    return codegen.generate(parser.parse_yxmd(p))


# --- expression-language additions ---------------------------------------------


def test_row_refs_emit_shift():
    ctx = RowContext()
    assert translate_expression("[Row-1:X]", "df", row_context=ctx) == "df['X'].shift(1)"
    assert translate_expression("[Row+2:X]", "df", row_context=ctx) == "df['X'].shift(-2)"


def test_row_refs_honor_grouping_and_zero_fill():
    ctx = RowContext(group_cols=("G",), zero_fill=True)
    assert (
        translate_expression("[Row-1:X]", "df", row_context=ctx)
        == "df.groupby(['G'], sort=False)['X'].shift(1, fill_value=0)"
    )


def test_row_ref_outside_multirow_is_refused():
    with pytest.raises(ExprUnsupported):
        translate_expression("[Row-1:X]", "df")


def test_bare_identifiers_are_field_refs():
    # Seen in a real Designer export: brackets are optional for simple names,
    # and case must survive (pandas columns are case-sensitive).
    assert translate_expression("Y + 1", "df") == "df['Y'] + 1"
    assert (
        translate_expression("([Row+1:Y] - Y) / ([Row+1:X] - X)", "df", row_context=RowContext())
        == "(df['Y'].shift(-1) - df['Y']) / (df['X'].shift(-1) - df['X'])"
    )


# --- tool-level behavior --------------------------------------------------------


def test_running_total_refuses_with_verbatim_expression(tmp_path):
    script = _generate(tmp_path, TEXTINPUT + _mrf("""
        <UpdateField value="False" />
        <CreateField_Name>Total</CreateField_Name>
        <OtherRows>0</OtherRows>
        <Expression>[Row-1:Total] + [V]</Expression>
        <GroupByFields />
    """))
    assert not script.clean
    assert "[Row-1:Total] + [V]" in script.source
    assert "sequential" in script.source
    assert ".shift(" not in script.source  # a plausible-but-wrong shift must NOT be emitted


def test_update_mode_writes_back_to_the_same_field(tmp_path):
    script = _generate(tmp_path, TEXTINPUT + _mrf("""
        <UpdateField value="True" />
        <UpdateField_Name>V</UpdateField_Name>
        <CreateField_Name />
        <OtherRows>NULL</OtherRows>
        <Expression>[Row-1:W]</Expression>
        <GroupByFields />
    """))
    assert script.clean
    assert "df_2['V'] = df_2['W'].shift(1)" in script.source


def test_update_mode_self_reference_refuses(tmp_path):
    script = _generate(tmp_path, TEXTINPUT + _mrf("""
        <UpdateField value="True" />
        <UpdateField_Name>V</UpdateField_Name>
        <OtherRows>NULL</OtherRows>
        <Expression>[Row-1:V] * 2</Expression>
        <GroupByFields />
    """))
    assert not script.clean
    assert "[Row-1:V] * 2" in script.source


def test_unsupported_otherrows_value_refuses(tmp_path):
    script = _generate(tmp_path, TEXTINPUT + _mrf("""
        <UpdateField value="False" />
        <CreateField_Name>P</CreateField_Name>
        <OtherRows>Nearest</OtherRows>
        <Expression>[Row-1:V]</Expression>
    """))
    assert not script.clean
    assert "'NEAREST' is not supported" in script.source
