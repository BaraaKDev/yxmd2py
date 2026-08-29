"""Shared harness: translate a fixture, execute the generated script, compare outputs.

Golden convention: tests/fixtures/<name>/ holds workflow.yxmd, optional inputs/, and
expected/. The fixture dir is copied to tmp, the script runs there (in-process exec,
cwd = the copy), then every file in expected/ is compared against the same-named file
the script produced in the copy's root.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import pandas.testing as pdt
import pytest

from yxmd2py import codegen, parser

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_names() -> list[str]:
    return sorted(p.name for p in FIXTURES.iterdir() if (p / "workflow.yxmd").exists())


@pytest.fixture
def run_fixture(tmp_path, monkeypatch):
    """Translate + execute a named fixture; returns (script, workdir)."""

    def _run(name: str):
        src = FIXTURES / name
        work = tmp_path / name
        shutil.copytree(src, work)
        wf = parser.parse_yxmd(work / "workflow.yxmd")
        script = codegen.generate(wf)
        (work / "generated.py").write_text(script.source, encoding="utf-8")
        monkeypatch.chdir(work)
        namespace: dict = {"__name__": "__translated__"}
        exec(compile(script.source, str(work / "generated.py"), "exec"), namespace)
        return script, work

    return _run


def assert_expected_outputs(work: Path) -> None:
    expected_dir = work / "expected"
    expected_files = sorted(expected_dir.glob("*")) if expected_dir.exists() else []
    assert expected_files, f"{work.name}: fixture has no expected/ files"
    for exp in expected_files:
        got = work / exp.name
        assert got.exists(), f"script did not produce {exp.name}"
        assert_frames_match(got, exp)


def assert_frames_match(actual_path: Path, expected_path: Path) -> None:
    """Tolerant comparison: read both through pandas, ignore dtype differences."""
    read = _reader(actual_path)
    actual, expected = read(actual_path), read(expected_path)
    pdt.assert_frame_equal(actual, expected, check_dtype=False)


def _reader(path: Path):
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel
    return pd.read_csv
