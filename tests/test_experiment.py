import json

from lsmlab.experiment import ExperimentConfig, run_experiment


def test_experiment_is_reproducible():
    config = ExperimentConfig(operations=600, key_count=100, seed=21)
    assert run_experiment(config).to_json() == run_experiment(config).to_json()


def test_report_compares_leveled_and_tiered_policies():
    report = run_experiment(ExperimentConfig(operations=1_000, key_count=120, seed=3))
    assert [result.policy for result in report.results] == ["leveled", "tiered"]
    assert all(result.compaction_input_bytes >= result.compaction_output_bytes for result in report.results)


def test_report_has_versioned_json_and_configuration():
    payload = json.loads(run_experiment(ExperimentConfig(operations=100, key_count=20)).to_json())
    assert payload["schema_version"] == 1
    assert payload["config"]["operations"] == 100
    assert len(payload["results"]) == 2
