// What to show as "the output" of one scheduler run (a TaskRun row from /api/tasks).
//
// A run that fails keeps the placeholder it started with ("Starting…", "Queued — waiting for Odysseus to be idle…")
// in `result`; the reason is in `error`. Showing `result || error` therefore shows the placeholder and hides the reason.

const PLACEHOLDER = /^(Starting|Queued)\b/i;

export function runText(r) {
  const result = String(r?.result || '').trim();
  const error = String(r?.error || '').trim();
  if (error && (r.status === 'error' || r.status === 'aborted' || r.status === 'skipped')) {
    return !result || PLACEHOLDER.test(result) ? error : `${error}\n\n${result}`;
  }
  return result || error;
}
