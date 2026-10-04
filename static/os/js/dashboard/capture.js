// Dashboard · quick capture bar. One line in, a parsed preview (kind chip + human text), then Confirm / Edit / Cancel.
// Nothing is stored until Confirm; Undo in the toast removes exactly what was created.

import { h, icon, toast } from '../dom.js';
import { post } from '../api.js';
import { os } from '../ctx.js';
import { tzOffset } from './common.js';

const KIND_LABEL = { todo: 'Todo', event: 'Event', reminder: 'Reminder', automation: 'Automation' };
const KINDS = ['todo', 'event', 'reminder', 'automation'];
const CTA = { todo: 'Add todo', event: 'Add event', reminder: 'Set reminder', automation: 'Create automation' };

export function createCapture({ refresh }) {
  const input = h('input', { class: 'cap-input', type: 'text', placeholder: 'Capture a todo, event, reminder or automation…', 'aria-label': 'Quick capture', autocomplete: 'off', spellcheck: 'false', maxlength: 600 });
  const hint = h('kbd', { class: 'cap-kbd', text: 'Enter' });
  const field = h('div', { class: 'cap-field' }, icon('plus', 17), input, hint);
  const preview = h('div', { class: 'cap-preview', hidden: true, role: 'group', 'aria-label': 'Capture preview', dataset: { state: 'idle' } });
  const error = h('div', { class: 'cap-error', role: 'alert', hidden: true });
  const el = h('form', { class: 'cap', autocomplete: 'off', on: { submit: (e) => { e.preventDefault(); onEnter(); } } }, field, preview, error);

  let current = null;       // { kind, draft, preview_text, can_commit, text }
  let forced = null;        // kind pinned by the Edit chips
  let editing = false;
  let busy = false;

  function setError(msg) { error.hidden = !msg; error.textContent = msg || ''; }

  function reset({ keepText = false } = {}) {
    current = null; forced = null; editing = false; busy = false;
    preview.hidden = true; preview.replaceChildren(); preview.dataset.state = 'idle';
    setError('');
    if (!keepText) input.value = '';
  }

  async function parse(text, kind = null) {
    busy = true; field.classList.add('busy'); setError('');
    try {
      const r = await post('/capture', { text, kind, tz_offset: tzOffset() });
      current = { ...r, text };
      drawPreview();
    } catch (e) {
      setError(e.message);
      preview.hidden = true; preview.replaceChildren(); current = null;
    } finally { busy = false; field.classList.remove('busy'); }
  }

  function onEnter() {
    if (busy) return;
    const text = input.value.trim();
    if (!text) return;
    if (current && !editing && current.text === text) { confirm(); return; }       // Enter twice = confirm
    parse(text, editing ? forced : null);
  }

  function drawPreview() {
    preview.replaceChildren();
    preview.hidden = false;
    preview.dataset.state = editing ? 'editing' : 'preview';
    const c = current;
    const chip = h('span', { class: ['cap-chip', `k-${c.kind}`], dataset: { kind: c.kind }, text: KIND_LABEL[c.kind] });
    const text = h('span', { class: 'cap-text', text: c.preview_text });
    const needs = !c.can_commit;
    const actions = h('div', { class: 'cap-actions' },
      c.kind === 'automation' ? h('button', { class: 'btn btn-ghost btn-sm', type: 'button', dataset: { action: 'cap-open' }, text: 'Open in Automations', on: { click: openInAutomations } }) : null,
      h('button', { class: 'btn btn-ink btn-sm', type: 'button', dataset: { action: 'cap-confirm' }, text: needs ? 'Confirm' : 'Confirm', disabled: needs, title: needs ? 'Say what the automation should do first' : CTA[c.kind], on: { click: confirm } }),
      h('button', { class: 'btn btn-soft btn-sm', type: 'button', dataset: { action: 'cap-edit' }, text: 'Edit', 'aria-pressed': editing ? 'true' : 'false', on: { click: () => { editing = !editing; drawPreview(); if (editing) { input.focus(); input.select(); } } } }),
      h('button', { class: 'btn btn-ghost btn-sm', type: 'button', dataset: { action: 'cap-cancel' }, text: 'Cancel', on: { click: () => { reset(); input.focus(); } } }));
    preview.append(h('div', { class: 'cap-line' }, chip, text, actions));
    if (needs) preview.append(h('div', { class: 'cap-note muted', text: 'Add what it should do, for example “every weekday at 7am summarize my unread email”.' }));
    if (editing) {
      preview.append(h('div', { class: 'cap-edit' },
        h('span', { class: 'cap-edit-l mono', text: 'TREAT AS' }),
        h('div', { class: 'segmented', role: 'radiogroup', 'aria-label': 'Capture kind' }, KINDS.map((k) => h('button', { class: ['seg', k === c.kind && 'on'], type: 'button', role: 'radio', 'aria-checked': k === c.kind ? 'true' : 'false', dataset: { kind: k }, text: KIND_LABEL[k],
          on: { click: () => { forced = k; parse(c.text, k); } } }))),
        h('span', { class: 'cap-edit-h muted', text: 'Change the text above and press Enter to parse it again.' })));
    }
  }

  function openInAutomations() {
    if (!current || current.kind !== 'automation') return;
    const d = current.draft;
    const prefill = { name: d.name || undefined, output_target: d.output_target, schedule: d.human.replace(/^Every /, 'every ').replace(/^Monthly /, 'monthly ').replace(/^Daily /, 'daily ') };
    if (d.action) prefill.action = d.action; else prefill.prompt = d.prompt || '';
    os.openApp('automations', { intent: 'new', prefill });
    reset();
  }

  async function confirm() {
    if (!current || busy || !current.can_commit) return;
    busy = true;
    const { kind, draft } = current;
    preview.querySelectorAll('button').forEach((b) => { b.disabled = true; });
    try {
      const r = await post('/capture/commit', { kind, draft, tz_offset: tzOffset() });
      reset();
      toast(r.label + (kind === 'automation' && r.next_run ? `. First run ${new Date(r.next_run).toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' })}.` : ''), {
        kind: 'ok', ms: 6500,
        action: { label: 'Undo', run: async () => {
          try { await post('/capture/undo', { kind, id: r.id, item_id: r.item_id }); toast('Undone', { ms: 1600 }); } catch (e) { toast(e.message, { kind: 'error' }); }
          refresh();
        } },
      });
      refresh();
      os.emit('capture', { kind, id: r.id });
    } catch (e) {
      busy = false;
      setError(e.message);
      drawPreview();
    }
  }

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && (current || input.value)) { e.preventDefault(); e.stopPropagation(); reset(); }
  });
  input.addEventListener('input', () => { if (current && input.value.trim() !== current.text) { hint.textContent = 'Enter'; preview.dataset.state = editing ? 'editing' : 'stale'; } setError(''); });

  return {
    el,
    focus() { input.focus(); input.select(); },
    /** Put text in the bar; with run:true it is parsed straight away. */
    prefill(text, { run = false } = {}) {
      reset();
      input.value = text;
      input.focus();
      input.setSelectionRange(text.length, text.length);
      if (run && text.trim()) parse(text.trim());
    },
    get busy() { return busy; },
  };
}
