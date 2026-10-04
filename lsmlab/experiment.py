"""Paired policy experiments and stable JSON reports."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .engine import Simulator, SimulatorConfig
from .models import SimulationResult
from .policies import LeveledPolicy, TieredPolicy
from .workload import WorkloadSpec, generate_workload


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    operations: int = 10_000
    key_count: int = 2_000
    seed: int = 2026
    read_ratio: float = 0.25
    phases: int = 4
    memtable_bytes: int = 32 * 1024
    background_bytes_per_tick: int = 16 * 1024
    l0_compaction_trigger: int = 4
    l0_slowdown_trigger: int = 8
    l0_stop_trigger: int = 12
    max_backlog_bytes: int = 2 * 1024 * 1024
    base_level_bytes: int = 256 * 1024
    level_ratio: int = 8
    tiered_fanout: int = 4
    max_levels: int = 5

    def validate(self) -> None:
        WorkloadSpec(
            operations=self.operations,
            key_count=self.key_count,
            seed=self.seed,
            read_ratio=self.read_ratio,
            phases=self.phases,
        ).validate()
        SimulatorConfig(
            memtable_bytes=self.memtable_bytes,
            background_bytes_per_tick=self.background_bytes_per_tick,
            l0_slowdown_trigger=self.l0_slowdown_trigger,
            l0_stop_trigger=self.l0_stop_trigger,
            max_backlog_bytes=self.max_backlog_bytes,
            max_levels=self.max_levels,
        ).validate()


@dataclass(frozen=True, slots=True)
class ExperimentReport:
    config: ExperimentConfig
    results: tuple[SimulationResult, ...]
    schema_version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "config": asdict(self.config),
            "results": [result.as_dict() for result in self.results],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n"


def run_experiment(config: ExperimentConfig) -> ExperimentReport:
    config.validate()
    workload = generate_workload(
        WorkloadSpec(
            operations=config.operations,
            key_count=config.key_count,
            seed=config.seed,
            read_ratio=config.read_ratio,
            phases=config.phases,
        )
    )
    simulator_config = SimulatorConfig(
        memtable_bytes=config.memtable_bytes,
        background_bytes_per_tick=config.background_bytes_per_tick,
        l0_slowdown_trigger=config.l0_slowdown_trigger,
        l0_stop_trigger=config.l0_stop_trigger,
        max_backlog_bytes=config.max_backlog_bytes,
        max_levels=config.max_levels,
    )
    policies = (
        LeveledPolicy(
            l0_trigger=config.l0_compaction_trigger,
            base_level_bytes=config.base_level_bytes,
            level_ratio=config.level_ratio,
        ),
        TieredPolicy(fanout=config.tiered_fanout),
    )
    results = tuple(Simulator(simulator_config, policy).run(workload) for policy in policies)
    return ExperimentReport(config, results)
