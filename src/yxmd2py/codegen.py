"""Turn a parsed Workflow into a standalone pandas script.

Order: Kahn topological sort, ties broken by ascending ToolID so output is
deterministic. Only ports actually consumed downstream are materialized. Every I/O
path is hoisted into a constants block at the top of the script — real workflows
point at network drives that whoever runs the script must repoint first.
"""

from __future__ import annotations

import datetime as _dt
import heapq
from dataclasses import dataclass, field

from . import __version__, registry
from . import tools as _tools  # noqa: F401  (import side effect: registers every tool)
from .errors import ConfigUnsupported, ParseError
from .exprlang import translate_expression
from .model import Node, Workflow
from .spec import Emission, TranslationContext, stub_emission

# Port-name -> variable suffix for multi-output tools.
_PORT_SUFFIX = {
    "true": "true", "false": "false",
    "join": "j", "left": "l", "right": "r",
    "unique": "uniq", "dup": "dup",
}


@dataclass
class NodeResult:
    tool_id: int
    label: str
    status: str  # "ok" | "partial" | "stub" | "ignored"
    todos: list[str] = field(default_factory=list)


@dataclass
class GeneratedScript:
    source: str
    results: list[NodeResult]

    @property
    def todo_count(self) -> int:
        return sum(len(r.todos) for r in self.results)

    @property
    def clean(self) -> bool:
        return all(r.status in ("ok", "ignored", "disabled") for r in self.results)


def topo_order(wf: Workflow) -> list[int]:
    indegree = {tid: 0 for tid in wf.nodes}
    downstream: dict[int, list[int]] = {tid: [] for tid in wf.nodes}
    seen_pairs: set[tuple[int, int]] = set()
    for e in wf.edges:
        pair = (e.src.tool_id, e.dst.tool_id)
        if pair in seen_pairs:
            continue  # parallel edges (Join L+R from one origin) count once
        seen_pairs.add(pair)
        indegree[e.dst.tool_id] += 1
        downstream[e.src.tool_id].append(e.dst.tool_id)

    ready = [tid for tid, deg in indegree.items() if deg == 0]
    heapq.heapify(ready)
    order: list[int] = []
    while ready:
        tid = heapq.heappop(ready)
        order.append(tid)
        for nxt in downstream[tid]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(ready, nxt)
    if len(order) != len(wf.nodes):
        cyclic = sorted(set(wf.nodes) - set(order))
        raise ParseError(f"workflow contains a cycle involving tools {cyclic}")
    return order


def _make_var(node: Node, out_ports: tuple[str, ...]):
    def var(port: str) -> str:
        if len(out_ports) <= 1:
            return f"df_{node.tool_id}"
        suffix = _PORT_SUFFIX.get(port.lower(), port.lower().replace("#", "n"))
        return f"df_{node.tool_id}_{suffix}"

    return var


def generate(wf: Workflow) -> GeneratedScript:
    order = topo_order(wf)

    path_consts: list[tuple[str, str]] = []  # (const_name, raw_path)
    const_counts: dict[str, int] = {}

    def add_path_const(kind: str, path: str) -> str:
        # Alteryx paths are Windows-style. A RELATIVE one gets forward slashes so
        # the script runs on any OS (Windows accepts them too). An ABSOLUTE one
        # (C:\... or \\share\...) stays verbatim - it is machine-specific and the
        # user must repoint it regardless, so rewriting separators only obscures
        # where it came from.
        is_absolute = len(path) >= 2 and (path[1] == ":" or path.startswith("\\\\"))
        if not is_absolute:
            path = path.replace("\\", "/")
        const_counts[kind] = const_counts.get(kind, 0) + 1
        name = f"{kind.upper()}_{const_counts[kind]}"
        path_consts.append((name, path))
        return name

    emissions: dict[int, Emission] = {}
    results: list[NodeResult] = []
    blocks: list[list[str]] = []
    ignored_count = 0

    for tid in order:
        node = wf.nodes[tid]
        spec = registry.resolve(node.plugin)

        if node.disabled:
            # Alteryx would not run this tool (disabled Tool Container), so no code.
            results.append(NodeResult(tid, spec.display, "disabled"))
            continue

        if spec.kind == "ignore":
            ignored_count += 1
            results.append(NodeResult(tid, spec.display, "ignored"))
            continue

        # Wire inputs: upstream emission's variable for the port feeding each edge.
        inputs: dict[str, str] = {}
        ordered_inputs: list[tuple[str, str]] = []
        for e in wf.input_edges_of(tid):
            up = emissions.get(e.src.tool_id)
            if up is None:
                continue  # upstream was ignored (Browse never feeds anything anyway)
            var_name = up.outputs.get(e.src.name)
            if var_name is None and up.outputs:
                # Unknown port name on a stubbed tool: any output var will do.
                var_name = next(iter(up.outputs.values()))
            if var_name is None:
                continue
            inputs[e.dst.name] = var_name
            ordered_inputs.append((e.dst.name, var_name))
        # Union wires arrive as "#1", "#2", ...; sort numerically where possible.
        ordered_inputs.sort(key=lambda p: (len(p[0]), p[0]))

        ctx = TranslationContext(
            inputs=inputs,
            ordered_inputs=ordered_inputs,
            consumed=wf.consumed_ports_of(tid),
            var=_make_var(node, spec.out_ports),
            source_dir=wf.source_path.parent,
            add_path_const=add_path_const,
            translate_expression=translate_expression,
        )

        try:
            if spec.kind == "stub" and node.macro:
                # Not an unknown tool - a macro reference. Say what it is and
                # where the logic actually lives, instead of the generic text.
                emission = stub_emission(
                    node, ctx,
                    reason=(
                        f"macro reference ({node.macro}) - a macro's logic lives in "
                        "its own canvas; run yxmd2py on that file and splice the result in here"
                    ),
                    display="Macro",
                )
            else:
                emission = spec.translate(node, ctx)
        except ConfigUnsupported as exc:
            emission = stub_emission(node, ctx, reason=str(exc), display=spec.display)

        display = "Macro" if (spec.kind == "stub" and node.macro) else spec.display
        emissions[tid] = emission
        results.append(NodeResult(tid, display, emission.status, list(emission.todos)))

        header = f"# {'=' * 12} Tool {tid}: {display} {'=' * 12}"
        block = [header]
        if node.annotation:
            for ann_line in node.annotation.splitlines():
                block.append(f"# Annotation: {ann_line}")
        block.extend(emission.lines)
        blocks.append(block)

    body = "\n\n".join("\n".join(b) for b in blocks)

    uses_numpy = "np." in body
    uses_excel = "read_excel" in body or "to_excel" in body

    deps = ['"pandas"']
    if uses_numpy:
        deps.append('"numpy"')
    if uses_excel:
        deps.append('"openpyxl"')

    lines: list[str] = [
        "# /// script",
        '# requires-python = ">=3.12"',
        f"# dependencies = [{', '.join(deps)}]",
        "# ///",
        '"""Translated from an Alteryx workflow by yxmd2py - review before relying on it.',
        "",
        f"Source:     {wf.source_path.name}",
        f"Translated: {_dt.date.today().isoformat()} (yxmd2py {__version__}, yxmdVer {wf.yxmd_version or '?'})",
        "Run with:   uv run <this file>",
        '"""',
        "",
        "import pandas as pd",
    ]
    if uses_numpy:
        lines.append("import numpy as np")

    if path_consts:
        lines += ["", "# --- File paths (edit here) ---"]
        for name, raw in path_consts:
            lines.append(f"{name} = {path_literal(raw)}")

    lines.append("")
    lines.append(body)
    lines.append("")

    return GeneratedScript(source="\n".join(lines), results=results)


def path_literal(value: str) -> str:
    """A complete python string literal for a file path.

    Raw strings keep Windows backslashes readable, but a raw string cannot end in
    a backslash or contain a double quote — those fall back to a normal repr.
    """
    if value.endswith("\\") or '"' in value:
        return repr(value)
    return f'r"{value}"'
