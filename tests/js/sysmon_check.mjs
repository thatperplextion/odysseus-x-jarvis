// Run with: node tests/js/sysmon_check.mjs   (exit code != 0 on failure)
// static/os/js/sysmon.js: the shared ring buffer of CPU / RAM samples that the Today System widget draws its sparklines from.
import { createHistory, HISTORY_KEEP } from '../../static/os/js/sysmon.js';

let failures = 0;
const eq = (name, got, want) => {
  const a = JSON.stringify(got); const b = JSON.stringify(want);
  if (a !== b) { failures++; console.error(`FAIL ${name}\n   got  ${a}\n   want ${b}`); } else console.log(`ok   ${name}`);
};

const snap = (time, cpu, mem) => ({ time, cpu: { percent: cpu, threads: 9 }, memory: { percent: mem } });
const fakeStorage = () => { const m = new Map(); return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, v), raw: m }; };

{
  const h = createHistory({ keep: 5 });
  eq('starts empty', [h.size, h.series()], [0, { cpu: [], mem: [], time: [] }]);
  eq('records a sample', [h.record(snap(100, 10, 50)), h.size], [true, 1]);
  eq('the same snapshot twice (menu bar and widget share it) counts once', [h.record(snap(100, 10, 50)), h.size], [false, 1]);
  eq('an older snapshot is ignored', [h.record(snap(90, 99, 99)), h.size], [false, 1]);
  for (let i = 1; i <= 6; i++) h.record(snap(100 + i, i, 50 + i));
  eq('keeps only the newest `keep` samples, oldest first', h.series().cpu, [2, 3, 4, 5, 6]);
  eq('series(n) is the last n', h.series(2).mem, [55, 56]);
  eq('series carries the times too', h.series(2).time, [105, 106]);
}
{
  const h = createHistory({ keep: 5 });
  eq('malformed snapshots are refused', [h.record(null), h.record({}), h.record({ time: 1 }), h.record(snap(NaN, 1, 1)), h.record(snap(1, 'x', 1)), h.size], [false, false, false, false, false, 0]);
  eq('numeric strings are fine', [h.record({ time: '5', cpu: { percent: '12.5' }, memory: { percent: '40' } }), h.series().cpu], [true, [12.5]]);
}
{
  // survives a page reload through the storage it is given, and drops what is too old or broken
  const st = fakeStorage();
  const now = 1000;
  const a = createHistory({ keep: 5, storage: st, now: () => now });
  for (let i = 0; i < 4; i++) a.record(snap(990 + i, 10 * i, 30));
  const b = createHistory({ keep: 5, storage: st, now: () => now + 5 });
  eq('a new page starts with the previous page\'s samples (graph has shape at once)', b.series().cpu, [0, 10, 20, 30]);
  const stale = createHistory({ keep: 5, storage: st, now: () => now + 1000, maxAgeS: 300 });
  eq('samples older than the age limit are not restored', stale.size, 0);
  st.setItem('os.sysmon.v1', '{not json');
  eq('corrupt storage is ignored', createHistory({ storage: st }).size, 0);
  st.setItem('os.sysmon.v1', JSON.stringify([{ time: 5000, cpu: 1, mem: 1 }, { time: 995, cpu: 'x', mem: 1 }, { time: 996, cpu: 7, mem: 8 }]));
  eq('entries from the future or with bad numbers are dropped', createHistory({ storage: st, now: () => now }).series().cpu, [7]);
  const broken = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); } };
  const c = createHistory({ storage: broken });
  eq('blocked storage does not break recording', [c.record(snap(1, 2, 3)), c.size], [true, 1]);
}
eq('default size covers a few minutes of samples', HISTORY_KEEP >= 36, true);

process.exit(failures ? 1 : 0);
