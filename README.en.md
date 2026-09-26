# Grounded QA — Internal Policy Assistant（有据 · 内部制度问答）

<a id="top"></a>
<a href="README.md">中文</a> &nbsp;|&nbsp; **English**

A multi-turn RAG QA + generative service built against the AKP take-home brief
(Asst Manager, Backend Developer): bilingual (CN/EN) knowledge base including a text PDF and a
scanned/OCR page, semantic embeddings (local Ollama `bge-m3`, zero token cost; switchable to Zhipu
embedding-3 or an offline hash fallback),
configurable retrieval (vector / hybrid / +rerank — switched by config, not code),
three refusal classes (injection / out-of-scope / low confidence) plus model-declared
"insufficient context" detection, numeric-grounding checks, PII redaction, answer caching,
structured logs, one-click evaluation and load test, and an ops report.

## Contents

| Section | 中文 | English |
|---|---|---|
| 1 Quick Start | [§1](README.md#s1) | [§1](#s1) |
| 2 Architecture | [§2](README.md#s2) | [§2](#s2) |
| 3 Configuration | [§3](README.md#s3) | [§3](#s3) |
| 4 Design rationale | [§4](README.md#s4) | [§4](#s4) |
| 5 Ingestion & vector store | [§5](README.md#s5) | [§5](#s5) |
| 6 Limitations | [§6](README.md#s6) | [§6](#s6) |
| 7 Model choice & cost | [§7](README.md#s7) | [§7](#s7) |
| 8 Deliverables | [§8](README.md#s8) | [§8](#s8) |

<a id="s1"></a>
## 1. Quick Start (Windows)

Dependencies are already installed for the global `python`. After the first ingest, either
double-click `app.py` or run it from a terminal:

```bat
cd /d D:\myspace\grounded-qa
python ingest.py      &REM build the index (already built; re-run after editing data/)
python app.py         &REM serve at http://127.0.0.1:8788, Ctrl+C to stop
```

Open `http://127.0.0.1:8788` in a browser — the page pins one `session_id`, so follow-up questions
work immediately. The page offers:

- **Newest answer pinned on top**, each card carrying the answer plus retrieved evidence (score / cosine
  / weight bar) and metric badges (provider, retrieval mode, latency, cache hit, faithfulness, tokens);
- **One-click demo buttons** reproducing every pipeline branch: normal answer / expense / anaphora follow-up
  / English / out-of-scope refusal / prompt-injection refusal / low-confidence refusal;
- **Status chips** in the header showing the live `llm.active` model, embedding signature and chunk count.
  "新会话" (new session) mints a fresh `session_id`, dropping multi-turn context.

> Requirements: `chromadb`, `pypdf`, `reportlab`, `rapidocr-onnxruntime`, `pillow` (`python -m pip install -r requirements.txt`).

### LLM & embedding configuration (config.json + config.local.json, layered)

Configuration has two layers, **local overrides the template** (deep merge):

- **`config.json`**: template plus all non-secret settings (retrieval knobs, provider endpoints /
  model names, embedding choice). **Keys are empty — safe to commit or share.**
- **`config.local.json`**: secrets only (`api_key` etc.). **Listed in `.gitignore`, never committed.**
  Same shape as config.json; matching keys win:

```json
{ "llm": { "providers": { "zhipu": { "api_key": "your-key" } } } }
```

- **Switch models**: set `llm.active` to `"zhipu"` (default) / `"deepseek"` (add presets with the same shape — no code change). Generation always runs on a cloud OpenAI-compatible endpoint.
- **Switch embeddings**: set `embedding.provider` to `"ollama"` (local `bge-m3` — semantic and cross-lingual, zero token cost, works without internet; **this is what `config.json` ships with**),
  `"zhipu"` (cloud embedding-3, same quality, reuses the Zhipu key) or `"hash"` (deterministic offline
  bag-of-words fallback); **re-run `python ingest.py` after switching** (an index
  fingerprint check refuses stale indexes instead of returning meaningless similarity scores).
- Retrieval knobs (`retrieval_mode` / `rerank_enabled` / `top_k` / `refuse_threshold`, …) are
  hot-reloaded per request; changing LLM connection settings needs an `app.py` restart.
- On endpoint failure or a missing key the service returns a uniform refusal
  (`provider=*+unavailable` / `*+insufficient`) and records the reason in the `llm_error` log field —
  no silent degradation, no partial answers.
- `/api/config` masks every `api_key` as `***`; **do not copy `config.local.json` into submissions**.

### Local embedding model (optional, fully offline, zero tokens)

The embedding model runs on the local Ollama server (semantic + cross-lingual, no per-call billing):

```bat
ollama pull bge-m3     &REM 1.2GB, embedding model
python ingest.py       &REM rebuild the index with the configured embedding.provider
```

> There is deliberately **no local generation preset**: `qwen3:30b-a3b` on this machine ran at
> **100% CPU** (`ollama ps`: 19GB weights), 32–33s per request — 3× the 10s p95 target — with
> Faithfulness down to 0.458–0.607 (evidence in `docs/issue_diagnosis.md` issue 5). Without Ollama
> installed, point `embedding.provider` at `"zhipu"` (cloud, reuses the same key) or `"hash"`
> (pure offline fallback) and re-run `python ingest.py`.

### Evaluation / load test / reports (one click)

```bat
python eval.py                              &REM -> reports/eval_report.md + eval_metrics.csv
python scripts\load_test.py 60 8            &REM needs app.py running -> reports/load_test.csv
python scripts\ops_report.py 96             &REM aggregate logs (optional arg = last N events) -> reports/ops_report.{csv,md}
python scripts\smoke_test.py                &REM smoke test (8 in-process scenarios)
python scripts\prompt_experiment.py         &REM prompt A/B -> reports/prompt_experiment.md
python scripts\threshold_experiment.py      &REM refusal-threshold A/B -> reports/threshold_experiment.md
python scripts\embedding_experiment.py      &REM embedding A/B -> reports/embedding_experiment.md
```

<a id="s2"></a>
## 2. Architecture

```
POST /api/ask {q, session_id, retrieval_mode?, rerank_enabled?}
  -> app.py (ThreadingHTTPServer :8788) -> pipeline.answer_question
      safety (injection / out-of-scope -> refuse) -> cache -> sessions (followup-cue-aware rewrite)
      -> retrieve (vector | hybrid [+rerank]) -> low-score refusal (vector cosine on semantic embeddings / pre-rerank fusion score on hash)
      -> llm (DeepSeek / Zhipu GLM, OpenAI-compatible) -> insufficient-context detection / numeric grounding / PII redaction
      -> logging, caching, session update
Data plane: data/*.(txt|pdf) -> ingest.py + pdf_reader.py (text PDF via pypdf; scanned PDF auto-RapidOCR) -> store (chunking + ollama bge-m3 | zhipu embedding-3 | hash) -> Chroma (chroma_data/)
```

| File | Responsibility |
|---|---|
| `app.py` | HTTP: `/api/ask` `/api/health` `/api/config` + static page |
| `pipeline.py` | Main orchestration (safety → cache → retrieval → generation → logging); low-confidence refusal: `top_v_score` (vector cosine) on semantic embeddings, pre-rerank fusion score on `hash`; numeric-grounding check `numeric_grounded` |
| `settings.py` | Config loading: `config.json` (template) + `config.local.json` (secrets, gitignored), deep-merged, hot-read |
| `store.py` | Chunking; pluggable embeddings (`OpenAICompatEmbeddingFunction` semantic — local Ollama bge-m3 / cloud Zhipu embedding-3; `LocalHashEmbeddingFunction` offline lexical fallback); collection fingerprint check; embedded Chroma |
| `retrieve.py` | Vector / BM25(k1=1.5,b=0.75, inverted stats cached per corpus) fusion `0.55v+0.45b` / light rerank `0.55s+0.35cover+0.10phrase` (keeps `raw_score` for threshold gating) |
| `llm.py` | Preset resolution (`llm.active`), OpenAI-compatible HTTP (timeout/max-tokens configurable, default 8s/400; a preset may override `timeout_seconds` / `reasoning_effort` — Zhipu glm-5.x always thinks, `low` cuts reasoning tokens from 300+ to 0), CoT stripping `strip_thinking`, `finish_reason=length` truncation detection, one auto-retry each for unusable output and transient failures (timeout/network/5xx), then refusal; insufficient-context detection (`+insufficient`); prompt version in the cache key |
| `sessions.py` | In-memory multi-turn + cue-gated rewrite + TTL eviction (only concatenates the last 2 questions when anaphora/continuation cues exist, so independent questions are not diluted) |
| `safety.py` | CN/EN injection regexes, out-of-scope keywords, PII redaction (phone/email/ID/bank card) |
| `cache.py` | `sha256(q+mode+rerank)` disk cache, TTL 600s by default, bad answers never replayed |
| `pdf_reader.py` | PDF extraction: text PDFs via pypdf; no text layer → scanned → RapidOCR on the embedded bitmaps (explicit dependency, errors loudly, no silent fallback); returns `(text, used_ocr)` for `metadata.ocr=true` |
| `eval.py` / `scripts/load_test.py` / `scripts/ops_report.py` | One-click evaluation / load test / ops report |

<a id="s3"></a>
## 3. Configuration (config.json, hot-reloaded, no code change)

| Key | Meaning | Default |
|---|---|---|
| `retrieval_mode` | `vector` / `hybrid` | `hybrid` |
| `rerank_enabled` | Second-stage reranking switch (the refusal threshold always uses the pre-rerank score, so this switch cannot weaken it) | `true` |
| `top_k` / `return_k` | Candidate pool / chunks injected into the prompt | 8 / 3 |
| `refuse_threshold` | Low-confidence refusal threshold. **The criterion follows the embedding type**: semantic embeddings (`ollama`/`zhipu`) compare the vector cosine `top_v_score`; `hash` compares the pre-rerank fusion score | 0.55 (semantic) / 0.12 (hash) |
| `cache_enabled` / `cache_ttl_seconds` | Cache switch / TTL | true / 600 |
| `max_history_turns` | Turns kept per session | 4 |
| `embedding.provider` | `ollama` (local bge-m3, semantic + cross-lingual, zero token cost) / `zhipu` (cloud embedding-3) / `hash` (offline lexical fallback); re-run ingest after switching | `ollama` |
| `embedding.model` / `embedding.dimensions` / `embedding.base_url` | Embedding model name / dimensions / endpoint (empty `base_url` falls back to `store.DEFAULT_EMBED_BASE_URLS[provider]`) | bge-m3 / 1024 |
| `llm.active` | Active preset name (`zhipu` / `deepseek`, user-extensible) | `zhipu` |
| `llm.timeout_seconds` / `llm.max_tokens` | Per-call timeout / output cap (keeps the worst case inside the 10s SLA) | 8 / 300 |
| `llm.providers.<preset>.base_url / model / api_key` | Per-preset endpoint, model and key (OpenAI-compatible; keys live in config.local.json) | two built-in presets: deepseek / zhipu |

`config.json` + `config.local.json` are the only configuration sources (local deep-merges over the
template; secrets live only in local). `app.py` calls `load_config()` per request, so edits apply
immediately; `/api/config` shows the live config with `api_key` masked.

Answer cache key = `sha256(question + retrieval mode + rerank + llm.cache_salt())`, where the salt
covers `provider|model|prompt version`: switching models or editing the prompt invalidates stale
cache automatically, and answers where the model declares insufficient context are never cached.

`retrieval_mode` / `rerank_enabled` in the request body temporarily override global config.

<a id="s4"></a>
## 4. Key choices with quantitative evidence (see reports/)

- **Embedding choice**: same-question evaluation of a semantic embedding (`bge-m3` locally / `embedding-3`
  in the cloud) vs `hash` (offline bag-of-words) — three-config Context Precision went
  0.842/0.967/0.975 → **1.000/1.000/1.000** with local bge-m3 (0.975/1.000/1.000 with embedding-3), and
  cross-language questions are now answered in the question's language. Reproduce with
  `python scripts\embedding_experiment.py` → `reports/embedding_experiment.md`; diagnoses in
  `docs/issue_diagnosis.md` issues 4 and 5. `hash` is kept as the deterministic offline fallback (one config switch).
- **The refusal gate follows the embedding**: BM25 min-max normalisation makes the top fused score of
  *every* query 1.0, so the fused number expresses rank, not confidence. With semantic embeddings the
  low-confidence gate now reads the vector cosine (`top_v_score`; answerable minimum 0.600 vs
  refuse-worthy maximum 0.495 → threshold 0.55), `hash` keeps the fusion score. Before the fix only
  1 of 10 refuse-worthy questions was caught by confidence; afterwards 10 of 10 (issue 5).
- **hybrid by default**: with bge-m3 all three configs now score 1.000 on this evaluation set
  (`reports/eval_report.md` §1); hybrid stays the default for redundancy — BM25 exact-term recall
  backstops clause questions ("15 days", "after 3 months of service"), which is exactly what the
  hash-era gap proved (vector-only 0.842 vs hybrid 0.967). If the embedding gets weaker or the corpus
  grows, hybrid is the config that does not fall over.
- **Refusal loop**: all four refusal classes (injection / out-of-scope / low confidence / model-declared
  insufficiency) return `refused=true` and skip the cache; the `provider` suffix
  (`+insufficient` / `+unavailable`) plus the `llm_error` log field distinguish "model not connected"
  from "nothing retrieved". The low-confidence threshold always applies to a **pre-rerank** score — the
  vector cosine `top_v_score` for semantic embeddings, the fusion score `top_raw_score` for `hash` —
  so toggling rerank never changes the refusal semantics.
- **Numeric grounding**: `numeric_grounded` hard-checks that every number in the answer appears in the
  retrieved material, closing the lexical-faithfulness blind spot ("15 days" rewritten as "25 days")
  — flagged in logs and counted into Answer Compliance, not used to refuse.
- **Rule-based injection defense + out-of-scope lexicon**: assignment-demo grade; known variants can
  bypass it. Extension paths in §6.

<a id="s5"></a>
## 5. Knowledge-base ingestion and the vector store

### 5.1 Two paths: text PDF vs scanned PDF

| Corpus | Path | Code |
|---|---|---|
| Text PDF (`hr_policy_bilingual.pdf`, selectable text) | `pypdf.PdfReader` → per-page `extract_text()`, then `split_pdf_paragraphs()` breaks sections on heading lines (both CN/EN-mixed and pure-Chinese short headings are recognized) | `pdf_reader.extract_pdf_text`, `ingest.split_pdf_paragraphs` |
| Scanned PDF (`scanned_leave.pdf`, full-page bitmap, no text layer) | pypdf extracts nothing → classified as scanned → **RapidOCR** runs on each page's embedded bitmap (ONNX build of PaddleOCR models: pure pip, offline, Apache-2.0), ~4–5s per page on CPU — ingest-time only, never on the QA path | `pdf_reader.extract_pdf_text`, `scripts/make_scanned_pdf.py` |

- `scanned_leave.pdf` is generated by `scripts/make_scanned_pdf.py`: text rendered onto a paper-like
  image with skew/noise/blur — a genuine image-only PDF (pypdf extracts `""` from it; easy to verify).
- The `metadata.ocr` flag comes from the **real extraction path** (the `used_ocr` returned by
  `pdf_reader.extract_pdf_text`), not filename guessing; retrieval hits and logs can trace
  "this answer is grounded in OCR'd scanned material".
- A missing OCR dependency raises an explicit error with install instructions — **no silent
  fallback**, the same principle as the LLM path's "no silent degradation".
- Swapping OCR engines (PaddleOCR / Tesseract / Docling) only touches the OCR call site in
  `pdf_reader.py`.

### 5.2 Database: embedded Chroma (no separate server)

- **Instance**: `chromadb.PersistentClient(path="chroma_data/")`, called in-process — no Docker, no DB service.
- **On disk**: `chroma_data/chroma.sqlite3` holds collection metadata, documents, ids and the HNSW
  index ledger; each collection gets a UUID directory with HNSW binary segments
  (`data_level0.bin` / `header.bin` / `link_lists.bin`).
- **Collection and distance**: `internal_kb` with `metadata={"hnsw:space": "cosine"}`; similarity is `1 - cosine distance`.
- **Where vectors come from (configurable, three options)**: `embedding.provider=ollama` (default) calls
  the local Ollama OpenAI-compatible `/embeddings` endpoint with `bge-m3` (1024-dim, semantic,
  cross-lingual, zero token cost, no public network needed at query time); `=zhipu` calls cloud Zhipu
  `embedding-3` (same quality tier, reuses the Zhipu key, no Ollama install); `=hash` uses
  `LocalHashEmbeddingFunction` — per-CJK-character plus per-latin-word tokens, each token's MD5
  selecting one of 384 dimensions (signed ±1 accumulation), L2-normalised. Deterministic, offline,
  zero model download; kept as the lexical fallback. Head-to-head numbers in
  `reports/embedding_experiment.md` and `docs/issue_diagnosis.md` issues 4 and 5.
- **Index fingerprint guard**: the collection metadata records the embedding signature
  (e.g. `ollama:bge-m3:1024`); `query_vectors` raises and asks for `python ingest.py` on mismatch,
  so a stale index can never produce meaningless similarity scores after an embedding swap.
- **Full-text search lives outside the database**: BM25(k1=1.5, b=0.75) is built by
  `retrieve.py` over `store.get_all_chunks()` (inverted statistics — token counts, df, doc lengths —
  cached per corpus version, not recomputed per request), so hybrid needs no second storage engine.
- **Rebuild**: `python ingest.py` calls `store.rebuild_index()` (delete collection, then bulk add) — rerun after editing `data/`.

<a id="s6"></a>
## 6. Known limitations and evolution paths

1. Embeddings are now switchable (`ollama bge-m3` local / `zhipu embedding-3` cloud / `hash` lexical
   fallback; `docs/issue_diagnosis.md` issues 4 and 5); the next step would be a stronger local model
   such as bge-reranker or a sentence-transformers encoder — `store.get_embedding_function` is the
   single swap point.
2. Sessions can be persisted; query rewrite can become LLM coreference resolution; a conversation
   summary can be injected into generation.
3. Reranking can move to a cross-encoder or an API reranker (single-function swap in `retrieve.rerank_score`).
4. Injection detection can add a classifier second pass; the server can move to FastAPI + process management.
5. The refusal threshold is calibrated per embedding distribution (semantic `bge-m3`/`embedding-3` =
   0.55 on the vector cosine; `hash` = 0.12 on the fusion score); recalibrate after any embedding swap
   (method in `docs/issue_diagnosis.md` issue 5 and `docs/evaluation.md` §2).
6. OCR for scanned PDFs runs automatically at ingest time (`pdf_reader.py`, RapidOCR, ~4–5s per page on CPU, offline stage only); the QA path consumes the OCR'd text with no added latency.
7. The default embedding needs the local Ollama server running (installed as a background service on
   Windows; bge-m3 runs fine without a GPU). Without Ollama, point `embedding.provider` at `zhipu`
   (cloud, reuses the Zhipu key) or `hash` (fully offline) and re-run `python ingest.py`.
8. Generation only supports cloud OpenAI-compatible endpoints: a CPU-only local model takes 30s+ per
   request and cannot meet the 90%-under-10s requirement (measurement in
   `docs/issue_diagnosis.md` issue 5), so no local generation preset is offered.

<a id="s7"></a>
## 7. Model selection and cost

- **Currently measured: `zhipu glm-5.3-flash` + local `bge-m3`** (`llm.active=zhipu`, key in
  `config.local.json`). Current-scope log window (96 requests / 73 real LLM calls,
  `reports/ops_report.md`): mean 588.7 tokens/call, p50 4ms (a third of requests hit the cache) /
  p95 4692ms / p99 5726ms, **100% within 10s**, mean faithfulness 0.9675, numeric-grounding 1.0,
  answer compliance 1.0. The 8-worker load test (60 requests, `reports/load_test.csv`): 100% success,
  p50 23ms / p95 4175ms, 7.65 RPS. All 30 evaluation questions pass every metric
  (`reports/eval_report.md`; retrieval 1.000/1.000/1.000 across the three configs). Switching
  generation to `deepseek` is one config key (both keys are pre-configured locally).
- **Embedding cost: 0** (the default `ollama bge-m3` runs locally, nothing is metered). Cloud
  `embedding-3` is negligible too (<¥0.01 for the full 45-chunk ingest plus every evaluation call).
- **deepseek-flash reference** (measured before the embedding upgrade): 78 calls, mean 528.2
  tokens/call, p50 597ms / p95 2068ms; per 1,000 requests ≈ 140k tokens ≈ ¥0.22 at flash list pricing
  (¥1/M input, ¥4/M output; weekday peak capped at 2×).
- Cost basis: mean `token_usage.total_tokens` × 1000; cache hits and refusals cost 0 tokens. In this
  window (73 calls, a third cache-hit) that is ≈448k tokens per 1,000 requests; cold (0% hits) it is
  588.7 × 1000 ≈ 589k ≈ ¥2.8 at ¥1/M input + ¥4/M output. Switching models only changes `llm.active`;
  re-run `scripts/ops_report.py` to reprice.
- **Latency ceiling guard**: `llm.timeout_seconds=8` (configurable) — worst case is an 8s call plus one
  retry, then a uniform refusal; a single request can never hang 30s and blow the 10s SLA.
- Trade-offs: dropping to a 7B-class model halves latency but raises numeric/transcription errors in
  clauses; a 72B-class model improves quality but cannot sustain the ≥5-concurrency target on one instance.
- Prompt constraints (`llm.SYSTEM_PROMPT` v5): facts only from the retrieved material, single plain-text
  paragraph ≤150 characters, source filename at the end, **answer in the language of the question**.
  The A/B experiment (`scripts/prompt_experiment.py` → `reports/prompt_experiment.md`) shows large gains
  in Faithfulness and Style Consistency; genuine hallucinations (invented numbers/clauses) are caught by
  the faithfulness measure plus the numeric-grounding check.

<a id="s8"></a>
## 8. Deliverables

| Requirement | Location |
|---|---|
| Complete code and configuration | This directory (§2 file table; model/embedding presets in `config.json`, secrets in `config.local.json` — not committed) |
| One-click evaluation script | `eval.py`, `scripts/load_test.py`, `scripts/ops_report.py` |
| Evaluation report with before/after comparisons | `reports/eval_report.md`, `reports/eval_metrics.csv`, `reports/ops_report.md`, `reports/load_test.csv`, `reports/prompt_experiment.md`, `reports/threshold_experiment.md`, `reports/embedding_experiment.md` |
| Log field dictionary and sample logs | `docs/log_fields.md`, `logs/rag.jsonl` |
| Five diagnosed issues (evidence + ≥10% improvement) | `docs/issue_diagnosis.md` |
| Evaluation method and metric definitions | `docs/evaluation.md` |
| Bilingual PDF / OCR chain | `data/hr_policy_bilingual.pdf`, `data/scanned_leave.ocr.txt`, `scripts/make_bilingual_pdf.py` (see §5) |

---

[⬆ Back to top](#top) &nbsp;|&nbsp; <a href="README.md">阅读中文版</a>
