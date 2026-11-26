#!/usr/bin/env python3
"""Save the dictionary entries the parser tests read (tests/fixtures/dict_avoid_give.json).

The entries come from the Oxford dictionaries licensed with macOS, so they are not published with the code:
each developer makes the file from their own Mac. The parser tests are skipped until it exists.

    .venv/bin/python tests/make_fixtures.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from services import dictionary  # noqa: E402

OUT = os.path.join(ROOT, "tests", "fixtures", "dict_avoid_give.json")
WORDS = ["avoid", "give"]

raw = dictionary._raw(WORDS, [dictionary.NOAD, dictionary.OXTR])
missing = [(w, d) for w in WORDS for d in (dictionary.NOAD, dictionary.OXTR) if not raw.get(w, {}).get(d)]
if missing:
    sys.exit(f"Not found: {missing}. Enable New Oxford American and Oxford Turkish in Dictionary.app › Settings.")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(raw, f, ensure_ascii=False)
print("Saved", OUT)
