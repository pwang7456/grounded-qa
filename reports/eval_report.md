# 评测报告 Evaluation Report

- 生成时间：2026-09-27 13:14:33  用时 53.3s
- 题目：49（问答 37 / 应拒答 12）
- LLM provider：zhipu  模型：glm-5.3-flash
- Embedding：ollama:bge-m3:1024  refuse_threshold：0.55

## 1. 检索三配置对比（Context Precision / Recall / MRR / Top-1）

| 配置 | ContextP@k | Recall | MRR | Top-1 命中 |
|---|---|---|---|---|
| vector-only | 0.892 | 0.973 | 0.892 | 0.838 |
| hybrid | 0.892 | 0.973 | 0.892 | 0.838 |
| hybrid+rerank | 0.896 | 0.973 | 0.896 | 0.838 |

## 2. 生成质量指标 vs 目标

| 指标 | 实测 | 目标 | 达标 |
|---|---|---|---|
| Faithfulness | 0.931 | 0.85 | ✅ |
| Context Precision (best mode) | 0.896 | 0.70 | ✅ |
| Answer Compliance | 0.991 | 0.90 | ✅ |
| Refusal Appropriateness | 1.000 | 0.90 | ✅ |
| Style Consistency | 0.987 | 0.85 | ✅ |

## 3. 样例（前 5 题）

- **年假有几天？** → 年假按司龄计算：入职满1年不满10年每年15天带薪年假；满10年不满20年为20天；满20年为25天。新员工入职满3个月后可休年假，首年年假按剩余日历天数折算。年假须在当年12月31日前使用，未休完最… (faith=0.9839)
- **司龄满 10 年年假多少天？** → 司龄满 10 年不满 20 年为 20 天。（来源：employee_handbook.txt）… (faith=1.0)
- **年假没休完可以结转到明年吗？** → 可以。年假须在当年12月31日前使用，未休完的年假最多可结转5天至次年第一季度，逾期自动作废。（来源：employee_handbook.txt）… (faith=1.0)
- **病假期间工资怎么发？** → 病假需提供二级及以上医院或公司医务室出具的病假证明。15天以内的病假工资按基本工资的70%发放；超过15天按60%发放，医疗期内不得解除劳动合同。（来源：employee_handbook.txt）… (faith=1.0)
- **突然生病来不及请假怎么报备？** → 突发疾病应在当日 10:00 前电话或系统报备直属主管，事后 2 个工作日内补交证明；病假需提供二级及以上医院或公司医务室出具的病假证明。（来源：employee_handbook.txt）… (faith=1.0)
