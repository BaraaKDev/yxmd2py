"""Internal workflow model: what the parser produces and codegen consumes.

The parser guarantees only ToolID + plugin string + the raw <Configuration> element.
Everything tool-specific is read lazily by that tool's translator, so an exotic config
degrades that one node to a stub instead of failing the parse.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Port:
    tool_id: int
    name: str  # "Output", "True", "False", "Left", "Right", "Join", "#1", ...


@dataclass
class Node:
    tool_id: int
    plugin: str  # raw GuiSettings/@Plugin, verbatim (may be "")
    config: ET.Element | None  # raw <Configuration>, unparsed
    annotation: str | None = None


@dataclass
class Edge:
    src: Port  # origin tool + its output-port name
    dst: Port  # destination tool + its input-port name


@dataclass
class Workflow:
    source_path: Path
    yxmd_version: str | None
    nodes: dict[int, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def inputs_of(self, tool_id: int) -> dict[str, Port]:
        """Map of this node's input-port name -> the upstream output Port feeding it.

        Union-style tools receive many inputs on numbered ports ("#1", "#2", ...);
        a port name that repeats (some tools allow it) keeps the last edge, which is
        fine for every tool we translate and irrelevant for stubs.
        """
        return {e.dst.name: e.src for e in self.edges if e.dst.tool_id == tool_id}

    def input_edges_of(self, tool_id: int) -> list[Edge]:
        """All inbound edges, for tools where port multiplicity/order matters (Union)."""
        return [e for e in self.edges if e.dst.tool_id == tool_id]

    def consumed_ports_of(self, tool_id: int) -> set[str]:
        """Output-port names of this node that some downstream edge actually reads."""
        return {e.src.name for e in self.edges if e.src.tool_id == tool_id}
