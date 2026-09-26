# 评测报告 Evaluation Report

- 生成时间：2026-09-25 23:37:09  用时 55.5s
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
| Faithfulness | 0.923 | 0.85 | ✅ |
| Context Precision (best mode) | 1.000 | 0.70 | ✅ |
| Answer Compliance | 1.000 | 0.90 | ✅ |
| Refusal Appropriateness | 1.000 | 0.90 | ✅ |
| Style Consistency | 0.975 | 0.85 | ✅ |

## 3. 样例（前 5 题）

- **年假有几天？** → 年假天数按司龄计算：入职满 1 年不满 10 年的员工，每年享有 15 天带薪年假；司龄满 10 年不满 20 年为 20 天；满 20 年为 25 天。新入职员工自入职之日起满 3 个月后即可开始休… (faith=1.0)
- **司龄满 10 年年假多少天？** → 根据资料，司龄满 10 年不满 20 年的员工，每年享有 20 天带薪年假。（来源：employee_handbook.txt）… (faith=0.8095)
- **年假没休完可以结转到明年吗？** → 可以。年假须在当年12月31日前使用，未休完的年假最多可结转5天至次年第一季度，逾期自动作废。（来源：employee_handbook.txt）… (faith=0.9722)
- **病假期间工资怎么发？** → 15 天以内的病假工资按基本工资的 70% 发放；超过 15 天按 60% 发放。病假需提供二级及以上医院或公司医务室出具的病假证明，医疗期内不得解除劳动合同。（来源：employee_handboo… (faith=1.0)
- **突然生病来不及请假怎么报备？** → 突发疾病应在当日 10:00 前通过电话或系统报备直属主管，事后 2 个工作日内补交证明。（来源：employee_handbook.txt）… (faith=0.9714)
