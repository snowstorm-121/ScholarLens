import copy
import json
from types import SimpleNamespace

import httpx
import pytest

from scholarlens.generation import LocalGenerator
from scholarlens.indexing import ROOT
from scholarlens.qa import INSUFFICIENT, SYSTEM_PROMPT, answer, parse_answer
from tests_scholarlens.test_indexing import stored_pipeline


CONFIG = json.loads((ROOT / "configs/local.json").read_text())


def chunk(cid="a" * 64, paper="p1", text="The benchmark starts in 2024."):
    return {"chunk_id": cid, "text": text, "score": 0.03226, "rank": 1, "method": "hybrid",
            "metadata": {"paper_id": paper, "title": "A paper", "section": "Experiments",
                         "paragraph_id": paper + ":p1", "source_url": "https://example.com/paper",
                         "start": 10, "end": 10 + len(text)}}


def protocol(label="Saaaaaaaaaaaa", answer_text="The benchmark starts in 2024.【1】"):
    return (f"CITATION LIST\nCITATION【1】\nSOURCE: {label}\n"
            "START_PHRASE: benchmark starts\nEND_PHRASE: 2024.\nFINAL ANSWER\n" + answer_text)


class Counter:
    metadata = {"engine": "unit_test_counter"}

    def count(self, text):
        return len(text)


class Generator:
    def __init__(self, text=None, fail=None, reason="stop"):
        self.text, self.fail, self.reason = protocol() if text is None else text, fail, reason
        self.request = None

    def generate(self, messages):
        self.request = {"messages": messages}
        if self.fail:
            raise self.fail
        return {"message": {"content": self.text}, "done_reason": self.reason}


def call(tmp_path, generator=None, rows=None, query="What year?", config=None):
    return answer(query, "p1", config or CONFIG, tokenizer=Counter(),
                  retriever=lambda *args, **kwargs: [chunk()] if rows is None else rows,
                  generator=generator or Generator(), audit_dir=tmp_path)


def test_valid_citation_exact_span_and_persistent_audit(tmp_path):
    result = call(tmp_path)
    assert result["status"] == "ok" and result["error"] is None
    cite = result["citations"][0]
    assert cite["text"] == "benchmark starts in 2024."
    assert cite["start"] == 14 and cite["end"] == 39
    saved = json.loads((tmp_path / (result["experiment_id"] + ".json")).read_text())
    assert saved == result
    assert saved["prompt"][0]["content"] == SYSTEM_PROMPT
    assert saved["support_review"] == "requires_semantic_review"


def test_refusal_is_exact_and_not_runtime_error(tmp_path):
    result = call(tmp_path, Generator(INSUFFICIENT))
    assert result["status"] == "insufficient_evidence" and result["error"] is None
    assert result["answer"] == INSUFFICIENT and not result["citations"]


@pytest.mark.parametrize("raw,expected", [
    (protocol("Sbbbbbbbbbbbb"), "source_not_in_actual_context"),
    (protocol().replace("benchmark starts", "a quote that does not exist"), "quote_not_exactly_in_source"),
    (protocol(answer_text="2024.【99】"), "undefined_or_invalid"),
    ("2024", "invalid_protocol"),
    (protocol(answer_text="2024."), "no_citations"),
    (protocol(answer_text="2024. " + INSUFFICIENT), "mixed_refusal"),
    (protocol() + "<think>analysis</think>", "thinking"),
])
def test_bad_citations_and_mixed_refusal_detected(tmp_path, raw, expected):
    result = call(tmp_path, Generator(raw))
    assert result["status"] == "invalid_output"
    assert expected in " ".join(result["citation_errors"])


@pytest.mark.parametrize("failure,kind", [
    (httpx.ReadTimeout("slow model"), "timeout"),
    (ConnectionError("model unavailable"), "model_offline"),
    (ValueError("digest mismatch"), "ValueError"),
])
def test_runtime_errors_never_become_refusals(tmp_path, failure, kind):
    result = call(tmp_path, Generator(fail=failure))
    assert result["status"] == "error" and result["error"]["type"] == kind
    assert result["answer"] != INSUFFICIENT
    assert result["request"] is not None


@pytest.mark.parametrize("raw,reason,kind", [("", "stop", "empty_output"),
                                           (protocol(), "length", "output_truncated")])
def test_empty_and_truncated_not_success(tmp_path, raw, reason, kind):
    result = call(tmp_path, Generator(raw, reason=reason))
    assert result["status"] == "error" and result["error"]["type"] == kind


def test_foreign_paper_and_long_query_fail_before_generation(tmp_path):
    generator = Generator()
    result = call(tmp_path, generator, rows=[chunk(paper="p2")])
    assert result["status"] == "error" and result["error"]["stage"] == "retrieval"
    result = call(tmp_path, generator, query="x" * 9000)
    assert result["status"] == "error" and result["error"]["stage"] == "context"
    assert generator.request is None


def test_dropped_chunk_cannot_supply_a_citation(tmp_path):
    config = copy.deepcopy(CONFIG)
    config["generation"]["context_tokens"] = 400
    rows = [chunk(), chunk("b" * 64, text="Padding " * 200)]
    result = call(tmp_path, Generator(protocol("Sbbbbbbbbbbbb")), rows=rows, config=config)
    assert [r["chunk_id"] for r in result["dropped"]] == ["b" * 64]
    assert result["status"] == "invalid_output"


def test_empty_context_refuses_without_calling_model(tmp_path):
    generator = Generator()
    result = call(tmp_path, generator, rows=[])
    assert result["status"] == "insufficient_evidence"
    assert generator.request is None and result["refusal_reason"] == "empty_actual_context"


def test_switching_paper_does_not_reuse_previous_context(tmp_path):
    first = call(tmp_path)
    second = answer("What year?", "p2", CONFIG, tokenizer=Counter(),
                    retriever=lambda *args, **kwargs: [chunk("b" * 64, "p2")],
                    generator=Generator(protocol("Sbbbbbbbbbbbb")), audit_dir=tmp_path)
    assert first["experiment_id"] != second["experiment_id"]
    assert all(r["metadata"]["paper_id"] == "p2" for r in second["context_chunks"])
    assert "Saaaaaaaaaaaa" not in second["context"]


def test_native_request_uses_fixed_options_and_thinking_off():
    class Client:
        def list(self):
            return SimpleNamespace(models=[SimpleNamespace(model=CONFIG["generation"]["model"],
                digest=CONFIG["generation"]["model_digest"])])

        def chat(self, **kwargs):
            self.sent = kwargs
            return {"message": {"content": INSUFFICIENT}, "done_reason": "stop"}

    client = Client()
    generator = LocalGenerator(CONFIG["generation"], client)
    generator.generate([{"role": "user", "content": "question"}])
    assert client.sent == generator.request
    assert client.sent["think"] is False and client.sent["stream"] is False
    assert client.sent["options"] == {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 512}


def test_render_escapes_untrusted_text_and_shows_precise_score(tmp_path):
    from scholarlens.ui import evidence_html
    result = call(tmp_path, rows=[chunk(text="<script>alert(1)</script> benchmark starts in 2024.")])
    rendered = evidence_html(result)
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    assert "0.03226000" in rendered and "非置信度" in rendered
    assert "原论文来源" in rendered and "本次完整审计" in rendered


def test_protocol_header_must_be_exact(tmp_path):
    result = call(tmp_path, Generator(protocol().replace("CITATION LIST", "CITATION LISTgarbage")))
    assert result["status"] == "invalid_output"


def test_selection_backend_error_goes_through_audit(tmp_path):
    result = answer("question", None, CONFIG, selection_error=RuntimeError("database read failed"),
                    audit_dir=tmp_path)
    assert result["status"] == "error" and result["error"]["stage"] == "selection"
    assert result["error"]["message"] == "database read failed"
    assert (tmp_path / (result["experiment_id"] + ".json")).exists()


def test_native_model_calls_are_serialized_across_instances(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    import time

    class Client:
        active, peak = 0, 0
        guard = threading.Lock()

        def list(self):
            return SimpleNamespace(models=[SimpleNamespace(model=CONFIG["generation"]["model"],
                digest=CONFIG["generation"]["model_digest"])])

        def chat(self, **kwargs):
            with self.guard:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(0.03)
            with self.guard:
                self.active -= 1
            return {"message": {"content": INSUFFICIENT}, "done_reason": "stop"}

    client = Client()
    generators = [LocalGenerator(CONFIG["generation"], client, tmp_path / "generation.lock") for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda g: g.generate([]), generators))
    assert client.peak == 1


def test_title_filter_does_not_change_file_identity(stored_pipeline, monkeypatch):
    from scholarlens.ui import PaperSelector
    import scholarlens.ui as ui
    from tests_scholarlens.test_indexing import consume

    pipeline, path, framework = stored_pipeline
    file_id, _ = consume(pipeline.stream(path))
    monkeypatch.setattr(ui, "engine", framework.engine)
    index = SimpleNamespace(config={"FILE_INDEX_PIPELINE": "scholarlens.framework.ScholarIndexPipeline"},
                            _resources={"Source": pipeline.Source})
    selector = PaperSelector(SimpleNamespace(f_user_management=False), index)
    _, note = framework.FrameworkBackend(pipeline.Source, pipeline.Index, pipeline.DS,
                                         pipeline.VS, "tester", "fingerprint").source_for(paper_id="p1")
    update, choices = selector.load_files([file_id], "tester", note["title"].upper())
    assert choices == [(note["title"] + " · p1", file_id)]
    assert update["value"] == [file_id]
    assert selector.load_files([file_id], "tester", "no matching title")[0]["value"] == []


def test_sent_http_request_retained_on_timeout(tmp_path):
    class SentThenTimeout(Generator):
        wire_request = {"model": "local-model", "think": False}
        transport = {"timeout": "Timeout(timeout=180)"}

    result = call(tmp_path, SentThenTimeout(fail=httpx.ReadTimeout("after HTTP send")))
    assert result["wire_request"] == SentThenTimeout.wire_request
    assert result["transport"] == SentThenTimeout.transport


def test_ui_does_not_forward_old_conversation_history(tmp_path, monkeypatch):
    import scholarlens.ui as ui
    from scholarlens.framework import ScholarRetrieverPipeline
    from tests_scholarlens.test_indexing import consume

    retriever = ScholarRetrieverPipeline(scholar_settings=CONFIG["index"], fingerprint="test", selected=["file"])
    monkeypatch.setattr(ScholarRetrieverPipeline, "backend", lambda self: SimpleNamespace(
        source_for=lambda **kwargs: ("file", {"paper_id": "p1"})))
    monkeypatch.setattr(ScholarRetrieverPipeline, "retrieve", lambda *args, **kwargs: [chunk()])
    monkeypatch.setattr(ui, "answer", lambda query, pid, **kwargs: answer(
        query, pid, CONFIG, tokenizer=Counter(), generator=Generator(), audit_dir=tmp_path, **kwargs))
    result = consume(ui.ScholarQA(retrievers=[retriever]).stream(
        "What year?", "conversation", [("OLD_PAPER_QUESTION", "OLD_PAPER_EVIDENCE")])).metadata
    assert result["status"] == "ok"
    assert [m["role"] for m in result["prompt"]] == ["system", "user"]
    assert "OLD_PAPER" not in json.dumps(result["prompt"])
