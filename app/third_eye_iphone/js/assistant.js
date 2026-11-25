// Live answers, ported from assistant.py.
import { callAi } from './ai.js';
import { aiProvider } from './settings.js';

export const STOPWORDS = new Set(('a an the and or but if then so of to in on at for from with by as is are was were be been it its this that these those ' +
  'i you he she we they me my your our their do does did have has had not no yes can could will would should what when where which who why how ' +
  'about into than too very just also there here up down out over under again more most some any each other such only own same s t').split(' '));

export function keywords(text) {
  return (text.toLowerCase().match(/[a-z][a-z'-]+/g) || []).filter((w) => !STOPWORDS.has(w) && w.length > 2);
}

export function offlineAnswer(question, transcript, tasks = []) {
  const ql = question.toLowerCase(), now = new Date();
  if (/\bwhat time\b/.test(ql)) return `It's ${now.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}.`;
  if (/\bwhat(?:'s| is) (?:the |today's )?date\b|\bwhat day is it\b/.test(ql)) return `It's ${now.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })}.`;
  if (/\b(my tasks|to ?do|todo)\b/.test(ql)) {
    const open = tasks.filter((x) => !x.done);
    if (!open.length) return 'You have no tasks noted yet.';
    return `You have ${open.length} task${open.length === 1 ? '' : 's'}: ` + open.slice(0, 3).map((x) => x.task + (x.due ? `, due ${x.due}` : '')).join('. ') + '.';
  }
  const sentences = transcript.split(/(?<=[.!?])\s+/).filter((s) => s.trim() && !/\b(?:third|3rd)[\s-]?(?:eye|i|ai)\b/i.test(s));
  if (/\b(what did i miss|summari[sz]e|recap)\b/.test(ql)) return sentences.length ? 'Lately: ' + sentences.slice(-3).join(' ') : "I haven't heard anything yet.";
  const q = new Set(keywords(question));
  const hit = (s) => keywords(s).filter((w) => q.has(w)).length;
  const best = [...sentences].sort((a, b) => hit(b) - hit(a)).slice(0, 2).filter((s) => hit(s) > 0);
  return best.length ? 'From what I heard: ' + best.join(' ') : "I haven't heard anything about that yet.";
}

const SYSTEM = (context, topic) => "You are Third Eye, a discreet AI assistant in the user's earpiece. You can hear what is happening around them. " +
  `Current situation: ${context || 'unknown'}, ${topic || 'no clear topic'}. Answer in 1-3 short spoken sentences, no lists or markdown. ` +
  'Use what you heard when relevant, otherwise answer from general knowledge.';

export class Assistant {
  constructor() { this.provider = aiProvider(); this.online = !!this.provider; }
  async answer(question, recent, slideText = '', { context = '', topic = '', tasks = [] } = {}) {
    if (this.online) {
      try {
        const open = tasks.filter((x) => !x.done).map((x) => x.task + (x.due ? ` (due ${x.due})` : '')).join('; ');
        return await callAi(SYSTEM(context, topic), `Now: ${new Date().toString().slice(0, 21)}\n\nRecently heard:\n${recent || '(nothing yet)'}\n\n` +
          `Text from the camera:\n${slideText || '(none)'}\n\nOpen tasks: ${open || '(none)'}\n\nUser: ${question}`, 200, true);
      } catch (e) { console.warn('[assistant]', e); }
    }
    return offlineAnswer(question, recent, tasks);
  }
}

// iOS only allows speech after a tap. Call speak('') from the Start tap once.
export function speak(text) {
  if (!('speechSynthesis' in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  const voice = pickVoice();
  if (voice) u.voice = voice;
  u.rate = 0.95; u.pitch = 1;
  speechSynthesis.speak(u);
}

const PREFERRED = ['Ava (Premium)', 'Zoe (Premium)', 'Ava (Enhanced)', 'Zoe (Enhanced)', 'Samantha (Enhanced)', 'Ava', 'Samantha', 'Karen', 'Moira'];
let chosen = null;
function pickVoice() {
  if (chosen) return chosen;
  const voices = speechSynthesis.getVoices().filter((v) => v.lang.startsWith('en'));
  for (const name of PREFERRED) {
    const v = voices.find((x) => x.name === name || x.name.startsWith(name));
    if (v) return (chosen = v);
  }
  return (chosen = voices.find((v) => /female|natural|premium|enhanced/i.test(v.name)) || null);
}
