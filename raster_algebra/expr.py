"""Safe arithmetic-expression parser.

Grammar:
    expr    := term (('+' | '-') term)*
    term    := factor (('*' | '/') factor)*
    factor  := '-' factor | '+' factor | atom
    atom    := number | name | call | '(' expr ')'
    call    := 'coalesce' '(' expr (',' expr)* ')'

Only literal numbers, grid names and coalesce(...) calls are allowed.
No attribute access, subscripts, or other identifiers/calls.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Union


class ExprError(ValueError):
    pass


@dataclass(frozen=True)
class Num:
    value: float


@dataclass(frozen=True)
class Ref:
    name: str


@dataclass(frozen=True)
class Bin:
    op: str
    left: "Node"
    right: "Node"


@dataclass(frozen=True)
class Neg:
    operand: "Node"


@dataclass(frozen=True)
class Coalesce:
    args: tuple["Node", ...]


Node = Union[Num, Ref, Bin, Neg, Coalesce]

_OPS = set("+-*/(),")


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch in _OPS:
            tokens.append((ch, ch))
            i += 1
            continue
        if ch.isdigit() or ch == ".":
            j = i
            seen_dot = False
            while j < n and (text[j].isdigit() or text[j] == "."):
                if text[j] == ".":
                    if seen_dot:
                        raise ExprError("malformed number")
                    seen_dot = True
                j += 1
            word = text[i:j]
            if word == ".":
                raise ExprError("malformed number")
            tokens.append(("num", word))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i
            while j < n and (text[j].isalnum() or text[j] == "_"):
                j += 1
            tokens.append(("name", text[i:j]))
            i = j
            continue
        raise ExprError(f"unexpected character {ch!r}")
    return tokens


class _Parser:
    def __init__(self, text: str):
        self.tokens = _tokenize(text)
        self.pos = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def parse(self) -> Node:
        if not self.tokens:
            raise ExprError("empty expression")
        node = self.expr()
        if self.pos != len(self.tokens):
            raise ExprError("unexpected trailing tokens")
        return node

    def expr(self) -> Node:
        node = self.term()
        while (t := self.peek()) and t[0] in "+-":
            op = self.take()[0]
            node = Bin(op, node, self.term())
        return node

    def term(self) -> Node:
        node = self.factor()
        while (t := self.peek()) and t[0] in "*/":
            op = self.take()[0]
            node = Bin(op, node, self.factor())
        return node

    def factor(self) -> Node:
        t = self.peek()
        if t is None:
            raise ExprError("unexpected end of expression")
        if t[0] == "-":
            self.take()
            return Neg(self.factor())
        if t[0] == "+":
            self.take()
            return self.factor()
        return self.atom()

    def atom(self) -> Node:
        t = self.peek()
        if t is None:
            raise ExprError("unexpected end of expression")
        kind, val = t
        if kind == "num":
            self.take()
            try:
                number = float(val)
            except ValueError:
                raise ExprError("malformed number") from None
            if not math.isfinite(number):
                raise ExprError("numbers must be finite")
            return Num(number)
        if kind == "(":
            self.take()
            node = self.expr()
            self.expect(")")
            return node
        if kind == "name":
            self.take()
            if val == "coalesce":
                return self.call()
            return Ref(val)
        raise ExprError(f"unexpected token {val!r}")

    def call(self) -> Node:
        self.expect("(")
        args = [self.expr()]
        while True:
            t = self.peek()
            if t is None:
                raise ExprError("unterminated coalesce call")
            if t[0] == ")":
                self.take()
                break
            if t[0] != ",":
                raise ExprError("expected ',' or ')' in coalesce")
            self.take()
            args.append(self.expr())
        return Coalesce(tuple(args))

    def expect(self, kind: str) -> None:
        t = self.peek()
        if t is None or t[0] != kind:
            raise ExprError(f"expected {kind!r}")
        self.take()


def parse(text: object, known: set[str]) -> Node:
    if not isinstance(text, str) or not text.strip():
        raise ExprError("expression must be a non-empty string")
    node = _Parser(text).parse()
    _check_names(node, known)
    return node


def _check_names(node: Node, known: set[str]) -> None:
    if isinstance(node, Num):
        return
    if isinstance(node, Ref):
        if node.name not in known:
            raise ExprError(f"unknown grid name {node.name!r}")
        return
    if isinstance(node, Bin):
        _check_names(node.left, known)
        _check_names(node.right, known)
    elif isinstance(node, Neg):
        _check_names(node.operand, known)
    elif isinstance(node, Coalesce):
        for arg in node.args:
            _check_names(arg, known)
