"""Parser + registry + topo unit tests, driven by inline XML strings."""

from __future__ import annotations

from pathlib import Path

import pytest

from yxmd2py import registry
from yxmd2py.codegen import topo_order
from yxmd2py.errors import ParseError
from yxmd2py.parser import parse_yxmd

MINIMAL = """<?xml version="1.0"?>
<AlteryxDocument yxmdVer="2023.1">
  <Nodes>
    <Node ToolID="1">
      <GuiSettings Plugin="AlteryxBasePluginsGui.TextInput.TextInput" />
      <Properties><Configuration /></Properties>
    </Node>
    <Node ToolID="2">
      <GuiSettings Plugin="AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect" />
      <Properties><Configuration /></Properties>
    </Node>
  </Nodes>
  <Connections>
    <Connection>
      <Origin ToolID="1" Connection="Output" />
      <Destination ToolID="2" Connection="Input" />
    </Connection>
  </Connections>
</AlteryxDocument>
"""


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "wf.yxmd"
    p.write_text(text, encoding="utf-8")
    return p


def test_parse_minimal(tmp_path):
    wf = parse_yxmd(_write(tmp_path, MINIMAL))
    assert wf.yxmd_version == "2023.1"
    assert set(wf.nodes) == {1, 2}
    assert wf.nodes[1].plugin.endswith("TextInput")
    assert len(wf.edges) == 1
    assert wf.edges[0].src.name == "Output"
    assert wf.inputs_of(2)["Input"].tool_id == 1


def test_parse_rejects_non_workflow_xml(tmp_path):
    with pytest.raises(ParseError):
        parse_yxmd(_write(tmp_path, "<html><body>nope</body></html>"))


def test_parse_rejects_broken_xml(tmp_path):
    with pytest.raises(ParseError):
        parse_yxmd(_write(tmp_path, "<AlteryxDocument><Nodes>"))


def test_edge_to_missing_tool_is_dropped(tmp_path):
    text = MINIMAL.replace('Destination ToolID="2"', 'Destination ToolID="99"')
    wf = parse_yxmd(_write(tmp_path, text))
    assert wf.edges == []


def test_container_children_are_found(tmp_path):
    text = MINIMAL.replace(
        "<Nodes>",
        '<Nodes><Node ToolID="10"><GuiSettings Plugin="AlteryxGuiToolkit.ToolContainer.ToolContainer" />'
        "<Properties><Configuration /></Properties><ChildNodes>",
    ).replace("</Nodes>", "</ChildNodes></Node></Nodes>")
    wf = parse_yxmd(_write(tmp_path, text))
    assert {1, 2, 10} <= set(wf.nodes)


def test_topo_order_and_cycle(tmp_path):
    wf = parse_yxmd(_write(tmp_path, MINIMAL))
    assert topo_order(wf) == [1, 2]
    # Manufacture a cycle 2 -> 1.
    from yxmd2py.model import Edge, Port

    wf.edges.append(Edge(src=Port(2, "Output"), dst=Port(1, "Input")))
    with pytest.raises(ParseError):
        topo_order(wf)


def test_registry_token_and_aliases():
    assert registry.plugin_token("AlteryxBasePluginsGui.AlteryxSelect.AlteryxSelect") == "AlteryxSelect"
    assert registry.plugin_token("Weird") == "Weird"
    assert registry.resolve("AlteryxGuiToolkit.Browse.Browse").kind == "ignore"
    assert registry.resolve("Whatever.BrowseV2.BrowseV2").kind == "ignore"
    assert registry.resolve("No.SuchTool.Ever").kind == "stub"
    assert registry.resolve("").kind == "stub"
