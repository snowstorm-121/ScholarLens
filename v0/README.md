# V0：最小本地 RAG 检索原型

这是一个不用 LangChain、LlamaIndex 或向量数据库的学习型 RAG 基线。目标是把每个中间结果保留下来，便于观察数据流、定位检索问题，并追溯来源。

## 当前能力

```text
Markdown/TXT
  -> 清洗、固定字符切分、metadata
  -> BGE Embedding
  -> embeddings.npy: E [N, 512]
  -> 余弦相似度 scores [N]
  -> Top-k 原文、分数、来源
  -> context / Prompt
  -> mock answer + JSON 审计记录
```

`MockGenerator` 明确不会调用 LLM，因此本项目当前是“本地检索 + 可追溯问答组装原型”，不是已经接入真实生成模型的完整问答应用。

## 项目结构

```text
rag/
  documents.py    # 文档清洗、切分与 metadata
  embeddings.py   # BGE 编码与 .npy 持久化
  retrieval.py    # 余弦分数与 Top-k
  pipeline.py     # context、Prompt、问答记录
  generation.py   # 可替换的 mock generator
build_index.py    # 离线建库入口
ask.py            # 在线检索入口
tests/            # 11 个标准库 unittest
```

## 环境

- Python 3.11+
- NumPy
- sentence-transformers
- Embedding 模型：`BAAI/bge-small-zh-v1.5`

入口脚本使用 `local_files_only=True` 加载模型：首次请自行下载模型到本机 Hugging Face 缓存，后续可离线运行。

## 运行

先在 [`build_index.py`](./build_index.py) 的 `SOURCE_PATHS` 中替换为你允许建库的本地 Markdown/TXT 路径。原始文档、索引和问答记录均不提交到仓库。

```bash
cd Stage_6_Projects/rag-minimal/v0

PYTHONPATH=. python build_index.py
PYTHONPATH=. python ask.py "RAG 与 LoRA 的区别" --top-k 2
PYTHONPATH=. python -m unittest discover -s tests -v
```

离线建库会生成：

- `data/chunks.jsonl`：chunk 原文及 metadata；
- `data/embeddings.npy`：向量矩阵 `E [N, 512]`；
- `data/manifest.json`：模型、切分参数、来源与 shape。

在线查询会在 `artifacts/queries/` 保存 query、Top-k、context、Prompt、mock answer 与 shape 信息。

## 数据完整性与已知限制

- `embeddings.npy[i]` 必须始终对应 `chunks.jsonl` 的第 `i` 条记录；行数不一致时程序会停止。
- 当前固定按 500 字符切分、80 字符 overlap；它可能把语义不完整的片段召回到 Top-k。
- 当前只有 dense vector retrieval；不包含 rerank、hybrid search 或 query rewriting。
- 真实生成器与答案质量评测属于后续阶段。
