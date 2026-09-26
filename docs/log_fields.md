# 日志字段字典 logs/rag.jsonl

每个请求写一行 JSON（append-only），问题与答案在写入前均已 PII 脱敏。

| 字段 | 类型 | 说明 |
|---|---|---|
| `request_id` | string | 单次请求唯一 ID（uuid4 前 12 位），用于串联排查 |
| `session_id` | string | 会话 ID，多轮追问共享；`anon` 表示未传 |
| `question` | string | 用户问题（PII 脱敏后：`[PHONE]/[EMAIL]/[ID]/[BANKCARD]` 占位） |
| `answer` | string | 最终答复（PII 脱敏后）；拒答时为拒答文案 |
| `refused` | bool | 是否拒答（安全 / 越界 / 低置信 / 模型自述资料不足四类） |
| `provider` | string | 答复来源：`deepseek` / `zhipu`（= config.json 的 `llm.active`，生成侧只有云端预设）/ `safety` / `low-confidence` / `embedding-unavailable`（embedding 端点异常，记为拒答）/ `*+insufficient`（模型自述资料不足，记为拒答） / `*+unavailable`（端点异常，记为拒答） / `*+unusable-output`（CoT 残留等不可用输出，记为拒答） / `*-low-faithfulness-flag`（低忠实度标记） / `*-num-ungrounded-flag`（数字不接地标记，仅标记不拒答） |
| `retrieval_mode` | string | 本次生效的检索模式：`vector` / `hybrid` |
| `rerank_enabled` | bool | 本次是否启用 rerank |
| `cache_hit` | bool | 是否命中答案缓存 |
| `token_usage` | object | `{prompt_tokens, completion_tokens, total_tokens}`；缓存/拒答/兜底为 0 |
| `latency_ms` | int | 服务端端到端耗时（毫秒），压测口径 p50/p95 即此字段 |
| `hit_ids` | string[] | 检索命中 chunk ID 列表（`文件名:段号`），可回溯到知识库原文 |
| `top_score` | float | 最高检索分（rerank 后展示口径） |
| `top_raw_score` | float | rerank 前分数（hybrid 融合分 / vector 相似度）。`embedding.provider=hash` 时低置信拒答作用于此字段 |
| `top_v_score` | float | 命中里最高的向量余弦（`1 - cosine distance`，与 embedding 模型同量纲）。语义 embedding（`ollama`/`zhipu`）时低置信拒答作用于此字段——hybrid 融合分里的 BM25 项经 min-max 归一化后每题第一名恒为 1.0，绝对值跨问题不可比（见 `docs/issue_diagnosis.md` 问题五） |
| `faithfulness` | float\|null | 答案 token 被检索资料覆盖的比例（0~1）；拒答/缓存路径为 null 或缓存值 |
| `numeric_grounded` | bool\|null | 数字接地：答案中数字是否全部出现在检索资料中（null=缓存外未测路径）。false 会打 `*-num-ungrounded-flag` 并计入合规扣分 |
| `llm_error` | string\|null | LLM 调用失败或输出不可用的原因（`HTTP 401 ...` / `endpoint unreachable` / `api_key 未配置` / `模型输出不可用…原始输出片段`）；正常为 null。用于区分「模型没接好」与「检索没命中」 |
| `ok` | bool | 处理是否完成（保留字段，异常可据此报警） |

## 用途

- 生成监控：`refusal_rate`、`p95(latency_ms)`、`avg(faithfulness)`、`cache_hit_rate`（`scripts/ops_report.py` 直接聚合）。
- 问题诊断：按 `session_id` 回放多轮；按 `hit_ids` 定位误召回 chunk；`provider` 分布突变说明模型/兜底链路异常。
- 采样示例：

```json
{"request_id":"a1b2c3d4e5f6","session_id":"web-42","question":"年假有几天？","refused":false,"provider":"deepseek","retrieval_mode":"hybrid","rerank_enabled":true,"cache_hit":false,"token_usage":{"prompt_tokens":403,"completion_tokens":187,"total_tokens":590},"latency_ms":1317,"hit_ids":["employee_handbook.txt:2","employee_handbook.txt:3"],"top_score":0.6599,"top_raw_score":0.8401,"top_v_score":0.7092,"faithfulness":1.0,"numeric_grounded":true,"llm_error":null,"answer":"年假天数按司龄计算：入职满1年不满10年每年享有15天带薪年假…（来源：employee_handbook.txt）","ok":true}
```
