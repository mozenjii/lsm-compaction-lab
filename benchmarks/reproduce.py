"""End-to-end policy comparison across three deterministic operating regimes."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lsmlab.experiment import ExperimentConfig, run_experiment  # noqa: E402


def main() -> int:
    base = ExperimentConfig(
        operations=8_000,
        key_count=1_500,
        seed=2026,
        read_ratio=0.25,
        phases=4,
        memtable_bytes=24 * 1024,
        background_bytes_per_tick=12 * 1024,
        base_level_bytes=192 * 1024,
    )
    scenarios = {
        "balanced": base,
        "overwrite_heavy": replace(base, key_count=400, read_ratio=0.1, seed=2027),
        "constrained_background": replace(
            base,
            operations=5_000,
            memtable_bytes=8 * 1024,
            background_bytes_per_tick=768,
            l0_slowdown_trigger=4,
            l0_stop_trigger=6,
            max_backlog_bytes=96 * 1024,
            seed=2028,
        ),
    }
    for name, config in scenarios.items():
        payload = run_experiment(config).as_dict()
        payload["scenario"] = name
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
