import json

import httpx
import pytest

from scholarlens.context import QwenTokenCounter, build_context


SETTINGS = {"model": "qwen:test", "model_digest": "sha256:test", "timeout": 180}


def client(info, digest="sha256:test"):
    def respond(request):
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "qwen:test", "digest": digest}]})
        assert json.loads(request.content) == {"model": "qwen:test", "verbose": True}
        return httpx.Response(200, json={"model_info": info})
    return httpx.Client(base_url="http://test", transport=httpx.MockTransport(respond))


def info():
    return {"tokenizer.ggml.tokens": ["a", "b", "ab", "<|endoftext|>", "<|im_end|>"],
            "tokenizer.ggml.token_type": [1, 1, 1, 3, 3],
            "tokenizer.ggml.merges": ["a b"], "tokenizer.ggml.pre": "qwen2",
            "tokenizer.ggml.model": "gpt2", "tokenizer.ggml.add_bos_token": False,
            "tokenizer.ggml.eos_token_id": 4}


def test_real_library_construction_and_special_tokens():
    with client(info()) as http:
        counter = QwenTokenCounter(SETTINGS, http)
    assert counter.encode("ab") == [2]
    assert counter.encode("<|im_end|>") == [4]
    assert counter.count("abab") == 2
    assert counter.metadata["vocab_count"] == 5
    assert counter.metadata["merges_count"] == 1
    assert counter._tokenizer.backend_tokenizer.normalizer is None


def test_digest_mismatch():
    with client(info(), digest="different") as http:
        with pytest.raises(ValueError, match="digest"):
            QwenTokenCounter(SETTINGS, http)


@pytest.mark.parametrize("key,value", [("tokenizer.ggml.pre", "other"),
    ("tokenizer.ggml.model", "other"), ("tokenizer.ggml.add_bos_token", True),
    ("tokenizer.ggml.token_type", [1])])
def test_unsupported_metadata(key, value):
    data = info()
    data[key] = value
    with client(data) as http:
        with pytest.raises(ValueError, match="Unsupported"):
            QwenTokenCounter(SETTINGS, http)


class Counter:
    metadata = {"test": True}

    def count(self, text):
        return len(text)


def row(cid, text="中文\ntext"):
    return {"chunk_id": cid, "text": text, "metadata": {
        "paper_id": "p1", "title": "标题", "section": "intro",
        "paragraph_id": "p1-1", "start": 0, "end": len(text)}}


def test_json_labels_whole_string_budget_and_max_chunks():
    rows = [row(str(i)) for i in range(3)]
    full = build_context(rows[:2], Counter())
    assert full["tokens"] == len(full["context"])
    assert len(full["context"].splitlines()) == 2
    assert json.loads(full["context"].splitlines()[0])["text"] == rows[0]["text"]
    assert "标题" in full["context"]
    limited = build_context(rows, Counter(), token_budget=full["tokens"] - 1)
    assert len(limited["chunks"]) == 1
    assert all(r["reason"] == "token_budget" for r in limited["dropped"])
    capped = build_context(rows, Counter(), max_chunks=1)
    assert [r["reason"] for r in capped["dropped"]] == ["max_chunks", "max_chunks"]
    assert capped["chunks"][0]["source_label"] == "S0"


def test_skip_oversized_without_truncation_and_empty():
    rows = [row("big", "x" * 1000), row("small", "ok")]
    output = build_context(rows, Counter(), token_budget=250)
    assert output["chunks"] == [{**rows[1], "source_label": "Ssmall"}]
    assert output["dropped"][0]["reason"] == "token_budget"
    assert build_context([], Counter())["tokens"] == 0


@pytest.mark.parametrize("ids", [("same", "same"), ("abcdefghijkl1", "abcdefghijkl2")])
def test_duplicate_ids_and_prefix_collision(ids):
    with pytest.raises(ValueError, match="collision"):
        build_context([row(cid) for cid in ids], Counter())


def test_production_cache_avoids_network(monkeypatch):
    sentinel = object()
    key = (SETTINGS["model"], SETTINGS["model_digest"])
    monkeypatch.setattr(QwenTokenCounter, "_cache", {key: (sentinel, {"cached": True})})
    counter = QwenTokenCounter(SETTINGS)
    assert counter._tokenizer is sentinel
    assert counter.metadata == {"cached": True}
