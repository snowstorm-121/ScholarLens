# T3：评测集筛选与冻结

日期：2026-10-15。机器部分完成。后续同日用户委托助手替代本轮逐题核对，已完成 30 题/50 参考组的辅助语义审查；
不是人类独立核验，发现的疑点与限制见 [辅助审查报告](t3-review.md)。以下“待用户核验”段落保留为初次交付时的历史记录。
本次没有模型调用、检索或答案评分，没有根据系统输出选择问题。

## 冻结规模

| 集合 | 总数 | 可回答 | 无答案 |
|---|---:|---:|---:|
| 检索 Dev | 200 | 160 | 40 |
| 检索 Test | 300 | 240 | 60 |
| 生成 Dev（Dev 子集） | 50 | 40 | 10 |
| 生成 Test（Test 子集） | 100 | 80 | 20 |

唯一问题共 500 道；150 道生成题包含在其中，不是额外新增。实际数量达到计划配额，未借用 train、跨 split 补题或合成填充。

## 筛选口径与完整证据组

1. 仅从 T2 的官方 dev/test 题集中筛选；train 不进入正式集合。
2. 任意原始标注对 unanswerable 存在分歧即整题排除，即使冲突一方因证据问题已无效，仍采取保守排除。
3. 保留 T2 通过位置和完整文本证据校验的参考组。某一参考含无法定位、歧义或 FLOAT SELECTED 的证据，则整组无效；不能删掉困难证据后保留残缺组。
4. 有有效参考、同时有无效参考的题，保留完整有效参考；不同标注员参考组仍是替代关系，同一组内多个证据共同需要。
5. 无答案题要求原始标注在回答性上全部一致，且至少有一个有效的无答案参考，证据为空。
6. 问题先做 NFC/空白规范化与 casefold，按 paper_id + question 去重；同论文同题保留合格候选中哈希最低者，不合并不同 question_id 的参考。
7. 每类以 `SHA256("42|" + question_id)` 升序抽样，同哈希按 question_id 排序。生成子集用相同规则在各自检索集合中选取。

按内容结构规则筛选，不根据难度、召回结果或生成表现挑题。图表信息若无法由完整文本证据支撑则不保留该参考，未通过模糊匹配修正任何 gold。

| split | 原始题目 | 回答性冲突 | 无完整有效参考 | 规范化重复题 | 合格候选 |
|---|---:|---:|---:|---:|---:|
| dev | 1,005 | 75 | 125 | 0 | 805（745 可回答 / 60 无答案） |
| test | 1,451 | 164 | 114 | 1 | 1,172（1,093 可回答 / 79 无答案） |

合格但未入选：1,477 题。两个 split 中无效参考标注合计 900 个，属于“标注”计数，不能与排除题目数混加。
逐题/逐参考排除原因、合格未入选 ID 都独立保存。

## 产物与保护

本地冻结目录：`data/qasper/v0.3/evaluation/v1/`（Git 忽略）。

- `questions.dev.jsonl` / `questions.test.jsonl`：入选问题、回答性、完整有效参考及 paragraph/span。
- `generation.dev.ids.json` / `generation.test.ids.json`：对应生成子集 ID。
- `gold.retrieval.{dev,test}.json` / `gold.generation.{dev,test}.json`：官方 evaluator 兼容的 paper → qas → answers 结构；只含对应题目和保留的 annotation，证据用原始段落文本。
- `review.dev.ids.json`：固定的 30 道 Dev 人工核验 ID。
- `excluded.questions.jsonl` / `excluded.annotations.jsonl` / `eligible.not_sampled.jsonl`：排除及未入选记录。
- `selection_report.json` / `freeze.json`：配额、实际计数、规则、输入/代码哈希、问题及 annotation ID、文件哈希。

可公开的 `configs/evaluation-v1.freeze.json` 与本地 freeze.json 完全一致，包含 ID/规则/哈希，不含问题正文、答案或证据。
原文/gold 未进入检索 Document 或 prompt 示例；没有加载或运行任何 RAG 模型。

冻结 SHA-256：`5c94800e12c0b5b0b37afd17e93e0b23ea9593bbd12c35e6499e2b2878ea0d44`。

重复执行 freeze 不改时间戳、ID、内容或哈希。任一输入/规则/代码、输出文件或公开快照变化会被检测；
冻结后不能覆盖，需将 evaluation.version 改为新版本并保留旧目录。普通 validate 只校验，不生成新题集，不调用评分器。
仅冻结与数据抽样相关的配置，不把后续模型/检索调优配置错误锁死在此阶段。

## 验证结果

```sh
.venv/bin/python -m scholarlens.cli freeze --config configs/local.json
.venv/bin/python -m scholarlens.cli validate --config configs/local.json
.venv/bin/python -m pytest tests_scholarlens -q
```

- T2/T3 共 48 项测试通过，其中 T3 新增 21 项；原 V0 的 11 个 unittest 通过。
- 验证了冲突、完整/替代参考、无答案、规范化去重、配额不足、确定性哈希顺序、span、生成子集、输出防覆盖、新版本保留旧文件、冻结文件与输入变动检测。
- 检查全量合格候选及入选问题的 paper_id、split、annotation 唯一性和证据位置；Dev/Test 论文不交叉。
- 从官方发布包中仅取出 `get_answers_and_evidence` 函数进行格式兼容检查，四份 gold 分别解析到 200/300/50/100 题；未调用 evaluate/F1 评分函数。
- 重复冻结与结构校验通过，哈希一致。正式 Test 题目只做了标注和结构处理，没有查看系统输出或用成绩调题。
- 本次新增冻结产物约 5.6 MiB，人工核验材料约 124 KiB；没有下载新数据、模型或依赖。

为避免把 T2 单文件继续堆大，T3 题集逻辑独立放入 `scholarlens/dataset.py`，复用 data.py 的规范化、位置和哈希工具；CLI 增加 freeze/validate。

## 必须由用户完成的 30 题核验

清单：`artifacts/t3/v1/dev-review.md`，固定 ID 位于冻结目录的 review.dev.ids.json。
已列出题目、论文、有效答案、每个独立参考组及其证据位置，保留 30 个未勾选项；没有伪造“用户已检查”。

本轮按冻结规则取 Dev 哈希前 30 题，实际均为可回答题，其中 19 题有多个有效参考组。
因此这 30 题人工核验**不覆盖无答案标注质量**；学习时可另查看 Dev 无答案样例，但不能将其冒充原定 30 题或据此修改冻结 Test。

请逐题判断：题意与答案是否对应；每个参考组的证据是否完整支持该答案；位置是否正确；有多个参考组时是否误当作必须全部命中。
“无答案”表示所选论文未提供答案，并非现实世界没有答案。结构正确不等于内容已经人工认可。

清单备注不属于冻结文件，可由用户填写；不会自动更改题集，也不自动认证人工核验完成。
发现标注缺陷需记录、决定是否形成新版本，不能静默修补 v1。T3 的人工核验项仍未勾选。

未进行 Git 提交或推送；未实施 T4 的索引与检索改造，网页仍为 T1 两篇样例。
