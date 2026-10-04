// Editor: plain-text editing with safe saves.
//
// Saves send the content version we opened. If the file changed on disk since, the server
// answers 409 and we ask before overwriting. Line endings (LF/CRLF), BOM and encoding
// survive a round-trip, so editing a Windows file doesn't silently rewrite it.

import { h, icon, dialog, toast, basename, dirname, fmtBytes } from '../dom.js';
import { get, put, rawUrl, ApiError } from '../api.js';
import { os } from '../ctx.js';
import { pushRecent, dropRecent } from '../state.js';

export const meta = { id: 'editor', name: 'Editor', icon: 'file-text', width: 760, height: 540 };

export function mount(body, win, props = {}) {
  const path = props.path;
  let doc = null;               // {content, version, encoding, bom, eol, readonly}
  let original = '';
  let dirty = false;
  let wrap = false;
  let failed = false;

  const saveBtn = h('button', { class: 'btn btn-ink btn-sm', on: { click: () => save() } }, icon('save', 14), 'Save');
  const nameEl = h('span', { class: 'editor-name', text: basename(path || '') });
  const dirtyDot = h('span', { class: 'dirty-dot', hidden: true, title: 'Unsaved changes' });
  const pathEl = h('span', { class: 'editor-path muted', text: dirname(path || '') });
  const eolChip = h('button', { class: 'chip', title: 'Line endings (click to switch)', on: { click: () => { if (doc && !doc.readonly) { doc.eol = doc.eol === 'lf' ? 'crlf' : 'lf'; refreshChips(); setDirty(true); } } } });
  const encChip = h('span', { class: 'chip static' });
  const wrapBtn = h('button', { class: 'chip', title: 'Toggle word wrap', on: { click: () => { wrap = !wrap; applyWrap(); } } }, 'Wrap');
  const roBadge = h('span', { class: 'badge', hidden: true }, icon('lock', 12), 'Read-only');
  const bar = h('div', { class: 'editor-bar' },
    saveBtn, h('div', { class: 'editor-file' }, nameEl, dirtyDot, pathEl), h('span', { class: 'win-spacer' }), roBadge, wrapBtn, eolChip, encChip);

  const gutter = h('div', { class: 'editor-gutter', 'aria-hidden': 'true' });
  // Read-only with a placeholder until the file arrives, so nothing can be typed into a document
  // that is about to be replaced by the real contents.
  const ta = h('textarea', { class: 'editor-text', spellcheck: 'false', autocapitalize: 'off', autocomplete: 'off', wrap: 'off', readOnly: true, placeholder: 'Loading…', 'aria-label': `Contents of ${basename(path || '')}` });
  const wrapEl = h('div', { class: 'editor-wrap' }, gutter, ta);
  const posEl = h('span', { text: '' });
  const hintEl = h('span', { class: 'muted', text: 'Ctrl S save · Esc then Tab to leave the editor' });
  const statusBar = h('div', { class: 'editor-status' }, posEl, h('span', { class: 'win-spacer' }), hintEl);
  const message = h('div', { class: 'editor-message', hidden: true });
  const root = h('div', { class: 'editor' }, bar, wrapEl, message, statusBar);
  body.append(root);

  // ------------------------------------------------------------------ state
  function setDirty(v) {
    dirty = v;
    dirtyDot.hidden = !v;
    win.setTitle(`${v ? '• ' : ''}${basename(path)} — Editor`);
  }

  function refreshChips() {
    if (!doc) return;
    eolChip.textContent = doc.eol === 'crlf' ? 'CRLF' : 'LF';
    encChip.textContent = doc.encoding === 'latin-1' ? 'Latin-1' : (doc.bom ? 'UTF-8 BOM' : 'UTF-8');
  }

  function applyWrap() {
    ta.setAttribute('wrap', wrap ? 'soft' : 'off');
    ta.classList.toggle('wrapped', wrap);
    wrapEl.classList.toggle('no-gutter', wrap);
    wrapBtn.classList.toggle('on', wrap);
    updateGutter();
  }

  function updateGutter() {
    if (wrap) return;
    const lines = ta.value.split('\n').length;
    if (gutter.dataset.lines === String(lines)) { gutter.scrollTop = ta.scrollTop; return; }
    gutter.dataset.lines = String(lines);
    let out = '';
    for (let i = 1; i <= lines; i++) out += i + '\n';
    gutter.textContent = out;
    gutter.style.minWidth = `${String(lines).length + 2}ch`;
    gutter.scrollTop = ta.scrollTop;
  }

  function updatePos() {
    const before = ta.value.slice(0, ta.selectionStart);
    const line = before.split('\n').length;
    const col = ta.selectionStart - before.lastIndexOf('\n');
    const sel = ta.selectionEnd - ta.selectionStart;
    posEl.textContent = `Ln ${line}, Col ${col}${sel ? ` · ${sel} selected` : ''} · ${ta.value.split('\n').length} lines · ${fmtBytes(new Blob([ta.value]).size)}`;
  }

  function showMessage(title, text, withDownload) {
    failed = true;
    wrapEl.hidden = true;
    statusBar.hidden = true;
    saveBtn.hidden = true;
    for (const c of [wrapBtn, eolChip, encChip]) c.hidden = true;
    clearNode(message);
    message.append(...[icon('alert', 28), h('h3', { text: title }), h('p', { class: 'muted', text }),
      withDownload && h('a', { class: 'btn btn-soft', href: rawUrl(path, true), download: basename(path) }, icon('download', 15), 'Download instead')].filter(Boolean));
    message.hidden = false;
  }
  const clearNode = (el) => { while (el.firstChild) el.removeChild(el.firstChild); };

  // ---------------------------------------------------------------- loading
  async function load() {
    if (!path) { showMessage('No file', 'Open a file from Files to edit it.'); return; }
    try {
      doc = await get('/fs/read', { path });
    } catch (e) {
      if (e instanceof ApiError && e.status === 415) showMessage('Not a text file', 'This looks like binary data, so it can’t be edited as text.', true);
      else if (e instanceof ApiError && e.status === 413) showMessage('File is too large', 'The editor opens files up to a couple of megabytes.', true);
      else if (e instanceof ApiError && e.status === 404) { dropRecent(path); showMessage('File not found', 'This file was moved or deleted, so it has been removed from Recent.'); }
      else showMessage('Could not open file', e.message);
      return;
    }
    original = doc.content;
    ta.value = doc.content;
    ta.placeholder = '';
    ta.readOnly = !!doc.readonly;
    roBadge.hidden = !doc.readonly;
    saveBtn.disabled = !!doc.readonly;
    eolChip.disabled = !!doc.readonly;
    refreshChips();
    setDirty(false);
    updateGutter();
    updatePos();
    pushRecent(doc.path || path);
    ta.focus();
  }

  // ------------------------------------------------------------------ saving
  async function save({ force = false } = {}) {
    if (!doc || doc.readonly || failed) return true;
    if (!dirty && !force) { toast('Nothing to save', { ms: 1200 }); return true; }
    const text = ta.value;
    try {
      const out = await put('/fs/write', { path, content: text, version: force ? undefined : doc.version, encoding: doc.encoding, bom: doc.bom, eol: doc.eol, create: true });
      doc.version = out.version;
      doc.encoding = out.encoding;
      original = text;
      setDirty(ta.value !== text);
      refreshChips();
      os.emit('fs-changed', dirname(path));
      toast(`Saved ${basename(path)}`, { kind: 'ok', ms: 1600 });
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        const choice = await dialog.choose('File changed on disk', `“${basename(path)}” was modified by something else since you opened it.`, [
          { label: 'Cancel', value: 'cancel' },
          { label: 'Reload from disk', value: 'reload' },
          { label: 'Overwrite', kind: 'danger', value: 'overwrite' },
        ], { detail: 'Overwrite replaces the version on disk with yours. Reload discards your edits.' });
        if (choice === 'overwrite') return save({ force: true });
        if (choice === 'reload') { await load(); return true; }
        return false;
      }
      // Odysseus unreachable: an info toast (error toasts are held back while offline) so a save never fails silently.
      if (e?.network) toast('Not saved: Odysseus isn’t responding. Your edits are still here; save again once it reconnects.', { ms: 5500 });
      else toast(`Could not save: ${e.message}`, { kind: 'error' });
      return false;
    }
  }

  // ------------------------------------------------------------------- input
  ta.addEventListener('input', () => { setDirty(ta.value !== original); updateGutter(); updatePos(); });
  ta.addEventListener('scroll', () => { gutter.scrollTop = ta.scrollTop; });
  for (const ev of ['keyup', 'click', 'select']) ta.addEventListener(ev, updatePos);

  ta.addEventListener('keydown', (e) => {
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === 's') { e.preventDefault(); save(); return; }
    if (ta.readOnly) return;
    if (e.key === 'Escape') { ta.blur(); win.el.focus(); return; }
    if (e.key === 'Tab') {
      e.preventDefault();
      indent(e.shiftKey);
    } else if (e.key === 'Enter' && !mod && !e.shiftKey) {
      const start = ta.selectionStart;
      const lineStart = ta.value.lastIndexOf('\n', start - 1) + 1;
      const lead = /^[ \t]*/.exec(ta.value.slice(lineStart, start))[0];
      if (lead) { e.preventDefault(); insert('\n' + lead); }
    }
  });

  function insert(text) {
    // execCommand keeps the browser's native undo stack; fall back to direct edit.
    if (!document.execCommand || !document.execCommand('insertText', false, text)) {
      const s = ta.selectionStart, en = ta.selectionEnd;
      ta.setRangeText(text, s, en, 'end');
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  function indent(outdent) {
    const unit = '  ';
    const { selectionStart: s, selectionEnd: en, value } = ta;
    if (s === en && !outdent) { insert(unit); return; }
    const lineStart = value.lastIndexOf('\n', s - 1) + 1;
    const block = value.slice(lineStart, en);
    const lines = block.split('\n');
    const changed = lines.map((l) => (outdent ? l.replace(/^(?: {1,2}|\t)/, '') : unit + l)).join('\n');
    ta.setSelectionRange(lineStart, en);
    insert(changed);
    ta.setSelectionRange(lineStart, lineStart + changed.length);
  }

  // ---------------------------------------------------------------- lifecycle
  const offFs = os.on('fs-changed', () => { /* an external change is detected at save time via the version */ });
  load();
  return {
    focus: () => (failed ? win.el.focus() : ta.focus()),
    serialize: () => ({ path }),
    onResize: updateGutter,
    destroy: () => offFs(),
    async onClose() {
      if (!dirty) return true;
      const c = await dialog.choose('Unsaved changes', `Save changes to “${basename(path)}” before closing?`, [
        { label: 'Cancel', value: 'cancel' },
        { label: 'Don’t save', value: 'discard' },
        { label: 'Save', kind: 'primary', value: 'save' },
      ]);
      if (c === 'discard') return true;
      if (c === 'save') return save();
      return false;
    },
  };
}
