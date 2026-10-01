"""Tests for aligned raster algebra."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import unittest

from raster_algebra.expr import parse_expression
from raster_algebra.grid import TaskError
from raster_algebra.task import run_task


def grid(origin, data, cell_size=10):
    return {"origin": origin, "cell_size": cell_size, "data": data}


class AlignmentTests(unittest.TestCase):
    def test_negative_origin_union_aligned(self):
        task = {
            "mode": "union",
            "grids": {
                "a": grid([-20, -10], [[1, 2], [3, 4]]),
                "b": grid([0, 0], [[10]]),
            },
            "expression": "coalesce(a, b)",
        }
        result = run_task(task)
        self.assertEqual(result["origin"], [-20, -10])
        self.assertEqual(result["data"], [[1.0, 2.0, None], [3.0, 4.0, 10.0]])
        self.assertEqual(result["stats"]["valid_count"], 5)
        self.assertEqual(result["stats"]["null_count"], 1)

    def test_intersection_offset_grids(self):
        task = {
            "mode": "intersection",
            "grids": {
                "a": grid([0, 0], [[1, 2], [3, 4]]),
                "b": grid([10, 10], [[10, 20], [30, 40]]),
            },
            "expression": "a + b",
        }
        result = run_task(task)
        self.assertEqual(result["origin"], [10, 10])
        self.assertEqual(result["data"], [[14.0]])

    def test_misaligned_origin_rejected(self):
        task = {
            "grids": {
                "a": grid([0, 0], [[1]]),
                "b": grid([5, 0], [[2]]),
            },
            "expression": "a + b",
        }
        with self.assertRaises(TaskError):
            run_task(task)

    def test_different_cell_size_rejected(self):
        task = {
            "grids": {
                "a": grid([0, 0], [[1]], cell_size=10),
                "b": grid([0, 0], [[2]], cell_size=20),
            },
            "expression": "a + b",
        }
        with self.assertRaises(TaskError):
            run_task(task)

    def test_empty_intersection_rejected(self):
        task = {
            "mode": "intersection",
            "grids": {
                "a": grid([0, 0], [[1]]),
                "b": grid([100, 100], [[2]]),
            },
            "expression": "a",
        }
        with self.assertRaises(TaskError):
            run_task(task)

    def test_bad_matrix_shapes_rejected(self):
        for data in ([], [[]], [[1, 2], [3]], [[1, "x"]], [[True]]):
            with self.subTest(data=data):
                task = {"grids": {"a": grid([0, 0], data)}, "expression": "a"}
                with self.assertRaises(TaskError):
                    run_task(task)


class ExpressionTests(unittest.TestCase):
    def test_null_propagation_and_unary_minus(self):
        task = {
            "grids": {"a": grid([0, 0], [[1, None]])},
            "expression": "-a + 2",
        }
        result = run_task(task)
        self.assertEqual(result["data"], [[1.0, None]])

    def test_division_by_zero_recorded(self):
        task = {
            "grids": {"a": grid([0, 0], [[1, 2]])},
            "expression": "a / (a - a)",
        }
        result = run_task(task)
        self.assertEqual(result["data"], [[None, None]])
        self.assertEqual(result["invalid_cells"], [[0, 0], [0, 1]])

    def test_null_operand_not_recorded_as_invalid(self):
        task = {
            "grids": {"a": grid([0, 0], [[None]])},
            "expression": "a / 0",
        }
        result = run_task(task)
        self.assertEqual(result["data"], [[None]])
        self.assertEqual(result["invalid_cells"], [])

    def test_coalesce_fallback_short_circuits(self):
        # b/0 must never be evaluated when a is non-null.
        task = {
            "grids": {
                "a": grid([0, 0], [[7, None]]),
                "b": grid([0, 0], [[9, 3]]),
            },
            "expression": "coalesce(a, b / 0, -1)",
        }
        result = run_task(task)
        self.assertEqual(result["data"], [[7.0, -1.0]])
        # First cell: short-circuit before b/0. Second cell: b/0 is
        # evaluated but rescued by -1, so no invalid output cell recorded.
        self.assertEqual(result["invalid_cells"], [])

    def test_coalesce_all_null_records_invalid_branch(self):
        task = {
            "grids": {"a": grid([0, 0], [[None, 1]])},
            "expression": "coalesce(a / 0)",
        }
        result = run_task(task)
        self.assertEqual(result["data"], [[None, None]])
        self.assertEqual(result["invalid_cells"], [[0, 1]])

    def test_coalesce_requires_argument(self):
        with self.assertRaises(TaskError):
            parse_expression("coalesce()", set())

    def test_forbidden_syntax_rejected(self):
        for text in [
            "a.__class__",
            "a[0]",
            "foo(1)",
            "a + ",
            "(a + 1",
            "import os",
            "a and b",
            "1 ** 2",
            "a.b()",
        ]:
            with self.subTest(text=text):
                with self.assertRaises(TaskError):
                    parse_expression(text, {"a", "b"})

    def test_unknown_name_rejected(self):
        with self.assertRaises(TaskError):
            parse_expression("a + z", {"a"})


class OrderingAndStatsTests(unittest.TestCase):
    def test_result_independent_of_grid_order(self):
        task1 = {
            "grids": {
                "a": grid([0, 0], [[1, 2]]),
                "b": grid([10, 0], [[3, 4]]),
            },
            "expression": "a * 2 + b",
        }
        task2 = {
            "grids": {
                "b": grid([10, 0], [[3, 4]]),
                "a": grid([0, 0], [[1, 2]]),
            },
            "expression": "b + 2 * a",
        }
        self.assertEqual(run_task(task1)["data"], run_task(task2)["data"])

    def test_stats_all_null(self):
        task = {
            "grids": {"a": grid([0, 0], [[None, None]])},
            "expression": "a + 1",
        }
        stats = run_task(task)["stats"]
        self.assertEqual(stats["valid_count"], 0)
        self.assertEqual(stats["null_count"], 2)
        self.assertIsNone(stats["min"])
        self.assertIsNone(stats["max"])
        self.assertIsNone(stats["mean"])

    def test_stats_values(self):
        task = {
            "grids": {"a": grid([0, 0], [[1, 2], [3, None]])},
            "expression": "a",
        }
        stats = run_task(task)["stats"]
        self.assertEqual((stats["min"], stats["max"], stats["mean"]), (1.0, 3.0, 2.0))


class CliTests(unittest.TestCase):
    def test_cli_success_and_failure(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            good = tmp_path / "task.json"
            out = tmp_path / "out.json"
            good.write_text(
                json.dumps(
                    {
                        "grids": {"a": grid([0, 0], [[1]])},
                        "expression": "a + 1",
                    }
                ),
                encoding="utf-8",
            )
            proc = subprocess.run(
                [sys.executable, "-m", "raster_algebra", str(good), str(out)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["data"], [[2.0]])

            bad = tmp_path / "bad.json"
            bad.write_text(
                json.dumps({"grids": {"a": grid([0, 0], [[1]])}, "expression": "x"}),
                encoding="utf-8",
            )
            bad_out = tmp_path / "bad_out.json"
            proc = subprocess.run(
                [sys.executable, "-m", "raster_algebra", str(bad), str(bad_out)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(bad_out.exists())


if __name__ == "__main__":
    unittest.main()
