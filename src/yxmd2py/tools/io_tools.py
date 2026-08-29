"""Input Data / Output Data (DbFileInput / DbFileOutput) -> pandas file I/O.

The <File> element's text is the path. Excel paths carry a sheet suffix:
    book.xlsx|||Sheet1        or        book.xlsx|||`Sheet1$`
Split on '|||', strip backticks and a trailing '$'.

CSV options live in <FormatSpecificOptions>; the real element name for the delimiter
is the misspelled <Delimeter> — read both spellings. Unknown/proprietary extensions
(.yxdb above all) become a loud TODO stub: the fix is exporting to CSV from Designer,
not us reverse-engineering the format.
"""

from __future__ import annotations

from ..errors import ConfigUnsupported
from ..model import Node
from ..spec import Emission, ToolSpec, TranslationContext, cfg_text, pystr

# Alteryx CodePage numbers -> python encodings (best-effort; default utf-8).
_CODEPAGES = {"65001": "utf-8", "1252": "cp1252", "28591": "latin-1"}


def split_file_ref(raw: str) -> tuple[str, str | None]:
    """(path, sheet_or_None) from an Alteryx <File> value."""
    if "|||" in raw:
        path, sheet = raw.split("|||", 1)
        sheet = sheet.strip().strip("`").rstrip("$").strip("`").strip()
        return path.strip(), sheet or None
    return raw.strip(), None


def _csv_options(node: Node) -> tuple[str, str | None]:
    """(delimiter, encoding_or_None) read defensively from FormatSpecificOptions."""
    delim = cfg_text(node, "FormatSpecificOptions/Delimeter", default="")
    if not delim:
        delim = cfg_text(node, "FormatSpecificOptions/Delimiter", default=",")
    if delim in ("", "\\0"):  # \0 is Alteryx for "no delimiter (single field)"
        delim = ","
    codepage = cfg_text(node, "FormatSpecificOptions/CodePage", default="")
    encoding = _CODEPAGES.get(codepage) if codepage else None
    return delim, encoding


def _translate_input(node: Node, ctx: TranslationContext) -> Emission:
    raw = cfg_text(node, "File")
    path, sheet = split_file_ref(raw)
    var = ctx.var("Output")
    ext = path.lower().rsplit(".", 1)[-1] if "." in path else ""

    if ext == "csv":
        const = ctx.add_path_const("INPUT", path)
        delim, encoding = _csv_options(node)
        args = [const]
        if delim != ",":
            args.append(f"sep={pystr(delim)}")
        if encoding and encoding != "utf-8":
            args.append(f"encoding={pystr(encoding)}")
        return Emission(
            lines=[f"{var} = pd.read_csv({', '.join(args)})"],
            outputs={"Output": var},
        )

    if ext in ("xlsx", "xls", "xlsm"):
        const = ctx.add_path_const("INPUT", path)
        args = [const]
        if sheet:
            args.append(f"sheet_name={pystr(sheet)}")
        return Emission(
            lines=[f"{var} = pd.read_excel({', '.join(args)})"],
            outputs={"Output": var},
        )

    reason = (
        f".{ext or '?'} input is not supported"
        + (" - export it to CSV from Alteryx Designer" if ext == "yxdb" else "")
    )
    return Emission(
        lines=[
            f"# TODO(yxmd2py): {reason}",
            f"# Source: {raw}",
            f"{var} = pd.DataFrame()  # TODO(yxmd2py): load {path} here",
        ],
        outputs={"Output": var},
        status="stub",
        todos=[f"Input Data (ToolID {node.tool_id}): {reason}"],
    )


def _translate_output(node: Node, ctx: TranslationContext) -> Emission:
    raw = cfg_text(node, "File")
    path, sheet = split_file_ref(raw)
    src = ctx.sole_input()
    ext = path.lower().rsplit(".", 1)[-1] if "." in path else ""

    if ext == "csv":
        const = ctx.add_path_const("OUTPUT", path)
        delim, encoding = _csv_options(node)
        args = [const, "index=False"]
        if delim != ",":
            args.insert(1, f"sep={pystr(delim)}")
        if encoding and encoding != "utf-8":
            args.append(f"encoding={pystr(encoding)}")
        return Emission(lines=[f"{src}.to_csv({', '.join(args)})"], outputs={})

    if ext in ("xlsx", "xlsm"):
        const = ctx.add_path_const("OUTPUT", path)
        args = [const, "index=False"]
        if sheet:
            args.insert(1, f"sheet_name={pystr(sheet)}")
        return Emission(lines=[f"{src}.to_excel({', '.join(args)})"], outputs={})

    reason = f".{ext or '?'} output is not supported"
    return Emission(
        lines=[
            f"# TODO(yxmd2py): {reason}",
            f"# Destination: {raw}",
            f"# {src}.to_csv(...)  # TODO(yxmd2py): write {path} here",
        ],
        outputs={},
        status="stub",
        todos=[f"Output Data (ToolID {node.tool_id}): {reason}"],
    )


INPUT_SPEC = ToolSpec(
    kind="input", in_ports=(), out_ports=("Output",),
    translate=_translate_input, label="Input Data",
)

OUTPUT_SPEC = ToolSpec(
    kind="output", in_ports=("Input",), out_ports=(),
    translate=_translate_output, label="Output Data",
)
