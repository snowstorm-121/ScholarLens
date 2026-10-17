# T2：QASPER 论文与证据位置转换验收

日期：2026-10-15。范围仅为数据准备，不包含索引、题集抽样冻结、模型调用或 Test 成绩。

## 输入与来源

QASPER v0.3 的两个官方发布包，由[官方加载脚本](https://huggingface.co/datasets/allenai/qasper/blob/main/qasper.py)
列出的地址获取。没有执行数据集加载脚本或包内 evaluator，也没有安装新依赖。
数据署名 Dasigi et al. (2021) / Allen Institute for AI；标注许可证 CC BY 4.0，保留原论文权利。

| 发布包 | SHA-256 | 本次获取方式 |
|---|---|---|
| train/dev | `a28fdf966db827bcee3d873107d6b6669864fb7ca8fbf73a192f5e39191bdb5a` | 复用 T1 官方下载缓存 |
| test/evaluator | `72a52a41193e2838b8074f80ac074b94f956b84886c36a61c58a7df4171bdd72` | 新下载约 3.7 MiB |

校验值是对官方地址下载文件的本地固定值，并非发布方签名或独立公布的校验值。
缓存内容变更会报错，不会自动接受新哈希。manifest 记录 URL、字节数、版本、哈希、取得/固定时间及来源说明。
不向文件系统任意解压：验证所有包内路径/类型/重名，仅在内存读取指定 JSON，拒绝越界路径和链接。

## 实际规模

| split | 可用论文 | 章节 | 段落（含摘要） | 题目（尚未筛选抽样） | 参考标注 | 定位校验有效标注 |
|---|---:|---:|---:|---:|---:|---:|
| train | 887 | 12,450 | 47,769 | 2,590 | 2,672 | 2,184 |
| dev | 281 | 3,796 | 13,547 | 1,005 | 1,764 | 1,446 |
| test | 416 | 5,663 | 20,233 | 1,451 | 3,554 | 2,972 |
| 合计 | 1,584 | 21,909 | 81,549 | 5,046 | 7,990 | 6,602 |

原始 1,585 篇/5,049 题中，train 的 `1801.07804` 正文为空（full_text=[]），对应 3 道题被一并隔离。
先实际复现停止，再实现明确隔离：底层单篇转换仍报 MissingBodyError，批处理只针对该已知缺陷
写入 `rejected_papers.jsonl` 和报告；未知解析错误、重复 ID、包路径/哈希问题仍直接终止。
未补造正文、未把摘要当作完整论文、未把未通过的参考组当有效组。

先用按 paper_id 排序的前 100 篇 train 试转换：1,199 章节、5,830 段落、269 题、273 参考标注，
其中 220 个参考有效；无缺正文、重复 ID 或解析失败。随后才运行全量转换。

1,388 个参考标注未通过，按原因统计如下（同一参考可有多种原因，不能相加当独立标注数）：

- FLOAT SELECTED / 图表证据：930。
- 空证据组：210。
- 正文中找不到完整证据段落：236。
- 同一规范化文本出现多处、无法唯一定位：25。

保留完整原始 answer、annotation_id 和逐标注原因。不同标注员参考组独立保存；
同组内任何一段失败都会使整组无效，不能删掉困难证据后把残缺组当正确参考。
无答案参考可合法没有 evidence；跨标注冲突、问题去重及配额抽样是 T3，不在此宣称完成。

## 输出、定位与防泄漏

文件在 `data/qasper/v0.3/`，原包缓存仍在 `data/t1/`。两者均被 Git 忽略。

- `papers.jsonl`：显式白名单导出的论文标题、摘要、规范化全文、段落 ID、来源等，无 qas/answer 字段。
- `paragraphs.jsonl`：段落正文、原始文本、章节、paper_id、paragraph_id、字符 start/end、来源。
- `questions.raw.jsonl`：独立保存题目及参考标注、映射结果、有效性；**禁止作为建库输入**。
- `mapping_issues.jsonl` / `rejected_papers.jsonl`：诊断与排除信息，不参与索引。
- `corpus_manifest.json` / `conversion_report.json`：输入与输出哈希、实际计数及规则。

规范化版本 `nfc-whitespace-v1`：Unicode NFC，段内换行、连续空白折叠成单个空格，去掉首尾空白；
段落间保留两个换行，绝不跨段落合并。空段落省略，但不改变后续原始 section/paragraph 序号。

段落 ID：`paper_id:s{section_index}:p{paragraph_index}`；摘要为 `paper_id:abstract`。
start/end 是对应 paper.normalized_text 中的 Python Unicode 字符半开区间 `[start,end)`，不是字节或 token。
gold 只在整个规范化段落精确且唯一匹配时定位；每条已映射证据都验证
`normalized_text[start:end] == evidence_text`，并与对应 paragraph_id 的边界一致。
没有用模糊匹配、第一次命中或旧 chunk 编号兜底。

## 复现与验证

在 v2 目录中执行：

```sh
.venv/bin/python -m scholarlens.cli prepare --config configs/local.json
.venv/bin/python -m pytest tests_scholarlens/test_data.py -q
```

新测试 27 项通过，涵盖规范化、位置、多个互补证据、替代参考、重复文本歧义、缺正文隔离、
缺字段、归档越界/链接/重名、哈希变化、重复论文/问题/标注 ID、正文不含 QA、重复转换和输出防覆盖。
原 V0 的 11 个 unittest 通过。没有重新安装或下载模型。

全量 prepare 多次运行结果相同；输入/输出哈希、ID、计数不变，写入采用确定性顺序且不追加重复行。
已有产物与本次内容不同会报错，要求新版本/新输出目录，不静默覆盖；本次没有创建或冻结正式 Test 题集。

关键输出哈希：

| 文件 | SHA-256 |
|---|---|
| papers.jsonl | `63f349f4a5e892457a730db28d073d28d49b1d13e0f2691b1c87a92c1f308e6a` |
| paragraphs.jsonl | `6c58c642ddf9d82743302ea53eb2cfe1b5652856005fd45a656d4e0a438a8296` |
| questions.raw.jsonl | `3ba2689fe42a55efeb3c32a87fd16709a901e578eae2c5f995a5f83cc768afe3` |

全量与 100 篇预览转换文件实测约 179 MiB，原包及 T1 数据约 15 MiB。
正文与标注保留原始/规范化文本用于定位，因此转换体积大于压缩包；不是额外模型或新环境。

## 完成边界

这些论文已经转换成可用数据，**尚未进入网页的向量索引**。页面仍使用 T1 的两篇样例，
全量索引和页面接入分别是 T4/T5。T3 冻结题集、正式指标、跨论文推理均未完成。
本任务未修改上游 libs、V0/V1、总体求职计划，未进行 Git 提交或推送。
