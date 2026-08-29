"""Expression translator tests.

Two styles by design: EVALUATED rows (many — run the emitted code on a real frame
and check values, robust to emitter refactors) and EMISSION rows (few — pin exact
code style). Every function in the tier-1 table gets at least one evaluated row.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from yxmd2py.errors import ExprUnsupported
from yxmd2py.exprlang import translate_expression

DF = pd.DataFrame(
    {
        "Score": [90.0, 42.0, np.nan, 50.0],
        "Bonus": [10.0, 5.0, 1.0, 0.0],
        "Name": [" Alice ", "bob", "CARA", None],
        "Code": ["A-1", "b-2", "A-3", "c-4"],
    }
)


def evaluate(expr: str):
    code = translate_expression(expr, "df")
    return eval(code, {"pd": pd, "np": np, "df": DF, "abs": abs})


def as_list(result):
    seq = result.tolist() if hasattr(result, "tolist") else result
    return [None if isinstance(x, float) and np.isnan(x) else (None if x is pd.NA else x) for x in seq]


EVALUATED = [
    # arithmetic + comparison + precedence
    ("[Score] + [Bonus]", [100.0, 47.0, None, 50.0]),
    ("[Score] * 2 - 10", [170.0, 74.0, None, 90.0]),
    ("[Score] > 50", [True, False, False, False]),
    ("[Score] >= 50 AND [Bonus] > 0", [True, False, False, False]),
    ("[Score] > 80 OR [Bonus] > 4", [True, True, False, False]),
    ("NOT [Score] > 50", [False, True, True, True]),
    ("-[Bonus]", [-10.0, -5.0, -1.0, -0.0]),
    ("[Score] != 42", [True, False, True, True]),
    ("[Score] <> 42", [True, False, True, True]),
    # IF chains
    (
        "IF [Score] >= 90 THEN 'A' ELSEIF [Score] >= 50 THEN 'B' ELSE 'C' ENDIF",
        ["A", "C", "C", "B"],
    ),
    ("IF [Score] > 50 THEN 1 ELSE 0 ENDIF", [1, 0, 0, 0]),
    ("IIF([Score] > 50, 'hi', 'lo')", ["hi", "lo", "lo", "lo"]),
    # null handling
    ("IsNull([Score])", [False, False, True, False]),
    ("IsEmpty([Name])", [False, False, False, True]),
    # strings
    ("Uppercase([Name])", [" ALICE ", "BOB", "CARA", None]),
    ("Lowercase([Name])", [" alice ", "bob", "cara", None]),
    ("Trim([Name])", ["Alice", "bob", "CARA", None]),
    ("Length([Code])", [3, 3, 3, 3]),
    ("Left([Code], 1)", ["A", "b", "A", "c"]),
    ("Right([Code], 2)", ["-1", "-2", "-3", "-4"]),
    ("Contains([Code], 'a')", [True, False, True, False]),  # case-insensitive default
    ("Contains([Code], 'a', 0)", [False, False, False, False]),  # case forced on
    ("Replace([Code], '-', '_')", ["A_1", "b_2", "A_3", "c_4"]),
    ("Substring([Code], 1, 2)", ["-1", "-2", "-3", "-4"]),  # 0-based start
    ("ToString([Bonus])", ["10.0", "5.0", "1.0", "0.0"]),
    ("ToNumber(Substring([Code], 2))", [1, 2, 3, 4]),
    # numbers
    ("Abs(0 - [Bonus])", [10.0, 5.0, 1.0, 0.0]),
    ("Round([Score], 25)", [100.0, 50.0, None, 50.0]),
    ("Floor([Score] / 10)", [9.0, 4.0, None, 5.0]),
    ("Ceil([Score] / 100)", [1.0, 1.0, None, 1.0]),
    ("Mod([Score], 7)", [6.0, 0.0, None, 1.0]),
    ("Min([Score], 60)", [60.0, 42.0, None, 50.0]),
    ("Max([Score], 60)", [90.0, 60.0, None, 60.0]),
    # comments survive
    ("[Score] > 50 // pass mark", [True, False, False, False]),
    ("/* pass mark */ [Score] > 50", [True, False, False, False]),
    # tier 2: strings
    ("StartsWith([Code], 'a')", [True, False, True, False]),  # case-insensitive default
    ("StartsWith([Code], 'A', 0)", [True, False, True, False]),  # case-sensitive
    ("EndsWith([Code], '2')", [False, True, False, False]),
    ("FindString([Code], '-')", [1, 1, 1, 1]),
    ("FindString([Code], 'a')", [-1, -1, -1, -1]),  # case-SENSITIVE, unlike Contains
    ("PadLeft([Code], 5, '0')", ["00A-1", "00b-2", "00A-3", "00c-4"]),
    ("PadRight([Code], 5, '.')", ["A-1..", "b-2..", "A-3..", "c-4.."]),
    ("Pow([Bonus], 2)", [100.0, 25.0, 1.0, 0.0]),
]

DATES = pd.DataFrame(
    {
        "Start": ["2026-01-01", "2026-08-28", "bad"],
        "End": ["2026-01-03", "2026-08-28", "2026-01-01"],
    }
)

DATE_EVALUATED = [
    (
        "DateTimeFormat(DateTimeParse([Start], '%Y-%m-%d'), '%d/%m/%Y')",
        ["01/01/2026", "28/08/2026", None],
    ),
    (
        "DateTimeDiff(DateTimeParse([End], '%Y-%m-%d'), DateTimeParse([Start], '%Y-%m-%d'), 'days')",
        [2, 0, None],
    ),
    (
        "DateTimeFormat(DateTimeAdd(DateTimeParse([Start], '%Y-%m-%d'), 36, 'hours'), '%Y-%m-%d %H')",
        ["2026-01-02 12", "2026-08-29 12", None],
    ),
    # Raw string columns (the read_csv reality) coerce; invalid values go null, not boom.
    (
        "DateTimeFormat(DateTimeAdd([Start], 1, 'days'), '%Y-%m-%d')",
        ["2026-01-02", "2026-08-29", None],
    ),
    ("DateTimeDiff([End], [Start], 'days')", [2, 0, None]),
]


@pytest.mark.parametrize("expr,expected", DATE_EVALUATED, ids=[e for e, _ in DATE_EVALUATED])
def test_datetime_evaluated(expr, expected):
    code = translate_expression(expr, "df")
    result = eval(code, {"pd": pd, "np": np, "df": DATES, "abs": abs})
    assert as_list(result) == expected


@pytest.mark.parametrize("expr,expected", EVALUATED, ids=[e for e, _ in EVALUATED])
def test_evaluated(expr, expected):
    assert as_list(evaluate(expr)) == expected


EMISSION = [
    ("[Score] > 50", "df['Score'] > 50"),
    ("[A] = 'x' AND [B] = 'y'", "(df['A'] == 'x') & (df['B'] == 'y')"),
    ("Null()", "pd.NA"),
    (
        "IF [S] > 1 THEN 'a' ELSEIF [S] > 0 THEN 'b' ELSE 'c' ENDIF",
        "np.select([(df['S'] > 1), (df['S'] > 0)], ['a', 'b'], default='c')",
    ),
]


@pytest.mark.parametrize("expr,code", EMISSION, ids=[e for e, _ in EMISSION])
def test_emission_style(expr, code):
    assert translate_expression(expr, "df") == code


UNSUPPORTED = [
    "REGEX_Match([A], '\\d+')",  # tier-3 function
    "[A] +",  # syntax error
    "Switch([A], 'x', 1, 2)",  # tier-3, deliberately absent until a real workflow needs it
    "DateTimeAdd([A], 1, 'months')",  # calendar arithmetic refused, not guessed
    "bareword",  # field without brackets
    "",  # empty
    "Contains([A])",  # wrong arity
]


@pytest.mark.parametrize("expr", UNSUPPORTED, ids=[repr(e) for e in UNSUPPORTED])
def test_unsupported_raises(expr):
    with pytest.raises(ExprUnsupported):
        translate_expression(expr, "df")
