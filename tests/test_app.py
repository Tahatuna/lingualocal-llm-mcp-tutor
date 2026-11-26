"""LinguaLocal tests: your data (history, saved), the server's guards and the page script.
Temporary data folder and port; no network.

    python3 -m unittest discover tests
"""
import http.client
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest

TMP = tempfile.mkdtemp(prefix="pm-test-")
os.environ["LL_DATA_DIR"] = TMP
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import server  # noqa: E402
import store  # noqa: E402


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class StoreTest(unittest.TestCase):
    def setUp(self):
        store.history_clear()

    def test_history_newest_first_kept_until_cleared(self):
        for i in range(150):  # no size limit
            store.history_add(f"word{i}", "word", f"tr{i}")
        store.history_add("word3", "word", "")  # a repeat moves to the top and keeps its result
        items = store.history_list()
        self.assertEqual((len(items), items[0]["text"], items[0]["result"]), (150, "word3", "tr3"))
        self.assertEqual(store.history_clear(), 150)

    def test_save_and_remove(self):
        store.save("word", "avoid", "kaçınmak")
        store.save("sentence", "I missed the bus.", "Otobüsü kaçırdım.")
        s = store.saved_list()
        self.assertIn(("avoid", "kaçınmak"), [(w["text"], w["tr"]) for w in s["words"]])
        self.assertIn("Otobüsü kaçırdım.", [x["tr"] for x in s["sentences"]])
        store.unsave("word", "avoid")
        self.assertNotIn("avoid", [w["text"] for w in store.saved_list()["words"]])


class MigrationTest(unittest.TestCase):
    def test_the_old_single_chat_becomes_a_named_chat_with_a_backup(self):
        import sqlite3
        old = tempfile.mkdtemp(prefix="pm-old-")
        try:
            con = sqlite3.connect(os.path.join(old, "deck.sqlite"))
            con.executescript("""
              CREATE TABLE history (id INTEGER PRIMARY KEY, text TEXT NOT NULL UNIQUE, kind TEXT NOT NULL,
                result TEXT NOT NULL DEFAULT '', count INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL, updated_at REAL NOT NULL);
              INSERT INTO history(text, kind, result, created_at, updated_at) VALUES('avoid', 'word', 'kaçınmak', 1, 1);
              CREATE TABLE chat (id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL, created_at REAL NOT NULL);
              INSERT INTO chat(role, content, created_at) VALUES('assistant', 'Hi', 10), ('user', 'Check my sentence please', 11);""")
            con.commit(); con.close()
            saved = store.DATA_DIR, store.DB_PATH
            store.DATA_DIR, store.DB_PATH = old, os.path.join(old, "deck.sqlite")
            try:
                chats = store.chats_list()
                store.chats_list()  # running again changes nothing
                self.assertEqual([(c["title"], c["count"]) for c in store.chats_list()], [("Check my sentence please", 2)])
                self.assertEqual([m["content"] for m in store.chat_list(chats[0]["id"])], ["Hi", "Check my sentence please"])
                self.assertEqual(store.history_list()[0]["lang"], "")
                self.assertTrue(os.path.exists(os.path.join(old, "deck.before-chats.sqlite")))
            finally:
                store.DATA_DIR, store.DB_PATH = saved
        finally:
            shutil.rmtree(old, ignore_errors=True)


class DataFolderTest(unittest.TestCase):
    """The app was renamed: a Mac that already has data under the first name must keep using it."""

    def test_existing_data_under_the_old_name_is_kept(self):
        with tempfile.TemporaryDirectory() as support:
            self.assertEqual(store.default_data_dir(support), os.path.join(support, "LinguaLocal"))  # new Mac
            os.mkdir(os.path.join(support, "Pronunciation Mirror"))
            self.assertEqual(store.default_data_dir(support), os.path.join(support, "Pronunciation Mirror"))
            os.mkdir(os.path.join(support, "LinguaLocal"))  # once the new folder exists, it wins
            self.assertEqual(store.default_data_dir(support), os.path.join(support, "LinguaLocal"))


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        server.PORT = cls.port
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def req(self, method, path, body=None, host=None, pm=True):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": host or f"localhost:{self.port}", "Content-Type": "application/json"}
        if pm:
            h["X-LL"] = "1"
        c.request(method, path, json.dumps(body) if body is not None else None, h)
        r = c.getresponse()
        out = r.status, r.read(), dict(r.getheaders())
        c.close()
        return out

    def test_page_has_csp_and_no_inline_script(self):
        st, body, h = self.req("GET", "/")
        self.assertEqual(st, 200)
        self.assertIn("script-src 'self'", h["Content-Security-Policy"])
        self.assertNotIn(b"<script>", body)  # only <script type=module src=...>
        self.assertNotIn(b'style="', body)

    def test_foreign_host_and_missing_header_refused(self):
        self.assertEqual(self.req("GET", "/api/history", host="evil.example")[0], 403)
        self.assertEqual(self.req("POST", "/api/history/clear", {}, pm=False)[0], 403)

    def test_only_listed_files_are_served(self):
        self.assertEqual(self.req("GET", "/store.py")[0], 404)
        self.assertEqual(self.req("GET", "/../store.py")[0], 404)

    def test_saved_roundtrip(self):
        st, body, _ = self.req("POST", "/api/saved/add", {"kind": "word", "text": "Think", "tr": "düşünmek"})
        self.assertEqual((st, json.loads(body)["words"][0]["text"]), (200, "think"))
        self.assertEqual(self.req("POST", "/api/saved/add", {"kind": "<b>", "text": "x"})[0], 400)

    def test_chats_are_kept_side_by_side_renamed_and_deleted(self):
        st, body, _ = self.req("POST", "/api/chats/new", {})
        first = json.loads(body)["id"]
        st, body, _ = self.req("POST", "/api/chat/add", {"chat_id": first, "role": "user", "content": "Line one\nLine two\x07"})
        self.assertEqual((st, json.loads(body)["content"]), (200, "Line one\nLine two"))
        self.assertEqual(self.req("POST", "/api/chat/add", {"chat_id": first, "role": "system", "content": "x"})[0], 400)
        self.assertEqual(self.req("POST", "/api/chat/add", {"chat_id": first, "role": "user", "content": "  "})[0], 400)
        self.assertEqual(self.req("POST", "/api/chat/add", {"chat_id": 999999, "role": "user", "content": "x"})[0], 404)
        self.assertEqual(self.req("POST", "/api/chat/add", {"role": "user", "content": "x"})[0], 400)
        # a new chat does not lose the first one
        second = json.loads(self.req("POST", "/api/chats/new", {})[1])["id"]
        self.req("POST", "/api/chat/add", {"chat_id": second, "role": "user", "content": "Second chat"})
        self.assertEqual(len(json.loads(self.req("GET", f"/api/chat?id={first}")[1])), 1)
        self.assertEqual(json.loads(self.req("GET", f"/api/chat?id={second}")[1])[0]["content"], "Second chat")
        self.assertEqual(self.req("GET", "/api/chat?id=x")[0], 400)
        chats = {c["id"]: c for c in json.loads(self.req("GET", "/api/chats")[1])}
        self.assertEqual((chats[first]["title"], chats[first]["count"]), ("Line one Line two", 1))  # named after the first question
        # renaming keeps the name; an empty name gives the automatic one back
        st, body, _ = self.req("POST", "/api/chats/rename", {"id": first, "title": "Passive <b>practice</b>\x07"})
        self.assertEqual((st, json.loads(body)["title"]), (200, "Passive <b>practice</b>"))
        self.req("POST", "/api/chat/add", {"chat_id": first, "role": "user", "content": "more"})
        self.assertEqual(json.loads(self.req("GET", "/api/chats")[1])[0]["title"], "Passive <b>practice</b>")  # newest first
        self.assertEqual(json.loads(self.req("POST", "/api/chats/rename", {"id": first, "title": ""})[1])["title"], "Line one Line two")
        self.assertEqual(self.req("POST", "/api/chats/rename", {"id": 999999, "title": "x"})[0], 404)
        st, body, _ = self.req("POST", "/api/chats/delete", {"id": first})
        self.assertEqual((st, json.loads(body)["removed"]), (200, 2))
        self.assertEqual(json.loads(self.req("GET", f"/api/chat?id={first}")[1]), [])
        self.assertIn(second, [c["id"] for c in json.loads(self.req("GET", "/api/chats")[1])])
        store.chat_delete(second)

    def test_long_names_are_shortened(self):
        cid = store.chat_new()["id"]
        store.chat_add(cid, "assistant", "Hello")  # the teacher speaking first does not name the chat
        self.assertEqual(store.chat_rename(cid, "")["title"], "")
        store.chat_add(cid, "user", "word " * 30)
        title = [c for c in store.chats_list() if c["id"] == cid][0]["title"]
        self.assertTrue(len(title) <= store.AUTO_TITLE and title.endswith("…"), title)
        self.assertEqual(len(store.chat_rename(cid, "x" * 200)["title"]), store.MAX_TITLE)
        store.chat_delete(cid)

    def test_a_chat_keeps_only_its_newest_messages(self):
        a, b = store.chat_new()["id"], store.chat_new()["id"]
        store.chat_add(b, "user", "other chat")
        for i in range(store.CHAT_KEEP + 5):
            store.chat_add(a, "user", f"m{i}")
        rows = store.chat_list(a)
        self.assertEqual((len(rows), rows[-1]["content"]), (store.CHAT_KEEP, f"m{store.CHAT_KEEP + 4}"))
        self.assertEqual(len(store.chat_list(b)), 1)  # the limit is per chat
        store.chat_delete(a); store.chat_delete(b)

    def test_history_keeps_the_input_language(self):
        st, body, _ = self.req("POST", "/api/history/add", {"text": "kitap", "kind": "word", "result": "book", "lang": "tr"})
        self.assertEqual(json.loads(body)["lang"], "tr")
        body = self.req("POST", "/api/history/add", {"text": "kitap", "kind": "word", "lang": "xx"})[1]
        self.assertEqual(json.loads(body)["lang"], "tr")  # an unknown language does not overwrite the known one

    def test_remove_one_history_item(self):
        self.req("POST", "/api/history/add", {"text": "keep me", "kind": "word"})
        st, body, _ = self.req("POST", "/api/history/add", {"text": "remove me", "kind": "word"})
        self.assertEqual(self.req("POST", "/api/history/remove", {"id": json.loads(body)["id"]})[0], 200)
        texts = [h["text"] for h in json.loads(self.req("GET", "/api/history")[1])]
        self.assertIn("keep me", texts)
        self.assertNotIn("remove me", texts)

    def test_mouth_script_is_served(self):
        st, body, h = self.req("GET", "/mouth.js")
        self.assertEqual(st, 200)
        self.assertIn(b"export function mountMouth", body)

    def test_config_points_to_services(self):
        st, body, _ = self.req("GET", "/config.js")
        self.assertIn(b"export const SERVICES", body)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class ScriptTest(unittest.TestCase):
    """The page scripts, run in Node (no browser, no server)."""

    def node(self, code):
        r = subprocess.run(["node", "--input-type=module", "-e", f"import * as chat from 'file://{ROOT}/chat.js';" + code],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_quiz_asks_only_saved_words_with_a_meaning(self):
        saved = [{"text": "avoid", "tr": "kaçınmak"}, {"text": "commute", "tr": "işe gidip gelmek"},
                 {"text": "bicycle bay", "tr": ""}, {"text": "", "tr": "boş"}]
        picks = self.node(f"const pool = chat.quizPool({json.dumps(saved)}); let last = null, out = [];"
                          "for (let i = 0; i < 200; i++) { const w = chat.pickWord(pool, last); out.push([w.text, w.text === last]); last = w.text; }"
                          "console.log(JSON.stringify(out));")
        self.assertEqual({w for w, _ in picks}, {"avoid", "commute"})  # never a word without Turkish, never an unsaved one
        self.assertFalse(any(repeat for _, repeat in picks))         # never the same word twice in a row

    def test_quiz_with_one_word_and_with_none(self):
        self.assertEqual(self.node("console.log(JSON.stringify([chat.pickWord([{text:'a',tr:'b'}], 'a').text,"
                                   " chat.pickWord([], null) ?? null]))"), ["a", None])

    def test_quiz_grading_is_done_by_code(self):
        cases = [({"toTurkish": True, "tr": "kaçınmak, sakınmak", "word": "avoid"}, "  SAKINMAK! ", True),
                 ({"toTurkish": True, "tr": "ışık", "word": "light"}, "IŞIK", True),       # Turkish İ/ı casing
                 ({"toTurkish": True, "tr": "kaçınmak", "word": "avoid"}, "kaçmak", False),
                 ({"toTurkish": False, "tr": "kaçınmak", "word": "Look forward to"}, "look forward to.", True),
                 ({"toTurkish": False, "tr": "kaçınmak", "word": "avoid"}, "evade", False)]
        got = self.node(f"console.log(JSON.stringify({json.dumps([[q, a] for q, a, _ in cases])}.map(([q, a]) => chat.isRightAnswer(q, a))));")
        self.assertEqual(got, [ok for _, _, ok in cases])

    def test_quiz_answers_are_normalised(self):
        got = self.node("const a = chat.alternatives('Koy; cumba, defne');"
                        "console.log(JSON.stringify([a, a.includes(chat.norm('  CUMBA! ')), a.includes(chat.norm('bay')), chat.norm('IŞIK')]));")
        self.assertEqual(got, [["koy", "cumba", "defne"], True, False, "ışık"])

    def test_page_scripts_parse(self):
        for name in ("app.js", "mouth.js", "chat.js"):
            r = subprocess.run(["node", "--check", "--input-type=module"],
                               input=pathlib.Path(ROOT, name).read_text(encoding="utf-8"), capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, name + ": " + r.stderr)


if __name__ == "__main__":
    unittest.main()
