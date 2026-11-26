#!/usr/bin/env python3
"""Language Services as an MCP server (Model Context Protocol, stdio transport).

Lets an AI assistant (Claude Code, Claude Desktop, any MCP client) use the same local tools as the page:
translation, sentence checks, better wording, word cards and real example sentences. It is a thin adapter: every
tool calls the running HTTP API (server.py), so the model, the dictionaries and the cache are shared.

    .venv/bin/python mcp_server.py      # speaks JSON-RPC on stdin/stdout; logs go to stderr

Settings: LS_URL (default http://127.0.0.1:8770). The tools only read; none of them touches your saved data.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")  # newest first
SERVER_INFO = {"name": "language-services", "version": "1.0.0"}
LS_URL = (os.environ.get("LS_URL") or "http://127.0.0.1:8770").rstrip("/")
TIMEOUT_S = 60  # a sentence check on the local model can take ~15 s; leave room for a cold start
MAX_TEXT = 2000

LANG = {"type": "string", "enum": ["auto", "en", "tr"]}
TEXT = {"type": "string", "description": "English or Turkish text", "maxLength": MAX_TEXT}
WORD = {"type": "string", "description": "An English word or short phrase, e.g. 'give up'", "maxLength": 80}
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False}

TOOLS = [
    {"name": "translate",
     "description": "Translate between English and Turkish. Single words come from the Oxford Turkish Dictionary, "
                    "sentences from the local language model. The language is detected when 'from' is auto.",
     "inputSchema": {"type": "object", "properties": {"text": TEXT, "from": LANG, "to": LANG},
                     "required": ["text"], "additionalProperties": False}},
    {"name": "check_english",
     "description": "Check an English sentence written by a Turkish speaker: wrong words, wrong prepositions and "
                    "grammar. Returns the corrected sentence and each fix with its reason in Turkish.",
     "inputSchema": {"type": "object", "properties": {"text": TEXT}, "required": ["text"],
                     "additionalProperties": False}},
    {"name": "rewrite_english",
     "description": "Up to three better ways to write an English text (more natural, more formal, simpler).",
     "inputSchema": {"type": "object", "properties": {"text": TEXT}, "required": ["text"],
                     "additionalProperties": False}},
    {"name": "word_card",
     "description": "Everything about an English word from the macOS Oxford dictionaries and curated lists: meanings "
                    "by frequency, Turkish per meaning, US/UK IPA, verb forms, -ing or to, prepositions, phrasal "
                    "verbs, word family, how common it is and typical mistakes of Turkish speakers.",
     "inputSchema": {"type": "object", "properties": {"word": WORD}, "required": ["word"],
                     "additionalProperties": False}},
    {"name": "example_sentences",
     "description": "Real English sentences with human Turkish translations (Tatoeba) that use the word.",
     "inputSchema": {"type": "object", "properties": {"word": WORD}, "required": ["word"],
                     "additionalProperties": False}},
]
for _t in TOOLS:
    _t["annotations"] = READ_ONLY


class ToolError(Exception):
    """A failure the assistant should read (bad input, service down); sent back as an isError result."""


def _request(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(LS_URL + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            return json.loads(r.read(1_000_000))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read(10_000)).get("error") or e.reason
        except ValueError:
            detail = e.reason
        raise ToolError(f"Language Services answered {e.code}: {detail}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        raise ToolError(f"Language Services is not reachable at {LS_URL}. Start it with scripts/lsctl start.") from None
    except ValueError:
        raise ToolError("Language Services sent something that is not JSON.") from None


def _text(args, key="text", limit=MAX_TEXT):
    value = args.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"'{key}' must be a non-empty string.")
    if len(value) > limit:
        raise ToolError(f"'{key}' is longer than {limit} characters.")
    return value.strip()


def _lang(args, key):
    value = args.get(key, "auto")
    if value not in ("auto", "en", "tr"):
        raise ToolError(f"'{key}' must be auto, en or tr.")
    return value


def _check_english(args):
    text = _text(args)
    translated = _request("POST", "/v1/translate", {"text": text, "from": "en", "to": "tr"})
    return _request("POST", "/v1/translate/check", {"text": text, "translation": translated.get("translation", ""),
                                                    "from": "en", "to": "tr"})


def _word(path):
    return lambda args: _request("GET", path + "?" + urllib.parse.urlencode({"word": _text(args, "word", 80)}))


HANDLERS = {
    "translate": lambda a: _request("POST", "/v1/translate",
                                    {"text": _text(a), "from": _lang(a, "from"), "to": _lang(a, "to")}),
    "check_english": _check_english,
    "rewrite_english": lambda a: _request("POST", "/v1/translate/rewrite", {"text": _text(a)}),
    "word_card": _word("/v1/word"),
    "example_sentences": _word("/v1/word/examples"),
}


def call_tool(name, args):
    if name not in HANDLERS:
        raise KeyError(name)
    try:
        result = HANDLERS[name](args if isinstance(args, dict) else {})
    except ToolError as e:
        return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
            "structuredContent": result if isinstance(result, dict) else {"result": result}, "isError": False}


def handle(msg):
    """One JSON-RPC message in, the response out (None for notifications)."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid request"}}
    if "id" not in msg:
        return None  # notifications (initialized, cancelled) need no answer
    mid, method, params = msg["id"], msg["method"], msg.get("params") or {}

    def ok(result):
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}

    if method == "initialize":
        asked = params.get("protocolVersion")
        return ok({"protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                   "capabilities": {"tools": {"listChanged": False}}, "serverInfo": SERVER_INFO,
                   "instructions": "Local English-Turkish tools. Dictionary data is reliable; translations, checks "
                                   "and rewrites come from a local language model and may be wrong."})
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": TOOLS})
    if method == "tools/call":
        try:
            return ok(call_tool(params.get("name"), params.get("arguments")))
        except KeyError:
            return err(-32602, f"Unknown tool: {params.get('name')}")
    return err(-32601, f"Method not found: {method}")


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
