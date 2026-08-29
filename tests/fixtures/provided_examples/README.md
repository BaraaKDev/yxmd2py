# Hand-authored .yxmd test fixtures

Four synthetic Alteryx workflow files for developing and testing a `.yxmd` parser.

## Provenance and caveat

These were **written by hand**, not exported from Alteryx Designer. The document
structure, node model, and connection model reflect the real format, but specific
attribute names, plugin identifiers, and configuration sub-elements may differ from
a genuine Designer export.

Build your parser defensively against these, then validate against a real file
before trusting the mapping. Expect to find discrepancies.

No Alteryx software was installed or used to produce these files, and no
third-party workflows were copied.

## Document structure

```
AlteryxDocument[yxmdVer]
├── Nodes
│   └── Node[ToolID]
│       ├── GuiSettings[Plugin]        <- tool type lives here
│       │   └── Position[x,y]
│       ├── Properties
│       │   ├── Configuration          <- tool-specific, varies per tool
│       │   └── Annotation             <- user label, useful for docs output
│       └── EngineSettings[EngineDll, EngineDllEntryPoint]
├── Connections
│   └── Connection
│       ├── Origin[ToolID, Connection]       <- Connection = output anchor name
│       └── Destination[ToolID, Connection]  <- Connection = input anchor name
└── Properties
    └── MetaInfo (Name, Description, Author, ...)
```

Tool type comes from the `Plugin` attribute on `GuiSettings`, e.g.
`AlteryxBasePluginsGui.Filter.Filter`. The last segment is the usable name.

## The fixtures

### 01_simple_linear.yxmd
Input -> Select -> Filter -> Output. Single path, no branching.

Covers: CSV input config, column selection and renaming, column dropping,
the `*Unknown` catch-all field, a Filter with a custom expression, CSV output.

Note the Filter connection uses anchor name `True`, not `Output`. Filter has two
output anchors (`True` and `False`) and only one is wired here.

### 02_formula.yxmd
Input -> Formula -> Sort -> Output.

Exists to exercise the expression language, which is the hardest part of the
project. The Formula tool defines six fields covering:

- plain arithmetic on two columns
- nested `IIF()`
- `IF ... THEN ... ELSE ... ENDIF` syntax
- string functions (`Uppercase`, `Trim`)
- date arithmetic (`DateTimeAdd`)
- null handling (`IsNull`) and type coercion (`ToNumber`)
- a boolean-producing function (`Contains`)
- **overwriting an existing field** rather than creating a new one
  (`CustomerName` and `DiscountPct`)

That last case matters: field creation order is significant, since later
expressions can reference fields created by earlier ones in the same tool.

Expressions are XML-escaped. `&gt;` and `&quot;` need unescaping before parsing.

### 03_join_branch.yxmd
Two inputs -> Unique -> Join -> Summarize -> two outputs.

The structural test. Covers:

- multiple root nodes, so topological sort is required
- named input anchors (`Left`, `Right`) on the Join
- named output anchors: `Unique` from the Unique tool, `Join` and `Left` from
  the Join tool
- a branch where one Join output feeds an aggregation and another is written
  directly to a separate file
- Join's embedded `SelectConfiguration`, a Select tool nested inside the Join

The Join `Left` output means unmatched left-hand records. Mapping that to pandas
requires an indicator merge, not a plain inner join.

### 04_unsupported_tools.yxmd
Input -> Select -> Fuzzy Match -> Create Points -> Summarize -> Browse.

Tests the refusal path. Fuzzy Match and Create Points have no clean pandas
equivalent and should produce loud stubs naming the tool and its configuration,
never a silent skip.

Browse is a viewer with no data effect and can be dropped, but the tool should
say that it dropped it rather than staying quiet.

## Suggested next fixtures

- Union with multiple inputs
- Text To Columns
- Multi-Row Formula (windowing, genuinely hard)
- A workflow containing a macro reference
- A deliberately malformed file, to test error handling
