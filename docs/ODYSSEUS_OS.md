# Odysseus OS

A desktop operating-system shell that runs **on top of Odysseus**, driven by the **Jarvis kernel**.
Open it at **`/os`** (e.g. `http://localhost:7000/os`). It has windows, a dock, a command palette,
a file manager with a recoverable Trash, a terminal, a task manager, an editor, Settings, and an
AI assistant — and your existing Odysseus apps (Chat, Notes, Documents, Email, Calendar, Tasks,
Memory, Gallery, Cookbook) open as windows alongside them.

```
 browser ── /os  (static/os: window manager + apps, vanilla ES modules, no build step)
              │  fetch / SSE
              ▼
 routes/os_routes.py  ── /api/os/*      desktop API   ┐ admin-only, same-site only,
 routes/jarvis_routes.py ── /api/jarvis/* legacy API  ┘ loopback-only when auth is off
              │
              ▼
 services/os_shell/            pure service layer (unit-tested without FastAPI)
   sandbox.py   mounts + path resolution        fs.py        file ops, Trash, uploads
   procs.py     processes, system metrics       winproc.py   one-call Windows process snapshot
   terminal.py  streamed shell execution        procgroup.py kill a command *and everything it started*
   approvals.py single-use approval tokens      command_guard.py  accident prevention for AI commands
              │
              ▼
 JARVIS/  kernel · agent · automation · security/audit · consciousness   (Jarvis OS)
```

## Apps

| App | What it does |
|---|---|
| **Jarvis** | Assistant. Answers with Odysseus's configured model; runs your day (automations, to-dos, calendar, reminders), runs commands, reads/writes files, checks processes. **Anything that creates or changes something shows an approval card first.** |
| **Files** | Browse mounted folders. List/grid, multi-select, drag & drop (move, upload from the desktop), rename, copy/cut/paste, search, Trash with Undo. |
| **Editor** | Plain-text editing with atomic saves and conflict detection. Preserves CRLF/LF, BOM and Latin-1. |
| **Viewer** | Images, audio, video. |
| **Terminal** | Real shell (PowerShell / cmd / Git Bash / bash / zsh), streamed live. `cd` carries over, Ctrl C stops the command and everything it started. |
| **Task Manager** | Processes grouped by program (correct CPU %, protected-process locks), live Performance charts, Background jobs run by the Jarvis kernel. |
| **Automations** | Schedule and watch what Odysseus does for you: AI prompts, built-in actions, shell commands, event and webhook triggers. See [Automations](#automations). |
| **Settings** | Theme, wallpaper, dock; **AI models** (benchmark the free models, pick the default); **Folders** (mount points); default shell; Security & activity log. |
| **Chat, Notes, Documents, Email, Calendar, Tasks, Memory, Gallery, Cookbook** | The real Odysseus pages, framed as windows. |

Shortcuts: `Ctrl K` palette (apps, files, actions, "ask Jarvis") · `Ctrl Alt T` terminal · `Ctrl Alt J` Jarvis ·
`F2` rename · `Del` trash · `Ctrl S` save · `Esc` leaves a text field so Tab can move focus.

## AI models

**Settings → AI models** shows which model Odysseus uses (default chat model, its fallback chain, and the
model for background jobs and the OS assistant), benchmarks the ones you have connected, and switches the
default in one click. The benchmark reads your enabled endpoints from Odysseus's own database and sorts every
model into **local** (this computer), **free** (a provider's free tier) or **paid**. Paid and unknown-price
models are **never called** unless you name one explicitly on the command line.

Each model gets six short tasks, each run twice with different inputs, graded by code, not by another model:
a JSON tool plan in the Jarvis planner's exact format (checked with the planner's own parser), schedule →
cron, a word problem, strict formatting, event extraction as JSON and a two-sentence summary that must keep
given facts. `<think>` blocks are stripped before grading. Quality dominates the score (the JSON plan counts
double), then reliability (errors, rate limits), and median latency only breaks ties. A model that is rate
limited gets one back-off retry; one that keeps failing is abandoned early so it does not burn quota.

The recommendation: **default** = best overall free model; **fallbacks** = the next best from *different
providers* (so one provider's outage or rate limit cannot take everything down), then the local model last as
the offline fallback; **background** = the fastest model that clears 80% and can write valid planner JSON.
Apply it with one button, or use **Make default** / **Add as fallback** on any row.

Calls go through Odysseus's own client, so API keys never leave the server process and are never returned or
stored. Results are saved to `<data dir>/os/model_bench.json`. A run continues on the server if you close the
window; reopening Settings re-attaches to it.

```
venv\Scripts\python.exe -m services.os_shell.model_bench                   # test everything that is free/local
venv\Scripts\python.exe -m services.os_shell.model_bench --models gpt-oss  # only models matching a substring
venv\Scripts\python.exe -m services.os_shell.model_bench --exclude local --apply   # skip the local GPU model, then apply
```

Also: `--merge` folds a partial run into the saved results, `--include-paid` opts in to billed models, `--list`
shows what would be tested. The OS assistant plans with the Utility model (the Default Chat model when Utility
is unset) followed by the Utility fallbacks.

## Automations

A native front-end for the scheduler that already ships with Odysseus (`routes/task_routes.py`, `/api/tasks/*`). It adds no
scheduler of its own: every list, run, pause and history view is the existing API.

* **List and detail.** Each row shows the name, a type chip (AI prompt, Action, Command, Event, Webhook), the schedule in
  plain English ("Every weekday at 9:30", "When an email arrives (every 5)"), a live-ticking next run, the last-run dot
  (ok / failed / running / never) and an on/off switch. Filter by All, Active, Paused, Built-in or Mine; search covers
  names and prompts. The list refreshes every 15 s while the window is visible (5 s while something runs) and right after
  every change.
* **Run now** shows progress until the run finishes and then the output; **Stop** cancels it. Run history keeps every run with
  duration and copyable output. Webhook automations show their URL with Copy and Regenerate.
* **New / Edit.** Pick a template (morning brief, inbox triage, weekly tidy, nightly folder backup, daily stand-up, weekly
  review, custom AI prompt, custom command, event trigger, webhook) or describe it. The schedule field understands
  "every weekday at 9:30am", "every 2 hours", "mon, wed and fri at 7", "monthly on the 15th", "tomorrow at 3pm" and shows the
  next three runs; the manual controls cover intervals, daily, weekdays, weekly, monthly, once and raw cron.
* **Keys.** `N` new, `/` search, `Del` delete (asks first), `↑ ↓` move, `Enter` jump to the actions, `Esc` closes the sheet.
* **Open it from other apps:**
  `os.openApp('automations', { intent: 'new', prefill: { name, prompt | action | command, schedule: 'every weekday at 9:30am' | cron: '0 4 * * 1-5', output_target } })`
  or `{ intent: 'show', id }` (optionally `filter: 'active' | 'paused' | 'builtin' | 'mine'`). The window is a singleton, so a
  second call reaches the open window through `onReuse`.

Things worth knowing:

* **Time zones.** The scheduler reads every clock time and cron field as **UTC**. Automations shows and edits local time and
  converts at the edge (including half-hour zones and the day shift near midnight), using your *current* UTC offset, so a
  schedule saved before a daylight-saving change fires an hour off in local time afterwards. The raw cron mode is UTC.
* **Shell commands** (`run_local`) run on this computer as the user that started Odysseus, in Git Bash when it is installed
  (the backup template adapts to this). `/api/tasks` only lets a *signed-in administrator* create them, so with sign-in turned
  off the two command templates are disabled instead of failing; editing an existing command is unaffected.
* **Built-in automations** (tidy, inbox triage, ...) exist once per user and Odysseus recreates them and removes duplicates, so a
  template for one of them switches on and configures the built-in instead of adding a second. Event-triggered built-ins keep
  their trigger. A built-in's trigger type (and any automation's) cannot be changed after creation; duplicate it instead.
* **Results.** "Notification" delivers a browser notification for AI prompts only, and "Chat session" saves the result as a chat;
  every run's output is also kept in its history.
* The classic page is still available as **Tasks (classic)**: it has the cross-task Activity log, email-account options, urgency
  rules and personas that Automations does not repeat.

## Today (the desktop)

Under the greeting the desktop is a live command centre for the day. Everything on it is real data from the apps it links to,
fetched in one round trip (`GET /api/os/today`, owner-scoped, each section fails on its own: one broken subsystem shows an error
and a **Retry** in its widget while the rest keep rendering). The summary line ("2 events · next: Standup in 25 min · 6 todos ·
1 automation ran overnight") keeps counting down. It refreshes every 30 s while the desktop is on screen and right after anything
you change (including changes Jarvis makes: the assistant announces `os.emit('personal-changed', { kinds })` and the dashboard
reloads within a second, even while Jarvis' window covers it); nothing polls while the tab is hidden or windows cover the desktop.
The menu-bar CPU/RAM pulse and the System widget share one `/api/os/system` sample (`static/os/js/sysmon.js`), so an idle desktop
makes about 20 requests a minute in total. That module also keeps the last few minutes of samples (mirrored to `sessionStorage`), so
the CPU and RAM sparklines have their shape the moment the widget is built, rebuilt or the page reloaded, not after a few polls.

* **Capture bar.** Type a line, press Enter, get a preview (kind chip + parsed text), then **Confirm**, **Edit** (re-classify as
  todo / event / reminder / automation, or retype) or **Cancel**. Enter twice confirms. The parser is deterministic and runs on
  the server, no model call: *"every weekday at 7am summarize my email"* is an automation, *"lunch with Sara friday 1pm"* an
  event, *"remind me to call mom tomorrow at 6pm"* or *"in 30 minutes stretch"* a reminder, *"buy oat milk"* a todo. A time-of-day word next
  to a schedule is the time, not part of the task: *"every monday morning check my email"* runs at 8:00 am (afternoon 2 pm, evening 6 pm,
  night 9 pm; an explicit time wins) and the prompt is just "Check my email".
  Todos are appended to a checklist called **Quick capture** in Notes, reminders are Notes with a due time, events go on your
  local calendar and automations become scheduler tasks (AI prompts or the daily brief, never shell commands). Every confirmation
  has an **Undo**. An automation draft can also go to the Automations app (**Open in Automations**) to refine it first.
* **Widgets.** *Agenda* (today and tomorrow, next-up card with a ticking countdown, reminders with **Done**) · *Todos* (check off is
  the real Notes toggle, inline add) · *Automations* (next runs, last results, **Run now**, **New automation**) · *Focus* (25/5
  pomodoro, the timer survives a reload and keeps its time while windows cover the desktop, a chip in the menu bar shows the time
  left, finished sessions are logged to `<data>/jarvis/os/focus.json`) · *Inbox* (unread and top senders from the local mail
  index only, never a mail-server call; otherwise "Connect email") · *System* (CPU, RAM, disk sparklines) · *AI model*.
* **Reminders and finished runs.** A reminder that comes due, a finished focus session and every automation run that finishes
  (polled every 20 s from `/api/tasks/runs/recent`, first poll is only a baseline) raise a toast, an entry in the notification
  bell (de-duplicated per run, so two tabs don't stack copies) and, if you allowed it in the Focus widget, a browser notification.
* **Palette** (`Ctrl K`): *New automation*, *Start focus*, *Open Today*, *Add todo: …*, *Capture: …*.
* **Dock.** Apps added to the default dock later (Automations) are offered once to people who already saved their dock; if you
  unpin one it does not come back (`dockOffered` in the saved prefs).

Time zones: the browser sends its UTC offset with every request; events and reminders are the wall-clock times you typed, and an
automation's time is converted to the UTC the scheduler stores (including half-hour zones and the day shift near midnight).

## Jarvis and your day

Ask in plain words; Jarvis plans with the model set in **AI models** (Utility, then its fallbacks) and uses the same data the
Automations, Notes and Calendar apps use. Try: "every morning at 8 give me a brief of my day", "remind me to call the bank
tomorrow at 11", "add 'renew passport' to my todos", "what's on my calendar tomorrow?", "run my morning brief now",
"pause the inbox triage automation", "put a dentist appointment on Tuesday at 3pm". The empty state has chips for the common ones.

| Tool | Approval | What it does |
|---|---|---|
| `list_automations`, `get_agenda`, `list_todos` | no | Read-only. Each answers with a card: automations (status, schedule in words, next run, click to open in Automations), the agenda for a day or range (events and timed reminders), and your open to-dos with **checkboxes that work**. |
| `create_automation` | **yes** | An AI-prompt or built-in action automation on a daily, weekly, monthly, once or cron schedule; result as a notification (AI prompts), a chat session or an email. |
| `update_automation_status`, `run_automation` | **yes** | Pause / resume / run now, by id or by name ("inbox triage" finds the built-in *Email Tags*). A run shows its output in the result card when it finishes. |
| `add_todo`, `complete_todo` | **yes** | To-dos live in one checklist note called **To-do** (that is also what the daily brief reads). `add_todo` with a due time also sets a reminder. |
| `create_event`, `create_reminder` | **yes** | A Calendar event (default one hour; a clash with an existing event is flagged on the card) or a timed reminder note. |

An approval card says exactly what will happen in your local time ("Create automation 'Morning Brief': every day at 08:00,
runs daily_brief, result as a chat session", "Add event 'Dentist' Tue 6 Oct 15:00-16:00"). Tokens are the same single-use,
owner-bound, 5-minute tokens as every other assistant change, and a plan is stored *resolved*: approving "tomorrow at 11" runs
exactly the time that was shown, even if it is approved after midnight.
The card is headed "Waiting for your approval", and the sentence above it is always a proposal: the prompt asks the model to write in future
tense, and if a reply still says a change is already made ("I've marked it as done") while it waits for approval, the server replaces that
text with "Here's what I'd like to do. Nothing happens until you approve it." (`planner.as_proposal`).

How it stays identical to the apps: the approved step calls the real route handlers in-process (`POST /api/tasks`,
`/api/notes`, `/api/calendar/events`, `/api/tasks/{id}/pause|resume|run`), so validation, owner scoping, `next_run` and every
side effect match a row made in the UI. Nothing is an HTTP call to itself. Another user's automations, notes and events are
invisible to the assistant, and a stranger cannot redeem your approval.

Things worth knowing:

* **Your clock.** The browser sends its time zone with each request; the model gets the current date, time and the next days
  with their dates, so "tomorrow at 11" and "next Tuesday" resolve correctly. Reminders are stored with the UTC offset, events
  as local wall-clock times (as the Calendar app does), and automation schedules as UTC (as the scheduler reads them) with
  the weekday moved when the local time falls on another UTC day.
* **No shell automations.** `run_local`, `ssh_command` and `run_script` can only be created by you in Automations; the assistant
  refuses them. An *AI prompt* automation runs with Odysseus's agent tools (which, for an admin, include shell and file
  tools), so a prompt that is really a command ("every hour run `rm -rf ~`") is refused too. That is a pattern check, not a
  guarantee: the card always shows the full prompt, and you are the approval.
* **Notifications.** The scheduler pops up a notification for AI-prompt automations only. A built-in action such as
  `daily_brief` delivers to a chat session (Jarvis switches a requested "notification" to that and says so on the card); every
  run's output is also kept in its history.
* **Reminders fire** through Odysseus's own reminder scanner and the Notes page (the same path as a reminder you create by
  hand), so the scanner or an open Odysseus tab must be running at that time.
* **Rate limits.** Planner calls are small (about 1.1k tokens of instructions). A free model tier with a tokens-per-minute cap
  gets a short wait-and-retry on the same model before Jarvis falls back to the next one, and gpt-oss models that answer with a
  native tool call (which the API rejects) are asked once more for plain JSON.

## Security model

Odysseus OS can read files, run commands and signal processes, so it is built defensively. Know where
the guarantees stop.

**Who can use it.** Administrators only (`require_admin`). Every route also refuses cross-site browser
requests (`Sec-Fetch-Site: cross-site`). With `AUTH_ENABLED=false` the routes additionally require a
loopback `Host` header, which defeats DNS-rebinding attacks from web pages you visit; allow extra names
with `ODYSSEUS_ALLOWED_HOSTS=a.lan,b.lan`.

**Files are sandboxed.** The desktop and the Jarvis agents only reach *mounted folders*. `Home` (a private
workspace in `data/jarvis/home`) is mounted by default; admins add more in **Settings → Folders**, optionally
read-only. Paths are resolved through symlinks/junctions *before* the containment check, `..` and
Windows alternate-data-stream/reserved-name tricks are rejected, and `/data/safe` does not admit
`/data/safe-evil`. Deleting moves to a recoverable Trash.

**The terminal is *not* sandboxed.** It is a real shell running as the user that started Odysseus, anywhere
on the machine — it would be pointless otherwise. It is admin-only and every command is audited.
Secrets (`*KEY*`, `*TOKEN*`, `*SECRET*`, `*PASSWORD*` …) and the Odysseus virtualenv are stripped from its
environment. Don't give admin to anyone you wouldn't give a shell.

**AI actions need approval.** The assistant never changes the machine on its own. A request to run a
command, write a file, trigger a workflow or shut Jarvis down returns an approval card carrying a
server-issued token that is single-use, expires after 5 minutes, is bound to the user who was asked and to the
exact stored action. Even after approval, commands that look catastrophic (`rm -rf /`, `format C:`,
`curl … | sh`, `shutdown`, …) are refused by `command_guard` — a speed bump for mistakes, not a security
boundary; run those yourself in the Terminal if you really mean them.

**Other protections.** The Task Manager refuses to end the Odysseus server, the shell that launched it, and core
system processes. Raw file downloads never render HTML/SVG/JS inline (they would run with the admin's session)
and carry `Content-Security-Policy: sandbox`. Only these pages may be framed, and only by this origin:
`/ /notes /calendar /cookbook /email /memory /gallery /tasks /library`.

**Audit.** File changes, mounts, terminal commands, process kills, AI commands and refused attempts are
recorded (Settings → Security & activity, and `data/jarvis/security_audit.log`).

## Running it

**Windows: double-click `Start Odysseus OS.cmd`** in the repository root (or run `launch-windows.ps1 -Quick`). It opens its own
console window, starts the server with the repo's `venv\Scripts\python.exe`, and opens `http://localhost:7000/os` as soon as the port
answers. It never starts a second copy: if Odysseus already answers on the port it just opens the browser, and if something else owns
the port it says so. If the virtual environment is missing it tells you to run `launch-windows.ps1` once (that full script creates the
venv, installs the dependencies and runs the first-time setup; `-Quick` skips all of that). Leave the window open (minimise it);
closing it stops Odysseus. It also turns off the classic console's QuickEdit mode for that window, because clicking inside a QuickEdit
console freezes the program until you press Enter, and a frozen server looks exactly like a dead one.

| Option | Meaning |
|---|---|
| `-Quick` | The everyday start described above (the `.cmd` passes it for you). |
| `-Port 7001` | Another port. The default is 7000, or the `APP_PORT` environment variable when it is set. The data folder follows `ODYSSEUS_DATA_DIR`. |
| `-NoBrowser` | Do not open the browser. |
| `-BindHost 0.0.0.0` | Listen on the LAN too (default `127.0.0.1`, local only). |
| `-NoOllama` | Do not start Ollama. By default, if Ollama is installed (`%LOCALAPPDATA%\Programs\Ollama\ollama app.exe`, or `ollama` on PATH) but not answering on `127.0.0.1:11434`, `-Quick` starts it hidden in the background so the local model at the end of your fallback chain exists. The launcher never waits for it and never fails because of it. |

**Why not start it from an AI coding tool's shell?** A server started as a background shell of Claude Code (or a similar tool) is closed
by that tool when the machine runs critically low on memory (RAM around 90-95 %, a full system drive). The open `/os` page then lost its
server, which used to show up as raw "Failed to fetch" errors everywhere. A normal window of your own is not reaped. The launcher does
not register a Windows service or a startup item; put a shortcut to the `.cmd` in `shell:startup` if you want it at sign-in. On other
systems run `python app.py` (or `python -m uvicorn app:app`) in a terminal of your own.

If Odysseus does go away anyway, the desktop copes (see "When Odysseus stops responding" under Troubleshooting): your windows stay put and
everything refreshes by itself once it is back.

## Staying small and staying up

* **Memory.** Odysseus' built-in tool servers (email, memory, RAG, image generation, the optional browser) and the MCP servers you add in
  Settings used to run from boot to shutdown, about 70 MB each (an `npx` server is three processes): roughly 480 MB for the server plus its
  children on a quiet machine. They are now *registered* at boot from a cached tool list (`data/cache/mcp_tools.json`, rebuilt by itself when
  a server's definition changes) and start on the first tool call; a server nobody has used for 15 minutes is stopped again and starts
  anew on the next call. A quiet server is one process (about 170 MB). `ODYSSEUS_MCP_LAZY=0` brings the old behaviour back,
  `ODYSSEUS_MCP_IDLE_SECONDS` (default 900, 0 = never) sets the idle time, `ODYSSEUS_MCP_CONNECT_TIMEOUT` (default 30) bounds one server's
  start-up. An MCP server defined as `npx` with no arguments is refused with one clear line (it would only open an interactive shell and
  hang); the others are no longer held up by it. The tool-index warm-up (loads the embedding model) is skipped when under 3 GB of RAM is
  free; `ODYSSEUS_WARM_TOOL_INDEX=1|0` forces it.
* **A reset connection cannot kill the listener.** On Windows, Python's event loop closes the *listening socket* when a client connects
  and is reset before the server accepts it (closed tab, aborted request, port probe): the process stays up and refuses everything, which
  looks exactly like "Failed to fetch after some time". `src/asyncio_noise.py` keeps accepting instead and logs the harmless
  `ConnectionResetError [WinError 10054]` at debug level. `GET /api/os/session`, the page's liveness probe, no longer waits for a worker
  thread, so a busy server still answers it at once.
* **Reminders fire on the server.** A reminder made in the OS (quick capture, or Jarvis) is an ordinary note with a `due_date`; Odysseus'
  own scanner picks it up every minute (from 30 s before the due time until 2 minutes after) whether or not any page is open. With no
  OS tab polling, the server adds it to the notification centre and, on a single-user Windows machine, shows a desktop toast
  (`reminder_desktop_notify` setting, `ODYSSEUS_DESKTOP_REMINDERS=0|1`); email / ntfy / webhook channels work as before. While an OS tab
  is open it announces the reminder itself, and the two never repeat each other: both record `reminder:<note id>:<due ms>`
  (`POST /api/os/notify` for the page, the same key for the server), and `GET /api/os/today` returns `server_fired` for each reminder.
* **Local model.** See `-NoOllama` above. A dead endpoint (for example a Docker host name that does not resolve on this machine) costs
  about 3 s of DNS timeout on the first model-list request after every start; disable it in Settings → Models.

## Configuration

| Setting | Meaning |
|---|---|
| `JARVIS_ENABLED=0` | Do not start Jarvis (and therefore `/os`). Default on. |
| `AUTH_ENABLED` | Normal Odysseus switch. `false` ⇒ OS routes only answer on loopback hosts. |
| `ODYSSEUS_ALLOWED_HOSTS` | Extra `Host` values accepted when auth is off. |
| `ODYSSEUS_DATA_DIR` | Where everything below lives. |

Data under `data/jarvis/`: `home/` (the Home mount), `trash/`, `os_config.json` (mounts), `os_sessions/<user>.json`
(window layout), `security_audit.log`.

## HTTP API (admin only)

`GET /api/os/boot` · `GET|PUT /api/os/session` · files: `/api/os/fs/{roots,list,stat,read,write,mkdir,create,rename,transfer,delete,search,raw,upload,trash…}` ·
mounts: `/api/os/mounts` · `/api/os/processes[/{pid}/terminate]` · `/api/os/system` · `/api/os/jobs` ·
today: `GET /api/os/today` · `POST /api/os/capture` · `POST /api/os/capture/commit` · `POST /api/os/capture/undo` · `POST /api/os/focus` · `GET /api/os/focus/stats` · `POST /api/os/notify` ·
`POST /api/os/terminal/exec` (Server-Sent Events) · `POST /api/os/assistant` · `POST /api/os/assistant/todos/toggle` · `GET /api/os/assistant/run-result` · `/api/os/audit` · `/api/os/notifications` ·
models: `GET /api/os/models/current` · `POST /api/os/models/bench` (SSE) · `POST /api/os/models/bench/cancel` · `GET /api/os/models/bench/latest` · `POST /api/os/models/default`.
The legacy `/api/jarvis/*` API is unchanged in shape but is now admin-only and sandboxed.

## Troubleshooting

* **When Odysseus stops responding** (it was closed, crashed, or the machine ran out of memory) one calm banner appears under the menu bar:
  "Odysseus isn't responding — reconnecting…", a live countdown to the next try and a **Retry now** button. Nothing else shouts: error
  toasts and widget error states are held back (the last data stays on screen, a little dimmer), every poller (Today, the menu bar's
  CPU/RAM, notifications, Task Manager, Automations, Files, run watchers) pauses instead of hammering a dead server, and open windows,
  their positions and their text are untouched. `static/os/js/net.js` probes `GET /api/os/session` after 2 s, 4 s, 8 s and then about every
  15 s (with jitter), and straight away when the browser comes back online or the tab or window regains focus. When it answers the
  banner goes, a short "Reconnected" toast appears (with "Odysseus restarted" if it is a new server process, told apart by `boot_id`
  from `/api/os/boot` and `/api/os/session`) and everything refreshes once; a 401 sends you to the sign-in page as always.
  A command that was streaming in the Terminal gets a "Connection lost" note and its input waits for the reconnect; Jarvis hands your
  unsent question back; the Editor keeps unsaved text and says "Not saved". The shell treats a rejected `fetch` (or a stream that dies
  mid-way), and a 502/503/504 page that is not JSON (a proxy's, not Odysseus' own), as "unreachable".
  A server that is **up but hung** (frozen, out of memory, stuck in a long blocking call: it accepts connections and answers nothing) is
  caught by deadlines: an ordinary API call gets 20 s, the AI planner and bulk file work 3 minutes, a stream must send its headers
  within 30 s, and a stream or upload that goes quiet for 25-30 s is checked. A deadline that passes only asks the server once
  (`GET /api/os/session`, 4 s); if it answers, just that request fails with an ordinary "took too long, try again" error and no banner
  appears; if it does not, the same banner as above shows (about 25-30 s after the hang) and a streaming command is dropped as
  "Connection lost". The embedded classic pages (Chat, Notes, ...) are iframes with their own handling.
* **"Jarvis isn't running" on the boot screen** — the reason is shown. A missing `psutil` was the original cause
  (`pip install -r requirements.txt`).
* **Terminal output arrives all at once** — something in front of Odysseus is buffering the response. The stream
  is `text/event-stream` precisely so Odysseus's own gzip layer leaves it alone; check any reverse proxy
  (`proxy_buffering off`).
* **A folder is missing in Files** — only mounted folders are visible. Add it in Settings → Folders.

## Developing

Everything under `static/os/` is plain ES modules. An app is `export const meta = {…}` plus
`export function mount(body, win, props)` returning `{focus, serialize, onClose, destroy}`; register it in
`static/os/js/main.js`. Never build DOM with `innerHTML` — file names, process command lines and terminal output
are untrusted (use `h()` from `dom.js`; note native `append()` prints `false`/`null` as text).

CSS: every component owns a class prefix (`au-` Automations app, `dau-` the dashboard's Automations widget, `tw-` widgets, `jv-` Jarvis,
`mdl-` AI models, ...). Two sheets must not style the same class: a dashboard rule once squeezed the Automations run history to 26 px that
way. `tests/test_os_static_css.py` fails when one is added.

Tests: `venv/bin/python -m pytest tests/test_os_*.py tests/test_jarvis_*.py` (Today: `tests/test_os_today.py`), plus the pure
front-end checks `node tests/js/dock_migrate_check.mjs`, `node tests/js/automations_schedule_check.mjs`, `node tests/js/runtext_check.mjs`,
`node tests/js/net_check.mjs` (the reconnect backoff / state machine and the request deadlines in `net.js`, including a local server that accepts
connections and never answers), `node tests/js/suspender_check.mjs` (when hidden embedded pages sleep), `node tests/js/sysmon_check.mjs` (the
shared CPU / RAM history behind the Today sparklines) and `node tests/js/reminders_check.mjs` (which due reminders the Today page announces
itself: one the server already announced, `server_fired`, gets no second toast, desktop notification or bell entry).
Every network call in the shell goes through `netFetch()` in `api.js` (or reports to `net.js` itself) and so has a deadline: pass
`timeoutMs` for a call that legitimately takes long (0 = none, then watch it for silence like `streamEvents` does). A poller must check
`isOnline()` from `net.js` before it fires, and an app that wants a refresh after an outage listens for `os.on('reconnected', ...)`.
A window's app may export `onVisibility(visible)` from its handle: the window manager calls it when the window is minimised or
completely covered by a maximised window, and again when it shows.

### Browser scripts (`tests/e2e/`, not collected by pytest)

Real Edge via Playwright (`pip install playwright`; `--channel chromium` after `playwright install chromium` works too) against a
**scratch** server, never your real data directory:

```
set APP_PORT=7405 & set ODYSSEUS_DATA_DIR=C:\scratch\data & venv\Scripts\python.exe app.py        # fresh data dir; seed it through the APIs
python tests/e2e/os_click_everything.py --url http://127.0.0.1:7405/os --out C:\scratch\click       # every button in every window
python tests/e2e/os_features.py         --url http://127.0.0.1:7405/os --out C:\scratch\features [--ai] # behaviour checklist
python tests/e2e/os_perf.py             --url http://127.0.0.1:7405/os --out C:\scratch\perf           # latency, polling, leaks
python tests/e2e/os_connection.py       --port 7406 --data C:\scratch\data2 --out C:\scratch\conn      # starts + kills + restarts its own scratch server
```

* **`os_click_everything.py`** opens every app from the launcher and clicks each visible button, tab, link, checkbox and select (also
  inside the embedded Odysseus pages, with a stricter deny-list there). It never clicks "Empty Trash", "End task", "Run now", sign-out,
  or the terminal's Run; destructive confirmations are cancelled unless they name a disposable `qa-` item; theme, dock, mounts, model
  settings and automations it changes are restored. Per click it records console errors, page errors, unhandled rejections, failed
  requests, HTTP >= 400, junk text such as "false" / "undefined" on screen, and *dead* clicks (no structural DOM change, request,
  focus move, scroll, clipboard or download within 1.5 s; a heuristic, so the list is for review). `--apps a,b` limits it, `-v` prints
  every click, JSON and a readable summary land in `--out`.
* **`os_features.py`** verifies what happened (server state and screen) for window management, menubar/palette/dock/launcher, Files,
  Editor, Terminal (every shell: echo, streaming, Ctrl C and its children, timeout), Task Manager (sorting, filter, ending a dummy
  process, live graphs, jobs), Settings, AI models, Jarvis, Automations, Today, reminders (`server_fired`), the nine embedded apps, hidden
  embedded pages going to sleep and waking in place (`sleep`) and light/dark. `--only wm,files`
  selects sections; `--ai` adds the checks that call the configured model (at most five turns, spaced for tokens-per-minute limits).
* **`os_perf.py`** reports time to desktop / to a dashboard with data, `/api/os/today` latency, requests per minute (idle, every app
  open, minimised, tab hidden), timers/listeners/heap after opening and closing every app five times, and probes `/api/os/session`
  every 250 ms to show whether the server's event loop ever stalls.
* **`os_connection.py`** starts its own scratch server, opens `/os` with four apps (a command streaming in the Terminal), kills the server by
  the exact PID listening on `--port`, and checks the banner (within ~5 s, live countdown, Retry now), no toast storm, no polling (only the
  `/api/os/session` probe), the Terminal's "Connection lost" note; then restarts the server and checks the banner clears within one probe
  interval, "Reconnected" (and "Odysseus restarted"), refreshed Today data, windows and terminal text intact, and a 502-from-a-proxy round
  trip. Two more phases cover a *hung* server: one request held past its 20 s deadline on a live server must not raise the banner, and
  then the server process is suspended (it still accepts connections and answers nothing): the banner must appear within ~35 s, the
  streaming Terminal command says "Connection lost", nothing polls, and resuming the process clears it with a plain "Reconnected"
  (`--skip-hang` leaves these two out). It also screenshots the banner in light and dark and counts uncaught page errors (zero expected;
  the browser's own "Failed to load resource" lines for the dead port are counted separately).

Errors that come from the embedded Odysseus pages themselves (the Library page asks highlight.js for an `email` grammar, the chat page
polls a session id that does not exist yet) reproduce in a plain browser tab and are allow-listed in `tests/e2e/_os_e2e.py`.

## Known limitations

* The terminal runs one process per command (no PTY): interactive programs (`vim`, REPLs) do not work. In Command Prompt, `for %i` loop
  variables are rewritten to the batch form `%%i` because commands run from a temporary batch file.
* The embedded Odysseus pages keep their own timers (an activity heartbeat, mail state: about 10 requests a minute per open page) while
  their window is on screen. A window that has been hidden for a minute (minimised, or completely behind a maximised window) is put
  to sleep: its frame is replaced by a "paused while hidden" placeholder and comes back at the same address (query, #hash and scroll
  position) when the window is shown again, so unsaved in-page state is lost on that reload. A page that is in use is never paused:
  a chat answer still streaming, media playing, or text typed into a message box and not sent. `localStorage['os.embedSuspendMs']`
  changes the minute. The desktop's own widgets stop when the tab is hidden.
* The assistant's open-ended conversation needs a model configured in Odysseus; without one it still runs commands
  but cannot plan multi-step tasks.
* Jarvis state (plans, memory, audit events) is in memory; only the audit *file* survives a restart.
* On Windows, asyncio can hang if *every* task is cancelled in the one loop iteration right after a subprocess was spawned (a CPython bug in `_connect_pipes`). It only shows up when a script or test starts a command and closes its event loop without waiting; the running server and normal cancellation (e.g. a closed browser tab) are not affected. Await the command, or call `jarvis.shutdown()`, before closing a loop yourself.
