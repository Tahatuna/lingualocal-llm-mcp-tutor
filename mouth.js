// Mouth and tongue for a word: a front view (lips, teeth) and a side cut (where the tongue touches), moving with the
// voice. Each sound can be held to read what the mouth does. Brought over from the first version of the app.
//   const m = mountMouth(container, { word, ipa, audioUrl: (speed) => url });  m.play(speed); m.destroy();

// Articulation targets. Front view: o = jaw open, w = lip spread, r = lip rounding, t = teeth visible,
// bite = upper teeth on lower lip, th = tongue between teeth, tip = tongue tip raised, nas = soft palate lowered.
// Side view: tg = tongue control points [tipX, tipY, bladeX, bladeY, dorsumX, dorsumY, rootX] in side-view coordinates.
const VIS = {
  rest: { o: 0.04, w: 0.1, r: 0, t: 0.1, tg: [98, 186, 130, 165, 190, 150, 250] },
  A:    { o: 0.85, w: 0.2, r: 0.15, t: 0.3, tg: [100, 212, 135, 200, 212, 170, 262] },
  AE:   { o: 0.7, w: 0.65, r: 0, t: 0.6, tg: [98, 205, 130, 184, 180, 166, 252] },
  E:    { o: 0.45, w: 0.55, r: 0, t: 0.7, tg: [97, 198, 128, 168, 175, 146, 248] },
  I:    { o: 0.18, w: 0.95, r: 0, t: 0.9, tg: [96, 190, 125, 146, 165, 110, 240] },
  IH:   { o: 0.3, w: 0.6, r: 0, t: 0.8, tg: [97, 194, 126, 156, 168, 121, 244] },
  U:    { o: 0.16, w: 0, r: 1, t: 0, tg: [100, 195, 135, 175, 215, 112, 252] },
  O:    { o: 0.5, w: 0, r: 0.8, t: 0.2, tg: [100, 200, 135, 185, 210, 135, 256] },
  UH:   { o: 0.55, w: 0.3, r: 0, t: 0.4, tg: [99, 202, 132, 182, 195, 150, 254] },
  ER:   { o: 0.3, w: 0.1, r: 0.55, t: 0.3, tg: [128, 136, 142, 154, 190, 128, 252] },
  F:    { o: 0.1, w: 0.4, r: 0, t: 0.6, bite: 1, tg: [98, 188, 130, 167, 190, 148, 250] },
  TH:   { o: 0.2, w: 0.4, r: 0, t: 1, th: 1, tg: [78, 157, 104, 150, 180, 140, 250] },
  MBP:  { o: 0, w: 0.2, r: 0, t: 0, tg: [98, 186, 130, 165, 190, 150, 250] },
  M:    { o: 0, w: 0.2, r: 0, t: 0, nas: 1, tg: [98, 186, 130, 165, 190, 150, 250] },
  L:    { o: 0.35, w: 0.4, r: 0, t: 0.7, tip: 1, tg: [100, 118, 118, 131, 185, 150, 252] },
  TD:   { o: 0.14, w: 0.5, r: 0, t: 1, tg: [100, 117, 120, 122, 180, 138, 250] },
  N:    { o: 0.14, w: 0.5, r: 0, t: 1, nas: 1, tg: [100, 117, 120, 122, 180, 138, 250] },
  K:    { o: 0.3, w: 0.35, r: 0, t: 0.5, tg: [100, 196, 140, 170, 222, 101, 252] },
  NG:   { o: 0.3, w: 0.35, r: 0, t: 0.5, nas: 1, tg: [100, 196, 140, 170, 222, 101, 252] },
  SH:   { o: 0.2, w: 0.2, r: 0.6, t: 0.9, tg: [106, 135, 125, 124, 180, 135, 250] },
  W:    { o: 0.12, w: 0, r: 1, t: 0, tg: [100, 195, 135, 175, 215, 112, 252] },
  S:    { o: 0.12, w: 0.6, r: 0, t: 1, tg: [104, 126, 122, 124, 180, 138, 250] },
  H:    { o: 0.35, w: 0.3, r: 0, t: 0.4, tg: [99, 198, 132, 178, 192, 150, 252] }
};

// What happens inside the mouth for each target. contact: point in side view, 'lips', or null. near: close but no touch.
const NOTES = {
  TD:  { place: 'Tongue tip on the ridge behind the upper teeth', how: 'Block the air, then let it go.', contact: [101, 115] },
  N:   { place: 'Tongue tip on the ridge, soft palate lowered', how: 'Air leaves through the nose.', contact: [101, 115] },
  L:   { place: 'Tongue tip on the ridge behind the upper teeth', how: 'Air flows around the sides of the tongue.', contact: [101, 115] },
  TH:  { place: 'Tongue tip lightly between the teeth', how: 'Blow air over the tongue. Don’t press.', contact: [79, 156] },
  F:   { place: 'Upper teeth rest on the lower lip', how: 'Push air through the narrow gap.', contact: [79, 151] },
  MBP: { place: 'Both lips pressed together', how: 'Close, build a little pressure, open.', contact: 'lips' },
  M:   { place: 'Both lips together, soft palate lowered', how: 'Hum: the air goes out through the nose.', contact: 'lips' },
  K:   { place: 'Back of the tongue against the soft palate', how: 'Block the air at the back, then release.', contact: [222, 100] },
  NG:  { place: 'Back of the tongue against the soft palate', how: 'Air goes through the nose. No hard “g” after it.', contact: [222, 100] },
  SH:  { place: 'Tongue close to the ridge, lips pushed forward', how: 'A steady hiss. The tongue does not touch.', contact: [113, 117], near: true },
  ER:  { place: 'Tongue tip curled up, touching nothing', how: 'Round the lips a little. Keep the tongue off the roof.', contact: [128, 124], near: true },
  W:   { place: 'Lips tightly rounded, back of tongue high', how: 'Start small and round, then open into the vowel.', contact: null },
  A:   { place: 'Jaw low, tongue low and pulled back', how: 'Open wide and keep it long.', contact: null },
  AE:  { place: 'Jaw open, tongue low and forward', how: 'Spread the lips. Between “a” and “e”.', contact: null },
  E:   { place: 'Tongue mid and forward, jaw half open', how: 'Short and clean.', contact: null },
  I:   { place: 'Tongue high and forward, lips spread', how: 'Smile and hold it long.', contact: null },
  IH:  { place: 'Tongue high but relaxed', how: 'Short and loose. Not “ee”.', contact: null },
  U:   { place: 'Lips small and round, back of tongue high', how: 'Keep the lips round to the end.', contact: null },
  O:   { place: 'Lips round, tongue mid and back', how: 'Glide toward smaller, rounder lips.', contact: null },
  UH:  { place: 'Mouth half open, tongue resting in the middle', how: 'Relaxed and short.', contact: null },
  S:   { place: 'Tongue tip close to the ridge, teeth almost closed', how: 'A sharp hiss through a narrow gap. Z is the same with voice.', contact: [104, 121], near: true },
  H:   { place: 'Mouth already shaped for the next vowel', how: 'Just a puff of breath, no friction.', contact: null }
};

const VOICELESS = new Set(['t', 'k', 'p', 'f', 'θ', 's', 'ʃ', 'h']);
const NASAL_KEYS = new Set(['N', 'M', 'NG']);

// IPA symbol → mouth targets [viseme, label, weight]
const MAP = {
  'tʃ': [['TD', 't', 0.5], ['SH', 'ʃ', 1]], 'dʒ': [['TD', 'd', 0.5], ['SH', 'ʒ', 1]],
  'aɪ': [['A', 'a', 1.3], ['IH', 'ɪ', 0.9]], 'aʊ': [['A', 'a', 1.3], ['U', 'ʊ', 0.9]], 'ɔɪ': [['A', 'ɔ', 1.2], ['IH', 'ɪ', 0.9]],
  'eɪ': [['E', 'e', 1.2], ['IH', 'ɪ', 0.8]], 'oʊ': [['O', 'o', 1.2], ['U', 'ʊ', 0.8]], 'əʊ': [['O', 'ə', 1.1], ['U', 'ʊ', 0.8]],
  'ɪə': [['IH', 'ɪ', 1], ['UH', 'ə', 0.8]], 'eə': [['E', 'e', 1], ['UH', 'ə', 0.8]], 'ʊə': [['U', 'ʊ', 1], ['UH', 'ə', 0.8]],
  p: [['MBP', 'p', 1]], b: [['MBP', 'b', 1]], m: [['M', 'm', 1]],
  t: [['TD', 't', 1]], d: [['TD', 'd', 1]], n: [['N', 'n', 1]], 'ɾ': [['TD', 'ɾ', 0.6]], 'ʔ': [['rest', 'ʔ', 0.5]],
  k: [['K', 'k', 1]], g: [['K', 'ɡ', 1]], 'ɡ': [['K', 'ɡ', 1]], 'ŋ': [['NG', 'ŋ', 1]],
  f: [['F', 'f', 1.1]], v: [['F', 'v', 1.1]], 'θ': [['TH', 'θ', 1.3]], 'ð': [['TH', 'ð', 1.1]],
  s: [['S', 's', 1.1]], z: [['S', 'z', 1.1]], 'ʃ': [['SH', 'ʃ', 1.2]], 'ʒ': [['SH', 'ʒ', 1.1]],
  l: [['L', 'l', 1]], 'ɫ': [['L', 'l', 1]], 'ɹ': [['ER', 'r', 1]], r: [['ER', 'r', 1]], 'ɻ': [['ER', 'r', 1]],
  w: [['W', 'w', 1]], 'ʍ': [['W', 'w', 1]], j: [['I', 'j', 0.7]], h: [['H', 'h', 0.8]],
  i: [['I', 'i', 1.2]], 'ɪ': [['IH', 'ɪ', 1.1]], e: [['E', 'e', 1.3]], 'ɛ': [['E', 'ɛ', 1.3]], 'æ': [['AE', 'æ', 1.5]],
  a: [['A', 'a', 1.3]], 'ɑ': [['A', 'ɑ', 1.5]], 'ɒ': [['A', 'ɒ', 1.4]], 'ɔ': [['A', 'ɔ', 1.5]], 'ʌ': [['UH', 'ʌ', 1.3]],
  'ə': [['UH', 'ə', 0.8]], 'ɐ': [['UH', 'ɐ', 0.9]], 'ɜ': [['ER', 'ɜ', 1.5]], 'ɝ': [['ER', 'ɝ', 1.5]], 'ɚ': [['ER', 'ɚ', 1.1]],
  u: [['U', 'u', 1.3]], 'ʉ': [['U', 'u', 1.3]], 'ʊ': [['U', 'ʊ', 1]], o: [['O', 'o', 1.3]], 'ɵ': [['UH', 'ɵ', 1]], 'ɘ': [['UH', 'ɘ', 1]]
};
const MULTI = Object.keys(MAP).filter((k) => k.length > 1);

function ipaToSeq(ipa) {
  const s = ipa.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[\/\[\]ˈˌ.()‿ʰˑ\s-]/g, '').replace(/ɡ/g, 'g');
  const seq = [];
  let i = 0;
  while (i < s.length) {
    let tok = MULTI.find((m) => s.startsWith(m, i)) || s[i];
    i += tok.length;
    let long = false;
    if (s[i] === 'ː') { long = true; i++; }
    const parts = MAP[tok];
    if (!parts) continue;
    parts.forEach(([v, l, wt], k) => seq.push([v, l + (long && k === parts.length - 1 ? 'ː' : ''), long ? wt * 1.6 : wt]));
  }
  return seq;
}

const TRICKY = [
  ['θ', 'TH: tongue lightly between the teeth, then blow. Not “t” or “s”.'],
  ['ð', 'Voiced TH: tongue between the teeth, with voice. Not “d” or “z”.'],
  ['r', 'R: the tongue touches nothing. Round the lips a little.'],
  ['v', 'V: top teeth on the lower lip, with voice. Not “w”.'],
  ['w', 'W: start with small, round lips.'],
  ['æ', 'æ: open the jaw and spread the lips, between “a” and “e”.'],
  ['ŋ', 'NG: back of the tongue on the soft palate. No hard “g” after it.'],
  ['ɪ', 'ɪ: short and relaxed, not a long “ee”.'],
  ['iː', 'iː: smile and hold it long.'],
  ['ʌ', 'ʌ: a short, relaxed “uh”.'],
  ['ə', 'ə: unstressed and weak, a quick “uh”.'],
  ['ɚ', 'ɚ: a weak “er” with the tongue pulled back.'],
  ['ɝ', 'ɝ: a long “er”, the tongue touches nothing.']
];
function makeTip(seq) {
  const labels = new Set(seq.map((s) => s[1]));
  const hits = TRICKY.filter(([l]) => labels.has(l)).slice(0, 2).map((t) => t[1]);
  return hits.length ? hits.join(' ') : 'Click each sound to see where the tongue goes.';
}

const f = (n) => n.toFixed(1);
const byId = (id) => document.getElementById(id);
function set(id, attrs) { const el = byId(id); for (const k in attrs) el.setAttribute(k, attrs[k]); }

function drawFront(p) {
  const cx = 200, cy = 165;
  const hw = 78 * (1 + 0.24 * p.w - 0.42 * p.r), open = 3 + 62 * p.o;
  const uo = open * 0.375, lo = open * 0.675, ut = 20 + 9 * p.r, lt = 26 + 10 * p.r;
  const L = cx - hw, R = cx + hw, top = cy - uo - ut;
  const upper = `M${f(L)},${cy} C${f(cx - hw * 0.6)},${f(top - 2)} ${f(cx - hw * 0.22)},${f(top - 6)} ${cx},${f(top + 5)} ` +
    `C${f(cx + hw * 0.22)},${f(top - 6)} ${f(cx + hw * 0.6)},${f(top - 2)} ${f(R)},${cy} ` +
    `C${f(cx + hw * 0.5)},${f(cy - open * 0.5)} ${f(cx - hw * 0.5)},${f(cy - open * 0.5)} ${f(L)},${cy} Z`;
  const ld = (lo + lt) * 1.333;
  const lower = `M${f(L)},${cy} C${f(cx - hw * 0.5)},${f(cy + open * 0.9)} ${f(cx + hw * 0.5)},${f(cy + open * 0.9)} ${f(R)},${cy} ` +
    `C${f(cx + hw * 0.55)},${f(cy + ld)} ${f(cx - hw * 0.55)},${f(cy + ld)} ${f(L)},${cy} Z`;
  const cav = `M${f(L)},${cy} C${f(cx - hw * 0.5)},${f(cy - open * 0.5)} ${f(cx + hw * 0.5)},${f(cy - open * 0.5)} ${f(R)},${cy} ` +
    `C${f(cx + hw * 0.5)},${f(cy + open * 0.9)} ${f(cx - hw * 0.5)},${f(cy + open * 0.9)} ${f(L)},${cy} Z`;
  set('f-upper', { d: upper }); set('f-lower', { d: lower }); set('f-cav', { d: cav }); set('f-clip', { d: cav });
  set('f-tongue', { cy: f(cy + lo + 4), rx: f(hw * 0.6), ry: f(4 + open * 0.45) });
  set('f-tip', { cy: f(cy - uo + 6), ry: f(8 + open * 0.15), opacity: f(p.tip || 0) });
  set('f-upT', { x: f(cx - hw * 0.72), width: f(hw * 1.44), y: f(cy - uo - 6), height: f(10 + 14 * p.t), opacity: f(Math.min(1, 0.35 + p.t)) });
  set('f-loT', { x: f(cx - hw * 0.72), width: f(hw * 1.44), y: f(cy + lo - (2 + 10 * p.t)), opacity: f(0.15 + 0.7 * p.t) });
  set('f-hl', { cy: f(cy + lo + lt * 0.5), rx: f(hw * 0.35) });
  set('f-th', { opacity: f(p.th || 0) });
  set('f-bite', { x: f(cx - hw * 0.5), y: cy - 4, width: f(hw), opacity: f(p.bite || 0) });
  set('f-cL', { cx: f(L) }); set('f-cR', { cx: f(R) });
}

// Closed Catmull-Rom spline through points, as cubic Bezier path.
function spline(pts) {
  const n = pts.length; let d = `M${f(pts[0][0])},${f(pts[0][1])}`;
  for (let i = 0; i < n; i++) {
    const p0 = pts[(i - 1 + n) % n], p1 = pts[i], p2 = pts[(i + 1) % n], p3 = pts[(i + 2) % n];
    d += ` C${f(p1[0] + (p2[0] - p0[0]) / 6)},${f(p1[1] + (p2[1] - p0[1]) / 6)} ${f(p2[0] - (p3[0] - p1[0]) / 6)},${f(p2[1] - (p3[1] - p1[1]) / 6)} ${f(p2[0])},${f(p2[1])}`;
  }
  return d + ' Z';
}

// info: { note, voiced, nasal, active } for the sound being shown (or null at rest)
function drawSide(p, info) {
  const bite = p.bite || 0, nas = p.nas || 0;
  const D = p.o * 28, jx = D * 0.3;
  const ULf = 60 - 9 * p.r, ULb = 148 - p.o * 3;
  const gap = p.o * 32 * (1 - bite * 0.85);
  const LLt = ULb + gap + bite * 2;
  const LLf = 62 - 8 * p.r + bite * 12 + jx;
  const chx = 66 + jx, chy = 212 + D;

  const skin = `M400,0 L150,0 C140,25 75,55 52,72 C46,78 52,92 70,92 C74,102 ${f(ULf + 4)},112 ${f(ULf)},128 ` +
    `C${f(ULf - 1)},138 ${f(ULf + 2)},${f(ULb - 1)} ${f(ULf + 10)},${f(ULb)} L${f(LLf + 10)},${f(LLt)} ` +
    `C${f(LLf)},${f(LLt + 3)} ${f(LLf - 2)},${f(LLt + 14)} ${f(LLf + 2)},${f(LLt + 20)} ` +
    `C${f(LLf + 6)},${f(LLt + 26)} ${f(LLf + 14)},${f(LLt + 27)} ${f(LLf + 14)},${f(LLt + 32)} ` +
    `C${f(LLf + 8)},${f(LLt + 50)} ${f(chx)},${f(chy - 20)} ${f(chx)},${f(chy)} ` +
    `C${f(chx + 4)},${f(chy + 30)} ${f(chx + 40)},${f(chy + 40)} 150,${f(chy + 42)} C200,${f(chy + 44)} 228,${f(chy + 50)} 238,320 L400,320 Z`;
  set('s-skin', { d: skin });

  const [tx, ty, bx, by, dx, dy, kx] = p.tg;
  const oral = `M${f(ULf - 3)},${f(ULb)} L${f(ULf + 12)},${f(ULb)} L79,150 L98,114 C106,108 112,106 120,103 C150,92 190,92 215,98 ` +
    `C240,104 262,108 285,108 L285,305 L262,305 L${f(kx - 6)},262 L170,${f(242 + D)} L${f(104 + jx)},${f(212 + D)} ` +
    `L${f(88 + jx)},${f(180 + D)} L${f(LLf + 12)},${f(LLt)} L${f(LLf - 3)},${f(LLt)} Z`;
  set('s-oral', { d: oral });

  const vx = 286 + (256 - 286) * nas, vy = 100 + 40 * nas;
  set('s-velum', { d: `M212,88 C240,89 ${f(vx - 14)},${f(vy - 16)} ${f(vx)},${f(vy)} C${f(vx - 6)},${f(vy + 8)} 240,105 212,100 Z` });

  const tongue = [[tx, ty], [bx, by], [dx, dy], [kx, Math.max(dy + 40, 178)], [kx - 3, 252 + D * 0.4], [kx - 10, 296],
    [170, 250 + D], [104 + jx, 218 + D], [tx + 6, ty + 13]];
  set('s-tongue', { d: spline(tongue) });
  set('s-tongueLbl', { x: f((bx + dx) / 2 + 8), y: f(Math.max(by, dy) + 30) });

  set('s-loT', { d: `M${f(79 + jx)},${f(156 + D)} L${f(86 + jx)},${f(156 + D)} C${f(89 + jx)},${f(170 + D)} ${f(94 + jx)},${f(182 + D)} ${f(96 + jx)},${f(192 + D)} ` +
    `L${f(86 + jx)},${f(194 + D)} C${f(84 + jx)},${f(180 + D)} ${f(80 + jx)},${f(168 + D)} ${f(79 + jx)},${f(156 + D)} Z` });

  const mouthY = (ULb + LLt) / 2;
  const showOral = info && !info.nasal && gap > 2 ? 1 : 0;
  set('s-airO', { transform: `translate(0 ${f(mouthY)})`, opacity: showOral });
  set('s-airN', { opacity: info && info.nasal ? 1 : 0 });
  byId('s-voice').classList.toggle('on', !!(info && info.voiced));

  let c = info && info.note ? info.note.contact : null;
  if (c === 'lips') c = [ULf + 6, ULb];
  if (c) {
    set('s-contact', { cx: f(c[0]), cy: f(c[1]), opacity: 1 });
    set('s-contactRing', { cx: f(c[0]), cy: f(c[1]), opacity: 1, 'stroke-dasharray': info.note.near ? '3 3' : 'none' });
  } else {
    set('s-contact', { opacity: 0 }); set('s-contactRing', { opacity: 0 });
  }
}

const KEYS = ['o', 'w', 'r', 't', 'bite', 'th', 'tip', 'nas'];
const PAUSE_NOTE = { place: 'Short pause between words', how: 'Let the mouth relax for a moment.', contact: null };
const AUDIO_SHARE = 0.92;  // the sounds fill this share of the clip; the rest is the voice's breath at the ends
const SVG = `<div class="mo-views">
  <figure class="mo-pane">
    <figcaption>front</figcaption>
    <svg viewBox="0 -10 400 320" role="img" aria-label="Lips and teeth seen from the front">
      <defs>
        <radialGradient id="g-skin" cx="50%" cy="48%" r="72%"><stop offset="0%" stop-color="#EEC4A8"/><stop offset="65%" stop-color="#DFA486"/><stop offset="100%" stop-color="#C4876A"/></radialGradient>
        <linearGradient id="g-up" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#A24D4A"/><stop offset="100%" stop-color="#BC625C"/></linearGradient>
        <linearGradient id="g-lo" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#C46E66"/><stop offset="100%" stop-color="#AE5852"/></linearGradient>
        <radialGradient id="g-cav" cx="50%" cy="40%" r="60%"><stop offset="0%" stop-color="#5A1E22"/><stop offset="100%" stop-color="#2A0D10"/></radialGradient>
        <clipPath id="f-clipPath"><path id="f-clip"/></clipPath>
      </defs>
      <rect y="-10" width="400" height="320" fill="url(#g-skin)"/>
      <ellipse cx="200" cy="10" rx="70" ry="34" fill="#E9B497" opacity=".8"/>
      <ellipse cx="166" cy="30" rx="15" ry="7" fill="#7E4A38" opacity=".55"/>
      <ellipse cx="234" cy="30" rx="15" ry="7" fill="#7E4A38" opacity=".55"/>
      <ellipse cx="200" cy="82" rx="15" ry="30" fill="#B97B60" opacity=".28"/>
      <ellipse cx="200" cy="300" rx="130" ry="44" fill="#B97B60" opacity=".28"/>
      <path id="f-cav" fill="url(#g-cav)"/>
      <g clip-path="url(#f-clipPath)">
        <ellipse id="f-tongue" cx="200" fill="#C2525A"/>
        <ellipse id="f-tip" cx="200" rx="20" fill="#CC5D64"/>
        <rect id="f-upT" rx="4" fill="#F3EEE4"/>
        <rect id="f-loT" rx="4" height="16" fill="#E6DFD2"/>
      </g>
      <path id="f-lower" fill="url(#g-lo)"/>
      <ellipse id="f-hl" cx="200" ry="5" fill="#fff" opacity=".16"/>
      <ellipse id="f-th" cx="200" cy="168" rx="24" ry="8" fill="#C9585F"/>
      <rect id="f-bite" height="10" rx="3" fill="#F3EEE4"/>
      <path id="f-upper" fill="url(#g-up)"/>
      <circle id="f-cL" cy="165" r="6" fill="#7A3A33" opacity=".35"/>
      <circle id="f-cR" cy="165" r="6" fill="#7A3A33" opacity=".35"/>
    </svg>
  </figure>
  <figure class="mo-pane">
    <figcaption>side cut — tongue, teeth, palate</figcaption>
    <svg viewBox="0 0 400 320" role="img" aria-label="Cross-section of the mouth from the side, showing where the tongue touches">
      <rect width="400" height="320" fill="#FBFAF7"/>
      <path id="s-skin" fill="#ECD3C5" stroke="#B98C78" stroke-width="1.2"/>
      <path id="s-nasal" d="M48,86 C60,78 80,70 110,67 C160,60 240,58 285,62 L285,100 L262,94 C230,88 160,86 120,87 C100,87 70,90 50,90 Z" fill="#FBFAF7"/>
      <path id="s-oral" fill="#FBFAF7"/>
      <path id="s-velum" fill="#E2B8A6" stroke="#B98C78" stroke-width="1"/>
      <path id="s-tongue" fill="#C55B63" stroke="#8F3A42" stroke-width="1"/>
      <text id="s-tongueLbl" class="mo-lbl light">tongue</text>
      <path d="M86,112 C82,124 77,140 77,153 L84,153 C88,140 94,126 98,116 Z" fill="#FFFFFF" stroke="#A89C8E" stroke-width="1"/>
      <path id="s-loT" fill="#FFFFFF" stroke="#A89C8E" stroke-width="1"/>
      <g id="s-airO" class="mo-air" aria-hidden="true"><path d="M40,-5 L33,0 L40,5 M30,-5 L23,0 L30,5 M20,-5 L13,0 L20,5"/></g>
      <g id="s-airN" class="mo-air" aria-hidden="true"><path d="M44,79 L37,84 L44,89 M34,79 L27,84 L34,89 M24,79 L17,84 L24,89"/></g>
      <g id="s-voice" class="mo-voice" aria-hidden="true"><path d="M300,300 l6,-7 l6,14 l6,-14 l6,14 l6,-14 l6,7"/></g>
      <circle id="s-contactRing" r="10" fill="none" stroke="#1B1A18" stroke-width="1.6" opacity="0" class="mo-pulse"/>
      <circle id="s-contact" r="3.5" fill="#1B1A18" opacity="0"/>
      <text x="140" y="78" class="mo-lbl">nasal cavity</text>
      <text x="296" y="98" class="mo-lbl">soft palate</text>
      <line x1="294" y1="95" x2="262" y2="98" class="mo-lead"/>
      <text x="296" y="128" class="mo-lbl">hard palate</text>
      <line x1="294" y1="125" x2="160" y2="94" class="mo-lead"/>
      <text x="296" y="210" class="mo-lbl">throat</text>
      <text x="296" y="286" class="mo-lbl">voice</text>
    </svg>
  </figure>
</div>`;

function mixPose(a, b, s) {
  const o = {};
  for (const k of KEYS) o[k] = (a[k] || 0) + ((b[k] || 0) - (a[k] || 0)) * s;
  o.tg = a.tg.map((v, i) => v + (b.tg[i] - v) * s);
  return o;
}
const smooth = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * (3 - 2 * x); };

// Each sound gets a share of the clip by its weight; the pose holds in the middle half of its slot and blends between.
function timeline(seq, durMs) {
  const W = seq.reduce((s, x) => s + x[2], 0) || 1, unit = durMs / W;
  let t = 0;
  const segs = seq.map(([k, ph, wt]) => { const s = { k, ph, t0: t, t1: t + wt * unit }; t = s.t1; return s; });
  const keys = [{ t: -90, v: VIS.rest }];
  for (const s of segs) { const d = s.t1 - s.t0; keys.push({ t: s.t0 + d * 0.25, v: VIS[s.k] || VIS.rest }, { t: s.t0 + d * 0.75, v: VIS[s.k] || VIS.rest }); }
  keys.push({ t: t + 110, v: VIS.rest });
  return { segs, keys };
}
function poseAt(tl, t) {
  const k = tl.keys;
  let pose = VIS.rest;
  if (t >= k[0].t && t <= k[k.length - 1].t) {
    for (let i = 0; i < k.length - 1; i++) {
      if (t >= k[i].t && t <= k[i + 1].t) { pose = mixPose(k[i].v, k[i + 1].v, smooth((t - k[i].t) / Math.max(1, k[i + 1].t - k[i].t))); break; }
    }
  }
  return { pose, idx: tl.segs.findIndex((s) => t >= s.t0 && t < s.t1) };
}

const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

export function mountMouth(container, { ipa, audioUrl }) {
  const seq = ipaToSeq(ipa || '');
  container.textContent = '';
  if (!seq.length) { container.appendChild(el('p', 'mo-empty', 'No pronunciation to show for this word.')); return { play() {}, destroy() {} }; }
  const views = el('div'); views.innerHTML = SVG;  // static markup, no user data in it
  const sounds = el('div', 'mo-sounds');
  const chips = el('div', 'mo-chips'); chips.setAttribute('role', 'group'); chips.setAttribute('aria-label', 'Sounds in this word. Click one to hold its mouth position.');
  const note = el('div', 'mo-note'); note.setAttribute('aria-live', 'polite');
  sounds.append(chips, note);
  container.append(views, sounds);

  let frozen = -1, active = -1, raf = 0, audio = null;
  const info = (idx) => {
    if (idx < 0) return null;
    const [k, ph] = seq[idx];
    return { note: NOTES[k], voiced: k !== 'rest' && !VOICELESS.has(ph), nasal: NASAL_KEYS.has(k) };
  };
  function renderChips() {
    chips.textContent = '';
    seq.forEach(([k, ph], i) => {
      const b = el('button', i === active ? 'active' : ''); b.type = 'button';
      b.setAttribute('aria-pressed', i === frozen ? 'true' : 'false');
      b.setAttribute('aria-label', `Sound ${ph}. Click to hold this mouth position.`);
      b.append(el('span', 'g', ph), el('span', 'v', k === 'rest' ? 'pause' : (VOICELESS.has(ph) ? 'air' : 'voice') + (NASAL_KEYS.has(k) ? '·nose' : '')));
      b.onclick = () => freeze(i === frozen ? -1 : i);
      chips.appendChild(b);
    });
  }
  function renderNote() {
    note.textContent = '';
    const idx = frozen >= 0 ? frozen : active;
    if (idx < 0) {
      note.append(el('p', null, makeTip(seq)), el('span', 'm', 'Click a sound to hold its position and see where the tongue goes.'));
      return;
    }
    const [k, ph] = seq[idx], n = NOTES[k] || PAUSE_NOTE;
    const t = el('div', 't'); t.append(el('span', 'g', ph), n.place);
    const m = [VOICELESS.has(ph) ? 'voiceless — no buzz in the throat' : 'voiced — throat buzzes',
      NASAL_KEYS.has(k) ? 'air through the nose' : 'air through the mouth', n.contact ? (n.near ? 'close, no touch' : 'touch point marked') : null].filter(Boolean).join(' · ');
    note.append(t, el('p', null, n.how), el('span', 'm', m));
  }
  function show(pose, idx) {
    drawFront(pose); drawSide(pose, info(idx));
    if (idx !== active) { active = idx; renderChips(); renderNote(); }
  }
  function freeze(i) {
    stop();
    frozen = i;
    if (i >= 0) show(VIS[seq[i][0]] || VIS.rest, i); else show(VIS.rest, -1);
    renderChips(); renderNote();
  }
  function stop() {
    cancelAnimationFrame(raf); raf = 0;
    if (audio) { audio.pause(); audio = null; }
  }
  // Plays the word and moves the mouth with the clip's own clock, so a slow voice gives a slow mouth.
  function play(speed = 1) {
    stop(); frozen = -1;
    audio = new Audio(audioUrl(speed));
    const a = audio;
    a.addEventListener('playing', () => {
      const tl = timeline(seq, (a.duration || 1) * 1000 * AUDIO_SHARE);
      const lead = (a.duration || 1) * 1000 * (1 - AUDIO_SHARE) / 2;
      const tick = () => {
        if (a !== audio) return;
        const { pose, idx } = poseAt(tl, a.currentTime * 1000 - lead);
        show(pose, idx);
        if (!a.ended) raf = requestAnimationFrame(tick); else { show(VIS.rest, -1); audio = null; }
      };
      tick();
    });
    a.play().catch(() => { audio = null; });
  }
  show(VIS.rest, -1); renderChips(); renderNote();
  return { play, destroy: stop };
}
