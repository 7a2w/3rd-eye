// Slide change detection, a port of vision.py SlideWatcher. Text reading is ocr.js.
const W = 160, H = 90;

export function changePercent(a, b) {
  let n = 0; for (let i = 0; i < a.length; i++) if (Math.abs(a[i] - b[i]) > 30) n++;
  return (n * 100) / a.length;
}

export class SlideWatcher {
  constructor(settings) {
    this.s = settings; this.count = 0; this.prev = null; this.saved = null; this.still = 0; this.lastT = -1e9;
    this.small = document.createElement('canvas'); this.small.width = W; this.small.height = H;
    this.ctx = this.small.getContext('2d', { willReadFrequently: true });
    // The laptop sees about 30 frames a second. The phone sends about 5, so scale the stillness rule.
    this.needStill = Math.max(1, Math.ceil(settings.slideStableFrames * 5 / 30));
  }

  gray(video) {
    this.ctx.filter = 'grayscale(1) blur(1.5px)';
    this.ctx.drawImage(video, 0, 0, W, H);
    const d = this.ctx.getImageData(0, 0, W, H).data, g = new Uint8ClampedArray(W * H);
    for (let i = 0; i < g.length; i++) g[i] = d[i * 4];
    return g;
  }

  // Returns {t, n, blob, dataUrl} when a new slide is saved, else null.
  async process(video, t) {
    if (!video.videoWidth) return null;
    const g = this.gray(video);
    const moving = this.prev ? changePercent(g, this.prev) > 1 : true;
    this.prev = g;
    this.still = moving ? 0 : this.still + 1;
    if (moving || this.still < this.needStill) return null;
    const changed = this.saved ? changePercent(g, this.saved) > this.s.slideChangeThreshold : true;
    if (!changed || t - this.lastT < this.s.minSecondsBetweenSlides) return null;
    this.saved = g; this.lastT = t; this.count++;
    const c = document.createElement('canvas'); c.width = video.videoWidth; c.height = video.videoHeight;
    c.getContext('2d').drawImage(video, 0, 0);
    const blob = await new Promise((r) => c.toBlob(r, 'image/jpeg', 0.85));
    return { t, n: this.count, blob, dataUrl: URL.createObjectURL(blob) };
  }
}
