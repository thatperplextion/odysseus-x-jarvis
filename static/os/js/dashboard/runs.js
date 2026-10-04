// Dashboard · "an automation just finished" toasts. Polls the scheduler's recent runs (every 20 s while the page is
// visible), records a baseline on the first poll, and from then on announces each run that finishes: a toast with
// a "View" action, an entry in the OS notification centre (the bell) and, if permitted, a browser notification.

import { toast } from '../dom.js';
import { post } from '../api.js';
import { os } from '../ctx.js';
import { runText } from '../runtext.js';
import { tasksApi } from './http.js';
import { isOnline } from '../net.js';

const POLL_MS = 20000;

export function startRunWatcher({ housekeeping, onFinished }) {
  const seen = new Map();       // run id -> last status we saw
  let primed = false;
  let timer = null;
  let fails = 0;
  let stopped = false;

  async function poll() {
    if (document.hidden || !isOnline()) return;          // paused while Odysseus is unreachable
    let runs;
    try { runs = (await tasksApi.recent(15)).runs || []; fails = 0; } catch (e) { if (!e?.network) fails += 1; return; }
    if (!primed) {            // the first poll only records what already happened
      for (const r of runs) seen.set(r.id, r.status);
      primed = true;
      return;
    }
    const skip = housekeeping();
    let any = false;
    for (const r of runs.slice().reverse()) {
      const prev = seen.get(r.id);
      seen.set(r.id, r.status);
      if (r.status === 'running' || (prev !== undefined && prev !== 'running')) continue;     // still going, or already announced
      if (r.action && skip.has(r.action) && r.task_type === 'action') continue;                // built-in housekeeping is not news
      any = true;
      announce(r);
    }
    if (any) onFinished?.();
  }

  function announce(r) {
    const ok = r.status === 'success';
    const name = r.task_name || 'Automation';
    const title = ok ? `${name} finished` : `${name} failed`;
    const detail = runText(r).replace(/\s+/g, ' ').trim().slice(0, 160);
    toast(title, { kind: ok ? 'ok' : 'error', ms: 8000, action: { label: 'View', run: () => os.openApp('automations', { intent: 'show', id: r.task_id }) } });
    post('/notify', { title, message: detail || (ok ? 'Completed.' : 'It did not complete.'), severity: ok ? 'success' : 'error', key: `run:${r.id}` }).catch(() => {});
    try {
      if (typeof Notification !== 'undefined' && Notification.permission === 'granted') new Notification(title, { body: detail, tag: `odysseus-run-${r.id}` });
    } catch { /* ignore */ }
  }

  function schedule() {
    if (stopped) return;
    timer = setTimeout(async () => { await poll(); schedule(); }, Math.min(120000, POLL_MS * 2 ** Math.min(fails, 3)));
  }
  poll();
  schedule();
  return { stop() { stopped = true; clearTimeout(timer); }, poll };
}
