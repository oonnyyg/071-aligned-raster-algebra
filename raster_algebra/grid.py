"""Grid validation, alignment and extent computation."""

from __future__ import annotations

import math
from dataclasses import dataclass


class TaskError(ValueError):
    """Raised for any invalid task input."""


@dataclass(frozen=True)
class Grid:
    """A rectangular raster with an integer origin and a positive cell size."""

    name: str
    origin_x: int
    origin_y: int
    cell_size: int
    data: tuple[tuple[float | None, ...], ...]

    @property
    def rows(self) -> int:
        return len(self.data)

    @property
    def cols(self) -> int:
        return len(self.data[0])

    def value_at(self, col_index: int, row_index: int) -> float | None:
        """Return the value at common-grid column/row indices; outside is null."""
        local_col = col_index - (self.origin_x // self.cell_size)
        local_row = row_index - (self.origin_y // self.cell_size)
        if 0 <= local_col < self.cols and 0 <= local_row < self.rows:
            return self.data[local_row][local_col]
        return None


def _is_real_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def parse_grid(name: object, raw: object, common_cell_size: int | None):
    """Validate one grid object; return (Grid, cell_size)."""
    if not isinstance(name, str) or not name:
        raise TaskError("grid names must be non-empty strings")
    if not isinstance(raw, dict):
        raise TaskError(f"grid {name!r}: definition must be an object")

    origin = raw.get("origin")
    if not isinstance(origin, (list, tuple)) or len(origin) != 2:
        raise TaskError(f"grid {name!r}: origin must be [x, y]")
    origin_x, origin_y = origin
    if not isinstance(origin_x, int) or isinstance(origin_x, bool):
        raise TaskError(f"grid {name!r}: origin x must be an integer")
    if not isinstance(origin_y, int) or isinstance(origin_y, bool):
        raise TaskError(f"grid {name!r}: origin y must be an integer")

    cell_size = raw.get("cell_size")
    if not isinstance(cell_size, int) or isinstance(cell_size, bool) or cell_size <= 0:
        raise TaskError(f"grid {name!r}: cell_size must be a positive integer")
    if common_cell_size is not None and cell_size != common_cell_size:
        raise TaskError(
            f"grid {name!r}: cell_size {cell_size} differs from {common_cell_size}"
        )

    data = raw.get("data")
    if not isinstance(data, list) or len(data) == 0:
        raise TaskError(f"grid {name!r}: data must be a non-empty matrix")
    width: int | None = None
    checked_rows: list[tuple[float | None, ...]] = []
    for row_index, row in enumerate(data):
        if not isinstance(row, list) or len(row) == 0:
            raise TaskError(f"grid {name!r}: row {row_index} must be a non-empty list")
        if width is None:
            width = len(row)
        elif len(row) != width:
            raise TaskError(f"grid {name!r}: ragged row {row_index}")
        checked: list[float | None] = []
        for cell in row:
            if cell is None:
                checked.append(None)
            elif _is_real_finite_number(cell):
                checked.append(float(cell))
            else:
                raise TaskError(
                    f"grid {name!r}: cell at row {row_index} "
                    "is not a finite number or null"
                )
        checked_rows.append(tuple(checked))

    return (
        Grid(name, origin_x, origin_y, cell_size, tuple(checked_rows)),
        cell_size,
    )


def check_alignment(grids: list[Grid], cell_size: int) -> None:
    """Reject origins that do not lie on the shared cell lattice."""
    for grid in grids:
        if grid.origin_x % cell_size != 0 or grid.origin_y % cell_size != 0:
            raise TaskError(
                f"grid {grid.name!r}: origin ({grid.origin_x}, {grid.origin_y}) "
                f"is not a multiple of cell_size {cell_size}"
            )


@dataclass(frozen=True)
class Extent:
    """Output extent in common-grid column/row index space."""

    origin_x: int
    origin_y: int
    cols: int
    rows: int


def compute_extent(grids: list[Grid], cell_size: int, mode: str) -> Extent:
    """Compute the intersection or union (minimum bounding box) extent."""
    xs = [g.origin_x for g in grids]
    ys = [g.origin_y for g in grids]
    rights = [g.origin_x + g.cols * cell_size for g in grids]
    bottoms = [g.origin_y + g.rows * cell_size for g in grids]

    if mode == "union":
        min_x, min_y = min(xs), min(ys)
        max_x, max_y = max(rights), max(bottoms)
    elif mode == "intersection":
        min_x, min_y = max(xs), max(ys)
        max_x, max_y = min(rights), min(bottoms)
        if min_x >= max_x or min_y >= max_y:
            raise TaskError("grids have no overlapping extent; intersection is empty")
    else:
        raise TaskError(
            f"unknown extent mode {mode!r}; use 'intersection' or 'union'"
        )

    cols = (max_x - min_x) // cell_size
    rows = (max_y - min_y) // cell_size
    return Extent(min_x, min_y, cols, rows)
