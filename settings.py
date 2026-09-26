"""运行时配置：config.json（模板，可提交）+ config.local.json（本地密钥，不入库）。

两层深度合并，local 优先：key 只放 config.local.json（.gitignore 已排除），
config.json 保持 key 为空字符串，可直接提交/分享。
切换大模型：把 `llm.active` 改成 `llm.providers` 里的预设名（deepseek / zhipu）。
向量模型同理：`embedding.provider`（hash / zhipu / ollama）。
"""
import copy
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOCAL_PATH = os.path.join(BASE_DIR, "config.local.json")

DEFAULTS = {
    "retrieval_mode": "hybrid",
    "rerank_enabled": True,
    "top_k": 8,
    "return_k": 3,
    # 语义 embedding（ollama/zhipu）：判定用向量余弦，相关资料≈0.6+、无关≈0.45 → 取中间 0.55
    # 词面 hash：判定用 hybrid 融合分，量纲不同 → 0.12
    "refuse_threshold": 0.55,
    "cache_enabled": True,
    "cache_ttl_seconds": 600,
    "max_history_turns": 4,
    "server_host": "127.0.0.1",
    "server_port": 8788,
    "embedding": {
        # hash（离线词面）| zhipu（embedding-3 API）| ollama（本地 bge-m3，零 token 费用）
        "provider": "ollama",
        "model": "bge-m3",
        "dimensions": 1024,
        "base_url": "",   # 留空 = store.DEFAULT_EMBED_BASE_URLS[provider]
    },
    "llm": {
        "active": "zhipu",
        "timeout_seconds": 8,   # 单次调用上限：8s + 重试 1 次仍可控在 10s SLA 口径内
        "max_tokens": 400,
        "providers": {
            "deepseek": {
                "base_url": "https://api.deepseek.com/v1",
                "model": "deepseek-flash",
                "api_key": "",
            },
            "zhipu": {
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
                "model": "glm-5.3-flash",
                "api_key": "",
                # glm-5.3-flash 始终思考且不支持关闭（API 会拒绝 type=disabled），
                # 实测默认推理就烧 300+ token、延迟 6~10s；reasoning_effort=low
                # 把推理 token 压到 0、延迟 1~3s（智谱 OpenAI 兼容参数）
                "reasoning_effort": "low",
            },
        },
    },
}


def _read(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"[settings] 忽略无法解析的 {os.path.basename(path)}: {e}")
        return {}


def _merge(base: dict, extra: dict) -> dict:
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config() -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    _merge(cfg, _read(CONFIG_PATH))
    _merge(cfg, _read(LOCAL_PATH))  # 本地覆盖：api_key 等敏感项
    return cfg
