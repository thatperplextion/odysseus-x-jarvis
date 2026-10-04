// Dashboard · Inbox (unread + top senders, or a calm "connect" state) and the AI model strip.

import { h, icon } from '../dom.js';
import { os } from '../ctx.js';
import { makeWidget, emptyState } from './common.js';

export function createInbox() {
  const w = makeWidget({ key: 'inbox', title: 'INBOX', openApp: 'email' });
  let sig = '';
  function render(d) {
    const key = JSON.stringify(d);
    if (key === sig) return;
    sig = key;
    w.body.replaceChildren();
    if (!d.configured) {
      w.setCount(null);
      w.body.append(emptyState('Connect an email account to see unread mail and top senders here.', 'Connect email', () => os.openApp('email')));
      return;
    }
    if (d.unread == null) {
      w.setCount(null);
      w.body.append(emptyState('Your inbox hasn’t synced yet. Open Email once and the count will show up here.', 'Open Email', () => os.openApp('email')));
      return;
    }
    w.setCount(null);
    w.body.append(
      h('div', { class: 'ib-count' }, h('span', { class: 'ib-num serif', dataset: { unread: d.unread }, text: String(d.unread) }), h('span', { class: 'muted', text: d.unread === 1 ? 'unread message' : 'unread messages' })),
      d.top_senders.length
        ? h('ul', { class: 'ib-senders' }, d.top_senders.map((s) => h('li', {}, h('span', { class: 'ib-name', text: s.name }), h('span', { class: 'muted mono', text: `${s.count}` }))))
        : h('p', { class: 'muted', text: 'Inbox zero.' }));
  }
  return { el: w.el, shell: w, render, tick() {}, section: 'inbox' };
}

export function createModel() {
  const w = makeWidget({ key: 'model', title: 'AI MODEL' });
  const change = () => os.openApp('settings', { section: 'models' });
  let sig = '';
  function render(d) {
    const key = JSON.stringify(d);
    if (key === sig) return;
    sig = key;
    w.body.replaceChildren();
    if (!d.configured) {
      w.body.append(h('div', { class: 'md-row' }, h('span', { class: 'muted', text: d.model === '' || d.endpoint_name ? 'No default model chosen yet.' : 'No AI model connected yet.' }),
        h('button', { class: 'btn btn-soft btn-sm', type: 'button', dataset: { action: 'change-model' }, text: 'Choose a model', on: { click: change } })));
      return;
    }
    w.body.append(h('div', { class: 'md-row' },
      icon('sparkles', 15),
      h('span', { class: 'md-name mono', text: d.model, title: d.model }),
      h('span', { class: 'md-via muted', text: `via ${d.endpoint_name}${d.host ? ` (${d.host})` : ''}` }),
      h('span', { class: 'win-spacer' }),
      h('button', { class: 'tw-open', type: 'button', dataset: { action: 'change-model' }, 'aria-label': 'Change default model', text: 'Change', on: { click: change } })));
  }
  return { el: w.el, shell: w, render, tick() {}, section: 'model' };
}
