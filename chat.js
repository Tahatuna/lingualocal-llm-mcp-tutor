// The teacher chat: a right-hand panel to talk to the local model as an English teacher (sentence checks, quizzes from
// your saved words, exercises). Every chat is kept in your data (see /api/chats) side by side: pick one, rename it,
// delete it. A new chat is stored only once you write in it, so "New chat" never leaves empty ones behind.
const MAX_CONTEXT_WORDS = 80;     // saved words sent along so the teacher can quiz you on them
const MAX_INPUT = 1000;
const QUIZ_KEY = 'pm.quiz';
const STOP_WORDS = new Set(['stop', 'quit', 'exit', 'bitir', 'dur']);
const UNNAMED = 'New chat';
const QUIZ_TITLE = 'Saved-words quiz';

// Quiz answers are checked here, not by the model: it would otherwise invent words and mark answers wrongly.
export const norm = (t) => t.toLocaleLowerCase('tr').replace(/[.!?"'“”‘’()]/g, '').replace(/\s+/g, ' ').trim();
export const alternatives = (tr) => tr.split(/[,;/]|\sveya\s/).map(norm).filter(Boolean);
// The quiz is decided by code, never by the model: questions come only from saved words that have a Turkish meaning.
export const quizPool = (words) => words.filter((w) => w.text && w.tr);
export function pickWord(pool, last, rand = Math.random) {
  const choices = pool.length > 1 ? pool.filter((w) => w.text !== last) : pool;  // never the same word twice in a row
  return choices[Math.floor(rand() * choices.length)];
}
export const isRightAnswer = (q, text) =>
  q.toTurkish ? alternatives(q.tr).includes(norm(text)) : norm(text) === norm(q.word);

export function initChat({ api, ls, pref, keepPref, el, getSaved }) {
  const $ = (id) => document.getElementById(id);
  const panel = $('chat'), log = $('chatLog'), input = $('chatInput'), form = $('chatForm'), btn = $('chatBtn');
  const pick = $('chatPick'), titleIn = $('chatTitle'), more = $('chatMore'), menu = $('chatMenu');
  let messages = [], busy = false;
  let chats = [], chatId = null;   // chatId null: a new chat that is not stored yet
  let newTitle = '';               // the name a new chat gets when it is stored ('' = its first question)
  let saving = Promise.resolve();  // messages are stored one after another, in order

  // Plain text with line breaks, **bold** and "* " bullets: built from nodes, so nothing the model writes is run as HTML.
  function rich(parent, text) {
    text.split('\n').forEach((line, i) => {
      if (i) parent.appendChild(document.createElement('br'));
      line = line.replace(/^\s*[*-]\s+/, '• ');
      line.split(/(\*\*[^*]+\*\*)/).forEach((part) => {
        if (/^\*\*[^*]+\*\*$/.test(part)) parent.appendChild(el('strong', null, part.slice(2, -2)));
        else if (part) parent.appendChild(document.createTextNode(part.replace(/\*([^*]+)\*/g, '$1')));
      });
    });
  }
  function bubble(role, text) {
    const b = el('div', 'msg ' + role); rich(b, text); log.appendChild(b); log.scrollTop = log.scrollHeight; return b;
  }
  function redraw() {
    log.textContent = '';
    if (!messages.length) log.appendChild(el('p', 'chat-hint', 'Your English teacher. Ask anything or paste a sentence to check. Every chat is kept: pick an earlier one above, and rename it or start a quiz from your saved words with ⋯.'));
    messages.forEach((m) => bubble(m.role, m.content));
  }
  function context() {
    const words = getSaved().words.slice(0, MAX_CONTEXT_WORDS);
    return words.length ? 'Saved words: ' + words.map((w) => (w.tr ? `${w.text} = ${w.tr}` : w.text)).join('; ') : '';
  }
  // The first message of a new chat creates it; switching chats waits while the teacher is answering (busy), so a
  // reply always lands in the chat it belongs to.
  function keep(role, content) {
    saving = saving.then(async () => {
      if (chatId == null) { const c = await api('/api/chats/new', { title: newTitle }); newTitle = ''; chats.unshift(c); chatId = c.id; rememberChat();
        if (quiz && quiz.chat == null) { quiz.chat = c.id; keepQuiz(); }
      }
      await api('/api/chat/add', { chat_id: chatId, role, content });
      await loadChats();
    }).catch(() => { /* the chat still works; it is just not kept */ });
    return saving;
  }

  async function ask() {
    setBusy(true);
    const wait = el('div', 'msg assistant wait', 'Thinking…'); log.appendChild(wait); log.scrollTop = log.scrollHeight;
    try {
      const r = await ls.chat(messages.map(({ role, content }) => ({ role, content })), context());
      wait.remove();
      messages.push({ role: 'assistant', content: r.reply }); bubble('assistant', r.reply); keep('assistant', r.reply);
    } catch (e) {
      wait.remove();
      const err = el('div', 'msg err', /fetch|network/i.test(e.message) ? 'Language Services is not running.' : e.message);
      const retry = el('button', 'link', 'Try again'); retry.type = 'button';
      retry.onclick = () => { err.remove(); ask(); };
      err.append(' ', retry); log.appendChild(err); log.scrollTop = log.scrollHeight;
    } finally { setBusy(false); }
  }
  function say(role, text) {
    if (!messages.length) log.textContent = '';
    messages.push({ role, content: text }); bubble(role, text); keep(role, text);
  }

  // ---- quiz from your saved words
  let quiz = null;
  try { quiz = JSON.parse(localStorage.getItem(QUIZ_KEY) || 'null'); } catch (e) { quiz = null; }
  const keepQuiz = () => { try { if (quiz) localStorage.setItem(QUIZ_KEY, JSON.stringify(quiz)); else localStorage.removeItem(QUIZ_KEY); } catch (e) { /* optional */ } };
  const usable = () => quizPool(getSaved().words);
  function question() {
    const w = pickWord(usable(), quiz.word);
    const toTurkish = Math.random() < 0.5;
    quiz.word = w.text; quiz.tr = w.tr; quiz.toTurkish = toTurkish; keepQuiz();
    return toTurkish ? `Question ${quiz.asked + 1}: what does **${w.text}** mean in Turkish?`
      : `Question ${quiz.asked + 1}: which English word or phrase means **${alternatives(w.tr)[0]}**?`;
  }
  function startQuiz() {
    if (!usable().length) { say('assistant', 'Save a few words first (press “Save word” on a word card), then I can quiz you on them.'); return; }
    if (chatId == null && !messages.length) newTitle = QUIZ_TITLE;
    quiz = { asked: 0, right: 0, chat: chatId };
    say('assistant', `A quiz from your ${usable().length} saved word${usable().length === 1 ? '' : 's'}. Answer each question; type “stop” to finish.\n\n${question()}`);
    input.focus();
  }
  function endQuiz() {
    const done = quiz; quiz = null; keepQuiz();
    say('assistant', done.asked ? `Quiz finished: ${done.right} of ${done.asked} right.` : 'Quiz stopped.');
  }
  function answer(text) {
    say('user', text);
    if (STOP_WORDS.has(norm(text))) { endQuiz(); return; }
    const ok = isRightAnswer(quiz, text);
    quiz.asked += 1; if (ok) quiz.right += 1;
    const shown = quiz.toTurkish ? quiz.tr : quiz.word;
    const verdict = ok ? 'Correct!' : `Not quite. The answer: **${shown}** (${quiz.word}${quiz.toTurkish ? ' = ' + quiz.tr : ''}).`;
    say('assistant', `${verdict} Score: ${quiz.right}/${quiz.asked}.\n\n${question()}`);
  }

  function send(text) {
    text = String(text || '').trim().slice(0, MAX_INPUT);
    if (!text || busy) return;
    input.value = ''; grow();
    if (quiz && usable().length) { answer(text); return; }
    if (quiz) { quiz = null; keepQuiz(); }
    say('user', text); ask();
  }
  function grow() { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 140) + 'px'; }

  form.onsubmit = (e) => { e.preventDefault(); send(input.value); };
  input.addEventListener('input', grow);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); form.requestSubmit(); } });
  function setBusy(on) {
    busy = on; form.classList.toggle('busy', on);
    pick.disabled = on; $('chatNew').disabled = on; more.disabled = on;
  }

  // ---- which chat
  const titleOf = (c) => c.title || UNNAMED;
  function rememberChat() { pref.chatId = chatId; keepPref(); }
  function drawPicker() {
    pick.textContent = '';
    if (chatId == null) { const o = el('option', null, UNNAMED); o.value = ''; pick.appendChild(o); }
    chats.forEach((c) => { const o = el('option', null, titleOf(c)); o.value = String(c.id); o.title = titleOf(c); pick.appendChild(o); });
    pick.value = chatId == null ? '' : String(chatId);
    pick.title = chatId == null ? UNNAMED : titleOf(chats.find((c) => c.id === chatId) || {});
  }
  async function loadChats() {
    try { chats = await api('/api/chats'); } catch (e) { /* keep what is shown */ }
    if (chatId != null && !chats.some((c) => c.id === chatId)) chatId = null;
    drawPicker();
  }
  async function openChat(id) {
    chatId = id; newTitle = ''; rememberChat(); drawPicker();
    if (quiz && quiz.chat !== id) { quiz = null; keepQuiz(); }  // a quiz belongs to the chat it was started in
    messages = [];
    if (id != null) { try { messages = await api('/api/chat?id=' + id); } catch (e) { messages = []; } }
    if (chatId === id) redraw();
  }
  pick.onchange = () => { if (busy) return; openChat(pick.value ? Number(pick.value) : null); };
  $('chatNew').onclick = async () => {
    if (busy) return;
    await saving;
    if (chatId != null || messages.length) await openChat(null);  // the current chat stays in the list
    input.focus();
  };

  function startRename() {
    if (chatId == null) return;
    titleIn.value = (chats.find((c) => c.id === chatId) || {}).title || '';
    pick.hidden = true; titleIn.hidden = false; titleIn.focus(); titleIn.select();
  }
  let renaming = false;
  async function endRename(commit) {
    if (titleIn.hidden || renaming) return;
    renaming = true;
    const id = chatId, title = titleIn.value.trim();
    titleIn.hidden = true; pick.hidden = false;
    if (commit && id != null) { try { await api('/api/chats/rename', { id, title }); await loadChats(); } catch (e) { /* keeps the old name */ } }
    renaming = false; pick.focus();
  }
  titleIn.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.isComposing) { e.preventDefault(); endRename(true); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); endRename(false); }
  });
  titleIn.addEventListener('blur', () => endRename(true));

  async function deleteChat() {
    const c = chats.find((x) => x.id === chatId); if (!c) return;
    if (!confirm(`Delete the chat “${titleOf(c)}” and its ${c.count} message${c.count === 1 ? '' : 's'}? This can’t be undone.`)) return;
    try { await api('/api/chats/delete', { id: c.id }); } catch (e) { return; }
    chats = chats.filter((x) => x.id !== c.id);
    await openChat(chats.length ? chats[0].id : null);
  }

  // ---- the ⋯ menu: arrow keys, Escape gives the focus back, a click outside closes it
  const items = () => [...menu.querySelectorAll('[role="menuitem"]')].filter((b) => !b.disabled);
  function openMenu(byKeyboard) {
    menu.querySelector('[data-act="rename"]').disabled = chatId == null;
    menu.querySelector('[data-act="delete"]').disabled = chatId == null;
    menu.querySelector('[data-act="quiz"]').textContent = quiz ? 'Stop the quiz' : 'Quiz me on my saved words';
    menu.hidden = false; more.setAttribute('aria-expanded', 'true');
    if (byKeyboard) items()[0]?.focus();
  }
  function closeMenu(focusBack) {
    if (menu.hidden) return;
    menu.hidden = true; more.setAttribute('aria-expanded', 'false');
    if (focusBack) more.focus();
  }
  more.onclick = (e) => { if (menu.hidden) openMenu(e.detail === 0); else closeMenu(false); };
  menu.addEventListener('keydown', (e) => {
    const list = items(), i = list.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); list[(i + 1) % list.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); list[(i - 1 + list.length) % list.length].focus(); }
    else if (e.key === 'Home') { e.preventDefault(); list[0].focus(); }
    else if (e.key === 'End') { e.preventDefault(); list[list.length - 1].focus(); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeMenu(true); }
    else if (e.key === 'Tab') closeMenu(false);
  });
  document.addEventListener('pointerdown', (e) => { if (!menu.hidden && !menu.contains(e.target) && e.target !== more) closeMenu(false); });
  menu.onclick = (e) => {
    const act = e.target.closest('[role="menuitem"]')?.dataset.act; if (!act || busy) return;
    closeMenu(false);
    if (act === 'rename') startRename();
    else if (act === 'delete') deleteChat();
    else if (act === 'quiz') { if (quiz) endQuiz(); else startQuiz(); }
  };

  function setOpen(open, focus) {
    pref.chat = open; keepPref();
    panel.hidden = !open; document.querySelector('.layout').classList.toggle('has-chat', open);
    btn.setAttribute('aria-expanded', String(open)); btn.setAttribute('aria-pressed', String(open));
    if (open && focus) input.focus();
  }
  btn.onclick = () => setOpen(!pref.chat, true);
  $('chatClose').onclick = () => { setOpen(false); btn.focus(); };
  panel.addEventListener('keydown', (e) => { if (e.key === 'Escape') { setOpen(false); btn.focus(); } });

  setOpen(!!pref.chat && !window.matchMedia('(max-width: 900px)').matches, false);  // a phone opens it on demand
  // The chat you had open last, else the newest one.
  loadChats().then(() => {
    const last = chats.find((c) => c.id === pref.chatId);
    return openChat(last ? last.id : chats.length ? chats[0].id : null);
  });
}
