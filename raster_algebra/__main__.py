"""CLI: python -m raster_algebra INPUT.json OUTPUT.json.

Reads a task JSON document, runs aligned raster algebra, and writes the
result JSON. On any invalid task the process exits non-zero and no output
file is created or modified.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

from .engine import TaskError, run_task


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python -m raster_algebra INPUT.json OUTPUT.json",
              file=sys.stderr)
        return 2
    in_path, out_path = args
    try:
        with open(in_path, "r", encoding="utf-8") as fh:
            task = json.load(fh)
        result = run_task(task)
    except (OSError, json.JSONDecodeError, TaskError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    out_dir = os.path.dirname(os.path.abspath(out_path))
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=out_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(result, fh, allow_nan=False, indent=2)
            fh.write("\n")
        os.replace(tmp, out_path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
