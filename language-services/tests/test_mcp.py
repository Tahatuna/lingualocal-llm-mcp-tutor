"""MCP server tests: the real stdio process talks to a stub of the HTTP API on a random local port.
No model, no dictionaries, no network.

    .venv/bin/python -m unittest tests.test_mcp
"""
import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEN = []  # (method, path, body) the stub received


class StubAPI(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        SEEN.append(("GET", self.path, None))
        if self.path.startswith("/v1/word?"):
            return self._reply(200, {"word": "give", "tr": "vermek"})
        return self._reply(404, {"error": "not found"})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(("POST", self.path, body))
        if self.path == "/v1/translate":
            return self._reply(200, {"translation": "Okula gidiyor.", "from": "en", "to": "tr"})
        if self.path == "/v1/translate/check":
            return self._reply(200, {"has_errors": True, "corrected": "She goes to school.",
                                     "fixes": [{"wrong": "go", "right": "goes", "why_tr": "Üçüncü tekil şahıs"}]})
        return self._reply(503, {"error": "model busy"})


class MCPServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = ThreadingHTTPServer(("127.0.0.1", 0), StubAPI)
        threading.Thread(target=cls.api.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.api.shutdown()
        cls.api.server_close()

    def setUp(self):
        SEEN.clear()

    def run_session(self, *messages, url=None):
        env = dict(os.environ, LS_URL=url or f"http://127.0.0.1:{self.api.server_address[1]}")
        lines = "".join((m if isinstance(m, str) else json.dumps(m)) + "\n" for m in messages)
        r = subprocess.run([sys.executable, os.path.join(ROOT, "mcp_server.py")], input=lines, env=env,
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        return [json.loads(x) for x in r.stdout.splitlines()]

    def test_handshake_lists_read_only_tools(self):
        out = self.run_session(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(len(out), 2)  # the notification gets no answer
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-06-18")
        tools = out[1]["result"]["tools"]
        self.assertEqual({t["name"] for t in tools},
                         {"translate", "check_english", "rewrite_english", "word_card", "example_sentences"})
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools))

    def test_unknown_protocol_version_gets_the_newest(self):
        out = self.run_session({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
        self.assertEqual(out[0]["result"]["protocolVersion"], "2025-06-18")

    def test_check_english_translates_then_checks(self):
        out = self.run_session({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                                "params": {"name": "check_english", "arguments": {"text": "She go to school."}}})
        result = out[0]["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["corrected"], "She goes to school.")
        self.assertEqual([p for _, p, _ in SEEN], ["/v1/translate", "/v1/translate/check"])
        self.assertEqual(SEEN[1][2]["translation"], "Okula gidiyor.")

    def test_word_is_url_encoded(self):
        out = self.run_session({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                                "params": {"name": "word_card", "arguments": {"word": "give up&x=1"}}})
        self.assertFalse(out[0]["result"]["isError"])
        self.assertEqual(SEEN[0][1], "/v1/word?word=give+up%26x%3D1")

    def test_bad_input_and_api_errors_are_tool_errors(self):
        out = self.run_session(
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "translate", "arguments": {"text": "  "}}},
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "translate",
                                                                           "arguments": {"text": "hi", "from": "de"}}},
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "rewrite_english",
                                                                           "arguments": {"text": "x" * 2001}}},
            {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "rewrite_english",
                                                                           "arguments": {"text": "Hello"}}})
        self.assertTrue(all(o["result"]["isError"] for o in out))
        self.assertIn("model busy", out[3]["result"]["content"][0]["text"])
        self.assertEqual([p for _, p, _ in SEEN], ["/v1/translate/rewrite"])  # invalid input never reached the API

    def test_service_down_is_reported_not_crashed(self):
        out = self.run_session({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                                "params": {"name": "translate", "arguments": {"text": "hello"}}},
                               url="http://127.0.0.1:9")
        self.assertTrue(out[0]["result"]["isError"])
        self.assertIn("not reachable", out[0]["result"]["content"][0]["text"])

    def test_protocol_errors(self):
        out = self.run_session("{not json", {"jsonrpc": "2.0", "id": 10, "method": "nope"},
                               {"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "rm_rf"}},
                               {"jsonrpc": "2.0", "id": 12, "method": "ping"})
        self.assertEqual([o.get("error", {}).get("code") for o in out], [-32700, -32601, -32602, None])
        self.assertEqual(out[3]["result"], {})


if __name__ == "__main__":
    unittest.main()
