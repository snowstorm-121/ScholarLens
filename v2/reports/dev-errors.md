# T7 Dev 失败与边界分析

检索与生成批次已完成；以下为真实检索案例，生成十例详见下方链接。不把检索结果冒称生成结论。
审查由助手辅助完成，不是独立人类正确性认证；没有根据这些案例改变已预注册的参数或 prompt。

## 已核对的 1600/200 三路检索案例

原始记录路径模式：`artifacts/evaluation/t7-1600-{bm25,dense,hybrid}-v2/questions/<ID>.json`。
下面的 Recall 都是完整 gold 段落覆盖，不等同于答案可回答性。

### R1：相关内容排在直接证据前（检索排序）

- ID：`15e481e668114e4afe0c78eefb716ffe1646b494`；paper `1908.09246`。
- 问题：What alternative to Gibbs sampling is used?
- 证据：gold `s3:p2 [7824,8921)` 说明 AEM 的 generator network。BM25 排 1、Hybrid 排 2，Dense Top-10 未命中。
- 观察：三路 Recall@5 为 `1 / 0 / 1`；Dense 首位讨论 Gibbs sampling 的训练耗时，而不是所问替代方法。
- 判断：具体的 Dense 排序失败；也说明 Hybrid 能改善个别题，但不能据此宣布总体胜出。
- 后续候选：先比较真实排名和关键词，不把“应该加 reranker”当作已验证结论。

### R2：融合损失与多参考组口径（检索、指标边界）

- ID：`435570723b37ee1f5898c1a34ef86a0b2e8701bb`；paper `1801.10293`。
- 问题：Which translation systems do they compare against?
- 证据：一组 gold 要求 `s14:p2+p3`，另一组只要求 `s14:p2`。Dense 的两段排名为 2/6，Hybrid 为 6/5。
- 观察：三路 Recall@5 为 `0 / 1 / 0.5`。
- 判断：Dense 满分因为满足较短参考组，并非覆盖所有标注；Hybrid 将 p2 降出 Top-5，是可见的融合代价。
- 后续候选：报告参考组含义并检查逐题排名；不能用一个满分掩盖遗漏的系统。

### R3：Top-5 结构性覆盖上限（切分/检索预算）

- ID：`9193006f359c53eb937deff1248ee3317978e576`；paper `1908.06267`。
- 问题：Which datasets are used?
- 证据：两个参考组均需 11 个段落，含总述与十个数据集介绍；当前 chunk 不跨段。
- 观察：三路 Recall@5 均为 `2/11`。Dense 在首位命中总述，因此 MRR@10=1，但完整覆盖仍不足。
- 判断：即使理想排序，五个不跨段的块也无法覆盖十一段；实际排序又只覆盖两段。两类原因必须分开。
- 后续候选：更大证据预算或分步检索只能列入后续实验，当前有界对照不临时扩参。

### R4：非 gold 段落也能提供答案（参考标注风险）

- ID：`a2015f02dfb376bf9b218d1c897018f4e70424d7`；paper `2004.01862`。
- 问题：How large is the collection of COVID-19 literature?
- 证据：非 gold 的 `s1:p0 [4266,4968)` 明确给出超过 45,000 篇文章、超过 33,000 篇全文；Dense 排 1、Hybrid 排 5。
- 观察：三路 Recall@5 为 `0 / 0.5 / 0`。gold 包含另一段重复数字及一段描述临床发现的文字。
- 判断：低 gold Recall 不足以断言实际 context 没有答案；这是标注覆盖和指标的边界，不自动等于模型答对。
- 后续候选：保留原冻结集与疑点记录；不在看到分数后改 gold 美化成绩。

## 生成案例

固定 50 题 Dev 首次生成全部保留，详细逐题证据与分类见 [十例生成失败与边界分析](dev-generation-cases.md)。
另有两例按用户委托由助手完成判断，见 [U3 材料](t7-u3.md)；不记作用户独立分析，也不是独立人类认证。
