#!/usr/bin/env python3
"""LinguaLocal: the web page (http://localhost:8767) and your data (history, saved words and sentences).

Translation, speech, word cards and pronunciation scoring come from Language Services
(language-services/, http://localhost:8770), which the page calls directly.

    python3 server.py
"""
import json
import os
import re
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import store

# Language Services uses 8770; LL_PORT overrides the page port.
PORT = int(os.environ.get("LL_PORT") or 8767)
SERVICES = os.environ.get("LL_SERVICES") or "http://localhost:8770"
ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC = {"/": "index.html", "/index.html": "index.html", "/app.css": "app.css", "/app.js": "app.js", "/mouth.js": "mouth.js", "/chat.js": "chat.js"}
MAX_BODY = 64 * 1024
CTRL = re.compile(r"[\x00-\x1f\x7f]")
# No inline scripts or styles; the page may only talk to itself and to Language Services.
CSP = ("default-src 'self'; script-src 'self' {s}; connect-src 'self' {s}; media-src 'self' {s} blob:; "
       "style-src 'self' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:; "
       "frame-ancestors 'none'; base-uri 'none'; form-action 'none'").format(s=SERVICES)


CTRL_KEEP_LINES = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_multiline(text, limit):
    """Chat messages keep their line breaks and tabs; other control characters go."""
    return CTRL_KEEP_LINES.sub(" ", str(text or "")).strip()[:limit]


def clean(text, limit=store.MAX_TEXT):
    return CTRL.sub(" ", str(text or "")).strip()[:limit]


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def log_message(self, *args):
        pass

    def end_headers(self):
        # API answers are never stored; static files are revalidated on every load, so a change is never hidden by
        # the browser cache.
        self.send_header("Cache-Control", "no-store" if self.path.startswith("/api/") else "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", CSP)
        super().end_headers()

    def host_ok(self):
        # DNS rebinding guard.
        return self.headers.get("Host", "") in {f"localhost:{PORT}", f"127.0.0.1:{PORT}"}

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.host_ok():
            return self.send_json({"error": "forbidden"}, 403)
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/history":
            return self.send_json(store.history_list())
        if path == "/api/saved":
            return self.send_json(store.saved_list())
        if path == "/api/chats":
            return self.send_json(store.chats_list())
        if path == "/api/chat":
            try:
                cid = int(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("id", [""])[0])
            except ValueError:
                return self.send_json({"error": "bad id"}, 400)
            return self.send_json(store.chat_list(cid))
        if path == "/config.js":
            body = f"export const SERVICES = {json.dumps(SERVICES)};\n".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if path not in STATIC:
            return self.send_json({"error": "not found"}, 404)
        self.path = "/" + STATIC[path]
        return super().do_GET()

    def do_POST(self):
        if not self.host_ok() or self.headers.get("X-LL") != "1":
            return self.send_json({"error": "forbidden"}, 403)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(n, MAX_BODY)) or b"{}") if n <= MAX_BODY else None
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return self.send_json({"error": "bad json"}, 400)
        path = urllib.parse.urlparse(self.path).path
        kind = str(body.get("kind", ""))
        if path == "/api/history/add":
            text = clean(body.get("text"))
            if not text or kind not in store.KINDS:
                return self.send_json({"error": "bad entry"}, 400)
            lang = str(body.get("lang", ""))
            return self.send_json(store.history_add(text, kind, clean(body.get("result"), 300), lang if lang in store.LANGS else ""))
        if path == "/api/history/clear":
            return self.send_json({"removed": store.history_clear()})
        if path == "/api/history/remove":
            try:
                store.history_remove(int(body.get("id")))
            except (TypeError, ValueError):
                return self.send_json({"error": "bad id"}, 400)
            return self.send_json({"ok": True})
        if path == "/api/chats/new":
            return self.send_json(store.chat_new(clean(body.get("title"), store.MAX_TITLE)))
        if path in ("/api/chat/add", "/api/chats/rename", "/api/chats/delete"):
            try:
                cid = int(body.get("chat_id", body.get("id")))
            except (TypeError, ValueError):
                return self.send_json({"error": "bad id"}, 400)
            if path.endswith("delete"):
                return self.send_json({"removed": store.chat_delete(cid)})
            if path.endswith("rename"):
                chat = store.chat_rename(cid, clean(body.get("title"), store.MAX_TITLE))
                return self.send_json(chat) if chat else self.send_json({"error": "no such chat"}, 404)
            role, content = str(body.get("role", "")), clean_multiline(body.get("content"), store.MAX_CHAT)
            if role not in ("user", "assistant") or not content:
                return self.send_json({"error": "bad message"}, 400)
            msg = store.chat_add(cid, role, content)
            return self.send_json(msg) if msg else self.send_json({"error": "no such chat"}, 404)
        if path in ("/api/saved/add", "/api/saved/remove"):
            text = clean(body.get("text"))
            if not text or kind not in store.KINDS:
                return self.send_json({"error": "bad entry"}, 400)
            if path.endswith("add"):
                store.save(kind, text.lower() if kind == "word" else text, clean(body.get("tr"), 300))
            else:
                store.unsave(kind, text)
            return self.send_json(store.saved_list())
        return self.send_json({"error": "not found"}, 404)


def main():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"LinguaLocal: http://localhost:{PORT}  (services: {SERVICES})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
