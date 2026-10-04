// Automations · the New / Edit sheet. Step 1: pick a template (or describe it). Step 2: configure it.
// It only builds the payload for the scheduler API; saving, refreshing and selecting is up to the caller.

import { h, icon, clear, debounce, toast } from '../../dom.js';
import { tasksApi, ApiError } from './client.js';
import {
  parseNaturalSchedule, schedulePayload, nextRuns, describeStructured, describeTask, cronToStructured, fmtWhen,
  DOW_SHORT, tzOffsetMin, hhmm, localToUtc,
} from './schedule.js';
import { TEMPLATES, KIND_LABEL, blankDraft, actionTitle, actionBlurb, COMMAND_ACTIONS, draftFromTask } from './templates.js';

const MODES = [
  ['interval', 'Every few minutes or hours'], ['daily', 'Every day'], ['weekdays', 'Every weekday'], ['weekend', 'Every weekend'],
  ['weekly', 'Certain days of the week'], ['monthly', 'Once a month'], ['once', 'Just once'], ['cron', 'Custom (cron, UTC)'],
];
const DAY_ORDER = [1, 2, 3, 4, 5, 6, 0];

export function tzLabel() {
  const off = tzOffsetMin();
  const sign = off < 0 ? '-' : '+';
  const a = Math.abs(off);
  const zone = (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone; } catch { return ''; } })();
  return `UTC${sign}${Math.floor(a / 60)}${a % 60 ? `:${String(a % 60).padStart(2, '0')}` : ''}${zone ? ` · ${zone}` : ''}`;
}

const shiftTime = (t, minutes) => {
  const [hh, mm] = String(t || '09:00').split(':').map(Number);
  const total = (((hh * 60 + mm + minutes) % 1440) + 1440) % 1440;
  return hhmm(Math.floor(total / 60), total % 60);
};

/** Fields of an AI draft (/api/tasks/parse) -> editor draft. The model is told to answer in LOCAL time. */
export function draftFromAi(ai) {
  const d = { ...blankDraft(), kind: ai.task_type === 'research' ? 'research' : 'llm', name: ai.name || '', prompt: ai.prompt || '', output: ai.output_target || 'session' };
  const time = ai.scheduled_time && /^\d{1,2}:\d{2}$/.test(ai.scheduled_time) ? hhmm(...ai.scheduled_time.split(':').map(Number)) : '09:00';
  if (ai.schedule === 'weekly') d.sched = { mode: 'weekly', time, days: [((ai.scheduled_day ?? 0) + 1) % 7] };
  else if (ai.schedule === 'monthly') d.sched = { mode: 'monthly', time, dom: Math.max(1, Math.min(28, ai.scheduled_day ?? 1)) };
  else if (ai.schedule === 'once' && ai.scheduled_date) d.sched = { mode: 'once', date: ai.scheduled_date.slice(0, 10), time: ai.scheduled_date.slice(11, 16) || time };
  else if (ai.schedule === 'cron' && ai.cron_expression) d.sched = cronToStructured(ai.cron_expression, 0) || { mode: 'cron', cron: ai.cron_expression };
  else d.sched = { mode: 'daily', time };
  if (d.sched.times) delete d.sched.times;
  return d;
}

/**
 * @param host     element (position: relative) the sheet covers
 * @param opts     { existing?:task, draft?, template?, env:{shells,isWindows,canCommand}, meta:{actions,events,targets,models},
 *                   tasks:[...], onSaved(task, {companion}), onClose() }
 */
export function openEditor(host, opts) {
  let { existing = null } = opts;
  const { env, meta, tasks, onSaved, onClose } = opts;
  let activate = false;               // editing a built-in on behalf of a template: switch it on when saved
  const builtinFor = (action) => (action ? tasks.find((x) => x.action === action && x.is_builtin && (x.task_type || 'llm') === 'action') : null);
  let step = existing || opts.draft ? 'form' : 'gallery';
  let d = opts.draft ? structuredClone(opts.draft) : null;
  let template = opts.template || null;
  let companionOn = false;
  let saving = false;

  const sheet = h('div', { class: 'au-sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': existing ? 'Edit automation' : 'New automation' });
  const back = h('div', { class: 'au-sheet-back' }, sheet);
  const previouslyFocused = document.activeElement;

  const close = () => { back.remove(); document.removeEventListener('keydown', onKey, true); if (previouslyFocused?.focus) previouslyFocused.focus(); onClose?.(); };
  const onKey = (e) => {
    if (!back.isConnected) return;
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }
  };
  document.addEventListener('keydown', onKey, true);
  back.addEventListener('pointerdown', (e) => { if (e.target === back) close(); });
  host.append(back);

  // ------------------------------------------------------------------------------------------ gallery
  function gallery() {
    clear(sheet);
    const ai = h('input', { class: 'input au-ai-input', type: 'text', placeholder: 'Describe it: every weekday at 7am summarise my unread email', 'aria-label': 'Describe the automation', spellcheck: 'false' });
    const aiMsg = h('div', { class: 'au-hint', role: 'status' });
    const aiBtn = h('button', { class: 'btn btn-soft', type: 'button', text: 'Draft with AI', on: { click: () => draft() } });
    async function draft() {
      const text = ai.value.trim();
      if (!text) { ai.focus(); return; }
      aiBtn.disabled = true; aiMsg.className = 'au-hint'; aiMsg.textContent = 'Asking your model to draft it…';
      try {
        const res = await tasksApi.parse(text);
        if (res.success && res.draft) { d = draftFromAi(res.draft); template = null; step = 'form'; render(); return; }
        const local = parseNaturalSchedule(text);
        aiMsg.className = 'au-hint warn';
        aiMsg.textContent = `${res.message || 'The AI could not draft that'}. ${local.ok ? 'Pick a template and describe the schedule there.' : 'Pick a template below instead.'}`;
      } catch (e) { aiMsg.className = 'au-hint warn'; aiMsg.textContent = e.message; }
      aiBtn.disabled = false;
    }
    ai.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); draft(); } });
    sheet.append(
      h('header', { class: 'au-sheet-head' },
        h('div', {}, h('h2', { class: 'serif au-sheet-title' }, 'New ', h('em', { text: 'automation' })),
          h('p', { class: 'muted au-sheet-sub', text: 'Start from a template, or describe what you want and let your model draft it.' })),
        h('button', { class: 'icon-btn', 'aria-label': 'Close', title: 'Close (Esc)', on: { click: close } }, icon('x', 17))),
      h('div', { class: 'au-sheet-scroll' },
        h('div', { class: 'au-ai' }, ai, aiBtn), aiMsg,
        h('div', { class: 'au-eyebrow mono', text: 'TEMPLATES' }),
        h('div', { class: 'au-templates' }, TEMPLATES.map((t) => {
          const blocked = t.admin && !env.canCommand;
          return h('button', {
            class: ['au-tpl', blocked && 'blocked'], type: 'button', disabled: blocked, dataset: { template: t.id }, 'aria-label': `${t.title}${blocked ? ' (unavailable)' : ''}`,
            on: { click: () => {
              template = t; d = t.build(env); companionOn = !!t.companion; step = 'form';
              // Housekeeping actions (tidy, inbox triage...) exist once per user as built-ins, and Odysseus deletes extra copies,
              // so a template for one of them configures and switches on the built-in instead of creating a second.
              const bi = d.kind === 'action' ? builtinFor(d.action) : null;
              if (bi) { const sched = d.sched; existing = bi; d = draftFromTask(bi, () => null); d.sched = sched; d.name = bi.name; activate = true; }
              render();
            } },
          },
          h('span', { class: 'au-tpl-icon' }, icon(t.icon, 18)),
          h('span', { class: 'au-tpl-text' },
            h('span', { class: 'au-tpl-title', text: t.title }),
            h('span', { class: 'au-tpl-blurb', text: blocked ? 'Unavailable: the scheduler only creates shell commands for signed-in administrators. Turn sign-in on in Odysseus to use this.' : t.blurb }),
            h('span', { class: 'au-tpl-when mono', text: t.admin ? `${t.when} · admin` : (t.id !== 'custom-ai' && builtinFor(t.build(env).action) ? `${t.when} · already built in` : t.when) })));
        }))));
    ai.focus();
  }

  // ------------------------------------------------------------------------------------------ the form
  function form() {
    if (!d) return gallery();
    clear(sheet);
    const errs = {};
    let flushNl = null;               // applies the schedule sentence if the user hits Save before the typing debounce fired
    const errEl = (key) => (errs[key] = h('div', { class: 'au-err', role: 'alert', hidden: true }));
    const showErr = (key, msg) => { const el = errs[key]; if (!el) return; el.textContent = msg || ''; el.hidden = !msg; };
    const field = (label, control, { hint, key, id } = {}) => h('div', { class: 'au-field' },
      h('label', { class: 'au-label', for: id }, label), control, hint && h('div', { class: 'au-hint', text: hint }), key && errEl(key));

    const nameInput = h('input', { class: 'input', id: 'au-name', type: 'text', value: d.name, maxlength: 120, placeholder: 'e.g. Morning brief', on: { input: () => { d.name = nameInput.value; showErr('name'); } } });

    // ---- what
    const whatBox = h('div', { class: 'au-what' });
    const kindSeg = h('div', { class: 'segmented au-seg', role: 'radiogroup', 'aria-label': 'What it does' });
    const kinds = existing ? [d.kind] : ['llm', 'research', 'action', 'command'];
    function drawKinds() {
      clear(kindSeg);
      for (const k of kinds) {
        const off = k === 'command' && !env.canCommand && !(existing && d.kind === 'command');
        kindSeg.append(h('button', {
          class: ['seg', d.kind === k && 'on'], type: 'button', role: 'radio', 'aria-checked': d.kind === k ? 'true' : 'false', disabled: off || (!!existing && k !== d.kind),
          title: off ? 'Shell commands need a signed-in administrator' : undefined, dataset: { kind: k },
          on: { click: () => { d.kind = k; if (k === 'command') d.output = d.output === 'notification' ? 'none' : d.output; drawKinds(); drawWhat(); drawOutput(); drawAdvanced(); } },
        }, KIND_LABEL[k]));
      }
    }
    function drawWhat() {
      clear(whatBox);
      if (d.kind === 'llm' || d.kind === 'research') {
        const ta = h('textarea', { class: 'input au-textarea', id: 'au-prompt', rows: 5, placeholder: d.kind === 'research' ? 'What should it research? e.g. The latest on open-source LLM releases this week' : 'What should the AI do? Be specific; it can use your calendar, notes, mail and tools.', on: { input: () => { d.prompt = ta.value; showErr('prompt'); } } });
        ta.value = d.prompt;
        whatBox.append(field(d.kind === 'research' ? 'Research question' : 'Instruction', ta, { key: 'prompt', id: 'au-prompt' }));
      } else if (d.kind === 'action') {
        const actions = meta.actions.filter((a) => !COMMAND_ACTIONS.has(a.name));
        const sel = h('select', { class: 'select au-wide', id: 'au-action', on: { change: () => { d.action = sel.value; blurb.textContent = actionBlurb(d.action, meta.actions); showErr('action'); } } },
          h('option', { value: '', text: 'Choose an action…' }),
          actions.map((a) => {
            const taken = !(existing && existing.action === a.name) && builtinFor(a.name);
            return h('option', { value: a.name, selected: a.name === d.action, disabled: !!taken, text: `${actionTitle(a.name)}${taken ? ' (built-in, already in your list)' : ''}` });
          }),
          d.action && !actions.some((a) => a.name === d.action) && h('option', { value: d.action, selected: true, text: actionTitle(d.action) }));
        const blurb = h('div', { class: 'au-hint', text: actionBlurb(d.action, meta.actions) });
        whatBox.append(field('Action', sel, { key: 'action', id: 'au-action' }), blurb);
      } else {
        const shellNote = env.isWindows
          ? (env.shells.some((s) => s.id === 'bash') ? 'Runs in Git Bash on this computer, so use POSIX syntax (tar, cp, $HOME).' : 'Git Bash was not found, so this runs in Command Prompt (cmd).')
          : 'Runs in bash on this computer.';
        const ta = h('textarea', { class: 'input au-textarea mono', id: 'au-command', rows: 4, spellcheck: 'false', placeholder: 'echo hello', on: { input: () => { d.command = ta.value; showErr('command'); } } });
        ta.value = d.command;
        whatBox.append(
          h('div', { class: 'au-callout' }, icon('alert', 15), h('span', {}, h('strong', { text: 'Runs with your permissions. ' }), `${shellNote} Output is kept in the run history. Only schedule commands you trust.`)),
          field('Command', ta, { key: 'command', id: 'au-command' }));
      }
    }

    // ---- when
    const trigSeg = h('div', { class: 'segmented au-seg', role: 'radiogroup', 'aria-label': 'When it runs' });
    const whenBox = h('div', { class: 'au-when' });
    function drawTrigger() {
      clear(trigSeg);
      for (const [k, label] of [['schedule', 'On a schedule'], ['event', 'When something happens'], ['webhook', 'Webhook']]) {
        trigSeg.append(h('button', {
          class: ['seg', d.trigger === k && 'on'], type: 'button', role: 'radio', 'aria-checked': d.trigger === k ? 'true' : 'false', disabled: !!existing && d.trigger !== k,
          title: existing && d.trigger !== k ? 'How an automation starts cannot change after it is created. Duplicate it instead.' : undefined, dataset: { trigger: k },
          on: { click: () => { d.trigger = k; drawTrigger(); drawWhen(); } },
        }, label));
      }
    }
    function drawWhen() {
      clear(whenBox);
      if (d.trigger === 'schedule') whenBox.append(scheduleBlock());
      else if (d.trigger === 'event') {
        const evSel = h('select', { class: 'select au-wide', id: 'au-event', on: { change: () => { d.event = evSel.value; evHint.textContent = meta.events.find((x) => x.name === d.event)?.description || ''; } } },
          meta.events.map((x) => h('option', { value: x.name, selected: x.name === d.event, text: x.name.replace(/_/g, ' ') })));
        const evHint = h('div', { class: 'au-hint', text: meta.events.find((x) => x.name === d.event)?.description || '' });
        const count = h('input', { class: 'input au-num', id: 'au-count', type: 'number', min: 1, max: 1000, value: d.count, on: { input: () => { d.count = Number(count.value); showErr('count'); } } });
        whenBox.append(field('Event', evSel, { id: 'au-event' }), evHint,
          h('div', { class: 'au-field au-inline' }, h('span', { text: 'Run every' }), count, h('span', { text: 'of these' })), errEl('count'));
      } else {
        whenBox.append(h('div', { class: 'au-callout soft' }, icon('link', 15), h('span', { text: 'A private URL is created when you save. Anything that can send an HTTP POST to it will start this automation.' })));
      }
    }

    function scheduleBlock() {
      const box = h('div', { class: 'au-sched' });
      const nl = h('input', { class: 'input au-wide', id: 'au-nl', type: 'text', placeholder: 'Describe it: every weekday at 9:30am', 'aria-label': 'Describe the schedule', spellcheck: 'false' });
      const nlMsg = h('div', { class: 'au-hint', role: 'status' });
      const manual = h('div', { class: 'au-manual' });
      const preview = h('div', { class: 'au-preview', 'aria-live': 'polite' });

      function drawPreview() {
        clear(preview);
        const p = schedulePayload(d.sched);
        if (p.error) { preview.append(h('div', { class: 'au-preview-err', text: p.error })); return p; }
        const task = { trigger_type: 'schedule', ...p.fields };
        const summary = d.sched.mode === 'cron' ? describeTask(task).text : describeStructured(d.sched);
        const runs = nextRuns(task, 3);
        preview.append(
          h('div', { class: 'au-preview-line' }, icon('clock', 14), h('strong', { text: summary })),
          runs.length ? h('div', { class: 'au-preview-runs' }, h('span', { class: 'mono au-preview-label', text: 'NEXT 3 RUNS' }), runs.map((r) => h('span', { class: 'au-run-chip mono', text: fmtWhen(r) })))
            : h('div', { class: 'au-hint', text: 'This will never run. Check the date or expression.' }),
          h('div', { class: 'au-hint', text: `Shown in your time zone (${tzLabel()}). Odysseus keeps schedules in UTC and converts for you.` }));
        return p;
      }
      function drawManual() {
        clear(manual);
        const s = d.sched;
        const modeSel = h('select', { class: 'select au-wide', id: 'au-mode', 'aria-label': 'Repeat', on: { change: () => {
          const m = modeSel.value;
          const time = s.time || '09:00';
          d.sched = m === 'interval' ? { mode: m, unit: 'hours', every: 1, at: 0 } : m === 'weekly' ? { mode: m, time, days: [1] } : m === 'monthly' ? { mode: m, time, dom: 1 }
            : m === 'once' ? { mode: m, date: '', time } : m === 'cron' ? { mode: m, cron: schedulePayload(s).fields?.cron_expression || '0 9 * * *' } : { mode: m, time };
          nl.value = ''; nlMsg.textContent = ''; drawManual(); drawPreview();
        } } }, MODES.map(([v, label]) => h('option', { value: v, selected: v === s.mode, text: label })));
        const upd = () => { drawPreview(); showErr('sched'); };
        const timeInput = () => h('input', { class: 'input au-time', type: 'time', 'aria-label': 'Time of day', value: s.time || '09:00', on: { input: (e) => { s.time = e.target.value; upd(); } } });
        const row = (...c) => h('div', { class: 'au-inline' }, ...c);
        manual.append(field('Repeat', modeSel, { id: 'au-mode' }));
        if (s.mode === 'interval') {
          const every = h('input', { class: 'input au-num', type: 'number', min: 1, max: 59, value: s.every, 'aria-label': 'How many', on: { input: (e) => { s.every = Number(e.target.value); upd(); } } });
          const unit = h('select', { class: 'select', 'aria-label': 'Unit', on: { change: (e) => { s.unit = e.target.value; drawManual(); upd(); } } },
            h('option', { value: 'minutes', selected: s.unit === 'minutes', text: 'minutes' }), h('option', { value: 'hours', selected: s.unit === 'hours', text: 'hours' }));
          const at = h('input', { class: 'input au-num', type: 'number', min: 0, max: 59, value: s.at || 0, 'aria-label': 'Minute past the hour', on: { input: (e) => { s.at = Number(e.target.value); upd(); } } });
          manual.append(row(h('span', { text: 'Every' }), every, unit, s.unit === 'hours' && row(h('span', { class: 'muted', text: 'at minute' }), at)));
        } else if (s.mode === 'weekly') {
          manual.append(row(...DAY_ORDER.map((dd) => {
            const on = s.days.includes(dd);
            return h('button', { class: ['au-day', on && 'on'], type: 'button', 'aria-pressed': on ? 'true' : 'false', text: DOW_SHORT[dd], on: { click: (e) => {
              s.days = on ? s.days.filter((x) => x !== dd) : [...s.days, dd]; drawManual(); upd();
            } } });
          })), row(h('span', { class: 'muted', text: 'at' }), timeInput()));
        } else if (s.mode === 'monthly') {
          const dom = h('input', { class: 'input au-num', type: 'number', min: 1, max: 28, value: s.dom, 'aria-label': 'Day of the month', on: { input: (e) => { s.dom = Number(e.target.value); upd(); } } });
          manual.append(row(h('span', { text: 'On day' }), dom, h('span', { class: 'muted', text: 'at' }), timeInput()));
        } else if (s.mode === 'once') {
          const date = h('input', { class: 'input au-date', type: 'date', 'aria-label': 'Date', value: s.date || '', min: new Date().toISOString().slice(0, 10), on: { input: (e) => { s.date = e.target.value; upd(); } } });
          manual.append(row(date, h('span', { class: 'muted', text: 'at' }), timeInput()));
        } else if (s.mode === 'cron') {
          const cron = h('input', { class: 'input mono au-wide', type: 'text', value: s.cron || '', placeholder: '*/5 * * * *', 'aria-label': 'Cron expression', spellcheck: 'false', on: { input: (e) => { s.cron = e.target.value; upd(); } } });
          manual.append(cron, h('div', { class: 'au-hint', text: 'Five fields: minute hour day-of-month month day-of-week. The scheduler reads cron in UTC.' }));
        } else manual.append(row(h('span', { class: 'muted', text: 'at' }), timeInput()));
      }

      let aiBusy = false;
      let nlDirty = false;
      const applyText = () => {
        nlDirty = false;
        const text = nl.value.trim();
        nlMsg.className = 'au-hint';
        if (!text) { nlMsg.textContent = ''; return; }
        const r = parseNaturalSchedule(text);
        if (r.ok) {
          d.sched = r.sched; nlMsg.className = 'au-hint ok'; nlMsg.textContent = `Understood: ${r.sched.mode === 'once' ? describeStructured(r.sched) : describeStructured({ ...r.sched, times: undefined })}`;
          drawManual(); drawPreview(); showErr('sched');
        } else { nlMsg.className = 'au-hint'; nlMsg.textContent = `${r.reason === 'empty' ? '' : r.reason} Press Enter to ask your model instead.`.trim(); }
      };
      const deb = debounce(applyText, 220);
      nl.addEventListener('input', () => { nlDirty = true; deb(); });
      flushNl = () => { if (nlDirty) { deb.cancel(); applyText(); } };
      nl.addEventListener('keydown', async (e) => {
        if (e.key !== 'Enter') return;
        e.preventDefault(); e.stopPropagation();
        const text = nl.value.trim();
        if (!text || aiBusy) return;
        const local = parseNaturalSchedule(text);
        if (local.ok) { applyText(); return; }
        aiBusy = true; nlMsg.className = 'au-hint'; nlMsg.textContent = 'Asking your model…';
        try {
          const res = await tasksApi.parse(text);
          if (res.success && res.draft) { d.sched = draftFromAi(res.draft).sched; nlMsg.className = 'au-hint ok'; nlMsg.textContent = 'Drafted by your model. Check the preview below.'; drawManual(); drawPreview(); }
          else { nlMsg.className = 'au-hint warn'; nlMsg.textContent = res.message ? `${res.message}. Use the controls below instead.` : 'Could not read that. Use the controls below instead.'; }
        } catch (err) { nlMsg.className = 'au-hint warn'; nlMsg.textContent = err.message; }
        aiBusy = false;
      });
      box.append(field('Describe the schedule', nl, { id: 'au-nl' }), nlMsg, manual, preview, errEl('sched'));
      drawManual(); drawPreview();
      return box;
    }

    // ---- output
    const outBox = h('div', { class: 'au-out' });
    function drawOutput() {
      clear(outBox);
      const isAct = d.kind === 'action' || d.kind === 'command';
      const targets = [
        { value: 'session', label: 'Chat session' },
        !isAct && { value: 'notification', label: 'Notification' },
        { value: 'email', label: 'Email' },
        { value: 'none', label: 'Run history only' },
        ...meta.targets.filter((t) => t.value.startsWith('mcp__')).map((t) => ({ value: t.value, label: t.label })),
      ].filter(Boolean);
      if (!targets.some((t) => t.value === d.output)) targets.push({ value: d.output, label: d.output });
      const sel = h('select', { class: 'select au-wide', id: 'au-output', on: { change: () => { d.output = sel.value; drawOutput(); } } },
        targets.map((t) => h('option', { value: t.value, selected: t.value === d.output, text: t.label })));
      const hints = { session: 'Saved as a chat called “[Task] name”.', notification: 'A browser notification while Odysseus is open.', email: 'Sent through your configured email account.', none: 'The result stays in this automation’s run history.' };
      outBox.append(field('Send the result to', sel, { id: 'au-output', hint: hints[d.output] || 'Delivered with the tool you picked.' }));
      if (d.output === 'email') {
        const to = h('input', { class: 'input au-wide', id: 'au-email', type: 'email', value: d.emailTo, placeholder: 'Leave blank to email yourself', on: { input: () => { d.emailTo = to.value; showErr('email'); } } });
        outBox.append(field('Recipient', to, { id: 'au-email', key: 'email' }));
      }
    }

    // ---- advanced
    const advBox = h('div', { class: 'au-adv-body' });
    function drawAdvanced() {
      clear(advBox);
      if (d.kind === 'llm' || d.kind === 'research') {
        const sel = h('select', { class: 'select au-wide', id: 'au-model', on: { change: () => { d.model = sel.value; } } },
          h('option', { value: '', text: 'Default model' }),
          meta.models.filter((m) => m.is_enabled !== false && (m.model_type || 'llm') === 'llm' && (m.models || []).length).map((ep) =>
            h('optgroup', { label: ep.name || ep.base_url }, ep.models.map((m) => h('option', { value: `${ep.base_url}::${m}`, selected: d.model === `${ep.base_url}::${m}`, text: m })))),
          d.model && !meta.models.some((ep) => (ep.models || []).some((m) => d.model === `${ep.base_url}::${m}`)) && h('option', { value: d.model, selected: true, text: d.model.split('::')[1] }));
        advBox.append(field('Model', sel, { id: 'au-model', hint: 'Leave on the default to follow whatever you chat with.' }));
        const sw = h('input', { type: 'checkbox', role: 'switch', checked: d.notify, 'aria-label': 'Notify me when it finishes', on: { change: () => { d.notify = sw.checked; } } });
        advBox.append(h('div', { class: 'au-switch-row' }, h('div', {}, h('div', { class: 'au-label plain', text: 'Notify me when it finishes' }), h('div', { class: 'au-hint', text: 'Also tells you when a run fails.' })),
          h('label', { class: 'switch' }, sw, h('span', { class: 'switch-track' }, h('span', { class: 'switch-thumb' })))));
      }
      const others = tasks.filter((t) => !existing || t.id !== existing.id);
      const chain = h('select', { class: 'select au-wide', id: 'au-chain', on: { change: () => { d.then = chain.value; } } },
        h('option', { value: '', text: 'Nothing, stop here' }), others.map((t) => h('option', { value: t.id, selected: t.id === d.then, text: t.name })));
      advBox.append(field('After it succeeds, run', chain, { id: 'au-chain' }));
    }

    // ---- companion (templates only)
    const comp = template?.companion && (!existing || activate)
      ? h('label', { class: 'au-check' }, h('input', { type: 'checkbox', checked: companionOn, on: { change: (e) => { companionOn = e.target.checked; } } }), h('span', { text: template.companion.label }))
      : null;

    const footErr = h('div', { class: 'au-form-error', role: 'alert', hidden: true });
    const saveBtn = h('button', { class: 'btn btn-ink', type: 'button', id: 'au-save', text: activate ? 'Save and turn on' : existing ? 'Save changes' : 'Create automation', on: { click: () => save() } });

    drawKinds(); drawWhat(); drawTrigger(); drawWhen(); drawOutput(); drawAdvanced();

    sheet.append(
      h('header', { class: 'au-sheet-head' },
        h('div', {}, h('h2', { class: 'serif au-sheet-title' }, existing ? (activate ? 'Turn on ' : 'Edit ') : 'Set up ', h('em', { text: activate ? existing.name.toLowerCase() : existing ? 'automation' : (template ? template.title.replace(/^./, (c) => c.toLowerCase()) : 'automation') })),
          h('p', { class: 'muted au-sheet-sub', text: activate ? (d.trigger === 'schedule' ? 'This is a built-in automation Odysseus already keeps for you. Saving switches it on with this schedule.' : 'This is a built-in automation Odysseus already keeps for you. Built-ins keep their own trigger, so it runs after the number of events below, not on a clock.') : existing ? 'Changes apply to the next run.' : 'Review the details, then create it. You can pause or edit it any time.' })),
        h('button', { class: 'icon-btn', 'aria-label': 'Close', title: 'Close (Esc)', on: { click: close } }, icon('x', 17))),
      h('div', { class: 'au-sheet-scroll' },
        field('Name', nameInput, { key: 'name', id: 'au-name' }),
        h('div', { class: 'au-section' }, h('div', { class: 'au-eyebrow mono', text: 'WHAT IT DOES' }), kindSeg, whatBox),
        h('div', { class: 'au-section' }, h('div', { class: 'au-eyebrow mono', text: 'WHEN IT RUNS' }), trigSeg, whenBox),
        h('div', { class: 'au-section' }, h('div', { class: 'au-eyebrow mono', text: 'RESULT' }), outBox),
        h('details', { class: 'au-section au-adv' }, h('summary', {}, h('span', { class: 'au-eyebrow mono', text: 'MORE OPTIONS' })), advBox),
        comp),
      h('footer', { class: 'au-sheet-foot' },
        (!existing || activate) && !opts.draft ? h('button', { class: 'btn btn-ghost', type: 'button', text: 'Templates', on: { click: () => { step = 'gallery'; d = null; existing = null; activate = false; render(); } } }, icon('arrow-left', 14)) : null,
        footErr, h('span', { class: 'win-spacer' }),
        h('button', { class: 'btn btn-ghost', type: 'button', text: 'Cancel', on: { click: close } }), saveBtn));
    nameInput.focus();

    // ---------------------------------------------------------------------------------------- validate + save
    function build() {
      const bad = {};
      const name = d.name.trim();
      if (!name) bad.name = 'Give it a name so you can find it later.';
      const p = {
        name, task_type: d.kind === 'llm' ? 'llm' : d.kind === 'research' ? 'research' : 'action', trigger_type: d.trigger,
        output_target: d.output === 'email' ? (d.emailTo.trim() ? `email:${d.emailTo.trim()}` : 'email') : d.output,
        then_task_id: d.then || '',
      };
      if (d.output === 'email' && d.emailTo.trim() && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(d.emailTo.trim())) bad.email = 'That does not look like an email address.';
      if (d.kind === 'llm' || d.kind === 'research') {
        if (!d.prompt.trim()) bad.prompt = d.kind === 'research' ? 'What should it research?' : 'Tell the AI what to do.';
        p.prompt = d.prompt.trim();
        p.notifications_enabled = !!d.notify;
        if (d.model && d.model.includes('::')) { const i = d.model.indexOf('::'); p.endpoint_url = d.model.slice(0, i); p.model = d.model.slice(i + 2); } else { p.endpoint_url = ''; p.model = ''; }
      } else if (d.kind === 'action') {
        if (!d.action) bad.action = 'Choose an action.';
        if (!existing && d.action && builtinFor(d.action)) bad.action = `“${actionTitle(d.action)}” already exists as a built-in automation. Edit that one instead.`;
        if (!existing || existing.action !== d.action) p.action = d.action;
      } else {
        if (!d.command.trim()) bad.command = 'Enter the command to run.';
        p.prompt = d.command.trim();
        if (!existing) p.action = 'run_local';
      }
      if (d.trigger === 'schedule') {
        const sp = schedulePayload(d.sched);
        if (sp.error) bad.sched = sp.error; else Object.assign(p, sp.fields);
      } else if (d.trigger === 'event') {
        if (!d.event) bad.count = 'Choose an event.';
        if (!Number.isInteger(Number(d.count)) || Number(d.count) < 1) bad.count = 'Use a whole number of 1 or more.';
        p.trigger_event = d.event; p.trigger_count = Number(d.count);
      }
      return { bad, p };
    }

    async function save() {
      if (saving) return;
      flushNl?.();
      const { bad, p } = build();
      for (const k of Object.keys(errs)) showErr(k, bad[k]);
      footErr.hidden = true;
      const first = Object.keys(bad)[0];
      if (first) {
        const target = { name: '#au-name', prompt: '#au-prompt', action: '#au-action', command: '#au-command', sched: '#au-nl', count: '#au-count', email: '#au-email' }[first];
        sheet.querySelector(target)?.focus();
        footErr.textContent = 'Fix the highlighted fields to continue.'; footErr.hidden = false;
        return;
      }
      saving = true; saveBtn.disabled = true; saveBtn.textContent = 'Saving…';
      try {
        let saved;
        if (existing) {
          saved = await tasksApi.update(existing.id, p);
          if ((existing.status === 'completed' && d.trigger === 'schedule') || (activate && existing.status !== 'active')) { try { await tasksApi.resume(existing.id); } catch { /* shown on next refresh */ } }
        } else {
          saved = await tasksApi.create(p);
        }
        let companion = null;
        if ((!existing || activate) && companionOn && template?.companion) {
          const c = template.companion;
          const csched = c.sched ? c.sched : { ...d.sched, time: shiftTime(d.sched.time, c.offsetMin || 0) };
          const sp = schedulePayload(csched);
          if (!sp.error) {
            try {
              const bi = builtinFor(c.action);
              if (bi) {
                // A built-in that fires on events keeps its trigger (Odysseus puts it back), so only switch it on.
                companion = (bi.trigger_type || 'schedule') === 'schedule' ? await tasksApi.update(bi.id, sp.fields) : bi;
                if (bi.status !== 'active') await tasksApi.resume(bi.id);
              } else companion = await tasksApi.create({ ...p, ...sp.fields, name: c.name, action: c.action, then_task_id: '' });
            } catch (e) { toast(`Saved “${saved.name}”, but the second automation failed: ${e.message}`, { kind: 'error' }); }
          }
        }
        back.remove(); document.removeEventListener('keydown', onKey, true);
        onSaved?.(saved, { companion, created: !existing, activated: activate });
      } catch (e) {
        saving = false; saveBtn.disabled = false; saveBtn.textContent = activate ? 'Save and turn on' : existing ? 'Save changes' : 'Create automation';
        footErr.textContent = e instanceof ApiError && e.status === 403 && /admin/i.test(e.message)
          ? 'Shell commands can only be scheduled by a signed-in administrator. With sign-in off, Odysseus will not create them.'
          : e.message;
        footErr.hidden = false;
      }
    }
  }

  function render() { if (step === 'gallery') gallery(); else form(); }

  render();
  return { close, el: back };
}
