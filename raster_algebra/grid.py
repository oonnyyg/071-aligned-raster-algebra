"""Grid loading and structural validation."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Grid:
    name: str
    x: int          # origin column coordinate (left edge of first cell)
    y: int          # origin row coordinate (top edge of first cell)
    cell: int       # cell width (positive)
    data: tuple[tuple[float | None, ...], ...]

    @property
    def cols(self) -> int:
        return len(self.data[0])

    @property
    def rows(self) -> int:
        return len(self.data)

    def get(self, col: int, row: int) -> float | None:
        """Value at aligned cell coordinates; None outside the grid."""
        c = (col - self.x) // self.cell
        r = (row - self.y) // self.cell
        if 0 <= c < self.cols and 0 <= r < self.rows:
            return self.data[r][c]
        return None


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def load_grids(raw_grids: object) -> dict[str, Grid]:
    if not isinstance(raw_grids, dict) or not raw_grids:
        raise ValueError("grids must be a non-empty object")
    grids: dict[str, Grid] = {}
    for name, spec in raw_grids.items():
        if not isinstance(name, str) or not name:
            raise ValueError("grid names must be non-empty strings")
        grids[name] = _load_one(name, spec)
    cell = next(iter(grids.values())).cell
    for g in grids.values():
        if g.cell != cell:
            raise ValueError(f"grid {g.name!r} cell width differs")
        if (g.x - grids[next(iter(grids))].x) % cell != 0 or (
            g.y - grids[next(iter(grids))].y
        ) % cell != 0:
            raise ValueError(f"grid {g.name!r} origin is not aligned to cell width")
    return grids


def _load_one(name: str, spec: object) -> Grid:
    if not isinstance(spec, dict):
        raise ValueError(f"grid {name!r} must be an object")
    x, y = spec.get("x"), spec.get("y")
    cell = spec.get("cell")
    matrix = spec.get("data")
    if not _is_int(x) or not _is_int(y):
        raise ValueError(f"grid {name!r}: x and y must be integers")
    if not _is_int(cell) or cell <= 0:
        raise ValueError(f"grid {name!r}: cell must be a positive integer")
    if not isinstance(matrix, list) or not matrix:
        raise ValueError(f"grid {name!r}: data must be a non-empty matrix")
    if not all(isinstance(row, list) for row in matrix):
        raise ValueError(f"grid {name!r}: each row must be a list")
    width = len(matrix[0])
    if width == 0 or any(len(row) != width for row in matrix):
        raise ValueError(f"grid {name!r}: empty or ragged rows")
    checked: list[tuple[float | None, ...]] = []
    for row in matrix:
        out_row: list[float | None] = []
        for v in row:
            if v is None:
                out_row.append(None)
            elif isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"grid {name!r}: cells must be numbers or null")
            else:
                fv = float(v)
                if not math.isfinite(fv):
                    raise ValueError(f"grid {name!r}: cells must be finite")
                out_row.append(fv)
        checked.append(tuple(out_row))
    return Grid(name, x, y, cell, tuple(checked))
