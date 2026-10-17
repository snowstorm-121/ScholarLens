import copy

import pytest

import scholarlens.dev_experiments as dev


def run(size, method, score=(.5, .3, .4)):
    config = {"index": {"name": str(size), "chunk_size": size, "overlap": 200,
                         "retrieval": {"method": "hybrid"}}, "generation": {"seed": 42}}
    manifest = {"config": config, "method": method, "question_set_sha256": "questions",
                "corpus_manifest_sha256": "corpus", "freeze_sha256": "frozen",
                "evaluator": "official", "code_sha256": {"eval": "v1"}, "runtime": "same"}
    return {"directory": f"{size}-{method}", "manifest": manifest,
            "summary": dict(zip(dev.PRIORITY, score))}


def fixture_runs(monkeypatch, values):
    entries = {entry["directory"]: entry for entry in values}
    monkeypatch.setattr(dev, "read_run", lambda p: entries[p])
    return list(entries)


def test_chunk_selection_is_lexicographic_and_tie_keeps_1600(monkeypatch):
    paths = fixture_runs(monkeypatch, [run(1600, "hybrid"), run(2400, "hybrid")])
    assert dev.choose_chunking(paths) == 1600
    paths = fixture_runs(monkeypatch, [run(1600, "hybrid", (.5, .3, .9)),
                                      run(2400, "hybrid", (.5, .4, .1))])
    assert dev.choose_chunking(paths) == 2400
    paths = fixture_runs(monkeypatch, [run(1600, "hybrid", (.51, .1, .1)),
                                      run(2400, "hybrid", (.5, .9, .9))])
    assert dev.choose_chunking(paths) == 1600


def test_methods_must_share_winning_chunk_set_and_tie_prefers_dense(monkeypatch):
    paths = fixture_runs(monkeypatch, [run(1600, method) for method in dev.METHOD_TIES])
    assert dev.choose_method(paths, 1600) == "dense"
    with pytest.raises(ValueError, match="All three"):
        dev.choose_method(paths, 2400)
    entries = [run(1600, "dense"), run(1600, "bm25", (.6, .3, .4)), run(1600, "hybrid")]
    assert dev.choose_method(fixture_runs(monkeypatch, entries), 1600) == "bm25"


@pytest.mark.parametrize("key", ["question_set_sha256", "corpus_manifest_sha256", "freeze_sha256",
                                "evaluator", "code_sha256", "runtime"])
def test_uncontrolled_experiment_difference_rejected(monkeypatch, key):
    a, b = run(1600, "hybrid"), run(2400, "hybrid")
    b["manifest"][key] = "changed"
    with pytest.raises(ValueError, match="Uncontrolled"):
        dev.choose_chunking(fixture_runs(monkeypatch, [a, b]))


def test_only_chunk_size_and_name_may_change(monkeypatch):
    a, b = run(1600, "hybrid"), run(2400, "hybrid")
    b["manifest"]["config"]["generation"]["seed"] = 1
    with pytest.raises(ValueError, match="Uncontrolled"):
        dev.choose_chunking(fixture_runs(monkeypatch, [a, b]))
    b = run(2400, "hybrid")
    b["manifest"]["config"]["index"]["overlap"] = 0
    with pytest.raises(ValueError, match="Uncontrolled"):
        dev.choose_chunking(fixture_runs(monkeypatch, [a, b]))


def test_duplicate_retry_cannot_be_selected(monkeypatch):
    item = run(1600, "hybrid")
    monkeypatch.setattr(dev, "read_run", lambda p: copy.deepcopy(item))
    with pytest.raises(ValueError, match="Duplicate"):
        dev.checked_runs(["first", "retry"])


def test_selected_snapshot_is_usable_config_but_not_test_authorization(monkeypatch):
    paths = fixture_runs(monkeypatch, [run(1600, method) for method in dev.METHOD_TIES] + [run(2400, "hybrid")])
    result = dev.selected_snapshot(paths)
    assert result["index"]["chunk_size"] == 1600
    assert result["index"]["retrieval"]["method"] == "dense"
    assert result["selection"]["ready_for_test"] is False
    assert result["selection"]["prompt_sha256"]


def test_final_selection_requires_all_three_baseline_runs(monkeypatch):
    paths = fixture_runs(monkeypatch, [run(1600, "hybrid", (.1, .1, .1))] +
                         [run(2400, method) for method in dev.METHOD_TIES])
    with pytest.raises(ValueError, match="baseline"):
        dev.selected_snapshot(paths)
