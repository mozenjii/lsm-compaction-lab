"""Immutable logical records, SSTables, compaction plans, and results."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable


ENTRY_OVERHEAD_BYTES = 16


@dataclass(frozen=True, slots=True)
class Entry:
    key: str
    sequence: int
    value_bytes: int
    tombstone: bool = False

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("key must be non-empty")
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if self.value_bytes < 0:
            raise ValueError("value_bytes must be non-negative")
        if self.tombstone and self.value_bytes:
            raise ValueError("tombstones cannot carry value bytes")

    @property
    def storage_bytes(self) -> int:
        return len(self.key.encode("utf-8")) + self.value_bytes + ENTRY_OVERHEAD_BYTES


@dataclass(frozen=True, slots=True)
class SSTable:
    identifier: int
    level: int
    entries: tuple[Entry, ...]
    storage_bytes: int
    min_key: str
    max_key: str

    @classmethod
    def build(cls, identifier: int, level: int, entries: Iterable[Entry]) -> "SSTable":
        if identifier <= 0:
            raise ValueError("table identifier must be positive")
        if level < 0:
            raise ValueError("level must be non-negative")
        ordered = tuple(sorted(entries, key=lambda entry: entry.key))
        return cls(
            identifier=identifier,
            level=level,
            entries=ordered,
            storage_bytes=sum(entry.storage_bytes for entry in ordered),
            min_key=ordered[0].key if ordered else "",
            max_key=ordered[-1].key if ordered else "",
        )

    def might_contain(self, key: str) -> bool:
        return bool(self.entries) and self.min_key <= key <= self.max_key

    def find(self, key: str) -> Entry | None:
        low = 0
        high = len(self.entries)
        while low < high:
            middle = (low + high) // 2
            candidate = self.entries[middle]
            if candidate.key < key:
                low = middle + 1
            else:
                high = middle
        if low < len(self.entries) and self.entries[low].key == key:
            return self.entries[low]
        return None


def merge_tables(
    identifier: int,
    level: int,
    tables: Iterable[SSTable],
    *,
    drop_tombstones: bool = False,
) -> SSTable:
    newest: dict[str, Entry] = {}
    for table in tables:
        for entry in table.entries:
            previous = newest.get(entry.key)
            if previous is None or entry.sequence > previous.sequence:
                newest[entry.key] = entry
    entries = (
        entry for entry in newest.values() if not (drop_tombstones and entry.tombstone)
    )
    return SSTable.build(identifier, level, entries)


@dataclass(frozen=True, slots=True)
class CompactionPlan:
    input_ids: tuple[int, ...]
    target_level: int
    reason: str


@dataclass(frozen=True, slots=True)
class SimulationResult:
    policy: str
    operations: int
    puts: int
    reads: int
    read_hits: int
    table_probes: int
    logical_write_bytes: int
    flush_write_bytes: int
    compaction_input_bytes: int
    compaction_output_bytes: int
    compaction_input_by_target_level: tuple[int, ...]
    compaction_output_by_target_level: tuple[int, ...]
    resident_bytes: int
    live_bytes: int
    peak_resident_bytes: int
    peak_space_amplification: float
    peak_backlog_bytes: int
    pending_compaction_bytes: int
    pending_compactions: int
    stall_ticks: int
    slowdown_ticks: int
    compactions: int

    @property
    def write_amplification(self) -> float:
        physical = self.flush_write_bytes + self.compaction_output_bytes
        return physical / self.logical_write_bytes if self.logical_write_bytes else 0.0

    @property
    def read_amplification(self) -> float:
        return self.table_probes / self.reads if self.reads else 0.0

    @property
    def read_hit_ratio(self) -> float:
        return self.read_hits / self.reads if self.reads else 0.0

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["write_amplification"] = self.write_amplification
        data["read_amplification"] = self.read_amplification
        data["read_hit_ratio"] = self.read_hit_ratio
        return data
