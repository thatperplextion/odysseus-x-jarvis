// Terminal: runs real commands on the server (admin-only, audited) and streams the output.
// Each command is its own shell process; the working directory carries over between them.

import { h, icon, basename } from '../dom.js';
import { streamEvents } from '../api.js';
import { os } from '../ctx.js';
import { net } from '../net.js';
import { getPrefs, setPref } from '../state.js';

export const meta = { id: 'terminal', name: 'Terminal', icon: 'terminal', width: 780, height: 480 };

const ANSI = /\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\)/g;
const MAX_LINES = 5000;
const HISTORY_KEY = 'ody.term.history';

function loadHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]').slice(-200); } catch { return []; }
}
function saveHistory(list) {
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(-200))); } catch { /* ignore */ }
}

export function mount(body, win, props = {}) {
  const shells = os.boot.shells;
  let shell = getPrefs().shell && shells.some((s) => s.id === getPrefs().shell) ? getPrefs().shell : (shells.find((s) => s.default) || shells[0])?.id;
  let cwd = props.cwd || '';
  let controller = null;
  let history = loadHistory();
  let histIdx = history.length;
  let draft = '';
  let curEl = null;
  let curBuf = '';

  const shellSel = h('select', { class: 'select', 'aria-label': 'Shell', on: { change: () => { shell = shellSel.value; setPref('shell', shell); notice(`Shell: ${shells.find((s) => s.id === shell)?.label}`); } } },
    shells.map((s) => h('option', { value: s.id, text: s.label, selected: s.id === shell })));
  const cwdEl = h('span', { class: 'term-cwd mono', title: 'Working directory' });
  const clearBtn = h('button', { class: 'icon-btn', 'aria-label': 'Clear', title: 'Clear (Ctrl L)', on: { click: clearOut } }, icon('trash', 15));
  const stopBtn = h('button', { class: 'btn btn-danger btn-sm', hidden: true, on: { click: () => stop() } }, icon('stop', 13), 'Stop');
  const bar = h('div', { class: 'term-bar' }, shellSel, cwdEl, h('span', { class: 'win-spacer' }), stopBtn, clearBtn);
  const out = h('div', { class: 'term-out', role: 'log', 'aria-live': 'off', tabindex: '-1' });
  const prompt = h('span', { class: 'term-prompt mono' });
  const input = h('textarea', { class: 'term-input mono', rows: 1, spellcheck: 'false', autocapitalize: 'off', autocomplete: 'off', 'aria-label': 'Command' });
  const row = h('div', { class: 'term-row' }, prompt, input);
  const root = h('div', { class: 'term' }, bar, out, row);
  body.append(root);

  const sys = os.boot.system || {};
  notice(`Odysseus Terminal · ${shells.find((s) => s.id === shell)?.label || 'shell'}  —  commands run as ${sys.user || 'the server user'} on ${sys.hostname || 'this machine'}. Type help.`);
  newLine();
  renderPrompt();

  // ------------------------------------------------------------------ output
  function clearOut() { out.replaceChildren(); curEl = null; curBuf = ''; newLine(); input.focus(); }

  function newLine() {
    if (curEl) curEl.textContent = curBuf;
    curBuf = '';
    curEl = h('div', { class: 'tline' });
    out.append(curEl);
    while (out.childElementCount > MAX_LINES) out.removeChild(out.firstChild);
  }

  function write(text) {
    const stick = out.scrollHeight - out.scrollTop - out.clientHeight < 48;
    text = text.replace(ANSI, '');
    let i = 0;
    while (i < text.length) {
      const ch = text[i];
      if (ch === '\n') { newLine(); i++; }
      else if (ch === '\r') {
        if (text[i + 1] === '\n') { newLine(); i += 2; } else { curBuf = ''; i++; }   // bare CR: progress bars redraw the line
      } else {
        let j = i;
        while (j < text.length && text[j] !== '\n' && text[j] !== '\r') j++;
        curBuf += text.slice(i, j);
        i = j;
      }
    }
    curEl.textContent = curBuf;
    if (stick) out.scrollTop = out.scrollHeight;
  }

  function lineOf(text, cls) {
    if (curBuf) newLine();
    curEl.className = `tline ${cls || ''}`;
    curBuf = text;      // newLine() writes curBuf into the current line, then starts a fresh one
    newLine();
    out.scrollTop = out.scrollHeight;
  }
  function notice(t) { if (!curEl) newLine(); lineOf(t, 'dim'); }   // a declaration: it runs during setup, before this line

  function renderPrompt() {
    const label = cwd ? (cwd.length > 34 ? `…${cwd.slice(-33)}` : cwd) : 'Home';
    cwdEl.textContent = cwd || '/Home';
    // cwd is a real path as reported by the shell: C:\Users\me\proj on Windows, /home/me/proj elsewhere.
    const leaf = cwd.replace(/[\\/]+$/, '').split(/[\\/]/).pop();
    prompt.textContent = `${leaf || 'Home'} ›`;
    prompt.title = label;
  }

  // ----------------------------------------------------------------- running
  function setRunning(on) {
    stopBtn.hidden = !on;
    input.readOnly = on;
    row.classList.toggle('running', on);
    input.placeholder = on ? 'Running… Ctrl C to stop' : '';
    shellSel.disabled = on;
  }

  function stop() {
    if (controller) { controller.abort(); controller = null; }
  }

  // ------------------------------------------------------------ lost connection
  // When Odysseus stops answering (it was closed, or the machine ran out of memory) the window says so in plain words and
  // holds input until the desktop has reconnected, instead of printing a raw "network error".
  let waiting = false;
  function connectionLost(midRun) {
    if (waiting) return;
    waiting = true;
    if (midRun) {
      lineOf('Connection lost: Odysseus stopped responding while this command was running.', 'warn');
      lineOf('Odysseus ends a command when its connection closes, so it was most likely stopped. If the server itself went away it may still be running; check Task Manager once Odysseus is back.', 'dim');
    } else {
      lineOf('Can’t reach Odysseus, so the command did not run. Input resumes when it reconnects.', 'warn');
    }
  }
  /** Read-only with a clear placeholder while we are waiting for the reconnect; back to normal (and a note) afterwards. */
  function syncConnection() {
    if (waiting && net.isOnline()) { waiting = false; lineOf('Reconnected.', 'dim'); input.placeholder = ''; }
    const hold = waiting && !net.isOnline();
    if (hold) { input.readOnly = true; input.placeholder = 'Odysseus isn’t responding. Waiting to reconnect…'; row.classList.add('running'); }
    else if (!controller) { input.readOnly = false; input.placeholder = ''; row.classList.remove('running'); if (document.activeElement === document.body || win.focused) input.focus(); }
  }
  const offNet = net.subscribe(() => { if (waiting) syncConnection(); });

  async function run(command) {
    lineOf(`${prompt.textContent} ${command}`, 'cmd');
    const trimmed = command.trim();
    if (!trimmed) return;
    if (history[history.length - 1] !== command) { history.push(command); saveHistory(history); }
    histIdx = history.length;

    const lower = trimmed.toLowerCase();
    if (lower === 'clear' || lower === 'cls') { clearOut(); return; }
    if (lower === 'exit') { win.close(); return; }
    if (lower === 'help') {
      lineOf('Commands run in a real shell on this machine, one process per command; cd carries over.', 'dim');
      lineOf('clear · cls      clear the screen          Ctrl C    stop the running command', 'dim');
      lineOf('exit             close this window         ↑ / ↓     command history', 'dim');
      lineOf('Shift Enter      new line in a command     Ctrl L    clear', 'dim');
      return;
    }

    controller = new AbortController();
    setRunning(true);
    const started = performance.now();
    let exitEvent = null;
    let aborted = false;
    let began = false;
    try {
      await streamEvents('/terminal/exec', { command, cwd: cwd || undefined, shell }, (ev) => {
        began = true;
        if (ev.t === 'out') write(ev.d);
        else if (ev.t === 'exit') exitEvent = ev;
      }, controller.signal);
    } catch (e) {
      if (e.name === 'AbortError') { aborted = true; lineOf('^C', 'warn'); }
      else if (e.network) connectionLost(e.lost || began);
      else lineOf(e.message || String(e), 'err');
    }
    if (!aborted && !exitEvent && !waiting && began) connectionLost(true);        // the stream ended without an exit event: the server went away cleanly
    controller = null;
    setRunning(false);
    syncConnection();
    if (curBuf) newLine();
    if (exitEvent) {
      if (exitEvent.cwd) { cwd = exitEvent.cwd; renderPrompt(); }
      const secs = (performance.now() - started) / 1000;
      if (exitEvent.timeout) lineOf('Timed out and was stopped.', 'err');
      else if (exitEvent.truncated) lineOf('Output limit reached; the command was stopped.', 'err');
      else if (exitEvent.code) lineOf(`exit ${exitEvent.code}${secs > 2 ? ` · ${secs.toFixed(1)}s` : ''}`, 'err');
      else if (secs > 2) lineOf(`done · ${secs.toFixed(1)}s`, 'dim');
    }
    out.scrollTop = out.scrollHeight;
    input.focus();
  }

  // ------------------------------------------------------------------- input
  function autosize() {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
  }
  input.addEventListener('input', autosize);

  input.addEventListener('keydown', (e) => {
    const mod = e.ctrlKey || e.metaKey;
    if (e.key === 'Enter' && !e.shiftKey && !input.readOnly) {
      e.preventDefault();
      const cmd = input.value;
      input.value = '';
      autosize();
      run(cmd);
    } else if (mod && e.key.toLowerCase() === 'c' && (controller || input.selectionStart === input.selectionEnd)) {
      if (controller) { e.preventDefault(); stop(); }
      else if (input.value) { e.preventDefault(); lineOf(`${prompt.textContent} ${input.value}^C`, 'cmd'); input.value = ''; autosize(); }
    } else if (mod && e.key.toLowerCase() === 'l') {
      e.preventDefault(); clearOut();
    } else if (e.key === 'ArrowUp' && !e.shiftKey && cursorOnFirstLine() && !controller) {
      if (histIdx > 0) { e.preventDefault(); if (histIdx === history.length) draft = input.value; histIdx--; input.value = history[histIdx]; autosize(); moveCaretEnd(); }
    } else if (e.key === 'ArrowDown' && !e.shiftKey && cursorOnLastLine() && !controller) {
      if (histIdx < history.length) { e.preventDefault(); histIdx++; input.value = histIdx === history.length ? draft : history[histIdx]; autosize(); moveCaretEnd(); }
    } else if (e.key === 'Escape') {
      input.blur(); win.el.focus();
    }
  });
  const cursorOnFirstLine = () => !input.value.slice(0, input.selectionStart).includes('\n');
  const cursorOnLastLine = () => !input.value.slice(input.selectionEnd).includes('\n');
  const moveCaretEnd = () => input.setSelectionRange(input.value.length, input.value.length);

  // Clicking the output focuses the prompt unless the user is selecting text to copy.
  out.addEventListener('click', () => { if (!window.getSelection().toString()) input.focus(); });
  row.addEventListener('click', () => input.focus());

  input.focus();
  return {
    focus: () => input.focus(),
    serialize: () => ({ cwd }),
    onClose: () => { stop(); return true; },
    destroy: () => { stop(); offNet(); },
    onReuse: (p) => { if (p?.cwd) { cwd = p.cwd; renderPrompt(); input.focus(); } },
  };
}
