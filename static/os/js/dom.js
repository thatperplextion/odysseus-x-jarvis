// Small DOM toolkit for the Odysseus OS shell.
//
// Everything is built with createElement/textContent: file names, process command
// lines and terminal output are untrusted, so nothing here ever uses innerHTML.

const SVG_NS = 'http://www.w3.org/2000/svg';

/** h('div', {class:'a', on:{click:fn}, text:'x'}, child, 'text', [more]) */
export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === 'class') el.className = Array.isArray(v) ? v.filter(Boolean).join(' ') : v;
      else if (k === 'text') el.textContent = v;
      else if (k === 'on') for (const [ev, fn] of Object.entries(v)) el.addEventListener(ev, fn);
      else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
      else if (k === 'dataset') Object.assign(el.dataset, v);
      else if (k === 'value') el.value = v;
      else if (k === 'checked' || k === 'disabled' || k === 'hidden' || k === 'readOnly' || k === 'selected') el[k] = !!v;
      else el.setAttribute(k, v === true ? '' : String(v));
    }
  }
  append(el, children);
  return el;
}

export function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }

// ---------------------------------------------------------------- icons
// 24x24 monoline glyphs drawn from basic primitives; colour comes from currentColor.
const ICONS = {
  folder: [['path', 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z']],
  file: [['path', 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z'], ['path', 'M14 3v5h5']],
  'file-text': [['path', 'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z'], ['path', 'M14 3v5h5'], ['path', 'M9 13h6M9 17h6']],
  terminal: [['rect', { x: 3, y: 4, width: 18, height: 16, rx: 2.5 }], ['path', 'M7 9.5l3 2.5-3 2.5M13 15h4']],
  activity: [['path', 'M3 12h4l3-8 4 16 3-8h4']],
  sliders: [['path', 'M4 7h9M17 7h3M4 17h3M11 17h9'], ['circle', { cx: 15, cy: 7, r: 2 }], ['circle', { cx: 9, cy: 17, r: 2 }]],
  sparkles: [['path', 'M11 3l1.9 5.1L18 10l-5.1 1.9L11 17l-1.9-5.1L4 10l5.1-1.9z'], ['path', 'M19 15v5M16.5 17.5h5']],
  image: [['rect', { x: 3, y: 4, width: 18, height: 16, rx: 2.5 }], ['circle', { cx: 9, cy: 10, r: 1.6 }], ['path', 'M21 16l-5-5-9 9']],
  music: [['path', 'M9 18V6l11-2v12'], ['circle', { cx: 6.5, cy: 18, r: 2.5 }], ['circle', { cx: 17.5, cy: 16, r: 2.5 }]],
  film: [['rect', { x: 3, y: 5, width: 18, height: 14, rx: 2.5 }], ['path', 'M10 9.5v5l4.5-2.5z']],
  search: [['circle', { cx: 11, cy: 11, r: 6 }], ['path', 'M20 20l-4.2-4.2']],
  bell: [['path', 'M6 9a6 6 0 0 1 12 0c0 6 2 7 2 7H4s2-1 2-7z'], ['path', 'M10 20a2 2 0 0 0 4 0']],
  sun: [['circle', { cx: 12, cy: 12, r: 4 }], ['path', 'M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4']],
  moon: [['path', 'M20 14.5A8 8 0 1 1 9.5 4 6.5 6.5 0 0 0 20 14.5z']],
  plus: [['path', 'M12 5v14M5 12h14']],
  x: [['path', 'M6 6l12 12M18 6L6 18']],
  minus: [['path', 'M5 12h14']],
  maximize: [['rect', { x: 5, y: 5, width: 14, height: 14, rx: 2 }]],
  restore: [['rect', { x: 8, y: 8, width: 11, height: 11, rx: 2 }], ['path', 'M5 15V7a2 2 0 0 1 2-2h8']],
  'chevron-left': [['path', 'M15 5l-7 7 7 7']],
  'chevron-right': [['path', 'M9 5l7 7-7 7']],
  'chevron-down': [['path', 'M5 9l7 7 7-7']],
  'chevron-up': [['path', 'M5 15l7-7 7 7']],
  'arrow-left': [['path', 'M19 12H5M11 6l-6 6 6 6']],
  'arrow-right': [['path', 'M5 12h14M13 6l6 6-6 6']],
  'arrow-up': [['path', 'M12 19V5M6 11l6-6 6 6']],
  refresh: [['path', 'M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6']],
  upload: [['path', 'M12 16V4M7 9l5-5 5 5M4 20h16']],
  download: [['path', 'M12 4v12M7 11l5 5 5-5M4 20h16']],
  trash: [['path', 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6']],
  edit: [['path', 'M4 20h4L19 9l-4-4L4 16z']],
  copy: [['rect', { x: 9, y: 9, width: 11, height: 11, rx: 2 }], ['path', 'M5 15V6a2 2 0 0 1 2-2h9']],
  scissors: [['circle', { cx: 6, cy: 6, r: 2.5 }], ['circle', { cx: 6, cy: 18, r: 2.5 }], ['path', 'M8 8l12 10M8 16L20 6']],
  clipboard: [['rect', { x: 6, y: 5, width: 12, height: 16, rx: 2 }], ['path', 'M9 5V3h6v2M9 11h6M9 15h4']],
  grid: [['rect', { x: 4, y: 4, width: 7, height: 7, rx: 1.5 }], ['rect', { x: 13, y: 4, width: 7, height: 7, rx: 1.5 }], ['rect', { x: 4, y: 13, width: 7, height: 7, rx: 1.5 }], ['rect', { x: 13, y: 13, width: 7, height: 7, rx: 1.5 }]],
  list: [['path', 'M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01']],
  message: [['path', 'M4 5h16v11H9l-5 4z']],
  mail: [['rect', { x: 3, y: 5, width: 18, height: 14, rx: 2.5 }], ['path', 'M3.5 7.5L12 13l8.5-5.5']],
  calendar: [['rect', { x: 3, y: 5, width: 18, height: 16, rx: 2.5 }], ['path', 'M3 10h18M8 3v4M16 3v4']],
  note: [['path', 'M5 4h14v12l-4 4H5z'], ['path', 'M15 20v-4h4M8 9h8M8 13h5']],
  database: [['ellipse', { cx: 12, cy: 6, rx: 7, ry: 3 }], ['path', 'M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6']],
  'check-square': [['rect', { x: 4, y: 4, width: 16, height: 16, rx: 3 }], ['path', 'M8.5 12l2.5 2.5 4.5-5']],
  flask: [['path', 'M9 3h6M10 3v6L5 19a1.5 1.5 0 0 0 1.3 2h11.4A1.5 1.5 0 0 0 19 19l-5-10V3'], ['path', 'M7.5 15h9']],
  book: [['path', 'M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z'], ['path', 'M5 17a3 3 0 0 1 3-3h11']],
  globe: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', 'M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18']],
  lock: [['rect', { x: 5, y: 11, width: 14, height: 9, rx: 2 }], ['path', 'M8 11V8a4 4 0 0 1 8 0v3']],
  check: [['path', 'M5 12.5l4.5 4.5L19 7']],
  alert: [['path', 'M12 4l9.5 16h-19z'], ['path', 'M12 10v4M12 17.2v.3']],
  info: [['circle', { cx: 12, cy: 12, r: 9 }], ['path', 'M12 11v6M12 7.5v.3']],
  play: [['path', 'M8 5l11 7-11 7z']],
  stop: [['rect', { x: 6, y: 6, width: 12, height: 12, rx: 2 }]],
  more: [['path', 'M5 12h.01M12 12h.01M19 12h.01']],
  external: [['path', 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5']],
  cpu: [['rect', { x: 7, y: 7, width: 10, height: 10, rx: 2 }], ['path', 'M10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4']],
  power: [['path', 'M12 3v8'], ['path', 'M7 6.5A8 8 0 1 0 17 6.5']],
  user: [['circle', { cx: 12, cy: 8, r: 4 }], ['path', 'M4 21c1-4 4-6 8-6s7 2 8 6']],
  save: [['path', 'M5 4h11l4 4v12H5z'], ['path', 'M8 4v5h7V4M8 20v-6h8v6']],
  home: [['path', 'M4 11l8-7 8 7v9a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z']],
  drive: [['rect', { x: 3, y: 12, width: 18, height: 7, rx: 2 }], ['path', 'M5 12l2-7h10l2 7M17 15.5h.01']],
  star: [['path', 'M12 4l2.4 5 5.6.7-4.1 3.8 1.1 5.5L12 16.3 7 19l1.1-5.5L4 9.7 9.6 9z']],
  shield: [['path', 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z'], ['path', 'M9 12l2 2 4-4']],
  eye: [['path', 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z'], ['circle', { cx: 12, cy: 12, r: 3 }]],
  command: [['path', 'M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z']],
  zap: [['path', 'M13 3L5 13.5h6L10.5 21l8-10.5h-6z']],
  link: [['path', 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1']],
  clock: [['circle', { cx: 12, cy: 12, r: 8.5 }], ['path', 'M12 7.5V12l3 2']],
};

export function icon(name, size = 18, cls = '') {
  const def = ICONS[name] || ICONS.file;
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.6');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  if (cls) svg.setAttribute('class', cls);
  for (const [tag, spec] of def) {
    const node = document.createElementNS(SVG_NS, tag);
    if (typeof spec === 'string') node.setAttribute('d', spec);
    else for (const [k, v] of Object.entries(spec)) node.setAttribute(k, v);
    svg.append(node);
  }
  return svg;
}

export const hasIcon = (name) => name in ICONS;

// -------------------------------------------------------------- formatting
export function fmtBytes(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return '';
  if (n < 1024) return `${Math.round(n)} B`;   // rates arrive as floats ("266.28068 B/s")
  const units = ['KB', 'MB', 'GB', 'TB'];
  let v = n / 1024, i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v.toFixed(2)} ${units[i]}`;
}

export function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  const sameYear = d.getFullYear() === now.getFullYear();
  return d.toLocaleDateString([], sameYear ? { month: 'short', day: 'numeric' } : { year: 'numeric', month: 'short', day: 'numeric' });
}

export function fmtDuration(sec) {
  sec = Math.max(0, Math.floor(sec));
  const d = Math.floor(sec / 86400), hr = Math.floor((sec % 86400) / 3600), m = Math.floor((sec % 3600) / 60);
  if (d) return `${d}d ${hr}h`;
  if (hr) return `${hr}h ${m}m`;
  if (m) return `${m}m ${sec % 60}s`;
  return `${sec}s`;
}

export const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);

export function debounce(fn, ms) {
  let t;
  const wrapped = (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
  wrapped.cancel = () => clearTimeout(t);
  return wrapped;
}

export function basename(p) { return (p || '').replace(/\/+$/, '').split('/').pop() || p; }
export function dirname(p) { const parts = p.replace(/\/+$/, '').split('/'); parts.pop(); return parts.join('/') || '/'; }
export function extname(name) { const i = name.lastIndexOf('.'); return i > 0 ? name.slice(i + 1).toLowerCase() : ''; }
export function joinPath(dir, name) { return dir.replace(/\/+$/, '') + '/' + name; }

// ---------------------------------------------------------------- overlays
const overlayRoot = () => document.getElementById('overlays');

let toastHost;
let toastGate = null;
/** netui.js installs a gate that holds error toasts back while the server is unreachable (the banner says it once).
 *  The gate returns true (show), false (drop) or {message, kind} (show that instead). */
export function setToastGate(fn) { toastGate = fn; }
export function toast(message, { kind = 'info', action, ms = 4200 } = {}) {
  const verdict = toastGate ? toastGate(message, { kind, action, ms }) : true;
  if (verdict === false) return { close() {}, el: null };
  if (verdict && typeof verdict === 'object') ({ message = message, kind = kind } = verdict);
  if (!toastHost) {
    toastHost = h('div', { class: 'toasts', role: 'status', 'aria-live': 'polite' });
    overlayRoot().append(toastHost);
  }
  const el = h('div', { class: ['toast', `toast-${kind}`] },
    icon(kind === 'error' ? 'alert' : kind === 'ok' ? 'check' : 'info', 16),
    h('span', { class: 'toast-msg', text: message }),
    action && h('button', { class: 'toast-action', text: action.label, on: { click: () => { action.run(); close(); } } }),
  );
  const close = () => { el.classList.add('out'); setTimeout(() => el.remove(), 180); };
  toastHost.append(el);
  if (ms) setTimeout(close, ms);
  return { close, el };
}

/** Modal dialog. Resolves with whatever `result()` returns for the pressed button, or null on cancel. */
function modal({ title, body, buttons, onOpen, width = 420 }) {
  return new Promise((resolve) => {
    const previouslyFocused = document.activeElement;
    const backdrop = h('div', { class: 'modal-backdrop' });
    const box = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': title, style: { width: `${width}px` } },
      h('h2', { class: 'modal-title', text: title }),
      h('div', { class: 'modal-body' }, body),
      h('div', { class: 'modal-actions' }),
    );
    const finish = (value) => {
      backdrop.remove();
      document.removeEventListener('keydown', onKey, true);
      if (previouslyFocused && previouslyFocused.focus) previouslyFocused.focus();
      resolve(value);
    };
    const actions = box.querySelector('.modal-actions');
    let primary = null;
    for (const b of buttons) {
      const btn = h('button', {
        class: ['btn', b.kind === 'primary' ? 'btn-ink' : b.kind === 'danger' ? 'btn-danger' : 'btn-ghost'],
        text: b.label,
        on: { click: () => { const r = b.result ? b.result() : b.value; if (r !== undefined) finish(r); } },
      });
      if (b.kind === 'primary' || b.kind === 'danger') primary = primary || btn;
      actions.append(btn);
    }
    const onKey = (e) => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); finish(null); }
      else if (e.key === 'Enter' && !(e.target instanceof HTMLTextAreaElement) && primary) { e.preventDefault(); primary.click(); }
      else if (e.key === 'Tab') {  // keep focus inside the dialog
        const focusables = [...box.querySelectorAll('button, input, select, textarea')].filter((x) => !x.disabled);
        if (!focusables.length) return;
        const first = focusables[0], last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', onKey, true);
    backdrop.addEventListener('pointerdown', (e) => { if (e.target === backdrop) finish(null); });
    backdrop.append(box);
    overlayRoot().append(backdrop);
    if (onOpen) onOpen(box);
    else (primary || box.querySelector('button'))?.focus();
  });
}

export const dialog = {
  confirm(title, message, { confirmLabel = 'OK', danger = false, detail } = {}) {
    return modal({
      title,
      body: [h('p', { class: 'modal-text', text: message }), detail && h('pre', { class: 'modal-detail', text: detail })],
      buttons: [
        { label: 'Cancel', value: false },
        { label: confirmLabel, kind: danger ? 'danger' : 'primary', value: true },
      ],
    }).then((v) => v === true);
  },

  prompt(title, { label = '', value = '', placeholder = '', confirmLabel = 'OK', select = true, validate } = {}) {
    const input = h('input', { class: 'input', type: 'text', value, placeholder, spellcheck: 'false', autocomplete: 'off' });
    const error = h('div', { class: 'modal-error', text: '', hidden: true });
    return modal({
      title,
      body: [label && h('label', { class: 'modal-label', text: label }), input, error],
      buttons: [
        { label: 'Cancel', value: null },
        {
          label: confirmLabel, kind: 'primary',
          result: () => {
            const v = input.value;
            const problem = validate ? validate(v) : null;
            if (problem) { error.textContent = problem; error.hidden = false; input.focus(); return undefined; }
            return v;
          },
        },
      ],
      onOpen: () => {
        input.focus();
        if (select) {
          const dot = value.lastIndexOf('.');
          input.setSelectionRange(0, dot > 0 ? dot : value.length);
        }
      },
    });
  },

  /** Pick one of several actions. buttons: [{label, value, kind}] */
  choose(title, message, buttons, { detail } = {}) {
    return modal({
      title,
      body: [h('p', { class: 'modal-text', text: message }), detail && h('pre', { class: 'modal-detail', text: detail })],
      buttons,
    });
  },

  alert(title, message, { detail } = {}) {
    return modal({
      title,
      body: [h('p', { class: 'modal-text', text: message }), detail && h('pre', { class: 'modal-detail', text: detail })],
      buttons: [{ label: 'OK', kind: 'primary', value: true }],
    });
  },
};

// ------------------------------------------------------------ context menu
let openMenu = null;
export function closeContextMenu() { if (openMenu) { openMenu.remove(); openMenu = null; } }

/** items: [{label, icon, run, danger, disabled, hint}] | 'sep' */
export function contextMenu(x, y, items) {
  closeContextMenu();
  const menu = h('div', { class: 'ctx', role: 'menu' });
  for (const it of items) {
    if (it === 'sep') { menu.append(h('div', { class: 'ctx-sep', role: 'separator' })); continue; }
    menu.append(h('button', {
      class: ['ctx-item', it.danger && 'danger'], role: 'menuitem', disabled: it.disabled,
      on: { click: () => { closeContextMenu(); it.run && it.run(); } },
    }, it.icon ? icon(it.icon, 15) : h('span', { class: 'ctx-pad' }), h('span', { class: 'ctx-label', text: it.label }), it.hint && h('span', { class: 'ctx-hint', text: it.hint })));
  }
  overlayRoot().append(menu);
  const r = menu.getBoundingClientRect();
  menu.style.left = `${clamp(x, 6, window.innerWidth - r.width - 6)}px`;
  menu.style.top = `${clamp(y, 6, window.innerHeight - r.height - 6)}px`;
  openMenu = menu;
  menu.querySelector('.ctx-item:not([disabled])')?.focus();
  menu.addEventListener('keydown', (e) => {
    const items = [...menu.querySelectorAll('.ctx-item:not([disabled])')];
    const i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length]?.focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length]?.focus(); }
    else if (e.key === 'Escape') { closeContextMenu(); }
  });
  return menu;
}

document.addEventListener('pointerdown', (e) => { if (openMenu && !openMenu.contains(e.target)) closeContextMenu(); }, true);
window.addEventListener('blur', closeContextMenu);
window.addEventListener('resize', closeContextMenu);
