import json
import os
import subprocess
import sys
from pathlib import Path


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    root = str(Path(__file__).parents[1])
    environment["PYTHONPATH"] = root + os.pathsep + environment.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "lsmlab.cli", *arguments],
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_emits_byte_stable_json():
    arguments = ("--operations", "400", "--key-count", "80", "--seed", "11", "--json")
    first = run_cli(*arguments)
    second = run_cli(*arguments)
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    assert [row["policy"] for row in json.loads(first.stdout)["results"]] == ["leveled", "tiered"]


def test_cli_rejects_invalid_capacity():
    result = run_cli("--operations", "0")
    assert result.returncode != 0
    assert "positive" in result.stderr
