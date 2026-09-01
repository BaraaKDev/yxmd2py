"""Regressions from the first genuine Designer exports (found in public GitHub
repos - an Alteryx-authored guide, a DataKind analyst workflow, the CReW macro
pack). The files themselves stay out of the repo (they carry their own licenses);
each finding is encoded here as a synthetic regression instead.
"""

from __future__ import annotations

from pathlib import Path

from yxmd2py import codegen, parser, registry

WRAP = """<?xml version="1.0"?>
<AlteryxDocument yxmdVer="2023.1">
  <Nodes>{nodes}</Nodes>
  <Connections>{conns}</Connections>
</AlteryxDocument>
"""

TEXTINPUT = """
<Node ToolID="1">
  <GuiSettings Plugin="AlteryxBasePluginsGui.TextInput.TextInput" />
  <Properties><Configuration>
    <Fields><Field name="A" /><Field name="B" /></Fields>
    <Data><r><c>x</c><c>1</c></r></Data>
  </Configuration></Properties>
</Node>
"""

CONN_1_TO_2 = """
<Connection>
  <Origin ToolID="1" Connection="Output" />
  <Destination ToolID="2" Connection="Input" />
</Connection>
"""


def _generate(tmp_path: Path, nodes: str, conns: str) -> codegen.GeneratedScript:
    p = tmp_path / "wf.yxmd"
    p.write_text(WRAP.format(nodes=nodes, conns=conns), encoding="utf-8")
    return codegen.generate(parser.parse_yxmd(p))


def test_crosstab_attribute_form_is_the_real_designer_shape(tmp_path):
    # DataKind export: <HeaderField field=.../>, <DataField field=.../>,
    # <Method method="Sum"/> - attributes, where the synthetic fixtures used text.
    nodes = TEXTINPUT + """
    <Node ToolID="2">
      <GuiSettings Plugin="AlteryxBasePluginsGui.CrossTab.CrossTab" />
      <Properties><Configuration>
        <GroupFields><Field field="A" /></GroupFields>
        <HeaderField field="H" />
        <DataField field="V" />
        <Methods><Method method="Sum" /></Methods>
      </Configuration></Properties>
    </Node>
    """
    script = _generate(tmp_path, nodes, CONN_1_TO_2)
    assert script.clean
    assert "pivot_table(index=['A'], columns='H'" in script.source


def test_interface_tools_are_noops_and_their_arrows_are_not_data_inputs(tmp_path):
    # CReW macros: Action tools point configuration arrows at data tools; those
    # arrows must not count as data inputs (a Sort was refusing "2 inputs").
    nodes = TEXTINPUT + """
    <Node ToolID="2">
      <GuiSettings Plugin="AlteryxBasePluginsGui.Sort.Sort" />
      <Properties><Configuration>
        <SortInfo><Field field="A" order="Ascending" /></SortInfo>
      </Configuration></Properties>
    </Node>
    <Node ToolID="9">
      <GuiSettings Plugin="AlteryxGuiToolkit.Action.Action" />
      <Properties><Configuration /></Properties>
    </Node>
    <Node ToolID="10">
      <GuiSettings Plugin="AlteryxGuiToolkit.TextBox.TextBox" />
      <Properties><Configuration /></Properties>
    </Node>
    """
    conns = CONN_1_TO_2 + """
    <Connection>
      <Origin ToolID="9" Connection="Output" />
      <Destination ToolID="2" Connection="Action" />
    </Connection>
    """
    script = _generate(tmp_path, nodes, conns)
    assert script.clean
    assert "sort_values" in script.source
    statuses = {r.tool_id: r.status for r in script.results}
    assert statuses[9] == "ignored" and statuses[10] == "ignored"


def test_guitoolkit_prefix_rule_covers_the_family():
    for plugin in (
        "AlteryxGuiToolkit.HtmlBox.HtmlBox",
        "AlteryxGuiToolkit.Questions.Tab.Tab",
        "AlteryxGuiToolkit.Questions.DropDownListBox.ListBox",
        "AlteryxGuiToolkit.Error.Error",
        "AlteryxGuiToolkit.ToolContainer.ToolContainer",
        "AlteryxGuiToolkit.Browse.Browse",
    ):
        assert registry.resolve(plugin).kind == "ignore", plugin


def test_join_embedded_select_applies_drops_and_renames(tmp_path):
    # DataKind deselects arbitrary Left_/Right_ fields; CReW renames Right_ ones.
    nodes = TEXTINPUT + TEXTINPUT.replace('ToolID="1"', 'ToolID="5"') + """
    <Node ToolID="2">
      <GuiSettings Plugin="AlteryxBasePluginsGui.Join.Join" />
      <Properties><Configuration>
        <JoinInfo connection="Left"><Field field="A" /></JoinInfo>
        <JoinInfo connection="Right"><Field field="B" /></JoinInfo>
        <SelectConfiguration>
          <Configuration outputConnection="Join">
            <SelectFields>
              <SelectField field="Left_B" selected="False" />
              <SelectField field="Right_A" selected="True" rename="A_from_right" />
              <SelectField field="*Unknown" selected="True" />
            </SelectFields>
          </Configuration>
        </SelectConfiguration>
      </Configuration></Properties>
    </Node>
    """
    conns = """
    <Connection>
      <Origin ToolID="1" Connection="Output" />
      <Destination ToolID="2" Connection="Left" />
    </Connection>
    <Connection>
      <Origin ToolID="5" Connection="Output" />
      <Destination ToolID="2" Connection="Right" />
    </Connection>
    """
    script = _generate(tmp_path, nodes, conns)
    assert script.clean, [t for r in script.results for t in r.todos]
    src = script.source
    assert "_jdrops2 = ['B']" in src
    assert "errors='ignore'" in src  # select configs remember stale fields
    assert "'A_from_right'" in src


def test_leading_zero_filter_operand_compiles(tmp_path):
    # DataKind filtered on a FIPS code: <Operand>095</Operand>. Emitted verbatim
    # that is a SyntaxError (leading-zero int literal); it must normalize to 95.
    nodes = TEXTINPUT + """
    <Node ToolID="2">
      <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter" />
      <Properties><Configuration>
        <Expression>[B] = 095</Expression>
        <Mode>Simple</Mode>
        <Simple>
          <Operator>=</Operator>
          <Field>B</Field>
          <Operands><Operand>095</Operand></Operands>
        </Simple>
      </Configuration></Properties>
    </Node>
    """
    script = _generate(tmp_path, nodes, CONN_1_TO_2)
    assert "== 95" in script.source
    compile(script.source, "<test>", "exec")  # generate() already guards; belt and braces
