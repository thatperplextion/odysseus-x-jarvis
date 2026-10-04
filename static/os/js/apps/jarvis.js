// Jarvis: the assistant. Asks Odysseus's model questions, runs your day (automations, to-dos, calendar,
// reminders) and can run commands, write files and manage processes -- but anything that creates or changes
// something appears as an approval card first.

import { h, icon, clear, toast, fmtDuration } from '../dom.js';
import { get, post } from '../api.js';
import { os } from '../ctx.js';
import { isOnline } from '../net.js';

export const meta = { id: 'jarvis', name: 'Jarvis', icon: 'sparkles', width: 560, height: 640, singleton: true };

// send = ask right away; fill = put the start of a sentence in the box for the person to finish
const SUGGESTIONS = [
  { label: 'Plan my day', send: "Plan my day: what's on my calendar today, what's still open on my to-do list, and what should I start with?" },
  { label: 'Every morning at 8, brief me', send: 'Every morning at 8, give me a brief of my day' },
  { label: 'What’s on tomorrow?', send: "What's on my calendar tomorrow?" },
  { label: 'Add a todo', fill: 'Add to my todos: ' },
  { label: 'What is using my CPU?', send: 'cpu' },
];
const KIND_ICON = { automation: 'zap', event: 'calendar', reminder: 'bell', todo: 'check-square' };
const MAX_SAVED = 60;
const STORE = (user) => `ody.jarvis.chat.${user}`;

/** The browser's clock, so "tomorrow at 11" means the person's tomorrow, whatever the server's zone is. */
function clockContext() {
  let tz = '';
  try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch { /* old browser */ }
  return { tz, offset_min: -new Date().getTimezoneOffset() };
}

/** Open Automations (the native app), or the older Tasks page if this build has no such app. */
function openAutomations(props = {}) {
  const has = typeof os.appList === 'function' && os.appList().some((a) => a.id === 'automations');
  if (has) os.openApp('automations', props);
  else os.openApp('tasks');
}
function openTarget(target) {
  if (!target) return;
  if (target.app === 'automations') openAutomations(target.props || {});
  else os.openApp(target.app, target.props || {});
}

export function mount(body, win, props = {}) {
  const user = os.boot.user;
  let messages = load();
  let pending = false;
  let timers = [];
  let alive = true;
  const runTimers = new Set();     // pending polls for runs started from a result card
  const polling = new Set();

  const scroll = h('div', { class: 'jv-scroll', role: 'log', 'aria-live': 'polite', tabindex: '-1' });
  const input = h('textarea', { class: 'jv-input', rows: 1, placeholder: 'Ask Jarvis, or tell it what to do…', 'aria-label': 'Message Jarvis', spellcheck: 'true' });
  const sendBtn = h('button', { class: 'jv-send', 'aria-label': 'Send', title: 'Send (Enter)', on: { click: () => submit() } }, icon('arrow-up', 17));
  const clearBtn = h('button', { class: 'icon-btn', 'aria-label': 'New conversation', title: 'New conversation', on: { click: () => { messages = []; save(); render(); } } }, icon('plus', 16));
  const composer = h('div', { class: 'jv-composer' }, input, sendBtn);
  const hint = h('div', { class: 'jv-hint muted' }, os.boot.assistant?.llm
    ? 'Jarvis asks before it runs commands, changes files or creates anything.'
    : 'No language model is configured in Odysseus, so Jarvis understands commands but not open-ended questions.');
  const bar = h('div', { class: 'jv-bar' }, h('span', { class: 'jv-title' }, icon('sparkles', 15), 'Jarvis'), h('span', { class: 'win-spacer' }), clearBtn);
  body.append(h('div', { class: 'jarvis' }, bar, scroll, h('div', { class: 'jv-foot' }, composer, hint)));

  // ------------------------------------------------------------ persistence
  function load() {
    try {
      const saved = JSON.parse(localStorage.getItem(STORE(user)) || '[]').filter((m) => m.role !== 'approval' || m.state);   // stale approvals are gone
      for (const m of saved) for (const r of m.results || []) if (r.run && !r.run.done) { r.run.done = true; r.run.timedOut = true; }   // not followed across sessions
      return saved;
    } catch { return []; }
  }
  function save() {
    try { localStorage.setItem(STORE(user), JSON.stringify(messages.slice(-MAX_SAVED).map(({ token, ...m }) => (m.role === 'approval' && !m.state ? { ...m, state: 'expired' } : m)))); } catch { /* ignore */ }
  }

  // --------------------------------------------------------------- rendering
  function render() {
    timers.forEach(clearInterval);
    timers = [];
    clear(scroll);
    if (!messages.length) {
      scroll.append(h('div', { class: 'jv-empty' },
        h('h2', { class: 'serif' }, 'How can I ', h('em', { text: 'help' }), '?'),
        h('p', { class: 'muted', text: 'I can plan your day, schedule automations, keep your to-dos, calendar and reminders, run commands and work with your files. I ask before I change anything.' }),
        h('div', { class: 'jv-chips' }, SUGGESTIONS.map((s) => h('button', { class: 'chip', text: s.label, on: { click: () => (s.send ? submit(s.send) : fillInput(s.fill)) } })))));
    }
    for (const m of messages) scroll.append(renderMessage(m));
    if (pending) scroll.append(h('div', { class: 'jv-msg assistant' }, h('div', { class: 'jv-typing', 'aria-label': 'Jarvis is thinking' }, h('i'), h('i'), h('i'))));
    scroll.scrollTop = scroll.scrollHeight;
  }

  function renderMessage(m) {
    if (m.role === 'user') return h('div', { class: 'jv-msg user' }, h('div', { class: 'jv-bubble', text: m.text }));
    if (m.role === 'approval') return renderApproval(m);
    if (m.role === 'result') return renderResult(m);
    const mono = m.mono;
    return h('div', { class: ['jv-msg', 'assistant', m.error && 'error'] },
      h('div', { class: 'jv-stack' },
        m.text ? h('div', { class: ['jv-text', mono && 'mono-block'] }, mono ? h('pre', { text: m.text }) : markdown(m.text)) : null,
        (m.cards || []).map(renderCard)));
  }

  // ---- approval card: what Jarvis wants to do, in plain words
  function renderApproval(m) {
    const items = m.action.items || [];
    const rich = items.some((i) => i.kind);
    const card = h('div', { class: ['jv-approval', m.state && `is-${m.state}`] },
      h('div', { class: 'jv-ap-head' }, icon('shield', 15), h('span', { text: m.state === 'approved' ? 'Approved' : m.state === 'denied' ? 'Cancelled' : m.state === 'expired' ? 'Expired' : 'Waiting for your approval' })),
      h('div', { class: 'jv-ap-title', text: m.action.title }),
      rich ? h('div', { class: 'jv-steps' }, items.map(renderStep)) : (m.action.detail && h('pre', { class: 'jv-ap-detail mono', text: m.action.detail })));
    if (!m.state) {
      const left = h('span', { class: 'muted jv-ap-timer' });
      const approve = h('button', { class: 'btn btn-ink btn-sm', on: { click: () => decide(m, true) } }, icon('check', 14), 'Approve');
      const deny = h('button', { class: 'btn btn-ghost btn-sm', on: { click: () => decide(m, false) } }, 'Cancel');
      card.append(h('div', { class: 'jv-ap-actions' }, approve, deny, left));
      const until = m.until || (m.until = Date.now() + (m.expires_in || 300) * 1000);
      const tick = () => {
        const s = Math.round((until - Date.now()) / 1000);
        if (s <= 0) { m.state = 'expired'; save(); render(); return; }
        left.textContent = `expires in ${fmtDuration(s)}`;
      };
      tick();
      timers.push(setInterval(tick, 1000));
    }
    return h('div', { class: 'jv-msg assistant' }, card);
  }

  function renderStep(it) {
    if (!it.kind) return h('div', { class: 'jv-step plain mono', text: it.label });
    return h('div', { class: ['jv-step', `k-${it.kind}`] },
      h('span', { class: 'jv-step-ico' }, icon(KIND_ICON[it.kind] || 'sparkles', 15)),
      h('div', { class: 'jv-step-body' },
        h('div', { class: 'jv-step-verb mono', text: it.verb }),
        h('div', { class: 'jv-step-title', text: it.title }),
        it.rows?.length ? h('dl', { class: 'jv-rows' }, it.rows.flatMap(([k, v]) => [h('dt', { text: k }), h('dd', { class: k === 'Prompt' ? 'jv-prompt' : '', text: v })])) : null,
        (it.warnings || []).map((w) => h('div', { class: 'jv-warn' }, icon('alert', 13), h('span', { text: w }))),
        (it.notes || []).map((n) => h('div', { class: 'jv-note muted', text: n }))));
  }

  // ---- result cards: what actually happened, with a way to go and see it
  function renderResult(m) {
    return h('div', { class: 'jv-msg assistant' }, h('div', { class: 'jv-stack' },
      m.pure ? null : h('div', { class: ['jv-text', 'mono-block'] }, h('pre', { text: m.text })),
      m.results.map(resultCard)));
  }

  function resultCard(r) {
    let msg = String((r.ok !== false && r.headline) || r.message || r.title || '').replace(/^[✓✗]\s*/, '');
    let ok = r.ok !== false;
    const running = !!(r.run && !r.run.done);
    if (running) watchRun(r);
    else if (r.run) {
      if (r.run.timedOut) msg = `“${r.title}” is taking a while; check Automations for its result`;
      else if (r.run.ok) msg = `Ran “${r.title}”`;
      else { msg = `“${r.title}” did not finish OK`; ok = false; }
    }
    return h('div', { class: ['jv-card', 'jv-result', ok ? 'ok' : 'bad'] },
      h('div', { class: 'jv-result-head' },
        h('span', { class: 'jv-result-ico' }, icon(ok ? 'check' : 'alert', 14)),
        h('span', { class: 'jv-result-msg', text: msg }),
        running ? h('span', { class: 'jv-run-state mono' }, h('i'), h('i'), h('i')) : null),
      r.rows?.length ? h('dl', { class: 'jv-rows' }, r.rows.flatMap(([k, v]) => [h('dt', { text: k }), h('dd', { text: v })])) : null,
      r.output ? h('pre', { class: 'jv-output mono', text: r.output }) : null,
      r.open ? h('div', { class: 'jv-card-foot' },
        h('button', { class: 'btn btn-soft btn-sm', on: { click: () => openTarget(r.open) } }, icon('external', 13), r.open.label || 'Open')) : null);
  }

  /** "Run it now" returns at once; follow the run until it finishes (every 5 s, at most two minutes). */
  function watchRun(r) {
    const key = `${r.run.task_id}@${r.run.since}`;
    if (polling.has(key)) return;
    polling.add(key);
    let tries = 0;
    const finish = (patch) => { polling.delete(key); Object.assign(r.run, { done: true }, patch); save(); if (alive) render(); };
    const step = async () => {
      if (!alive) return;
      if (!isOnline()) {         // Odysseus unreachable: keep following the run, without burning tries
        const wait = setTimeout(() => { runTimers.delete(wait); step(); }, 5000);
        runTimers.add(wait);
        return;
      }
      tries++;
      try {
        const res = await get('/assistant/run-result', { task_id: r.run.task_id, since: r.run.since });
        if (res.done) { r.output = res.output || ''; finish({ ok: !!res.ok }); os.emit('personal-changed', { kinds: ['automation'] }); return; }
      } catch { /* keep trying; the run may not have started yet */ }
      if (tries >= 24) { finish({ timedOut: true }); return; }
      const t = setTimeout(() => { runTimers.delete(t); step(); }, 5000);
      runTimers.add(t);
    };
    const first = setTimeout(() => { runTimers.delete(first); step(); }, 2000);
    runTimers.add(first);
  }

  // ---- read-only cards (agenda, to-dos, automations)
  function renderCard(c) {
    if (c.type === 'agenda') return agendaCard(c);
    if (c.type === 'todos') return todosCard(c);
    if (c.type === 'automations') return automationsCard(c);
    return null;
  }

  function cardHead(ic, label, count) {
    return h('div', { class: 'jv-card-head' }, icon(ic, 14), h('span', { class: 'mono', text: label }), count ? h('span', { class: 'jv-card-count mono', text: count }) : null);
  }

  function agendaCard(c) {
    return h('div', { class: 'jv-card jv-agenda' },
      cardHead('calendar', c.range, c.days.length ? `${c.days.reduce((n, d) => n + d.items.length, 0)}` : ''),
      c.days.length
        ? c.days.map((d) => h('div', { class: 'jv-day' },
          h('div', { class: 'jv-day-label mono', text: d.label }),
          d.items.map((i) => h('div', { class: ['jv-item', `k-${i.kind}`] },
            h('span', { class: 'jv-time mono', text: i.time }),
            h('span', { class: 'jv-it-title' }, i.title, i.kind === 'reminder' ? h('span', { class: 'jv-tag mono', text: 'reminder' }) : null),
            i.location ? h('span', { class: 'jv-it-loc muted', text: i.location }) : null))))
        : h('div', { class: 'jv-card-empty muted', text: 'Nothing scheduled.' }),
      h('div', { class: 'jv-card-foot' }, h('button', { class: 'btn btn-ghost btn-sm', on: { click: () => os.openApp('calendar') } }, icon('external', 13), 'Open Calendar')));
  }

  function todosCard(c) {
    const open = c.items.filter((t) => !t.done).length;
    const list = h('div', { class: 'jv-todos' });
    for (const t of c.items) list.append(todoRow(t));
    return h('div', { class: 'jv-card jv-todo-card' },
      cardHead('check-square', 'To-do', c.items.length ? `${open} open` : ''),
      c.items.length ? list : h('div', { class: 'jv-card-empty muted', text: 'Nothing open. Enjoy it.' }),
      h('div', { class: 'jv-card-foot' },
        h('button', { class: 'btn btn-ghost btn-sm', on: { click: () => fillInput('Add to my todos: ') } }, icon('plus', 13), 'Add one'),
        h('button', { class: 'btn btn-ghost btn-sm', on: { click: () => os.openApp('notes') } }, icon('external', 13), 'Open Notes')));
  }

  function todoRow(t) {
    const box = h('button', { class: ['jv-check', t.done && 'on'], type: 'button', role: 'checkbox', 'aria-checked': String(!!t.done), 'aria-label': t.text }, icon('check', 12));
    const row = h('div', { class: ['jv-todo', t.done && 'done'] }, box, h('span', { class: 'jv-todo-text', text: t.text }));
    let busy = false;
    const paint = () => { row.classList.toggle('done', !!t.done); box.classList.toggle('on', !!t.done); box.setAttribute('aria-checked', String(!!t.done)); };
    box.addEventListener('click', async () => {
      if (busy) return;
      busy = true;
      const want = !t.done;
      t.done = want; paint();                                   // optimistic; the server has the last word
      try {
        const res = await post('/assistant/todos/toggle', { ref: t.ref, done: want });
        t.done = !!res.done; paint();
        os.emit('personal-changed', { kinds: ['todo'] });
      } catch (e) {
        t.done = !want; paint();
        toast(e.message || 'Could not update that to-do.', { kind: 'error' });
      }
      busy = false;
      save();
    });
    return row;
  }

  function automationsCard(c) {
    return h('div', { class: 'jv-card jv-auto-card' },
      cardHead('zap', 'Automations', c.items.length ? `${c.items.length}` : ''),
      c.items.length
        ? c.items.map((a) => h('button', { class: 'jv-auto', type: 'button', title: 'Open in Automations', on: { click: () => openAutomations({ intent: 'show', id: a.id }) } },
          h('span', { class: ['jv-dot', `st-${a.status}`], title: a.status }),
          h('span', { class: 'jv-auto-main' },
            h('span', { class: 'jv-auto-name', text: a.name }),
            h('span', { class: 'jv-auto-when muted', text: a.schedule })),
          h('span', { class: 'jv-auto-side mono' }, a.status === 'paused' ? 'paused' : (a.next_run ? `next ${a.next_run}` : a.status))))
        : h('div', { class: 'jv-card-empty muted', text: c.query ? `Nothing matches “${c.query}”.` : 'No automations yet. Try “every weekday at 9, summarise my inbox”.' }),
      h('div', { class: 'jv-card-foot' }, h('button', { class: 'btn btn-ghost btn-sm', on: { click: () => openAutomations() } }, icon('external', 13), 'Open Automations')));
  }

  // ---------------------------------------------------------------- behaviour
  function fillInput(text) {
    input.value = text;
    autosize();
    input.focus();
    input.setSelectionRange(text.length, text.length);
  }

  async function submit(textOverride) {
    const text = (textOverride ?? input.value).trim();
    if (!text || pending) return;
    input.value = '';
    autosize();
    const history = recentHistory();       // before this message is added
    messages.push({ role: 'user', text });
    await ask({ message: text, history });
  }

  /** The last few plain turns, so the assistant can follow up on what was just said. */
  function recentHistory() {
    return messages
      .filter((m) => (m.role === 'user' || m.role === 'assistant') && m.text && !m.error)
      .slice(-8)
      .map((m) => ({ role: m.role, content: m.text.slice(0, 2000) }));
  }

  async function ask(payload) {
    pending = true;
    sendBtn.disabled = true;
    render();
    try {
      const r = await post('/assistant', { ...payload, context: clockContext() });
      handle(r);
    } catch (e) {
      if (e?.network) {
        // The server went away mid-question. Say so calmly and give the person their words back to send again.
        const last = messages[messages.length - 1];
        if (payload.message && last?.role === 'user' && last.text === payload.message) messages.pop();       // it never arrived: no duplicate bubble when it is sent again
        if (payload.confirm_token) { const card = messages.find((m) => m.role === 'approval' && m.token === payload.confirm_token); if (card) delete card.state; }   // not approved after all
        messages.push({ role: 'assistant', text: 'I can’t reach Odysseus right now, so that didn’t go through. It will reconnect on its own; then send it again.', error: true });
        if (payload.message && !input.value) fillInput(payload.message);
      } else messages.push({ role: 'assistant', text: e.message || 'Something went wrong.', error: true });
    }
    pending = false;
    sendBtn.disabled = false;
    save();
    render();
    input.focus();
  }

  function handle(r) {
    for (const a of r.ui_actions || []) if (a.type === 'open_app') os.openApp(a.app, a.props || {});
    const cards = r.cards || [];
    if (r.requires_confirmation) {
      if (r.say || cards.length) messages.push({ role: 'assistant', text: r.say || '', cards });     // what Jarvis intends, above the card
      messages.push({ role: 'approval', action: r.action, token: r.confirm_token, expires_in: r.expires_in });
      return;
    }
    if (r.intent === 'plan_result' && r.results?.length) {
      const steps = (r.response || '').split('\n').filter((l) => /^[✓✗]/.test(l)).length;
      messages.push({ role: 'result', ok: r.success, results: r.results, text: r.response, pure: steps === r.results.length });
      if (r.results.some((x) => x.ok)) os.emit('personal-changed', { kinds: [...new Set(r.results.filter((x) => x.ok).map((x) => x.kind))] });
      return;
    }
    const mono = ['list_directory', 'list_processes', 'system_metrics', 'execute_command', 'read_file', 'help', 'plan_result'].includes(r.intent)
      || (/\n.+\n/.test(r.response || '') && !['chat', 'plan'].includes(r.intent));
    messages.push({ role: 'assistant', text: r.response || (r.success ? 'Done.' : 'That did not work.'), error: !r.success, mono, cards });
  }

  async function decide(m, approve) {
    if (pending) return;
    if (!approve) {
      m.state = 'denied';
      try { await post('/assistant/cancel', { confirm_token: m.token }); } catch { /* it expires anyway */ }
      save(); render();
      return;
    }
    m.state = 'approved';
    save();
    await ask({ message: '', confirm_token: m.token });
    os.emit('fs-changed');
  }

  function autosize() {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
  }
  input.addEventListener('input', autosize);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); submit(); }
    else if (e.key === 'Escape') { input.blur(); win.el.focus(); }
  });

  render();
  input.focus();
  if (props.ask) submit(props.ask);
  return {
    focus: () => input.focus(),
    serialize: () => ({}),
    destroy: () => { alive = false; timers.forEach(clearInterval); runTimers.forEach(clearTimeout); },
    onReuse: (p) => { if (p?.ask) submit(p.ask); input.focus(); },
  };
}

// ----------------------------------------------------------------- markdown
// A deliberately small renderer: paragraphs, **bold**, `code`, fenced blocks, - lists. DOM nodes only.
function markdown(text) {
  const root = h('div', { class: 'md' });
  const lines = String(text).replace(/\r\n/g, '\n').split('\n');
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (/^```/.test(line)) {
      const buf = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      i++;
      root.append(h('pre', { class: 'md-code mono' }, h('code', { text: buf.join('\n') })));
    } else if (/^\s*[-*]\s+/.test(line)) {
      const ul = h('ul');
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) ul.append(h('li', {}, inline(lines[i++].replace(/^\s*[-*]\s+/, ''))));
      root.append(ul);
    } else if (/^\s*\d+\.\s+/.test(line)) {
      const ol = h('ol');
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) ol.append(h('li', {}, inline(lines[i++].replace(/^\s*\d+\.\s+/, ''))));
      root.append(ol);
    } else if (/^#{1,3}\s+/.test(line)) {
      root.append(h('h4', { class: 'md-h' }, inline(line.replace(/^#{1,3}\s+/, ''))));
      i++;
    } else if (!line.trim()) {
      i++;
    } else {
      const buf = [];
      while (i < lines.length && lines[i].trim() && !/^```|^\s*[-*]\s+|^\s*\d+\.\s+|^#{1,3}\s+/.test(lines[i])) buf.push(lines[i++]);
      const p = h('p');
      buf.forEach((l, k) => { if (k) p.append(document.createElement('br')); p.append(inline(l)); });
      root.append(p);
    }
  }
  return root;
}

function inline(text) {
  const frag = document.createDocumentFragment();
  const re = /(`[^`\n]+`|\*\*[^*\n]+\*\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) frag.append(text.slice(last, m.index));
    const tok = m[0];
    frag.append(tok.startsWith('`') ? h('code', { class: 'md-inline mono', text: tok.slice(1, -1) }) : h('strong', { text: tok.slice(2, -2) }));
    last = m.index + tok.length;
  }
  if (last < text.length) frag.append(text.slice(last));
  return frag;
}
