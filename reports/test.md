# T8 一次正式 Test 结果

日期：2026-10-16。运行对象为 ScholarLens 的 QASPER v0.3 冻结 Test；不是线上业务验证。T7 仅用 Dev 选择了 2400/200 切分与 Dense；正式 Test 没有用于调参。配置原件 `configs/selected_config.json` SHA-256 为 `e20e8a29e2e22274f6bd04d955427fdb4f01588e67c02fa7f5343703cc15a6cd`，数据冻结文件 SHA-256 为 `5c94800e12c0b5b0b37afd17e93e0b23ea9593bbd12c35e6499e2b2878ea0d44`。Test 运行契约 `configs/t8-test-contract.json` SHA-256 为 `4b164f52164ec3546a4f1f1fe04eb93fbbe22de9721d520d75c43768a79568e5`。

T7 配置中的 `ready_for_test=false` 保留为历史冻结状态；本次授权以独立 T8 契约实现。为开放受控 Test 入口，只改 `scholarlens/cli.py` 和 `scholarlens/evaluate.py`，并在运行前将新版代码哈希写入 T8 契约。T7 内嵌的旧代码哈希因此不能冒充当前源码哈希；检索、指标、生成参数和 prompt 未改。缺少合法契约、唯一预注册 experiment ID，或指定 `--limit` 时 Test 仍拒绝执行。

## 运行与数据口径

- 检索 Test：300 题（240 可回答、60 无答案），固定论文范围、同一 2400/200 索引、Top-10 计分、Top-5 证据覆盖；分别运行 BM25、Dense、Hybrid 一次。
- 生成 Test：预先冻结的 100 题子集（80 可回答、20 无答案）；Dev 所选方法与 Dense 基线相同，只运行 Dense 一次。Top-5 最多 4500 context tokens。
- 生成：本地 Ollama 0.15.6，`qwen3:4b-instruct-2507-q4_K_M`，temperature=0、seed=42、num_ctx=8192、num_predict=512、think=false。向量模型 `nomic-embed-text`；两模型 digest 与配置一致。Prompt 版本 `scholar-qa-v1`，未看 Test 改动。
- 环境：MacBook M5/16GB，macOS 26.5.1 arm64，Python 3.10.22；关键包版本在各批次 manifest 中。延迟为本地逐题调用墙钟时间，不含准备索引；它不是并发服务吞吐或 SLA。

## 检索：相同 Test 条件下三路对照

下列召回/MRR 的分母为 240 道可回答题；无答案题不混入这些指标。EvidenceRecall 是所标完整 span 的覆盖比例，AllEvidence@5 是完整覆盖整组证据的题目比例，并非答案正确率。

| 方法 | EvidenceRecall@1 | @3 | @5 | AllEvidence@5 | MRR@10 | 系统错误 | 单题 P50 / P95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BM25 | 0.1984 | 0.3588 | 0.4654 | 0.4250 | 0.3649 | 0/300 | 0.341 / 0.376 s |
| Dense | 0.3014 | 0.4872 | 0.6290 | 0.5542 | 0.4965 | 0/300 | 0.394 / 0.457 s |
| Hybrid | 0.2819 | 0.4964 | 0.5901 | 0.5250 | 0.4878 | 0/300 | 0.393 / 0.428 s |

本样本中 Dense 的 @5 和 MRR 高于另外两路；Hybrid 的 @3 略高于 Dense，但 @5 较低。不能据此声称 Hybrid 普遍有效或 Dense 对所有论文都占优。正式目录分别为 `artifacts/evaluation/t8-v1-bm25-retrieval/`、`t8-v1-dense-retrieval/`、`t8-v1-hybrid-retrieval/`；每个目录含 manifest、逐题 JSON 和不可覆盖的 summary。

## 本地生成：100 题

| 指标 | 正式结果 |
|---|---:|
| Answer F1 / Evidence F1（官方 QASPER 评分适配） | 0.3347 / 0.3790 |
| 可回答题 Context EvidenceRecall / AllEvidence | 0.5967 / 0.5625 |
| 可回答题错误拒答 | 22/80（27.5%） |
| 无答案题正确拒答 / 错误回答 / 系统错误 | 17 / 3 / 0（20 题） |
| 引用格式合规 | 45/52（86.5%，仅有可计分答案的子集） |
| 引用可追溯 | 64/88（72.7%，以解析出的引用条目为分母） |
| 系统错误 | 9/100，均为 `output_truncated` |
| 输出状态 | 31 ok、21 invalid_output、39 insufficient_evidence、9 error |
| 单题 P50 / P95 | 11.944 / 48.294 s |

100 题的整体 Answer/Evidence F1 包含无答案题，不能解释成 80 道可回答题的答案质量；生成子集的召回分母也是 80，不能直接与上表 240 题检索结果作因果比较。P95 使用 nearest-rank 定义，均为本机串行运行的观察值。`invalid_output` 不等于全部算系统调用错误：其原始文本和引用错误仍保留，官方计分可给部分 Answer F1，但不把无效引用算作可追溯证据。9 次截断没有重试或调大预算。

无答案题的 3 次错误回答：`04914917…`（低资源语言）、`3e4e415e…`（测试语言）、`4830459e…`（说话人数量）。它们与 17 次规范拒答分别保留；不根据这些 Test 题改写 gold 或 prompt。

## 固定 20 题的助手逐条证据核查

样本为 100 题生成清单中可回答题按 `SHA256("42|question_id")` 排序的前 20 道，选择与模型输出无关。助手逐条查看 question、最终答案、引用 span/context 和系统状态；这不是独立人类复核，也不代表对全部 100 题做了语义认证。以下短 ID 唯一对应 `t8-v1-dense-generation/questions/<完整 question_id>.json`，完整 ID 及复核顺序见 `artifacts/t8/verification.json`。

| 序号 / 短 ID | 检查结论 |
|---|---|
| 1 `7380e62e` | LSTM 结构陈述有有效引用；核心陈述受支持。 |
| 2 `a28c73a6` | 检索/context 完整覆盖 gold，但生成达到输出上限；无可交付答案。 |
| 3 `d3cfbe49` | fasttext、ELMo 及维度的关键陈述均可由两条有效引文支持。 |
| 4 `0c4e419f` | 规范拒答；Top-5 未覆盖 gold。 |
| 5 `16cc37e4` | 用户划分和 200k/10k 数字有实际引用支持，但该引用不覆盖标注 gold；不能以引用有效替代 gold 命中。 |
| 6 `f2bcfdbe` | 规范拒答；Top-5 未覆盖 gold。 |
| 7 `baec9975` | 规范拒答；Top-5 未覆盖 gold。 |
| 8 `2c60628d` | pseudo language model 的两项核心陈述有有效引文；末尾额外 Note 未单独加引用，属表达边界。 |
| 9 `0fee37eb` | 输出含 4 个引用但均未从原文精确定位；不能视作有证据答案。 |
| 10 `a7e1b13c` | 规范拒答；Top-5 未覆盖 gold。 |
| 11 `6d55e377` | 只 1/3 条引文可追溯，答案整体协议无效；不能用部分有效引用背书整个结论。 |
| 12 `5b2839be` | precision/recall/F1 及 macro F1 用途有有效引文；4/4 引用可追溯。 |
| 13 `e3c44964` | 0/2 引文可追溯；阈值说法不纳入可信答案。 |
| 14 `acac0606` | 规范拒答；Top-5 未覆盖 gold。 |
| 15 `43729be0` | 六种语言列表与有效引文一致。 |
| 16 `f15bc409` | 32,227 对数据及标注内容与有效引文一致。 |
| 17 `a064337b` | 0/1 引文可追溯；答案过泛且协议无效。 |
| 18 `b78bb6fe` | 规范拒答；Top-5 仅覆盖 40% gold，不是完整证据。 |
| 19 `0bde3ecf` | Top-5 已完整覆盖 gold，但仍拒答；属生成/证据使用失败，不能归咎检索。 |
| 20 `610fc593` | Top-5 已完整覆盖 gold，但仍拒答；同样是生成阶段失败。 |

这 20 题中，7 条回答的核心陈述有可追溯引文（第 8 条仍有多余未引述 Note），8 条拒答，4 条协议/引用无效，1 条截断。核查只说明此固定样本的证据关系，不等于总体正确率。

## 可复核性和边界

`scripts/t8_verify.py` 不调用检索或模型，只重算四批原始逐题记录、核对配置/代码/Test 哈希、原文 span、实际 context/prompt/wire 参数、官方整批 Answer/Evidence F1，以及 20 题固定样本。结果为 `artifacts/t8/verification.json`；四个 manifest 的 SHA-256 分别为 `ff4c0d54…`、`8b09ed19…`、`b3c0d11e…`、`82b3dd75…`，完整值在该验收文件中。评测前后配置、契约和数据哈希一致。V2 回归 186 项、V0 unittest 11 项通过。

本项目完成的是可复核的本地研究论文问答实验；QASPER 小样本、论文范围检索、单机 4B 模型、无独立人类 gold 审查的限制必须随简历数字一起说明。尤其不能把引用格式合规率等同于答案事实正确率，也不能把当前延迟宣传为生产 SLA。
