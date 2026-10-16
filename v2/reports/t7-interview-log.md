# T7 Dev 对照：实施与面试复盘

日期：2026-10-15 开始，2026-10-16 完成工程跑批、机器核验和受用户委托的 U3。最终 Test 冻结仍待完成，不冒称全部 T7 完成。

范围：1600/200 三路检索、一次 2400/200 Hybrid 切分对照、胜出切分三路比较、
固定 50 题生成 Dev 的 Dense 基线/所选方案。复用 T6 的同一 pipeline 和指标，保留全部首次结果。
不运行 Test，不增加模型、reranker 或新搜索参数，不提交/推送 Git。

## 执行分工与学习边界

代码和跑批由助手完成。最初计划将 U3 留给用户；用户后来明确委托助手完成两个真实案例判断和一条审计回归测试。
因此 U3 记为“助手按用户委托完成”，不记作用户独立分析或亲手改码。selected_config 仍是候选，
ready_for_test=false；其中 pending_user_U3 是生成候选时的历史状态，须在单独最终冻结时刷新，不能称为已冻结 T8 方案。

## 问题一：写 --config 不等于注册工厂真的切换了索引

- 依据：T4/T6 工厂刻意拒绝与唯一活动配置不一致的参数；flowsettings 与索引/QA 默认入口此前直接读取 configs/local.json。
- 风险：绕过检查会让评测使用另一套参数；直接在运行中覆盖 local.json 又可能让现有网页配置和工厂混用。
- 处理：新增进程级 SCHOLAR_CONFIG，导入前显式指定独立配置快照，注册、index_context 和 QA 使用同一路径。每个对照使用独立新进程与 collection；默认网页仍保持 local.json。
- 验证：无环境变量保持原样、替代配置注册与 QA 默认一致、显式配置冲突拒绝、导入后改环境变量拒绝，四项子进程测试通过；受影响回归 66 项通过。
- 边界：固定的是进程活动路径，不是在运行中修改配置文件的许可证；实验快照运行期间不编辑，代码/配置变动必须新实验。
- 面试要点：配置文件、已注册组件和实际请求必须一致；不能为了实验方便删掉 fail-closed 检查。

## 预先约定而非事后挑结果

选择顺序：EvidenceRecall@5 → AllEvidence@5 → MRR@10；切分全部并列保留 1600，方法全部并列 Dense > BM25 > Hybrid。
比较器检查题集、语料、冻结文件、模型/生成参数、代码和运行环境；只允许指定切分大小与 collection 名变化。
生成基线和所选方法共用同一胜出 chunk 集，所选就是 Dense 时只跑一次，不制造重复“对照”。
失败预测保留分母和系统错误，不从结果中删除难题；原始 JSON、日志均在 artifacts/evaluation 与 artifacts/t7。

## 问题二：能选出赢家，不代表必做对照跑齐了

- 审查发现：若 2400 胜出，初版只要求 1600 Hybrid 和 2400 三路，漏跑 1600 Dense/BM25 也能输出 selected_config。
- 复现：构造该四路结果，预期拒绝却没有报错；反例测试修复前失败。
- 处理：最终 selected_snapshot 另行要求 1600 三路基线齐全，仍保留只用两路 Hybrid 判断切分的中间步骤。
- 验证：选择规则测试 12 项通过，全部并列、分级优先、配置变化和重复挑重跑等边界均覆盖。
- 面试要点：选择函数要验证实验矩阵完整性，不只是实现 max 分数。

## 问题三：活动文件选了 Dense，UI 默认却仍是 Hybrid

- 审查定位：ScholarRetrieverPipeline.get_user_settings 将默认值写死 Hybrid；get_pipeline 优先采用界面设置，UI 又显式把该 method 传入 QA。
- 风险：CLI 按选定方案跑，网页默认却走另一方法；只检查 JSON 不会发现。
- 处理：默认方式由活动配置读取，用户显式下拉选择仍允许覆盖；用新进程验证非 Hybrid 配置下真实设置与 pipeline 一致。
- 验证：以针对性回归及完整回归结果为准，不将字段存在当作已经生效。
- 面试要点：默认设置是数据流的一环，不能只对齐模型名和索引路径。

## 执行清单

- [x] T6 基线 150 项通过，确认磁盘空间。
- [x] 独立配置快照与进程活动配置接入。
- [x] 确定性选择规则及反例测试。
- [x] 独立代码审查通过（v2 开跑前）。
- [x] 三路基线、唯一切分对照及胜出配置补齐。
- [x] 五十题生成 Dev 运行与复算。
- [x] 至少十个真实失败/边界案例分析（生成十例、另有检索四例；助手辅助审查，非人类独立认证）。
- [x] 报告与候选配置完成；计划同步见唯一执行文档。
- [x] U3：助手按用户委托分析两个真实案例并补充一条错误记录 context 审计回归；用户未亲自完成，不表述为用户独立判断。
- [ ] 最终 Test 配置冻结与授权；Test 仍未运行。

## 问题四：HNSW 查询不是“枚举该论文所有向量”

- 现象：1600 Dense/Hybrid 在同一道 Dev（3e432d71…，paper1705.01214）报 `Cannot return the results in a contigious 2D array. Probably ef or M is too small`。失败已留在原始分母，未删除。
- 诊断：Source.note、文档关系、原生按 paper_id/file_id 过滤的 ID/向量数均为 290；同一查询可复现错误，不是简单的缺向量。
- 源码依据：原适配层即使 top_k=全部论文 chunk，底层仍执行 filtered HNSW knn_query，不保证枚举所有节点。默认 search_ef=10 是观察值，不能断言只因该参数太小。
- 处理：在所选论文范围用原生 Chroma.get 的 AND 元数据预过滤读取已存向量，再精确计算 squared L2；保持 exp(-distance) 返回契约、既有余弦转换与稳定 ID 排序，不重新归一化。它是明确唯一的 Dense 路径，不是碰到错误才换算法的隐藏 fallback。
- 不采用：盲目调大 ef/M 会改变搜索配置，且仍不保证全量枚举；没有根据 Dev 分数搜新超参数。
- 版本：三路 v1 全部保留并标记 invalidated_implementation_defect；在相同问题/参数下用新代码重跑整组三路为 v2，不能混用新旧 Dense 或只挑一次成功重试。
- 边界：Chroma 仍承担向量存储和存储侧过滤；论文范围内的打分为精确计算，不再宣传这里使用全库 ANN。float32 累加末位可与旧 HNSW 不同，不承诺分数逐位等同。
- 证据：artifacts/t7/chroma-reproduction.log、invalidated-v1.json；对应反例和完整回归验收后才进入最终选择。

## 问题五：目录写 Dense，不代表实际跑的是 Dense

- 审查发现：离线生成报告按目录名称命名基线，若该目录实际 manifest.method 为 Hybrid，初版可能仍标为 Dense。
- 复现：放入错误 method 的受控 manifest，原脚本进入计分而非拒绝；测试修复前失败。
- 处理：读取 manifest 后先核对 method 与该组预注册名称一致，再接受其结果；比较其他条件仍全部相同。
- 验证：错名批次反例测试通过。
- 面试要点：实验名称是标签，实际执行参数才是证据。

## 问题六：长任务跨时段恢复，服务状态不能沿用旧结论

- 中断：额度审核服务不可用导致原定本机验证未执行；没有通过其他渠道绕过审批，也未将未运行命令当成功。
- 恢复：重新检查文件和测试，完整 179 项通过；实机查询却出现 Ollama ConnectionError，确认当前服务离线。
- 处理：启动原有官方桌面应用，核对运行时和已安装模型 digest，再继续原失败问题的验证；不重装或重下模型。
- 边界：诊断过程的连接失败不冒充一轮 Dev 评测，也不覆盖 v1 失效实验；恢复后的有效批次仍使用新的 v2 版本。
- 面试要点：代码状态、实验状态和服务状态需要分别恢复；不能拿昨日的“运行中”当作今日可用证据。

## 问题七：验收脚本也可能给出虚假的“已核验”

- 审查发现：初版离线核验对早期失败无条件读取 context 字段，会崩溃；只检查 metric_retrieval_results，没有核对实际 context 与 prompt。
- 复现：早期 ConnectionError 记录触发 KeyError；篡改 context 文本后原检查未拒绝，两项反例均先失败。
- 处理：失败记录仅校验已产生的字段，完整成功记录仍强制要求完整审计；同时核对检索和实际 context 的论文/字符区间/原文，并重建证据 JSON 与实际 prompt 比对。
- 验证：五项针对性测试通过，包含失败保留、context 篡改、prompt 篡改、成功样例和显式 missing_prediction；另用五道真实 train 记录检查兼容性。缺失记录的 None 预测也先复现 AttributeError 再修复，成功记录缺预测仍拒绝。
- 边界：修改的是 scripts/t7_verify.py 和测试，不改变已冻结的 scholarlens 评分/检索/生成源码，正在运行的 v2 实验代码哈希保持不变。
- 面试要点：验收工具本身也需反例；“检索文本正确”不能替代“发给模型的证据正确”。

## 实验解读提醒：切分上限不是固定块长度

当前在各段落内部调用 splitter，不跨段拼接；2400/200 不会把每个短段落补成 2400 字符。
离线遍历完整正文预先确认 1600/200 为 82,491 块，2400/200 为 81,670 块，后者只少 821 块。
这是当前设计的结果，不是只建了 Dev 小索引。建库仍需分别验证 1,584 篇和原生存储计数。
因此解释切分实验时要结合段落长度、完整 gold span 与排名，不能宣称“块越大就一定召回越好”。

## 已完成的检索选择（Dev，不是 Test）

六组均为 200 题，Recall/MRR 分母均为 160 道可回答题，系统错误均为 0。
Hybrid 在 1600/200 的 EvidenceRecall@5 为 0.587133，在 2400/200 为 0.600526，按预注册顺序选择后者。
在同一 2400 chunk 集上，BM25/Dense/Hybrid 分别为 0.468919 / 0.649321 / 0.600526，因此选 Dense。
所选 AllEvidence@5=0.6（96/160），MRR@10=0.472617；相比 1600 Dense，Recall@5 只增加 0.625 个百分点，不夸大为显著提升。
原始决策记录为 artifacts/t7/retrieval-decision.json；50 题生成沿用 2400 Dense 的同一配置，不制造第二次 Dense“对照”。

面试表达：Hybrid 是待验证方案，不是预设赢家。已观察到个别问题融合降名次，也有融合挽回 Dense 漏检的案例；
不足以断言全部整体差异都由 BM25 噪声造成，或说 Hybrid 对其他语料无效。

## 问题八：检索完整仍可能输出截断、混淆方法归属

- 实例：Dev `d9884734…` 询问 RQE 使用的方法，实际检索/上下文 gold 覆盖均为 1；context 为 1295 tokens，未丢弃块。
- 原始请求固定 num_predict=512，响应 eval_count=512、done_reason=length；这是输出预算触顶，不是 8192 输入窗口溢出。
- 处理：按预定策略保留为 output_truncated 错误，官方 F1=0；上游覆盖仍为 1。原文已有 FINAL ANSWER，不能说模型完全没回答，也不因为末尾看似成句就挑选放行。
- 语义检查：虽然开头的 Logistic Regression/neural networks 与参考一致，后文混入 Related Work 其他系统的结构，单一引用不支持全部展开，不能将完整 gold 入 context 当作答案正确。
- 当前边界：不在看到 Dev 输出后擅改 512 上限、prompt 或挑重试。更短引用表达/输出预算对照属于后续新授权实验，不是本次已验证改进。

## 问题九：修好引用格式不等于修好回答对象

- 实例：Dev `efe9bad5…` 问压缩比较基线，实际 context 的 Results 段落提到 PKD/NoKD，模型却回答作者自己的 dual training/shared projections。
- 引用故障：END_PHRASE 留空，被严格校验标记 missing_quote_phrases，解析引用有效数为 0；不以模糊匹配放宽通过。
- 指标边界：该题 gold span 覆盖为 0，但不等于 context 没有回答线索；citation_compliant=1 是解析格式口径，不等于引用有效，需一起看 traceability 和 invalid_output。
- 处理：保留独立的引用错误和语义对象混淆风险，作为助手辅助案例审查；仅补 END_PHRASE 仍不能让“自身方法”成为“比较基线”。
- 面试要点：检索、context、协议、精确引用和事实支持是不同层，不能用一个指标代替全部验收。

## 问题十：生成错误状态仍要核验已经产生的证据

- U3 案例 A（`d9884734…`）：gold 段落在 Dense rank 2，`EvidenceRecall@5=1`、`Context EvidenceRecall=1`；输出达到 `eval_count=512` 且 `done_reason=length`，被记录为生成截断。主要故障在生成阶段；原始答案虽然先答出 Logistic Regression 与 neural networks，又把 Related Work 的网络结构细节混入本文方法，不能因为 gold 覆盖完整就视作答案和引用都正确。
- U3 案例 B（`efe9bad5…`）：gold span 未进入 Top-5，然而实际 Results context 已提及 PKD 与 NoKD baselines；模型却回答本文的 dual training/shared projections。故障同时涉及 gold 检索缺口、比较对象混淆和空 `END_PHRASE` 导致的引用无效，不能简化成“上下文完全没有答案”或“只要补引用格式就行”。
- 回归：在 `tests_scholarlens/test_t7_verify.py` 增加 `test_error_output_cannot_bypass_actual_context_audit`。使用 `saved_example()`，先 deepcopy context chunks，再篡改其文本并将行状态设为 error；核验器仍必须按原文 span 拒绝。
- 为什么 deepcopy：夹具把同一个 chunk 对象放进 context 与检索结果；深拷贝确保只污染待核验 context，不连带篡改检索结果，从而测到目标约束。
- 验证：`.venv/bin/python -m pytest tests_scholarlens/test_t7_verify.py -q`，6 passed。只增强测试覆盖，不改评分/检索/生成核心代码，不重跑模型、不重算 Dev 指标。
- 面试要点：失败状态只说明流水线没有成功产出答案，不会抹掉失败前已生成的检索与 context 审计记录；错误记录仍需验证所有已存在字段。
- 发布复核：候选配置原先把七个实验目录写成这台机器的绝对路径；同步前改为项目相对的 `artifacts/evaluation/...` 路径，未更改检索/生成参数与实验记录。GitHub 不包含这些被忽略的运行产物，故克隆仓库后仍需先按数据准备流程建立本地 corpus/index 和评测 artifacts，才能执行完整离线验收。
- 发布前核验：用相对目录读取并复算七组既有结果均通过；随后完整 `scripts/t7_verify.py` 在 UI/CLI 检索探针调用本机 embedding 服务时失败，当前 Ollama 未连接。启动时 NLTK 还尝试联网补 `punkt_tab`，网络访问被环境拒绝。没有安装/下载或伪报整体验收通过；U3 定向测试和 V2 全量测试均已通过，最终候选冻结时仍需在 Ollama 可用环境重新完成整体验收。

## 最终机器验收与真实质量边界

- 六组检索逐题复算一致；候选 2400/200 Dense，索引指纹 `7cdc7972495576359456cbdb0c93afbdc7b04f5fbaed33dce7f44dfabe388c8e`。
- 生成 50 题整体 Answer F1=0.251667、Evidence F1=0.376667；40 道可回答题 Answer F1 均值仅 0.139584。
- 14 次 ok、7 次 invalid_output、20 次规范拒答、9 次 output_truncated。可回答题拒答 13/40；无答案题为正确拒答 7、回答 2、系统错误 1。
- 引用解析合规 19/21，可追溯 24/30；两者分母不同，均不是“50 题中答案正确的比例”。
- 生成子集 Context EvidenceRecall=0.729167，与该子集检索覆盖一致，未观察到预算裁剪损失；不能与 160 道可回答检索 Dev 的 0.649321 直接相减宣称生成提高了召回。
- scripts/t7_verify.py 实测通过：所有结果原文 span、实际 context/prompt/wire 请求、官方批量评分一致；两套全量索引的文档/向量/Chroma/Lance 数均匹配，原 T1 2 篇/28 块保留。候选 UI 默认与 CLI 的 train 检索一致，不渲染联网 Help 页面。
- 最终回归：V2 184 项通过（15.99 秒）、原 V0 11 项通过。未安装依赖、未下载新模型，Test 实验 manifest 数为 0，未提交/推送 Git。
- selected_config.json 是带来源契约的候选，SHA-256 为 `d55863d3d7253889337383b76eddc3c51027b57792a2c1c2aa04a2469babf6fc`，ready_for_test=false；其状态字段仍反映 U3 完成前的快照。U3 已由助手按用户委托完成，最终冻结仍待单独执行；Test 未运行。

可用于面试的短述：在固定公开论文语料和 Dev 上比较三路检索、两种切分，按事前规则选 Dense；不仅报告检索指标，还保留生成截断、错误拒答与无效引用，逐层复核证据链。当前完成的是可复核实验，不是生产级问答质量认证。
