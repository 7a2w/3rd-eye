// Network calls to Claude and Gemini, ported from assistant.py. Keys come from settings only.
import { getSettings } from './settings.js';

const GEMINI_FAST = ['gemini-2.5-flash-lite', 'gemini-2.0-flash-lite', 'gemini-2.5-flash', 'gemini-2.0-flash'];
const GEMINI_SMART = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-2.5-flash-lite'];
const lastGood = {};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function callClaude(system, user, maxTokens = 600) {
  const s = getSettings();
  const r = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'content-type': 'application/json', 'x-api-key': s.anthropicKey, 'anthropic-version': '2023-06-01',
      'anthropic-dangerous-direct-browser-access': 'true',
    },
    body: JSON.stringify({ model: s.aiModel, max_tokens: maxTokens, system, messages: [{ role: 'user', content: user }] }),
  });
  if (!r.ok) throw new Error(`Claude returned ${r.status}`);
  const data = await r.json();
  return (data.content || []).map((b) => b.text || '').join('').trim();
}

async function geminiRequest(model, system, parts, maxTokens, key) {
  const gen = { maxOutputTokens: maxTokens };
  const body = { systemInstruction: { parts: [{ text: system }] }, contents: [{ role: 'user', parts }], generationConfig: gen };
  const url = key.startsWith('AQ.')
    ? `https://aiplatform.googleapis.com/v1/publishers/google/models/${model}:generateContent`
    : `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
  return fetch(url, {
    method: 'POST', headers: { 'content-type': 'application/json', 'x-goog-api-key': key }, body: JSON.stringify(body),
  });
}

export async function callGemini(system, user, maxTokens = 600, fast = false, extraParts = []) {
  const s = getSettings(), mode = fast ? 'fast' : 'smart';
  let models = [...(s.geminiModel && !fast ? [s.geminiModel] : []), ...(fast ? GEMINI_FAST : GEMINI_SMART)];
  if (lastGood[mode]) models.unshift(lastGood[mode]);
  models = [...new Set(models)];
  let lastError = 'no Gemini model answered';
  for (let attempt = 0; attempt < 2; attempt++) {
    for (const model of models) {
      try {
        const r = await geminiRequest(model, system, [...extraParts, { text: user }], maxTokens, s.geminiKey);
        if (r.ok) {
          const d = await r.json();
          const text = (d.candidates?.[0]?.content?.parts || []).map((p) => p.text || '').join('').trim();
          if (text) { lastGood[mode] = model; return text; }
          lastError = `${model} returned an empty answer`; continue;
        }
        if ([404, 500, 503, 504].includes(r.status)) { lastError = `${model}: ${r.status === 404 ? 'not available' : 'busy right now'}`; continue; }
        if (r.status === 429) { lastError = `${model}: limit reached`; continue; }
        if (r.status === 400 || r.status === 403) throw new Error('Gemini did not accept the key or the request.');
        lastError = `${model} returned ${r.status}`;
      } catch (e) {
        if (String(e.message).startsWith('Gemini did not')) throw e;
        lastError = `could not reach ${model}`;
      }
    }
    if (attempt === 0) await sleep(1500);
  }
  throw new Error(lastError);
}

export async function callAi(system, user, maxTokens = 600, fast = false) {
  const s = getSettings();
  if (s.anthropicKey) return callClaude(system, user, maxTokens);
  if (s.geminiKey) return callGemini(system, user, maxTokens, fast);
  throw new Error('no AI key set');
}
