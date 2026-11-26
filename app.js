// LinguaLocal: one screen. Type or say a word or sentence (English or Turkish) and see the translation,
// the word card (meanings, Turkish, forms, -ing/to, prepositions, mistakes, tenses, examples), hear it, test your
// pronunciation, save it. Language work comes from Language Services; history and saved items from this server.
import { SERVICES } from './config.js';
import { mountMouth } from './mouth.js';
import { initChat } from './chat.js';

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

let ls = null, listen = null, testPronunciation = null, canListen = () => false;
try {
  const mod = await import(SERVICES + '/client.js');
  ls = mod.createClient(SERVICES); listen = mod.listen; testPronunciation = mod.testPronunciation; canListen = mod.canListen;
} catch (e) { /* shown below */ }

const MAX_CARD_WORDS = 3;         // up to this many words get a word card (look forward to)
const SETTLE_MS = 5000;           // a translation shown this long without edits goes into the history
const AUTO_MS = 900;              // translate a typed sentence after this pause
const TOAST_MS = 3000;
const AUTO_SAY_REPEAT_MS = 4000;  // the same word looked up again this soon is not said twice
const st = { text: '', from: 'en', to: 'tr', translation: '', english: '', cardWord: '', seq: 0 };
const pref = { accent: 'us', speed: 1, savedKind: 'word', dir: 'auto', mouth: false, chat: false, autoSay: false };  // dir: auto | en | tr (the input language)
// Storage keys keep the app's first name (pm.*) so saved settings survive the rename.
try { Object.assign(pref, JSON.parse(localStorage.getItem('pm.pref') || '{}')); } catch (e) { /* defaults */ }
const keepPref = () => { try { localStorage.setItem('pm.pref', JSON.stringify(pref)); } catch (e) { /* storage unavailable */ } };

// ---------------------------------------------------------------- small helpers
let toastTimer = 0;
function toast(msg) {
  let t = document.querySelector('.toast');
  if (!t) { t = el('div', 'toast'); t.setAttribute('role', 'status'); document.body.appendChild(t); }
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, TOAST_MS);
}
function status(msg, err) { const s = $('status'); s.textContent = msg || ''; s.className = 'status' + (err ? ' err' : ''); }
const SERVICE_DOWN = 'Language Services is not running. Start it with: language-services/scripts/lsctl start';

async function api(path, body) {
  const r = await fetch(path, body ? { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-LL': '1' }, body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || 'Request failed');
  return j;
}
function speak(text, lang) {
  if (!ls || !text) return;
  ls.speak(text, { lang, accent: pref.accent, speed: pref.speed }).catch(() => toast('Could not play the sound.'));
}
function hearBtn(text, lang = 'en') {
  const b = el('button', 'hear'); b.type = 'button'; b.setAttribute('aria-label', 'Listen: ' + text);
  b.appendChild(el('span', 'play')); b.onclick = () => speak(text, lang);
  return b;
}
const isEnglishWordish = (t) => /^[a-z][a-z' -]*$/i.test(t) && t.trim().split(/\s+/).length <= MAX_CARD_WORDS;

// ---------------------------------------------------------------- preferences
function renderPrefs() {
  document.querySelectorAll('#accentSeg button').forEach((b) => b.setAttribute('aria-pressed', b.dataset.accent === pref.accent));
  document.querySelectorAll('#speedSeg button').forEach((b) => b.setAttribute('aria-pressed', Number(b.dataset.speed) === pref.speed));
  document.querySelectorAll('#savedSeg button').forEach((b) => b.setAttribute('aria-pressed', b.dataset.kind === pref.savedKind));
  $('dirSel').value = pref.dir;
  $('autoSay').setAttribute('aria-pressed', String(!!pref.autoSay));
}
document.querySelectorAll('#accentSeg button').forEach((b) => { b.onclick = () => { pref.accent = b.dataset.accent; keepPref(); renderPrefs(); }; });
document.querySelectorAll('#speedSeg button').forEach((b) => { b.onclick = () => { pref.speed = Number(b.dataset.speed); keepPref(); renderPrefs(); }; });
document.querySelectorAll('#savedSeg button').forEach((b) => { b.onclick = () => { pref.savedKind = b.dataset.kind; keepPref(); renderPrefs(); renderSaved(); }; });

// ---------------------------------------------------------------- history and saved
let history = [], saved = { words: [], sentences: [] };
async function loadHistory() { try { history = await api('/api/history'); } catch (e) { history = []; } renderHistory(); }
async function loadSaved() { try { saved = await api('/api/saved'); } catch (e) { /* keep */ } renderSaved(); renderHistory(); updateSaveButtons(); }
async function record(text, kind, result, lang) {
  try { await api('/api/history/add', { text, kind, lang, result: (result || '').slice(0, 140) }); await loadHistory(); } catch (e) { /* history is a convenience */ }
}
const SPEAKER = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/></svg>';
// The language of a stored lookup is not saved: Turkish letters say it, otherwise the service decides.
async function speakGuess(text) {
  let lang = TR_CHARS.test(text) ? 'tr' : 'en';
  if (lang === 'en' && ls) { try { lang = (await ls.detect(text)).lang || 'en'; } catch (e) { /* English */ } }
  speak(text, lang);
}
const BOOKMARK = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 3h12v18l-6-4-6 4z"/></svg>';
function listItem(text, sub, current, onOpen, onRemove, removeLabel, onSpeak, saveBtn) {
  const li = el('li');
  const b = el('button', 'item'); b.type = 'button'; b.title = text + (sub ? ' — ' + sub : '');
  b.setAttribute('aria-current', current ? 'true' : 'false');
  b.append(el('span', 't', text), el('span', 'r', sub || ''));
  b.onclick = onOpen;
  li.appendChild(b);
  if (saveBtn) li.appendChild(saveBtn);
  if (onSpeak) {
    const p = el('button', 'x p'); p.type = 'button'; p.setAttribute('aria-label', 'Listen: ' + text); p.title = 'Listen';
    p.innerHTML = SPEAKER;  // a fixed icon, no data
    p.onclick = onSpeak; li.appendChild(p);
  }
  if (onRemove) {
    const x = el('button', 'x', '×'); x.type = 'button'; x.setAttribute('aria-label', removeLabel); x.onclick = onRemove;
    li.appendChild(x);
  }
  return li;
}
// What saving a lookup keeps: the English side as a word or a sentence, with the Turkish (as the Save button does).
// Lookups stored before the language was kept say it by Turkish letters, or the service decides when you save.
function historyTarget(h, lang = h.lang || (TR_CHARS.test(h.text) ? 'tr' : 'en')) {
  const english = (lang === 'tr' ? (h.result || '').split(',')[0] : h.text).trim();
  if (!english) return null;
  const tr = lang === 'tr' ? h.text : h.result || '';
  return isEnglishWordish(english) ? { kind: 'word', text: english.toLowerCase(), tr } : { kind: 'sentence', text: english, tr };
}
function historySaveButton(h) {
  const t = historyTarget(h), on = !!t && isSaved(t.kind, t.text);
  const b = el('button', 'x s'); b.type = 'button';
  b.setAttribute('aria-pressed', String(on));
  b.setAttribute('aria-label', (on ? 'Saved: ' : 'Save: ') + h.text); b.title = on ? 'Saved — click to remove' : 'Save';
  b.innerHTML = BOOKMARK;  // a fixed icon, no data
  b.onclick = async () => {
    let target = t;
    if (!h.lang && !TR_CHARS.test(h.text) && ls) {  // an old lookup: ask which language it was in
      try { target = historyTarget(h, (await ls.detect(h.text)).lang || 'en'); } catch (e) { /* the guess above */ }
    }
    if (!target) { toast('Look it up again to save it'); return; }
    if (isSaved(target.kind, target.text)) await unsave(target.kind, target.text); else await saveItem(target.kind, target.text, target.tr);
    renderHistory();
    // The list is redrawn: give the focus back to the same row's button.
    const idx = history.findIndex((x) => x.id === h.id);
    $('histList').children[idx]?.querySelector('.x.s')?.focus();
  };
  return b;
}
function renderHistory() {
  const ol = $('histList'); ol.textContent = '';
  history.forEach((h) => ol.appendChild(listItem(h.text, h.result, h.text === st.text, () => go(h.text),
    () => removeHistory(h), 'Remove from history: ' + h.text, () => speakGuess(h.text), historySaveButton(h))));
  $('histEmpty').hidden = history.length > 0;
  $('histClear').hidden = !history.length;
  $('histCount').textContent = history.length ? String(history.length) : '';
}
async function removeHistory(h) {
  try { await api('/api/history/remove', { id: h.id }); await loadHistory(); toast(`Removed “${h.text}” from history`); }
  catch (e) { toast('Could not remove: ' + e.message); }
}
$('histClear').onclick = async () => {
  const n = history.length;
  if (!n || !confirm(`Clear all ${n} item${n === 1 ? '' : 's'} from your history? Saved words and sentences stay. This can’t be undone.`)) return;
  try { await api('/api/history/clear', {}); await loadHistory(); toast('History cleared'); } catch (e) { toast('Could not clear: ' + e.message); }
};
function renderSaved() {
  const kind = pref.savedKind, list = kind === 'word' ? saved.words : saved.sentences;
  const ol = $('savedList'); ol.textContent = '';
  list.forEach((s) => ol.appendChild(listItem(s.text, s.tr, s.text === st.text || s.text === st.cardWord, () => go(s.text),
    () => unsave(kind, s.text), 'Remove ' + s.text, () => speak(s.text, 'en'))));
  $('savedEmpty').hidden = list.length > 0;
  $('savedWordsN').textContent = saved.words.length ? String(saved.words.length) : '';
  $('savedSentN').textContent = saved.sentences.length ? String(saved.sentences.length) : '';
}
const isSaved = (kind, text) => (kind === 'word' ? saved.words : saved.sentences).some((s) => s.text === text);
async function saveItem(kind, text, tr, quiet) {
  try { saved = await api('/api/saved/add', { kind, text, tr }); renderSaved(); renderHistory(); updateSaveButtons(); if (!quiet) toast(`Saved “${text}”`); }
  catch (e) { toast('Could not save: ' + e.message); }
}
async function unsave(kind, text) {
  try { saved = await api('/api/saved/remove', { kind, text }); renderSaved(); renderHistory(); updateSaveButtons(); toast(`Removed “${text}”`); }
  catch (e) { toast('Could not remove: ' + e.message); }
}
function currentSaveTarget() {
  // A sentence is saved as a sentence (English + Turkish); a word as a word.
  const english = st.english.trim();
  if (!english) return null;
  if (isEnglishWordish(english)) return { kind: 'word', text: english.toLowerCase(), tr: st.from === 'en' ? st.translation : st.text };
  return { kind: 'sentence', text: english, tr: st.from === 'en' ? st.translation : st.text };
}
function updateSaveButtons() {
  const t = currentSaveTarget(), on = !!t && isSaved(t.kind, t.text);
  $('trSave').setAttribute('aria-pressed', on); $('trSave').textContent = on ? 'Saved' : 'Save';
  const cs = document.getElementById('cardSave');
  if (cs) { const s = isSaved('word', st.cardWord); cs.setAttribute('aria-pressed', s); cs.textContent = s ? 'Saved' : 'Save word'; }
}
$('trSave').onclick = () => {
  const t = currentSaveTarget(); if (!t) return;
  if (isSaved(t.kind, t.text)) unsave(t.kind, t.text); else saveItem(t.kind, t.text, t.tr);
};

// ---------------------------------------------------------------- input box
const box = $('input');
function grow() { if (!box.offsetParent) return; box.style.height = 'auto'; box.style.height = box.scrollHeight + 'px'; }
window.addEventListener('resize', grow);
// The app works out the language itself; the direction buttons only override it.
const forcedFrom = () => (pref.dir === 'auto' ? null : pref.dir);
function setDir(from) {
  st.from = from; st.to = from === 'en' ? 'tr' : 'en';
  // Auto shows what it detected, in the same quiet control: "Auto · TR → EN".
  $('dirSel').options[0].textContent = st.text ? `Auto · ${from === 'en' ? 'EN → TR' : 'TR → EN'}` : 'Auto';
}
const TR_CHARS = /[çğıöşüİĞŞÇÖÜ]/;
let autoTimer = 0;
box.addEventListener('input', () => {
  grow(); clearTimeout(autoTimer);
  const v = box.value.trim();
  if (v && (v.split(/\s+/).length >= 4 || TR_CHARS.test(v))) autoTimer = setTimeout(() => { if (box.value.trim() === v) go(v, { record: 'settle' }); }, AUTO_MS);
});
box.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); $('box').requestSubmit(); } });
$('box').onsubmit = (e) => { e.preventDefault(); clearTimeout(autoTimer); const v = box.value.trim(); if (v) go(v); };
$('dirSel').onchange = () => {
  pref.dir = $('dirSel').value; keepPref();
  const v = box.value.trim(); if (v) go(v); else setDir(forcedFrom() || st.from);
};
$('hearInput').onclick = () => { const v = box.value.trim(); if (v) speak(v, TR_CHARS.test(v) ? 'tr' : st.from); };

// ---------------------------------------------------------------- go: translate, then the word card and checks
// "Say words": a looked-up word (not a sentence) is spoken in its own language, once.
let lastSaid = { text: '', at: 0 };
function autoSay(text, lang) {
  if (!pref.autoSay || text.split(/\s+/).length > MAX_CARD_WORDS) return;
  const now = Date.now();
  if (lastSaid.text === text && now - lastSaid.at < AUTO_SAY_REPEAT_MS) return;
  lastSaid = { text, at: now };
  speak(text, lang);
}
$('autoSay').onclick = () => { pref.autoSay = !pref.autoSay; keepPref(); renderPrefs(); toast(pref.autoSay ? 'Words are said aloud when you look them up' : 'Words are not said aloud'); };

async function go(text, { record: rec = true, from = forcedFrom() } = {}) {
  text = String(text || '').trim().slice(0, 1000);
  if (!text || !ls) { if (!ls) status(SERVICE_DOWN, true); return; }
  const mySeq = ++st.seq;
  st.text = text;
  if (box.value.trim() !== text) { box.value = text; grow(); }
  renderHistory();
  $('result').hidden = false; $('trOut').classList.add('pending');
  if (!st.translation) $('trOut').textContent = '…';
  $('trSource').textContent = ''; $('checkBox').textContent = ''; $('variantsBox').textContent = ''; $('keywords').hidden = true; $('trPron').hidden = true;
  $('card').hidden = true; cardSeq++;  // the previous word's card must not stay on screen
  status('');
  let r;
  try { r = await ls.translate(text, { from: from || 'auto' }); }
  catch (e) { if (mySeq === st.seq) { status(/fetch|network/i.test(e.message) ? SERVICE_DOWN : e.message, true); $('trOut').classList.remove('pending'); } return; }
  if (mySeq !== st.seq) return;
  st.translation = r.translation; setDir(r.from);
  st.english = r.from === 'en' ? text : r.translation;
  $('trLang').textContent = r.to === 'tr' ? 'Turkish' : 'English';
  $('trOut').textContent = r.translation; $('trOut').classList.remove('pending');
  $('trSource').textContent = r.source === 'dictionary' ? 'Oxford' : 'AI'; $('trSource').className = 'badge' + (r.source === 'dictionary' ? '' : ' ai');
  if (rec !== false) autoSay(text, r.from);  // not for the live dictation steps or the page-load restore
  $('trSource').title = r.source === 'dictionary' ? 'From the Oxford Turkish Dictionary' : 'Translated by the local language model';
  updateSaveButtons();
  const kind = text.split(/\s+/).length === 1 ? 'word' : 'sentence';
  if (rec === true) record(text, kind, r.translation, r.from);
  else if (rec === 'settle') setTimeout(() => { if (st.text === text && box.value.trim() === text) record(text, kind, r.translation, r.from); }, SETTLE_MS);

  // The English side: a word or short phrase gets its card; a sentence gets key words and a check.
  const english = st.english.split(',')[0].trim();
  // A word: the card has the translation, sound, test and save, so the translation box would only repeat it.
  if (isEnglishWordish(english)) { $('result').hidden = true; renderKeywords([]); loadCard(english.toLowerCase()); }
  else {
    $('card').hidden = true; st.cardWord = ''; renderKeywords(r.key_words || []);
    // Your English is checked first (the queue keeps the order), then other ways to say it.
    if (r.from === 'en') { loadCheck(text, r, mySeq); loadRewrite(text, mySeq); }
    else loadVariants(text, r, mySeq);
  }
}

function renderKeywords(words) {
  const k = $('keywords'); k.textContent = '';
  if (!words.length) { k.hidden = true; return; }
  k.appendChild(el('span', 'lbl', 'Words in it:'));
  words.forEach((w) => {
    const b = el('button', 'chip', w); b.type = 'button'; b.setAttribute('aria-current', w === st.cardWord);
    b.onclick = () => { loadCard(w); renderKeywords(words); };
    k.appendChild(b);
  });
  k.hidden = false;
}

async function loadCheck(text, r, mySeq) {
  const boxEl = $('checkBox');
  const wait = el('p', 'wait', 'Checking your English…'); boxEl.appendChild(wait);
  let c;
  try { c = await ls.check(text, r.translation, { from: r.from, to: r.to }); } catch (e) { if (mySeq === st.seq) wait.remove(); return; }
  if (mySeq !== st.seq) return;
  boxEl.textContent = '';
  if (!c.has_errors) return;
  const sec = el('div', 'check');
  sec.appendChild(el('h3', null, 'Correct English'));
  const p = el('p', 'corrected'); p.append(hearBtn(c.corrected), c.corrected); sec.appendChild(p);
  sec.appendChild(pairs(c.fixes.map((f) => [f.wrong, f.right, f.why_tr])));
  sec.appendChild(el('p', 'fine', 'Checked by the local language model.'));
  boxEl.appendChild(sec);
}

// Up to three translations, closest in meaning first, each named by its nuance ("Everyday and natural", "Stronger").
async function loadVariants(text, r, mySeq) {
  const boxEl = $('variantsBox');
  const wait = el('p', 'wait', 'Finding other ways to say it…'); boxEl.appendChild(wait);
  let v;
  try { v = await ls.variants(text, { from: r.from, to: r.to }); } catch (e) { if (mySeq === st.seq) wait.remove(); return; }
  if (mySeq !== st.seq) return;
  boxEl.textContent = '';
  const list = v.variants;  // all of them, the one matching the main translation too: its label names its tone
  if (!list.length) return;
  const sec = el('div', 'check');
  const h = el('h3', null, 'Closest in meaning'); h.appendChild(el('span', 'ai', 'AI')); sec.appendChild(h);
  const ul = el('ul', 'variants');
  list.forEach((x) => {
    const li = el('li');
    const t = el('span', 'txt'); t.append(hearBtn(x.text, r.to), x.text);
    li.append(el('span', 'lbl', x.label || '—'), t);
    ul.appendChild(li);
  });
  sec.appendChild(ul);
  boxEl.appendChild(sec);
}

// Better ways to write the English you typed (more natural, more formal, simpler), each named by what is better.
async function loadRewrite(text, mySeq) {
  const boxEl = $('variantsBox');
  const wait = el('p', 'wait', 'Finding better ways to write it…'); boxEl.appendChild(wait);
  let v;
  try { v = await ls.rewrite(text); } catch (e) { if (mySeq === st.seq) wait.remove(); return; }
  if (mySeq !== st.seq) return;
  boxEl.textContent = '';
  if (!v.versions.length) return;
  const sec = el('div', 'check');
  const h = el('h3', null, 'Better ways to write it'); h.appendChild(el('span', 'ai', 'AI')); sec.appendChild(h);
  const ul = el('ul', 'variants');
  v.versions.forEach((x) => {
    const li = el('li'); const t = el('span', 'txt'); t.append(hearBtn(x.text, 'en'), x.text);
    li.append(el('span', 'lbl', x.label || '—'), t); ul.appendChild(li);
  });
  sec.appendChild(ul); boxEl.appendChild(sec);
}

function pairs(rows) {
  const ul = el('ul', 'pairs');
  rows.forEach(([wrong, right, why]) => {
    const li = el('li'); const pr = el('span', 'pair');
    pr.append(el('del', null, wrong), el('span', 'why', '→'), el('ins', null, right));
    li.append(pr); if (why) li.appendChild(el('span', 'why', why)); ul.appendChild(li);
  });
  return ul;
}

// ---------------------------------------------------------------- listen, copy, test (translation box)
$('trHear').onclick = () => speak(st.translation, st.to);
$('trCopy').onclick = async () => { try { await navigator.clipboard.writeText(st.translation); toast('Copied'); } catch (e) { toast('Could not copy'); } };
$('trTest').onclick = () => runTest($('trTest'), $('trPron'), st.english);

let testing = null;
function runTest(btn, out, target, onStart) {
  if (testing) { testing.stop(); return; }
  if (!target || !testPronunciation) return;
  if (!canListen()) { toast('Speech input needs Chrome, Edge or Safari.'); return; }
  ls.stop();
  if (onStart) onStart();  // the result appears below the card: make room for it
  btn.classList.add('on'); btn.querySelector('.lbl').textContent = 'Listening… say it';
  out.hidden = false; out.textContent = ''; out.appendChild(el('p', 'msg', `Say: “${target}”`));
  testing = testPronunciation(ls, target, { lang: pref.accent === 'uk' ? 'en-GB' : 'en-US' });
  testing.then((r) => showScore(out, r)).catch((e) => { out.textContent = ''; out.appendChild(el('p', 'msg', e.message)); })
    .finally(() => { testing = null; btn.classList.remove('on'); btn.querySelector('.lbl').textContent = 'Test my pronunciation'; });
}
function showScore(out, r) {
  out.textContent = '';
  const line = el('p', 'line');
  line.appendChild(el('span', 'score', r.score + '%'));
  r.words.forEach((w, i) => {
    const s = el('span', 'w-' + w.status, w.word);
    if (w.heard) s.title = 'Heard: ' + w.heard;
    line.append(i ? ' ' : '', s);
  });
  const msg = r.verdict === 'clear' ? 'Clear — understood as you meant it.'
    : r.verdict === 'not heard' ? 'Nothing was heard. Check the microphone and try again.'
    : `Heard: “${r.heard}”. Red words were understood as another word: listen, then try again slowly.`;
  out.append(line, el('p', 'msg', msg));
}

// ---------------------------------------------------------------- word card
let cardSeq = 0;
async function loadCard(word) {
  const mySeq = ++cardSeq;
  st.cardWord = word;
  const card = $('card'); card.hidden = false; card.textContent = '';
  card.appendChild(el('p', 'wait', `Looking up “${word}”…`));
  let c;
  try { c = await ls.word(word); } catch (e) { if (mySeq === cardSeq) { card.textContent = ''; card.appendChild(el('p', 'status err', e.message)); } return; }
  if (mySeq !== cardSeq) return;
  st.cardWord = c.lemma;
  renderCard(c);
  renderSaved(); updateSaveButtons();
  ls.examples(c.lemma).then((x) => { if (mySeq === cardSeq) renderExamples(x); }).catch(() => {});
  ls.fill(c.lemma).then((f) => { if (mySeq === cardSeq) applyFill(c, f); }).catch(() => {});
  // Neither dictionary has it ("bicycle bay", a new word): the local model explains it, marked AI.
  if (!c.meanings.length && !c.turkish.length && !c.tr) {
    ls.senses(c.lemma).then((r) => { if (mySeq === cardSeq) applySenses(c, r.senses || []); }).catch(() => { if (mySeq === cardSeq) applySenses(c, []); });
  }
}

// Turkish that arrived from the model after the card was drawn: Save uses it, and a word saved before it came gets it too
// (the quiz needs a Turkish meaning for every saved word).
function adoptTr(c, tr) {
  if (c.tr || !tr) return;
  c.tr = tr;
  const s = saved.words.find((w) => w.text === c.lemma);
  if (s && !s.tr) saveItem('word', c.lemma, tr, true);
}

function applySenses(c, list) {
  const ai = () => el('span', 'ai', 'AI');
  const trSec = $('trFill');
  if (!list.length) {
    if (trSec) { trSec.querySelectorAll('.wait').forEach((n) => n.remove()); trSec.appendChild(el('p', 'wait', 'The language model could not explain this. Check the spelling.')); }
    return;
  }
  if (trSec) {
    trSec.querySelectorAll('.wait, .c-tr').forEach((n) => n.remove());
    const p = el('p', 'c-tr', [...new Set(list.map((x) => x.tr))].slice(0, 4).join(', ')); p.appendChild(ai()); trSec.appendChild(p);
  }
  adoptTr(c, [...new Set(list.map((x) => x.tr))].slice(0, 3).join(', '));
  const s = section('Meanings', 'Local language model (AI): check it against a dictionary');
  const ol = el('ol', 'defs');
  list.forEach((x) => {
    const li = el('li'); const d = el('p', 'd');
    d.append(el('span', 'g', x.pos), x.en, ' ', el('span', 'ind', '— ' + x.tr));
    li.appendChild(d);
    if (x.example) { const p = el('p', 'ex'); p.append(hearBtn(x.example), x.example, el('span', 'tr', x.example_tr)); li.appendChild(p); }
    ol.appendChild(li);
  });
  s.appendChild(ol);
  if (trSec) trSec.after(s); else $('card').appendChild(s);
}

const FREQ_DOTS = { 'very common': 5, common: 4, moderate: 3, uncommon: 2, rare: 1 };
function freqRow(f) {
  const p = el('p', 'freq'); p.title = `Zipf ${f.zipf} (wordfreq: Wikipedia, subtitles, news, books, web)`;
  const dots = el('span', 'dots'); dots.setAttribute('aria-hidden', 'true');
  for (let i = 1; i <= 5; i++) dots.appendChild(el('i', i <= FREQ_DOTS[f.band] ? 'on' : ''));
  const [label, detail] = f.en.split(' — ');
  p.append(dots, el('strong', null, label), detail || '');
  if (f.rank) p.append(` · #${f.rank.toLocaleString('en-US')} most used word`);
  if (f.estimate) p.append(' · estimate for a phrase');
  return p;
}

function section(title, src) {
  const s = el('section', 'sec'); const h = el('div', 'sec-head');
  h.appendChild(el('h3', null, title)); if (src) h.appendChild(el('span', 'src', src));
  s.appendChild(h); return s;
}

const MOUTH_SLOW = 0.6;  // slowest speed the voice allows: each sound stays long enough to watch
let mouth = null;
function renderCard(c) {
  if (mouth) { mouth.destroy(); mouth = null; }
  const card = $('card'); card.textContent = '';
  // head: word, parts of speech, IPA with sound, save, test
  const head = el('div', 'c-head');
  head.appendChild(el('h2', null, c.lemma));
  c.pos.forEach((p) => head.appendChild(el('span', 'pos', p)));
  [['us', 'US'], ['uk', 'UK']].forEach(([acc, name]) => {
    if (!c.ipa[acc]) return;
    const b = el('button', 'ipa'); b.type = 'button'; b.title = `Listen (${name})`;
    b.append(el('span', 'play'), el('span', 'acc', name), el('span', 't', c.ipa[acc]));
    b.onclick = () => { if (ls) ls.speak(c.lemma, { lang: 'en', accent: acc, speed: pref.speed }); };
    head.appendChild(b);
  });
  // The actions get a row of their own: on one wrapping line they broke apart (two below, one at the far right).
  const actions = el('div', 'tools c-actions');
  const save = el('button', 'btn'); save.type = 'button'; save.id = 'cardSave';
  save.onclick = () => (isSaved('word', c.lemma) ? unsave('word', c.lemma) : saveItem('word', c.lemma, c.tr));
  const test = el('button', 'btn rec'); test.type = 'button'; test.append(el('span', 'dot'), el('span', 'lbl', 'Test my pronunciation'));
  const mouthBtn = el('button', 'btn', 'Mouth & tongue'); mouthBtn.type = 'button';
  mouthBtn.title = 'See how the lips and the tongue move for this word';
  actions.append(save, test, mouthBtn);
  card.append(head, actions);
  const mouthBox = el('div', 'mo'); card.appendChild(mouthBox);
  const openMouth = (open) => {
    pref.mouth = open; keepPref();
    mouthBtn.setAttribute('aria-pressed', open ? 'true' : 'false');
    mouthBox.hidden = !open;
    if (mouth) { mouth.destroy(); mouth = null; }
    if (!open) return;
    const ipa = c.ipa[pref.accent] || c.ipa.us || c.ipa.uk;
    const stage = el('div');
    const bar = el('div', 'tools');
    const playB = el('button', 'btn'); playB.type = 'button'; playB.append(el('span', 'play'), 'Play');
    const slowB = el('button', 'btn'); slowB.type = 'button'; slowB.append(el('span', 'play'), 'Slow');
    bar.append(playB, slowB, el('span', 'mo-ipa', ipa));
    mouthBox.textContent = '';
    mouthBox.append(bar, stage);
    mouth = mountMouth(stage, { ipa, audioUrl: (speed) => ls.ttsUrl(c.lemma, { lang: 'en', accent: pref.accent, speed }) });
    playB.onclick = () => mouth.play(pref.speed);
    slowB.onclick = () => mouth.play(MOUTH_SLOW);
  };
  mouthBtn.onclick = () => openMouth(!pref.mouth);
  openMouth(pref.mouth);
  const pron = el('div', 'pron'); pron.hidden = true; pron.setAttribute('aria-live', 'polite'); card.appendChild(pron);
  test.onclick = () => runTest(test, pron, c.lemma, () => { if (pref.mouth) openMouth(false); });
  if (c.frequency) card.appendChild(freqRow(c.frequency));
  if (c.note) card.appendChild(el('p', 'note', c.note));
  if (!c.known) card.appendChild(el('p', 'status err', 'This word is not in the dictionaries. Check the spelling.'));

  // Turkish
  if (c.tr || c.turkish.length) {
    const s = section('Turkish', 'Oxford Turkish Dictionary');
    if (c.tr) s.appendChild(el('p', 'c-tr', c.tr));
    if (c.turkish.length) {
      const ul = el('ul', 'trlist');
      c.turkish.forEach((b) => {
        const li = el('li'); li.appendChild(el('span', 'pos', b.pos));
        const v = el('span', 'v');
        b.senses.forEach((x, i) => {
          if (i) v.append(' · ');
          v.append(x.tr.join(', '));
          if (x.for) v.append(' ', el('span', 'ind', `(${x.for})`));
        });
        li.appendChild(v); ul.appendChild(li);
      });
      s.appendChild(ul);
    }
    if (c.turkish_phrases.length) {
      const ul = el('ul', 'trlist');
      c.turkish_phrases.forEach((p) => { const li = el('li'); li.append(el('span', 'v', p.en), el('span', 'ind', '→ ' + p.tr)); ul.appendChild(li); });
      s.appendChild(ul);
    }
    card.appendChild(s);
  } else {
    const s = section('Turkish'); s.id = 'trFill'; s.appendChild(el('p', 'wait', 'Finding the Turkish…')); card.appendChild(s);
  }

  // Meanings
  if (c.meanings.length) {
    const s = section('Meanings', 'New Oxford American Dictionary');
    c.meanings.forEach((m, mi) => {
      s.appendChild(el('p', 'pos-h', m.pos));
      const ol = el('ol', 'defs'); ol.dataset.pos = m.pos;
      m.senses.forEach((x, i) => {
        const li = el('li'); const d = el('p', 'd');
        if (x.grammar.length) d.appendChild(el('span', 'g', x.grammar.join(', ')));
        if (x.register) d.appendChild(el('span', 'g', x.register));
        d.append(x.def);
        const fill = el('span', 'ind'); fill.dataset.fill = `${m.pos}|${i}`; d.append(' ', fill);
        li.appendChild(d);
        x.examples.forEach((ex) => { const p = el('p', 'ex'); p.append(hearBtn(ex), ex); li.appendChild(p); });
        x.sub.forEach((sub) => li.appendChild(el('p', 'sub', sub.def + (sub.examples[0] ? ` — “${sub.examples[0]}”` : ''))));
        ol.appendChild(li);
      });
      s.appendChild(ol);
    });
    card.appendChild(s);
  }

  // Grammar: -ing or to, stative, prepositions, typical mistakes
  const g = section('How to use it');
  if (c.complement) {
    const p = el('div', 'pattern');
    p.append(el('span', 'kind', c.complement.kind), el('p', null, c.complement.en), el('p', 'trr', c.complement.tr));
    if (c.complement.contrast.length) {
      const ul = el('ul', 'contrast');
      c.complement.contrast.forEach((x) => {
        const li = el('li'); const ex = el('span', 'ex'); ex.append(hearBtn(x.example), x.example);
        li.append(el('span', 'f', x.form), el('span', null, x.en + ' — ' + x.tr), ex); ul.appendChild(li);
      });
      p.appendChild(ul);
    }
    g.appendChild(p);
  }
  if (c.aspect && c.aspect.en) g.appendChild(el('p', 'aspect', `${c.aspect.en} ${c.aspect.tr}`));
  if (c.prepositions.length) {
    g.appendChild(el('h3', null, 'With prepositions'));
    g.appendChild(phraseList(c.prepositions.map((p) => ({ phrase: p.phrase, tr: p.tr, def: '' }))));
  }
  if (c.mistakes.length) {
    g.appendChild(el('h3', null, 'Typical mistakes'));
    const ul = el('ul', 'mistakes');
    c.mistakes.forEach((m) => {
      const li = el('li'); const pr = el('span', 'pair');
      pr.append(el('del', null, m.wrong), el('span', 'why', '→'), el('ins', null, m.right));
      li.append(pr, el('span', 'why', m.why_tr)); ul.appendChild(li);
    });
    g.appendChild(ul);
  }
  if (g.childNodes.length > 1) card.appendChild(g);

  // Forms and word family
  if (c.forms.length || Object.keys(c.family).length) {
    const s = section('Forms and word family');
    if (c.forms.length) {
      const f = el('div', 'forms');
      c.forms.forEach((x) => {
        const b = el('button', 'form'); b.type = 'button'; b.title = 'Listen';
        b.append(el('span', 'l', x.label), el('span', 'f', x.form));
        b.onclick = () => speak(x.form.replace(/\s*\(.*?\)/g, ''), 'en');
        f.appendChild(b);
      });
      if (c.irregular) f.appendChild(el('span', 'irr', 'irregular'));
      s.appendChild(f);
    }
    const groups = Object.entries(c.family);
    if (groups.length) {
      const fam = el('div', 'family');
      groups.forEach(([pos, words]) => {
        const grp = el('div', 'grp'); grp.appendChild(el('h4', null, pos));
        const ul = el('ul');
        words.forEach((w) => {
          const li = el('li'); const b = el('button', 'w', w.word); b.type = 'button'; b.onclick = () => go(w.word);
          const tr = el('span', 'ind', w.tr ? ' ' + w.tr : ''); tr.dataset.fillFamily = w.word;
          li.append(b, tr); ul.appendChild(li);
        });
        grp.appendChild(ul); fam.appendChild(grp);
      });
      s.appendChild(fam);
    }
    card.appendChild(s);
  }

  // Phrasal verbs and idioms
  if (c.phrasal_verbs.length || c.idioms.length) {
    const s = section('Phrasal verbs and idioms', 'Oxford');
    if (c.phrasal_verbs.length) s.appendChild(phraseList(c.phrasal_verbs, 'phrasal'));
    if (c.idioms.length) { s.appendChild(el('h3', null, 'Idioms')); s.appendChild(phraseList(c.idioms, 'idiom')); }
    card.appendChild(s);
  }

  // Tenses
  if (c.tenses && c.tenses.length) {
    const d = el('details', 'tenses sec');
    d.appendChild(el('summary', null, 'All tenses (with I / she, negative, question)'));
    const ul = el('ul', 'tense-list');
    c.tenses.forEach((t) => {
      const li = el('li', t.ok ? '' : 'no');
      li.append(el('span', 'n', t.tense), el('span', null, `${t.i} · ${t.she}`), el('span', 'neg', `${t.negative} · ${t.question}`));
      if (t.note) li.appendChild(el('p', 'note', t.note));
      ul.appendChild(li);
    });
    d.appendChild(ul); card.appendChild(d);
  }

  const ex = section('In real sentences', 'Tatoeba'); ex.id = 'examplesSec'; ex.appendChild(el('p', 'wait', 'Loading examples…'));
  card.appendChild(ex);
}

function phraseList(items, kind) {
  const ul = el('ul', 'phr');
  items.forEach((p) => {
    const li = el('li');
    const ph = el('span', 'p'); ph.append(hearBtn(p.phrase.replace(/\s*\(.*?\)/g, '')), p.phrase);
    const tr = el('span', 'tr', p.tr || ''); if (kind) tr.dataset.fillPhrase = kind + '|' + p.phrase;
    li.append(ph, tr);
    if (p.def) li.appendChild(el('span', 'd', p.def + (p.example ? ` — “${p.example}”` : '')));
    ul.appendChild(li);
  });
  return ul;
}

function renderExamples(x) {
  const s = $('examplesSec'); if (!s) return;
  s.querySelectorAll('.wait, .examples, .fine').forEach((n) => n.remove());
  if (!x.examples.length) { s.appendChild(el('p', 'fine', 'No example sentences found.')); return; }
  const ul = el('ul', 'examples');
  x.examples.forEach((e) => { const li = el('li'); li.append(hearBtn(e.en), e.en, el('span', 'tr', e.tr)); ul.appendChild(li); });
  s.appendChild(ul);
}

// Turkish from the model for items the dictionary lacked: marked "AI".
function applyFill(c, f) {
  const ai = () => el('span', 'ai', 'AI');
  const trSec = $('trFill');
  if (trSec) {
    trSec.querySelectorAll('.wait').forEach((n) => n.remove());
    const vals = Object.values(f.meanings || {});
    if (vals.length) { const p = el('p', 'c-tr', [...new Set(vals)].slice(0, 4).join(', ')); p.appendChild(ai()); trSec.appendChild(p); adoptTr(c, [...new Set(vals)].slice(0, 3).join(', ')); }
  }
  Object.entries(f.meanings || {}).forEach(([key, tr]) => {
    const n = document.querySelector(`[data-fill="${CSS.escape(key)}"]`); if (n) { n.textContent = '— ' + tr; n.appendChild(ai()); }
  });
  [['phrasal', f.phrasal_verbs], ['idiom', f.idioms]].forEach(([kind, map]) => Object.entries(map || {}).forEach(([phrase, tr]) => {
    const n = document.querySelector(`[data-fill-phrase="${CSS.escape(kind + '|' + phrase)}"]`);
    if (n && !n.textContent) { n.textContent = tr; n.appendChild(ai()); }
  }));
  Object.entries(f.family || {}).forEach(([word, tr]) => {
    const n = document.querySelector(`[data-fill-family="${CSS.escape(word)}"]`);
    if (n && !n.textContent.trim()) { n.textContent = ' ' + tr; n.appendChild(ai()); }
  });
}

// ---------------------------------------------------------------- dictation: click = until you pause, right-click = stays on
const LIVE_MS = 600;   // translate what was said this long after the last word, while still listening
let dictation = null;
function startMic(keepOpen) {
  if (!listen) { status(SERVICE_DOWN, true); return; }
  ls.stop();
  const from = forcedFrom() || st.from, mic = $('mic');
  mic.setAttribute('aria-pressed', 'true'); mic.classList.toggle('hold', keepOpen);
  const spoken = from === 'tr' ? 'Turkish' : 'English';
  status(keepOpen ? `The microphone stays on (${spoken}) — click it again to stop.`
    : `Listening… speak ${spoken}. It stops when you pause.`);
  let said = '', liveT = 0, busy = false, pending = '';
  const live = async (text) => {
    // One translation at a time; while one runs only the newest text waits.
    if (busy) { pending = text; return; }
    busy = true; await go(text, { record: false, from }); busy = false;
    if (pending && pending !== text) { const p = pending; pending = ''; live(p); }
  };
  const stop = listen({
    lang: from === 'tr' ? 'tr-TR' : (pref.accent === 'uk' ? 'en-GB' : 'en-US'), keepOpen,
    onText: (fin, interim) => {
      said = [fin, interim].filter(Boolean).join(' '); box.value = said; grow();
      clearTimeout(liveT); liveT = setTimeout(() => live(said), LIVE_MS);
    },
    onEnd: (err) => {
      clearTimeout(liveT); dictation = null;
      mic.setAttribute('aria-pressed', 'false'); mic.classList.remove('hold');
      status(err && !said ? err : '', !!err && !said);
      if (said) go(said.split(/\s+/).length < 4 ? said.replace(/[.?!]+$/, '') : said, { from });
    }
  });
  dictation = { stop };
}
$('mic').onclick = (e) => { if (dictation) dictation.stop(); else startMic(e.shiftKey); };
$('mic').oncontextmenu = (e) => { e.preventDefault(); if (dictation) dictation.stop(); else startMic(true); };

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && dictation) { dictation.stop(); return; }
  if (e.key === '/' && !e.target.closest('input, textarea, select')) { e.preventDefault(); box.focus(); box.select(); }
});

// ---------------------------------------------------------------- start
renderPrefs(); grow();
if (!ls) status(SERVICE_DOWN, true);
else { fetch(SERVICES + '/v1/warm').catch(() => {}); if (!canListen()) $('mic').hidden = true; }
await Promise.all([loadHistory(), loadSaved()]);
if (ls) initChat({ api, ls, pref, keepPref, el, getSaved: () => saved });
if (history[0] && ls) go(history[0].text, { record: false });
