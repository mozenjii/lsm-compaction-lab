from lsmlab.models import Entry, SSTable, merge_tables


def test_table_tracks_range_and_bytes():
    table = SSTable.build(1, 0, [Entry("a", 1, 100), Entry("z", 2, 50)])
    assert table.min_key == "a"
    assert table.max_key == "z"
    assert table.storage_bytes == sum(entry.storage_bytes for entry in table.entries)
    assert table.might_contain("m")
    assert not table.might_contain("zz")


def test_merge_keeps_newest_version_per_key():
    old = SSTable.build(1, 1, [Entry("a", 1, 10), Entry("b", 2, 20)])
    new = SSTable.build(2, 0, [Entry("a", 3, 30)])
    merged = merge_tables(3, 1, [old, new])
    values = {entry.key: entry for entry in merged.entries}
    assert values["a"].sequence == 3
    assert values["a"].value_bytes == 30
    assert values["b"].sequence == 2


def test_merge_can_drop_bottom_level_tombstones():
    old = SSTable.build(1, 1, [Entry("a", 1, 10)])
    deleted = SSTable.build(2, 0, [Entry("a", 2, 0, tombstone=True)])
    merged = merge_tables(3, 2, [old, deleted], drop_tombstones=True)
    assert merged.entries == ()


def test_entry_validates_inputs():
    for args in [("", 1, 1), ("a", -1, 1), ("a", 1, -1)]:
        try:
            Entry(*args)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid entry accepted")
