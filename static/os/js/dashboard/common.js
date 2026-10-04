// Dashboard · small shared helpers: widget shell, states, time formatting, sparkline.

import { h, icon } from '../dom.js';
import { os } from '../ctx.js';

export const tzOffset = () => new Date().getTimezoneOffset();     // minutes, UTC minus local (what the server expects)

// ----------------------------------------------------------------- time
export function timeLabel(ms) {
  return new Date(ms).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }).replace(/\s?([AP])M$/i, (_, a) => ` ${a.toLowerCase()}m`);
}

/** "now", "in 25 min", "in 2 h 5 min", "in 3 d" */
export function relFuture(ms, now = Date.now()) {
  const s = Math.round((ms - now) / 1000);
  if (s < 45) return 'now';
  const m = Math.round(s / 60);
  if (m < 60) return `in ${m} min`;
  const hr = Math.floor(m / 60);
  if (hr < 24) return `in ${hr} h${m % 60 ? ` ${m % 60} min` : ''}`;
  return `in ${Math.floor(hr / 24)} d`;
}

/** "just now", "12 min ago", "3 h ago", "yesterday", "4 d ago" */
export function relPast(ms, now = Date.now()) {
  const s = Math.round((now - ms) / 1000);
  if (s < 45) return 'just now';
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const hr = Math.floor(m / 60);
  if (hr < 24) return `${hr} h ago`;
  const d = Math.floor(hr / 24);
  return d === 1 ? 'yesterday' : `${d} d ago`;
}

/** mm:ss, or h:mm:ss from an hour up */
export function clock(ms) {
  const s = Math.max(0, Math.ceil(ms / 1000));
  const hr = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, '0');
  return hr ? `${hr}:${String(m).padStart(2, '0')}:${ss}` : `${String(m).padStart(2, '0')}:${ss}`;
}

/** Countdown wording for the agenda: ticking mm:ss inside the hour, words beyond it. */
export function untilLabel(ms, now = Date.now()) {
  const left = ms - now;
  if (left < 1000) return 'now';
  return left < 3600e3 ? `in ${clock(left)}` : relFuture(ms, now);
}

export function dayTime(ms, now = Date.now()) {
  const d = new Date(ms); const n = new Date(now);
  const key = (x) => x.getFullYear() * 400 + x.getMonth() * 32 + x.getDate();
  const tomorrow = new Date(n); tomorrow.setDate(n.getDate() + 1);
  const day = key(d) === key(n) ? 'Today' : key(d) === key(tomorrow) ? 'Tomorrow' : d.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' });
  return `${day}, ${timeLabel(ms)}`;
}

// ----------------------------------------------------------- widget shell
/** A calm panel: mono uppercase label, optional count, "Open" link to the related app. */
export function makeWidget({ key, title, openApp, openProps, openLabel = 'Open' }) {
  const count = h('span', { class: 'tw-count mono', hidden: true });
  const open = openApp
    ? h('button', { class: 'tw-open', type: 'button', 'aria-label': `Open ${title.toLowerCase()}`, dataset: { open: key }, on: { click: () => os.openApp(openApp, typeof openProps === 'function' ? openProps() : openProps) } }, openLabel, icon('arrow-right', 12))
    : null;
  const body = h('div', { class: 'tw-body' });
  const stateHost = h('div', { class: 'tw-state', hidden: true });
  const el = h('section', { class: ['tw', `tw-${key}`], dataset: { widget: key }, 'aria-label': title }, h('header', { class: 'tw-head' }, h('h3', { class: 'tw-label mono', text: title }), count, h('span', { class: 'win-spacer' }), open), stateHost, body);
  return {
    el, body,
    setCount(text) { count.textContent = text == null ? '' : String(text); count.hidden = text == null || text === ''; },
    /** Replace the content with a loading / error node (the body keeps its state underneath). */
    showState(node) { stateHost.replaceChildren(node); stateHost.hidden = false; body.hidden = true; },
    showBody() { if (!stateHost.hidden) { stateHost.hidden = true; stateHost.replaceChildren(); } body.hidden = false; },
  };
}

export const skeleton = (rows = 3) => h('div', { class: 'tw-skel', 'aria-hidden': 'true', dataset: { state: 'loading' } },
  Array.from({ length: rows }, (_, i) => h('span', { class: 'sk', style: { width: `${92 - i * 16}%` } })));

export const emptyState = (text, cta, onCta) => h('div', { class: 'tw-empty', dataset: { state: 'empty' } },
  h('p', { class: 'muted', text }),
  cta ? h('button', { class: 'btn btn-soft btn-sm', type: 'button', text: cta, on: { click: onCta } }) : null);

export const errorState = (message, onRetry) => h('div', { class: 'tw-error', role: 'alert', dataset: { state: 'error' } },
  h('p', { text: message || 'Something went wrong.' }),
  h('button', { class: 'btn btn-soft btn-sm', type: 'button', text: 'Retry', on: { click: onRetry } }));

// ---------------------------------------------------------------- sparkline
const SVG = 'http://www.w3.org/2000/svg';
/** Tiny inline line chart for 0-100 values. Returns {el, set(values)}. */
export function sparkline({ width = 120, height = 26 } = {}) {
  const svg = document.createElementNS(SVG, 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', height);
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('aria-hidden', 'true');
  svg.classList.add('spark');
  const area = document.createElementNS(SVG, 'polygon');
  const line = document.createElementNS(SVG, 'polyline');
  svg.append(area, line);
  return {
    el: svg,
    set(values) {
      if (values.length < 2) { line.setAttribute('points', ''); area.setAttribute('points', ''); return; }
      const step = width / (values.length - 1);
      const pts = values.map((v, i) => `${(i * step).toFixed(1)},${(height - 2 - (Math.min(100, Math.max(0, v)) / 100) * (height - 4)).toFixed(1)}`);
      line.setAttribute('points', pts.join(' '));
      area.setAttribute('points', `0,${height} ${pts.join(' ')} ${width},${height}`);
    },
  };
}

export const pluralize = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
