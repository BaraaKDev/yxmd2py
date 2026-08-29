"""CLI behavior: exit codes, folder mode, --check writing nothing."""

from __future__ import annotations

import shutil
from pathlib import Path

from yxmd2py.cli import main

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_clean_translation_exits_0(tmp_path):
    out = tmp_path / "out.py"
    code = main([str(FIXTURES / "select_basic" / "workflow.yxmd"), "-o", str(out)])
    assert code == 0
    assert "pd.read_csv" in out.read_text(encoding="utf-8")


def test_stubs_exit_1_but_still_write(tmp_path):
    out = tmp_path / "out.py"
    code = main([str(FIXTURES / "unsupported_tool" / "workflow.yxmd"), "-o", str(out)])
    assert code == 1
    assert "NOT TRANSLATED" in out.read_text(encoding="utf-8")


def test_check_writes_nothing(tmp_path):
    wf = tmp_path / "workflow.yxmd"
    shutil.copy(FIXTURES / "unsupported_tool" / "workflow.yxmd", wf)
    code = main([str(wf), "--check"])
    assert code == 1  # gaps found
    assert list(tmp_path.glob("*.py")) == []


def test_check_clean_exits_0():
    assert main([str(FIXTURES / "kitchen_sink" / "workflow.yxmd"), "--check"]) == 0


def test_folder_mode_needs_out_dir(tmp_path):
    (tmp_path / "a.yxmd").write_bytes((FIXTURES / "select_basic" / "workflow.yxmd").read_bytes())
    assert main([str(tmp_path)]) == 2


def test_folder_mode_translates_every_workflow(tmp_path):
    src_dir = tmp_path / "flows"
    src_dir.mkdir()
    for name in ("select_basic", "sort_unique_sample"):
        shutil.copy(FIXTURES / name / "workflow.yxmd", src_dir / f"{name}.yxmd")
    out_dir = tmp_path / "build"
    assert main([str(src_dir), "--out-dir", str(out_dir)]) == 0
    assert sorted(p.name for p in out_dir.glob("*.py")) == [
        "select_basic.py",
        "sort_unique_sample.py",
    ]


def test_missing_file_exits_2(tmp_path):
    assert main([str(tmp_path / "nope.yxmd")]) == 2


def test_broken_xml_exits_2(tmp_path):
    bad = tmp_path / "bad.yxmd"
    bad.write_text("<AlteryxDocument><Nodes>", encoding="utf-8")
    assert main([str(bad)]) == 2
