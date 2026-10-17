"""Paper-scoped BM25 / Chroma Dense / rank-only RRF, shared by UI and CLI."""

import math
import re

from rank_bm25 import BM25Okapi


def tokenize(text):
    return re.findall(r"[a-z0-9]+(?:[-_'][a-z0-9]+)*", text.lower())


def rank_rows(rows):
    return [{**row, "rank": i} for i, row in enumerate(
        sorted(rows, key=lambda row: (-row["score"], row["chunk_id"])), 1)]


def rrf(rankings, constant=60):
    scores, rows, ranks = {}, {}, {}
    for method, ranking in rankings.items():
        seen = set()
        for rank, row in enumerate(ranking, 1):
            cid = row["chunk_id"]
            if cid in seen:
                raise ValueError("Duplicate chunk within one ranking")
            seen.add(cid)
            rows[cid] = row
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (constant + rank)
            ranks.setdefault(cid, {})[method] = rank
    return rank_rows([{**rows[cid], "score": score, "branch_ranks": ranks[cid]}
                      for cid, score in scores.items()])


class Retriever:
    """Backend loads only one paper BEFORE BM25 statistics or vector scoring."""
    def __init__(self, backend, encoder, settings):
        self.backend, self.encoder, self.settings = backend, encoder, settings

    def retrieve(self, query, paper_id, method="hybrid", k=5, *, trace=None):
        if method not in {"bm25", "dense", "hybrid"}:
            raise ValueError("Unknown retrieval method")
        if not isinstance(k, int) or k < 1:
            raise ValueError("k must be positive")
        if method == "hybrid" and k > self.settings["branch_k"]:
            raise ValueError("Hybrid k exceeds the frozen branch depth")
        documents = self.backend.paper_documents(paper_id)
        if not documents or any(d.metadata["paper_id"] != paper_id for d in documents):
            raise ValueError("Paper missing or foreign chunk escaped the prefilter")
        rows = {d.doc_id: {"chunk_id": d.doc_id, "text": d.text, "metadata": d.metadata} for d in documents}
        if len(rows) != len(documents):
            raise ValueError("Duplicate chunk IDs in scoped corpus")
        rankings = {}
        if method in {"bm25", "hybrid"}:
            tokens = [tokenize(d.text) for d in documents]
            if not any(tokens):
                raise ValueError("Paper contains no lexical tokens")
            index = BM25Okapi(tokens, k1=self.settings["k1"], b=self.settings["b"])
            scores = index.get_scores(tokenize(query))
            rankings["bm25"] = rank_rows([{**row, "score": float(score)}
                                           for row, score in zip(rows.values(), scores)])
        if method in {"dense", "hybrid"}:
            vector = self.encoder.encode([query], "query")[0].tolist()
            # Fetch all of this paper, so ties at the Top-k boundary resolve by stable ID.
            scores, ids = self.backend.dense_scores(vector, paper_id, len(documents))
            if len(scores) != len(ids) or set(ids) != set(rows):
                raise ValueError("Vector/document identity mismatch or foreign retrieval")
            # The locked Chroma adapter returns exp(-squared_L2); for unit vectors,
            # cosine = 1 - squared_L2 / 2. This is not a BM25-comparable score.
            rankings["dense"] = rank_rows([{**rows[cid], "score": 1 + math.log(max(score, 1e-30)) / 2}
                                            for cid, score in zip(ids, scores)])
        if method == "hybrid":
            rankings = {name: ranking[:self.settings["branch_k"]] for name, ranking in rankings.items()}
            output = rrf(rankings, self.settings["rrf_constant"])
        else:
            output = rankings[method]
        if trace is not None:
            trace.update({name: [{key: row[key] for key in ("chunk_id", "score", "rank")}
                                for row in ranking[:self.settings["branch_k"]]]
                          for name, ranking in rankings.items()})
        return [{**row, "method": method} for row in output[:k]]


def retrieve(query, paper_id, method="hybrid", k=5, config_path=None):
    from .framework import application_retriever
    from .indexing import ROOT

    pipeline = application_retriever(config_path or ROOT / "configs/local.json", paper_id, method)
    return pipeline.retrieve(query, paper_id, method, k)
