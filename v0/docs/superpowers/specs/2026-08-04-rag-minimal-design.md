# RAG Minimal Pipeline Design

## Goal

Build a transparent local RAG pipeline for a small, fixed set of Chinese Markdown notes. Every answer must retain the query, retrieved chunks, similarity scores, sources, context, prompt, and generated answer.

## Scope and constraints

- Project path: `Stage_6_Projects/rag-minimal`.
- Source documents are read in place and are not copied into the project.
- Initial corpus contains these four Markdown files:
  1. `/Users/yyy/Documents/知识库/Notes/Pytorch学习/stage6/Stage 6 学习笔记：RAG 理论学习与复盘.md`
  2. `/Users/yyy/Documents/知识库/Notes/Pytorch学习/stage5/Stage 5 学习笔记：BERT 全量微调与 LoRA 参数高效微调对比实验.md`
  3. `/Users/yyy/Documents/知识库/Notes/Pytorch学习/stage4/Day 3 学习笔记：HuggingFace BERT tokenizer 与 DataLoader.md`
  4. `/Users/yyy/Documents/知识库/Notes/Pytorch学习/stage4/Day 1 学习笔记：Attention 机制原理——Scaled Dot-Product Attention.md`
- Embedding model: `BAAI/bge-small-zh-v1.5`, loaded on CPU. The cached model produces normalized vectors with dimension `D = 512`.
- Do not use LangChain, LlamaIndex, a vector database, reranking, hybrid search, query rewriting, an API key, or a local LLM.
- Use only Python standard library, NumPy, PyTorch, and sentence-transformers already available in `pytorch_env`.
- Tests use the standard-library `unittest` module; pytest is not required.
- MPS is not selected until `torch.backends.mps.is_available()` is true in the actual runtime.

## Architecture

```text
source Markdown/TXT files
  -> documents.py: load, normalize, chunk, metadata
  -> chunks.jsonl + manifest.json
  -> embeddings.py: encode chunks
  -> embeddings.npy, E [N, 512]
  -> retrieval.py: encode query [512], cosine scores [N], Top-k
  -> pipeline.py: context and prompt
  -> generation.py: mock generator
  -> artifacts/queries/<query-id>.json
```

The pipeline is intentionally split by data boundary, not by framework abstraction:

- `rag/documents.py` produces JSON-serializable chunks.
- `rag/embeddings.py` owns model loading and the stored vector matrix.
- `rag/retrieval.py` owns only ranking normalized vectors.
- `rag/generation.py` defines the replaceable generator protocol and an honest mock implementation.
- `rag/pipeline.py` connects the preceding modules, creates context and prompt, and writes an auditable record.

## Data contracts

### Chunk metadata

Each line in `data/chunks.jsonl` is one object:

```json
{
  "chunk_id": "source-0001",
  "source_path": "/absolute/path/to/note.md",
  "source_name": "note.md",
  "chunk_index": 1,
  "text": "cleaned chunk text"
}
```

`documents.py` accepts UTF-8 `.md` and `.txt` files. It normalizes line endings, trims leading and trailing whitespace, collapses runs of blank lines, and preserves headings and ordinary text. It uses fixed character chunks of 500 characters with an 80-character overlap. These values are stored in the manifest so a rebuilt index remains comparable.

### Index files

- `data/manifest.json` records model name, device choice, source paths, chunk parameters, chunk count, and vector dimension.
- `data/embeddings.npy` stores `E` as `float32` with shape `[N, 512]`; row `i` corresponds to line `i` in `chunks.jsonl`.

### Retrieval result

For a query, `retrieval.py` creates normalized `query_embedding [512]`, calculates cosine scores `scores [N]`, and returns at most `k` results. Each result includes `chunk_id`, `text`, source metadata, rank, and score. The initial default is `k = 3`.

### Query record

`artifacts/queries/<query-id>.json` contains:

```json
{
  "query": "RAG 与 LoRA 的区别",
  "retrieval_results": [],
  "context": "",
  "prompt": "",
  "answer": "",
  "generator": "mock"
}
```

The context labels every chunk with its source name, chunk id, and score. The prompt instructs the generator to answer only from the context and to cite those source labels. The mock generator does not claim that it performed real language generation; it returns a deterministic placeholder response plus the supplied source labels.

## Entrypoints and failure boundaries

- `build_index.py` is the offline entrypoint. It reports source count, chunk count, `E` shape, model name, and output paths.
- `ask.py` is the online entrypoint. It accepts a query and optional Top-k, prints ranked results, context, prompt, and answer, then writes one query record.
- An empty source file is skipped with a clear message. An unsupported extension, missing source file, missing index file, empty query, or incompatible matrix/chunk count stops with a specific error before generation.
- A retrieval failure is observable through unexpected Top-k chunks or scores. A generation failure is isolated to the generator output. A citation failure is observable by comparing the answer citations with `retrieval_results`.

## Tests and acceptance evidence

- `tests/test_documents.py` verifies normalization, chunk overlap, and metadata/source preservation using temporary local files.
- `tests/test_retrieval.py` verifies normalized cosine ranking and Top-k ordering with fixed small NumPy vectors; it does not download a model.
- `tests/test_pipeline.py` verifies context, prompt, mock generator output, and saved query-record fields with injected fixed retrieval results.
- An end-to-end smoke run uses the four approved notes and cached BGE model. Evidence must show `E [N, 512]`, a query vector `[512]`, score vector `[N]`, three ranked chunks with sources, an assembled prompt, and a saved JSON record.

## Out of scope

No additional retrieval strategies, UI, web service, vector database, evaluation benchmark, API-backed generation, local LLM, document copying, or Git/GitHub automation is included in the first version.
