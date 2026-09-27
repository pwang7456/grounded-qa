"""答案磁盘缓存（按 问题+检索配置 哈希）。"""
import hashlib
import json
import os
import threading
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "cache", "answers.json")
_lock = threading.Lock()


def make_key(question: str, mode: str, rerank_enabled, salt: str = "") -> str:
    raw = f"{question}|{mode}|{bool(rerank_enabled)}|{salt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)


def get(key: str, ttl: int):
    with _lock:
        data = _load()
        entry = data.get(key)
        if not entry:
            return None
        if time.time() - entry.get("created_at", 0) > ttl:
            return None
        return entry.get("value")


def put(key: str, value: dict):
    with _lock:
        data = _load()
        data[key] = {"created_at": time.time(), "value": value}
        # 简单防膨胀：只保留最近 500 条
        if len(data) > 500:
            keep = sorted(data.items(), key=lambda kv: kv[1].get("created_at", 0))[-500:]
            data = dict(keep)
        _save(data)
