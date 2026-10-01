import json
import subprocess
import sys
import unittest
from pathlib import Path

from raster_algebra.engine import TaskError, run_task


def grid(x, y, cell, data):
    return {"x": x, "y": y, "cell": cell, "data": data}


class AlignmentTests(unittest.TestCase):
    def test_negative_origins_intersection(self):
        task = {
            "grids": {
                "a": grid(-4, -2, 2, [[1, 2], [3, 4]]),
                "b": grid(-2, 0, 2, [[10, 20], [30, 40]]),
            },
            "expression": "a + b",
            "extent": "intersection",
        }
        r = run_task(task)
        # overlap cell: a's column1,row1 == 4 ; b's column0,row0 == 10
        self.assertEqual((r["x"], r["y"]), (-2, 0))
        self.assertEqual(r["data"], [[14]])

    def test_union_bounding_rectangle_with_nulls(self):
        task = {
            "grids": {
                "a": grid(0, 0, 1, [[1, 2], [3, 4]]),
                "b": grid(1, 1, 1, [[9]]),
            },
            "expression": "a + b",
            "extent": "union",
        }
        r = run_task(task)
        self.assertEqual((r["x"], r["y"]), (0, 0))
        self.assertEqual(r["data"], [[None, None], [None, 13]])

    def test_order_independent(self):
        g = {
            "a": grid(0, 0, 2, [[1, 2], [3, 4]]),
            "b": grid(2, 0, 2, [[5, 6], [7, 8]]),
        }
        r1 = run_task({"grids": g, "expression": "a + b", "extent": "union"})
        r2 = run_task({"grids": dict(reversed(list(g.items()))),
                       "expression": "a + b", "extent": "union"})
        self.assertEqual(r1["data"], r2["data"])
        self.assertEqual(r1["data"], [[None, 7, None], [None, 11, None]])

    def test_misaligned_origin_rejected(self):
        with self.assertRaises(ValueError):
            run_task({"grids": {
                "a": grid(0, 0, 2, [[1]]),
                "b": grid(1, 0, 2, [[1]])}, "expression": "a"})

    def test_different_cell_width_rejected(self):
        with self.assertRaises(ValueError):
            run_task({"grids": {
                "a": grid(0, 0, 2, [[1]]),
                "b": grid(0, 0, 3, [[1]])}, "expression": "a"})

    def test_empty_and_ragged_and_bad_values(self):
        with self.assertRaises(ValueError):
            run_task({"grids": {"a": grid(0, 0, 1, [])}, "expression": "a"})
        with self.assertRaises(ValueError):
            run_task({"grids": {"a": grid(0, 0, 1, [[1], [2, 3]])},
                      "expression": "a"})
        with self.assertRaises(ValueError):
            run_task({"grids": {"a": grid(0, 0, 1, [["x"]])},
                      "expression": "a"})
        with self.assertRaises(ValueError):
            run_task({"grids": {"a": grid(0, 0, 1, [[float("inf")]])},
                      "expression": "a"})

    def test_empty_intersection_rejected(self):
        with self.assertRaises(TaskError):
            run_task({"grids": {
                "a": grid(0, 0, 1, [[1]]),
                "b": grid(5, 5, 1, [[1]])}, "expression": "a + b"})


class ExpressionTests(unittest.TestCase):
    def test_null_propagation_and_stats(self):
        r = run_task({"grids": {"a": grid(0, 0, 1, [[1, None], [None, 4]]),
                                "b": grid(0, 0, 1, [[10, 20], [30, None]])},
                      "expression": "a + b"})
        self.assertEqual(r["data"], [[11, None], [None, None]])
        self.assertEqual(r["stats"], {"valid": 1, "null": 3, "min": 11,
                                      "max": 11, "mean": 11})

    def test_all_null_stats(self):
        r = run_task({"grids": {"a": grid(0, 0, 1, [[None]])},
                      "expression": "a + 1"})
        self.assertEqual(r["stats"], {"valid": 0, "null": 1, "min": None,
                                      "max": None, "mean": None})

    def test_unary_minus_precedence_and_parens(self):
        r = run_task({"grids": {"a": grid(0, 0, 1, [[6]])},
                      "expression": "-a * (1 + 1)"})
        self.assertEqual(r["data"], [[-12]])

    def test_coalesce_fallback(self):
        r = run_task({"grids": {
            "a": grid(0, 0, 1, [[None, 5]]),
            "b": grid(0, 0, 1, [[7, 8]])},
            "expression": "coalesce(a, b, 99)"})
        self.assertEqual(r["data"], [[7, 5]])

    def test_coalesce_short_circuits_unevaluated_branch(self):
        # b is 0: division is never evaluated because a is non-null first.
        r = run_task({"grids": {
            "a": grid(0, 0, 1, [[4, None]]),
            "b": grid(0, 0, 1, [[0, 2]])},
            "expression": "coalesce(a, 1/b, 0)"})
        self.assertEqual(r["data"], [[4, 0.5]])
        self.assertEqual(r["error_cells"], [])

    def test_division_by_zero_recorded_and_null(self):
        r = run_task({"grids": {"a": grid(0, 0, 1, [[1, 0]])},
                      "expression": "1 / a"})
        self.assertEqual(r["data"], [[1, None]])
        self.assertEqual(r["error_cells"], [[1, 0]])

    def test_non_finite_overflow_recorded(self):
        big = sys.float_info.max
        r = run_task({"grids": {"a": grid(0, 0, 1, [[big]])},
                      "expression": "a * a"})
        self.assertEqual(r["data"], [[None]])
        self.assertEqual(r["error_cells"], [[0, 0]])

    def test_both_operands_evaluated_even_after_error(self):
        # coalesce inside right operand still evaluated by binary op,
        # so a second div-by-zero is also reported.
        r = run_task({"grids": {
            "a": grid(0, 0, 1, [[0]]),
            "b": grid(0, 0, 1, [[0]])},
            "expression": "1/a + 1/b"})
        self.assertEqual(r["error_cells"], [[0, 0]])

    def test_illegal_expressions_rejected(self):
        g = {"grids": {"a": grid(0, 0, 1, [[1]])}}
        for e in ["a.b", "a[0]", "foo(a)", "import x", "a +", "(a",
                  "a ) b", "coalesce()", "a..2", "1e3", "NaN", ""]:
            with self.subTest(e=e):
                with self.assertRaises(ValueError):
                    run_task({**g, "expression": e})

    def test_unknown_name_rejected(self):
        with self.assertRaises(ValueError):
            run_task({"grids": {"a": grid(0, 0, 1, [[1]])},
                      "expression": "a + z"})


class CliTests(unittest.TestCase):
    def test_cli_success_and_failure(self):
        root = Path(__file__).resolve().parents[1]
        task = {"grids": {"a": grid(0, 0, 1, [[1, None]]),
                          "b": grid(0, 0, 1, [[2, 3]])},
                "expression": "coalesce(a, b) * 2", "extent": "intersection"}
        inp = root / "task.json"
        outp = root / "result.json"
        inp.write_text(json.dumps(task), encoding="utf-8")
        try:
            p = subprocess.run([sys.executable, "-m", "raster_algebra",
                                str(inp), str(outp)], cwd=root,
                               capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            result = json.loads(outp.read_text(encoding="utf-8"))
            self.assertEqual(result["data"], [[2, 6]])

            bad = {"grids": {"a": grid(0, 0, 1, [[1]])}, "expression": "x"}
            inp.write_text(json.dumps(bad), encoding="utf-8")
            p = subprocess.run([sys.executable, "-m", "raster_algebra",
                                str(inp), str(outp)], cwd=root,
                               capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            # stale successful result must remain untouched
            self.assertEqual(json.loads(outp.read_text(encoding="utf-8"))["data"],
                             [[2, 6]])
        finally:
            inp.unlink(missing_ok=True)
            outp.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
