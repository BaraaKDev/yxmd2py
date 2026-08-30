"""Emission-level tests for the M2 tools: assertions on generated code, no execution.

These pin the code style (risk: readability decay) and the corner cases fixtures
can't reach cheaply, like the .yxdb stub.
"""

from __future__ import annotations

from pathlib import Path

from yxmd2py import codegen, parser

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
    <Fields><Field name="A" /></Fields>
    <Data><r><c>1</c></r></Data>
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


def test_yxdb_input_is_a_loud_stub(tmp_path):
    nodes = """
    <Node ToolID="1">
      <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileInput.DbFileInput" />
      <Properties><Configuration>
        <File>\\\\share\\data\\big.yxdb</File>
      </Configuration></Properties>
    </Node>
    """
    script = _generate(tmp_path, nodes, "")
    assert not script.clean
    assert ".yxdb input is not supported" in script.source
    assert "export it to CSV" in script.source
    assert script.results[0].status == "stub"


def test_filter_only_true_leg_consumed_skips_false(tmp_path):
    nodes = TEXTINPUT + """
    <Node ToolID="2">
      <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter" />
      <Properties><Configuration>
        <Expression>[A] = '1'</Expression>
        <Mode>Simple</Mode>
        <Simple>
          <Operator>=</Operator>
          <Field>A</Field>
          <Operands><Operand>1</Operand></Operands>
        </Simple>
      </Configuration></Properties>
    </Node>
    <Node ToolID="3">
      <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput" />
      <Properties><Configuration><File>x.csv</File></Configuration></Properties>
    </Node>
    """
    conns = CONN_1_TO_2 + """
    <Connection>
      <Origin ToolID="2" Connection="True" />
      <Destination ToolID="3" Connection="Input" />
    </Connection>
    """
    script = _generate(tmp_path, nodes, conns)
    assert "df_2_true = df_1[mask_2]" in script.source
    assert "df_2_false" not in script.source
    assert "fillna(False)" in script.source


def test_custom_filter_translates_through_expression_engine(tmp_path):
    nodes = TEXTINPUT + """
    <Node ToolID="2">
      <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter" />
      <Properties><Configuration>
        <Expression>[A] * 2 &gt; 10 AND Contains([A], 'x')</Expression>
        <Mode>Custom</Mode>
      </Configuration></Properties>
    </Node>
    """
    script = _generate(tmp_path, nodes, CONN_1_TO_2)
    assert script.clean
    assert "(df_1['A'] * 2 > 10) & ((df_1['A']).str.contains('x', case=False, regex=False))" in script.source


def test_untranslatable_custom_filter_degrades_with_verbatim_expression(tmp_path):
    nodes = TEXTINPUT + """
    <Node ToolID="2">
      <GuiSettings Plugin="AlteryxBasePluginsGui.Filter.Filter" />
      <Properties><Configuration>
        <Expression>REGEX_Match([A], '^x.*')</Expression>
        <Mode>Custom</Mode>
      </Configuration></Properties>
    </Node>
    """
    script = _generate(tmp_path, nodes, CONN_1_TO_2)
    assert not script.clean
    # The verbatim expression must survive into the TODO.
    assert "REGEX_Match([A], '^x.*')" in script.source


def test_unknown_tool_passthrough_keeps_pipeline_wired(tmp_path):
    nodes = TEXTINPUT + """
    <Node ToolID="2">
      <GuiSettings Plugin="Some.FutureTool.FutureTool" />
      <Properties><Configuration /></Properties>
    </Node>
    <Node ToolID="3">
      <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput" />
      <Properties><Configuration><File>x.csv</File></Configuration></Properties>
    </Node>
    """
    conns = CONN_1_TO_2 + """
    <Connection>
      <Origin ToolID="2" Connection="Output" />
      <Destination ToolID="3" Connection="Input" />
    </Connection>
    """
    script = _generate(tmp_path, nodes, conns)
    assert "df_2 = df_1.copy()" in script.source
    assert "NOT TRANSLATED" in script.source
    assert "df_2.to_csv" in script.source


def test_browse_is_skipped_silently(tmp_path):
    nodes = TEXTINPUT + """
    <Node ToolID="2">
      <GuiSettings Plugin="AlteryxGuiToolkit.Browse.Browse" />
      <Properties><Configuration /></Properties>
    </Node>
    """
    script = _generate(tmp_path, nodes, CONN_1_TO_2)
    assert "Browse" not in script.source
    assert any(r.status == "ignored" for r in script.results)
    assert script.clean


def test_path_constants_are_hoisted(tmp_path):
    nodes = """
    <Node ToolID="1">
      <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileInput.DbFileInput" />
      <Properties><Configuration>
        <File>C:\\data\\in.csv</File>
      </Configuration></Properties>
    </Node>
    <Node ToolID="2">
      <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput" />
      <Properties><Configuration>
        <File>C:\\data\\out.csv</File>
      </Configuration></Properties>
    </Node>
    """
    script = _generate(tmp_path, nodes, CONN_1_TO_2)
    assert 'INPUT_1 = r"C:\\data\\in.csv"' in script.source
    assert 'OUTPUT_1 = r"C:\\data\\out.csv"' in script.source
    assert "pd.read_csv(INPUT_1)" in script.source


def test_relative_paths_normalize_to_forward_slashes(tmp_path):
    # Alteryx writes inputs\file.csv; forward slashes run on every OS, and
    # Windows accepts them too. Absolute paths (above) stay verbatim.
    nodes = """
    <Node ToolID="1">
      <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileInput.DbFileInput" />
      <Properties><Configuration>
        <File>inputs\\nested\\in.csv</File>
      </Configuration></Properties>
    </Node>
    """
    script = _generate(tmp_path, nodes, "")
    assert 'INPUT_1 = r"inputs/nested/in.csv"' in script.source
