# Dev annotation decisions

- `dev-002`: The initial wording only asked about Ollama streaming. It was narrowed to compare the REST API and SDK defaults because the selected evidence supports those two explicit states.
- `dev-003`: The initial wording included “Instruct”. It was removed because the selected gold span contains only the stable command `ollama run qwen2.5:7b`; the revised question makes no claim beyond that span.
- `dev-010`: A broader candidate asked how to use structured outputs reliably. It was replaced with the two specific, complementary actions supported by separate evidence: schema definition and lowering temperature.
- `dev-028` to `dev-030`: These are near-domain unanswerable questions. The frozen normalized corpus contains no occurrences of the capability terms `retry`, `hybrid`, or `rerank`; they therefore have no gold evidence and do not assert anything about product capabilities outside this corpus snapshot.
