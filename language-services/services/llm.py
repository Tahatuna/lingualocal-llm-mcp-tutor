"""The local language model (Ollama), behind a priority queue.

Ollama answers one request at a time on this machine: a short translation measured 23.5 s when it waited behind a
long word-card request. So every call goes through one queue: translations first, then sentence checks, then word
cards. When a translation arrives while a slower request is running, that request is cut off (closing its connection
makes Ollama stop generating) and its caller gets 503: the translation is what the person is waiting for.
"""
import heapq
import http.client
import itertools
import json
import threading
import urllib.error
import urllib.parse
import urllib.request

from . import config

PRIORITY = {"translate": 0, "check": 1, "chat": 1, "card": 2}
MAX_BYTES = 256 * 1024
TEMPERATURE = 0.1  # dictionary facts and faithful translation, not creative writing


class _Queue:
    def __init__(self):
        self._heap, self._count = [], itertools.count()
        self._cv = threading.Condition()
        self.running = None  # (priority, connection) of the request Ollama is working on
        threading.Thread(target=self._work, daemon=True, name="llm-queue").start()

    def run(self, priority, fn):
        prio = PRIORITY[priority]
        job = {"fn": fn, "done": threading.Event(), "result": None, "prio": prio, "conn": None}
        with self._cv:
            heapq.heappush(self._heap, (prio, next(self._count), job))
            running = self.running
            if running and prio < running["prio"] and running["conn"] is not None:
                running["preempted"] = True
                _close(running["conn"])  # Ollama stops generating when the client goes away
            self._cv.notify()
        job["done"].wait()
        return job["result"]

    def _work(self):
        while True:
            with self._cv:
                while not self._heap:
                    self._cv.wait()
                _, _, job = heapq.heappop(self._heap)
                self.running = job
            try:
                job["result"] = job["fn"](job)
                if job.get("preempted"):
                    job["result"] = (503, {"error": "Stopped for a newer translation. Ask again."})
            except Exception as e:  # noqa: BLE001 - a failed job must not stop the queue; the caller gets the error
                job["result"] = (500, {"error": f"model error: {type(e).__name__}"})
            with self._cv:
                self.running = None
            job["done"].set()


_queue = _Queue()


def _close(conn):
    try:
        conn.sock and conn.sock.shutdown(2)
    except OSError:
        pass  # already closed


def _post(messages, fmt=None, max_tokens=None, timeout=120, job=None, temperature=TEMPERATURE):
    body = {"model": config.OLLAMA_MODEL, "stream": False, "keep_alive": config.OLLAMA_KEEP_ALIVE,
            "options": {"temperature": temperature}, "messages": messages}
    if fmt is not None:
        body["format"] = fmt
    if max_tokens:
        body["options"]["num_predict"] = max_tokens
    url = urllib.parse.urlparse(config.OLLAMA_URL)
    # http.client instead of urlopen: the queue needs the connection to cut a request off.
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=timeout)
    if job is not None:
        job["conn"] = conn
    try:
        conn.request("POST", "/api/chat", json.dumps(body), {"Content-Type": "application/json"})
        r = conn.getresponse()
        raw = r.read(MAX_BYTES + 1)
        if r.status == 404:
            return 503, {"error": f"The model {config.OLLAMA_MODEL} is not installed. Run: ollama pull {config.OLLAMA_MODEL}"}
        if r.status != 200:
            return 502, {"error": "The model failed."}
    except (ConnectionError, http.client.HTTPException, OSError) as e:
        if isinstance(e, TimeoutError):
            return 504, {"error": "The model took too long."}
        return 503, {"error": "The local model is not running. Open the Ollama app."}
    finally:
        conn.close()
    if len(raw) > MAX_BYTES:
        return 502, {"error": "The model's answer was too long."}
    try:
        return 200, json.loads(raw)["message"]["content"]
    except (ValueError, KeyError, TypeError):
        return 502, {"error": "The model gave no usable answer."}


def chat(messages, priority, max_tokens=400, temperature=TEMPERATURE):
    """Plain text answer to a message list (system, examples, user). Returns (status, text_or_error)."""
    return _queue.run(priority, lambda job: _post(messages, max_tokens=max_tokens, job=job, temperature=temperature))


def text(system, user, priority, max_tokens=400):
    """Plain text answer. Returns (status, text_or_error)."""
    return _queue.run(priority, lambda job: _post([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                                  max_tokens=max_tokens, job=job))


def structured(system, schema, user, priority, max_tokens=900):
    """JSON answer constrained to schema. Returns (status, dict_or_error)."""
    def call(job):
        status, content = _post([{"role": "system", "content": system + " Answer only with JSON matching this schema: "
                                  + json.dumps(schema)}, {"role": "user", "content": user}], fmt=schema, max_tokens=max_tokens,
                                job=job)
        if status != 200:
            return status, content
        try:
            data = json.loads(content)
        except ValueError:
            return 502, {"error": "The model gave no usable answer."}
        return (200, data) if isinstance(data, dict) else (502, {"error": "The model gave no usable answer."})
    return _queue.run(priority, call)


def warm():
    """Loads the model into memory in the background (an empty request), so the first real one is fast."""
    def go():
        _post([{"role": "user", "content": "hi"}], max_tokens=1, timeout=120)
    if available():
        threading.Thread(target=go, daemon=True).start()


def available():
    try:
        with urllib.request.urlopen(config.OLLAMA_URL + "/api/version", timeout=1):
            return True
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return False
