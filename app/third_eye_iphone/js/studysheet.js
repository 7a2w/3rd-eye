// Summary sheet after a session, ported from study_sheet.py.
import { callAi } from './ai.js';
import { keywords } from './assistant.js';
import { parseDue } from './brain.js';

const WEEKDAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const TODO_WORDS = /\b(due|homework|assignment|problem set|quiz|exam|midterm|read(ing)? (chapter|pages?|section)|submit|deadline|lab report|essay|project|final exam)\b/i;
const FILLER = new Set('one two three four five six seven eight nine ten first second third next last today talk talking going called happens make makes made thing things something stuff right basically actually kind sort lot people into onto over under want need look see said says say good great example mean means let'.split(' '));

const PROMPT = (course, date, transcript, slides, context) => `You are making a one-page summary sheet for someone with ADHD/insomnia
who may have zoned out during parts of this session. Be concise, concrete and skimmable.

Session: ${course}
What it was: ${context || 'unknown'}
Session date: ${date}

TRANSCRIPT (auto speech-to-text, may contain errors):
${transcript || '(empty)'}

TEXT CAPTURED FROM SLIDES/WHITEBOARD (OCR, may contain errors):
${slides || '(none)'}

Return ONLY valid JSON with exactly these keys:
{
 "title": "short session topic",
 "tldr": "2-3 sentence summary of the whole session",
 "key_points": ["5-8 most important ideas, one short sentence each"],
 "key_terms": [{"term": "...", "definition": "short definition as used in the session"}],
 "exam_questions": ["3-5 self-test questions"],
 "todos": [{"task": "tasks, readings, deadlines or events that came up", "due_in_days": 7}],
 "confusing_parts": ["anything that sounded unclear or worth following up on (can be empty)"]
}
For todos, estimate due_in_days from what was said (e.g. 'next class' ~2, 'next week' 7). Use [] if none.`;

function dueGuess(s) {
  s = s.toLowerCase();
  if (s.includes('tomorrow')) return 1;
  if (s.includes('next class') || s.includes('next lecture')) return 2;
  if (s.includes('next week')) return 7;
  if (s.includes('two weeks')) return 14;
  const today = (new Date().getDay() + 6) % 7;
  for (let i = 0; i < 7; i++) if (s.includes(WEEKDAYS[i])) { const d = ((i - today + 7) % 7) || 7; return s.includes('next ' + WEEKDAYS[i]) && i > today ? d + 7 : d; }
  return 3;
}

export function offlineSheet(course, transcript, slides) {
  transcript = transcript.split(/(?<=[.!?])\s+/).filter((s) => !/\b(?:third|3rd)[\s-]?(?:eye|i|ai)\b/i.test(s)).join(' ');
  const words = keywords(transcript + ' ' + slides);
  const freq = new Map(); words.forEach((w) => freq.set(w, (freq.get(w) || 0) + 1));
  const sentences = [...new Set(transcript.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter((s) => s.split(/\s+/).length >= 6))];
  const good = (w) => !w.includes("'") && !FILLER.has(w) && w.length > 3;
  const bi = new Map();
  for (let i = 0; i < words.length - 1; i++) if (words[i] !== words[i + 1] && good(words[i]) && good(words[i + 1])) {
    const k = words[i] + ' ' + words[i + 1]; bi.set(k, (bi.get(k) || 0) + 1);
  }
  const terms = [], used = new Set();
  for (const [b, c] of [...bi].sort((a, b) => b[1] - a[1]).slice(0, 15)) {
    const p = b.split(' '); if (c >= 2 && !p.some((x) => used.has(x)) && terms.length < 4) { terms.push(b); p.forEach((x) => used.add(x)); }
  }
  for (const [w, c] of [...freq].sort((a, b) => b[1] - a[1]).slice(0, 40)) {
    if (terms.length >= 8 || c < 2) break; if (good(w) && !used.has(w)) { terms.push(w); used.add(w); }
  }
  const score = (s) => { const k = keywords(s); return k.reduce((a, w) => a + (freq.get(w) || 0), 0) / (k.length + 3); };
  const top = new Set([...sentences].sort((a, b) => score(b) - score(a)).slice(0, 7));
  const keyPoints = sentences.filter((s) => top.has(s));
  const define = (t) => sentences.find((s) => s.toLowerCase().includes(t)) || '(mentioned on slides)';
  const todoSents = [...new Set(transcript.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter((s) => TODO_WORDS.test(s) && s.split(/\s+/).length >= 4))];
  return {
    title: course, tldr: keyPoints.slice(0, 2).join(' ') || 'No speech was captured.', key_points: keyPoints,
    key_terms: terms.map((t) => ({ term: t, definition: define(t) })),
    exam_questions: terms.slice(0, 4).map((t) => `Explain '${t}' in your own words and give an example.`),
    todos: todoSents.slice(0, 8).map((s) => ({ task: s, due_in_days: dueGuess(s) })), confusing_parts: [],
    _note: 'Made without an AI key. Add a free Gemini key or a Claude key in Settings for a better sheet.',
  };
}

const ymd = (d) => `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };

export function reviewDates(date, s) { return s.reviewDays.map((n) => addDays(date, n)); }

export function toMarkdown(sheet, course, date, reviewDays) {
  const md = [`# Study sheet: ${sheet.title || course}`, `*${course} - ${date.toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}*`, ''];
  if (sheet._note) md.push(`> ${sheet._note}`, '');
  md.push('## TL;DR', sheet.tldr || '', '', '## Key points', ...(sheet.key_points || []).map((p) => `- ${p}`), '',
    '## Key terms', ...(sheet.key_terms || []).map((t) => `- **${t.term}**: ${t.definition}`), '',
    '## Test yourself', ...(sheet.exam_questions || []).map((q, i) => `${i + 1}. ${q}`), '');
  if ((sheet.confusing_parts || []).length) md.push('## Follow up', ...sheet.confusing_parts.map((c) => `- ${c}`), '');
  md.push('## Tasks and deadlines', ...((sheet.todos || []).length ? sheet.todos.map((t) => `- [ ] ${t.task} (${t.due ? 'due ' + t.due : `due in about ${t.due_in_days} days`})`) : ['None came up.']), '',
    '## Review again on', ...reviewDates(date, { reviewDays }).map((d) => `- ${d.toDateString()}`), '');
  return md.join('\n');
}

export function toIcs(sheet, course, date, s) {
  const ev = [], stamp = new Date().toISOString().replace(/[-:]/g, '').slice(0, 15) + 'Z', hh = String(s.reminderHour).padStart(2, '0');
  const add = (summary, day, desc) => ev.push('BEGIN:VEVENT', `UID:${crypto.randomUUID()}@thirdeye`, `DTSTAMP:${stamp}`,
    `DTSTART:${ymd(day)}T${hh}0000`, `DTEND:${ymd(day)}T${hh}1500`, `SUMMARY:${summary.replace(/[,;\n]/g, ' ')}`, `DESCRIPTION:${desc.replace(/[,;\n]/g, ' ')}`,
    'BEGIN:VALARM', 'ACTION:DISPLAY', 'DESCRIPTION:Review', 'TRIGGER:-PT0M', 'END:VALARM', 'END:VEVENT');
  s.reviewDays.forEach((n) => add(`Review: ${sheet.title || course}`, addDays(date, n), 'Read the study sheet and test yourself out loud.'));
  (sheet.todos || []).forEach((t) => add(`${course}: ${t.task}`.slice(0, 120), addDays(date, t.due_in_days || 3), t.task));
  return ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Third Eye//EN', ...ev, 'END:VCALENDAR'].join('\r\n');
}

const normTask = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9 ]/g, '').trim();

export function mergeTodos(todos, tasks, date) {
  const seen = new Set(tasks.map((x) => normTask(x.task))), out = [];
  for (const x of tasks) {
    if (x.done) continue;
    const due = parseDue(x.due);
    out.push({ task: x.task, due_in_days: due ? Math.max(0, Math.round((due - date) / 864e5)) : 3, due: x.due || null });
  }
  for (const t of todos) if (!seen.has(normTask(t.task))) { seen.add(normTask(t.task)); out.push(t); }
  return out;
}

// Builds the sheet, saves study_sheet.md / .json and reminders.ics, returns the sheet.
export async function generate(notes, s) {
  const date = new Date(notes.started), transcript = notes.transcript(), slides = notes.slideText();
  let sheet;
  try {
    if (!s.anthropicKey && !s.geminiKey) throw new Error('offline');
    const raw = await callAi('You write excellent, accurate study materials. Output JSON only.',
      PROMPT(notes.course, date.toISOString().slice(0, 10), transcript.slice(-60000), slides.slice(-15000), [notes.context, notes.topic].filter(Boolean).join(', ')), 2000);
    const m = raw.match(/\{[\s\S]*\}/); sheet = JSON.parse(m ? m[0] : raw);
  } catch (e) {
    sheet = offlineSheet(notes.course, transcript, slides);
    if (e.message !== 'offline') sheet._note = `The AI could not be reached (${e.message}). This sheet was made without it.`;
  }
  sheet.todos = mergeTodos(sheet.todos || [], notes.tasks || [], date);
  notes.sheet = sheet;
  const t = (x, type) => new Blob([x], { type });
  await notes.saveFile('study_sheet.md', t(toMarkdown(sheet, notes.course, date, s.reviewDays), 'text/markdown'));
  await notes.saveFile('study_sheet.json', t(JSON.stringify(sheet, null, 2), 'application/json'));
  await notes.saveFile('reminders.ics', t(toIcs(sheet, notes.course, date, s), 'text/calendar'));
  await notes.flush();
  return sheet;
}
