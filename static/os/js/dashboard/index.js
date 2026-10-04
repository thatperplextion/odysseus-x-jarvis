// Dashboard · the "Today" command centre under the desktop greeting.
//
// createDashboard() builds the capture bar and the widget grid and owns everything live about them:
//   - GET /api/os/today every 30 s while the desktop is on screen (and straight after any mutation)
//   - a 1 s tick for countdowns / relative times / the focus timer
//   - reminder alerts, "automation finished" toasts, the live one-line summary
// Nothing polls while the tab is hidden or while windows cover the desktop (#home.behind).

import { h, toast, dialog, debounce } from '../dom.js';
import { post } from '../api.js';
import { os } from '../ctx.js';
import { createStore, buildSummary } from './store.js';
import { createCapture } from './capture.js';
import { createAgenda } from './agenda.js';
import { createTodos } from './todos.js';
import { createAutomations } from './automations.js';
import { createFocusController, createFocusWidget, createFocusChip, MODES } from './focus.js';
import { createSystem } from './system.js';
import { createInbox, createModel } from './inbox.js';
import { startRunWatcher } from './runs.js';
import { isOnline } from '../net.js';
import { notesApi } from './http.js';
import { errorState, skeleton, tzOffset } from './common.js';
import { planReminders } from './reminders.js';

const POLL_MS = 30000;
const FIRED_KEY = 'ody.os.reminders.fired';

const readFired = () => { try { return JSON.parse(localStorage.getItem(FIRED_KEY) || '[]'); } catch { return []; } };
const writeFired = (list) => { try { localStorage.setItem(FIRED_KEY, JSON.stringify(list.slice(-80))); } catch { /* ignore */ } };

export function createDashboard() {
  let home = null;
  const isActive = () => !document.hidden && !!home && !home.classList.contains('behind');

  const store = createStore();
  const refresh = () => store.refresh();
  const capture = createCapture({ refresh });
  const ctl = createFocusController({ onLogged: refresh });
  const agenda = createAgenda({ refresh, capture });
  const todos = createTodos({ refresh });
  const automations = createAutomations({ refresh });
  const focus = createFocusWidget({ ctl });
  const inbox = createInbox();
  const model = createModel();
  const system = createSystem({ isActive });
  const chip = createFocusChip({ ctl });
  const dataWidgets = [agenda, todos, automations, focus, inbox, model];

  const grid = h('div', { class: 'dash-grid' }, agenda.el, todos.el, automations.el, focus.el, inbox.el, system.el, model.el);
  const summary = h('p', { class: 'home-sub dash-summary', dataset: { summary: '' }, text: 'What would you like to do?' });
  const el = h('div', { class: 'dash' }, capture.el, grid);

  // ------------------------------------------------------------------ painting
  function paintSummary() {
    const S = store.state;
    if (!S.data) { summary.textContent = S.error && !S.loading ? 'Can’t reach Odysseus right now. Retrying…' : 'What would you like to do?'; return; }
    const text = buildSummary(S.data);
    summary.textContent = S.error ? `${text} (offline, retrying)` : text;
    summary.dataset.stale = S.error ? '1' : '';
  }

  function paint() {
    const S = store.state;
    for (const wd of dataWidgets) {
      if (!wd.section) continue;
      if (wd === focus) {              // the timer works without the server; only its "today" line needs data
        if (S.data?.focus && !S.data.focus.error) wd.render(S.data.focus);
        continue;
      }
      if (!S.data) {
        wd.shell.showState(S.loading || !S.error ? skeleton(3) : errorState(S.error.message, refresh));
        continue;
      }
      const sec = S.data[wd.section];
      if (!sec) continue;
      if (sec.error) { wd.shell.showState(errorState(sec.error, refresh)); continue; }
      wd.shell.showBody();
      try { wd.render(sec); } catch (e) { console.error(e); wd.shell.showState(errorState('This section could not be drawn.', refresh)); }
    }
    paintSummary();
    checkReminders();
  }
  store.subscribe(paint);

  // ------------------------------------------------------------------ reminders
  function checkReminders() {
    const ag = store.state.data?.agenda;
    if (!ag || ag.error) return;
    const fired = readFired();
    for (const { id, key, reminder: r, announce } of planReminders(ag.reminders, Date.now(), fired)) {      // only fresh, not-yet-announced ones
      fired.push(id);
      writeFired(fired);
      if (!announce) continue;          // the server already toasted it and put it in the bell (server_fired): remember it, say nothing
      toast(`Reminder: ${r.summary}`, { kind: 'ok', ms: 12000, action: { label: 'Done', run: async () => { try { await notesApi.archive(r.id); } catch (e) { toast(e.message, { kind: 'error' }); } refresh(); } } });
      post('/notify', { title: 'Reminder', message: r.summary, severity: 'info', key }).catch(() => {});       // same key as the server's: whoever is first wins
      try {
        if (typeof Notification !== 'undefined' && Notification.permission === 'granted') new Notification('Reminder', { body: r.summary, tag: `odysseus-reminder-${r.id}` });
      } catch { /* ignore */ }
    }
  }

  // ------------------------------------------------------------------ polling + tick
  let pollTimer = null;
  let backoff = 0;
  function schedulePoll() {
    clearTimeout(pollTimer);
    const delay = backoff ? Math.min(300000, POLL_MS * 2 ** backoff) : POLL_MS;
    pollTimer = setTimeout(async () => {
      if (isActive() && isOnline()) { await refresh(); backoff = store.state.error ? Math.min(backoff + 1, 4) : 0; }     // paused while Odysseus is unreachable
      schedulePoll();
    }, delay);
  }

  let tickTimer = null;
  let lastSlow = 0;
  function tick() {
    const now = Date.now();
    ctl.tick(now);
    chip.tick();
    if (!isActive()) return;
    for (const wd of dataWidgets) wd.tick(now);
    if (now - lastSlow >= 15000) { lastSlow = now; paintSummary(); checkReminders(); }
  }

  function onVisibility() {
    ctl.tick();
    if (!isActive()) return;
    system.wake();
    if (Date.now() - store.state.last > 15000) refresh();
    tick();
  }

  let observer = null;
  let watcher = null;
  function start(homeEl) {
    home = homeEl;
    paint();
    refresh().then(() => { backoff = store.state.error ? 1 : 0; });
    schedulePoll();
    system.start();
    tickTimer = setInterval(tick, 1000);
    ctl.tick();
    document.addEventListener('visibilitychange', onVisibility);
    observer = new MutationObserver(onVisibility);        // #home.behind flips when windows open / the last one closes
    observer.observe(home, { attributes: true, attributeFilter: ['class'] });
    watcher = startRunWatcher({ housekeeping: () => new Set(store.state.data?.automations?.builtin_actions || []), onFinished: () => setTimeout(refresh, 600) });
    // Jarvis (or any app) announces `os.emit('personal-changed', {kinds})` after it creates or changes automations, todos,
    // events or reminders: reload at once instead of waiting for the 30 s poll. Debounced so a batch of changes is one
    // request, and done even while windows cover the desktop so it is already fresh when they are minimised.
    offPersonal = os.on('personal-changed', onPersonalChanged);
    // Odysseus was unreachable and is back (netui.js): refresh everything once, whether or not the desktop is showing.
    offReconnect = os.on('reconnected', () => { backoff = 0; refresh(); system.wake(); watcher?.poll(); schedulePoll(); });
  }

  let offPersonal = null;
  let offReconnect = null;
  const onPersonalChanged = debounce(() => { refresh(); }, 250);

  function destroy() {
    clearTimeout(pollTimer); clearInterval(tickTimer);
    offPersonal?.(); offReconnect?.(); onPersonalChanged.cancel();
    document.removeEventListener('visibilitychange', onVisibility);
    observer?.disconnect(); watcher?.stop(); system.destroy();
  }

  // ------------------------------------------------------------------ actions used by the palette
  async function captureText(text, { confirmFirst = true } = {}) {
    const clean = (text || '').trim();
    if (!clean) { toast('Type something to capture first.', { ms: 2200 }); return; }
    if (isActive()) { capture.prefill(clean, { run: true }); return; }
    // The desktop is covered by windows: confirm in a dialog instead.
    let res;
    try { res = await post('/capture', { text: clean, tz_offset: tzOffset() }); } catch (e) { toast(e.message, { kind: 'error' }); return; }
    if (!res.can_commit) { toast('Say what the automation should do, e.g. “every weekday at 7am summarize my email”.', { kind: 'error', ms: 5000 }); return; }
    const label = { todo: 'Todo', event: 'Event', reminder: 'Reminder', automation: 'Automation' }[res.kind];
    if (confirmFirst && !(await dialog.confirm(`Add this ${label.toLowerCase()}?`, res.preview_text, { confirmLabel: 'Add' }))) return;
    try {
      const r = await post('/capture/commit', { kind: res.kind, draft: res.draft, tz_offset: tzOffset() });
      toast(r.label, { kind: 'ok', ms: 6000, action: { label: 'Undo', run: async () => { try { await post('/capture/undo', { kind: res.kind, id: r.id, item_id: r.item_id }); } catch (e) { toast(e.message, { kind: 'error' }); } refresh(); } } });
      refresh();
    } catch (e) { toast(e.message, { kind: 'error' }); }
  }

  async function addTodo(text) {
    const clean = (text || '').trim();
    if (!clean) { toast('Type the todo after “Add todo:”.', { ms: 2200 }); return; }
    try {
      const r = await post('/capture/commit', { kind: 'todo', draft: { text: clean }, tz_offset: tzOffset() });
      toast('Todo added', { kind: 'ok', ms: 5000, action: { label: 'Undo', run: async () => { try { await post('/capture/undo', { kind: 'todo', id: r.id, item_id: r.item_id }); } catch (e) { toast(e.message, { kind: 'error' }); } refresh(); } } });
      refresh();
    } catch (e) { toast(e.message, { kind: 'error' }); }
  }

  function startFocus() {
    if (ctl.state.mode !== 'focus') ctl.setMode('focus');
    if (ctl.state.status !== 'running') ctl.start();
    toast(`Focus started: ${MODES.focus.minutes} minutes`, { kind: 'ok', ms: 2500 });
  }

  return { el, summaryEl: summary, focusChip: chip.el, capture, ctl, store, start, destroy, captureText, addTodo, startFocus, refresh, isActive };
}
