// Run with: node tests/js/suspender_check.mjs   (exit code != 0 on failure)
// static/os/js/suspender.js: when a hidden window's content is put to sleep (the embedded Odysseus pages), and which windows
// count as hidden. Pure logic with a fake clock; no browser, no server.
import { createSuspender, visibilityOf, SUSPEND_AFTER_MS, RECHECK_MS } from '../../static/os/js/suspender.js';

let failures = 0;
const eq = (name, got, want) => {
  const a = JSON.stringify(got); const b = JSON.stringify(want);
  if (a !== b) { failures++; console.error(`FAIL ${name}\n   got  ${a}\n   want ${b}`); } else console.log(`ok   ${name}`);
};

function clock() {
  let t = 0; let id = 1; const timers = new Map();
  return {
    setTimer: (fn, ms) => { const k = id++; timers.set(k, { at: t + ms, fn }); return k; },
    clearTimer: (k) => timers.delete(k),
    advance(ms) {
      const end = t + ms;
      for (;;) {
        const due = [...timers.entries()].filter(([, v]) => v.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        timers.delete(due[0]); t = due[1].at; due[1].fn();
      }
      t = end;
    },
    pending: () => timers.size,
  };
}

eq('default is one minute', [SUSPEND_AFTER_MS, RECHECK_MS], [60000, 15000]);

{
  // hidden for a minute -> suspended; shown again -> resumed exactly once
  const c = clock(); const log = [];
  const s = createSuspender({ ...c, onSuspend: () => log.push('suspend'), onResume: () => log.push('resume') });
  eq('a visible window has no timer', c.pending(), 0);
  s.setVisible(false);
  c.advance(59000); eq('59 s hidden: still running', log, []);
  c.advance(1500); eq('60 s hidden: suspended', [log, s.suspended], [['suspend'], true]);
  c.advance(600000); eq('and nothing else happens while it stays hidden', [log, c.pending()], [['suspend'], 0]);
  s.setVisible(true); eq('shown again: resumed once', [log, s.suspended], [['suspend', 'resume'], false]);
  s.setVisible(true); eq('showing a visible window again does nothing', log.length, 2);
}
{
  // brief hide: never suspended, and the timer is gone
  const c = clock(); const log = [];
  const s = createSuspender({ ...c, onSuspend: () => log.push('suspend'), onResume: () => log.push('resume') });
  s.setVisible(false); c.advance(20000); s.setVisible(true);
  c.advance(120000);
  eq('hidden for 20 s only: never suspended, no resume, no timer', [log, c.pending()], [[], 0]);
  s.setVisible(false); c.advance(40000); s.setVisible(true); s.setVisible(false); c.advance(40000);
  eq('the minute restarts every time the window is hidden', log, []);
  c.advance(21000); eq('...and counts from the latest hide', log, ['suspend']);
}
{
  // a page in use is left alone, then suspended once it is idle
  const c = clock(); const log = []; let busy = true;
  const s = createSuspender({ ...c, isBusy: () => busy, onSuspend: () => log.push('suspend') });
  s.setVisible(false);
  c.advance(60000); eq('busy at the minute mark: not suspended', [log, c.pending()], [[], 1]);
  c.advance(RECHECK_MS * 3); eq('still busy: keeps asking, still running', log, []);
  busy = false; c.advance(RECHECK_MS); eq('idle on the next check: suspended', log, ['suspend']);
}
{
  // busy page shown again before the next check: nothing to resume
  const c = clock(); const log = [];
  const s = createSuspender({ ...c, isBusy: () => true, onSuspend: () => log.push('suspend'), onResume: () => log.push('resume') });
  s.setVisible(false); c.advance(61000); s.setVisible(true);
  eq('shown while it was protected: nothing suspended, nothing resumed, timer cleared', [log, c.pending()], [[], 0]);
}
{
  // a throwing isBusy / callbacks must not wedge it
  const c = clock(); const log = [];
  const s = createSuspender({ ...c, isBusy: () => { throw new Error('frame gone'); }, onSuspend: () => log.push('suspend') });
  s.setVisible(false); c.advance(61000);
  eq('if the busy check throws, the page counts as idle', log, ['suspend']);
  s.destroy();
}
{
  const c = clock();
  const s = createSuspender({ ...c, afterMs: 3000 });
  s.setVisible(false); s.destroy();
  eq('destroy() clears the timer', c.pending(), 0);
}

// ----------------------------------------------------------------------------------------- which windows are hidden
const W = (state, z, y = 100, h = 400) => ({ state, z, rect: { y, h } });
const line = 704;
eq('a lone window is visible', visibilityOf([W('normal', 11)], line), [true]);
eq('a minimised window is hidden', visibilityOf([W('min', 11), W('normal', 12)], line), [false, true]);
eq('a window under a maximised one is hidden', visibilityOf([W('normal', 11), W('max', 12)], line), [false, true]);
eq('a window ABOVE a maximised one is visible (and the maximised one still shows around it)', visibilityOf([W('max', 11), W('normal', 12)], line), [true, true]);
eq('two maximised: only the top one shows', visibilityOf([W('max', 11), W('max', 13), W('max', 12)], line), [false, true, false]);
eq('a window poking out below the maximised one is still visible', visibilityOf([W('normal', 11, 600, 300), W('max', 12)], line), [true, true]);
eq('...one that ends exactly at the line is covered', visibilityOf([W('normal', 11, 304, 400), W('max', 12)], line), [false, true]);
eq('a minimised maximised window covers nothing', visibilityOf([W('normal', 11), W('min', 12)], line), [true, false]);
eq('no windows', visibilityOf([], line), []);

process.exit(failures ? 1 : 0);
