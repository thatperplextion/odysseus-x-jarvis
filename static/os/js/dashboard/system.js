// Dashboard · System: CPU / memory / disk with small sparklines. Polls /api/os/system (the Task Manager's endpoint)
// every 5 s, and only while the desktop is actually on screen.

import { h, fmtBytes } from '../dom.js';
import { systemSnapshot, lastSnapshot, history } from '../sysmon.js';
import { isOnline } from '../net.js';
import { makeWidget, errorState, skeleton, sparkline } from './common.js';

const POLL_MS = 5000;
const KEEP = 36;                // points in each graph; the shared history (sysmon.js) is where they come from

export function createSystem({ isActive }) {
  const w = makeWidget({ key: 'system', title: 'SYSTEM', openApp: 'taskmgr', openLabel: 'Task Manager' });
  const cpu = { hist: [], spark: sparkline(), val: h('span', { class: 'sy-val mono' }), sub: h('span', { class: 'sy-sub muted mono' }) };
  const mem = { hist: [], spark: sparkline(), val: h('span', { class: 'sy-val mono' }), sub: h('span', { class: 'sy-sub muted mono' }) };
  const diskVal = h('span', { class: 'sy-val mono' });
  const diskSub = h('span', { class: 'sy-sub muted mono' });
  const diskBar = h('i', { class: 'sy-fill' });
  const row = (name, c) => h('div', { class: 'sy-row', dataset: { metric: name.toLowerCase() } },
    h('div', { class: 'sy-head' }, h('span', { class: 'sy-name mono', text: name }), c.val, c.sub), c.spark.el);
  const rows = h('div', { class: 'sy-rows', hidden: true },
    row('CPU', cpu), row('RAM', mem),
    h('div', { class: 'sy-row sy-disk', dataset: { metric: 'disk' } }, h('div', { class: 'sy-head' }, h('span', { class: 'sy-name mono', text: 'DISK' }), diskVal, diskSub), h('span', { class: 'sy-bar' }, diskBar)));
  const holder = h('div', { class: 'sy-state' }, skeleton(3));
  w.body.append(holder, rows);
  let timer = null;
  let fails = 0;
  let inflight = false;
  let lastSample = 0;

  // The graphs draw sysmon.js's shared history (the menu bar has been sampling since boot), so a widget that is built or rebuilt
  // later starts with the recent past instead of an empty line. This widget does not poll more for it.
  const draw = () => { const hs = history.series(KEEP); cpu.hist = hs.cpu; mem.hist = hs.mem; cpu.spark.set(hs.cpu); mem.spark.set(hs.mem); };

  function paint(s) {
    holder.hidden = true; rows.hidden = false;
    if (s.time !== lastSample) { lastSample = s.time; draw(); }       // the menu bar may have fetched this very snapshot already
    cpu.val.textContent = `${Math.round(s.cpu.percent)}%`;
    cpu.sub.textContent = `${s.cpu.threads} threads`;
    mem.val.textContent = `${Math.round(s.memory.percent)}%`;
    mem.sub.textContent = `${fmtBytes(s.memory.used)} of ${fmtBytes(s.memory.total)}`;
    const d = (s.disks || []).find((x) => x.system) || (s.disks || [])[0];   // the drive the OS is on, not just the first one listed
    if (d) {
      diskVal.textContent = `${Math.round(d.percent)}%`;
      diskSub.textContent = `${d.mount.replace(/[\\/]+$/, '') || d.mount} · ${fmtBytes(d.used)} of ${fmtBytes(d.total)}`;
      diskBar.style.width = `${Math.min(100, d.percent)}%`;
    }
    w.el.dataset.hot = s.memory.percent > 90 || s.cpu.percent > 90 ? '1' : '';
  }

  async function sample() {
    if (inflight || !isOnline()) return;          // paused while Odysseus is unreachable; the graphs keep their last values
    inflight = true;
    try {
      const s = await systemSnapshot();
      fails = 0;
      paint(s);
    } catch (e) {
      if (e?.network) return;            // the connection banner covers it; keep the skeleton / last values
      fails += 1;
      if (rows.hidden) { holder.hidden = false; holder.replaceChildren(errorState(e.message, () => { holder.replaceChildren(skeleton(3)); sample(); })); }
    } finally { inflight = false; }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(async () => { if (isActive()) await sample(); schedule(); }, Math.min(60000, POLL_MS * 2 ** Math.min(fails, 4)));
  }

  draw();           // whatever the shared history already holds, before the first sample of this widget arrives
  const known = lastSnapshot(15000);
  if (known) paint(known);                  // a snapshot from the last few seconds is on hand: show it at once, no request

  return {
    el: w.el,
    section: null,
    start() { if (isActive()) sample(); schedule(); },
    wake() { if (isActive()) sample(); },
    destroy() { clearTimeout(timer); },
    render() {}, tick() {},
  };
}
