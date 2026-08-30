"""Disabled Tool Containers: Alteryx does not run their contents, so neither do we.

The disabled flag inherits downward - an enabled container nested inside a
disabled one is still dead. Enabled containers are pure organization: children
translate normally and the container itself is a counted no-op, not a stub.
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

SORT_2 = """
<Node ToolID="2">
  <GuiSettings Plugin="AlteryxBasePluginsGui.Sort.Sort" />
  <Properties><Configuration>
    <SortInfo><Field field="A" order="Ascending" /></SortInfo>
  </Configuration></Properties>
</Node>
"""


def _container(tool_id: int, disabled: bool, children: str) -> str:
    return f"""
<Node ToolID="{tool_id}">
  <GuiSettings Plugin="AlteryxGuiToolkit.ToolContainer.ToolContainer" />
  <Properties><Configuration>
    <Caption>box</Caption>
    <Disabled value="{disabled}" />
  </Configuration></Properties>
  <ChildNodes>{children}</ChildNodes>
</Node>
"""


CONN_1_TO_2 = """
<Connection>
  <Origin ToolID="1" Connection="Output" />
  <Destination ToolID="2" Connection="Input" />
</Connection>
"""


def _generate(tmp_path: Path, nodes: str, conns: str = "") -> codegen.GeneratedScript:
    p = tmp_path / "wf.yxmd"
    p.write_text(WRAP.format(nodes=nodes, conns=conns), encoding="utf-8")
    return codegen.generate(parser.parse_yxmd(p))


def test_enabled_container_children_translate_and_container_is_a_noop(tmp_path):
    script = _generate(tmp_path, TEXTINPUT + _container(10, False, SORT_2), CONN_1_TO_2)
    assert script.clean
    assert "df_2 = df_1.sort_values" in script.source
    statuses = {r.tool_id: r.status for r in script.results}
    assert statuses[10] == "ignored"  # the container box itself, never a stub
    assert statuses[2] == "ok"


def test_disabled_container_children_emit_no_code(tmp_path):
    script = _generate(tmp_path, TEXTINPUT + _container(10, True, SORT_2), CONN_1_TO_2)
    assert script.clean  # disabled is expected, not a defect
    assert "sort_values" not in script.source
    statuses = {r.tool_id: r.status for r in script.results}
    assert statuses[2] == "disabled"


def test_disabled_inherits_through_nested_enabled_container(tmp_path):
    inner = _container(11, False, SORT_2)
    script = _generate(tmp_path, TEXTINPUT + _container(10, True, inner), CONN_1_TO_2)
    assert "sort_values" not in script.source
    statuses = {r.tool_id: r.status for r in script.results}
    assert statuses[2] == "disabled"


def test_consumer_of_a_disabled_tool_degrades_honestly(tmp_path):
    out = """
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
    script = _generate(tmp_path, TEXTINPUT + _container(10, True, SORT_2) + out, conns)
    # The output tool's only input is dead; it must stub loudly, not write junk.
    assert not script.clean
    statuses = {r.tool_id: r.status for r in script.results}
    assert statuses[3] == "stub"
