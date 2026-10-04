from lsmlab.workload import WorkloadSpec, generate_workload


def test_workload_is_seeded_and_deterministic():
    spec = WorkloadSpec(operations=200, key_count=50, seed=17)
    assert generate_workload(spec) == generate_workload(spec)


def test_workload_contains_reads_writes_and_overwrites():
    operations = generate_workload(WorkloadSpec(operations=500, key_count=40, seed=9, read_ratio=0.4))
    kinds = {operation.kind for operation in operations}
    writes = [operation.key for operation in operations if operation.kind == "put"]
    assert kinds == {"get", "put"}
    assert len(set(writes)) < len(writes)


def test_workload_rotates_hot_ranges():
    operations = generate_workload(
        WorkloadSpec(operations=600, key_count=90, phases=3, hot_fraction=0.1, seed=4)
    )
    phase_size = len(operations) // 3
    leaders = []
    for start in range(0, len(operations), phase_size):
        counts: dict[str, int] = {}
        for operation in operations[start : start + phase_size]:
            counts[operation.key] = counts.get(operation.key, 0) + 1
        leaders.append(max(counts, key=counts.get))
    assert len(set(leaders)) >= 2


def test_workload_rejects_invalid_parameters():
    try:
        WorkloadSpec(operations=0).validate()
    except ValueError as exc:
        assert "operations" in str(exc)
    else:
        raise AssertionError("invalid workload accepted")
