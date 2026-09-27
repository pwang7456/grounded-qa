"""分块、可配置 embedding（hash 离线 / 智谱 embedding-3 / 本地 Ollama bge-m3）、嵌入式 Chroma 读写。"""
import hashlib
import json
import math
import os
import re
import threading
import urllib.error
import urllib.request
import uuid

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
import chromadb
from chromadb.config import Settings

from settings import load_config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_DIR = os.path.join(BASE_DIR, "chroma_data")
COLLECTION_NAME = "internal_kb"
DIM = 384
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9]+")

_lock = threading.RLock()  # 可重入：get_all_chunks 持锁内会再进 get_client
_client = None
_all_cache = None  # (version, chunks)

# embedding.provider → 默认 OpenAI 兼容端点与模型（config.json 的 embedding.base_url/model 可覆盖）
DEFAULT_EMBED_BASE_URLS = {
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "ollama": "http://127.0.0.1:11434/v1",
}
DEFAULT_EMBED_MODELS = {"zhipu": "embedding-3", "ollama": "bge-m3"}


class EmbeddingUnavailable(Exception):
    """embedding 端点不可用（仅 API embedding 时）。"""


def get_client():
    global _client
    with _lock:
        if _client is None:
            os.makedirs(CHROMA_DIR, exist_ok=True)
            _client = chromadb.PersistentClient(
                path=CHROMA_DIR,
                settings=Settings(anonymized_telemetry=False, allow_reset=True),
            )
        return _client


def get_collection():
    return get_client().get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "embedding": embedding_signature()},
    )


class LocalHashEmbeddingFunction:
    """确定性、离线的 hash bag-of-words embedding（中英混合 token）。"""

    def embed(self, text: str):
        vec = [0.0] * DIM
        for tok in TOKEN_RE.findall(text.lower()):
            h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
            pos = h % DIM
            sign = 1.0 if (h // DIM) % 2 == 0 else -1.0
            vec[pos] += sign
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def __call__(self, texts):
        return [self.embed(t) for t in texts]


class OpenAICompatEmbeddingFunction:
    """OpenAI 兼容 /embeddings（智谱 embedding-3 / Ollama bge-m3）。入库批量调用，查询向量带进程内缓存。

    api_key 为空时不发 Authorization 头（本地 Ollama 无需鉴权）。
    """

    BATCH = 16

    def __init__(self, base_url, model, api_key="", dimensions=1024, timeout=10):
        self.url = base_url.rstrip("/") + "/embeddings"
        self.model = model
        self.api_key = api_key
        self.dimensions = int(dimensions or 1024)
        self.timeout = timeout
        self._cache = {}  # 查询文本 -> 向量，重复问题零开销
        self._cache_lock = threading.Lock()

    def _embed_batch(self, texts):
        body = {"model": self.model, "input": list(texts)}
        if self.dimensions:
            body["dimensions"] = self.dimensions
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(
            self.url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", "replace")[:150]
            except Exception:
                detail = ""
            raise EmbeddingUnavailable(f"embedding HTTP {e.code}: {detail}")
        except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError) as e:
            raise EmbeddingUnavailable(f"embedding endpoint unreachable: {e}")
        items = sorted(data.get("data") or [], key=lambda x: x.get("index", 0))
        if len(items) != len(texts):
            raise EmbeddingUnavailable(
                f"embedding 返回数量不符: {len(items)} != {len(texts)}")
        return [it["embedding"] for it in items]

    def embed(self, text: str):
        key = text[:512]
        with self._cache_lock:
            hit = self._cache.get(key)
        if hit is not None:
            return hit
        vec = self._embed_batch([key])[0]
        with self._cache_lock:
            if len(self._cache) >= 2048:
                self._cache.clear()  # 简单防膨胀：满了整体清空
            self._cache[key] = vec
        return vec

    def __call__(self, texts):
        out = []
        for i in range(0, len(texts), self.BATCH):
            out.extend(self._embed_batch(texts[i:i + self.BATCH]))
        return out


_ef = None
_ef_sig = None
_ef_lock = threading.Lock()


def _embedding_cfg() -> dict:
    cfg = load_config().get("embedding") or {}
    return cfg if isinstance(cfg, dict) else {}


def embedding_signature() -> str:
    """当前 embedding 配置指纹；写入 collection metadata，防换 embedding 后查旧索引。"""
    ecfg = _embedding_cfg()
    provider = str(ecfg.get("provider") or "hash").lower()
    if provider == "hash":
        return f"hash:{DIM}"
    model = str(ecfg.get("model") or DEFAULT_EMBED_MODELS.get(provider, provider))
    return f"{provider}:{model}:{int(ecfg.get('dimensions') or 1024)}"


def _embed_endpoint(provider: str):
    """返回 (base_url, api_key)。api_key 复用 llm.providers 里的同名录入，本地端点为空。"""
    ecfg = _embedding_cfg()
    base_url = str(ecfg.get("base_url") or DEFAULT_EMBED_BASE_URLS.get(provider) or "").strip()
    if not base_url:
        raise EmbeddingUnavailable(
            f"embedding.provider={provider} 需要 base_url（config.json 的 embedding.base_url）")
    api_key = ""
    if provider == "zhipu":
        zcfg = (load_config().get("llm") or {}).get("providers", {}).get("zhipu") or {}
        api_key = str(zcfg.get("api_key") or "")
        if not api_key:
            raise EmbeddingUnavailable(
                "embedding.provider=zhipu 需要 llm.providers.zhipu.api_key"
                "（写在 config.local.json 里）")
    return base_url, api_key


def get_embedding_function():
    global _ef, _ef_sig
    sig = embedding_signature()
    with _ef_lock:
        if _ef is not None and _ef_sig == sig:
            return _ef
        provider = str(_embedding_cfg().get("provider") or "hash").lower()
        if provider == "hash":
            _ef = LocalHashEmbeddingFunction()
        else:
            ecfg = _embedding_cfg()
            base_url, api_key = _embed_endpoint(provider)
            _ef = OpenAICompatEmbeddingFunction(
                base_url=base_url,
                model=str(ecfg.get("model") or DEFAULT_EMBED_MODELS.get(provider, "")),
                api_key=api_key,
                dimensions=ecfg.get("dimensions") or 1024,
            )
        _ef_sig = sig
        return _ef


def embed(text: str):
    return get_embedding_function().embed(text)


def detect_language(text: str) -> str:
    cjk = len(re.findall(r"[一-鿿]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cjk == 0 and latin == 0:
        return "unknown"
    return "zh" if cjk * 2 >= latin else "en"


CHUNKER_VERSION = "v3"  # 切块逻辑版本，参与缓存 salt：切块/元数据契约变更后旧缓存自动失效
HEADING_PATH_SEP = " > "
MAX_CHUNK_CHARS = 400
OVERLAP_CHARS = 50
MIN_BLOCK_CHARS = 6
MAX_PREFIX_CHARS = 60
SENT_ENDINGS = "。！？；;\n"


def _context_prefix(stack, budget: int = MAX_PREFIX_CHARS) -> str:
    """标题路径前缀：从最贴近正文的标题往上取，超出预算就停（最上层文档名最先被舍）。

    全文档共用的 H1 若进每个 chunk，会把它的词塞进每一块的 BM25 词袋——idf 被压低、
    文档长度被拉长，等于给检索加噪声，所以这里给前缀设上限而不是无脑拼完整路径。
    """
    picked, used = [], 0
    for _, title in reversed(stack):
        cost = len(title) + (len(HEADING_PATH_SEP) if picked else 0)
        if picked and used + cost > budget:
            break
        picked.append(title)
        used += cost
    return HEADING_PATH_SEP.join(reversed(picked))


def _split_long(body: str, limit: int = MAX_CHUNK_CHARS, overlap: int = OVERLAP_CHARS):
    """超长正文按句末边界切开，相邻块保留 overlap 字重叠，防止关键句恰好骑在边界上。"""
    n = len(body)
    if n <= limit:
        return [body]
    parts, start = [], 0
    while start < n:
        end = min(start + limit, n)
        if end < n:
            floor = start + int(limit * 0.4)
            cut = max((body.rfind(sep, floor, end + 1) for sep in SENT_ENDINGS), default=-1)
            if cut > start:
                end = cut + 1
        piece = body[start:end].strip()
        if piece:
            parts.append(piece)
        if end >= n:
            break
        start = max(end - overlap, start + 1)  # 单调推进，避免重叠导致死循环
    return parts


def chunk_blocks(blks, filename: str, ocr: bool = False):
    """Block 列表 → chunks。每个 chunk 文本 = 标题路径前缀 + 正文；
    正文原文一字不改（eval 的 gold_contains 靠正文子串匹配，前缀只能增不能改）。"""
    chunks = []
    stack = []  # [(level, title)]
    idx = 0
    for b in blks:
        if b["type"] == "heading":
            while stack and stack[-1][0] >= b["level"]:
                stack.pop()
            stack.append((b["level"], b["text"]))
            continue
        full_path = HEADING_PATH_SEP.join(t for _, t in stack)
        prefix = _context_prefix(stack)
        # 表格块不跨块切：拆开后单元格会脱离列名，等于把表格变成噪声
        bodies = [b["text"]] if b["type"] == "table" else _split_long(b["text"])
        for body in bodies:
            if len(body) < MIN_BLOCK_CHARS:
                continue
            text = f"{prefix}：{body}" if prefix else body
            chunks.append({
                "id": f"{filename}:{idx}",
                "text": text,
                "metadata": {
                    "source": filename,
                    "language": detect_language(text),
                    "ocr": ocr,
                    "chunk_index": idx,
                    # 完整路径只进 metadata 供溯源展示；进 embedding 的是预算内的尾部前缀
                    "heading_path": full_path,
                    "block_type": b["type"],
                    # rerank 的词面覆盖只在正文上算才不失真；前缀长度供检索层剥离
                    "prefix_len": len(text) - len(body),
                },
            })
            idx += 1
    return chunks


def rebuild_index(chunks):
    """全量重建集合。chunks: [{id, text, metadata}]"""
    try:
        get_client().delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    # 用 create_collection（而非 get_or_create）：metadata 里的 ingest_id 是跨进程
    # 缓存失效的哨兵，每次重建必须换新，运行中的服务才能感知索引已换血
    coll = get_client().create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine",
                  "embedding": embedding_signature(),
                  "ingest_id": uuid.uuid4().hex[:12]},
    )
    if chunks:
        ef = get_embedding_function()
        coll.add(
            ids=[c["id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            embeddings=ef([c["text"] for c in chunks]),
            metadatas=[c["metadata"] for c in chunks],
        )
    invalidate_cache()
    return len(chunks)


def count() -> int:
    return get_collection().count()


def query_vectors(question: str, n: int):
    """返回 [(id, text, metadata, score)]，score = 1 - cosine distance。"""
    coll = get_collection()
    total = coll.count()
    if total == 0:
        return []
    idx_sig = (coll.metadata or {}).get("embedding")
    cur_sig = embedding_signature()
    if idx_sig and idx_sig != cur_sig:
        raise RuntimeError(
            f"embedding 配置({cur_sig})与索引({idx_sig})不一致，请重跑: python ingest.py")
    res = coll.query(
        query_embeddings=[embed(question)],
        n_results=min(n, total),
        include=["documents", "metadatas", "distances"],
    )
    out = []
    for cid, doc, meta, dist in zip(
        res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        out.append((cid, doc, meta, max(0.0, 1.0 - dist)))
    return out


def get_all_chunks():
    """全库 chunks（BM25 用），带缓存。

    版本 = (块数, ingest_id) 双因子：入库进程重建集合后，即使块数恰好相同，
    ingest_id 也必然变化——单靠 count 判断会让运行中的服务一直用旧语料。"""
    global _all_cache
    with _lock:
        coll = get_collection()
        version = (coll.count(), (coll.metadata or {}).get("ingest_id") or "")
        if _all_cache is not None and _all_cache[0] == version:
            return _all_cache[1]
        res = coll.get(include=["documents", "metadatas"])
        chunks = [
            {"id": cid, "text": doc, "metadata": meta}
            for cid, doc, meta in zip(res["ids"], res["documents"], res["metadatas"])
        ]
        _all_cache = (version, chunks)
        return chunks


def invalidate_cache():
    global _all_cache
    with _lock:
        _all_cache = None


def index_ready() -> bool:
    try:
        return count() > 0
    except Exception:
        return False
