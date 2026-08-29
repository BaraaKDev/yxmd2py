"""Exception types that separate "this file is broken" from "this node is beyond us".

ParseError aborts the file (exit 2). ConfigUnsupported and ExprUnsupported are caught
per-node / per-expression and degrade to TODO stubs — they must never escape codegen.
"""


class ParseError(Exception):
    """The .yxmd cannot be read at the document level (bad XML, no <Nodes>)."""


class ConfigUnsupported(Exception):
    """One node's <Configuration> doesn't match the shape this translator understands."""


class ExprUnsupported(Exception):
    """An Alteryx expression contains syntax or a function we don't translate."""
