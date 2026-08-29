"""AST nodes for the Alteryx expression grammar. Deliberately tiny."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FieldRef:
    name: str


@dataclass(frozen=True)
class Lit:
    value: str | int | float


@dataclass(frozen=True)
class BinOp:
    op: str  # normalized: == != < <= > >= + - * / and or
    left: object
    right: object


@dataclass(frozen=True)
class UnaryOp:
    op: str  # not, neg
    operand: object


@dataclass(frozen=True)
class Func:
    name: str  # lowercased
    args: tuple


@dataclass(frozen=True)
class IfExpr:
    pairs: tuple  # ((cond, value), ...) for IF/ELSEIF branches
    default: object | None  # ELSE value, or None when absent
