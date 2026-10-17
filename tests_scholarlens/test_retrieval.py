import math
from types import SimpleNamespace

import numpy as np
import pytest

from scholarlens.retrieval import Retriever, rank_rows, rrf, tokenize


SETTINGS = {"k1": 1.5, "b": 0.75, "branch_k": 20, "rrf_constant": 60}


def row(cid, score=0):
    return {"chunk_id": cid, "score": score, "text": cid, "metadata": {"paper_id": "p1"}}


def test_rrf_hand_calculation_overlap_and_tie_break():
    output = rrf({"bm25": [row("a"), row("b"), row("c")], "dense": [row("b"), row("a")]})
    assert [r["chunk_id"] for r in output] == ["a", "b", "c"]
    assert output[0]["score"] == pytest.approx(1 / 61 + 1 / 62)
    assert output[1]["score"] == pytest.approx(1 / 61 + 1 / 62)
    assert output[2]["score"] == pytest.approx(1 / 63)
    assert output[0]["branch_ranks"] == {"bm25": 1, "dense": 2}
    assert [r["rank"] for r in output] == [1, 2, 3]


def test_rrf_duplicate_within_branch_not_double_counted():
    with pytest.raises(ValueError, match="Duplicate"):
        rrf({"bm25": [row("a"), row("a")]})


def test_rank_ties_stable_and_tokenizer_fixed():
    assert [r["chunk_id"] for r in rank_rows([row("b"), row("a")])] == ["a", "b"]
    assert tokenize("Qwen-3 / API: foo_bar, IT'S 2026!") == ["qwen-3", "api", "foo_bar", "it's", "2026"]


class Encoder:
    def __init__(self):
        self.requests = []

    def encode(self, texts, role):
        self.requests.append((texts, role))
        return np.array([[1, 0]], dtype=np.float32)


class Backend:
    def __init__(self):
        self.dense_requests = []

    def paper_documents(self, paper_id):
        return [SimpleNamespace(doc_id=paper_id + cid, text=text,
                                metadata={"paper_id": paper_id, "file_id": paper_id + "-file", "chunk_id": paper_id + cid})
                for cid, text in (("a", "rare rare token"), ("b", "token many"), ("c", "other word word word"))]

    def dense_scores(self, vector, paper_id, count):
        self.dense_requests.append((paper_id, count))
        return [math.exp(-1), math.exp(-0.2), math.exp(-1)], [paper_id + "a", paper_id + "b", paper_id + "c"]


def test_bm25_uses_selected_paper_and_matches_hand_formula():
    backend, encoder = Backend(), Encoder()
    engine = Retriever(backend, encoder, SETTINGS)
    output = engine.retrieve("rare", "p1", "bm25", 3)
    assert output[0]["chunk_id"] == "p1a"
    # N=3, df=1, tf=2, dl=avgdl=3; library's positive IDF branch.
    assert output[0]["score"] == pytest.approx(math.log(2.5 / 1.5) * 5 / 3.5)
    assert not encoder.requests and not backend.dense_requests


def test_u1_identical_terms_never_escape_paper_and_dense_prefilters():
    backend, encoder = Backend(), Encoder()
    engine = Retriever(backend, encoder, SETTINGS)
    for method in ("bm25", "dense", "hybrid"):
        first = engine.retrieve("rare", "p1", method, 3)
        second = engine.retrieve("rare", "p2", method, 3)
        assert {r["metadata"]["paper_id"] for r in first} == {"p1"}
        assert {r["metadata"]["paper_id"] for r in second} == {"p2"}
        assert first == engine.retrieve("rare", "p1", method, 3)
    assert ("p1", 3) in backend.dense_requests and ("p2", 3) in backend.dense_requests
    assert all(role == "query" for _, role in encoder.requests)


def test_dense_scores_convert_locked_l2_space_to_cosine():
    result = Retriever(Backend(), Encoder(), SETTINGS).retrieve("query", "p1", "dense", 3)
    assert [r["chunk_id"] for r in result] == ["p1b", "p1a", "p1c"]
    assert result[0]["score"] == pytest.approx(0.9)
    assert result[1]["score"] == pytest.approx(0.5)


def test_unsafe_backend_does_not_silently_postfilter():
    class Unsafe(Backend):
        def dense_scores(self, vector, paper_id, count):
            return [1.0], ["foreign-id"]
    with pytest.raises(ValueError, match="identity mismatch"):
        Retriever(Unsafe(), Encoder(), SETTINGS).retrieve("query", "p1", "dense", 1)


@pytest.mark.parametrize("method,k", [("unknown", 5), ("dense", 0), ("hybrid", 21)])
def test_invalid_retrieval_parameters_rejected(method, k):
    with pytest.raises(ValueError):
        Retriever(Backend(), Encoder(), SETTINGS).retrieve("query", "p1", method, k)


def test_hybrid_uses_only_first_twenty_in_each_branch():
    class Many(Backend):
        def paper_documents(self, paper_id):
            return [SimpleNamespace(doc_id=f"c{i:02}", text="word " * (i + 1),
                                    metadata={"paper_id": paper_id}) for i in range(25)]

        def dense_scores(self, vector, paper_id, count):
            return [1.0] * 25, [f"c{i:02}" for i in range(25)]
    results = Retriever(Many(), Encoder(), SETTINGS).retrieve("word", "p1", "hybrid", 20)
    assert all(all(rank <= 20 for rank in r["branch_ranks"].values()) for r in results)
