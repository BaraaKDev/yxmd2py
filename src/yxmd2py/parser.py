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


def _collect_nodes(parent_el: ET.Element, wf: Workflow, disabled: bool) -> None:
    """Walk <Node> children, recursing into Tool Containers via <ChildNodes>.

    A container's <Configuration><Disabled value="True"/> disables its entire
    subtree — Alteryx would not run those tools, so translating them would emit
    code the workflow never executes. The disabled flag inherits downward: an
    enabled container inside a disabled one is still dead.
    """
    for node_el in parent_el.findall("Node"):
        tool_id_raw = node_el.get("ToolID")
        try:
            tool_id = int(tool_id_raw) if tool_id_raw is not None else None
        except ValueError:
            tool_id = None

        gui = node_el.find("GuiSettings")
        plugin = (gui.get("Plugin") or "") if gui is not None else ""
        config = node_el.find("Properties/Configuration")

        node_disabled = disabled
        if not node_disabled and config is not None:
            dis_el = config.find("Disabled")
            if dis_el is not None and dis_el.get("value") == "True":
                node_disabled = True

        if tool_id is not None:
            # AnnotationText is the user-typed note; DefaultAnnotationText is
            # Designer's auto-generated label. Prefer the former.
            annotation = None
            for tag in ("AnnotationText", "DefaultAnnotationText"):
                ann_el = node_el.find(f"Properties/Annotation/{tag}")
                if ann_el is not None and ann_el.text and ann_el.text.strip():
                    annotation = ann_el.text.strip()
                    break

            # A macro reference: EngineSettings carries the .yxmc path instead of
            # an engine DLL. The node's real logic lives in that file.
            engine_el = node_el.find("EngineSettings")
            macro = engine_el.get("Macro") if engine_el is not None else None

            wf.nodes[tool_id] = Node(
                tool_id=tool_id, plugin=plugin, config=config,
                annotation=annotation, disabled=node_disabled,
                macro=(macro or None),
            )

        child_el = node_el.find("ChildNodes")
        if child_el is not None:
            _collect_nodes(child_el, wf, disabled=node_disabled)


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
    _collect_nodes(nodes_el, wf, disabled=False)

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
