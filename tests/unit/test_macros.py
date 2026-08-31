"""Macro references: recognized as macros, stubbed with a message that says where
the logic actually lives - never the generic unknown-tool text."""

from __future__ import annotations

from pathlib import Path

from yxmd2py import codegen, parser

WF = """<?xml version="1.0"?>
<AlteryxDocument yxmdVer="2023.1">
  <Nodes>
    <Node ToolID="1">
      <GuiSettings Plugin="AlteryxBasePluginsGui.TextInput.TextInput" />
      <Properties><Configuration>
        <Fields><Field name="A" /></Fields>
        <Data><r><c>1</c></r></Data>
      </Configuration></Properties>
    </Node>
    <Node ToolID="2">
      <GuiSettings Plugin="LookupMacro" />
      <Properties><Configuration>
        <Value name="Threshold">5</Value>
      </Configuration></Properties>
      <EngineSettings Macro="macros\\LookupMacro.yxmc" />
    </Node>
    <Node ToolID="3">
      <GuiSettings Plugin="AlteryxBasePluginsGui.DbFileOutput.DbFileOutput" />
      <Properties><Configuration><File>x.csv</File></Configuration></Properties>
    </Node>
  </Nodes>
  <Connections>
    <Connection>
      <Origin ToolID="1" Connection="Output" />
      <Destination ToolID="2" Connection="Input" />
    </Connection>
    <Connection>
      <Origin ToolID="2" Connection="Output" />
      <Destination ToolID="3" Connection="Input" />
    </Connection>
  </Connections>
</AlteryxDocument>
"""


def test_macro_reference_stubs_with_its_own_message(tmp_path):
    p = tmp_path / "wf.yxmd"
    p.write_text(WF, encoding="utf-8")
    script = codegen.generate(parser.parse_yxmd(p))
    assert not script.clean
    src = script.source
    assert "macro reference (macros\\LookupMacro.yxmc)" in src
    assert "run yxmd2py on that file" in src
    assert "unsupported tool" not in src  # the generic text must not appear
    statuses = {r.tool_id: (r.label, r.status) for r in script.results}
    assert statuses[2] == ("Macro", "stub")
    # Passthrough keeps the pipeline wired to the output.
    assert "df_2 = df_1.copy()" in src


def test_engine_dll_nodes_are_not_macros(tmp_path):
    text = WF.replace(
        '<EngineSettings Macro="macros\\LookupMacro.yxmc" />',
        '<EngineSettings EngineDll="SomeEngine.dll" EngineDllEntryPoint="X" />',
    )
    p = tmp_path / "wf.yxmd"
    p.write_text(text, encoding="utf-8")
    script = codegen.generate(parser.parse_yxmd(p))
    labels = {r.tool_id: r.label for r in script.results}
    assert labels[2] == "Unknown tool"
