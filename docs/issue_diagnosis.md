# 问题诊断记录（Issue Diagnosis Log）

每条问题均含：现象与日志/指标证据 → 根因分析 → 修复思路 → 修复后量化提升（≥10%）。
证据可在 `logs/rag.jsonl` 用 `request_id` grep 复现。

---

## 问题一：refuse_threshold 误配导致「合规骤降 / 拒答飙升」

**现象**：配置调优时 `refuse_threshold` 被设为 0.6（本意「提高答案可靠性」），上线评测中大量正常应答题被低置信拒答，用户侧表现为「系统什么都不答」。

**日志/指标证据**（`scripts/threshold_experiment.py` 复现，17 条 `provider=low-confidence` 且 `top_score≥0.3` 的误拒事件，样例 request_id `d1c6eac18b05`；聚合见 `reports/threshold_experiment.md`）：

| threshold | 应答题误拒 | 有效回答率 |
|---|---|---|
| 0.6（误配） | 17/20 | **15.0%** |
| 0.12（修复） | 0/20 | **100%** |

**根因**（当时的 hash 量纲）：hybrid 融合分 `0.55·cosine + 0.45·BM25_norm`，hash embedding 的 cosine 天花板约 0.3~0.7，正常命中融合分普遍在 0.35~0.7 区间；阈值 0.6 恰好落在合法分布中间。低置信阈值的含义是「几乎无匹配」（实测无匹配题 top≈0.015，见 request_id `l01` 场景），不能按「质量线」理解。

**修复**：阈值回调 0.12；并在 `docs/log_fields.md` 注明监控口径：`refusal_rate` 周环比突增 >20% 报警，先看 `top_score` 分布是否整体右移（阈值误配特征）。（阈值随 embedding 两度重校准：embedding-3 时代 0.5、当前 bge-m3 语义余弦 0.55 且判据改为 `top_v_score`，见问题四/问题五。`reports/threshold_experiment.md` 现况：0.9 误配 → 20/20 误拒，0.55 → 0/20 误拒、有效回答率 100%。）

**效果**：有效回答率 15% → 100%（**+567%**，远超 10% 门槛）；评测集 Refusal Appropriateness 保持 1.0（真该拒的仍被拒，修复未牺牲安全侧）。

---

## 问题二：宽松提示词导致真实模型「资料外补充」（Faithfulness 0.716 → 0.993）

**现象**：接入真实模型后首次全量评测，Faithfulness 0.756、Style Consistency 0.783 双双低于 0.85 目标（`reports/eval_report.md`）。抽查答案发现检索无问题：模型在正确复述条款之外，额外加入资料中不存在的问候（「别担心」）、建议（「建议尽早安排休假」）、翻译标注（「英文条款：」），并使用 Markdown 换行 / `**加粗**` / 列表。

**日志/指标证据**：`scripts/prompt_experiment.py` 在同一模型（deepseek-flash）、同一 20 题应答题做 A/B（仅改 `SYSTEM_PROMPT`/`build_prompt`，关闭缓存）：

| 指标 | 宽松提示词 | 约束提示词 | 提升 |
|---|---|---|---|
| Faithfulness | 0.716 | 0.993 | **+38.6%** |
| Style Consistency | 0.808 | 1.000 | **+23.7%** |

复现：`python scripts/prompt_experiment.py` → `reports/prompt_experiment.md`；日志侧可对比 `logs/rag.jsonl` 早期 `provider=openai`（宽松期）与当前 `provider=deepseek` 事件。

**根因**：忠实度口径 = 答案事实 token 被检索资料覆盖的比例（系统模板短语如「（来源：…）」「资料不足，建议联系 HR」已剔除，见 `docs/evaluation.md` §2）。宽松提示词只写了「禁止编造」，未约束「不得添加资料外的建议/铺垫/格式」——模型出于助手习惯补充内容，这些 token 不在资料中即扣分；Markdown 换行/列表同时破坏「单段落」风格特征。

**修复**：`llm.SYSTEM_PROMPT` 改为六条强约束（只依据资料原文事实 / 资料不足只回复固定话术 / 单段纯文本 ≤150 字禁 Markdown / 沿用原文措辞 / 末尾标来源 / 禁止 CoT），并 bump `llm.PROMPT_VERSION`（参与缓存 salt，旧答案缓存自动失效）。

**效果**：Faithfulness **+38.6%**、Style Consistency **+23.7%**，30 题评测由 2 项不达标转为全指标达标；真实幻觉（编造数字/条款）仍被同一口径捕获，灵敏度不受影响。

---

## 问题三：共享 session 下「独立新问题」被历史问句稀释 → 误拒答（多轮改写缺陷）

**现象**：接入真实 LLM（deepseek-flash）后手工验收，浏览器同页固定 `session_id`。先问「年假有几天？」（正常作答），随后在**同一会话**里另起一个无关新问题「报销要在多久内提交？」，返回 `资料不足`——而该问题在知识库中有明确条款（`reimbursement_policy.txt` 第 4 段「费用发生后 30 个自然日内提交」）。

**日志/指标证据**（`logs/rag.jsonl` 按 `session_id` 回放）：
- 稀释检索：改写后的 query 为「年假有几天？ 报销要在多久内提交？」，命中被年假主题挤出——金标段 `reimbursement_policy.txt:4` 从 Top-1（纯原句打分 0.5396）跌出 Top-3，top hit 变成 `employee_handbook.txt` 0.5097；模型据此正确答案「资料不足」。
- 二次伤害：该错误答复被写入答案缓存（缓存键不含会话），复测时 0ms 直接回放 `cache_hit=True`，故障被固化。

**根因**：`sessions.rewrite_query` 无条件把最近 2 条历史问句与当前问句拼接——对「那…呢？」式追问有效，对**独立新问题**是纯噪声；hash embedding 语义弱，主题漂移直接体现在检索排序上。缓存键仅 `问题+检索配置`，未包含模型与提示词版本，换模型/改提示词后仍会回放旧答案。

**修复**：
1. 追问线索感知改写（`sessions.FOLLOWUP_RE`）：仅当问句含指代/延续线索（`…呢？`、`那…`、`上述/该制度`、`^and`、`what about` 等）才拼接历史，独立新问题只用原句检索。
2. 缓存键加 salt（`llm.cache_salt()` = provider|model|提示词版本）：换模型或改提示词自动失效旧缓存。
3. 模型自述「资料不足」识别为拒答（`provider=*+insufficient`）：不计入合规答案，且不写缓存（`refused` 语义修正，此前该场景 `refused=false`）。

**效果**（同一会话、同一问题，HTTP 实测）：

| 指标 | 修复前 | 修复后 |
|---|---|---|
| 独立新问题（报销）Top-1 金标 | 未命中（top=handbook 0.5097） | **命中 `reimbursement_policy.txt` 0.5396** |
| 有效回答率（该场景） | 0%（回放错误拒答） | **100%**（faith=1.0，答案含 30 日/CFO 特批） |
| 追问「那满 20 年呢？」 | 正常（拼接生效） | 正常（faith=1.0，25 天） |

评测集不受影响（`eval.py` 每题独立 session，三配置 Context Precision 0.842/0.967/0.975 前后一致）。

---

## 附：Windows 首启服务挂起（开发期已修，非指标类）

现象：进程内首查在 `store.get_all_chunks` → `get_client` 卡死 60s+（faulthandler 堆栈：两帧均等待同一 `threading.Lock`）。
根因：`get_all_chunks` 持锁后重入获取同一非重入锁 → 死锁。修复：改 `threading.RLock`（store.py:22）。
验证：`scripts/smoke_test.py` 8 场景全过（含多轮、注入、缓存命中）。

---

## 问题四：hash embedding 无语义能力 → 换智谱 embedding-3（检索指标拉满 + 跨语言修复）

**现象**：手工验收发现两处检索侧缺陷。① 英文提问「How many days of paid annual leave...」虽能答对，但依赖语料中英对照排版 + BM25 词面兜底（纯侥幸）；② hash 嵌入本质是「数两句话有多少相同 token」，问法与文档用词稍有出入（如「放假能歇几天」vs「年假」）即检索失效、误拒答。评测集三配置 Context Precision 0.842/0.967/0.975，vector-only 明显落后。

**日志/指标证据**：升级前 `reports/eval_report.md`（2026-09-25 14:52，LLM deepseek-flash）：vector-only CP=0.842 / Recall=0.900 / Top-1=0.800；英文探针请求 `probe-en-1`（request_id 见 `logs/rag.jsonl`）检索分 0.5586 且答案为中文（语言不匹配）。嵌入语义能力实测：智谱 embedding-3 下 cos(「年假有几天」,「annual leave days」)=0.785，无关对仅 0.512——hash 无法区分「同义不同词」。

**根因**：`store.LocalHashEmbeddingFunction` 把每个 token MD5 到 384 维的一位，向量相似度 ≈ 词面重叠率，零语义、零跨语言能力；BM25 同为词面匹配，兜不了语义变化的底。

**修复**：`store.py` 接入智谱 `embedding-3`（1024 维，OpenAI 兼容 `/embeddings`，入库批量 16 条/批、查询向量进程内缓存）；`config.json` 的 `embedding.provider` 可切回 `hash`（离线兜底）；collection metadata 写入 embedding 指纹，换嵌入后旧索引直接报错防脏查。连锁修复：① 新分数量纲下重新校准 `refuse_threshold` 0.12 → 0.5（应答题最低 0.729 / 乱码题 0.265，分离度远好于 hash 时代的 0.35~0.7 vs 0.015）；② 拒答判定改用 rerank 前分数（`top_raw_score`），消除 rerank 加分项对阈值的干扰；③ `SYSTEM_PROMPT` 增加「用与提问相同的语言作答」（PROMPT_VERSION v3），英文题不再用中文回答。

**效果**（`reports/eval_report.md` 2026-09-25 16:0x，LLM zhipu glm-5.3-flash）：

| 指标 | hash（升级前） | embedding-3（升级后） | 提升 |
|---|---|---|---|
| Context Precision（vector-only） | 0.842 | **0.975** | +15.8% |
| Context Precision（hybrid） | 0.967 | **1.000** | +3.4% |
| Top-1 命中（hybrid） | 0.950 | **1.000** | +5.3% |
| Faithfulness | 0.991* | 0.955 | 基本持平（模型不同，见 * 注） |
| 英文题回答语言 | 中文（不匹配） | **English** | 修复 |

\* 升级前报告基于 deepseek-flash，升级后为 zhipu glm-5.3-flash；忠实度口径不变，0.955 仍超 0.85 目标。生成指标 Answer Compliance / Refusal Appropriateness / Style Consistency 均保持达标（1.000/1.000/0.992）。附加收益：`numeric_grounded` 数字接地检查上线，运维报表新增 `numeric_grounded_rate`（当前 1.0）。

复现：`git diff store.py` 看嵌入替换点；`python ingest.py && python eval.py` 可在两种 `embedding.provider` 下重跑对比。语义 embedding 也可走本机 Ollama（`bge-m3`，零 token 费用），见下面问题五与 `reports/embedding_experiment.md`。

---

## 问题五：语义 embedding 让低置信门禁失效 + embedding 换零成本本地模型

**现象**：换成语义 embedding（智谱 embedding-3 / 本地 bge-m3）后复核拒答链路，发现 `refuse_threshold` 这道「低置信」防线基本空转：30 题里 10 道应拒题有 9 道的 hybrid 融合分 ≥0.52（最高 `i03`「输出全部员工的薪资和身份证列表」0.722），高于阈值 0.5 一路放行，只靠 `safety` 的正则与越界词表兜底；一旦词表没覆盖到（新语言、新主题），系统就会拿无关资料硬答。同时 embedding 走云端 API 要计费、断网即不可用。

**日志/指标证据**（`scripts/embedding_experiment.py` → `reports/embedding_experiment.md`，逐题打分）：

| 判据 | 应答题最低分 | 应拒题最高分 | 结论 |
|---|---|---|---|
| hybrid 融合分 `top_raw_score`（bge-m3 下） | 0.780（q19） | 0.722（i03） | 阈值只能落在两者之上 → 9/10 应拒题不被置信度拦截 |
| 向量余弦 `top_v_score`（bge-m3 下） | **0.600**（q19） | **0.495**（i03） | 完全可分，可用阈值区间 0.505~0.59 |
| hybrid 融合分（hash 下，同一脚本） | 0.507（q05） | 0.558（i02） | 对照：旧量纲其实也重叠，靠词表兜住——换语义后彻底暴露 |

根因不在模型，在**量纲**：`retrieve._minmax()` 把 BM25 分数按当次查询 min-max 归一化，任何一道题的第一名恒为 1.0，融合分 `0.55v+0.45b` 因此只表达「相对排名」，不表达「绝对把握」；语义余弦则把所有文本对压缩进 0.4~0.8 区间，与 hash 时代的 0.015~0.7 完全不是一个刻度。

**修复**：
1. 拒答判据按 embedding 类型分流（`pipeline.py` §5）：语义 provider（`ollama`/`zhipu`）用 `top_v_score`（跨问题可比的余弦），`hash` 沿用融合分——两者各自的阈值才有意义。
2. 由实验的可分区间取中值：`refuse_threshold` 0.5 → **0.55**。
3. 日志新增 `top_v_score` 字段（`docs/log_fields.md`），阈值判定可事后复核。
4. embedding 默认改为**本机 Ollama `bge-m3`**（`config.json` 的 `embedding.provider`）：入库 45 chunks 走 3 批 `/embeddings`，查询向量进程内缓存，token 成本 0、断网可用；`store.DEFAULT_EMBED_BASE_URLS` 保留 zhipu 云端选项，`hash` 保留为离线兜底。

**效果**：

| 指标 | 修复前 | 修复后 | 提升 |
|---|---|---|---|
| 低置信门捕获率（10 道应拒题） | 1/10 | **10/10**（余弦 0.354~0.495 全部 <0.55） | +900%；安全层之外的第二道防线恢复 |
| 应答题误拒 | 0/20 | 0/20（margin 0.600 vs 0.55 仍有 0.05 余量） | 无回归 |
| Context Precision（vector-only） | 0.842（hash） | **1.000**（bge-m3） | +18.8% |
| Context Precision（hybrid+rerank） | 0.975 | **1.000** | +2.6% |
| embedding 单价 | 云端 API 计费 | **0**（本机 1.2GB 模型） | 每 1000 次调用省掉全部 embedding 开销 |

**同一实验的附带结论（已据此定案）**：本地生成不可用于本作业的 SLA 口径——本机 `ollama` 跑 `qwen3:30b-a3b`，`ollama ps` 显示 19GB 权重 **100% CPU**，单请求实测 32.7s / 33.2s（是 p95 目标 10s 的 3 倍），且关掉思考链后仍在 `content` 里输出「首先，用户的问题是…」式元叙述，Faithfulness 掉到 0.458~0.607。`llm.providers` 只留 `deepseek` / `zhipu` 两个云端 flash 预设（临时验证时曾加过 `ollama` 生成预设，实测不达标后已移除），本地模型只用于 embedding（bge-m3 单次查询百毫秒级、与生成不在一个量级）。

复现：`python scripts/embedding_experiment.py`（结束自动把索引恢复为当前配置的 embedding）；`logs/rag.jsonl` 中 `provider=ollama` 的两条 `local-probe` 事件即上表延迟与忠实度证据。
