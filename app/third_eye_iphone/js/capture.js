// Mic and camera. Resamples the mic to 16 kHz mono and hands out chunks, like audio_capture.py.
import { bus } from './bus.js';
import { getSettings } from './settings.js';

const RATE = 16000;

export function pcmToWav(f32, sampleRate = RATE) {
  const buf = new ArrayBuffer(44 + f32.length * 2);
  const v = new DataView(buf);
  const str = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, 'RIFF'); v.setUint32(4, 36 + f32.length * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
  v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, sampleRate, true); v.setUint32(28, sampleRate * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, 'data'); v.setUint32(40, f32.length * 2, true);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: 'audio/wav' });
}

export class Capture {
  constructor() {
    this.level = 0; this.paused = true; this.sessionStart = 0; this.facing = 'environment';
    this.stream = null; this.ctx = null; this.chunk = []; this.chunkLen = 0; this.askBuf = null;
    this.begun = false; this.wake = null; this.videoEl = document.createElement('video');
    this.videoEl.playsInline = true; this.videoEl.muted = true; this.videoEl.setAttribute('playsinline', '');
    this.error = '';
    document.addEventListener('visibilitychange', () => this._visibility());
  }

  async open({ camera = 'environment' } = {}) {
    this.facing = camera;
    await this._acquire();
    if (!this.ctx) this._startAudio();
    else if (this.ctx.state === 'suspended') await this.ctx.resume();
  }

  async _acquire() {
    const audio = { echoCancellation: true, noiseSuppression: true, autoGainControl: true };
    const tryGet = (c) => navigator.mediaDevices.getUserMedia(c);
    try {
      this.stream = this.facing === 'off' ? await tryGet({ audio }) :
        await tryGet({ audio, video: { facingMode: { ideal: this.facing }, width: { ideal: 1280 }, height: { ideal: 720 } } });
    } catch (e) {
      if (this.facing !== 'off') {
        bus.emit('notice', { level: 'warn', text: 'The camera is not available. Recording audio only.' });
        this.facing = 'off';
        this.stream = await tryGet({ audio });
      } else { this.error = e.message || String(e); throw e; }
    }
    this.error = '';
    const vt = this.stream.getVideoTracks()[0];
    if (vt) { this.videoEl.srcObject = new MediaStream([vt]); this.videoEl.play().catch(() => {}); }
    else this.videoEl.srcObject = null;
    this.stream.getTracks().forEach((t) => { t.onended = () => this._ended(); });
  }

  _startAudio() {
    const AC = window.AudioContext || window.webkitAudioContext;
    this.ctx = new AC();
    const src = this.ctx.createMediaStreamSource(new MediaStream(this.stream.getAudioTracks()));
    this.proc = this.ctx.createScriptProcessor(4096, 1, 1);
    const mute = this.ctx.createGain(); mute.gain.value = 0;
    src.connect(this.proc); this.proc.connect(mute); mute.connect(this.ctx.destination);
    const ratio = this.ctx.sampleRate / RATE;
    this.proc.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      let sum = 0; for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
      const rms = Math.sqrt(sum / input.length);
      this.level = Math.max(Math.min(1, rms * 12), this.level * 0.8);
      const out = new Float32Array(Math.floor(input.length / ratio));
      for (let i = 0; i < out.length; i++) {
        const a = Math.floor(i * ratio), b = Math.min(input.length, Math.floor((i + 1) * ratio));
        let s = 0; for (let j = a; j < b; j++) s += input[j]; out[i] = s / Math.max(1, b - a);
      }
      if (this.askBuf) { this.askBuf.push(out); return; }
      if (!this.begun || this.paused) return;
      this.chunk.push(out); this.chunkLen += out.length;
      if (this.chunkLen >= getSettings().chunkSeconds * RATE) this._flush();
    };
    this._meter = setInterval(() => { this.level *= 0.9; bus.emit('level', { level: this.level }); }, 100);
  }

  _flush() {
    if (!this.chunkLen) return;
    const pcm = new Float32Array(this.chunkLen); let o = 0;
    for (const c of this.chunk) { pcm.set(c, o); o += c.length; }
    const t = Math.max(0, this.elapsed() - pcm.length / RATE);
    this.chunk = []; this.chunkLen = 0;
    bus.emit('chunk', { t, pcm });
  }

  begin() { this.sessionStart = Date.now(); this.begun = true; this.paused = false; this._lock(); }
  elapsed() { return this.begun ? (Date.now() - this.sessionStart) / 1000 : 0; }

  askQuestion(seconds) {
    return new Promise((resolve) => {
      this.askBuf = [];
      setTimeout(() => {
        const parts = this.askBuf; this.askBuf = null;
        const n = parts.reduce((a, p) => a + p.length, 0), pcm = new Float32Array(n); let o = 0;
        for (const p of parts) { pcm.set(p, o); o += p.length; }
        resolve(pcm);
      }, seconds * 1000);
    });
  }

  async switchCamera(facing) {
    this.facing = facing;
    this.stream?.getVideoTracks().forEach((t) => { t.onended = null; t.stop(); });
    if (facing === 'off') { this.videoEl.srcObject = null; return; }
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: facing }, width: { ideal: 1280 }, height: { ideal: 720 } } });
      const vt = s.getVideoTracks()[0];
      this.videoEl.srcObject = new MediaStream([vt]); this.videoEl.play().catch(() => {});
      vt.onended = () => this._ended();
    } catch { bus.emit('notice', { level: 'warn', text: 'Could not switch the camera.' }); }
  }

  get hasVideo() { return !!this.videoEl.srcObject && this.videoEl.videoWidth > 0; }
  snapshot() {
    const c = document.createElement('canvas');
    c.width = this.videoEl.videoWidth; c.height = this.videoEl.videoHeight;
    c.getContext('2d').drawImage(this.videoEl, 0, 0); return c;
  }

  async _lock() {
    try { if ('wakeLock' in navigator && !document.hidden) this.wake = await navigator.wakeLock.request('screen'); } catch {}
  }
  _ended() {
    if (!this.begun || this._gap) return;
    this._gap = this.elapsed();
    bus.emit('interrupted', { reason: 'ended', t: this._gap });
  }
  async _visibility() {
    if (!this.begun) return;
    if (document.hidden) {
      if (this._gap == null) { this._gap = this.elapsed(); bus.emit('interrupted', { reason: 'hidden', t: this._gap }); }
      return;
    }
    await this._lock();
    try { if (this.ctx?.state !== 'running') await this.ctx.resume(); } catch {}
    const dead = !this.stream || this.stream.getAudioTracks().some((t) => t.readyState === 'ended');
    if (dead) {
      try { this.stream?.getTracks().forEach((t) => t.stop()); await this._acquire();
        this.ctx?.close(); this.ctx = null; this._startAudio(); }
      catch { bus.emit('notice', { level: 'error', text: 'The microphone did not come back. Tap Pause, then Resume.' }); }
    } else if (this.videoEl.paused) this.videoEl.play().catch(() => {});
    if (this._gap != null) { const t0 = this._gap; this._gap = null; bus.emit('resumed', { t: this.elapsed(), t0 }); }
  }

  stop() {
    this._flush(); this.begun = false; this.paused = true;
    clearInterval(this._meter); try { this.wake?.release(); } catch {}
    this.stream?.getTracks().forEach((t) => { t.onended = null; t.stop(); });
    try { this.ctx?.close(); } catch {} this.ctx = null; this.stream = null;
    this.videoEl.srcObject = null;
  }
}
