// Viewer: images, audio and video from the file API. (HTML/SVG/PDF are never rendered inline:
// served from this origin they would run with the admin's session, so the server forces a download.)

import { h, icon, basename, dirname, joinPath } from '../dom.js';
import { get, rawUrl } from '../api.js';
import { os, kindOf } from '../ctx.js';
import { pushRecent } from '../state.js';

export const meta = { id: 'viewer', name: 'Viewer', icon: 'image', width: 720, height: 540 };

export function mount(body, win, props = {}) {
  let path = props.path;
  let siblings = [];
  let fit = true;

  const stage = h('div', { class: 'viewer-stage' });
  const caption = h('span', { class: 'viewer-name' });
  const prev = h('button', { class: 'icon-btn', 'aria-label': 'Previous', title: 'Previous', on: { click: () => step(-1) } }, icon('chevron-left', 16));
  const next = h('button', { class: 'icon-btn', 'aria-label': 'Next', title: 'Next', on: { click: () => step(1) } }, icon('chevron-right', 16));
  const fitBtn = h('button', { class: 'chip on', on: { click: () => { fit = !fit; fitBtn.classList.toggle('on', fit); stage.classList.toggle('actual', !fit); } } }, 'Fit');
  const dl = h('a', { class: 'btn btn-soft btn-sm' }, icon('download', 14), 'Download');
  const bar = h('div', { class: 'viewer-bar' }, prev, next, caption, h('span', { class: 'win-spacer' }), fitBtn, dl);
  const root = h('div', { class: 'viewer' }, bar, stage);
  body.append(root);

  async function show(p) {
    path = p;
    const name = basename(p);
    const kind = kindOf(name);
    win.setTitle(`${name} — Viewer`);
    caption.textContent = name;
    dl.href = rawUrl(p, true);
    dl.setAttribute('download', name);
    stage.replaceChildren();
    stage.classList.toggle('actual', !fit);
    const src = rawUrl(p);
    if (kind === 'image') stage.append(h('img', { class: 'viewer-img', src, alt: name, draggable: 'false', on: { error: () => fail('This image could not be loaded.') } }));
    else if (kind === 'audio') stage.append(h('div', { class: 'viewer-audio' }, icon('music', 44), h('p', { text: name }), h('audio', { controls: true, src, autoplay: false })));
    else if (kind === 'video') stage.append(h('video', { class: 'viewer-video', controls: true, src }));
    else fail('This file type can’t be previewed here. Use Download to open it elsewhere.');
    pushRecent(p);
    prev.disabled = next.disabled = true;
    try {
      const data = await get('/fs/list', { path: dirname(p) });
      siblings = data.entries.filter((e) => e.type === 'file' && kindOf(e.name) === kind).map((e) => e.path);
      const i = siblings.indexOf(p);
      prev.disabled = i <= 0;
      next.disabled = i < 0 || i >= siblings.length - 1;
    } catch { /* navigation is optional */ }
  }

  function fail(text) { stage.replaceChildren(h('div', { class: 'viewer-fail' }, icon('alert', 28), h('p', { text }))); }

  function step(d) {
    const i = siblings.indexOf(path);
    const target = siblings[i + d];
    if (target) show(target);
  }

  body.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); step(1); }
  });
  root.tabIndex = 0;

  show(path);
  return {
    focus: () => root.focus(),
    serialize: () => ({ path }),
    onReuse: (p) => { if (p?.path) show(p.path); },
  };
}
