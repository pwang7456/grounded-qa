# 有据 · 内部制度问答（Grounded QA）

<a id="top"></a>
**中文** &nbsp;|&nbsp; <a href="README.en.md">English</a>

对照 take-home（Asst Manager, Backend Developer, AKP）实现的多轮 RAG 问答 + 生成服务：
中英双语知识库（**docx / md / txt / 文字 PDF / 扫描 OCR 页**，四种格式统一翻译成同一种中间结构后切块）、语义 embedding（本机 Ollama `bge-m3`，零 token 成本；可切云端智谱 embedding-3 或离线 hash 兜底）、
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

> 依赖清单：`chromadb`、`pypdf`、`python-docx`、`reportlab`、`rapidocr-onnxruntime`、`pillow`（`python -m pip install -r requirements.txt`）。

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
python scripts\make_structured_docs.py      &REM 生成带 Heading 样式与表格的 docx / md 语料
```

<a id="s2"></a>
## 2. 架构

```
POST /api/ask {q, session_id, retrieval_mode?, rerank_enabled?}
  → app.py(ThreadingHTTPServer :8788) → pipeline.answer_question
      safety(注入/越界→拒答) → cache → sessions(追问线索感知改写) → retrieve(vector|hybrid[+rerank])
      → 低分拒答(语义 embedding 用向量余弦 / hash 用 rerank 前融合分) → llm(DeepSeek / 智谱 GLM，OpenAI 兼容) → 资料不足识别/数字接地/PII 脱敏 → 日志/缓存/会话
数据面：data/*.(docx|md|txt|pdf) → 各格式 reader 翻译成统一 Block(heading|paragraph|table)
        → ingest.py 按扩展名分发（不支持的扩展名显式 [skip] 并说明原因）→ store.chunk_blocks(标题栈+上下文前缀)
        → embedding(ollama bge-m3|zhipu embedding-3|hash) → Chroma(chroma_data/)
```

| 文件 | 职责 |
|---|---|
| `app.py` | HTTP：`/api/ask` `/api/health` `/api/config` + 静态页 |
| `pipeline.py` | 主编排（安全→缓存→检索→生成→日志）；低置信拒答：语义 embedding 用向量余弦 `top_v_score`，hash 用 rerank 前融合分；数字接地检查 `numeric_grounded` |
| `settings.py` | 配置加载：`config.json`（模板）+ `config.local.json`（密钥，gitignore）深度合并，热读 |
| `store.py` | **切块器 `chunk_blocks()`（只认 Block，不认识任何文件格式）**：标题栈组装 + 就近标题前缀（预算 60 字）+ >400 字按句末切（50 字重叠）+ 表格块不跨块切；`CHUNKER_VERSION` 参与缓存 salt；可配置 embedding（`OpenAICompatEmbeddingFunction` 语义：本机 Ollama bge-m3 / 云端智谱 embedding-3；`LocalHashEmbeddingFunction` 离线词面兜底）；collection 指纹校验；嵌入式 Chroma |
| `blocks.py` | **中间结构契约**：`{"type": "heading"\|"paragraph"\|"table", "level": 1~6, "text": ...}` + `table_from_rows()` 把表格展平成 `列名:值 \| 列名:值` 键值行（每行自带列名，命中后不必回看表头） |
| `ingest.py` | 按扩展名分发到各 reader，产出 `(chunks, per_file, skipped, failed)`；不支持的格式打印 `[skip] unsupported: 文件（原因）`，抽取失败 `[fail]` 并 `exit 1`，绝不静默少一份资料 |
| `docx_reader.py` | docx → Block：遍历 `document.element.body` 子元素保序（`doc.paragraphs` 与 `doc.tables` 是两个独立列表，直接用会丢交错顺序），标题级别取自样式名 |
| `md_reader.py` | md → Block：行状态机（ATX 标题 / 围栏代码 / 管道表格 / 空行分段），GFM `|---|` 分隔行只跳过不触发 flush，零新依赖 |
| `text_reader.py` | txt / pdf → Block：pypdf 抽取后按标题行切段；`_is_heading` 在此**降级为无结构来源的专用兜底**（不再是切块逻辑的一部分），补 `SECTION_MARK_RE` 识别长双语章节标题 |
| `retrieve.py` | 向量 / BM25(k1=1.5,b=0.75，倒排统计随语料缓存) 融合 `0.55v+0.45b` / 轻量 rerank `0.55s+0.35cover+0.10phrase`（cover/phrase 剥掉 `prefix_len` 前缀只在正文上算；附 `raw_score` 供阈值判定） |
| `llm.py` | 模型预设解析（`llm.active`）、OpenAI 兼容 HTTP（超时/最大输出可配置，默认 8s/400；预设级 `timeout_seconds` / `reasoning_effort` 可覆盖——智谱 glm-5.x 始终思考，`low` 把推理 token 从 300+ 压到 0）、CoT 清洗 `strip_thinking`、`finish_reason=length` 截断识别、坏输出与瞬时故障（超时/网络/5xx）各自动重试一次后按拒答处理、自述资料不足识别（`+insufficient`）、提示词版本参与缓存键 |
| `sessions.py` | 内存多轮 + 追问线索感知改写 + TTL 淘汰；仅含指代/延续线索时拼接最近 2 问，独立新问题不被历史稀释 |
| `safety.py` | 中英注入正则、越界关键词、PII 脱敏（手机/邮箱/身份证/银行卡） |
| `cache.py` | `sha256(问题+检索模式+rerank+模型/提示词版本+CHUNKER_VERSION)` 磁盘缓存，TTL 默认 600s，坏答案不回放 |
| `pdf_reader.py` | PDF 抽取：文字型走 pypdf 搬运字符；无文字层判定为扫描件，对页面嵌入位图跑 RapidOCR（显式依赖，失败即报错，不静默兜底）；返回 `(text, used_ocr)` 供入库打 `metadata.ocr=true` |
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

答案缓存键 = `sha256(问题 + 检索模式 + rerank + llm.cache_salt() + "chunk"+store.CHUNKER_VERSION)`，salt 含 `provider|model|提示词版本`，切块版本单独参与：换模型、改提示词**或改切块**都会自动失效旧缓存，不会拿旧切块的答案冒充新效果。模型自述「资料不足」的答复不写缓存。

请求体里的 `retrieval_mode` / `rerank_enabled` 可临时覆盖全局配置。

<a id="s4"></a>
## 4. 关键选型与量化依据（见 reports/ 实测）

- **embedding 选型**：语义 embedding（本机 `bge-m3` 或云端 `embedding-3`）对比 `hash`（离线袋词）的同题评测——三配置 Context Precision 0.842/0.967/0.975 → **1.000/1.000/1.000**（本机 bge-m3 实测；云端 embedding-3 为 0.975/1.000/1.000），跨语言问答与「换说法提问」不再依赖语料对照排版侥幸；复现 `python scripts/embedding_experiment.py` → `reports/embedding_experiment.md`，诊断见 `docs/issue_diagnosis.md` 问题四/问题五。`hash` 保留为离线词面兜底（`embedding.provider` 一键切换）。
- **拒答判据随 embedding 分流**：BM25 融合分经 min-max 归一化后「每题第一名恒为 1.0」，只表达相对排名不表达绝对把握；语义 embedding 下低置信门禁改判向量余弦（`top_v_score`，应答题最低 0.600 / 应拒题最高 0.495 → 阈值 0.55），`hash` 下仍判融合分。修复前 10 道应拒题只有 1 道被置信度拦下，修复后 10/10（详见问题五）。
- **hybrid 默认**：49 题扩展评测集（含 docx/md 真实语料、题目与语料交叉独立）上，三配置 CP 0.892 / 0.892 / 0.896（`reports/eval_report.md` §1）——hybrid 与 rerank 相对 vector-only 的优势从 hash 时代的显著（0.842 vs 0.967）收敛到 ±0.005，仍默认 hybrid+rerank 取的是**鲁棒性冗余**：BM25 精确词条兜底条款题（「15 天」「入职满 3 个月」类），语义向量一旦换 weaker 模型或语料变大，hybrid 是唯一不掉分的档位。**rerank 的词面覆盖只在正文上算**（`prefix_len` 剥掉标题路径前缀）——前缀词若计入 cover，同章节块会被系统性抬高、排序偏向「标题像」而非「正文像」（修复前实测 CP 0.883，修复后 0.896）。

- **拒答闭环**：注入 / 越界 / 低置信 / 模型自述资料不足 四类拒答统一走 `refused=true` 且不写缓存；`provider` 后缀（`+insufficient` / `+unavailable`）与日志 `llm_error` 字段可区分「模型没接好」与「检索没命中」。低置信阈值始终作用在 rerank **之前**的分数（语义 embedding 用向量余弦 `top_v_score`，`hash` 用融合分 `top_raw_score`），rerank 开关不影响拒答口径。
- **数字接地**：`numeric_grounded` 硬校验答案数字全部来自检索资料，补足词面忠实度抓不住「15 天说成 25 天」的盲区（只标记不拒答，纳入合规分）。
- **规则级注入防护 + 越界词表**：作业演示级，已知变体可绕过；扩展路线见 §6。

<a id="s5"></a>
## 5. 知识库摄入与向量数据库

### 5.1 统一中间结构 Block：新增格式 = 新增一个「翻译器」

真实制度文档的载体是 Word 和 Markdown，不是 txt。如果让切块器直接面对格式，每加一种格式就要改一次切块器、重跑一次全量评测。所以链路上插了一层契约：

```
docx_reader / md_reader / text_reader(txt) / text_reader(pdf→pypdf 或 RapidOCR)
        ↓ 全部返回 List[Block]，Block = {"type": "heading"|"paragraph"|"table", "level": 1~6, "text": "..."}
store.chunk_blocks()   ← 只认 Block，不认识任何文件格式扩展名
        ↓ chunk = 就近标题前缀 + 正文原文，metadata 带 heading_path / block_type / ocr / language
```

| 格式 | 结构信息怎么进 Block | 已知丢失（不藏着） |
|---|---|---|
| `.docx` | 遍历 `document.element.body` 子元素保序；标题级别取样式名 `Heading N / 标题 N`；表格每行展平成 `列名:值 \| 列名:值` | **文本框（TextBox）与图片内文字读不到**；合并单元格会按跨度重复读出同一文本（表现为重复列名）；`.doc` 旧二进制格式不支持，入库时显式提示「请先另存为 .docx」 |
| `.md` | ATX 标题 `#{1,6}` → level；围栏代码整块作一个段落；管道表格 → 表格 Block；空行只作段落分隔符，不再是 chunk 边界 | 不解析 HTML 标签、YAML front-matter；无序列表整组合并成一个段落 Block（按项切块会让每项丢失上下文）；引用/斜体等行内样式仅保留原字符 |
| `.txt` | 空行分段；短行按启发式认作标题 | 无任何真实样式信息，标题只能猜（见下） |
| `.pdf` | 文字型：pypdf 抽字符 → 按标题行切段；扫描型：RapidOCR 结果同样走这条 | PDF 里只有坐标和字号，没有语义，标题层级必然是推断的；多栏排版可能串栏 |

`_is_heading`（行长 + 标点猜标题）在这层改造里被**降级**为「无结构来源的专用兜底」，只服务 txt 与 pypdf——docx/md 带真实样式，不该再走猜测。补了 `SECTION_MARK_RE` 认 `第三章 婚假与产假 Chapter 3 Marriage and Maternity Leave` 这类长双语章节标题（旧实现有 40 字上限，天然漏）。切块效果与由此暴露的三个新缺陷的量化归因见 `docs/issue_diagnosis.md` 问题六。

切块规则（`store.chunk_blocks`，`CHUNKER_VERSION=v2`）：标题按 level 弹栈、容忍跳级；每个 chunk 前挂**就近标题**（预算 60 字，全文档共用的 H1 不进每个 chunk，否则它的词会污染每一块的 BM25 词袋），完整路径写进 `metadata.heading_path`；>400 字按句末边界切、留 50 字重叠；**表格 Block 不跨块切**（拆开后单元格脱离列名，表格就退化成噪声）；正文原文一字不改。

### 5.2 PDF / 扫描 PDF 的两条链路

| 语料 | 链路 | 代码位置 |
|---|---|---|
| 文字型 PDF（`hr_policy_bilingual.pdf`，可复制选中） | `pypdf.PdfReader` 逐页 `extract_text()` → `split_pdf_paragraphs()` 按标题行切段（中英混排标题与纯中文短标题均可识别）→ 段落 Block | `pdf_reader.extract_pdf_text`、`text_reader.split_pdf_paragraphs` |
| 扫描型 PDF（`scanned_leave.pdf`，整页位图、无文字层） | pypdf 抽出文字为空 → 判定扫描件 → 对每页嵌入位图跑 **RapidOCR**（PaddleOCR 模型的 ONNX 版，纯 pip、离线、Apache-2.0），单页 CPU 约 4~5s（仅发生在入库，不在问答链路上） | `pdf_reader.extract_pdf_text`、`scripts/make_scanned_pdf.py` |

- `scanned_leave.pdf` 由 `scripts/make_scanned_pdf.py` 生成：文字渲染成纸面图像 + 歪斜/噪点/模糊，是真正的图片型 PDF（pypdf 读出为空，可用 `python -c` 自验）。
- `metadata.ocr` 标记来自**真实抽取路径**（`pdf_reader.extract_pdf_text` 返回的 `used_ocr`），不做文件名猜测；检索命中与日志可据此追溯「该答案依据来自扫描件 OCR」。
- 依赖缺失（无 rapidocr）时显式报错并提示安装，**不做静默兜底**——与 LLM 链路「不静默降级」同一原则。
- 换 OCR 引擎（PaddleOCR / Tesseract / Docling）只需替换 `pdf_reader.py` 内的 OCR 调用点。

### 5.3 数据库：嵌入式 Chroma（无独立服务）

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
6. 扫描 PDF 的 OCR 在入库时自动完成（`pdf_reader.py` 内 RapidOCR，CPU 单页 4~5s，仅离线阶段）；问答链路消费的是 OCR 后文本，不新增延迟。
7. 默认 embedding 依赖本机 Ollama 服务在跑（装完 Ollama 后台常驻即可，无 GPU 也能跑 bge-m3）；没有 Ollama 时把 `embedding.provider` 设为 `zhipu`（走云端、复用智谱 key）或 `hash`（纯离线词面），改完重跑 `python ingest.py`。
8. 生成侧只支持云端 OpenAI 兼容端点：本机 `ollama serve` 上 CPU 解码的大模型单请求 30s+，无法满足 90% < 10s 的性能要求（实测见 `docs/issue_diagnosis.md` 问题五），因此不提供本地生成预设。
9. 格式 reader 覆盖 docx / md / txt / pdf 四类；`.pptx` / `.xlsx` / 图片 / `.doc` 未接入，但入库时会显式 `[skip] unsupported: 文件名（原因）` 并计入报告的 `skipped_unsupported`，不会静默少一份资料。新增格式只需实现一个返回 `List[Block]` 的 reader 并注册进 `ingest.READERS`，切块器与下游零改动。
10. 标题前缀是双刃剑：它让 chunk 自带上下文，也把标题词注入兄弟块的 BM25 词袋，实测把 `q06 产假` 挤下 top1（`docs/issue_diagnosis.md` 问题六）。同类未修的还有 BM25 min-max 基准随语料漂移导致的 `q08` 误序、以及跨语言查询下 BM25 这条腿反而压低正确块（英文题 vector-only 全面优于 hybrid）。三条均已量化并给出消融证据，按「先诊断」口径暂不动代码。

<a id="s7"></a>
## 7. 模型选型与成本

- **当前实测：`zhipu glm-5.3-flash` + 本机 `bge-m3`**（`llm.active=zhipu`，key 在 `config.local.json`）。当前口径日志窗口（96 请求 / 73 次真实调用，`reports/ops_report.md`）：均值 588.7 token/次，p50 4ms（缓存命中占 1/3）/ p95 4692ms / p99 5726ms，**≤10s 完成率 1.0**，答案平均忠实度 0.9675、数字接地率 1.0、合规率 1.0。8 并发压测 60 请求（`reports/load_test.csv`）：成功率 100%、p50 23ms / p95 4175ms、RPS 7.65。49 题评测全指标达标（`reports/eval_report.md`：Context Precision 0.892 / 0.892 / 0.883 三配置，Faithfulness 0.929，Compliance 0.987，Refusal 1.000，Style 0.973；改造前 30 题基线见 `reports/baseline_before_format.md`，逐题归因见 `docs/issue_diagnosis.md` 问题六）。切换到 `deepseek` 只需改 `llm.active`（两把 key 都已配好）。
- **embedding 成本：0**（默认 `ollama bge-m3` 本机推理，无按量计费）。改用云端 `embedding-3` 时计费也极低（57 块语料入库 + 全量评测合计 <¥0.01）。
- **deepseek-flash 对照数据**（升级 embedding 前实测）：78 次调用均值 528.2 token/次，p50 597ms / p95 2068ms；每 1000 次请求 ≈ 14.0 万 token ≈ ¥0.22（输入 ¥1/M、输出 ¥4/M，高峰 2×）。
- 成本口径：`token_usage.total_tokens` 均值 × 1000；缓存命中/拒答请求 0 token。切换模型只改 `llm.active`，重跑 `scripts/ops_report.py` 按新模型重算。窗口内（73 次调用、1/3 缓存命中）折算约 **44.8 万 token / 1000 次请求**；冷启动全命中率为 0 时按 588.7 × 1000 ≈ 58.9 万估算 ≈ ¥2.8（输入 ¥1/M、输出 ¥4/M）。
- **延迟上界保护**：`llm.timeout_seconds=8`（可配置）——瞬时故障（超时/网络/5xx）与坏输出各自动重试一次，仍失败走统一拒答；`reasoning_effort=low` 关闭 glm-5.x 的隐藏推理后，单请求 p95 从 ~4.7s 降至 ~2.5s，90% <10s SLA 余量显著扩大。
- 权衡：换 7B 级→延迟减半、条款数字转述错误率上升；换 72B 级→质量↑但单实例并发 <5 不达标。
- 提示词约束（`llm.SYSTEM_PROMPT` v5）：只依据资料原文事实、单段纯文本 ≤150 字、末尾标来源、**回答语言与提问一致（英文提问用 English）**。对照实验（`scripts/prompt_experiment.py` → `reports/prompt_experiment.md`）显示 Faithfulness / Style Consistency 显著提升，且真实幻觉（编造数字/条款）会被忠实度口径 + 数字接地检查双重捕获。

<a id="s8"></a>
## 8. 交付物清单

| 要求 | 位置 |
|---|---|
| 完整代码与配置 | 本目录（§2 文件表；模型/embedding 预设见 `config.json`，密钥在 `config.local.json`，不入库） |
| 一键评测脚本 | `eval.py`、`scripts/load_test.py`、`scripts/ops_report.py` |
| 评测报告（前后对比） | `reports/eval_report.md`、`reports/eval_metrics.csv`、`reports/baseline_before_format.md`（多格式改造前基线）、`reports/ops_report.md`、`reports/load_test.csv`、`reports/prompt_experiment.md`、`reports/threshold_experiment.md`、`reports/embedding_experiment.md` |
| 日志字段字典与样例 | `docs/log_fields.md`、`logs/rag.jsonl` |
| 问题诊断 6 个（含证据与量化归因） | `docs/issue_diagnosis.md` |
| 评测方法与指标定义 | `docs/evaluation.md` |
| 双语 PDF / 扫描 PDF（真 OCR）链路 | `data/hr_policy_bilingual.pdf`、`data/scanned_leave.pdf`（图片型扫描件）、`scripts/make_bilingual_pdf.py`、`scripts/make_scanned_pdf.py`（说明见 §5.2） |
| Word / Markdown 真实结构语料 | `data/leave_management_policy.docx`（Heading 样式层级 + 两张三列表格 + 超长条款）、`data/remote_work_policy.md`（`#` 层级 + GFM 表格 + 围栏代码）、`scripts/make_structured_docs.py` 可复生成（说明见 §5.1） |

---

[⬆ 返回顶部](#top) &nbsp;|&nbsp; <a href="README.en.md">Read this in English</a>
