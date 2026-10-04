// Run with: node tests/js/net_check.mjs   (exit code != 0 on failure)
// static/os/js/net.js: the connectivity state machine behind the "Odysseus isn't responding" banner. Pure logic,
// driven by a fake clock and a scripted probe; no browser, no server.
import http from 'node:http';
import {
  backoffDelay, BACKOFF_MS, isNetworkFailure, isGatewayStatus, countdownLabel, createNet,
  fetchWithTimeout, createIdleWatch, timeoutError, REQUEST_TIMEOUT_MS, LONG_TIMEOUT_MS, PROBE_TIMEOUT_MS, net as theNet,
} from '../../static/os/js/net.js';
import { get, streamEvents, timeoutFor, ApiError } from '../../static/os/js/api.js';

let failures = 0;
const eq = (name, got, want) => {
  const a = JSON.stringify(got); const b = JSON.stringify(want);
  if (a !== b) { failures++; console.error(`FAIL ${name}\n   got  ${a}\n   want ${b}`); } else console.log(`ok   ${name}`);
};
const yes = (name, v) => eq(name, !!v, true);

// ---------------------------------------------------------------------------------------------------- pure helpers
eq('backoff steps are 2 s, 4 s, 8 s, 15 s', [0, 1, 2, 3].map((n) => backoffDelay(n, () => 0.5)), [2000, 4000, 8000, 15000]);
eq('backoff never goes above 15 s', [4, 5, 20, 1000].map((n) => backoffDelay(n, () => 1)), [15000, 15000, 15000, 15000]);
eq('jitter keeps the first retry within +-15 %', [backoffDelay(0, () => 0), backoffDelay(0, () => 1)], [1700, 2300]);
yes('jitter never leaves the band', Array.from({ length: 200 }, (_, i) => backoffDelay(i % 6, Math.random)).every((d, i) => d >= BACKOFF_MS[Math.min(i % 6, 3)] * 0.85 - 1 && d <= 15000));
eq('negative / odd attempts are clamped', [backoffDelay(-3, () => 0.5), backoffDelay(NaN, () => 0.5)], [2000, 2000]);

eq('a fetch TypeError is a network failure', isNetworkFailure(new TypeError('Failed to fetch')), true);
eq('a flagged ApiError is a network failure', isNetworkFailure({ name: 'ApiError', network: true }), true);
eq('the caller aborting is not', isNetworkFailure(Object.assign(new Error('x'), { name: 'AbortError' })), false);
eq('an ordinary HTTP error is not', isNetworkFailure({ name: 'ApiError', status: 404 }), false);
eq('null is not', isNetworkFailure(null), false);

eq('proxy 502 page is a gateway failure', isGatewayStatus(502, 'text/html'), true);
eq('proxy 504 with no content type is', isGatewayStatus(504, ''), true);
eq('Odysseus JSON 503 is not (server is up)', isGatewayStatus(503, 'application/json'), false);
eq('500 is not', isGatewayStatus(500, 'text/html'), false);
eq('200 is not', isGatewayStatus(200, 'text/html'), false);

eq('countdown rounds up', [countdownLabel(3100), countdownLabel(1), countdownLabel(0), countdownLabel(-5)], ['4 s', '1 s', 'now', 'now']);

// ------------------------------------------------------------------------------------------------ the state machine
function harness(script) {
  let t = 0;
  let nextId = 1;
  const timers = new Map();
  const log = [];
  const probes = [];
  const probe = () => new Promise((resolve) => { const r = script.shift() ?? { ok: false }; probes.push(t); resolve(r); });
  const net = createNet({
    probe, now: () => t, random: () => 0.5,
    setTimer: (fn, ms) => { const id = nextId++; timers.set(id, { at: t + ms, fn }); return id; },
    clearTimer: (id) => timers.delete(id),
  });
  net.subscribe((e) => log.push(e.type + (e.restarted ? ':restarted' : '')));
  const flush = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };
  const advance = async (ms) => {          // run due timers in order, letting the probe promise settle between them
    const end = t + ms;
    for (;;) {
      const due = [...timers.entries()].filter(([, v]) => v.at <= end).sort((a, b) => a[1].at - b[1].at)[0];
      if (!due) break;
      timers.delete(due[0]); t = due[1].at; due[1].fn(); await flush();
    }
    t = end; await flush();
  };
  return { net, log, probes, advance, flush, timers, at: () => t };
}

{
  // server dies: failure -> checking -> (probe fails) -> offline; then 2 s, 4 s, 8 s, 15 s, 15 s probes; then it answers
  const H = harness([{ ok: false }, { ok: false }, { ok: false }, { ok: false }, { ok: false }, { ok: false }, { ok: true, boot: 'A' }]);
  H.net.setBootId('A');
  eq('starts online', H.net.state, 'online');
  H.net.reportFailure(); await H.flush();
  eq('one failed request + failed probe = offline', H.net.state, 'offline');
  eq('first probe was immediate', H.probes, [0]);
  H.net.reportFailure(); H.net.reportFailure(); await H.flush();
  eq('more failures while offline do not cause more probes', H.probes.length, 1);
  await H.advance(2100); eq('retry #1 after ~2 s', H.probes, [0, 2000]);
  await H.advance(4100); eq('retry #2 ~4 s later', H.probes, [0, 2000, 6000]);
  await H.advance(8100); eq('retry #3 ~8 s later', H.probes, [0, 2000, 6000, 14000]);
  await H.advance(15100); eq('retry #4 ~15 s later', H.probes.slice(-1), [29000]);
  await H.advance(15100); eq('then it stays at 15 s', H.probes.slice(-1), [44000]);
  eq('still offline, one banner', H.net.state, 'offline');
  const before = H.probes.length;
  await H.advance(14000); eq('request rate while offline is one probe per interval, not per call', H.probes.length - before, 0);
  await H.advance(2000);
  eq('server answers: back online', H.net.state, 'online');
  eq('reconnect is announced exactly once', H.log.filter((x) => x === 'reconnect').length, 1);
  eq('same boot id: not flagged as a restart', H.log.includes('reconnect:restarted'), false);
  eq('no timer left running when online', H.timers.size, 0);
}

{
  // a blip: the verifying probe succeeds at once -> never shows offline, no reconnect refresh
  const H = harness([{ ok: true, boot: 'A' }]);
  H.net.setBootId('A');
  H.net.reportFailure(); await H.flush();
  eq('a one-off failure that the probe disproves goes back to online', H.net.state, 'online');
  eq('and announces no reconnect', H.log.filter((x) => x.startsWith('reconnect')).length, 0);
  eq('and never reached offline', H.log.includes('probing'), false);
}

{
  // the server came back as a new process while we were not looking
  const H = harness([{ ok: false }, { ok: true, boot: 'B' }]);
  H.net.setBootId('A');
  H.net.reportFailure(); await H.flush();
  await H.advance(2100);
  eq('a new boot id is reported as a restart', H.log.filter((x) => x.startsWith('reconnect')), ['reconnect:restarted']);
}

{
  // new process answers the very first verifying probe: that is still a reconnect (everything pending was lost)
  const H = harness([{ ok: true, boot: 'B' }]);
  H.net.setBootId('A');
  H.net.reportFailure(); await H.flush();
  eq('restart caught by the first probe refreshes too', H.log.filter((x) => x.startsWith('reconnect')), ['reconnect:restarted']);
}

{
  // "Retry now" and wake events
  const H = harness([{ ok: false }, { ok: false }, { ok: true }]);
  H.net.reportFailure(); await H.flush();
  H.net.wake(); await H.flush();
  eq('wake right after a probe does nothing', H.probes.length, 1);
  await H.advance(1500);
  H.net.wake(); await H.flush();
  eq('wake later probes at once (before the 2 s timer)', H.probes, [0, 1500]);
  eq('only one timer pending after a probe', H.timers.size, 1);
  H.net.retryNow(); await H.flush();
  eq('"Retry now" probes at once and succeeds', [H.net.state, H.probes.length], ['online', 3]);
  eq('retryNow while online is a no-op', (H.net.retryNow(), H.probes.length), 3);
}

{
  // any successful request proves the server is there
  const H = harness([{ ok: false }]);
  H.net.reportFailure(); await H.flush();
  eq('offline', H.net.state, 'offline');
  H.net.reportSuccess();
  eq('a user request that succeeds brings the desktop back', H.net.state, 'online');
  eq('and refreshes once', H.log.filter((x) => x === 'reconnect').length, 1);
  eq('and stops the retry timer', H.timers.size, 0);
}

{
  // a server that answers but is still starting (Jarvis kernel not ready) keeps the banner, with a hint
  const H = harness([{ ok: false }, { ok: false, starting: true }, { ok: true }]);
  H.net.reportFailure(); await H.flush();
  await H.advance(2100);
  eq('"starting" is surfaced while offline', H.net.snapshot().starting, true);
  await H.advance(4100);
  eq('and cleared once it is ready', [H.net.state, H.net.snapshot().starting], ['online', false]);
}

{
  // failures while the page is unloading are ignored
  const H = harness([{ ok: false }]);
  H.net.setUnloading(true);
  H.net.reportFailure(); await H.flush();
  eq('unloading page: no offline state', [H.net.state, H.probes.length], ['online', 0]);
}

{
  // a probe that throws counts as a failed probe
  let t = 0;
  const net = createNet({ probe: () => Promise.reject(new Error('boom')), now: () => t, setTimer: () => 1, clearTimer: () => {} });
  net.reportFailure();
  for (let i = 0; i < 6; i++) await Promise.resolve();
  eq('a throwing probe does not wedge the machine', net.state, 'offline');
}

{
  // suspect(): "something that should have answered has not" -> the verdict once the probe has run
  const H = harness([{ ok: true }]);
  const v = await H.net.suspect();
  eq('suspect() with a live server resolves online', v, 'online');
  eq('and left no banner state behind', H.log.filter((x) => x === 'probing' || x === 'reconnect').length, 0);
  const H2 = harness([{ ok: false }]);
  eq('suspect() with a dead server resolves offline', await H2.net.suspect(), 'offline');
  eq('and a second suspect() while offline does not probe again', (await H2.net.suspect(), H2.probes.length), 1);
  const H3 = harness([{ ok: false }]);
  const both = await Promise.all([H3.net.suspect(), H3.net.suspect(), H3.net.suspect()]);
  eq('concurrent suspects share one probe', [both, H3.probes.length], [['offline', 'offline', 'offline'], 1]);
}

// -------------------------------------------------------------------------------------------------- deadlines (fake fetch)
const never = (_i, init) => new Promise((_res, rej) => {       // like fetch() with a signal: rejects when it aborts, at once if it already has
  const abort = () => rej(Object.assign(new Error('aborted'), { name: 'AbortError' }));
  if (init.signal?.aborted) abort(); else init.signal?.addEventListener('abort', abort);
});
const fakeRes = (body, extra = {}) => ({ status: 200, ok: true, body: {}, json: async () => body, text: async () => JSON.stringify(body), ...extra });

{
  const t0 = Date.now();
  const err = await fetchWithTimeout('/x', {}, { timeoutMs: 80, fetchImpl: never }).then(() => null, (e) => e);
  eq('a request that never answers rejects with a timeout error after its deadline', [err?.name, err?.network, err?.timedOut, err?.why], ['TimeoutError', true, true, 'timeout']);
  yes('...after about the deadline, not at once and not never', Date.now() - t0 >= 70 && Date.now() - t0 < 600);
  eq('a timeout counts as a network failure (so it goes through the probe)', isNetworkFailure(err), true);
}
{
  const r = await fetchWithTimeout('/x', {}, { timeoutMs: 200, fetchImpl: async () => fakeRes({ a: 1 }) });
  eq('a prompt answer is returned untouched', await r.json(), { a: 1 });
}
{
  // headers arrive, the body never does: the deadline still covers it
  const stall = (_i, init) => Promise.resolve({ status: 200, ok: true, body: {}, json: () => new Promise((_r, rej) => init.signal.addEventListener('abort', () => rej(Object.assign(new Error('aborted'), { name: 'AbortError' })))) });
  const r = await fetchWithTimeout('/x', {}, { timeoutMs: 80, fetchImpl: stall });
  const err = await r.json().then(() => null, (e) => e);
  eq('a body that stalls after the headers is caught too', [err?.name, err?.timedOut], ['TimeoutError', true]);
}
{
  // headersOnly: a stream is not cut when its body takes long
  const r = await fetchWithTimeout('/x', {}, { timeoutMs: 60, headersOnly: true, fetchImpl: async () => fakeRes({}) });
  await new Promise((r2) => setTimeout(r2, 150));
  eq('headersOnly ends the deadline at the headers', r.status, 200);
}
{
  // an answer that nobody reads must not turn into a late abort/report
  const r = await fetchWithTimeout('/x', {}, { timeoutMs: 50, fetchImpl: async () => fakeRes({ late: true }) });
  await new Promise((r2) => setTimeout(r2, 120));
  eq('an unread answer is not aborted later; reading it afterwards still works', await r.json(), { late: true });
}
{
  // the caller's own abort passes through untouched, and is not a network failure
  const ac = new AbortController();
  const p = fetchWithTimeout('/x', { signal: ac.signal }, { timeoutMs: 5000, fetchImpl: never }).then(() => null, (e) => e);
  setTimeout(() => ac.abort(), 20);
  const err = await p;
  eq('the caller aborting is an AbortError, not a timeout', [err?.name, isNetworkFailure(err)], ['AbortError', false]);
  const ac2 = new AbortController(); ac2.abort();
  const err2 = await fetchWithTimeout('/x', { signal: ac2.signal }, { timeoutMs: 5000, fetchImpl: never }).then(() => null, (e) => e);
  eq('an already-aborted signal rejects at once', err2?.name, 'AbortError');
}
{
  // the watch hook cuts a long wait short
  let cut = null;
  const p = fetchWithTimeout('/x', {}, { timeoutMs: 60000, fetchImpl: never, watch: (abort) => { cut = abort; return () => {}; } }).then(() => null, (e) => e);
  setTimeout(() => cut(), 20);
  const err = await p;
  eq('watch(abort) ends a long request as "offline"', [err?.name, err?.why], ['TimeoutError', 'offline']);
}
{
  // the mapper decides what the caller sees
  const err = await fetchWithTimeout('/x', {}, { timeoutMs: 40, fetchImpl: never, mapTimeout: async (e) => Object.assign(new Error('mapped'), { from: e.why }) }).then(() => null, (e) => e);
  eq('mapTimeout can replace the error (api.js asks the server first)', [err?.message, err?.from], ['mapped', 'timeout']);
}
eq('timeoutError names the deadline', timeoutError(20000).message, 'No answer within 20 s.');
eq('per-call deadlines: ordinary 20 s, AI planner and bulk file work long',
  [timeoutFor('/system'), timeoutFor('/fs/list'), timeoutFor('/assistant'), timeoutFor('/assistant/cancel'), timeoutFor('/fs/transfer'), timeoutFor('/fs/search')],
  [REQUEST_TIMEOUT_MS, REQUEST_TIMEOUT_MS, LONG_TIMEOUT_MS, REQUEST_TIMEOUT_MS, LONG_TIMEOUT_MS, LONG_TIMEOUT_MS]);
eq('the liveness probe waits 4 s', PROBE_TIMEOUT_MS, 4000);

// ------------------------------------------------------------------------------------------------------------ idle watch
{
  let t = 0; let nextId = 1; const timers = new Map(); const idles = [];
  const w = createIdleWatch(1000, (q) => idles.push(q), { setTimer: (fn, d) => { const id = nextId++; timers.set(id, { at: t + d, fn }); return id; }, clearTimer: (id) => timers.delete(id), now: () => t });
  const run = (to) => { for (;;) { const due = [...timers.entries()].filter(([, v]) => v.at <= to).sort((a, b) => a[1].at - b[1].at)[0]; if (!due) break; timers.delete(due[0]); t = due[1].at; due[1].fn(); } t = to; };
  run(900); w.poke();
  run(1500); eq('traffic keeps the watch quiet', idles.length, 0);
  run(1950); eq('silence for the whole period fires once', idles.length, 1);
  run(2900); eq('and keeps asking once per period while the silence lasts', idles.length, 2);
  w.stop();
  run(10000); eq('stop() ends it, no timer left', [idles.length, timers.size], [2, 0]);
}

// ----------------------------------------------------------------------- the real thing: a server that accepts and never answers
{
  const realFetch = globalThis.fetch;
  let mode = 'ok';                                     // ok | hang (accept every connection, answer nothing)
  const sockets = new Set();
  const server = http.createServer((req, res) => {
    if (mode === 'hang') return;                      // never respond
    if (req.url.startsWith('/api/os/session')) { res.setHeader('content-type', 'application/json'); res.end(JSON.stringify({ boot_id: 'B1' })); return; }
    if (req.url.startsWith('/api/os/stuck')) return;  // this one endpoint never answers, the server itself is fine
    if (req.url.startsWith('/api/os/halfbody')) { res.writeHead(200, { 'content-type': 'application/json' }); res.write('{"a":'); return; }
    if (req.url.startsWith('/api/os/stream')) {
      res.writeHead(200, { 'content-type': 'text/event-stream' });
      res.write('data: {"n":1}\n\n');
      return;                                         // ...and then silence, forever
    }
    res.setHeader('content-type', 'application/json'); res.end(JSON.stringify({ ok: true }));
  });
  server.on('connection', (s) => { sockets.add(s); s.on('close', () => sockets.delete(s)); });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const origin = `http://127.0.0.1:${server.address().port}`;
  globalThis.fetch = (u, o) => realFetch(typeof u === 'string' && u.startsWith('/') ? origin + u : u, o);
  const states = []; theNet.subscribe((e) => { if (e.type === 'state') states.push(e.state); });

  eq('a live server answers an ordinary call', await get('/anything'), { ok: true });

  // one request that never answers, on a healthy server: this request fails, nothing else is declared dead
  const t0 = Date.now();
  const e1 = await get('/stuck', undefined, { timeoutMs: 300 }).then(() => null, (e) => e);
  eq('one stuck request on a live server: a plain, showable error, not a network error', [e1 instanceof ApiError, e1?.status, e1?.network, e1?.timedOut], [true, 408, false, true]);
  yes('...which waited for its deadline and one quick probe only', Date.now() - t0 < 2500);
  eq('and the desktop never went offline (the probe confirmed first)', [theNet.state, states.includes('offline')], ['online', false]);

  // a body that stalls after the headers
  const e2 = await get('/halfbody', undefined, { timeoutMs: 300 }).then(() => null, (e) => e);
  eq('headers then silence is caught by the same deadline', [e2?.timedOut, e2?.network], [true, false]);
  eq('...still online', theNet.state, 'online');

  // the whole server hangs: accepts everything, answers nothing
  mode = 'hang';
  const t1 = Date.now();
  const e3 = await get('/system', undefined, { timeoutMs: 300 }).then(() => null, (e) => e);
  const took = Date.now() - t1;
  eq('a hung server: the request fails as a network error', [e3?.network, e3?.timedOut], [true, true]);
  eq('and the desktop is OFFLINE (deadline, then the probe also got no answer)', [theNet.state, states.includes('checking'), states.includes('offline')], ['offline', true, true]);
  yes(`...after the deadline plus the probe time (took ${took} ms)`, took >= 300 + PROBE_TIMEOUT_MS - 200 && took < 300 + PROBE_TIMEOUT_MS + 2500);
  const before = Date.now();
  const e4 = await get('/system', undefined, { timeoutMs: 200 }).then(() => null, (e) => e);
  yes('while offline another timeout is answered at once (no second probe wait)', Date.now() - before < 1200 && e4?.network === true);

  // it comes back
  mode = 'ok';
  await theNet.retryNow();
  eq('a probe that is answered again brings the desktop back online', theNet.state, 'online');
  for (const s of sockets) s.destroy();

  // a stream that goes silent on a live server is left alone; on a hung server it is dropped as "connection lost"
  const got = [];
  const ac = new AbortController();
  const live = streamEvents('/stream', {}, (ev) => got.push(ev.n), ac.signal, { idleMs: 250 }).then(() => 'ended', (e) => e);
  await new Promise((r) => setTimeout(r, 900));
  eq('a quiet stream on a live server is not touched (the probe says alive)', [got, theNet.state], [[1], 'online']);
  mode = 'hang';
  const lost = await live;
  eq('the same stream once the server hangs: connection lost, network error', [lost?.network, lost?.lost], [true, true]);
  eq('...and the desktop is offline', theNet.state, 'offline');
  mode = 'ok';
  await theNet.retryNow();
  const ac2 = new AbortController();
  const stop = streamEvents('/stream', {}, () => {}, ac2.signal, { idleMs: 60000 }).then(() => 'ended', (e) => e);
  setTimeout(() => ac2.abort(), 150);
  eq('the caller aborting a stream is still a plain AbortError', (await stop)?.name, 'AbortError');

  globalThis.fetch = realFetch;
  for (const s of sockets) s.destroy();
  await new Promise((r) => server.close(r));
}

process.exit(failures ? 1 : 0);
