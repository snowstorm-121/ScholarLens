# 实现与设计取舍

ScholarLens 的核心是把一次回答拆成可检查的步骤：限定论文、检索证据、构建上下文、调用模型、校验引用。[首页](../../README.md)提供演示与结果，本页按数据流说明关键实现。

## 正文和标注分开

`data.py` 转换 QASPER 正文，记录 `paper_id`、稳定 `paragraph_id` 和规范化字符半开区间。问题、答案及 evidence 标注单独导出，不进入检索索引。`dataset.py` 在这些位置上构建题集，避免切分参数变化后 gold 跟着 chunk ID 变化。

一个 gold 段落可以由多个相邻或重叠块覆盖；指标按字符区间并集判断是否完整覆盖，不因重叠重复加分。位置核对证明文本可定位，不自动证明标注的语义正确。

代码：[data.py](../../scholarlens/data.py)、[dataset.py](../../scholarlens/dataset.py)、[metrics.py](../../scholarlens/metrics.py)。

## 为什么限定单篇论文

论文中的相似术语、方法名和实验设置容易互相干扰。检索先按用户选定的 `paper_id` 和文件身份过滤，再计算 BM25、Dense 或 RRF 排名。

Dense 从 Chroma 读取这篇论文的已存向量后精确打分。相比全库近似搜索，它让论文内候选范围与排序更容易核对，但不代表已经解决大规模跨论文检索。网页与 CLI 使用同一注册适配层，避免演示和实验走两套排序代码。

代码：[indexing.py](../../scholarlens/indexing.py)、[embedding.py](../../scholarlens/embedding.py)、[retrieval.py](../../scholarlens/retrieval.py)。

## 从候选到模型上下文

上下文使用真实 Qwen tokenizer 计数，最多放入 5 个完整 chunk、4,500 context tokens。块的原始位置保留到生成阶段，引用只能指向实际送入模型的内容。

检索 Top-10 用于 MRR@10；生成只读取 Top-5。排第 6 的正确证据可能计入排名指标，却没有进入模型上下文。这也是为什么检索指标与生成质量必须分开检查。

模型通过本地 Ollama 调用。输出被分为正常回答、证据不足、引用不合法及调用错误；实际 prompt、响应和引用位置随逐题审计记录保存。

代码：[context.py](../../scholarlens/context.py)、[qa.py](../../scholarlens/qa.py)、[generation.py](../../scholarlens/generation.py)。

## 实验如何比较

Dev 检索共 200 题，Test 检索共 300 题；生成子集分别为 50 题和 100 题。Dev 比较 `1600/200`、`2400/200` 切分与三路检索，选择 `2400/200 + Dense` 后固定正式 Test 条件。

| 指标 | 含义 |
| --- | --- |
| EvidenceRecall@5 | Top-5 完整覆盖的 gold 段落比例；一题取最佳替代参考组，再对可回答题平均 |
| AllEvidence@5 | 至少完整覆盖一组参考证据的题目比例 |
| MRR@10 | 前十个候选中首次完整覆盖任一 gold 段落的倒数排名 |
| Answer / Evidence F1 | 官方 QASPER scorer 的词面答案与引用段落评分适配 |
| 引用可追溯 | 解析后的引用能否定位到实际上下文；不等于陈述获证据支持 |

失败预测保留在总体分母中。无答案题不进入检索 Recall/MRR；无答案正确拒答与可回答题错误拒答分别统计。

正式 Test 中 Dense 的 EvidenceRecall@5 为 0.6290、MRR@10 为 0.4965。生成 Answer F1 为 0.3347，存在错误拒答和截断。完整条件、分母与局限见[正式报告](../../reports/test.md)，不从单例或少数成功回答推断总体质量。

## 一个有用的失败定位顺序

1. 原文是否包含问题需要的证据？
2. gold 是否进入检索候选，排名多少？
3. 证据是否实际进入 context，还是被 Top-k 或预算排除？
4. 模型是否正确使用证据，引用能否回查？

[三个真实案例](../../reports/t9-failures.md)分别对应检索未召回、第六名证据被 Top-5 排除，以及已有完整证据却仍拒答。它们给出下一版实验方向，但不用于回改本版 Test 结果。

## 复核入口

```sh
.venv/bin/python -m pytest -q tests_scholarlens
.venv/bin/python scripts/t8_verify.py
```

第二条命令需要本机保存的正式逐题产物，离线复算而不调用模型。公开仓库保留配置、汇总报告及验证代码；模型、全文、索引和完整运行产物不随 Git 分发。

上游组件、数据和辅助开发的说明见[来源清单](../../UPSTREAM.md)。
