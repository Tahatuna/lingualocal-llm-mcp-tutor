"""Runs the translation quality set through several models with the service's own prompt (cache bypassed) and
writes a side-by-side table for reading.

    .venv/bin/python tests/quality/compare_models.py gemma3:12b aya-expanse:8b
"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from services import config, llm, translate

models = sys.argv[1:]
items = json.load(open(os.path.join(os.path.dirname(__file__), "translation_set.json"), encoding="utf-8"))
res = {}
for m in models:
    config.OLLAMA_MODEL = m
    llm._post([{"role": "user", "content": "hi"}], max_tokens=1)  # load the model first
    for it in items:
        src, dst = translate._pair(it["text"], "auto", "auto")
        t = time.time()
        st, out = llm._post(translate._messages(it["text"], src, dst), max_tokens=translate.MAX_TRANSLATION_TOKENS)
        dt = time.time() - t
        miss = [k for k in it["must"] if k.lower() not in str(out).lower()]
        res.setdefault(it["text"], {})[m] = (round(dt, 2), str(out).strip(), miss)
for text, by in res.items():
    print(text)
    for m in models:
        dt, out, miss = by[m]
        print(f"   {m:16} {dt:5.2f}s {'MISS ' + str(miss) if miss else 'ok  '} {out}")
for m in models:
    ts = sorted(by[m][0] for by in res.values())
    print(f"{m}: median {ts[len(ts)//2]:.2f}s  max {ts[-1]:.2f}s  key-word misses {sum(bool(by[m][2]) for by in res.values())}/{len(res)}")
