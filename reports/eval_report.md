# 评测报告 Evaluation Report

- 生成时间：2026-09-26 22:08:45  用时 26.9s
- 题目：30（问答 20 / 应拒答 10）
- LLM provider：zhipu  模型：glm-5.3-flash
- Embedding：ollama:bge-m3:1024  refuse_threshold：0.55

## 1. 检索三配置对比（Context Precision / Recall / MRR / Top-1）

| 配置 | ContextP@k | Recall | MRR | Top-1 命中 |
|---|---|---|---|---|
| vector-only | 1.000 | 1.000 | 1.000 | 1.000 |
| hybrid | 1.000 | 1.000 | 1.000 | 1.000 |
| hybrid+rerank | 1.000 | 1.000 | 1.000 | 1.000 |

## 2. 生成质量指标 vs 目标

| 指标 | 实测 | 目标 | 达标 |
|---|---|---|---|
| Faithfulness | 0.951 | 0.85 | ✅ |
| Context Precision (best mode) | 1.000 | 0.70 | ✅ |
| Answer Compliance | 1.000 | 0.90 | ✅ |
| Refusal Appropriateness | 1.000 | 0.90 | ✅ |
| Style Consistency | 1.000 | 0.85 | ✅ |

## 3. 样例（前 5 题）

- **年假有几天？** → 年假按司龄计算：司龄满1年不满10年，每年享有15天带薪年假；满10年不满20年为20天；满20年为25天。（来源：employee_handbook.txt）… (faith=1.0)
- **司龄满 10 年年假多少天？** → 司龄满 10 年不满 20 年的员工每年享有 20 天带薪年假。（来源：employee_handbook.txt）… (faith=1.0)
- **年假没休完可以结转到明年吗？** → 未休完的年假最多可结转 5 天至次年第一季度，逾期自动作废；年假原则上须在当年 12 月 31 日前使用。（来源：employee_handbook.txt）… (faith=0.9211)
- **病假期间工资怎么发？** → 15 天以内的病假工资按基本工资的 70% 发放；超过 15 天按 60% 发放，医疗期内不得解除劳动合同。病假需提供二级及以上医院或公司医务室出具的病假证明。（来源：employee_handboo… (faith=1.0)
- **突然生病来不及请假怎么报备？** → 突发疾病应在当日 10:00 前电话或系统报备直属主管，事后 2 个工作日内补交证明。（来源：employee_handbook.txt）… (faith=1.0)
