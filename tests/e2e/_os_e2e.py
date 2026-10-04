"""Shared helpers for the Odysseus OS browser scripts (os_click_everything.py, os_features.py).

Not a pytest module (leading underscore, no ``test_`` prefix). Needs ``pip install playwright`` and an installed
Microsoft Edge (or pass ``--channel chromium`` after ``playwright install chromium``).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# --------------------------------------------------------------------------------------------- in-page probe
# Injected into every frame before any app code runs. It only observes; it never changes behaviour.
PROBE_JS = r"""
(() => {
  if (window.__qa) return;
  const q = window.__qa = { struct: 0, fx: 0, scroll: 0, rej: [], raf: 0, intervals: new Set(), timeouts: new Set(), listeners: new Map() };
  // structural mutations only: ticking clocks (text replaced every second) and animated SVG/style must not count as "an effect"
  const quiet = new Set(['style', 'd', 'points', 'x', 'y', 'x1', 'x2', 'y1', 'y2', 'width', 'height', 'transform', 'stroke-dashoffset', 'data-hot', 'title', 'aria-valuenow', 'value', 'data-qa-target']);
  const isSvg = (n) => n && n.namespaceURI === 'http://www.w3.org/2000/svg';
  try {
    new MutationObserver((list) => {
      for (const m of list) {
        if (m.type === 'attributes') { if (!quiet.has(m.attributeName) && !isSvg(m.target)) q.struct++; }
        else if (m.type === 'childList') {
          const els = [...m.addedNodes, ...m.removedNodes].filter((n) => n.nodeType === 1 && !isSvg(n));
          if (els.length) q.struct++;
        }
      }
    }).observe(document, { subtree: true, childList: true, attributes: true });
  } catch (e) { /* ignore */ }
  document.addEventListener('scroll', () => { q.scroll++; }, true);
  window.addEventListener('unhandledrejection', (e) => { q.rej.push(String((e.reason && e.reason.message) || e.reason)); });
  // effects with no DOM change: copy to clipboard, downloads (anchor.click on a download link), window.open
  try { const wt = navigator.clipboard && navigator.clipboard.writeText; if (wt) navigator.clipboard.writeText = function (...a) { q.fx++; return wt.apply(this, a); }; } catch (e) { /* ignore */ }
  try { const ac = HTMLAnchorElement.prototype.click; HTMLAnchorElement.prototype.click = function (...a) { q.fx++; return ac.apply(this, a); }; } catch (e) { /* ignore */ }
  try { const wo = window.open; window.open = function (...a) { q.fx++; return wo.apply(this, a); }; } catch (e) { /* ignore */ }
  // timers + long-lived listeners, for the leak checks
  const si = window.setInterval, ci = window.clearInterval, st = window.setTimeout, ct = window.clearTimeout, raf = window.requestAnimationFrame;
  window.setInterval = function (f, ms, ...a) { const id = si.call(this, f, ms, ...a); q.intervals.add(id); return id; };
  window.clearInterval = function (id) { q.intervals.delete(id); return ci.call(this, id); };
  window.setTimeout = function (f, ms, ...a) {
    let id; id = st.call(this, function (...b) { q.timeouts.delete(id); return typeof f === 'function' ? f.apply(this, b) : undefined; }, ms, ...a);
    q.timeouts.add(id); return id;
  };
  window.clearTimeout = function (id) { q.timeouts.delete(id); return ct.call(this, id); };
  window.requestAnimationFrame = function (f) { q.raf++; return raf.call(this, f); };
  const add = EventTarget.prototype.addEventListener, rem = EventTarget.prototype.removeEventListener;
  const name = (t) => (t === window ? 'window' : t === document ? 'document' : t === document.body ? 'body' : t === document.documentElement ? 'html' : null);
  const keyOf = (n, type, fn, cap) => { if (!fn.__qaid) Object.defineProperty(fn, '__qaid', { value: Math.random().toString(36).slice(2) }); return `${n}|${type}|${fn.__qaid}|${!!cap}`; };
  EventTarget.prototype.addEventListener = function (type, fn, opts) {
    try { const n = name(this); if (n && typeof fn === 'function') q.listeners.set(keyOf(n, type, fn, opts && typeof opts === 'object' ? opts.capture : opts), `${n}:${type}`); } catch (e) { /* ignore */ }
    return add.call(this, type, fn, opts);
  };
  EventTarget.prototype.removeEventListener = function (type, fn, opts) {
    try { const n = name(this); if (n && typeof fn === 'function') q.listeners.delete(keyOf(n, type, fn, opts && typeof opts === 'object' ? opts.capture : opts)); } catch (e) { /* ignore */ }
    return rem.call(this, type, fn, opts);
  };
})();
"""

ENUM_JS = r"""
([rootSel, skipRe, seenCounts, maxPerBase]) => {
  const roots = rootSel === 'document' ? [document] : [...document.querySelectorAll(rootSel)];
  const sel = 'button, [role=button], [role=tab], [role=menuitem], [role=option], [role=switch], summary, a[href], input[type=checkbox], input[type=radio], select';
  const skip = skipRe ? new RegExp(skipRe, 'i') : null;
  const out = []; const bases = {};
  for (const root of roots) for (const el of root.querySelectorAll(sel)) {
    if (el.disabled || el.getAttribute('aria-disabled') === 'true' || el.hasAttribute('data-qa-skip')) continue;
    if (el.closest('[hidden], [inert], .win-actions, .win-resize')) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || cs.pointerEvents === 'none' || +cs.opacity === 0) continue;
    const label = (el.getAttribute('aria-label') || el.title || el.textContent || el.value || el.name || '').trim().replace(/\s+/g, ' ').slice(0, 70);
    const cls = (typeof el.className === 'string' ? el.className : '').split(/\s+/).filter((c) => !/^(on|sel|active|focused|running|open|hover)$/.test(c)).slice(0, 3).join('.');
    const base = `${el.tagName.toLowerCase()}|${el.getAttribute('role') || el.type || ''}|${label.replace(/\d+/g, '#')}|${cls}`;   // digits normalised: countdowns tick
    const text = `${label} ${el.getAttribute('href') || ''} ${el.getAttribute('aria-label') || ''}`;
    const d = { base, label, tag: el.tagName.toLowerCase(), role: el.getAttribute('role') || el.type || '', cls, href: el.getAttribute('href') || '', skipped: !!(skip && skip.test(text)) };
    bases[base] = (bases[base] || 0) + 1;
    d.sig = `${base}#${bases[base]}`;
    d.index = out.length;
    d.times = seenCounts[base] || 0;
    out.push(d);
  }
  return out;
}
"""

TAG_JS = r"""
([rootSel, sig]) => {
  for (const x of document.querySelectorAll('[data-qa-target]')) x.removeAttribute('data-qa-target');
  const roots = rootSel === 'document' ? [document] : [...document.querySelectorAll(rootSel)];
  const sel = 'button, [role=button], [role=tab], [role=menuitem], [role=option], [role=switch], summary, a[href], input[type=checkbox], input[type=radio], select';
  const bases = {};
  for (const root of roots) for (const el of root.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || cs.pointerEvents === 'none' || +cs.opacity === 0) continue;
    if (el.disabled || el.closest('[hidden], [inert], .win-actions, .win-resize')) continue;
    const label = (el.getAttribute('aria-label') || el.title || el.textContent || el.value || el.name || '').trim().replace(/\s+/g, ' ').slice(0, 70);
    const cls = (typeof el.className === 'string' ? el.className : '').split(/\s+/).filter((c) => !/^(on|sel|active|focused|running|open|hover)$/.test(c)).slice(0, 3).join('.');
    const base = `${el.tagName.toLowerCase()}|${el.getAttribute('role') || el.type || ''}|${label.replace(/\d+/g, '#')}|${cls}`;   // digits normalised: countdowns tick
    bases[base] = (bases[base] || 0) + 1;
    if (`${base}#${bases[base]}` === sig) { el.setAttribute('data-qa-target', '1'); return true; }
  }
  return false;
}
"""

# text nodes that should never be visible: a native append(false) / template slip
BAD_TEXT_JS = r"""
(rootSel) => {
  const roots = rootSel === 'document' ? [document.body] : [...document.querySelectorAll(rootSel)];
  const bad = [];
  const re = /^(false|true|null|undefined|NaN|\[object Object\]|Invalid Date|-?Infinity)$/;
  for (const root of roots) {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = w.nextNode())) {
      const t = n.nodeValue.trim();
      if (!t) continue;
      if (re.test(t) || /\b(undefined|NaN|\[object Object\])\b/.test(t) && t.length < 80) {
        const p = n.parentElement;
        if (p && p.closest('textarea, pre.term-out, .term-out, .editor-text, code')) continue;
        bad.push(`${t.slice(0, 60)} in <${p ? p.tagName.toLowerCase() : '?'} class="${p ? p.className : ''}">`);
      }
    }
  }
  return bad.slice(0, 8);
}
"""


# Messages raised by the embedded *Odysseus* pages themselves: reproducible in a plain browser tab at /library and /notes, not caused
# by the desktop shell. Listed so a run is not drowned in them; os_click_everything.py / os_features.py both use this list.
UPSTREAM_ALLOW = [
    dict(url=r"/api/(research/status|chat/stream_status)/[0-9a-f-]{36}$", status=404, method="GET", why="chat page polls a session that does not exist (yet)"),
    dict(url=r"highlight\.min\.js", status=None, method=None, why="the Library page asks highlight.js for an 'email' grammar it does not have"),
]
# server log lines that are the Odysseus email page's own noise when no mail account is configured
UPSTREAM_SERVER_LOG = [r"IMAP is not configured", r"SMTP not configured", r"_ProactorBasePipeTransport._call_connection_lost", r"ConnectionResetError"]


class Problem(dict):
    """One recorded problem: kind, message, where (app / action)."""


class Recorder:
    """Collects console errors, page errors, failed requests and HTTP >= 400 across the whole run."""

    def __init__(self, page, *, allow: Optional[List[Dict[str, Any]]] = None, server_log: Optional[Path] = None):
        self.page = page
        self.where = "boot"
        self.problems: List[Problem] = []
        self.requests = 0
        self.req_times: List[float] = []
        self.api_counts: Dict[str, int] = {}
        self.allow = allow or []     # [{url: regex, status: int|None, method: str|None, why: str}] expected failures
        self.fx_events = 0           # downloads / popups / file choosers (non-DOM effects)
        self.tearing_down = False    # while windows are being closed, "Failed to fetch" from an aborted frame is noise
        self.grace_until = 0.0       # ...and for a moment after
        self.server_log = server_log
        self._log_pos = server_log.stat().st_size if server_log and server_log.exists() else 0
        page.on("console", self._on_console)
        page.on("pageerror", lambda e: self.add("pageerror", str(e)))
        page.on("requestfailed", self._on_failed)
        page.on("response", self._on_response)
        page.on("request", self._on_request)
        page.on("download", lambda d: self._fx("download"))
        page.on("popup", lambda p: (self._fx("popup"), p.close()))
        page.on("filechooser", lambda fc: self._fx("filechooser"))
        page.on("dialog", lambda d: d.dismiss())   # native alert/confirm/prompt: never accept

    def _fx(self, _kind: str) -> None:
        self.fx_events += 1

    def add(self, kind: str, msg: str, **extra) -> None:
        self.problems.append(Problem(kind=kind, msg=msg[:500], where=self.where, **extra))

    def _allowed(self, url: str, status: Optional[int], method: str) -> bool:
        for a in self.allow:
            if re.search(a["url"], url) and (a.get("status") in (None, status)) and (a.get("method") in (None, method)):
                return True
        return False

    def _on_console(self, m) -> None:
        if m.type != "error":
            return
        text = m.text
        if text.startswith("Failed to load resource"):
            loc = m.location or {}
            if self._allowed(loc.get("url", ""), None, None) or any(re.search(a["url"], loc.get("url", "")) for a in self.allow):
                return
            # the matching response is recorded separately with its URL; keep this one out of the noise
            return
        loc = (m.location or {}).get("url", "")
        if any(a.get("status") is None and a.get("method") is None and re.search(a["url"], loc) for a in self.allow):
            return
        if (self.tearing_down or time.time() < self.grace_until) and re.search(r"Failed to fetch|AbortError|aborted|NetworkError", text):
            self.add("teardown", text, url=loc)   # reported, but not counted as an error
            return
        self.add("console", text, url=loc)

    def _on_failed(self, req) -> None:
        err = (req.failure or "") if isinstance(req.failure, str) else str(req.failure)
        if "ERR_ABORTED" in err or "aborted" in err.lower():
            return   # an AbortController / a closed window, not a failure
        if self._allowed(req.url, None, req.method):
            return
        self.add("netfail", f"{req.method} {req.url} {err}")

    def _on_response(self, res) -> None:
        if res.status >= 400 and not self._allowed(res.url, res.status, res.request.method):
            self.add("http", f"{res.status} {res.request.method} {res.url}", status=res.status)

    def _on_request(self, req) -> None:
        self.requests += 1
        self.req_times.append(time.time())
        m = re.match(r"https?://[^/]+(/[^?#]*)", req.url)
        if m and m.group(1).startswith(("/api/", "/static/os/js/", "/os")):
            key = f"{req.method} {re.sub(r'[0-9a-f]{8,}', ':id', m.group(1))}"
            self.api_counts[key] = self.api_counts.get(key, 0) + 1

    def server_errors(self) -> List[str]:
        """Tracebacks / ERROR lines the server wrote since this recorder was created."""
        if not self.server_log or not self.server_log.exists():
            return []
        with open(self.server_log, "rb") as f:
            f.seek(self._log_pos)
            data = f.read().decode("utf-8", "replace")
        self._log_pos += len(data.encode("utf-8", "replace"))
        lines = [ln for ln in data.splitlines() if re.search(r"Traceback|\bERROR\b|\bCRITICAL\b|Exception in ASGI", ln)]
        # a Traceback line directly under an upstream-noise ERROR line is part of it
        keep: List[str] = []
        skip_next_tb = False
        for ln in lines:
            noisy = any(re.search(p, ln) for p in UPSTREAM_SERVER_LOG)
            if noisy:
                skip_next_tb = True
                continue
            if ln.startswith("Traceback") and skip_next_tb:
                skip_next_tb = False
                continue
            skip_next_tb = False
            keep.append(ln)
        return keep[:30]

    def drain_page_rejections(self) -> None:
        """Unhandled promise rejections recorded by the in-page probe (also logged to the console by the app)."""
        for fr in self.page.frames:
            try:
                rej = fr.evaluate("(() => { const r = (window.__qa && window.__qa.rej) || []; const c = r.slice(); if (window.__qa) window.__qa.rej.length = 0; return c; })()")
            except Exception:
                continue
            for r in rej:
                self.add("unhandledrejection", r)


class Desk:
    """A launched browser pointed at the desktop, with helpers to drive it."""

    def __init__(self, pw, url: str, *, channel: str = "msedge", width: int = 1280, height: int = 800, headed: bool = False,
                 server_log: Optional[Path] = None, allow=None, scheme: str = "light"):
        self.pw = pw
        self.url = url
        launch = dict(headless=not headed)
        if channel != "chromium":
            launch["channel"] = channel
        self.browser = pw.chromium.launch(**launch)
        self.ctx = self.browser.new_context(viewport={"width": width, "height": height}, color_scheme=scheme, accept_downloads=True)
        self.ctx.add_init_script(PROBE_JS)
        self.page = self.ctx.new_page()
        self.rec = Recorder(self.page, allow=allow, server_log=server_log)

    def boot(self) -> float:
        t0 = time.time()
        self.page.goto(self.url, wait_until="domcontentloaded")
        self.page.locator("#desktop:not([hidden])").wait_for(timeout=30000)
        self.page.locator(".dash-grid .widget, .dash-grid > *").first.wait_for(timeout=15000)
        return time.time() - t0

    def close(self) -> None:
        try:
            self.browser.close()
        except Exception:
            pass

    # -- os access ----------------------------------------------------------------------------------------
    def os_eval(self, js: str, arg: Any = None):
        """Run `js` (an arrow function taking (os, arg)) with the shell's `os` context object."""
        wrapped = "async (arg) => { const { os } = await import('/static/os/js/ctx.js'); return (" + js + ")(os, arg); }"
        return self.page.evaluate(wrapped, arg)

    def open_app(self, app_id: str, props: Optional[dict] = None) -> None:
        self.os_eval("(os, a) => { os.openApp(a.id, a.props); }", {"id": app_id, "props": props or {}})
        self.page.locator(f'section.win[data-app="{app_id}"]').last.wait_for(timeout=10000)

    def open_via_launcher(self, name: str) -> None:
        self.page.get_by_role("button", name="All apps").click()
        self.page.locator(".launch-item", has=self.page.locator(".launch-name", has_text=re.compile(f"^{re.escape(name)}$"))).click()

    def win(self, app_id: str):
        return self.page.locator(f'section.win[data-app="{app_id}"]').last

    def close_all_windows(self) -> None:
        self.rec.tearing_down = True
        try:
            self.os_eval("async (os) => { for (const w of os.wm.list()) await w.close({ force: true }); }")
            self.page.wait_for_timeout(450)
        finally:
            self.rec.tearing_down = False
            self.rec.grace_until = time.time() + 2.5

    def settle(self, ms: int = 400) -> None:
        self.page.wait_for_timeout(ms)

    def probe(self, key: str = "struct") -> int:
        total = 0
        for fr in self.page.frames:
            try:
                total += fr.evaluate(f"(window.__qa && window.__qa.{key}) || 0")
            except Exception:
                pass
        return total

    def shot(self, path: Path) -> None:
        self.page.screenshot(path=str(path))


# ------------------------------------------------------------------------------------------------ small utils
def http_get(base: str, path: str, host: str = "127.0.0.1", timeout: float = 30):
    import urllib.request

    req = urllib.request.Request(base.rstrip("/") + path, headers={"Host": host})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def http_json(base: str, method: str, path: str, body: Optional[dict] = None, timeout: float = 30):
    import urllib.error
    import urllib.request

    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base.rstrip("/") + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except (urllib.error.URLError, OSError) as e:   # server not reachable
        return 0, str(e)


def origin_of(url: str) -> str:
    m = re.match(r"(https?://[^/]+)", url)
    return m.group(1) if m else url
