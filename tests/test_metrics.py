from lsmlab.engine import Simulator, SimulatorConfig
from lsmlab.policies import LeveledPolicy
from lsmlab.workload import Operation


def test_level_accounting_sums_to_compaction_totals():
    simulator = Simulator(
        SimulatorConfig(
            memtable_bytes=100,
            background_bytes_per_tick=10_000,
            l0_slowdown_trigger=6,
            l0_stop_trigger=8,
            max_backlog_bytes=100_000,
            max_levels=4,
        ),
        LeveledPolicy(l0_trigger=2, base_level_bytes=200, level_ratio=2),
    )
    result = simulator.run([Operation("put", f"k-{index:03d}", 60) for index in range(30)])
    assert sum(result.compaction_input_by_target_level) == result.compaction_input_bytes
    assert sum(result.compaction_output_by_target_level) == result.compaction_output_bytes
    assert result.compactions > 0


def test_read_and_write_ratios_handle_no_matching_operations():
    read_only = Simulator(SimulatorConfig(), LeveledPolicy()).run([Operation("get", "absent")])
    assert read_only.write_amplification == 0.0
    write_only = Simulator(SimulatorConfig(), LeveledPolicy()).run([Operation("put", "a", 100)])
    assert write_only.read_amplification == 0.0
    assert write_only.read_hit_ratio == 0.0
