"""Seeded phased read/write workload generation."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Operation:
    kind: str
    key: str
    value_bytes: int = 0

    def __post_init__(self) -> None:
        if self.kind not in {"put", "get"}:
            raise ValueError("kind must be put or get")
        if not self.key:
            raise ValueError("key must be non-empty")
        if self.kind == "put" and self.value_bytes <= 0:
            raise ValueError("put value_bytes must be positive")
        if self.kind == "get" and self.value_bytes != 0:
            raise ValueError("get cannot carry value bytes")


@dataclass(frozen=True, slots=True)
class WorkloadSpec:
    operations: int = 10_000
    key_count: int = 2_000
    seed: int = 2026
    read_ratio: float = 0.25
    phases: int = 4
    hot_fraction: float = 0.1
    hot_probability: float = 0.75
    min_value_bytes: int = 64
    max_value_bytes: int = 1024

    def validate(self) -> None:
        if self.operations <= 0:
            raise ValueError("operations must be positive")
        if self.key_count < 2:
            raise ValueError("key_count must be at least two")
        if not 0 <= self.read_ratio < 1:
            raise ValueError("read_ratio must be in [0, 1)")
        if not 1 <= self.phases <= self.operations:
            raise ValueError("phases must be between one and operations")
        if not 0 < self.hot_fraction <= 1:
            raise ValueError("hot_fraction must be in (0, 1]")
        if not 0 <= self.hot_probability <= 1:
            raise ValueError("hot_probability must be in [0, 1]")
        if self.min_value_bytes <= 0 or self.max_value_bytes < self.min_value_bytes:
            raise ValueError("invalid value-size range")


def generate_workload(spec: WorkloadSpec) -> list[Operation]:
    spec.validate()
    rng = random.Random(spec.seed)
    keys = [f"key-{index:06d}" for index in range(spec.key_count)]
    hot_count = max(1, round(spec.key_count * spec.hot_fraction))
    phase_length = math.ceil(spec.operations / spec.phases)
    phase_keys: list[tuple[list[str], list[str]]] = []
    for phase in range(spec.phases):
        offset = phase * hot_count % spec.key_count
        hot = [keys[(offset + index) % spec.key_count] for index in range(hot_count)]
        hot_set = set(hot)
        phase_keys.append((hot, [key for key in keys if key not in hot_set]))
    operations: list[Operation] = []
    for sequence in range(spec.operations):
        phase = min(sequence // phase_length, spec.phases - 1)
        hot, cold = phase_keys[phase]
        pool = hot if rng.random() < spec.hot_probability or not cold else cold
        key = pool[rng.randrange(len(pool))]
        if rng.random() < spec.read_ratio:
            operations.append(Operation("get", key))
        else:
            size = rng.randint(spec.min_value_bytes, spec.max_value_bytes)
            operations.append(Operation("put", key, size))
    return operations
