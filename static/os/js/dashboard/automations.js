// Dashboard · Automations: next runs (with live relative time), last results, "Run now", "New automation".

import { h, icon, clear, toast, append } from '../dom.js';
import { os } from '../ctx.js';
import { makeWidget, emptyState, relFuture, relPast, pluralize } from './common.js';
import { tasksApi } from './http.js';

export function createAutomations({ refresh }) {
  const w = makeWidget({ key: 'automations', title: 'AUTOMATIONS', openApp: 'automations' });
  const stats = h('div', { class: 'dau-stats mono' });
  const upcoming = h('div', { class: 'dau-block' });
  const recent = h('div', { class: 'dau-block' });
  const foot = h('div', { class: 'dau-foot' },
    h('button', { class: 'btn btn-soft btn-sm', type: 'button', dataset: { action: 'new-automation' }, on: { click: () => os.openApp('automations', { intent: 'new' }) } }, icon('plus', 13), 'New automation'));
  w.body.append(stats, upcoming, recent, foot);
  let sig = '';
  let data = null;
  const running = new Map();        // task id -> when "Run now" was pressed; shown as running for a few seconds until the server says so itself

  async function runNow(t, btn) {
    btn.disabled = true;
    running.set(t.id, Date.now());
    try {
      await tasksApi.run(t.id);
      toast(`Running “${t.name}”…`, { ms: 2500 });
      setTimeout(refresh, 1200);
    } catch (e) {
      running.delete(t.id);
      btn.disabled = false;
      toast(e.status === 409 ? `“${t.name}” is already running.` : e.message, { kind: e.status === 409 ? 'info' : 'error' });
    }
  }

  const show = (id) => os.openApp('automations', { intent: 'show', id });

  function render(d) {
    data = d;
    const key = JSON.stringify([d.total, d.active, d.paused, d.upcoming.map((u) => [u.id, u.name, u.next_ts, u.label]), d.recent.map((r) => [r.id, r.status]), d.running]);
    if (key === sig) return;
    sig = key;
    w.setCount(d.total ? String(d.total) : null);
    clear(stats); clear(upcoming); clear(recent);
    foot.hidden = false;
    if (!d.total) {
      stats.hidden = true;
      upcoming.append(emptyState('Nothing automated yet. A daily brief or a weekly review is a good first one.', null));
      return;
    }
    stats.hidden = false;
    append(stats, [h('span', { text: `${d.active} active` }), d.paused ? h('span', { text: `${d.paused} paused` }) : null]);
    const now = Date.now();
    if (d.upcoming.length) {
      append(upcoming, [h('div', { class: 'dau-gl mono', text: 'NEXT RUNS' }), d.upcoming.map((u) => {
        const isRunning = d.running.includes(u.id) || (running.get(u.id) || 0) > now - 6000;
        const play = h('button', { class: 'icon-btn dau-run', type: 'button', 'aria-label': `Run now: ${u.name}`, title: 'Run now', disabled: isRunning, dataset: { id: u.id },
          on: { click: (e) => runNow(u, e.currentTarget) } }, icon('play', 13));
        return h('div', { class: 'dau-row', dataset: { id: u.id } },
          h('button', { class: 'dau-hit', type: 'button', title: 'Open in Automations', on: { click: () => show(u.id) } },
            h('span', { class: 'dau-name', text: u.name }),
            h('span', { class: 'dau-sub muted', text: u.label })),
          h('span', { class: 'dau-when mono', dataset: { ts: u.next_ts, kind: 'future' }, text: isRunning ? 'running' : relFuture(u.next_ts, now) }), play);
      })]);
    } else {
      append(upcoming, [h('div', { class: 'dau-gl mono', text: 'NEXT RUNS' }), h('p', { class: 'muted dau-none', text: 'No scheduled runs. Everything is paused or event-driven.' })]);
    }
    if (d.recent.length) {
      append(recent, [h('div', { class: 'dau-gl mono', text: 'LAST RESULTS' }), d.recent.map((r) => h('button', { class: 'dau-row dau-res', type: 'button', dataset: { id: r.task_id, run: r.id }, title: r.summary || 'Open in Automations', on: { click: () => show(r.task_id) } },
        h('i', { class: ['dot', r.status === 'success' ? 'ok' : r.status === 'running' ? 'run' : 'err'], 'aria-label': r.status }),
        h('span', { class: 'dau-hit dau-name', text: r.name }),
        h('span', { class: 'dau-when mono', dataset: { ts: r.started_ts || '', kind: 'past' }, text: r.status === 'running' ? 'running' : r.started_ts ? relPast(r.started_ts, now) : '' })))]);
    }
  }

  function tick(now) {
    if (!data) return;
    let expired = false;
    for (const [id, at] of running) if (at <= now - 6000) { running.delete(id); expired = true; }
    if (expired) { sig = ''; render(data); }
    for (const el of w.el.querySelectorAll('.dau-when[data-ts]')) {
      const ts = Number(el.dataset.ts);
      if (!ts) continue;
      if (el.dataset.kind === 'future') { if (el.textContent !== 'running') { const t = relFuture(ts, now); if (el.textContent !== t) el.textContent = t; } }
      else if (el.textContent !== 'running') { const t = relPast(ts, now); if (el.textContent !== t) el.textContent = t; }
    }
  }

  return { el: w.el, shell: w, render, tick, section: 'automations', summaryCount: (d) => pluralize(d.total, 'automation') };
}
