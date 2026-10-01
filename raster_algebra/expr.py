"""Safe arithmetic expression parser for map algebra.

Grammar (no attribute access, subscripts, or calls other than coalesce)::

    expr   := term (('+' | '-') term)*
    term   := factor (('*' | '/') factor)*
    factor := ('+' | '-') factor | primary
    primary:= NUMBER | NAME | 'coalesce' '(' expr (',' expr)* ')' | '(' expr ')'

The parser is hand-written so no expression-supplied code can ever execute.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .grid import TaskError


class Node:
    """Base class for expression tree nodes."""


@dataclass(frozen=True)
class Number(Node):
    value: float


@dataclass(frozen=True)
class Name(Node):
    name: str


@dataclass(frozen=True)
class Unary(Node):
    op: str
    operand: Node


@dataclass(frozen=True)
class Binary(Node):
    op: str
    left: Node
    right: Node


@dataclass(frozen=True)
class Coalesce(Node):
    arguments: tuple[Node, ...]


_KEYWORDS = frozenset({"coalesce"})


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "+-*/(),":
            tokens.append((char, char))
            index += 1
            continue
        if char.isalpha() or char == "_":
            start = index
            index += 1
            while index < length and (text[index].isalnum() or text[index] == "_"):
                index += 1
            word = text[start:index]
            tokens.append(("NAME", word))
            continue
        if char.isdigit() or char == ".":
            start = index
            seen_dot = False
            seen_digit = False
            while index < length:
                cur = text[index]
                if cur.isdigit():
                    seen_digit = True
                    index += 1
                elif cur == "." and not seen_dot:
                    seen_dot = True
                    index += 1
                else:
                    break
            word = text[start:index]
            if not seen_digit or word in {".", ".."}:
                raise TaskError(f"invalid number {word!r} in expression")
            # Reject trailing exponent / malformed forms explicitly.
            try:
                value = float(word)
            except ValueError:
                raise TaskError(f"invalid number {word!r} in expression") from None
            if not math.isfinite(value):
                raise TaskError(f"number {word!r} is not finite")
            tokens.append(("NUMBER", word))
            continue
        raise TaskError(f"unexpected character {char!r} in expression")
    tokens.append(("EOF", ""))
    return tokens


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens = _tokenize(text)
        self.pos = 0

    def _peek(self) -> tuple[str, str]:
        return self.tokens[self.pos]

    def _advance(self) -> tuple[str, str]:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def _expect(self, kind: str) -> tuple[str, str]:
        token = self._peek()
        if token[0] != kind:
            raise TaskError(
                f"expected {kind!r} but found {token[1] or token[0]!r} in expression"
            )
        return self._advance()

    def parse(self) -> Node:
        node = self._parse_expr()
        if self._peek()[0] != "EOF":
            token = self._peek()
            raise TaskError(f"unexpected token {token[1]!r} in expression")
        return node

    def _parse_expr(self) -> Node:
        node = self._parse_term()
        while self._peek()[0] in ("+", "-"):
            op = self._advance()[0]
            right = self._parse_term()
            node = Binary(op, node, right)
        return node

    def _parse_term(self) -> Node:
        node = self._parse_factor()
        while self._peek()[0] in ("*", "/"):
            op = self._advance()[0]
            right = self._parse_factor()
            node = Binary(op, node, right)
        return node

    def _parse_factor(self) -> Node:
        kind, value = self._peek()
        if kind in ("+", "-"):
            self._advance()
            return Unary(value, self._parse_factor())
        return self._parse_primary()

    def _parse_primary(self) -> Node:
        kind, value = self._peek()
        if kind == "NUMBER":
            self._advance()
            return Number(float(value))
        if kind == "(":
            self._advance()
            node = self._parse_expr()
            self._expect(")")
            return node
        if kind == "NAME":
            self._advance()
            if value in _KEYWORDS:
                if value != "coalesce":  # pragma: no cover - defensive
                    raise TaskError(f"unsupported function {value!r}")
                self._expect("(")
                arguments = [self._parse_expr()]
                while self._peek()[0] == ",":
                    self._advance()
                    arguments.append(self._parse_expr())
                self._expect(")")
                if not arguments:
                    raise TaskError("coalesce requires at least one argument")
                return Coalesce(tuple(arguments))
            return Name(value)
        raise TaskError(
            f"expected number, name or '(' but found {value or kind!r} in expression"
        )


def parse_expression(text: object, known_names: set[str]) -> Node:
    """Parse an expression string and validate every referenced name."""
    if not isinstance(text, str) or not text.strip():
        raise TaskError("expression must be a non-empty string")
    root = _Parser(text).parse()

    referenced: set[str] = set()

    def visit(node: Node) -> None:
        if isinstance(node, Number):
            return
        if isinstance(node, Name):
            referenced.add(node.name)
            return
        if isinstance(node, Unary):
            visit(node.operand)
            return
        if isinstance(node, Binary):
            visit(node.left)
            visit(node.right)
            return
        if isinstance(node, Coalesce):
            for argument in node.arguments:
                visit(argument)
            return
        raise TaskError("internal error: unknown expression node")  # pragma: no cover

    visit(root)
    unknown = sorted(referenced - known_names)
    if unknown:
        raise TaskError(f"expression references unknown grid name(s): {', '.join(unknown)}")
    return root
