// Automations · what kinds of automation exist, how to name them, and the starter templates.
//
// A "draft" is the editor's form state (see editor.js):
//   { kind:'llm'|'research'|'action'|'command', name, prompt, action, command, trigger:'schedule'|'event'|'webhook',
//     sched:{...structured, see schedule.js}, event, count, output, emailTo, model, notify, then }

export const COMMAND_ACTIONS = new Set(['run_local', 'run_script', 'ssh_command']);

export function kindOfTask(t) {
  if ((t.task_type || 'llm') === 'action') return COMMAND_ACTIONS.has(t.action) ? 'command' : 'action';
  return t.task_type === 'research' ? 'research' : 'llm';
}

export const KIND_LABEL = { llm: 'AI prompt', research: 'Research', action: 'Action', command: 'Command' };

/** The chip shown in lists: how it starts beats what it does. */
export function typeChip(t) {
  const trig = t.trigger_type || 'schedule';
  if (trig === 'webhook') return { label: 'Webhook', tone: 'webhook' };
  if (trig === 'event') return { label: 'Event', tone: 'event' };
  const k = kindOfTask(t);
  return { label: KIND_LABEL[k], tone: k };
}

const ACTION_TITLES = {
  daily_brief: 'Morning brief', check_email_urgency: 'Inbox triage', summarize_emails: 'Summarise new email', draft_email_replies: 'Draft email replies',
  email_auto_translate: 'Translate foreign email', extract_email_events: 'Email to calendar', classify_events: 'Classify calendar events',
  tidy_sessions: 'Tidy chat sessions', tidy_documents: 'Tidy documents', consolidate_memory: 'Merge duplicate memories', tidy_research: 'Tidy research files',
  learn_sender_signatures: 'Learn sender signatures', test_skills: 'Test skills', audit_skills: 'Audit skills', cookbook_serve: 'Serve a model',
  run_local: 'Run a command', run_script: 'Run a script', ssh_command: 'Run a command over SSH',
};
const ACTION_BLURB = {
  run_local: 'Runs a command on this computer as the user that started Odysseus.',
  run_script: 'Runs a script on this computer, or on ODYSSEUS_SCRIPT_HOST over SSH.',
  ssh_command: 'Runs a command locally or on a remote host over SSH.',
  cookbook_serve: 'Starts a model from the Cookbook.',
};
export const actionTitle = (a) => ACTION_TITLES[a] || String(a || 'Action').replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase());
export const actionBlurb = (a, actions = []) => actions.find((x) => x.name === a)?.description || ACTION_BLURB[a] || '';

export function outputLabel(target, targets = []) {
  const t = String(target || 'session');
  if (t === 'session') return 'Chat session';
  if (t === 'notification') return 'Notification';
  if (t === 'none') return 'Run history only';
  if (t === 'email' || t === 'email:self') return 'Email to me';
  if (t.startsWith('email:')) return `Email to ${t.slice(6).split('|')[0]}`;
  if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(t)) return `Email to ${t}`;
  const hit = targets.find((x) => x.value === t);
  if (hit) return hit.label;
  return t.replace(/^mcp__/, '').replace(/__/g, ' → ');
}

/** A command that works on this machine: Git Bash / bash when present (what run_local uses), cmd otherwise. */
export function backupCommand(shells = [], isWindows = false) {
  const hasBash = !isWindows || shells.some((s) => s.id === 'bash');
  if (hasBash) {
    return 'mkdir -p "$HOME/Backups" && tar -czf "$HOME/Backups/Documents-$(date +%F).tgz" -C "$HOME" Documents && echo "Backed up Documents to $HOME/Backups"';
  }
  return 'if not exist "%USERPROFILE%\\Backups" mkdir "%USERPROFILE%\\Backups" & robocopy "%USERPROFILE%\\Documents" "%USERPROFILE%\\Backups\\Documents" /MIR /R:1 /W:1 /NFL /NDL & if errorlevel 8 (exit 1) else (exit 0)';
}

const base = () => ({
  kind: 'llm', name: '', prompt: '', action: '', command: '', trigger: 'schedule', sched: { mode: 'daily', time: '09:00' },
  event: 'email_received', count: 5, output: 'session', emailTo: '', model: '', notify: true, then: '',
});

/** Starter templates. `build(env)` returns a draft; env = { shells, isWindows }. */
export const TEMPLATES = [
  {
    id: 'morning-brief', title: 'Morning brief', icon: 'sun', when: 'Every day, 8:00',
    blurb: 'Today’s calendar, unread mail and open to-dos in one digest.',
    build: () => ({ ...base(), kind: 'action', name: 'Morning brief', action: 'daily_brief', sched: { mode: 'daily', time: '08:00' }, output: 'session', notify: false }),
  },
  {
    id: 'inbox-triage', title: 'Inbox triage', icon: 'mail', when: 'Every hour',
    blurb: 'Tags urgent mail and flags what needs a fast reply. Needs an email account in Odysseus.',
    companion: { label: 'Also pre-write summaries of new mail', action: 'summarize_emails', name: 'Inbox summaries', sched: { mode: 'interval', unit: 'hours', every: 1, at: 10 } },
    build: () => ({ ...base(), kind: 'action', name: 'Inbox triage', action: 'check_email_urgency', sched: { mode: 'interval', unit: 'hours', every: 1, at: 0 }, output: 'none', notify: false }),
  },
  {
    id: 'weekly-tidy', title: 'Weekly tidy', icon: 'sparkles', when: 'Sundays, 10:00',
    blurb: 'Clears empty chat sessions and sorts the rest into folders.',
    companion: { label: 'Also remove junk documents (10 minutes later)', action: 'tidy_documents', name: 'Weekly tidy: documents', offsetMin: 10 },
    build: () => ({ ...base(), kind: 'action', name: 'Weekly tidy', action: 'tidy_sessions', sched: { mode: 'weekly', days: [0], time: '10:00' }, output: 'none', notify: false }),
  },
  {
    id: 'folder-backup', title: 'Nightly folder backup', icon: 'drive', when: 'Every night, 2:00', admin: true,
    blurb: 'Compresses your Documents folder into ~/Backups. Edit the command to back up something else.',
    build: (env = {}) => ({ ...base(), kind: 'command', name: 'Nightly folder backup', command: backupCommand(env.shells, env.isWindows), sched: { mode: 'daily', time: '02:00' }, output: 'none', notify: false }),
  },
  {
    id: 'standup', title: 'Daily stand-up notes', icon: 'note', when: 'Weekdays, 9:00',
    blurb: 'Drafts a short stand-up from your calendar and notes, saved to a chat.',
    build: () => ({ ...base(), kind: 'llm', name: 'Daily stand-up notes', prompt: 'Look at my calendar and notes for today and draft a short stand-up update: what I finished yesterday, what I am doing today, and any blockers. Keep it under 120 words.', sched: { mode: 'weekdays', time: '09:00' }, output: 'session' }),
  },
  {
    id: 'weekly-review', title: 'Weekly review', icon: 'check-square', when: 'Fridays, 17:00',
    blurb: 'Summarises the week and suggests three priorities for the next one.',
    build: () => ({ ...base(), kind: 'llm', name: 'Weekly review', prompt: 'Review my week: summarise what I got done, what slipped, and suggest the three most important priorities for next week. Use my notes, calendar and recent chats.', sched: { mode: 'weekly', days: [5], time: '17:00' }, output: 'session' }),
  },
  {
    id: 'custom-ai', title: 'Custom AI prompt', icon: 'sparkles', when: 'You choose',
    blurb: 'Any instruction, on any schedule. The AI can use your tools and data.',
    build: () => ({ ...base(), kind: 'llm' }),
  },
  {
    id: 'custom-command', title: 'Custom command', icon: 'terminal', when: 'You choose', admin: true,
    blurb: 'Runs a shell command on this computer. Admin only.',
    build: () => ({ ...base(), kind: 'command', output: 'none', notify: false }),
  },
  {
    id: 'on-event', title: 'When something happens', icon: 'activity', when: 'On an event',
    blurb: 'Runs every few emails, chats, documents or memories instead of on a clock.',
    build: () => ({ ...base(), kind: 'llm', trigger: 'event', event: 'email_received', count: 5, name: 'New mail digest', prompt: 'Summarise the newest emails in my inbox and list anything that needs a reply today.' }),
  },
  {
    id: 'on-webhook', title: 'Webhook trigger', icon: 'link', when: 'On an HTTP call',
    blurb: 'Gets a private URL. Call it from a script, a shortcut or another service to run this.',
    build: () => ({ ...base(), kind: 'llm', trigger: 'webhook', name: 'Webhook automation' }),
  },
];

export const blankDraft = base;

/** Draft from a stored task (edit / duplicate). */
export function draftFromTask(t, schedFromTask) {
  const kind = kindOfTask(t);
  const trig = t.trigger_type || 'schedule';
  const out = String(t.output_target || 'session');
  const email = out.startsWith('email') || /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(out);
  let emailTo = '';
  if (email) {
    const raw = out.startsWith('email:') ? out.slice(6).split('|')[0] : out.includes('@') ? out : '';
    emailTo = raw === 'self' ? '' : raw;
  }
  return {
    ...base(), kind, name: t.name || '', prompt: kind === 'command' ? '' : (t.prompt || ''), command: kind === 'command' ? (t.prompt || '') : '',
    action: kind === 'action' ? (t.action || '') : '', trigger: trig,
    sched: trig === 'schedule' ? (schedFromTask(t) || base().sched) : base().sched,
    event: t.trigger_event || 'email_received', count: t.trigger_count || 5,
    output: email ? 'email' : out, emailTo,
    model: t.model && t.endpoint_url ? `${t.endpoint_url}::${t.model}` : '',
    notify: t.notifications_enabled !== false, then: t.then_task_id || '',
  };
}
