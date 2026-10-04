from lsmlab.engine import Simulator, SimulatorConfig
from lsmlab.policies import LeveledPolicy, TieredPolicy
from lsmlab.workload import Operation


def config(**changes) -> SimulatorConfig:
    values = dict(
        memtable_bytes=100,
        background_bytes_per_tick=1_000,
        l0_slowdown_trigger=6,
        l0_stop_trigger=8,
        max_backlog_bytes=100_000,
        max_levels=4,
    )
    values.update(changes)
    return SimulatorConfig(**values)


def test_puts_flush_memtable_and_account_bytes():
    simulator = Simulator(config(), LeveledPolicy(l0_trigger=2, base_level_bytes=500))
    result = simulator.run([Operation("put", f"k{i}", 40) for i in range(6)])
    assert result.logical_write_bytes > 0
    assert result.flush_write_bytes > 0
    assert result.resident_bytes > 0
    assert result.write_amplification >= 1.0


def test_gets_count_table_probes_and_observe_latest_value():
    simulator = Simulator(config(), TieredPolicy(fanout=3))
    operations = [Operation("put", "a", 60), Operation("put", "b", 60), Operation("put", "a", 90)]
    operations.extend([Operation("get", "a"), Operation("get", "missing")])
    result = simulator.run(operations)
    assert result.reads == 2
    assert result.read_hits == 1
    assert result.table_probes >= 1


def test_low_background_budget_creates_backlog_and_stalls():
    simulator = Simulator(
        config(background_bytes_per_tick=20, l0_slowdown_trigger=2, l0_stop_trigger=3, max_backlog_bytes=250),
        LeveledPolicy(l0_trigger=2, base_level_bytes=200),
    )
    result = simulator.run([Operation("put", f"k{i % 10}", 80) for i in range(80)])
    assert result.peak_backlog_bytes > 0
    assert result.stall_ticks > 0


def test_final_drain_completes_pending_compactions():
    simulator = Simulator(config(background_bytes_per_tick=50), TieredPolicy(fanout=2))
    result = simulator.run([Operation("put", f"k{i}", 60) for i in range(20)], drain=True)
    assert result.pending_compaction_bytes == 0


def test_space_amplification_accounts_for_obsolete_versions():
    simulator = Simulator(config(), TieredPolicy(fanout=4))
    operations = [Operation("put", "same", 60) for _ in range(20)]
    result = simulator.run(operations, drain=False)
    assert result.peak_space_amplification >= 1.0
    assert result.peak_resident_bytes >= result.live_bytes


def test_serial_worker_never_queues_multiple_compaction_plans():
    simulator = Simulator(
        config(
            background_bytes_per_tick=1,
            l0_slowdown_trigger=20,
            l0_stop_trigger=30,
            max_backlog_bytes=1_000_000,
        ),
        LeveledPolicy(l0_trigger=2, base_level_bytes=100),
    )
    result = simulator.run(
        [Operation("put", f"k-{index:03d}", 80) for index in range(20)],
        drain=False,
    )
    assert result.pending_compactions == 1


def test_reads_do_not_trigger_write_slowdown_ticks():
    simulator = Simulator(
        config(
            l0_slowdown_trigger=2,
            l0_stop_trigger=8,
            background_bytes_per_tick=1,
        ),
        LeveledPolicy(l0_trigger=10, base_level_bytes=10_000),
    )
    operations = [Operation("put", f"k-{index}", 80) for index in range(4)]
    operations.extend(Operation("get", "missing") for _ in range(10))
    result = simulator.run(operations, drain=False)
    assert result.slowdown_ticks == 1
