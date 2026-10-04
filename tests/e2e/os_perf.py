"""Efficiency and "is it really live, but not wasteful" numbers for Odysseus OS. NOT collected by pytest (no ``test_`` prefix).

    python tests/e2e/os_perf.py --url http://127.0.0.1:7405/os --out C:\\scratch\\perf [--idle-seconds 60] [--cycles 5]

Measures, in a real Edge against a real server (use a scratch data dir):

1. time from navigation to the desktop and to a dashboard with real data, and how many module requests the boot makes;
2. ``GET /api/os/today`` latency (p50 / p95 / max over 20 calls);
3. requests per minute: the idle desktop, every app open, every window minimised, every window minimised for over a minute (the
   embedded pages are put to sleep then and must stop polling; ``--no-suspend`` switches that off to measure the old behaviour), and
   the tab hidden. The shell's own endpoints (``/api/os/*``, ``/api/tasks/runs/recent``) are counted apart from what the embedded
   Odysseus pages poll for themselves;
4. leaks: open + close every app N times and compare the page's live timers (intervals / timeouts), window/document listeners
   and JS heap before and after;
5. event-loop responsiveness: ``GET /api/os/session`` is probed every 250 ms for the whole run (a blocked server loop shows up as
   a slow probe).

Exit code 1 if a budget is exceeded (idle desktop > 40 shell requests/min, minimised > idle, tab hidden > 2/min, a window asleep that
still polls (> 6 embedded requests/min) or not woken at the same address, any leaked interval or listener, probe max > 1.5 s).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from _os_e2e import Desk, UPSTREAM_ALLOW, http_json, origin_of  # noqa: E402

SHELL_RE = r"^(GET|POST|PUT|DELETE) /api/(os/|tasks/runs/recent)"
EMBEDDED = ["chat", "notes", "documents", "email", "calendar", "tasks", "memory", "gallery", "cookbook"]
NATIVE = ["jarvis", "files", "terminal", "taskmgr", "automations", "settings"]


class Probe(threading.Thread):
    """Samples GET /api/os/session every 250 ms from outside the browser."""

    def __init__(self, base: str):
        super().__init__(daemon=True)
        self.base, self.samples, self.stop_flag = base, [], threading.Event()

    def run(self) -> None:
        import urllib.request

        while not self.stop_flag.is_set():
            t0 = time.perf_counter()
            try:
                urllib.request.urlopen(urllib.request.Request(self.base + "/api/os/session"), timeout=10).read()
                self.samples.append((time.time(), (time.perf_counter() - t0) * 1000))
            except Exception:
                self.samples.append((time.time(), 10000.0))
            self.stop_flag.wait(0.25)

    def stats(self) -> Dict[str, Any]:
        v = sorted(x[1] for x in self.samples)
        if not v:
            return {}
        return dict(n=len(v), p50_ms=round(statistics.median(v), 1), p95_ms=round(v[int(len(v) * 0.95) - 1], 1), max_ms=round(v[-1], 1), over_500ms=sum(1 for x in v if x > 500))


def probe_state(d: Desk) -> Dict[str, int]:
    return d.page.evaluate("""() => { const q = window.__qa; return { intervals: q.intervals.size, timeouts: q.timeouts.size, listeners: q.listeners.size,
        heap: (performance.memory && performance.memory.usedJSHeapSize) || 0, nodes: document.getElementsByTagName('*').length }; }""")


def rpm(d: Desk, seconds: float, label: str, res: Dict[str, Any]) -> None:
    before = dict(d.rec.api_counts)
    t0 = time.time()
    d.page.wait_for_timeout(int(seconds * 1000))
    dt = time.time() - t0
    delta = {k: v - before.get(k, 0) for k, v in d.rec.api_counts.items() if v - before.get(k, 0) > 0}
    import re

    shell = {k: v for k, v in delta.items() if re.match(SHELL_RE, k)}
    other = {k: v for k, v in delta.items() if k not in shell and "/static/" not in k}
    res[label] = dict(seconds=round(dt), shell_per_min=round(sum(shell.values()) * 60 / dt, 1), other_per_min=round(sum(other.values()) * 60 / dt, 1),
                      shell=dict(sorted(shell.items(), key=lambda kv: -kv[1])), other=dict(sorted(other.items(), key=lambda kv: -kv[1])[:8]))
    print(f"  {label:<22} shell {res[label]['shell_per_min']:>6}/min   embedded pages {res[label]['other_per_min']:>6}/min", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://127.0.0.1:7000/os")
    ap.add_argument("--out", default="perf_out")
    ap.add_argument("--idle-seconds", type=float, default=60)
    ap.add_argument("--cycles", type=int, default=5)
    ap.add_argument("--channel", default="msedge")
    ap.add_argument("--server-log", default="")
    ap.add_argument("--no-suspend", action="store_true", help="turn the sleeping of hidden embedded pages off (to measure the old behaviour)")
    args = ap.parse_args()
    base = origin_of(args.url)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    res: Dict[str, Any] = dict(url=args.url, started=time.strftime("%Y-%m-%d %H:%M:%S"))
    failures: List[str] = []

    status, saved = http_json(base, "GET", "/api/os/session")
    if status == 200 and (saved or {}).get("session"):
        http_json(base, "PUT", "/api/os/session", dict(saved["session"], windows=[]))

    # ---- 2. /api/os/today latency (server side, no browser)
    import urllib.request

    lat = []
    for _ in range(20):
        t0 = time.perf_counter()
        urllib.request.urlopen(urllib.request.Request(base + "/api/os/today?tz_offset=0"), timeout=30).read()
        lat.append((time.perf_counter() - t0) * 1000)
    lat.sort()
    res["today_latency_ms"] = dict(p50=round(statistics.median(lat), 1), p95=round(lat[18], 1), max=round(lat[-1], 1))
    print(f"/api/os/today latency: p50 {res['today_latency_ms']['p50']} ms, p95 {res['today_latency_ms']['p95']} ms, max {res['today_latency_ms']['max']} ms", flush=True)

    probe = Probe(base)
    probe.start()
    with sync_playwright() as p:
        d = Desk(p, args.url, channel=args.channel, server_log=Path(args.server_log) if args.server_log else None, allow=UPSTREAM_ALLOW)
        if args.no_suspend:
            d.ctx.add_init_script("try { localStorage.setItem('os.embedSuspendMs', '99999999'); } catch (e) {}")
        res["embedded_pages_sleep"] = not args.no_suspend
        # ---- 1. boot
        t0 = time.time()
        d.page.goto(args.url, wait_until="domcontentloaded")
        d.page.locator("#desktop:not([hidden])").wait_for(timeout=30000)
        t_desktop = time.time() - t0
        for _ in range(200):
            if d.page.locator(".dash-summary").inner_text().strip() not in ("", "What would you like to do?"):
                break
            d.page.wait_for_timeout(50)
        t_data = time.time() - t0
        mods = sum(v for k, v in d.rec.api_counts.items() if "/static/os/js/" in k)
        nav = d.page.evaluate("""() => { const n = performance.getEntriesByType('navigation')[0]; const r = performance.getEntriesByType('resource');
            return { dcl: Math.round(n.domContentLoadedEventEnd), load: Math.round(n.loadEventEnd), resources: r.length, kb: Math.round(r.reduce((a, x) => a + (x.transferSize || 0), 0) / 1024) }; }""")
        res["boot"] = dict(desktop_s=round(t_desktop, 2), dashboard_with_data_s=round(t_data, 2), os_module_requests=mods, **nav)
        print(f"boot: desktop {t_desktop:.2f}s, dashboard with data {t_data:.2f}s, {mods} module requests, {nav['resources']} resources, {nav['kb']} KB", flush=True)
        d.settle(1500)
        d.close_all_windows()

        # ---- 3. requests per minute
        rpm_res: Dict[str, Any] = {}
        rpm(d, args.idle_seconds, "idle desktop", rpm_res)
        for a in NATIVE + EMBEDDED:
            d.open_app(a)
            d.page.wait_for_timeout(400)
        d.settle(3000)
        rpm(d, args.idle_seconds, "every app open", rpm_res)
        # a place to come back to: a #hash inside a page that stays on the same document
        d.page.evaluate("() => { const f = document.querySelector('section.win[data-app=notes] iframe.embed-frame'); if (f) f.contentWindow.location.hash = '#qa-place'; }")
        d.os_eval("(os) => os.wm.list().forEach((w) => w.minimize())")
        t_min = time.time()
        d.settle(2500)
        rpm(d, min(args.idle_seconds, 40), "all minimised", rpm_res)
        # ...and the same windows once they have been hidden for over a minute: the embedded pages must be asleep, not polling
        d.page.wait_for_timeout(max(0, int((68 - (time.time() - t_min)) * 1000)))
        asleep = d.page.locator(".embed[data-suspended]").count()
        frames_while_asleep = d.page.locator("iframe.embed-frame").count()
        rpm(d, min(args.idle_seconds, 40), "minimised > 1 min", rpm_res)
        rpm_res["minimised > 1 min"]["asleep_windows"] = asleep
        print(f"  windows asleep: {asleep} of {len(EMBEDDED)} (iframes alive: {frames_while_asleep})", flush=True)
        if not args.no_suspend:
            if asleep != len(EMBEDDED) or frames_while_asleep != 0:
                failures.append(f"after a minute hidden {asleep} of {len(EMBEDDED)} embedded windows were asleep, {frames_while_asleep} iframes still alive")
            if rpm_res["minimised > 1 min"]["other_per_min"] > 6:
                failures.append(f"asleep windows still make {rpm_res['minimised > 1 min']['other_per_min']} embedded-page requests/min (> 6)")
        # waking: each window brings its page back at the address it was left at
        d.os_eval("(os) => os.wm.list().forEach((w) => os.wm.restore(w))")
        d.page.locator("iframe.embed-frame").nth(len(EMBEDDED) - 1).wait_for(timeout=10000)
        d.settle(3500)
        woke = d.page.locator("iframe.embed-frame").count()
        still_asleep = d.page.locator(".embed[data-suspended]").count()
        place = d.page.evaluate("() => { const f = document.querySelector('section.win[data-app=notes] iframe.embed-frame'); try { return f.contentWindow.location.pathname + f.contentWindow.location.hash; } catch (e) { return String(e); } }")
        rpm_res["wake"] = dict(frames=woke, still_asleep=still_asleep, notes_place=place)
        print(f"  woken: {woke} iframes, {still_asleep} still asleep, notes frame at {place}", flush=True)
        if not args.no_suspend and (woke != len(EMBEDDED) or still_asleep or place != "/notes#qa-place"):
            failures.append(f"waking the windows: {woke} iframes, {still_asleep} still asleep, notes at {place!r} (want /notes#qa-place)")
        d.close_all_windows()
        d.page.evaluate("Object.defineProperty(document, 'hidden', { configurable: true, get: () => true }); document.dispatchEvent(new Event('visibilitychange'))")
        d.settle(1500)
        rpm(d, min(args.idle_seconds, 40), "tab hidden", rpm_res)
        d.page.evaluate("delete document.hidden; document.dispatchEvent(new Event('visibilitychange'))")
        res["requests_per_minute"] = rpm_res
        if rpm_res["idle desktop"]["shell_per_min"] > 40:
            failures.append(f"idle desktop makes {rpm_res['idle desktop']['shell_per_min']} shell requests/min (> 40)")
        # minimising every window shows the desktop again, so it should cost what the idle desktop costs (no more): the windows' own timers stop
        if rpm_res["all minimised"]["shell_per_min"] > rpm_res["idle desktop"]["shell_per_min"] * 1.25 + 3:
            failures.append(f"all minimised: {rpm_res['all minimised']['shell_per_min']} shell requests/min vs idle {rpm_res['idle desktop']['shell_per_min']}: {list(rpm_res['all minimised']['shell'])[:3]}")
        if rpm_res["tab hidden"]["shell_per_min"] > 2:
            failures.append(f"tab hidden: {rpm_res['tab hidden']['shell_per_min']} shell requests/min (> 2): {list(rpm_res['tab hidden']['shell'])[:3]}")

        # ---- 4. leaks
        d.settle(1000)
        base_state = probe_state(d)
        leaks: Dict[str, Any] = {}
        for a in NATIVE + EMBEDDED:
            d.open_app(a)
            d.page.wait_for_timeout(700 if a in EMBEDDED else 350)
            d.close_all_windows()
            d.settle(400)
        warm = probe_state(d)                       # first open/close warms lazy singletons: the baseline is taken after one round
        for a in NATIVE + EMBEDDED:
            before = probe_state(d)
            for _ in range(args.cycles):
                d.open_app(a)
                d.page.wait_for_timeout(700 if a in EMBEDDED else 350)
                d.close_all_windows()
                d.page.wait_for_timeout(250)
            d.settle(1200)
            after = probe_state(d)
            leaks[a] = {k: after[k] - before[k] for k in ("intervals", "timeouts", "listeners", "nodes")} | {"heap_kb": round((after["heap"] - before["heap"]) / 1024)}
            bad = [k for k in ("intervals", "listeners") if leaks[a][k] > 0]
            print(f"  leak check {a:<12} intervals {leaks[a]['intervals']:+d}  listeners {leaks[a]['listeners']:+d}  timeouts {leaks[a]['timeouts']:+d}  nodes {leaks[a]['nodes']:+d}  heap {leaks[a]['heap_kb']:+d} KB", flush=True)
            if bad:
                failures.append(f"{a}: leaked {', '.join(f'{k} {leaks[a][k]:+d}' for k in bad)} after {args.cycles} open/close cycles")
        res["leaks"] = leaks
        res["state_baseline"], res["state_warm"], res["state_end"] = base_state, warm, probe_state(d)
        res["browser_problems"] = [x for x in d.rec.problems if x["kind"] != "teardown"]
        res["server_errors"] = d.rec.server_errors()
        d.close()
    probe.stop_flag.set()
    probe.join(2)
    res["event_loop_probe"] = probe.stats()
    print("event loop probe:", res["event_loop_probe"], flush=True)
    if res["event_loop_probe"].get("max_ms", 0) > 1500:
        failures.append(f"server event loop stalled: probe max {res['event_loop_probe']['max_ms']} ms")
    res["failures"] = failures
    (out / "perf_report.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print("\nbrowser problems:", len(res["browser_problems"]), " server log errors:", len(res["server_errors"]))
    for f in failures:
        print("FAIL", f)
    print("OK" if not failures else f"{len(failures)} budget(s) exceeded")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
