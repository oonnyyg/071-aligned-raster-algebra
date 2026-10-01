"""Task loading, per-cell computation, statistics and result assembly."""

from __future__ import annotations

import json

from .evaluate import CellEvaluator
from .expr import parse_expression
from .grid import (
    Extent,
    Grid,
    TaskError,
    check_alignment,
    compute_extent,
    parse_grid,
)


def _load_grids(raw_grids: object) -> tuple[dict[str, Grid], int]:
    if not isinstance(raw_grids, dict) or not raw_grids:
        raise TaskError("'grids' must be a non-empty object of named grids")
    grids: dict[str, Grid] = {}
    cell_size: int | None = None
    for name, raw in raw_grids.items():
        grid, cell_size = parse_grid(name, raw, cell_size)
        if grid.name in grids:  # pragma: no cover - dict keys are unique
            raise TaskError(f"duplicate grid name {grid.name!r}")
        if grid.name == "coalesce":
            raise TaskError("grid name 'coalesce' is reserved")
        grids[grid.name] = grid
    assert cell_size is not None
    return grids, cell_size


def run_task(task: object) -> dict:
    """Validate a task object and compute the result object."""
    if not isinstance(task, dict):
        raise TaskError("task must be a JSON object")

    grids, cell_size = _load_grids(task.get("grids"))
    grid_list = list(grids.values())
    check_alignment(grid_list, cell_size)

    mode = task.get("mode", "intersection")
    if not isinstance(mode, str):
        raise TaskError("'mode' must be 'intersection' or 'union'")
    extent = compute_extent(grid_list, cell_size, mode)

    root = parse_expression(task.get("expression"), set(grids))
    evaluator = CellEvaluator(root, grids)

    return _render(evaluator, extent, cell_size)


def _render(
    evaluator: CellEvaluator, extent: Extent, cell_size: int
) -> dict:
    base_col = extent.origin_x // cell_size
    base_row = extent.origin_y // cell_size

    output: list[list[float | None]] = []
    invalid_cells: list[list[int]] = []
    valid_values: list[float] = []

    for row_offset in range(extent.rows):
        out_row: list[float | None] = []
        for col_offset in range(extent.cols):
            value, invalid = evaluator.evaluate(
                base_col + col_offset, base_row + row_offset
            )
            if value is None:
                out_row.append(None)
                if invalid:
                    invalid_cells.append([row_offset, col_offset])
            else:
                out_row.append(value)
                valid_values.append(value)
        output.append(out_row)

    if valid_values:
        stats = {
            "valid_count": len(valid_values),
            "null_count": extent.rows * extent.cols - len(valid_values),
            "min": min(valid_values),
            "max": max(valid_values),
            "mean": sum(valid_values) / len(valid_values),
        }
    else:
        stats = {
            "valid_count": 0,
            "null_count": extent.rows * extent.cols,
            "min": None,
            "max": None,
            "mean": None,
        }

    return {
        "origin": [extent.origin_x, extent.origin_y],
        "cell_size": cell_size,
        "data": output,
        "invalid_cells": invalid_cells,
        "stats": stats,
    }


def load_task_file(path: str) -> object:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise TaskError(f"cannot read task file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise TaskError(f"invalid JSON: {exc}") from exc
