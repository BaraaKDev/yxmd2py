"""Tier-1 Alteryx function table: name -> emitter over already-emitted arg strings.

Each entry owns its own semantic notes. Two Alteryx behaviors are pinned here:
Contains() is case-INsensitive by default, and Substring() start is 0-based.
Round(x, m) rounds to the nearest multiple m, not to m decimal places.
Unknown functions and wrong arg counts raise ExprUnsupported so the caller's TODO
carries the verbatim expression.
"""

from __future__ import annotations

from collections.abc import Callable

from ..errors import ExprUnsupported


def _arity(name: str, args: list[str], *counts: int) -> None:
    if len(args) not in counts:
        want = " or ".join(str(c) for c in counts)
        raise ExprUnsupported(f"{name}() takes {want} argument(s), got {len(args)}")


def _fn(name: str, *counts: int):
    def deco(fn: Callable[[list[str]], str]):
        def wrapped(args: list[str]) -> str:
            _arity(name, args, *counts)
            return fn(args)

        FUNCTIONS[name] = wrapped
        return fn

    return deco


FUNCTIONS: dict[str, Callable[[list[str]], str]] = {}

# --- null handling -------------------------------------------------------------
_fn("isnull", 1)(lambda a: f"pd.isna({a[0]})")
_fn("isempty", 1)(lambda a: f"(pd.isna({a[0]}) | ({a[0]} == ''))")
_fn("null", 0)(lambda a: "pd.NA")

# --- conversion ----------------------------------------------------------------
_fn("tonumber", 1)(lambda a: f"pd.to_numeric({a[0]}, errors='coerce')")
_fn("tostring", 1)(lambda a: f"({a[0]}).astype('string')")

# --- strings -------------------------------------------------------------------
_fn("uppercase", 1)(lambda a: f"({a[0]}).str.upper()")
_fn("lowercase", 1)(lambda a: f"({a[0]}).str.lower()")
_fn("trim", 1, 2)(lambda a: f"({a[0]}).str.strip({a[1] if len(a) > 1 else ''})")
_fn("trimleft", 1, 2)(lambda a: f"({a[0]}).str.lstrip({a[1] if len(a) > 1 else ''})")
_fn("trimright", 1, 2)(lambda a: f"({a[0]}).str.rstrip({a[1] if len(a) > 1 else ''})")
_fn("left", 2)(lambda a: f"({a[0]}).str.slice(0, {a[1]})")
_fn("right", 2)(lambda a: f"({a[0]}).str.slice(-({a[1]}))")
_fn("length", 1)(lambda a: f"({a[0]}).str.len()")
_fn("contains", 2, 3)(
    # Alteryx Contains is case-insensitive unless the third arg (0) says otherwise.
    lambda a: f"({a[0]}).str.contains({a[1]}, case={'True' if len(a) > 2 and a[2] == '0' else 'False'}, regex=False)"
)
_fn("replace", 3)(lambda a: f"({a[0]}).str.replace({a[1]}, {a[2]}, regex=False)")
_fn("substring", 2, 3)(
    # 0-based start; without a length it runs to the end.
    lambda a: f"({a[0]}).str.slice({a[1]}, {a[1]} + {a[2]})" if len(a) > 2 else f"({a[0]}).str.slice({a[1]})"
)

# --- numbers -------------------------------------------------------------------
_fn("abs", 1)(lambda a: f"abs({a[0]})")
_fn("round", 2)(
    # Round to the nearest MULTIPLE (Alteryx semantics), not to N decimal places.
    lambda a: f"((({a[0]}) / {a[1]}).round() * {a[1]})"
)
_fn("floor", 1)(lambda a: f"np.floor({a[0]})")
_fn("ceil", 1)(lambda a: f"np.ceil({a[0]})")
_fn("mod", 2)(
    # C-style remainder (sign follows the dividend), unlike python's %.
    lambda a: f"np.fmod({a[0]}, {a[1]})"
)
_fn("min", 2)(lambda a: f"np.minimum({a[0]}, {a[1]})")
_fn("max", 2)(lambda a: f"np.maximum({a[0]}, {a[1]})")

# --- conditionals --------------------------------------------------------------
_fn("iif", 3)(lambda a: f"np.where({a[0]}, {a[1]}, {a[2]})")


# --- tier 2: strings -----------------------------------------------------------
def _str_literal(arg: str) -> str | None:
    """The inner text when an emitted arg is a plain string literal, else None."""
    if len(arg) >= 2 and arg[0] == arg[-1] == "'" and "\\" not in arg:
        return arg[1:-1]
    return None


def _affix(which: str):
    # Alteryx StartsWith/EndsWith are case-insensitive unless the third arg is 0.
    def emit(args: list[str]) -> str:
        case_sensitive = len(args) > 2 and args[2] == "0"
        if case_sensitive:
            return f"({args[0]}).str.{which}({args[1]})"
        target = _str_literal(args[1])
        if target is None:
            raise ExprUnsupported(
                f"case-insensitive {which} needs a literal target (pass 0 as the third argument for case-sensitive)"
            )
        return f"({args[0]}).str.lower().str.{which}({target.lower()!r})"

    return emit


_fn("startswith", 2, 3)(_affix("startswith"))
_fn("endswith", 2, 3)(_affix("endswith"))
_fn("findstring", 2)(
    # Case-SENSITIVE (unlike Contains); 0-based index, -1 when absent - .str.find exactly.
    lambda a: f"({a[0]}).str.find({a[1]})"
)
_fn("padleft", 3)(lambda a: f"({a[0]}).str.rjust({a[1]}, {a[2]})")
_fn("padright", 3)(lambda a: f"({a[0]}).str.ljust({a[1]}, {a[2]})")
_fn("pow", 2)(lambda a: f"(({a[0]}) ** ({a[1]}))")

# --- regex ---------------------------------------------------------------------
# All three are case-insensitive by default (icase=1 per the Alteryx docs); a
# third argument of 0 forces case sensitivity. Insensitivity rides on an inline
# (?i) prefix concatenated onto the pattern, which works for literal and
# computed patterns alike and needs no re import in the generated script.


def _rx_pattern(args: list[str], icase_index: int) -> str:
    case_sensitive = len(args) > icase_index and args[icase_index] == "0"
    return args[1] if case_sensitive else f"'(?i)' + {args[1]}"


def _regex_match(args: list[str]) -> str:
    # Alteryx REGEX_Match matches "from the first character to the end" - the
    # ENTIRE string - hence fullmatch, never contains.
    return f"({args[0]}).str.fullmatch({_rx_pattern(args, 2)})"


def _regex_countmatches(args: list[str]) -> str:
    return f"({args[0]}).str.count({_rx_pattern(args, 2)})"


def _regex_replace(args: list[str]) -> str:
    # Alteryx replacements reference groups as $1; python re wants \g<1>. The
    # conversion is textual on the emitted source literal, so a computed
    # replacement carrying $ refs is refused rather than silently emitting
    # literal dollar signs.
    import re as _re

    repl = args[2]
    if "$" in repl:
        if not (repl.startswith("'") and repl.endswith("'")):
            raise ExprUnsupported(
                "REGEX_Replace() with $ group refs in a non-literal replacement"
            )
        repl = _re.sub(r"\$(\d+)", r"\\\\g<\1>", repl)
    return f"({args[0]}).str.replace({_rx_pattern(args, 3)}, {repl}, regex=True)"


_fn("regex_match", 2, 3)(_regex_match)
_fn("regex_countmatches", 2, 3)(_regex_countmatches)
_fn("regex_replace", 3, 4)(_regex_replace)


# --- tier 2: datetime ----------------------------------------------------------
_DT_UNITS = {"days": "D", "hours": "h", "minutes": "m", "seconds": "s"}


def _dt_unit(arg: str, fn_name: str) -> str:
    unit = _str_literal(arg)
    if unit is None or unit not in _DT_UNITS:
        raise ExprUnsupported(
            f"{fn_name}() unit must be one of {sorted(_DT_UNITS)} as a literal"
            " (months/years need calendar arithmetic - translate by hand)"
        )
    return unit


def _as_dt(arg: str) -> str:
    """Coerce to datetime, mirroring Alteryx's leniency toward ISO date strings.

    A workflow's date column arrives from read_csv as strings; Alteryx would have
    typed it at the input tool. to_datetime is a no-op on an already-datetime
    series, so wrapping is safe in both worlds, and errors='coerce' turns an
    unparseable value into null the way an Alteryx conversion does. Skipped when
    the arg is already a DateTimeParse call.
    """
    if arg.startswith("pd.to_datetime("):
        return arg
    return f"pd.to_datetime({arg}, errors='coerce')"


_fn("datetimeparse", 2)(lambda a: f"pd.to_datetime({a[0]}, format={a[1]}, errors='coerce')")
_fn("datetimeformat", 2)(lambda a: f"({_as_dt(a[0])}).dt.strftime({a[1]})")
_fn("datetimenow", 0)(lambda a: "pd.Timestamp.now()")
_fn("datetimeadd", 3)(
    lambda a: f"{_as_dt(a[0])} + pd.to_timedelta({a[1]}, unit={_DT_UNITS[_dt_unit(a[2], 'DateTimeAdd')]!r})"
)


def _datetimediff(args: list[str]) -> str:
    unit = _dt_unit(args[2], "DateTimeDiff")
    seconds = {"days": 86400, "hours": 3600, "minutes": 60, "seconds": 1}[unit]
    base = f"({_as_dt(args[0])} - {_as_dt(args[1])}).dt.total_seconds()"
    if seconds == 1:
        return f"({base}).astype('Int64')"
    return f"({base} // {seconds}).astype('Int64')"


_fn("datetimediff", 3)(_datetimediff)


def emit_call(name: str, args: list[str]) -> str:
    fn = FUNCTIONS.get(name)
    if fn is None:
        raise ExprUnsupported(f"function {name}() is not supported")
    return fn(args)
