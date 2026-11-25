// Background thinking while Third Eye listens, a port of brain.py: works out what is going on,
// pulls out tasks and deadlines, explains things unprompted, hears "Hey Third Eye" and ends after a long silence.
import { callAi } from './ai.js';
import { keywords, speak } from './assistant.js';
import { getSettings, aiProvider } from './settings.js';

export const WAKE = /\b(?:hey|hi|ok|okay|yo)?[\s,]*(?:third|3rd)[\s-]?(?:eye|i|ai)\b[\s,.:!?-]*(.*)/i;

const CONTEXT_WORDS = {
  lecture: "professor class lecture chapter exam midterm quiz slide homework students textbook syllabus today we're going to cover equation theory".split(' '),
  meeting: 'agenda meeting action item items deadline project team client sprint quarter budget stakeholder deliverable roadmap update sync standup'.split(' '),
  studying: 'flashcard practice problem review notes studying memorize answer solution'.split(' '),
  'phone call': 'hello calling call hear speaking bye phone'.split(' '),
  media: 'subscribe episode channel video watch season trailer'.split(' '),
};

const TASK_HINT = new RegExp(
  "\\b(due|homework|assignment|problem set|quiz|exam|midterm|deadline|submit|hand in|turn in|read(ing)? chapter|" +
  "remind me|don't forget|do not forget|remember to|i need to|i have to|we need to|we have to|you need to|" +
  'make sure|appointment|meeting (on|at)|call (him|her|them|back)|email|send|book|schedule|pick up|buy)\\b', 'i');

const WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const MIN_WORDS = 25;
const SPEAK_GAP = 45;

const pad = (n) => String(n).padStart(2, '0');
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const fmtDue = (d) => `${ymd(d)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
const norm = (s) => s.toLowerCase().replace(/[^a-z0-9 ]/g, '').trim();

const PROMPT = ({ now, context, topic, known, earlier, fresh }) => `You are the background mind of Third Eye, an AI earpiece. It hears everything around the user
and must work out on its own what is happening and what the user would want done, without being asked.

Now: ${now}
What you decided last time: context='${context}', topic='${topic}'
Tasks already noted (do not repeat): ${known}

EARLIER (for context):
${earlier}

NEW SINCE LAST TIME:
${fresh}

Return ONLY JSON:
{
 "context": "one of: lecture, meeting, conversation, studying, phone call, media, quiet, other",
 "topic": "short topic, 2-6 words",
 "title": "short name for this session, e.g. 'BIOL 1010: cellular respiration' or 'Team sync with Sam'",
 "tasks": [{"task": "clear action for the user", "kind": "task|deadline|event", "due": "YYYY-MM-DD HH:MM or YYYY-MM-DD or null"}],
 "explain": [{"about": "the question or term", "say": "1-2 short spoken sentences"}]
}
Rules:
- Infer. Resolve relative dates ("next Friday", "in two weeks", "tomorrow at 3") against Now.
- tasks: only real things the user should do or attend, from the NEW text. [] if none.
- explain: only when the NEW text has a question nobody answered, or a technical term a student or
  newcomer would likely not know. At most 1 item, and [] most of the time. Never explain small talk.`;

const at = (d, days, h, m = 0) => { const x = new Date(d); x.setDate(x.getDate() + days); x.setHours(h, m, 0, 0); return x; };

export function guessDue(sentence, now = new Date()) {
  const s = sentence.toLowerCase();
  if (s.includes('tonight') || s.includes('today')) return at(now, 0, 20);
  if (s.includes('tomorrow')) return at(now, 1, 9);
  if (s.includes('next class') || s.includes('next lecture')) return at(now, 2, 9);
  if (s.includes('next week')) return at(now, 7, 9);
  if (s.includes('two weeks')) return at(now, 14, 9);
  const today = (now.getDay() + 6) % 7;
  for (let i = 0; i < 7; i++) if (s.includes(WEEKDAYS[i])) return at(now, ((i - today + 7) % 7) || 7, 9);
  return null;
}

export function offlineContext(text) {
  const words = text.toLowerCase().match(/[a-z']+/g) || [];
  const count = new Map(); words.forEach((w) => count.set(w, (count.get(w) || 0) + 1));
  let best = '', top = -1;
  for (const [c, ws] of Object.entries(CONTEXT_WORDS)) {
    const n = ws.reduce((a, w) => a + (count.get(w) || 0), 0);
    if (n > top) { best = c; top = n; }
  }
  if (top >= 2) return best;
  return words.length > 30 ? 'conversation' : 'quiet';
}

export function offlineTopic(text) {
  const freq = new Map();
  for (const w of keywords(text)) if (w.length > 4) freq.set(w, (freq.get(w) || 0) + 1);
  return [...freq].sort((a, b) => b[1] - a[1]).slice(0, 3).map(([w]) => w).join(' ');
}

export function parseDue(due) {
  const m = String(due || '').trim().match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?$/);
  if (!m) return null;
  return new Date(+m[1], +m[2] - 1, +m[3], m[4] ? +m[4] : 9, m[5] ? +m[5] : 0);
}

export function tasksIcs(tasks) {
  const esc = (s) => s.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\n/g, '\\n');
  const stamp = new Date().toISOString().replace(/[-:]/g, '').slice(0, 15) + 'Z';
  const local = (d) => `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}T${pad(d.getHours())}${pad(d.getMinutes())}00`;
  const out = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//ThirdEye//Assistant//EN', 'CALSCALE:GREGORIAN'];
  for (const x of tasks) {
    const due = parseDue(x.due);
    if (!due || x.done) continue;
    const start = x.kind === 'event' ? due : new Date(due.getTime() - 3600e3);
    out.push('BEGIN:VEVENT', `UID:${x.id}@thirdeye`, `DTSTAMP:${stamp}`,
      `DTSTART:${local(start)}`, `DTEND:${local(new Date(start.getTime() + 1800e3))}`,
      `SUMMARY:${esc(x.task.slice(0, 90))}`, `DESCRIPTION:${esc(x.task)}`,
      'BEGIN:VALARM', 'ACTION:DISPLAY', `DESCRIPTION:${esc(x.task.slice(0, 90))}`, 'TRIGGER:-PT30M', 'END:VALARM',
      'END:VEVENT');
  }
  out.push('END:VCALENDAR');
  return out.join('\r\n') + '\r\n';
}

// host: { notes, courseGiven, paused(), ask(text), askVoice(), end(auto), changed() }
export class Brain {
  constructor(host) {
    this.host = host;
    this.context = 'listening'; this.topic = ''; this.title = '';
    this.tasks = host.notes.tasks || (host.notes.tasks = []);
    this.thinking = false; this.lastThink = Date.now(); this.lastSpeech = Date.now(); this.lastSpoken = 0;
    this.doneUpto = 0; this.timer = null;
  }

  start() { this.timer = setInterval(() => this.tick(), 2000); }
  stop() { clearInterval(this.timer); this.timer = null; }

  tick() {
    if (this.host.paused()) { this.lastSpeech = Date.now(); return; }
    const s = getSettings();
    if (Date.now() - this.lastThink >= s.thinkSeconds * 1000) this.think();
    const silentMin = (Date.now() - this.lastSpeech) / 60000;
    if (s.autoEndMinutes && silentMin >= s.autoEndMinutes && this.speech().length) {
      this.stop();
      this.host.end(true);
    }
  }

  onSpeech(text) {
    this.lastSpeech = Date.now();
    const m = WAKE.exec(text);
    if (!m) return;
    const q = m[1].trim();
    if (q.split(/\s+/).filter(Boolean).length >= 2) this.host.ask(q);
    else { speak('Yes?'); setTimeout(() => this.host.askVoice(), 600); }
  }

  speech() { return this.host.notes.entries.filter((e) => e.kind === 'speech'); }

  async think(final = false) {
    if (this.thinking) return;
    const speech = this.speech(), fresh = speech.slice(this.doneUpto);
    const freshText = fresh.map((e) => e.text).join(' ');
    if (!final && freshText.split(/\s+/).filter(Boolean).length < MIN_WORDS) { this.lastThink = Date.now(); return; }
    if (!fresh.length) return;
    this.thinking = true; this.lastThink = Date.now();
    const upto = speech.length;
    try {
      const earlier = speech.slice(Math.max(0, this.doneUpto - 20), this.doneUpto).map((e) => e.text).join(' ');
      let r = null;
      if (aiProvider()) {
        try { r = await this.aiThink(earlier, freshText); } catch (e) { console.warn('[brain] AI failed, using simple rules', e); }
      }
      if (!r) r = this.offlineThink(speech.slice(-40).map((e) => e.text).join(' '), fresh);
      this.apply(r, fresh[fresh.length - 1].t, final);
      this.doneUpto = upto;
    } finally { this.thinking = false; }
  }

  async aiThink(earlier, fresh) {
    const d = new Date();
    const now = `${d.toLocaleDateString('en-US', { weekday: 'long' })} ${fmtDue(d)}`;
    const known = JSON.stringify(this.tasks.map((x) => x.task).slice(-15));
    const raw = await callAi('You infer context and tasks from overheard speech. Output JSON only.',
      PROMPT({ now, context: this.context, topic: this.topic, known, earlier: earlier.slice(-4000) || '(none)', fresh: fresh.slice(-6000) }), 700, true);
    const m = raw.match(/\{[\s\S]*\}/);
    return JSON.parse(m ? m[0] : raw);
  }

  offlineThink(recent, fresh) {
    const now = new Date(), tasks = [];
    for (const e of fresh) {
      for (const s of e.text.split(/(?<=[.!?])\s+/)) {
        if (!TASK_HINT.test(s) || s.split(/\s+/).length < 4 || WAKE.test(s)) continue;
        const due = guessDue(s, now);
        const kind = /\b(due|deadline|submit|exam|quiz|midterm)\b/i.test(s) ? 'deadline' : 'task';
        tasks.push({ task: s.trim(), kind, due: due ? fmtDue(due) : null });
      }
    }
    return { context: offlineContext(recent), topic: offlineTopic(recent), title: '', tasks, explain: [] };
  }

  canSpeak(final) {
    return !final && getSettings().autoSpeak && Date.now() - this.lastSpoken > SPEAK_GAP * 1000;
  }

  apply(r, t, final) {
    const n = this.host.notes;
    const ctx = String(r.context || '').trim().toLowerCase() || this.context;
    if (ctx !== this.context && ctx !== 'quiet') n.addContext(t, ctx, r.topic || '');
    if (ctx !== 'quiet') this.context = ctx;
    this.topic = String(r.topic || this.topic || '').trim();
    n.context = this.context; n.topic = this.topic;
    const title = String(r.title || '').trim();
    if (title && !this.host.courseGiven) { this.title = title; n.course = title; }
    const seen = new Set(this.tasks.map((x) => norm(x.task))), added = [];
    for (const x of r.tasks || []) {
      const task = String(x.task || '').trim();
      if (!task || seen.has(norm(task))) continue;
      seen.add(norm(task));
      const item = { id: crypto.randomUUID().replace(/-/g, '').slice(0, 8), task, kind: x.kind || 'task', due: x.due || null, t, done: false };
      this.tasks.push(item); added.push(item);
    }
    for (const x of added) n.addTask(x.t, x.task, x.due);
    if (added.length) this.writeFiles();
    for (const x of (r.explain || []).slice(0, 1)) {
      const say = String(x.say || '').trim();
      if (!say) continue;
      n.addInsight(t, x.about || '', say);
      if (this.canSpeak(final) && getSettings().speakAnswers) { this.lastSpoken = Date.now(); speak(say); }
    }
    if (added.length && this.canSpeak(final) && getSettings().speakAnswers) {
      this.lastSpoken = Date.now(); speak('Noted: ' + added[0].task.slice(0, 120));
    }
    this.host.changed();
  }

  setDone(id, done = true) {
    const x = this.tasks.find((k) => k.id === id);
    if (x) x.done = !!done;
    this.writeFiles();
  }

  async writeFiles() {
    const n = this.host.notes;
    await n.saveFile('tasks.json', new Blob([JSON.stringify(this.tasks, null, 2)], { type: 'application/json' }));
    await n.saveFile('tasks.ics', new Blob([tasksIcs(this.tasks)], { type: 'text/calendar' }));
    n._later();
  }
}
