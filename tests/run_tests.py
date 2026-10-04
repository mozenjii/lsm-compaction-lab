"""Dependency-free test runner."""

from __future__ import annotations

import importlib
import inspect
import sys
import tempfile
import traceback
from pathlib import Path


ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    failures: list[str] = []
    executed = 0
    for path in sorted(Path(__file__).parent.glob("test_*.py")):
        try:
            module = importlib.import_module(f"tests.{path.stem}")
        except Exception:
            failures.append(f"{path.stem} import\n{traceback.format_exc()}")
            continue
        for name, function in inspect.getmembers(module, inspect.isfunction):
            if not name.startswith("test_"):
                continue
            executed += 1
            try:
                if "tmp_path" in inspect.signature(function).parameters:
                    with tempfile.TemporaryDirectory() as directory:
                        function(Path(directory))
                else:
                    function()
            except Exception:
                failures.append(f"{path.stem}.{name}\n{traceback.format_exc()}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        print(f"FAILED: {len(failures)} failures across {executed} tests", file=sys.stderr)
        return 1
    print(f"PASS: {executed} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
