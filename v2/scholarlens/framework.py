"""Thin adapters over existing file identity tables, LanceDB and Chroma APIs."""

from pathlib import Path

from ktem.db.models import engine
from ktem.index.file.base import BaseFileIndexRetriever
from ktem.index.file.pipelines import IndexDocumentPipeline, IndexPipeline
from llama_index.core.readers.base import BaseReader
from llama_index.core.vector_stores import MetadataFilter, MetadataFilters
from sqlalchemy import select
from sqlalchemy.orm import Session

from kotaemon.base import Document, DocumentWithEmbedding, RetrievedDocument
from kotaemon.embeddings import BaseEmbeddings

from .embedding import NomicEncoder
from .data import sha256
from .indexing import index_context, read_paper
from .retrieval import Retriever


class NomicEmbeddings(BaseEmbeddings):
    model_config: dict

    def run(self, text, **kwargs):
        docs = text if isinstance(text, list) else [text]
        if not all(isinstance(doc, Document) for doc in docs):
            raise ValueError("Document encoder only accepts Documents; query role is explicit")
        vectors = NomicEncoder(self.model_config).encode([d.text for d in docs], "document")
        return [DocumentWithEmbedding(**{**doc.to_dict(), "embedding": vector.tolist()})
                for doc, vector in zip(docs, vectors)]


class QasperReader(BaseReader):
    def __init__(self, settings):
        self.settings = settings

    def load_data(self, file, extra_info=None):
        _, chunks = read_paper(file, self.settings)
        return [Document(id_=row["chunk_id"], text=row["text"],
                         metadata={**row["metadata"], **(extra_info or {})}) for row in chunks]


def relationships(index, file_id, kind):
    with Session(engine) as session:
        return {row[0] for row in session.execute(select(index.target_id).where(
            index.source_id == file_id, index.relation_type == kind))}


def record_relationships(index, file_id, ids, kind):
    missing = set(ids) - relationships(index, file_id, kind)
    if missing:
        with Session(engine) as session:
            session.add_all([index(source_id=file_id, target_id=cid, relation_type=kind)
                             for cid in sorted(missing)])
            session.commit()


class ScholarPaperPipeline(IndexPipeline):
    fingerprint: str
    scholar_settings: dict

    def stream(self, file_path, reindex=False, **kwargs):
        file_path = Path(file_path)
        paper, _ = read_paper(file_path, self.scholar_settings)
        file_id = self.get_id_if_exists(file_path)
        if file_id is None:
            file_id = self.store_file(file_path)
        with Session(engine) as session:
            source = session.get(self.Source, file_id)
            note = dict(source.note)
            if source.path != sha256(file_path):
                raise ValueError("Source file changed: use a new corpus/index version")
            if not note:
                if any(relationships(self.Index, file_id, kind) for kind in ("document", "vector")):
                    raise ValueError("Uninitialized source has conflicting relationships")
                note = {"fingerprint": self.fingerprint, "paper_id": paper["paper_id"],
                        "title": paper["title"], "source_url": paper["source_url"], "complete": False}
                source.note = note
                session.commit()
        if note.get("fingerprint") != self.fingerprint or note.get("paper_id") != paper["paper_id"]:
            raise ValueError("Index fingerprint changed: use a separate new collection, not implicit overwrite")
        docs = self.loader.load_data(file_path, extra_info={"file_id": file_id,
                                     "file_name": file_path.name, "collection_name": "ScholarLens"})
        expected = {d.doc_id for d in docs}
        if len(expected) != len(docs):
            raise ValueError("Duplicate stable chunk IDs")
        stored = {d.doc_id: d for d in self.DS.get(sorted(expected))}
        if any(stored[cid].text != d.text or stored[cid].metadata != d.metadata
               for d in docs if (cid := d.doc_id) in stored):
            raise ValueError("Persisted chunk differs from original text/metadata")
        missing_docs = [d for d in docs if d.doc_id not in stored]
        if missing_docs:
            # BM25 uses rank-bm25, so avoid rebuilding unrelated Lance full-text indexes.
            self.DS.add(missing_docs, refresh_indices=False)
        record_relationships(self.Index, file_id, expected, "document")
        collection = self.VS._client.client
        if (collection.metadata or {}).get("hnsw:space", "l2") != "l2":
            raise ValueError("Unexpected Chroma distance space")
        existing = set(collection.get(ids=sorted(expected), include=[])["ids"])
        missing_vectors = [d for d in docs if d.doc_id not in existing]
        for start in range(0, len(missing_vectors), self.chunk_batch_size):
            batch = missing_vectors[start:start + self.chunk_batch_size]
            self.vector_indexing.add_to_vectorstore(batch)
            record_relationships(self.Index, file_id, [d.doc_id for d in batch], "vector")
            yield Document(f"Encoded {min(start + len(batch), len(missing_vectors))}/{len(missing_vectors)}", channel="debug")
        # Also repairs a crash between vector-store commit and relation-table commit.
        record_relationships(self.Index, file_id, existing, "vector")
        if (relationships(self.Index, file_id, "document") != expected
                or relationships(self.Index, file_id, "vector") != expected):
            raise ValueError("Document/vector relation alignment mismatch")
        with Session(engine) as session:
            source = session.get(self.Source, file_id)
            source.note = {**note, "complete": True, "chunks": len(docs)}
            session.commit()
        yield Document(f"Ready {paper['paper_id']}: {len(docs)} chunks", channel="debug")
        return file_id, docs


class ScholarIndexPipeline(IndexDocumentPipeline):
    scholar_settings: dict
    fingerprint: str

    @classmethod
    def get_user_settings(cls):
        return {}

    @classmethod
    def get_pipeline(cls, user_settings, index_settings):
        _, config, _, descriptor = index_context()
        encoder = NomicEncoder(config["index"]["embedding"])
        encoder.verify_model()
        return cls(embedding=NomicEmbeddings(model_config=config["index"]["embedding"]),
                   scholar_settings=config["index"], fingerprint=descriptor["fingerprint"],
                   reader_mode="default", run_embedding_in_thread=False)

    def route(self, file_path):
        if not isinstance(file_path, Path) or not file_path.name.endswith(".qasper.json"):
            raise ValueError("Only .qasper.json body exports are accepted; no URL/PDF/QA ingestion")
        return ScholarPaperPipeline(loader=QasperReader(self.scholar_settings), splitter=None,
                                    embedding=self.embedding, fingerprint=self.fingerprint,
                                    scholar_settings=self.scholar_settings,
                                    chunk_batch_size=self.scholar_settings["batch_size"],
                                    run_embedding_in_thread=False, Source=self.Source, Index=self.Index,
                                    VS=self.VS, DS=self.DS, FSPath=self.FSPath,
                                    user_id=self.user_id, private=self.private)


class FrameworkBackend:
    def __init__(self, source, index, ds, vs, user_id, fingerprint):
        self.source, self.index, self.ds, self.vs = source, index, ds, vs
        self.user_id, self.fingerprint = user_id, fingerprint

    def source_for(self, paper_id=None, file_id=None):
        with Session(engine) as session:
            stmt = select(self.source).where(self.source.user == self.user_id)
            if file_id is not None:
                stmt = stmt.where(self.source.id == file_id)
            else:
                stmt = stmt.where(self.source.name == paper_id + ".qasper.json")
            source = session.execute(stmt).scalar_one_or_none()
            if source is None or not source.note.get("complete"):
                raise ValueError("Selected QASPER paper is not fully indexed")
            if source.note.get("fingerprint") != self.fingerprint:
                raise ValueError("Index fingerprint mismatch")
            return source.id, dict(source.note)

    def paper_documents(self, paper_id):
        file_id, note = self.source_for(paper_id=paper_id)
        ids = sorted(relationships(self.index, file_id, "document"))
        docs = self.ds.get(ids)
        if len(docs) != note["chunks"] or any(d.metadata["file_id"] != file_id for d in docs):
            raise ValueError("Stored paper/chunk identity mismatch")
        return docs

    def dense_scores(self, vector, paper_id, count):
        file_id, _ = self.source_for(paper_id=paper_id)
        # Mandatory storage-side prefilter: the upstream Chroma adapter ignores node_ids.
        filters = MetadataFilters(filters=[MetadataFilter(key="paper_id", value=paper_id),
                                            MetadataFilter(key="file_id", value=file_id)])
        _, scores, ids = self.vs.query(embedding=vector, top_k=count, filters=filters)
        return scores, ids


class ScholarRetrieverPipeline(BaseFileIndexRetriever):
    selected: list = []
    method: str = "hybrid"
    top_k: int = 5
    scholar_settings: dict
    fingerprint: str

    @classmethod
    def get_user_settings(cls):
        return {"scholar_method": {"name": "ScholarLens retrieval", "value": "hybrid",
                                   "choices": [("BM25", "bm25"), ("Dense", "dense"), ("RRF Hybrid", "hybrid")],
                                   "component": "dropdown"}}

    @classmethod
    def get_pipeline(cls, user_settings, index_settings, selected=None):
        _, config, _, descriptor = index_context()
        return cls(selected=selected or [], method=user_settings.get("scholar_method", config["index"]["retrieval"]["method"]),
                   scholar_settings=config["index"], fingerprint=descriptor["fingerprint"])

    def backend(self):
        return FrameworkBackend(self.Source, self.Index, self.DS, self.VS, self.user_id, self.fingerprint)

    def retrieve(self, query, paper_id, method=None, k=5, *, trace=None):
        encoder = NomicEncoder(self.scholar_settings["embedding"])
        if (method or self.method) != "bm25":
            encoder.verify_model()
        return Retriever(self.backend(), encoder, self.scholar_settings["retrieval"]).retrieve(
            query, paper_id, method or self.method, k, trace=trace)

    def run(self, text, doc_ids=None, **kwargs):
        selected = self.selected if doc_ids is None else doc_ids
        if not selected:
            return []
        if len(selected) != 1 or selected[0].startswith("["):
            raise ValueError("Select exactly one QASPER paper for ScholarLens retrieval")
        _, note = self.backend().source_for(file_id=selected[0])
        rows = self.retrieve(text, note["paper_id"], self.method, self.top_k)
        return [RetrievedDocument(id_=r["chunk_id"], text=r["text"], score=r["score"],
                                  metadata={**r["metadata"], "retrieval_method": r["method"],
                                            "retrieval_rank": r["rank"]}) for r in rows]

    def generate_relevant_scores(self, query, documents):
        return documents


def application_retriever(config_path, paper_id, method="hybrid"):
    """Resolve the same registered FileIndex/selector/factory used by the web app."""
    _, config, _, descriptor = index_context(config_path)
    _, active, _, registered = index_context()
    if config["index"] != active["index"] or descriptor != registered:
        raise ValueError("CLI index settings must match the registered UI configuration")
    from ktem.main import App

    app = App()
    # __init__ registers indices/settings; rendering pages here fetches remote Help content.
    index = next(i for i in app.index_manager.indices if i.name == config["index"]["name"])
    index.get_selector_component_ui()
    settings = app.default_settings.flatten()
    settings[f"index.options.{index.id}.scholar_method"] = method
    backend = FrameworkBackend(index._resources["Source"], index._resources["Index"],
                               index._docstore, index._vs, "default", descriptor["fingerprint"])
    file_id, _ = backend.source_for(paper_id=paper_id)
    return index.get_retriever_pipelines(settings, "default", ["select", [file_id], "default"])[0]
