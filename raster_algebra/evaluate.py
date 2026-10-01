"""Per-cell expression evaluation over aligned grids."""

from __future__ import annotations

import math

from .expr import Binary, Coalesce, Name, Node, Number, Unary
from .grid import Grid


class CellEvaluator:
    """Evaluates the parsed expression for one cell at a time."""

    def __init__(self, root: Node, grids: dict[str, Grid]) -> None:
        self._root = root
        self._grids = grids

    def evaluate(self, col_index: int, row_index: int) -> tuple[float | None, bool]:
        """Return ``(value, invalid)`` for one output cell.

        ``invalid`` is True when the expression ran but produced a
        non-finite result or hit a division by zero. Null propagation
        from null operands is not counted as invalid.
        """
        return self._eval(self._root, col_index, row_index)

    def _eval(self, node: Node, col: int, row: int) -> tuple[float | None, bool]:
        if isinstance(node, Number):
            return node.value, False
        if isinstance(node, Name):
            return self._grids[node.name].value_at(col, row), False
        if isinstance(node, Unary):
            value, invalid = self._eval(node.operand, col, row)
            if value is None:
                return None, invalid
            if node.op == "-":
                return -value, invalid
            return value, invalid
        if isinstance(node, Coalesce):
            # Short-circuit: stop at the first non-null argument. An
            # arithmetic error inside an argument that is then rescued by a
            # later non-null argument does not mark the output cell invalid.
            saw_invalid = False
            for argument in node.arguments:
                value, invalid = self._eval(argument, col, row)
                saw_invalid = saw_invalid or invalid
                if value is not None:
                    return value, False
            return None, saw_invalid
        if isinstance(node, Binary):
            # Both sides are always evaluated for ordinary operators.
            left, left_invalid = self._eval(node.left, col, row)
            right, right_invalid = self._eval(node.right, col, row)
            invalid = left_invalid or right_invalid
            if left is None or right is None:
                return None, invalid
            try:
                if node.op == "+":
                    result = left + right
                elif node.op == "-":
                    result = left - right
                elif node.op == "*":
                    result = left * right
                else:
                    if right == 0.0:
                        return None, True
                    result = left / right
            except ZeroDivisionError:
                return None, True
            if not math.isfinite(result):
                return None, True
            return result, invalid
        raise AssertionError(f"unhandled node type {type(node)!r}")  # pragma: no cover
