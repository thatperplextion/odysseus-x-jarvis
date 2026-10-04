// Decides when a hidden window's expensive content should be put to sleep, and wakes it when the window is shown again.
// Used by the embedded Odysseus pages (apps/odysseus.js): a classic page polls its own endpoints about ten times a minute, which
// adds up to ~100 requests/min with all nine open, even when every one of them is minimised or buried under a maximised window.
//
//   setVisible(false)  starts the clock; after `afterMs` hidden, `onSuspend()` runs unless `isBusy()` says the page is in use
//                      (then it asks again every `recheckMs` until the page is idle or shown)
//   setVisible(true)   cancels the clock, and runs `onResume()` if the content was suspended
//
// No DOM in here, so tests/js/suspender_check.mjs can run it in node with a fake clock.

export const SUSPEND_AFTER_MS = 60000;
export const RECHECK_MS = 15000;

/**
 * Which windows can anyone see? `wins` are {state: 'normal'|'max'|'min', z, rect: {y, h}}; `line` is where a maximised window
 * ends (the desktop height minus the dock's reserve). Minimised windows are hidden; so is any window that ends above `line` (or
 * is itself maximised) while another maximised window sits above it in z-order. Returns the visibility of each, in order.
 */
export function visibilityOf(wins, line) {
  const maxZ = Math.max(-1, ...wins.filter((w) => w.state === 'max').map((w) => w.z));
  return wins.map((w) => {
    if (w.state === 'min') return false;
    if (maxZ > w.z && (w.state === 'max' || w.rect.y + w.rect.h <= line + 1)) return false;
    return true;
  });
}

export function createSuspender({
  afterMs = SUSPEND_AFTER_MS, recheckMs = RECHECK_MS, isBusy = () => false, onSuspend = () => {}, onResume = () => {},
  setTimer = (fn, ms) => setTimeout(fn, ms), clearTimer = (t) => clearTimeout(t),
} = {}) {
  let visible = true;
  let suspended = false;
  let timer = null;
  const clear = () => { if (timer !== null) { clearTimer(timer); timer = null; } };
  const arm = (ms) => { clear(); timer = setTimer(fire, ms); };
  function fire() {
    timer = null;
    if (visible || suspended) return;
    let busy = false;
    try { busy = !!isBusy(); } catch { busy = false; }
    if (busy) { arm(recheckMs); return; }
    suspended = true;
    try { onSuspend(); } catch (e) { console.error(e); }
  }
  return {
    get suspended() { return suspended; },
    get visible() { return visible; },
    setVisible(v) {
      v = !!v;
      if (v === visible) return;
      visible = v;
      if (v) {
        clear();
        if (suspended) { suspended = false; try { onResume(); } catch (e) { console.error(e); } }
      } else arm(afterMs);
    },
    destroy() { clear(); },
  };
}
