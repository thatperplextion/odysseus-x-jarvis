"""Click every visible button / tab / link / checkbox / select in every Odysseus OS window and report what happened.

NOT collected by pytest (no ``test_`` prefix). Needs ``pip install playwright`` and Microsoft Edge (or ``--channel chromium``).

    # 1. start a server on a SCRATCH data dir (never your real data; seed it first, see docs/ODYSSEUS_OS.md "Developing"):
    #      set APP_PORT=7405 & set ODYSSEUS_DATA_DIR=C:\\scratch\\data & venv\\Scripts\\python.exe app.py
    # 2. run the sweep:
    #      python tests/e2e/os_click_everything.py --url http://127.0.0.1:7405/os --out C:\\scratch\\click
    #      python tests/e2e/os_click_everything.py --url ... --apps files,settings --max-clicks 60 --no-embedded

For every app it opens the window from the launcher, enumerates the visible clickables (button, [role=button|tab|menuitem|
option|switch], a[href], summary, checkbox, radio, select), and clicks each one (at most ``--per-base`` times for identical
rows). Destructive confirmations are Cancelled unless the dialog text names a disposable ``qa-`` item the script created.
"Delete all", "Empty Trash", ending processes, sign-out and leaving the page are never clicked. The terminal never runs a
command. Preferences changed by the sweep (theme, dock, wallpaper), mounts added in Settings, model settings and automations it created are
restored/removed; todos it ticks off and reminders it marks done are not (seed fresh data before a run). Per click it records console errors,
page errors, unhandled rejections, failed requests, HTTP >= 400 responses, junk text such as "false"/"undefined" on screen
and "dead" clicks (no structural DOM change, request, focus, scroll, clipboard or download within ``--dead-ms`` ms).
Dead clicks are a heuristic: they are listed for review (an already-selected tab is legitimately dead).

Output: ``click_report.json`` and ``click_summary.txt`` in ``--out``, a readable table on stdout, exit code 1 on errors.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from _os_e2e import BAD_TEXT_JS, ENUM_JS, TAG_JS, UPSTREAM_ALLOW as _UPSTREAM_ALLOW, Desk, http_json, origin_of  # noqa: E402

# never click these (matched against label, aria-label and href)
NEVER = (r"delete all|wipe|empty trash|empty the trash|factory|sign ?out|log ?out|shut ?down|restart|uninstall|erase|format\b|"
         r"end task|end process|force end|\bkill\b|terminate|back to odysseus|remove all|purge|clear all|reset all|^open in its own tab$|"
         r"^run now|^run automation|^run$")   # run-now starts a real job (and may call the model): os_features.py covers it
# extra guard inside the embedded Odysseus pages, where there is no confirm we control
NEVER_EMBEDDED = NEVER + (r"|delete|remove|clear|reset|discard|disconnect|unlink|revoke|wipe|empty|trash|archive|logout|sign|admin|upgrade|update now|"
                          r"odysseus os|shell access|nobody mode|^(minimize|close)$")
# the Terminal must never execute a command during the sweep
# (and Jarvis' suggestion chips that go to the language model are skipped: each one is a real model call)
APP_NEVER = {"terminal": r"^run$|^send$|^execute$", "jarvis": r"plan my day|every morning|what.s on tomorrow"}
SANDBOX = "/Home/qa-sandbox"
UPSTREAM_ALLOW = _UPSTREAM_ALLOW   # errors raised by the embedded Odysseus pages themselves (see _os_e2e.py)


def seed_sandbox(base: str) -> None:
    http_json(base, "POST", "/api/os/fs/mkdir", {"path": SANDBOX})
    http_json(base, "POST", "/api/os/fs/mkdir", {"path": f"{SANDBOX}/qa-sub"})
    for name, text in (("qa-note.txt", "disposable note\n"), ("qa-readme.md", "# qa\n"), ("qa-sub/qa-inner.txt", "inner\n")):
        http_json(base, "PUT", "/api/os/fs/write", {"path": f"{SANDBOX}/{name}", "content": text})
    png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc000000301010018dd8db00000000049454e44ae426082")
    req = urllib.request.Request(base.rstrip("/") + f"/api/os/fs/upload?path={SANDBOX}/qa-pic.png&overwrite=true", data=png, method="PUT")
    try:
        urllib.request.urlopen(req, timeout=20).read()
    except Exception as e:  # noqa: BLE001
        print("  (could not upload sample png:", e, ")")


def _ref(r):
    return {"endpoint_id": r["endpoint_id"], "model": r["model"]} if r else None


def models_selection(base: str):
    status, cur = http_json(base, "GET", "/api/os/models/current")
    return cur if status == 200 else None


def restore_models(base: str, cur) -> None:
    """The AI models pane has "Remove from fallbacks" / "Apply recommendation" buttons that really change the settings."""
    if not cur or not cur.get("default"):
        return
    body = {"default": _ref(cur["default"]), "fallbacks": [_ref(f) for f in cur.get("fallbacks") or []],
            "utility": _ref(cur.get("utility")), "utility_fallbacks": [_ref(f) for f in cur.get("utility_fallbacks") or []]}
    http_json(base, "POST", "/api/os/models/default", body)


def mounts_snapshot(base: str):
    status, data = http_json(base, "GET", "/api/os/fs/roots")
    return {m["name"] for m in (data or {}).get("mounts", [])} if status == 200 else None


def restore_mounts(base: str, names) -> None:
    """Settings > Folders has "Quick add" chips that mount real folders (Documents, Downloads...): unmount what the sweep added."""
    if names is None:
        return
    for name in mounts_snapshot(base) or ():
        if name not in names:
            http_json(base, "DELETE", f"/api/os/mounts/{urllib.parse.quote(name)}")


def task_ids(base: str):
    status, data = http_json(base, "GET", "/api/tasks")
    return {t["id"] for t in (data or {}).get("tasks", [])} if status == 200 else None


def remove_new_tasks(base: str, before) -> int:
    """The Automations app has Duplicate / New: delete the automations the sweep itself created."""
    if before is None:
        return 0
    n = 0
    for tid in (task_ids(base) or set()) - before:
        http_json(base, "DELETE", f"/api/tasks/{tid}")
        n += 1
    return n


def cleanup_sandbox(base: str) -> None:
    http_json(base, "POST", "/api/os/fs/delete", {"path": SANDBOX})


class Sweeper:
    def __init__(self, desk: Desk, args):
        self.d = desk
        self.args = args
        self.page = desk.page
        self.rec = desk.rec

    # -- helpers ---------------------------------------------------------------------------------------
    def snapshot(self, target) -> Dict[str, Any]:
        focus = ""
        try:
            # focus only counts when it moved somewhere OTHER than the clicked element (every click focuses its own button)
            focus = self.page.evaluate("(() => { const a = document.activeElement; if (!a || a === document.body || a.hasAttribute('data-qa-target') || a.closest('[data-qa-target]')) return ''; return a.tagName + '.' + (a.className || '') + '.' + (a.getAttribute('aria-label') || a.textContent || '').slice(0, 30); })()")
        except Exception:
            pass
        overlay = self.page.evaluate("document.querySelectorAll('#overlays > *, #overlays .modal, #overlays .ctx, #overlays .popover, #overlays .toast').length")
        return dict(struct=self.d.probe("struct"), scroll=self.d.probe("scroll"), fx=self.d.probe("fx") + self.rec.fx_events,
                    req=self.rec.requests, url=self.page.url, focus=focus, overlay=overlay)

    def handle_overlay(self, ctx: str) -> str:
        """Close whatever the click opened. Returns a short note about what it was."""
        note = ""
        modal = self.page.locator("#overlays .modal")
        if modal.count():
            text = modal.first.inner_text()
            note = "modal: " + re.sub(r"\s+", " ", text)[:80]
            primary = modal.first.locator(".btn-ink, .btn-danger").first
            if re.search(r"\bqa-", text) and primary.count() and not re.search(r"empty trash|all \d+ items", text, re.I):
                primary.click()
                note += "  -> confirmed (disposable)"
            else:
                self.page.keyboard.press("Escape")
        for sel in ("#overlays .ctx", "#overlays .popover", "#overlays .palette-backdrop", "#overlays .launcher"):
            if self.page.locator(sel).count():
                note = note or f"opened {sel.split('.')[-1]}"
                self.page.keyboard.press("Escape")
                if self.page.locator(sel).count():   # Escape did not close it: click away
                    self.page.mouse.click(5, 300)
        self.page.wait_for_timeout(120)
        return note

    def wait_effect(self, target, before: Dict[str, Any]) -> bool:
        deadline = time.time() + self.args.dead_ms / 1000
        while time.time() < deadline:
            self.page.wait_for_timeout(100)
            now = self.snapshot(target)
            if any(now[k] != before[k] for k in ("struct", "scroll", "fx", "req", "url", "focus", "overlay")):
                return True
        return False

    # -- the sweep -------------------------------------------------------------------------------------
    def sweep(self, app: str, root: str, target, *, embedded: bool = False, reset_each: bool = False) -> Dict[str, Any]:
        res: Dict[str, Any] = dict(app=app, clicks=0, dead=[], errors=[], skipped=[], notes=[], bad_text=[], vanished=0, seconds=0.0)
        skip_re = (NEVER_EMBEDDED if embedded else NEVER) + (("|" + APP_NEVER[app]) if app in APP_NEVER else "")
        seen: Dict[str, int] = {}
        clicked_sigs = set()
        prev_bases: set = set()
        t0 = time.time()
        stall = 0
        keep_app = app.split(":")[0] if (root.startswith("section.win") or embedded) else None
        while res["clicks"] < self.args.max_clicks and time.time() - t0 < self.args.app_seconds:
            if root.startswith("section.win") and self.page.locator(root).count() == 0:
                res["notes"].append("window closed itself")
                break
            try:
                items = target.evaluate(ENUM_JS, [root, skip_re, seen, self.args.per_base])
            except Exception as e:  # noqa: BLE001 - frame navigated mid-evaluate
                res["notes"].append(f"enumerate failed: {str(e)[:80]}")
                self.page.wait_for_timeout(300)
                stall += 1
                if stall > 3:
                    break
                continue
            for it in items:
                if it["skipped"] and it["sig"] not in [s["sig"] for s in res["skipped"]]:
                    res["skipped"].append({"sig": it["sig"], "label": it["label"]})
            cands = [i for i in items if not i["skipped"] and i["sig"] not in clicked_sigs and seen.get(i["base"], 0) < self.args.per_base
                     and not (i["tag"] == "a" and re.match(r"https?://", i["href"]) and origin_of(i["href"]) != origin_of(self.page.url))]
            if not cands:
                break
            # depth first: what the last click revealed (a new pane, a form) is explored before moving on along the page
            fresh = [i for i in cands if i["base"] not in prev_bases]
            cand = (fresh or cands)[0]
            prev_bases = {i["base"] for i in items}
            clicked_sigs.add(cand["sig"])
            seen[cand["base"]] = seen.get(cand["base"], 0) + 1
            where = f"{app} > {cand['label'] or cand['base']}"
            self.rec.where = where
            ok = target.evaluate(TAG_JS, [root, cand["sig"]])
            if not ok:
                res["vanished"] += 1
                continue
            before = self.snapshot(target)
            n_problems = len(self.rec.problems)
            how = "click"
            try:
                target.locator("[data-qa-target]").first.click(timeout=2500)
            except Exception as e:  # noqa: BLE001
                how = "js-click"
                try:
                    target.evaluate("() => { const el = document.querySelector('[data-qa-target]'); if (el) el.click(); }")
                except Exception:
                    res["notes"].append(f"could not click {cand['label']}: {str(e)[:60]}")
                    continue
                res["notes"].append(f"{cand['label'] or cand['base']}: needed js click ({str(e).splitlines()[0][:70]})")
            res["clicks"] += 1
            changed = self.wait_effect(target, before)
            if cand["role"] in ("checkbox", "radio") and cand["tag"] == "input":
                try:   # a toggle changes real data (a todo, a setting): put it back
                    if target.evaluate("() => { const el = document.querySelector('[data-qa-target]'); return el ? el.checked : null; }") is not None:
                        target.locator("[data-qa-target]").first.click(timeout=1500)
                        res["notes"].append(f"{cand['label'] or cand['base']}: toggled and restored")
                except Exception:  # noqa: BLE001
                    pass
            if self.args.verbose:
                print(f"    [{app}] {cand['label'] or cand['base']!r}  {'changed' if changed else 'DEAD?'}", flush=True)
            note = self.handle_overlay(where)
            if note:
                res["notes"].append(f"{cand['label'] or cand['base']}: {note}")
            if not changed and not note:
                res["dead"].append({"label": cand["label"], "tag": cand["tag"], "role": cand["role"], "cls": cand["cls"], "how": how})
            if reset_each:
                self.d.close_all_windows()
                self.page.keyboard.press("Escape")
            elif keep_app:
                # a click can open another app's window (a recent file -> the Editor); it would cover the window being swept
                self.d.os_eval("(os, keep) => { for (const w of os.wm.list()) if (w.app !== keep) w.close({ force: true }); }", keep_app)
            new = self.rec.problems[n_problems:]
            if new:
                res["errors"].extend({"click": cand["label"] or cand["base"], **p} for p in new)
        res["seconds"] = round(time.time() - t0, 1)
        try:
            res["bad_text"] = target.evaluate(BAD_TEXT_JS, "document" if embedded else root)
        except Exception:  # noqa: BLE001 - the window may be gone
            res["bad_text"] = []
        self.rec.drain_page_rejections()
        return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://127.0.0.1:7000/os")
    ap.add_argument("--apps", default="", help="comma list of app ids (default: all, incl. editor and viewer)")
    ap.add_argument("--out", default="click_out")
    ap.add_argument("--max-clicks", type=int, default=90)
    ap.add_argument("--per-base", type=int, default=2, help="max clicks on identical-looking elements (list rows)")
    ap.add_argument("--app-seconds", type=float, default=150)
    ap.add_argument("--dead-ms", type=int, default=1500)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=800)
    ap.add_argument("--channel", default="msedge")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--no-embedded", dest="embedded", action="store_false", help="do not click inside the embedded Odysseus pages")
    ap.add_argument("--server-log", default="", help="path of the server's log, to report Tracebacks written during the run")
    ap.add_argument("--embedded-clicks", type=int, default=30, help="max clicks inside each embedded Odysseus page")
    ap.add_argument("--keep-sandbox", action="store_true")
    ap.add_argument("--verbose", "-v", action="store_true", help="print every click")
    args = ap.parse_args()

    base = origin_of(args.url)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    seed_sandbox(base)
    models0 = models_selection(base)
    mounts0 = mounts_snapshot(base)
    tasks0 = task_ids(base)
    report: Dict[str, Any] = dict(url=args.url, started=time.strftime("%Y-%m-%d %H:%M:%S"), apps={}, problems=[], server_errors=[])

    with sync_playwright() as p:
        d = Desk(p, args.url, channel=args.channel, width=args.width, height=args.height, headed=args.headed,
                 server_log=Path(args.server_log) if args.server_log else None, allow=UPSTREAM_ALLOW)
        sw = Sweeper(d, args)
        report["boot_seconds"] = round(d.boot(), 2)
        d.settle(800)
        prefs0 = d.page.evaluate("async () => (await import('/static/os/js/state.js')).getPrefs()")
        apps = d.os_eval("(os) => os.appList().map((a) => ({ id: a.id, name: a.name, hidden: !!a.hidden }))")
        wanted = [a for a in args.apps.split(",") if a]
        order = [a for a in apps if not a["hidden"]]
        order = [a for a in order if not wanted or a["id"] in wanted]
        if not wanted or "editor" in wanted:
            order.append(dict(id="editor", name="Editor", hidden=True))
        if not wanted or "viewer" in wanted:
            order.append(dict(id="viewer", name="Viewer", hidden=True))

        # the shell chrome itself (menubar, dock, launcher, desktop widgets) is swept first
        d.rec.where = "desktop"
        d.close_all_windows()   # a saved session may have restored windows over the desktop
        for name, root in (("desktop", "#home"), ("menubar", "#menubar"), ("dock", "#dock")):
            if wanted and "desktop" not in wanted:
                break
            r = sw.sweep(name, root, d.page, reset_each=True)
            report["apps"][name] = r
            print(f"  {name:<12} {r['clicks']:>3} clicks  {len(r['errors'])} errors  {len(r['dead'])} dead  {r['seconds']}s", flush=True)
            d.close_all_windows()
            d.page.keyboard.press("Escape")

        for a in order:
            app = a["id"]
            d.rec.where = f"open {app}"
            try:
                if app == "editor":
                    d.open_app("editor", {"path": f"{SANDBOX}/qa-note.txt"})
                elif app == "viewer":
                    d.open_app("viewer", {"path": f"{SANDBOX}/qa-pic.png"})
                elif app == "files":
                    d.open_via_launcher(a["name"])
                    d.win("files").wait_for(timeout=8000)
                    d.close_all_windows()
                    d.open_app("files", {"path": SANDBOX})
                else:
                    d.open_via_launcher(a["name"])
                    d.win(app).wait_for(timeout=8000)
                d.settle(1200 if a["id"] in {"chat", "notes", "documents", "email", "calendar", "tasks", "memory", "gallery", "cookbook"} else 700)
            except Exception as e:  # noqa: BLE001
                report["apps"][app] = dict(app=app, clicks=0, errors=[dict(kind="open", msg=str(e)[:200])], dead=[], skipped=[], notes=["could not open"], bad_text=[], seconds=0)
                print(f"  {app:<12} COULD NOT OPEN: {str(e)[:100]}")
                continue
            root = f'section.win[data-app="{app}"]'
            try:
                r = sw.sweep(app, root, d.page)
            except Exception as e:  # noqa: BLE001
                r = dict(app=app, clicks=0, errors=[dict(kind="sweep", msg=str(e)[:200])], dead=[], skipped=[], notes=["sweep crashed"], bad_text=[], seconds=0)
            if app in {"chat", "notes", "documents", "email", "calendar", "tasks", "memory", "gallery", "cookbook"} and args.embedded:
                try:
                    frame = d.win(app).locator("iframe").first.element_handle().content_frame()
                    if frame:
                        saved_max, args.max_clicks = args.max_clicks, args.embedded_clicks
                        try:
                            fr = sw.sweep(f"{app}:embedded", "document", frame, embedded=True)
                        finally:
                            args.max_clicks = saved_max
                        r["embedded"] = {k: fr[k] for k in ("clicks", "dead", "errors", "skipped", "notes", "bad_text", "seconds")}
                        r["clicks"] += fr["clicks"]
                        r["errors"] += fr["errors"]
                        r["dead"] += [dict(x, label="[embedded] " + x["label"]) for x in fr["dead"]]
                except Exception as e:  # noqa: BLE001
                    r["notes"].append(f"embedded sweep failed: {str(e)[:80]}")
            d.shot(out / f"{app}.png")
            report["apps"][app] = r
            (out / "click_report.partial.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
            print(f"  {app:<12} {r['clicks']:>3} clicks  {len(r['errors'])} errors  {len(r['dead'])} dead  {len(r['bad_text'])} bad-text  {r['seconds']}s", flush=True)
            d.close_all_windows()
            d.page.keyboard.press("Escape")

        restore_models(base, models0)
        restore_mounts(base, mounts0)
        report["tasks_removed"] = remove_new_tasks(base, tasks0)
        # restore preferences the sweep may have changed
        d.page.evaluate("async (p) => { const st = await import('/static/os/js/state.js'); for (const k of Object.keys(p)) st.setPref(k, p[k]); st.applyTheme(); }", prefs0)
        d.rec.drain_page_rejections()
        report["problems"] = [x for x in d.rec.problems if x["kind"] != "teardown"]
        report["teardown_noise"] = [x["msg"][:120] for x in d.rec.problems if x["kind"] == "teardown"]
        report["server_errors"] = d.rec.server_errors()
        report["requests_total"] = d.rec.requests
        d.close()

    if not args.keep_sandbox:
        cleanup_sandbox(base)
    (out / "click_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines: List[str] = [f"Odysseus OS click-everything  {report['started']}  {args.url}", f"boot to desktop: {report['boot_seconds']} s", ""]
    lines.append(f"{'app':<14}{'clicks':>7}{'errors':>8}{'dead':>6}{'bad text':>9}{'skipped':>9}{'s':>7}")
    for k, r in report["apps"].items():
        lines.append(f"{k:<14}{r['clicks']:>7}{len(r['errors']):>8}{len(r['dead']):>6}{len(r['bad_text']):>9}{len(r['skipped']):>9}{r['seconds']:>7}")
    lines.append("")
    n_err = sum(len(r["errors"]) for r in report["apps"].values())
    for k, r in report["apps"].items():
        for e in r["errors"]:
            lines.append(f"ERROR [{k}] {e.get('click', '')}: {e['kind']} {e['msg'][:200]}")
        for b in r["bad_text"]:
            lines.append(f"BAD TEXT [{k}] {b}")
        if r["dead"]:
            lines.append(f"dead clicks [{k}]: " + "; ".join(f"{x['label'] or x['cls'] or x['tag']}" for x in r["dead"]))
    for p in report["problems"]:
        if not any(p["msg"] == e["msg"] for r in report["apps"].values() for e in r["errors"]):
            lines.append(f"UNATTRIBUTED [{p['where']}] {p['kind']} {p['msg'][:200]}")
    for s in report["server_errors"]:
        lines.append(f"SERVER LOG: {s[:200]}")
    if report.get("teardown_noise"):
        lines.append(f"(+{len(report['teardown_noise'])} 'Failed to fetch' console lines from embedded pages that were closed mid-request; not counted)")
    lines.append("")
    lines.append(f"total clicks {sum(r['clicks'] for r in report['apps'].values())}, errors {n_err}, requests {report['requests_total']}")
    text = "\n".join(lines)
    (out / "click_summary.txt").write_text(text, encoding="utf-8")
    print("\n" + text)
    return 1 if (n_err or report["problems"] or report["server_errors"]) else 0


if __name__ == "__main__":
    sys.exit(main())
