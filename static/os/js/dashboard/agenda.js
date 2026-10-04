// Dashboard · Agenda: today + tomorrow as a timeline, a next-up card with a live countdown.

import { h, icon, clear, toast } from '../dom.js';
import { os } from '../ctx.js';
import { makeWidget, emptyState, timeLabel, untilLabel } from './common.js';
import { nextUp } from './store.js';
import { notesApi } from './http.js';

const MAX_TODAY = 6;
const MAX_TOMORROW = 3;

export function createAgenda({ refresh, capture }) {
  const w = makeWidget({ key: 'agenda', title: 'AGENDA', openApp: 'calendar' });
  const next = h('div', { class: 'ag-next', hidden: true });
  const list = h('div', { class: 'ag-list' });
  w.body.append(next, list);
  let sec = null;
  let sig = '';
  let nextEls = null;

  const openCalendar = () => os.openApp('calendar');

  function row(item, now) {
    const isReminder = item.kind === 'reminder';
    const end = item.end_ts || item.start_ts;
    const when = item.all_day ? 'All day' : timeLabel(item.start_ts);
    const hit = h('button', { class: 'ag-hit', type: 'button', title: isReminder ? 'Open Notes' : 'Open Calendar', on: { click: () => os.openApp(isReminder ? 'notes' : 'calendar') } },
      h('span', { class: 'ag-time mono', text: when }),
      h('span', { class: 'ag-main' },
        h('span', { class: 'ag-title' }, isReminder ? icon('bell', 12) : null, h('span', { text: item.summary })),
        item.location ? h('span', { class: 'ag-sub muted', text: item.location }) : null));
    const done = isReminder ? h('button', { class: 'icon-btn ag-done', type: 'button', 'aria-label': `Mark reminder done: ${item.summary}`, title: 'Done',
      on: { click: async () => {
        try { await notesApi.archive(item.id); toast('Reminder cleared', { kind: 'ok', ms: 1800 }); } catch (e) { toast(e.message, { kind: 'error' }); }
        refresh();
      } } }, icon('check', 14)) : null;
    const el = h('div', { class: ['ag-row', isReminder && 'is-reminder'], dataset: { kind: item.kind, start: item.start_ts, end, allDay: item.all_day ? '1' : '' } }, hit, done);
    classify(el, now);
    return el;
  }

  function classify(el, now) {
    if (el.dataset.allDay) return;
    const start = Number(el.dataset.start); const end = Number(el.dataset.end);
    const isReminder = el.dataset.kind === 'reminder';
    el.classList.toggle('past', !isReminder && end <= now);
    el.classList.toggle('now', !isReminder && start <= now && now < end);
    el.classList.toggle('due', isReminder && start <= now);
  }

  function group(label, items, max, now) {
    if (!items.length) return null;
    const shown = items.slice(0, max);
    return h('div', { class: 'ag-group', dataset: { group: label.toLowerCase() } },
      h('div', { class: 'ag-gl mono', text: `${label} · ${items.length}` }),
      shown.map((i) => row(i, now)),
      items.length > shown.length ? h('button', { class: 'ag-more', type: 'button', text: `+${items.length - shown.length} more`, on: { click: openCalendar } }) : null);
  }

  function renderNext(now) {
    if (!sec) return;
    const nu = nextUp(sec, now);
    next.hidden = false;
    clear(next);
    nextEls = null;
    if (!nu || nu.day !== 'today') {
      const tomorrow = sec.events.filter((e) => e.day === 'tomorrow').length;
      next.append(h('div', { class: 'ag-next-empty' },
        h('span', { class: 'ag-kicker mono', text: 'NEXT UP' }),
        h('span', { class: 'ag-next-title', text: 'Nothing else today' }),
        tomorrow ? h('span', { class: 'ag-sub muted', text: `${tomorrow} tomorrow` }) : null));
      return;
    }
    const ongoing = nu.kind === 'event' && nu.start_ts <= now;
    const until = h('span', { class: 'ag-count mono', text: ongoing ? 'now' : untilLabel(nu.start_ts, now) });
    nextEls = { until, nu, ongoing };
    const range = nu.kind === 'reminder' ? timeLabel(nu.start_ts) : `${timeLabel(nu.start_ts)} – ${timeLabel(nu.end_ts)}`;
    next.append(h('button', { class: 'ag-next-card', type: 'button', title: 'Open Calendar', on: { click: () => os.openApp(nu.kind === 'reminder' ? 'notes' : 'calendar') } },
      h('span', { class: 'ag-kicker mono', text: ongoing ? 'HAPPENING NOW' : nu.kind === 'reminder' ? 'REMINDER' : 'NEXT UP' }),
      h('span', { class: 'ag-next-title', text: nu.summary }),
      h('span', { class: 'ag-sub muted', text: nu.location ? `${range} · ${nu.location}` : range }),
      until));
  }

  function render(data) {
    sec = data;
    const now = Date.now();
    const all = [...data.events, ...(data.reminders || [])];
    const nextKey = (() => { const nu = nextUp(data, now); return nu ? `${nu.kind}:${nu.uid || nu.id}` : ''; })();
    const nextSig = JSON.stringify([all.map((e) => [e.uid || e.id, e.summary, e.start_ts, e.end_ts, e.day]), nextKey]);
    if (nextSig === sig) return;
    sig = nextSig;
    w.setCount(data.today_count + (data.today_reminders || 0) ? `${data.today_count + (data.today_reminders || 0)} today` : null);
    clear(list);
    if (!all.length) {
      next.hidden = true;
      list.append(emptyState('Your calendar is clear for the next two days.', 'Add an event', () => capture.prefill('Event: ')));
      return;
    }
    renderNext(now);
    const byDay = (d) => all.filter((e) => e.day === d).sort((a, b) => (b.all_day ? 1 : 0) - (a.all_day ? 1 : 0) || a.start_ts - b.start_ts);
    list.append(...[group('Today', byDay('today'), MAX_TODAY, now), group('Tomorrow', byDay('tomorrow'), MAX_TOMORROW, now)].filter(Boolean));
  }

  function tick(now) {
    if (!sec) return;
    for (const el of list.querySelectorAll('.ag-row')) classify(el, now);
    if (!nextEls) return;
    const { until, nu, ongoing } = nextEls;
    const current = nextUp(sec, now);
    const started = nu.kind === 'event' && nu.start_ts <= now;
    if (!current || current.kind !== nu.kind || (current.uid || current.id) !== (nu.uid || nu.id) || started !== ongoing) { renderNext(now); return; }
    const label = ongoing ? 'now' : untilLabel(nu.start_ts, now);
    if (until.textContent !== label) until.textContent = label;
  }

  return { el: w.el, shell: w, render, tick, section: 'agenda' };
}
