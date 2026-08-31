# yxmd2py

![tests](https://github.com/BaraaKDev/yxmd2py/actions/workflows/test.yml/badge.svg)

**Translate Alteryx workflow files (`.yxmd`) into standalone Python/pandas scripts.**

This is a migration aid, not an Alteryx replacement. You have workflows; you want the same
logic as plain Python you can read, version, and run anywhere. Point this at the `.yxmd`
and you get one commented pandas script per workflow — with every piece it *couldn't*
translate marked by a loud `TODO` rather than silently guessed at.

```
uv run yxmd2py workflow.yxmd                 # -> workflow.py alongside it
uv run yxmd2py workflow.yxmd --check         # coverage report, writes nothing
uv run yxmd2py flows\ --out-dir build\       # a folder at a time
```

## What it translates

**Tools:** Select, Filter (Simple and Custom expressions), Formula, Join, Union,
Summarize, Sort, Unique, Sample, Record ID, Text To Columns, Transpose, Cross Tab —
plus Input Data / Output Data / Text Input for CSV and Excel. Browse tools are recognized and skipped, and tools inside **disabled Tool
Containers emit no code** — Alteryx wouldn't run them, so neither does the translation
(a downstream tool that depended on one degrades to a loud stub). Anything else becomes a passthrough stub
with a `TODO(yxmd2py)` comment, a warning in the summary, and **exit code 1** — the
script is still written and still runs, but CI can refuse it and a human knows where to
look. Proprietary `.yxdb` inputs get the same treatment (the fix: export to CSV from
Designer).

**Expressions:** a real parser for the Alteryx formula language — `[Field]` references,
`IF/ELSEIF/ELSE/ENDIF`, `IIF`, `AND/OR/NOT`, and a function library covering null
handling, conversions, strings, regex (`REGEX_Match`/`Replace`/`CountMatches`, with
Alteryx's full-string-match and `$1` group-ref semantics), math, and datetimes. An
expression the engine doesn't support is kept **verbatim** in a TODO comment; nothing
is approximated. Macro references are recognized as such and stub with a pointer to
the `.yxmc` they run.

## What the generated script looks like

- A PEP 723 `# /// script` header, so a bare `uv run script.py` resolves pandas itself —
  no project, no venv setup.
- Every file path hoisted into a constants block at the top (`# --- File paths (edit
  here) ---`), because real workflows point at network drives you'll need to repoint.
- One commented block per tool, in execution order, carrying the tool's canvas
  annotation. Variables are `df_<toolid>`, with `_true/_false`, `_j/_l/_r`,
  `_uniq/_dup` suffixes for multi-output tools — traceable straight back to the canvas.

## Semantics that are deliberately pinned

Alteryx and pandas disagree in places where a naive translation silently changes your
data. These are handled explicitly, each with a NOTE in the generated code:

| | Alteryx | naive pandas | yxmd2py emits |
|---|---|---|---|
| Filter on null | row goes to the **False** leg | row vanishes or errors | `mask.fillna(False)` |
| Join on null keys | never match | NaN matches NaN | null-keyed rows filtered into L/R legs |
| Summarize Count | counts records incl. nulls | `count` skips nulls | `size` |
| Null group keys | form a group | dropped | `groupby(dropna=False)` |
| First/Last | the row's value, even null | first non-null | `iloc[0]` / `iloc[-1]` |
| `Contains()` | case-insensitive by default | case-sensitive | `case=False` |
| `Round(x, m)` | nearest multiple of m | m decimal places | `(x / m).round() * m` |

## Setup

Windows with [uv](https://docs.astral.sh/uv/) is all you need — uv brings its own Python.

```
git clone <this repo>
cd yxmd2py
uv run yxmd2py --help
uv run pytest                    # -m "not slow" skips the subprocess round trip
```

## When a real workflow doesn't translate

The test fixtures are synthetic (no real Alteryx file existed on the build machine), so a
real Designer export may use plugin strings or config shapes we didn't predict. That's a
designed-for case, not a failure:

1. `uv run yxmd2py realfile.yxmd --check` — see exactly which tools are stubs.
2. [tests/fixtures/README.md](tests/fixtures/README.md) lists every format assumption,
   tool by tool.
3. A variant plugin string is one `ALIASES` line in `src/yxmd2py/registry.py`; a config
   difference is a change to that one tool's module in `src/yxmd2py/tools/`.

## Layout

```
src/yxmd2py/
  parser.py         .yxmd XML -> workflow model (defensive; stdlib ElementTree)
  registry.py       plugin string -> translator; THE extension point
  codegen.py        topological order, consumed-port analysis, script assembly
  spec.py           the translator contract (Emission, TranslationContext)
  tools/            one module per tool
  exprlang/         lexer -> parser -> AST -> pandas emitter, + the function table
tests/
  fixtures/         synthetic golden workflows: .yxmd + inputs + expected outputs
    provided_examples/   independently hand-authored .yxmd files, kept as a
                         cross-check on the format assumptions (translation-level
                         regression tests; they ship no input data)
  unit/  e2e/       golden tests execute the generated scripts for real
```
