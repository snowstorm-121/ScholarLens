# RAG Minimal Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local, transparent RAG pipeline that indexes four approved Chinese notes and records every retrieval and mock answer.

**Architecture:** Plain Python modules own documents, embeddings, retrieval, generation, and pipeline orchestration. JSONL plus NPY provide inspectable persistent storage; a mock generator keeps the answer stage replaceable without an API.

**Tech Stack:** Python 3.11, standard-library `unittest`, NumPy, sentence-transformers, `BAAI/bge-small-zh-v1.5` on CPU.

## Global Constraints

- Work directly in `Stage_6_Projects/rag-minimal`; do not modify Stage 5 files.
- Read only the four approved source notes specified in the design document.
- Use no LangChain, LlamaIndex, vector database, reranker, hybrid search, query rewriting, API, or local LLM.
- Keep source documents in place; persist only derived chunks, vectors, manifests, and query records inside this project.
- Use CPU until `torch.backends.mps.is_available()` is true in this runtime.
- Every production function is introduced through a failing `unittest` test.

---

### Task 1: Document contracts and offline chunk preparation

**Files:**
- Create: `rag/__init__.py`
- Create: `rag/documents.py`
- Create: `tests/__init__.py`
- Create: `tests/test_documents.py`

**Interfaces:**
- Consumes: absolute UTF-8 `.md` or `.txt` paths.
- Produces: `Chunk` objects and JSONL/manifest-ready dictionaries.
- Exports: `normalize_text(text)`, `chunk_text(text, chunk_size, overlap)`, `build_chunks(source_paths, chunk_size=500, overlap=80)`.

- [ ] **Step 1: Write the failing document tests**

```python
import tempfile
import unittest
from pathlib import Path

from rag.documents import build_chunks, chunk_text, normalize_text


class DocumentTests(unittest.TestCase):
    def test_normalize_text_preserves_headings_and_collapses_blank_lines(self):
        self.assertEqual(normalize_text("\r\n# 标题\r\n\r\n\r\n正文  \r\n"), "# 标题\n\n正文")

    def test_chunk_text_keeps_requested_overlap(self):
        chunks = chunk_text("abcdefghij", chunk_size=6, overlap=2)
        self.assertEqual(chunks, ["abcdef", "efghij"])

    def test_build_chunks_preserves_source_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "note.md"
            source.write_text("# 标题\n正文内容", encoding="utf-8")
            chunks = build_chunks([source], chunk_size=100, overlap=10)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["source_name"], "note.md")
        self.assertEqual(chunks[0]["chunk_id"], "note-0001")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify RED**

Run: `PYTHONPATH=. /opt/miniconda3/envs/pytorch_env/bin/python -m unittest tests.test_documents -v`

Expected: import failure because `rag.documents` does not yet exist.

- [ ] **Step 3: Implement the minimal document module**

```python
from pathlib import Path
import re


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap must be smaller")
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks


def build_chunks(source_paths: list[Path], chunk_size: int = 500, overlap: int = 80) -> list[dict]:
    chunks = []
    for source_path in source_paths:
        if source_path.suffix.lower() not in {".md", ".txt"}:
            raise ValueError(f"unsupported source extension: {source_path}")
        text = normalize_text(source_path.read_text(encoding="utf-8"))
        for index, chunk in enumerate(chunk_text(text, chunk_size, overlap), start=1):
            chunks.append({"chunk_id": f"{source_path.stem}-{index:04d}", "source_path": str(source_path), "source_name": source_path.name, "chunk_index": index, "text": chunk})
    return chunks
```

- [ ] **Step 4: Run the test and verify GREEN**

Run: `PYTHONPATH=. /opt/miniconda3/envs/pytorch_env/bin/python -m unittest tests.test_documents -v`

Expected: 3 tests pass.

---

### Task 2: Embedding matrix persistence

**Files:**
- Create: `rag/embeddings.py`
- Create: `tests/test_embeddings.py`

**Interfaces:**
- Consumes: chunk dictionaries with a `text` field and a loaded sentence-transformers model.
- Produces: a float32 matrix `E [N, D]` and an NPY file.
- Exports: `encode_texts(model, texts)`, `save_embeddings(path, matrix)`, `load_embeddings(path)`.

- [ ] **Step 1: Write the failing embedding persistence test**

```python
import tempfile
import unittest
from pathlib import Path
import numpy as np

from rag.embeddings import load_embeddings, save_embeddings


class EmbeddingTests(unittest.TestCase):
    def test_saved_embeddings_round_trip_as_float32(self):
        matrix = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "embeddings.npy"
            save_embeddings(path, matrix)
            restored = load_embeddings(path)
        self.assertEqual(restored.dtype, np.float32)
        np.testing.assert_array_equal(restored, matrix)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=. /opt/miniconda3/envs/pytorch_env/bin/python -m unittest tests.test_embeddings -v`

Expected: import failure because `rag.embeddings` does not yet exist.

- [ ] **Step 3: Implement the minimal embedding module**

```python
from pathlib import Path
import numpy as np


def encode_texts(model, texts: list[str]) -> np.ndarray:
    return np.asarray(model.encode(texts, normalize_embeddings=True), dtype=np.float32)


def save_embeddings(path: Path, matrix: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, np.asarray(matrix, dtype=np.float32))


def load_embeddings(path: Path) -> np.ndarray:
    return np.load(path).astype(np.float32, copy=False)
```

- [ ] **Step 4: Run GREEN**

Run: `PYTHONPATH=. /opt/miniconda3/envs/pytorch_env/bin/python -m unittest tests.test_embeddings -v`

Expected: 1 test passes.

---

### Task 3: Cosine Top-k retrieval

**Files:**
- Create: `rag/retrieval.py`
- Create: `tests/test_retrieval.py`

**Interfaces:**
- Consumes: normalized query vector `[D]`, matrix `E [N, D]`, chunk dictionaries, and `k`.
- Produces: `scores [N]` and ranked result dictionaries.
- Exports: `cosine_scores(query_embedding, embedding_matrix)`, `top_k_results(query_embedding, embedding_matrix, chunks, k)`.

- [ ] **Step 1: Write the failing retrieval test**

```python
import unittest
import numpy as np

from rag.retrieval import cosine_scores, top_k_results


class RetrievalTests(unittest.TestCase):
    def test_top_k_returns_highest_score_first_with_source(self):
        matrix = np.array([[1.0, 0.0], [0.0, 1.0], [0.8, 0.6]], dtype=np.float32)
        query = np.array([1.0, 0.0], dtype=np.float32)
        chunks = [{"chunk_id": "a", "source_name": "a.md", "text": "A"}, {"chunk_id": "b", "source_name": "b.md", "text": "B"}, {"chunk_id": "c", "source_name": "c.md", "text": "C"}]
        self.assertEqual(cosine_scores(query, matrix).shape, (3,))
        results = top_k_results(query, matrix, chunks, k=2)
        self.assertEqual([item["chunk_id"] for item in results], ["a", "c"])
        self.assertEqual(results[0]["rank"], 1)
        self.assertEqual(results[0]["source_name"], "a.md")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=. /opt/miniconda3/envs/pytorch_env/bin/python -m unittest tests.test_retrieval -v`

Expected: import failure because `rag.retrieval` does not yet exist.

- [ ] **Step 3: Implement the minimal retrieval module**

```python
import numpy as np


def cosine_scores(query_embedding: np.ndarray, embedding_matrix: np.ndarray) -> np.ndarray:
    query = query_embedding / np.linalg.norm(query_embedding)
    matrix = embedding_matrix / np.linalg.norm(embedding_matrix, axis=1, keepdims=True)
    return matrix @ query


def top_k_results(query_embedding, embedding_matrix, chunks, k: int) -> list[dict]:
    if len(chunks) != len(embedding_matrix):
        raise ValueError("chunk count and embedding rows differ")
    scores = cosine_scores(query_embedding, embedding_matrix)
    indices = np.argsort(-scores)[:k]
    return [{**chunks[index], "rank": rank, "score": float(scores[index])} for rank, index in enumerate(indices, start=1)]
```

- [ ] **Step 4: Run GREEN**

Run: `PYTHONPATH=. /opt/miniconda3/envs/pytorch_env/bin/python -m unittest tests.test_retrieval -v`

Expected: 1 test passes.

---

### Task 4: Context, prompt, mock generation, and audit record

**Files:**
- Create: `rag/generation.py`
- Create: `rag/pipeline.py`
- Create: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: query and ranked retrieval-result dictionaries.
- Produces: context, prompt, deterministic mock answer, and JSON record.
- Exports: `MockGenerator.generate(prompt, sources)`, `build_context(results)`, `build_prompt(query, context)`, `save_query_record(path, record)`.

- [ ] **Step 1: Write the failing pipeline test**

```python
import json
import tempfile
import unittest
from pathlib import Path

from rag.generation import MockGenerator
from rag.pipeline import build_context, build_prompt, save_query_record


class PipelineTests(unittest.TestCase):
    def test_record_contains_query_context_prompt_answer_and_sources(self):
        results = [{"chunk_id": "rag-0001", "source_name": "rag.md", "score": 0.9, "text": "RAG 使用检索上下文。"}]
        context = build_context(results)
        prompt = build_prompt("RAG 是什么？", context)
        answer = MockGenerator().generate(prompt, results)
        record = {"query": "RAG 是什么？", "retrieval_results": results, "context": context, "prompt": prompt, "answer": answer, "generator": "mock"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "query.json"
            save_query_record(path, record)
            restored = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("[rag.md | rag-0001 | 0.9000]", restored["context"])
        self.assertIn("仅依据以下上下文", restored["prompt"])
        self.assertEqual(restored["retrieval_results"][0]["chunk_id"], "rag-0001")
        self.assertIn("mock", restored["answer"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=. /opt/miniconda3/envs/pytorch_env/bin/python -m unittest tests.test_pipeline -v`

Expected: import failure because `rag.generation` and `rag.pipeline` do not yet exist.

- [ ] **Step 3: Implement minimal pipeline components**

```python
# rag/generation.py
class MockGenerator:
    def generate(self, prompt: str, sources: list[dict]) -> str:
        labels = ", ".join(item["chunk_id"] for item in sources)
        return f"[mock] 未调用语言模型；可用来源：{labels}"


# rag/pipeline.py
import json
from pathlib import Path


def build_context(results: list[dict]) -> str:
    return "\n\n".join(f"[{item['source_name']} | {item['chunk_id']} | {item['score']:.4f}]\n{item['text']}" for item in results)


def build_prompt(query: str, context: str) -> str:
    return f"仅依据以下上下文回答问题；引用方括号中的来源标签。\n\n上下文：\n{context}\n\n问题：{query}"


def save_query_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run GREEN**

Run: `PYTHONPATH=. /opt/miniconda3/envs/pytorch_env/bin/python -m unittest tests.test_pipeline -v`

Expected: 1 test passes.

---

### Task 5: Offline build and online query entrypoints

**Files:**
- Create: `build_index.py`
- Create: `ask.py`
- Create: `tests/test_end_to_end.py`

**Interfaces:**
- Consumes: the four approved source paths, model name, `data/` files, query, and Top-k.
- Produces: `chunks.jsonl`, `manifest.json`, `embeddings.npy`, console evidence, and an artifact JSON file.

- [ ] **Step 1: Write the failing end-to-end test with injected vectors**

```python
import unittest
import numpy as np

from rag.pipeline import answer_from_vectors


class EndToEndTests(unittest.TestCase):
    def test_answer_from_vectors_returns_auditable_record(self):
        chunks = [{"chunk_id": "a", "source_name": "a.md", "text": "RAG 使用检索。"}]
        record = answer_from_vectors("RAG 是什么？", np.array([1.0, 0.0], dtype=np.float32), np.array([[1.0, 0.0]], dtype=np.float32), chunks, k=1)
        self.assertEqual(record["retrieval_results"][0]["chunk_id"], "a")
        self.assertEqual(record["generator"], "mock")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run RED**

Run: `PYTHONPATH=. /opt/miniconda3/envs/pytorch_env/bin/python -m unittest tests.test_end_to_end -v`

Expected: import failure because `answer_from_vectors` does not yet exist.

- [ ] **Step 3: Add orchestration and complete command-line scripts**

```python
# add to rag/pipeline.py
from rag.retrieval import top_k_results
from rag.generation import MockGenerator


def answer_from_vectors(query, query_embedding, embedding_matrix, chunks, k=3):
    results = top_k_results(query_embedding, embedding_matrix, chunks, k)
    context = build_context(results)
    prompt = build_prompt(query, context)
    return {"query": query, "retrieval_results": results, "context": context, "prompt": prompt, "answer": MockGenerator().generate(prompt, results), "generator": "mock"}


# build_index.py
import json
from pathlib import Path
from sentence_transformers import SentenceTransformer

from rag.documents import build_chunks
from rag.embeddings import encode_texts, save_embeddings

PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
SOURCE_PATHS = [
    Path("/Users/yyy/Documents/知识库/Notes/Pytorch学习/stage6/Stage 6 学习笔记：RAG 理论学习与复盘.md"),
    Path("/Users/yyy/Documents/知识库/Notes/Pytorch学习/stage5/Stage 5 学习笔记：BERT 全量微调与 LoRA 参数高效微调对比实验.md"),
    Path("/Users/yyy/Documents/知识库/Notes/Pytorch学习/stage4/Day 3 学习笔记：HuggingFace BERT tokenizer 与 DataLoader.md"),
    Path("/Users/yyy/Documents/知识库/Notes/Pytorch学习/stage4/Day 1 学习笔记：Attention 机制原理——Scaled Dot-Product Attention.md"),
]
MODEL_NAME = "BAAI/bge-small-zh-v1.5"

chunks = build_chunks(SOURCE_PATHS)
if not chunks:
    raise ValueError("no non-empty chunks were built")
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "chunks.jsonl").write_text("\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")
model = SentenceTransformer(MODEL_NAME, device="cpu")
matrix = encode_texts(model, [chunk["text"] for chunk in chunks])
save_embeddings(DATA_DIR / "embeddings.npy", matrix)
manifest = {"model_name": MODEL_NAME, "device": "cpu", "source_paths": [str(path) for path in SOURCE_PATHS], "chunk_size": 500, "overlap": 80, "chunk_count": len(chunks), "vector_dimension": int(matrix.shape[1])}
(DATA_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"chunks={len(chunks)}")
print(f"embedding_shape={matrix.shape}")
print(f"data_dir={DATA_DIR}")


# ask.py
import argparse
import json
from pathlib import Path
from uuid import uuid4
from sentence_transformers import SentenceTransformer

from rag.embeddings import encode_texts, load_embeddings
from rag.pipeline import answer_from_vectors, save_query_record

parser = argparse.ArgumentParser()
parser.add_argument("query")
parser.add_argument("--top-k", type=int, default=3)
args = parser.parse_args()
if not args.query.strip():
    raise ValueError("query must not be empty")
if args.top_k <= 0:
    raise ValueError("top-k must be positive")
project_root = Path(__file__).resolve().parent
data_dir = project_root / "data"
chunks_path = data_dir / "chunks.jsonl"
matrix_path = data_dir / "embeddings.npy"
if not chunks_path.exists() or not matrix_path.exists():
    raise FileNotFoundError("build the index before asking a question")
chunks = [json.loads(line) for line in chunks_path.read_text(encoding="utf-8").splitlines()]
matrix = load_embeddings(matrix_path)
if len(chunks) != matrix.shape[0]:
    raise ValueError("chunk count and embedding rows differ")
model = SentenceTransformer("BAAI/bge-small-zh-v1.5", device="cpu")
query_embedding = encode_texts(model, [args.query])[0]
record = answer_from_vectors(args.query, query_embedding, matrix, chunks, k=min(args.top_k, len(chunks)))
artifact_path = project_root / "artifacts" / "queries" / f"{uuid4().hex}.json"
save_query_record(artifact_path, record)
print(f"query_embedding_shape={query_embedding.shape}")
print(f"scores_shape=({matrix.shape[0]},)")
for item in record["retrieval_results"]:
    print(f"rank={item['rank']} score={item['score']:.4f} source={item['source_name']} chunk={item['chunk_id']}")
print("context:\n" + record["context"])
print("prompt:\n" + record["prompt"])
print("answer:\n" + record["answer"])
print(f"artifact={artifact_path}")
```

- [ ] **Step 4: Run GREEN and the real smoke run**

Run: `PYTHONPATH=. /opt/miniconda3/envs/pytorch_env/bin/python -m unittest discover -s tests -v`

Expected: all unit tests pass.

Run: `PYTHONPATH=. /opt/miniconda3/envs/pytorch_env/bin/python build_index.py`

Expected: reports a nonzero chunk count and `E [N, 512]`.

Run: `PYTHONPATH=. /opt/miniconda3/envs/pytorch_env/bin/python ask.py "RAG 与 LoRA 的区别" --top-k 2`

Expected: prints query vector `[512]`, scores `[N]`, two ranked chunks with sources, context, prompt, mock answer, and an artifact path.

## Plan self-review

- Spec coverage: Tasks 1–5 cover document loading, cleanup, chunks/metadata, vector persistence, cosine Top-k, context/Prompt, replaceable mock generation, audit records, tests, and end-to-end evidence.
- Scope check: no task adds a framework, database, reranker, API, local LLM, or unrelated feature.
- Type consistency: the same chunk dictionary flows from Task 1 through Task 5; vector matrix rows match chunk order.
- Placeholder scan: no incomplete implementation instructions remain.
