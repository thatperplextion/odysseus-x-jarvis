// Dashboard · the single source of truth for GET /api/os/today, plus the one-line live summary.

import { get } from '../api.js';
import { isOnline } from '../net.js';
import { tzOffset, relFuture, pluralize } from './common.js';

/** One store per desktop. `refresh()` coalesces: a refresh asked for while one is in flight runs once more afterwards. */
export function createStore() {
  const S = { data: null, error: null, loading: false, last: 0 };
  const subs = new Set();
  let inflight = null;
  let again = false;
  const emit = () => subs.forEach((fn) => { try { fn(S); } catch (e) { console.error(e); } });

  async function run() {
    if (!isOnline()) return;       // server unreachable: keep what is on screen, the reconnect refreshes once
    S.loading = true;
    emit();
    try {
      S.data = await get('/today', { tz_offset: tzOffset() });
      S.error = null;
      S.last = Date.now();
    } catch (e) {
      if (!e?.network) S.error = e;      // an unreachable server is the connection banner's business, not an error state per widget
    } finally {
      S.loading = false;
    }
    emit();
  }

  function refresh() {
    if (inflight) { again = true; return inflight; }
    inflight = (async () => {
      do { again = false; await run(); } while (again);
      inflight = null;
    })();
    return inflight;
  }

  return {
    state: S,
    refresh,
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
    get data() { return S.data; },
  };
}

/** Same wording as the server's build_summary(), but against the live clock so "in 25 min" keeps counting down. */
export function buildSummary(data, now = Date.now()) {
  if (!data) return '';
  const parts = [];
  const ag = data.agenda;
  if (ag && !ag.error) {
    const today = ag.events.filter((e) => e.day === 'today');
    if (today.length) parts.push(pluralize(today.length, 'event'));
    const nu = nextUp(ag, now);
    if (nu && nu.day === 'today') parts.push(nu.start_ts <= now ? `now: ${nu.summary}` : `next: ${nu.summary} ${relFuture(nu.start_ts, now)}`);
    else if (!today.length && !(ag.today_reminders)) parts.push('nothing on the calendar');
  }
  const td = data.todos;
  if (td && !td.error && td.open) parts.push(pluralize(td.open, 'todo'));
  const au = data.automations;
  if (au && !au.error && au.ran_since) {
    parts.push(`${pluralize(au.ran_since, 'automation')} ran ${au.since_label || 'today'}${au.failed_since ? ` (${au.failed_since} failed)` : ''}`);
  }
  const ib = data.inbox;
  if (ib && ib.configured && ib.unread) parts.push(`${ib.unread} unread`);
  const fo = data.focus;
  if (fo && !fo.error && fo.minutes_today) parts.push(`${Math.round(fo.minutes_today)} min focused`);
  return parts.length ? parts.join(' · ') : 'A clear day ahead.';
}

/** The first timed event (or not-yet-due reminder) that has not finished, as seen from `now`. */
export function nextUp(ag, now = Date.now()) {
  const timed = [...ag.events.filter((e) => !e.all_day), ...(ag.reminders || [])].sort((a, b) => a.start_ts - b.start_ts);
  return timed.find((x) => (x.kind === 'reminder' ? x.start_ts > now - 1000 : x.end_ts > now)) || null;
}
