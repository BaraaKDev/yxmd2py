"""Tokenizer for Alteryx expressions.

[Field Name] refs, single- or double-quoted strings, numbers, // and /* */ comments,
case-insensitive keywords. Anything unrecognized raises ExprUnsupported with the
offending slice, so the caller's TODO explains itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import ExprUnsupported

KEYWORDS = {"if", "then", "elseif", "else", "endif", "and", "or", "not"}

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<comment>//[^\n]*|/\*.*?\*/)
  | (?P<field>\[[^\]]+\])
  | (?P<string>'[^']*'|"[^"]*")
  | (?P<number>\d+\.\d*|\.\d+|\d+)
  | (?P<ident>[A-Za-z_][A-Za-z_0-9]*)
  | (?P<op><=|>=|!=|<>|==|=|<|>|\+|-|\*|/|!|\(|\)|,)
    """,
    re.VERBOSE | re.DOTALL,
)


@dataclass(frozen=True)
class Token:
    kind: str  # field | string | number | ident | keyword | op | end
    value: str


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if m is None:
            raise ExprUnsupported(f"unrecognized syntax at: {text[pos:pos + 20]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind in ("ws", "comment"):
            continue
        value = m.group()
        if kind == "field":
            tokens.append(Token("field", value[1:-1]))
        elif kind == "string":
            tokens.append(Token("string", value[1:-1]))
        elif kind == "ident":
            low = value.lower()
            # Keywords normalize to lowercase; other identifiers KEEP their case,
            # because a bare identifier can be a field reference (Alteryx allows
            # unbracketed names, seen in a real export) and column names are
            # case-sensitive in pandas. Function names lowercase at call sites.
            tokens.append(Token("keyword", low) if low in KEYWORDS else Token("ident", value))
        else:
            tokens.append(Token(kind, value))
    tokens.append(Token("end", ""))
    return tokens
