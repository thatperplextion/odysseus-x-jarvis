"""Browser check for the lost-server behaviour of Odysseus OS (static/os/js/net.js + netui.js).

Not a pytest module. Starts its OWN scratch server (fresh data dir, never your real one) on --port, opens /os in Edge with
several apps open, then kills the server by the exact PID listening on that port and checks what the desktop does:

  * the "Odysseus isn't responding" banner appears within ~5 s, with a countdown and a Retry button
  * at most one error toast (no storm), no raw "Failed to fetch" text anywhere on screen
  * while down the page only probes GET /api/os/session (request rate drops to the probe rate)
  * a command that was streaming in the Terminal gets a clear "Connection lost" note and its input is held
  * after the server is started again the banner goes away within one probe interval, "Reconnected" shows,
    /api/os/today is fetched again (new data appears), windows are all still open, the terminal keeps its text
  * a proxy answering 502 raises the same banner, and clears when it answers again
  * ONE slow request on a live server (held past the 20 s request deadline) does not raise the banner: the deadline passing
    only asks the server once, and it answers
  * a server that is up but HUNG (the process is suspended: it accepts connections and never answers) raises the same banner
    within ~35 s (20 s request deadline + 4 s probe), a streaming Terminal command says "Connection lost", polling stops, and
    resuming the process clears it ("Reconnected", no restart note), the terminal works again
  * zero uncaught page errors / unhandled rejections (browser-level "Failed to load resource" lines for the dead
    port are counted separately: Chromium prints one for every refused request, nothing the page can suppress)

  python tests/e2e/os_connection.py --port 7406 --data C:\\scratch\\data --out C:\\scratch\\shots
Needs `pip install playwright` and Microsoft Edge (or --channel chromium). Pass --skip-hang to leave out the two slow phases (~100 s).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, name: str, detail: str = "") -> bool:
    RESULTS.append((bool(ok), name))
    print(f"{'ok  ' if ok else 'FAIL'} {name}" + (f"   [{detail}]" if detail else ""), flush=True)
    return bool(ok)


# ------------------------------------------------------------------------------------------------ server control
def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def listening_pids(port: int) -> list[int]:
    out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True).stdout
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3] == "LISTENING" and parts[1].endswith(f":{port}"):
            pids.add(int(parts[4]))
    return sorted(pids)


class Server:
    def __init__(self, port: int, data: Path, log: Path):
        self.port, self.data, self.log = port, data, log
        self.proc: subprocess.Popen | None = None

    def start(self, timeout: float = 90) -> float:
        env = dict(os.environ, APP_PORT=str(self.port), ODYSSEUS_DATA_DIR=str(self.data), PYTHONUTF8="1")
        py = ROOT / "venv" / "Scripts" / "python.exe"
        self.data.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        self.proc = subprocess.Popen([str(py), "app.py"], cwd=ROOT, env=env, stdout=open(self.log, "ab"), stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
        while time.time() - t0 < timeout:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/os/boot", timeout=2) as r:
                    if r.status == 200 and json.loads(r.read()).get("ready"):
                        return time.time() - t0
            except Exception:
                pass
            time.sleep(0.4)
        raise RuntimeError(f"server on {self.port} did not become ready in {timeout}s, see {self.log}")

    def kill(self) -> list[int]:
        pids = listening_pids(self.port)
        for pid in pids:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        if self.proc:
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
        t0 = time.time()
        while port_open(self.port) and time.time() - t0 < 10:
            time.sleep(0.2)
        return pids


def _signal_process(pid: int, stop: bool) -> None:
    """Freeze / thaw a whole process: the kernel keeps accepting connections for it, it just never answers (a hung server)."""
    if sys.platform == "win32":
        h = ctypes.windll.kernel32.OpenProcess(0x0800, False, pid)       # PROCESS_SUSPEND_RESUME
        if not h:
            raise OSError(f"cannot open process {pid}")
        try:
            (ctypes.windll.ntdll.NtSuspendProcess if stop else ctypes.windll.ntdll.NtResumeProcess)(h)
        finally:
            ctypes.windll.kernel32.CloseHandle(h)
    else:
        import signal
        os.kill(pid, signal.SIGSTOP if stop else signal.SIGCONT)


def http(port: int, path: str, body=None, method=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method=method or ("POST" if body is not None else "GET"))
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read() or b"null")


# ------------------------------------------------------------------------------------------------------- the test
TOAST_PROBE = """
(() => {
  window.__toasts = [];
  const seen = new WeakSet();
  const scan = () => document.querySelectorAll('.toast').forEach((el) => {
    if (seen.has(el)) return; seen.add(el);
    window.__toasts.push({ t: performance.now(), text: el.textContent.trim(), error: el.classList.contains('toast-error') });
  });
  new MutationObserver(scan).observe(document, { childList: true, subtree: true });
})();
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7406)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--channel", default="msedge")
    ap.add_argument("--skip-hang", action="store_true", help="skip the slow-request and hung-server phases")
    ap.add_argument("--down-seconds", type=float, default=24, help="how long the server stays dead (the request-rate window)")
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    port = args.port
    base = f"http://127.0.0.1:{port}"
    srv = Server(port, Path(args.data), out / "server.log")
    print(f"starting scratch server on {port} ...", flush=True)
    print(f"  ready in {srv.start():.1f}s", flush=True)

    errors: list[str] = []          # uncaught page errors + non-resource console errors
    resource_noise = 0              # "Failed to load resource" lines Chromium prints for refused requests
    reqs: list[tuple[float, str, str]] = []
    bad_http: list[str] = []
    t_zero = time.time()

    try:
        http(port, "/api/os/capture/commit", {"kind": "todo", "draft": {"text": "Water the plants"}, "tz_offset": 0})
        http(port, "/api/os/capture/commit", {"kind": "todo", "draft": {"text": "Renew passport"}, "tz_offset": 0})
        with sync_playwright() as p:
            browser = p.chromium.launch(channel=args.channel, headless=True)
            ctx = browser.new_context(viewport={"width": 1280, "height": 800}, color_scheme="light")
            ctx.add_init_script(TOAST_PROBE)
            page = ctx.new_page()

            def on_console(m):
                nonlocal resource_noise
                if m.type != "error":
                    return
                if re.search(r"Failed to load resource|net::ERR_", m.text):
                    resource_noise += 1
                else:
                    errors.append(f"console: {m.text}")
            page.on("console", on_console)
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.on("request", lambda r: reqs.append((time.time(), r.method, re.sub(r"^https?://[^/]+", "", r.url))))
            page.on("response", lambda r: bad_http.append(f"{r.status} {r.url}") if r.status >= 400 and time.time() > 0 else None)

            # ---------------------------------------------------------------- 1. a working desktop with several windows
            page.goto(f"{base}/os")
            page.locator(".dash").wait_for(timeout=30000)
            page.locator(".tw-todos .tw-body, [data-widget=todos]").first.wait_for(timeout=15000)
            page.get_by_text("Water the plants").first.wait_for(timeout=15000)
            for app in ("terminal", "taskmgr", "automations", "files"):
                page.locator(f'.dock-item[data-app="{app}"]').click()
                page.wait_for_timeout(500)
            n_windows = page.locator("#windows .win").count()
            check(n_windows >= 4, "several windows are open before the outage", str(n_windows))
            term = page.locator(".term").first
            term_in = term.locator(".term-input")
            term_in.fill("echo before-the-outage")
            term_in.press("Enter")
            page.get_by_text("before-the-outage").last.wait_for(timeout=15000)
            term_in.fill("ping -n 60 127.0.0.1")
            term_in.press("Enter")
            page.get_by_text("Reply from 127.0.0.1").first.wait_for(timeout=20000)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(out / "01_before_outage.png"))
            before = [r for r in reqs if r[0] > time.time() - 10]
            print(f"  requests in the 10 s before the outage: {len(before)}", flush=True)

            # ------------------------------------------------------------------------------- 2. the server dies
            t_kill = time.time()
            toasts_before = page.evaluate("window.__toasts.length")
            pids = srv.kill()
            print(f"  killed listener PID(s) {pids}", flush=True)
            check(bool(pids) and not port_open(port), "the scratch server is really gone")
            try:
                page.locator("[data-net-banner]:not([hidden])").wait_for(timeout=9000)
                t_banner = time.time() - t_kill
            except Exception:
                t_banner = 99
            check(t_banner <= 5.5, "the banner appears within ~5 s", f"{t_banner:.1f}s")
            banner = page.locator("[data-net-banner]")
            check("isn’t responding" in banner.inner_text() or "isn't responding" in banner.inner_text(), "banner text", banner.inner_text().replace("\n", " | "))
            check(page.locator("[data-net-banner] .net-retry").is_visible(), "Retry now button is there")
            page.wait_for_timeout(1200)
            eta1 = banner.locator(".net-eta").inner_text()
            page.wait_for_timeout(1100)
            eta2 = banner.locator(".net-eta").inner_text()
            check(eta1 != eta2 and re.search(r"\d", eta1 + eta2) is not None, "the countdown is live", f"{eta1!r} -> {eta2!r}")
            page.screenshot(path=str(out / "02_banner_light.png"))
            page.emulate_media(color_scheme="dark")
            page.wait_for_timeout(300)
            page.screenshot(path=str(out / "03_banner_dark.png"))
            page.screenshot(path=str(out / "03b_banner_dark_crop.png"), clip={"x": 240, "y": 0, "width": 800, "height": 140})
            page.emulate_media(color_scheme="light")

            # terminal: a clear note, input held, nothing raw
            check(page.get_by_text("Connection lost").first.is_visible(), "the streaming terminal says 'Connection lost'")
            check(term_in.evaluate("e => e.readOnly") is True, "terminal input is held while offline", (term_in.get_attribute("placeholder") or ""))

            # request rate while the server is dead
            t_win0 = time.time()
            page.wait_for_timeout(int(args.down_seconds * 1000))
            window = [r for r in reqs if r[0] >= t_win0]
            api = [r for r in window if r[2].startswith("/api/")]
            non_probe = [r for r in api if not r[2].startswith("/api/os/session")]
            print(f"  during {args.down_seconds:.0f}s down: {len(api)} api requests, {len(non_probe)} not the probe: {sorted(set(r[2] for r in non_probe))[:6]}", flush=True)
            check(len(non_probe) == 0, "no polling while offline (only the session probe goes out)")
            check(len(api) <= 7, "probe rate is backed off", f"{len(api)} probes in {args.down_seconds:.0f}s")
            toast_log = page.evaluate("window.__toasts")
            new_toasts = toast_log[toasts_before:]
            errs = [t for t in new_toasts if t["error"]]
            check(len(new_toasts) <= 1 and len(errs) == 0, "no toast storm while offline", f"{len(new_toasts)} toasts: {[t['text'] for t in new_toasts]}")
            body = page.inner_text("body")
            check(not re.search(r"failed to fetch|networkerror|network error|load failed", body, re.I), "no raw 'Failed to fetch' text on screen")
            check(page.locator("#windows .win").count() == n_windows, "windows stay open while offline")
            check(page.locator(".tw-error, [data-state=error]").count() == 0, "no per-widget error states while offline")
            page.get_by_text("Water the plants").first.wait_for(timeout=2000)
            check(True, "last dashboard data stays visible")

            # Retry now: a real attempt, still offline
            page.locator("[data-net-banner] .net-retry").click()
            page.wait_for_timeout(300)
            check(page.locator("[data-net-banner]:not([hidden])").count() == 1, "Retry now while the server is dead keeps the banner")
            check(page.locator(".mb-pulse").inner_text().strip() == "", "the menu bar drops its stale CPU / RAM numbers")

            # what the Terminal window and the dashboard look like while offline
            page.locator('.dock-item[data-app="terminal"]').click()
            page.wait_for_timeout(400)
            page.screenshot(path=str(out / "02b_terminal_offline.png"))
            page.keyboard.press("Control+k")
            page.locator(".palette-input").fill("open today")
            page.keyboard.press("Enter")
            page.wait_for_timeout(900)
            page.screenshot(path=str(out / "02c_dashboard_offline.png"))
            # the person's own action fails while offline: one calm "didn't go through" note (not an error toast, not silence)
            n_before = page.evaluate("window.__toasts.length")
            todo_in = page.get_by_placeholder("Add a todo…")
            todo_in.fill("Typed while offline")
            todo_in.press("Enter")
            page.wait_for_timeout(900)
            mine = page.evaluate("window.__toasts")[n_before:]
            check(len(mine) == 1 and not mine[0]["error"] and "didn’t go through" in mine[0]["text"], "a user action that fails offline gets one calm note", str([t["text"] for t in mine]))
            page.screenshot(path=str(out / "02d_action_failed_offline.png"))
            todo_in.fill("")
            for app in ("terminal", "taskmgr", "automations", "files"):       # bring the windows back (dock click restores a minimised one)
                page.locator(f'.dock-item[data-app="{app}"]').click()
                page.wait_for_timeout(250)
            check(page.locator("#windows .win").count() == n_windows, "windows survive being minimised and restored while offline")

            # ------------------------------------------------------------------------------ 3. the server comes back
            print("restarting scratch server ...", flush=True)
            took = srv.start()
            t_up = time.time()
            http(port, "/api/os/capture/commit", {"kind": "todo", "draft": {"text": "Back online todo"}, "tz_offset": 0})
            reqs_mark = len(reqs)
            try:
                page.wait_for_selector("[data-net-banner]", state="hidden", timeout=20000)
                t_back = time.time() - t_up
            except Exception:
                t_back = 99
            check(t_back <= 17, "the banner disappears within one probe interval of the server answering", f"{t_back:.1f}s (server took {took:.0f}s to boot)")
            page.get_by_text("Reconnected").first.wait_for(timeout=4000)
            check(True, "'Reconnected' toast shown")
            check(any("restarted" in t["text"] for t in page.evaluate("window.__toasts")), "a new server process is recognised: 'Reconnected, Odysseus restarted'")
            page.get_by_text("Back online todo").first.wait_for(timeout=8000)
            check(True, "the dashboard refreshed (a todo created while it was away appears)")
            after = reqs[reqs_mark:]
            check(any(r[2].startswith("/api/os/today") for r in after), "GET /api/os/today was fetched again after reconnecting")
            check(page.locator("#windows .win").count() == n_windows, "all windows are still open after reconnecting", str(page.locator("#windows .win").count()))
            check("before-the-outage" in page.locator(".term-out").first.inner_text(), "the terminal kept its text")
            check(term_in.evaluate("e => e.readOnly") is False, "terminal input is usable again")
            check(page.get_by_text("Reconnected.").count() >= 1, "terminal notes the reconnect")
            term_in.fill("echo after-the-outage")
            term_in.press("Enter")
            page.get_by_text("after-the-outage").last.wait_for(timeout=15000)
            check(True, "a new command runs after reconnecting")
            page.wait_for_timeout(2500)
            page.screenshot(path=str(out / "04_after_reconnect.png"))
            tm_rows = page.locator(".tm-table tbody tr").count()
            check(tm_rows > 0, "Task Manager lists processes again", str(tm_rows))
            all_toasts = page.evaluate("window.__toasts")
            check(not any(t["error"] for t in all_toasts), "no error toast during the whole outage", str([t["text"] for t in all_toasts if t["error"]]))

            # ------------------------------------- 4. a proxy in front answers 502 (the server process itself is fine)
            gw_mark = len(bad_http)
            toasts_mark = len(all_toasts)
            page.route("**/api/**", lambda route: route.fulfill(status=502, content_type="text/html", body="<h1>502 Bad Gateway</h1>"))
            page.locator('.dock-item[data-app="taskmgr"]').click()          # make something poll against the broken proxy
            try:
                page.locator("[data-net-banner]:not([hidden])").wait_for(timeout=9000)
                gw_ok = True
            except Exception:
                gw_ok = False
            check(gw_ok, "502 pages from a proxy raise the same banner")
            page.wait_for_timeout(3000)
            page.screenshot(path=str(out / "05_proxy_502.png"))
            page.unroute("**/api/**")
            page.locator("[data-net-banner] .net-retry").click()
            try:
                page.wait_for_selector("[data-net-banner]", state="hidden", timeout=20000)
                gw_back = True
            except Exception:
                gw_back = False
            check(gw_back, "and clears again when the proxy answers")
            page.wait_for_timeout(800)
            gw_toasts = page.evaluate("window.__toasts")[toasts_mark:]
            check(not any(t["error"] for t in gw_toasts), "no error toast during the 502 outage", str([t["text"] for t in gw_toasts]))
            check(any(t["text"] == "Reconnected" for t in gw_toasts), "same server back: plain 'Reconnected' (no restart note)")
            del bad_http[gw_mark:]            # the 502s above were injected on purpose

            if not args.skip_hang:
                # ------------------------- 5. one slow request on a live server: no banner (the deadline only asks, the server answers)
                held: list = []

                def hold_first(route):
                    if not held and "/api/os/system" in route.request.url:
                        held.append(route)              # never answered: this one request hangs while everything else works
                    else:
                        route.continue_()
                page.route("**/api/os/*", hold_first)
                toasts_mark = len(page.evaluate("window.__toasts"))
                sess_mark = len([r for r in reqs if r[2].startswith("/api/os/session")])
                t_hold = time.time()
                for _ in range(40):
                    if held:
                        break
                    page.wait_for_timeout(500)
                check(bool(held), "a request is being held (the menu bar system sample)")
                page.wait_for_timeout(24000)           # past the 20 s deadline
                check(page.locator("[data-net-banner]:not([hidden])").count() == 0, "one request past its deadline on a live server raises NO banner", f"{time.time() - t_hold:.0f}s in")
                check(page.evaluate("document.documentElement.dataset.net || ''") == "", "the desktop never entered the offline state")
                probes = len([r for r in reqs if r[2].startswith("/api/os/session")]) - sess_mark
                check(1 <= probes <= 3, "the deadline made the desktop ask the server once or twice", f"{probes} /api/os/session probe(s)")
                slow_toasts = page.evaluate("window.__toasts")[toasts_mark:]
                check(not any("responding" in t["text"] for t in slow_toasts), "and no 'not responding' note", str([t["text"] for t in slow_toasts]))
                page.unroute_all(behavior="ignoreErrors")       # the held request was given up on by the page long ago

                # ------------------------------------------ 6. a HUNG server: up, accepting connections, answering nothing
                term_in.fill("ping -n 120 127.0.0.1")
                term_in.press("Enter")
                page.get_by_text("Reply from 127.0.0.1").last.wait_for(timeout=20000)
                page.wait_for_timeout(1500)
                pids = listening_pids(port)
                check(bool(pids), "found the listening server process", str(pids))
                toasts_mark = len(page.evaluate("window.__toasts"))
                for pid in pids:
                    _signal_process(pid, True)
                t_hang = time.time()
                try:
                    check(port_open(port), "the hung server still accepts connections (so this is not a refusal)")
                    try:
                        page.locator("[data-net-banner]:not([hidden])").wait_for(timeout=50000)
                        t_hang_banner = time.time() - t_hang
                    except Exception:
                        t_hang_banner = 99
                    check(t_hang_banner <= 35, "a hung server raises the banner within ~35 s", f"{t_hang_banner:.1f}s")
                    banner = page.locator("[data-net-banner]")
                    check("responding" in banner.inner_text(), "same banner text as for a dead server", banner.inner_text().replace("\n", " | "))
                    page.screenshot(path=str(out / "06_hung_banner.png"))
                    try:
                        page.get_by_text("Connection lost").last.wait_for(timeout=30000)
                        lost_ok = True
                    except Exception:
                        lost_ok = False
                    check(lost_ok, "the streaming Terminal command says 'Connection lost'", f"{time.time() - t_hang:.0f}s after the hang")
                    check(term_in.evaluate("e => e.readOnly") is True, "terminal input is held while the server is hung")
                    mark = len(reqs)
                    page.wait_for_timeout(18000)
                    api_hung = [r for r in reqs[mark:] if r[2].startswith("/api/")]
                    other_hung = [r for r in api_hung if not r[2].startswith("/api/os/session")]
                    check(len(other_hung) == 0, "no polling while it is hung (only the session probe)", f"{len(api_hung)} api requests, others: {sorted(set(r[2] for r in other_hung))[:4]}")
                    body = page.inner_text("body")
                    check(not re.search(r"failed to fetch|networkerror|network error|load failed|took too long", body, re.I), "no raw network text on screen")
                    hung_toasts = page.evaluate("window.__toasts")[toasts_mark:]
                    check(not any(t["error"] for t in hung_toasts) and len(hung_toasts) <= 1, "no toast storm while hung", str([t["text"] for t in hung_toasts]))
                    check(page.locator("#windows .win").count() == n_windows, "windows stay open while the server is hung")
                finally:
                    for pid in pids:
                        try:
                            _signal_process(pid, False)
                        except OSError:
                            pass
                t_thaw = time.time()
                try:
                    page.wait_for_selector("[data-net-banner]", state="hidden", timeout=25000)
                    t_thaw_back = time.time() - t_thaw
                except Exception:
                    t_thaw_back = 99
                check(t_thaw_back <= 17, "the banner clears within one probe interval of the server answering again", f"{t_thaw_back:.1f}s")
                recon = [t["text"] for t in page.evaluate("window.__toasts")[toasts_mark:]]
                check("Reconnected" in recon, "plain 'Reconnected' (same server process: no restart note)", str(recon))
                check(not any("restarted" in t for t in recon), "and not 'Odysseus restarted'")
                page.wait_for_timeout(1200)
                check(term_in.evaluate("e => e.readOnly") is False, "terminal input is usable again")
                term_in.fill("echo after-the-hang")
                term_in.press("Enter")
                page.get_by_text("after-the-hang").last.wait_for(timeout=20000)
                check(True, "a new command runs after the server is thawed")
                page.wait_for_timeout(1500)
                page.screenshot(path=str(out / "07_after_hang.png"))
                check(page.locator(".tm-table tbody tr").count() > 0, "Task Manager lists processes again")
                check(page.locator("#windows .win").count() == n_windows, "all windows are still open after the hang")
            browser.close()
    finally:
        try:
            for pid in listening_pids(port):
                _signal_process(pid, False)            # never leave the scratch server frozen
        except Exception:
            pass
        srv.kill()

    check(not errors, "zero uncaught page errors / unhandled rejections / non-resource console errors", "; ".join(errors[:4]))
    print(f"  browser 'Failed to load resource' lines for the dead port: {resource_noise} (Chromium prints these itself)", flush=True)
    http_bad = [b for b in bad_http if "ERR" not in b]
    check(not [b for b in http_bad if not b.startswith("503")], "no HTTP >= 400 responses", "; ".join(http_bad[:4]))
    failed = [n for ok, n in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed in {time.time() - t_zero:.0f}s", flush=True)
    (out / "result.json").write_text(json.dumps({"results": RESULTS, "errors": errors, "resource_noise": resource_noise}, indent=1))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
