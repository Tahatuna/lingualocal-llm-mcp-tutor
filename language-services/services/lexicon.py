"""The word card: everything a learner needs about one English word, from the most reliable source for each part.

    meanings, Turkish, phrasal verbs, idioms, word family   Oxford dictionaries built into macOS (services/dictionary)
    forms, irregular verbs, the 13 tense rows               rules + the lemminflect lexicon
    -ing / to, stative verbs, prepositions, typical mistakes curated lists and rules (services/grammar_data)
    IPA                                                     Oxford (UK), Wiktionary or the voice's phonemizer (US)
    examples                                                Tatoeba: real sentences with human Turkish translations
    fallback meanings                                       the local model, only for words not in the dictionaries

Everything but the examples is local and returns in well under a second. Each source is cached on disk.
"""
import json
import re
import urllib.parse
import urllib.request

import lemminflect

from . import cache, config, dictionary as dicts, grammar_data, llm, tts

WORD_OK = re.compile(r"^[a-z][a-z' -]{0,39}$")
NET_TIMEOUT = 4      # seconds for the dictionary and Tatoeba
NET_MAX = 512 * 1024
POS_ORDER = ["VERB", "NOUN", "ADJ", "ADV", "AUX"]
POS_NAME = {"VERB": "verb", "NOUN": "noun", "ADJ": "adjective", "ADV": "adverb", "AUX": "verb"}


def normalize(word):
    w = re.sub(r"\s+", " ", str(word or "").strip().lower().replace("’", "'"))
    return w if WORD_OK.match(w) else None


# ---------------------------------------------------------------- base (instant)

def _pos(lemma):
    """Parts of speech in which the word is itself the dictionary form ('thought' is a noun; as a verb it is 'think')."""
    if " " in lemma:
        return ["VERB"] if lemminflect.getAllLemmas(lemma.split(" ")[0]).get("VERB") else []
    found = lemminflect.getAllLemmas(lemma)
    out = [p for p in POS_ORDER if p in found and lemma in found[p]]
    return ["VERB" if p == "AUX" else p for p in out if not (p == "AUX" and "VERB" in out)]


def also_form_of(word):
    """'thought' -> [('think', 'verb')]: other words this one is an inflected form of."""
    if " " in word:
        return []
    return [(v[0], POS_NAME[p]) for p, v in lemminflect.getAllLemmas(word).items() if v[0] != word]


def lemma_of(word):
    """The dictionary form: 'went' -> 'go', 'children' -> 'child'. A word that is itself a lemma ('better', 'thought')
    stays as typed."""
    if " " in word:
        return word
    lem = lemminflect.getAllLemmas(word)
    if not lem or any(word in forms_ for forms_ in lem.values()):
        return word
    return next(lem[p][0] for p in POS_ORDER + list(lem) if p in lem)


def _infl(lemma, tag):
    head, _, rest = lemma.partition(" ")
    forms = lemminflect.getInflection(head, tag, inflect_oov=True)
    out = forms[0] if forms else head
    return (out + " " + rest).strip() if rest else out


def _all(lemma, tag):
    head, _, rest = lemma.partition(" ")
    vals = lemminflect.getAllInflections(head).get(tag) or lemminflect.getInflection(head, tag, inflect_oov=True)
    return " / ".join((v + " " + rest).strip() for v in dict.fromkeys(vals))


def _irregular(lemma):
    head = lemma.split(" ")[0]
    lex = lemminflect.getAllInflections(head, upos="VERB")
    rule = lemminflect.getAllInflectionsOOV(head, upos="VERB")
    return any(lex.get(t) and rule.get(t) and lex[t][0] != rule[t][0] for t in ("VBD", "VBN"))


def forms(lemma, pos):
    out = []
    if "VERB" in pos or "AUX" in pos:
        if lemma == "be":
            out += [{"label": "base", "form": "be"}, {"label": "present", "form": "am / is / are"},
                    {"label": "past simple", "form": "was / were"}, {"label": "past participle", "form": "been"},
                    {"label": "-ing form", "form": "being"}]
        elif lemma in grammar_data.MODALS:
            out += [{"label": "modal", "form": lemma + " (no -s, no -ing, no to after it)"}]
            if lemma in grammar_data.MODAL_PAST:
                out.append({"label": "past / conditional", "form": grammar_data.MODAL_PAST[lemma]})
        else:
            over = grammar_data.FORM_OVERRIDES.get(lemma, {})
            out += [{"label": "base", "form": lemma}, {"label": "he/she/it", "form": _infl(lemma, "VBZ")},
                    {"label": "past simple", "form": over.get("past simple") or _all(lemma, "VBD")},
                    {"label": "past participle", "form": over.get("past participle") or _all(lemma, "VBN")},
                    {"label": "-ing form", "form": _infl(lemma, "VBG")}]
    # A noun plural only for words that are mainly nouns: "thinks" (a think) would only confuse.
    if "NOUN" in pos and " " not in lemma and pos[0] == "NOUN":
        plurals = [p for p in lemminflect.getAllInflections(lemma, upos="NOUN").get("NNS", ()) if p != lemma]
        out.append({"label": "plural", "form": " / ".join(plurals) if plurals else lemma + " (no plural)"})
    if "ADJ" in pos and " " not in lemma:
        # Lexicon forms only: the spelling rule would build "significanter".
        inf = lemminflect.getAllInflections(lemma, upos="ADJ")
        out += [{"label": "comparative", "form": inf["JJR"][0] if inf.get("JJR") else "more " + lemma},
                {"label": "superlative", "form": inf["JJS"][0] if inf.get("JJS") else "most " + lemma}]
    return out


TENSES = [  # name, I, she, negative (I), question (you)
    ("present simple", "I {vb}", "she {vbz}", "I don't {vb}", "Do you {vb}?"),
    ("present continuous", "I am {vbg}", "she is {vbg}", "I'm not {vbg}", "Are you {vbg}?"),
    ("present perfect", "I have {vbn}", "she has {vbn}", "I haven't {vbn}", "Have you {vbn}?"),
    ("present perfect continuous", "I have been {vbg}", "she has been {vbg}", "I haven't been {vbg}", "Have you been {vbg}?"),
    ("past simple", "I {vbd}", "she {vbd}", "I didn't {vb}", "Did you {vb}?"),
    ("past continuous", "I was {vbg}", "she was {vbg}", "I wasn't {vbg}", "Were you {vbg}?"),
    ("past perfect", "I had {vbn}", "she had {vbn}", "I hadn't {vbn}", "Had you {vbn}?"),
    ("past perfect continuous", "I had been {vbg}", "she had been {vbg}", "I hadn't been {vbg}", "Had you been {vbg}?"),
    ("future simple", "I will {vb}", "she will {vb}", "I won't {vb}", "Will you {vb}?"),
    ("be going to", "I am going to {vb}", "she is going to {vb}", "I'm not going to {vb}", "Are you going to {vb}?"),
    ("future continuous", "I will be {vbg}", "she will be {vbg}", "I won't be {vbg}", "Will you be {vbg}?"),
    ("future perfect", "I will have {vbn}", "she will have {vbn}", "I won't have {vbn}", "Will you have {vbn}?"),
    ("future perfect continuous", "I will have been {vbg}", "she will have been {vbg}", "I won't have been {vbg}",
     "Will you have been {vbg}?"),
]
BE_FORMS = {"present simple": ("I am", "she is", "I'm not", "Are you?"), "past simple": ("I was", "she was", "I wasn't", "Were you?")}


def tenses(lemma):
    if lemma in grammar_data.MODALS:
        return []
    f = {"vb": lemma, "vbz": _infl(lemma, "VBZ"), "vbd": _infl(lemma, "VBD"), "vbn": _infl(lemma, "VBN"), "vbg": _infl(lemma, "VBG")}
    if lemma == "be":
        f.update(vbz="is", vbd="was")
    aspect = grammar_data.aspect_of(lemma)
    rows = []
    for name, *cells in TENSES:
        if lemma == "be" and name in BE_FORMS:
            cells = BE_FORMS[name]
        else:
            cells = [c.format(**f) for c in cells]
        continuous = "continuous" in name
        note = ""
        if continuous and aspect == "stative":
            note = "Usually not used: a stative verb. Use the simple form."
        elif continuous and aspect == "both":
            note = "Only in the action meaning."
        rows.append({"tense": name, "i": cells[0], "she": cells[1], "negative": cells[2], "question": cells[3],
                     "ok": not (continuous and aspect == "stative"), "note": note})
    return rows


def complement(lemma):
    kind, source = grammar_data.complement_of(lemma)
    if not kind:
        return None
    en, tr = grammar_data.COMPLEMENT_RULE[kind]
    return {"kind": kind, "en": en, "tr": tr, "source": source,
            "contrast": [{"form": f, "en": e, "tr": t, "example": x} for f, e, t, x in grammar_data.DIFFERENT_MEANING.get(lemma, [])]}


def aspect(lemma):
    a = grammar_data.aspect_of(lemma)
    note = grammar_data.STATIVE_AND_DYNAMIC.get(lemma, ("", ""))
    if a == "stative":
        note = ("A state verb: normally not used in continuous tenses (not 'I am " + _infl(lemma, "VBG") + "').",
                "Durum fiili: normalde sürekli zamanlarda kullanılmaz.")
    return {"kind": a, "en": note[0], "tr": note[1]}


def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=NET_TIMEOUT) as r:
        if "json" not in r.headers.get("Content-Type", ""):
            raise ValueError("not json")
        return json.loads(r.read(NET_MAX))


def wiktionary(lemma):
    """IPA (and definitions) from the free dictionary API (Wiktionary data). Cached; {} when unreachable."""
    hit = cache.get_json("dict", lemma)
    if hit is not None:
        return hit
    try:
        data = _get_json("https://api.dictionaryapi.dev/api/v2/entries/en/" + urllib.parse.quote(lemma))
    except (OSError, ValueError):
        return {}  # not cached: try again next time
    ipa, defs = {}, []
    for entry in data if isinstance(data, list) else []:
        for ph in entry.get("phonetics") or []:
            t, audio = str(ph.get("text") or ""), str(ph.get("audio") or "")
            if not t:
                continue
            acc = "uk" if "-uk" in audio else "us" if "-us" in audio else None
            if acc and acc not in ipa:
                ipa[acc] = t
            ipa.setdefault("any", t)
        for m in entry.get("meanings") or []:
            for d in (m.get("definitions") or [])[:3]:
                if len(defs) < 8 and d.get("definition"):
                    defs.append({"pos": str(m.get("partOfSpeech", ""))[:20], "en": str(d["definition"])[:300],
                                 "example": str(d.get("example") or "")[:300]})
    out = {"ipa": ipa, "definitions": defs}
    cache.put_json("dict", lemma, out)
    return out


def tidy_ipa(s):
    """Dictionary-style IPA in slashes. espeak puts the stress mark before the vowel ('ɐvˈɔɪd'); dictionaries put it
    before the syllable ('əˈvɔɪd'). One-syllable words carry no stress mark."""
    s = s.strip().strip("/[]").strip()
    if not s:
        return ""
    words = []
    for w in s.split(" "):
        nuclei = len(re.findall(r"[aeiouæɑɒɔəɛɜɪʊʌɐɚɝ]+", w))
        if nuclei <= 1:
            w = w.replace("ˈ", "").replace("ˌ", "")
        else:
            w = re.sub(r"([bcdfɡhjklmnpqrstvwxzðθʃʒŋɹɾʔ])([ˈˌ])", r"\2\1", w)
            w = re.sub(r"(t͡ʃ|d͡ʒ)([ˈˌ])", r"\2\1", w)
        words.append(w)
    return "/" + " ".join(words) + "/"


# Dictionary transcriptions with dialect marks, optional sounds or syllable dots ("ɡɪ̈d", "ɡʊ(d)", "sɪˈɡnɪ.fɪ.kənt")
# confuse a learner; the voice's own phonemizer gives a clean standard form instead.
CLEAN_IPA = re.compile(r"^[a-zæɑɒɔəɛɜɪʊʌɐɚɝθðʃʒŋɹɾʔɡːˈˌ͡ ]+$")


def _ipa(dict_ipa, word, accent):
    d = (dict_ipa or "").strip().strip("/[]").replace(".", "")
    return tidy_ipa(d if d and CLEAN_IPA.match(d) else tts.ipa(word, accent))


# ---------------------------------------------------------------- frequency (wordfreq: Wikipedia, subtitles, news,
# books and web text). Zipf scale: 6+ = one of the ~200 commonest words, 3 = about once per million words.
FREQ_BANDS = [  # (lowest Zipf, key, English, Turkish)
    (6.0, "very common", "Very common — among the most used words", "Çok yaygın — en sık kullanılan kelimelerden"),
    (5.0, "common", "Common — basic everyday vocabulary", "Yaygın — temel, günlük kelime"),
    (4.0, "moderate", "Fairly common — you will meet it often", "Orta — sık karşılaşırsınız"),
    (3.0, "uncommon", "Less common — mostly in writing or specific topics", "Az yaygın — daha çok yazıda ya da belirli konularda"),
    (0.0, "rare", "Rare", "Nadir"),
]
TOP_N = 50000
_top_rank = None


def _rank_table():
    global _top_rank
    if _top_rank is None:
        from wordfreq import top_n_list
        _top_rank = {w: i + 1 for i, w in enumerate(top_n_list("en", TOP_N))}
    return _top_rank


def frequency(lemma):
    """How common the word is in English, counting all its forms (think, thinks, thought, thinking)."""
    try:
        from wordfreq import word_frequency, zipf_frequency
    except ImportError:
        return None
    import math
    if " " in lemma:
        zipf, estimate = zipf_frequency(lemma, "en"), True  # a phrase: wordfreq can only estimate it
    else:
        total = sum(word_frequency(f, "en") for f in {lemma} | _own_forms(lemma))
        zipf, estimate = (round(math.log10(total * 1e9), 2) if total else 0.0), False
    _, key, en, tr = next(b for b in FREQ_BANDS if zipf >= b[0])
    return {"zipf": zipf, "band": key, "en": en, "tr": tr, "rank": None if estimate else _rank_table().get(lemma),
            "estimate": estimate, "source": "wordfreq"}


MAX_MEANINGS_PER_POS = 4
MAX_ENTRIES = 3
OXFORD_IPA = str.maketrans({"υ": "ʊ", "ε": "ɛ"})  # older Oxford symbols -> current IPA


def _meanings(entries):
    """NOAD entries (homographs included: bank 1, bank 2) -> [{pos, senses: [{def, grammar, examples, sub}]}]."""
    out = []
    for e in entries[:MAX_ENTRIES]:
        for b in e["blocks"]:
            out.append({"pos": b["pos"], "senses": [
                {"def": s_["def"], "grammar": s_["grammar"], "register": s_.get("register", ""), "examples": s_["examples"][:2],
                 "sub": [{"def": x["def"], "examples": x["examples"][:1]} for x in s_["sub"][:2]]}
                for s_ in b["senses"][:MAX_MEANINGS_PER_POS]]})
    return out


OXFORD_POS = {"n": "noun", "adj": "adjective", "adv": "adverb", "prep": "preposition", "conj": "conjunction",
              "pron": "pronoun", "interj": "exclamation"}


def _oxford_pos(label):
    label = label.strip()
    if "verb" in label:
        return "verb"
    return OXFORD_POS.get(label, label)


def _turkish(entries):
    """Oxford Turkish entries -> [{pos, senses: [{tr: [...], for}]}, ...] and example phrases with Turkish."""
    blocks, phrases = [], []
    for e in entries[:MAX_ENTRIES]:
        for b in e["blocks"]:
            b = dict(b, pos=_oxford_pos(b["pos"]))
            senses = [{"tr": [t["tr"] for t in s_["tr"]], "for": next((t["for"] for t in s_["tr"] if t["for"]), "")}
                      for s_ in b["senses"] if s_["tr"]]
            if senses:
                blocks.append({"pos": b["pos"], "senses": senses})
            phrases += [x for s_ in b["senses"] for x in s_["examples"]]
    return blocks, phrases


MAX_SUMMARY = 4


def _summary_tr(blocks, pos_order, lemma, phrases, headword):
    """The main Turkish equivalents for the one-line answer at the top of the card, main part of speech first.
    When the dictionary redirected the word ('interested' -> 'interest'), its own example phrase is the answer."""
    if headword and headword != lemma:
        own = [p["tr"] for p in phrases if re.search(rf"\b{re.escape(lemma)}\b", p["en"])]
        return ", ".join(own[:2])
    rank = {p: i for i, p in enumerate(pos_order)}
    out = []
    for b in sorted(blocks, key=lambda b: rank.get(b["pos"], 99)):
        for s_ in b["senses"][:2]:
            out += s_["tr"][:1]
    return ", ".join(list(dict.fromkeys(out))[:MAX_SUMMARY])


def _phrasal_and_idioms(lemma, noad_entries, oxtr_entries):
    head = lemma.split(" ")[0]
    pv = {}
    for e in noad_entries:
        for p in e["phrasal_verbs"]:
            pv.setdefault(p["phrase"], {"phrase": p["phrase"], "def": p["def"], "example": p["example"]})
    for e in oxtr_entries:  # Oxford Turkish lists phrasal verbs as related entries ("give up", "give in 1")
        for r in e["related"]:
            phrase = re.sub(r"\s+\d+$", "", r)
            words_ = phrase.split()
            if len(words_) == 2 and words_[0] == head and words_[1] in PARTICLES:
                pv.setdefault(phrase, {"phrase": phrase, "def": "", "example": ""})
    idioms = [{"phrase": p["phrase"], "def": p["def"], "example": p["example"]} for e in noad_entries for p in e["phrases"]]
    return list(pv.values())[:12], idioms[:8]


PARTICLES = {"up", "down", "off", "out", "on", "in", "over", "away", "back", "forward", "around", "through", "about",
             "along", "aside", "by", "for", "into", "after", "onto", "across", "apart"}


def _family(lemma, noad_entries, oxtr_entries):
    """Derived words from the dictionaries and from affix rules, kept only when the English lexicon knows them;
    grouped by their own part of speech."""
    cands = [d["phrase"] for e in noad_entries for d in e["derivatives"]]
    cands += [r for e in oxtr_entries for r in e["related"] if " " not in r]
    cands += family_candidates(lemma)
    out, seen = {}, {lemma}
    for c in cands:
        c = re.sub(r"\s*\(.*?\)", "", c).strip().lower()
        lem = lemminflect.getAllLemmas(c) if WORD_OK.match(c or "-") else {}
        if not lem or c in seen:
            continue
        seen.add(c)
        p = next((p for p in POS_ORDER if p in lem and lem[p][0] == c), None)
        if p:
            out.setdefault(POS_NAME[p], []).append({"word": c, "tr": ""})
    return out


def _add_turkish(items, key):
    """Fills 'tr' of each item from the Oxford Turkish dictionary (one batch lookup)."""
    found = dicts.first_turkish([it[key] for it in items])
    for it in items:
        it["tr"] = found.get(it[key], "")


def _usage(lemma, pos):
    comp = complement(lemma)
    curated = [{"phrase": p, "tr": t} for p, t in grammar_data.PREPOSITIONS.get(lemma, [])]
    if not comp and curated and ("ADJ" in pos or lemma in PREP_ING_VERBS):
        en, tr = grammar_data.COMPLEMENT_RULE["preposition + -ing"]
        comp = {"kind": "preposition + -ing", "en": en, "tr": tr, "source": "curated", "contrast": []}
    return comp, curated, mistakes(lemma, pos, comp["kind"] if comp else None)


def _made_of_english_words(lemma):
    """An unlisted phrase ('bicycle bay') is still a real phrase when each of its words is a known English word."""
    from wordfreq import zipf_frequency
    return " " in lemma and all(zipf_frequency(x, "en") > 0 for x in lemma.split())


def base(word):
    """The whole card except the examples. Returns (status, card)."""
    w = normalize(word)
    if not w:
        return 400, {"error": "type an English word or short phrase (letters only)"}
    lemma = lemma_of(w)
    pos = _pos(lemma)
    noad = dicts.lookup([lemma], dicts.NOAD).get(lemma, [])
    # The search also returns related entries ('interest' for 'interested'); the word's own entries come first.
    noad = [e for e in noad if re.sub(r"[\s\d]+$", "", e["headword"].lower()) == lemma] or noad
    oxtr = dicts.english_to_turkish(lemma)
    turkish, tr_phrases = _turkish(oxtr)
    phrasal, idioms = _phrasal_and_idioms(lemma, noad, oxtr)
    meanings = _meanings(noad)
    if " " in lemma:
        # 'look forward to' is a sub-entry of 'look': its own meaning, not the meanings of 'look'.
        own = [p for p in phrasal + idioms if p["phrase"].lower() == lemma]
        meanings = [{"pos": "phrasal verb" if own and own[0] in phrasal else "phrase", "senses": [
            {"def": own[0]["def"], "grammar": [], "register": "", "examples": [own[0]["example"]] if own[0]["example"] else [],
             "sub": []}]}] if own and own[0]["def"] else []
        phrasal = [p for p in phrasal if p["phrase"].lower() != lemma]
    if " " in lemma and not any(p["phrase"].lower() == lemma for p in phrasal):
        pos = []  # 'bicycle bay' is not a verb because 'bicycle' can be one; only a real phrasal verb keeps VERB
    family_ = _family(lemma, noad, oxtr)
    _add_turkish(phrasal, "phrase")
    _add_turkish([x for group in family_.values() for x in group], "word")
    # UK: Oxford's IPA. US: Wiktionary's (one cached network call), else the voice's phonemizer.
    uk = next((e["ipa_uk"] for e in oxtr if e.get("ipa_uk")), "").translate(OXFORD_IPA)
    us_dict = wiktionary(lemma).get("ipa", {})
    other = [f"“{lemma}” is also a form of “{b}” ({p})." for b, p in also_form_of(lemma) if b != lemma]
    comp, preps, mist = _usage(lemma, pos)
    # Main part of speech first, as the dictionary orders it ('book' is mainly a noun, 'give' a verb).
    dict_order = [b["pos"] for e in noad for b in e["blocks"]]
    pos_names = sorted(dict.fromkeys(POS_NAME[p] for p in pos),
                       key=lambda n: dict_order.index(n) if n in dict_order else len(dict_order))
    card = {
        "word": w, "lemma": lemma, "known": bool(pos or noad or oxtr) or _made_of_english_words(lemma),
        "pos": pos_names,
        "note": " ".join(([f"“{w}” is a form of “{lemma}”."] if lemma != w else []) + other),
        "ipa": {"us": _ipa(us_dict.get("us") or us_dict.get("any"), lemma, "us"), "uk": _ipa(uk, lemma, "uk")},
        "tr": _summary_tr(turkish, pos_names, lemma, tr_phrases,
                          oxtr[0]["headword"].lower() if oxtr else ""),
        "turkish": turkish,
        "turkish_phrases": tr_phrases[:6],
        "meanings": meanings,
        "phrasal_verbs": phrasal,
        "idioms": idioms,
        "family": family_,
        "frequency": frequency(lemma),
        "forms": forms(lemma, pos),
        "irregular": ("VERB" in pos) and " " not in lemma and _irregular(lemma),
        "complement": comp,
        "prepositions": preps,
        "mistakes": mist,
        "sources": {"meanings": "New Oxford American Dictionary" if noad else "",
                    "turkish": "Oxford Turkish Dictionary" if oxtr else ""},
    }
    if "VERB" in pos:
        card["aspect"] = aspect(lemma)
        card["tenses"] = tenses(lemma)
    return 200, card


# ---------------------------------------------------------------- model parts

S, B = {"type": "string"}, {"type": "boolean"}


def _obj(props):
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


SYSTEM = ("You are a precise English lexicographer and an English teacher for Turkish speakers. Use only real, common "
          "English; never invent words, forms or phrasal verbs. Turkish must be natural and specific to the meaning. "
          "Keep every field short.")

SENSES_SCHEMA = _obj({
    "senses": {"type": "array", "maxItems": 4, "items": _obj({"pos": S, "tr": S, "en": S, "example": S, "example_tr": S})},
})
SENSES_PROMPT = ("Word: {w} ({pos}).\nsenses: its most common meanings, most frequent first (2-4). For each: part of "
                 "speech, the Turkish word(s) for THIS meaning, a short English definition (max 12 words), one natural "
                 "everyday example sentence that contains the word '{w}' itself, and its Turkish translation. The Turkish "
                 "word must fit that part of speech and meaning.")

PHRASE_PROMPT = ("Phrase: '{w}'. It is not in the dictionaries. Work out what the whole phrase means as people use it "
                 "(for example a compound noun such as 'main building' = the principal building of a site), 1-3 meanings, "
                 "most likely first. It is a noun phrase unless its last word is clearly a verb, adjective or adverb: do "
                 "not turn a noun phrase into a verb. For each: part of speech of the WHOLE phrase, the natural Turkish "
                 "for it, a short English definition (max 12 words), one everyday example sentence that contains the "
                 "exact phrase '{w}', and its Turkish translation.")


def _cached_model_part(part, lemma, build):
    hit = cache.get_json("word-" + part, lemma)
    if hit is not None:
        return 200, hit
    status, data = build()
    if status == 200:
        cache.put_json("word-" + part, lemma, data)
    return status, data


def _pos_text(lemma):
    return ", ".join(POS_NAME[p] for p in _pos(lemma)) or "word"


def senses(word):
    """Fallback meanings from the local model, for words the dictionaries do not have. Slower and less reliable."""
    w = normalize(word)
    if not w:
        return 400, {"error": "bad word"}
    lemma = lemma_of(w)

    def build():
        prompt = (PHRASE_PROMPT.format(w=lemma) if " " in lemma
                  else SENSES_PROMPT.format(w=lemma, pos=_pos_text(lemma)))
        status, data = llm.structured(SYSTEM, SENSES_SCHEMA, prompt, "card", 500)
        if status != 200:
            return status, data
        forms_ = {lemma} | _own_forms(lemma.split(" ")[0])
        # An example that does not contain the word ("My first thought..." for 'think') teaches the wrong word.
        senses_ = [{k: str(s.get(k, ""))[:300] for k in ("pos", "tr", "en", "example", "example_tr")}
                   for s in data.get("senses") or [] if isinstance(s, dict) and s.get("tr")
                   and set(re.findall(r"[a-z']+", str(s.get("example", "")).lower())) & forms_][:4]
        return 200, {"senses": senses_}
    return _cached_model_part("senses4", lemma, build)


FILL_SCHEMA = _obj({"items": {"type": "array", "maxItems": 24, "items": _obj({"n": {"type": "integer"}, "tr": S})}})
FILL_PROMPT = ("Give the natural Turkish equivalent of each numbered English item, in exactly the meaning described "
               "after the colon: the words a Turkish dictionary would give, 1-4 words, no notes or parentheses. Idioms "
               "get the Turkish idiom or plain meaning, never a word-for-word translation. One entry per number.\n{items}")
MAX_FILL = 20


def fill(word):
    """Turkish for the parts of the card the Turkish dictionary does not cover: meanings of words it lacks ('go'),
    phrasal verbs, idioms and family words. The model is given each item's English definition, so it translates
    a known meaning instead of guessing one."""
    status, card = base(word)
    if status != 200:
        return status, card
    lemma = card["lemma"]
    items = []  # (section, key, text for the prompt)
    if not card["tr"]:
        for m in card["meanings"]:
            for i, s_ in enumerate(m["senses"][:2]):
                items.append(("meanings", f"{m['pos']}|{i}", f"{lemma} ({m['pos']}): {s_['def']}"))
    items += [("phrasal_verbs", p["phrase"], f"{p['phrase']}: {p['def'] or 'phrasal verb'}") for p in card["phrasal_verbs"] if not p["tr"]]
    items += [("idioms", p["phrase"], f"{p['phrase']}: {p['def']}") for p in card["idioms"] if p["def"]]
    items += [("family", x["word"], f"{x['word']} ({pos_}): a word of the same family as '{lemma}'")
              for pos_, group in card["family"].items() for x in group if not x["tr"]]
    items = items[:MAX_FILL]
    if not items:
        return 200, {"meanings": {}, "phrasal_verbs": {}, "idioms": {}, "family": {}}

    def build():
        status, data = llm.structured(SYSTEM, FILL_SCHEMA, FILL_PROMPT.format(
            items="\n".join(f"{i + 1}. {text}" for i, (_, _, text) in enumerate(items))), "card", 600)
        if status != 200:
            return status, data
        out = {"meanings": {}, "phrasal_verbs": {}, "idioms": {}, "family": {}}
        for x in data.get("items") or []:
            if isinstance(x, dict) and isinstance(x.get("n"), int) and 1 <= x["n"] <= len(items) and str(x.get("tr", "")).strip():
                section, key, _ = items[x["n"] - 1]
                out[section][key] = str(x["tr"]).strip()[:120]
        return 200, out
    return _cached_model_part("fill2", lemma, build)


# ---------------------------------------------------------------- typical mistakes (rule-made, always correct)

# Stative verbs whose continuous-tense mistake is clear with a simple sentence.
STATIVE_MISTAKE = {"know", "understand", "like", "love", "hate", "want", "need", "prefer", "believe", "remember", "own",
                   "possess", "recognize", "recognise", "realize", "realise", "seem", "appear", "belong", "cost", "consist",
                   "depend", "contain", "include", "mean", "matter"}
STATIVE_OBJECT = {"seem": ("He", "tired"), "appear": ("He", "tired"), "belong": ("It", "to me"), "cost": ("It", "a lot"),
                  "consist": ("It", "of three parts"), "depend": ("It", "on the weather"), "contain": ("It", "sugar"),
                  "include": ("It", "breakfast"), "mean": ("What", None), "matter": ("It", "a lot to me")}
PREP_ING_VERBS = {"insist", "succeed", "apologize", "apologise", "think", "concentrate", "focus", "dream", "worry",
                  "complain", "object", "persist", "specialize", "believe", "look"}


def _past(lemma):
    return " ".join([_infl(lemma.split(" ")[0], "VBD")] + lemma.split(" ")[1:])


def mistakes(lemma, pos, kind):
    """Typical mistakes of Turkish speakers, built from the word's known pattern, so they are always correct."""
    out = []
    add = lambda wrong, right, why: out.append({"wrong": wrong, "right": right, "why_tr": why})
    v, past = lemma, _past(lemma) if "VERB" in pos else lemma
    if kind == "gerund":
        if lemma.startswith("can't"):
            add(f"I {v} to laugh.", f"I {v} laughing.", f"'{v}' sonrasında fiil -ing alır.")
        elif lemma in ("be used to", "get used to"):
            add("I'm used to get up early.", "I'm used to getting up early.", "'used to' burada edattır: arkasından -ing gelir.")
        elif lemma == "look forward to":
            add("I'm looking forward to see you.", "I'm looking forward to seeing you.",
                "'look forward to' içindeki 'to' edattır: arkasından fiilin -ing hali gelir.")
        elif lemma == "object to":
            add("I object to pay more.", "I object to paying more.", "'object to' içindeki 'to' edattır: arkasından -ing gelir.")
        elif lemma == "mind":
            add("Do you mind to open the window?", "Do you mind opening the window?", "'mind' sonrasında fiil -ing alır.")
        else:
            add(f"I {past} to do it.", f"I {past} doing it.", f"'{v}' sonrasında to + fiil değil, fiilin -ing hali gelir.")
    elif kind == "infinitive" and lemma in ("seem", "appear", "tend", "happen"):
        add(f"He {_infl(lemma, 'VBZ')} being happy.", f"He {_infl(lemma, 'VBZ')} to be happy.", f"'{v}' sonrasında to + fiil gelir.")
    elif kind == "infinitive":
        form = v if v.startswith("would") else past
        add(f"I {form} doing it.", f"I {form} to do it.", f"'{v}' sonrasında to + fiil gelir, -ing gelmez.")
    elif kind == "object + infinitive":
        add(f"She {past} me do it.", f"She {past} me to do it.", f"'{v} someone' sonrasında to unutulmaz: {v} someone to do.")
        add(f"She {past} that I do it.", f"She {past} me to do it.", f"'{v}' ile Türkçedeki gibi 'that' cümlesi değil, nesne + to + fiil kullanılır.")
    elif kind == "bare infinitive" and lemma != "help":
        if lemma in ("had better", "would rather"):
            add(f"You {v} to go.", f"You {v} go.", f"'{v}' sonrasında to kullanılmaz.")
        else:
            add(f"She {past} me to do it.", f"She {past} me do it.", f"'{v} someone' sonrasında to kullanılmaz (passive hariç).")
    elif kind == "modal":
        add(f"I {v} to swim.", f"I {v} swim.", "Kip fiillerinden sonra to kullanılmaz.")
        if lemma in ("can", "may", "must", "will", "shall"):
            add(f"She {v}s swim.", f"She {v} swim.", "Kip fiilleri üçüncü tekil şahısta -s almaz.")
    elif kind == "that-clause" and lemma == "think":
        add("I think to go home.", "I think I'll go home.", "'think' ile to + fiil kullanılmaz; 'I think I'll ...' ya da 'I'm thinking of going' denir.")
    if "VERB" in pos and grammar_data.aspect_of(lemma) == "stative" and lemma in STATIVE_MISTAKE:
        subj, obj = STATIVE_OBJECT.get(lemma, ("I", "it"))
        if obj is None:
            add(f"What are you {_infl(lemma, 'VBG')}?", f"What do you {lemma}?", "Durum fiilleri sürekli zamanda kullanılmaz.")
        else:
            be = "is" if subj in ("He", "It") else "am"
            simple = _infl(lemma, "VBZ") if subj in ("He", "It") else lemma
            add(f"{subj} {be} {_infl(lemma, 'VBG')} {obj}.", f"{subj} {simple} {obj}.", "Durum fiilleri (know, need, belong...) sürekli zamanda kullanılmaz.")
    preps = grammar_data.PREPOSITIONS.get(lemma, [])
    action_preps = [p for p, _ in preps if "(" not in p and "/" not in p]
    if action_preps and ("ADJ" in pos or lemma in PREP_ING_VERBS) and kind != "gerund":
        p = action_preps[0]
        lead = f"I'm {p}" if "ADJ" in pos else f"I {p}"
        add(f"{lead} do it.", f"{lead} doing it.", f"Edattan ('{p.split()[-1]}') sonra fiil -ing alır.")
    return out[:4]


def _own_forms(head):
    return {f for forms_ in lemminflect.getAllInflections(head).values() for f in forms_}


MIN_RULE_LEN = 5
SUFFIXES = ["ly", "ness", "ity", "ment", "ance", "ence", "ion", "ation", "tion", "al", "ive", "able", "ible", "ful",
            "less", "er", "or", "ist", "ism", "ize", "en", "y", "ous", "ic", "ical", "ically", "ure", "ant", "ent"]
PREFIXES = ["un", "in", "im", "ir", "il", "dis", "mis", "re", "over", "under"]


def family_candidates(lemma):
    """Derived forms built by English affix rules, kept only when the lexicon knows them."""
    if " " in lemma or len(lemma) < MIN_RULE_LEN:
        return []  # short words give false relatives by rule ("go" + "al" = "goal")
    stems = {lemma, lemma[:-1] if lemma.endswith("e") else lemma, lemma[:-1] + "i" if lemma.endswith("y") else lemma,
             lemma[:-2] if lemma.endswith(("ant", "ent")) else lemma, lemma[:-3] if lemma.endswith(("ate", "ous")) else lemma}
    if re.search(r"[^aeiou][aeiou][bdgmnprt]$", lemma):
        stems.add(lemma + lemma[-1])
    for end, swap in (("ant", "ance"), ("ent", "ence"), ("ic", "ically"), ("le", "ly")):
        if lemma.endswith(end):
            stems.add(lemma[: -len(end)] + swap)
    cands = set()
    for s in stems:
        cands.add(s)
        for suf in SUFFIXES:
            cands.add(s + suf)
    for p in PREFIXES:
        cands.add(p + lemma)
    cands.discard(lemma)
    return sorted(c for c in cands if lemminflect.getAllLemmas(c) and lemma_of(c) == c)


# ---------------------------------------------------------------- real examples

EXAMPLES_MAX = 6


def examples(word):
    """Real sentences containing the word with their human Turkish translations (Tatoeba, CC BY 2.0 FR)."""
    w = normalize(word)
    if not w:
        return 400, {"error": "bad word"}
    hit = cache.get_json("examples3", w)
    if hit is not None:
        return 200, hit
    # sort=random: relevance and length order return only one- and two-word sentences ("Think!") first.
    url = ("https://api.tatoeba.org/unstable/sentences?lang=eng&trans%3Alang=tur&sort=random&limit=40&q="
           + urllib.parse.quote(f'"{w}"' if " " in w else w))
    try:
        data = _get_json(url)
    except (OSError, ValueError):
        return 503, {"error": "Example sentences are unavailable right now."}
    head, _, rest = w.partition(" ")
    heads = {head} | _own_forms(head)
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, sorted(heads, key=len, reverse=True))) + r")\b"
                         + (r"\s+" + re.escape(rest) if rest else "") + r"\b", re.I)
    out = []
    for s in data.get("data") or []:
        text = str(s.get("text") or "")
        if not pattern.search(text):
            continue  # the search matches stems: 'interested' also finds 'interesting'
        trs = [t for t in s.get("translations") or [] if t.get("lang") == "tur" and not t.get("is_unapproved")]
        if not trs or not (4 <= len(text.split()) <= 14):
            continue
        out.append({"en": text[:300], "tr": str(trs[0].get("text") or "")[:300], "id": s.get("id")})
        if len(out) >= EXAMPLES_MAX:
            break
    result = {"examples": out, "source": "Tatoeba (CC BY 2.0 FR)"}
    if out:  # an empty answer may be a passing problem: ask again next time
        cache.put_json("examples3", w, result)
    return 200, result
