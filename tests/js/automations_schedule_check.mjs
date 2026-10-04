// Run with: node tests/js/automations_schedule_check.mjs   (exit code != 0 on failure)
// Checks the pure schedule maths of the Odysseus OS Automations app (static/os/js/apps/automations/schedule.js).
import {
  localToUtc, utcToLocal, parseCron, cronNextRuns, cronToStructured, structuredToCron, describeStructured,
  describeTask, scheduleFromTask, schedulePayload, parseNaturalSchedule, nextRuns, relFuture, relPast, dowToCron,
} from '../../static/os/js/apps/automations/schedule.js';

let failures = 0;
const eq = (name, got, want) => {
  const stable = (v) => JSON.stringify(v, (k, x) => (x && typeof x === 'object' && !Array.isArray(x) ? Object.fromEntries(Object.entries(x).sort()) : x));
  const g = stable(got); const w = stable(want);
  if (g !== w) { failures++; console.error(`FAIL ${name}\n   got  ${g}\n   want ${w}`); } else console.log(`ok   ${name}`);
};

const IST = 330;      // UTC+5:30, the half-hour offset that breaks naive "subtract whole hours" code
const PST = -480;     // UTC-8
const UTC = 0;

// --- timezone conversion
eq('IST 09:30 -> UTC 04:00 same day', localToUtc(9, 30, IST), { h: 4, m: 0, dayShift: 0 });
eq('IST 01:00 -> UTC 19:30 previous day', localToUtc(1, 0, IST), { h: 19, m: 30, dayShift: -1 });
eq('PST 20:00 -> UTC 04:00 next day', localToUtc(20, 0, PST), { h: 4, m: 0, dayShift: 1 });
eq('UTC 19:30 -> IST 01:00 next day', utcToLocal(19, 30, IST), { h: 1, m: 0, dayShift: 1 });

// --- cron parsing / next runs
eq('parseCron rejects 6 fields', parseCron('0 0 9 * * *'), null);
eq('parseCron rejects garbage', parseCron('hello'), null);
const from = new Date(Date.UTC(2026, 9, 2, 7, 10, 0));     // Fri 2 Oct 2026 07:10 UTC
eq('weekday 04:00 UTC from Fri 07:10 -> Mon', cronNextRuns('0 4 * * 1-5', from, 3).map((d) => d.toISOString()),
  ['2026-10-05T04:00:00.000Z', '2026-10-06T04:00:00.000Z', '2026-10-07T04:00:00.000Z']);
eq('every 15 minutes', cronNextRuns('*/15 * * * *', from, 3).map((d) => d.toISOString().slice(11, 16)), ['07:15', '07:30', '07:45']);
eq('names: MON-FRI / DEC', cronNextRuns('0 9 1 JAN *', from, 1).map((d) => d.toISOString()), ['2027-01-01T09:00:00.000Z']);
eq('dom OR dow when both restricted', cronNextRuns('0 0 13 * 5', from, 2).map((d) => d.toISOString().slice(0, 10)), ['2026-10-09', '2026-10-13']);
eq('dowToCron compresses runs', [dowToCron([1, 2, 3, 4, 5]), dowToCron([0, 6]), dowToCron([1, 3, 5]), dowToCron([0, 1, 2, 3, 4, 5, 6])], ['1-5', '0,6', '1,3,5', '*']);

// --- cron -> English (local time, IST)
const d = (cron) => describeTask({ schedule: 'cron', cron_expression: cron }, IST).text;
eq('weekdays 09:30 IST', d('0 4 * * 1-5'), 'Every weekday at 9:30');
eq('every 2 hours', d('0 */2 * * *'), 'Every 2 hours');
eq('every 15 minutes', d('*/15 * * * *'), 'Every 15 minutes');
eq('hourly', d('0 * * * *'), 'Every hour');
eq('hourly at :15', d('15 * * * *'), 'Every hour at :15');
eq('daily 08:00 IST', d('30 2 * * *'), 'Every day at 8:00');
eq('two times a day', d('30 0,12 * * *'), 'Every day at 6:00 and 18:00');
eq('monday only', d('0 4 * * 1'), 'Every Monday at 9:30');
eq('mon wed fri', d('0 4 * * 1,3,5'), 'Every Mon, Wed and Fri at 9:30');
eq('weekend', d('0 4 * * 0,6'), 'Every weekend at 9:30');
eq('monthly', d('0 4 1 * *'), 'Monthly on the 1st at 9:30');
eq('day shift: 20:00 UTC Sun = Mon 01:30 IST', d('0 20 * * 0'), 'Every Monday at 1:30');
eq('raw fallback', d('5 4 * * 2#1'), 'Cron 5 4 * * 2#1');
eq('raw fallback 2 (hour range)', d('0 9-17 * * *'), 'Cron 0 9-17 * * *');

// --- other task kinds
eq('event', describeTask({ trigger_type: 'event', trigger_event: 'email_received', trigger_count: 5 }).text, 'When an email arrives (every 5)');
eq('event n=1', describeTask({ trigger_type: 'event', trigger_event: 'session_created', trigger_count: 1 }).text, 'When a chat is started');
eq('webhook', describeTask({ trigger_type: 'webhook' }).text, 'When its webhook is called');
eq('daily native', describeTask({ schedule: 'daily', scheduled_time: '04:00' }, IST).text, 'Every day at 9:30');
eq('weekly native Mon (API day 0)', describeTask({ schedule: 'weekly', scheduled_time: '04:00', scheduled_day: 0 }, IST).text, 'Every Monday at 9:30');
eq('monthly native', describeTask({ schedule: 'monthly', scheduled_time: '04:00', scheduled_day: 15 }, IST).text, 'Monthly on the 15th at 9:30');

// --- editor round trips (local -> UTC payload -> local)
const round = (st, off) => {
  const p = schedulePayload(st, off);
  if (p.error) return { error: p.error };
  const task = { trigger_type: 'schedule', ...p.fields };
  const back = scheduleFromTask(task, off);
  return { fields: p.fields, back };
};
let r = round({ mode: 'weekdays', time: '09:30' }, IST);
eq('weekdays payload', r.fields, { schedule: 'cron', cron_expression: '0 4 * * 1-5' });
eq('weekdays round trip', r.back, { mode: 'weekdays', time: '09:30' });
r = round({ mode: 'weekdays', time: '01:00' }, IST);
eq('weekdays 01:00 IST crosses midnight -> UTC Sun-Thu', r.fields, { schedule: 'cron', cron_expression: '30 19 * * 0-4' });
eq('  and reads back as weekdays', r.back, { mode: 'weekdays', time: '01:00' });
r = round({ mode: 'daily', time: '08:00' }, IST);
eq('daily payload', r.fields, { cron_expression: '', schedule: 'daily', scheduled_time: '02:30' });
eq('daily round trip', r.back, { mode: 'daily', time: '08:00' });
r = round({ mode: 'weekly', time: '17:00', days: [5] }, IST);
eq('weekly Fri 17:00 IST -> native weekly Fri (API 4) 11:30 UTC', r.fields, { cron_expression: '', schedule: 'weekly', scheduled_time: '11:30', scheduled_day: 4 });
eq('weekly round trip', r.back, { mode: 'weekly', time: '17:00', days: [5] });
r = round({ mode: 'weekly', time: '00:30', days: [1] }, IST);
eq('weekly Mon 00:30 IST -> Sun (API 6) 19:00 UTC', r.fields, { cron_expression: '', schedule: 'weekly', scheduled_time: '19:00', scheduled_day: 6 });
eq('  round trip', r.back, { mode: 'weekly', time: '00:30', days: [1] });
r = round({ mode: 'weekly', time: '09:00', days: [1, 3, 5] }, PST);
eq('weekly multi-day cron', r.fields, { schedule: 'cron', cron_expression: '0 17 * * 1,3,5' });
eq('  round trip', r.back, { mode: 'weekly', time: '09:00', days: [1, 3, 5] });
r = round({ mode: 'monthly', time: '09:00', dom: 1 }, IST);
eq('monthly', r.fields, { cron_expression: '', schedule: 'monthly', scheduled_time: '03:30', scheduled_day: 1 });
eq('  round trip', r.back, { mode: 'monthly', time: '09:00', dom: 1 });
r = round({ mode: 'monthly', time: '03:00', dom: 1 }, IST);
eq('monthly impossible UTC date -> error not wrong schedule', typeof r.error, 'string');
r = round({ mode: 'interval', unit: 'hours', every: 2, at: 0 }, IST);
eq('interval hours', r.fields, { schedule: 'cron', cron_expression: '0 */2 * * *' });
eq('  round trip', r.back, { mode: 'interval', unit: 'hours', every: 2, at: 0 });
r = round({ mode: 'interval', unit: 'minutes', every: 15 }, IST);
eq('interval minutes', r.fields, { schedule: 'cron', cron_expression: '*/15 * * * *' });
eq('interval 90 minutes rejected', typeof schedulePayload({ mode: 'interval', unit: 'minutes', every: 90 }, IST).error, 'string');
eq('raw cron kept', schedulePayload({ mode: 'cron', cron: '5 4 * * 2' }, IST).fields, { schedule: 'cron', cron_expression: '5 4 * * 2' });
eq('bad cron rejected', typeof schedulePayload({ mode: 'cron', cron: 'nope' }, IST).error, 'string');
eq('once in the past rejected', typeof schedulePayload({ mode: 'once', date: '2020-01-01', time: '09:00' }, IST).error, 'string');
const future = new Date(Date.now() + 3 * 86400000);
const ymd = `${future.getFullYear()}-${String(future.getMonth() + 1).padStart(2, '0')}-${String(future.getDate()).padStart(2, '0')}`;
r = round({ mode: 'once', date: ymd, time: '18:00' }, -future.getTimezoneOffset());
eq('once round trip', r.back, { mode: 'once', date: ymd, time: '18:00' });

// --- next runs
eq('next runs for native weekly (API Mon 04:00 UTC)', nextRuns({ schedule: 'weekly', scheduled_time: '04:00', scheduled_day: 0 }, 2, from).map((x) => x.toISOString()),
  ['2026-10-05T04:00:00.000Z', '2026-10-12T04:00:00.000Z']);
eq('next runs for event task is empty', nextRuns({ trigger_type: 'event' }), []);

// --- natural language (fixed "now": Fri 2 Oct 2026 12:00 local)
const now = new Date(2026, 9, 2, 12, 0, 0);
const nl = (t) => { const x = parseNaturalSchedule(t, now); return x.ok ? x.sched : { ok: false }; };
eq('nl: every weekday at 9:30am', nl('every weekday at 9:30am'), { mode: 'weekdays', time: '09:30' });
eq('nl: weekdays 7pm', nl('weekdays at 7pm'), { mode: 'weekdays', time: '19:00' });
eq('nl: every 2 hours', nl('every 2 hours'), { mode: 'interval', unit: 'hours', every: 2, at: 0 });
eq('nl: every 15 minutes', nl('Every 15 minutes'), { mode: 'interval', unit: 'minutes', every: 15, at: 0 });
eq('nl: hourly', nl('hourly'), { mode: 'interval', unit: 'hours', every: 1, at: 0 });
eq('nl: every day at 8', nl('every day at 8'), { mode: 'daily', time: '08:00' });
eq('nl: daily at 6:45 pm', nl('daily at 6:45 pm'), { mode: 'daily', time: '18:45' });
eq('nl: every morning', nl('every morning'), { mode: 'daily', time: '08:00' });
eq('nl: every monday at 10am', nl('every monday at 10am'), { mode: 'weekly', days: [1], time: '10:00' });
eq('nl: mon, wed and fri at 7', nl('mon, wed and fri at 7'), { mode: 'weekly', days: [1, 3, 5], time: '07:00' });
eq('nl: weekends', nl('every weekend at noon'), { mode: 'weekend', time: '12:00' });
eq('nl: monthly on the 15th at 9', nl('monthly on the 15th at 9'), { mode: 'monthly', dom: 15, time: '09:00' });
eq('nl: first of the month', nl('first of the month at 8am'), { mode: 'monthly', dom: 1, time: '08:00' });
eq('nl: tomorrow at 3pm', nl('tomorrow at 3pm'), { mode: 'once', date: '2026-10-03', time: '15:00' });
eq('nl: in 2 hours', nl('in 2 hours'), { mode: 'once', date: '2026-10-02', time: '14:00' });
eq('nl: on 4 oct at 6pm', nl('on 4 oct at 6pm'), { mode: 'once', date: '2026-10-04', time: '18:00' });
eq('nl: next monday at 9', nl('next monday at 9'), { mode: 'once', date: '2026-10-05', time: '09:00' });
eq('nl: 2026-12-25 08:00', nl('2026-12-25 at 08:00'), { mode: 'once', date: '2026-12-25', time: '08:00' });
eq('nl: bare time means daily', nl('at 5pm'), { mode: 'daily', time: '17:00' });
eq('nl: nonsense', nl('purple monkey dishwasher'), { ok: false });
eq('nl: 90 minutes refused', parseNaturalSchedule('every 90 minutes', now).ok, false);

// --- relative time
const base = Date.UTC(2026, 9, 2, 10, 0, 0);
eq('relFuture 42s', relFuture(new Date(base + 42000), base), 'in 42s');
eq('relFuture 5m', relFuture(new Date(base + 5 * 60000), base), 'in 5m');
eq('relFuture 3h05', relFuture(new Date(base + (3 * 60 + 5) * 60000), base), 'in 3h 5m');
eq('relFuture past is due', relFuture(new Date(base - 1000), base), 'due now');
eq('relPast', relPast(new Date(base - 125000), base), '2m ago');

if (failures) { console.error(`\n${failures} check(s) failed`); process.exit(1); }
console.log('\nall schedule checks passed');
