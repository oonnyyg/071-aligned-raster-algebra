"""Validate tasks, align grids, evaluate map algebra per cell."""

from __future__ import annotations

import math

from . import expr
from .grid import Grid, load_grids


class TaskError(ValueError):
    pass


def run_task(task: object) -> dict:
    if not isinstance(task, dict):
        raise TaskError("task must be a JSON object")
    grids = load_grids(task.get("grids"))
    ast = expr.parse(task.get("expression"), set(grids))
    extent = _extent(task.get("extent", "intersection"), grids)
    cell = next(iter(grids.values())).cell

    matrix: list[list[float | None]] = []
    error_cells: list[list[int]] = []
    x0, y0, cols, rows = extent
    for r in range(rows):
        out_row: list[float | None] = []
        gy = y0 + r * cell
        for c in range(cols):
            gx = x0 + c * cell
            env = {name: g.get(gx, gy) for name, g in grids.items()}
            value, bad = _eval(ast, env)
            if bad:
                if value is not None and not math.isfinite(value):
                    value = None
                error_cells.append([c, r])
            out_row.append(value)
        matrix.append(out_row)

    stats = _stats(matrix)
    return {
        "x": x0,
        "y": y0,
        "cell": cell,
        "data": matrix,
        "stats": stats,
        "error_cells": error_cells,
    }


def _extent(mode: object, grids: dict[str, Grid]) -> tuple[int, int, int, int]:
    if mode not in ("intersection", "union"):
        raise TaskError("extent must be 'intersection' or 'union'")
    cell = next(iter(grids.values())).cell
    g = next(iter(grids.values()))
    x_min, y_min = g.x, g.y
    x_max, y_max = g.x + g.cols * cell, g.y + g.rows * cell
    ix0, iy0 = x_min, y_min
    ix1, iy1 = x_max, y_max
    for g in grids.values():
        gx1, gy1 = g.x + g.cols * cell, g.y + g.rows * cell
        x_min, y_min = min(x_min, g.x), min(y_min, g.y)
        x_max, y_max = max(x_max, gx1), max(y_max, gy1)
        ix0, iy0 = max(ix0, g.x), max(iy0, g.y)
        ix1, iy1 = min(ix1, gx1), min(iy1, gy1)
    if mode == "union":
        return x_min, y_min, (x_max - x_min) // cell, (y_max - y_min) // cell
    if ix1 <= ix0 or iy1 <= iy0:
        raise TaskError("grids have no intersecting extent")
    return ix0, iy0, (ix1 - ix0) // cell, (iy1 - iy0) // cell


def _eval(node: expr.Node, env: dict[str, float | None]) -> tuple[float | None, bool]:
    """Return (value, error_flag). error_flag marks div-by-zero / non-finite."""
    if isinstance(node, expr.Num):
        return node.value, False
    if isinstance(node, expr.Ref):
        return env[node.name], False
    if isinstance(node, expr.Neg):
        v, bad = _eval(node.operand, env)
        if v is None:
            return None, bad
        return -v, bad
    if isinstance(node, expr.Coalesce):
        for arg in node.args:
            v, bad = _eval(arg, env)
            if v is not None:
                return v, bad  # stop; later branches are never evaluated
        return None, False
    lv, lb = _eval(node.left, env)
    rv, rb = _eval(node.right, env)
    if lv is None or rv is None:
        return None, lb or rb
    result = _binop(node.op, lv, rv)
    if result is None or not math.isfinite(result):
        return None, True
    return result, lb or rb


def _binop(op: str, a: float, b: float) -> float | None:
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        return None if b == 0 else a / b
    raise TaskError(f"unsupported operator {op!r}")


def _stats(matrix: list[list[float | None]]) -> dict:
    values = [v for row in matrix for v in row if v is not None]
    if not values:
        return {"valid": 0, "null": sum(len(row) for row in matrix),
                "min": None, "max": None, "mean": None}
    total = sum(values)
    return {
        "valid": len(values),
        "null": sum(len(row) for row in matrix) - len(values),
        "min": min(values),
        "max": max(values),
        "mean": total / len(values),
    }
