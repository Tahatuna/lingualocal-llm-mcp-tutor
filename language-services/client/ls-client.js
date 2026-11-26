// Browser client for Language Services. Import from the service itself:
//   import { createClient, listen, testPronunciation } from 'http://localhost:8770/client.js';
// The page's origin must be in LS_ALLOWED_ORIGINS on the service.

export function createClient(base = 'http://localhost:8770') {
  const post = async (path, body, signal) => {
    const r = await fetch(base + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `Request failed (${r.status})`);
    return j;
  };
  const get = async (path, params, signal) => {
    const r = await fetch(base + path + '?' + new URLSearchParams(params), { signal });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || `Request failed (${r.status})`);
    return j;
  };
  const ttsUrl = (text, { lang = 'en', accent = 'us', speed = 1 } = {}) =>
    base + '/v1/tts?' + new URLSearchParams({ text, lang, accent, speed: String(speed) });
  let player = null;
  return {
    health: () => get('/v1/health', {}),
    detect: (text) => post('/v1/detect', { text }),
    translate: (text, opts = {}, signal) => post('/v1/translate', { text, from: opts.from || 'auto', to: opts.to || 'auto' }, signal),
    variants: (text, opts = {}, signal) => post('/v1/translate/variants', { text, from: opts.from || 'auto', to: opts.to || 'auto' }, signal),
    chat: (messages, context = '', signal) => post('/v1/chat', { messages, context }, signal),
    rewrite: (text, signal) => post('/v1/translate/rewrite', { text }, signal),
    check: (text, translation, opts = {}, signal) => post('/v1/translate/check', { text, translation, from: opts.from || 'auto', to: opts.to || 'auto' }, signal),
    word: (word, signal) => get('/v1/word', { word }, signal),
    examples: (word, signal) => get('/v1/word/examples', { word }, signal),
    fill: (word, signal) => get('/v1/word/fill', { word }, signal),
    senses: (word, signal) => get('/v1/word/senses', { word }, signal),
    score: (target, alternatives) => post('/v1/pronunciation/score', { target, alternatives }),
    ttsUrl,
    // Plays text aloud; a new call stops the previous one. Resolves when playback starts.
    speak(text, opts = {}) {
      if (player) player.pause();
      player = new Audio(ttsUrl(text, opts));
      return player.play();
    },
    stop() { if (player) player.pause(); }
  };
}

// ---------- speech input (browser recognizer: Chrome, Edge, Safari) ----------
const SR = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition;
export const canListen = () => !!SR;
const ERR = { 'not-allowed': 'Microphone blocked. Allow it for this page.', 'no-speech': 'Didn’t hear anything — try again.', network: 'Speech recognition needs an internet connection.' };
export const SILENCE_MS = 1600;   // auto mode: stop this long after the last word
const FIRST_WORD_MS = 8000;       // auto mode: give up if nothing is said at first

// Joins recognizer pieces with exactly one space. Chrome starts later pieces with or without a space; gluing them
// ran words together ("testbecause").
export function joinText(...parts) {
  return parts.map((p) => String(p || '').trim()).filter(Boolean).join(' ');
}

// Dictation. onText(finalText, interimText) as words arrive; onEnd(errorMessage|null) once.
// Auto mode stops after a pause; keepOpen listens until stop() (the browser's own sessions are restarted).
export function listen({ lang = 'en-US', onText, onEnd, keepOpen = false, silenceMs = SILENCE_MS }) {
  if (!SR) { onEnd && onEnd('Speech input needs Chrome, Edge or Safari.'); return () => {}; }
  let finals = '', stopped = false, done = false, err = null, timer = 0, rec = null;
  const finish = () => { if (done) return; done = true; clearTimeout(timer); onEnd && onEnd(err); };
  const stop = () => { stopped = true; clearTimeout(timer); try { rec.stop(); } catch (e) { finish(); } };
  const arm = (ms) => { clearTimeout(timer); if (!keepOpen) timer = setTimeout(stop, ms); };
  function session() {
    let mine = '';
    rec = new SR();
    rec.lang = lang; rec.interimResults = true; rec.continuous = true; rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) mine = joinText(mine, t); else interim = joinText(interim, t);
      }
      onText && onText(joinText(finals, mine), interim);
      arm(silenceMs);
    };
    rec.onerror = (e) => {
      if (e.error === 'aborted' || (e.error === 'no-speech' && keepOpen)) return;
      err = ERR[e.error] || 'Speech input stopped: ' + e.error;
    };
    rec.onend = () => {
      finals = joinText(finals, mine);
      if (keepOpen && !stopped && !err) { try { session(); return; } catch (e) { /* cannot restart: finish */ } }
      finish();
    };
    rec.start();
  }
  try { session(); } catch (e) { err = 'Could not start the microphone.'; finish(); return () => {}; }
  arm(FIRST_WORD_MS);
  return stop;
}

// Pronunciation test: listens once, then scores what the recognizer heard against target.
// Resolves with {score, verdict, heard, words}. Call the returned promise's .stop() to end early.
export function testPronunciation(client, target, { lang = 'en-US', onListening } = {}) {
  let rec = null;
  const p = new Promise((resolve, reject) => {
    if (!SR) { reject(new Error('Speech input needs Chrome, Edge or Safari.')); return; }
    rec = new SR();
    rec.lang = lang; rec.maxAlternatives = 5; rec.interimResults = false; rec.continuous = false;
    let alts = null, err = null;
    rec.onresult = (e) => { alts = [...e.results[0]].map((a) => ({ text: a.transcript, confidence: a.confidence })); };
    rec.onerror = (e) => { if (e.error !== 'aborted' && e.error !== 'no-speech') err = ERR[e.error] || e.error; };
    rec.onend = () => { if (err) reject(new Error(err)); else client.score(target, alts || []).then(resolve, reject); };
    rec.start();
    onListening && onListening();
  });
  p.stop = () => { try { rec && rec.stop(); } catch (e) { /* already stopped */ } };
  return p;
}
