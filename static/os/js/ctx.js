// Shared context. main.js fills it in; apps import { os } and use it.
//
//   os.boot        response of GET /api/os/boot
//   os.wm          the WindowManager
//   os.openApp(id, props)       open (or focus) an app window
//   os.openFile(path, entry?)   open a file in the right app
//   os.refreshMounts()          reload mount list after a change
//   os.on(event, fn) / os.emit(event, payload)

const listeners = new Map();

export const os = {
  boot: null,
  wm: null,
  openApp: () => { throw new Error('os not ready'); },
  openFile: () => { throw new Error('os not ready'); },
  refreshMounts: async () => {},
  askJarvis: () => {},
  on(event, fn) {
    if (!listeners.has(event)) listeners.set(event, new Set());
    listeners.get(event).add(fn);
    return () => listeners.get(event)?.delete(fn);
  },
  emit(event, payload) {
    for (const fn of listeners.get(event) || []) {
      try { fn(payload); } catch (e) { console.error(e); }
    }
  },
};

// File-type helpers shared by Files, the editor and the palette.
const TEXT_EXT = new Set(('txt md markdown json jsonl js mjs cjs ts tsx jsx css scss sass less html htm xml svg csv tsv log yml yaml toml ini cfg conf env ' +
  'sh bash zsh fish bat cmd ps1 py rb go rs java kt c h cpp hpp cs php sql lua r swift vue svelte tex rst properties gradle lock editorconfig gitignore gitattributes dockerfile makefile').split(' '));
const IMAGE_EXT = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'avif', 'bmp']);
const AUDIO_EXT = new Set(['mp3', 'wav', 'ogg', 'm4a', 'flac']);
const VIDEO_EXT = new Set(['mp4', 'webm', 'ogv']);

export function kindOf(name) {
  const i = name.lastIndexOf('.');
  const ext = i > 0 ? name.slice(i + 1).toLowerCase() : '';
  const bare = name.toLowerCase();
  if (IMAGE_EXT.has(ext)) return 'image';
  if (AUDIO_EXT.has(ext)) return 'audio';
  if (VIDEO_EXT.has(ext)) return 'video';
  if (TEXT_EXT.has(ext) || TEXT_EXT.has(bare)) return 'text';
  if (ext === 'pdf') return 'pdf';
  return ext ? 'other' : 'text';   // extension-less files (LICENSE, Makefile) are usually text
}

export function iconForEntry(entry) {
  if (entry.type === 'dir') return 'folder';
  switch (kindOf(entry.name)) {
    case 'image': return 'image';
    case 'audio': return 'music';
    case 'video': return 'film';
    case 'text': return 'file-text';
    default: return 'file';
  }
}
