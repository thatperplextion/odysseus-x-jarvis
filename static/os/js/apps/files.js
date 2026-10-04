// Files: browse mounted folders, with Trash, search, drag & drop and uploads.

import { h, icon, clear, contextMenu, dialog, toast, fmtBytes, fmtDate, basename, dirname, joinPath, debounce, extname } from '../dom.js';
import { get, post, rawUrl, uploadFile, ApiError } from '../api.js';
import { os, kindOf, iconForEntry } from '../ctx.js';
import { isOnline } from '../net.js';
import { getPrefs, setPref } from '../state.js';

const DRAG_TYPE = 'application/x-ody-paths';
let clipboard = { mode: null, paths: [] };   // shared by every Files window

export const meta = { id: 'files', name: 'Files', icon: 'folder', width: 860, height: 560 };

export function mount(body, win, props = {}) {
  const prefs = getPrefs();
  let cwd = props.path || '/Home';
  let mode = 'dir';                   // dir | trash | search
  let entries = [];
  let trashItems = [];
  let readonly = false;
  let selection = new Set();
  let anchor = null;
  let query = '';
  let view = prefs.filesView || 'list';
  let sort = { ...(prefs.filesSort || { key: 'name', dir: 'asc' }) };
  let hist = [cwd];
  let hIdx = 0;
  let lastSignature = '';
  let renaming = false;
  let loadToken = 0;

  // ------------------------------------------------------------------ layout
  const backBtn = iconBtn('arrow-left', 'Back', () => go(hist[hIdx - 1], { fromHistory: -1 }));
  const fwdBtn = iconBtn('arrow-right', 'Forward', () => go(hist[hIdx + 1], { fromHistory: +1 }));
  const upBtn = iconBtn('arrow-up', 'Up one level', () => up());
  const crumbs = h('nav', { class: 'files-crumbs', 'aria-label': 'Location' });
  const search = h('input', { class: 'input files-search', type: 'search', placeholder: 'Search this folder', 'aria-label': 'Search this folder', spellcheck: 'false' });
  const viewBtn = iconBtn(view === 'list' ? 'grid' : 'list', 'Switch view', () => {
    view = view === 'list' ? 'grid' : 'list';
    setPref('filesView', view);
    viewBtn.replaceChildren(icon(view === 'list' ? 'grid' : 'list', 16));
    render();
  });
  // Labels are spans so a narrow window can show icons only (see .btn-label in apps.css).
  const toolBtn = (iconName, label, run) => h('button', { class: 'btn btn-soft btn-sm', title: `New ${label.toLowerCase()}`, 'aria-label': label, on: { click: run } },
    icon(iconName, 15), h('span', { class: 'btn-label', text: label }));
  const newFolderBtn = toolBtn('plus', 'Folder', () => newFolder());
  const newFileBtn = toolBtn('file-text', 'File', () => newFile());
  const uploadBtn = toolBtn('upload', 'Upload', () => pickUpload());
  uploadBtn.title = 'Upload files';
  const trashActions = h('div', { class: 'files-trash-actions', hidden: true },
    h('button', { class: 'btn btn-soft', on: { click: () => trashRestore() } }, icon('refresh', 15), 'Restore'),
    h('button', { class: 'btn btn-soft', on: { click: () => trashPurge() } }, icon('trash', 15), 'Delete forever'),
    h('button', { class: 'btn btn-soft danger', on: { click: () => trashEmpty() } }, 'Empty Trash'),
  );
  const toolbar = h('div', { class: 'files-toolbar' },
    h('div', { class: 'files-nav' }, backBtn, fwdBtn, upBtn), crumbs, h('span', { class: 'win-spacer' }),
    search, viewBtn, newFolderBtn, newFileBtn, uploadBtn, trashActions);

  const side = h('aside', { class: 'files-side', 'aria-label': 'Places' });
  const list = h('div', { class: 'files-list', role: 'listbox', 'aria-multiselectable': 'true', tabindex: '0', 'aria-label': 'Files' });
  const status = h('span', { class: 'files-status-text' });
  const progress = h('div', { class: 'files-progress', hidden: true }, h('div', { class: 'files-progress-bar' }));
  const roBadge = h('span', { class: 'badge', hidden: true }, icon('lock', 12), 'Read-only');
  const statusBar = h('div', { class: 'files-statusbar' }, status, h('span', { class: 'win-spacer' }), progress, roBadge);
  const dropVeil = h('div', { class: 'files-drop', hidden: true }, h('div', {}, icon('upload', 28), h('p', { text: 'Drop to upload' })));
  const main = h('div', { class: 'files-main' }, toolbar, list, statusBar, dropVeil);
  const root = h('div', { class: 'files' }, side, main);
  body.append(root);

  // ------------------------------------------------------------- navigation
  function iconBtn(name, label, run) {
    return h('button', { class: 'icon-btn', 'aria-label': label, title: label, on: { click: run } }, icon(name, 16));
  }

  async function go(path, { fromHistory = 0, keepSearch = false } = {}) {
    if (!path) return;
    const token = ++loadToken;
    try {
      const data = await get('/fs/list', { path, hidden: getPrefs().showHidden ? 'true' : undefined });
      if (token !== loadToken) return;
      mode = 'dir';
      cwd = data.path;
      entries = data.entries;
      readonly = data.readonly;
      selection.clear();
      anchor = null;
      if (!keepSearch) { query = ''; search.value = ''; }
      if (fromHistory) hIdx += fromHistory;
      else if (hist[hIdx] !== cwd) { hist = hist.slice(0, hIdx + 1); hist.push(cwd); hIdx = hist.length - 1; }
      lastSignature = signature();
      win.setTitle(data.name === 'Home' ? 'Files' : `${data.name} · Files`);
      render();
      list.scrollTop = 0;
    } catch (e) {
      if (token !== loadToken) return;
      // A restored window (or a stale link) can point at a folder that has since been deleted: show the nearest folder
      // that still exists instead of an empty list under an error.
      if (e instanceof ApiError && e.status === 404 && !fromHistory) {
        const parent = dirname(path);
        if (parent && parent !== path && parent !== '/') {
          toast(`“${basename(path)}” is gone. Showing ${basename(parent)} instead.`, { ms: 3500 });
          return go(parent, { keepSearch });
        }
      }
      if (e?.network) return;       // Odysseus is unreachable: keep the listing on screen; the reconnect reloads it
      toast(e.message, { kind: 'error' });
      if (path === cwd) { entries = []; render(); }
    }
  }

  const refresh = async (keepSelection = false) => {
    const keep = new Set(selection);
    if (mode === 'trash') return showTrash();
    if (mode === 'search' && query) return runSearch(query);
    await go(cwd, { fromHistory: 0, keepSearch: true });
    if (keepSelection) { selection = new Set([...keep].filter((p) => entries.some((e) => e.path === p))); render(); }
  };

  function up() {
    if (mode !== 'dir') { go(cwd); return; }
    const parent = dirname(cwd);
    if (parent && parent !== '/' && parent !== cwd) go(parent);
  }

  async function showTrash() {
    mode = 'trash';
    try {
      trashItems = (await get('/fs/trash')).items;
    } catch (e) { toast(e.message, { kind: 'error' }); trashItems = []; }
    selection.clear();
    win.setTitle('Trash · Files');
    render();
  }

  async function runSearch(q) {
    try {
      const data = await get('/fs/search', { path: cwd, q });
      mode = 'search';
      entries = data.results;
      selection.clear();
      render(data.truncated ? 'Showing the first matches only' : '');
    } catch (e) { toast(e.message, { kind: 'error' }); }
  }

  search.addEventListener('input', debounce(() => {
    query = search.value.trim();
    if (!query) { if (mode === 'search') go(cwd); return; }
    runSearch(query);
  }, 250));
  search.addEventListener('keydown', (e) => { if (e.key === 'Escape') { search.value = ''; query = ''; if (mode === 'search') go(cwd); list.focus(); } });

  // --------------------------------------------------------------- rendering
  const signature = () => JSON.stringify(entries.map((e) => [e.name, e.size, e.modified]));

  function sorted() {
    const dir = sort.dir === 'asc' ? 1 : -1;
    const key = sort.key;
    return [...entries].sort((a, b) => {
      if (a.type !== b.type) return a.type === 'dir' ? -1 : 1;
      let r;
      if (key === 'size') r = (a.size || 0) - (b.size || 0);
      else if (key === 'modified') r = (a.modified || '').localeCompare(b.modified || '');
      else r = a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
      return r * dir || a.name.localeCompare(b.name);
    });
  }

  function renderSide() {
    clear(side);
    side.append(h('div', { class: 'side-label', text: 'Places' }));
    for (const m of os.boot.mounts) {
      const active = mode !== 'trash' && (cwd === m.path || cwd.startsWith(m.path + '/'));
      const item = h('button', { class: ['side-item', active && 'active'], on: { click: () => go(m.path) } },
        icon(m.name === 'Home' ? 'home' : 'drive', 16), h('span', { class: 'side-name', text: m.name }), m.readonly && icon('lock', 12, 'side-lock'));
      wireDrop(item, m.path);
      side.append(item);
    }
    side.append(h('div', { class: 'side-label', text: 'Library' }));
    side.append(h('button', { class: ['side-item', mode === 'trash' && 'active'], on: { click: () => showTrash() } },
      icon('trash', 16), h('span', { class: 'side-name', text: 'Trash' })));
    const recent = getPrefs().recent || [];
    if (recent.length) {
      side.append(h('div', { class: 'side-label', text: 'Recent' }));
      for (const p of recent.slice(0, 5)) {
        side.append(h('button', { class: 'side-item side-recent', title: p, on: { click: () => os.openFile(p) } },
          icon('file-text', 16), h('span', { class: 'side-name', text: basename(p) })));
      }
    }
  }

  function renderCrumbs() {
    clear(crumbs);
    if (mode === 'trash') { crumbs.append(h('span', { class: 'crumb current', text: 'Trash' })); return; }
    const parts = cwd.split('/').filter(Boolean);
    let acc = '';
    parts.forEach((part, i) => {
      acc += '/' + part;
      const path = acc;
      const last = i === parts.length - 1;
      if (i) crumbs.append(icon('chevron-right', 12, 'crumb-sep'));
      const el = h('button', { class: ['crumb', last && 'current'], text: part, on: { click: () => !last && go(path) }, 'aria-current': last ? 'page' : undefined });
      if (!last) wireDrop(el, path);
      crumbs.append(el);
    });
    if (mode === 'search') crumbs.append(h('span', { class: 'crumb-note', text: `· results for “${query}”` }));
  }

  function render(note = '') {
    renderSide();
    renderCrumbs();
    backBtn.disabled = hIdx <= 0;
    fwdBtn.disabled = hIdx >= hist.length - 1;
    upBtn.disabled = mode === 'dir' && (dirname(cwd) === '/' || cwd.split('/').filter(Boolean).length <= 1);
    const trashMode = mode === 'trash';
    for (const b of [newFolderBtn, newFileBtn, uploadBtn, search, viewBtn]) b.hidden = trashMode;
    newFolderBtn.disabled = newFileBtn.disabled = uploadBtn.disabled = readonly;
    trashActions.hidden = !trashMode;
    roBadge.hidden = !(readonly && mode === 'dir');
    list.classList.toggle('grid', view === 'grid' && !trashMode);
    clear(list);

    if (trashMode) renderTrash(); else renderEntries();
    updateStatus(note);
  }

  function renderEntries() {
    const rows = sorted();
    if (view === 'list') {
      const hdr = h('div', { class: 'frow fhead', role: 'presentation' },
        sortHead('name', 'Name'), sortHead('modified', mode === 'search' ? 'Location' : 'Modified'), sortHead('size', 'Size'));
      list.append(hdr);
    }
    if (!rows.length) {
      list.append(h('div', { class: 'files-empty' }, icon(mode === 'search' ? 'search' : 'folder', 30),
        h('p', { text: mode === 'search' ? 'No matches' : 'This folder is empty' }),
        mode === 'dir' && !readonly && h('p', { class: 'muted', text: 'Drop files here to upload, or create something new.' })));
      return;
    }
    let thumbs = 0;
    for (const e of rows) {
      const selected = selection.has(e.path);
      const nameCell = h('span', { class: 'fname' },
        view === 'grid' && e.type === 'file' && kindOf(e.name) === 'image' && thumbs++ < 150
          ? h('img', { class: 'fthumb', src: rawUrl(e.path), alt: '', loading: 'lazy', draggable: 'false' })
          : h('span', { class: ['ficon', e.type === 'dir' && 'dir'] }, icon(iconForEntry(e), view === 'grid' ? 34 : 17)),
        h('span', { class: 'ftext', text: e.name }),
        e.link && h('span', { class: 'flink', title: e.restricted ? 'Link leaves the mounted folders' : 'Link' }, icon(e.restricted ? 'lock' : 'external', 11)));
      const cells = view === 'list'
        ? [nameCell,
          h('span', { class: 'fcell muted', text: mode === 'search' ? dirname(e.path) : fmtDate(e.modified) }),
          h('span', { class: 'fcell muted fright', text: e.type === 'dir' ? '' : fmtBytes(e.size) })]
        : [nameCell];
      const row = h('div', {
        class: ['frow', 'fitem', selected && 'selected', e.hidden && 'hidden-file'], role: 'option', 'aria-selected': selected ? 'true' : 'false',
        draggable: true, dataset: { path: e.path }, title: e.name,
        on: {
          click: (ev) => select(e, ev),
          dblclick: () => open(e),
          contextmenu: (ev) => { ev.preventDefault(); if (!selection.has(e.path)) { selection = new Set([e.path]); anchor = e.path; paintSelection(); } itemMenu(ev.clientX, ev.clientY); },
          dragstart: (ev) => dragStart(ev, e),
        },
      }, cells);
      if (e.type === 'dir' && !e.restricted) wireDrop(row, e.path);
      list.append(row);
    }
  }

  function sortHead(key, label) {
    const active = sort.key === key;
    return h('button', {
      class: ['fh', active && 'active', key !== 'name' && key !== 'modified' && 'fright'], 'aria-sort': active ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none',
      on: { click: () => { sort = { key, dir: active && sort.dir === 'asc' ? 'desc' : 'asc' }; setPref('filesSort', sort); render(); } },
    }, label, active && icon(sort.dir === 'asc' ? 'chevron-up' : 'chevron-down', 12));
  }

  function renderTrash() {
    list.append(h('div', { class: 'frow fhead trash', role: 'presentation' },
      h('span', { class: 'fh', text: 'Name' }), h('span', { class: 'fh', text: 'Original location' }), h('span', { class: 'fh', text: 'Deleted' })));
    if (!trashItems.length) {
      list.append(h('div', { class: 'files-empty' }, icon('trash', 30), h('p', { text: 'Trash is empty' }),
        h('p', { class: 'muted', text: 'Deleted files stay here until you empty it.' })));
      return;
    }
    for (const t of trashItems) {
      const selected = selection.has(t.id);
      list.append(h('div', {
        class: ['frow', 'fitem', 'trash', selected && 'selected'], role: 'option', 'aria-selected': selected ? 'true' : 'false', dataset: { path: t.id },
        on: {
          click: (ev) => {
            if (ev.ctrlKey || ev.metaKey) { selection.has(t.id) ? selection.delete(t.id) : selection.add(t.id); } else selection = new Set([t.id]);
            render();
          },
          contextmenu: (ev) => { ev.preventDefault(); selection = new Set([t.id]); render(); contextMenu(ev.clientX, ev.clientY, [
            { label: 'Restore', icon: 'refresh', run: trashRestore }, { label: 'Delete forever', icon: 'trash', danger: true, run: trashPurge }]); },
        },
      },
      h('span', { class: 'fname' }, h('span', { class: 'ficon' }, icon(t.type === 'dir' ? 'folder' : 'file-text', 17)), h('span', { class: 'ftext', text: t.name })),
      h('span', { class: 'fcell muted', text: t.original }),
      h('span', { class: 'fcell muted', text: fmtDate(t.deleted_at) })));
    }
  }

  function updateStatus(note = '') {
    const count = mode === 'trash' ? trashItems.length : entries.length;
    const sel = selection.size;
    const parts = [`${count} item${count === 1 ? '' : 's'}`];
    if (sel) {
      parts.push(`${sel} selected`);
      if (mode !== 'trash') {
        const bytes = entries.filter((e) => selection.has(e.path) && e.type === 'file').reduce((n, e) => n + (e.size || 0), 0);
        if (bytes) parts.push(fmtBytes(bytes));
      }
    }
    if (note) parts.push(note);
    status.textContent = parts.join(' · ');
  }

  function paintSelection() {
    for (const row of list.querySelectorAll('.fitem')) {
      const on = selection.has(row.dataset.path);
      row.classList.toggle('selected', on);
      row.setAttribute('aria-selected', on ? 'true' : 'false');
    }
    updateStatus();
  }

  // --------------------------------------------------------------- selection
  function select(e, ev) {
    const order = sorted().map((x) => x.path);
    if (ev.shiftKey && anchor) {
      const a = order.indexOf(anchor), b = order.indexOf(e.path);
      const [lo, hi] = a < b ? [a, b] : [b, a];
      selection = new Set(order.slice(lo, hi + 1));
    } else if (ev.ctrlKey || ev.metaKey) {
      selection.has(e.path) ? selection.delete(e.path) : selection.add(e.path);
      anchor = e.path;
    } else {
      selection = new Set([e.path]);
      anchor = e.path;
    }
    paintSelection();
  }

  list.addEventListener('pointerdown', (ev) => { if (ev.target === list || ev.target.classList.contains('files-empty')) { selection.clear(); paintSelection(); } });
  list.addEventListener('contextmenu', (ev) => {
    if (ev.target.closest('.fitem') || mode !== 'dir') return;
    ev.preventDefault();
    contextMenu(ev.clientX, ev.clientY, [
      { label: 'New folder', icon: 'plus', run: newFolder, disabled: readonly },
      { label: 'New file', icon: 'file-text', run: newFile, disabled: readonly },
      { label: 'Paste', icon: 'clipboard', run: paste, disabled: readonly || !clipboard.paths.length, hint: 'Ctrl V' },
      'sep',
      { label: 'Upload files…', icon: 'upload', run: pickUpload, disabled: readonly },
      { label: 'Open terminal here', icon: 'terminal', run: () => os.openApp('terminal', { cwd }) },
      { label: 'Refresh', icon: 'refresh', run: () => refresh(true) },
    ]);
  });

  const selectedEntries = () => entries.filter((e) => selection.has(e.path));

  function itemMenu(x, y) {
    const sel = selectedEntries();
    if (!sel.length) return;
    const single = sel.length === 1 ? sel[0] : null;
    contextMenu(x, y, [
      single && { label: 'Open', icon: single.type === 'dir' ? 'folder' : 'file-text', run: () => open(single), hint: 'Enter' },
      single && single.type === 'file' && kindOf(single.name) !== 'text' && { label: 'Open in editor', icon: 'edit', run: () => os.openApp('editor', { path: single.path }) },
      single && single.type === 'dir' && { label: 'Open terminal here', icon: 'terminal', run: () => os.openApp('terminal', { cwd: single.path }) },
      single && single.type === 'file' && { label: 'Download', icon: 'download', run: () => download(single) },
      'sep',
      { label: 'Rename', icon: 'edit', run: startRename, disabled: !single || readonly, hint: 'F2' },
      { label: 'Copy', icon: 'copy', run: () => setClipboard('copy'), hint: 'Ctrl C' },
      { label: 'Cut', icon: 'scissors', run: () => setClipboard('cut'), disabled: readonly, hint: 'Ctrl X' },
      { label: 'Paste into folder', icon: 'clipboard', run: () => paste(single && single.type === 'dir' ? single.path : cwd), disabled: readonly || !clipboard.paths.length },
      'sep',
      { label: 'Copy path', icon: 'copy', run: () => copyText(sel.map((s) => s.path).join('\n')) },
      { label: sel.length > 1 ? `Move ${sel.length} items to Trash` : 'Move to Trash', icon: 'trash', danger: true, run: trashSelected, disabled: readonly, hint: 'Del' },
    ].filter(Boolean));
  }

  // ----------------------------------------------------------------- actions
  function open(e) {
    if (e.type === 'dir') { if (!e.restricted) go(e.path); else toast('That link leaves the mounted folders.', { kind: 'error' }); return; }
    os.openFile(e.path, e);
  }

  function download(e) {
    const a = h('a', { href: rawUrl(e.path, true), download: e.name });
    document.body.append(a); a.click(); a.remove();
  }

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); toast('Copied', { kind: 'ok', ms: 1400 }); }
    catch { toast('Could not access the clipboard', { kind: 'error' }); }
  }

  function setClipboard(kind) {
    const paths = [...selection];
    if (!paths.length) return;
    clipboard = { mode: kind, paths };
    toast(`${kind === 'cut' ? 'Cut' : 'Copied'} ${paths.length} item${paths.length === 1 ? '' : 's'}`, { kind: 'ok', ms: 1400 });
  }

  async function paste(target) {
    const dest = typeof target === 'string' ? target : cwd;
    if (!clipboard.paths.length || readonly) return;
    const { mode: m, paths } = clipboard;
    let done = 0;
    for (const src of paths) {
      try {
        await post('/fs/transfer', { src, dst_dir: dest, copy: m === 'copy' });
        done++;
      } catch (e) {
        if (e.status === 409 && m === 'cut') {
          const choice = await dialog.choose('Already exists', `“${basename(src)}” already exists in the destination.`,
            [{ label: 'Skip', value: 'skip' }, { label: 'Replace', kind: 'danger', value: 'replace' }]);
          if (choice === 'replace') { try { await post('/fs/transfer', { src, dst_dir: dest, copy: false, overwrite: true }); done++; } catch (e2) { toast(e2.message, { kind: 'error' }); } }
        } else toast(`${basename(src)}: ${e.message}`, { kind: 'error' });
      }
    }
    if (m === 'cut') clipboard = { mode: null, paths: [] };
    if (done) toast(`${m === 'cut' ? 'Moved' : 'Pasted'} ${done} item${done === 1 ? '' : 's'}`, { kind: 'ok' });
    refresh();
  }

  async function newFolder() {
    if (readonly) return;
    const name = await dialog.prompt('New folder', { label: 'Name', value: 'New folder', confirmLabel: 'Create', select: true, validate: validName });
    if (!name) return;
    try { await post('/fs/mkdir', { path: joinPath(cwd, name.trim()) }); await refresh(); selectByName(name.trim()); }
    catch (e) { toast(e.message, { kind: 'error' }); }
  }

  async function newFile() {
    if (readonly) return;
    const name = await dialog.prompt('New file', { label: 'Name', value: 'untitled.txt', confirmLabel: 'Create', validate: validName });
    if (!name) return;
    try {
      const made = await post('/fs/create', { path: joinPath(cwd, name.trim()) });
      await refresh();
      os.openApp('editor', { path: made.path });
    } catch (e) { toast(e.message, { kind: 'error' }); }
  }

  const validName = (v) => {
    const t = v.trim();
    if (!t) return 'Enter a name';
    if (/[\\/]/.test(t)) return 'Names cannot contain slashes';
    if (/[<>:"|?*\x00-\x1f]/.test(t)) return 'Names cannot contain < > : " | ? *';
    if (/[. ]$/.test(t)) return 'Names cannot end with a dot or space';
    return null;
  };

  function selectByName(name) {
    const e = entries.find((x) => x.name === name);
    if (e) { selection = new Set([e.path]); anchor = e.path; paintSelection(); list.querySelector(`[data-path="${CSS.escape(e.path)}"]`)?.scrollIntoView({ block: 'nearest' }); }
  }

  function startRename() {
    const sel = selectedEntries();
    if (sel.length !== 1 || readonly || renaming) return;
    const e = sel[0];
    const row = list.querySelector(`[data-path="${CSS.escape(e.path)}"]`);
    const text = row?.querySelector('.ftext');
    if (!text) return;
    renaming = true;
    const input = h('input', { class: 'input rename-input', type: 'text', value: e.name, spellcheck: 'false' });
    text.replaceWith(input);
    input.focus();
    const dot = e.name.lastIndexOf('.');
    input.setSelectionRange(0, dot > 0 && e.type === 'file' ? dot : e.name.length);
    let finished = false;
    const finish = async (commit) => {
      if (finished) return;
      finished = true;
      renaming = false;
      const next = input.value.trim();
      if (commit && next && next !== e.name) {
        const problem = validName(next);
        if (problem) { toast(problem, { kind: 'error' }); render(); return; }
        try { await post('/fs/rename', { path: e.path, name: next }); await refresh(); selectByName(next); }
        catch (err) { toast(err.message, { kind: 'error' }); render(); }
      } else render();
    };
    input.addEventListener('keydown', (ev) => { ev.stopPropagation(); if (ev.key === 'Enter') finish(true); else if (ev.key === 'Escape') finish(false); });
    input.addEventListener('blur', () => finish(true));
    input.addEventListener('dblclick', (ev) => ev.stopPropagation());
    input.addEventListener('click', (ev) => ev.stopPropagation());
  }

  async function trashSelected() {
    const sel = selectedEntries();
    if (!sel.length || readonly) return;
    const ids = [];
    for (const e of sel) {
      try { ids.push((await post('/fs/delete', { path: e.path })).id); }
      catch (err) { toast(`${e.name}: ${err.message}`, { kind: 'error' }); }
    }
    selection.clear();
    await refresh();
    if (ids.length) {
      toast(`Moved ${ids.length} item${ids.length === 1 ? '' : 's'} to Trash`, {
        action: { label: 'Undo', run: async () => { for (const id of ids) { try { await post('/fs/trash/restore', { id }); } catch (e) { toast(e.message, { kind: 'error' }); } } refresh(); } },
        ms: 6000,
      });
    }
  }

  const selectedTrash = () => [...selection];
  async function trashRestore() {
    for (const id of selectedTrash()) { try { await post('/fs/trash/restore', { id }); } catch (e) { toast(e.message, { kind: 'error' }); } }
    await showTrash();
  }
  async function trashPurge() {
    const ids = selectedTrash();
    if (!ids.length) return;
    if (!await dialog.confirm('Delete forever?', `${ids.length} item${ids.length === 1 ? '' : 's'} will be permanently deleted. This cannot be undone.`, { confirmLabel: 'Delete forever', danger: true })) return;
    for (const id of ids) { try { await post('/fs/trash/purge', { id }); } catch (e) { toast(e.message, { kind: 'error' }); } }
    await showTrash();
  }
  async function trashEmpty() {
    if (!trashItems.length) return;
    if (!await dialog.confirm('Empty Trash?', `All ${trashItems.length} item${trashItems.length === 1 ? '' : 's'} will be permanently deleted. This cannot be undone.`, { confirmLabel: 'Empty Trash', danger: true })) return;
    try { await post('/fs/trash/empty'); } catch (e) { toast(e.message, { kind: 'error' }); }
    await showTrash();
  }

  // ----------------------------------------------------------------- uploads
  function pickUpload() {
    if (readonly) return;
    const input = h('input', { type: 'file', multiple: true, hidden: true });
    input.addEventListener('change', () => { if (input.files.length) uploadFiles([...input.files], cwd); input.remove(); });
    document.body.append(input);
    input.click();
  }

  async function uploadFiles(files, destDir) {
    if (!files.length) return;
    progress.hidden = false;
    const bar = progress.firstChild;
    let ok = 0;
    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      status.textContent = `Uploading ${i + 1} of ${files.length}: ${f.name}`;
      bar.style.width = '0%';
      const target = joinPath(destDir, f.name);
      try {
        await uploadFile(target, f, { onProgress: (p) => { bar.style.width = `${Math.round(p * 100)}%`; } });
        ok++;
      } catch (e) {
        if (e.status === 409) {
          const c = await dialog.choose('File already exists', `“${f.name}” is already in this folder.`,
            [{ label: 'Skip', value: 'skip' }, { label: 'Keep both', value: 'both' }, { label: 'Replace', kind: 'danger', value: 'replace' }]);
          try {
            if (c === 'replace') { await uploadFile(target, f, { overwrite: true, onProgress: (p) => { bar.style.width = `${Math.round(p * 100)}%`; } }); ok++; }
            else if (c === 'both') {
              const dot = f.name.lastIndexOf('.');
              const alt = dot > 0 ? `${f.name.slice(0, dot)} (copy)${f.name.slice(dot)}` : `${f.name} (copy)`;
              await uploadFile(joinPath(destDir, alt), f); ok++;
            }
          } catch (e2) { toast(`${f.name}: ${e2.message}`, { kind: 'error' }); }
        } else toast(`${f.name}: ${e.message}`, { kind: 'error' });
      }
    }
    progress.hidden = true;
    if (ok) toast(`Uploaded ${ok} file${ok === 1 ? '' : 's'}`, { kind: 'ok' });
    refresh(true);
  }

  // ------------------------------------------------------------- drag & drop
  function dragStart(ev, entry) {
    if (!selection.has(entry.path)) { selection = new Set([entry.path]); paintSelection(); }
    ev.dataTransfer.setData(DRAG_TYPE, JSON.stringify([...selection]));
    ev.dataTransfer.setData('text/plain', [...selection].join('\n'));
    ev.dataTransfer.effectAllowed = 'copyMove';
  }

  function wireDrop(el, target) {
    const dest = () => (typeof target === 'function' ? target() : target);
    el.addEventListener('dragover', (ev) => {
      const types = ev.dataTransfer.types;
      if (!types.includes(DRAG_TYPE) && !types.includes('Files')) return;
      if (mode === 'trash' || (readonly && el === list)) return;   // nothing can be dropped here
      ev.preventDefault();
      ev.stopPropagation();
      ev.dataTransfer.dropEffect = types.includes('Files') ? 'copy' : (ev.ctrlKey ? 'copy' : 'move');
      el.classList.add('drop-target');
    });
    el.addEventListener('dragleave', () => el.classList.remove('drop-target'));
    el.addEventListener('drop', async (ev) => {
      el.classList.remove('drop-target');
      if (mode === 'trash') return;
      const destPath = dest();
      const internal = ev.dataTransfer.getData(DRAG_TYPE);
      if (internal) {
        ev.preventDefault(); ev.stopPropagation();
        const paths = JSON.parse(internal);
        let done = 0;
        for (const src of paths) {
          if (src === destPath || (dirname(src) === destPath && !ev.ctrlKey)) continue;   // dropped where it already is
          try { await post('/fs/transfer', { src, dst_dir: destPath, copy: ev.ctrlKey }); done++; }
          catch (e) { toast(`${basename(src)}: ${e.message}`, { kind: 'error' }); }
        }
        if (done) toast(`${ev.ctrlKey ? 'Copied' : 'Moved'} ${done} item${done === 1 ? '' : 's'} to ${basename(destPath)}`, { kind: 'ok' });
        refresh();
      } else if (ev.dataTransfer.files.length) {
        ev.preventDefault(); ev.stopPropagation();
        uploadFiles([...ev.dataTransfer.files], destPath);
      }
    });
  }

  let veilDepth = 0;
  main.addEventListener('dragenter', (ev) => { if (ev.dataTransfer.types.includes('Files') && !readonly && mode === 'dir') { veilDepth++; dropVeil.hidden = false; } });
  main.addEventListener('dragleave', () => { veilDepth = Math.max(0, veilDepth - 1); if (!veilDepth) dropVeil.hidden = true; });
  main.addEventListener('drop', () => { veilDepth = 0; dropVeil.hidden = true; });
  wireDrop(list, () => cwd);   // dropping on empty space targets the folder that is open

  // ---------------------------------------------------------------- keyboard
  list.addEventListener('keydown', (ev) => {
    if (renaming) return;
    const order = mode === 'trash' ? trashItems.map((t) => t.id) : sorted().map((x) => x.path);
    const idx = order.indexOf(anchor);
    const mod = ev.ctrlKey || ev.metaKey;
    if (view === 'grid' && mode !== 'trash' && (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight')) {
      ev.preventDefault();
      const next = order[clampIdx(idx + (ev.key === 'ArrowRight' ? 1 : -1), order.length)];
      if (next === undefined) return;
      selection = new Set([next]);
      anchor = next;
      paintSelection();
      list.querySelector(`[data-path="${CSS.escape(next)}"]`)?.scrollIntoView({ block: 'nearest' });
    } else if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
      ev.preventDefault();
      const cols = view === 'grid' && mode !== 'trash' ? Math.max(1, Math.floor(list.clientWidth / 112)) : 1;
      const next = order[clampIdx(idx + (ev.key === 'ArrowDown' ? cols : -cols), order.length)];
      if (next === undefined) return;
      if (ev.shiftKey && anchor) { selection.add(next); } else selection = new Set([next]);
      anchor = next;
      paintSelection();
      list.querySelector(`[data-path="${CSS.escape(next)}"]`)?.scrollIntoView({ block: 'nearest' });
    } else if (ev.key === 'Enter') { const e = selectedEntries()[0]; if (e) open(e); }
    else if (ev.key === 'Delete') { mode === 'trash' ? trashPurge() : trashSelected(); }
    else if (ev.key === 'F2') { ev.preventDefault(); startRename(); }
    else if (ev.key === 'Backspace') { ev.preventDefault(); up(); }
    else if (ev.key === 'F5') { ev.preventDefault(); refresh(true); }
    else if (mod && ev.key.toLowerCase() === 'a') { ev.preventDefault(); selection = new Set(order); paintSelection(); }
    else if (mod && ev.key.toLowerCase() === 'c') { ev.preventDefault(); setClipboard('copy'); }
    else if (mod && ev.key.toLowerCase() === 'x') { ev.preventDefault(); setClipboard('cut'); }
    else if (mod && ev.key.toLowerCase() === 'v') { ev.preventDefault(); paste(); }
    else if (ev.key === 'Escape') { selection.clear(); paintSelection(); }
  });
  const clampIdx = (i, n) => Math.max(0, Math.min(n - 1, i < 0 ? 0 : i));

  // ---------------------------------------------------------------- lifecycle
  const offMounts = os.on('mounts', () => { renderSide(); });
  const offFs = os.on('fs-changed', (path) => { if (!path || path === cwd || path.startsWith(cwd + '/')) refresh(true); });
  const offReconnect = os.on('reconnected', () => { if (mode === 'dir') refresh(true); });
  const timer = setInterval(async () => {
    if (document.hidden || win.state === 'min' || renaming || mode !== 'dir' || query) return;
    if (!win.focused || !isOnline()) return;          // paused while Odysseus is unreachable
    try {
      const data = await get('/fs/list', { path: cwd, hidden: getPrefs().showHidden ? 'true' : undefined });
      const sig = JSON.stringify(data.entries.map((e) => [e.name, e.size, e.modified]));
      if (sig !== lastSignature) { entries = data.entries; lastSignature = sig; selection = new Set([...selection].filter((p) => entries.some((e) => e.path === p))); render(); }
    } catch { /* transient */ }
  }, 5000);

  go(cwd);
  return {
    focus: () => list.focus(),
    serialize: () => ({ path: cwd }),
    destroy: () => { clearInterval(timer); offMounts(); offFs(); offReconnect(); },
    onReuse: (p) => { if (p?.path) go(p.path); },
  };
}
