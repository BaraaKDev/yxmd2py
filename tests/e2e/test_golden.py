"""Golden tests: every fixture translates, executes, and reproduces expected/ files."""

from __future__ import annotations

import pytest

from conftest import assert_expected_outputs, fixture_names

# Fixtures that deliberately contain untranslatable pieces still run, but are not
# expected to be clean.
EXPECTED_DIRTY = {"unsupported_tool", "formula_tier1"}


@pytest.mark.parametrize("name", fixture_names())
def test_golden(name, run_fixture):
    script, work = run_fixture(name)
    assert_expected_outputs(work)
    if name not in EXPECTED_DIRTY:
        assert script.clean, [t for r in script.results for t in r.todos]
