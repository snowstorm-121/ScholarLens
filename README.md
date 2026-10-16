# ScholarLens · 研知

面向 AI 论文阅读的**本地证据问答助手**。选择一篇论文，询问方法、数据集或实验设置；答案附带原文引用，可回到具体段落核对。项目重点不只是生成一段回答，还包括检查“证据是否被检索到、是否进入模型上下文、引用能否定位、失败发生在哪一层”。

这是在 Apple Silicon Mac 上验证的个人研究原型，**不是**跨论文自动综述或生产服务。

## 能做什么

- 按标题筛选并选择一篇论文，在该论文范围内使用 BM25、Dense 或 RRF Hybrid 检索。
- 用本地 Ollama + Qwen3 4B 回答问题；证据不足时按统一协议拒答，模型调用失败不会伪装成成功。
- 在网页中查看引用对应的论文、章节、段落、字符区间和实际送入模型的原文；审计记录保留检索结果、context、prompt、回答及引用检查。
- 用冻结的 Dev/Test 题集复核检索与生成结果，而非只展示几道成功样例。

```text
QASPER 论文正文 ──规范化/保留段落位置──> chunk + metadata ──> BM25 / Nomic 向量
                                                              ↓
选定论文 + 问题 ──> Top-k 检索 ──> Top-5 context ──> 本地 Qwen ──> 答案/拒答 + 引用审计
```

知识库包含 **1,584 篇**可用 QASPER 论文。正文与原数据集的问题、答案和证据标注分开导出；标注不进入检索索引。两个实验索引分别采用 `1600/200` 和 `2400/200` 字符切分，后者为 Dev 选出的配置。检索限定在用户选定的论文内，**不支持全库跨论文推理**。

## 可复核的结果

Dev 用于选配置：检索 200 题、生成子集 50 题。冻结 Test 用于一次正式评测：检索 300 题（其中 240 题可回答）、生成子集 100 题（其中 80 题可回答）。全部方法在同一 `2400/200` 索引上比较；EvidenceRecall@5 要求 Top-5 文本完整覆盖标注的原文证据 span，并非答案正确率。

| Test 检索方法 | EvidenceRecall@5 | MRR@10 |
|---|---:|---:|
| BM25 | 0.4654 | 0.3649 |
| Dense | **0.6290** | **0.4965** |
| RRF Hybrid | 0.5901 | 0.4878 |

所选 Dense + 本地 `qwen3:4b-instruct-2507-q4_K_M` 在 100 题生成 Test 上，Answer F1 为 **0.3347**、Evidence F1 为 **0.3790**；仍有 **9/100** 次输出截断、**22/80** 次可回答题错误拒答，无答案题为 **17/20** 次正确拒答。不能把引用可定位当成答案一定正确，也不能从这组结果推断 Hybrid 普遍有效。

完整分母、环境、冻结哈希、逐题记录位置和限制见 [正式 Test 报告](v2/reports/test.md)；[Dev 六组切分/方法对照](v2/reports/dev-retrieval.md)和[三类实际失败](v2/reports/t9-failures.md)保留了选择依据与反例。30 道 Dev 题经过助手辅助语义检查，**不是独立人类 gold 审查**。

## 在已准备好的本机启动

需要 Python 3.10 环境、已校验的 QASPER 数据及两个本地 Ollama 模型；首次在新机器部署请先看 [环境、数据与复现说明](v2/README.scholar.md)，下面的命令不承诺一键完成下载或建库。

1. 打开 Ollama 桌面应用。
2. 在 `v2/` 目录启动已选定配置：

```sh
SCHOLAR_CONFIG="$PWD/configs/selected_config.json" bash scripts/start_app.sh
```

3. 打开 `http://127.0.0.1:7860/`，在 **ScholarLens QASPER 2400-200** 集合里只选一篇论文。可搜索 `Learning to Compose Neural Networks for Question Answering · 1601.01705`，问 `Which release of the VQA dataset do the authors use?`，再点开引用查看原文中的 “We use the VQA 1.0 release”。这是演示题，**不是**正式成绩。

应用与命令行共用检索/问答适配层。数据准备、建库、评测命令和本机依赖注意事项见 [V2 技术说明](v2/README.md)；过程问题和处理见 [T9 面试复盘](v2/reports/t9-interview-log.md)。本机 V2 回归测试 **187 项**、旧 V0 测试 **11 项**通过，T8 四批结果通过离线复算。

## 来源、范围与许可证

数据来自 [QASPER 官方数据集](https://huggingface.co/datasets/allenai/qasper)；原始包地址和 SHA-256 在 [配置](v2/configs/selected_config.json) 中。全文、模型、数据库、索引和逐题运行产物不提交 Git；仓库保留代码、固定配置、来源、测试与汇总报告。论文原有权利保留，QASPER 标注遵循其数据卡许可。

应用复用 [Kotaemon](https://github.com/Cinnamon/kotaemon) 的 Gradio、存储和模型接入等组件；本项目的改造集中在论文数据/证据位置、论文范围内三路检索、问答引用审计和冻结评测。上游版本、许可证与具体改动见 [UPSTREAM.md](v2/UPSTREAM.md) 和 [LICENSE.txt](v2/LICENSE.txt)，不将框架原有代码表述为从零自研。

当前限制：仅单论文范围、英文 QASPER 小规模题集、本机 4B 模型、无独立人类逐题复核；延迟数字不代表生产服务 SLA。演示视频和项目本人独立口述尚未完成，不作为仓库已验证成果。
