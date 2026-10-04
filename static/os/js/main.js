// Odysseus OS: the desktop shell. Boots, builds the menubar/dock/home, owns the app registry.

import { h, icon, clear, toast, dialog, debounce, basename, dirname, fmtDate, contextMenu, closeContextMenu } from './dom.js';
import { get, post, ApiError, rawUrl } from './api.js';
import { systemSnapshot } from './sysmon.js';
import { isOnline, net } from './net.js';
import { initNetUi } from './netui.js';
import { os, kindOf } from './ctx.js';
import { WindowManager } from './wm.js';
import { loadState, getPrefs, setPref, onPref, applyTheme, getSavedWindows, saveWindows } from './state.js';
import * as filesApp from './apps/files.js';
import * as editorApp from './apps/editor.js';
import * as viewerApp from './apps/viewer.js';
import * as terminalApp from './apps/terminal.js';
import * as taskmgrApp from './apps/taskmgr.js';
import * as settingsApp from './apps/settings.js';
import * as jarvisApp from './apps/jarvis.js';
import * as automationsApp from './apps/automations.js';
import { EMBEDS, embedApp } from './apps/odysseus.js';
import { createDashboard } from './dashboard/index.js';

const APPS = new Map();
function register(mod, extra = {}) { APPS.set(mod.meta.id, { ...mod.meta, mount: mod.mount, ...extra }); }
register(jarvisApp);
register(filesApp);
register(terminalApp);
register(taskmgrApp);
register(automationsApp);
register(settingsApp);
register(editorApp, { hidden: true });
register(viewerApp, { hidden: true });
for (const e of EMBEDS) register(embedApp(e));

const $id = (id) => document.getElementById(id);
let wm = null;

// ============================================================ boot screen
function bootScreen({ title, message, detail, actions = [] }) {
  const el = $id('boot');
  el.hidden = false;
  clear(el);
  el.append(h('div', { class: 'boot-card' },
    h('div', { class: 'boot-mark serif' }, 'Odysseus', h('em', { text: ' OS' })),
    h('h1', { class: 'boot-title', text: title }),
    message && h('p', { class: 'boot-msg', text: message }),
    detail && h('pre', { class: 'boot-detail mono', text: detail }),
    actions.length > 0 && h('div', { class: 'boot-actions' }, actions.map((a) => h(a.href ? 'a' : 'button', { class: ['btn', a.primary ? 'btn-ink' : 'btn-soft'], href: a.href, text: a.label, on: a.run ? { click: a.run } : undefined })))));
}

let bootRetryArmed = false;
let booting = false;
async function boot() {
  if (booting) return;        // a reconnect and a "Try again" click can arrive together
  booting = true;
  try { await bootOnce(); } finally { booting = false; }
}
async function bootOnce() {
  try { applyTheme(); } catch { /* theme is cosmetic */ }
  initNetUi();
  bootScreen({ title: 'Starting up…', message: 'Waking the Jarvis kernel.' });
  let data;
  try {
    data = await get('/boot');
  } catch (e) {
    if (e instanceof ApiError && e.network) {
      // Odysseus is not answering (yet): the banner keeps probing, and the desktop starts by itself when it does.
      bootScreen({ title: 'Can’t reach Odysseus', message: 'It isn’t responding. This page will start as soon as it is back.', actions: [{ label: 'Try again', primary: true, run: () => net.retryNow() }] });
      if (!bootRetryArmed) { bootRetryArmed = true; os.on('reconnected', () => { if ($id('desktop').hidden) boot(); }); }
      setTimeout(() => { if ($id('desktop').hidden && isOnline()) boot(); }, 2500);     // it was only a blip: the probe answered, so no 'reconnected' will come
      return;
    }
    if (e instanceof ApiError && e.status === 403) {
      bootScreen({
        title: 'Administrators only',
        message: /Host not allowed/.test(e.message) ? 'With sign-in turned off, Odysseus OS only answers on localhost.' : 'Odysseus OS can read files, run commands and control processes, so it is limited to admin accounts.',
        detail: e.message,
        actions: [{ label: 'Back to Odysseus', href: '/', primary: true }],
      });
    } else {
      bootScreen({ title: 'Can’t reach Odysseus', message: e.message, actions: [{ label: 'Try again', primary: true, run: boot }] });
    }
    return;
  }
  if (!data.ready) {
    bootScreen({
      title: 'Jarvis isn’t running',
      message: `The kernel is “${data.jarvis_state}”.`,
      detail: data.jarvis_error || 'Check the Odysseus log for the startup error.',
      actions: [{ label: 'Try again', primary: true, run: boot }, { label: 'Back to Odysseus', href: '/' }],
    });
    return;
  }
  os.boot = data;
  net.setBootId(data.boot_id);          // lets a reconnect tell "same server" from "Odysseus restarted"
  await loadState(data.user);
  applyTheme();
  buildDesktop();
  $id('boot').hidden = true;
  $id('desktop').hidden = false;
  restoreWindows();
}

// ============================================================== registry
os.appList = () => [...APPS.values()];

os.openApp = (id, props = {}) => {
  const app = APPS.get(id);
  if (!app) { toast(`Unknown app “${id}”`, { kind: 'error' }); return null; }
  let singletonKey = null;
  if (app.singleton) singletonKey = id;
  else if (id === 'editor') singletonKey = `editor:${props.path}`;
  else if (id === 'viewer') singletonKey = 'viewer';
  return wm.open({
    app: id, title: app.name, icon: app.icon, width: app.width, height: app.height, props, singletonKey,
    onReuse: (w) => w.handle?.onReuse?.(props),
    mount: (body, win) => app.mount(body, win, props),
  });
};

os.openFile = (path, entry) => {
  const name = basename(path);
  switch (kindOf(name)) {
    case 'image': case 'audio': case 'video': os.openApp('viewer', { path }); break;
    case 'text': os.openApp('editor', { path }); break;
    default: {
      const a = h('a', { href: rawUrl(path, true), download: name });
      document.body.append(a); a.click(); a.remove();
      toast(`“${name}” can’t be previewed, so it is downloading instead.`, { ms: 3500 });
    }
  }
};

os.refreshMounts = async () => {
  const data = await get('/boot');
  os.boot.mounts = data.mounts;
  os.boot.suggested_mounts = data.suggested_mounts;
  os.emit('mounts');
};

os.askJarvis = (text) => os.openApp('jarvis', { ask: text });

// ============================================================ desktop shell
function buildDesktop() {
  const desktop = $id('desktop');
  clear(desktop);

  // -- menubar
  const activeName = h('span', { class: 'mb-active', text: 'Desktop' });
  const brand = h('button', { class: 'mb-brand serif', 'aria-label': 'Odysseus OS menu', on: { click: (e) => brandMenu(e.currentTarget) } }, 'Odysseus', h('em', { text: ' OS' }));
  const trigger = h('button', { class: 'mb-trigger', 'aria-label': 'Search or ask Jarvis', on: { click: () => openPalette() } },
    icon('search', 14), h('span', { text: 'Search, or ask Jarvis…' }), h('kbd', { text: 'Ctrl K' }));
  const pulse = h('span', { class: 'mb-pulse mono', title: 'CPU · Memory', text: '' });
  const bell = h('button', { class: 'mb-btn', 'aria-label': 'Notifications', title: 'Notifications', on: { click: () => toggleNotifications(bell) } }, icon('bell', 16), h('i', { class: 'bell-dot', hidden: true }));
  const themeBtn = h('button', { class: 'mb-btn', 'aria-label': 'Change theme', title: 'Theme', on: { click: cycleTheme } });
  const clock = h('span', { class: 'mb-clock mono' });
  const userName = shortName();
  const userBtn = h('button', { class: 'mb-user', 'aria-label': `Account: ${userName}`, title: userName, on: { click: (e) => userMenu(e.currentTarget) } }, userName.slice(0, 1).toUpperCase());
  const dash = createDashboard();      // the "Today" command centre under the greeting (static/os/js/dashboard/)
  os.dashboard = dash;
  const menubar = h('header', { id: 'menubar' }, brand, activeName, h('span', { class: 'win-spacer' }), trigger, h('span', { class: 'win-spacer' }), dash.focusChip, pulse, bell, themeBtn, clock, userBtn);

  // -- workspace
  const home = h('section', { id: 'home', 'aria-label': 'Desktop' });
  const windows = h('div', { id: 'windows' });
  const workspace = h('main', { id: 'workspace' }, home, windows);

  // -- dock
  const dock = h('nav', { id: 'dock', 'aria-label': 'Dock' });
  desktop.append(menubar, workspace, dock);

  wm = new WindowManager(windows, {
    onEvent: (type, win) => {
      if (['open', 'close', 'focus', 'minimize', 'restore', 'title'].includes(type)) { renderDock(); updateActive(); }
      if (type === 'change' || type === 'open' || type === 'close') saveWindows(wm.serialize());
      if (type === 'open' && win && win.app && win.props?.path) { /* recents are pushed by the apps */ }
      home.classList.toggle('behind', wm.list().some((w) => w.state !== 'min'));
    },
  });
  os.wm = wm;

  function updateActive() {
    const top = wm.list().find((w) => w.focused);
    activeName.textContent = top ? top.title.replace(/^•\s*/, '') : 'Desktop';
  }

  // -- dock
  function renderDock() {
    clear(dock);
    const pinned = getPrefs().dock.filter((id) => APPS.has(id));
    const running = [...new Set(wm.list().map((w) => w.app))].filter((id) => !pinned.includes(id) && !APPS.get(id)?.hiddenInDock);
    for (const id of [...pinned, ...running]) {
      const app = APPS.get(id);
      if (!app) continue;
      const wins = wm.list().filter((w) => w.app === id);
      const focused = wins.some((w) => w.focused);
      const item = h('button', {
        class: ['dock-item', wins.length && 'running', focused && 'focused'], 'aria-label': app.name, dataset: { label: app.name, app: id },
        on: {
          click: () => dockClick(id, wins),
          contextmenu: (e) => { e.preventDefault(); dockMenu(e.clientX, e.clientY, id, wins); },
        },
      }, icon(app.icon, 22), wins.length > 1 && h('span', { class: 'dock-count', text: wins.length }));
      dock.append(item);
    }
    dock.append(h('span', { class: 'dock-sep' }),
      h('button', { class: 'dock-item', 'aria-label': 'All apps', dataset: { label: 'All apps' }, on: { click: openLauncher } }, icon('grid', 22)));
  }

  function dockClick(id, wins) {
    if (!wins.length) { os.openApp(id); return; }
    if (wins.length === 1) {
      const w = wins[0];
      if (w.state === 'min') w.focus();
      else if (w.focused) w.minimize();
      else w.focus();
      return;
    }
    const top = wins.filter((w) => w.state !== 'min').sort((a, b) => b.z - a.z)[0] || wins[0];
    if (!top.focused || top.state === 'min') top.focus();
    else { const next = wins.filter((w) => w !== top).sort((a, b) => b.z - a.z)[0]; next?.focus(); }
  }

  function dockMenu(x, y, id, wins) {
    const app = APPS.get(id);
    const pinned = getPrefs().dock.includes(id);
    contextMenu(x, y, [
      ...wins.map((w) => ({ label: w.title.slice(0, 40), icon: app.icon, run: () => w.focus() })),
      wins.length && 'sep',
      !app.singleton && { label: `New ${app.name} window`, icon: 'plus', run: () => os.openApp(id) },
      !wins.length && { label: `Open ${app.name}`, icon: app.icon, run: () => os.openApp(id) },
      { label: pinned ? 'Unpin from dock' : 'Pin to dock', icon: 'star', run: () => setPref('dock', pinned ? getPrefs().dock.filter((d) => d !== id) : [...getPrefs().dock, id]) },
      wins.length && 'sep',
      wins.length && { label: wins.length > 1 ? 'Close all windows' : 'Close', icon: 'x', danger: true, run: () => wins.forEach((w) => w.close()) },
    ].filter(Boolean));
  }
  onPref((k) => { if (k === 'dock') renderDock(); if (k === 'theme' || k === 'wallpaper') updateThemeBtn(); if (k === 'recent') renderHome(); });

  // -- home (desktop) -------------------------------------------------------
  // The head (date, greeting, pills) is rebuilt every few minutes; the dashboard below it is built once and stays live.
  const homeHead = h('div', { class: 'home-head' });
  const homeRecent = h('div', { class: 'home-recent', hidden: true });
  home.append(h('div', { class: 'home-inner' }, homeHead, dash.el, homeRecent));
  function renderHome() {
    clear(homeHead);
    const now = new Date();
    const hour = now.getHours();
    const greet = hour < 5 ? 'Still up' : hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
    const recent = (getPrefs().recent || []).slice(0, 5);
    // Native append() turns false/null into the text "false"/"null", hence the filter.
    homeHead.append(...[
      h('p', { class: 'eyebrow mono', text: now.toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' }).toUpperCase() }),
      h('h1', { class: 'home-title serif' }, `${greet}, `, h('em', { text: `${userName}.` })),
      dash.summaryEl,
      h('div', { class: 'home-actions' },
        h('button', { class: 'btn btn-ink btn-lg', on: { click: () => os.openApp('jarvis') } }, icon('sparkles', 16), 'Ask Jarvis'),
        h('button', { class: 'btn btn-soft btn-lg', on: { click: () => os.openApp('files') } }, icon('folder', 16), 'Files'),
        h('button', { class: 'btn btn-soft btn-lg', on: { click: () => os.openApp('terminal') } }, icon('terminal', 16), 'Terminal'),
        h('button', { class: 'btn btn-soft btn-lg', on: { click: () => os.openApp('chat') } }, icon('message', 16), 'Chat'))].filter(Boolean));
    clear(homeRecent);
    homeRecent.hidden = recent.length === 0;
    if (recent.length > 0) {
      homeRecent.append(h('div', { class: 'eyebrow mono', text: 'RECENT' }),
        recent.map((p) => h('button', { class: 'recent-item', on: { click: () => os.openFile(p) }, title: p }, icon('file-text', 15), h('span', { class: 'recent-name', text: basename(p) }), h('span', { class: 'recent-dir muted mono', text: dirname(p) }))));
    }
  }

  /** "Open Today": get the windows out of the way and show the dashboard from the top. */
  os.showToday = () => {
    for (const w of wm.list()) if (w.state !== 'min') w.minimize();
    home.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // -- clock / tray -----------------------------------------------------------
  const tick = () => { clock.textContent = new Date().toLocaleString([], { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }); };
  tick();
  setInterval(tick, 20000);
  setInterval(() => { renderHome(); }, 10 * 60 * 1000);

  async function updatePulse() {
    if (document.hidden) return;
    if (!isOnline()) { pulse.textContent = ''; return; }       // no stale numbers, and no polling of a dead server
    try {
      const s = await systemSnapshot();
      pulse.textContent = `CPU ${s.cpu.percent.toFixed(0)}%  ·  RAM ${s.memory.percent.toFixed(0)}%`;
    } catch { pulse.textContent = ''; }
  }
  updatePulse();
  setInterval(updatePulse, 6000);
  os.on('reconnected', updatePulse);
  net.subscribe(() => { if (!isOnline()) pulse.textContent = ''; });       // stale numbers would be a lie

  // -- theme ------------------------------------------------------------------
  function updateThemeBtn() {
    const t = getPrefs().theme;
    themeBtn.replaceChildren(icon(t === 'dark' ? 'moon' : t === 'light' ? 'sun' : 'eye', 16));
    themeBtn.title = `Theme: ${t}`;
  }
  function cycleTheme() {
    const order = ['auto', 'light', 'dark'];
    setPref('theme', order[(order.indexOf(getPrefs().theme) + 1) % 3]);
    applyTheme();
    updateThemeBtn();
    toast(`Theme: ${getPrefs().theme}`, { ms: 1200 });
  }
  updateThemeBtn();

  // -- notifications --------------------------------------------------------
  let panel = null;
  const bellDot = bell.querySelector('.bell-dot');
  async function pollNotifications() {
    if (document.hidden || !isOnline()) return;
    try {
      const { notifications } = await get('/notifications', { unread_only: 'true' });
      bellDot.hidden = !notifications.length;
    } catch { /* ignore */ }
  }
  pollNotifications();
  setInterval(pollNotifications, 15000);
  os.on('reconnected', pollNotifications);

  async function toggleNotifications(anchor) {
    if (panel) { panel.remove(); panel = null; return; }
    let items = [];
    try { items = (await get('/notifications')).notifications; } catch (e) { toast(e.message, { kind: 'error' }); }
    panel = h('div', { class: 'popover notif', role: 'dialog', 'aria-label': 'Notifications' },
      h('div', { class: 'popover-head' }, h('strong', { text: 'Notifications' })),
      items.length ? h('div', { class: 'notif-list' }, items.map((n) => h('div', { class: ['notif-item', !n.read && 'unread'] },
        h('div', { class: 'notif-title', text: n.title }), h('div', { class: 'notif-msg', text: n.message }), h('div', { class: 'notif-time muted mono', text: fmtDate(n.timestamp) }))))
        : h('div', { class: 'notif-empty muted' }, icon('bell', 22), h('p', { text: 'You’re all caught up.' })));
    $id('overlays').append(panel);
    const r = anchor.getBoundingClientRect();
    panel.style.top = `${r.bottom + 8}px`;
    panel.style.right = `${Math.max(8, window.innerWidth - r.right - 8)}px`;
    for (const n of items.filter((x) => !x.read)) post('/notifications/read', { id: n.id }).catch(() => {});
    bellDot.hidden = true;
    const away = (e) => { if (panel && !panel.contains(e.target) && !anchor.contains(e.target)) { panel.remove(); panel = null; document.removeEventListener('pointerdown', away, true); } };
    document.addEventListener('pointerdown', away, true);
  }

  // -- menus ------------------------------------------------------------------
  function brandMenu(anchor) {
    const r = anchor.getBoundingClientRect();
    contextMenu(r.left, r.bottom + 6, [
      { label: 'About this computer', icon: 'info', run: () => os.openApp('settings', { section: 'about' }) },
      { label: 'Settings', icon: 'sliders', run: () => os.openApp('settings') },
      'sep',
      { label: 'Back to Odysseus', icon: 'arrow-left', run: () => { window.location.href = '/'; } },
    ]);
  }
  function userMenu(anchor) {
    const r = anchor.getBoundingClientRect();
    contextMenu(Math.min(r.left, window.innerWidth - 220), r.bottom + 6, [
      { label: `Signed in as ${userName}`, icon: 'user', disabled: true },
      'sep',
      { label: 'Security & activity', icon: 'shield', run: () => os.openApp('settings', { section: 'security' }) },
      os.boot.auth_enabled && { label: 'Sign out', icon: 'power', danger: true, run: signOut },
    ].filter(Boolean));
  }
  async function signOut() {
    try { await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }); } catch { /* ignore */ }
    window.location.href = '/login';
  }

  renderHome();
  renderDock();
  updateActive();
  dash.start(home);
}

function shortName() {
  // "DOMAIN\Junaid Asad Khan" / "junaid@example.com" / "local"  ->  "Junaid"
  const u = os.boot.user && os.boot.user !== 'local' ? os.boot.user : (os.boot.system?.user || 'you');
  const first = u.split('\\').pop().split('@')[0].trim().split(/[\s._-]+/)[0] || 'you';
  return first.charAt(0).toUpperCase() + first.slice(1).toLowerCase();
}

// ============================================================== launcher
function openLauncher() {
  const apps = os.appList().filter((a) => !a.hidden);
  const search = h('input', { class: 'input launcher-search', type: 'search', placeholder: 'Search apps', 'aria-label': 'Search apps', spellcheck: 'false' });
  const grid = h('div', { class: 'launcher-grid', role: 'listbox' });
  const backdrop = h('div', { class: 'launcher', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'All apps' }, h('div', { class: 'launcher-box' }, search, grid));
  const close = () => { backdrop.remove(); document.removeEventListener('keydown', onKey, true); };
  const draw = () => {
    clear(grid);
    const q = search.value.trim().toLowerCase();
    const shown = apps.filter((a) => !q || a.name.toLowerCase().includes(q));
    for (const a of shown) {
      grid.append(h('button', { class: 'launch-item', role: 'option', on: { click: () => { close(); os.openApp(a.id); } } },
        h('span', { class: 'launch-icon' }, icon(a.icon, 26)), h('span', { class: 'launch-name', text: a.name })));
    }
    if (!shown.length) grid.append(h('p', { class: 'muted launch-none', text: 'No apps match.' }));
  };
  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'Enter') { const first = grid.querySelector('.launch-item'); if (first) { e.preventDefault(); first.click(); } }
  };
  search.addEventListener('input', draw);
  backdrop.addEventListener('pointerdown', (e) => { if (e.target === backdrop) close(); });
  document.addEventListener('keydown', onKey, true);
  draw();
  $id('overlays').append(backdrop);
  search.focus();
}

// ============================================================== palette
let paletteOpen = false;
function openPalette(initial = '') {
  if (paletteOpen) return;
  paletteOpen = true;
  const input = h('input', { class: 'palette-input', type: 'text', placeholder: 'Search apps and files, run an action, or ask Jarvis…', 'aria-label': 'Command palette', value: initial, spellcheck: 'false', autocomplete: 'off', role: 'combobox', 'aria-expanded': 'true', 'aria-controls': 'palette-list' });
  const list = h('div', { class: 'palette-list', id: 'palette-list', role: 'listbox' });
  const box = h('div', { class: 'palette', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Command palette' }, h('div', { class: 'palette-top' }, icon('search', 17), input), list,
    h('div', { class: 'palette-foot muted mono' }, h('span', { text: '↑↓ navigate' }), h('span', { text: '↵ open' }), h('span', { text: 'Esc close' })));
  const backdrop = h('div', { class: 'palette-backdrop' }, box);
  let results = [];
  let sel = 0;
  let fileHits = [];
  let token = 0;

  const close = () => { backdrop.remove(); paletteOpen = false; document.removeEventListener('keydown', onKey, true); };
  const act = (r) => { close(); r.run(); };

  const score = (name, q) => {
    const n = name.toLowerCase();
    if (!q) return 1;
    if (n.startsWith(q)) return 3;
    if (n.includes(q)) return 2;
    let i = 0;
    for (const ch of n) if (ch === q[i]) i++;
    return i === q.length ? 1 : 0;
  };

  const actions = [
    { label: 'New automation', icon: 'zap', run: () => os.openApp('automations', { intent: 'new' }) },
    { label: 'Start focus', icon: 'clock', run: () => os.dashboard?.startFocus() },
    { label: 'Open Today', icon: 'home', run: () => os.showToday?.() },
    { label: 'New terminal', icon: 'terminal', run: () => os.openApp('terminal') },
    { label: 'Toggle theme', icon: 'sun', run: () => { const o = ['auto', 'light', 'dark']; setPref('theme', o[(o.indexOf(getPrefs().theme) + 1) % 3]); applyTheme(); } },
    { label: 'Settings: Folders', icon: 'folder', run: () => os.openApp('settings', { section: 'folders' }) },
    { label: 'Settings: Security & activity', icon: 'shield', run: () => os.openApp('settings', { section: 'security' }) },
    { label: 'Back to Odysseus', icon: 'arrow-left', run: () => { window.location.href = '/'; } },
  ];

  function compute() {
    const q = input.value.trim().toLowerCase();
    const out = [];
    for (const a of os.appList().filter((x) => !x.hidden)) { const s = score(a.name, q); if (s) out.push({ s: s + 0.5, group: 'Apps', label: a.name, icon: a.icon, run: () => os.openApp(a.id) }); }
    for (const a of actions) { const s = score(a.label, q); if (s && q) out.push({ s, group: 'Actions', ...a }); }
    for (const f of fileHits) out.push({ s: 1.2, group: 'Files', label: basename(f.path), sub: dirname(f.path), icon: f.type === 'dir' ? 'folder' : 'file-text', run: () => (f.type === 'dir' ? os.openApp('files', { path: f.path }) : os.openFile(f.path)) });
    out.sort((a, b) => b.s - a.s);
    const trimmed = out.slice(0, 9);
    const raw = input.value.trim();
    // "Add todo: buy milk" / "todo buy milk" / "capture: lunch with Sara friday 1pm" -> the text after the prefix
    const payload = (/^(?:add\s+(?:a\s+)?todo|todo|capture)\s*:?\s+(.+)$/i.exec(raw) || [])[1] || raw;
    const short = (s) => (s.length > 48 ? `${s.slice(0, 48)}…` : s);
    if (raw && os.dashboard) {
      trimmed.push({ group: 'Today', label: `Capture: “${short(payload)}”`, icon: 'plus', run: () => os.dashboard.captureText(payload) });
      trimmed.push({ group: 'Today', label: `Add todo: “${short(payload)}”`, icon: 'check-square', run: () => os.dashboard.addTodo(payload) });
    }
    if (raw) trimmed.push({ group: 'Jarvis', label: `Ask Jarvis: “${raw.length > 60 ? raw.slice(0, 60) + '…' : raw}”`, icon: 'sparkles', run: () => os.askJarvis(raw) });
    results = trimmed;
    sel = Math.min(sel, Math.max(0, results.length - 1));
    draw();
  }

  function draw() {
    clear(list);
    let lastGroup = null;
    results.forEach((r, i) => {
      if (r.group !== lastGroup) { list.append(h('div', { class: 'palette-group mono', text: r.group })); lastGroup = r.group; }
      list.append(h('button', { class: ['palette-item', i === sel && 'sel'], role: 'option', 'aria-selected': i === sel ? 'true' : 'false', on: { click: () => act(r), pointermove: () => { if (sel !== i) { sel = i; mark(); } } } },
        icon(r.icon, 16), h('span', { class: 'pi-label', text: r.label }), r.sub && h('span', { class: 'pi-sub muted mono', text: r.sub })));
    });
    if (!results.length) list.append(h('p', { class: 'muted palette-none', text: 'Start typing…' }));
  }
  const mark = () => { [...list.querySelectorAll('.palette-item')].forEach((el, i) => { el.classList.toggle('sel', i === sel); el.setAttribute('aria-selected', i === sel ? 'true' : 'false'); }); list.querySelector('.sel')?.scrollIntoView({ block: 'nearest' }); };

  const searchFiles = debounce(async () => {
    const q = input.value.trim();
    const my = ++token;
    if (q.length < 2) { fileHits = []; compute(); return; }
    try {
      const data = await get('/fs/search', { path: '/Home', q });
      if (my !== token) return;
      fileHits = data.results.slice(0, 5);
    } catch { fileHits = []; }
    compute();
  }, 220);

  input.addEventListener('input', () => { sel = 0; compute(); searchFiles(); });
  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); sel = (sel + 1) % Math.max(1, results.length); mark(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); sel = (sel - 1 + results.length) % Math.max(1, results.length); mark(); }
    else if (e.key === 'Enter') { e.preventDefault(); if (results[sel]) act(results[sel]); }
  };
  document.addEventListener('keydown', onKey, true);
  backdrop.addEventListener('pointerdown', (e) => { if (e.target === backdrop) close(); });
  $id('overlays').append(backdrop);
  compute();
  input.focus();
  input.select();
}

// ============================================================ session restore
function restoreWindows() {
  const saved = getSavedWindows().slice(-12);
  let restored = 0;
  for (const s of saved) {
    const app = APPS.get(s.app);
    if (!app) continue;
    try {
      const win = wm.open({
        app: s.app, title: app.name, icon: app.icon, width: app.width, height: app.height, props: s.props || {}, rect: s.rect, state: s.state,
        singletonKey: app.singleton ? s.app : (s.app === 'editor' ? `editor:${s.props?.path}` : null),
        mount: (body, w) => app.mount(body, w, s.props || {}),
      });
      if (win) restored++;
    } catch (e) { console.warn('could not restore', s.app, e); }
  }
  if (!restored) { /* empty desktop: the home screen shows */ }
}

// ============================================================== global keys
document.addEventListener('keydown', (e) => {
  const mod = e.ctrlKey || e.metaKey;
  if (mod && e.key.toLowerCase() === 'k' && !e.shiftKey && !e.altKey) { e.preventDefault(); openPalette(); }
  else if (mod && e.altKey && e.key.toLowerCase() === 't') { e.preventDefault(); os.openApp('terminal'); }
  else if (mod && e.altKey && e.key.toLowerCase() === 'j') { e.preventDefault(); os.openApp('jarvis'); }
  else if (e.key === 'Escape') closeContextMenu();
});

window.addEventListener('beforeunload', () => { if (wm) saveWindows(wm.serialize()); });
window.addEventListener('unhandledrejection', (e) => {
  const msg = e.reason?.message || String(e.reason || 'Unexpected error');
  if (e.reason?.name === 'AbortError') return;
  if (e.reason?.network && !isOnline()) { e.preventDefault(); return; }       // the connection banner already says it
  console.error(e.reason);
  toast(msg, { kind: 'error' });
});
document.addEventListener('contextmenu', (e) => {
  // Keep the browser menu for text fields; elsewhere the shell provides its own (or none).
  if (!e.target.closest('input, textarea, [contenteditable], .term-out, .editor-text')) e.preventDefault();
});

boot();
