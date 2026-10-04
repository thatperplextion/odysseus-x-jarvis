// Preferences + desktop session. localStorage is the fast path (and works if the server
// is slow); the server copy (/api/os/session) follows the user across browsers.

import { get, put } from './api.js';
import { debounce } from './dom.js';
import { migrateDock } from './dock-migrate.js';

const DEFAULTS = {
  theme: 'auto',              // auto | light | dark
  wallpaper: 'paper',         // paper | dusk | ink
  shell: null,                // default terminal shell id
  showHidden: false,
  filesView: 'list',          // list | grid
  filesSort: { key: 'name', dir: 'asc' },
  dock: ['jarvis', 'files', 'terminal', 'taskmgr', 'automations', 'chat', 'notes', 'settings'],
  recent: [],                 // recently opened file paths
  sidebarCollapsed: false,
};

let userKey = 'local';
let prefs = { ...DEFAULTS };
let windows = [];
const listeners = new Set();

const storageKey = () => `ody.os.v1.${userKey}`;

function readLocal() {
  try { return JSON.parse(localStorage.getItem(storageKey()) || 'null'); } catch { return null; }
}
function writeLocal(data) {
  try { localStorage.setItem(storageKey(), JSON.stringify(data)); } catch { /* private mode / quota */ }
}

const pushToServer = debounce(async () => {
  try { await put('/session', { prefs, windows, saved: Date.now() }); } catch { /* offline: local copy still holds */ }
}, 1500);

function persist() {
  writeLocal({ prefs, windows, saved: Date.now() });
  pushToServer();
}

export async function loadState(user) {
  userKey = user || 'local';
  const local = readLocal();
  let server = null;
  try { server = (await get('/session')).session; } catch { /* use local */ }
  const newest = [local, server].filter((s) => s && s.prefs).sort((a, b) => (b.saved || 0) - (a.saved || 0))[0];
  if (newest) {
    prefs = { ...DEFAULTS, ...newest.prefs };
    windows = Array.isArray(newest.windows) ? newest.windows : [];
  }
  // Default dock apps added after the user saved their dock are offered once (see dock-migrate.js).
  const m = migrateDock(newest ? newest.prefs : null, DEFAULTS.dock);
  prefs = { ...prefs, dock: m.dock, dockOffered: m.dockOffered };
  if (newest && m.changed) persist();
  return { prefs, windows };
}

export const getPrefs = () => prefs;
export function setPref(key, value) {
  prefs = { ...prefs, [key]: value };
  persist();
  for (const fn of listeners) fn(key, value);
}
export const onPref = (fn) => { listeners.add(fn); return () => listeners.delete(fn); };

export const getSavedWindows = () => windows;
export function saveWindows(list) {
  windows = list;
  persist();
}

/** Forget a recent file that no longer exists (opening it answered 404), so the Recent lists stop offering it. */
export function dropRecent(path) {
  if (prefs.recent.includes(path)) setPref('recent', prefs.recent.filter((p) => p !== path));
}

export function pushRecent(path) {
  const next = [path, ...prefs.recent.filter((p) => p !== path)].slice(0, 8);
  setPref('recent', next);
}

export function applyTheme() {
  document.documentElement.dataset.theme = prefs.theme;
  document.documentElement.dataset.wallpaper = prefs.wallpaper;
  try { localStorage.setItem('ody.os.theme', prefs.theme); } catch { /* ignore */ }
}
