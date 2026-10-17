# T7：10 条真实生成案例的助手语义复核

范围：完整覆盖 `artifacts/t7/error-review-cases.json` 中的 10 个不同问题。原始记录统一位于 `artifacts/evaluation/t7-2400-dense-generation-v2/questions/<question_id>.json`，以下逐条给出 ID、论文及段落，便于追溯。阅读对象包括问题、参考答案、实际上下文、原始输出及引用记录，不仅是自动分类标签。

本报告是助手的证据分析，不是用户人工验收或人工支持率认证。**U3 已按用户委托由助手完成，Test 未运行。**案例包按类别及 ID 选取，不用于估计各种失败的总体占比。R5/C 分别指完整 gold 段落覆盖的 EvidenceRecall@5 / Context EvidenceRecall；AF1/EF1 为官方答案/证据 F1，显示值四舍五入。

十条记录均为 5 个实际上下文块、`dropped=[]`，上下文为 789–1740 tokens，低于 4500 预算。因此本组没有观察到上下文打包丢弃；这不意味着五块上下文总能回答问题。以下“后续”均为未来独立实验或审查建议，**本轮未执行、未改提示词/参数/标注、未重算已报告指标**。

## 1. 集成方法：低词面分数，不等于事实失败

ID：`09c86ef78e567033b725fc56b85c5d2602c1a7c3`；论文 `1610.00956`。问题：How does their ensemble method work?

- 观察：R5/C=1/1，`ok`，AF1=0.0941、EF1=0.5，3 条有效引用。rank 1 的 `s13:p8` 明确写 predictions averaging；rank 3 的 `s13:p9` 写验证集贪心选择，rank 5 的 `s13:p10` 写 10 选 5。回答覆盖三者，所述步骤可在实际上下文找到支持。
- 主因/边界：主要是短参考答案与长回答的词面计分差异；参考只要求“平均各单模型预测”。次要是附加两个真实段落使证据集合大于标注集合，降低 EF1。不能把自动 `answer_or_reference_review` 当作已证实幻觉。
- 后续：独立研究简洁回答与事实支持审查；保留本轮原始分数，不删除有支持的补充信息来追求分数。

## 2. 平行数据：结论方向有支持，输出协议破坏

ID：`111afb77cfbf4c98e0458606378fa63a0e965e36`；论文 `1603.01514`。问题：Overall, does having parallel data improve semantic role induction across multiple languages?

- 观察：R5/C=1/1，`invalid_output`，AF1=0.0541、EF1=0，0 条有效引用。rank 2 的 gold `s13:p0` 说对齐带来小且不显著的提升；rank 4 `s9:p5` 给出仅 8%/17% 论元对齐。模型反复输出三个 `FINAL ANSWER`，第一条 `END_PHRASE` 为空，触发 `invalid_protocol` 和缺失引用短语。
- 主因：生成协议/引用失败；次要是重复冗长答案拉低 yes/no 词面分数。参考为 No，输出“不显著改善”的方向与证据一致，但不能扩展成“任何平行数据都完全无益”；abstract 同时说明增加单语数据的影响。
- 后续：未来单独验证单一答案段与短引用格式；当前无须把该例归为 gold 未召回。

## 3. 主动学习定义：上下文足够，仍然拒答

ID：`1cfed6b0c9b5a079a51166209649a987e7553e4e`；论文 `1801.07887`。问题：What is active learning?

- 观察：R5/C=1/1，`insufficient_evidence`，AF1/EF1=0/0。rank 4 的 gold `s0:p1` 明确解释迭代训练中选择未标注样本进行标注；两份参考都以这一过程为定义。实际输出只有 `[INSUFFICIENT_EVIDENCE]`。
- 主因：有直接定义证据时的生成误拒答；次要可能是 rank 1 停止条件段落引入干扰，但单条记录不能证明模型内部为何拒答。无上下文丢弃，无证据表明是 token 窗口溢出。
- 后续：将该例作为未来拒答边界复核样本；不因本轮看到失败而修改冻结规则。

## 4. 最优翻译数据集：召回相关数据集，但漏掉结果主张

ID：`1ed49a8c07ef0ac15cfa6b7decbde6604decbd5b`；论文 `1906.07701`。问题：What dataset does this approach achieve state of the art results on?

- 观察：R5/C=0.5/0.5，`insufficient_evidence`，AF1/EF1=0/0。rank 1 `s0:p0` 介绍 Multi30K 及德/法语言；rank 5 的 gold `s5:p0` 仅描述比较设置。另一 gold `s5:p1` 才明确说在 English-German dataset 上达到 transformer constrained models 的最优表现，未进入实际上下文。
- 主因：检索遗漏回答所需的结果限定；次要是输出拒答在官方可回答题上计零，但就现有上下文而言拒绝猜测哪种语言是合理的。不能把“已看到 Multi30K”等同于已得到 SOTA 对应子集。
- 后续：未来独立检查结果段排序或相邻段关联；本轮不补召回、不重新生成。

## 5. 人与机器的错觉：生成截断，不是成功拒答

ID：`27cf16bc9ef71761b9df6217f00f39f21130ce15`；论文 `1906.01040`。问题：Are humans and machine learning systems fooled by the same kinds of illusions?

- 观察：标注为不可回答，R5/C 不适用；`error`、`output_truncated`、`done_reason=length`，AF1/EF1=0/0。1530 context tokens、无丢弃。原始输出连续复制长引用，在第三条 START_PHRASE 中断，没有完成 FINAL ANSWER。
- 主因：输出生成长度截断，自动标签 `runtime_error` 过于宽泛，不能解释成数据库/网络故障。rank 2 `s1:p0` 明确讨论 McGurk 与典型机器对抗样本的不同，且提及部分视觉样例；这些限定不支持对所有“相同种类错觉”给出笼统结论。
- 边界/次因：该例计入不可回答系统错误，不计正确拒答，也不应根据未完成引用推断模型已作出错误最终判断。没有完整 gold 可用于判断检索失败。
- 后续：未来单独研究引用长度与生成预算；本轮保留截断原始输出和失败分母。

## 6. 语言学特征：引用可追溯，研究对象归属仍可能错

ID：`4e748cb2b5e74d905d9b24b53be6cfdf326e8054`；论文 `1701.05574`。问题：What traditional linguistics features did they use?

- 观察：标注不可回答，`ok`，AF1/EF1=0/0，1 条有效引用；被计 `unanswerable_wrong_answer=1`。rank 1 `s1:p1` 以“Computational linguists have previously addressed”引出 unigrams/pragmatic、stylistic/situational disparity、hashtag 特征，模型将其写成“they used”。
- 主因：语义上的归属跳跃风险，引用确实包含这些词，但描述的是先前研究。rank 2 `s8:p0` 才描述本研究采用 lexical/implicit/explicit incongruity 及 readability/word count，并指向缺失的表格细项。
- 边界/次因：数据标注与语义可回答性仍值得复核，不能仅因 unanswerable 标签宣称整篇没有相关特征信息；也不能因引用有效宣布回答正确。当前已能指出具体的 related-work→本研究归属混淆。
- 后续：未来由人核对问题指代、表格缺失及参考标注；不更改当前 gold 或误答计数。

## 7. SnapCaptions 大小：支持充分的数值回答

ID：`1591068b747c94f45b948e12edafe74b5e721047`；论文 `1802.07862`。问题：How large is their MNER SnapCaptions dataset?

- 观察：R5/C=1/1，`ok`，AF1=0.6364、EF1=1，1 条有效引用。rank 1 `s6:p0` 写 10K image-caption pairs；回答准确给出 10K pairs。两个参考分别为较短的 10K 描述和 `10000`。
- 主因/边界：这是成功边界案例，没有在核对字段中发现数量事实失败。低于 1 的 AF1 涉及回答长度及表述形式；不能把 10K 与 10000 的词面差异当成数值冲突。次要不确定性仅是本次助手审查不构成全面人工认证。
- 后续：未来另行统计数值等价性；不修改官方 scorer 或把本例包装成失败。

## 8. 可解释性实验：参考分歧与句级引用支持分开看

ID：`17a1eff7993c47c54eddc7344e7454fbe64191cd`；论文 `1807.07279`。问题：What experiments do they use to quantify the extent of interpretability?

- 观察：R5/C=1/1，`ok`，AF1=0.3279、EF1=0.6667，2 条有效引用。rank 2 的 gold `s6:p0` 提到 word intrusion test 成本高，随后明确“In this study”使用 SEMCAT semantic category-based approach 与 IS；回答报告后者。
- 主边界：一份参考声称人类 word intrusion 加自动 SEMCAT，另一份只写 semantic category-based approach。现有 gold 段落没有明确证明本研究实际执行了人类 word intrusion，不能机械地把模型未提该项认定遗漏。
- 次要引用问题：回答的 IS 句挂 `【2】`，对应 rank 1 `s6:p4` 仅讲 SEMCAT 与 Roget's 的区分；IS 实际位于 `【1】` 的 `s6:p0`。两个引用都可追溯，不代表逐句支持关系都正确。
- 后续：未来人工复核参考分歧及逐句引用绑定；当前不修 gold、不将引用有效数当语义支持率。

## 9. CNN baseline features：正确文本绑定了错误 SOURCE

ID：`1beb4a590fa6127a138f4ed1dd13d5d51cc96809`；论文 `1610.08815`。问题：What are the network's baseline features?

- 观察：R5/C=1/1，`invalid_output`，AF1=0.2105、EF1=0，0 条有效引用。rank 3 的 gold `s8:p0` 明确解释 CNN 抽取特征及 100 neurons→100 features，模型答案和起止短语来自这里。
- 主因：输出 SOURCE 却写为 rank 1 `s16:p0` 的 `S0c00bc95cde8`，而正确段落标签是 `Sbc3981439486`，因此 `quote_not_exactly_in_source`。这不是“所有上下文都没有该引文”，而是实际引用地址绑定错误。
- 次要边界：参考只有“features extracted from CNN”，扩写拉低 AF1；扩写内容在正确的上下文块中有支持。不能把协议失败一并解读为核心答案事实错误。
- 后续：未来独立验证 source-label 与引文配对；当前不自动修复原输出，不回填有效引用。

## 10. GRU 所捕获的信息：直接答案进入上下文后误拒答

ID：`1d9aeeaa6efa1367c22be0718f5a5635a73844bd`；论文 `1907.09369`。问题：What meaningful information does the GRU model capture, which traditional ML models do not?

- 观察：R5/C=1/1，`insufficient_evidence`，AF1/EF1=0/0。rank 2 的 gold `s4:p1` 明说 context and sequential nature of the text，并将其与 bidirectional GRU 联系；rank 1 `s1:p1` 说明 BOW/lexicon 方法丢失信息，rank 3 `s7:p0` 再强调序列性。两份参考均是上下文和序列信息。
- 主因：生成误拒答，实际证据不只是完整 gold 指标为 1，而是包含可直接回答的语句。次要注意问题对“traditional ML”的概括比论文的 BOW/lexicon 比较宽，合理回答应保留比较范围，而非完全拒答。
- 后续：未来独立评估有证据时的保守回答策略；不根据此例调整本轮拒答规则。

## 标签解释与未完成边界

`ok` 仅表示当前输出协议通过，不自动证明语义正确（例 6、8）；`invalid_output` 也不等于全文事实错误（例 2、9）。`answer_or_reference_review` 包含成功但词面分数低的边界例（1、7）。`runtime_error` 在例 5 实际是生成输出截断。以上区分不改变原始分类字段与分数。

十条逐项复核已写入本报告；U3 案例判断与审计测试记录见 `reports/t7-u3.md`，由助手按用户委托完成。未来建议没有实施，最终配置冻结仍待处理，Test 未运行。
