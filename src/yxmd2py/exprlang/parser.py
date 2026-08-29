"""Recursive-descent parser: token list -> AST.

Precedence, loosest first: OR, AND, NOT, comparison, additive, multiplicative,
unary minus, primary. IF/ELSEIF/ELSE/ENDIF parses wherever an expression may
appear. Any surprise raises ExprUnsupported — no partial recovery, by contract.
"""

from __future__ import annotations

from ..errors import ExprUnsupported
from .ast import BinOp, FieldRef, Func, IfExpr, Lit, UnaryOp
from .lexer import Token, tokenize

_COMPARE = {"=": "==", "==": "==", "!=": "!=", "<>": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">="}


class _Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def next(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect_keyword(self, word: str) -> None:
        tok = self.next()
        if tok.kind != "keyword" or tok.value != word:
            raise ExprUnsupported(f"expected {word.upper()}, found {tok.value!r}")

    def at_keyword(self, *words: str) -> bool:
        tok = self.peek()
        return tok.kind == "keyword" and tok.value in words

    # --- grammar, loosest binding first ---

    def expression(self):
        return self.or_expr()

    def or_expr(self):
        node = self.and_expr()
        while self.at_keyword("or"):
            self.next()
            node = BinOp("or", node, self.and_expr())
        return node

    def and_expr(self):
        node = self.not_expr()
        while self.at_keyword("and"):
            self.next()
            node = BinOp("and", node, self.not_expr())
        return node

    def not_expr(self):
        if self.at_keyword("not") or (self.peek().kind == "op" and self.peek().value == "!"):
            self.next()
            return UnaryOp("not", self.not_expr())
        return self.comparison()

    def comparison(self):
        node = self.additive()
        tok = self.peek()
        if tok.kind == "op" and tok.value in _COMPARE:
            self.next()
            node = BinOp(_COMPARE[tok.value], node, self.additive())
        return node

    def additive(self):
        node = self.multiplicative()
        while self.peek().kind == "op" and self.peek().value in ("+", "-"):
            op = self.next().value
            node = BinOp(op, node, self.multiplicative())
        return node

    def multiplicative(self):
        node = self.unary()
        while self.peek().kind == "op" and self.peek().value in ("*", "/"):
            op = self.next().value
            node = BinOp(op, node, self.unary())
        return node

    def unary(self):
        if self.peek().kind == "op" and self.peek().value == "-":
            self.next()
            return UnaryOp("neg", self.unary())
        return self.primary()

    def primary(self):
        tok = self.next()
        if tok.kind == "field":
            return FieldRef(tok.value)
        if tok.kind == "string":
            return Lit(tok.value)
        if tok.kind == "number":
            text = tok.value
            return Lit(float(text) if "." in text else int(text))
        if tok.kind == "op" and tok.value == "(":
            node = self.expression()
            closing = self.next()
            if closing.kind != "op" or closing.value != ")":
                raise ExprUnsupported("unbalanced parentheses")
            return node
        if tok.kind == "keyword" and tok.value == "if":
            return self.if_expr()
        if tok.kind == "ident":
            opening = self.next()
            if opening.kind != "op" or opening.value != "(":
                raise ExprUnsupported(f"bare identifier {tok.value!r} (fields need [brackets])")
            args: list = []
            if not (self.peek().kind == "op" and self.peek().value == ")"):
                args.append(self.expression())
                while self.peek().kind == "op" and self.peek().value == ",":
                    self.next()
                    args.append(self.expression())
            closing = self.next()
            if closing.kind != "op" or closing.value != ")":
                raise ExprUnsupported(f"unbalanced call to {tok.value}()")
            return Func(tok.value, tuple(args))
        raise ExprUnsupported(f"unexpected {tok.value!r}")

    def if_expr(self):
        # IF has been consumed.
        pairs: list[tuple] = []
        cond = self.expression()
        self.expect_keyword("then")
        pairs.append((cond, self.expression()))
        while self.at_keyword("elseif"):
            self.next()
            cond = self.expression()
            self.expect_keyword("then")
            pairs.append((cond, self.expression()))
        default = None
        if self.at_keyword("else"):
            self.next()
            default = self.expression()
        self.expect_keyword("endif")
        return IfExpr(tuple(pairs), default)


def parse(text: str):
    if not text.strip():
        raise ExprUnsupported("empty expression")
    p = _Parser(tokenize(text))
    node = p.expression()
    tail = p.peek()
    if tail.kind != "end":
        raise ExprUnsupported(f"trailing content starting at {tail.value!r}")
    return node
