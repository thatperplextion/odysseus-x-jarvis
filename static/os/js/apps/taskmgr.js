// Task Manager: processes (grouped by program), live performance charts, and background jobs.

import { h, icon, clear, contextMenu, dialog, toast, fmtBytes, fmtDuration, fmtDate, debounce } from '../dom.js';
import { get, post } from '../api.js';
import { os } from '../ctx.js';
import { isOnline } from '../net.js';

export const meta = { id: 'taskmgr', name: 'Task Manager', icon: 'activity', width: 820, height: 560 };

const SVG_NS = 'http://www.w3.org/2000/svg';
const HISTORY = 60;
const sv = (tag, attrs = {}) => { const e = document.createElementNS(SVG_NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };

export function mount(body, win, props = {}) {
  let tab = props.tab || 'processes';
  let procs = [];
  let snap = null;
  const hist = { cpu: [], mem: [], up: [], down: [] };
  let lastNet = null;
  let sort = { key: 'cpu', dir: 'desc' };
  let filter = '';
  let grouped = true;
  const expanded = new Set();
  let selected = null;            // 'p:<pid>' | 'g:<name>'
  let jobs = [];
  let jobSel = null;
  let jobDetail = null;
  let timers = [];

  const tabs = h('div', { class: 'tabs', role: 'tablist' },
    ['processes', 'performance', 'jobs'].map((t) => h('button', {
      class: ['tab', t === tab && 'active'], role: 'tab', 'aria-selected': t === tab ? 'true' : 'false', dataset: { tab: t },
      text: { processes: 'Processes', performance: 'Performance', jobs: 'Background jobs' }[t],
      on: { click: () => setTab(t) },
    })));
  const summary = h('div', { class: 'tm-summary mono' });
  const head = h('div', { class: 'tm-head' }, tabs, h('span', { class: 'win-spacer' }), summary);
  const pane = h('div', { class: 'tm-pane' });
  body.append(h('div', { class: 'tm' }, head, pane));

  function setTab(t) {
    tab = t;
    for (const b of tabs.children) { const on = b.dataset.tab === t; b.classList.toggle('active', on); b.setAttribute('aria-selected', on ? 'true' : 'false'); }
    render();
    poll();
  }

  // ----------------------------------------------------------------- polling
  async function poll() {
    if (document.hidden || win.state === 'min' || !isOnline()) return;     // paused while Odysseus is unreachable; the last numbers stay
    try {
      if (tab === 'processes') {
        const [p, s] = await Promise.all([get('/processes'), get('/system')]);
        procs = p.processes; snap = s; sample(s);
      } else if (tab === 'performance') {
        snap = await get('/system'); sample(snap);
      } else {
        const [j, s] = await Promise.all([get('/jobs'), get('/system')]);
        jobs = j.jobs; snap = s;
        if (jobSel) { try { jobDetail = await get(`/jobs/${encodeURIComponent(jobSel)}`); } catch { jobDetail = null; } }
      }
      updateSummary();
      renderLive();
    } catch (e) { /* transient while the server restarts */ }
  }

  function sample(s) {
    push(hist.cpu, s.cpu.percent);
    push(hist.mem, s.memory.percent);
    const now = s.time;
    if (lastNet && now > lastNet.t) {
      const dt = now - lastNet.t;
      push(hist.up, Math.max(0, (s.network.sent - lastNet.sent) / dt));
      push(hist.down, Math.max(0, (s.network.recv - lastNet.recv) / dt));
    }
    lastNet = { t: now, sent: s.network.sent, recv: s.network.recv };
  }
  const push = (arr, v) => { arr.push(v); if (arr.length > HISTORY) arr.shift(); };

  function updateSummary() {
    if (!snap) return;
    summary.textContent = `CPU ${snap.cpu.percent.toFixed(0)}% · RAM ${snap.memory.percent.toFixed(0)}% · ${snap.processes} processes · up ${fmtDuration(snap.uptime)}`;
  }

  // -------------------------------------------------------------- rendering
  function render() {
    clear(pane);
    if (tab === 'processes') renderProcessesShell();
    else if (tab === 'performance') renderPerformanceShell();
    else renderJobsShell();
    renderLive();
  }
  const renderLive = () => {
    if (tab === 'processes') renderProcessRows();
    else if (tab === 'performance') renderPerformance();
    else renderJobs();
  };

  // ---- processes
  let tbody, filterInput, endBtn, groupBtn, countEl;
  function renderProcessesShell() {
    filterInput = h('input', { class: 'input tm-filter', type: 'search', placeholder: 'Filter processes', value: filter, 'aria-label': 'Filter processes', spellcheck: 'false' });
    filterInput.addEventListener('input', debounce(() => { filter = filterInput.value.trim().toLowerCase(); renderProcessRows(); }, 120));
    endBtn = h('button', { class: 'btn btn-danger btn-sm', disabled: true, on: { click: () => endSelected() } }, 'End task');
    groupBtn = h('button', { class: ['chip', grouped && 'on'], on: { click: () => { grouped = !grouped; groupBtn.classList.toggle('on', grouped); renderProcessRows(); } } }, 'Group by program');
    countEl = h('span', { class: 'muted tm-count' });
    tbody = h('tbody');
    const th = (key, label, cls) => h('th', { class: [cls, 'sortable', sort.key === key && 'active'], 'aria-sort': sort.key === key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none', scope: 'col' },
      // text columns start A to Z, numeric ones biggest first; a second click reverses
      h('button', { on: { click: () => { sort = { key, dir: sort.key === key ? (sort.dir === 'desc' ? 'asc' : 'desc') : (key === 'name' || key === 'user' ? 'asc' : 'desc') }; renderProcessesShell(); renderProcessRows(); } } },
        label, sort.key === key && icon(sort.dir === 'asc' ? 'chevron-up' : 'chevron-down', 12)));
    clear(pane);
    pane.append(
      h('div', { class: 'tm-tools' }, filterInput, groupBtn, countEl, h('span', { class: 'win-spacer' }), endBtn),
      h('div', { class: 'tm-tablewrap' }, h('table', { class: 'tm-table' },
        h('thead', {}, h('tr', {}, th('name', 'Name'), th('pid', 'PID', 'num'), th('user', 'User'), th('cpu', 'CPU', 'num'), th('memory', 'Memory', 'num'), th('threads', 'Threads', 'num'))),
        tbody)),
    );
  }

  function buildGroups(rows) {
    const map = new Map();
    for (const p of rows) {
      const key = p.name.toLowerCase();
      let g = map.get(key);
      if (!g) { g = { key: `g:${key}`, name: p.name, children: [], cpu: 0, memory: 0, threads: 0, protectedAll: true, user: p.user }; map.set(key, g); }
      g.children.push(p);
      g.cpu += p.cpu; g.memory += p.memory; g.threads += p.threads;
      g.protectedAll = g.protectedAll && p.protected;
    }
    return [...map.values()];
  }

  const cmp = (a, b) => {
    const dir = sort.dir === 'asc' ? 1 : -1;
    const k = sort.key;
    const av = a[k], bv = b[k];
    const r = typeof av === 'string' ? av.localeCompare(bv, undefined, { sensitivity: 'base' }) : (av - bv);
    return (r || a.name.localeCompare(b.name)) * dir;
  };

  function renderProcessRows() {
    if (tab !== 'processes' || !tbody) return;
    const q = filter;
    const rows = q ? procs.filter((p) => p.name.toLowerCase().includes(q) || String(p.pid) === q || (p.cmdline || '').toLowerCase().includes(q)) : procs;
    clear(tbody);
    const maxCpu = Math.max(5, ...rows.map((r) => r.cpu));
    const addRow = (item, { child = false, group = false } = {}) => {
      const key = group ? item.key : `p:${item.pid}`;
      const isSel = selected === key;
      const protectedRow = group ? item.protectedAll : item.protected;
      const tr = h('tr', {
        class: [isSel && 'selected', child && 'child', group && 'group', protectedRow && 'protected'], dataset: { key },
        on: {
          click: () => { selected = key; syncSelection(); },
          dblclick: () => { if (group && item.children.length > 1) toggleGroup(item.key); },
          contextmenu: (e) => { e.preventDefault(); selected = key; syncSelection(); rowMenu(e.clientX, e.clientY, item, group); },
        },
      },
      h('td', { class: 'name' },
        group && item.children.length > 1
          ? h('button', { class: 'twisty', 'aria-label': expanded.has(item.key) ? 'Collapse' : 'Expand', 'aria-expanded': expanded.has(item.key) ? 'true' : 'false', on: { click: (e) => { e.stopPropagation(); toggleGroup(item.key); } } }, icon(expanded.has(item.key) ? 'chevron-down' : 'chevron-right', 12))
          : h('span', { class: 'twisty-pad' }),
        h('span', { class: 'pname', text: group && item.children.length > 1 ? `${item.name}` : item.name, title: group ? item.name : (item.cmdline || item.name) }),
        group && item.children.length > 1 && h('span', { class: 'pcount', text: `${item.children.length}` }),
        protectedRow && h('span', { class: 'plock', title: 'Protected: ending it could take down Odysseus or the system' }, icon('lock', 11)),
        !group && item.is_server && h('span', { class: 'badge badge-brand', text: 'Odysseus' }),
      ),
      h('td', { class: 'num muted', text: group ? (item.children.length === 1 ? item.children[0].pid : '') : item.pid }),
      h('td', { class: 'muted user', text: shortUser(group ? (item.children[0]?.user || '') : item.user) }),
      h('td', { class: 'num cpu' }, h('span', { class: 'heat', style: { width: `${Math.min(100, (item.cpu / maxCpu) * 100)}%` } }), h('span', { class: 'heat-val', text: item.cpu >= 0.1 ? `${item.cpu.toFixed(1)}%` : '0%' })),
      h('td', { class: 'num', text: fmtBytes(item.memory) }),
      h('td', { class: 'num muted', text: item.threads || '' }));
      tbody.append(tr);
    };

    if (grouped) {
      const groups = buildGroups(rows).sort(cmp);
      for (const g of groups) {
        addRow(g, { group: true });
        if (expanded.has(g.key) && g.children.length > 1) for (const c of [...g.children].sort(cmp)) addRow(c, { child: true });
      }
      countEl.textContent = `${groups.length} programs`;
    } else {
      for (const p of [...rows].sort(cmp)) addRow(p);
      countEl.textContent = `${rows.length} processes`;
    }
    syncSelection();
  }

  const shortUser = (u) => (u || '').split('\\').pop();

  function toggleGroup(key) { expanded.has(key) ? expanded.delete(key) : expanded.add(key); renderProcessRows(); }

  function selectionTargets() {
    if (!selected) return [];
    if (selected.startsWith('p:')) { const p = procs.find((x) => `p:${x.pid}` === selected); return p ? [p] : []; }
    const name = selected.slice(2);
    return procs.filter((p) => p.name.toLowerCase() === name);
  }

  function syncSelection() {
    for (const tr of tbody.querySelectorAll('tr')) tr.classList.toggle('selected', tr.dataset.key === selected);
    const targets = selectionTargets();
    endBtn.disabled = !targets.length || targets.every((p) => p.protected);
  }

  function rowMenu(x, y, item, group) {
    const targets = group ? item.children : [item];
    const canEnd = targets.some((p) => !p.protected);
    contextMenu(x, y, [
      { label: 'End task…', icon: 'x', run: () => endSelected(), disabled: !canEnd },
      { label: 'Force end…', icon: 'power', danger: true, run: () => endSelected(true), disabled: !canEnd },
      'sep',
      { label: 'Copy PID', icon: 'copy', run: () => navigator.clipboard?.writeText(targets.map((t) => t.pid).join(', ')) },
      !group && item.cmdline && { label: 'Copy command line', icon: 'copy', run: () => navigator.clipboard?.writeText(item.cmdline) },
    ].filter(Boolean));
  }

  async function endSelected(force) {
    const targets = selectionTargets().filter((p) => !p.protected);
    if (!targets.length) return;
    const label = targets.length === 1 ? `“${targets[0].name}” (PID ${targets[0].pid})` : `${targets.length} “${targets[0].name}” processes`;
    let useForce = force;
    if (force === undefined) {
      const c = await dialog.choose('End task?', `End ${label}? Unsaved data in ${targets.length === 1 ? 'it' : 'them'} will be lost.`,
        [{ label: 'Cancel', value: null }, { label: 'End task', kind: 'primary', value: 'end' }, { label: 'Force end', kind: 'danger', value: 'force' }]);
      if (!c) return;
      useForce = c === 'force';
    } else if (force) {
      if (!await dialog.confirm('Force end?', `Immediately kill ${label}? It gets no chance to save.`, { confirmLabel: 'Force end', danger: true })) return;
    }
    let ok = 0;
    for (const p of targets) {
      try { await post(`/processes/${p.pid}/terminate`, { force: !!useForce }); ok++; }
      catch (e) { toast(`${p.name} (${p.pid}): ${e.message}`, { kind: 'error' }); }
    }
    if (ok) toast(`Ended ${ok} process${ok === 1 ? '' : 'es'}`, { kind: 'ok' });
    selected = null;
    poll();
  }

  // ---- performance
  const charts = {};
  function renderPerformanceShell() {
    const card = (id, title, sub) => {
      const svg = sv('svg', { class: 'chart', viewBox: '0 0 300 90', preserveAspectRatio: 'none', role: 'img', 'aria-label': `${title} over the last minute` });
      for (const y of [22.5, 45, 67.5]) svg.append(sv('line', { x1: 0, x2: 300, y1: y, y2: y, class: 'chart-grid', 'vector-effect': 'non-scaling-stroke' }));
      const area = sv('path', { class: 'chart-area' });
      const line = sv('path', { class: 'chart-line', 'vector-effect': 'non-scaling-stroke' });
      const area2 = sv('path', { class: 'chart-area two' });
      const line2 = sv('path', { class: 'chart-line two', 'vector-effect': 'non-scaling-stroke' });
      svg.append(area, line, area2, line2);
      const value = h('div', { class: 'perf-value' });
      const detail = h('div', { class: 'perf-detail muted' });
      charts[id] = { svg, area, line, area2, line2, value, detail };
      return h('section', { class: 'perf-card' }, h('header', {}, h('h3', { text: title }), h('span', { class: 'muted mono', text: sub })), value, svg, detail);
    };
    pane.append(h('div', { class: 'perf' },
      card('cpu', 'CPU', 'last 60 s'), card('mem', 'Memory', 'last 60 s'), card('net', 'Network', 'last 60 s'),
      h('section', { class: 'perf-card' }, h('header', {}, h('h3', { text: 'Storage' })), h('div', { class: 'perf-disks' })),
      h('section', { class: 'perf-card wide' }, h('header', {}, h('h3', { text: 'Cores' })), h('div', { class: 'perf-cores' }))));
  }

  function renderPerformance() {
    if (!snap || !charts.cpu) return;
    drawChart(charts.cpu, hist.cpu, 100);
    charts.cpu.value.textContent = `${snap.cpu.percent.toFixed(0)}%`;
    charts.cpu.detail.textContent = `${snap.cpu.threads} threads${snap.cpu.mhz ? ` · ${(snap.cpu.mhz / 1000).toFixed(2)} GHz` : ''}`;

    drawChart(charts.mem, hist.mem, 100);
    charts.mem.value.textContent = `${snap.memory.percent.toFixed(0)}%`;
    charts.mem.detail.textContent = `${fmtBytes(snap.memory.used)} of ${fmtBytes(snap.memory.total)}${snap.swap?.total ? ` · swap ${snap.swap.percent.toFixed(0)}%` : ''}`;

    const maxNet = Math.max(1024, ...hist.up, ...hist.down);
    drawChart(charts.net, hist.down, maxNet, hist.up);
    charts.net.value.textContent = `↓ ${fmtBytes(hist.down[hist.down.length - 1] || 0)}/s`;
    charts.net.detail.textContent = `↑ ${fmtBytes(hist.up[hist.up.length - 1] || 0)}/s upload`;

    const disks = pane.querySelector('.perf-disks');
    clear(disks);
    for (const d of snap.disks) {
      disks.append(h('div', { class: 'disk' },
        h('div', { class: 'disk-row' }, h('span', { class: 'mono', text: d.mount }), h('span', { class: 'muted', text: `${fmtBytes(d.used)} / ${fmtBytes(d.total)}` })),
        h('div', { class: ['bar', d.percent > 90 && 'bar-warn'] }, h('div', { class: 'bar-fill', style: { width: `${d.percent}%` } }))));
    }
    if (snap.battery) disks.append(h('div', { class: 'muted perf-battery', text: `Battery ${snap.battery.percent}%${snap.battery.plugged ? ' · plugged in' : ''}` }));

    const cores = pane.querySelector('.perf-cores');
    clear(cores);
    snap.cpu.per_core.forEach((c, i) => cores.append(h('div', { class: 'core', title: `Thread ${i}: ${c.toFixed(0)}%` },
      h('div', { class: 'core-fill', style: { height: `${Math.max(2, c)}%` } }), h('span', { class: 'core-n mono', text: i }))));
  }

  function drawChart(c, values, max, values2) {
    const path = (vals) => {
      if (!vals.length) return ['', ''];
      const step = 300 / (HISTORY - 1);
      const x0 = 300 - (vals.length - 1) * step;
      const pts = vals.map((v, i) => [x0 + i * step, 88 - Math.min(1, v / max) * 84]);
      const d = pts.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`).join('');
      return [d, `${d}L${pts[pts.length - 1][0].toFixed(1)},90L${pts[0][0].toFixed(1)},90Z`];
    };
    const [l1, a1] = path(values);
    c.line.setAttribute('d', l1); c.area.setAttribute('d', a1);
    const [l2, a2] = values2 ? path(values2) : ['', ''];
    c.line2.setAttribute('d', l2); c.area2.setAttribute('d', a2);
  }

  // ---- jobs
  let jobInput, jobList, jobOut;
  function renderJobsShell() {
    jobInput = h('input', { class: 'input mono', type: 'text', placeholder: 'Run a command in the background, e.g. pip install requests', spellcheck: 'false', 'aria-label': 'Command to run in the background' });
    const runBtn = h('button', { class: 'btn btn-ink', on: { click: () => startJob() } }, icon('play', 13), 'Run');
    jobInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') startJob(); });
    jobList = h('div', { class: 'jobs-list', role: 'listbox', 'aria-label': 'Background jobs' });
    jobOut = h('div', { class: 'jobs-detail' });
    pane.append(h('div', { class: 'jobs' },
      h('div', { class: 'jobs-new' }, jobInput, runBtn),
      h('p', { class: 'muted jobs-note', text: 'Jobs run through the Jarvis kernel in your Home folder, keep running if you close this window, and can be cancelled here.' }),
      h('div', { class: 'jobs-cols' }, jobList, jobOut)));
  }

  async function startJob() {
    const command = jobInput.value.trim();
    if (!command) return;
    try {
      const r = await post('/jobs', { command });
      jobInput.value = '';
      jobSel = r.id;
      await poll();
    } catch (e) { toast(e.message, { kind: 'error' }); }
  }

  function renderJobs() {
    if (tab !== 'jobs' || !jobList) return;
    clear(jobList);
    if (!jobs.length) jobList.append(h('div', { class: 'files-empty small' }, icon('activity', 24), h('p', { text: 'No background jobs yet' })));
    for (const j of jobs) {
      jobList.append(h('button', {
        class: ['job', j.id === jobSel && 'active'], role: 'option', 'aria-selected': j.id === jobSel ? 'true' : 'false',
        on: { click: () => { jobSel = j.id; jobDetail = null; poll(); renderJobs(); } },
      }, h('span', { class: ['dot', `st-${j.state}`] }), h('span', { class: 'job-cmd mono', text: j.command || j.name }), h('span', { class: 'job-when muted', text: fmtDate(j.created_at) })));
    }
    clear(jobOut);
    if (!jobSel) { jobOut.append(h('div', { class: 'files-empty small' }, h('p', { class: 'muted', text: 'Select a job to see its output.' }))); return; }
    const d = jobDetail || jobs.find((j) => j.id === jobSel);
    if (!d) return;
    const active = d.state === 'running' || d.state === 'created';
    jobOut.append(...[
      h('div', { class: 'job-head' }, h('span', { class: ['pill', `st-${d.state}`], text: d.state }), h('span', { class: 'mono job-title', text: d.command || '' }),
        h('span', { class: 'win-spacer' }),
        active && h('button', { class: 'btn btn-danger btn-sm', on: { click: async () => { try { await post(`/jobs/${encodeURIComponent(d.id)}/cancel`); poll(); } catch (e) { toast(e.message, { kind: 'error' }); } } } }, 'Cancel')),
      h('pre', { class: 'job-output mono', text: d.result?.output ?? (active ? 'Running…' : (d.error || '')) }),
      d.error && !active && h('p', { class: 'err-text', text: d.error }),
    ].filter(Boolean));
  }

  // ---------------------------------------------------------------- lifecycle
  render();
  poll();
  timers.push(setInterval(poll, 2000));
  const onVis = () => { if (!document.hidden) poll(); };
  document.addEventListener('visibilitychange', onVis);
  const offReconnect = os.on('reconnected', poll);
  return {
    focus: () => pane.querySelector('input, button')?.focus(),
    serialize: () => ({ tab }),
    onShow: poll,
    destroy: () => { timers.forEach(clearInterval); document.removeEventListener('visibilitychange', onVis); offReconnect(); },
  };
}
