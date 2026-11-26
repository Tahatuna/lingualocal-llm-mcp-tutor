"""The dictionaries built into macOS, read through Dictionary Services (services/jxa/dictionary.js):

    New Oxford American Dictionary   meanings in order of frequency, examples, grammar notes, phrases,
                                     phrasal verbs, derivatives
    Oxford Turkish Dictionary        human Turkish equivalents per meaning, example phrases, Turkish -> English

These are the most reliable sources on this machine, so the word card prefers them to the language model. Lookups
take ~0.1 s for a batch and are cached on disk. On a Mac without these dictionaries every function returns empty
results and the card falls back to its other sources.
"""
import html.parser
import json
import os
import re
import subprocess

from . import cache

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jxa", "dictionary.js")
NOAD, OXTR = "New Oxford American", "Oxford Turkish"
TIMEOUT = 10


# ---------------------------------------------------------------- tiny DOM

class _Node:
    __slots__ = ("tag", "cls", "attrs", "kids", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.cls = set((self.attrs.get("class") or "").split())
        self.kids = []

    def text(self):
        out = ""
        for k in self.kids:
            piece = k if isinstance(k, str) else k.text()
            # The dictionary data sometimes glues a bold word to the one before it ("the checkgiven to").
            if not isinstance(k, str) and "bold" in k.cls and out[-1:].isalnum() and piece[:1].isalnum():
                out += " "
            out += piece
        return out

    def find_all(self, cls=None, tag=None, stop=None):
        """Descendants with class cls (and tag), not descending into nodes that have class stop."""
        out = []
        for k in self.kids:
            if isinstance(k, str):
                continue
            if (cls is None or cls in k.cls) and (tag is None or k.tag == tag):
                out.append(k)
            if stop is None or stop not in k.cls:
                out += k.find_all(cls, tag, stop)
        return out

    def find(self, cls=None, tag=None, stop=None):
        found = self.find_all(cls, tag, stop)
        return found[0] if found else None


class _Builder(html.parser.HTMLParser):
    VOID = {"meta", "br", "img", "link", "base", "hr", "input"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = _Node("root", [], None)

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.cur)
        self.cur.kids.append(node)
        if tag not in self.VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.kids.append(_Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not None and n.tag != tag:
            n = n.parent
        if n is not None and n.parent is not None:
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.kids.append(data)


def _dom(html_text):
    b = _Builder()
    b.feed(html_text)
    return b.root


def _t(node):
    return re.sub(r"\s+", " ", node.text()).strip() if node is not None else ""


# ---------------------------------------------------------------- lookup

def _raw(words, dicts):
    """{word: {dict: [html, ...]}} for words not yet cached; one osascript call for the whole batch."""
    if not words:
        return {}
    try:
        out = subprocess.run(["osascript", "-l", "JavaScript", SCRIPT, json.dumps({"words": words, "dicts": dicts})],
                             capture_output=True, text=True, timeout=TIMEOUT)
        return json.loads(out.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}


def lookup(words, kind):
    """Parsed entries for each word from one dictionary (kind = NOAD or OXTR). Cached per word."""
    parse = parse_noad if kind == NOAD else parse_turkish
    result, missing = {}, []
    for w in words:
        hit = cache.get_json("dict-" + kind, w)
        if hit is None:
            missing.append(w)
        else:
            result[w] = hit
    raw = _raw(missing, [kind])
    for w in missing:
        if w not in raw:
            continue  # the lookup failed: not cached, try again next time
        entries = [parse(h) for h in raw[w].get(kind, [])]
        entries = [e for e in entries if e]
        result[w] = entries
        cache.put_json("dict-" + kind, w, entries)
    return result


# ---------------------------------------------------------------- Oxford Turkish

TURKISH_POS = {"isim", "fiil", "sıfat", "zarf", "ünlem", "edat", "bağlaç", "zamir", "sayı", "önek", "sonek"}


def is_turkish_entry(e):
    """The Turkish-English half of the dictionary labels parts of speech in Turkish ('isim', 'fiil')."""
    return any(b["pos"].split(" ")[0] in TURKISH_POS for b in e.get("blocks", []))


def english_to_turkish(word):
    return [e for e in lookup([word], OXTR).get(word, []) if not is_turkish_entry(e)]


def turkish_to_english(word):
    return [e for e in lookup([word], OXTR).get(word, []) if is_turkish_entry(e)]


def first_turkish(words):
    """{word: 'main Turkish equivalent'} for a batch of English words or phrases (empty when not in the dictionary)."""
    out = {}
    for w, entries in lookup(words, OXTR).items():
        for e in entries:
            if is_turkish_entry(e) or e["headword"].lower() != w.lower():
                continue
            trs = [t["tr"] for b in e["blocks"] for s in b["senses"] for t in s["tr"]]
            if trs:
                out[w] = ", ".join(dict.fromkeys(trs[:2]))
                break
    return out

def parse_turkish(html_text):
    root = _dom(html_text)
    entry = root.find("entry")
    if entry is None:
        return None
    hw = _t(entry.find("hw")).rstrip("0123456789 ").strip()
    blocks = []
    for g in entry.find_all("gramb"):
        senses = []
        for sem in g.find_all("semb"):
            trs = []
            for trg in sem.find_all("trg", stop="exg"):
                tr = _t(trg.find("trans"))
                if tr:
                    trs.append({"tr": tr.strip(" ;,"), "for": _t(trg.find("ind"))})
            exs = [{"en": _t(x.find("ex")), "tr": _t(x.find("trans"))} for x in sem.find_all("exg")]
            if trs or exs:
                senses.append({"tr": trs, "examples": [e for e in exs if e["en"] and e["tr"]]})
        if senses:
            blocks.append({"pos": _t(g.find("ps")), "senses": senses})
    xrefs = [_t(a) for a in entry.find_all(tag="a")]
    return {"headword": hw, "ipa_uk": _t(entry.find("ph")), "blocks": blocks, "related": [x for x in xrefs if x]}


# ---------------------------------------------------------------- New Oxford American

def _noad_sense(ms):
    df = _t(ms.find("df", stop="msDict"))
    if not df:
        return None
    grammar = [_t(g).strip("[] ") for g in ms.find_all("gg", stop="eg")]
    exs = [_t(e).lstrip(": ").strip() for e in ms.find_all("ex")]
    return {"def": df, "grammar": [g for g in grammar if g][:2], "examples": [e for e in exs if e][:3],
            "register": _t(ms.find("lg", stop="eg")) or _t(ms.find("reg", stop="eg"))}


def parse_noad(html_text):
    root = _dom(html_text)
    entry = root.find("entry")
    if entry is None:
        return None
    hw = _t(entry.find("hw")).replace("·", "").strip()
    blocks = []
    for se1 in entry.find_all("se1", stop="subEntryBlock"):
        pos = _t(se1.find("pos"))
        senses = []
        for se2 in se1.find_all("se2") or [se1]:
            core = se2.find("t_first") or se2.find("t_core")
            main = _noad_sense(core) if core is not None else None
            if not main:
                continue
            main["sub"] = [s for s in (_noad_sense(x) for x in se2.find_all("t_subsense")) if s][:3]
            senses.append(main)
        if senses:
            blocks.append({"pos": pos, "senses": senses})
    sections = {}
    for block in entry.find_all("subEntryBlock"):
        name = next((c[2:] for c in block.cls if c.startswith("t_")), "")
        items = []
        for sub in block.find_all("subEntry"):
            head = _t(sub.find("l")) or _t(sub.find("x_xoh"))
            ms = sub.find("msDict")
            sense = _noad_sense(ms) if ms is not None else None
            pos = _t(sub.find("pos"))
            if head:
                items.append({"phrase": head, "pos": pos, "def": sense["def"] if sense else "",
                              "example": sense["examples"][0] if sense and sense["examples"] else ""})
        sections[name] = items
    return {"headword": hw, "blocks": blocks, "phrases": sections.get("phrases", []),
            "phrasal_verbs": sections.get("phrasalVerbs", []), "derivatives": sections.get("derivatives", [])}
