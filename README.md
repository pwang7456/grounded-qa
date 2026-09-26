# 有据 · 内部制度问答（Grounded QA）

<a id="top"></a>
**中文** &nbsp;|&nbsp; <a href="README.en.md">English</a>

对照 take-home（Asst Manager, Backend Developer, AKP）实现的多轮 RAG 问答 + 生成服务：
中英双语知识库（含文字 PDF 与扫描 OCR 页）、语义 embedding（本机 Ollama `bge-m3`，零 token 成本；可切云端智谱 embedding-3 或离线 hash 兜底）、
可配置检索（vector / hybrid / +rerank，改配置不改代码）、
三类拒答（注入 / 越界 / 低置信）＋模型自述资料不足识别、数字接地校验、PII 脱敏、答案缓存、结构化日志、一键评测与压测、运维报表。

## 目录

| 章节 | 中文 | English |
|---|---|---|
| 1 快速开始 Quick Start | [§1](#s1) | [§1](README.en.md#s1) |
| 2 架构 Architecture | [§2](#s2) | [§2](README.en.md#s2) |
| 3 配置 Configuration | [§3](#s3) | [§3](README.en.md#s3) |
| 4 选型依据 Design rationale | [§4](#s4) | [§4](README.en.md#s4) |
| 5 知识库摄入与数据库 Ingestion & store | [§5](#s5) | [§5](README.en.md#s5) |
| 6 限制 Limitations | [§6](#s6) | [§6](README.en.md#s6) |
| 7 模型与成本 Model & cost | [§7](#s7) | [§7](README.en.md#s7) |
| 8 交付物 Deliverables | [§8](#s8) | [§8](README.en.md#s8) |

<a id="s1"></a>
## 1. 快速开始（Windows）

依赖已装好（`python` 命令直接可用）。首次入库后，双击 `app.py` 或命令行启动均可：

```bat
cd /d D:\myspace\grounded-qa
python ingest.py      &REM 知识库入库（已入库，改了 data/ 再跑）
python app.py         &REM 起服务：http://127.0.0.1:8788，Ctrl+C 停止
```

浏览器打开 `http://127.0.0.1:8788`，同页固定 session_id，可直接多轮追问。页面提供：

- **最新问答置顶**，每张卡片带答案 + 依据片段（分数/余弦/权重条）+ 指标徽章（provider、检索模式、延迟、缓存命中、faithfulness、token）；
- **演示入口按钮**：正常问答 / 报销 / 多轮追问（代词补全）/ 英文 / 越界拒答 / 注入拒答 / 低置信拒答，一条点击即复现对应链路；
- **顶部状态胶囊**：实时显示当前 `llm.active` 模型、embedding 签名、chunk 数，便于演示前确认配置；「新会话」按钮换一个 session_id（清掉多轮上下文）。

> 依赖清单：`chromadb`、`pypdf`、`reportlab`（`python -m pip install -r requirements.txt`）。

### 配置大模型与 embedding（config.json + config.local.json 双层）

项目内配置分两层，**local 覆盖模板**（深度合并）：

- **`config.json`**：模板与全部非敏感配置（检索参数、模型预设端点/模型名、embedding 选择），**key 留空，可直接提交/分享**。
- **`config.local.json`**：只放 `api_key` 等敏感项，**已加入 `.gitignore`，不会入库**。格式与 config.json 一致，同名键覆盖：

```json
{ "llm": { "providers": { "zhipu": { "api_key": "你的key" } } } }
```

- **切换模型**：把 `config.json` 的 `llm.active` 改成 `"zhipu"`（默认）或 `"deepseek"`（新增预设格式一致，无需改代码）。生成侧统一走云端 OpenAI 兼容端点。
- **切换 embedding**：`embedding.provider` 三选一——`"ollama"`（本机 `bge-m3`，语义 + 跨语言，零 token 费用、断网可用；**仓库当前 config.json 即此项**）、`"zhipu"`（云端 embedding-3，效果同级、复用同一个智谱 key）或 `"hash"`（离线词面兜底）；**换 embedding 后必须重跑 `python ingest.py`**（索引指纹校验，不重跑直接报错防脏查）。
- 检索类参数（`retrieval_mode` / `rerank_enabled` / `top_k` / `refuse_threshold` 等）热读即时生效；改模型连接参数需重启 `app.py`。
- 端点异常 / key 未配置时返回统一错误答复（`provider=*+unavailable` 或 `*+insufficient`），embedding 端点异常记为 `embedding-unavailable`；原因写入日志 `llm_error` 字段，不静默降级、不返回残缺答案。
- `/api/config` 回传配置时会把 `api_key` 掩码为 `***`；**提交/分享前请自行清空 `config.local.json`（或直接不拷贝它）**。

### 本地向量模型（embedding，可选全离线）

向量模型跑在本机 Ollama 上（语义 + 跨语言，零 token 费用、查询不依赖网络）：

```bat
ollama pull bge-m3     &REM 1.2GB，向量模型
python ingest.py       &REM 按当前 embedding.provider 重建索引
```

> 生成侧不设本地预设：本机 `qwen3:30b-a3b` 实测 **100% CPU**（`ollama ps`：19GB 权重）、单请求 32~33s，达不到 10s SLA，Faithfulness 也掉到 0.458~0.607，因此只保留云端 flash 级预设做生成（证据见 `docs/issue_diagnosis.md` 问题五）。不想装 Ollama 时把 `embedding.provider` 改成 `"zhipu"`（复用智谱 key）或 `"hash"`（纯离线词面兜底），改完重跑 `python ingest.py`。

### 评测 / 压测 / 报表（一键）

```bat
python eval.py                              &REM → reports/eval_report.md + eval_metrics.csv
python scripts\load_test.py 60 8            &REM 需先启动 app.py → reports/load_test.csv
python scripts\ops_report.py 96             &REM 聚合日志（可选参数=只统计最后 N 条）→ reports/ops_report.{csv,md}
python scripts\smoke_test.py                &REM 冒烟（进程内 8 场景）
python scripts\prompt_experiment.py         &REM 提示词对照实验 → reports/prompt_experiment.md
python scripts\threshold_experiment.py      &REM 拒答阈值实验 → reports/threshold_experiment.md
python scripts\embedding_experiment.py      &REM embedding 同题对比 → reports/embedding_experiment.md
```

<a id="s2"></a>
## 2. 架构

```
POST /api/ask {q, session_id, retrieval_mode?, rerank_enabled?}
  → app.py(ThreadingHTTPServer :8788) → pipeline.answer_question
      safety(注入/越界→拒答) → cache → sessions(追问线索感知改写) → retrieve(vector|hybrid[+rerank])
      → 低分拒答(语义 embedding 用向量余弦 / hash 用 rerank 前融合分) → llm(DeepSeek / 智谱 GLM，OpenAI 兼容) → 资料不足识别/数字接地/PII 脱敏 → 日志/缓存/会话
数据面：data/*.(txt|pdf|ocr.txt) → ingest.py + pdf_reader.py → store(分块+embedding：ollama bge-m3|zhipu embedding-3|hash) → Chroma(chroma_data/)
```

| 文件 | 职责 |
|---|---|
| `app.py` | HTTP：`/api/ask` `/api/health` `/api/config` + 静态页 |
| `pipeline.py` | 主编排（安全→缓存→检索→生成→日志）；低置信拒答：语义 embedding 用向量余弦 `top_v_score`，hash 用 rerank 前融合分；数字接地检查 `numeric_grounded` |
| `settings.py` | 配置加载：`config.json`（模板）+ `config.local.json`（密钥，gitignore）深度合并，热读 |
| `store.py` | 分块；可配置 embedding（`OpenAICompatEmbeddingFunction` 语义：本机 Ollama bge-m3 / 云端智谱 embedding-3；`LocalHashEmbeddingFunction` 离线词面兜底）；collection 指纹校验；嵌入式 Chroma |
| `retrieve.py` | 向量 / BM25(k1=1.5,b=0.75，倒排统计随语料缓存) 融合 `0.55v+0.45b` / 轻量 rerank `0.55s+0.35cover+0.10phrase`（附 `raw_score` 供阈值判定） |
| `llm.py` | 模型预设解析（`llm.active`）、OpenAI 兼容 HTTP（超时/最大输出可配置，默认 8s/300；预设级 `timeout_seconds` 可覆盖）、CoT 清洗 `strip_thinking`、坏输出自动重试一次后按拒答处理、自述资料不足识别（`+insufficient`）、提示词版本参与缓存键 |
| `sessions.py` | 内存多轮 + 追问线索感知改写 + TTL 淘汰；仅含指代/延续线索时拼接最近 2 问，独立新问题不被历史稀释 |
| `safety.py` | 中英注入正则、越界关键词、PII 脱敏（手机/邮箱/身份证/银行卡） |
| `cache.py` | `sha256(q+mode+rerank)` 磁盘缓存，TTL 默认 600s，坏答案不回放 |
| `pdf_reader.py` | 文字 PDF 抽取（pypdf 优先，失败退回 Tj/TJ 文本算子解析） |
| `eval.py` / `scripts/load_test.py` / `scripts/ops_report.py` | 一键评测 / 压测 / 运维报表 |

<a id="s3"></a>
## 3. 配置（config.json，热加载，无需改代码）

| 键 | 含义 | 默认 |
|---|---|---|
| `retrieval_mode` | `vector` / `hybrid` | `hybrid` |
| `rerank_enabled` | 二段排序开关（拒答阈值不受其影响，始终用 rerank 前分数） | `true` |
| `top_k` / `return_k` | 初筛 / 注入 Prompt 段数 | 8 / 3 |
| `refuse_threshold` | 低置信拒答阈值。**判据随 embedding 变化**：语义 embedding（`ollama`/`zhipu`）比较向量余弦 `top_v_score`，`hash` 比较 rerank 前融合分 | 0.55（语义）/ 0.12（hash） |
| `cache_enabled` / `cache_ttl_seconds` | 缓存开关 / TTL | true / 600 |
| `max_history_turns` | 会话保留轮数 | 4 |
| `embedding.provider` | `ollama`（本机 bge-m3，语义 + 跨语言，零 token 费用）/ `zhipu`（云端 embedding-3）/ `hash`（离线词面兜底）；换后须重跑 ingest | `ollama` |
| `embedding.model` / `embedding.dimensions` / `embedding.base_url` | 向量模型名 / 维度 / 端点（`base_url` 留空则用 `store.DEFAULT_EMBED_BASE_URLS[provider]`） | bge-m3 / 1024 |
| `llm.active` | 当前使用的预设名（`zhipu` / `deepseek`，可自定义新增） | `zhipu` |
| `llm.timeout_seconds` / `llm.max_tokens` | 单次调用超时 / 输出上限（保证最坏情况仍在 10s SLA 内）；预设可用 `timeout_seconds` 单独覆盖 | 8 / 300 |
| `llm.providers.<预设>.base_url / model / api_key` | 各预设的端点、模型、密钥（OpenAI 兼容协议；key 放 config.local.json） | 内置 deepseek / zhipu 两个云端预设 |

`config.json` + `config.local.json` 是唯一配置来源（local 深度合并覆盖模板，密钥只放 local）。`app.py` 每次请求 `load_config()` 热读，改完即生效；`/api/config` 查看当前配置（`api_key` 已掩码）。

答案缓存键 = `sha256(问题 + 检索模式 + rerank + llm.cache_salt())`，salt 含 `provider|model|提示词版本`：换模型或改提示词自动失效旧缓存，模型自述「资料不足」的答复不写缓存。

请求体里的 `retrieval_mode` / `rerank_enabled` 可临时覆盖全局配置。

<a id="s4"></a>
## 4. 关键选型与量化依据（见 reports/ 实测）

- **embedding 选型**：语义 embedding（本机 `bge-m3` 或云端 `embedding-3`）对比 `hash`（离线袋词）的同题评测——三配置 Context Precision 0.842/0.967/0.975 → **1.000/1.000/1.000**（本机 bge-m3 实测；云端 embedding-3 为 0.975/1.000/1.000），跨语言问答与「换说法提问」不再依赖语料对照排版侥幸；复现 `python scripts/embedding_experiment.py` → `reports/embedding_experiment.md`，诊断见 `docs/issue_diagnosis.md` 问题四/问题五。`hash` 保留为离线词面兜底（`embedding.provider` 一键切换）。
- **拒答判据随 embedding 分流**：BM25 融合分经 min-max 归一化后「每题第一名恒为 1.0」，只表达相对排名不表达绝对把握；语义 embedding 下低置信门禁改判向量余弦（`top_v_score`，应答题最低 0.600 / 应拒题最高 0.495 → 阈值 0.55），`hash` 下仍判融合分。修复前 10 道应拒题只有 1 道被置信度拦下，修复后 10/10（详见问题五）。
- **hybrid 默认**：换 bge-m3 后三配置在本评测集上同为 1.000（`reports/eval_report.md` §1），仍默认 hybrid 是取它的**冗余兜底**——BM25 精确词条能兜住条款题（「15 天」「入职满 3 个月」类），这在 hash 时代的差距（vector-only 0.842 vs hybrid 0.967）里已经证明；语义向量一旦换 weaker 模型或语料变大，hybrid 是唯一不掉分的档位。
- **拒答闭环**：注入 / 越界 / 低置信 / 模型自述资料不足 四类拒答统一走 `refused=true` 且不写缓存；`provider` 后缀（`+insufficient` / `+unavailable`）与日志 `llm_error` 字段可区分「模型没接好」与「检索没命中」。低置信阈值始终作用在 rerank **之前**的分数（语义 embedding 用向量余弦 `top_v_score`，`hash` 用融合分 `top_raw_score`），rerank 开关不影响拒答口径。
- **数字接地**：`numeric_grounded` 硬校验答案数字全部来自检索资料，补足词面忠实度抓不住「15 天说成 25 天」的盲区（只标记不拒答，纳入合规分）。
- **规则级注入防护 + 越界词表**：作业演示级，已知变体可绕过；扩展路线见 §6。

<a id="s5"></a>
## 5. 知识库摄入与向量数据库

### 5.1 PDF / 扫描页的两条链路

| 语料 | 链路 | 代码位置 |
|---|---|---|
| 文字型 PDF（`hr_policy_bilingual.pdf`，可复制选中） | `pypdf.PdfReader` 逐页 `extract_text()` → `split_pdf_paragraphs()` 按标题行切段（PDF 抽出的文本无空行） | `pdf_reader.extract_pdf_text`、`ingest.split_pdf_paragraphs` |
| pypdf 不可用 / 抽取为空 | 兜底解析：按 latin-1 读原始字节，正则抓 `(...) Tj` 与 `[...] TJ` 文本绘制算子并反转义 | `pdf_reader._raw_parse` |
| 扫描页 | **不在本项目内跑 OCR**：语料以 OCR 后的文本入库（`.ocr.txt` 或文件名含 `scanned`），切块时打 `metadata.ocr=true`，检索与日志可追踪来源 | `ingest.is_ocr`、`store.chunk_text(ocr=True)` |

也就是说，PDF 的「识别」= 文字层提取（两级），图像 OCR 属上游步骤；换真 OCR 引擎（PaddleOCR / Tesseract）只需产出一个 `.ocr.txt` 放进 `data/`，链路不变。

### 5.2 数据库：嵌入式 Chroma（无独立服务）

- **实例**：`chromadb.PersistentClient(path="chroma_data/")`，进程内调用，不需要 Docker / 服务端。
- **物理布局**：`chroma_data/chroma.sqlite3` 存集合元数据、文档、ID 与 HNSW 索引台账；每个 collection 一个 UUID 目录存 HNSW 二进制段（`data_level0.bin` / `header.bin` / `link_lists.bin`）。
- **集合与距离**：`internal_kb`，`metadata={"hnsw:space": "cosine"}`，相似度取 `1 - cosine distance`。
- **向量来源（可配置，三选一）**：`embedding.provider=ollama`（默认）调本机 Ollama 的 OpenAI 兼容 `/embeddings`，模型 `bge-m3`（1024 维，语义、跨语言，零 token 费用、查询不依赖公网）；`=zhipu` 走云端智谱 `embedding-3`（同级效果，复用同一个智谱 key，无需装 Ollama）；`=hash` 用 `LocalHashEmbeddingFunction`——中文逐字 + 英文单词切 token，每个 token 的 MD5 映射到 384 维的一位（符号 ±1 累加）后 L2 归一化，确定性、离线、零模型下载，作词面兜底。同题对比见 `reports/embedding_experiment.md` 与 `docs/issue_diagnosis.md` 问题四/问题五。
- **索引指纹防脏查**：collection metadata 记录 embedding 指纹（如 `ollama:bge-m3:1024`），`query_vectors` 发现指纹不一致直接报错提示重跑 `ingest.py`，杜绝「换嵌入后拿旧索引算出无意义相似度」。
- **全文检索不放数据库**：BM25(k1=1.5, b=0.75) 由 `retrieve.py` 对 `store.get_all_chunks()`（按 collection 版本缓存）建倒排统计（token 计数/df/文档长度随语料缓存，非每请求重算），因此 hybrid 不引入第二个存储引擎。
- **重建**：`python ingest.py` 走 `store.rebuild_index()`（删集合后全量 add），改 `data/` 后重跑即可。

<a id="s6"></a>
## 6. 已知限制与演进方向

1. Embedding 已可配置切换（`ollama bge-m3` 本地 / `zhipu embedding-3` 云端 / `hash` 词面兜底，`docs/issue_diagnosis.md` 问题四/问题五）；再升级可换 bge-reranker / sentence-transformers 等本地模型——`store.get_embedding_function` 是唯一替换点。
2. 会话可落盘；改写可升级为 LLM 指代消解；生成侧可注入对话摘要。
3. Rerank 可换 cross-encoder / API rerank（`retrieve.rerank_score` 单函数替换）。
4. 注入检测可加分类器二次审核；服务可换 FastAPI + 进程管理。
5. 拒答阈值随 embedding 分布校准（语义 `bge-m3`/`embedding-3`=0.55 判向量余弦；`hash`=0.12 判融合分）；更换 embedding 后须重新校准（校准方法见 `docs/issue_diagnosis.md` 问题五与 `docs/evaluation.md` §2）。
6. 扫描 PDF 的 OCR 在语料准备阶段完成（见 §5.1），服务侧只消费 OCR 文本。
7. 默认 embedding 依赖本机 Ollama 服务在跑（装完 Ollama 后台常驻即可，无 GPU 也能跑 bge-m3）；没有 Ollama 时把 `embedding.provider` 设为 `zhipu`（走云端、复用智谱 key）或 `hash`（纯离线词面），改完重跑 `python ingest.py`。
8. 生成侧只支持云端 OpenAI 兼容端点：本机 `ollama serve` 上 CPU 解码的大模型单请求 30s+，无法满足 90% < 10s 的性能要求（实测见 `docs/issue_diagnosis.md` 问题五），因此不提供本地生成预设。

<a id="s7"></a>
## 7. 模型选型与成本

- **当前实测：`zhipu glm-5.3-flash` + 本机 `bge-m3`**（`llm.active=zhipu`，key 在 `config.local.json`）。当前口径日志窗口（96 请求 / 73 次真实调用，`reports/ops_report.md`）：均值 588.7 token/次，p50 4ms（缓存命中占 1/3）/ p95 4692ms / p99 5726ms，**≤10s 完成率 1.0**，答案平均忠实度 0.9675、数字接地率 1.0、合规率 1.0。8 并发压测 60 请求（`reports/load_test.csv`）：成功率 100%、p50 23ms / p95 4175ms、RPS 7.65。30 题评测全指标达标（`reports/eval_report.md`，检索三配置 1.000/1.000/1.000）。切换到 `deepseek` 只需改 `llm.active`（两把 key 都已配好）。
- **embedding 成本：0**（默认 `ollama bge-m3` 本机推理，无按量计费）。改用云端 `embedding-3` 时计费也极低（45 块语料入库 + 全量评测合计 <¥0.01）。
- **deepseek-flash 对照数据**（升级 embedding 前实测）：78 次调用均值 528.2 token/次，p50 597ms / p95 2068ms；每 1000 次请求 ≈ 14.0 万 token ≈ ¥0.22（输入 ¥1/M、输出 ¥4/M，高峰 2×）。
- 成本口径：`token_usage.total_tokens` 均值 × 1000；缓存命中/拒答请求 0 token。切换模型只改 `llm.active`，重跑 `scripts/ops_report.py` 按新模型重算。窗口内（73 次调用、1/3 缓存命中）折算约 **44.8 万 token / 1000 次请求**；冷启动全命中率为 0 时按 588.7 × 1000 ≈ 58.9 万估算 ≈ ¥2.8（输入 ¥1/M、输出 ¥4/M）。
- **延迟上界保护**：`llm.timeout_seconds=8`（可配置）——单次调用最坏 8s + 一次重试，超时走统一拒答，不会出现「单请求挂 30s 击穿 10s SLA」。
- 权衡：换 7B 级→延迟减半、条款数字转述错误率上升；换 72B 级→质量↑但单实例并发 <5 不达标。
- 提示词约束（`llm.SYSTEM_PROMPT` v3）：只依据资料原文事实、单段纯文本 ≤150 字、末尾标来源、**用与提问相同的语言作答**。对照实验（`scripts/prompt_experiment.py` → `reports/prompt_experiment.md`）显示 Faithfulness / Style Consistency 显著提升，且真实幻觉（编造数字/条款）会被忠实度口径 + 数字接地检查双重捕获。

<a id="s8"></a>
## 8. 交付物清单

| 要求 | 位置 |
|---|---|
| 完整代码与配置 | 本目录（§2 文件表；模型/embedding 预设见 `config.json`，密钥在 `config.local.json`，不入库） |
| 一键评测脚本 | `eval.py`、`scripts/load_test.py`、`scripts/ops_report.py` |
| 评测报告（前后对比） | `reports/eval_report.md`、`reports/eval_metrics.csv`、`reports/ops_report.md`、`reports/load_test.csv`、`reports/prompt_experiment.md`、`reports/threshold_experiment.md`、`reports/embedding_experiment.md` |
| 日志字段字典与样例 | `docs/log_fields.md`、`logs/rag.jsonl` |
| 问题诊断 5 个（含证据与 ≥10% 提升） | `docs/issue_diagnosis.md` |
| 评测方法与指标定义 | `docs/evaluation.md` |
| 双语 PDF / OCR 链路 | `data/hr_policy_bilingual.pdf`、`data/scanned_leave.ocr.txt`、`scripts/make_bilingual_pdf.py`（说明见 §5） |

---

[⬆ 返回顶部](#top) &nbsp;|&nbsp; <a href="README.en.md">Read this in English</a>
