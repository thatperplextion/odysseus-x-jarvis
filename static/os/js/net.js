// Connectivity: the one place that knows whether the Odysseus server can be reached.
//
// Every network call site (api.js, the two /api/tasks|notes clients, streams, uploads) reports what happened to it here.
// A failed fetch (a TypeError), a dead stream, or a 502/503/504 from a proxy marks the desktop "offline"; from then on
//   - the banner (netui.js) shows one calm "reconnecting" line instead of a toast and an error state per request,
//   - pollers skip their ticks (`isOnline()`), instead of hammering a dead server,
//   - GET /api/os/session is probed with a growing delay (2 s, 4 s, 8 s, then every ~15 s) and at once when the browser
//     says it is back online, the tab becomes visible or the window gets focus,
//   - when it answers, subscribers get a 'reconnect' event and refresh once.
//
// A server that is up but stops answering (hung, suspended, out of memory) never refuses anything, so refusals alone are not
// enough. Every request therefore has a deadline (fetchWithTimeout): ordinary API calls 20 s, AI planner turns and bulk file work
// 3 min, streams and uploads have none for their total time but are watched for silence (createIdleWatch). A deadline that passes
// is "one request failed": it goes through the same checking -> probe -> offline path, so the banner only appears when the
// 4 s liveness probe fails as well, never because one request happened to be slow.
//
// This file has no DOM imports so tests/js/net_check.mjs can run it in node. Nothing here patches window.fetch.

export const PROBE_PATH = '/api/os/session';
export const BACKOFF_MS = [2000, 4000, 8000, 15000];
export const PROBE_TIMEOUT_MS = 4000;
export const REQUEST_TIMEOUT_MS = 20000;       // an ordinary API call
export const LONG_TIMEOUT_MS = 180000;         // AI planner turns, bulk file operations
export const STREAM_START_MS = 30000;          // a stream must at least answer with its headers by then
export const STREAM_IDLE_MS = 25000;           // silence on a stream / upload this long makes us ask the server if it is alive
export const UPLOAD_IDLE_MS = 30000;

/** Delay before probe number `attempt` (0 = the first retry): 2 s, 4 s, 8 s, 15 s, 15 s ... with +-15 % jitter, never above 15 s. */
export function backoffDelay(attempt, random = Math.random) {
  const steps = BACKOFF_MS;
  const base = steps[Math.max(0, Math.min(Math.floor(attempt) || 0, steps.length - 1))];
  const r = Math.min(1, Math.max(0, Number(random()) || 0));
  return Math.min(steps[steps.length - 1], Math.round(base * (0.85 + 0.3 * r)));
}

/** What fetch() / a stream reader reject with when the server cannot be reached. A caller's own abort is not a network failure. */
export function isNetworkFailure(err) {
  if (!err) return false;
  if (err.network === true) return true;
  if (err.name === 'AbortError') return false;
  return err.name === 'TypeError';
}

/** A proxy's "bad gateway" page (not Odysseus' own JSON 503, which means the server is up but a feature is not). */
export function isGatewayStatus(status, contentType = '') {
  return (status === 502 || status === 503 || status === 504) && !/json/i.test(contentType || '');
}

/** "4 s" / "15 s" / "now" for the banner countdown. */
export function countdownLabel(ms) {
  const s = Math.ceil(Math.max(0, ms) / 1000);
  return s <= 0 ? 'now' : `${s} s`;
}

/** What a request rejects with when it had no answer by its deadline (or the desktop declared the server gone while it waited). */
export function timeoutError(ms, why = 'timeout') {
  const e = new Error(why === 'offline' ? 'The server stopped responding.' : `No answer within ${Math.round(ms / 1000)} s.`);
  e.name = 'TimeoutError';
  e.network = true;
  e.timedOut = true;
  e.why = why;                     // 'timeout' (the deadline passed) | 'offline' (the desktop gave the server up while this waited)
  return e;
}

/**
 * fetch() with a deadline. The deadline covers the response headers and, when the caller then reads the body (json / text /
 * blob / arrayBuffer), the body too, so a server that sends headers and stalls is caught as well. `timeoutMs` 0 = no deadline.
 * `headersOnly` ends the deadline when the headers arrive (streams: the caller reads the body itself and watches it for silence).
 * `watch(abort)` may subscribe to something that should cut the wait short; it returns its unsubscribe function.
 * The caller's own `init.signal` aborting still rejects with that abort, untouched. A deadline rejects with timeoutError(), or
 * with whatever `await mapTimeout(thatError)` returns (api.js asks the server whether it is alive before deciding what to say).
 */
export function fetchWithTimeout(input, init = {}, { timeoutMs = REQUEST_TIMEOUT_MS, headersOnly = false, watch = null, mapTimeout = (e) => e, fetchImpl = (...a) => fetch(...a) } = {}) {
  if (!(timeoutMs > 0) && !watch) return fetchImpl(input, init);
  const ctrl = new AbortController();
  const outer = init.signal;
  let cause = null;                // 'timeout' | 'offline' when WE aborted
  let response = null;
  let askedBody = false;
  let done = false;
  let timer = null;
  let unwatch = null;
  const onOuter = () => ctrl.abort(outer.reason);
  const unlink = () => { if (outer) outer.removeEventListener('abort', onOuter); };
  // Ends the deadline. The link to the caller's signal stays until the body is finished with (unlink), so that aborting still
  // cancels a stream whose headers have arrived.
  const finish = () => {
    if (done) return;
    done = true;
    if (timer !== null) { clearTimeout(timer); timer = null; }
    if (unwatch) { try { unwatch(); } catch { /* ignore */ } unwatch = null; }
  };
  const ours = (why) => { if (done || cause) return; cause = why; ctrl.abort(); };
  const fail = async (e) => { const why = cause; finish(); unlink(); throw why ? await mapTimeout(timeoutError(timeoutMs, why)) : e; };
  if (outer) { if (outer.aborted) ctrl.abort(outer.reason); else outer.addEventListener('abort', onOuter, { once: true }); }
  if (timeoutMs > 0) {
    timer = setTimeout(() => {
      timer = null;
      if (response && !askedBody) { finish(); return; }          // the answer is in and nobody is reading it: nothing is hanging
      ours('timeout');
    }, timeoutMs);
  }
  if (watch) unwatch = watch(() => ours('offline')) || null;
  return fetchImpl(input, { ...init, signal: ctrl.signal }).then((res) => {
    response = res;
    if (headersOnly) { finish(); return res; }
    if (res.status === 204 || !res.body) { finish(); unlink(); return res; }
    for (const m of ['json', 'text', 'blob', 'arrayBuffer', 'formData']) {
      const orig = res[m];
      if (typeof orig !== 'function') continue;
      res[m] = function wrapped(...a) { askedBody = true; return orig.apply(res, a).then((v) => { finish(); unlink(); return v; }, fail); };
    }
    return res;
  }, fail);
}

/**
 * Silence detector for streams and uploads: `poke()` on every sign of life; after `ms` without one, `onIdle()` runs (once per
 * `ms` of continued silence). It does nothing else: whether silence means trouble is for onIdle to find out (ask the server).
 */
export function createIdleWatch(ms, onIdle, { setTimer = (fn, d) => setTimeout(fn, d), clearTimer = (t) => clearTimeout(t), now = () => Date.now() } = {}) {
  let last = now();
  let timer = null;
  let stopped = false;
  const arm = (d) => { timer = setTimer(fire, Math.max(50, d)); };
  function fire() {
    timer = null;
    if (stopped) return;
    const quiet = now() - last;
    if (quiet >= ms) { last = now(); try { onIdle(quiet); } catch (e) { console.error(e); } }
    if (!stopped) arm(ms - (now() - last));
  }
  arm(ms);
  return {
    poke() { last = now(); },
    stop() { stopped = true; if (timer !== null) { clearTimer(timer); timer = null; } },
  };
}

/**
 * The state machine. `probe()` resolves {ok, boot?, starting?}; it must never reject (a rejection counts as "not ok").
 *   online   everything is fine
 *   checking one request failed; asking the server once before telling the user anything
 *   offline  the probe failed too; retrying with backoff
 */
export function createNet({ probe, setTimer = (fn, ms) => setTimeout(fn, ms), clearTimer = (t) => clearTimeout(t), now = () => Date.now(), random = Math.random } = {}) {
  let state = 'online';
  let attempt = 0;
  let nextAt = 0;
  let since = 0;
  let starting = false;
  let timer = null;
  let probing = null;
  let lastProbeAt = 0;
  let bootId = null;
  let unloading = false;
  const subs = new Set();

  const snapshot = () => ({ state, attempt, nextAt, since, starting, probing: !!probing });
  const emit = (type, extra) => {
    const ev = { type, ...snapshot(), ...extra };
    for (const fn of [...subs]) { try { fn(ev); } catch (e) { console.error(e); } }
  };
  const stopTimer = () => { if (timer !== null) { clearTimer(timer); timer = null; } nextAt = 0; };
  const scheduleNext = () => {
    stopTimer();
    const d = backoffDelay(attempt, random);
    nextAt = now() + d;
    timer = setTimer(() => { timer = null; verify(); }, d);
  };

  function goOnline(result = {}) {
    const was = state;
    const restarted = !!(result.boot && bootId && result.boot !== bootId);
    if (result.boot) bootId = result.boot;
    stopTimer();
    state = 'online'; attempt = 0; starting = false;
    if (was === 'online') return;
    emit('state');
    // A blip that answered at once changes nothing, unless the server came back as a new process: then everything is stale.
    if (was === 'offline' || restarted) emit('reconnect', { restarted, downMs: since ? now() - since : 0 });
  }

  function verify() {
    if (probing) return probing;
    stopTimer();
    lastProbeAt = now();
    if (state === 'offline') emit('probing');
    probing = (async () => {
      let r;
      try { r = (await probe()) || { ok: false }; } catch { r = { ok: false }; }
      probing = null;
      if (r.ok) { goOnline(r); return; }
      starting = !!r.starting;
      if (state === 'checking') { state = 'offline'; attempt = 0; scheduleNext(); emit('state'); }
      else if (state === 'offline') { attempt += 1; scheduleNext(); emit('tick'); }
    })();
    return probing;
  }

  return {
    get state() { return state; },
    snapshot,
    /** True only when nothing is known to be wrong: pollers and the toast gate use this. */
    isOnline: () => state === 'online',
    isOffline: () => state === 'offline',
    /** A request failed the way an unreachable server fails. Ignored while the page itself is going away. */
    reportFailure() {
      if (unloading || state !== 'online') return;
      state = 'checking'; since = now(); attempt = 0;
      emit('state');
      verify();
    },
    /**
     * Something that should have answered by now has not (a stream went quiet, an upload stalled). Like reportFailure(), but it
     * resolves with the verdict once the probe has run: 'online' (the server answers, the silence was just the work) or 'offline'.
     */
    suspect() {
      if (unloading) return Promise.resolve(state);
      if (state === 'online') { state = 'checking'; since = now(); attempt = 0; emit('state'); return verify().then(() => state); }
      if (state === 'checking' && probing) return probing.then(() => state);
      return Promise.resolve(state);
    },
    /** A request got a real answer from the server: it is there, whatever the probe last said. */
    reportSuccess() { if (state !== 'online') goOnline({}); },
    /** "Retry now", or the browser coming back online. */
    retryNow() { if (state === 'offline') { stopTimer(); return verify(); } return probing; },
    /** Tab visible / window focused / browser online: probe at once unless we just did. */
    wake() { if (state === 'offline' && !probing && now() - lastProbeAt > 1000) verify(); },
    setBootId(id) { if (id) bootId = id; },
    setUnloading(on = true) { unloading = on; },
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
    destroy() { stopTimer(); subs.clear(); },
  };
}

// ----------------------------------------------------------------------------------------------- browser wiring
/** GET /api/os/session with a timeout. 401 means the login expired: same redirect as every other client. */
export async function sessionProbe() {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), PROBE_TIMEOUT_MS);
  try {
    const res = await fetch(PROBE_PATH, { credentials: 'same-origin', cache: 'no-store', signal: ctrl.signal });
    if (res.status === 401) { window.location.href = '/login'; return { ok: true }; }
    const type = res.headers.get('content-type') || '';
    if (isGatewayStatus(res.status, type)) return { ok: false };
    // Odysseus' own 503 ("Jarvis OS is not running (starting)") = the process is up but the kernel is not ready yet.
    if (res.status === 503) return { ok: false, starting: true };
    let boot = null;
    if (res.ok) { try { boot = (await res.json()).boot_id || null; } catch { /* not JSON */ } }
    return { ok: true, boot };
  } catch {
    return { ok: false };
  } finally {
    clearTimeout(t);
  }
}

export const net = createNet({ probe: sessionProbe });
export const { isOnline, isOffline, reportFailure, reportSuccess, suspect, retryNow, subscribe } = net;

let attached = false;
/** Probe at once when the browser, the tab or the window says things may have changed. Call once at boot. */
export function attachBrowserEvents() {
  if (attached || typeof window === 'undefined') return;
  attached = true;
  window.addEventListener('online', () => net.wake());
  window.addEventListener('focus', () => net.wake());
  document.addEventListener('visibilitychange', () => { if (!document.hidden) net.wake(); });
  // A fetch that dies because the page is navigating away is not the server's fault.
  window.addEventListener('pagehide', () => net.setUnloading(true));
  window.addEventListener('beforeunload', () => net.setUnloading(true));
  window.addEventListener('pageshow', () => net.setUnloading(false));
}
