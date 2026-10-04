// One-time dock migration. Pure (no DOM, no storage) so it can be unit-tested with node.
//
// The dock pref is saved per user, so an app added to the default dock later (Automations) never reaches
// people who already have a saved dock. `dockOffered` remembers which default apps a user has already been
// offered: every default they have never been offered is added once, and never again, so unpinning it sticks.

// The default dock before `dockOffered` existed. A user with a saved dock and no `dockOffered` has, by
// definition, seen exactly these, so anything they removed from this list stays removed.
export const LEGACY_DOCK = ['jarvis', 'files', 'terminal', 'taskmgr', 'chat', 'notes', 'settings'];

/**
 * @param saved     the user's saved prefs (raw, before merging with defaults); may be null/empty
 * @param defaults  the current default dock
 * @returns {{dock: string[], dockOffered: string[], changed: boolean}}
 */
export function migrateDock(saved, defaults, legacy = LEGACY_DOCK) {
  const s = saved && typeof saved === 'object' ? saved : {};
  const hasDock = Array.isArray(s.dock);
  const dock = hasDock ? s.dock.filter((x) => typeof x === 'string') : [...defaults];
  const offered = new Set(Array.isArray(s.dockOffered) ? s.dockOffered.filter((x) => typeof x === 'string') : hasDock ? legacy : defaults);

  if (hasDock) {
    defaults.forEach((id, i) => {
      if (offered.has(id)) return;
      offered.add(id);
      if (dock.includes(id)) return;
      // slot it in after its predecessor in the default order, or at the end
      let at = dock.length;
      for (let j = i - 1; j >= 0; j--) {
        const k = dock.indexOf(defaults[j]);
        if (k >= 0) { at = k + 1; break; }
      }
      dock.splice(at, 0, id);
    });
  }
  const dockOffered = [...offered];
  const changed = !hasDock ? false
    : JSON.stringify(dock) !== JSON.stringify(s.dock) || JSON.stringify(dockOffered) !== JSON.stringify(s.dockOffered || null);
  return { dock, dockOffered, changed };
}
