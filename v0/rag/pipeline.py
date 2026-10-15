"""Assemble context, prompts, and auditable query records."""

import json
from pathlib import Path

from rag.generation import MockGenerator
from rag.retrieval import top_k_results


def build_context(results: list[dict]) -> str:
    return "\n\n".join(
        (
            f"[{item['source_name']} | {item['chunk_id']} | "
            f"{item['score']:.4f}]\n{item['text']}"
        )
        for item in results
    )


def build_prompt(query: str, context: str) -> str:
    return (
        "仅依据以下上下文回答问题；引用方括号中的来源标签。"
        f"\n\n上下文：\n{context}\n\n问题：{query}"
    )


def save_query_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def answer_from_vectors(
    query: str,
    query_embedding,
    embedding_matrix,
    chunks: list[dict],
    k: int = 3,
) -> dict:
    results = top_k_results(query_embedding, embedding_matrix, chunks, k)
    context = build_context(results)
    prompt = build_prompt(query, context)
    return {
        "query": query,
        "retrieval_results": results,
        "context": context,
        "prompt": prompt,
        "answer": MockGenerator().generate(prompt, results),
        "generator": "mock",
    }
