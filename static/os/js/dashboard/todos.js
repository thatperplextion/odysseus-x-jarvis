// Dashboard · Todos: open checklist items from Notes. Checking one off is the real Notes toggle; adding one is a real capture commit.

import { h, icon, clear, toast } from '../dom.js';
import { post } from '../api.js';
import { makeWidget, emptyState, tzOffset } from './common.js';
import { notesApi } from './http.js';

export function createTodos({ refresh }) {
  const w = makeWidget({ key: 'todos', title: 'TODOS', openApp: 'notes' });
  const list = h('div', { class: 'td-list', role: 'list' });
  const empty = h('div', { class: 'td-empty' });
  const input = h('input', { class: 'input td-input', type: 'text', placeholder: 'Add a todo…', 'aria-label': 'Add a todo', maxlength: 300, autocomplete: 'off', spellcheck: 'false' });
  const addBtn = h('button', { class: 'icon-btn td-add-btn', type: 'submit', 'aria-label': 'Add todo', title: 'Add todo' }, icon('plus', 15));
  let busy = false;
  const form = h('form', { class: 'td-add', on: { submit: async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;
    busy = true; addBtn.disabled = true;
    try {
      const r = await post('/capture/commit', { kind: 'todo', draft: { text }, tz_offset: tzOffset() });
      input.value = '';
      toast('Todo added', { kind: 'ok', ms: 5000, action: { label: 'Undo', run: async () => { try { await post('/capture/undo', { kind: 'todo', id: r.id, item_id: r.item_id }); } catch (err) { toast(err.message, { kind: 'error' }); } refresh(); } } });
    } catch (err) { toast(err.message, { kind: 'error' }); } finally { busy = false; addBtn.disabled = false; }
    refresh();
    input.focus();
  } } }, input, addBtn);
  w.body.append(list, empty, form);
  let sig = '';

  async function complete(item, row, check) {
    row.classList.add('done');
    check.setAttribute('aria-checked', 'true');
    try {
      const res = await notesApi.toggleItem(item.note_id, item.index);
      const now = res.items?.[item.index];
      if (!now || String(now.text || '').trim() !== item.text) {
        // the list changed under us (another window edited it): put it back and reload
        await notesApi.toggleItem(item.note_id, item.index).catch(() => {});
        toast('That list changed, so nothing was checked off. Refreshed.', { ms: 3000 });
        refresh();
        return;
      }
      toast('Done', { kind: 'ok', ms: 4000, action: { label: 'Undo', run: async () => { try { await notesApi.toggleItem(item.note_id, item.index); } catch (e) { toast(e.message, { kind: 'error' }); } refresh(); } } });
      setTimeout(refresh, 450);               // let the strike-through register before the row leaves
    } catch (e) {
      row.classList.remove('done');
      check.setAttribute('aria-checked', 'false');
      toast(e.message, { kind: 'error' });
    }
  }

  function render(data) {
    const key = JSON.stringify([data.open, data.items.map((i) => [i.note_id, i.index, i.text])]);
    if (key === sig) return;
    sig = key;
    w.setCount(data.open ? String(data.open) : null);
    clear(list); clear(empty);
    empty.hidden = data.open > 0;
    if (!data.open) empty.append(emptyState('Nothing to do. Add the first thing below.', null));
    for (const item of data.items) {
      const check = h('button', { class: 'td-check', type: 'button', role: 'checkbox', 'aria-checked': 'false', 'aria-label': `Mark done: ${item.text}` }, icon('check', 12));
      const row = h('div', { class: 'td-row', role: 'listitem', dataset: { note: item.note_id, index: item.index } }, check,
        h('span', { class: 'td-text', text: item.text }),
        item.list ? h('span', { class: 'td-from muted mono', text: item.list, title: `From the “${item.list}” list` }) : null);
      check.addEventListener('click', () => complete(item, row, check));
      list.append(row);
    }
    if (data.more) list.append(h('div', { class: 'td-more muted', text: `+${data.more} more in Notes` }));
  }

  return { el: w.el, shell: w, render, tick() {}, section: 'todos', focusInput: () => input.focus() };
}
