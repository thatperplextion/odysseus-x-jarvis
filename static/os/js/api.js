// Thin client for /api/os/*. Same-origin cookie session, JSON in/out.
//
// Network trouble (the server is gone, a stream died, a proxy answers 502/503/504) is reported to net.js, which owns the
// "Odysseus isn't responding" banner, the reconnect probe and the polling pause. Callers just see an ApiError with
// `network: true` (status 0, or the proxy's status) and a calm message; error toasts are suppressed while offline.

import {
  isNetworkFailure, isGatewayStatus, reportFailure, reportSuccess, suspect, subscribe, fetchWithTimeout, createIdleWatch,
  REQUEST_TIMEOUT_MS, LONG_TIMEOUT_MS, STREAM_START_MS, STREAM_IDLE_MS, UPLOAD_IDLE_MS,
} from './net.js';

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    this.network = false;      // true: the server could not be reached (not "it said no")
  }
}

export const OFFLINE_MESSAGE = 'Odysseus isn’t responding.';
export const SLOW_MESSAGE = 'Odysseus took too long to answer. Try again.';

// Calls that legitimately take long get a long deadline: the AI planner (a few model turns), bulk file work. Everything else has
// REQUEST_TIMEOUT_MS. Streams and uploads have no total time (see streamEvents / uploadFile); callers can pass `timeoutMs` too.
const LONG_PATHS = /^\/(assistant$|fs\/(transfer|search|delete|write)|fs\/trash\/(restore|purge|empty))/;
export const timeoutFor = (path) => (LONG_PATHS.test(path) ? LONG_TIMEOUT_MS : REQUEST_TIMEOUT_MS);

/** The error for an unreachable server; `cause` is what fetch() / the stream reader rejected with. */
export function networkError(cause, { status = 0, message = OFFLINE_MESSAGE, lost = false } = {}) {
  const e = new ApiError(status, message, null);
  e.network = true;
  e.lost = lost;           // true: a response had started and then the connection died
  e.cause = cause;
  return e;
}

/**
 * A request reached its deadline. Ask the server (net.js probes it once) before saying what happened: if it answers, only this
 * request was slow or stuck, so the caller gets an ordinary error it can show; if it does not, the server is gone or hung and the
 * caller gets the network error that the connection banner already explains.
 */
async function fromTimeout(te) {
  const verdict = te.why === 'offline' ? 'offline' : await suspect();
  if (verdict === 'offline') { const e = networkError(te); e.timedOut = true; return e; }
  const e = new ApiError(408, SLOW_MESSAGE, null);
  e.timedOut = true;
  return e;
}

/**
 * fetch() for every Odysseus client: tells net.js how it went. A rejected fetch becomes a network ApiError (the caller's own
 * AbortError passes through untouched); a real HTTP answer, whatever its status, proves the server is there, except a
 * proxy's 502/503/504 page. Has a deadline (`init.timeoutMs`, default 20 s; 0 = none; `init.headersOnly` ends it when the headers
 * arrive). Does not patch window.fetch.
 */
export async function netFetch(input, init = {}) {
  const { timeoutMs = REQUEST_TIMEOUT_MS, headersOnly = false, ...fetchInit } = init;
  // A long request stops waiting as soon as the desktop has given the server up, instead of sitting out its whole deadline.
  const watch = timeoutMs > REQUEST_TIMEOUT_MS ? (abort) => subscribe((ev) => { if (ev.state === 'offline') abort(); }) : null;
  let res;
  try { res = await fetchWithTimeout(input, fetchInit, { timeoutMs, headersOnly, watch, mapTimeout: fromTimeout }); }
  catch (e) {
    if (e instanceof ApiError) throw e;
    if (isNetworkFailure(e)) { reportFailure(); throw networkError(e); }
    throw e;
  }
  if (isGatewayStatus(res.status, res.headers.get('content-type'))) reportFailure();
  else reportSuccess();
  return res;
}

/** The ApiError for a 502/503/504 proxy page, or null for any other response. */
export function gatewayError(res) {
  return isGatewayStatus(res.status, res.headers.get('content-type')) ? networkError(null, { status: res.status }) : null;
}

function describe(body, fallback) {
  if (!body) return fallback;
  const d = body.detail ?? body.error ?? body.message;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => (x.msg ? `${(x.loc || []).slice(1).join('.')}: ${x.msg}` : String(x))).join('; ');
  return fallback;
}

async function failure(res) {
  const gateway = gatewayError(res);
  if (gateway) return gateway;
  let body = null;
  let text = '';
  try { text = await res.text(); body = JSON.parse(text); } catch { /* not JSON */ }
  if (res.status === 401) { window.location.href = '/login'; }
  return new ApiError(res.status, describe(body, text || res.statusText || `HTTP ${res.status}`), body);
}

function url(path, params) {
  const q = params
    ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null).map(([k, v]) => [k, String(v)]))
    : '';
  return '/api/os' + path + q;
}

export async function api(path, { method = 'GET', json, params, signal, body, headers, timeoutMs } = {}) {
  const init = { method, credentials: 'same-origin', signal, headers: { ...(headers || {}) }, timeoutMs: timeoutMs ?? timeoutFor(path) };
  if (json !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(json); }
  else if (body !== undefined) init.body = body;
  const res = await netFetch(url(path, params), init);
  if (!res.ok) throw await failure(res);
  if (res.status === 204) return null;
  return res.json();
}

export const get = (path, params, opts) => api(path, { ...opts, params });
export const post = (path, json, opts) => api(path, { ...opts, method: 'POST', json: json ?? {} });
export const put = (path, json, opts) => api(path, { ...opts, method: 'PUT', json });
export const del = (path, opts) => api(path, { ...opts, method: 'DELETE' });
export const patch = (path, json, opts) => api(path, { ...opts, method: 'PATCH', json });

/** URL for raw file bytes (used as <img src>, download links, ...). */
export const rawUrl = (path, download = false) => url('/fs/raw', { path, download: download ? 'true' : undefined });

/**
 * Stream server-sent events (`data: {json}`) from a POST. Resolves when the stream ends; abort via `signal`.
 * If the connection dies after the response started it rejects with a network ApiError whose `lost` is true
 * (callers say "connection lost" instead of showing a raw "network error").
 * A stream has no total time limit (a command or a benchmark can run for minutes), but the server has to answer with its headers
 * within STREAM_START_MS and may not stay silent unnoticed: after STREAM_IDLE_MS without a byte the server is asked whether it is
 * alive (net.js suspect()). If it is, the silence was just the work; if it is not, the stream is dropped as "connection lost".
 */
export async function streamEvents(path, json, onEvent, signal, { idleMs = STREAM_IDLE_MS } = {}) {
  const ctrl = new AbortController();
  const relay = () => ctrl.abort();
  if (signal) { if (signal.aborted) ctrl.abort(); else signal.addEventListener('abort', relay, { once: true }); }
  let idle = null;
  let silent = false;            // WE cut the stream because the server stopped answering
  try {
    const res = await netFetch(url(path), {
      method: 'POST', credentials: 'same-origin', signal: ctrl.signal,
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(json),
      timeoutMs: STREAM_START_MS, headersOnly: true,
    });
    if (!res.ok) throw await failure(res);
    idle = createIdleWatch(idleMs, async () => { if ((await suspect()) === 'offline') { silent = true; ctrl.abort(); } });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    const flush = (frame) => {
      const data = frame.split('\n').filter((l) => l.startsWith('data:')).map((l) => l.slice(5).replace(/^ /, '')).join('\n');
      if (data) onEvent(JSON.parse(data));
    };
    for (;;) {
      let chunk;
      try { chunk = await reader.read(); }
      catch (e) {
        if (silent || isNetworkFailure(e)) { reportFailure(); throw networkError(e, { lost: true, message: 'The connection to Odysseus was lost.' }); }
        throw e;       // the caller's own abort
      }
      const { value, done } = chunk;
      if (done) break;
      idle.poke();
      buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      let end;
      while ((end = buf.indexOf('\n\n')) >= 0) {   // a blank line ends one event
        flush(buf.slice(0, end));
        buf = buf.slice(end + 2);
      }
    }
    buf += decoder.decode();
    if (buf.trim()) flush(buf.trim());
  } finally {
    if (idle) idle.stop();
    if (signal) signal.removeEventListener('abort', relay);
  }
}

/**
 * Upload a File with progress. Resolves with the server's JSON; rejects with ApiError. No total time limit (a big file takes as
 * long as it takes), but UPLOAD_IDLE_MS without any progress asks the server whether it is alive; if it is not, the upload is
 * dropped with a network error.
 */
export function uploadFile(path, file, { overwrite = false, onProgress, signal } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    let stalled = false;
    const idle = createIdleWatch(UPLOAD_IDLE_MS, async () => { if ((await suspect()) === 'offline') { stalled = true; xhr.abort(); } });
    const end = () => idle.stop();
    xhr.open('PUT', url('/fs/upload', { path, overwrite: overwrite ? 'true' : undefined }));
    xhr.withCredentials = true;
    xhr.upload.onprogress = (e) => { idle.poke(); if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total); };
    xhr.onload = () => {
      end();
      let body = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300) { reportSuccess(); resolve(body); return; }
      if (isGatewayStatus(xhr.status, xhr.getResponseHeader('content-type'))) { reportFailure(); reject(networkError(null, { status: xhr.status })); return; }
      reportSuccess();
      reject(new ApiError(xhr.status, describe(body, xhr.statusText || `HTTP ${xhr.status}`), body));
    };
    xhr.onerror = () => { end(); reportFailure(); reject(networkError(null, { message: 'Odysseus stopped responding during the upload.' })); };
    xhr.onabort = () => { end(); reject(stalled ? networkError(null, { lost: true, message: 'Odysseus stopped responding during the upload.' }) : new ApiError(0, 'Upload cancelled')); };
    if (signal) signal.addEventListener('abort', () => xhr.abort());
    xhr.send(file);
  });
}
