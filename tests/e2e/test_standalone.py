"""Prove the PEP 723 claim: a generated script runs under a bare `uv run`,
outside the project venv, resolving its own dependencies from the inline block."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from yxmd2py import codegen, parser

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.slow
def test_kitchen_sink_runs_standalone_via_uv(tmp_path):
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv not on PATH")
    work = tmp_path / "kitchen_sink"
    shutil.copytree(FIXTURES / "kitchen_sink", work)
    wf = parser.parse_yxmd(work / "workflow.yxmd")
    script = codegen.generate(wf)
    script_path = work / "generated.py"
    script_path.write_text(script.source, encoding="utf-8")

    result = subprocess.run(
        [uv, "run", "--no-project", str(script_path)],
        cwd=work, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stderr
    got = (work / "final.csv").read_text(encoding="utf-8")
    expected = (work / "expected" / "final.csv").read_text(encoding="utf-8")
    assert got.replace("\r\n", "\n") == expected.replace("\r\n", "\n")
