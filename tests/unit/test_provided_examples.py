"""Regression suite over the hand-authored examples in tests/fixtures/provided_examples/.

These were written independently of this project's synthetic fixtures, so they act
as a cross-check on the format assumptions. They reference absolute C:\\data paths
and ship no input data, so they are validated at the translation level (parse ->
generate -> assert on the emitted code), not executed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from yxmd2py import codegen, parser

EXAMPLES = Path(__file__).parent.parent / "fixtures" / "provided_examples"


def _generate(name: str) -> codegen.GeneratedScript:
    return codegen.generate(parser.parse_yxmd(EXAMPLES / name))


def test_01_simple_linear_is_clean():
    script = _generate("01_simple_linear.yxmd")
    assert script.clean
    # *Unknown deselected: only the listed selected fields survive.
    assert (
        "df_2 = df_1[['OrderID', 'CustomerID', 'Region', 'Revenue', 'OrderDate']].copy()"
        in script.source
    )
    assert "df_2.rename(columns={'Revenue': 'revenue_usd'})" in script.source
    # Custom filter expression through the engine, double-quoted string included.
    assert "(df_2['revenue_usd'] > 10000) & (df_2['Region'] == 'West')" in script.source
    # Only the True leg is wired.
    assert "df_3_false" not in script.source


def test_02_formula_translates_all_six_fields():
    script = _generate("02_formula.yxmd")
    assert script.clean, [t for r in script.results for t in r.todos]
    src = script.source
    assert "df_2['LineTotal'] = df_2['Quantity'] * df_2['UnitPrice']" in src
    # Nested IIF -> nested np.where; the outer condition references the field
    # created two lines earlier in the same tool.
    assert (
        "df_2['ValueBand'] = np.where(df_2['LineTotal'] > 5000, 'High', "
        "np.where(df_2['LineTotal'] > 1000, 'Medium', 'Low'))"
    ) in src
    # Overwriting an existing field, not creating a new one.
    assert "df_2['CustomerName'] = ((df_2['CustomerName']).str.strip()).str.upper()" in src
    # Date column arrives as strings from read_csv; the emitter coerces first.
    assert (
        "df_2['DueDate'] = pd.to_datetime(df_2['OrderDate'], errors='coerce') + pd.to_timedelta(30, unit='D')"
    ) in src
    assert (
        "df_2['DiscountPct'] = np.where((pd.isna(df_2['DiscountPct'])), 0, "
        "pd.to_numeric(df_2['DiscountPct'], errors='coerce'))"
    ) in src
    assert (
        "df_2['IsEuropean'] = (df_2['ProductCode']).str.contains('-EU', case=False, regex=False)"
    ) in src


def test_03_join_branch_is_clean_with_single_key_column():
    script = _generate("03_join_branch.yxmd")
    assert script.clean, [t for r in script.results for t in r.todos]
    src = script.source
    # Same-named keys use on=, which already yields the single key column the
    # embedded Select's Right_CustomerID deselection asks for - no TODO, no drop.
    assert "on=_lkeys4, how='inner'" in src
    assert "Right_CustomerID" not in src
    # Both consumed legs materialize; annotations survive via DefaultAnnotationText.
    assert "df_4_j" in src and "df_4_l" in src
    assert "# Annotation: Join on CustomerID" in src
    # The JoinByRecordPos ELEMENT form (value=False) must not trip the stub path.
    assert "join by record position" not in src


def test_03_element_form_joinbyrecordpos_true_refuses(tmp_path):
    text = (EXAMPLES / "03_join_branch.yxmd").read_text(encoding="utf-8")
    text = text.replace('<JoinByRecordPos value="False" />', '<JoinByRecordPos value="True" />')
    p = tmp_path / "wf.yxmd"
    p.write_text(text, encoding="utf-8")
    script = codegen.generate(parser.parse_yxmd(p))
    assert not script.clean
    assert "join by record position is not supported" in script.source


def test_04_unsupported_tools_stub_loudly_and_browse_stays_quiet():
    script = _generate("04_unsupported_tools.yxmd")
    assert not script.clean
    src = script.source
    assert "AlteryxSpatialPluginsGui.FuzzyMatch.FuzzyMatch" in src
    assert "AlteryxSpatialPluginsGui.CreatePoints.CreatePoints" in src
    statuses = {r.tool_id: r.status for r in script.results}
    assert statuses[3] == "stub" and statuses[4] == "stub"
    assert statuses[6] == "ignored"  # Browse: counted, no code
    # The pipeline stays wired straight through both stubs to the Summarize.
    assert ".groupby(" in src


@pytest.mark.parametrize(
    "name", sorted(p.name for p in EXAMPLES.glob("*.yxmd"))
)
def test_every_example_parses_and_generates(name):
    script = _generate(name)
    assert script.source.startswith("# /// script")
