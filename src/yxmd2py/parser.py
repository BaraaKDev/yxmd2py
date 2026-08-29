"""Parse a .yxmd file into the internal Workflow model.

Deliberately shallow: ToolID, plugin string, raw config element, annotation, edges.
Tool containers nest their children under <ChildNodes>, so nodes are collected by
iterating every <Node> descendant of <Nodes> rather than only direct children.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .errors import ParseError
from .model import Edge, Node, Port, Workflow


def parse_yxmd(path: Path) -> Workflow:
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise ParseError(f"{path}: not well-formed XML ({exc})") from exc
    except OSError as exc:
        raise ParseError(f"{path}: cannot read ({exc})") from exc

    root = tree.getroot()
    nodes_el = root.find("Nodes")
    if nodes_el is None:
        raise ParseError(f"{path}: no <Nodes> element — is this a .yxmd workflow?")

    wf = Workflow(source_path=path, yxmd_version=root.get("yxmdVer"))

    for node_el in nodes_el.iter("Node"):
        tool_id_raw = node_el.get("ToolID")
        if tool_id_raw is None:
            continue  # a Node without a ToolID cannot be wired; skip defensively
        try:
            tool_id = int(tool_id_raw)
        except ValueError:
            continue

        gui = node_el.find("GuiSettings")
        plugin = (gui.get("Plugin") or "") if gui is not None else ""

        config = node_el.find("Properties/Configuration")

        # AnnotationText is the user-typed note; DefaultAnnotationText is Designer's
        # auto-generated label. Prefer the former, fall back to the latter.
        annotation = None
        for tag in ("AnnotationText", "DefaultAnnotationText"):
            ann_el = node_el.find(f"Properties/Annotation/{tag}")
            if ann_el is not None and ann_el.text and ann_el.text.strip():
                annotation = ann_el.text.strip()
                break

        wf.nodes[tool_id] = Node(
            tool_id=tool_id, plugin=plugin, config=config, annotation=annotation
        )

    conns_el = root.find("Connections")
    if conns_el is not None:
        for conn_el in conns_el.iter("Connection"):
            origin = conn_el.find("Origin")
            dest = conn_el.find("Destination")
            if origin is None or dest is None:
                continue
            try:
                src_id = int(origin.get("ToolID", ""))
                dst_id = int(dest.get("ToolID", ""))
            except ValueError:
                continue
            # Edges to/from tools that don't exist (corrupt or hand-edited files)
            # are dropped rather than crashing downstream lookups.
            if src_id not in wf.nodes or dst_id not in wf.nodes:
                continue
            wf.edges.append(
                Edge(
                    src=Port(src_id, origin.get("Connection") or "Output"),
                    dst=Port(dst_id, dest.get("Connection") or "Input"),
                )
            )

    return wf
