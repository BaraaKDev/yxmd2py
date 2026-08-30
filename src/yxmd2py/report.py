"""Per-file summary printing and the exit-code decision.

Exit codes: 0 = fully clean; 1 = output written but stubs/TODOs remain (CI can gate
on it while a human still gets usable output); 2 = hard failure (unparseable file,
bad arguments). --check uses the same 0/1 distinction for "gaps found".
"""

from __future__ import annotations

from collections import Counter

from .codegen import GeneratedScript, NodeResult


def summarize(script: GeneratedScript) -> str:
    by_status = Counter(r.status for r in script.results)
    parts = [f"translated {by_status.get('ok', 0)} tools"]
    if by_status.get("partial"):
        parts.append(f"{by_status['partial']} with TODOs")
    if by_status.get("stub"):
        parts.append(f"stubbed {by_status['stub']}")
    if by_status.get("ignored"):
        parts.append(f"skipped {by_status['ignored']} data no-op(s)")
    if by_status.get("disabled"):
        parts.append(f"skipped {by_status['disabled']} disabled tool(s)")
    lines = [", ".join(parts)]
    for r in script.results:
        for todo in r.todos:
            lines.append(f"  TODO  {todo}")
    return "\n".join(lines)


def coverage_table(results: list[NodeResult]) -> str:
    """--check output: one row per tool, worst statuses first."""
    rank = {"stub": 0, "partial": 1, "ignored": 2, "disabled": 2, "ok": 3}
    rows = sorted(results, key=lambda r: (rank.get(r.status, 0), r.tool_id))
    width = max((len(r.label) for r in rows), default=4)
    out = [f"  {'ToolID':>6}  {'Tool':<{width}}  Status"]
    for r in rows:
        out.append(f"  {r.tool_id:>6}  {r.label:<{width}}  {r.status}")
    return "\n".join(out)


def exit_code(scripts: list[GeneratedScript]) -> int:
    return 0 if all(s.clean for s in scripts) else 1
