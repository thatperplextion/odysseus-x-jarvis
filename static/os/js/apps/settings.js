// Settings: appearance, AI models, mounted folders, terminal, security/activity, about.

import { h, icon, clear, dialog, toast, fmtBytes, fmtDate } from '../dom.js';
import { get, post, patch, del } from '../api.js';
import { os } from '../ctx.js';
import { getPrefs, setPref, applyTheme } from '../state.js';
import { mountModelsPane } from './models-pane.js';

// A singleton: the menus call openApp('settings', { section }) and expect the open window to switch section (onReuse below).
export const meta = { id: 'settings', name: 'Settings', icon: 'sliders', width: 940, height: 660, singleton: true };

const SECTIONS = [
  ['appearance', 'Appearance', 'sun'],
  ['models', 'AI models', 'sparkles'],
  ['folders', 'Folders', 'folder'],
  ['terminal', 'Terminal', 'terminal'],
  ['security', 'Security & activity', 'shield'],
  ['about', 'About', 'info'],
];

export function mount(body, win, props = {}) {
  const known = (id) => SECTIONS.some(([s]) => s === id);
  let section = known(props.section) ? props.section : 'appearance';   // an unknown/stale section id must not break the window
  const nav = h('nav', { class: 'set-nav', 'aria-label': 'Settings sections' });
  const pane = h('div', { class: 'set-pane' });
  body.append(h('div', { class: 'settings' }, nav, pane));

  function renderNav() {
    clear(nav);
    for (const [id, label, ic] of SECTIONS) {
      nav.append(h('button', { class: ['side-item', id === section && 'active'], 'aria-current': id === section ? 'page' : undefined,
        on: { click: () => { section = id; renderNav(); renderPane(); } } }, icon(ic, 16), h('span', { class: 'side-name', text: label })));
    }
  }

  let modelsPane = null;   // live handle of the AI models section (it polls and listens while it is on screen)
  function renderPane() {
    modelsPane?.destroy(); modelsPane = null;
    clear(pane);
    ({ appearance, models, folders, terminal, security, about })[section]();
  }

  // ------------------------------------------------------------------ AI models
  function models() { modelsPane = mountModelsPane(pane, { group }); }

  const group = (title, ...children) => h('section', { class: 'set-group' }, h('h3', { text: title }), ...children);
  const row = (label, hint, control) => h('div', { class: 'set-row' }, h('div', { class: 'set-text' }, h('div', { class: 'set-label', text: label }), hint && h('div', { class: 'set-hint muted', text: hint })), control);
  const toggle = (checked, onChange, label) => {
    const input = h('input', { type: 'checkbox', checked, role: 'switch', 'aria-label': label, on: { change: () => onChange(input.checked) } });
    return h('label', { class: 'switch' }, input, h('span', { class: 'switch-track' }, h('span', { class: 'switch-thumb' })));
  };

  // -------------------------------------------------------------- appearance
  function appearance() {
    const prefs = getPrefs();
    const seg = (key, options) => h('div', { class: 'segmented', role: 'radiogroup' }, options.map(([v, label]) => h('button', {
      class: ['seg', prefs[key] === v && 'on'], role: 'radio', 'aria-checked': prefs[key] === v ? 'true' : 'false',
      on: { click: () => { setPref(key, v); applyTheme(); renderPane(); } },
    }, label)));
    const wallpapers = h('div', { class: 'wall-grid' }, [['paper', 'Paper'], ['dusk', 'Dusk'], ['ink', 'Ink']].map(([v, label]) => h('button', {
      class: ['wall', `wall-${v}`, prefs.wallpaper === v && 'on'], 'aria-label': `${label} wallpaper`, 'aria-pressed': prefs.wallpaper === v ? 'true' : 'false',
      on: { click: () => { setPref('wallpaper', v); applyTheme(); renderPane(); } },
    }, h('span', { text: label }))));
    const apps = os.appList().filter((a) => !a.hidden);
    pane.append(
      h('h2', { class: 'set-title', text: 'Appearance' }),
      group('Theme', row('Colour scheme', 'Auto follows your system.', seg('theme', [['auto', 'Auto'], ['light', 'Light'], ['dark', 'Dark']]))),
      group('Wallpaper', wallpapers),
      group('Dock', h('p', { class: 'set-hint muted', text: 'Choose which apps stay in the dock.' }),
        h('div', { class: 'dock-pick' }, apps.map((a) => {
          const on = prefs.dock.includes(a.id);
          return h('label', { class: ['pick', on && 'on'] },
            h('input', { type: 'checkbox', checked: on, on: { change: (e) => { const cur = getPrefs().dock; setPref('dock', e.target.checked ? [...cur, a.id] : cur.filter((x) => x !== a.id)); renderPane(); } } }),
            icon(a.icon, 15), h('span', { text: a.name }));
        }))),
      group('Files', row('Show hidden files', 'Dotfiles and files marked hidden.', toggle(prefs.showHidden, (v) => { setPref('showHidden', v); os.emit('fs-changed'); }, 'Show hidden files'))),
    );
  }

  // ----------------------------------------------------------------- folders
  function folders() {
    const list = h('div', { class: 'mount-list' });
    const name = h('input', { class: 'input', placeholder: 'Name, e.g. Projects', maxlength: 32, 'aria-label': 'Folder name' });
    const path = h('input', { class: 'input mono', placeholder: 'Folder on this computer, e.g. C:\\Users\\you\\Projects', 'aria-label': 'Folder path', spellcheck: 'false' });
    const ro = h('input', { type: 'checkbox', checked: true });

    const draw = () => {
      clear(list);
      for (const m of os.boot.mounts) {
        const isHome = m.name === 'Home';
        list.append(h('div', { class: 'mount' },
          h('span', { class: 'mount-icon' }, icon(isHome ? 'home' : 'drive', 18)),
          h('div', { class: 'mount-text' }, h('div', { class: 'mount-name' }, m.name, isHome && h('span', { class: 'badge', text: 'Default' })), h('div', { class: 'mount-path mono muted', text: m.real_path })),
          h('div', { class: 'mount-actions' },
            !isHome && h('label', { class: 'mount-ro' }, toggle(m.readonly, async (v) => { try { await patch(`/mounts/${encodeURIComponent(m.name)}`, { readonly: v }); await os.refreshMounts(); draw(); } catch (e) { toast(e.message, { kind: 'error' }); draw(); } }, `Read-only ${m.name}`), h('span', { class: 'muted', text: 'Read-only' })),
            !isHome && h('button', { class: 'icon-btn', 'aria-label': `Remove ${m.name}`, title: 'Remove (files stay where they are)', on: { click: async () => {
              if (!await dialog.confirm(`Remove “${m.name}”?`, 'Odysseus OS will stop showing this folder. Nothing on disk is deleted.', { confirmLabel: 'Remove' })) return;
              try { await del(`/mounts/${encodeURIComponent(m.name)}`); await os.refreshMounts(); draw(); } catch (e) { toast(e.message, { kind: 'error' }); }
            } } }, icon('trash', 16)))));
      }
    };
    draw();

    const add = async (n, p, readonly) => {
      try { await post('/mounts', { name: n, path: p, readonly }); await os.refreshMounts(); folders(); toast(`Added ${n}`, { kind: 'ok' }); }
      catch (e) { toast(e.message, { kind: 'error' }); }
    };

    clear(pane);
    pane.append(...[
      h('h2', { class: 'set-title', text: 'Folders' }),
      h('p', { class: 'set-hint muted', text: 'Odysseus OS only sees folders you mount here. Everything inside a mounted folder can be read, edited and (unless read-only) deleted by admins using this desktop and by the Jarvis assistant. Home is a private workspace inside Odysseus’s data folder.' }),
      list,
      os.boot.suggested_mounts?.length > 0 && group('Quick add', h('div', { class: 'chips' }, os.boot.suggested_mounts.map((s) =>
        h('button', { class: 'chip', title: s.path, on: { click: () => add(s.name, s.path, false) } }, icon('plus', 12), s.name)))),
      group('Add a folder', h('div', { class: 'add-form' }, name, path,
        h('label', { class: 'check' }, ro, h('span', { text: 'Read-only' })),
        h('button', { class: 'btn btn-ink', on: { click: () => { if (name.value.trim() && path.value.trim()) add(name.value.trim(), path.value.trim(), ro.checked); else toast('Enter a name and a folder path', { kind: 'error' }); } } }, 'Add folder'))),
    ].filter(Boolean));   // native append() would print a skipped section as the text "false"
  }

  // ---------------------------------------------------------------- terminal
  function terminal() {
    const prefs = getPrefs();
    const current = prefs.shell && os.boot.shells.some((s) => s.id === prefs.shell) ? prefs.shell : os.boot.shells.find((s) => s.default)?.id;
    const sel = h('select', { class: 'select', 'aria-label': 'Default shell', on: { change: () => { setPref('shell', sel.value); toast('Default shell updated', { kind: 'ok', ms: 1500 }); } } },
      os.boot.shells.map((s) => h('option', { value: s.id, text: s.label, selected: s.id === current })));
    pane.append(
      h('h2', { class: 'set-title', text: 'Terminal' }),
      group('Shell', row('Default shell', 'Used by new Terminal windows.', sel)),
      group('What the terminal can do', h('p', { class: 'set-hint', text: 'Terminal commands run as the user that started Odysseus, with that user’s permissions, anywhere on this computer. It is not limited to mounted folders. API keys and tokens in the server’s environment are not passed to commands. Every command is recorded under Security & activity.' })),
    );
  }

  // ---------------------------------------------------------------- security
  async function security() {
    clear(pane);
    pane.append(h('h2', { class: 'set-title', text: 'Security & activity' }));
    const auth = os.boot.auth_enabled;
    pane.append(group('Access',
      row('Sign-in', auth ? 'Odysseus OS is only available to signed-in administrators.' : 'Authentication is turned off for this Odysseus install.', h('span', { class: ['pill', auth ? 'st-completed' : 'st-failed'], text: auth ? 'Required' : 'Off' })),
      !auth && h('p', { class: 'set-hint warn-text', text: 'With sign-in off, Odysseus OS only answers requests addressed to localhost, but anyone using this computer can control it. Set AUTH_ENABLED=true to require an admin login.' }),
      row('Signed in as', null, h('span', { class: 'mono', text: os.boot.user })),
      row('AI actions', 'Anything the assistant wants to change (run a command, write a file) waits for your approval first.', h('span', { class: 'pill st-completed', text: 'Approval required' }))));
    const log = h('div', { class: 'audit' }, h('p', { class: 'muted', text: 'Loading…' }));
    pane.append(group('Recent activity', log));
    const load = async () => {
      try {
        const { events } = await get('/audit', { limit: 150 });
        clear(log);
        if (!events.length) { log.append(h('p', { class: 'muted', text: 'Nothing recorded yet this session.' })); return; }
        log.append(h('table', { class: 'audit-table' }, h('thead', {}, h('tr', {}, h('th', { text: 'When' }), h('th', { text: 'Event' }), h('th', { text: 'Details' }))),
          h('tbody', {}, events.map((e) => h('tr', {},
            h('td', { class: 'muted nowrap', text: fmtDate(e.time) }),
            h('td', {}, h('span', { class: ['pill', `sev-${e.severity}`], text: e.type.replace(/_/g, ' ') })),
            h('td', { class: 'mono muted detail', text: summarize(e.details) }))))));
      } catch (err) { clear(log); log.append(h('p', { class: 'err-text', text: err.message })); }
    };
    pane.append(h('button', { class: 'btn btn-soft', on: { click: load } }, icon('refresh', 14), 'Refresh'));
    load();
  }

  const summarize = (d) => Object.entries(d || {}).filter(([k]) => k !== 'user').map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`).join('  ·  ') + (d?.user ? `   — ${d.user}` : '');

  // ------------------------------------------------------------------- about
  function about() {
    const s = os.boot.system || {};
    pane.append(
      h('h2', { class: 'set-title', text: 'About' }),
      h('div', { class: 'about' },
        h('div', { class: 'about-mark' }, h('span', { class: 'serif', text: 'Odysseus' }), h('em', { class: 'serif muted', text: ' OS' })),
        h('p', { class: 'muted', text: `Jarvis kernel ${os.boot.version} · ${os.boot.jarvis_state}${os.boot.odysseus_connected ? ' · connected to Odysseus' : ''}` })),
      group('This computer',
        row('Name', null, h('span', { text: s.hostname })),
        row('System', null, h('span', { text: `${s.os} ${s.os_release}` })),
        row('Processor', null, h('span', { text: `${s.cores || '?'} cores · ${s.threads} threads` })),
        row('Memory', null, h('span', { text: fmtBytes(s.memory_total) })),
        row('Python', null, h('span', { class: 'mono', text: s.python })),
        row('Running as', null, h('span', { class: 'mono', text: s.user }))),
      group('Assistant', row('Language model', os.boot.assistant?.llm ? 'Jarvis answers questions with the model configured in Odysseus.' : 'No model is configured in Odysseus, so Jarvis can run commands but not hold a conversation.',
        h('span', { class: ['pill', os.boot.assistant?.llm ? 'st-completed' : 'st-failed'], text: os.boot.assistant?.llm ? 'Connected' : 'Not configured' }))),
    );
  }

  renderNav();
  renderPane();
  return {
    focus: () => nav.querySelector('.active')?.focus(),
    destroy: () => { modelsPane?.destroy(); modelsPane = null; },
    serialize: () => ({ section }),
    onReuse: (p) => { if (known(p?.section)) { section = p.section; renderNav(); renderPane(); } },
  };
}
