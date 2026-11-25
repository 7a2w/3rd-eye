// Tiny event emitter shared by every module. Event names and payloads are
// listed in the build contract (level, chunk, frame, slide, speech, entries,
// clip, interrupted, resumed, notice, status).

const handlers = new Map();

export const bus = {
  on(name, fn) {
    if (!handlers.has(name)) handlers.set(name, new Set());
    handlers.get(name).add(fn);
    return () => bus.off(name, fn);
  },
  off(name, fn) {
    const set = handlers.get(name);
    if (set) set.delete(fn);
  },
  emit(name, data) {
    const set = handlers.get(name);
    if (!set) return;
    for (const fn of [...set]) {
      try {
        fn(data);
      } catch (err) {
        // One broken listener must not stop the others.
        console.error(`[bus] listener for "${name}" failed:`, err);
      }
    }
  },
};

export default bus;
