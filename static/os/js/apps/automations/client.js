// Automations · client for the existing scheduler API (/api/tasks/*). The OS shell's own api.js is pinned to
// /api/os, so this is a small sibling with the same error behaviour (ApiError, redirect to /login on 401).

import { ApiError, netFetch, gatewayError } from '../../api.js';

function describe(body, fallback) {
  if (!body) return fallback;
  const d = body.detail ?? body.error ?? body.message;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => (x.msg ? `${(x.loc || []).slice(1).join('.')}: ${x.msg}` : String(x))).join('; ');
  return fallback;
}

async function request(url, { method = 'GET', json, params, signal, timeoutMs } = {}) {
  const q = params ? `?${new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null).map(([k, v]) => [k, String(v)]))}` : '';
  const init = { method, credentials: 'same-origin', signal, headers: {}, timeoutMs };     // undefined = the default 20 s deadline
  if (json !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(json); }
  const res = await netFetch(url + q, init);       // reports an unreachable server to net.js (banner, polling pause)
  if (!res.ok) {
    const gateway = gatewayError(res);
    if (gateway) throw gateway;
    let body = null; let text = '';
    try { text = await res.text(); body = JSON.parse(text); } catch { /* not JSON */ }
    if (res.status === 401) window.location.href = '/login';
    throw new ApiError(res.status, describe(body, text || res.statusText || `HTTP ${res.status}`), body);
  }
  if (res.status === 204) return null;
  return res.json();
}

const T = '/api/tasks';
export const tasksApi = {
  list: (opts) => request(T, opts),
  recent: (limit = 60) => request(`${T}/runs/recent`, { params: { limit, max_result_chars: 500 } }),
  runs: (id, { limit = 20, offset = 0 } = {}) => request(`${T}/${encodeURIComponent(id)}/runs`, { params: { limit, offset } }),
  create: (payload) => request(T, { method: 'POST', json: payload }),
  update: (id, payload) => request(`${T}/${encodeURIComponent(id)}`, { method: 'PUT', json: payload }),
  remove: (id) => request(`${T}/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  pause: (id) => request(`${T}/${encodeURIComponent(id)}/pause`, { method: 'POST', json: {} }),
  resume: (id) => request(`${T}/${encodeURIComponent(id)}/resume`, { method: 'POST', json: {} }),
  run: (id, force = false) => request(`${T}/${encodeURIComponent(id)}/run`, { method: 'POST', json: {}, params: force ? { force: 'true' } : undefined }),
  stop: (id) => request(`${T}/${encodeURIComponent(id)}/stop`, { method: 'POST', json: {} }),
  revert: (id) => request(`${T}/${encodeURIComponent(id)}/revert`, { method: 'POST', json: {} }),
  regenerateWebhook: (id) => request(`${T}/${encodeURIComponent(id)}/webhook-regenerate`, { method: 'POST', json: {} }),
  parse: (description) => request(`${T}/parse`, { method: 'POST', json: { description }, timeoutMs: 90000 }),    // asks a language model (the server waits up to 45 s for it)
  actions: () => request(`${T}/meta/actions`),
  events: () => request(`${T}/meta/events`),
  targets: () => request(`${T}/meta/output-targets`),
  models: () => request('/api/model-endpoints'),
  // Same first-open handshake as the classic Tasks page: until it has happened the server keeps switching paused built-ins back off.
  onboarding: () => request(`${T}/onboarding`),
  markOpened: () => request(`${T}/onboarding`, { method: 'POST', json: { enabled: false } }),
};

export { ApiError };
