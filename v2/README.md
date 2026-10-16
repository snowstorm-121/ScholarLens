# 研知 ScholarLens

面向 AI 科研论文的本地证据问答助手。

阅读论文时，仅有一段模型总结通常不够：还需要知道结论来自哪篇论文、哪段原文，以及模型是否真正获得了回答所需的证据。
ScholarLens 围绕“选论文、问问题、查依据”的流程，构建本地问答与可复核的数据准备链路。

## 使用场景

- 查找论文采用的数据集、方法和实验设置，减少反复翻阅全文。
- 从答案回到实际引用的原文，核对模型的表述。
- 将正文和标注答案分开管理，为后续检索、问答评测提供可追溯依据。

当前版本是个人研究与工程原型，不是生产服务；不承诺自动综述、可靠跨论文推理或 PDF 图表理解。

## 已实现能力

### 本地问答闭环

在 Apple M5 / 16GB 环境接入全量论文索引，并完成真实网页/CLI 问答烟测：

```text
选择论文与输入问题
        ↓
问题向量编码 → 论文范围内的 Top-5 检索
        ↓
原文证据与问题组成 Prompt
        ↓
本地 Qwen 生成 → 引用解析与原文展示
```

当前生成模型为 `qwen3:4b-instruct-2507-q4_K_M`，向量模型为 `nomic-embed-text`，通过 Ollama 本机接口调用。
模型断连时会报错，不静默回退到模拟生成器。已有失败案例和依赖警告见 [T1 报告](reports/t1-feasibility.md)。

### 可复现语料与证据位置

从 QASPER v0.3 转换得到：

| 项目 | 实际数量 |
|---|---:|
| 可用论文 | 1,584 |
| 章节 | 21,909 |
| 段落（含摘要） | 81,549 |
| 待筛选问题 | 5,046 |

正文使用稳定 `paper_id / paragraph_id`，保留规范化字符半开区间 `[start, end)`。
证据只有在精确且唯一匹配时才完成定位；无法映射、重复文本歧义和图表依赖分别记录原因。
缺正文的 1 篇论文及对应 3 道题明确隔离，不补造内容。

上述 1,584 篇论文已全量建立独立的 `1600/200`（82,491 块）与 `2400/200`（81,670 块）索引；
原两篇演示论文索引保留。默认启动仍使用 `configs/local.json`，不会静默覆盖为 Dev 候选配置。
问题数量不是已评测题数。已冻结检索 Dev/Test 的 200/300 题，以及其中的生成子集 50/100 题；
30 道 Dev 已按用户委托完成助手辅助语义审查，非人类独立审核，标注疑点仍保留；
T7 已完成六组 Dev 检索对照及 50 题生成验证；U3 已按用户委托由助手完成，最终配置冻结仍待处理，Test 未运行。
见 [T3 报告](reports/t3-dataset.md)、[辅助审查记录](reports/t3-review.md) 和下方 Dev 结果。

### 带定位的三路检索

索引层提供段落内 `1600/200` 字符切分，保存论文、段落与全文字符区间；
复用 LanceDB 保存原文/metadata，Chroma 保存完整 768 维归一化 Nomic 向量。
正文和问题分别使用 `search_document:` / `search_query:` 前缀。

提供 BM25、Dense 和 RRF Hybrid 三种检索方式。BM25 统计和 Dense metadata 过滤均限定在用户选定论文内；
Hybrid 融合两路各 Top-20 的排名，不直接相加不同量纲的分数，同分按稳定 chunk_id 排序。
T7 修复了将 HNSW 查询误作全量枚举的问题：Dense 先从 Chroma 按论文/文件元数据读取已存向量，
再在该论文范围内精确打分；这里不是全库 ANN 搜索，也不在失败时偷偷切换算法。
UI 与 CLI 复用同一注册适配层，不启用额外重排、MMR、查询改写或 LLM 相关性评分。
这仍是单论文问答，不将全量知识库等同于跨论文推理。

## 运行与验证

完整环境说明见 [本地运行指南](README.scholar.md)。已配置的本机可打开 Ollama 桌面应用，再运行：

```sh
bash scripts/start_app.sh
```

浏览器访问 `http://127.0.0.1:7860/`。这不是新电脑上的一键安装命令：首次使用须按运行指南准备独立 Python 环境、依赖和模型。

数据准备与测试：

```sh
.venv/bin/python -m scholarlens.cli prepare --config configs/local.json
.venv/bin/python -m pytest tests_scholarlens/test_data.py -q
```

当前 184 项测试通过，覆盖数据/题集校验、span、检索与恢复、预算、引用、错误审计，以及指标和运行器。
重复转换不会追加重复记录；已有输出变化时明确报错，不静默覆盖。
全量存储计数、真实向量和 UI/CLI 验收见 [T4 报告](reports/t4-indexing.md)；
训练问题的网页问答烟测不等于正式评测成绩。

### 可核对的论文证据与生成审计

标题关键词筛选后单选论文，网页和 CLI 复用同一个 `answer()`。
本地 Qwen tokenizer 将 context 限制在最多 5 个完整块、4500 token，记录被丢弃的块。
引用必须属于实际 context，并在指定块中精确定位；页面展示标题、章节、段落、字符区间及来源。
模型离线、超时、空输出、截断不会冒充正确拒答；输出协议错误单独标记，不静默切换模拟生成。
实际模型请求参数、原始响应及完整 audit 可复核。

已运行三个固定 Dev 演示，保留多证据未完整召回、注入样例输出格式失败，未开展正式 Test 评测。
引用可定位不保证陈述语义正确，单次烟测也不证明注入防护。见 [T5 验收](reports/t5-qa.md)
和 [排障及面试复盘](reports/t5-interview-log.md)。

早期模型接入、数据质量、评测冻结、论文隔离及建库续跑的问题与处理，见
[T1–T4 面试复盘](reports/t1-t4-interview-log.md)。其中区分实际故障、审查后复现和未解决限制。

### 可复算的评测运行器

复用固定提交的 QASPER 官方 evaluator 计算 Answer/Evidence F1；另实现段落完整 span 覆盖的
EvidenceRecall@1/3/5、AllEvidence@5、MRR@10，以及实际 context 覆盖、引用/拒答/系统错误统计。
UI 与批量调用同一检索与生成适配层，完整保存实验配置、版本和逐题首次结果，支持同契约续跑。

T6 阶段只完成固定五道 train 的功能验收，不是正式质量成绩：存在检索不足、可回答题拒答和输出截断；
T7 已完成有界 Dev 对照，尚未运行 T8 Test。无引用时可追溯率为 N/A，不伪报满分。
见 [T6 验收与口径](reports/t6-evaluation.md) 和 [T6 面试排障](reports/t6-interview-log.md)。
T7 的配置对齐、HNSW 枚举错误和整批失效重跑依据见 [T7 面试排障](reports/t7-interview-log.md)。

### Dev 实测与当前限制

在冻结的 200 道 Dev 中，以 160 道可回答题计算完整 gold 段落覆盖指标。
按预注册规则先选切分、再在同一 chunk 集选择方法，候选为 **2400/200 + Dense**：
EvidenceRecall@5=64.93%，AllEvidence@5=60%，MRR@10=0.4726；六组检索均无系统错误。
Hybrid 在两种切分下都未优于对应 Dense，不将这次结果推广到所有语料。
完整对照见 [Dev 检索报告](reports/dev-retrieval.md)。

固定生成子集 50 题已包含在上述 Dev 中，不是新增 50 道独立问题；所选方法就是 Dense，仅跑一组。
整体 Answer F1=0.2517、Evidence F1=0.3767；有 9/50 次输出截断、13/40 次可回答题拒答。
无答案题为 7/10 正确拒答、2/10 回答、1/10 系统错误；解析出的引用仅 24/30 可追溯。
可回答题 Answer F1 均值为 0.1396，不能用无答案题得分掩盖其效果。
引用存在或可定位不等于事实被支持，当前结果不构成质量达标声明。
见 [生成报告](reports/dev-generation.md)、[错误分析](reports/dev-errors.md) 与 [U3 任务](reports/t7-u3.md)。

候选保存在 `configs/selected_config.json`，标记 `ready_for_test=false`；其状态字段保留了 U3 完成前的候选快照，最终冻结时需刷新。Test 尚未运行。
若要用候选配置查看应用，请在未占用端口的情况下启动一个新进程：

```sh
SCHOLAR_CONFIG="$PWD/configs/selected_config.json" bash scripts/start_app.sh
```

它不会修改 `local.json`；未指定环境变量时仍沿用历史 1600/Hybrid 默认配置。

```sh
.venv/bin/python -m scholarlens.cli evaluate --config configs/local.json \
  --split train --stage retrieval --method hybrid
```

```sh
.venv/bin/python -m scholarlens.cli ask --config configs/local.json \
  --paper-id 1601.01705 --query "Which release of the VQA dataset do the authors use?" --method hybrid
```

## 代码导航

| 路径 | 作用 |
|---|---|
| `scholarlens/data.py` | 发布包校验、正文/标注分离、规范化与证据位置映射 |
| `scholarlens/cli.py` | 数据准备命令入口 |
| `scholarlens/dataset.py` | 题集筛选、确定性抽样、gold 导出及冻结校验 |
| `scholarlens/indexing.py` | 正文 reader、段落内切分、稳定 chunk ID 和索引指纹 |
| `scholarlens/embedding.py` | Nomic 文档/查询角色、模型 digest、维度与归一化校验 |
| `scholarlens/framework.py` | 复用 FileIndex 身份表、LanceDB/Chroma 的 UI/CLI 共同适配层 |
| `scholarlens/retrieval.py` | 论文范围内 BM25 / Dense / RRF 排名 |
| `scholarlens/build_index.py` | 分批建库、断点续跑及映射记录 |
| `scholarlens/qa.py` | 共同问答入口、引用检查、拒答/错误及审计 |
| `scholarlens/context.py` | 实际 Qwen tokenizer、完整块 token 预算 |
| `scholarlens/generation.py` | 本地真实请求、参数捕获与串行生成 |
| `scholarlens/ui.py` | 标题筛选与原文证据页面适配 |
| `scholarlens/metrics.py` | 完整段落覆盖与官方评分器适配、聚合分母 |
| `scholarlens/evaluate.py` | 共同 pipeline 运行器、不可覆盖记录及复算 |
| `configs/local.json` | 固定来源、校验值及转换配置 |
| `t1_components.py` | 本地检索默认配置与引用问答适配 |
| `t1_ollama.py` | 本地模型参数调用适配 |
| `tests_scholarlens/` | 个人数据适配层测试 |
| `reports/` | 验收结果、失败案例与边界 |
| `libs/` | 保留的第三方框架组件 |

原始语料、全文导出、模型、虚拟环境、数据库和运行日志不上传 Git。
Test 标注仅用于结构和位置校验，未写入知识库或作为 Prompt 示例。

## 数据与开源说明

数据来自 [QASPER](https://huggingface.co/datasets/allenai/qasper)，标注按 CC BY 4.0 使用，保留论文原有权利。
数据处理结果与规则见 [T2 报告](reports/t2-data.md)。

应用复用开源文档问答组件；保留 [许可证](LICENSE.txt)、源码版权声明和 [来源与改动记录](UPSTREAM.md)。
本项目关注科研场景适配、证据定位及后续评测工程，不将第三方框架代码表述为个人从零实现。
