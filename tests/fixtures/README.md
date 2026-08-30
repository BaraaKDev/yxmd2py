# Fixture format assumptions

Every `.yxmd` in this directory is **synthetic** — hand-written from the format's known
structure, because no real Alteryx file was available when the translator was built. That
makes this file the contract to check on the first day a real workflow arrives:

```
uv run yxmd2py realfile.yxmd --check
```

`--check` prints per-tool coverage without writing code. Anything it reports as `stub`
means a plugin string or config shape differs from the assumptions below. Fixing a
variant is one line in `src/yxmd2py/registry.py` (`ALIASES` or `register()`); fixing a
config-shape difference means updating that one tool's module and the fixture here.

## Document structure

| Assumption | Where it bites |
|---|---|
| Root `<AlteryxDocument yxmdVer="...">` with `<Nodes>` and `<Connections>` | `parser.py` refuses files with no `<Nodes>` |
| Nodes may nest inside Tool Containers (`<ChildNodes>`) | parser iterates all `<Node>` descendants |
| `<GuiSettings Plugin="A.B.C">` — the **middle token** identifies the tool | `registry.plugin_token()` |
| `<Properties><Configuration>` holds tool config; the canvas note is `<Annotation><AnnotationText>` (user-typed) with `<DefaultAnnotationText>` (Designer's auto label) as fallback | parser |
| `<Connection><Origin ToolID Connection/><Destination ToolID Connection/>`; port names default to `Output`/`Input` | parser |

## Per-tool config shapes (the middle token, then the assumed XML)

| Tool | Assumed shape |
|---|---|
| `TextInput` | `<Fields><Field name/></Fields>` + `<Data><r><c>text</c></r></Data>` |
| `DbFileInput` / `DbFileOutput` | `<File>` text is the path; Excel appends `\|\|\|Sheet` or `` \|\|\|`Sheet$` ``; CSV options in `<FormatSpecificOptions>` with the **misspelled** `<Delimeter>` (both spellings read); `<CodePage>` best-effort |
| `AlteryxSelect` | `<SelectFields><SelectField field selected rename type/>` + `*Unknown` sentinel; `<OrderChanged value/>` |
| `Filter` | `<Mode>Simple\|Custom</Mode>`; Simple: `<Simple><Operator/><Field/><Operands><Operand/></Operands></Simple>`; Custom: `<Expression>` through the expression engine. Output ports `True` / `False` |
| `Formula` | `<FormulaFields><FormulaField expression field type/>` applied in listed order |
| `Join` | Two `<JoinInfo connection="Left\|Right"><Field field/></JoinInfo>`; join-by-position read from BOTH observed forms (`joinByRecordPos` attr on Configuration, and a `<JoinByRecordPos value/>` child); same-named keys merge with `on=` (one key column); embedded `<SelectConfiguration>` honored only for deselected right keys. Ports `Left`/`Right` in, `Left`/`Join`/`Right` out |
| `Union` | `<Mode>ByName\|ByPos\|Manual</Mode>`, `<ByName_OutputMode>All\|Common</ByName_OutputMode>`; inputs on ports `#1`, `#2`, ... stacked in that order |
| `Summarize` | `<SummarizeFields><SummarizeField field action rename/>`; Concat separator in child `<SummarizeField_Concat_Separator value/>` |
| `Sort` | `<SortInfo><Field field order="Ascending\|Descending"/></SortInfo>` |
| `Unique` | `<UniqueFields><Field field/></UniqueFields>`; output ports `Unique` / `Dup` |
| `Sample` | `<Mode>First\|Last\|Skip\|OneInN</Mode>` + `<N>` (text or value attr) + optional `<GroupFields><Field field/></GroupFields>` |
| `Browse` (+ `BrowseV2` alias) | recognized and skipped — data no-op |
| `ToolContainer` | organizational no-op; children live under `<ChildNodes>`; `<Configuration><Disabled value="True"/>` disables the whole subtree (inherited downward — an enabled container inside a disabled one is still dead), and those tools emit **no code**, since Alteryx would not run them |

## Semantic conventions pinned by these fixtures

- **Filter**: rows whose expression evaluates to null go to the **False** leg.
- **Join**: null keys never match (Alteryx semantics; pandas alone would match NaN keys).
- **Summarize**: `Count` counts records including nulls (`size`); null group keys are groups
  (`dropna=False`); `First`/`Last` take the row's value even when null.
- **Sort**: stable; pandas puts nulls last in either direction (may differ from Alteryx).
- **Unique**: NaN keys equal each other — a second null-keyed row is a duplicate.
- **Text Input**: values emit as strings; typing happens downstream, as on the canvas.
- **Expressions**: `Contains`/`StartsWith`/`EndsWith` case-insensitive by default;
  `FindString` case-sensitive, 0-based, -1 when absent; `Substring` 0-based;
  `Round(x, m)` rounds to the nearest multiple m; `Mod` follows the dividend's sign.

## Golden-test convention

Each fixture folder: `workflow.yxmd` + optional `inputs/` + `expected/`. The harness
copies the folder to tmp, runs the generated script with cwd there, then compares every
file in `expected/` against the same-named file produced at the copy's root, via a
tolerant read (`assert_frame_equal(check_dtype=False)`). Paths inside fixtures are
**relative** so nothing needs rewriting.

The `.xlsx` fixture inputs are generated (see git history) — regenerate rather than
editing them by hand.

## provided_examples/

Four `.yxmd` files hand-authored **independently of this project** (see the README in
that folder), kept verbatim as a cross-check: they exercised conventions the synthetic
fixtures missed and each finding became a fix plus a regression test
(`tests/unit/test_provided_examples.py`). They reference absolute `C:\data` paths and
ship no input data, so they are asserted at the translation level, never executed.
Findings they produced: the `DefaultAnnotationText` fallback, the `<JoinByRecordPos>`
element form, `on=` for same-named join keys, and datetime coercion of raw string
columns (`errors='coerce'`, null on invalid — matching Alteryx conversion behavior).
