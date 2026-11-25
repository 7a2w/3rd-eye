// Controller and screens. The phone version of main.py plus the dashboard.
import { bus } from './bus.js';
import { getSettings, saveSettings, renderSettings, aiProvider } from './settings.js';
import { escapeHtml as esc, shortTime, fmtBytes } from './util.js';
import { Capture } from './capture.js';
import { SlideWatcher } from './slides.js';
import { NotesWriter, listLectures, deleteLecture } from './notes.js';
import { Transcriber } from './transcribe.js';
import { Assistant, speak } from './assistant.js';
import { ocrImage } from './ocr.js';
import { generate } from './studysheet.js';
import { Brain } from './brain.js';

const $ = (id) => document.getElementById(id);
const app = { phase: 'setup', mode: 'OFF', notes: null, cap: null, tr: null, asst: null, watcher: null, jobs: [], urls: new Map(), fileMode: null, asking: false, brain: null, courseGiven: false };

/* ---------------- small helpers ---------------- */
function toast(text, level = 'info') {
  const t = $('toast'); t.textContent = text; t.className = 'toast ' + level;
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.add('hidden'), 5000);
}
bus.on('notice', (n) => toast(n.text, n.level));

function setStatus(text) { $('status').textContent = text || ''; }
function show(id, on) { $(id).classList.toggle('hidden', !on); }
function showPhase(p) {
  app.phase = p;
  for (const k of ['setup', 'live', 'finishing', 'done']) show(k, k === p);
  const live = p === 'live';
  $('stateWord').textContent = { setup: 'Not listening', live: 'Listening', finishing: 'Saving', done: 'Saved' }[p];
  if (!live) setEye('');
}
function setEye(cls) { $('eye').setAttribute('class', 'eye ' + cls); $('state').className = 'state ' + cls; }
function setMode(mode) {
  app.mode = mode;
  const cls = { REC: 'rec', ASK: 'ask', PAUSED: 'paused' }[mode] || '';
  setEye(cls);
  $('stateWord').textContent = { REC: 'Listening', ASK: 'Listening to you', PAUSED: 'Paused' }[mode] || $('stateWord').textContent;
  const oa = $('onair'); oa.className = 'onair ' + cls;
  oa.querySelector('span').textContent = { REC: 'Listening', ASK: 'Listening to you', PAUSED: 'Paused' }[mode] || '';
  $('pauseBtn').textContent = mode === 'PAUSED' ? 'Resume' : 'Pause';
}

/* ---------------- tabs ---------------- */
for (const b of document.querySelectorAll('.tabbar button')) b.onclick = () => {
  document.querySelectorAll('.tabbar button').forEach((x) => x.classList.toggle('on', x === b));
  for (const v of ['record', 'lectures', 'settings']) $('v-' + v).classList.toggle('hidden', v !== b.dataset.tab);
  if (b.dataset.tab === 'lectures') showLectures();
};

/* ---------------- notes feed ---------------- */
async function slideUrl(notes, img) {
  const key = notes.id + '/' + img;
  if (!app.urls.has(key)) { const b = await notes.getFile(img); if (b) app.urls.set(key, URL.createObjectURL(b)); }
  return app.urls.get(key);
}
function entryHtml(e, notes) {
  const when = `<div class="when">${shortTime(e.t)}</div>`;
  if (e.kind === 'speech') return `<div class="entry">${when}<div class="said">${esc(e.text)}</div></div>`;
  if (e.kind === 'slide') return `<div class="entry slide">${when}<figure><img data-slide="${esc(e.img)}" alt="Captured slide"><figcaption>${esc(e.text || 'No readable text on this one.')}</figcaption></figure></div>`;
  if (e.kind === 'qa') return `<div class="entry">${when}<div class="qa"><div class="q">You asked: ${esc(e.q)}</div><div class="a">${esc(e.a)}</div></div></div>`;
  if (e.kind === 'insight') return `<div class="entry">${when}<div class="qa insight"><div class="q">${esc(e.q || 'Third Eye')}</div><div class="a">${esc(e.a)}</div></div></div>`;
  if (e.kind === 'task') return `<div class="entry">${when}<div class="task-line">Task: ${esc(e.text)}${e.due ? ` <small>due ${esc(e.due)}</small>` : ''}</div></div>`;
  if (e.kind === 'context') return `<div class="entry ctx"><div>Now: ${esc(e.text)}${e.topic ? ' · ' + esc(e.topic) : ''}</div></div>`;
  return `<div class="entry">${when}<div class="gap">Recording was interrupted until ${shortTime(e.t1)}.</div></div>`;
}
async function fillImages(root, notes) {
  for (const img of root.querySelectorAll('img[data-slide]')) {
    if (img.src) continue;
    const u = await slideUrl(notes, img.dataset.slide); if (u) { img.src = u; img.onclick = () => openLight(u); }
  }
}
function renderFeed() {
  const feed = $('feed'), n = app.notes; if (!n) return;
  const near = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
  feed.innerHTML = n.entries.length ? n.entries.map((e) => entryHtml(e, n)).join('') : '<p class="empty">Notes appear here as soon as someone starts talking.</p>';
  fillImages(feed, n);
  const lines = n.entries.filter((e) => e.kind === 'speech').length, slides = n.entries.filter((e) => e.kind === 'slide').length;
  $('countNote').textContent = lines ? `${lines} lines, ${slides} slides` : '';
  $('slideNote').textContent = `${slides} slide${slides === 1 ? '' : 's'}`;
  if (near) feed.scrollTop = feed.scrollHeight;
}
bus.on('entries', () => { if (app.phase === 'live') renderFeed(); });

function renderTasks() {
  const tasks = app.brain?.tasks || [];
  show('tasksPanel', tasks.length > 0);
  $('taskCount').textContent = tasks.length ? `${tasks.filter((x) => !x.done).length} open` : '';
  $('taskList').innerHTML = tasks.map((x) => `<label class="todo"><input type="checkbox" data-task="${esc(x.id)}"${x.done ? ' checked' : ''}><span>${esc(x.task)}${x.due ? `<small>Due ${esc(x.due)}</small>` : ''}</span></label>`).join('');
}
$('taskList').addEventListener('change', (e) => { const id = e.target.dataset.task; if (id && app.brain) { app.brain.setDone(id, e.target.checked); renderTasks(); } });

function renderSituation() {
  const b = app.brain, chip = $('hdrCtx'), on = !!b && b.context !== 'listening';
  chip.classList.toggle('hidden', !on);
  chip.textContent = on ? b.context + (b.topic ? ' · ' + b.topic : '') : '';
  if (app.notes) $('hdrCourse').textContent = app.notes.course;
}

function heard(t, text) {
  if (!text) return;
  app.notes.addSpeech(t, text);
  app.brain?.onSpeech(text);
}

function startBrain() {
  app.brain = new Brain({
    notes: app.notes, courseGiven: app.courseGiven,
    paused: () => app.phase !== 'live' || app.mode === 'PAUSED' || app.asking,
    ask: (q) => ask(q), askVoice: () => ask(), end: (auto) => end(auto),
    changed: () => { renderSituation(); renderTasks(); },
  });
  app.brain.start(); renderTasks(); renderSituation();
}
function openLight(src) { $('lightImg').src = src; show('lightbox', true); }
$('lightbox').onclick = () => show('lightbox', false);

/* ---------------- recording ---------------- */
bus.on('level', ({ level }) => { $('micMeter').style.width = (app.mode === 'REC' ? Math.round(level * 100) : 0) + '%'; });

function queue(fn) { const p = (app.jobs.length ? app.jobs[app.jobs.length - 1] : Promise.resolve()).then(fn).catch((e) => console.warn(e)); app.jobs.push(p); p.finally(() => { app.jobs = app.jobs.filter((x) => x !== p); }); return p; }

async function onChunk({ t, pcm }) {
  if (!app.tr || app.tr.live) return;
  queue(async () => {
    try { heard(t, await app.tr.transcribe(pcm)); }
    catch (e) { setStatus('Speech to text failed: ' + e.message); }
  });
}
bus.on('chunk', onChunk);

async function frameTick() {
  if (app.phase !== 'live' || app.mode !== 'REC' || !app.watcher || !app.cap.hasVideo) return;
  const s = await app.watcher.process(app.cap.videoEl, app.cap.elapsed());
  if (!s) return;
  const name = `slide_${String(s.n).padStart(3, '0')}.jpg`;
  await app.notes.saveFile(name, s.blob);
  app.urls.set(app.notes.id + '/' + name, s.dataUrl);
  app.notes.addSlide(s.t, name, '');
  queue(async () => { const text = await ocrImage(s.blob, getSettings()); if (text) app.notes.setSlideText(name, text); });
}

bus.on('interrupted', ({ reason }) => toast(reason === 'hidden' ? 'Listening paused: the screen was off or you switched apps.' : 'The microphone or camera stopped.', 'warn'));
bus.on('resumed', ({ t, t0 }) => { app.notes?.addGap(t0, t); toast('Back. The gap was marked in your notes.'); });

async function start() {
  const given = $('courseInput').value.trim(), course = given || 'Session';
  saveSettings({ course: given, camera: $('camSelect').value });
  const btn = $('startBtn'); btn.disabled = true; btn.textContent = 'Opening microphone…';
  try {
    app.cap = new Capture();
    await app.cap.open({ camera: $('camSelect').value });
  } catch (e) {
    btn.disabled = false; btn.textContent = 'Start listening';
    toast("Third Eye can't use the microphone: " + (e.message || e) + '. Allow it in Settings > Safari.', 'error'); return;
  }
  speak('');
  app.notes = await NotesWriter.create(course); app.courseGiven = !!given;
  app.tr = new Transcriber(getSettings()); app.asst = new Assistant(); app.watcher = new SlideWatcher(getSettings());
  $('camSlot').prepend(app.cap.videoEl);
  $('camPh').classList.toggle('hidden', app.cap.facing !== 'off');
  $('hdrCourse').textContent = course;
  app.cap.begin(); showPhase('live'); setMode('REC'); renderFeed(); startBrain();
  if (app.tr.live) app.tr.startLive((text) => heard(app.cap.elapsed(), text));
  setStatus(app.tr.live ? 'Using Safari speech recognition.' : `Speech to text: ${app.tr.engine}.`);
  app.frames = setInterval(frameTick, 200);
  app.timer = setInterval(() => { $('timer').textContent = shortTime(app.cap.elapsed()); }, 500);
  btn.disabled = false; btn.textContent = 'Start listening';
}

async function startFromFile(file) {
  const given = $('courseInput').value.trim(), course = given || 'Session';
  const ac = new (window.AudioContext || window.webkitAudioContext)();
  let buf; try { buf = await ac.decodeAudioData(await file.arrayBuffer()); } catch { toast('Could not read that file as audio.', 'error'); return; }
  const mono = buf.getChannelData(0), ratio = buf.sampleRate / 16000, n = Math.floor(mono.length / ratio), pcm = new Float32Array(n);
  for (let i = 0; i < n; i++) pcm[i] = mono[Math.floor(i * ratio)];
  app.cap = { paused: false, facing: 'off', hasVideo: false, begun: true, t0: Date.now(), elapsed() { return (Date.now() - this.t0) / 1000; }, stop() {} };
  app.notes = await NotesWriter.create(course); app.courseGiven = !!given; app.tr = new Transcriber({ ...getSettings(), sttEngine: getSettings().geminiKey ? 'gemini' : 'openai' });
  if (!getSettings().geminiKey && !getSettings().openaiKey) { toast('Add a Gemini or OpenAI key in Settings to transcribe a file.', 'warn'); return; }
  app.asst = new Assistant(); app.watcher = null; app.fileMode = true;
  $('hdrCourse').textContent = course; showPhase('live'); setMode('REC'); renderFeed(); startBrain(); setStatus('Playing the recording into Third Eye.');
  app.timer = setInterval(() => { $('timer').textContent = shortTime(app.cap.elapsed()); }, 500);
  const step = 8 * 16000; let i = 0;
  const feed = setInterval(() => {
    if (app.mode === 'PAUSED') return;
    if (i >= pcm.length) { clearInterval(feed); setStatus('Recording finished. Tap End session.'); return; }
    bus.emit('chunk', { t: i / 16000, pcm: pcm.slice(i, i + step) }); i += step;
  }, 8000);
  app.feed = feed;
}

function togglePause() {
  if (app.phase !== 'live') return;
  const pause = app.mode !== 'PAUSED';
  app.cap.paused = pause; setMode(pause ? 'PAUSED' : 'REC');
  if (app.tr?.live) pause ? app.tr.stopLive() : app.tr.startLive((t) => heard(app.cap.elapsed(), t));
}

async function ask(typed) {
  if (app.asking || app.phase !== 'live') return;
  app.asking = true; $('askBtn').disabled = $('askSend').disabled = true;
  const prev = app.mode;
  try {
    let q = typed || '';
    if (!q) {
      const secs = getSettings().questionSeconds; setMode('ASK');
      let left = secs; $('askBtn').textContent = `Listening… ${left}`;
      const tick = setInterval(() => { left--; if (left > 0) $('askBtn').textContent = `Listening… ${left}`; }, 1000);
      if (app.tr.live) { app.tr.stopLive(); q = await app.tr.listenOnce(secs); }
      else { const pcm = await app.cap.askQuestion(secs); q = await app.tr.transcribe(pcm); }
      clearInterval(tick);
      if (app.tr.live && prev !== 'PAUSED') app.tr.startLive((t) => heard(app.cap.elapsed(), t));
    }
    if (!q) { setStatus("I didn't catch a question. Try again."); return; }
    $('askBtn').textContent = 'Working on it…'; setStatus('You asked: ' + q);
    const t = app.cap.elapsed(), n = app.notes;
    const b = app.brain, situation = { context: b && b.context !== 'listening' ? b.context : '', topic: b?.topic || '', tasks: b?.tasks || [] };
    const a = await app.asst.answer(q, n.transcript(getSettings().contextMinutes * 60), n.slideText(true), situation);
    n.addQa(t, q, a); setStatus(a);
    if (getSettings().speakAnswers) speak(a);
  } catch (e) { setStatus('That did not work: ' + e.message); }
  finally { app.asking = false; $('askBtn').disabled = $('askSend').disabled = false; $('askBtn').textContent = 'Talk to Third Eye'; setMode(prev); }
}

async function end(auto = false) {
  if (app.phase !== 'live') return;
  if (!auto && !confirm('End the session and write the summary?')) return;
  clearInterval(app.frames); clearInterval(app.timer); clearInterval(app.feed);
  app.brain?.stop(); app.tr?.stopLive?.(); app.cap.stop(); showPhase('finishing');
  if (auto) toast('It has been quiet for a while, so the session was wrapped up.');
  await Promise.all(app.jobs);
  try { await app.brain?.think(true); } catch (e) { console.warn(e); }
  try { await generate(app.notes, getSettings()); } catch (e) { toast('Summary failed: ' + e.message, 'error'); }
  await app.notes.flush();
  showPhase('done'); await renderDone($('done'), app.notes, true);
}

/* ---------------- study sheet / files ---------------- */
async function renderDone(root, n, isNew) {
  const sh = n.sheet || {}, files = await n.listFiles();
  const list = (a, tag = 'ul') => `<${tag}>${(a || []).map((x) => `<li>${esc(x)}</li>`).join('')}</${tag}>`;
  const reviews = (getSettings().reviewDays || []).map((d) => { const x = new Date(n.started); x.setDate(x.getDate() + d); return x.toDateString(); });
  const names = files.map((f) => f.name).filter((x) => !x.startsWith('slide_'));
  root.innerHTML = `
    <div class="panel"><div class="pad">
      <p class="saved mono">${isNew ? 'Saved' : 'Recorded ' + new Date(n.started).toLocaleString()}</p>
      <h1>${esc(sh.title || n.course)}</h1>${n.context ? `<p class="saved mono">${esc(n.context)}${n.topic ? ' · ' + esc(n.topic) : ''}</p>` : ''}<p class="tldr">${esc(sh.tldr || 'No summary yet.')}</p>
      ${sh._note ? `<p class="warn">${esc(sh._note)}</p>` : ''}
      <div class="row"><button class="btn primary" data-share>Share files</button>
      ${isNew ? '<button class="btn" data-new>New session</button>' : '<button class="btn" data-back>Back</button><button class="btn danger" data-del>Delete</button>'}</div>
    </div></div>
    <div class="panel"><h2 class="panel-title">Key points</h2><div class="pad">${list(sh.key_points)}</div></div>
    <div class="panel"><h2 class="panel-title">Key terms</h2><div class="pad"><dl>${(sh.key_terms || []).map((t) => `<dt>${esc(t.term)}</dt><dd>${esc(t.definition)}</dd>`).join('')}</dl></div></div>
    <div class="panel"><h2 class="panel-title">Test yourself</h2><div class="pad">${list(sh.exam_questions, 'ol')}<p class="note">Answer out loud before you look at your notes.</p></div></div>
    ${(sh.confusing_parts || []).length ? `<div class="panel"><h2 class="panel-title">Follow up</h2><div class="pad">${list(sh.confusing_parts)}</div></div>` : ''}
    <div class="panel"><h2 class="panel-title">Tasks and deadlines</h2><div class="pad">${(sh.todos || []).length ? sh.todos.map((t) => `<label class="todo"><input type="checkbox"><span>${esc(t.task)}<small>${t.due ? 'Due ' + esc(t.due) : `Due in about ${t.due_in_days ?? 3} day${t.due_in_days === 1 ? '' : 's'}`}</small></span></label>`).join('') : '<p class="note">No tasks or deadlines came up.</p>'}</div></div>
    <div class="panel"><h2 class="panel-title">Review again on</h2><div class="pad mono">${reviews.map(esc).join('<br>')}</div></div>
    <div class="panel"><h2 class="panel-title">Files</h2><div class="pad"><div class="files">${names.map((f) => `<button class="btn small" data-file="${esc(f)}">${esc(f)}</button>`).join('')}</div>
      <p class="note">Share sends them to Files, iCloud Drive or Mail. The .ics files add tasks and review dates to your calendar.</p></div></div>
    <div class="panel"><h2 class="panel-title">Slides</h2><div class="pad slides">${(n.entries.filter((e) => e.kind === 'slide')).map((e) => `<img data-slide="${esc(e.img)}" alt="Slide at ${shortTime(e.t)}">`).join('') || '<p class="note">No slides were captured.</p>'}</div></div>
    <div class="panel"><h2 class="panel-title">Transcript</h2><div class="pad transcript">${n.entries.filter((e) => e.kind === 'speech').map((e) => `<div class="entry"><div class="when">${shortTime(e.t)}</div><div class="said">${esc(e.text)}</div></div>`).join('') || '<p class="note">No speech was captured.</p>'}</div></div>`;
  fillImages(root, n);
  root.querySelector('[data-share]').onclick = () => shareFiles(n, names);
  root.querySelector('[data-new]')?.addEventListener('click', reset);
  root.querySelector('[data-back]')?.addEventListener('click', showLectures);
  root.querySelector('[data-del]')?.addEventListener('click', async () => { if (confirm('Delete this session from the phone?')) { await deleteLecture(n.id); showLectures(); } });
  root.querySelectorAll('[data-file]').forEach((b) => { b.onclick = () => shareFiles(n, [b.dataset.file]); });
}

async function shareFiles(n, names) {
  const files = [];
  for (const name of names) { const b = await n.getFile(name); if (b) files.push(new File([b], name, { type: b.type || 'text/plain' })); }
  if (navigator.canShare?.({ files }) && files.length) { try { await navigator.share({ files, title: n.course }); return; } catch (e) { if (e.name === 'AbortError') return; } }
  for (const f of files) { const a = document.createElement('a'); a.href = URL.createObjectURL(f); a.download = f.name; a.click(); }
}

function reset() {
  app.notes = null; app.fileMode = null; app.brain = null; $('timer').textContent = ''; $('hdrCourse').textContent = ''; $('askBtn').disabled = false;
  renderSituation(); show('tasksPanel', false);
  show('done', false); showPhase('setup'); $('feed').innerHTML = '';
}

/* ---------------- past sessions ---------------- */
async function showLectures() {
  show('lecDetail', false); show('lecList', true);
  const all = await listLectures(), root = $('lecList');
  root.innerHTML = all.length ? `<div class="panel"><h2 class="panel-title">Sessions on this phone</h2><div class="rows">${all.map((l) => `
    <button class="row-item" data-id="${esc(l.id)}"><span><b>${esc(l.course)}</b><small class="mono">${new Date(l.started).toLocaleString()}</small></span>
    <span class="mono">${l.context ? esc(l.context) + ' · ' : ''}${l.entryCount} items${l.hasSheet ? ' · sheet' : ''}</span></button>`).join('')}</div></div>` : '<div class="panel"><div class="pad"><p class="note">No sessions yet. Start one on the Listen tab.</p></div></div>';
  root.querySelectorAll('[data-id]').forEach((b) => { b.onclick = async () => {
    const n = await NotesWriter.load(b.dataset.id); show('lecList', false); show('lecDetail', true); await renderDone($('lecDetail'), n, false); window.scrollTo(0, 0); }; });
}

/* ---------------- wiring ---------------- */
$('startBtn').onclick = start;
$('courseInput').onkeydown = (e) => { if (e.key === 'Enter') start(); };
$('camSelect').onchange = async (e) => { saveSettings({ camera: e.target.value }); };
$('fileInput').onchange = (e) => { if (e.target.files[0]) startFromFile(e.target.files[0]); };
$('askBtn').onclick = () => ask();
$('pauseBtn').onclick = togglePause;
$('endBtn').onclick = () => end();
const sendText = () => { const q = $('askInput').value.trim(); if (q) { $('askInput').value = ''; ask(q); } };
$('askSend').onclick = sendText;
$('askInput').onkeydown = (e) => { if (e.key === 'Enter') sendText(); };
$('camSlot').addEventListener('dblclick', async () => { if (app.cap?.switchCamera) await app.cap.switchCamera(app.cap.facing === 'environment' ? 'user' : 'environment'); });

renderSettings($('settingsRoot'), { onChange: () => { $('aiNote') && ($('aiNote').textContent = aiProvider()); } });
const s0 = getSettings(); $('courseInput').value = s0.course; $('camSelect').value = s0.camera;
if (!navigator.mediaDevices?.getUserMedia) {
  $('supportNote').textContent = 'This page needs HTTPS (or localhost) to use the microphone. Open it from the https address.';
  $('startBtn').disabled = true;
} else $('supportNote').textContent = aiProvider() ? `Answers by ${aiProvider()}.` : 'No AI key set. Add one in Settings for better answers and summaries.';
if ('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js').catch(() => {});
showPhase('setup');
