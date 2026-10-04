"""Discrete-event LSM simulator with bounded background compaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import CompactionPlan, Entry, SSTable, SimulationResult, merge_tables
from .policies import CompactionPolicy, Levels
from .workload import Operation


@dataclass(frozen=True, slots=True)
class SimulatorConfig:
    memtable_bytes: int = 32 * 1024
    background_bytes_per_tick: int = 64 * 1024
    l0_slowdown_trigger: int = 8
    l0_stop_trigger: int = 12
    max_backlog_bytes: int = 4 * 1024 * 1024
    max_levels: int = 5

    def validate(self) -> None:
        if self.memtable_bytes <= 0:
            raise ValueError("memtable_bytes must be positive")
        if self.background_bytes_per_tick <= 0:
            raise ValueError("background_bytes_per_tick must be positive")
        if not 1 <= self.l0_slowdown_trigger < self.l0_stop_trigger:
            raise ValueError("L0 triggers must be ordered positive values")
        if self.max_backlog_bytes <= 0:
            raise ValueError("max_backlog_bytes must be positive")
        if self.max_levels < 2:
            raise ValueError("max_levels must be at least two")


@dataclass(slots=True)
class _Pending:
    plan: CompactionPlan
    output: SSTable
    input_bytes: int
    remaining_bytes: int

    @property
    def temporary_output_bytes(self) -> int:
        completed = self.input_bytes - self.remaining_bytes
        if self.input_bytes == 0:
            return self.output.storage_bytes
        return self.output.storage_bytes * completed // self.input_bytes


class Simulator:
    def __init__(self, config: SimulatorConfig, policy: CompactionPolicy) -> None:
        config.validate()
        self.config = config
        self.policy = policy
        self._levels: list[list[SSTable]] = [[] for _ in range(config.max_levels)]
        self._memtable: dict[str, Entry] = {}
        self._pending: list[_Pending] = []
        self._reserved: set[int] = set()
        self._live: dict[str, Entry] = {}
        self._next_table_id = 1
        self._sequence = 0
        self._reset_metrics()

    def _reset_metrics(self) -> None:
        self.puts = self.reads = self.read_hits = self.table_probes = 0
        self.logical_write_bytes = self.flush_write_bytes = 0
        self.compaction_input_bytes = self.compaction_output_bytes = 0
        self.input_by_level = [0] * self.config.max_levels
        self.output_by_level = [0] * self.config.max_levels
        self.stall_ticks = self.slowdown_ticks = self.compactions = 0
        self.peak_backlog_bytes = self.peak_resident_bytes = 0
        self.peak_space_amplification = 1.0

    @property
    def levels(self) -> Levels:
        return tuple(tuple(level) for level in self._levels)

    @property
    def pending_bytes(self) -> int:
        return sum(task.remaining_bytes for task in self._pending)

    @property
    def resident_bytes(self) -> int:
        tables = sum(table.storage_bytes for level in self._levels for table in level)
        memory = sum(entry.storage_bytes for entry in self._memtable.values())
        transient = sum(task.temporary_output_bytes for task in self._pending)
        return tables + memory + transient

    @property
    def live_bytes(self) -> int:
        return sum(entry.storage_bytes for entry in self._live.values() if not entry.tombstone)

    def run(self, operations: Iterable[Operation], *, drain: bool = True) -> SimulationResult:
        operation_list = list(operations)
        for operation in operation_list:
            self._wait_for_write_capacity(operation)
            if operation.kind == "put":
                self._put(operation)
            else:
                self._get(operation.key)
            self._schedule()
            self._background_tick()
            if (
                operation.kind == "put"
                and len(self._levels[0]) >= self.config.l0_slowdown_trigger
            ):
                self.slowdown_ticks += 1
                self._background_tick()
            self._observe_peaks()
        self._flush()
        self._schedule()
        if drain:
            while self._pending:
                self._background_tick()
                self._schedule()
                self._observe_peaks()
        self._observe_peaks()
        return self._result(len(operation_list))

    def _wait_for_write_capacity(self, operation: Operation) -> None:
        if operation.kind != "put":
            return
        guard = 0
        while (
            len(self._levels[0]) >= self.config.l0_stop_trigger
            or self.pending_bytes > self.config.max_backlog_bytes
        ):
            self._schedule()
            if not self._pending:
                break
            self.stall_ticks += 1
            self._background_tick()
            self._observe_peaks()
            guard += 1
            if guard > 1_000_000:
                raise RuntimeError("write stall failed to make progress")

    def _put(self, operation: Operation) -> None:
        self._sequence += 1
        entry = Entry(operation.key, self._sequence, operation.value_bytes)
        self._memtable = {**self._memtable, operation.key: entry}
        self._live = {**self._live, operation.key: entry}
        self.puts += 1
        self.logical_write_bytes += entry.storage_bytes
        if sum(item.storage_bytes for item in self._memtable.values()) >= self.config.memtable_bytes:
            self._flush()

    def _get(self, key: str) -> None:
        self.reads += 1
        memory = self._memtable.get(key)
        if memory is not None:
            self.read_hits += int(not memory.tombstone)
            return
        newest: Entry | None = None
        for level_index, level in enumerate(self._levels):
            ordered = reversed(level) if level_index == 0 else level
            for table in ordered:
                if not table.might_contain(key):
                    continue
                self.table_probes += 1
                candidate = table.find(key)
                if candidate is not None and (newest is None or candidate.sequence > newest.sequence):
                    newest = candidate
        self.read_hits += int(newest is not None and not newest.tombstone)

    def _flush(self) -> None:
        if not self._memtable:
            return
        table = SSTable.build(self._allocate_id(), 0, self._memtable.values())
        self._levels[0].append(table)
        self.flush_write_bytes += table.storage_bytes
        self._memtable = {}

    def _allocate_id(self) -> int:
        identifier = self._next_table_id
        self._next_table_id += 1
        return identifier

    def _schedule(self) -> None:
        # One modeled background worker owns one plan at a time. Selecting the
        # next plan only after completion ensures it observes the installed
        # destination output and cannot prepare an overlapping stale merge.
        if self._pending:
            return
        plan = self.policy.pick(self.levels, frozenset(self._reserved))
        if plan is None:
            return
        tables = self._tables_for(plan.input_ids)
        input_bytes = sum(table.storage_bytes for table in tables)
        output = merge_tables(
            self._allocate_id(),
            plan.target_level,
            tables,
            drop_tombstones=plan.target_level == self.config.max_levels - 1,
        )
        self._pending.append(_Pending(plan, output, input_bytes, input_bytes))
        self._reserved.update(plan.input_ids)

    def _tables_for(self, identifiers: tuple[int, ...]) -> tuple[SSTable, ...]:
        wanted = set(identifiers)
        tables = tuple(table for level in self._levels for table in level if table.identifier in wanted)
        if len(tables) != len(wanted):
            raise RuntimeError("compaction input disappeared")
        return tables

    def _background_tick(self) -> None:
        budget = self.config.background_bytes_per_tick
        while budget > 0 and self._pending:
            task = self._pending[0]
            consumed = min(budget, task.remaining_bytes)
            task.remaining_bytes -= consumed
            budget -= consumed
            if task.remaining_bytes == 0:
                self._finish(self._pending.pop(0))

    def _finish(self, task: _Pending) -> None:
        identifiers = set(task.plan.input_ids)
        for level_index, level in enumerate(self._levels):
            self._levels[level_index] = [
                table for table in level if table.identifier not in identifiers
            ]
        if task.output.entries:
            self._levels[task.plan.target_level].append(task.output)
        self._reserved.difference_update(identifiers)
        self.compaction_input_bytes += task.input_bytes
        self.compaction_output_bytes += task.output.storage_bytes
        self.input_by_level[task.plan.target_level] += task.input_bytes
        self.output_by_level[task.plan.target_level] += task.output.storage_bytes
        self.compactions += 1
        self._schedule()

    def _observe_peaks(self) -> None:
        resident = self.resident_bytes
        self.peak_resident_bytes = max(self.peak_resident_bytes, resident)
        self.peak_backlog_bytes = max(self.peak_backlog_bytes, self.pending_bytes)
        if self.live_bytes:
            self.peak_space_amplification = max(
                self.peak_space_amplification, resident / self.live_bytes
            )

    def _result(self, operations: int) -> SimulationResult:
        return SimulationResult(
            policy=self.policy.name,
            operations=operations,
            puts=self.puts,
            reads=self.reads,
            read_hits=self.read_hits,
            table_probes=self.table_probes,
            logical_write_bytes=self.logical_write_bytes,
            flush_write_bytes=self.flush_write_bytes,
            compaction_input_bytes=self.compaction_input_bytes,
            compaction_output_bytes=self.compaction_output_bytes,
            compaction_input_by_target_level=tuple(self.input_by_level),
            compaction_output_by_target_level=tuple(self.output_by_level),
            resident_bytes=self.resident_bytes,
            live_bytes=self.live_bytes,
            peak_resident_bytes=self.peak_resident_bytes,
            peak_space_amplification=self.peak_space_amplification,
            peak_backlog_bytes=self.peak_backlog_bytes,
            pending_compaction_bytes=self.pending_bytes,
            pending_compactions=len(self._pending),
            stall_ticks=self.stall_ticks,
            slowdown_ticks=self.slowdown_ticks,
            compactions=self.compactions,
        )
