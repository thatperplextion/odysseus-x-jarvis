// Dashboard · which due reminders this page should announce itself. Pure, so tests/js/reminders_check.mjs can run it in node.
//
// The server announces a due reminder when no OS tab did (services/os_shell/reminders.py) and says so in the Today payload:
// `server_fired: true`, with the `key` both sides use to de-duplicate POST /api/os/notify. A page that opens after that must
// not toast or raise a desktop notification a second time, but it still remembers the reminder so a later poll does not
// reconsider it.

export const FRESH_MS = 10 * 60e3;          // a reminder older than this is history, not news

/**
 * @param reminders  agenda.reminders from GET /api/os/today
 * @param now        Date.now()
 * @param fired      ids this browser has already dealt with (localStorage)
 * @returns {{id, key, reminder, announce}[]}  everything that is due now and new to this browser, oldest first;
 *          `announce` is false when the server already did it (remember it, say nothing)
 */
export function planReminders(reminders, now, fired) {
  const seen = new Set(fired || []);
  const out = [];
  for (const r of reminders || []) {
    if (!r || !Number.isFinite(r.start_ts)) continue;
    const id = `${r.id}:${r.start_ts}`;
    if (r.start_ts > now || now - r.start_ts > FRESH_MS || seen.has(id)) continue;
    seen.add(id);
    out.push({ id, key: typeof r.key === 'string' && r.key ? r.key : `reminder:${id}`, reminder: r, announce: r.server_fired !== true });
  }
  return out;
}
