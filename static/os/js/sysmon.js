// One shared "what is the machine doing" sample for everything that wants it (the menu bar pulse, the Today System widget).
// Each of them used to poll /api/os/system on its own timer, so an idle desktop fetched the same snapshot ~25 times a minute.
//
// Every snapshot that comes through here is also recorded in a small ring buffer, so a graph that is built later (the Today view
// opened after a while, the dashboard re-rendered, the page reloaded) starts with the recent past instead of an empty line. The
// buffer is mirrored to sessionStorage (this tab only, a few minutes at most) so a reload does not lose it either.

import { get } from './api.js';

export const HISTORY_KEEP = 40;               // samples (about 3 minutes at one every ~5 s)
export const HISTORY_MAX_AGE_S = 300;         // older entries are dropped when restoring
const STORE_KEY = 'os.sysmon.v1';

/**
 * A ring of {time, cpu, mem} points. `record(snapshot)` ignores a snapshot it already has (same `time`) and anything malformed.
 * `storage` is any {getItem, setItem} (sessionStorage in the browser); failures to read or write it are ignored.
 */
export function createHistory({ keep = HISTORY_KEEP, storage = null, key = STORE_KEY, maxAgeS = HISTORY_MAX_AGE_S, now = () => Date.now() / 1000 } = {}) {
  let points = [];
  try {
    const raw = storage && storage.getItem(key);
    if (raw) {
      const saved = JSON.parse(raw);
      if (Array.isArray(saved)) points = saved.filter((p) => p && Number.isFinite(p.time) && Number.isFinite(p.cpu) && Number.isFinite(p.mem) && now() - p.time <= maxAgeS && p.time <= now() + 5).slice(-keep);
    }
  } catch { points = []; }
  const save = () => { try { if (storage) storage.setItem(key, JSON.stringify(points)); } catch { /* storage full or blocked */ } };
  return {
    record(snap) {
      const time = Number(snap?.time);
      const cpu = Number(snap?.cpu?.percent);
      const mem = Number(snap?.memory?.percent);
      if (!Number.isFinite(time) || !Number.isFinite(cpu) || !Number.isFinite(mem)) return false;
      if (points.length && time <= points[points.length - 1].time) return false;        // already have it (or an older one)
      points.push({ time, cpu, mem });
      if (points.length > keep) points.splice(0, points.length - keep);
      save();
      return true;
    },
    /** The last `n` samples as plain arrays, oldest first. */
    series(n = keep) {
      const tail = points.slice(-n);
      return { cpu: tail.map((p) => p.cpu), mem: tail.map((p) => p.mem), time: tail.map((p) => p.time) };
    },
    get size() { return points.length; },
  };
}

function browserStorage() {
  try { return typeof sessionStorage !== 'undefined' ? sessionStorage : null; } catch { return null; }
}

export const history = createHistory({ storage: browserStorage() });

let cache = { at: 0, data: null };
let inflight = null;

/** The latest /api/os/system snapshot; asks the server at most once per `maxAge` ms however many callers there are. */
export function systemSnapshot(maxAge = 4500) {
  if (cache.data && Date.now() - cache.at < maxAge) return Promise.resolve(cache.data);
  if (!inflight) {
    inflight = get('/system').then((data) => { cache = { at: Date.now(), data }; history.record(data); return data; }).finally(() => { inflight = null; });
  }
  return inflight;
}

/** The last snapshot that came through if it is younger than `maxAgeMs`, else null. Never makes a request. */
export function lastSnapshot(maxAgeMs = Infinity) { return cache.data && Date.now() - cache.at <= maxAgeMs ? cache.data : null; }
