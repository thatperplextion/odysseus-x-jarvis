// Automations · schedule maths. Pure functions, no DOM, so they can be unit-tested with node.
//
// How the scheduler thinks about time (src/task_scheduler.py): every clock time and every cron field is
// UTC. "daily 09:00" fires at 09:00 UTC, "0 9 * * 1-5" fires at 09:00 UTC. People think in local time, so
// this module converts at the edge: forms and descriptions are local, what is stored is UTC. Weekday numbers
// inside this module follow cron/JS (0 = Sunday); the API's weekly `scheduled_day` is 0 = Monday.

export const DOW_LONG = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
export const DOW_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTH_FULL = ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'];

const pad = (n) => String(n).padStart(2, '0');
export const fmtClock = (h, m) => `${h}:${pad(m)}`;
export const hhmm = (h, m) => `${pad(h)}:${pad(m)}`;
const ordinal = (n) => { const v = n % 100; return n + (['th', 'st', 'nd', 'rd'][(v - 20) % 10] || ['th', 'st', 'nd', 'rd'][v] || 'th'); };

/** Minutes east of UTC right now (India: +330). */
export const tzOffsetMin = (date = new Date()) => -date.getTimezoneOffset();

/** Local wall-clock time -> UTC slot. dayShift is the UTC date relative to the local date (-1, 0, +1). */
export function localToUtc(h, m, off = tzOffsetMin()) {
  const total = h * 60 + m - off;
  const dayShift = Math.floor(total / 1440);
  const t = total - dayShift * 1440;
  return { h: Math.floor(t / 60), m: t % 60, dayShift };
}
/** UTC slot -> local wall-clock time. dayShift is the local date relative to the UTC date. */
export function utcToLocal(h, m, off = tzOffsetMin()) {
  const total = h * 60 + m + off;
  const dayShift = Math.floor(total / 1440);
  const t = total - dayShift * 1440;
  return { h: Math.floor(t / 60), m: t % 60, dayShift };
}

// ------------------------------------------------------------------------------------------------ cron
const MONTH_NAMES = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
const DOW_NAMES = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };

function parseField(text, lo, hi, names) {
  const out = new Set();
  let star = false;
  for (const part of String(text).split(',')) {
    const [range, stepText] = part.split('/');
    const step = stepText === undefined ? 1 : Number(stepText);
    if (!Number.isInteger(step) || step < 1) return null;
    let a; let b;
    if (range === '*') { a = lo; b = hi; if (stepText === undefined) star = true; }
    else if (range.includes('-')) {
      const [x, y] = range.split('-').map((v) => num(v, names));
      if (x === null || y === null) return null;
      a = x; b = y;
    } else {
      const v = num(range, names);
      if (v === null) return null;
      a = v; b = stepText === undefined ? v : hi;
    }
    if (a < lo || b > hi + (hi === 6 ? 1 : 0) || a > b) return null;
    for (let v = a; v <= b; v += step) out.add(hi === 6 && v === 7 ? 0 : v);
  }
  return { set: out, star };
}
function num(v, names) {
  if (/^\d+$/.test(v)) return Number(v);
  const n = names?.[String(v).toLowerCase().slice(0, 3)];
  return n === undefined ? null : n;
}

/** Parse a 5-field cron expression. Returns null when it is not valid (or has seconds / extensions). */
export function parseCron(expr) {
  const f = String(expr || '').trim().split(/\s+/);
  if (f.length !== 5) return null;
  const min = parseField(f[0], 0, 59); const hour = parseField(f[1], 0, 23);
  const dom = parseField(f[2], 1, 31); const mon = parseField(f[3], 1, 12, MONTH_NAMES);
  const dow = parseField(f[4], 0, 6, DOW_NAMES);
  if (!min || !hour || !dom || !mon || !dow) return null;
  return { min: min.set, hour: hour.set, dom: dom.set, mon: mon.set, dow: dow.set, domStar: dom.star, dowStar: dow.star, fields: f };
}

/** The next `count` fire times (UTC instants) after `from`, like croniter does. */
export function cronNextRuns(expr, from = new Date(), count = 3) {
  const c = parseCron(expr);
  if (!c) return [];
  const hours = [...c.hour].sort((a, b) => a - b);
  const mins = [...c.min].sort((a, b) => a - b);
  const out = [];
  const f = new Date(from);
  let day = Date.UTC(f.getUTCFullYear(), f.getUTCMonth(), f.getUTCDate());
  for (let i = 0; i < 800 && out.length < count; i++, day += 86400000) {
    const d = new Date(day);
    if (!c.mon.has(d.getUTCMonth() + 1)) continue;
    const domOk = c.dom.has(d.getUTCDate()); const dowOk = c.dow.has(d.getUTCDay());
    const dayOk = (c.domStar || c.dowStar) ? (domOk && dowOk) : (domOk || dowOk);
    if (!dayOk) continue;
    for (const h of hours) {
      for (const m of mins) {
        const t = day + (h * 60 + m) * 60000;
        if (t > f.getTime()) { out.push(new Date(t)); if (out.length >= count) return out; }
      }
    }
  }
  return out;
}

const runOf = (xs) => xs.length > 2 && xs.every((v, i) => i === 0 || v === xs[i - 1] + 1);
export function dowToCron(days) {
  const xs = [...new Set(days)].sort((a, b) => a - b);
  if (!xs.length) return '*';
  if (xs.length === 7) return '*';
  if (runOf(xs)) return `${xs[0]}-${xs[xs.length - 1]}`;
  return xs.join(',');
}

// ---------------------------------------------------------------------- structured <-> cron (UTC)
// A "structured" schedule is what the editor edits (all times local):
//   { mode:'interval', unit:'minutes'|'hours', every, at }      (at = minute past the hour, for hours)
//   { mode:'daily'|'weekdays'|'weekend', time:'HH:MM' }
//   { mode:'weekly', time, days:[0..6] }        { mode:'monthly', time, dom }
//   { mode:'once', date:'YYYY-MM-DD', time }    { mode:'cron', cron }  (UTC, raw)

const WEEKDAYS = [1, 2, 3, 4, 5];
const WEEKEND = [0, 6];
const sameSet = (a, b) => a.length === b.length && a.every((v) => b.includes(v));

/** Turn a recurring cron (UTC) into something the editor and the describer understand, in local time. */
export function cronToStructured(expr, off = tzOffsetMin()) {
  const c = parseCron(expr);
  if (!c) return null;
  const [fm, fh, fd, fmo, fw] = c.fields;
  const single = (s) => (s.size === 1 ? [...s][0] : null);
  // Intervals.
  if (fh === '*' && fd === '*' && fmo === '*' && fw === '*') {
    if (fm === '*') return { mode: 'interval', unit: 'minutes', every: 1 };
    const step = /^\*\/(\d+)$/.exec(fm);
    if (step && Number(step[1]) >= 1 && Number(step[1]) <= 59) return { mode: 'interval', unit: 'minutes', every: Number(step[1]) };
    if (single(c.min) !== null && /^\d+$/.test(fm)) return { mode: 'interval', unit: 'hours', every: 1, at: single(c.min) };
  }
  if (fd === '*' && fmo === '*' && fw === '*' && /^\d+$/.test(fm)) {
    const step = /^\*\/(\d+)$/.exec(fh);
    if (step && Number(step[1]) >= 1 && Number(step[1]) <= 23) return { mode: 'interval', unit: 'hours', every: Number(step[1]), at: Number(fm) };
  }
  // Fixed times of day.
  if (/^\d+$/.test(fm) && fmo === '*' && c.hour.size >= 1 && !fh.includes('*') && !fh.includes('/') && !fh.includes('-')) {
    const slots = [...c.hour].sort((a, b) => a - b).map((h) => utcToLocal(h, Number(fm), off));
    const shift = slots[0].dayShift;
    if (!slots.every((s) => s.dayShift === shift)) return null;
    const times = slots.map((s) => hhmm(s.h, s.m)).sort();
    const base = { time: times[0], times };
    if (fd === '*') {
      const days = fw === '*' ? null : [...c.dow].map((d) => (d + shift + 7) % 7).sort((a, b) => a - b);
      if (!days) return { mode: 'daily', ...base };
      if (sameSet(days, WEEKDAYS)) return { mode: 'weekdays', ...base };
      if (sameSet(days, WEEKEND)) return { mode: 'weekend', ...base };
      return { mode: 'weekly', days, ...base };
    }
    if (fw === '*' && c.dom.size === 1 && !fd.includes('*')) {
      const dom = single(c.dom) + shift;
      if (dom < 1 || dom > 28) return null;
      return { mode: 'monthly', dom, ...base };
    }
  }
  return null;
}

/** Cron (UTC) for a recurring structured schedule; returns { cron } or { error }. */
export function structuredToCron(st, off = tzOffsetMin()) {
  if (st.mode === 'cron') return parseCron(st.cron) ? { cron: st.cron.trim() } : { error: 'That is not a valid 5-field cron expression.' };
  if (st.mode === 'interval') {
    const n = Number(st.every);
    if (!Number.isInteger(n) || n < 1) return { error: 'Enter how often, as a whole number.' };
    if (st.unit === 'minutes') {
      if (n > 59) return { error: 'Minutes go up to 59. Use hours for anything longer.' };
      return { cron: n === 1 ? '* * * * *' : `*/${n} * * * *` };
    }
    if (n > 23) return { error: 'Hours go up to 23. Use a daily schedule for anything longer.' };
    const at = Number.isInteger(Number(st.at)) ? Number(st.at) : 0;
    if (at < 0 || at > 59) return { error: 'The minute must be between 0 and 59.' };
    return { cron: n === 1 ? `${at} * * * *` : `${at} */${n} * * *` };
  }
  const t = /^(\d{1,2}):(\d{2})$/.exec(st.time || '');
  if (!t || Number(t[1]) > 23 || Number(t[2]) > 59) return { error: 'Pick a time of day.' };
  const u = localToUtc(Number(t[1]), Number(t[2]), off);
  const shiftDays = (days) => days.map((d) => (d + u.dayShift + 7) % 7);
  if (st.mode === 'daily') return { cron: `${u.m} ${u.h} * * *` };
  if (st.mode === 'weekdays') return { cron: `${u.m} ${u.h} * * ${dowToCron(shiftDays(WEEKDAYS))}` };
  if (st.mode === 'weekend') return { cron: `${u.m} ${u.h} * * ${dowToCron(shiftDays(WEEKEND))}` };
  if (st.mode === 'weekly') {
    if (!st.days?.length) return { error: 'Pick at least one day.' };
    return { cron: `${u.m} ${u.h} * * ${dowToCron(shiftDays(st.days))}` };
  }
  if (st.mode === 'monthly') {
    const dom = Number(st.dom) + u.dayShift;
    if (!Number.isInteger(Number(st.dom)) || st.dom < 1 || st.dom > 28) return { error: 'Pick a day of the month from 1 to 28 (so it exists every month).' };
    if (dom < 1 || dom > 31) return { error: 'At that time of day the UTC date falls in a different month. Pick another day or time.' };
    return { cron: `${u.m} ${u.h} ${dom} * *` };
  }
  return { error: 'Unknown schedule.' };
}

/** English for a structured schedule (local time). */
export function describeStructured(st) {
  const times = (st.times && st.times.length ? st.times : [st.time]).filter(Boolean).map((x) => { const [h, m] = x.split(':').map(Number); return fmtClock(h, m); });
  const at = times.length > 1 ? `${times.slice(0, -1).join(', ')} and ${times[times.length - 1]}` : times[0];
  switch (st.mode) {
    case 'interval':
      if (st.unit === 'minutes') return st.every === 1 ? 'Every minute' : `Every ${st.every} minutes`;
      return `${st.every === 1 ? 'Every hour' : `Every ${st.every} hours`}${st.at ? ` at :${pad(st.at)}` : ''}`;
    case 'daily': return `Every day at ${at}`;
    case 'weekdays': return `Every weekday at ${at}`;
    case 'weekend': return `Every weekend at ${at}`;
    case 'weekly': {
      const names = st.days.map((d) => DOW_SHORT[d]);
      const list = st.days.length === 1 ? DOW_LONG[st.days[0]] : names.length === 2 ? names.join(' and ') : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
      return `Every ${list} at ${at}`;
    }
    case 'monthly': return `Monthly on the ${ordinal(st.dom)} at ${at}`;
    case 'once': return `Once on ${fmtDay(new Date(`${st.date}T${st.time}`))}, ${st.time.replace(/^0/, '')}`;
    default: return '';
  }
}

export function fmtDay(d) {
  const now = new Date();
  return `${d.getDate()} ${MONTHS[d.getMonth()]}${d.getFullYear() === now.getFullYear() ? '' : ` ${d.getFullYear()}`}`;
}

// ------------------------------------------------------------------------------------ task <-> editor
export const EVENT_PHRASE = {
  session_created: 'a chat is started', message_sent: 'a message is sent', document_created: 'a document is created',
  memory_added: 'a memory is added', research_completed: 'research finishes', email_received: 'an email arrives', skill_added: 'a skill is added',
};
export const eventPhrase = (name) => EVENT_PHRASE[name] || String(name || 'an event').replace(/_/g, ' ');

/** The editor's structured schedule for a stored task (null for event / webhook tasks). */
export function scheduleFromTask(task, off = tzOffsetMin()) {
  const trig = task.trigger_type || 'schedule';
  if (trig !== 'schedule') return null;
  const split = (t) => { const [h, m] = String(t || '09:00').split(':').map(Number); return utcToLocal(h || 0, m || 0, off); };
  if (task.schedule === 'once') {
    const d = task.scheduled_date ? new Date(task.scheduled_date) : null;
    if (!d || Number.isNaN(d.getTime())) return { mode: 'once', date: '', time: '09:00' };
    return { mode: 'once', date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`, time: hhmm(d.getHours(), d.getMinutes()) };
  }
  if (task.schedule === 'daily') { const s = split(task.scheduled_time); return { mode: 'daily', time: hhmm(s.h, s.m) }; }
  if (task.schedule === 'weekly') {
    const s = split(task.scheduled_time);
    const utcDow = ((task.scheduled_day ?? 0) + 1) % 7;          // API 0=Mon -> JS 0=Sun
    return { mode: 'weekly', time: hhmm(s.h, s.m), days: [(utcDow + s.dayShift + 7) % 7] };
  }
  if (task.schedule === 'monthly') {
    const s = split(task.scheduled_time);
    return { mode: 'monthly', time: hhmm(s.h, s.m), dom: Math.max(1, Math.min(28, (task.scheduled_day ?? 1) + s.dayShift)) };
  }
  if (task.schedule === 'cron') {
    const st = cronToStructured(task.cron_expression, off);
    if (st && !(st.times && st.times.length > 1)) { delete st.times; return st; }
    return { mode: 'cron', cron: task.cron_expression || '' };
  }
  return null;
}

/** API fields for a structured schedule; returns { fields } or { error }. All times become UTC. */
export function schedulePayload(st, off = tzOffsetMin()) {
  const blank = { cron_expression: '' };
  if (st.mode === 'once') {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(st.date || '')) return { error: 'Pick a date.' };
    const t = /^(\d{1,2}):(\d{2})$/.exec(st.time || '');
    if (!t) return { error: 'Pick a time of day.' };
    const when = new Date(`${st.date}T${pad(Number(t[1]))}:${t[2]}:00`);
    if (Number.isNaN(when.getTime())) return { error: 'That date is not valid.' };
    if (when.getTime() <= Date.now()) return { error: 'That moment has already passed. Pick a time in the future.' };
    const u = localToUtc(Number(t[1]), Number(t[2]), off);
    return { fields: { ...blank, schedule: 'once', scheduled_time: hhmm(u.h, u.m), scheduled_date: when.toISOString() } };
  }
  const t = /^(\d{1,2}):(\d{2})$/.exec(st.time || '');
  const u = t ? localToUtc(Number(t[1]), Number(t[2]), off) : null;
  if (st.mode === 'daily') {
    if (!u) return { error: 'Pick a time of day.' };
    return { fields: { ...blank, schedule: 'daily', scheduled_time: hhmm(u.h, u.m) } };
  }
  if (st.mode === 'weekly' && st.days?.length === 1) {
    if (!u) return { error: 'Pick a time of day.' };
    const utcDow = (st.days[0] + u.dayShift + 7) % 7;
    return { fields: { ...blank, schedule: 'weekly', scheduled_time: hhmm(u.h, u.m), scheduled_day: (utcDow + 6) % 7 } };
  }
  if (st.mode === 'monthly') {
    if (!u) return { error: 'Pick a time of day.' };
    const dom = Number(st.dom);
    if (!Number.isInteger(dom) || dom < 1 || dom > 28) return { error: 'Pick a day of the month from 1 to 28 (so it exists every month).' };
    if (dom + u.dayShift < 1 || dom + u.dayShift > 28) return { error: 'At that time of day the UTC date falls in a different month. Pick another day or time.' };
    return { fields: { ...blank, schedule: 'monthly', scheduled_time: hhmm(u.h, u.m), scheduled_day: dom + u.dayShift } };
  }
  const c = structuredToCron(st, off);
  if (c.error) return { error: c.error };
  return { fields: { schedule: 'cron', cron_expression: c.cron } };
}

/** Cron (UTC) equivalent of any recurring task/payload, for the "next runs" preview. */
export function taskCron(t) {
  if (t.schedule === 'cron') return t.cron_expression || null;
  const [hh, mm] = String(t.scheduled_time || '').split(':').map(Number);
  if (!Number.isInteger(hh) || !Number.isInteger(mm)) return null;
  if (t.schedule === 'daily') return `${mm} ${hh} * * *`;
  if (t.schedule === 'weekly') return `${mm} ${hh} * * ${((t.scheduled_day ?? 0) + 1) % 7}`;
  if (t.schedule === 'monthly') return `${mm} ${hh} ${t.scheduled_day ?? 1} * *`;
  return null;
}

/** Next `count` fire times for a task/payload (Date[]). */
export function nextRuns(t, count = 3, from = new Date()) {
  if ((t.trigger_type || 'schedule') !== 'schedule') return [];
  if (t.schedule === 'once') {
    const d = t.scheduled_date ? new Date(t.scheduled_date) : null;
    return d && d > from ? [d] : [];
  }
  const c = taskCron(t);
  return c ? cronNextRuns(c, from, count) : [];
}

/** One line of English for any task. { text, raw, kind } */
export function describeTask(task, off = tzOffsetMin()) {
  const trig = task.trigger_type || 'schedule';
  if (trig === 'webhook') return { text: 'When its webhook is called', kind: 'webhook' };
  if (trig === 'event') {
    const n = task.trigger_count || 1;
    return { text: `When ${eventPhrase(task.trigger_event)}${n > 1 ? ` (every ${n})` : ''}`, kind: 'event' };
  }
  if (!task.schedule) return { text: 'No schedule', kind: 'none' };
  if (task.schedule === 'cron') {
    const st = cronToStructured(task.cron_expression, off);
    if (st) return { text: describeStructured(st), kind: 'cron' };
    return { text: `Cron ${task.cron_expression || '?'}`, kind: 'cron', raw: true };
  }
  const st = scheduleFromTask(task, off);
  if (!st) return { text: task.schedule, kind: 'other', raw: true };
  if (st.mode === 'once' && !st.date) return { text: 'Once', kind: 'once' };
  return { text: describeStructured(st), kind: task.schedule };
}

// -------------------------------------------------------------------------------------- relative time
export function relFuture(date, now = Date.now()) {
  const s = Math.round((date.getTime() - now) / 1000);
  if (s <= 0) return 'due now';
  if (s < 60) return `in ${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `in ${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return m % 60 ? `in ${h}h ${m % 60}m` : `in ${h}h`;
  const d = Math.floor(h / 24);
  if (d < 7) return `in ${d}d ${h % 24 ? `${h % 24}h` : ''}`.trim();
  return `on ${DOW_SHORT[date.getDay()]} ${fmtDay(date)}`;
}
export function relPast(date, now = Date.now()) {
  const s = Math.round((now - date.getTime()) / 1000);
  if (s < 10) return 'just now';
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 14) return `${d}d ago`;
  return fmtDay(date);
}
export function fmtWhen(date) {
  return `${DOW_SHORT[date.getDay()]} ${fmtDay(date)}, ${fmtClock(date.getHours(), date.getMinutes())}`;
}
export function fmtDuration(ms) {
  if (!Number.isFinite(ms) || ms < 0) return '';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s < 10 ? s.toFixed(1) : Math.round(s)} s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m ${Math.round(s % 60)}s` : `${Math.floor(m / 60)}h ${m % 60}m`;
}

// -------------------------------------------------------------------------- natural-language schedule
const NUM_WORDS = { a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, twelve: 12, fifteen: 15, twenty: 20, thirty: 30 };
const DAY_WORDS = [['sunday', 0], ['sun', 0], ['monday', 1], ['mon', 1], ['tuesday', 2], ['tues', 2], ['tue', 2], ['wednesday', 3], ['weds', 3], ['wed', 3],
  ['thursday', 4], ['thurs', 4], ['thur', 4], ['thu', 4], ['friday', 5], ['fri', 5], ['saturday', 6], ['sat', 6]];

function timeOfDay(s) {
  if (/\bnoon\b/.test(s)) return { h: 12, m: 0 };
  if (/\bmidnight\b/.test(s)) return { h: 0, m: 0 };
  let m = /\b(?:at|@)\s*(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?(?!\d)/.exec(s)
    || /\b(\d{1,2})[:.](\d{2})\s*(am|pm|a\.m\.|p\.m\.)?/.exec(s)
    || /\b(\d{1,2})()\s*(am|pm|a\.m\.|p\.m\.)/.exec(s);
  if (m) {
    let h = Number(m[1]); const min = Number(m[2] || 0);
    const ap = (m[3] || '').replace(/\./g, '');
    if (ap === 'pm' && h < 12) h += 12;
    if (ap === 'am' && h === 12) h = 0;
    if (h > 23 || min > 59) return null;
    return { h, m: min };
  }
  if (/\bmorning\b/.test(s)) return { h: 8, m: 0 };
  if (/\bafternoon\b/.test(s)) return { h: 14, m: 0 };
  if (/\bevening\b/.test(s)) return { h: 18, m: 0 };
  if (/\b(night|nightly)\b/.test(s)) return { h: 22, m: 0 };
  return null;
}

/**
 * Understand phrases like "every weekday at 9:30am", "every 2 hours", "mon, wed and fri at 7", "monthly on the 1st",
 * "tomorrow at 3pm", "in 2 hours", "on 4 oct at 18:00". Returns { ok:true, sched } (the editor's structured form) or
 * { ok:false, reason }.
 */
export function parseNaturalSchedule(input, now = new Date()) {
  const s = ` ${String(input || '').toLowerCase().replace(/[,;]/g, ' ').replace(/\s+/g, ' ').trim()} `;
  if (s.trim().length < 2) return { ok: false, reason: 'empty' };
  const word = (v) => (/^\d+$/.test(v) ? Number(v) : NUM_WORDS[v]);

  // every N minutes / hours
  let m = /\bevery (\d+|[a-z]+) ?(minutes?|mins?|hours?|hrs?)\b/.exec(s);
  if (m && word(m[1]) !== undefined) {
    const n = word(m[1]);
    const unit = m[2].startsWith('h') ? 'hours' : 'minutes';
    if (unit === 'minutes' && n > 59) return { ok: false, reason: 'Minutes go up to 59. For longer gaps use hours.' };
    if (unit === 'hours' && n > 23) return { ok: false, reason: 'Hours go up to 23. For longer gaps use a daily schedule.' };
    const at = /\bat (\d{1,2}) ?(?:past|after)\b/.exec(s);
    return { ok: true, sched: { mode: 'interval', unit, every: Math.max(1, n), at: unit === 'hours' && at ? Number(at[1]) : 0 } };
  }
  if (/\b(every minute|each minute)\b/.test(s)) return { ok: true, sched: { mode: 'interval', unit: 'minutes', every: 1 } };
  if (/\b(hourly|every hour|each hour|every other hour)\b/.test(s)) return { ok: true, sched: { mode: 'interval', unit: 'hours', every: /other/.test(s) ? 2 : 1, at: 0 } };
  if (/\bevery half[- ]hour\b/.test(s)) return { ok: true, sched: { mode: 'interval', unit: 'minutes', every: 30 } };
  if (/\bevery quarter[- ]hour\b/.test(s)) return { ok: true, sched: { mode: 'interval', unit: 'minutes', every: 15 } };

  const tod = timeOfDay(s);
  const timeStr = tod ? hhmm(tod.h, tod.m) : null;

  // relative one-offs: in 2 hours / in 30 minutes
  m = /\bin (\d+|[a-z]+) ?(minutes?|mins?|hours?|hrs?|days?)\b/.exec(s);
  if (m && word(m[1]) !== undefined) {
    const n = word(m[1]);
    const ms = /^h/.test(m[2]) ? n * 3600000 : /^d/.test(m[2]) ? n * 86400000 : n * 60000;
    const when = new Date(now.getTime() + ms);
    if (/^d/.test(m[2]) && tod) when.setHours(tod.h, tod.m, 0, 0);
    when.setSeconds(0, 0);
    return { ok: true, sched: { mode: 'once', date: `${when.getFullYear()}-${pad(when.getMonth() + 1)}-${pad(when.getDate())}`, time: hhmm(when.getHours(), when.getMinutes()) } };
  }
  // today / tomorrow / next <weekday> / on <date>
  const onceAt = (date) => {
    const t = timeStr || '09:00';
    return { ok: true, sched: { mode: 'once', date: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`, time: t } };
  };
  if (/\btomorrow\b/.test(s)) { const d = new Date(now); d.setDate(d.getDate() + 1); return onceAt(d); }
  if (/\btonight\b/.test(s)) { const r = onceAt(new Date(now)); if (!tod) r.sched.time = '21:00'; return r; }
  if (/\btoday\b/.test(s)) return onceAt(new Date(now));
  let nx = /\bnext (sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b/.exec(s);
  if (nx) {
    const dow = DAY_WORDS.find(([w]) => w === nx[1])[1];
    const d = new Date(now); d.setDate(d.getDate() + (((dow - d.getDay() + 7) % 7) || 7));
    return onceAt(d);
  }
  let dt = /\b(?:on )?(\d{4})-(\d{2})-(\d{2})\b/.exec(s);
  if (dt) return onceAt(new Date(Number(dt[1]), Number(dt[2]) - 1, Number(dt[3])));
  const monthRe = MONTH_FULL.map((x) => x.slice(0, 3)).join('|');
  dt = new RegExp(`\\b(?:on )?(\\d{1,2})(?:st|nd|rd|th)? (?:of )?(${monthRe})[a-z]*(?: (\\d{4}))?\\b`).exec(s)
    || new RegExp(`\\b(?:on )?(${monthRe})[a-z]* (\\d{1,2})(?:st|nd|rd|th)?(?: (\\d{4}))?\\b`).exec(s);
  if (dt && !/\bevery\b/.test(s)) {
    const [dayText, monText] = /^\d/.test(dt[1]) ? [dt[1], dt[2]] : [dt[2], dt[1]];
    const monthIdx = MONTH_FULL.findIndex((x) => x.startsWith(monText.slice(0, 3)));
    let year = dt[3] ? Number(dt[3]) : now.getFullYear();
    let d = new Date(year, monthIdx, Number(dayText));
    if (!dt[3] && d.getTime() < now.getTime() - 86400000) d = new Date(year + 1, monthIdx, Number(dayText));
    return onceAt(d);
  }

  // recurring: weekdays / weekend / named days / monthly / daily
  const t = timeStr || '09:00';
  if (/\b(weekdays?|workdays?|work days?|business days?|monday (?:to|through|-) friday|mon-fri)\b/.test(s)) return { ok: true, sched: { mode: 'weekdays', time: t } };
  if (/\bweekends?\b/.test(s)) return { ok: true, sched: { mode: 'weekend', time: t } };
  const days = [];
  for (const [w, d] of DAY_WORDS) { if (new RegExp(`\\b${w}s?\\b`).test(s) && !days.includes(d)) days.push(d); }
  const range = /\b(mon|tue|wed|thu|fri|sat|sun)[a-z]* (?:to|through|-) (mon|tue|wed|thu|fri|sat|sun)[a-z]*\b/.exec(s);
  if (range) {
    const a = DAY_WORDS.find(([w]) => w === range[1])[1]; const b = DAY_WORDS.find(([w]) => w === range[2])[1];
    const out = []; for (let d = a; ; d = (d + 1) % 7) { out.push(d); if (d === b || out.length > 7) break; }
    return { ok: true, sched: { mode: out.length === 7 ? 'daily' : 'weekly', days: out.sort((x, y) => x - y), time: t } };
  }
  if (days.length) return { ok: true, sched: { mode: 'weekly', days: days.sort((a, b) => a - b), time: t } };
  const dom = /\b(?:on )?(?:the )?(\d{1,2})(?:st|nd|rd|th)(?: of (?:every|each|the) month)?\b/.exec(s);
  if (/\b(monthly|every month|each month|first of the month|of every month|of each month)\b/.test(s) || dom) {
    const first = /\bfirst\b/.test(s);
    const day = dom ? Number(dom[1]) : first ? 1 : 1;
    if (day < 1 || day > 28) return { ok: false, reason: 'Pick a day from 1 to 28 so it exists every month.' };
    return { ok: true, sched: { mode: 'monthly', dom: day, time: t } };
  }
  if (/\bweekly|every week\b/.test(s)) return { ok: true, sched: { mode: 'weekly', days: [1], time: t } };
  if (/\b(daily|every day|each day|everyday|every (morning|evening|night|afternoon)|nightly|every night)\b/.test(s) || tod) {
    return { ok: true, sched: { mode: 'daily', time: t } };
  }
  return { ok: false, reason: 'I could not read that. Try “every weekday at 9:30am”, “every 2 hours” or “tomorrow at 3pm”.' };
}
