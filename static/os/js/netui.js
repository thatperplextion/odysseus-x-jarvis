// The "Odysseus isn't responding" line, and everything that goes with it. net.js decides whether the server is reachable;
// this module is the part that touches the screen:
//   - one calm banner under the menu bar with a live countdown to the next try and a "Retry now" button,
//   - error toasts are held back while offline (the banner already says it, once),
//   - on reconnect: a short "Reconnected" toast and `os.emit('reconnected', { restarted })`, which the dashboard, the
//     menu bar, Task Manager, Automations, Files, ... listen to and refresh once.
// The page and its open windows are never reloaded.

import { h, toast, setToastGate } from './dom.js';
import { os } from './ctx.js';
import { net, attachBrowserEvents, countdownLabel } from './net.js';

let started = false;

export function initNetUi() {
  if (started) return;
  started = true;
  attachBrowserEvents();

  const label = h('span', { class: 'net-label', text: 'Odysseus isn’t responding — reconnecting…' });
  const eta = h('span', { class: 'net-eta mono' });
  const retry = h('button', { class: 'btn btn-ink btn-sm net-retry', type: 'button', text: 'Retry now', on: { click: () => net.retryNow() } });
  const banner = h('div', { class: 'net-banner', role: 'status', 'aria-live': 'polite', hidden: true, dataset: { netBanner: '' } },
    h('span', { class: 'net-dot', 'aria-hidden': 'true' }), label, eta, retry);
  document.getElementById('overlays').append(banner);

  let ticker = null;
  const paintEta = () => {
    const s = net.snapshot();
    if (s.state !== 'offline') return;
    if (s.probing) eta.textContent = 'TRYING…';
    else eta.textContent = s.nextAt ? `NEXT TRY IN ${countdownLabel(s.nextAt - Date.now()).toUpperCase()}` : '';
    retry.disabled = s.probing;
  };
  const paint = () => {
    const s = net.snapshot();
    const offline = s.state === 'offline';
    banner.hidden = !offline;
    if (offline) document.documentElement.dataset.net = 'offline'; else delete document.documentElement.dataset.net;
    label.textContent = s.starting ? 'Odysseus is starting up — reconnecting…' : 'Odysseus isn’t responding — reconnecting…';
    if (offline && !ticker) ticker = setInterval(paintEta, 250);
    if (!offline && ticker) { clearInterval(ticker); ticker = null; }
    paintEta();
  };

  // Error toasts say what the banner already says, once per request, so while offline they are held back. One exception: when the
  // person has just clicked or typed (so it is their action that failed), say so once, calmly, instead of failing silently.
  let lastInput = 0;
  let lastNote = 0;
  for (const type of ['pointerdown', 'keydown']) document.addEventListener(type, () => { lastInput = Date.now(); }, { capture: true, passive: true });
  setToastGate((_msg, opts) => {
    if (opts.kind !== 'error' || net.isOnline()) return true;
    const now = Date.now();
    if (now - lastInput < 2500 && now - lastNote > 6000) {
      lastNote = now;
      return { message: 'That didn’t go through: Odysseus isn’t responding.', kind: 'info' };
    }
    return false;
  });

  net.subscribe((e) => {
    paint();
    if (e.type !== 'reconnect') return;
    toast(e.restarted ? 'Reconnected — Odysseus restarted' : 'Reconnected', { kind: 'ok', ms: 2400 });
    if (e.restarted) Promise.resolve(os.refreshMounts?.()).catch(() => {});
    os.emit('reconnected', { restarted: !!e.restarted, downMs: e.downMs || 0 });
  });
  paint();
}
