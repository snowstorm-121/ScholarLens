"""Recompute the pre-registered T7 Dev matrix; no retrieval/model/Test calls."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scholarlens.data import sha256
from scholarlens.dev_experiments import (checked_runs, choose_chunking, choose_method,
                                         generation_cases, selected_snapshot)
from scholarlens.evaluate import publish_new, recompute, save_new


def save_same(path, value):
    if path.exists():
        if json.loads(path.read_text()) != value:
            raise ValueError(f"Existing result changed: {path}")
    else:
        save_new(path, value)


def publish_same(path, text):
    if path.exists():
        if path.read_text() != text:
            raise ValueError(f"Existing report changed: {path}")
    else:
        publish_new(path, text)


def matrix():
    folder = ROOT / "artifacts/evaluation"
    dirs = [folder / f"t7-1600-{method}-v2" for method in ("bm25", "dense", "hybrid")]
    dirs.append(folder / "t7-2400-hybrid-v2")
    size = choose_chunking(dirs)
    if size == 2400:
        dirs.extend(folder / f"t7-2400-{method}-v2" for method in ("bm25", "dense"))
    return dirs, size


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["chunk", "select", "report"], required=True)
    phase = parser.parse_args().phase
    folder = ROOT / "artifacts/evaluation"
    initial = [folder / f"t7-1600-{method}-v2" for method in ("bm25", "dense", "hybrid")]
    initial.append(folder / "t7-2400-hybrid-v2")
    for directory in initial:
        manifest = json.loads((directory / "manifest.json").read_text())
        if any(sha256(ROOT / name) != value for name, value in manifest["code_sha256"].items()):
            raise ValueError("Scoring/pipeline source changed after experiment; do not freeze a mixed version")
    size = choose_chunking(initial)
    if phase == "chunk":
        print(json.dumps({"chunk_size": size, "overlap": 200}))
        return
    dirs, size = matrix()
    method = choose_method(dirs, size)
    decision = {"chunk_size": size, "method": method, "runs": [str(p) for p in dirs]}
    if phase == "select":
        save_same(ROOT / "artifacts/t7/retrieval-decision.json", decision)
        print(json.dumps(decision))
        return
    selected = selected_snapshot(dirs)
    methods = ["dense"] if method == "dense" else ["dense", method]
    gen_dirs = [folder / f"t7-{size}-{name}-generation-v2" for name in methods]
    summaries, manifests = {}, []
    generation = {}
    for name, directory in zip(methods, gen_dirs):
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest["method"] != name:
            raise ValueError("Generation directory label does not match actual manifest method")
        rows, summary = recompute(directory)
        assert len(rows) == 50 and summary["answerable"] == 40
        assert manifest["stage"] == "generation" and manifest["split"] == "dev"
        assert summary == json.loads((directory / "summary.json").read_text())["summary"]
        comparable = {k: v for k, v in manifest.items()
                      if k not in {"created_at_utc", "experiment_id", "contract", "method"}}
        if manifests and comparable != manifests[0]:
            raise ValueError("Generation comparisons changed more than retrieval method")
        manifests.append(comparable)
        summaries[name], generation[name] = summary, rows
    runs = checked_runs(dirs)
    winning = runs[size, method]["manifest"]
    for key in ("config", "code_sha256", "runtime", "freeze_sha256", "corpus_manifest_sha256", "evaluator"):
        if manifests[0][key] != winning[key]:
            raise ValueError(f"Generation contract drift: {key}")
    selected["selection"].update(status="dev_complete_pending_user_U3", ready_for_test=False,
                                  index_descriptor=winning["index"],
                                  generation_runs=[str(p) for p in gen_dirs],
                                  generation_summaries=summaries,
                                  analysis_script_sha256=sha256(Path(__file__)))
    save_same(ROOT / "configs/selected_config.json", selected)
    table = ["# T7 Dev 检索对照", "", "固定 QASPER v1 Dev 200 题；Recall/MRR 分母为 160 道可回答题。",
             "指标为完整 gold 段落 span 并集覆盖，不是官方排行榜 Recall。失败保留在分母。", "",
             "| 切分 | 方法 | EvidenceRecall@1 | @3 | @5 | AllEvidence@5 | MRR@10 | 系统错误 |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for (length, name), run in sorted(runs.items()):
        s = run["summary"]
        values = " | ".join(f"{s[k]:.6f}" for k in ("EvidenceRecall@1", "EvidenceRecall@3",
                              "EvidenceRecall@5", "AllEvidence@5", "MRR@10"))
        table.append(f"| {length}/200 | {name} | {values} | {s['system_errors']} |")
    table += ["", f"按预注册优先级选择：**{size}/200，{method}**。",
              "先比较两种 Hybrid 切分，再在胜出切分上比较三路；未进行额外参数搜索。",
              "全部原始批次保留，不证明该方法对所有语料有效；不是正式 Test 结果。",
              "", "候选配置：configs/selected_config.json；用户 U3 未完成，不标记 ready_for_test。",
              "完整问题与原文保留在忽略目录，公开报告不代替逐题审计。"]
    publish_same(ROOT / "reports/dev-retrieval.md", "\n".join(table) + "\n")
    lines = ["# T7 Dev 生成对照", "", f"同一 {size}/200 chunk 集、冻结生成 Dev 50 题（40 可回答、10 无答案）。",
             "固定 Qwen、prompt、温度/seed、8192 窗口、512 输出上限及 5 chunk/4500 token 预算。",
             "只有检索方法不同；全部首次结果保留，错误不伪装拒答。", ""]
    if method == "dense":
        lines += ["检索阶段选中的方法就是 Dense，因此只运行一次 50 题，没有伪造第二组。", ""]
    for name, s in summaries.items():
        lines += [f"## {name}", "", "| 指标 | 值 |", "|---|---:|"]
        for key in ("Answer F1", "Evidence F1", "Context EvidenceRecall", "Context AllEvidence",
                    "Correct refusal rate", "Wrong-answer rate", "Wrong refusal rate", "Citation compliance",
                    "Citation traceability", "system_errors", "System error rate", "citation_eligible",
                    "citation_compliant", "citations_parsed", "citations_valid", "unanswerable",
                    "Unanswerable system error rate", "unanswerable_correct_refusal", "unanswerable_wrong_answer",
                    "unanswerable_system_error", "answerable_refusal"):
            lines.append(f"| {key} | {'N/A' if s[key] is None else s[key]} |")
        answerable = [r for r in generation[name] if r["answerable"]]
        lines += ["", "官方整体 F1 分母为 50；以下为 40 道可回答题的单题分数均值，单列观察，不替代官方整体口径。",
                  f"可回答 Answer F1：{sum(r['metrics']['Answer F1'] for r in answerable) / len(answerable):.6f}；"
                  f"可回答 Evidence F1：{sum(r['metrics']['Evidence F1'] for r in answerable) / len(answerable):.6f}。"]
        lines += [""]
    lines += ["官方 F1 是词面/原始段落匹配，不等于所有事实语义正确。完整段落 Evidence F1 与实际 context 覆盖分开报告。",
              "引用可追溯不证明引用支持全部关键陈述；未自动认证人工支持率。",
              "", "失败案例见 dev-errors.md；用户 U3 未完成，最终 Test 冻结仍待确认。"]
    publish_same(ROOT / "reports/dev-generation.md", "\n".join(lines) + "\n")
    candidates = generation_cases(gen_dirs[-1])
    review_pool = [c for c in candidates if c["provisional_category"] != "success_boundary"]
    if len(review_pool) < 10:
        review_pool += [c for c in candidates if c["provisional_category"] == "success_boundary"]
    chosen, categories = [], set()
    for case in review_pool:
        if case["provisional_category"] not in categories:
            chosen.append(case)
            categories.add(case["provisional_category"])
    chosen.extend(c for c in review_pool if c not in chosen)
    cases = chosen[:10]
    save_same(ROOT / "artifacts/t7/error-review-cases.json", cases)
    result = {"retrieval": {f"{size}:{name}": run["summary"] for (size, name), run in runs.items()},
              "generation": summaries, "decision": decision, "question_ids_equal": True,
              "candidate_config_sha256": sha256(ROOT / "configs/selected_config.json"),
              "user_U3": "pending", "test_scoring": False}
    save_same(ROOT / "artifacts/t7/verification.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
