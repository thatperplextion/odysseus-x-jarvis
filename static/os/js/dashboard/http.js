// Dashboard · clients for the existing Odysseus APIs outside /api/os (Notes checklist toggle, scheduler runs).
// Same behaviour as api.js (ApiError, redirect to /login on 401); api.js itself is pinned to /api/os.

import { ApiError, netFetch, gatewayError } from '../api.js';

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

const enc = encodeURIComponent;

export const notesApi = {
  toggleItem: (noteId, index) => request(`/api/notes/${enc(noteId)}/items/${index}/toggle`, { method: 'POST', json: {} }),
  archive: (noteId) => request(`/api/notes/${enc(noteId)}/archive`, { method: 'POST', json: {} }),
};

export const tasksApi = {
  run: (id) => request(`/api/tasks/${enc(id)}/run`, { method: 'POST', json: {} }),
  recent: (limit = 15) => request('/api/tasks/runs/recent', { params: { limit, max_result_chars: 300 } }),
};
