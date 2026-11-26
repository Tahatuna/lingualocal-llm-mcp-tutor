#!/usr/bin/env python3
"""Language Services: translation, speech, word cards and pronunciation scoring over HTTP (see README.md).

    .venv/bin/python server.py        # http://127.0.0.1:8770
"""
import json
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from services import chat, config, lexicon, llm, pronounce, translate, tts

MAX_BODY = 64 * 1024
CLIENT_JS = config.ROOT + "/client/ls-client.js"


def log(**fields):
    # One JSON line per request; never the text the user typed (privacy).
    print(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), **fields}), file=sys.stderr, flush=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "language-services/1.0"

    def log_message(self, *args):
        pass

    # ---------- plumbing ----------
    def _host_ok(self):
        # DNS rebinding guard: only answer requests addressed to this machine.
        return self.headers.get("Host", "") in {f"localhost:{config.PORT}", f"127.0.0.1:{config.PORT}"}

    def _cors(self):
        origin = self.headers.get("Origin")
        if origin and origin in config.ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send(self, status, body, ctype, cache="no-store"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self._cors()
        self.end_headers()
        self.wfile.write(body)
        self._status = status

    def _json(self, status, payload):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _body(self):
        if "application/json" not in self.headers.get("Content-Type", ""):
            return None  # JSON only: a cross-site form cannot send it without a CORS preflight
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            return None
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def _handle(self, method):
        t0, self._status = time.time(), 0
        url = urllib.parse.urlparse(self.path)
        try:
            if not self._host_ok():
                return self._json(403, {"error": "forbidden host"})
            if method == "OPTIONS":
                return self._preflight()
            if method == "GET":
                q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
                return self._get(url.path, q)
            body = self._body()
            if body is None:
                return self._json(415, {"error": "send a JSON object with Content-Type: application/json"})
            return self._post(url.path, body)
        finally:
            log(method=method, path=url.path, status=self._status, ms=round((time.time() - t0) * 1000))

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_OPTIONS(self):
        self._handle("OPTIONS")

    def _preflight(self):
        self.send_response(204)
        if self.headers.get("Origin") in config.ALLOWED_ORIGINS:
            self._cors()
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()
        self._status = 204

    # ---------- routes ----------
    WORD_PARTS = {"/v1/word": lexicon.base, "/v1/word/examples": lexicon.examples, "/v1/word/senses": lexicon.senses,
                  "/v1/word/fill": lexicon.fill}

    def _get(self, path, q):
        if path == "/v1/health":
            return self._json(200, {"ok": True, "model": config.OLLAMA_MODEL, "model_running": llm.available(),
                                    "voices": tts.voices()})
        if path == "/v1/warm":
            # Called when a page opens: load the voice and the model now, not on the first lookup.
            threading.Thread(target=tts.warm, daemon=True).start()
            llm.warm()
            return self._json(202, {"ok": True})
        if path == "/v1/voices":
            return self._json(200, tts.voices())
        if path == "/v1/tts":
            return self._tts(q)
        if path in self.WORD_PARTS:
            status, data = self.WORD_PARTS[path](q.get("word", ""))
            return self._json(status, data)
        if path == "/client.js":
            with open(CLIENT_JS, "rb") as f:
                return self._send(200, f.read(), "text/javascript; charset=utf-8", "no-cache")
        return self._json(404, {"error": "not found"})

    def _post(self, path, b):
        if path == "/v1/detect":
            text = translate.clean(b.get("text"))
            return self._json(200 if text else 400, {"lang": translate.detect(text)} if text else {"error": "empty text"})
        if path == "/v1/translate":
            return self._json(*translate.translate(b.get("text"), str(b.get("from", "auto")), str(b.get("to", "auto"))))
        if path == "/v1/translate/check":
            return self._json(*translate.check(b.get("text"), b.get("translation"), str(b.get("from", "auto")),
                                               str(b.get("to", "auto"))))
        if path == "/v1/chat":
            return self._json(*chat.reply(b.get("messages"), b.get("context", "")))
        if path == "/v1/translate/rewrite":
            return self._json(*translate.rewrite(b.get("text")))
        if path == "/v1/translate/variants":
            return self._json(*translate.variants(b.get("text"), str(b.get("from", "auto")), str(b.get("to", "auto"))))
        if path == "/v1/tts":
            return self._tts(b)
        if path == "/v1/pronunciation/score":
            alts = b.get("alternatives") if isinstance(b.get("alternatives"), list) else []
            return self._json(*pronounce.score(b.get("target"), alts))
        return self._json(404, {"error": "not found"})

    def _tts(self, q):
        status, data = tts.speak(q.get("text"), str(q.get("lang", "en")), str(q.get("accent", "us")), q.get("speed", 1.0))
        if status != 200:
            return self._json(status, data)
        # The same text always gives the same audio: let the browser keep it.
        return self._send(200, data, "audio/wav", "public, max-age=604800")


def main():
    server = ThreadingHTTPServer((config.HOST, config.PORT), Handler)
    log(event="start", port=config.PORT, model=config.OLLAMA_MODEL)
    server.serve_forever()


if __name__ == "__main__":
    main()
