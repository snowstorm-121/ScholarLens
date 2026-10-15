# T4：带定位索引与三路检索

执行日期：2026-10-15。用户委托助手完成 T4、U1、U2；不将这两项记为用户亲自编码。

## 验收状态

T4、U1、U2 已完成。实际 1,584 篇论文、82,491 个 chunk；失败项 0。
文档关系、向量关系、LanceDB 行数及 Chroma 向量数均为 82,491。
原 T1 索引仍为 2 篇、28 个 chunk，没有覆盖。
这一步不计算 Dev/Test 检索或生成指标，不声称 Hybrid 优于其他方法。

## 本机验收记录

| 验收项 | 实际结果 |
|---|---|
| 首次全量运行 | 1,989.54 秒，包含复用先前 2 篇 pilot 的 183 个 chunk |
| 全量重复运行 | 188.94 秒，仍为 1,584 / 82,491，无新增编码日志 |
| 索引 ID / 指纹 | 2 / `cbc3d4536f45e7aba6f42f1874ed1e0276edd52b017b7de2715dbb500720e380` |
| 存储向量抽查 | 16×768、float32，L2 norm 0.99999994–1.00000012 |
| 真实 query 编码 | 1×768、float32、query 角色 |
| U1 | 两篇 train 论文、三种检索均无越界；真实临时 Chroma 异论文相同向量测试通过 |
| U2 | RRF 手算、去重、同分排序均通过 |
| 共享链路 | 注册 UI factory 与实际 CLI Top-5 chunk IDs 一致，重复查询一致 |
| 网页烟测 | 新 collection 选择 1601.01705，真实 Qwen 回答 VQA 1.0 release，并展示对应引用原文 |
| V2 回归 | 84 passed，含本轮新增 36 项 |
| 历史 V0 | 原有 11 项 unittest 通过，未改动 V0/V1 |
| 题集冻结 | 结构校验通过，哈希仍为 `5c94800e12c0b5b0b37afd17e93e0b23ea9593bbd12c35e6499e2b2878ea0d44` |

已执行独立只读代码审查；发现的两个重要边界已复现修复，复审无新增可操作问题。
完整本机证据：`artifacts/t4/first-build.json`、`repeat-index.log`、`verification.json`、
`cli-retrieval.log`、`tests.xml` 和 `ui-smoke.jpg`。网页在 `127.0.0.1:7860` 启动。

存储实测（含原 T1 数据，四舍五入）：向量库约 1.3 GiB、原文库约 201 MiB、
原始导入文件副本约 152 MiB、body-only 导入文件约 152 MiB、指纹/映射约 6 MiB。
没有下载新模型或新环境，仅新增 rank-bm25 包和真实索引。

网页旧展示格式将 RRF 小数四舍五入显示为 `0.0`，示例真实 Top-1 融合分约 0.03226646；
旧 `Relevance score: 0.0` 不是启用了 LLM 打分，更不能当作置信度。
精确分数保存在统一检索结果中，显示与来源标签优化留待 T5。
当前网页仍保留上游标题及交互布局；本轮不冒充已完成 T5 改造。

## 实现边界与数据流

```text
T2 正文与段落导出（不读取题目或 gold）
  → 每篇 body-only .qasper.json
  → 段落内 1600/200 字符切分，保留全局 [start, end)
  → FileIndex Source/Index 身份表 + LanceDB 原文/metadata
  → search_document: + Nomic 全维向量 → Chroma

选择单篇论文 + query
  → BM25：只用该论文 chunks 计算 TF/DF/平均长度
  → Dense：search_query: 编码，Chroma 按 paper_id AND file_id 预过滤
  → Hybrid：两路各 Top-20，RRF 常数 60，同分按 chunk_id
  → 统一 chunk_id / score / rank / text / metadata / method
```

切分复用 `langchain-text-splitters==0.2.4` 的 RecursiveCharacterTextSplitter，
长度单位为 Python Unicode 字符，不是 token。只在每个段落内部切分，关闭上游二次切分。
`start/end` 是规范化全文位置；同时保存 paragraph 的边界，不依赖旧 chunk 编号。
1600/200 是本轮固定基线，没有用 Test 选择参数，也未启用备选 2400。

增加独立 `ScholarLens QASPER 1600-200` collection；T1 两篇 HTML 演示索引保留。
CLI、UI 和后续评测通过同一注册的 FileIndex 工厂及 ScholarRetrieverPipeline 获取结果，
没有另建评测专用检索库。前端标题筛选、生成拒答、正式引用审计属于 T5 及后续任务。

## 向量与分数

模型为本机已有的 `nomic-embed-text`，固定 digest：
`8688dbc0926c1dfdc1b8b7489034e1fedb06f6ac66472dd2d7f0ed6d7d23ba29`。
正文/问题前缀分别为 `search_document: ` / `search_query: `，只添加一次。
使用原生 Ollama embed API，`truncate=False`，模型失败明确报错。
输出完整 768 维，转换 float32、检查有限非零后 L2 归一化。
未下载新模型；沿用 Ollama 桌面服务。

锁定的 Chroma adapter 使用默认 squared L2 并返回 `exp(-distance)`。
对单位向量，Dense 显示分数转换为 `1 + log(adapter_score) / 2`，即余弦相似度。
BM25 与 Dense 原始分数不可直接相加，Hybrid 只使用名次。
为稳定处理 Top-k 边界同分，Dense 请求所选论文的全部 chunk，而不是全库召回后过滤。
这是单论文范围内检索，不宣称实现了跨论文联合问答或优化过的全库 ANN 性能。

BM25 使用 `rank-bm25==0.2.2` 的 BM25Okapi，k1=1.5、b=0.75，
英文小写正则 token；保留词内连字符、下划线与英文撇号。没有额外词干化或停用词库。
没有 reranker、MMR、查询扩展、LLM 相关性打分。BM25 对空命中仍可能返回零分并列结果，
检索非空并不等于证据充分；拒答策略不在本任务中冒充已实现。

## U1：过滤必须在召回前生效

实现：BM25 首先加载选定论文的 chunk 后再建立统计；Dense 向 Chroma 传入
`paper_id` 和 `file_id` 的 AND metadata filter。
源码检查发现上游 Chroma adapter 忽略 `node_ids` 参数，因此不能仅传节点列表就声称已隔离。

自动测试覆盖两篇共享关键词的论文，以及真实临时 Chroma 中相同向量的异论文 chunk。
异论文候选必须无法进入结果，不允许全库 Top-k 后才过滤，也不允许通过丢弃越界结果掩盖后端问题。
真实语料验收使用 train 论文 1601.00901 和 1601.01705，共同查询 `model`，不使用 Dev/Test 输出调参。

## U2：RRF 手算与确定性排序

两路排名：BM25=`[a, b, c]`，Dense=`[b, a]`，名次从 1 开始。

| chunk | BM25 贡献 | Dense 贡献 | 总分 |
|---|---:|---:|---:|
| a | 1/61 | 1/62 | 0.03252247488101534 |
| b | 1/62 | 1/61 | 0.03252247488101534 |
| c | 1/63 | 0 | 0.015873015873015872 |

a/b 同分，按 chunk_id 升序得到 `[a, b, c]`。跨路同一 chunk 合并累加，
单路出现重复 chunk 则报错；结果保留 branch_ranks 便于解释。

## 一致性、续跑与实际问题修复

chunk_id 由规范化版本、段落 ID、span、切分参数与文本确定。
索引指纹包含语料 manifest 哈希、规范化、切分器版本/参数、模型 digest、前缀、向量规格及 BM25 版本。
另保存 paper_id → file_id → chunk_ids；语料或模型变化不能隐式覆盖现有索引。

重复建库通过已有 DS/VS ID 集合只补缺失项，修复 vector 已提交而关系表未提交的中断点。
嵌入完成后才将论文 Source 标记为 complete；未完成论文不可检索。
测试覆盖模型失败后续跑、向量提交后关系提交前失败及重复运行。

复现并修复一个实际边界问题：同名文件内容变化后，原实现直到关系集校验才报错，
此时已写入新 chunks。现复用 Source.path 中的原始文件 SHA-256，在写入前比对并拒绝变更；
测试确认拒绝后存储数量不变。未修改或清理任何真实语料文件。

独立代码审查另发现两条边界并用回归测试复现、修复：

- Source 身份首次提交后、初始化 metadata 前中断：核对原文件哈希且两类关系均为空，
  才恢复初始化；不能因空 note 把正确文件永久卡住，也不能接管有冲突关系的记录。
- CLI 传入另一个配置，但注册工厂仍读默认配置：现于构造 App 前显式拒绝与当前 UI
  注册配置不一致的索引/检索参数，防止悄悄使用默认 k1 等参数。
  当前只支持一份活动 UI 配置；后续切分实验需明确切换活动配置和独立 collection，
  不能通过一个不生效的 `--config` 冒充实验。

## 复现命令与产物

在 v2 目录、Ollama 桌面服务可用的前提下：

```sh
.venv/bin/python -m scholarlens.cli index --config configs/local.json
.venv/bin/python scripts/t4_verify.py
.venv/bin/python -m scholarlens.cli retrieve --config configs/local.json \
  --paper-id 1601.01705 --query "Which release of the VQA dataset do the authors use?" --method hybrid --k 5
.venv/bin/python -m pytest tests_scholarlens -q
.venv/bin/python -m scholarlens.cli validate --config configs/local.json
```

本机索引描述及 paper/file/chunk 映射位于 `data/indexes/<fingerprint>/`，
真实后端验收位于 `artifacts/t4/verification.json`，建库日志位于 `artifacts/t4/index.log`。
正文、数据库、索引和本机日志不提交 Git；脚本、配置、测试和本报告可提交。

唯一新增依赖为 rank-bm25 0.2.2。uv 更新了 lock 文件格式和 wheel 元数据，
已比较全部包名/版本集合，未升级其他已有包。
