# T6：可信指标与共享评测运行器

日期：2026-10-15。工程实现与机器验收完成；用户手算理解独立保留待核对。
范围仅是指标正确性与固定 5 题 train smoke，不是 T7 Dev 对照或 T8 正式 Test 成绩。

## 实现与输入输出

- `scholarlens/metrics.py`：输入一题完整有效参考组及实际排名/context/预测，输出逐题指标及分子分母；`aggregate` 按预定全部问题汇总，失败不删除。
- `scholarlens/evaluate.py`：校验冻结数据与官方 evaluator，按选定 paper_id 调用已注册检索 pipeline，生成阶段调用与网页相同的 `qa.answer()`，保存 manifest、逐题原始结果、summary.json、summary.md。
- `scholarlens/cli.py evaluate`：显式选择 split/stage/method，train 固定 3 道可回答和 2 道无答案，预测前按 seed=42 问题哈希选定。Dev 接口已提供，本轮没有运行；Test 入口在 T8 最终配置授权前锁定。
- `scripts/t6_verify.py`：不调用模型，重新从保存的预测/gold 计算指标，核对真实 span 切片、实际请求、官方整批 F1 和手算样例。

官方评分器直接保留未改源码，未安装其训练环境，Apache 许可证与来源在 vendor/。
固定 [e996b6c7 提交](https://github.com/allenai/qasper-led-baseline/blob/e996b6c7b1b5f95d9308a74e3586416c6e780df1/scripts/evaluator.py)，
本地文件 SHA-256 为 `781aba7cd8e524bef4f0a1b4bf3504e5b02cb1d8d5bf32a8f0a89dfa83e86bfe`，
Git blob 与官方 API 一致，均为 `daa0e48d32c55e6cd23d21e0d6254a35bc359ae4`。

## 指标规则

按 paper_id/paragraph_id 绑定实际规范化字符区间，合并并集，只有完整覆盖某 gold 段落才算命中。
块重叠不重复计分；重复 ID/完全相同 span 被视为数据错误，不压缩排名来抬高 MRR。

- EvidenceRecall@1/3/5：组内完整覆盖段落数 / 该组总段落数；一题取最佳替代组，再对可回答题宏平均。
- AllEvidence@5：是否至少完整覆盖一个参考组；不能把不同组各一半混成完整组。
- MRR@10：首次完整覆盖任一 gold 段落的倒数名次，不意味着整组证据已齐。
- Context EvidenceRecall / AllEvidence：只对真正送进模型的 context_chunks 计算，不使用 dropped 块或扩展段落。
- Answer F1：官方词面评分；从 raw_output 先清 thinking，再取最终正文、删引用编号，规范拒答映射为 Unanswerable。不是语义正确率。
- 官方 Evidence F1：实际最终答案使用的有效引用映射成原始完整段落，再由官方 scorer 评分。这是段落匹配适配，不声称模型真的读到整段；实际读取量以上述 Context 覆盖为准。
- 无答案题不进入检索 Recall/MRR。正确拒答、错误实质回答/协议异常、系统错误互斥覆盖无答案子集；可回答题另报错误拒答。
- 引用格式合规率、引用可追溯率分开；无引用分母为 0 显示 null/N/A，不记 100%。不自动认证人工证据支持率。
- 模型异常、超时、空最终输出、截断或缺预测的官方 Answer/Evidence F1 以 0 分保留；特别防止失败无答案预测因空 evidence 获得满分。已经观察到的检索/context 仍按实际块评分，不被后续生成失败抹成零。

### 手算对照（机器已验证，用户理解尚待核对）

唯一参考组为 A、B，排名为完整 A、无关 X、完整 B：

| 项目 | 值 | 原因 |
|---|---:|---|
| EvidenceRecall@1 | 0.5 | 只覆盖 A |
| EvidenceRecall@3 / @5 | 1 | A、B 都覆盖 |
| AllEvidence@5 | 1 | 完整组出现 |
| MRR@10 | 1 | 第 1 名已完整覆盖任一证据段 |

A 如果由 [0,6)、[4,10) 两块组成，Top-1 不算覆盖 A，Top-2 并集才覆盖；如果中间留一字符缺口，仍不算命中。

## 共享链路与可复算产物

为计算 MRR@10，共同 registered retriever 一次取 Top-10；生成只回放同一排名的 Top-5，
继续由原 `answer()` 执行 4500 token 预算、真实 Qwen 调用及引用/audit。没有另做评测专用排序或喂 gold。
原 QA audit 保留 Top-5 输入，评测独立字段 metric_retrieval_results 保存 Top-10，明确区分。

每个实验保存语料/题集/冻结哈希、索引指纹、完整配置、官方 scorer 提交/哈希、代码指纹、
Python/系统/关键依赖与实际 Ollama runtime；逐题保存 gold、原始预测/审计路径、计时、错误和评分用原始段落。
运行器只初始化注册索引与必要 selector，不为批处理渲染整个 Help 页面。

文件先序列化、同目录临时写入/fsync、再不覆盖原子发布；文件锁保证同一实验单写者。
resume 比较数据、配置、代码和环境，只补没有结果的题，连错误答案也不自动重试挑好结果。
JSON 汇总与 Markdown 可独立恢复。recompute 从预测重新评分，不信任缓存 metrics；缺失题补为 error，分母不缩小。

## 验证入口

```sh
.venv/bin/python -m pytest tests_scholarlens/test_metrics.py tests_scholarlens/test_evaluate.py -q
.venv/bin/python -m scholarlens.cli evaluate --config configs/local.json \
  --split train --stage retrieval --method hybrid
.venv/bin/python -m scholarlens.cli evaluate --config configs/local.json \
  --split train --stage generation --method hybrid
.venv/bin/python scripts/t6_verify.py
```

不提供直接运行 Test 的捷径；T8 需要另行预注册最终配置与正式批次。
重跑 smoke 会产生新实验，不能拿不同版本或最好一次替代首次结果。

## 验收与真实小样例

最终批次目录为 `artifacts/evaluation/t6-train-{retrieval,generation}-v2-final/`；
此前 `first`、`verified`、`accepted`、旧 `final` 名称的批次均属于实现过程留档，不代表最终有效成绩，
尤其 accepted 批次曾因 selector 初始化遗漏全部报错。版本说明见 `artifacts/t6/initial-smoke-status.json`。
质量数字只解释为五题 smoke；不能写成正式 Dev/Test 成绩、平均性能或服务 SLA。

机器验证和实际五题结果在 `artifacts/t6/verification-v2.json`、`tests.xml`。

- 最终完整 V2 测试 **150 passed**（T6 新增 29 项），原 V0 **11 passed**；独立代码审查无未解决的重要发现。
- 冻结题集结构校验通过，SHA-256 仍为 `5c94800e12c0b5b0b37afd17e93e0b23ea9593bbd12c35e6499e2b2878ea0d44`。
- 独立检索与生成批次的上游检索指标一致：三道可回答题 EvidenceRecall@1/3/5、AllEvidence@5 均为 0；MRR@10 为 0.0555556，即仅一题第 6 名完整覆盖任一 gold 段，宏平均为 `(1/6)/3`。
- 实际 context 的完整段落覆盖为 0。不能由此断言所有相关文本都没有出现，严格指标要求的是整个 gold 段落完整覆盖。
- 生成结果：两道可回答题拒答、一道 output_truncated；两道无答案规范拒答。官方 Answer/Evidence F1 均为 0.4，全来自两道无答案题的得分，**不是可回答题质量良好**。
- 系统错误 1/5；无答案正确拒答 2/2；可回答错误拒答 2/3；没有成功的非拒答输出或有效引用，因此引用合规/可追溯率均为 N/A。
- 保存的每题都能重算；官方 evaluator 对同五题整批评分与宏平均一致；检索 span 原文切片、实际请求参数、4500 token 预算均通过检查。
- 实际同契约 resume 通过，没有重跑已保存答案；接口与受控反例验证在配置/代码/运行环境变化时拒绝续写。

这些数量仅用于确认指标和错误分支工作，三道可回答/两道无答案不具备总体代表性。
没有改变问题、上下文预算、模型、输出上限来改善 smoke 表现；后续质量对照仍是 T7。

## 问题复盘与边界

实际复现了 thinking 文本误计分、半截 JSON 持久化、运行时变更续跑、额外空行、
Help 页联网副作用以及 selector 生命周期遗漏；完整处理过程见 [T6 面试复盘](t6-interview-log.md)。
输出上限 512 导致的真实截断按 error 保留，没有为提高 smoke 成绩加大预算或挑题。
本次不修改原有冻结 v1，不重建索引、不下载模型/依赖、不改 V0/V1、不提交或推送 Git。
