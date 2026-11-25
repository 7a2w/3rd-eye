// Settings: load/save in localStorage (key 'thirdeye.settings') plus the
// settings screen. Keys never leave this phone except in requests to the
// provider they belong to.

const STORAGE_KEY = 'thirdeye.settings';

export const DEFAULTS = {
  course: '',
  anthropicKey: '', aiModel: 'claude-sonnet-5-5',
  geminiKey: '', geminiModel: '',
  openaiKey: '',
  sttEngine: 'auto',        // 'auto' | 'safari' | 'gemini' | 'openai'
  ocrEngine: 'auto',        // 'auto' | 'tesseract' | 'ai' | 'off'
  camera: 'environment',    // 'environment' | 'user' | 'off'
  speakAnswers: true, autoSpeak: true,
  autoEndMinutes: 10, thinkSeconds: 45,
  chunkSeconds: 8, questionSeconds: 6, silenceRms: 0.004,
  slideChangeThreshold: 3, slideStableFrames: 15, minSecondsBetweenSlides: 5,
  clipSeconds: 30,
  contextMinutes: 5, reviewDays: [1, 3, 7], reminderHour: 18,
};

const KEY_FIELDS = ['anthropicKey', 'geminiKey', 'openaiKey'];

function readSaved() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) || {} : {};
  } catch {
    return {};
  }
}

export function getSettings() {
  const saved = readSaved();
  const out = { ...DEFAULTS };
  for (const k of Object.keys(DEFAULTS)) {
    if (saved[k] !== undefined && saved[k] !== null) out[k] = saved[k];
  }
  return out;
}

export function saveSettings(partial) {
  const next = { ...readSaved(), ...partial };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch (err) {
    console.warn('[settings] could not save:', err);
  }
  return getSettings();
}

export function forgetKeys() {
  const blank = {};
  for (const k of KEY_FIELDS) blank[k] = '';
  return saveSettings(blank);
}

// Same rule as config.ai_provider(): Claude if its key is set, else Gemini, else offline.
export function aiProvider() {
  const s = getSettings();
  if (s.anthropicKey) return 'Claude';
  if (s.geminiKey) return 'Gemini';
  return '';
}

// ---------- settings screen ----------

const NUMBER_FIELDS = [
  ['chunkSeconds', 'Speech chunk length (s)', 2, 30, 1],
  ['questionSeconds', 'Question recording length (s)', 2, 20, 1],
  ['contextMinutes', 'Minutes of listening used for answers', 1, 60, 1],
  ['thinkSeconds', 'Think about what it heard every (s)', 15, 600, 5],
  ['autoEndMinutes', 'End the session after this many quiet minutes (0 = never)', 0, 120, 1],
  ['clipSeconds', 'Saved clip length (s)', 5, 120, 5],
  ['silenceRms', 'Silence level (skip quieter chunks)', 0, 0.1, 0.001],
  ['slideChangeThreshold', 'Slide change needed (%)', 0.5, 50, 0.5],
  ['slideStableFrames', 'Frames a slide must stay still (at 30 fps)', 1, 120, 1],
  ['minSecondsBetweenSlides', 'Minimum seconds between slides', 1, 120, 1],
  ['reminderHour', 'Review reminder hour (0-23)', 0, 23, 1],
];

const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function keyRow(id, label, help) {
  return `
    <label class="field" for="set-${id}">
      <span class="field-label">${label}</span>
      <span class="key-row">
        <input id="set-${id}" data-key="${id}" type="password" autocomplete="off"
          autocapitalize="off" autocorrect="off" spellcheck="false" placeholder="Not set">
        <button type="button" class="btn btn-small" data-toggle="${id}">Show</button>
      </span>
      <span class="field-help">${help}</span>
    </label>`;
}

function selectRow(id, label, options, help = '') {
  return `
    <label class="field" for="set-${id}">
      <span class="field-label">${label}</span>
      <select id="set-${id}" data-key="${id}">
        ${options.map(([v, t]) => `<option value="${v}">${esc(t)}</option>`).join('')}
      </select>
      ${help ? `<span class="field-help">${help}</span>` : ''}
    </label>`;
}

// Renders the settings form into `root` and saves on every change.
// `onChange(settings)` lets the app react (new engine, camera, etc.).
export function renderSettings(root, { onChange } = {}) {
  root.innerHTML = `
    <section class="panel">
      <h2 class="panel-title">AI keys</h2>
      <p class="muted">Keys are stored only on this phone. Each key is sent only to its own
        provider when Third Eye asks it something. Without any key, Third Eye still listens,
        uses Safari speech recognition and builds a simpler summary.</p>
      ${keyRow('anthropicKey', 'Claude (Anthropic) key', 'Used for answers and the study sheet.')}
      ${keyRow('geminiKey', 'Gemini (Google) key', 'Free tier works. Used for speech to text, and for answers if there is no Claude key.')}
      ${keyRow('openaiKey', 'OpenAI key', 'Used only for speech to text if chosen.')}
      <button type="button" class="btn btn-danger-outline" id="set-forget">Forget keys</button>
    </section>

    <section class="panel">
      <h2 class="panel-title">Engines</h2>
      ${selectRow('sttEngine', 'Speech to text', [
        ['auto', 'Automatic (Gemini, then OpenAI, then Safari)'],
        ['safari', 'Safari speech recognition (no key)'],
        ['gemini', 'Gemini'],
        ['openai', 'OpenAI'],
      ])}
      ${selectRow('ocrEngine', 'Slide text', [
        ['auto', 'Automatic'],
        ['tesseract', 'On this phone (Tesseract, works offline)'],
        ['ai', 'AI vision (Gemini or Claude)'],
        ['off', 'Off'],
      ])}
      ${selectRow('camera', 'Camera', [
        ['environment', 'Back camera'],
        ['user', 'Front camera'],
        ['off', 'No camera'],
      ])}
      <label class="field field-inline" for="set-speakAnswers">
        <span class="field-label">Speak answers out loud</span>
        <input id="set-speakAnswers" data-key="speakAnswers" type="checkbox" class="switch">
      </label>
      <label class="field field-inline" for="set-autoSpeak">
        <span class="field-label">Speak up without being asked</span>
        <input id="set-autoSpeak" data-key="autoSpeak" type="checkbox" class="switch">
      </label>
    </section>

    <details class="panel">
      <summary class="panel-title">Advanced</summary>
      ${NUMBER_FIELDS.map(([id, label, min, max, step]) => `
        <label class="field field-inline" for="set-${id}">
          <span class="field-label">${label}</span>
          <input id="set-${id}" data-key="${id}" type="number" inputmode="decimal"
            min="${min}" max="${max}" step="${step}" class="num">
        </label>`).join('')}
      <label class="field field-inline" for="set-reviewDays">
        <span class="field-label">Review after (days, comma separated)</span>
        <input id="set-reviewDays" data-key="reviewDays" type="text" inputmode="numeric" class="num">
      </label>
      <label class="field" for="set-aiModel">
        <span class="field-label">Claude model</span>
        <input id="set-aiModel" data-key="aiModel" type="text" autocapitalize="off" autocorrect="off" spellcheck="false">
      </label>
      <label class="field" for="set-geminiModel">
        <span class="field-label">Gemini model (blank = automatic)</span>
        <input id="set-geminiModel" data-key="geminiModel" type="text" autocapitalize="off" autocorrect="off" spellcheck="false">
      </label>
      <button type="button" class="btn" id="set-reset">Reset advanced numbers</button>
    </details>
    <p class="muted small" id="set-saved" aria-live="polite"></p>
  `;

  const fill = () => {
    const s = getSettings();
    root.querySelectorAll('[data-key]').forEach((el) => {
      const k = el.dataset.key;
      if (el.type === 'checkbox') el.checked = !!s[k];
      else if (k === 'reviewDays') el.value = (s.reviewDays || []).join(', ');
      else el.value = s[k] ?? '';
    });
  };
  fill();

  const savedMsg = root.querySelector('#set-saved');
  let msgTimer;
  const flash = (text) => {
    savedMsg.textContent = text;
    clearTimeout(msgTimer);
    msgTimer = setTimeout(() => { savedMsg.textContent = ''; }, 1800);
  };

  root.addEventListener('change', (e) => {
    const el = e.target.closest('[data-key]');
    if (!el) return;
    const k = el.dataset.key;
    let v;
    if (el.type === 'checkbox') v = el.checked;
    else if (el.type === 'number') {
      v = parseFloat(el.value);
      if (Number.isNaN(v)) v = DEFAULTS[k];
      v = Math.min(+el.max, Math.max(+el.min, v));
      el.value = v;
    } else if (k === 'reviewDays') {
      v = el.value.split(/[,\s]+/).map((x) => parseInt(x, 10)).filter((x) => x > 0);
      if (!v.length) v = DEFAULTS.reviewDays;
    } else v = el.value.trim();
    const s = saveSettings({ [k]: v });
    flash('Saved');
    if (onChange) onChange(s, k);
  });

  root.addEventListener('click', (e) => {
    const t = e.target.closest('button');
    if (!t) return;
    if (t.dataset.toggle) {
      const input = root.querySelector(`#set-${t.dataset.toggle}`);
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      t.textContent = show ? 'Hide' : 'Show';
    } else if (t.id === 'set-forget') {
      if (!confirm('Remove all AI keys from this phone?')) return;
      const s = forgetKeys();
      fill();
      flash('Keys removed');
      if (onChange) onChange(s, 'keys');
    } else if (t.id === 'set-reset') {
      const reset = {};
      for (const [k] of NUMBER_FIELDS) reset[k] = DEFAULTS[k];
      reset.reviewDays = DEFAULTS.reviewDays;
      const s = saveSettings(reset);
      fill();
      flash('Advanced numbers reset');
      if (onChange) onChange(s, 'advanced');
    }
  });

  return { refresh: fill };
}
