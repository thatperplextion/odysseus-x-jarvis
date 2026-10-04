// Run with: node tests/js/runtext_check.mjs   (exit code != 0 on failure)
// static/os/js/runtext.js: what a scheduler run shows as its output. A failed run keeps "Starting…" in `result`
// and the reason in `error`; the reason must win. Mirrors routes/os_today_routes.py::_run_text.
import { runText } from '../../static/os/js/runtext.js';

let failures = 0;
const eq = (name, got, want) => {
  if (got !== want) { failures++; console.error(`FAIL ${name}\n   got  ${JSON.stringify(got)}\n   want ${JSON.stringify(want)}`); } else console.log(`ok   ${name}`);
};

eq('error replaces the placeholder', runText({ status: 'error', result: 'Starting…', error: 'RuntimeError: No model/endpoint configured' }), 'RuntimeError: No model/endpoint configured');
eq('stopped run says why', runText({ status: 'aborted', result: 'Queued — waiting for Odysseus to be idle…', error: 'Stopped by user' }), 'Stopped by user');
eq('error keeps real partial output after it', runText({ status: 'error', result: 'partial', error: 'Timed out' }), 'Timed out\n\npartial');
eq('success shows the result', runText({ status: 'success', result: 'All good', error: null }), 'All good');
eq('running shows the placeholder', runText({ status: 'running', result: 'Starting…', error: null }), 'Starting…');
eq('empty is empty', runText({ status: 'success', result: '', error: '' }), '');
eq('missing run is empty', runText(undefined), '');
process.exit(failures ? 1 : 0);
