"""Text to speech as WAV.

English: Kokoro (open neural voices, ~0.3 s for a sentence on this Mac), US and UK. A slow version is synthesized
slowly, not played back slowly, so the sounds stay natural.
Turkish: the macOS system voice (Yelda) through `say`.
Every clip is cached on disk; the same request is synthesized once.
"""
import io
import os
import re
import subprocess
import tempfile
import threading
import wave

from . import cache, config

MAX_CHARS = 800
SPEEDS = (0.6, 1.5)  # allowed speed range; 1.0 = normal
SAY_WPM = 175        # normal speaking rate for `say`
TEXT_OK = re.compile(r"^[\w ,.;:!?'’\"“”()\-\n]+$")
_kokoro = None
_load_lock = threading.Lock()   # loading the engine once
_synth_lock = threading.Lock()  # one synthesis at a time keeps memory flat; each takes well under a second


def _engine():
    global _kokoro
    with _load_lock:
        if _kokoro is None:
            from kokoro_onnx import Kokoro  # loaded on first use: ~0.4 s, ~300 MB
            _kokoro = Kokoro(os.path.join(config.MODELS_DIR, "kokoro-v1.0.int8.onnx"),
                             os.path.join(config.MODELS_DIR, "voices-v1.0.bin"))
        return _kokoro


def warm():
    _engine()


def voices():
    return [{"lang": "en", "accent": "us", "voice": config.VOICE_US, "engine": "kokoro"},
            {"lang": "en", "accent": "uk", "voice": config.VOICE_UK, "engine": "kokoro"},
            {"lang": "tr", "accent": "tr", "voice": config.VOICE_TR, "engine": "macos"}]


def _wav(samples, rate):
    import numpy as np
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm)
    return buf.getvalue()


def _kokoro_wav(text, accent, speed):
    voice = config.VOICE_UK if accent == "uk" else config.VOICE_US
    engine = _engine()
    with _synth_lock:
        samples, rate = engine.create(text, voice=voice, speed=speed, lang="en-gb" if accent == "uk" else "en-us")
    return _wav(samples, rate)


def _say_wav(text, speed):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "out.wav")
        subprocess.run(["say", "-v", config.VOICE_TR, "-r", str(round(SAY_WPM * speed)), "-o", path,
                        "--file-format=WAVE", "--data-format=LEI16@22050", "--", text], check=True, timeout=30)
        with open(path, "rb") as f:
            return f.read()


def speak(text, lang="en", accent="us", speed=1.0):
    """Returns (status, wav_bytes_or_error)."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_CHARS]
    if not text or not TEXT_OK.match(text):
        return 400, {"error": "text must be letters, digits and plain punctuation"}
    if lang not in ("en", "tr"):
        return 400, {"error": "lang must be en or tr"}
    try:
        speed = min(SPEEDS[1], max(SPEEDS[0], float(speed)))
    except (TypeError, ValueError):
        speed = 1.0
    accent = "uk" if accent == "uk" else "us"
    key = f"{lang}|{accent if lang == 'en' else 'tr'}|{speed:.2f}|{text}"
    hit = cache.get_bytes("tts", key)
    if hit:
        return 200, hit
    try:
        data = _say_wav(text, speed) if lang == "tr" else _kokoro_wav(text, accent, speed)
    except (subprocess.SubprocessError, OSError, RuntimeError) as e:
        return 500, {"error": f"speech failed: {type(e).__name__}"}
    cache.put_bytes("tts", key, data)
    return 200, data


def ipa(word, accent="us"):
    """IPA from the voice's own phonemizer (espeak-ng), used when the dictionary has none.

    Cached: the phonemizer starts again in each request thread (~0.5 s), which made every card for such a word slow.
    A failure is not cached, so a later call can still succeed."""
    lang = "en-gb" if accent == "uk" else "en-us"
    hit = cache.get_json("ipa-" + lang, word)
    if hit is not None:
        return hit
    try:
        out = _engine().tokenizer.phonemize(word, lang).strip()
    except Exception:  # noqa: BLE001 - IPA is optional; the card shows the dictionary's or none
        return ""
    if out:
        cache.put_json("ipa-" + lang, word, out)
    return out
