"""Command line: translate .yxmd file(s) to pandas scripts, or --check coverage.

    yxmd2py workflow.yxmd                  -> workflow.py alongside it
    yxmd2py workflow.yxmd -o out.py
    yxmd2py folder --out-dir build [--recursive]
    yxmd2py workflow.yxmd --check          -> coverage table, writes nothing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, codegen, parser, report
from .errors import ParseError


def _gather(inputs: list[Path], recursive: bool) -> list[Path]:
    files: list[Path] = []
    for item in inputs:
        if item.is_dir():
            pattern = "**/*.yxmd" if recursive else "*.yxmd"
            files.extend(sorted(item.glob(pattern)))
        else:
            files.append(item)
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="yxmd2py",
        description="Translate Alteryx .yxmd workflows into standalone pandas scripts.",
    )
    ap.add_argument("inputs", nargs="+", type=Path, metavar="INPUT",
                    help=".yxmd file(s) or folder(s) containing them")
    ap.add_argument("-o", "--output", type=Path,
                    help="output .py path (single input file only)")
    ap.add_argument("--out-dir", type=Path,
                    help="directory for generated scripts (required for folder inputs)")
    ap.add_argument("--check", action="store_true",
                    help="parse and report tool coverage; write nothing")
    ap.add_argument("--recursive", action="store_true",
                    help="recurse into folders when gathering .yxmd files")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--version", action="version", version=f"yxmd2py {__version__}")
    args = ap.parse_args(argv)

    files = _gather(args.inputs, args.recursive)
    if not files:
        print("yxmd2py: no .yxmd files found", file=sys.stderr)
        return 2
    if args.output and len(files) > 1:
        print("yxmd2py: -o only works with a single input file; use --out-dir", file=sys.stderr)
        return 2
    if any(p.is_dir() for p in args.inputs) and not args.check and not args.out_dir:
        print("yxmd2py: folder input needs --out-dir", file=sys.stderr)
        return 2

    scripts: list[codegen.GeneratedScript] = []
    for path in files:
        if not path.exists():
            print(f"yxmd2py: {path}: no such file", file=sys.stderr)
            return 2
        try:
            wf = parser.parse_yxmd(path)
            script = codegen.generate(wf)
        except ParseError as exc:
            print(f"yxmd2py: {exc}", file=sys.stderr)
            return 2

        scripts.append(script)
        print(f"{path.name}: {report.summarize(script)}")
        if args.check:
            print(report.coverage_table(script.results))
            continue

        if args.output:
            out_path = args.output
        elif args.out_dir:
            args.out_dir.mkdir(parents=True, exist_ok=True)
            out_path = args.out_dir / (path.stem + ".py")
        else:
            out_path = path.with_suffix(".py")
        out_path.write_text(script.source, encoding="utf-8", newline="\n")
        if args.verbose:
            print(f"  wrote {out_path}")

    return report.exit_code(scripts)


if __name__ == "__main__":
    raise SystemExit(main())
