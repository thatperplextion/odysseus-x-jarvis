// Dashboard · Focus: a 25/5 pomodoro. The timer lives in a controller, not in the widget, so it keeps running
// (and still announces its end) while windows cover the desktop, and it survives a page reload because its
// state is kept in localStorage (every access wrapped: private windows throw).

import { h, toast } from '../dom.js';
import { post } from '../api.js';
import { makeWidget, clock, tzOffset } from './common.js';

const KEY = 'ody.os.focus.v1';
const DONE_KEY = 'ody.os.focus.done';
export const MODES = { focus: { label: 'Focus', minutes: 25 }, break: { label: 'Break', minutes: 5 } };

const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch { return null; } };
const write = (v) => { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch { /* storage unavailable: the timer still works in memory */ } };
const readDone = () => { try { return localStorage.getItem(DONE_KEY) || ''; } catch { return ''; } };
const writeDone = (v) => { try { localStorage.setItem(DONE_KEY, String(v)); } catch { /* ignore */ } };

function blank(mode = 'focus', label = '') {
  const durationMs = MODES[mode].minutes * 60e3;
  return { mode, status: 'idle', durationMs, remainingMs: durationMs, endsAt: null, startedAt: null, label };
}

/** @returns the singleton timer controller */
export function createFocusController({ onLogged } = {}) {
  let s = blank();
  const saved = read();
  if (saved && MODES[saved.mode] && ['idle', 'running', 'paused'].includes(saved.status)) s = { ...blank(saved.mode), ...saved };
  const subs = new Set();
  const emit = () => { write(s); subs.forEach((fn) => { try { fn(s); } catch (e) { console.error(e); } }); };

  const remaining = (now = Date.now()) => (s.status === 'running' ? Math.max(0, s.endsAt - now) : s.remainingMs);

  function start() {
    if (s.status === 'running') return;
    if (s.status === 'idle') s = { ...s, startedAt: Date.now(), remainingMs: s.durationMs };
    s = { ...s, status: 'running', endsAt: Date.now() + s.remainingMs };
    emit();
  }
  function pause() {
    if (s.status !== 'running') return;
    s = { ...s, status: 'paused', remainingMs: remaining(), endsAt: null };
    emit();
  }
  function toggle() { if (s.status === 'running') pause(); else start(); }

  async function logSession(session, minutes, completed) {
    if (session.mode !== 'focus' || minutes < 1 / 6) return;
    try {
      await post('/focus', { minutes: Math.round(minutes * 100) / 100, label: session.label || '', completed, tz_offset: tzOffset() });
      onLogged?.();
    } catch (e) { toast(`Couldn’t save that focus session: ${e.message}`, { kind: 'error' }); }
  }

  function reset() {
    if (s.status !== 'idle' && s.mode === 'focus') {
      const elapsed = (s.durationMs - remaining()) / 60e3;
      if (elapsed >= 1) logSession(s, elapsed, false);        // the minutes still happened; they just don't count as a finished session
    }
    s = blank(s.mode, s.label);
    emit();
  }
  function setMode(mode) {
    if (!MODES[mode] || s.mode === mode) return;
    s = blank(mode, s.label);
    emit();
  }
  function setLabel(label) { s = { ...s, label: label.slice(0, 120) }; write(s); }

  function complete() {
    const finished = s;
    const marker = `${finished.startedAt}:${finished.mode}`;
    if (readDone() === marker) { s = blank(finished.mode === 'focus' ? 'break' : 'focus', finished.label); emit(); return; }     // another tab already announced it
    writeDone(marker);
    const minutes = finished.durationMs / 60e3;
    const next = finished.mode === 'focus' ? 'break' : 'focus';
    s = blank(next, finished.label);
    emit();
    const title = finished.mode === 'focus' ? 'Focus session complete' : 'Break is over';
    const message = finished.mode === 'focus'
      ? `${minutes} minutes${finished.label ? ` on “${finished.label}”` : ''}. Take a ${MODES.break.minutes}-minute break.`
      : 'Ready for another focus session?';
    toast(`${title}. ${finished.mode === 'focus' ? 'Time for a break.' : 'Ready when you are.'}`, { kind: 'ok', ms: 9000, action: { label: next === 'break' ? 'Start break' : 'Start focus', run: start } });
    post('/notify', { title, message, severity: 'success', key: `focus:${marker}` }).catch(() => {});
    try {
      if (typeof Notification !== 'undefined' && Notification.permission === 'granted') new Notification(title, { body: message, tag: 'odysseus-focus' });
    } catch { /* some browsers only allow it from a service worker */ }
    logSession(finished, minutes, true);
  }

  /** Called every second by the desktop; also right after load so a session that ended while the page was closed is announced. */
  function tick(now = Date.now()) {
    if (s.status === 'running' && now >= s.endsAt) complete();
  }

  return {
    get state() { return s; },
    remaining, start, pause, toggle, reset, setMode, setLabel, tick,
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
  };
}

// ------------------------------------------------------------------ widget
const R = 44;
const C = 2 * Math.PI * R;

export function createFocusWidget({ ctl }) {
  const w = makeWidget({ key: 'focus', title: 'FOCUS' });
  const SVG = 'http://www.w3.org/2000/svg';
  const ring = document.createElementNS(SVG, 'svg');
  ring.setAttribute('viewBox', '0 0 100 100');
  ring.setAttribute('class', 'fo-ring');
  ring.setAttribute('aria-hidden', 'true');
  const track = document.createElementNS(SVG, 'circle');
  const bar = document.createElementNS(SVG, 'circle');
  for (const c of [track, bar]) { c.setAttribute('cx', '50'); c.setAttribute('cy', '50'); c.setAttribute('r', String(R)); c.setAttribute('fill', 'none'); c.setAttribute('stroke-width', '5'); }
  track.setAttribute('class', 'fo-track');
  bar.setAttribute('class', 'fo-bar');
  bar.setAttribute('stroke-linecap', 'round');
  bar.setAttribute('stroke-dasharray', String(C));
  bar.setAttribute('transform', 'rotate(-90 50 50)');
  ring.append(track, bar);

  const time = h('div', { class: 'fo-time mono', role: 'timer', 'aria-label': 'Time remaining' });
  const mode = h('div', { class: 'fo-mode mono' });
  const dial = h('div', { class: 'fo-dial' }, ring, h('div', { class: 'fo-center' }, time, mode));
  const label = h('input', { class: 'input fo-label', type: 'text', placeholder: 'What are you working on?', 'aria-label': 'Focus label', maxlength: 120, autocomplete: 'off', spellcheck: 'false',
    on: { input: (e) => ctl.setLabel(e.target.value) } });
  const startBtn = h('button', { class: 'btn btn-ink btn-sm fo-start', type: 'button', dataset: { action: 'focus-toggle' }, on: { click: () => { ctl.toggle(); } } });
  const resetBtn = h('button', { class: 'btn btn-soft btn-sm fo-reset', type: 'button', dataset: { action: 'focus-reset' }, text: 'Reset', on: { click: () => ctl.reset() } });
  const modes = h('div', { class: 'segmented fo-modes', role: 'radiogroup', 'aria-label': 'Timer mode' }, Object.entries(MODES).map(([id, m]) =>
    h('button', { class: 'seg', type: 'button', role: 'radio', dataset: { mode: id }, text: `${m.label} ${m.minutes}`, on: { click: () => ctl.setMode(id) } })));
  const today = h('div', { class: 'fo-today muted mono' });
  const alerts = h('button', { class: 'fo-alerts', type: 'button', text: 'Allow desktop alerts', hidden: true, on: { click: async () => {
    try { await Notification.requestPermission(); } catch { /* ignore */ }
    paintAlerts();
  } } });
  w.body.append(h('div', { class: 'fo-main' }, dial, h('div', { class: 'fo-side' }, modes, label, h('div', { class: 'fo-actions' }, startBtn, resetBtn))), today, alerts);

  function paintAlerts() { alerts.hidden = !(typeof Notification !== 'undefined' && Notification.permission === 'default'); }

  function paint() {
    const s = ctl.state;
    const left = ctl.remaining();
    time.textContent = clock(left);
    mode.textContent = s.status === 'paused' ? `${MODES[s.mode].label.toUpperCase()} · PAUSED` : MODES[s.mode].label.toUpperCase();
    bar.setAttribute('stroke-dashoffset', String(C * (1 - (s.durationMs - left) / s.durationMs)));
    startBtn.textContent = s.status === 'running' ? 'Pause' : s.status === 'paused' ? 'Resume' : 'Start';
    resetBtn.disabled = s.status === 'idle';
    w.el.dataset.status = s.status;
    w.el.dataset.mode = s.mode;
    for (const b of modes.children) { const on = b.dataset.mode === s.mode; b.classList.toggle('on', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); }
    if (document.activeElement !== label && label.value !== s.label) label.value = s.label;
  }
  paint();
  paintAlerts();
  ctl.subscribe(paint);

  function render(sec) {
    const n = Math.round(sec.minutes_today || 0);
    today.textContent = n || sec.sessions_today ? `Today: ${n} min · ${sec.sessions_today} ${sec.sessions_today === 1 ? 'session' : 'sessions'}` : 'No focus sessions yet today.';
    w.setCount(null);
  }

  return { el: w.el, shell: w, render, tick: () => paint(), section: 'focus' };
}

/** The little "24:31" chip in the menu bar while a timer is running or paused, so it stays visible behind windows. */
export function createFocusChip({ ctl }) {
  const text = h('span', { class: 'mono' });
  const chip = h('button', { class: 'mb-focus', type: 'button', hidden: true, dataset: { chip: 'focus' }, on: { click: () => ctl.toggle() } }, h('i', { class: 'dot' }), text);
  function paint() {
    const s = ctl.state;
    chip.hidden = s.status === 'idle';
    chip.dataset.status = s.status;
    text.textContent = `${s.mode === 'break' ? 'Break' : 'Focus'} ${clock(ctl.remaining())}`;
    chip.title = s.status === 'running' ? 'Click to pause' : 'Click to resume';
    chip.setAttribute('aria-label', `${text.textContent}. ${chip.title}`);
  }
  paint();
  ctl.subscribe(paint);
  return { el: chip, tick: paint };
}
