// Run with: node tests/js/dock_migrate_check.mjs   (exit code != 0 on failure)
// Checks the one-time dock migration (static/os/js/dock-migrate.js): a default app added after a user saved
// their dock is offered exactly once, and unpinning it afterwards sticks.
import { migrateDock, LEGACY_DOCK } from '../../static/os/js/dock-migrate.js';

let failures = 0;
const eq = (name, got, want) => {
  const g = JSON.stringify(got); const w = JSON.stringify(want);
  if (g !== w) { failures++; console.error(`FAIL ${name}\n   got  ${g}\n   want ${w}`); } else console.log(`ok   ${name}`);
};

const DEFAULTS = ['jarvis', 'files', 'terminal', 'taskmgr', 'automations', 'chat', 'notes', 'settings'];

// 1. an existing user (saved dock, no dockOffered) gets Automations once, next to Task Manager
let r = migrateDock({ dock: [...LEGACY_DOCK] }, DEFAULTS);
eq('legacy dock: Automations inserted after taskmgr', r.dock, ['jarvis', 'files', 'terminal', 'taskmgr', 'automations', 'chat', 'notes', 'settings']);
eq('legacy dock: marked as offered', r.dockOffered.includes('automations'), true);
eq('legacy dock: reports a change', r.changed, true);

// 2. things the user removed before stay removed (legacy defaults count as already offered)
r = migrateDock({ dock: ['jarvis', 'files', 'settings'] }, DEFAULTS);
eq('custom dock: only Automations is added, nothing else comes back', r.dock, ['jarvis', 'files', 'automations', 'settings']);

// 3. unpinning it afterwards sticks (it is in dockOffered now)
const afterUnpin = { dock: r.dock.filter((x) => x !== 'automations'), dockOffered: r.dockOffered };
r = migrateDock(afterUnpin, DEFAULTS);
eq('unpinned Automations is not re-added', r.dock.includes('automations'), false);
eq('unpinned: no change reported', r.changed, false);

// 4. running the migration twice is a no-op
const once = migrateDock({ dock: [...LEGACY_DOCK] }, DEFAULTS);
const twice = migrateDock({ dock: once.dock, dockOffered: once.dockOffered }, DEFAULTS);
eq('idempotent', [twice.dock, twice.changed], [once.dock, false]);

// 5. an app they pinned themselves is not duplicated
r = migrateDock({ dock: ['jarvis', 'automations', 'files'] }, DEFAULTS);
eq('already pinned: no duplicate', r.dock.filter((x) => x === 'automations').length, 1);

// 6. a brand-new default introduced later is offered once too
const DEFAULTS_2 = [...DEFAULTS.slice(0, 5), 'today', ...DEFAULTS.slice(5)];
r = migrateDock({ dock: once.dock, dockOffered: once.dockOffered }, DEFAULTS_2);
eq('a later new default is offered once', r.dock.indexOf('today'), r.dock.indexOf('automations') + 1);

// 7. fresh install: no saved state at all -> the defaults, nothing to persist
r = migrateDock(null, DEFAULTS);
eq('fresh install: defaults', [r.dock, r.changed], [DEFAULTS, false]);
eq('fresh install: all offered', r.dockOffered, DEFAULTS);

// 8. garbage in saved prefs is tolerated
r = migrateDock({ dock: ['files', 7, null], dockOffered: 'x' }, DEFAULTS);
eq('garbage tolerated', r.dock.includes('automations') && r.dock.includes('files'), true);

if (failures) { console.error(`\n${failures} check(s) failed`); process.exit(1); }
console.log('\nall dock migration checks passed');
