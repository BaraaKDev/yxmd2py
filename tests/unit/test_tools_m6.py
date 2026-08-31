"""Emission and refusal tests for the M6 tools (RecordID, Text To Columns,
Transpose, Cross Tab) - the corners the reshape_tools golden fixture can't reach."""

from __future__ import annotations

from pathlib import Path

from yxmd2py import codegen, parser

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
    <Fields><Field name="A" /></Fields>
    <Data><r><c>x</c></r></Data>
  </Configuration></Properties>
</Node>
"""


def _generate(tmp_path: Path, tool_xml: str) -> codegen.GeneratedScript:
    p = tmp_path / "wf.yxmd"
    p.write_text(WRAP.format(nodes=TEXTINPUT + tool_xml), encoding="utf-8")
    return codegen.generate(parser.parse_yxmd(p))


def _tool(plugin: str, config: str) -> str:
    return f"""
    <Node ToolID="2">
      <GuiSettings Plugin="AlteryxBasePluginsGui.{plugin}.{plugin}" />
      <Properties><Configuration>{config}</Configuration></Properties>
    </Node>
    """


def test_recordid_at_end_assigns_instead_of_inserting(tmp_path):
    script = _generate(tmp_path, _tool("RecordID", "<FieldName>N</FieldName><StartValue>100</StartValue><Position>1</Position>"))
    assert script.clean
    assert "df_2['N'] = range(100, 100 + len(df_2))" in script.source
    assert ".insert(" not in script.source


def test_texttocolumns_multiple_delimiter_chars_become_a_class(tmp_path):
    cfg = '<Field>A</Field><Delimeters value=",;" /><NumFields value="2" /><RootName>P</RootName>'
    script = _generate(tmp_path, _tool("TextToColumns", cfg))
    assert script.clean
    assert "str.split('[,;]', regex=True, n=1, expand=True)" in script.source


def test_crosstab_multiple_methods_refuses(tmp_path):
    cfg = (
        "<GroupFields><Field field='A' /></GroupFields>"
        "<HeaderField>H</HeaderField><DataField>V</DataField>"
        "<Methods><Method>Sum</Method><Method>Avg</Method></Methods>"
    )
    script = _generate(tmp_path, _tool("CrossTab", cfg))
    assert not script.clean
    assert "split into one tool per method" in script.source


def test_transpose_with_no_data_fields_refuses(tmp_path):
    cfg = "<KeyFields><Field field='A' /></KeyFields><DataFields><Field field='*Unknown' selected='False' /></DataFields>"
    script = _generate(tmp_path, _tool("Transpose", cfg))
    assert not script.clean
    assert "no selected data fields" in script.source
