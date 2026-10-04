"""Deterministic leveled and size-tiered compaction selection."""

from __future__ import annotations

from typing import Protocol

from .models import CompactionPlan, SSTable


Levels = tuple[tuple[SSTable, ...], ...]


def _overlaps(table: SSTable, first: str, last: str) -> bool:
    return bool(table.entries) and table.min_key <= last and first <= table.max_key


class CompactionPolicy(Protocol):
    name: str

    def pick(self, levels: Levels, reserved: frozenset[int]) -> CompactionPlan | None: ...


class LeveledPolicy:
    """Some-to-some leveled compaction with range-overlap selection."""

    name = "leveled"

    def __init__(
        self,
        *,
        l0_trigger: int = 4,
        base_level_bytes: int = 256 * 1024,
        level_ratio: int = 8,
    ) -> None:
        if l0_trigger < 2:
            raise ValueError("l0_trigger must be at least two")
        if base_level_bytes <= 0:
            raise ValueError("base_level_bytes must be positive")
        if level_ratio < 2:
            raise ValueError("level_ratio must be at least two")
        self.l0_trigger = l0_trigger
        self.base_level_bytes = base_level_bytes
        self.level_ratio = level_ratio

    def pick(self, levels: Levels, reserved: frozenset[int]) -> CompactionPlan | None:
        available_l0 = tuple(table for table in levels[0] if table.identifier not in reserved)
        if len(available_l0) >= self.l0_trigger:
            selected = available_l0
            first = min(table.min_key for table in selected if table.entries)
            last = max(table.max_key for table in selected if table.entries)
            overlaps = tuple(
                table
                for table in levels[1]
                if table.identifier not in reserved and _overlaps(table, first, last)
            )
            return CompactionPlan(
                tuple(table.identifier for table in selected + overlaps), 1, "l0-run-count"
            )
        for level in range(1, len(levels) - 1):
            available = tuple(table for table in levels[level] if table.identifier not in reserved)
            target_bytes = self.base_level_bytes * (self.level_ratio ** (level - 1))
            if sum(table.storage_bytes for table in available) <= target_bytes or not available:
                continue
            selected = available[0]
            overlaps = tuple(
                table
                for table in levels[level + 1]
                if table.identifier not in reserved
                and _overlaps(table, selected.min_key, selected.max_key)
            )
            return CompactionPlan(
                (selected.identifier,) + tuple(table.identifier for table in overlaps),
                level + 1,
                f"level-{level}-bytes",
            )
        return None


class TieredPolicy:
    """Size-tiered runs: merge a fanout of peer runs into the next level."""

    name = "tiered"

    def __init__(self, *, fanout: int = 4) -> None:
        if fanout < 2:
            raise ValueError("fanout must be at least two")
        self.fanout = fanout

    def pick(self, levels: Levels, reserved: frozenset[int]) -> CompactionPlan | None:
        for level in range(len(levels) - 1):
            available = tuple(table for table in levels[level] if table.identifier not in reserved)
            if len(available) >= self.fanout:
                selected = available[: self.fanout]
                return CompactionPlan(
                    tuple(table.identifier for table in selected), level + 1, f"tier-{level}-fanout"
                )
        return None
