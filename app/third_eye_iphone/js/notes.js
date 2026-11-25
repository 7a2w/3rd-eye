// Session notes kept in IndexedDB, a port of sync.py NotesWriter.
import { bus } from './bus.js';
import { fmtTime } from './util.js';

let dbp;
function db() {
  if (dbp) return dbp;
  dbp = new Promise((res, rej) => {
    const r = indexedDB.open('thirdeye', 1);
    r.onupgradeneeded = () => { const d = r.result; d.createObjectStore('lectures', { keyPath: 'id' }); d.createObjectStore('blobs'); };
    r.onsuccess = () => { try { navigator.storage?.persist?.(); } catch {} res(r.result); };
    r.onerror = () => rej(r.error);
  });
  return dbp;
}
const tx = async (store, mode, fn) => {
  const d = await db();
  return new Promise((res, rej) => {
    const t = d.transaction(store, mode), out = fn(t.objectStore(store));
    t.oncomplete = () => res(out && 'result' in out ? out.result : undefined); t.onerror = () => rej(t.error);
  });
};
const pad = (n) => String(n).padStart(2, '0');

export class NotesWriter {
  constructor(rec) { Object.assign(this, rec); this.version = 0; this._timer = null; }

  static async create(course) {
    const d = new Date();
    const slug = (course || 'Session').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_|_$/g, '');
    const id = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}_${slug}`;
    const n = new NotesWriter({ id, course: course || 'Session', started: d.toISOString(), entries: [], sheet: null, tasks: [], context: '', topic: '' });
    await n._save(); return n;
  }
  static async load(id) {
    const rec = await tx('lectures', 'readonly', (s) => s.get(id));
    return rec ? new NotesWriter(rec) : null;
  }

  _add(e) {
    this.entries.push(e); this.entries.sort((a, b) => a.t - b.t);
    this.version++; bus.emit('entries', { version: this.version }); this._later();
  }
  addSpeech(t, text) { text = (text || '').trim(); if (text) this._add({ t, kind: 'speech', text }); }
  addSlide(t, img, text = '') { this._add({ t, kind: 'slide', img, text }); }
  addQa(t, q, a) { this._add({ t, kind: 'qa', q, a }); }
  addGap(t, t1) { this._add({ t, kind: 'gap', t1 }); }
  addInsight(t, q, a) { this._add({ t, kind: 'insight', q, a }); }
  addTask(t, text, due) { this._add({ t, kind: 'task', text, due: due || null }); }
  addContext(t, text, topic) { this._add({ t, kind: 'context', text, topic: topic || '' }); }
  setSlideText(img, text) {
    const e = this.entries.find((x) => x.kind === 'slide' && x.img === img);
    if (e) { e.text = text; this.version++; bus.emit('entries', { version: this.version }); this._later(); }
  }

  structured() { return this.entries; }
  transcript(lastSeconds) {
    const all = this.entries.filter((e) => e.kind === 'speech');
    const end = all.length ? all[all.length - 1].t : 0;
    return all.filter((e) => !lastSeconds || e.t >= end - lastSeconds).map((e) => e.text).join(' ');
  }
  timedTranscript() { return this.entries.filter((e) => e.kind === 'speech').map((e) => `[${fmtTime(e.t)}] ${e.text}`).join('\n'); }
  slideText(lastOnly) {
    const s = this.entries.filter((e) => e.kind === 'slide' && e.text);
    return (lastOnly ? s.slice(-1) : s).map((e) => e.text).join('\n\n');
  }

  renderMarkdown() {
    const out = [`# ${this.course}`, '', `Recorded ${new Date(this.started).toLocaleString()}`, ''];
    for (const e of this.entries) {
      if (e.kind === 'speech') out.push(`**[${fmtTime(e.t)}]** ${e.text}`, '');
      else if (e.kind === 'slide') out.push(`**[${fmtTime(e.t)}] Slide** (${e.img})`, '', e.text ? e.text.split('\n').map((l) => '> ' + l).join('\n') : '> No readable text.', '');
      else if (e.kind === 'qa') out.push(`**[${fmtTime(e.t)}] You asked:** ${e.q}`, '', `**Answer:** ${e.a}`, '');
      else if (e.kind === 'insight') out.push(`**[${fmtTime(e.t)}] Third Eye on ${e.q || 'this'}:** ${e.a}`, '');
      else if (e.kind === 'task') out.push(`- [ ] ${e.text}${e.due ? ` (due ${e.due})` : ''}`, '');
      else if (e.kind === 'context') out.push(`---`, '', `*[${fmtTime(e.t)}] Now: ${e.text}${e.topic ? ' · ' + e.topic : ''}*`, '');
      else if (e.kind === 'gap') out.push(`*[${fmtTime(e.t)} to ${fmtTime(e.t1)}] Recording was interrupted.*`, '');
    }
    return out.join('\n');
  }

  _later() { clearTimeout(this._timer); this._timer = setTimeout(() => this._save(), 800); }
  async _save() {
    const rec = { id: this.id, course: this.course, started: this.started, entries: this.entries, sheet: this.sheet, tasks: this.tasks || [], context: this.context || '', topic: this.topic || '' };
    await tx('lectures', 'readwrite', (s) => s.put(rec));
    await this.saveFile('live_notes.md', new Blob([this.renderMarkdown()], { type: 'text/markdown' }));
  }
  async flush() { clearTimeout(this._timer); await this._save(); }

  async saveFile(name, blob) { await tx('blobs', 'readwrite', (s) => s.put(blob, `${this.id}/${name}`)); }
  async getFile(name) { return tx('blobs', 'readonly', (s) => s.get(`${this.id}/${name}`)); }
  async listFiles() {
    const d = await db();
    return new Promise((res) => {
      const out = [], r = d.transaction('blobs').objectStore('blobs').openCursor();
      r.onsuccess = () => {
        const c = r.result; if (!c) return res(out);
        if (String(c.key).startsWith(this.id + '/')) out.push({ name: String(c.key).slice(this.id.length + 1), size: c.value.size });
        c.continue();
      };
    });
  }
}

export async function listLectures() {
  const d = await db();
  const all = await new Promise((res) => { const r = d.transaction('lectures').objectStore('lectures').getAll(); r.onsuccess = () => res(r.result); });
  return all.sort((a, b) => b.started.localeCompare(a.started))
    .map((l) => ({ id: l.id, course: l.course, started: l.started, entryCount: l.entries.length, hasSheet: !!l.sheet, context: l.context || '' }));
}

export async function deleteLecture(id) {
  const d = await db();
  await tx('lectures', 'readwrite', (s) => s.delete(id));
  await new Promise((res) => {
    const t = d.transaction('blobs', 'readwrite'), s = t.objectStore('blobs'), r = s.openKeyCursor();
    r.onsuccess = () => { const c = r.result; if (c) { if (String(c.key).startsWith(id + '/')) s.delete(c.key); c.continue(); } };
    t.oncomplete = res;
  });
}
