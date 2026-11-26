"""Translation quality run: every sentence through the model with the current prompt (cache bypassed).
Prints each output with time and whether the expected key words are there. Judge the outputs by reading them.

    .venv/bin/python tests/quality/run_translation.py
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from services import llm, translate

items = json.load(open(os.path.join(os.path.dirname(__file__), "translation_set.json"), encoding="utf-8"))
llm.text("hi", "hi", "translate", 1)  # load the model first
times, misses = [], 0
for it in items:
    src, dst = translate._pair(it["text"], "auto", "auto")
    t = time.time()
    st, out = llm.chat(translate._messages(it["text"], src, dst), "translate", translate.MAX_TRANSLATION_TOKENS)
    dt = time.time() - t; times.append(dt)
    miss = [m for m in it["must"] if m.lower() not in str(out).lower()]
    misses += bool(miss)
    print(f"{dt:4.1f}s {src}>{dst} {'MISS ' + str(miss) if miss else 'ok  '} | {it['text']}\n          -> {out}")
times.sort()
print(f"\nmedian {times[len(times)//2]:.2f}s  max {times[-1]:.2f}s  key-word misses {misses}/{len(items)}")
