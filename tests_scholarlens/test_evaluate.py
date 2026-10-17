import copy
import json
from types import MethodType, SimpleNamespace

import pytest

import scholarlens.evaluate as runner


@pytest.fixture
def setup_runner(tmp_path, monkeypatch):
    paragraph = {"paper_id": "p", "paragraph_id": "p:p0", "start": 0, "end": 10,
                 "text": "0123456789", "original_text": "0123456789"}
    gold = {**paragraph, "evidence_text": paragraph["text"],
            "original_evidence_text": paragraph["text"]}
    ref = {"annotation_id": "a", "valid": True, "errors": [], "gold_evidence": [gold],
           "answer": {"unanswerable": False, "extractive_spans": ["0123"],
                      "free_form_answer": "", "yes_no": None, "evidence": [paragraph["text"]]}}
    q1 = {"paper_id": "p", "question_id": "q1", "split": "train", "question": "Which?",
          "answerable": True, "references": [ref]}
    q2 = copy.deepcopy(q1)
    q2.update(question_id="q2", answerable=False)
    q2["references"][0].update(annotation_id="b", gold_evidence=[])
    q2["references"][0]["answer"].update(unanswerable=True, evidence=[], extractive_spans=[])
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "corpus_manifest.json").write_text("{}")
    config = {"generation": {"max_chunks": 5}, "index": {}}
    paragraphs = {"p:p0": paragraph}
    selected = [q1, q2]
    def select(*args):
        return tmp_path, config, corpus, {}, paragraphs, {"freeze_sha256": "freeze"}, selected
    monkeypatch.setattr(runner, "select_questions", select)
    monkeypatch.setattr(runner, "index_context", lambda _: (None, None, None, {"fingerprint": "fp"}))
    rows = [{"chunk_id": "c", "text": paragraph["text"], "rank": 1, "score": 1,
             "source_label": "S000000000001", "metadata": paragraph}]
    calls = []
    def factory(*args):
        def retrieve(query, paper_id, method, k, *, trace):
            calls.append((paper_id, method, k))
            trace.update(hybrid=[{"chunk_id": "c", "rank": 1, "score": 1}])
            return rows
        return SimpleNamespace(retrieve=retrieve, fingerprint="fp")
    def answer(query, paper_id, config, *, method, retriever):
        actual = retriever(query, paper_id, method, 5, trace={})
        return {"status": "ok", "answer": "0123【1】", "error": None,
                "retrieval_results": actual, "context_chunks": actual, "citation_errors": [],
                "citations": [{"number": 1, "valid": True, "paper_id": "p", "paragraph_id": "p:p0",
                               "source_label": "S000000000001", "chunk_id": "c", "start": 0,
                               "end": 4, "text": "0123"}]}
    return tmp_path, selected, calls, factory, answer


def test_runner_recomputes_metrics_from_predictions_and_retains_failures(setup_runner):
    root, questions, calls, factory, answer = setup_runner
    def sometimes_offline(*args):
        if len(calls):
            raise ConnectionError("offline")
        return factory(*args)
    result = runner.evaluate("config", stage="generation", experiment_id="fixture",
                             retriever_factory=sometimes_offline, answer_fn=answer, runtime={})
    directory = root / "artifacts/evaluation/fixture"
    rows, summary = runner.recompute(directory)
    assert summary == result["summary"]
    assert summary["questions"] == 2 and summary["system_errors"] == 1
    assert summary["Answer F1"] == .5 and summary["Evidence F1"] == .5
    assert summary["unanswerable_system_error"] == 1
    assert calls == [("p", "hybrid", 10)]  # QA reuses this exact ranking, no second search.
    assert rows[0]["metrics"]["Context EvidenceRecall"] == 1
    assert (directory / "summary.md").is_file()
    # A corrupted cached metrics column must not influence recalculation.
    path = directory / "questions/q1.json"
    saved = json.loads(path.read_text())
    saved["metrics"]["Answer F1"] = 999
    path.write_text(json.dumps(saved))
    assert runner.recompute(directory)[1] == summary


def test_resume_preserves_first_predictions_and_rejects_changed_contract(setup_runner):
    root, questions, calls, factory, answer = setup_runner
    args = dict(stage="retrieval", experiment_id="resume", retriever_factory=factory, runtime={})
    first = runner.evaluate("config", **args)
    before = len(calls)
    assert runner.evaluate("config", resume=True, **args) == first
    assert len(calls) == before
    with pytest.raises(ValueError, match="already exists"):
        runner.evaluate("config", **args)
    with pytest.raises(ValueError, match="changed"):
        runner.evaluate("config", resume=True, **{**args, "method": "dense"})


def test_missing_result_still_in_denominator(setup_runner):
    root, questions, calls, factory, answer = setup_runner
    runner.evaluate("config", stage="retrieval", experiment_id="missing",
                    retriever_factory=factory, runtime={})
    directory = root / "artifacts/evaluation/missing"
    (directory / "questions/q1.json").unlink()
    rows, summary = runner.recompute(directory)
    assert len(rows) == 2 and summary["system_errors"] == 1
    assert summary["EvidenceRecall@5"] == 0


def test_test_split_is_locked_before_any_data_or_model_access():
    with pytest.raises(ValueError, match="locked until T8"):
        runner.select_questions("nonexistent", "test", "generation")


def test_test_contract_rejects_unregistered_or_changed_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    config = tmp_path / "config.json"
    frozen = tmp_path / "test.jsonl"
    contract_path = tmp_path / "contract.json"
    config.write_text("{}")
    frozen.write_text("frozen")
    contract_path.write_text(json.dumps({
        "config_sha256": runner.sha256(config),
        "files_sha256": {"test.jsonl": runner.sha256(frozen)},
        "batches": {"t8-test": {"stage": "retrieval", "method": "dense"}},
    }))
    assert runner.validate_test_contract(config, contract_path, "retrieval", "dense",
                                         "t8-test", None) == runner.sha256(contract_path)
    with pytest.raises(ValueError, match="pre-registered"):
        runner.validate_test_contract(config, None, "retrieval", "dense", "t8-test", None)
    with pytest.raises(ValueError, match="pre-registered stage/method"):
        runner.validate_test_contract(config, contract_path, "generation", "dense", "t8-test", None)
    with pytest.raises(ValueError, match="no limit"):
        runner.validate_test_contract(config, contract_path, "retrieval", "dense", "t8-test", 1)
    frozen.write_text("changed")
    with pytest.raises(ValueError, match="file hash changed"):
        runner.validate_test_contract(config, contract_path, "retrieval", "dense", "t8-test", None)


def test_replay_checks_paper_scope():
    replay = runner.RetrievedOnce([{"metadata": {"paper_id": "other"}}], {}, "fp")
    with pytest.raises(ValueError, match="Foreign"):
        replay.retrieve("q", "p", "hybrid", 5)


def test_failed_serialization_does_not_publish_partial_file(tmp_path):
    path = tmp_path / "record.json"
    with pytest.raises(TypeError):
        runner.save_new(path, {"bad": object()})
    assert not path.exists()


def test_resume_rejects_runtime_change(setup_runner):
    root, questions, calls, factory, answer = setup_runner
    args = dict(stage="retrieval", experiment_id="runtime", retriever_factory=factory)
    runner.evaluate("config", runtime={"ollama_runtime": "original"}, **args)
    with pytest.raises(ValueError, match="changed"):
        runner.evaluate("config", resume=True, runtime={"ollama_runtime": "changed"}, **args)


def test_interruption_before_publication_leaves_no_visible_record(tmp_path, monkeypatch):
    path = tmp_path / "result.json"
    def interrupt(*args):
        raise InterruptedError("simulated publication interruption")
    monkeypatch.setattr(runner.os, "link", interrupt)
    with pytest.raises(InterruptedError):
        runner.save_new(path, {"complete": True})
    assert not path.exists() and not list(tmp_path.glob(".partial-*"))


def test_atomic_publication_never_replaces_first_result(tmp_path):
    path = tmp_path / "result.json"
    runner.save_new(path, {"first": True})
    with pytest.raises(FileExistsError):
        runner.save_new(path, {"first": False})
    assert json.loads(path.read_text()) == {"first": True}


def test_batch_factory_uses_registered_index_without_rendering_help(monkeypatch):
    import ktem.main
    import scholarlens.framework as framework
    from ktem.index.file.index import FileIndex
    from ktem.index.file.ui import FileSelector

    pipeline = SimpleNamespace()
    index = SimpleNamespace(name="active", id=2, config={}, _selector_ui=None,
                            _resources={"Source": object(), "Index": object()}, _fs_path="files",
                            _docstore=object(), _vs=object(), _retriever_pipeline_cls=[SimpleNamespace(
                                get_pipeline=lambda *args: pipeline)])
    def initialize_selector():
        index._selector_ui = SimpleNamespace(get_selected_ids=lambda components:
            FileSelector.get_selected_ids(None, components))
        return index._selector_ui
    index.get_selector_component_ui = initialize_selector
    index.get_retriever_pipelines = MethodType(FileIndex.get_retriever_pipelines, index)
    def unexpected_page_render():
        raise AssertionError("Batch factory must not render Help or fetch remote changelogs")
    app = SimpleNamespace(index_manager=SimpleNamespace(indices=[index]), make=unexpected_page_render,
                          default_settings=SimpleNamespace(flatten=lambda: {}))
    monkeypatch.setattr(ktem.main, "App", lambda: app)
    monkeypatch.setattr(framework, "index_context", lambda *args: (
        None, {"index": {"name": "active"}}, None, {"fingerprint": "fp"}))
    monkeypatch.setattr(framework, "FrameworkBackend", lambda *args: SimpleNamespace(
        source_for=lambda **kwargs: ("file", {})))
    assert framework.application_retriever("config", "p") is pipeline
    assert pipeline.user_id == "default"


def test_generation_failure_does_not_erase_successful_upstream_coverage(setup_runner):
    root, questions, calls, factory, answer = setup_runner
    pred = answer("Which?", "p", {}, method="hybrid", retriever=factory().retrieve)
    pred.update(status="error", error={"type": "output_truncated"}, answer="")
    paragraph = pred["context_chunks"][0]["metadata"]
    metrics = runner.score_question(questions[0], pred, "generation", {"p:p0": paragraph})
    assert metrics["EvidenceRecall@5"] == metrics["Context EvidenceRecall"] == 1
    assert metrics["Answer F1"] == metrics["Evidence F1"] == 0
