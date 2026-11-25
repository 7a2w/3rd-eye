// Speech to text. Gemini and OpenAI take audio; Safari's own recognizer works live with no key.
import { pcmToWav } from './capture.js';
import { callGemini } from './ai.js';

const rms = (a) => { let s = 0; for (let i = 0; i < a.length; i++) s += a[i] * a[i]; return Math.sqrt(s / Math.max(1, a.length)); };
const b64 = (blob) => new Promise((res) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1]); r.readAsDataURL(blob); });

export class Transcriber {
  constructor(s) {
    this.s = s; this.last = ''; this.status = 'ready'; this.rec = null;
    const sr = window.SpeechRecognition || window.webkitSpeechRecognition;
    this.safariOk = !!sr;
    const pick = s.sttEngine === 'auto' ? (s.geminiKey ? 'gemini' : s.openaiKey ? 'openai' : 'safari') : s.sttEngine;
    this.engine = pick;
    if (pick === 'safari' && !sr) this.status = 'error: this browser has no speech recognition';
  }

  get live() { return this.engine === 'safari'; }

  async transcribe(pcm) {
    if (rms(pcm) < this.s.silenceRms) return '';
    const wav = pcmToWav(pcm);
    let text = '';
    if (this.engine === 'gemini') {
      const data = await b64(wav);
      text = await callGemini('You transcribe speech. Return only the words spoken, no commentary. Return nothing if there is no speech.',
        this.last ? `Previous words, for context: ${this.last.slice(-200)}` : 'Transcribe this audio.', 600, true,
        [{ inlineData: { mimeType: 'audio/wav', data } }]);
    } else if (this.engine === 'openai') {
      const f = new FormData(); f.append('file', wav, 'chunk.wav'); f.append('model', 'whisper-1');
      if (this.last) f.append('prompt', this.last.slice(-200));
      const r = await fetch('https://api.openai.com/v1/audio/transcriptions', { method: 'POST', headers: { Authorization: `Bearer ${this.s.openaiKey}` }, body: f });
      if (!r.ok) throw new Error(`OpenAI returned ${r.status}`);
      text = (await r.json()).text || '';
    }
    text = text.trim();
    if (text) this.last = text;
    return text;
  }

  // Safari only. onText(text) fires for each finished phrase.
  startLive(onText) {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    this.stopped = false;
    const run = () => {
      const r = new SR(); r.continuous = true; r.interimResults = false; r.lang = 'en-US';
      r.onresult = (e) => { for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) onText(e.results[i][0].transcript.trim()); };
      r.onend = () => { if (!this.stopped) setTimeout(() => { try { run(); } catch {} }, 300); };
      r.onerror = () => {};
      this.rec = r; try { r.start(); } catch {}
    };
    run();
  }
  stopLive() { this.stopped = true; try { this.rec?.stop(); } catch {} }

  // One short phrase from the mic, for spoken questions on the Safari engine.
  listenOnce(seconds) {
    return new Promise((res) => {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SR) return res('');
      const r = new SR(); let text = '';
      r.lang = 'en-US'; r.interimResults = false;
      r.onresult = (e) => { text += ' ' + e.results[0][0].transcript; };
      r.onend = () => res(text.trim()); r.onerror = () => res(text.trim());
      try { r.start(); } catch { return res(''); }
      setTimeout(() => { try { r.stop(); } catch {} }, seconds * 1000);
    });
  }
}
