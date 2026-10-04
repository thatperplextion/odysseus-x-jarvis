// Settings > AI models: which model Odysseus uses, a benchmark of the free ones, one-click "make default".
//
// Backed by /api/os/models/* (routes/os_models_routes.py). The benchmark runs on the server and keeps going if
// this window closes; its live state lives at module level so switching Settings sections (or reopening the
// window) re-attaches instead of starting over.

import { h, icon, clear, toast, fmtDate } from '../dom.js';
import { get, post, streamEvents } from '../api.js';
import { os } from '../ctx.js';

const TIER = {
  local: { label: 'Local', hint: 'Runs on this computer: free, private, works offline' },
  free: { label: 'Free tier', hint: 'Cloud provider free tier, subject to its limits' },
  paid: { label: 'Paid', hint: 'Billed per token' },
  unknown: { label: 'Unknown cost', hint: 'Could not tell whether this is free' },
};
const STATUS = {
  partial: ['some calls failed', 'warn'],
  rate_limited: ['rate limited', 'warn'],
  too_slow: ['too slow', 'warn'],
  unavailable: ['not available', 'bad'],
  failed: ['failed', 'bad'],
};

// ------------------------------------------------------------------ shared state
const lab = {
  loaded: false, error: null,
  current: null,            // GET /models/current
  last: null,               // saved results (GET /models/bench/latest -> results)
  running: false, ctrl: null, startedAt: 0, tasks: [], rows: new Map(), done: 0, total: 0, runError: null,
  busy: false,              // a selection change is being saved
  focusBench: false,        // scroll the benchmark into view once, right after the user starts a run
  listeners: new Set(),
};
const notify = () => lab.listeners.forEach((fn) => fn());

const modelName = (m) => String(m || '').replace(/^models\//, '');
const refOf = (r) => ({ endpoint_id: r.endpoint_id, model: r.model });
const sameRef = (a, b) => !!a && !!b && a.endpoint_id === b.endpoint_id && a.model === b.model;
const fmtMs = (ms) => (ms === null || ms === undefined ? '' : ms >= 1000 ? `${(ms / 1000).toFixed(1)} s` : `${ms} ms`);
const fmtElapsed = (ms) => { const s = Math.max(0, Math.round(ms / 1000)); return s >= 60 ? `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s` : `${s}s`; };

async function loadAll() {
  try {
    const [current, latest] = await Promise.all([get('/models/current'), get('/models/bench/latest')]);
    lab.current = current; lab.last = latest.results; lab.error = null; lab.loaded = true;
    if (latest.running && !lab.running) startBench({});
  } catch (e) {
    if (!e?.network) { lab.error = e.message; lab.loaded = true; }      // an unreachable server is the connection banner's business; the reconnect reloads
  }
  notify();
}
// Odysseus was unreachable and is back: re-read the live selection, and re-attach to a benchmark that kept running.
os.on('reconnected', () => { if (lab.loaded || lab.listeners.size) loadAll(); });

async function refreshCurrent() {
  try { lab.current = await get('/models/current'); } catch { /* keep what we have */ }
  notify();
}

function startBench(body = {}, userStarted = false) {
  if (lab.running) return;
  lab.focusBench = userStarted;
  lab.running = true; lab.runError = null; lab.rows = new Map(); lab.done = 0; lab.total = 0; lab.startedAt = Date.now();
  lab.ctrl = new AbortController();
  notify();
  let finished = false;
  streamEvents('/models/bench', body, (ev) => {
    if (ev.type === 'start') {
      lab.tasks = ev.tasks; lab.total = ev.models.length; lab.startedAt = Date.parse(ev.started_at) || lab.startedAt;
      for (const m of ev.models) lab.rows.set(m.key, { ...m, status: 'queued', tasks: {}, result: null });
    } else if (ev.type === 'model_start') {
      const r = lab.rows.get(ev.key); if (r) r.status = 'running';
    } else if (ev.type === 'task_result') {
      const r = lab.rows.get(ev.key);
      if (r) (r.tasks[ev.task] ||= []).push({ variant: ev.variant, passed: ev.passed, latency_ms: ev.latency_ms, error: ev.error, detail: ev.detail });
    } else if (ev.type === 'model_done') {
      const r = lab.rows.get(ev.key); if (r) { r.status = 'done'; r.result = ev.result; }
      lab.done += 1;
    } else if (ev.type === 'done') {
      finished = true; lab.last = ev.data; lab.running = false; lab.rows = new Map();
      toast(`Benchmark finished: ${ev.data.results.length} models tested`, { kind: 'ok' });
      refreshCurrent();
    } else if (ev.type === 'error') {
      finished = true; lab.running = false; lab.runError = ev.message;
    } else if (ev.type === 'cancelled') {
      finished = true; lab.running = false; lab.rows = new Map(); toast('Benchmark stopped');
    }
    notify();
  }, lab.ctrl.signal).catch((e) => {
    if (e.name === 'AbortError') return;
    lab.runError = e.network
      ? 'Lost the connection to Odysseus during the benchmark. If the server is still running it carries on, and this page picks it up again when it reconnects.'
      : e.message;
  }).finally(() => {
    if (!finished) { lab.running = false; if (!lab.runError) lab.runError = 'The connection to the server ended before the benchmark finished.'; }
    lab.ctrl = null; notify();
  });
}

async function stopBench() {
  try { await post('/models/bench/cancel'); } catch (e) { toast(e.message, { kind: 'error' }); }
}

async function save(body, message) {
  lab.busy = true; notify();
  try {
    const res = await post('/models/default', body);
    lab.current = res.current;
    if (message) toast(message, { kind: 'ok' });
  } catch (e) { toast(e.message, { kind: 'error' }); }
  lab.busy = false; notify();
}

const withDefault = (extra) => ({ default: refOf(lab.current.default), ...extra });
const needDefault = () => { if (lab.current?.default) return true; toast('Choose a default model first', { kind: 'error' }); return false; };
const makeDefault = (r) => save({ default: refOf(r), fallbacks: (lab.current?.fallbacks || []).map(refOf) },
  `${modelName(r.model)} is now the default`);
const addFallback = (r) => (lab.current?.default
  ? save(withDefault({ fallbacks: [...lab.current.fallbacks.map(refOf), refOf(r)] }), `${modelName(r.model)} added as a fallback`)
  : makeDefault(r));
const removeFallback = (ref) => needDefault() && save(withDefault({ fallbacks: lab.current.fallbacks.filter((f) => !sameRef(f, ref)).map(refOf) }));
const resetUtility = () => needDefault() && save(withDefault({ utility: null }), 'Background jobs now use the default model');
const applyRecommendation = (rec) => save({
  default: refOf(rec.default),
  fallbacks: rec.fallbacks.map(refOf),
  ...(rec.utility ? { utility: refOf(rec.utility), utility_fallbacks: rec.utility_fallbacks.map(refOf) } : {}),
}, 'Recommendation applied');

// --------------------------------------------------------------------- pieces
const tierBadge = (tier) => h('span', { class: ['mdl-tier', `mdl-tier-${tier}`], title: (TIER[tier] || TIER.unknown).hint, text: (TIER[tier] || TIER.unknown).label });

function modelLine(ref, extra) {
  return h('div', { class: 'mdl-ref' },
    h('div', { class: 'mdl-ref-main' },
      h('span', { class: 'mdl-model mono', text: modelName(ref.model) || 'Not set' }),
      ref.endpoint_name && h('span', { class: 'mdl-sub', text: ref.endpoint_name }),
      tierBadge(ref.tier),
      ref.problem && h('span', { class: 'pill st-failed', title: 'This reference can no longer be used', text: ref.problem })),
    extra);
}

function inUse() {
  const cur = lab.current;
  const rows = [];
  rows.push(h('div', { class: 'mdl-slot' },
    h('div', { class: 'mdl-slot-label' }, h('div', { class: 'set-label', text: 'Default chat model' }), h('div', { class: 'set-hint muted', text: 'Used first for chat and for Jarvis.' })),
    cur.default ? modelLine(cur.default) : h('span', { class: 'muted', text: 'Not set' })));
  rows.push(h('div', { class: 'mdl-slot' },
    h('div', { class: 'mdl-slot-label' }, h('div', { class: 'set-label', text: 'Fallbacks' }), h('div', { class: 'set-hint muted', text: 'Tried in order when the one above fails or is rate limited.' })),
    cur.fallbacks.length
      ? h('ol', { class: 'mdl-chain' }, cur.fallbacks.map((f) => h('li', {},
        modelLine(f, h('button', { class: 'icon-btn', 'aria-label': `Remove ${modelName(f.model)} from fallbacks`, title: 'Remove from fallbacks', disabled: lab.busy, on: { click: () => removeFallback(f) } }, icon('x', 14))))))
      : h('span', { class: 'muted', text: 'None' })));
  rows.push(h('div', { class: 'mdl-slot' },
    h('div', { class: 'mdl-slot-label' }, h('div', { class: 'set-label', text: 'Background jobs' }), h('div', { class: 'set-hint muted', text: 'Summaries, naming and the OS assistant.' })),
    cur.utility
      ? modelLine(cur.utility, h('button', { class: 'btn btn-ghost btn-sm', disabled: lab.busy, title: 'Use the default model instead', on: { click: resetUtility } }, 'Reset'))
      : h('span', { class: 'muted', text: 'Same as the default model' }),
    cur.utility && cur.utility_fallbacks.length > 0 && h('div', { class: 'mdl-sub-chain muted' }, 'then ', cur.utility_fallbacks.map((f) => modelName(f.model)).join(', '))));
  return rows;
}

// One result row's data, from a finished result or from live events.
function rowView(src) {
  if (src.result || src.score !== undefined) {
    const r = src.result || src;
    return { key: r.key, endpoint_id: r.endpoint_id, endpoint_name: r.endpoint_name, model: r.model, provider: r.provider, tier: r.tier,
      state: 'done', status: r.status, score: r.score, median: r.median_latency_ms, tasks: r.tasks, notes: r.notes || [], quality: r.quality };
  }
  const tasks = {};
  for (const [id, runs] of Object.entries(src.tasks)) {
    const passed = runs.filter((x) => x.passed).length;
    tasks[id] = { passed, of: runs.length, status: runs.length < (lab.tasks.find((t) => t.id === id)?.runs || 2) ? 'pending' : passed === runs.length ? 'pass' : passed ? 'partial' : runs.every((x) => x.error) ? 'error' : 'fail', runs };
  }
  return { key: src.key, endpoint_id: src.endpoint_id, endpoint_name: src.endpoint_name, model: src.model, provider: src.provider, tier: src.tier,
    state: src.status, status: src.status, score: null, median: null, tasks, notes: [] };
}

function dots(view, taskDefs) {
  return h('span', { class: 'mdl-dots', role: 'img', 'aria-label': 'Result per task' }, taskDefs.map((t) => {
    const info = view.tasks?.[t.id];
    const state = info ? info.status : 'pending';
    const runs = (info?.runs || []).map((r) => `#${r.variant} ${r.passed ? 'passed' : r.error === 'skipped' ? 'skipped' : r.error ? `error (${r.error})` : 'failed'}${r.passed ? '' : r.detail ? `: ${r.detail}` : ''}`);
    const title = `${t.label}\n${info ? `${info.passed}/${info.of} passed` : 'waiting'}${runs.length ? `\n${runs.join('\n')}` : ''}`;
    return h('span', { class: ['mdl-dot', `mdl-dot-${state}`], title });
  }));
}

const shortReason = (text) => {
  const t = String(text || '').replace(/^failing on every attempt:\s*/i, '').replace(/^unavailable:\s*/i, '');
  return t.length > 130 ? `${t.slice(0, 127)}…` : t;
};

function resultRow(view, taskDefs, off) {
  const cur = lab.current;
  const isDefault = cur?.default && sameRef(cur.default, view);
  const fbIndex = (cur?.fallbacks || []).findIndex((f) => sameRef(f, view));
  const live = view.state === 'queued' || view.state === 'running';
  const [statusText, statusKind] = STATUS[view.status] || [];
  const note = view.notes?.[0] || '';
  const canAct = !off && !live;
  const name = h('div', { class: 'mdl-cell-name' },
    h('div', { class: 'mdl-model-line' },
      view.state === 'running' && h('span', { class: 'mdl-spin', 'aria-label': 'Testing' }),
      h('span', { class: 'mdl-model mono', text: modelName(view.model) })),
    h('div', { class: 'mdl-sub', text: view.endpoint_name }));
  if (off) {   // nothing to rank: just say why it cannot be used
    return h('div', { class: 'mdl-row mdl-row-off', 'data-key': view.key },
      name,
      h('div', { class: 'mdl-cell-tier' }, statusText && h('span', { class: ['pill', statusKind === 'bad' ? 'st-failed' : 'sev-medium'], text: statusText }), tierBadge(view.tier)),
      note && h('div', { class: 'mdl-why muted', title: note, text: shortReason(note) }));
  }
  return h('div', { class: ['mdl-row', live && 'mdl-row-live'], 'data-key': view.key },
    name,
    h('div', { class: 'mdl-cell-tier' }, tierBadge(view.tier)),
    h('div', { class: 'mdl-cell-meta' },
      h('div', { class: 'mdl-cell-score' }, view.score === null || view.score === undefined
        ? h('span', { class: 'muted mono', text: view.state === 'queued' ? 'queued' : '…' })
        : [h('span', { class: 'mdl-bar', role: 'img', 'aria-label': `Score ${view.score} out of 100` }, h('span', { class: 'mdl-bar-fill', style: { width: `${Math.max(0, Math.min(100, view.score))}%` } })),
          h('span', { class: 'mdl-score mono', text: view.score.toFixed(0) })]),
      dots(view, taskDefs),
      h('div', { class: 'mdl-cell-lat mono muted', title: 'Median response time', text: fmtMs(view.median) })),
    h('div', { class: 'mdl-cell-act' },
      statusText && h('span', { class: ['pill', statusKind === 'bad' ? 'st-failed' : 'sev-medium'], title: note, text: statusText }),
      canAct && (isDefault
        ? h('span', { class: 'mdl-flag', text: 'Default' })
        : h('button', { class: 'btn btn-soft btn-sm', disabled: lab.busy, on: { click: () => makeDefault(view) } }, 'Make default')),
      canAct && !isDefault && (fbIndex >= 0
        ? h('span', { class: 'mdl-flag', text: `Fallback ${fbIndex + 1}` })
        : h('button', { class: 'btn btn-ghost btn-sm', disabled: lab.busy, on: { click: () => addFallback(view) } }, 'Add as fallback'))));
}

function recommendation(rec) {
  if (!rec?.default) return h('p', { class: 'set-hint muted', text: rec?.note || 'No model answered reliably enough to recommend one.' });
  const cur = lab.current;
  const applied = cur?.default && sameRef(cur.default, rec.default)
    && rec.fallbacks.length === cur.fallbacks.length && rec.fallbacks.every((f, i) => sameRef(f, cur.fallbacks[i]))
    && (!rec.utility || (cur.utility && sameRef(cur.utility, rec.utility)));
  const line = (label, r) => h('div', { class: 'mdl-rec-line' },
    h('span', { class: 'mdl-rec-label', text: label }),
    h('div', { class: 'mdl-rec-what' },
      h('div', { class: 'mdl-ref-main' }, h('span', { class: 'mdl-model mono', text: modelName(r.model) }), h('span', { class: 'mdl-sub', text: r.endpoint_name }), tierBadge(r.tier)),
      h('div', { class: 'mdl-why muted', text: r.why })));
  return h('div', { class: 'mdl-rec' },
    h('div', { class: 'mdl-rec-body' },
      line('Default', rec.default),
      rec.fallbacks.map((f, i) => line(`Fallback ${i + 1}`, f)),
      rec.utility && line('Background', rec.utility)),
    h('div', { class: 'mdl-rec-act' },
      h('button', { class: 'btn btn-ink', disabled: lab.busy || applied, on: { click: () => applyRecommendation(rec) } }, applied ? [icon('check', 14), 'Applied'] : 'Apply recommendation')));
}

function results() {
  const taskDefs = lab.running && lab.tasks.length ? lab.tasks : (lab.last?.tasks || []);
  let views;
  if (lab.running) views = [...lab.rows.values()].map(rowView);
  else views = (lab.last?.results || []).map(rowView);
  if (!views.length) return null;
  const usable = views.filter((v) => v.state !== 'done' || v.status === 'ok' || v.status === 'partial');
  const off = views.filter((v) => !usable.includes(v));
  const key = (state, text) => h('span', { class: 'mdl-legend-item' }, h('span', { class: ['mdl-dot', `mdl-dot-${state}`] }), text);
  const legend = h('div', { class: 'mdl-legend muted' },
    h('span', { text: `Dots, left to right: ${taskDefs.map((t) => t.label).join(', ')}. Hover a dot for details.` }),
    h('span', { class: 'mdl-legend-keys' }, key('pass', 'both passed'), key('partial', 'one passed'), key('fail', 'failed'), key('error', 'no answer')));
  return h('div', { class: 'mdl-table' },
    usable.map((v) => resultRow(v, taskDefs, false)),
    off.length > 0 && h('details', { class: 'mdl-off' },
      h('summary', {}, icon('chevron-right', 14), `${off.length} model${off.length === 1 ? '' : 's'} not usable right now`),
      off.map((v) => resultRow(v, taskDefs, true))),
    legend);
}

const testingNow = () => {
  const names = [...lab.rows.values()].filter((r) => r.status === 'running').map((r) => modelName(r.model));
  return names.length ? ` · testing ${names.slice(0, 2).join(', ')}${names.length > 2 ? '…' : ''}` : '';
};

// ------------------------------------------------------------------------ pane
export function mountModelsPane(pane, { group }) {
  const root = h('div', { class: 'mdl' });
  pane.append(root);
  let timer = null;
  let elapsedEl = null;

  const stopTimer = () => { clearInterval(timer); timer = null; };

  function render() {
    clear(root);
    elapsedEl = null;
    const title = h('h2', { class: 'set-title serif' }, 'AI ', h('em', { text: 'models' }));
    if (!lab.loaded) {
      root.append(title, h('div', { class: 'mdl-skel', 'aria-busy': 'true' }, h('span', {}), h('span', {}), h('span', {})));
      return;
    }
    if (lab.error || !lab.current) {
      root.append(title, h('p', { class: 'err-text', text: lab.error || 'Could not read the model settings.' }),
        h('button', { class: 'btn btn-soft', on: { click: () => { lab.loaded = false; notify(); loadAll(); } } }, icon('refresh', 14), 'Try again'));
      return;
    }
    const last = lab.last;
    root.append(
      title,
      h('p', { class: 'set-hint muted', text: 'Odysseus tries the default model first and moves down the fallbacks when a provider is rate limited or unreachable. Test your connected models and pick the best free one.' }),
      group('In use', ...inUse()));
    const benchGroup = group('Benchmark',
        h('div', { class: 'mdl-run' },
          lab.running
            ? h('button', { class: 'btn btn-soft', on: { click: stopBench } }, icon('stop', 14), 'Stop')
            : h('button', { class: 'btn btn-ink', on: { click: () => startBench({}, true) } }, icon('play', 14), last ? 'Run again' : 'Run benchmark'),
          h('span', { class: 'mdl-run-status muted' },
            lab.running
              ? [`${lab.done} of ${lab.total || '…'} models · `, elapsedEl = h('span', { class: 'mono', text: fmtElapsed(Date.now() - lab.startedAt) }), testingNow()]
              : last ? `Last run ${fmtDate(last.finished_at)} · ${last.results.length} models · ${fmtElapsed((last.duration_s || 0) * 1000)}` : 'Not run yet')),
        h('p', { class: 'set-hint muted', text: 'Each model gets twelve short tasks: a JSON tool plan for the OS assistant, schedule to cron, a word problem, strict formatting, event extraction and a summary. Only free and local models are called; paid providers are never used.' }),
        lab.runError && h('p', { class: 'err-text mdl-err', text: lab.runError }),
        !last && !lab.running && !lab.runError && h('p', { class: 'mdl-empty muted', text: 'No results yet. Run the benchmark to see which of your models is best and free.' }),
        last && !lab.running && recommendation(last.recommended),
        results(),
        last && !lab.running && paidNote(last));
    root.append(benchGroup);
    if (lab.focusBench) { lab.focusBench = false; requestAnimationFrame(() => benchGroup.scrollIntoView({ block: 'start', behavior: 'smooth' })); }
    if (lab.running) {
      stopTimer();
      timer = setInterval(() => { if (!document.hidden && elapsedEl) elapsedEl.textContent = fmtElapsed(Date.now() - lab.startedAt); }, 1000);
    } else stopTimer();
  }

  const paid = (last) => (last.skipped || []).filter((s) => s.kind === 'paid');
  function paidNote(last) {
    const p = paid(last);
    if (!p.length) return null;
    const names = [...new Set(p.map((s) => `${s.endpoint_name}: ${modelName(s.model)}`))];
    return h('p', { class: 'set-hint muted mdl-paid', text: `Not tested because they bill per token: ${names.join(', ')}.` });
  }

  let raf = 0;
  const onChange = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; render(); }); };
  lab.listeners.add(onChange);
  render();
  if (!lab.loaded || !lab.current) loadAll(); else refreshCurrent();   // always re-read the live selection

  return {
    destroy: () => { lab.listeners.delete(onChange); stopTimer(); if (raf) cancelAnimationFrame(raf); },
  };
}
