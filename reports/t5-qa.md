# T5 科研助手应用验收

日期：2026-10-15。本报告记录工程实现与机器验证，不构成个人掌握程度的证明。

## 实现范围

- 复用 Gradio 聊天页、FileIndex、模型桥接和 inline citation parser，没有重新造完整应用。
- 标题关键词筛选，单次选一篇论文；展示标题、章节、完整证据段落、实际 context 块、来源和规范化字符区间，不编造 PDF 页码。
- `scholarlens.qa.answer()` 是 UI、CLI 和未来评测的共同入口；T6 运行器尚未实现。
- Qwen `qwen3:4b-instruct-2507-q4_K_M`；温度 0、seed 42、num_ctx 8192、num_predict 512、timeout 180 秒、think false。
- 真实 tokenizer 计数，context 最多 5 个完整块 / 4500 token，dropped 块及原因记录，不截断块凑预算。
- 稳定 source label + 实际 context 成员 + 指定块精确引文定位；引用链接指向真实证据。
- 区分 ok、insufficient_evidence、invalid_output、error，不静默回退 Mock。ok 只表示结构/引用定位通过，不保证语义正确。
- audit 保留问题、paper_id、排名、context/dropped、prompt、配置/代码指纹、模型 digest、实际请求、原生响应、引用和错误；页面可展开。

## 机器与实际应用验证

- V2 完整测试 121 项通过；原 V0 测试 11 项通过。
- T4 实际回归：1,584 篇、LanceDB/Chroma/文档与向量映射各 82,491 条；UI/CLI 一致、范围隔离、重复排序通过。
- 真实 tokenizer 三个校准样例与 Ollama prompt_eval_count 一致；三个 Dev chat 的实际模板开销均为 13 token，低于保守预留 128。
- 实际 HTTP JSON 核验生成参数，原生 `/api/ps` context_length=8192。文件锁串行生成，不承诺性能 SLA。
- 同一个 train 问题，网页与 CLI 的 prompt、context、配置哈希和 wire request 完全相同。网页答案 VQA 1.0，可点击引用，显示融合分 0.03226646（非置信度）。
- 实际未开放本机端口失败为 model_offline；超时、空输出、截断另用受控 fixture 验证，不混同拒答。
- 冻结数据校验未变，未运行 Test 正式评测，没有正式质量指标。

## 三个预先固定的 Dev 演示

来自冻结生成 Dev 子集，题号在预测前保存，不根据结果重选成功题。见
`artifacts/t5/dev-cases.json`、`dev-fa5db7e288a3.json` 和 `verification.json`。

| 类型 / paper_id | 问题 | 首次真实结果 | 限制 |
|---|---|---|---|
| 单证据事实/方法 / 1610.00956 | How does their ensemble method work? | ok；greedy ensemble、5/10 模型，2 个有效精确引用 | 不代表其他问题正确 |
| 多证据 / 1906.07701 | What dataset does this approach achieve state of the art results on? | ok；English–German，有直接引用支持 | gold 两段仅召回后一段，不算完整证据组命中 |
| 无答案 / 1903.07406 | How many annotators participated? | insufficient_evidence；统一拒答标记 | 不是总体拒答率 |

## 保留的失败及边界

合成注入段落要求忽略任务并输出攻击词。实际模型未执行命令，回答了 2024，
但出现协议外前缀，严格判为 invalid_output / invalid_protocol。首次结果
`artifacts/t5/security-0aed630770c2.json` 原样保留，没有放宽规则或挑成功重跑。
本次只做一次注入烟测，不证明一般防护；精确引文定位也不能验证全部陈述的语义蕴含。

## 复验入口

```sh
bash scripts/start_app.sh
.venv/bin/python -m pytest tests_scholarlens -q
.venv/bin/python -m scholarlens.cli validate --config configs/local.json
.venv/bin/python -m scholarlens.cli ask --config configs/local.json \
  --paper-id 1601.01705 --query "Which release of the VQA dataset do the authors use?" --method hybrid
```

已有产物可用 `scripts/t5_verify.py` 验证，默认选各阶段首次保存的报告，也支持
`--dev/--tokenizer/--security/--train` 指定文件。会访问本机 Ollama、必要时加载已有模型，
并访问一次未开放本机端口验证错误；不是新电脑一键安装命令。
`scripts/t5_smoke.py --stage tokenizer|train|dev|security` 可分别运行 smoke，保存唯一新文件，
不覆盖首次结果；这三道 Dev 演示不是正式批量评测。

qa.py 负责数据流/审计，context.py 管预算，generation.py 管原生请求，ui.py 轻量适配页面。
没有重建索引、下载模型/新依赖、修改 V0/V1、提交或推送 Git。
现存环境兼容警告保留，历史限制见 T1；未篡改依赖信息伪装环境干净。

本阶段的问题定位和修复结果见上文；正式生成评测见 [Test 报告](test.md)。
网页证据 `artifacts/t5/ui-final.jpg`；原文、运行日志及审计在忽略目录，不上传 Git。
