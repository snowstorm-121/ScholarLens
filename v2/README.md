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

在 Apple M5 / 16GB 环境验证了两篇论文的本地问答：

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

上述 1,584 篇论文已全量建立索引，共 82,491 个 chunk；网页新增独立的
`ScholarLens QASPER 1600-200` collection，原两篇演示论文索引保留。
问题数量不是已评测题数。已冻结检索 Dev/Test 的 200/300 题，以及其中的生成子集 50/100 题；
30 道 Dev 已按用户委托完成助手辅助语义审查，非人类独立审核，标注疑点仍保留；
三路检索对照与生成指标尚未运行。见 [T3 报告](reports/t3-dataset.md) 和 [辅助审查记录](reports/t3-review.md)。

### 带定位的三路检索

索引层提供段落内 `1600/200` 字符切分，保存论文、段落与全文字符区间；
复用 LanceDB 保存原文/metadata，Chroma 保存完整 768 维归一化 Nomic 向量。
正文和问题分别使用 `search_document:` / `search_query:` 前缀。

提供 BM25、Dense 和 RRF Hybrid 三种检索方式。BM25 统计和 Dense metadata 过滤均限定在用户选定论文内；
Hybrid 融合两路各 Top-20 的排名，不直接相加不同量纲的分数，同分按稳定 chunk_id 排序。
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

当前 84 项测试通过，覆盖数据/题集校验、精确 span、向量角色、三路排名、真实临时存储过滤及中断恢复。
重复转换不会追加重复记录；已有输出变化时明确报错，不静默覆盖。
全量存储计数、真实向量和 UI/CLI 验收见 [T4 报告](reports/t4-indexing.md)；
训练问题的网页问答烟测不等于正式评测成绩。网页旧分数格式会把小数显示为 `0.0`，待 T5 改造。

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
