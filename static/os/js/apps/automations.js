// Automations: schedule, trigger and watch the things Odysseus does for you. A native front-end for the existing
// scheduler (routes/task_routes.py -> /api/tasks/*). Nothing here schedules anything itself.
//
// Open it from anywhere in the shell:
//   os.openApp('automations', { intent: 'new', prefill: { name, prompt | action | command, schedule: 'every weekday at 9:30am' | cron: '0 4 * * 1-5', output_target } })
//   os.openApp('automations', { intent: 'show', id })           also { filter: 'active' | 'paused' | 'builtin' | 'mine' }
// The window is a singleton, so a second call is delivered to the open one through onReuse().

import { h, icon, clear, dialog, toast } from '../dom.js';
import { os } from '../ctx.js';
import { isOnline } from '../net.js';
import { runText } from '../runtext.js';
import { tasksApi, ApiError } from './automations/client.js';
import {
  describeTask, nextRuns, relFuture, relPast, fmtWhen, fmtDuration, scheduleFromTask, parseNaturalSchedule, cronToStructured,
} from './automations/schedule.js';
import {
  typeChip, kindOfTask, actionTitle, actionBlurb, outputLabel, draftFromTask, blankDraft, COMMAND_ACTIONS, TEMPLATES,
} from './automations/templates.js';
import { openEditor, tzLabel } from './automations/editor.js';

export const meta = { id: 'automations', name: 'Automations', icon: 'zap', width: 1020, height: 660, singleton: true };

const POLL_MS = 15000;
const POLL_BUSY_MS = 5000;
const WATCH_MS = 2800;            // the scheduler waits ~1.5 s of API quiet before starting a run, so don't poll faster
const TABS = [['all', 'All'], ['active', 'Active'], ['paused', 'Paused'], ['builtin', 'Built-in'], ['mine', 'Mine']];
const RUNNING = new Set(['queued', 'running']);

function copyText(text, what = 'Copied') {
  const done = () => toast(what, { kind: 'ok', ms: 1600 });
  const fallback = () => {
    const ta = h('textarea', { style: { position: 'fixed', opacity: '0', left: '-999px' }, 'aria-hidden': 'true' });
    ta.value = text; document.body.append(ta); ta.select();
    try { document.execCommand('copy'); done(); } catch { toast('Copy failed. Select the text and press Ctrl C.', { kind: 'error' }); }
    ta.remove();
  };
  if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(done, fallback); else fallback();
}

export function mount(body, win, props = {}) {
  const S = {
    tasks: [], last: new Map(), filter: TABS.some(([k]) => k === props.filter) ? props.filter : 'all', query: '', selected: null, showDetail: false,
    runs: new Map(), expanded: new Set(), watching: new Map(), flash: new Map(), loading: true, error: null, narrow: false,
    meta: { actions: [], events: [], targets: [], models: [], at: 0 }, editor: null, busy: new Set(),
  };
  let alive = true;
  let pollTimer = null;
  let backoff = 0;
  let lastFetch = 0;
  let onboarded = false;
  let ready;

  // ------------------------------------------------------------------------------------------------- shell
  const title = h('h1', { class: 'au-title serif' }, 'Automations', ' ', h('em', { class: 'au-count', text: '' }));
  const search = h('input', { class: 'input au-search', type: 'search', placeholder: 'Search', 'aria-label': 'Search automations', spellcheck: 'false', autocomplete: 'off',
    on: { input: () => { S.query = search.value.trim().toLowerCase(); renderList(); } } });
  const newBtn = h('button', { class: 'btn btn-ink au-new', type: 'button', 'aria-label': 'New automation', on: { click: () => openNew() } }, icon('plus', 15), h('span', { text: 'New automation' }), h('kbd', { text: 'N' }));
  const tabs = h('div', { class: 'au-tabs', role: 'tablist', 'aria-label': 'Filter automations' });
  const nextUp = h('div', { class: 'au-nextup mono', 'aria-live': 'off' });
  const list = h('div', { class: 'au-list', role: 'listbox', 'aria-label': 'Automations', tabindex: '0' });
  const detail = h('section', { class: 'au-detail', 'aria-label': 'Automation details' });
  const root = h('div', { class: 'au' },
    h('header', { class: 'au-head' }, title, h('span', { class: 'win-spacer' }), h('label', { class: 'au-search-wrap' }, icon('search', 14), search, h('kbd', { text: '/' })), newBtn),
    h('div', { class: 'au-toolbar' }, tabs, nextUp),
    h('div', { class: 'au-body' }, h('div', { class: 'au-list-wrap' }, list), detail));
  body.append(root);

  // ------------------------------------------------------------------------------------------------- data
  const byId = (id) => S.tasks.find((t) => t.id === id);

  async function refresh({ quiet = false } = {}) {
    if (!quiet) { S.loading = !S.tasks.length; if (S.loading) renderAll(); }
    const [res, recent] = await Promise.all([tasksApi.list(), tasksApi.recent(60).catch(() => null)]);
    if (!alive) return;
    S.tasks = res.tasks || [];
    S.last = new Map();
    for (const r of recent?.runs || []) if (!S.last.has(r.task_id)) S.last.set(r.task_id, r);
    S.error = null; S.loading = false; lastFetch = Date.now();
    if (S.selected && !byId(S.selected)) { S.selected = null; S.showDetail = false; }
    renderAll({ soft: true });
    if (S.selected) loadRuns(S.selected, { quiet: true });
  }

  async function loadRuns(id, { quiet = false, append = false } = {}) {
    const prev = S.runs.get(id);
    try {
      const offset = append && prev ? prev.runs.length : 0;
      const res = await tasksApi.runs(id, { limit: 20, offset });
      if (!alive) return;
      const runs = append && prev ? [...prev.runs, ...res.runs] : res.runs;
      const next = { runs, total: res.total, at: Date.now() };
      const changed = !prev || JSON.stringify(prev.runs.map((r) => [r.id, r.status, r.finished_at])) !== JSON.stringify(runs.map((r) => [r.id, r.status, r.finished_at]));
      S.runs.set(id, next);
      if (changed && S.selected === id) renderDetail();
    } catch (e) { if (!quiet) toast(e.message, { kind: 'error' }); }
  }

  async function ensureMeta() {
    if (Date.now() - S.meta.at < 60000 && S.meta.at) return;
    const [actions, events, targets, models] = await Promise.all([
      tasksApi.actions().catch(() => ({ actions: [] })), tasksApi.events().catch(() => ({ events: [] })),
      tasksApi.targets().catch(() => ({ targets: [] })), tasksApi.models().catch(() => []),
    ]);
    S.meta = { actions: actions.actions || [], events: events.events || [], targets: targets.targets || [], models: Array.isArray(models) ? models : [], at: Date.now() };
    if (S.selected) renderDetail();
  }

  function schedulePoll() {
    clearTimeout(pollTimer);
    if (!alive) return;
    const busy = S.watching.size > 0 || [...S.last.values()].some((r) => RUNNING.has(r.status));
    pollTimer = setTimeout(async () => {
      if (!document.hidden && win.state !== 'min' && !S.editor && isOnline()) {       // paused while Odysseus is unreachable
        try { await refresh({ quiet: true }); backoff = 0; } catch (e) { if (!e?.network) backoff = Math.min(backoff + 1, 3); }
      }
      schedulePoll();
    }, (busy ? POLL_BUSY_MS : POLL_MS) * 2 ** backoff);
  }

  // ----------------------------------------------------------------------------------------------- derived
  function visibleTasks() {
    const q = S.query;
    const rank = (t) => (t.status === 'active' ? ((t.trigger_type || 'schedule') === 'schedule' ? 0 : 1) : t.status === 'paused' ? 2 : 3);
    return S.tasks.filter((t) => {
      if (S.filter === 'active' && t.status !== 'active') return false;
      if (S.filter === 'paused' && t.status !== 'paused') return false;
      if (S.filter === 'builtin' && !t.is_builtin) return false;
      if (S.filter === 'mine' && t.is_builtin) return false;
      if (!q) return true;
      return `${t.name} ${t.prompt || ''} ${t.action || ''} ${describeTask(t).text} ${typeChip(t).label}`.toLowerCase().includes(q);
    }).sort((a, b) => rank(a) - rank(b) || (a.next_run ? Date.parse(a.next_run) : 9e15) - (b.next_run ? Date.parse(b.next_run) : 9e15) || a.name.localeCompare(b.name));
  }

  function runState(t) {
    if (S.watching.has(t.id)) return 'run';
    const r = S.last.get(t.id);
    if (r) {
      if (RUNNING.has(r.status)) return 'run';
      if (r.status === 'success') return 'ok';
      if (r.status === 'error') return 'fail';
      if (r.status === 'aborted') return 'warn';
      return 'skip';
    }
    return t.last_run ? 'seen' : 'never';
  }
  const STATE_TEXT = { run: 'Running now', ok: 'Last run succeeded', fail: 'Last run failed', warn: 'Last run was stopped', skip: 'Last run had nothing to do', seen: 'Has run before', never: 'Has not run yet' };

  function nextText(t) {
    if (t.status === 'paused') return { text: 'Paused' };
    if (t.status === 'completed') return { text: 'Done' };
    const trig = t.trigger_type || 'schedule';
    if (trig === 'event') return { text: `${t.trigger_counter || 0} of ${t.trigger_count || 1}` };
    if (trig === 'webhook') return { text: 'On call' };
    if (!t.next_run) return { text: 'No next run' };
    return { text: relFuture(new Date(t.next_run)), ts: Date.parse(t.next_run), fmt: 'future' };
  }

  // ----------------------------------------------------------------------------------------------- render
  function renderAll({ soft = false } = {}) { renderHeader(); renderTabs({ soft }); renderList({ soft }); renderDetail({ soft }); applyLayout(); }

  function renderHeader() {
    const total = S.tasks.length;
    const active = S.tasks.filter((t) => t.status === 'active').length;
    const paused = S.tasks.filter((t) => t.status === 'paused').length;
    title.querySelector('.au-count').textContent = total ? `${active} active${paused ? `, ${paused} paused` : ''}` : '';
  }

  function renderTabs({ soft = false } = {}) {
    const soon0 = S.tasks.filter((t) => t.status === 'active' && t.next_run && (t.trigger_type || 'schedule') === 'schedule').sort((a, b) => Date.parse(a.next_run) - Date.parse(b.next_run))[0];
    const sig = JSON.stringify([S.filter, S.tasks.map((t) => [t.status, t.is_builtin]), soon0 && [soon0.id, soon0.name, soon0.next_run]]);
    if (soft && sig === S.tabsSig) return;
    S.tabsSig = sig;
    clear(tabs);
    const count = (k) => S.tasks.filter((t) => (k === 'all' ? true : k === 'active' ? t.status === 'active' : k === 'paused' ? t.status === 'paused' : k === 'builtin' ? t.is_builtin : !t.is_builtin)).length;
    for (const [k, label] of TABS) {
      tabs.append(h('button', { class: ['au-tab', S.filter === k && 'on'], type: 'button', role: 'tab', 'aria-selected': S.filter === k ? 'true' : 'false', dataset: { filter: k },
        on: { click: () => { S.filter = k; renderTabs(); renderList(); } } }, label, h('span', { class: 'au-tab-n mono', text: count(k) })));
    }
    const soon = S.tasks.filter((t) => t.status === 'active' && t.next_run && (t.trigger_type || 'schedule') === 'schedule').sort((a, b) => Date.parse(a.next_run) - Date.parse(b.next_run))[0];
    clear(nextUp);
    if (soon) nextUp.append('NEXT UP · ', h('span', { class: 'au-nextup-name', text: soon.name }), ' · ', h('span', { dataset: { ts: Date.parse(soon.next_run), fmt: 'future' }, text: relFuture(new Date(soon.next_run)) }));
  }

  function rowEl(t) {
    const chip = typeChip(t);
    const sched = describeTask(t);
    const state = runState(t);
    const nx = nextText(t);
    const sw = h('input', { type: 'checkbox', role: 'switch', checked: t.status === 'active', disabled: t.status === 'completed' || S.busy.has(t.id), 'aria-label': `${t.status === 'active' ? 'Pause' : 'Resume'} ${t.name}`,
      on: { click: (e) => e.stopPropagation(), change: () => toggle(t, sw.checked, sw) } });
    return h('div', { class: ['au-row', S.selected === t.id && 'selected', t.status !== 'active' && 'dim'], role: 'option', 'aria-selected': S.selected === t.id ? 'true' : 'false', tabindex: '-1', dataset: { id: t.id },
      on: { click: () => select(t.id), dblclick: () => select(t.id, { focusDetail: true }) } },
      h('span', { class: ['au-dot', `st-${state}`], title: STATE_TEXT[state] }),
      h('div', { class: 'au-row-main' },
        h('div', { class: 'au-row-name', text: t.name }),
        h('div', { class: 'au-row-sub' }, h('span', { class: ['au-chip', `k-${chip.tone}`], text: chip.label }), h('span', { class: 'au-row-sched', text: sched.text, title: sched.text }))),
      h('div', { class: 'au-row-side' },
        h('label', { class: 'switch au-switch', title: t.status === 'completed' ? 'Finished' : t.status === 'active' ? 'On. Click to pause' : 'Paused. Click to resume' }, sw, h('span', { class: 'switch-track' }, h('span', { class: 'switch-thumb' }))),
        h('span', { class: 'au-row-next mono', dataset: nx.ts ? { ts: nx.ts, fmt: nx.fmt } : {}, text: nx.text })));
  }

  function renderList({ soft = false } = {}) {
    const sig = JSON.stringify([S.filter, S.query, S.selected, S.loading, S.error, [...S.watching.keys()], visibleTasks().map((t) => [t.id, t.name, t.status, t.next_run, t.last_run, t.trigger_counter, runState(t), describeTask(t).text])]);
    if (soft && sig === S.listSig) return;
    S.listSig = sig;
    const keep = list.scrollTop;
    const hadFocus = list.contains(document.activeElement) || document.activeElement === list;
    clear(list);
    if (hadFocus) list.focus({ preventScroll: true });
    if (S.loading) { for (let i = 0; i < 6; i++) list.append(h('div', { class: 'au-skel' }, h('i'), h('div', {}, h('b'), h('s')))); return; }
    if (S.error) { list.append(h('div', { class: 'au-empty small' }, icon('alert', 22), h('p', { text: S.error }), h('button', { class: 'btn btn-soft btn-sm', text: 'Try again', on: { click: () => load() } }))); return; }
    const rows = visibleTasks();
    if (!S.tasks.length) { list.append(h('div', { class: 'au-empty small' }, icon('zap', 22), h('p', { class: 'muted', text: 'No automations yet.' }))); return; }
    if (!rows.length) {
      const why = S.query ? `Nothing matches “${search.value.trim()}”.` : S.filter === 'builtin' ? 'No built-in automations on this install. They appear once Odysseus’ housekeeping is turned on.' : `No ${S.filter === 'all' ? '' : `${S.filter} `}automations.`;
      list.append(h('div', { class: 'au-empty small' }, icon('search', 22), h('p', { class: 'muted', text: why }),
        (S.query || S.filter !== 'all') && h('button', { class: 'btn btn-soft btn-sm', text: 'Clear filters', on: { click: () => { S.query = ''; search.value = ''; S.filter = 'all'; renderTabs(); renderList(); } } })));
      return;
    }
    for (const t of rows) list.append(rowEl(t));
    list.scrollTop = keep;
  }

  // ----------------------------------------------------------------------------------------------- detail
  const fact = (label, ...value) => h('div', { class: 'au-fact' }, h('dt', { class: 'mono', text: label }), h('dd', {}, ...value));

  function renderEmptyDetail() {
    clear(detail);
    if (S.loading) { detail.append(h('div', { class: 'au-skel-detail' }, h('b'), h('s'), h('s'))); return; }
    if (!S.tasks.length && !S.error) {
      detail.append(h('div', { class: 'au-welcome' },
        h('p', { class: 'eyebrow mono', text: 'GETTING STARTED' }),
        h('h2', { class: 'serif au-welcome-title' }, 'Put the routine on ', h('em', { text: 'autopilot.' })),
        h('p', { class: 'au-welcome-sub', text: 'An automation does something for you on a schedule, when something happens, or when you call it: a morning brief, an inbox sweep, a nightly backup, a weekly review.' }),
        h('div', { class: 'au-welcome-actions' },
          h('button', { class: 'btn btn-ink btn-lg', type: 'button', text: 'Create your first automation', on: { click: () => openNew() } }),
          h('button', { class: 'btn btn-soft btn-lg', type: 'button', text: 'Morning brief', on: { click: () => openNew({ template: 'morning-brief' }) } })),
        h('ul', { class: 'au-tips' },
          h('li', {}, h('kbd', { text: 'N' }), ' new  ', h('kbd', { text: '/' }), ' search  ', h('kbd', { text: 'Del' }), ' delete  ', h('kbd', { text: '↑ ↓' }), ' move'),
          h('li', { text: `Times are in your time zone (${tzLabel()}). Odysseus stores them in UTC and converts for you.` }),
          h('li', { text: 'Anything that can run in the background (email triage, tidying, AI prompts, shell commands) can be scheduled here.' }))));
      return;
    }
    detail.append(h('div', { class: 'au-pick' }, icon('zap', 26), h('h2', { class: 'serif', text: 'Select an automation' }), h('p', { class: 'muted', text: 'Pick one from the list to see what it does, when it runs next, and how its last runs went.' })));
  }

  function renderDetail({ soft = false } = {}) {
    const t = byId(S.selected);
    const hist0 = t && S.runs.get(t.id);
    const sig = JSON.stringify([S.selected, t, t && S.last.get(t.id)?.status, t && S.watching.get(t.id)?.state, t && S.watching.get(t.id)?.note, t && S.flash.get(t.id), S.meta.at, S.loading, S.tasks.length, hist0 && [hist0.total, hist0.runs.map((r) => [r.id, r.status, r.finished_at])], t?.then_task_id && byId(t.then_task_id)?.name]);
    if (soft && sig === S.detailSig) return;
    S.detailSig = sig;
    if (!t) { renderEmptyDetail(); return; }
    const keep = detail.scrollTop;
    const focusedAct = detail.contains(document.activeElement) ? document.activeElement.dataset?.act : null;
    const openIds = new Set([...detail.querySelectorAll('details.au-run[open]')].map((x) => x.dataset.run));
    for (const id of openIds) S.expanded.add(id);
    clear(detail);
    const chip = typeChip(t);
    const kind = kindOfTask(t);
    const sched = describeTask(t);
    const watch = S.watching.get(t.id);
    const ext = S.last.get(t.id);
    const running = !!watch || (ext && RUNNING.has(ext.status));
    const trig = t.trigger_type || 'schedule';
    const flash = S.flash.get(t.id);
    const statusLabel = t.status === 'active' ? 'Active' : t.status === 'paused' ? 'Paused' : 'Done';

    const actions = h('div', { class: 'au-actions' },
      running
        ? h('button', { class: 'btn btn-soft', type: 'button', dataset: { act: 'stop' }, on: { click: () => stop(t) } }, icon('stop', 14), 'Stop')
        : h('button', { class: 'btn btn-ink', type: 'button', dataset: { act: 'run' }, disabled: t.status !== 'active', title: t.status !== 'active' ? 'Resume it to run it' : 'Run it right now', on: { click: () => runNow(t) } }, icon('play', 14), 'Run now'),
      h('button', { class: 'btn btn-soft', type: 'button', dataset: { act: 'edit' }, on: { click: () => openEdit(t) } }, icon('edit', 14), 'Edit'),
      h('button', { class: 'btn btn-soft', type: 'button', dataset: { act: 'duplicate' }, on: { click: () => duplicate(t) } }, icon('copy', 14), 'Duplicate'),
      t.is_builtin && t.is_modified && h('button', { class: 'btn btn-soft', type: 'button', dataset: { act: 'revert' }, on: { click: () => revert(t) } }, icon('refresh', 14), 'Reset to default'),
      h('button', { class: 'btn btn-soft danger', type: 'button', dataset: { act: 'delete' }, on: { click: () => remove(t) } }, icon('trash', 14), 'Delete'));

    const banner = running
      ? h('div', { class: 'au-banner running', role: 'status' }, h('span', { class: 'au-spin' }),
        h('div', { class: 'au-banner-text' }, h('strong', { text: (watch?.state || ext?.status) === 'queued' ? 'Waiting to start…' : 'Running…' }),
          h('span', { class: 'muted', text: ((watch?.note || ext?.result || '') + '').slice(0, 140) || 'Hang on, this updates by itself.' })),
        h('span', { class: 'mono au-elapsed', dataset: { ts: watch ? watch.start : Date.parse(ext.started_at), fmt: 'elapsed' }, text: '' }))
      : flash && h('div', { class: ['au-banner', flash.status === 'success' ? 'ok' : flash.status === 'error' ? 'fail' : 'neutral'], role: 'status' },
        icon(flash.status === 'success' ? 'check' : 'alert', 16),
        h('div', { class: 'au-banner-text' }, h('strong', { text: flash.status === 'success' ? 'Finished' : flash.status === 'error' ? 'Failed' : flash.status === 'skipped' ? 'Nothing to do' : `Run ${flash.status}` }), h('span', { class: 'au-banner-out', text: flash.summary || 'No output.' })),
        h('button', { class: 'icon-btn', 'aria-label': 'Dismiss', on: { click: () => { S.flash.delete(t.id); renderDetail(); } } }, icon('x', 14)));

    // what it does ------------------------------------------------------------------------------------
    let doesLine = ''; let does;
    if (kind === 'command') { doesLine = 'Runs a shell command on this computer.'; does = h('pre', { class: 'au-code mono', text: t.prompt || '' }); }
    else if (kind === 'action') { doesLine = actionBlurb(t.action, S.meta.actions) || actionTitle(t.action); does = h('div', {}, h('strong', { text: actionTitle(t.action) }), h('div', { class: 'muted', text: actionBlurb(t.action, S.meta.actions) })); }
    else { doesLine = `${kind === 'research' ? 'Researches' : 'Asks the AI'}: ${(t.prompt || '').replace(/\s+/g, ' ').slice(0, 110)}${(t.prompt || '').length > 110 ? '…' : ''}`; does = h('div', { class: 'au-prompt', text: t.prompt || '' }); }

    const nx = nextText(t);
    const nextRun = t.status === 'active' && t.next_run && trig === 'schedule' ? new Date(t.next_run) : null;
    const cronUtc = t.schedule === 'cron' && sched.raw;
    const upcoming = nextRun ? nextRuns(t, 3).slice(1, 3) : [];
    const chain = t.then_task_id ? byId(t.then_task_id) : null;
    const lastRun = t.last_run ? new Date(t.last_run) : null;

    const facts = h('dl', { class: 'au-facts' },
      fact('WHEN', h('span', { class: 'au-fact-main', text: sched.text }), cronUtc && h('div', { class: 'au-hint', text: 'This cron expression is read in UTC.' }),
        trig === 'event' && h('div', { class: 'au-hint', text: `${t.trigger_counter || 0} of ${t.trigger_count || 1} so far` })),
      trig === 'schedule' && fact('NEXT RUN', nextRun
        ? [h('span', { class: 'au-fact-main', text: fmtWhen(nextRun) }), ' ', h('span', { class: 'muted mono', dataset: { ts: nextRun.getTime(), fmt: 'future' }, text: relFuture(nextRun) }),
          upcoming.length > 0 && h('div', { class: 'au-hint', text: `Then ${upcoming.map(fmtWhen).join(' · ')}` })]
        : h('span', { class: 'muted', text: t.status === 'paused' ? 'Paused. Switch it on to schedule the next run.' : t.status === 'completed' ? 'This one-off has run.' : 'Nothing scheduled.' })),
      fact('LAST RUN', lastRun ? [h('span', { class: 'au-fact-main', text: fmtWhen(lastRun) }), ' ', h('span', { class: 'muted mono', dataset: { ts: lastRun.getTime(), fmt: 'past' }, text: relPast(lastRun) }),
        ' ', h('span', { class: ['au-dot', `st-${runState(t)}`, 'inline'], title: STATE_TEXT[runState(t)] })] : h('span', { class: 'muted', text: 'Never' })),
      fact(kind === 'command' ? 'COMMAND' : kind === 'action' ? 'ACTION' : kind === 'research' ? 'RESEARCH' : 'INSTRUCTION', does,
        kind === 'command' && h('button', { class: 'btn btn-ghost btn-sm au-copy', type: 'button', on: { click: () => copyText(t.prompt || '', 'Command copied') } }, icon('copy', 13), 'Copy')),
      fact('RESULT GOES TO', h('span', { text: outputLabel(t.output_target, S.meta.targets) })),
      (kind === 'llm' || kind === 'research') && fact('MODEL', h('span', { text: t.model || 'Default model', class: t.model ? 'mono' : 'muted' })),
      chain && fact('THEN', 'Runs ', h('button', { class: 'au-link', type: 'button', text: chain.name, on: { click: () => select(chain.id) } }), ' after it succeeds'),
      t.then_task_id && !chain && fact('THEN', h('span', { class: 'muted', text: 'Runs another automation that no longer exists.' })),
      fact('RUNS', h('span', { text: `${t.run_count || 0} so far` }), t.created_at && h('span', { class: 'muted', text: ` · created ${fmtWhen(new Date(t.created_at))}` })));

    // webhook ------------------------------------------------------------------------------------------
    let hook = null;
    if (trig === 'webhook') {
      const url = t.webhook_token ? `${location.origin}/api/tasks/${t.id}/webhook/${t.webhook_token}` : '';
      hook = h('section', { class: 'au-hook' },
        h('div', { class: 'au-eyebrow mono', text: 'WEBHOOK' }),
        url ? h('div', { class: 'au-hook-url' }, h('input', { class: 'input mono', readOnly: true, value: url, 'aria-label': 'Webhook URL', on: { focus: (e) => e.target.select() } }),
          h('button', { class: 'btn btn-soft btn-sm', type: 'button', dataset: { act: 'copy-hook' }, on: { click: () => copyText(url, 'Webhook URL copied') } }, icon('copy', 13), 'Copy'),
          h('button', { class: 'btn btn-soft btn-sm', type: 'button', dataset: { act: 'regen-hook' }, on: { click: () => regenerate(t) } }, icon('refresh', 13), 'Regenerate'))
          : h('p', { class: 'muted', text: 'No webhook token yet. Save the automation again to create one.' }),
        url && h('div', { class: 'au-hint' }, 'Send an HTTP POST to this URL to run it now. Anyone with the URL can do that, so treat it like a password. ', h('button', { class: 'au-link', type: 'button', text: 'Copy a curl command', on: { click: () => copyText(`curl -X POST "${url}"`, 'curl command copied') } })),
        t.status !== 'active' && h('div', { class: 'au-hint warn', text: 'The webhook only works while the automation is active.' }));
    }

    // history ------------------------------------------------------------------------------------------
    const hist = S.runs.get(t.id);
    const history = h('section', { class: 'au-history' },
      h('div', { class: 'au-history-head' }, h('div', { class: 'au-eyebrow mono', text: 'RUN HISTORY' }), hist && h('span', { class: 'muted mono', text: `${hist.total} run${hist.total === 1 ? '' : 's'}` })),
      !hist ? h('div', { class: 'au-skel-detail' }, h('s'), h('s'))
        : !hist.runs.length ? h('div', { class: 'au-hist-empty muted', text: 'It has not run yet. Use Run now to try it.' })
          : h('div', { class: 'au-runs' }, hist.runs.map((r) => runEl(r))),
      hist && hist.runs.length < hist.total && h('button', { class: 'btn btn-ghost btn-sm', type: 'button', text: `Show older runs (${hist.total - hist.runs.length})`, on: { click: () => loadRuns(t.id, { append: true }) } }));

    detail.append(...[
      h('div', { class: 'au-d-top' },
        h('button', { class: 'icon-btn au-back', type: 'button', 'aria-label': 'Back to the list', title: 'Back', on: { click: () => { S.showDetail = false; applyLayout(); list.focus(); } } }, icon('chevron-left', 18)),
        h('span', { class: ['au-chip', `k-${chip.tone}`], text: chip.label }),
        h('span', { class: ['au-status', `s-${t.status}`], text: statusLabel }),
        t.is_builtin && h('span', { class: 'badge', text: t.is_modified ? 'Built-in · modified' : 'Built-in' })),
      h('h2', { class: 'au-d-title serif', text: t.name }),
      h('p', { class: 'au-d-desc', text: doesLine }),
      actions, banner || null, facts, hook, history].filter(Boolean));
    detail.scrollTop = keep;
    if (focusedAct) detail.querySelector(`[data-act="${focusedAct}"]`)?.focus({ preventScroll: true });
    tick();
  }

  function runEl(r) {
    const started = r.started_at ? new Date(r.started_at) : null;
    const fin = r.finished_at ? new Date(r.finished_at) : null;
    const text = runText(r).trim();
    const st = r.status === 'success' ? 'ok' : r.status === 'error' ? 'fail' : RUNNING.has(r.status) ? 'run' : r.status === 'aborted' ? 'warn' : 'skip';
    const label = { success: 'Succeeded', error: 'Failed', running: 'Running', queued: 'Queued', skipped: 'Skipped', aborted: 'Stopped' }[r.status] || r.status;
    const el = h('details', { class: ['au-run', `st-${st}`], dataset: { run: r.id } },
      h('summary', {},
        h('span', { class: ['au-dot', `st-${st}`] }),
        h('span', { class: 'au-run-status', text: label }),
        h('span', { class: 'au-run-when', title: started ? started.toLocaleString() : '' }, started ? fmtWhen(started) : '', ' ', started && h('span', { class: 'muted mono', dataset: { ts: started.getTime(), fmt: 'past' }, text: relPast(started) })),
        h('span', { class: 'au-run-dur mono muted', text: started && fin ? fmtDuration(fin - started) : '' }),
        h('span', { class: 'au-run-peek muted', text: text.replace(/\s+/g, ' ').slice(0, 90) }),
        h('span', { class: 'au-run-caret' }, icon('chevron-down', 14))),
      h('div', { class: 'au-run-body' },
        h('pre', { class: 'au-out mono', text: text || '(no output)' }),
        h('div', { class: 'au-run-foot' }, r.model && h('span', { class: 'muted mono', text: r.model }), h('span', { class: 'win-spacer' }),
          h('button', { class: 'btn btn-ghost btn-sm', type: 'button', on: { click: () => copyText(text, 'Output copied') } }, icon('copy', 13), 'Copy output'))));
    if (S.expanded.has(r.id)) el.open = true;
    return el;
  }

  // ------------------------------------------------------------------------------------------------ layout
  function applyLayout() {
    const narrow = body.clientWidth > 0 && body.clientWidth < 760;
    S.narrow = narrow;
    root.classList.toggle('narrow', narrow);
    root.classList.toggle('show-detail', narrow && S.showDetail && !!S.selected);
  }

  // ------------------------------------------------------------------------------------------------ actions
  function select(id, { focusDetail = false } = {}) {
    S.selected = id; S.showDetail = true;
    for (const el of list.querySelectorAll('.au-row')) { const on = el.dataset.id === id; el.classList.toggle('selected', on); el.setAttribute('aria-selected', on ? 'true' : 'false'); if (on) el.scrollIntoView({ block: 'nearest' }); }
    renderDetail(); applyLayout();
    loadRuns(id);
    ensureMeta().catch(() => {});
    if (focusDetail) detail.querySelector('[data-act="run"], [data-act="stop"], [data-act="edit"]')?.focus();
  }

  async function toggle(t, on, input) {
    S.busy.add(t.id); input.disabled = true;
    try {
      if (on) await tasksApi.resume(t.id); else await tasksApi.pause(t.id);
      toast(on ? `“${t.name}” is on` : `“${t.name}” is paused`, { kind: 'ok', ms: 1600 });
    } catch (e) { toast(e.message, { kind: 'error' }); }
    S.busy.delete(t.id);
    try { await refresh({ quiet: true }); } catch { /* next poll retries */ }
  }

  async function runNow(t) {
    if (S.watching.has(t.id)) return;
    if (!S.runs.get(t.id)) await loadRuns(t.id, { quiet: true });
    const known = new Set((S.runs.get(t.id)?.runs || []).map((r) => r.id));
    S.flash.delete(t.id);
    try { await tasksApi.run(t.id); }
    catch (e) {
      if (e instanceof ApiError && e.status === 409) toast('It is already running.', { ms: 2200 });
      else { toast(e.message, { kind: 'error' }); return; }
    }
    const w = { id: t.id, start: Date.now(), known, state: 'queued', note: '', timer: null, runId: null };
    S.watching.set(t.id, w);
    renderList(); if (S.selected === t.id) renderDetail();
    const step = async () => {
      if (!alive || S.watching.get(t.id) !== w) return;
      if (!isOnline()) { w.timer = setTimeout(step, WATCH_MS); return; }          // Odysseus unreachable: keep watching, ask again once it is back
      try {
        const res = await tasksApi.runs(t.id, { limit: 3 });
        const run = res.runs.find((r) => !known.has(r.id));
        if (run) {
          w.runId = run.id; w.state = run.status; w.note = RUNNING.has(run.status) ? (run.result || '') : '';
          if (!RUNNING.has(run.status)) { finish(t, w, run); return; }
          if (S.selected === t.id) renderDetail();
        } else if (Date.now() - w.start > 40000) {
          S.watching.delete(t.id); toast('The scheduler did not report a run. Check the run history in a moment.', { kind: 'error' }); renderList(); renderDetail(); return;
        }
      } catch { /* transient: keep waiting */ }
      w.timer = setTimeout(step, WATCH_MS);
    };
    w.timer = setTimeout(step, WATCH_MS);
  }

  async function finish(t, w, run) {
    S.watching.delete(t.id);
    const text = (run.result || run.error || '').trim();
    S.flash.set(t.id, { status: run.status, summary: text.replace(/\s+/g, ' ').slice(0, 280), runId: run.id });
    S.expanded.add(run.id);
    toast(`“${t.name}” ${run.status === 'success' ? 'finished' : run.status === 'error' ? 'failed' : run.status === 'skipped' ? 'had nothing to do' : run.status}`, { kind: run.status === 'error' ? 'error' : 'ok', ms: 2600 });
    try { await refresh({ quiet: true }); } catch { /* ignore */ }
    await loadRuns(t.id, { quiet: true });
    if (S.selected === t.id) renderDetail();
  }

  async function stop(t) {
    try { await tasksApi.stop(t.id); toast('Stopped.', { ms: 1600 }); }
    catch (e) { toast(e.message, { kind: 'error' }); }
    const w = S.watching.get(t.id); if (w) { clearTimeout(w.timer); S.watching.delete(t.id); }
    try { await refresh({ quiet: true }); await loadRuns(t.id, { quiet: true }); } catch { /* ignore */ }
    renderDetail();
  }

  async function remove(t) {
    const ok = await dialog.confirm(`Delete “${t.name}”?`,
      t.is_builtin ? 'This is a built-in automation. Its run history is removed, and Odysseus puts built-ins back the next time a signed-in user opens the list. To switch it off for good, pause it instead.' : 'The automation and its run history will be removed. This cannot be undone.',
      { confirmLabel: 'Delete', danger: true });
    if (!ok) return;
    const order = visibleTasks().map((x) => x.id);
    const i = order.indexOf(t.id);
    try { await tasksApi.remove(t.id); } catch (e) { toast(e.message, { kind: 'error' }); return; }
    S.runs.delete(t.id); S.flash.delete(t.id);
    const next = order[i + 1] || order[i - 1];
    S.selected = null; S.showDetail = false;
    try { await refresh({ quiet: true }); } catch { /* ignore */ }
    if (next && byId(next) && !S.narrow) select(next); else { renderDetail(); applyLayout(); }
    toast(`Deleted “${t.name}”`, { kind: 'ok', ms: 2200 });
    list.focus();
  }

  async function revert(t) {
    const ok = await dialog.confirm(`Reset “${t.name}”?`, 'Its name, schedule and prompt return to the built-in defaults.', { confirmLabel: 'Reset' });
    if (!ok) return;
    try { await tasksApi.revert(t.id); toast('Reset to default', { kind: 'ok', ms: 1800 }); await refresh({ quiet: true }); } catch (e) { toast(e.message, { kind: 'error' }); }
  }

  async function regenerate(t) {
    const ok = await dialog.confirm('Regenerate the webhook URL?', 'The current URL stops working immediately. Anything that calls it will need the new one.', { confirmLabel: 'Regenerate', danger: true });
    if (!ok) return;
    try { await tasksApi.regenerateWebhook(t.id); toast('New webhook URL created', { kind: 'ok', ms: 2000 }); await refresh({ quiet: true }); } catch (e) { toast(e.message, { kind: 'error' }); }
  }

  // ---------------------------------------------------------------------------------------------- editor
  const env = () => ({
    shells: os.boot?.shells || [], isWindows: /windows/i.test(os.boot?.system?.os || ''),
    canCommand: S.meta.actions.some((a) => COMMAND_ACTIONS.has(a.name)),   // /meta/actions only lists these for administrators (it omits run_local itself)
  });

  async function openSheet(o) {
    S.editor?.close();
    await ensureMeta();
    S.editor = openEditor(root, {
      ...o, env: env(), meta: S.meta, tasks: S.tasks,
      onClose: () => { S.editor = null; },
      onSaved: async (saved, { created, companion, activated }) => {
        S.editor = null;
        try { await refresh({ quiet: true }); } catch { /* ignore */ }
        S.query = ''; search.value = ''; if (S.filter !== 'all' && byId(saved.id) && visibleTasks().every((x) => x.id !== saved.id)) S.filter = 'all';
        renderTabs(); select(saved.id);
        toast(`${created ? 'Created' : activated ? 'Turned on' : 'Saved'} “${saved.name}”${companion ? ` and “${companion.name}”` : ''}`, { kind: 'ok' });
        list.querySelector(`.au-row[data-id="${saved.id}"]`)?.scrollIntoView({ block: 'nearest' });
      },
    });
  }

  function draftFromPrefill(pf = {}) {
    const d = blankDraft();
    d.name = pf.name || '';
    const action = pf.action || '';
    if (action) { d.kind = COMMAND_ACTIONS.has(action) ? 'command' : 'action'; d.action = d.kind === 'command' ? '' : action; if (d.kind === 'command') d.command = pf.command || pf.script || pf.prompt || ''; }
    else if (pf.command) { d.kind = 'command'; d.command = pf.command; }
    else { d.kind = pf.task_type === 'research' || pf.kind === 'research' ? 'research' : 'llm'; d.prompt = pf.prompt || ''; }
    if (pf.trigger_type === 'event' || pf.trigger === 'event') { d.trigger = 'event'; d.event = pf.trigger_event || pf.event || 'email_received'; d.count = pf.trigger_count || pf.count || 5; }
    else if (pf.trigger_type === 'webhook' || pf.trigger === 'webhook') d.trigger = 'webhook';
    let note = null;
    if (pf.sched && pf.sched.mode) d.sched = pf.sched;
    else if (typeof pf.schedule === 'string' && pf.schedule.trim()) {
      const r = parseNaturalSchedule(pf.schedule);
      if (r.ok) d.sched = r.sched; else note = `I could not read the schedule “${pf.schedule}”. Pick it below.`;
    } else if (pf.cron || pf.cron_expression) {
      const expr = pf.cron || pf.cron_expression;
      d.sched = cronToStructured(expr) || { mode: 'cron', cron: expr };
      if (d.sched.times) delete d.sched.times;
    }
    const out = pf.output_target || pf.output;
    if (out) d.output = out.startsWith('email') && out !== 'email' ? 'email' : out;
    if (d.kind === 'command' && d.output === 'session') d.output = 'none';
    return { d, note };
  }

  async function openNew(pf) {
    if (pf?.template) {
      const t = TEMPLATES.find((x) => x.id === pf.template);
      await ensureMeta();
      if (t) { openSheet({ draft: t.build(env()), template: t }); return; }
    }
    if (pf && Object.keys(pf).length) {
      const { d, note } = draftFromPrefill(pf);
      await openSheet({ draft: d });
      if (note) toast(note, { ms: 5000 });
      return;
    }
    openSheet({});
  }

  async function openEdit(t) {
    openSheet({ existing: t, draft: draftFromTask(t, (x) => scheduleFromTask(x)) });
  }

  async function duplicate(t) {
    const d = draftFromTask(t, (x) => scheduleFromTask(x));
    d.name = `${t.name} (copy)`;
    if (d.trigger === 'schedule' && d.sched.mode === 'once') d.sched = { mode: 'daily', time: d.sched.time || '09:00' };
    d.then = '';
    await openSheet({ draft: d });
    toast('Review the copy, then create it.', { ms: 2200 });
  }

  // ----------------------------------------------------------------------------------------- live clock
  function tick() {
    const now = Date.now();
    for (const el of root.querySelectorAll('[data-ts]')) {
      const ts = Number(el.dataset.ts);
      const f = el.dataset.fmt;
      const next = f === 'future' ? relFuture(new Date(ts), now) : f === 'past' ? relPast(new Date(ts), now) : fmtDuration(now - ts);
      if (el.textContent !== next) el.textContent = next;
    }
  }
  const tickTimer = setInterval(() => { if (!document.hidden && win.state !== 'min') tick(); }, 1000);

  // -------------------------------------------------------------------------------------------- keyboard
  body.addEventListener('keydown', (e) => {
    if (S.editor || e.ctrlKey || e.metaKey || e.altKey) return;
    const typing = e.target.closest?.('input, textarea, select, [contenteditable], .au-run summary');
    if (e.key === 'Escape' && e.target === search) { search.value = ''; S.query = ''; renderList(); list.focus(); return; }
    if (e.key === '/' && !typing) { e.preventDefault(); search.focus(); search.select(); return; }
    if (typing && !(e.target.closest?.('.au-run summary') && (e.key === 'Delete'))) return;
    const k = e.key;
    if (k.toLowerCase() === 'n') { e.preventDefault(); openNew(); }
    else if (k === 'Delete') { const t = byId(S.selected); if (t) { e.preventDefault(); remove(t); } }
    else if (k === 'ArrowDown' || k === 'ArrowUp') {
      if (!e.target.closest?.('.au-list')) return;
      e.preventDefault();
      const ids = visibleTasks().map((x) => x.id);
      if (!ids.length) return;
      const i = ids.indexOf(S.selected);
      select(ids[Math.max(0, Math.min(ids.length - 1, i < 0 ? 0 : i + (k === 'ArrowDown' ? 1 : -1)))]);
    } else if (k === 'Enter' && e.target.closest?.('.au-list')) {
      e.preventDefault();
      const ids = visibleTasks().map((x) => x.id);
      select(S.selected && ids.includes(S.selected) ? S.selected : ids[0], { focusDetail: true });
    }
  });

  // ---------------------------------------------------------------------------------------------- start
  async function load() {
    S.error = null; S.loading = !S.tasks.length; renderAll();
    try {
      if (!onboarded) {
        onboarded = true;
        try { if (!(await tasksApi.onboarding()).opened) await tasksApi.markOpened(); } catch (e) { if (e?.network) onboarded = false; /* else optional; the list still loads */ }
      }
      await refresh();
    } catch (e) {
      // Unreachable server: the connection banner says so. Keep the skeleton (or the list we have); the reconnect reloads.
      if (e?.network) { renderAll(); return; }
      S.loading = false; S.error = e.message || 'Could not load automations.'; renderAll();
    }
  }
  const offReconnect = os.on('reconnected', () => { if (S.loading || S.error) load(); else refresh({ quiet: true }).catch(() => {}); });
  const onVis = () => { if (!document.hidden && Date.now() - lastFetch > 5000) refresh({ quiet: true }).catch(() => {}); };
  document.addEventListener('visibilitychange', onVis);

  function applyProps(p = {}) {
    if (TABS.some(([k]) => k === p.filter)) { S.filter = p.filter; renderTabs(); renderList(); }
    if (p.intent === 'show' && p.id) {
      ready.then(() => { if (byId(p.id)) select(p.id); else toast('That automation no longer exists.', { kind: 'error' }); });
    } else if (p.intent === 'new') ready.then(() => openNew(p.prefill));
  }

  renderAll();
  ready = load();
  schedulePoll();
  ensureMeta().catch(() => {});
  applyProps(props);

  return {
    focus: () => list.focus(),
    serialize: () => (S.selected ? { intent: 'show', id: S.selected, filter: S.filter } : { filter: S.filter }),
    onReuse: (p) => applyProps(p),
    onShow: () => { refresh({ quiet: true }).catch(() => {}); tick(); },
    onResize: () => applyLayout(),
    destroy: () => {
      alive = false; clearTimeout(pollTimer); clearInterval(tickTimer); document.removeEventListener('visibilitychange', onVis); offReconnect();
      for (const w of S.watching.values()) clearTimeout(w.timer);
      S.editor?.close?.();
    },
  };
}
