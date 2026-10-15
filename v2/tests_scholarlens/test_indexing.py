import json
from types import SimpleNamespace

import numpy as np
import pytest

from scholarlens.data import convert_paper
from scholarlens.embedding import NomicEncoder, task_input
from scholarlens.indexing import paper_chunks, read_paper
from tests_scholarlens.test_data import paper


def test_short_paragraphs_stay_separate_and_have_global_spans():
    document, paragraphs = convert_paper("p1", paper("Actual evidence."), "train")
    chunks = paper_chunks(document, paragraphs)
    assert len(chunks) == 2
    for row, original in zip(chunks, paragraphs):
        meta = row["metadata"]
        assert meta["paragraph_id"] == original["paragraph_id"]
        assert document["normalized_text"][meta["start"]:meta["end"]] == row["text"]
        assert set(("paper_id", "title", "section", "paragraph_id", "start", "end", "source_url", "chunk_id")) <= meta.keys()


@pytest.mark.parametrize("text", ["alpha beta gamma " * 500, "重复字符" * 1000, "x" * 4000])
def test_long_chunks_cover_source_without_gaps_and_do_not_cross_paragraph(text):
    document, paragraphs = convert_paper("p1", paper(text), "train")
    chunks = paper_chunks(document, paragraphs, 160, 20)
    for paragraph in paragraphs:
        spans = sorted((r["metadata"]["start"], r["metadata"]["end"]) for r in chunks
                       if r["metadata"]["paragraph_id"] == paragraph["paragraph_id"])
        covered = paragraph["start"]
        for start, end in spans:
            assert start <= covered and end - start <= 160
            covered = max(covered, end)
        assert covered == paragraph["end"]
    assert all(document["normalized_text"][r["metadata"]["start"]:r["metadata"]["end"]] == r["text"] for r in chunks)


def test_stable_chunk_ids_and_parameter_change():
    document, paragraphs = convert_paper("p1", paper("test text " * 100), "train")
    first = paper_chunks(document, paragraphs, 100, 10)
    assert first == paper_chunks(document, paragraphs, 100, 10)
    assert {r["chunk_id"] for r in first}.isdisjoint(r["chunk_id"] for r in paper_chunks(document, paragraphs, 200, 10))


@pytest.mark.parametrize("mutation", ["qa", "foreign_paper", "span", "sequence"])
def test_bad_index_input_rejected(mutation):
    document, paragraphs = convert_paper("p1", paper(), "train")
    if mutation == "qa":
        document["qas"] = [{"answer": "do not index"}]
    elif mutation == "foreign_paper":
        paragraphs[0]["paper_id"] = "other"
    elif mutation == "span":
        paragraphs[0]["end"] -= 1
    else:
        paragraphs.reverse()
    with pytest.raises(ValueError):
        paper_chunks(document, paragraphs)


def test_reader_rejects_question_file(tmp_path):
    path = tmp_path / "qa.qasper.json"
    path.write_text(json.dumps({"question": "question", "references": []}))
    with pytest.raises(ValueError, match="body-only"):
        read_paper(path, {"chunk_size": 1600, "overlap": 200})


def test_task_prefixes_applied_exactly_once():
    assert task_input("text", "document") == "search_document: text"
    assert task_input("search_document: search_document: text", "document") == "search_document: text"
    assert task_input("question", "query") == "search_query: question"
    with pytest.raises(ValueError):
        task_input("search_document: text", "query")


class EmbeddingClient:
    def __init__(self, vectors):
        self.vectors, self.requests = vectors, []

    def embed(self, **kwargs):
        self.requests.append(kwargs)
        return SimpleNamespace(embeddings=self.vectors)

    def list(self):
        return SimpleNamespace(models=[SimpleNamespace(model="nomic-embed-text:latest", digest="digest")])


def test_encoder_shape_dtype_normalization_and_real_request_options():
    client = EmbeddingClient([[3, 4], [0, 2]])
    encoder = NomicEncoder({"model": "nomic-embed-text", "model_digest": "digest", "dimensions": 2}, client)
    assert encoder.verify_model() == "digest"
    vectors = encoder.encode(["one", "two"], "document")
    assert vectors.dtype == np.float32 and vectors.shape == (2, 2)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1)
    assert client.requests[0]["input"] == ["search_document: one", "search_document: two"]
    assert client.requests[0]["truncate"] is False


@pytest.mark.parametrize("vectors", [[[0, 0]], [[float("nan"), 1]], [[1]], [[1, 0], [1, 0]]])
def test_invalid_embedding_outputs_rejected(vectors):
    encoder = NomicEncoder({"model": "nomic", "dimensions": 2}, EmbeddingClient(vectors))
    with pytest.raises(ValueError):
        encoder.encode(["text"], "document")


def test_changed_model_digest_rejected():
    encoder = NomicEncoder({"model": "nomic-embed-text", "model_digest": "changed", "dimensions": 2}, EmbeddingClient([]))
    with pytest.raises(ValueError, match="digest"):
        encoder.verify_model()


def consume(events):
    while True:
        try:
            next(events)
        except StopIteration as complete:
            return complete.value


@pytest.fixture
def stored_pipeline(tmp_path, monkeypatch):
    from sqlalchemy import Column, Integer, JSON, String, create_engine
    from sqlalchemy.orm import declarative_base
    from kotaemon.base import DocumentWithEmbedding
    from kotaemon.embeddings import BaseEmbeddings
    from kotaemon.storages import ChromaVectorStore, LanceDBDocumentStore
    import scholarlens.framework as framework
    import ktem.index.file.pipelines as upstream

    base = declarative_base()

    class Source(base):
        __tablename__ = "sources"
        id = Column(String, primary_key=True, default=lambda: "test-file")
        name = Column(String)
        path = Column(String)
        size = Column(Integer)
        user = Column(String)
        note = Column(JSON, default=dict)

    class Link(base):
        __tablename__ = "links"
        id = Column(Integer, primary_key=True)
        source_id = Column(String)
        target_id = Column(String)
        relation_type = Column(String)

    engine = create_engine("sqlite://")
    base.metadata.create_all(engine)
    monkeypatch.setattr(framework, "engine", engine)
    monkeypatch.setattr(upstream, "engine", engine)

    class Embedding(BaseEmbeddings):
        fail: bool = False
        calls: int = 0

        def run(self, docs, **kwargs):
            self.calls += 1
            if self.fail:
                raise RuntimeError("simulated model failure")
            return [DocumentWithEmbedding(**{**d.to_dict(), "embedding": [1.0, 0.0, 0.0]}) for d in docs]

    document, paragraphs = convert_paper("p1", paper("Evidence words " * 10), "train")
    path = tmp_path / "p1.qasper.json"
    path.write_text(json.dumps({"schema": "scholarlens.paper.v1", "paper": document, "paragraphs": paragraphs}))
    fs = tmp_path / "files"
    fs.mkdir()
    settings = {"chunk_size": 50, "overlap": 10}
    pipeline = framework.ScholarPaperPipeline(
        loader=framework.QasperReader(settings), splitter=None, fingerprint="fingerprint",
        scholar_settings=settings, embedding=Embedding(), chunk_batch_size=2,
        Source=Source, Index=Link,
        DS=LanceDBDocumentStore(path=str(tmp_path / "ds"), collection_name="test"),
        VS=ChromaVectorStore(path=str(tmp_path / "vs"), collection_name="test_collection"),
        FSPath=fs, user_id="tester", private=True, run_embedding_in_thread=False)
    return pipeline, path, framework


def test_actual_storage_roundtrip_metadata_and_idempotence(stored_pipeline):
    pipeline, path, framework = stored_pipeline
    file_id, docs = consume(pipeline.stream(path))
    first_calls = pipeline.embedding.calls
    repeated_id, repeated = consume(pipeline.stream(path))
    assert repeated_id == file_id and [d.doc_id for d in repeated] == [d.doc_id for d in docs]
    assert pipeline.embedding.calls == first_calls
    assert pipeline.splitter is None
    assert pipeline.VS._client.client.count() == len(docs)
    assert pipeline.DS.db_connection.open_table("test").count_rows() == len(docs)
    restored = pipeline.DS.get([d.doc_id for d in docs])
    assert [(d.text, d.metadata) for d in restored] == [(d.text, d.metadata) for d in docs]
    backend = framework.FrameworkBackend(pipeline.Source, pipeline.Index, pipeline.DS, pipeline.VS, "tester", "fingerprint")
    assert len(backend.paper_documents("p1")) == len(docs)
    scores, ids = backend.dense_scores([1, 0, 0], "p1", len(docs))
    assert set(ids) == {d.doc_id for d in docs} and len(scores) == len(docs)


def test_resume_after_embedding_failure_without_duplicate_documents(stored_pipeline):
    pipeline, path, _ = stored_pipeline
    pipeline.embedding.fail = True
    with pytest.raises(RuntimeError, match="simulated"):
        consume(pipeline.stream(path))
    count = pipeline.DS.db_connection.open_table("test").count_rows()
    pipeline.embedding.fail = False
    _, docs = consume(pipeline.stream(path))
    assert len(docs) == count == pipeline.DS.db_connection.open_table("test").count_rows()
    assert pipeline.VS._client.client.count() == count


def test_real_vector_store_filters_foreign_paper_before_ranking(stored_pipeline):
    from kotaemon.base import DocumentWithEmbedding

    pipeline, path, framework = stored_pipeline
    _, docs = consume(pipeline.stream(path))
    foreign = DocumentWithEmbedding(
        text="Evidence words", id_="foreign-chunk", embedding=[1.0, 0.0, 0.0],
        metadata={"paper_id": "p2", "file_id": "foreign-file"})
    pipeline.VS.add([foreign])
    backend = framework.FrameworkBackend(pipeline.Source, pipeline.Index, pipeline.DS,
                                         pipeline.VS, "tester", "fingerprint")
    scores, ids = backend.dense_scores([1, 0, 0], "p1", len(docs))
    assert len(scores) == len(docs)
    assert set(ids) == {d.doc_id for d in docs}
    assert "foreign-chunk" not in ids


def test_resume_after_vector_commit_before_relation_commit(stored_pipeline, monkeypatch):
    pipeline, path, framework = stored_pipeline
    original = framework.record_relationships
    failed = []

    def fail_once(index, file_id, ids, kind):
        if kind == "vector" and not failed:
            failed.append(True)
            raise RuntimeError("simulated relation commit failure")
        return original(index, file_id, ids, kind)

    monkeypatch.setattr(framework, "record_relationships", fail_once)
    with pytest.raises(RuntimeError, match="relation commit"):
        consume(pipeline.stream(path))
    file_id, docs = consume(pipeline.stream(path))
    assert framework.relationships(pipeline.Index, file_id, "vector") == {d.doc_id for d in docs}
    assert pipeline.VS._client.client.count() == len(docs)
    assert pipeline.DS.db_connection.open_table("test").count_rows() == len(docs)


def test_storage_fingerprint_change_fails_closed(stored_pipeline):
    pipeline, path, _ = stored_pipeline
    consume(pipeline.stream(path))
    pipeline.fingerprint = "changed"
    with pytest.raises(ValueError, match="fingerprint changed"):
        consume(pipeline.stream(path))


def test_changed_file_rejected_before_any_new_chunks(stored_pipeline):
    pipeline, path, _ = stored_pipeline
    _, docs = consume(pipeline.stream(path))
    document, paragraphs = convert_paper("p1", paper("Completely different body " * 10), "train")
    path.write_text(json.dumps({"schema": "scholarlens.paper.v1", "paper": document, "paragraphs": paragraphs}))
    with pytest.raises(ValueError, match="Source file changed"):
        consume(pipeline.stream(path))
    assert pipeline.VS._client.client.count() == len(docs)
    assert pipeline.DS.db_connection.open_table("test").count_rows() == len(docs)


def test_resume_after_source_registration_before_note_commit(stored_pipeline):
    pipeline, path, _ = stored_pipeline
    registered_id = pipeline.store_file(path)
    file_id, docs = consume(pipeline.stream(path))
    assert file_id == registered_id
    assert pipeline.VS._client.client.count() == len(docs)


def test_cli_rejects_settings_different_from_registered_ui(monkeypatch):
    import scholarlens.framework as framework

    active = {"index": {"retrieval": {"k1": 1.5}}}
    changed = {"index": {"retrieval": {"k1": 2.0}}}
    monkeypatch.setattr(framework, "index_context", lambda path=None:
                        (None, changed if path else active, None, {"fingerprint": "same"}))
    with pytest.raises(ValueError, match="registered UI configuration"):
        framework.application_retriever("changed.json", "p1")
