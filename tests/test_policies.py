from lsmlab.models import Entry, SSTable
from lsmlab.policies import LeveledPolicy, TieredPolicy


def table(identifier: int, level: int, first: int, last: int) -> SSTable:
    return SSTable.build(
        identifier,
        level,
        [Entry(f"k-{index:03d}", identifier * 100 + index, 10) for index in range(first, last + 1)],
    )


def test_leveled_l0_compaction_includes_overlapping_next_level_tables():
    levels = (
        (table(1, 0, 0, 9), table(2, 0, 10, 19)),
        (table(3, 1, 5, 12), table(4, 1, 40, 49)),
        (),
    )
    plan = LeveledPolicy(l0_trigger=2, base_level_bytes=10_000).pick(levels, frozenset())
    assert plan is not None
    assert plan.input_ids == (1, 2, 3)
    assert plan.target_level == 1


def test_leveled_size_pressure_selects_oldest_table_and_overlap():
    levels = (
        (),
        (table(1, 1, 0, 9), table(2, 1, 20, 29)),
        (table(3, 2, 5, 15),),
    )
    plan = LeveledPolicy(l0_trigger=4, base_level_bytes=1, level_ratio=2).pick(levels, frozenset())
    assert plan is not None
    assert plan.input_ids == (1, 3)
    assert plan.target_level == 2


def test_tiered_waits_for_fanout_then_merges_runs_without_next_level_rewrite():
    levels = ((table(1, 0, 0, 9), table(2, 0, 10, 19), table(3, 0, 20, 29)), (), ())
    policy = TieredPolicy(fanout=3)
    plan = policy.pick(levels, frozenset())
    assert plan is not None
    assert plan.input_ids == (1, 2, 3)
    assert plan.target_level == 1


def test_policies_ignore_reserved_inputs():
    levels = ((table(1, 0, 0, 1), table(2, 0, 2, 3)), (), ())
    assert LeveledPolicy(l0_trigger=2).pick(levels, frozenset({1})) is None
    assert TieredPolicy(fanout=2).pick(levels, frozenset({2})) is None
