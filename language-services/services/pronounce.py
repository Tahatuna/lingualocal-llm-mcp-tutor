"""Pronunciation score from a speech recognizer's answer.

The browser's recognizer (Web Speech API) hears the learner and returns its best guesses with confidences. A word
is well pronounced when the recognizer understood that word; if it heard another word (ship / sheep, think / sink)
that is the mistake to show. This finds real word mix-ups quickly; it does not grade fine accent details.
"""
import re

NUM = {"0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five", "6": "six", "7": "seven",
       "8": "eight", "9": "nine", "10": "ten"}
MAX_ALTERNATIVES = 5
MAX_WORDS = 60


def norm(w):
    s = re.sub(r"[^a-z0-9']", "", w.lower().replace("’", "'")).strip("'")
    return NUM.get(s, s)


def _edit(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def align(target, heard):
    """Word-by-word alignment of heard words with the target. Returns [{word, status, heard}] with status
    ok | close (one letter off: probably fine) | wrong (heard another word) | missing."""
    n, m = len(target), len(heard)
    D = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        D[i][0] = i
    for j in range(1, m + 1):
        D[0][j] = j * 0.8
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            a, b = target[i - 1], heard[j - 1]
            sub = 0 if a == b else 0.6 if _edit(a, b) <= max(1, len(a) // 3) else 1.1
            D[i][j] = min(D[i - 1][j - 1] + sub, D[i - 1][j] + 1, D[i][j - 1] + 0.8)
    out, i, j = [], n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            a, b = target[i - 1], heard[j - 1]
            sub = 0 if a == b else 0.6 if _edit(a, b) <= max(1, len(a) // 3) else 1.1
            if abs(D[i][j] - (D[i - 1][j - 1] + sub)) < 1e-9:
                out.append({"status": "ok" if a == b else "close" if sub < 1 else "wrong", "heard": b if a != b else ""})
                i, j = i - 1, j - 1
                continue
        if i > 0 and (j == 0 or abs(D[i][j] - (D[i - 1][j] + 1)) < 1e-9):
            out.append({"status": "missing", "heard": ""})
            i -= 1
        else:
            j -= 1
    return list(reversed(out))


def score(target, alternatives):
    """target: the text the learner should say. alternatives: [{text, confidence}] from the recognizer, best first.
    Returns {score 0-100, verdict, heard, words: [{word, status, heard}]}."""
    raw = [w for w in str(target or "").split() if norm(w)][:MAX_WORDS]
    tgt = [norm(w) for w in raw]
    alts = [a for a in (alternatives or [])[:MAX_ALTERNATIVES] if isinstance(a, dict) and str(a.get("text", "")).strip()]
    if not tgt:
        return 400, {"error": "target is required"}
    if not alts:
        return 200, {"score": 0, "verdict": "not heard", "heard": "",
                     "words": [{"word": w, "status": "missing", "heard": ""} for w in raw]}
    best = None
    for rank, alt in enumerate(alts):
        heard = [norm(w) for w in str(alt["text"]).split() if norm(w)]
        marks = align(tgt, heard)
        ok = sum(1 for x in marks if x["status"] == "ok") + 0.7 * sum(1 for x in marks if x["status"] == "close")
        try:
            conf = float(alt.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        conf = conf if 0 < conf <= 1 else 0.9  # some browsers report 0: treat as "no information"
        # A match found only in a lower alternative counts less: the recognizer was unsure.
        value = ok / len(tgt) * (0.6 + 0.4 * conf) * (1 - 0.15 * rank)
        if best is None or value > best[0]:
            best = (value, marks, alt["text"])
    value = best[0]
    s = round(min(1.0, value) * 100)
    verdict = "clear" if s >= 85 else "close" if s >= 60 else "unclear"
    # Show the words as the recognizer most believed them: that is what a listener would hear first.
    top = str(alts[0]["text"])
    marks = align(tgt, [norm(w) for w in top.split() if norm(w)])
    return 200, {"score": s, "verdict": verdict, "heard": top[:300], "also_heard": str(best[2])[:300] if best[2] != top else "",
                 "words": [{"word": w, **m} for w, m in zip(raw, marks)]}
