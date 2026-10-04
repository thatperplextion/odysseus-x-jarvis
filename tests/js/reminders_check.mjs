// Run with: node tests/js/reminders_check.mjs   (exit code != 0 on failure)
// static/os/js/dashboard/reminders.js: which due reminders the Today page announces itself (toast + desktop notification),
// and which it leaves alone because the server already did (server_fired). Pure logic, no browser.
import { planReminders, FRESH_MS } from '../../static/os/js/dashboard/reminders.js';

let failures = 0;
const eq = (name, got, want) => {
  const a = JSON.stringify(got); const b = JSON.stringify(want);
  if (a !== b) { failures++; console.error(`FAIL ${name}\n   got  ${a}\n   want ${b}`); } else console.log(`ok   ${name}`);
};

const NOW = 1_800_000_000_000;
const R = (id, ago, extra = {}) => ({ kind: 'reminder', id, summary: `r ${id}`, start_ts: NOW - ago, key: `reminder:${id}:${NOW - ago}`, ...extra });
const ids = (plan) => plan.map((p) => [p.id.split(':')[0], p.announce]);

eq('a due reminder is announced, with the server key', planReminders([R('a', 5000)], NOW, []).map((p) => [p.key, p.announce]), [[`reminder:a:${NOW - 5000}`, true]]);
eq('a reminder in the future is not due yet', planReminders([R('a', -60000)], NOW, []), []);
eq('one older than the freshness window is history', planReminders([R('a', FRESH_MS + 1000)], NOW, []), []);
eq('one this browser already handled is skipped', planReminders([R('a', 5000)], NOW, [`a:${NOW - 5000}`]), []);
eq('server_fired: remembered but not announced (no toast, no notification)', ids(planReminders([R('a', 5000, { server_fired: true })], NOW, [])), [['a', false]]);
eq('server_fired false / missing: announced', ids(planReminders([R('a', 5000, { server_fired: false }), R('b', 4000)], NOW, [])), [['a', true], ['b', true]]);
eq('the key falls back to the page-made one when the server sends none', planReminders([{ id: 'x', summary: 's', start_ts: NOW - 1000 }], NOW, []).map((p) => p.key), [`reminder:x:${NOW - 1000}`]);
eq('a reminder listed twice is planned once', planReminders([R('a', 5000), R('a', 5000)], NOW, []).length, 1);
eq('junk entries are ignored', planReminders([null, {}, { id: 'q', start_ts: 'soon' }, R('ok', 100)], NOW, []).map((p) => p.id.split(':')[0]), ['ok']);
eq('nothing at all is fine', [planReminders(undefined, NOW, undefined), planReminders([], NOW, [])], [[], []]);
eq('mixed: the server-announced one is silent, the other is not', ids(planReminders([R('a', 9000, { server_fired: true }), R('b', 3000)], NOW, [])), [['a', false], ['b', true]]);

process.exit(failures ? 1 : 0);
