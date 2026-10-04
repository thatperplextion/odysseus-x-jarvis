// Odysseus apps as windows: each is the real Odysseus page loaded in a same-origin frame.
// (The server allows framing of exactly these pages by this origin and nobody else; see
// core/middleware.py OS_EMBEDDABLE_PAGES.)
//
// A classic page polls its own endpoints (about ten requests a minute each), so a window that nobody can see should not keep one
// alive. After a window has been hidden for a minute (minimised, or fully covered by a maximised window) its frame is taken out and
// a plain "paused" placeholder stays; when the window is shown again the frame comes back at the same address (query and #hash
// included) and the same scroll position. A page that is in use is left alone: a chat answer streaming in, media playing, or
// text typed into a message box and not sent. `localStorage['os.embedSuspendMs']` changes the minute (tests, tinkering).

import { h, icon } from '../dom.js';
import { createSuspender, SUSPEND_AFTER_MS, RECHECK_MS } from '../suspender.js';

export const EMBEDS = [
  { id: 'chat', name: 'Chat', icon: 'message', path: '/', width: 980, height: 640 },
  { id: 'notes', name: 'Notes', icon: 'note', path: '/notes', width: 900, height: 620 },
  { id: 'documents', name: 'Documents', icon: 'book', path: '/library', width: 940, height: 640 },
  { id: 'email', name: 'Email', icon: 'mail', path: '/email', width: 980, height: 640 },
  { id: 'calendar', name: 'Calendar', icon: 'calendar', path: '/calendar', width: 960, height: 640 },
  { id: 'tasks', name: 'Tasks (classic)', icon: 'check-square', path: '/tasks', width: 900, height: 600 },
  { id: 'memory', name: 'Memory', icon: 'database', path: '/memory', width: 860, height: 600 },
  { id: 'gallery', name: 'Gallery', icon: 'image', path: '/gallery', width: 960, height: 640 },
  { id: 'cookbook', name: 'Cookbook', icon: 'flask', path: '/cookbook', width: 960, height: 640 },
];

function suspendDelay() {
  try {
    const v = Number(localStorage.getItem('os.embedSuspendMs'));
    if (Number.isFinite(v) && v >= 500) return v;
  } catch { /* storage blocked */ }
  return SUSPEND_AFTER_MS;
}

/** The page inside the frame is doing something the person would lose by pausing it. */
export function frameBusy(frame) {
  try {
    const w = frame.contentWindow;
    const d = frame.contentDocument;
    if (!w || !d) return false;
    if (w.__odysseusChatBusy || Date.now() < (w.__odysseusChatBusyUntil || 0)) return true;      // a chat answer is on its way
    if ([...d.querySelectorAll('audio, video')].some((m) => !m.paused && !m.ended)) return true;  // something is playing
    // Text typed into a message box and not sent. (activeElement would not do: a hidden frame loses its focus.)
    for (const t of d.querySelectorAll('textarea')) if (!t.readOnly && !t.disabled && t.value.trim()) return true;
  } catch { /* the frame is gone or not ours: nothing to protect */ }
  return false;
}

/** Where the frame is now, as a same-origin address, so a resume lands on the same page, query and #hash. */
function placeOf(frame, fallback) {
  try {
    const u = new URL(frame.contentWindow.location.href);
    if (u.origin === window.location.origin) return { url: u.pathname + u.search + u.hash, scroll: frame.contentWindow.scrollY || 0 };
  } catch { /* cross-origin or detached */ }
  return { url: fallback, scroll: 0 };
}

export function embedApp(def) {
  return {
    meta: { id: def.id, name: def.name, icon: def.icon, width: def.width, height: def.height, singleton: true, group: 'odysseus' },
    mount(body, win) {
      const label = h('p', { class: 'muted', text: `Loading ${def.name}…` });
      const skeleton = h('div', { class: 'embed-loading' }, icon(def.icon, 26), label);
      const wrap = h('div', { class: 'embed' }, skeleton);
      let frame = null;
      let scrollTo = 0;

      function makeFrame(src) {
        const f = h('iframe', { class: 'embed-frame', src, title: def.name, referrerpolicy: 'same-origin', allow: 'clipboard-read; clipboard-write; microphone; fullscreen' });
        f.addEventListener('load', () => {
          skeleton.remove();
          if (scrollTo) { try { f.contentWindow.scrollTo(0, scrollTo); } catch { /* not scrollable */ } scrollTo = 0; }
        });
        return f;
      }
      frame = makeFrame(def.path);
      wrap.append(frame);
      body.append(wrap);

      let place = null;
      const suspender = createSuspender({
        afterMs: suspendDelay(),
        recheckMs: Math.min(RECHECK_MS, suspendDelay()),
        isBusy: () => !!frame && frameBusy(frame),
        onSuspend() {
          place = placeOf(frame, def.path);
          frame.src = 'about:blank';          // drops the page and every timer / connection it had
          frame.remove();
          frame = null;
          label.textContent = `${def.name} is paused while hidden`;
          wrap.append(skeleton);
          wrap.dataset.suspended = '1';
        },
        onResume() {
          label.textContent = `Loading ${def.name}…`;
          scrollTo = place?.scroll || 0;
          frame = makeFrame(place?.url || def.path);
          wrap.prepend(frame);
          delete wrap.dataset.suspended;
        },
      });

      win.addAction('external', 'Open in its own tab', () => window.open(frame ? placeOf(frame, def.path).url : (place?.url || def.path), '_blank', 'noopener'));
      win.addAction('refresh', 'Reload', () => { if (frame) frame.contentWindow?.location.reload(); });
      return {
        focus: () => frame?.focus(),
        serialize: () => ({}),
        /** Called by the window manager whenever the window is shown or hidden (minimised, or covered by a maximised window). */
        onVisibility: (visible) => suspender.setVisible(visible),
        destroy: () => { suspender.destroy(); if (frame) frame.src = 'about:blank'; },
      };
    },
  };
}
