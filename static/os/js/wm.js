// Window manager: drag, resize (8 handles), snap, maximise/minimise, z-order, focus.

import { h, icon, clamp, debounce } from './dom.js';
import { visibilityOf } from './suspender.js';

const MIN_W = 340;
const MIN_H = 220;
const TITLE_H = 38;
const NARROW = 720;
const SNAP_EDGE = 8;

let zCounter = 10;
let idCounter = 1;

export class Win {
  constructor(wm, spec) {
    this.wm = wm;
    this.id = `w${idCounter++}`;
    this.app = spec.app;
    this.title = spec.title || spec.app;
    this.iconName = spec.icon || 'file';
    this.props = spec.props || {};
    this.state = 'normal';           // normal | max | min
    this.rect = { x: 0, y: 0, w: spec.width || 760, h: spec.height || 520 };
    this.restoreRect = null;
    this.z = 0;
    this.handle = null;              // whatever the app's mount() returned
    this.focused = false;
    this.singletonKey = spec.singletonKey || null;
    this.createdAt = Date.now();
  }

  setTitle(title) {
    this.title = title;
    this.titleEl.textContent = title;
    this.el.setAttribute('aria-label', title);
    this.wm.emit('title', this);
  }

  setIcon(name) {
    this.iconName = name;
    this.iconEl.replaceChildren(icon(name, 15));
    this.wm.emit('title', this);
  }

  /** Extra title-bar button (before minimise/maximise/close). */
  addAction(iconName, label, run) {
    const btn = h('button', {
      class: ['win-btn', 'win-extra'], 'aria-label': label, title: label, tabindex: -1,
      on: { click: (e) => { e.stopPropagation(); run(); }, pointerdown: (e) => e.stopPropagation() },
    }, icon(iconName, 13));
    this.actionsEl.prepend(btn);
    return btn;
  }

  focus() { this.wm.focus(this); }
  minimize() { this.wm.minimize(this); }
  toggleMaximize() { this.wm.toggleMaximize(this); }
  close(opts) { return this.wm.close(this, opts); }
  serialize() { return { app: this.app, props: this.handle?.serialize ? this.handle.serialize() : this.props, rect: this.restoreRect || this.rect, state: this.state === 'min' ? 'normal' : this.state }; }
}

export class WindowManager {
  /**
   * @param host    element that positions windows (position: relative/absolute, overflow hidden)
   * @param options.onEvent (type, win) => void   open | close | focus | minimize | restore | title | change
   */
  constructor(host, { onEvent } = {}) {
    this.host = host;
    this.onEvent = onEvent || (() => {});
    this.wins = new Map();
    this.snapEl = h('div', { class: 'snap-preview', hidden: true });
    host.append(this.snapEl);
    this.emitChange = debounce(() => this.onEvent('change', null), 400);

    // Clicks inside an embedded app's <iframe> never reach us; the parent window blurs instead.
    window.addEventListener('blur', () => {
      const el = document.activeElement;
      if (el && el.tagName === 'IFRAME') {
        const win = [...this.wins.values()].find((w) => w.el.contains(el));
        if (win) this.focus(win, { keepFocus: true });
      }
    });
    window.addEventListener('resize', () => this.refit());
  }

  emit(type, win) {
    this.onEvent(type, win);
    if (type !== 'change') this.emitChange();
    if (type !== 'title') this.refreshVisibility();
  }

  /**
   * Tell each window's app whether anyone can see it: hidden when minimised, or when a maximised window above it covers all of
   * it (a maximised window fills the desktop above the dock, so a window that ends above that line is completely behind it).
   * Apps with heavy content (the embedded Odysseus pages) use `onVisibility(visible)` to go to sleep while they are hidden.
   */
  refreshVisibility() {
    const wins = this.list();
    const seen = visibilityOf(wins, this.bounds().h - this.dockReserve);
    wins.forEach((win, i) => {
      if (win.visible === seen[i]) return;
      win.visible = seen[i];
      try { win.handle?.onVisibility?.(seen[i]); } catch (e) { console.error(e); }
    });
  }

  get narrow() { return window.innerWidth < NARROW; }
  get dockReserve() { return parseFloat(getComputedStyle(this.host).getPropertyValue('--dock-reserve')) || 0; }
  bounds() { return { w: this.host.clientWidth, h: this.host.clientHeight }; }

  list() { return [...this.wins.values()]; }
  find(fn) { return this.list().find(fn); }
  top() {
    return this.list().filter((w) => w.state !== 'min').sort((a, b) => b.z - a.z)[0] || null;
  }

  // ------------------------------------------------------------------ open
  open(spec) {
    if (spec.singletonKey) {
      const existing = this.find((w) => w.singletonKey === spec.singletonKey);
      if (existing) {
        if (existing.state === 'min') this.restore(existing);
        this.focus(existing);
        if (spec.onReuse) spec.onReuse(existing);
        return existing;
      }
    }
    const win = new Win(this, spec);
    const b = this.bounds();
    const n = this.wins.size % 8;
    const w = clamp(spec.width || 760, MIN_W, Math.max(MIN_W, b.w - 24));
    const hgt = clamp(spec.height || 520, MIN_H, Math.max(MIN_H, b.h - this.dockReserve - 12));
    const rect = spec.rect || {
      w, h: hgt,
      x: spec.x ?? clamp(70 + n * 30, 8, Math.max(8, b.w - w - 8)),
      y: spec.y ?? clamp(24 + n * 28, 8, Math.max(8, b.h - this.dockReserve - hgt)),
    };
    win.rect = { ...rect };
    this.build(win);
    this.wins.set(win.id, win);
    this.host.append(win.el);
    this.apply(win);
    win.handle = spec.mount(win.body, win) || {};
    if (spec.state === 'max' || this.narrow) { win.restoreRect = { ...win.rect }; this.setState(win, 'max'); }
    this.focus(win);
    this.emit('open', win);
    return win;
  }

  build(win) {
    win.iconEl = h('span', { class: 'win-icon' }, icon(win.iconName, 15));
    win.titleEl = h('span', { class: 'win-title-text', text: win.title });
    const mkBtn = (cls, label, ic, run) => h('button', {
      class: ['win-btn', cls], 'aria-label': label, title: label, tabindex: -1,
      on: { click: (e) => { e.stopPropagation(); run(); }, pointerdown: (e) => e.stopPropagation() },
    }, icon(ic, 13));
    win.maxBtn = mkBtn('win-max', 'Maximize', 'maximize', () => this.toggleMaximize(win));
    win.actionsEl = h('div', { class: 'win-actions' },
      mkBtn('win-min', 'Minimize', 'minus', () => this.minimize(win)),
      win.maxBtn,
      mkBtn('win-close', 'Close', 'x', () => this.close(win)),
    );
    win.bar = h('div', { class: 'win-bar' },
      win.iconEl, win.titleEl,
      h('span', { class: 'win-spacer' }),
      win.actionsEl,
    );
    win.body = h('div', { class: 'win-body' });
    win.el = h('section', { class: ['win', `win-${win.app}`], role: 'dialog', 'aria-label': win.title, tabindex: '-1', dataset: { win: win.id, app: win.app } },
      win.bar, win.body);
    for (const dir of ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']) {
      const handle = h('div', { class: ['win-resize', `rz-${dir}`], dataset: { dir } });
      handle.addEventListener('pointerdown', (e) => this.startResize(win, dir, e));
      win.el.append(handle);
    }
    win.el.addEventListener('pointerdown', () => { if (!win.focused) this.focus(win, { keepFocus: true }); }, true);
    win.bar.addEventListener('pointerdown', (e) => this.startDrag(win, e));
    win.bar.addEventListener('dblclick', (e) => { if (!e.target.closest('.win-actions')) this.toggleMaximize(win); });
    win.el.addEventListener('keydown', (e) => {
      if (e.altKey && e.key.toLowerCase() === 'w') { e.preventDefault(); this.close(win); }
    });
    if (typeof ResizeObserver !== 'undefined') {
      new ResizeObserver(() => win.handle?.onResize?.()).observe(win.body);
    }
  }

  apply(win) {
    const s = win.el.style;
    if (win.state === 'max') { s.left = s.top = s.width = s.height = ''; }
    else {
      s.left = `${Math.round(win.rect.x)}px`;
      s.top = `${Math.round(win.rect.y)}px`;
      s.width = `${Math.round(win.rect.w)}px`;
      s.height = `${Math.round(win.rect.h)}px`;
    }
    s.zIndex = win.z;
  }

  // ----------------------------------------------------------------- state
  focus(win, { keepFocus = false } = {}) {
    if (win.state === 'min') this.restore(win);
    for (const w of this.wins.values()) {
      const f = w === win;
      if (w.focused !== f) { w.focused = f; w.el.classList.toggle('focused', f); }
    }
    win.z = ++zCounter;
    win.el.style.zIndex = win.z;
    if (!keepFocus && !win.el.contains(document.activeElement)) {
      (win.handle?.focus ? win.handle.focus() : win.el.focus({ preventScroll: true }));
    }
    win.handle?.onFocus?.();
    this.emit('focus', win);
  }

  minimize(win) {
    if (win.state === 'min') return;
    win.prevState = win.state;
    win.state = 'min';
    win.el.classList.add('min');
    win.focused = false;
    win.el.classList.remove('focused');
    win.handle?.onHide?.();
    const next = this.top();
    if (next) this.focus(next);
    this.emit('minimize', win);
  }

  restore(win) {
    if (win.state !== 'min') return;
    win.state = win.prevState || 'normal';
    win.el.classList.remove('min');
    win.handle?.onShow?.();
    this.emit('restore', win);
  }

  setState(win, state) {
    win.state = state;
    win.el.classList.toggle('max', state === 'max');
    win.maxBtn.replaceChildren(icon(state === 'max' ? 'restore' : 'maximize', 13));
    win.maxBtn.setAttribute('aria-label', state === 'max' ? 'Restore' : 'Maximize');
    this.apply(win);
    win.handle?.onResize?.();
    this.emit('change', win);
  }

  toggleMaximize(win) {
    if (win.state === 'min') { this.restore(win); return; }
    if (win.state === 'max') {
      if (win.restoreRect) win.rect = { ...win.restoreRect };
      this.setState(win, 'normal');
    } else {
      win.restoreRect = { ...win.rect };
      this.setState(win, 'max');
    }
  }

  async close(win, { force = false } = {}) {
    if (!force && win.handle?.onClose) {
      const ok = await win.handle.onClose();
      if (ok === false) return false;
    }
    win.handle?.destroy?.();
    win.el.classList.add('closing');
    this.wins.delete(win.id);
    setTimeout(() => win.el.remove(), 140);
    const next = this.top();
    if (next) this.focus(next);
    this.emit('close', win);
    return true;
  }

  // ------------------------------------------------------------------ drag
  startDrag(win, e) {
    if (e.button !== 0 || e.target.closest('.win-actions') || this.narrow) return;
    if (win.state === 'min') return;
    const hostRect = this.host.getBoundingClientRect();
    let start = { x: e.clientX, y: e.clientY, rect: { ...win.rect } };
    // A maximised window only leaves that state once the pointer really moves. Doing it on
    // pointerdown made the first click of a double-click un-maximise it and the dblclick then
    // maximise it again, so double-clicking a maximised title bar could never restore it.
    let started = win.state !== 'max';
    let snap = null;
    win.bar.setPointerCapture(e.pointerId);
    if (started) document.body.classList.add('dragging');
    const begin = (ev) => {
      const prev = win.restoreRect || { ...win.rect };
      const fraction = clamp((ev.clientX - hostRect.left) / hostRect.width, 0, 1);
      win.rect = { ...prev, x: clamp(ev.clientX - hostRect.left - prev.w * fraction, 0, hostRect.width - prev.w), y: 0 };
      this.setState(win, 'normal');
      start = { x: ev.clientX, y: ev.clientY, rect: { ...win.rect } };
      started = true;
      document.body.classList.add('dragging');
    };
    const move = (ev) => {
      if (!started) {
        if (Math.hypot(ev.clientX - start.x, ev.clientY - start.y) < 5) return;
        begin(ev);
      }
      const b = this.bounds();
      win.rect.x = clamp(start.rect.x + ev.clientX - start.x, 120 - win.rect.w, b.w - 120);
      win.rect.y = clamp(start.rect.y + ev.clientY - start.y, 0, b.h - TITLE_H);
      this.apply(win);
      const px = ev.clientX - hostRect.left, py = ev.clientY - hostRect.top;
      snap = px <= SNAP_EDGE ? 'left' : px >= hostRect.width - SNAP_EDGE ? 'right' : py <= SNAP_EDGE - 2 ? 'max' : null;
      this.showSnap(snap);
    };
    const up = (ev) => {
      win.bar.releasePointerCapture?.(ev.pointerId);
      win.bar.removeEventListener('pointermove', move);
      win.bar.removeEventListener('pointerup', up);
      win.bar.removeEventListener('pointercancel', up);
      document.body.classList.remove('dragging');
      this.showSnap(null);
      if (snap) this.snapTo(win, snap, start.rect);
      this.emit('change', win);
    };
    win.bar.addEventListener('pointermove', move);
    win.bar.addEventListener('pointerup', up);
    win.bar.addEventListener('pointercancel', up);
  }

  showSnap(kind) {
    if (!kind) { this.snapEl.hidden = true; return; }
    const b = this.bounds();
    const usableH = b.h - this.dockReserve;
    const r = kind === 'left' ? { x: 6, y: 6, w: b.w / 2 - 9, h: usableH - 6 }
      : kind === 'right' ? { x: b.w / 2 + 3, y: 6, w: b.w / 2 - 9, h: usableH - 6 }
        : { x: 6, y: 6, w: b.w - 12, h: usableH - 6 };
    Object.assign(this.snapEl.style, { left: `${r.x}px`, top: `${r.y}px`, width: `${r.w}px`, height: `${r.h}px` });
    this.snapEl.hidden = false;
  }

  snapTo(win, kind, original) {
    if (kind === 'max') { win.restoreRect = { ...original }; this.setState(win, 'max'); return; }
    const b = this.bounds();
    const usableH = b.h - this.dockReserve;
    win.restoreRect = { ...original };
    win.rect = kind === 'left'
      ? { x: 6, y: 6, w: b.w / 2 - 9, h: usableH - 6 }
      : { x: b.w / 2 + 3, y: 6, w: b.w / 2 - 9, h: usableH - 6 };
    this.setState(win, 'normal');
  }

  // ---------------------------------------------------------------- resize
  startResize(win, dir, e) {
    if (e.button !== 0 || win.state !== 'normal' || this.narrow) return;
    e.preventDefault();
    e.stopPropagation();
    this.focus(win, { keepFocus: true });
    const target = e.currentTarget;
    const start = { x: e.clientX, y: e.clientY, rect: { ...win.rect } };
    target.setPointerCapture(e.pointerId);
    document.body.classList.add('dragging');
    const move = (ev) => {
      const b = this.bounds();
      const dx = ev.clientX - start.x, dy = ev.clientY - start.y;
      let { x, y, w, h: hh } = start.rect;
      if (dir.includes('e')) w = clamp(start.rect.w + dx, MIN_W, b.w - x);
      if (dir.includes('s')) hh = clamp(start.rect.h + dy, MIN_H, b.h - y);
      if (dir.includes('w')) { const nw = clamp(start.rect.w - dx, MIN_W, start.rect.x + start.rect.w); x = start.rect.x + start.rect.w - nw; w = nw; }
      if (dir.includes('n')) { const nh = clamp(start.rect.h - dy, MIN_H, start.rect.y + start.rect.h); y = start.rect.y + start.rect.h - nh; hh = nh; }
      win.rect = { x, y, w, h: hh };
      this.apply(win);
    };
    const up = (ev) => {
      target.releasePointerCapture?.(ev.pointerId);
      target.removeEventListener('pointermove', move);
      target.removeEventListener('pointerup', up);
      target.removeEventListener('pointercancel', up);
      document.body.classList.remove('dragging');
      this.emit('change', win);
    };
    target.addEventListener('pointermove', move);
    target.addEventListener('pointerup', up);
    target.addEventListener('pointercancel', up);
  }

  /** Keep every window reachable after the viewport shrinks. */
  refit() {
    const b = this.bounds();
    for (const win of this.wins.values()) {
      if (win.state !== 'normal') continue;
      win.rect.w = Math.min(win.rect.w, b.w - 8);
      win.rect.h = Math.min(win.rect.h, Math.max(MIN_H, b.h - 8));
      win.rect.x = clamp(win.rect.x, 120 - win.rect.w, b.w - 120);
      win.rect.y = clamp(win.rect.y, 0, Math.max(0, b.h - TITLE_H));
      this.apply(win);
    }
    this.refreshVisibility();
  }

  serialize() {
    return this.list().sort((a, b) => a.z - b.z).map((w) => w.serialize());
  }
}
