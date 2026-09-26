"""HTTP 入口：ThreadingHTTPServer，/api/ask /api/health /api/config + 静态页。"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import llm
import pipeline
import store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/ask":
            qs = parse_qs(parsed.query)
            q = qs.get("q", [""])[0]
            sid = qs.get("session_id", [""])[0]
            return self._handle_ask({"q": q, "session_id": sid})
        if path == "/api/health":
            cfg = pipeline.load_config()
            try:
                n = store.count()
            except Exception:
                n = -1
            try:
                emb = store.embedding_signature()
            except Exception:
                emb = "unknown"
            return self._send_json({
                "index_ready": store.index_ready(),
                "chunks": n,
                "embedding": emb,
                "llm_provider": llm.active_name(),
                "llm_model": llm.model_name(),
                "retrieval_mode": cfg["retrieval_mode"],
                "rerank_enabled": cfg["rerank_enabled"],
            })
        if path == "/api/config":
            cfg = pipeline.load_config()
            for preset in (cfg.get("llm", {}).get("providers") or {}).values():
                if isinstance(preset, dict) and preset.get("api_key"):
                    preset["api_key"] = "***"
            return self._send_json(cfg)
        if path in ("/", "/index.html"):
            return self._serve_static("index.html")
        if path.startswith("/static/"):
            return self._serve_static(path[len("static/"):])
        self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/ask":
            return self._send_json({"error": "not found"}, 404)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._send_json({"error": "invalid json"}, 400)
        if not isinstance(payload, dict):
            return self._send_json({"error": "body must be object"}, 400)
        self._handle_ask(payload)

    def _handle_ask(self, payload):
        if not store.index_ready():
            return self._send_json(
                {"error": "index not ready, run: python ingest.py"}, 503)
        try:
            resp = pipeline.answer_question(payload)
        except Exception as e:  # 未预期异常（如 embedding/索引不一致）：返回 500 而非让线程崩掉
            return self._send_json({"error": f"internal error: {e}"}, 500)
        self._send_json(resp)

    def _serve_static(self, rel):
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(STATIC_DIR) or not os.path.isfile(full):
            return self._send_json({"error": "not found"}, 404)
        ctype = "text/html; charset=utf-8" if full.endswith(".html") else "text/plain; charset=utf-8"
        with open(full, "rb") as f:
            self._send(200, f.read(), ctype)

    def log_message(self, fmt, *args):
        pass  # 结构化日志走 logs/rag.jsonl，屏蔽默认 access log


def main():
    cfg = pipeline.load_config()
    host = str(cfg.get("server_host", "127.0.0.1"))
    port = int(cfg.get("server_port", 8788))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"grounded-qa server on http://{host}:{port}  "
          f"(llm.active={llm.active_name()}, model={llm.model_name()}, "
          f"api_key={'set' if llm.has_api_key() else 'none'}, embedding={store.embedding_signature()})")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
