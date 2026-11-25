// Slide text. Tesseract.js runs on the phone, or Gemini/Claude read the picture.
import { callGemini, callClaude } from './ai.js';

let worker = null;

function clean(text) {
  return (text || '').split('\n').map((l) => l.trim()).filter((l) => {
    if (l.length < 3) return false;
    const letters = [...l].filter((c) => /[A-Za-z]/.test(c)).length;
    return letters / l.length >= 0.5;
  }).join('\n');
}

export function ocrEngineName(s) {
  if (s.ocrEngine === 'off') return 'off';
  if (s.ocrEngine === 'ai') return s.geminiKey || s.anthropicKey ? 'ai' : 'tesseract';
  return s.ocrEngine === 'auto' ? 'tesseract' : s.ocrEngine;
}

async function tesseract(blob) {
  if (!worker) {
    const T = await import('../vendor/tesseract/tesseract.esm.min.js');
    worker = await T.createWorker('eng', 1, {
      workerPath: new URL('../vendor/tesseract/worker.min.js', import.meta.url).href,
      corePath: new URL('../vendor/tesseract/core/', import.meta.url).href,
      langPath: new URL('../vendor/tesseract/lang/', import.meta.url).href,
      gzip: true,
    });
  }
  return (await worker.recognize(blob)).data.text;
}

async function viaAi(blob, s) {
  const data = await new Promise((res) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1]); r.readAsDataURL(blob); });
  const sys = 'Read the text on this slide or whiteboard. Return only the text, one line per line. Return nothing if there is none.';
  if (s.geminiKey) return callGemini(sys, 'Read this picture.', 800, true, [{ inlineData: { mimeType: 'image/jpeg', data } }]);
  const r = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-api-key': s.anthropicKey, 'anthropic-version': '2023-06-01', 'anthropic-dangerous-direct-browser-access': 'true' },
    body: JSON.stringify({ model: s.aiModel, max_tokens: 800, system: sys, messages: [{ role: 'user', content: [
      { type: 'image', source: { type: 'base64', media_type: 'image/jpeg', data } }, { type: 'text', text: 'Read this picture.' }] }] }),
  });
  if (!r.ok) throw new Error(`Claude returned ${r.status}`);
  return ((await r.json()).content || []).map((b) => b.text || '').join('');
}

export async function ocrImage(blob, s) {
  const eng = ocrEngineName(s);
  if (eng === 'off') return '';
  try { return clean(eng === 'ai' ? await viaAi(blob, s) : await tesseract(blob)); }
  catch (e) { console.warn('[ocr]', e); return ''; }
}
