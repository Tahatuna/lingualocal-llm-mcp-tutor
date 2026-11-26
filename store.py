"""Your data: lookup history and saved words and sentences, in
~/Library/Application Support/LinguaLocal/deck.sqlite (LL_DATA_DIR overrides it for tests). A Mac that ran the app
under its first name (Pronunciation Mirror) keeps using that folder, so no data is moved or lost.

The tables are the ones earlier versions created, so existing data carries over; the review columns of `cards` are
no longer used.
"""
import contextlib
import os
import sqlite3
import threading
import time

APP_SUPPORT = os.path.expanduser("~/Library/Application Support")


def default_data_dir(app_support=APP_SUPPORT):
    new, old = os.path.join(app_support, "LinguaLocal"), os.path.join(app_support, "Pronunciation Mirror")
    return old if os.path.isdir(old) and not os.path.isdir(new) else new


DATA_DIR = os.environ.get("LL_DATA_DIR") or default_data_dir()
DB_PATH = os.path.join(DATA_DIR, "deck.sqlite")
MAX_TEXT = 600
MAX_CHAT = 4000
CHAT_KEEP = 500  # the newest messages kept per chat; older ones are dropped so a chat cannot grow without bound
MAX_TITLE = 80
AUTO_TITLE = 40  # an unnamed chat is called after the start of its first question
KINDS = ("word", "sentence")
LANGS = ("en", "tr")
_lock = threading.Lock()


def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=5)
    con.row_factory = sqlite3.Row
    con.executescript("""
    PRAGMA journal_mode=WAL;
    CREATE TABLE IF NOT EXISTS cards (
      word TEXT PRIMARY KEY, accent TEXT DEFAULT 'us', tr TEXT DEFAULT '', ipa TEXT DEFAULT '', image TEXT DEFAULT '',
      added REAL, state TEXT DEFAULT 'new', step INTEGER DEFAULT 0, due REAL, ivl REAL DEFAULT 0,
      ease REAL DEFAULT 2.5, reps INTEGER DEFAULT 0, lapses INTEGER DEFAULT 0, last REAL);
    CREATE TABLE IF NOT EXISTS phrases (
      id INTEGER PRIMARY KEY, text TEXT NOT NULL UNIQUE CHECK (length(text) BETWEEN 1 AND 600),
      tr TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
      created_at REAL NOT NULL, updated_at REAL NOT NULL,
      state TEXT NOT NULL DEFAULT 'new', step INTEGER DEFAULT 0, due REAL, ivl REAL DEFAULT 0,
      ease REAL DEFAULT 2.5, reps INTEGER DEFAULT 0, lapses INTEGER DEFAULT 0, last REAL);
    CREATE TABLE IF NOT EXISTS history (
      id INTEGER PRIMARY KEY, text TEXT NOT NULL UNIQUE CHECK (length(text) BETWEEN 1 AND 600),
      kind TEXT NOT NULL CHECK (kind IN ('word', 'sentence')), result TEXT NOT NULL DEFAULT '',
      count INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL, updated_at REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS history_recent ON history(updated_at);
    CREATE TABLE IF NOT EXISTS chat (
      id INTEGER PRIMARY KEY, role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
      content TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 4000), created_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS chats (
      id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT '' CHECK (length(title) <= 80),
      created_at REAL NOT NULL, updated_at REAL NOT NULL);
    """)
    _migrate(con)
    return con


def _columns(con, table):
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}


def _migrate(con):
    """Forward-only and idempotent: the input language of a lookup, and chats kept side by side."""
    with con:
        if "lang" not in _columns(con, "history"):
            con.execute("ALTER TABLE history ADD COLUMN lang TEXT NOT NULL DEFAULT ''")
        if "chat_id" not in _columns(con, "chat"):
            if con.execute("SELECT 1 FROM chat LIMIT 1").fetchone():  # existing chat is moved: keep a copy first
                copy = sqlite3.connect(os.path.join(DATA_DIR, "deck.before-chats.sqlite"))
                try:
                    con.backup(copy)
                finally:
                    copy.close()
            con.execute("ALTER TABLE chat ADD COLUMN chat_id INTEGER REFERENCES chats(id)")
            con.execute("CREATE INDEX IF NOT EXISTS chat_by_chat ON chat(chat_id, id)")
        # The one conversation earlier versions kept becomes the first saved chat.
        if con.execute("SELECT 1 FROM chat WHERE chat_id IS NULL LIMIT 1").fetchone():
            first = con.execute("SELECT content FROM chat WHERE chat_id IS NULL AND role='user' ORDER BY id LIMIT 1").fetchone()
            times = con.execute("SELECT MIN(created_at), MAX(created_at) FROM chat WHERE chat_id IS NULL").fetchone()
            cid = con.execute("INSERT INTO chats(title, created_at, updated_at) VALUES(?,?,?)",
                              (_auto_title(first[0] if first else ""), times[0], times[1])).lastrowid
            con.execute("UPDATE chat SET chat_id=? WHERE chat_id IS NULL", (cid,))


def _auto_title(text):
    text = " ".join(str(text or "").split())
    return text if len(text) <= AUTO_TITLE else text[:AUTO_TITLE - 1].rstrip() + "…"


@contextlib.contextmanager
def _conn():
    """One transaction on a connection that is closed afterwards (a long-running server must not leak them)."""
    con = _db()
    try:
        with con:
            yield con
    finally:
        con.close()


# ---------------------------------------------------------------- history

HISTORY_COLS = "id, text, kind, result, lang, count, updated_at"


def history_list():
    with _lock, _conn() as con:
        return [dict(r) for r in con.execute(f"SELECT {HISTORY_COLS} FROM history ORDER BY updated_at DESC")]


def history_add(text, kind, result="", lang=""):
    """Adds the lookup or moves it to the top; a non-empty result or language replaces the stored one.
    lang is the language of `text` ('en' / 'tr'; '' for lookups saved before it was kept)."""
    now = time.time()
    with _lock, _conn() as con:
        con.execute("""INSERT INTO history(text, kind, result, lang, created_at, updated_at) VALUES(?,?,?,?,?,?)
                       ON CONFLICT(text) DO UPDATE SET count=history.count+1, updated_at=excluded.updated_at,
                         kind=excluded.kind,
                         result=CASE WHEN excluded.result!='' THEN excluded.result ELSE history.result END,
                         lang=CASE WHEN excluded.lang!='' THEN excluded.lang ELSE history.lang END""",
                    (text, kind, result, lang, now, now))
        return dict(con.execute(f"SELECT {HISTORY_COLS} FROM history WHERE text=?", (text,)).fetchone())


def history_remove(hid):
    with _lock, _conn() as con:
        con.execute("DELETE FROM history WHERE id=?", (hid,))


def history_clear():
    with _lock, _conn() as con:
        return con.execute("DELETE FROM history").rowcount


# ---------------------------------------------------------------- saved words and sentences

def saved_list():
    with _lock, _conn() as con:
        words = [{"text": r["word"], "tr": r["tr"], "saved_at": r["added"]}
                 for r in con.execute("SELECT word, tr, added FROM cards ORDER BY added DESC")]
        sentences = [{"text": r["text"], "tr": r["tr"], "saved_at": r["created_at"]}
                     for r in con.execute("SELECT text, tr, created_at FROM phrases ORDER BY created_at DESC")]
    return {"words": words, "sentences": sentences}


def save(kind, text, tr=""):
    now = time.time()
    with _lock, _conn() as con:
        if kind == "word":
            con.execute("""INSERT INTO cards(word, tr, added, due) VALUES(?,?,?,?)
                           ON CONFLICT(word) DO UPDATE SET tr=CASE WHEN excluded.tr!='' THEN excluded.tr ELSE cards.tr END""",
                        (text, tr, now, now))
        else:
            con.execute("""INSERT INTO phrases(text, tr, created_at, updated_at, due) VALUES(?,?,?,?,?)
                           ON CONFLICT(text) DO UPDATE SET tr=CASE WHEN excluded.tr!='' THEN excluded.tr ELSE phrases.tr END,
                             updated_at=excluded.updated_at""", (text, tr, now, now, now))


def unsave(kind, text):
    with _lock, _conn() as con:
        if kind == "word":
            con.execute("DELETE FROM cards WHERE word=?", (text,))
        else:
            con.execute("DELETE FROM phrases WHERE text=?", (text,))


# ---------------------------------------------------------------- teacher chats (kept side by side, each with a name)

CHAT_COLS = """c.id, c.title, c.created_at, c.updated_at,
               (SELECT COUNT(*) FROM chat m WHERE m.chat_id=c.id) AS count"""


def chats_list():
    """Newest activity first."""
    with _lock, _conn() as con:
        return [dict(r) for r in con.execute(f"SELECT {CHAT_COLS} FROM chats c ORDER BY c.updated_at DESC, c.id DESC")]


def _chat(con, cid):
    row = con.execute(f"SELECT {CHAT_COLS} FROM chats c WHERE c.id=?", (cid,)).fetchone()
    return dict(row) if row else None


def chat_new(title=""):
    now = time.time()
    with _lock, _conn() as con:
        cid = con.execute("INSERT INTO chats(title, created_at, updated_at) VALUES(?,?,?)",
                          (title[:MAX_TITLE], now, now)).lastrowid
        return _chat(con, cid)


def chat_rename(cid, title):
    """An empty title gives the chat back its automatic name (the start of its first question)."""
    with _lock, _conn() as con:
        if not title:
            first = con.execute("SELECT content FROM chat WHERE chat_id=? AND role='user' ORDER BY id LIMIT 1", (cid,)).fetchone()
            title = _auto_title(first[0] if first else "")
        con.execute("UPDATE chats SET title=? WHERE id=?", (title[:MAX_TITLE], cid))
        return _chat(con, cid)


def chat_delete(cid):
    """Deletes the chat and its messages; returns how many messages went."""
    with _lock, _conn() as con:
        n = con.execute("DELETE FROM chat WHERE chat_id=?", (cid,)).rowcount
        con.execute("DELETE FROM chats WHERE id=?", (cid,))
        return n


def chat_list(cid):
    with _lock, _conn() as con:
        rows = con.execute("SELECT id, role, content, created_at FROM chat WHERE chat_id=? ORDER BY id", (cid,)).fetchall()
    return [dict(r) for r in rows]


def chat_add(cid, role, content):
    """Adds a message to the chat; None if there is no such chat. An unnamed chat takes its first question as its name."""
    now = time.time()
    with _lock, _conn() as con:
        chat = con.execute("SELECT title FROM chats WHERE id=?", (cid,)).fetchone()
        if not chat:
            return None
        cur = con.execute("INSERT INTO chat(chat_id, role, content, created_at) VALUES(?,?,?,?)", (cid, role, content, now))
        title = chat["title"] or (_auto_title(content) if role == "user" else "")
        con.execute("UPDATE chats SET updated_at=?, title=? WHERE id=?", (now, title, cid))
        con.execute("""DELETE FROM chat WHERE chat_id=? AND id NOT IN
                       (SELECT id FROM chat WHERE chat_id=? ORDER BY id DESC LIMIT ?)""", (cid, cid, CHAT_KEEP))
        return dict(con.execute("SELECT id, role, content, created_at FROM chat WHERE id=?", (cur.lastrowid,)).fetchone())
