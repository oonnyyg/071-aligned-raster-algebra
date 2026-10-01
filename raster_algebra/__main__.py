"""Command line entry point: ``python -m raster_algebra TASK.json RESULT.json``."""

from __future__ import annotations

import argparse
import json
import sys

from .grid import TaskError
from .task import load_task_file, run_task


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m raster_algebra",
        description="Run aligned raster map algebra from a JSON task file.",
    )
    parser.add_argument("task", help="path to the input JSON task file")
    parser.add_argument("output", help="path where the JSON result is written")
    args = parser.parse_args(argv)

    try:
        task = load_task_file(args.task)
        result = run_task(task)
    except TaskError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except OSError as exc:
        print(f"error: cannot write result file: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
