# T7 Dev 生成对照

同一 2400/200 chunk 集、冻结生成 Dev 50 题（40 可回答、10 无答案）。
固定 Qwen、prompt、温度/seed、8192 窗口、512 输出上限及 5 chunk/4500 token 预算。
只有检索方法不同；全部首次结果保留，错误不伪装拒答。

检索阶段选中的方法就是 Dense，因此只运行一次 50 题，没有伪造第二组。

## dense

| 指标 | 值 |
|---|---:|
| Answer F1 | 0.2516672803691196 |
| Evidence F1 | 0.37666666666666665 |
| Context EvidenceRecall | 0.7291666666666666 |
| Context AllEvidence | 0.7 |
| Correct refusal rate | 0.7 |
| Wrong-answer rate | 0.2 |
| Wrong refusal rate | 0.325 |
| Citation compliance | 0.9047619047619048 |
| Citation traceability | 0.8 |
| system_errors | 9 |
| System error rate | 0.18 |
| citation_eligible | 21 |
| citation_compliant | 19 |
| citations_parsed | 30 |
| citations_valid | 24 |
| unanswerable | 10 |
| Unanswerable system error rate | 0.1 |
| unanswerable_correct_refusal | 7 |
| unanswerable_wrong_answer | 2 |
| unanswerable_system_error | 1 |
| answerable_refusal | 13 |

官方整体 F1 分母为 50；以下为 40 道可回答题的单题分数均值，单列观察，不替代官方整体口径。
可回答 Answer F1：0.139584；可回答 Evidence F1：0.295833。

官方 F1 是词面/原始段落匹配，不等于所有事实语义正确。完整段落 Evidence F1 与实际 context 覆盖分开报告。
引用可追溯不证明引用支持全部关键陈述；未自动认证人工支持率。

失败案例见 [Dev 错误分析](dev-errors.md)；本报告仅记录 Dev 阶段结果，不替代正式 Test。
