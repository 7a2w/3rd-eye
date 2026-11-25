// Live answers during a lecture, ported from assistant.py.
import { callAi } from './ai.js';
import { aiProvider } from './settings.js';

export const STOPWORDS = new Set(('a an the and or but if then so of to in on at for from with by as is are was were be been it its this that these those ' +
  'i you he she we they me my your our their do does did have has had not no yes can could will would should what when where which who why how ' +
  'about into than too very just also there here up down out over under again more most some any each other such only own same s t').split(' '));

export function keywords(text) {
  return (text.toLowerCase().match(/[a-z][a-z'-]+/g) || []).filter((w) => !STOPWORDS.has(w) && w.length > 2);
}

export function offlineAnswer(question, transcript) {
  const q = new Set(keywords(question));
  const sentences = transcript.split(/(?<=[.!?])\s+/).filter((s) => s.trim());
  const hit = (s) => keywords(s).filter((w) => q.has(w)).length;
  const best = [...sentences].sort((a, b) => hit(b) - hit(a)).slice(0, 2).filter((s) => hit(s) > 0);
  return best.length ? 'From the lecture: ' + best.join(' ') : "The professor hasn't mentioned that yet in this lecture.";
}

const SYSTEM = 'You are a discreet study assistant speaking through an earpiece to a university student during a lecture. ' +
  'The student may have ADHD or be tired, so answer in 1-3 short, clear spoken sentences. No lists, no markdown. ' +
  'Use the lecture transcript when it is relevant; if you add general knowledge, keep it consistent with what the professor said.';

export class Assistant {
  constructor() { this.provider = aiProvider(); this.online = !!this.provider; }
  async answer(question, recent, slideText = '') {
    if (this.online) {
      try {
        return await callAi(SYSTEM, `Recent lecture transcript:\n${recent || '(nothing yet)'}\n\nText on the current slide/board:\n${slideText || '(none)'}\n\nStudent's question: ${question}`, 200, true);
      } catch (e) { console.warn('[assistant]', e); }
    }
    return offlineAnswer(question, recent);
  }
}

// iOS only allows speech after a tap. Call speak('') from the Start tap once.
export function speak(text) {
  if (!('speechSynthesis' in window)) return;
  const u = new SpeechSynthesisUtterance(text); u.rate = 1;
  speechSynthesis.speak(u);
}
