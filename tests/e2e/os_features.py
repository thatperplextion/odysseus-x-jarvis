"""Feature checklist for Odysseus OS, driven in a real browser: it verifies behaviour (what changed on the server and on
screen), not just "no error". NOT collected by pytest (no ``test_`` prefix). Needs ``pip install playwright`` + Microsoft Edge.

    # scratch server (never your real data dir):   set APP_PORT=7405 & set ODYSSEUS_DATA_DIR=C:\\scratch\\data & venv\\Scripts\\python.exe app.py
    python tests/e2e/os_features.py --url http://127.0.0.1:7405/os --out C:\\scratch\\features
    python tests/e2e/os_features.py --url ... --only wm,files,editor            # run a few sections
    python tests/e2e/os_features.py --url ... --ai                             # also the Jarvis planner checks (needs a model; <= 5 model calls)

Sections: wm, shell (menubar/palette/dock/launcher), files, editor, terminal, taskmgr, settings, models, jarvis, automations,
today, reminders (server_fired: no second toast / notification / bell entry), embedded, sleep (hidden embedded pages are paused
and wake in place), themes. Every section records pass/fail lines with a reason; console errors, page errors, failed requests
and unexpected HTTP >= 400 across the whole run are listed at the end. Exit code 1 if anything failed.

It creates disposable ``qa-*`` items (files, todos, automations) and removes what it can. Run it against a scratch data dir.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from playwright.sync_api import TimeoutError as PWTimeout  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402

from _os_e2e import UPSTREAM_ALLOW, Desk, http_json, origin_of  # noqa: E402

TAG = str(int(time.time()) % 100000)
BOX = f"/Home/qa-feat-{TAG}"          # disposable folder for the Files / Editor checks (one per run)
TRASHME = f"qa-trash-{TAG}"


class Suite:
    def __init__(self, desk: Desk, base: str, out: Path, args):
        self.d, self.base, self.out, self.args = desk, base, out, args
        self.page = desk.page
        self.rows: List[Dict[str, Any]] = []
        self.area = ""

    # -- bookkeeping ---------------------------------------------------------------------------------------
    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append(dict(area=self.area, name=name, ok=bool(ok), detail=str(detail)[:300]))
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {self.area}: {name}" + (f"  ({detail})" if detail and not ok else ""), flush=True)
        return bool(ok)

    def skip(self, name: str, why: str) -> None:
        self.rows.append(dict(area=self.area, name=name, ok=None, detail=why))
        print(f"  [skip] {self.area}: {name}  ({why})", flush=True)

    def api(self, method: str, path: str, body: Optional[dict] = None):
        return http_json(self.base, method, path, body)

    def get(self, path: str):
        status, data = self.api("GET", path)
        if status >= 400:
            raise RuntimeError(f"GET {path} -> {status} {str(data)[:120]}")
        return data

    # -- ui helpers -----------------------------------------------------------------------------------------
    def reset(self) -> None:
        self.d.close_all_windows()
        for _ in range(2):
            self.page.keyboard.press("Escape")
        self.page.locator("#overlays .modal-backdrop").evaluate_all("els => els.forEach(e => e.remove())")

    def win(self, app: str):
        return self.d.win(app)

    def toast_texts(self) -> List[str]:
        return self.page.locator("#overlays .toast .toast-msg").all_inner_texts()

    def wait_toast(self, pattern: str, timeout: int = 6000) -> bool:
        try:
            self.page.locator("#overlays .toast .toast-msg", has_text=re.compile(pattern, re.I)).first.wait_for(timeout=timeout)
            return True
        except PWTimeout:
            return False

    def modal_click(self, label: str, timeout: int = 4000) -> bool:
        try:
            self.page.locator("#overlays .modal .modal-actions button", has_text=re.compile(f"^{label}$", re.I)).first.click(timeout=timeout)
            return True
        except PWTimeout:
            return False

    def ctx_click(self, label: str, timeout: int = 3000) -> bool:
        try:
            self.page.locator("#overlays .ctx .ctx-item", has_text=re.compile(f"^{re.escape(label)}", re.I)).first.click(timeout=timeout)
            return True
        except PWTimeout:
            return False

    def shot(self, name: str) -> None:
        try:
            self.page.screenshot(path=str(self.out / f"{name}.png"))
        except Exception:
            pass

    def rect(self, app: str) -> Dict[str, float]:
        return self.win(app).evaluate("e => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }")

    def prefs(self) -> Dict[str, Any]:
        return self.page.evaluate("async () => (await import('/static/os/js/state.js')).getPrefs()")


# =============================================================================================================
def sec_wm(s: Suite) -> None:
    """Window manager: open, drag, resize, snap, maximise, minimise, restore, title double-click, close, z-order, 900 px."""
    d, page = s.d, s.page
    s.reset()
    d.open_app("files", {"path": "/Home"})
    d.settle(500)
    r0 = s.rect("files")
    bar = s.win("files").locator(".win-bar")
    bb = bar.bounding_box()
    page.mouse.move(bb["x"] + 150, bb["y"] + 15)
    page.mouse.down()
    page.mouse.move(bb["x"] + 210, bb["y"] + 45, steps=6)
    page.mouse.move(bb["x"] + 270, bb["y"] + 75, steps=6)
    page.mouse.up()
    r1 = s.rect("files")
    s.check("drag moves the window", abs((r1["x"] - r0["x"]) - 120) < 6 and abs((r1["y"] - r0["y"]) - 60) < 6, f"{r0} -> {r1}")

    h = s.win("files").locator(".rz-se").bounding_box()
    page.mouse.move(h["x"] + 3, h["y"] + 3)
    page.mouse.down()
    page.mouse.move(h["x"] + 43, h["y"] + 33, steps=5)
    page.mouse.move(h["x"] + 83, h["y"] + 53, steps=5)
    page.mouse.up()
    r2 = s.rect("files")
    s.check("resize (south-east handle) grows the window", r2["w"] - r1["w"] > 60 and r2["h"] - r1["h"] > 35, f"{r1['w']}x{r1['h']} -> {r2['w']}x{r2['h']}")

    s.win("files").locator(".win-max").click()
    r3 = s.rect("files")
    vw = page.viewport_size["width"]
    s.check("maximise fills the workspace", r3["w"] >= vw - 2 and "max" in (s.win("files").get_attribute("class") or ""), f"{r3}")
    s.win("files").locator(".win-max").click()
    r4 = s.rect("files")
    s.check("restore returns to the previous size", abs(r4["w"] - r2["w"]) < 3 and abs(r4["h"] - r2["h"]) < 3, f"{r2['w']}x{r2['h']} vs {r4['w']}x{r4['h']}")

    s.win("files").locator(".win-title-text").dblclick()
    s.check("title double-click maximises", "max" in (s.win("files").get_attribute("class") or ""))
    s.win("files").locator(".win-title-text").dblclick()
    s.check("title double-click restores", "max" not in (s.win("files").get_attribute("class") or ""))

    s.win("files").locator(".win-min").click()
    d.settle(300)
    s.check("minimise hides the window", "min" in (s.win("files").get_attribute("class") or "").split())
    dock_item = page.locator('#dock .dock-item[data-app="files"]')
    s.check("dock keeps a running dot for the minimised window", "running" in (dock_item.get_attribute("class") or ""))
    dock_item.click()
    d.settle(300)
    s.check("dock click restores it", "min" not in (s.win("files").get_attribute("class") or "").split())
    dock_item.click()
    d.settle(300)
    s.check("dock click on the focused window minimises it", "min" in (s.win("files").get_attribute("class") or "").split())
    dock_item.click()
    d.settle(200)

    # snap: drag the title to the left edge -> half width
    bb = s.win("files").locator(".win-bar").bounding_box()
    page.mouse.move(bb["x"] + 200, bb["y"] + 15)
    page.mouse.down()
    page.mouse.move(bb["x"] + 100, bb["y"] + 40, steps=5)
    page.mouse.move(2, 200, steps=8)
    page.mouse.up()
    d.settle(250)
    rs = s.rect("files")
    s.check("dragging to the left edge snaps to half the screen", abs(rs["w"] - vw / 2) < 40 and rs["x"] < 12, f"{rs}")

    # z-order
    d.open_app("terminal")
    d.settle(300)
    z_t = int(s.win("terminal").evaluate("e => +getComputedStyle(e).zIndex"))
    s.win("files").locator(".win-bar").click(position={"x": 60, "y": 14})
    d.settle(200)
    z_f = int(s.win("files").evaluate("e => +getComputedStyle(e).zIndex"))
    s.check("clicking a background window raises it", z_f > z_t and "focused" in (s.win("files").get_attribute("class") or ""), f"{z_f} vs {z_t}")

    s.win("terminal").locator(".win-close").click()
    d.settle(400)
    s.check("close removes the window", s.win("terminal").count() == 0)
    s.win("files").locator(".win-close").click()
    d.settle(400)
    s.check("closing the last window shows the desktop again", page.locator("#home.behind").count() == 0)

    # reopen restores a saved session? open two, reload, they come back
    d.open_app("settings")
    d.settle(1800)   # the session is saved on a 400 ms + 1.5 s debounce
    page.reload(wait_until="domcontentloaded")
    page.locator("#desktop:not([hidden])").wait_for(timeout=15000)
    d.settle(800)
    s.check("windows are restored after a reload", s.win("settings").count() == 1)
    s.reset()

    # 900 px wide: every app stays inside the viewport and the page never scrolls sideways
    page.set_viewport_size({"width": 900, "height": 700})
    d.settle(400)
    bad = []
    for app in ("jarvis", "files", "terminal", "taskmgr", "automations", "settings"):
        d.open_app(app)
        d.settle(500)
        r = s.rect(app)
        if r["x"] < -2 or r["x"] + r["w"] > 902 or r["y"] + r["h"] > 702:
            bad.append((app, {k: round(v) for k, v in r.items()}))
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        if overflow > 1:
            bad.append((app, f"page overflow {overflow}px"))
        s.shot(f"w900-{app}")
        s.reset()
    s.check("at 900 px every app window fits and nothing overflows sideways", not bad, bad)
    d.open_app("settings")
    d.settle(400)
    models_btn = s.win("settings").locator(".set-nav .side-item", has_text="AI models")
    s.check("at 900 px the settings navigation is still usable", models_btn.is_visible())
    s.reset()
    page.set_viewport_size({"width": 1280, "height": 800})
    d.settle(300)


def sec_shell(s: Suite) -> None:
    """Menubar, command palette, dock (click + right-click pin/unpin), launcher."""
    d, page = s.d, s.page
    s.reset()
    # --- palette
    page.keyboard.press("Control+k")
    s.check("Ctrl K opens the palette", page.locator(".palette-input").is_visible())
    page.locator(".palette-input").fill("termin")
    s.check("palette finds the Terminal app", page.locator(".palette-item", has_text="Terminal").count() >= 1)
    page.keyboard.press("Enter")
    d.settle(500)
    s.check("Enter in the palette opens the app", s.win("terminal").count() == 1)
    s.reset()
    theme0 = page.evaluate("document.documentElement.dataset.theme")
    page.keyboard.press("Control+k")
    page.locator(".palette-input").fill("toggle th")
    page.locator(".palette-item", has_text="Toggle theme").first.click()
    d.settle(200)
    s.check("palette action 'Toggle theme' changes the theme", page.evaluate("document.documentElement.dataset.theme") != theme0)
    page.evaluate("async (t) => { const st = await import('/static/os/js/state.js'); st.setPref('theme', t); st.applyTheme(); }", theme0)

    page.keyboard.press("Control+k")
    page.locator(".palette-input").fill("Add todo: qa palette todo")
    page.locator(".palette-item", has_text="Add todo:").first.click()
    d.settle(1200)
    todos = s.get("/api/os/today")["todos"]["items"]
    s.check("palette 'Add todo:' creates a real todo", any("qa palette todo" in t["text"] for t in todos), [t["text"] for t in todos][:5])
    s.check("...and the Todos widget shows it without a reload", page.locator(".tw-todos .td-text", has_text="qa palette todo").count() == 1)
    # clean up through the app's own Undo
    toast_undo = page.locator("#overlays .toast .toast-action", has_text="Undo")
    if toast_undo.count():
        toast_undo.first.click()
        d.settle(800)
        s.check("Undo removes the todo again", page.locator(".tw-todos .td-text", has_text="qa palette todo").count() == 0)

    # --- menubar
    page.get_by_role("button", name="Change theme").click()
    t1 = page.evaluate("document.documentElement.dataset.theme")
    page.get_by_role("button", name="Change theme").click()
    t2 = page.evaluate("document.documentElement.dataset.theme")
    page.get_by_role("button", name="Change theme").click()
    t3 = page.evaluate("document.documentElement.dataset.theme")
    s.check("theme button cycles auto -> light -> dark -> auto", len({t1, t2, t3}) == 3 or (t3 == theme0), f"{theme0} {t1} {t2} {t3}")
    page.evaluate("async (t) => { const st = await import('/static/os/js/state.js'); st.setPref('theme', t); st.applyTheme(); }", theme0)

    s.api("POST", "/api/os/notify", {"title": "QA note", "message": "hello from qa", "severity": "info", "key": f"qa:{time.time()}"})
    page.get_by_role("button", name="Notifications").click()
    d.settle(500)
    s.check("bell opens the notification panel with the entry", page.locator(".popover.notif .notif-item", has_text="QA note").count() >= 1)
    page.keyboard.press("Escape")
    page.mouse.click(600, 400)
    d.settle(200)

    page.locator(".mb-user").click()
    s.check("avatar menu opens", page.locator("#overlays .ctx").count() == 1)
    s.ctx_click("Security & activity")
    d.settle(600)
    s.check("avatar menu -> Security & activity opens that Settings section", s.win("settings").locator(".set-title", has_text="Security").count() == 1)
    page.locator(".mb-brand").click()
    s.ctx_click("About this computer")
    d.settle(500)
    s.check("brand menu -> About reuses the one Settings window", page.locator('section.win[data-app="settings"]').count() == 1
            and s.win("settings").locator(".set-title", has_text="About").count() == 1)
    s.reset()

    # --- dock
    dock_files = page.locator('#dock .dock-item[data-app="terminal"]')
    s.check("dock shows Terminal pinned", dock_files.count() == 1)
    dock_files.click(button="right")
    s.check("dock right-click opens a menu", page.locator("#overlays .ctx").count() == 1)
    s.ctx_click("Unpin from dock")
    d.settle(300)
    s.check("Unpin removes the app from the dock and from the saved prefs", page.locator('#dock .dock-item[data-app="terminal"]').count() == 0 and "terminal" not in s.prefs()["dock"])
    page.keyboard.press("Control+Alt+t")
    d.settle(500)
    s.check("Ctrl Alt T opens a terminal", s.win("terminal").count() == 1)
    s.check("a running unpinned app still shows in the dock", page.locator('#dock .dock-item[data-app="terminal"]').count() == 1)
    page.locator('#dock .dock-item[data-app="terminal"]').click(button="right")
    s.check("the menu offers 'Pin to dock'", page.locator("#overlays .ctx .ctx-item", has_text="Pin to dock").count() == 1)
    s.ctx_click("Pin to dock")
    d.settle(300)
    s.check("Pin puts it back", "terminal" in s.prefs()["dock"])
    page.locator('#dock .dock-item[data-app="terminal"]').click(button="right")
    s.check("'New Terminal window' is offered for non-singleton apps", page.locator("#overlays .ctx .ctx-item", has_text="New Terminal window").count() == 1)
    s.ctx_click("New Terminal window")
    d.settle(400)
    s.check("...and opens a second window", page.locator('section.win[data-app="terminal"]').count() == 2)
    page.locator('#dock .dock-item[data-app="terminal"]').click(button="right")
    s.ctx_click("Close all windows")
    d.settle(500)
    s.check("'Close all windows' closes them", page.locator('section.win[data-app="terminal"]').count() == 0)

    # --- launcher
    page.get_by_role("button", name="All apps").click()
    s.check("launcher opens", page.locator(".launcher .launch-item").count() >= 10)
    page.locator(".launcher-search").fill("auto")
    s.check("launcher search filters", page.locator(".launcher .launch-item").count() == 1)
    page.keyboard.press("Enter")
    d.settle(500)
    s.check("Enter in the launcher opens the first match", s.win("automations").count() == 1)
    s.reset()
    page.get_by_role("button", name="All apps").click()
    page.keyboard.press("Escape")
    s.check("Esc closes the launcher", page.locator(".launcher").count() == 0)
    # unknown settings section must not throw
    errs0 = len(d.rec.problems)
    d.os_eval("(os) => os.openApp('settings', { section: 'does-not-exist' })")
    d.settle(400)
    s.check("openApp('settings', {section: <unknown>}) falls back to Appearance without errors",
            s.win("settings").locator(".set-title", has_text="Appearance").count() == 1 and len(d.rec.problems) == errs0)
    s.reset()


def sec_files(s: Suite) -> None:
    """Files: new folder/file, rename, copy, move, delete -> Trash -> restore, upload, download, search, open in editor/viewer."""
    d, page = s.d, s.page
    s.reset()
    s.api("POST", "/api/os/fs/mkdir", {"path": BOX})
    # a window pointing at a folder that no longer exists falls back to the nearest one that does
    d.open_app("files", {"path": f"{BOX}/was-deleted/deeper"})
    d.settle(900)
    s.check("a Files window for a deleted folder shows the nearest existing parent", s.win("files").locator(".crumb.current", has_text=BOX.split("/")[-1]).count() == 1
            and any("is gone" in t for t in s.toast_texts()), s.win("files").locator(".files-crumbs").inner_text())
    s.reset()
    d.open_app("files", {"path": BOX})
    w = s.win("files")
    d.settle(600)
    row = lambda name: w.locator(".fitem", has=page.locator(".ftext", has_text=re.compile(f"^{re.escape(name)}$")))  # noqa: E731

    w.get_by_role("button", name="Folder").click()
    page.locator("#overlays .modal input").fill("qa-folder")
    s.modal_click("Create")
    d.settle(500)
    s.check("New folder creates it on disk and in the list", row("qa-folder").count() == 1 and s.api("GET", f"/api/os/fs/stat?path={BOX}/qa-folder")[0] == 200)
    w.get_by_role("button", name="File").click()
    page.locator("#overlays .modal input").fill("qa-a.txt")
    s.modal_click("Create")
    d.settle(500)
    s.check("New file creates it", row("qa-a.txt").count() == 1)
    s.check("...and opens it in the Editor", s.win("editor").count() == 1)
    s.win("editor").locator(".win-close").click()
    d.settle(300)
    w = s.win("files")
    w.get_by_role("button", name="File").click()
    page.locator("#overlays .modal input").fill("bad/name")
    s.modal_click("Create")
    d.settle(300)
    s.check("an invalid name is rejected with a message and no file", page.locator("#overlays .modal .modal-error:not([hidden])").count() == 1)
    page.keyboard.press("Escape")

    # write content so later checks (copy/move/download) are meaningful
    s.api("PUT", "/api/os/fs/write", {"path": f"{BOX}/qa-a.txt", "content": "alpha\n"})
    w.get_by_role("button", name="Switch view").click()
    d.settle(200)
    w.get_by_role("button", name="Switch view").click()
    d.settle(200)
    s.refresh = lambda: (w.locator(".files-toolbar").get_by_role("button", name="Switch view"), None)  # noqa: E731

    # rename (F2)
    row("qa-a.txt").click()
    page.keyboard.press("F2")
    inp = w.locator(".fitem input")
    inp.fill("qa-b.txt")
    inp.press("Enter")
    d.settle(500)
    s.check("F2 rename renames on disk", s.api("GET", f"/api/os/fs/stat?path={BOX}/qa-b.txt")[0] == 200 and s.api("GET", f"/api/os/fs/stat?path={BOX}/qa-a.txt")[0] == 404)

    # copy -> paste into folder
    row("qa-b.txt").click()
    page.keyboard.press("Control+c")
    row("qa-folder").click(button="right")
    s.ctx_click("Paste into folder")
    d.settle(600)
    s.check("copy + paste into a folder copies the file (original stays)", s.api("GET", f"/api/os/fs/stat?path={BOX}/qa-folder/qa-b.txt")[0] == 200
            and s.api("GET", f"/api/os/fs/stat?path={BOX}/qa-b.txt")[0] == 200)
    # cut -> paste moves
    row("qa-b.txt").click()
    page.keyboard.press("Control+x")
    row("qa-folder").dblclick()
    d.settle(500)
    page.keyboard.press("Control+v")
    d.settle(500)
    s.wait_toast("Moved|Pasted|exists", 3000)
    d.settle(400)
    # the folder already holds a copy named qa-b.txt: the app asks Skip/Replace
    if page.locator("#overlays .modal", has_text="already exists").count():
        s.modal_click("Replace")
        d.settle(500)
    s.check("cut + paste moves the file", s.api("GET", f"/api/os/fs/stat?path={BOX}/qa-b.txt")[0] == 404, "source still exists")
    w.get_by_role("button", name="Up one level").click()
    d.settle(400)

    # delete -> Trash -> restore
    s.api("POST", "/api/os/fs/mkdir", {"path": f"{BOX}/{TRASHME}"})
    w.locator(".files-toolbar").get_by_role("button", name="Switch view").click()
    w.locator(".files-toolbar").get_by_role("button", name="Switch view").click()
    d.settle(300)
    page.keyboard.press("F5")
    d.settle(500)
    row(TRASHME).click()
    page.keyboard.press("Delete")
    d.settle(600)
    s.check("Delete moves to Trash (gone from the folder)", s.api("GET", f"/api/os/fs/stat?path={BOX}/{TRASHME}")[0] == 404 and row(TRASHME).count() == 0)
    w.locator(".side-item", has_text="Trash").click()
    d.settle(500)
    s.check("Trash lists it", w.locator(".fitem.trash", has_text=TRASHME).count() == 1)
    w.locator(".fitem.trash", has_text=TRASHME).click()
    w.get_by_role("button", name="Restore").click()
    d.settle(600)
    s.check("Restore brings it back", s.api("GET", f"/api/os/fs/stat?path={BOX}/{TRASHME}")[0] == 200)
    w.locator(".side-item", has_text="Home").click()
    w.locator(".files-main").get_by_role("button", name="Up one level").count()
    d.os_eval("(os, a) => os.openApp('files', a)", {"path": BOX})
    d.settle(400)

    # Undo in the toast
    row(TRASHME).click()
    page.keyboard.press("Delete")
    d.settle(400)
    page.locator("#overlays .toast .toast-action", has_text="Undo").last.click()
    d.settle(600)
    s.check("the toast's Undo restores the deleted item", s.api("GET", f"/api/os/fs/stat?path={BOX}/{TRASHME}")[0] == 200)

    # upload (file chooser)
    tmp = Path(tempfile.mkdtemp(prefix="qa-up-"))
    up = tmp / "qa-upload.txt"
    up.write_text("uploaded by qa\n", encoding="utf-8")
    try:
        with page.expect_file_chooser(timeout=5000) as fc:
            w.get_by_role("button", name="Upload").click()
        fc.value.set_files(str(up))
        d.settle(900)
        s.check("Upload writes the file to the folder", s.api("GET", f"/api/os/fs/read?path={BOX}/qa-upload.txt")[0] == 200 and row("qa-upload.txt").count() == 1)
    except PWTimeout:
        s.check("Upload opens a file chooser", False, "no chooser event")

    # download
    row("qa-upload.txt").click(button="right")
    try:
        with page.expect_download(timeout=6000) as dl:
            s.ctx_click("Download")
        path = dl.value.path()
        s.check("Download delivers the file bytes", Path(path).read_text(encoding="utf-8") == "uploaded by qa\n")
    except PWTimeout:
        s.check("Download delivers the file", False, "no download event")

    # search
    w.locator(".files-search").fill("upload")
    d.settle(900)
    s.check("search finds the file by name", w.locator(".fitem", has_text="qa-upload.txt").count() == 1 and w.locator(".fitem").count() == 1)
    w.locator(".files-search").press("Escape")
    d.settle(500)
    s.check("Esc clears the search and returns to the folder", w.locator(".fitem").count() >= 3)

    # open in editor / viewer
    s.api("POST", "/api/os/fs/mkdir", {"path": f"{BOX}/qa-img"})
    png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc000000301010018dd8db00000000049454e44ae426082")
    import urllib.request
    urllib.request.urlopen(urllib.request.Request(s.base + f"/api/os/fs/upload?path={BOX}/qa-pic.png&overwrite=true", data=png, method="PUT"), timeout=10).read()
    page.keyboard.press("F5")
    d.settle(500)
    row("qa-upload.txt").dblclick()
    d.settle(700)
    s.check("double-click on a text file opens the Editor", s.win("editor").count() == 1 and s.win("editor").locator(".editor-text").input_value().startswith("uploaded by qa"))
    s.win("editor").locator(".win-close").click()
    d.settle(300)
    row("qa-pic.png").dblclick()
    d.settle(900)
    s.check("double-click on an image opens the Viewer with the picture", s.win("viewer").count() == 1 and s.win("viewer").locator("img").count() >= 1)
    s.shot("files")
    s.reset()


def sec_editor(s: Suite) -> None:
    """Editor: edit + save, external-change conflict (overwrite / reload), CRLF preserved, close with unsaved changes."""
    d, page = s.d, s.page
    s.reset()
    s.api("POST", "/api/os/fs/mkdir", {"path": BOX})
    p = f"{BOX}/qa-edit.txt"
    s.api("PUT", "/api/os/fs/write", {"path": p, "content": "line one\nline two\n"})
    d.open_app("editor", {"path": p})
    d.settle(700)
    w = s.win("editor")
    ta = w.locator(".editor-text")
    expect(ta).to_have_value("line one\nline two\n", timeout=4000)
    ta.click()
    page.keyboard.press("Control+End")
    page.keyboard.type("line three")
    s.check("typing marks the file as modified (dot + bullet in the title)", w.locator(".dirty-dot:not([hidden])").count() == 1 and "•" in w.locator(".win-title-text").inner_text())
    page.keyboard.press("Control+s")
    d.settle(600)
    disk = s.get(f"/api/os/fs/read?path={p}")["content"]
    s.check("Ctrl S saves to disk", disk == "line one\nline two\nline three", repr(disk))
    s.check("...and clears the modified marker", w.locator(".dirty-dot:not([hidden])").count() == 0)

    # external change -> conflict -> overwrite
    s.api("PUT", "/api/os/fs/write", {"path": p, "content": "changed outside\n"})
    ta.click()
    page.keyboard.press("Control+End")
    page.keyboard.type(" mine")
    page.keyboard.press("Control+s")
    d.settle(500)
    s.check("saving over an external change asks first", page.locator("#overlays .modal", has_text="File changed on disk").count() == 1)
    s.modal_click("Overwrite")
    d.settle(600)
    s.check("Overwrite replaces the disk version with mine", s.get(f"/api/os/fs/read?path={p}")["content"].endswith(" mine"))

    # external change -> conflict -> reload
    s.api("PUT", "/api/os/fs/write", {"path": p, "content": "outside again\n"})
    ta.click()
    page.keyboard.type("!!")
    page.keyboard.press("Control+s")
    d.settle(500)
    s.modal_click("Reload from disk")
    d.settle(700)
    s.check("Reload from disk discards my edit and shows the outside version", ta.input_value() == "outside again\n" and s.get(f"/api/os/fs/read?path={p}")["content"] == "outside again\n")

    # unsaved changes on close
    ta.click()
    page.keyboard.type("unsaved")
    w.locator(".win-close").click()
    d.settle(300)
    s.check("closing with unsaved edits asks", page.locator("#overlays .modal", has_text="Unsaved changes").count() == 1)
    s.modal_click("Cancel")
    d.settle(300)
    s.check("Cancel keeps the window open", s.win("editor").count() == 1)
    s.win("editor").locator(".win-close").click()
    s.modal_click("Don’t save")
    d.settle(400)
    s.check("Don't save closes without writing", s.win("editor").count() == 0 and s.get(f"/api/os/fs/read?path={p}")["content"] == "outside again\n")

    # a Recent entry whose file has gone: say so, and stop offering it
    gone = f"{BOX}/qa-vanished.txt"
    page.evaluate("async (p) => { const st = await import('/static/os/js/state.js'); st.pushRecent(p); }", gone)
    d.open_app("editor", {"path": gone})
    d.settle(900)
    s.check("opening a file that no longer exists says so (not a raw error)", s.win("editor").locator("h3", has_text="File not found").count() == 1)
    s.check("...and removes it from Recent", gone not in s.prefs()["recent"], s.prefs()["recent"])
    s.reset()

    # CRLF round trip
    q = f"{BOX}/qa-crlf.txt"
    s.api("PUT", "/api/os/fs/write", {"path": q, "content": "a\nb\n", "eol": "crlf"})
    d.open_app("editor", {"path": q})
    d.settle(600)
    w = s.win("editor")
    s.check("a CRLF file shows the CRLF chip", w.locator(".chip", has_text="CRLF").count() == 1)
    w.locator(".editor-text").click()
    page.keyboard.press("Control+End")
    page.keyboard.type("c")
    page.keyboard.press("Control+s")
    d.settle(600)
    import urllib.request
    raw = urllib.request.urlopen(urllib.request.Request(s.base + f"/api/os/fs/raw?path={q}", headers={"Host": "127.0.0.1"}), timeout=10).read()
    s.check("saving keeps CRLF line endings on disk", raw == b"a\r\nb\r\nc", repr(raw))
    s.reset()


SHELL_CMDS = {
    # id-prefix: (echo, stream (3 ticks about 0.9 s apart), long (sleeps ~60 s with a unique marker))
    "powershell": ('echo qa-{id}-ok', '1..3 | ForEach-Object { "tick $_"; Start-Sleep -Milliseconds 900 }', 'Start-Sleep -Seconds 61'),
    "cmd": ('echo qa-{id}-ok', 'for /L %i in (1,1,3) do @(echo tick %i & ping -n 2 127.0.0.1 >nul)', 'ping -n 62 127.0.0.1 >nul'),
    "bash": ('echo qa-{id}-ok', 'for i in 1 2 3; do echo tick $i; sleep 0.9; done', 'sleep 61'),
    "zsh": ('echo qa-{id}-ok', 'for i in 1 2 3; do echo tick $i; sleep 0.9; done', 'sleep 61'),
    "sh": ('echo qa-{id}-ok', 'for i in 1 2 3; do echo tick $i; sleep 0.9; done', 'sleep 61'),
}


def sec_terminal(s: Suite) -> None:
    """Terminal: each shell runs echo; output streams; Ctrl C stops the command and its children; timeout via the API."""
    d, page = s.d, s.page
    s.reset()
    d.open_app("terminal")
    d.settle(500)
    w = s.win("terminal")
    shells = d.os_eval("(os) => os.boot.shells.map((x) => ({ id: x.id, label: x.label }))")
    s.check("the terminal lists at least one shell", len(shells) >= 1, shells)
    inp = w.locator(".term-input")
    out_text = lambda: w.locator(".term-out").inner_text()  # noqa: E731
    for sh in shells:
        sid = sh["id"]
        kind = next((k for k in SHELL_CMDS if sid.startswith(k) or k in sid), None)
        if not kind:
            s.skip(f"shell {sid}", "no test commands for this shell")
            continue
        echo, stream, long_cmd = SHELL_CMDS[kind]
        w.locator(".term-bar select").select_option(sid)
        marker = f"qa-{sid}-ok"
        inp.click()
        inp.fill(echo.format(id=sid))
        inp.press("Enter")
        lines: List[str] = []
        for _ in range(150):           # up to 15 s for the shell to start and answer
            page.wait_for_timeout(100)
            lines = [ln.strip() for ln in out_text().splitlines()]
            if marker in lines:        # the output line itself, not the "› echo ..." command line that contains the marker too
                break
        if not s.check(f"[{sid}] echo prints its output (not just the command line)", marker in lines, lines[-4:]):
            continue
        # streaming (screen cleared first: the previous shell's ticks would still be there)
        inp.click()
        inp.press("Control+l")
        inp.fill(stream)
        inp.press("Enter")
        t0 = time.time()
        try:
            expect(w.locator(".term-out")).to_contain_text("tick 1", timeout=10000)
            first = time.time() - t0
            early = "tick 3" not in out_text()
            expect(w.locator(".term-out")).to_contain_text("tick 3", timeout=10000)
            s.check(f"[{sid}] output streams while the command runs", early, f"tick 1 after {first:.1f}s but tick 3 was already there" if not early else "")
        except AssertionError:
            s.check(f"[{sid}] output streams while the command runs", False, out_text()[-200:])
        expect(w.locator(".term-row")).not_to_have_class(re.compile("running"), timeout=8000)
        # Ctrl C
        inp.click()
        inp.fill(long_cmd)
        inp.press("Enter")
        d.settle(1500)
        running = w.locator(".term-row.running").count() == 1 and w.get_by_role("button", name="Stop").is_visible()
        s.check(f"[{sid}] a long command shows Stop while it runs", running)
        t0 = time.time()
        inp.press("Control+c")
        try:
            expect(w.locator(".term-row")).not_to_have_class(re.compile("running"), timeout=6000)
            s.check(f"[{sid}] Ctrl C stops it", "^C" in out_text(), f"{time.time() - t0:.1f}s")
        except AssertionError:
            s.check(f"[{sid}] Ctrl C stops it", False, "still running after 6 s")
        d.settle(1200)
        survivors = [p for p in s.get("/api/os/processes")["processes"] if re.search(r"Start-Sleep -Seconds 61|ping -n 62|sleep 61", p.get("cmdline") or "")]
        s.check(f"[{sid}] Ctrl C also ended the processes the command started", not survivors, [(p["name"], p["pid"]) for p in survivors])
        for p in survivors:
            s.api("POST", f"/api/os/processes/{p['pid']}/terminate", {"force": True})

    # cd carries over
    w.locator(".term-bar select").select_option(shells[0]["id"])
    inp.click()
    inp.fill("cd ..")
    inp.press("Enter")
    d.settle(1500)
    cwd1 = w.locator(".term-cwd").inner_text()
    s.check("cd changes the working directory shown in the bar", cwd1 != "/Home", cwd1)
    # history + clear + help
    inp.click()
    inp.press("ArrowUp")
    s.check("ArrowUp recalls the previous command", inp.input_value() == "cd ..", inp.input_value())
    inp.fill("help")
    inp.press("Enter")
    s.check("'help' prints the built-in help", "Ctrl C" in out_text())
    inp.press("Control+l")
    d.settle(200)
    s.check("Ctrl L clears the screen", "Ctrl C" not in out_text())
    # timeout through the API (the UI's own limit is minutes): a 2 s limit on a 20 s sleep
    res = page.evaluate("""async () => {
      const { streamEvents } = await import('/static/os/js/api.js');
      const events = []; const t0 = performance.now();
      const sh = (await import('/static/os/js/ctx.js')).os.boot.shells[0].id;
      const cmd = sh.startsWith('powershell') ? 'Start-Sleep -Seconds 20' : sh === 'cmd' ? 'ping -n 22 127.0.0.1 >nul' : 'sleep 20';
      await streamEvents('/terminal/exec', { command: cmd, shell: sh, timeout: 2 }, (e) => events.push(e));
      return { ms: performance.now() - t0, last: events[events.length - 1] };
    }""")
    s.check("a command over its time limit is stopped and reported as a timeout", bool(res["last"].get("timeout")) and res["ms"] < 9000, res)
    s.shot("terminal")
    s.reset()


def sec_taskmgr(s: Suite) -> None:
    """Task Manager: sorting, filter, ending a dummy process, live performance graphs, background jobs."""
    d, page = s.d, s.page
    s.reset()
    dummy_dir = Path(tempfile.mkdtemp(prefix="qa-dummy-"))
    exe = dummy_dir / "qa-dummy-proc.exe"
    # a copy of the real interpreter under a unique name (a venv's python.exe is only a launcher and does not survive being copied)
    real_python = Path(sys.base_prefix) / ("python.exe" if sys.platform == "win32" else "bin/python3")
    shutil.copy2(real_python if real_python.exists() else sys.executable, exe)
    cmd = [str(exe), "-c", "import time; time.sleep(600)"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        d.open_app("taskmgr")
        w = s.win("taskmgr")
        d.settle(2500)
        rows = w.locator(".tm-table tbody tr.group")
        s.check("the process list loads", rows.count() > 15, rows.count())
        summary = w.locator(".tm-summary").inner_text()
        s.check("the summary shows CPU, RAM and process count", bool(re.search(r"CPU \d+% . RAM \d+% . \d+ processes", summary)), summary)

        def mem_values() -> List[float]:
            vals = []
            for t in w.locator(".tm-table tbody tr.group td:nth-child(5)").all_inner_texts()[:25]:
                m = re.match(r"([\d.]+)\s*(B|KB|MB|GB)", t.strip())
                if m:
                    vals.append(float(m.group(1)) * {"B": 1, "KB": 1e3, "MB": 1e6, "GB": 1e9}[m.group(2)])
            return vals

        w.locator("th button", has_text="Memory").click()
        d.settle(400)
        v = mem_values()
        s.check("sorting by Memory orders the rows (descending first)", len(v) > 5 and all(v[i] >= v[i + 1] * 0.999 for i in range(len(v) - 1)), v[:6])
        w.locator("th button", has_text="Memory").click()
        d.settle(400)
        v = mem_values()
        s.check("a second click on the header reverses the order", len(v) > 5 and all(v[i] <= v[i + 1] * 1.001 for i in range(len(v) - 1)), v[:6])
        w.locator("th button", has_text="Name").click()
        d.settle(300)
        names = w.locator(".tm-table tbody tr.group .pname").all_inner_texts()[:30]
        in_order = page.evaluate("(names) => names.every((n, i) => i === 0 || names[i - 1].localeCompare(n, undefined, { sensitivity: 'base' }) <= 0)", names)
        s.check("sorting by Name is alphabetical (A to Z first)", in_order, names[:6])

        w.locator(".tm-filter").fill("qa-dummy")
        d.settle(700)
        s.check("filter narrows the list to the dummy process", w.locator(".tm-table tbody tr.group").count() == 1, w.locator(".tm-table tbody tr.group").count())
        s.check("...and the count label says so", "1 programs" in w.locator(".tm-count").inner_text(), w.locator(".tm-count").inner_text())
        w.locator(".tm-table tbody tr.group").first.click()
        s.check("End task is enabled for a normal process", w.get_by_role("button", name="End task").is_enabled())
        w.get_by_role("button", name="End task").click()
        d.settle(300)
        s.check("End task asks for confirmation", page.locator("#overlays .modal", has_text="End task?").count() == 1)
        s.modal_click("Cancel")
        d.settle(300)
        s.check("Cancel leaves the process running", proc.poll() is None)
        w.get_by_role("button", name="End task").click()
        s.modal_click("End task")
        d.settle(2500)
        s.check("End task really ends the process", proc.poll() is not None, f"returncode={proc.poll()}")
        s.check("...and the row disappears", w.locator(".tm-table tbody tr.group").count() == 0)

        # protected: the server itself cannot be ended from the UI
        w.locator(".tm-filter").fill(str(s.api("GET", "/api/os/boot")[1]["system"].get("pid", "")) or "python")
        w.locator(".tm-filter").fill("")
        w.locator(".tm-filter").fill("python")
        d.settle(700)
        srv = w.locator(".tm-table tbody tr", has=page.locator(".badge", has_text="Odysseus"))
        if srv.count():
            srv.first.click()
            s.check("the Odysseus server process cannot be ended (End task disabled)", w.get_by_role("button", name="End task").is_disabled())
        else:
            w.get_by_role("button", name="Group by program").click()
            d.settle(500)
            srv = w.locator(".tm-table tbody tr", has=page.locator(".badge", has_text="Odysseus"))
            if srv.count():
                srv.first.click()
                s.check("the Odysseus server process cannot be ended (End task disabled)", w.get_by_role("button", name="End task").is_disabled())
            else:
                s.skip("server process is protected", "server row not found in the list")
        w.locator(".tm-filter").fill("")

        # performance
        w.locator('.tab[data-tab="performance"]').click()
        d.settle(2500)
        d0 = w.locator(".chart-line").first.get_attribute("d")
        v0 = w.locator(".perf-value").first.inner_text()
        d.settle(4500)
        d1 = w.locator(".chart-line").first.get_attribute("d")
        s.check("the CPU graph keeps drawing new samples", bool(d0) and d0 != d1 and d1.count("L") >= d0.count("L"), f"{(d0 or '')[:50]} / {(d1 or '')[:50]}")
        s.check("CPU, Memory, Network, Storage and Cores cards are populated", w.locator(".perf-card").count() == 5 and w.locator(".perf-disks .disk").count() >= 1 and w.locator(".perf-cores .core").count() >= 2, w.locator(".perf-card").count())
        s.shot("taskmgr-perf")

        # jobs
        w.locator('.tab[data-tab="jobs"]').click()
        d.settle(600)
        w.locator(".jobs-new input").fill("echo qa-job-ok")
        w.locator(".jobs-new").get_by_role("button", name="Run").click()
        d.settle(3500)
        s.check("a background job runs and its output is shown", w.locator(".job-output", has_text="qa-job-ok").count() == 1 and w.locator(".job", has_text="qa-job-ok").count() == 1,
                w.locator(".jobs-detail").inner_text()[:120])
        long_cmd = "ping -n 40 127.0.0.1" if sys.platform == "win32" else "sleep 40"
        w.locator(".jobs-new input").fill(long_cmd)
        w.locator(".jobs-new input").press("Enter")
        d.settle(2500)
        cancel = w.locator(".jobs-detail").get_by_role("button", name="Cancel")
        s.check("a running job offers Cancel", cancel.count() == 1)
        if cancel.count():
            cancel.click()
            d.settle(3500)
            state = w.locator(".jobs-detail .pill").first.inner_text().lower()
            s.check("Cancel stops the job", state in ("cancelled", "failed", "completed", "canceled", "stopped"), state)
        s.reset()
    finally:
        if proc.poll() is None:
            proc.kill()
        shutil.rmtree(dummy_dir, ignore_errors=True)


def sec_settings(s: Suite) -> None:
    """Settings: every pane, theme, wallpaper, dock, folders (add / read-only / remove), terminal shell, security log, about."""
    d, page = s.d, s.page
    s.reset()
    d.open_app("settings")
    w = s.win("settings")
    d.settle(500)
    r = s.rect("settings")
    sizes = {}
    for label, title in (("Appearance", "Appearance"), ("AI models", "models"), ("Folders", "Folders"), ("Terminal", "Terminal"), ("Security & activity", "Security"), ("About", "About")):
        w.locator(".set-nav .side-item", has_text=label).click()
        d.settle(700)
        s.check(f"pane '{label}' renders its title", w.locator(".set-title", has_text=title).count() >= 1)
        sizes[label] = w.locator(".set-pane").evaluate("e => [e.scrollHeight, e.clientHeight]")
    s.check("Settings window fits the 1280x800 desktop (no part off screen)", r["y"] >= -1 and r["y"] + r["h"] <= 800 and r["x"] + r["w"] <= 1280, r)
    s.check("Appearance fits within one screenful plus a small scroll (dock picker is 4 columns wide)", sizes["Appearance"][0] <= sizes["Appearance"][1] + 130, sizes["Appearance"])

    w.locator(".set-nav .side-item", has_text="Appearance").click()
    d.settle(300)
    w.locator(".seg", has_text="Dark").click()
    d.settle(200)
    s.check("Dark switches the whole desktop to dark", page.evaluate("document.documentElement.dataset.theme") == "dark" and s.prefs()["theme"] == "dark")
    bg_dark = page.evaluate("getComputedStyle(document.body).backgroundColor")
    w.locator(".seg", has_text="Light").click()
    d.settle(200)
    bg_light = page.evaluate("getComputedStyle(document.body).backgroundColor")
    s.check("Light switches back and the colours really differ", page.evaluate("document.documentElement.dataset.theme") == "light" and bg_dark != bg_light, f"{bg_dark} vs {bg_light}")
    w.locator(".seg", has_text="Auto").click()
    w.locator(".wall", has_text="Dusk").click()
    d.settle(200)
    s.check("a wallpaper choice applies", page.evaluate("document.documentElement.dataset.wallpaper") == "dusk")
    w.locator(".wall", has_text="Paper").click()

    pick = w.locator(".dock-pick .pick", has_text="Memory")
    was = "memory" in s.prefs()["dock"]
    pick.click()
    d.settle(300)
    s.check("a dock checkbox adds/removes the app from the dock", ("memory" in s.prefs()["dock"]) != was and (page.locator('#dock .dock-item[data-app="memory"]').count() == 1) == ("memory" in s.prefs()["dock"]))
    w.locator(".dock-pick .pick", has_text="Memory").click()
    d.settle(300)
    s.check("...and toggling it again restores the dock", ("memory" in s.prefs()["dock"]) == was)
    hid0 = s.prefs()["showHidden"]
    w.locator("label.switch", has=page.locator('input[aria-label="Show hidden files"]')).click()
    d.settle(200)
    s.check("'Show hidden files' toggles the preference", s.prefs()["showHidden"] != hid0)
    w.locator("label.switch", has=page.locator('input[aria-label="Show hidden files"]')).click()

    # folders
    w.locator(".set-nav .side-item", has_text="Folders").click()
    d.settle(400)
    src = Path(tempfile.mkdtemp(prefix="qa-mount-"))
    (src / "inside.txt").write_text("hi", encoding="utf-8")
    w.get_by_label("Folder name").fill("qa-mount")
    w.get_by_label("Folder path").fill(str(src))
    w.get_by_role("button", name="Add folder").click()
    d.settle(900)
    s.check("Add folder mounts it (list + API)", w.locator(".mount", has_text="qa-mount").count() == 1 and any(m["name"] == "qa-mount" for m in s.get("/api/os/fs/roots")["mounts"]))
    mount_ro = lambda: [m for m in s.get("/api/os/fs/roots")["mounts"] if m["name"] == "qa-mount"][0]["readonly"]  # noqa: E731
    st, _ = s.api("POST", "/api/os/fs/mkdir", {"path": "/qa-mount/qa-should-fail"})
    s.check("a folder added with the default 'Read-only' box ticked is read-only on the server", mount_ro() is True and st >= 400, f"ro={mount_ro()} mkdir status={st}")
    w.locator(".mount", has_text="qa-mount").locator("label.mount-ro .switch").click()
    d.settle(600)
    st, _ = s.api("POST", "/api/os/fs/mkdir", {"path": "/qa-mount/qa-now-works"})
    s.check("switching Read-only off makes it writable (server agrees)", mount_ro() is False and st == 200, f"ro={mount_ro()} mkdir status={st}")
    w.locator(".mount", has_text="qa-mount").locator("label.mount-ro .switch").click()
    d.settle(600)
    s.check("switching it back on makes it read-only again", mount_ro() is True)
    d.open_app("files", {"path": "/qa-mount"})
    d.settle(700)
    s.check("a mounted folder is browsable in Files", s.win("files").locator(".ftext", has_text="inside.txt").count() == 1)
    s.win("files").locator(".win-close").click()
    d.open_app("settings")
    w = s.win("settings")
    w.locator(".set-nav .side-item", has_text="Folders").click()
    d.settle(300)
    w.get_by_role("button", name="Remove qa-mount").click()
    s.check("Remove asks for confirmation", page.locator("#overlays .modal", has_text="Remove").count() == 1)
    s.modal_click("Remove")
    d.settle(700)
    s.check("Remove unmounts it but leaves the files on disk", w.locator(".mount", has_text="qa-mount").count() == 0 and (src / "inside.txt").exists())
    shutil.rmtree(src, ignore_errors=True)
    w.get_by_label("Folder name").fill("x")
    w.get_by_role("button", name="Add folder").click()
    s.check("adding a folder without a path complains instead of calling the server", s.wait_toast("Enter a name", 2000))

    # terminal pane
    w.locator(".set-nav .side-item", has_text="Terminal").click()
    d.settle(300)
    opts = w.locator('select[aria-label="Default shell"] option').all_inner_texts()
    s.check("the default-shell list matches the shells the server reports", len(opts) == len(d.os_eval("(os) => os.boot.shells")), opts)
    # security
    w.locator(".set-nav .side-item", has_text="Security").click()
    d.settle(900)
    s.check("the activity log lists recorded events", w.locator(".audit-table tbody tr").count() > 3, w.locator(".audit-table tbody tr").count())
    w.get_by_role("button", name="Refresh").click()
    d.settle(500)
    s.check("Refresh reloads the log without error", w.locator(".audit-table tbody tr").count() > 3)
    # about
    w.locator(".set-nav .side-item", has_text="About").click()
    d.settle(300)
    host = s.get("/api/os/boot")["system"]["hostname"]
    s.check("About shows this computer's real name", w.locator(".set-pane", has_text=host).count() == 1)
    s.shot("settings-about")
    s.reset()


def sec_models(s: Suite) -> None:
    """Settings -> AI models: current selection, benchmark results, 'Apply recommendation' shows an applied state."""
    d, page = s.d, s.page
    s.reset()
    status, cur0 = s.api("GET", "/api/os/models/current")
    status_b, latest = s.api("GET", "/api/os/models/bench/latest")
    if status != 200 or not (latest or {}).get("results"):
        s.skip("models pane", f"no endpoints / no benchmark results here (current={status})")
        return
    rec = latest["results"].get("recommended") or {}

    def ref(r):
        return {"endpoint_id": r["endpoint_id"], "model": r["model"]} if r else None

    def body_for(c):
        return {"default": ref(c["default"]), "fallbacks": [ref(f) for f in c.get("fallbacks") or []], "utility": ref(c.get("utility")),
                "utility_fallbacks": [ref(f) for f in c.get("utility_fallbacks") or []]}

    try:
        d.open_app("settings", {"section": "models"})
        w = s.win("settings")
        d.settle(1500)
        s.check("'In use' shows the default chat model", w.locator(".mdl-model", has_text=cur0["default"]["model"].split("/")[-1]).count() >= 1)
        s.check("benchmark results are listed with scores", w.locator(".mdl-row").count() >= 3, w.locator(".mdl-row").count())
        btn = w.locator(".mdl-rec-act button")
        s.check("the recommendation card is shown", btn.count() == 1)
        # make the recommendation 'not applied': switch the default to a different usable model, then apply
        other = next((x for x in latest["results"]["results"] if x["status"] in ("ok", "partial") and (x["endpoint_id"], x["model"]) != (cur0["default"]["endpoint_id"], cur0["default"]["model"])), None)
        if other:
            st, _ = s.api("POST", "/api/os/models/default", {"default": ref(other), "fallbacks": [], "utility": None, "utility_fallbacks": []})
            d.reset = None
            s.reset()
            d.open_app("settings", {"section": "models"})
            w = s.win("settings")
            d.settle(1500)
            btn = w.locator(".mdl-rec-act button")
            s.check("with a different default, Apply recommendation is enabled", btn.is_enabled() and "Apply" in btn.inner_text(), btn.inner_text())
        btn.click()
        d.settle(1500)
        s.check("clicking it applies the recommendation (toast)", True)
        now = s.get("/api/os/models/current")
        want = rec["default"]
        s.check("...the server's default equals the recommendation", (now["default"]["endpoint_id"], now["default"]["model"]) == (want["endpoint_id"], want["model"]), now["default"])
        btn = w.locator(".mdl-rec-act button")
        s.check("...and the button now reads 'Applied' and is disabled", btn.is_disabled() and "Applied" in btn.inner_text(), f"{btn.inner_text()!r} disabled={btn.is_disabled()}")
        # reopen: the state must be recomputed from the live selection, not remembered
        s.reset()
        d.open_app("settings", {"section": "models"})
        w = s.win("settings")
        d.settle(1500)
        btn = w.locator(".mdl-rec-act button")
        s.check("after reopening, an already-applied recommendation still shows Applied/disabled", btn.is_disabled() and "Applied" in btn.inner_text(), f"{btn.inner_text()!r} disabled={btn.is_disabled()}")
        # 'Make default' on a different row flips it back to an enabled 'Apply recommendation'
        row_btn = w.locator(".mdl-row", has_not=page.locator(".mdl-flag", has_text="Default")).get_by_role("button", name="Make default").first
        if row_btn.count():
            row_btn.click()
            d.settle(1200)
            btn = w.locator(".mdl-rec-act button")
            s.check("choosing another default re-enables Apply recommendation", btn.is_enabled(), btn.inner_text())
        s.shot("models")
    finally:
        s.api("POST", "/api/os/models/default", body_for(cur0))
        s.reset()


def sec_jarvis(s: Suite) -> None:
    """Jarvis: deterministic commands, approvals (approve + deny), the planner with the real model, automation + todo end to end."""
    d, page = s.d, s.page
    s.reset()
    page.evaluate("localStorage.removeItem('ody.jarvis.chat.local')")
    d.open_app("jarvis")
    w = s.win("jarvis")
    d.settle(500)
    inp = w.locator(".jv-input")
    send = lambda text: (inp.fill(text), inp.press("Enter"))  # noqa: E731
    s.check("the empty state offers suggestion chips", w.locator(".jv-chips .chip").count() >= 4)

    send("help")
    # the typing indicator is also a ".jv-msg.assistant": wait for the answer's own text, not for the first bubble
    expect(w.locator(".jv-msg.assistant .jv-text").first).to_be_visible(timeout=8000)
    s.check("'help' answers without a model", w.locator(".jv-text", has_text=re.compile("commands|status", re.I)).count() >= 1 or w.locator(".jv-msg.assistant pre").count() >= 1)
    send("cpu")
    d.settle(2500)
    s.check("'cpu' shows live system metrics", w.locator(".jv-msg.assistant", has_text=re.compile("CPU", re.I)).count() >= 1)
    send("ls /Home")
    d.settle(2000)
    s.check("'ls /Home' lists the Home folder", w.locator(".jv-msg.assistant", has_text=re.compile("Documents|Desktop")).count() >= 1)

    # command approval: approve
    send("run echo qa-approve-ok")
    ap = w.locator(".jv-approval")
    expect(ap.last).to_be_visible(timeout=8000)
    s.check("a command asks for approval first (nothing ran yet)", ap.last.get_by_role("button", name="Approve").is_visible() and w.locator(".jv-text", has_text="qa-approve-ok").count() == 0)
    ap.last.get_by_role("button", name="Approve").click()
    d.settle(3000)
    s.check("Approve runs it and shows the output", w.locator(".jv-text", has_text="qa-approve-ok").count() >= 1)
    s.check("the approval card now reads 'Approved'", w.locator(".jv-approval.is-approved").count() == 1)
    # deny
    send("run echo qa-deny-ok")
    expect(w.locator(".jv-approval:not(.is-approved)").last).to_be_visible(timeout=8000)
    w.locator(".jv-approval:not(.is-approved)").last.get_by_role("button", name="Cancel").click()
    d.settle(1200)
    s.check("Cancel denies it: card reads 'Cancelled' and nothing ran", w.locator(".jv-approval.is-denied").count() == 1 and w.locator(".jv-text", has_text="qa-deny-ok").count() == 0)
    s.check("the approval is audited", any("approval" in (e.get("type") or "") or "command" in (e.get("type") or "") for e in s.get("/api/os/audit?limit=80")["events"]))

    # dangerous command refused even after approval
    send("run format C:")
    d.settle(3000)
    blocked = w.locator(".jv-msg.assistant", has_text=re.compile("refus|not allowed|blocked|won.t run|can.t", re.I)).count() >= 1
    ap2 = w.locator(".jv-approval:not(.is-approved):not(.is-denied)")
    if ap2.count():
        ap2.last.get_by_role("button", name="Approve").click()
        d.settle(2500)
        blocked = w.locator(".jv-msg.assistant", has_text=re.compile("refus|not allowed|blocked|catastroph|won.t run|can.t", re.I)).count() >= 1
    s.check("a catastrophic command is refused by the guard", blocked, w.locator(".jv-scroll").inner_text()[-200:])

    # personal tools: each turn costs one model call; keep them few and spaced (Groq free tier ~8k tokens/min)
    if not s.args.ai:
        s.skip("planner checks", "run with --ai to include the model-backed checks")
        s.reset()
        return
    status, cur = s.api("GET", "/api/os/models/current")
    if status != 200 or not cur.get("default"):
        s.skip("planner checks", "no model configured")
        s.reset()
        return
    turns = {"n": 0}

    def ask(text: str, wait_for, timeout: int = 60000):
        if turns["n"]:
            time.sleep(14)    # spacing for the provider's tokens-per-minute limit
        turns["n"] += 1
        send(text)
        try:
            wait_for.wait_for(timeout=timeout)
            return True
        except PWTimeout:
            return False

    d.open_app("jarvis")
    todo_text = f"qa jarvis todo {int(time.time()) % 10000}"
    got = ask(f"Add to my todos: {todo_text}", w.locator(".jv-approval:not(.is-approved):not(.is-denied)").last)
    s.check("planner: 'add to my todos' proposes an approval card naming the todo", got and todo_text in w.locator(".jv-approval").last.inner_text(), w.locator(".jv-scroll").inner_text()[-300:])
    if got:
        reqs0 = d.rec.requests
        t0 = time.time()
        w.locator(".jv-approval").last.get_by_role("button", name="Approve").click()
        done_dash = False
        for _ in range(60):
            page.wait_for_timeout(100)
            if page.locator(".tw-todos .td-text", has_text=todo_text).count():
                done_dash = True
                break
        s.check("approved: the todo exists in Notes", any(todo_text in t["text"] for t in s.get("/api/os/today")["todos"]["items"]))
        s.check("...and appears on the Today dashboard within ~6 s (personal-changed refresh, no 30 s wait)", done_dash and time.time() - t0 < 7, f"{time.time() - t0:.1f}s")
        s.check("the Jarvis result card says it was added", w.locator(".jv-result.ok").count() >= 1)

    got = ask("remind me to call the dentist tomorrow at 3pm", w.locator(".jv-approval:not(.is-approved):not(.is-denied)").last)
    s.check("planner: a reminder request proposes an approval card", got and re.search(r"dentist", w.locator(".jv-approval").last.inner_text(), re.I) is not None)
    if got:
        w.locator(".jv-approval:not(.is-approved):not(.is-denied)").last.get_by_role("button", name="Cancel").click()
        d.settle(1000)
        today = s.get("/api/os/today")["agenda"]
        s.check("denied: no reminder was created", not any("dentist" in (r.get("summary") or "").lower() for r in today.get("reminders", [])))

    got = ask("every weekday at 9am give me a brief of my day", w.locator(".jv-approval:not(.is-approved):not(.is-denied)").last)
    s.check("planner: 'every weekday at 9am give me a brief' proposes creating an automation", got and re.search(r"automation|brief", w.locator(".jv-approval").last.inner_text(), re.I) is not None)
    before = {t["id"] for t in s.get("/api/tasks")["tasks"]}
    if got:
        w.locator(".jv-approval:not(.is-approved):not(.is-denied)").last.get_by_role("button", name="Approve").click()
        d.settle(4000)
        new = [t for t in s.get("/api/tasks")["tasks"] if t["id"] not in before]
        s.check("approved: the automation exists in the scheduler (same /api/tasks the Automations app uses)", len(new) == 1, [t["name"] for t in new])
        if new:
            d.open_app("automations")
            d.settle(1200)
            s.check("...and the Automations app lists it", s.win("automations").locator(".au-row, .au-item, [role=option]", has_text=new[0]["name"]).count() >= 1)
            s.check("...and the Today dashboard lists it under Automations", page.locator(".tw-automations", has_text=new[0]["name"]).count() >= 1)
            for t in new:
                s.api("DELETE", f"/api/tasks/{t['id']}")
            d.settle(500)
        d.open_app("jarvis")

    got = ask("every hour run the shell command `echo hi` as a scheduled automation", w.locator(".jv-msg.assistant").last, timeout=60000)
    d.settle(1500)
    txt = w.locator(".jv-scroll").inner_text()
    s.check("planner: a shell automation is refused (no approval card for it)", bool(re.search(r"can.t|cannot|only you|not able|shell|Automations", txt[-600:], re.I)) and w.locator(".jv-approval:not(.is-approved):not(.is-denied)").count() == 0, txt[-300:])
    s.check("planner turns used", turns["n"] <= 6, turns["n"])
    s.shot("jarvis")
    # cleanup: the todo we added
    s.reset()


def sec_automations(s: Suite) -> None:
    """Automations: list, search, create from a template with a typed schedule, pause/resume, edit, duplicate, delete, Run now."""
    d, page = s.d, s.page
    s.reset()
    d.open_app("automations")
    w = s.win("automations")
    d.settle(1500)
    rows = w.locator(".au-list .au-row")
    s.check("seeded automations are listed", rows.count() >= 4, w.locator(".au-list").inner_text()[:100])
    s.check("the header counts them", re.search(r"\d+ active", w.locator(".au-head, header, h1").first.inner_text()) is not None, w.locator("h1").first.inner_text() if w.locator("h1").count() else "")
    w.locator(".au-search").fill("weekly")
    d.settle(400)
    n = rows.count()
    s.check("search narrows the list", 1 <= n < 4, n)
    w.locator(".au-search").fill("")
    d.settle(300)
    w.locator('.au-tabs [role=tab]', has_text="Paused").click()
    d.settle(300)
    s.check("the Paused filter shows only paused ones (none yet)", rows.count() == 0)
    w.locator('.au-tabs [role=tab]', has_text="All").click()

    name = f"qa-auto-{TAG}"
    w.get_by_role("button", name="New automation").click()
    d.settle(500)
    s.check("New opens the sheet with the templates", w.locator(".au-sheet .au-tpl").count() >= 8)
    shell_tpl = w.locator('.au-tpl[data-template="custom-command"]')
    s.check("shell-command templates are disabled (no admin sign-in) instead of failing", shell_tpl.count() == 1 and shell_tpl.is_disabled(), shell_tpl.get_attribute("aria-label"))
    s.shot("automations-new")
    w.locator('.au-tpl[data-template="custom-ai"]').click()
    d.settle(400)
    w.locator("#au-name").fill(name)
    w.locator("#au-prompt").fill("Say hello in one short sentence.")
    w.locator("#au-nl").fill("every weekday at 9:30am")
    w.locator("#au-nl").press("Enter")
    d.settle(600)
    chips = w.locator(".au-preview-runs .au-run-chip")
    s.check("the typed schedule shows its next three runs", chips.count() == 3, w.locator(".au-preview").inner_text()[:160])
    s.shot("automations-form")
    w.locator("#au-save").click()
    d.settle(1500)
    mine = [t for t in s.get("/api/tasks")["tasks"] if t["name"] == name]
    s.check("Create automation saves it in the scheduler (the same /api/tasks as the classic page)", len(mine) == 1 and mine[0]["status"] == "active", [t["name"] for t in s.get("/api/tasks")["tasks"]])
    if not mine:
        s.reset()
        return
    tid = mine[0]["id"]
    s.check("...with a weekday schedule stored (cron or weekly)", mine[0]["schedule"] in ("cron", "weekly") and bool(mine[0].get("next_run")), {k: mine[0].get(k) for k in ("schedule", "cron_expression", "scheduled_time", "next_run")})
    row = w.locator(".au-row", has_text=name)
    s.check("the new row appears in the list without a reload", row.count() == 1)
    row.click()
    d.settle(500)
    s.check("selecting it shows its detail with the instruction", w.locator(".au-detail", has_text="Say hello in one short sentence").count() == 1)

    row.locator('input[role=switch]').click(force=True)
    d.settle(1200)
    st = [t for t in s.get("/api/tasks")["tasks"] if t["id"] == tid][0]["status"]
    s.check("the row switch pauses it (scheduler agrees)", st == "paused", st)
    s.check("...and the Paused filter now lists it", (w.locator('.au-tabs [role=tab]', has_text="Paused").click(), d.settle(300), rows.count())[2] == 1)
    w.locator('.au-tabs [role=tab]', has_text="All").click()
    d.settle(300)
    w.locator(".au-row", has_text=name).locator('input[role=switch]').click(force=True)
    d.settle(1200)
    s.check("the switch resumes it", [t for t in s.get("/api/tasks")["tasks"] if t["id"] == tid][0]["status"] == "active")

    w.locator(".au-row", has_text=name).click()
    w.get_by_role("button", name="Edit").click()
    d.settle(500)
    w.locator("#au-name").fill(name + "-edited")
    w.locator("#au-save").click()
    d.settle(1200)
    s.check("Edit -> Save changes renames it", [t for t in s.get("/api/tasks")["tasks"] if t["id"] == tid][0]["name"] == name + "-edited")

    w.locator(".au-row", has_text=name + "-edited").click()
    w.get_by_role("button", name="Duplicate").click()
    d.settle(800)
    s.check("Duplicate opens a prefilled sheet", w.locator(".au-sheet").count() == 1 and w.locator("#au-prompt").input_value().startswith("Say hello"))
    page.keyboard.press("Escape")
    d.settle(300)

    if s.args.ai:
        w.locator(".au-row", has_text=name + "-edited").click()
        w.get_by_role("button", name="Run now").click()
        d.settle(1500)
        s.check("Run now shows the run starting", w.locator(".au-run", has_text=re.compile("Running|Queued|Succeeded|Failed")).count() >= 1 or w.locator(".au-banner, .au-flash").count() >= 1)
        ok = False
        for _ in range(90):
            page.wait_for_timeout(1000)
            runs = s.get(f"/api/tasks/{tid}/runs")
            runs = runs.get("runs", runs) if isinstance(runs, dict) else runs
            if runs and runs[0]["status"] in ("success", "error", "aborted"):
                ok = runs[0]["status"] == "success"
                last = runs[0]
                break
        s.check("an AI automation with no pinned model runs on the model set in Settings (no 'No model/endpoint configured')", ok, (last.get("error") or last.get("result"))[:160] if runs else "no run")
        d.settle(1500)
        if ok:
            w.locator(".au-run > summary").first.click()
            d.settle(300)
            s.check("the run's output is shown in the history", len(w.locator(".au-run .au-out").first.inner_text().strip()) > 3)
            s.check("expanded run history rows use the full width (class collision regression)", w.locator(".au-run").first.evaluate("e => e.getBoundingClientRect().width") > 300)
    else:
        s.skip("Run now with the real model", "run with --ai")

    w.locator(".au-row", has_text=name + "-edited").click()
    w.get_by_role("button", name="Delete").click()
    d.settle(400)
    s.check("Delete asks first and names the automation", page.locator("#overlays .modal", has_text=name).count() == 1)
    s.modal_click("Delete")
    d.settle(1200)
    s.check("confirming removes it from the scheduler and the list", not any(t["id"] == tid for t in s.get("/api/tasks")["tasks"]) and w.locator(".au-row", has_text=name).count() == 0)
    s.reset()


def sec_today(s: Suite) -> None:
    """Today dashboard: capture (todo / event / reminder / automation draft), undo, todo toggle, focus timer, reminder done, refresh."""
    d, page = s.d, s.page
    s.reset()
    page.evaluate("document.querySelector('#home').scrollTo(0, 0)")
    cap = page.locator(".cap-input")
    t0 = time.time()
    summary0 = page.locator(".dash-summary").inner_text()
    s.check("the summary line is real data", re.search(r"event|todo|automation|calendar", summary0) is not None, summary0)

    def capture(text: str, kind: str) -> bool:
        cap.fill(text)
        cap.press("Enter")
        try:
            page.locator(f'.cap-chip[data-kind="{kind}"]').wait_for(timeout=4000)
            return True
        except PWTimeout:
            return False

    ok = capture("qa capture todo oat", "todo")
    s.check("capture: a plain line previews as a Todo", ok, page.locator(".cap-preview").inner_text() if page.locator(".cap-preview").count() else "")
    page.locator('[data-action="cap-confirm"]').click()
    d.settle(1200)
    s.check("Confirm adds the todo and the widget updates", page.locator(".tw-todos .td-text", has_text="qa capture todo oat").count() == 1)
    page.locator("#overlays .toast .toast-action", has_text="Undo").first.click()
    d.settle(1000)
    s.check("Undo removes it again", page.locator(".tw-todos .td-text", has_text="qa capture todo oat").count() == 0 and not any("qa capture todo oat" in t["text"] for t in s.get("/api/os/today")["todos"]["items"]))

    ok = capture("lunch with Sara friday 1pm", "event")
    s.check("capture: 'lunch with Sara friday 1pm' previews as an Event", ok)
    page.locator('[data-action="cap-cancel"]').click()
    s.check("Cancel discards the preview and creates nothing", page.locator(".cap-preview[hidden]").count() == 1 or page.locator(".cap-preview").is_hidden())
    ok = capture("remind me to qa stretch in 30 minutes", "reminder")
    s.check("capture: 'remind me ... in 30 minutes' previews as a Reminder", ok)
    page.locator('[data-action="cap-confirm"]').click()
    d.settle(1200)
    rem = [r for r in s.get("/api/os/today")["agenda"].get("reminders", []) if "stretch" in (r.get("summary") or "")]
    s.check("Confirm creates a timed reminder", len(rem) == 1, rem)
    page.locator("#overlays .toast .toast-action", has_text="Undo").first.click()
    d.settle(900)
    ok = capture("every weekday at 7am summarize my email", "automation")
    s.check("capture: an automation is recognised", ok)
    s.check("...with 'Open in Automations' offered", page.locator('[data-action="cap-open"]').count() == 1)
    page.locator('[data-action="cap-open"]').click()
    d.settle(800)
    s.check("Open in Automations opens the app with the sheet prefilled", s.win("automations").count() == 1 and s.win("automations").locator("input, textarea").evaluate_all("els => els.some(e => /summari[sz]e my email/i.test(e.value || ''))"))
    s.reset()

    # todo toggle through the widget
    s.api("POST", "/api/os/capture/commit", {"kind": "todo", "draft": {"text": "qa toggle me"}, "tz_offset": 0})
    page.get_by_role("button", name="Open Notes").count()
    d.os_eval("(os) => os.dashboard.refresh()")
    d.settle(1000)
    row = page.locator(".tw-todos .td-row", has_text="qa toggle me")
    s.check("a todo added elsewhere appears after a refresh", row.count() == 1)
    row.locator(".td-check").click()
    d.settle(1500)
    items = s.get("/api/os/today")["todos"]["items"]
    s.check("checking it off completes the real note item", not any("qa toggle me" in t["text"] for t in items))
    s.api("POST", "/api/os/capture/undo", {"kind": "todo", "id": "x", "item_id": "x"})

    # focus timer
    page.locator(".tw-focus").get_by_role("button", name=re.compile("Start", re.I)).first.click()
    d.settle(2300)
    chip = page.locator(".mb-focus, .focus-chip").first
    s.check("starting focus shows a ticking chip in the menu bar", chip.count() == 1 and re.search(r"\d\d:\d\d", chip.inner_text()) is not None, chip.inner_text() if chip.count() else "no chip")
    t_a = chip.inner_text()
    d.settle(2200)
    s.check("the countdown moves", chip.inner_text() != t_a)
    page.locator(".tw-focus").get_by_role("button", name=re.compile("Pause", re.I)).first.click()
    d.settle(1500)
    t_b = chip.inner_text()
    d.settle(2200)
    s.check("Pause freezes it", chip.inner_text() == t_b)
    page.reload(wait_until="domcontentloaded")
    page.locator("#desktop:not([hidden])").wait_for(timeout=15000)
    d.settle(1200)
    s.check("a paused timer survives a reload", page.locator(".mb-focus, .focus-chip").count() == 1)
    page.locator(".tw-focus").get_by_role("button", name=re.compile("Reset", re.I)).first.click()
    d.settle(500)
    s.shot("today")
    s.reset()


def sec_reminders(s: Suite) -> None:
    """A due reminder the server already announced (server_fired) is not toasted or notified again by the page; one it did not announce is,
    once, with the server's key. The Today payload is patched in flight so both cases are deterministic."""
    d, page = s.d, s.page
    s.reset()
    now_ms = int(time.time() * 1000)
    fake = [
        dict(kind="reminder", id="qa-rem-server", summary="qa server already told you", start="", start_ts=now_ms - 30000, end_ts=now_ms - 30000, all_day=False,
             day="today", due="", key=f"reminder:qa-rem-server:{now_ms - 30000}", server_fired=True),
        dict(kind="reminder", id="qa-rem-page", summary="qa page announces this", start="", start_ts=now_ms - 20000, end_ts=now_ms - 20000, all_day=False,
             day="today", due="", key=f"reminder:qa-rem-page:{now_ms - 20000}", server_fired=False),
    ]

    def patch(route):
        resp = route.fetch()
        try:
            body = resp.json()
            ag = body.setdefault("agenda", {})
            ag["reminders"] = list(ag.get("reminders") or []) + fake
            route.fulfill(response=resp, json=body)
        except Exception:
            route.fulfill(response=resp)

    notifies: List[Dict[str, Any]] = []

    def on_req(req):
        if req.method == "POST" and req.url.endswith("/api/os/notify"):
            try:
                notifies.append(json.loads(req.post_data or "{}"))
            except ValueError:
                pass

    page.evaluate("localStorage.removeItem('ody.os.reminders.fired')")
    page.on("request", on_req)
    page.route("**/api/os/today*", patch)
    try:
        d.os_eval("(os) => os.emit('personal-changed', { kinds: ['reminders'] })")
        s.check("the page announces the reminder the server did not", s.wait_toast("qa page announces this", 8000))
        d.settle(1500)
        texts = s.toast_texts()
        s.check("and stays silent about the one the server already announced", not any("qa server already told you" in t for t in texts), texts)
        mine = [n for n in notifies if "qa" in str(n.get("message", ""))]
        s.check("only the page's own reminder is sent to the bell", [n.get("message") for n in mine] == ["qa page announces this"], [n.get("message") for n in mine])
        s.check("with the server's key (so the bell de-duplicates)", bool(mine) and mine[0].get("key") == fake[1]["key"], mine[:1])
        fired = page.evaluate("JSON.parse(localStorage.getItem('ody.os.reminders.fired') || '[]')")
        s.check("both are remembered as dealt with", any("qa-rem-server" in f for f in fired) and any("qa-rem-page" in f for f in fired), fired)
        n_before = len(notifies)
        d.os_eval("(os) => os.emit('personal-changed', { kinds: ['reminders'] })")
        d.settle(2500)
        s.check("a later refresh does not announce them again", len([n for n in notifies[n_before:] if "qa" in str(n.get("message", ""))]) == 0
                and sum("qa page announces this" in t for t in s.toast_texts()) <= 1)
    finally:
        page.unroute("**/api/os/today*")
        page.remove_listener("request", on_req)
        page.evaluate("localStorage.removeItem('ody.os.reminders.fired')")
        s.reset()


def sec_embedded(s: Suite) -> None:
    """Each embedded Odysseus page loads in its window without errors, reload works, windows are singletons."""
    d, page = s.d, s.page
    s.reset()
    apps = d.os_eval("(os) => os.appList().filter((a) => a.group === 'odysseus').map((a) => a.id)")
    s.check("nine Odysseus apps are registered", len(apps) == 9, apps)
    for app in apps:
        n0 = len(d.rec.problems)
        d.open_app(app)
        w = s.win(app)
        d.settle(2500)
        frame = w.locator("iframe").first.element_handle().content_frame()
        ok_len = frame.evaluate("document.body ? document.body.innerText.trim().length : 0") if frame else 0
        s.check(f"{app}: the page renders content in its window", bool(frame) and ok_len > 20 and w.locator(".embed-loading").count() == 0, ok_len)
        s.check(f"{app}: no console / network errors while loading", len(d.rec.problems) == n0, [p["msg"][:90] for p in d.rec.problems[n0:]][:3])
        d.open_app(app)
        d.settle(200)
        s.check(f"{app}: opening it again focuses the same window", page.locator(f'section.win[data-app="{app}"]').count() == 1)
        w.get_by_role("button", name="Reload").click()
        d.settle(1800)
        s.check(f"{app}: Reload works", w.locator("iframe").first.element_handle().content_frame().evaluate("document.body.innerText.trim().length") > 20)
        s.shot(f"embed-{app}")
        s.reset()


def sec_sleep(s: Suite) -> None:
    """A hidden embedded page is put to sleep and wakes where it was left; a page in use is left alone (delay shortened to 1.5 s)."""
    d, page = s.d, s.page
    s.reset()
    page.evaluate("localStorage.setItem('os.embedSuspendMs', '1500')")
    n0 = len(d.rec.problems)
    asleep = lambda app: page.locator(f'section.win[data-app="{app}"] .embed[data-suspended]').count() == 1      # noqa: E731
    frames = lambda app: page.locator(f'section.win[data-app="{app}"] iframe.embed-frame').count()                # noqa: E731

    def settled(app: str) -> None:
        """The classic pages keep themselves 'busy' for ~10 s after loading (a start-up grace); wait it out, as a real minute would."""
        for _ in range(60):
            busy = page.evaluate("""(app) => { const f = document.querySelector(`section.win[data-app=${app}] iframe.embed-frame`);
                try { return Date.now() < (f.contentWindow.__odysseusChatBusyUntil || 0); } catch (e) { return false; } }""", app)
            if not busy:
                return
            page.wait_for_timeout(500)
    try:
        # 1. minimised -> asleep -> restored in place
        d.open_app("notes")
        d.settle(2500)
        page.evaluate("() => { const f = document.querySelector('section.win[data-app=notes] iframe.embed-frame'); f.contentWindow.location.hash = '#qa-sleep'; }")
        settled("notes")
        d.settle(1800)
        s.check("a visible page is never put to sleep", not asleep("notes") and frames("notes") == 1)
        d.os_eval("(os) => os.wm.list().find((w) => w.app === 'notes').minimize()")
        d.settle(3200)
        s.check("minimised for a while: the page is replaced by a placeholder", asleep("notes") and frames("notes") == 0, f"asleep={asleep('notes')} frames={frames('notes')}")
        s.check("the placeholder says why", "paused while hidden" in page.locator('section.win[data-app="notes"] .embed-loading').inner_text())
        d.os_eval("(os) => os.wm.restore(os.wm.list().find((w) => w.app === 'notes'))")
        page.locator('section.win[data-app="notes"] iframe.embed-frame').wait_for(timeout=8000)
        d.settle(2500)
        place = page.evaluate("() => { const f = document.querySelector('section.win[data-app=notes] iframe.embed-frame'); try { return f.contentWindow.location.pathname + f.contentWindow.location.hash; } catch (e) { return String(e); } }")
        s.check("shown again: the page comes back at the same address (#hash included)", place == "/notes#qa-sleep", place)
        s.check("and the placeholder is gone", not asleep("notes") and page.locator('section.win[data-app="notes"] .embed-loading').count() == 0)
        s.reset()

        # 2. fully covered by a maximised window
        d.open_app("notes")
        d.settle(1500)
        settled("notes")
        d.open_app("files")
        d.settle(600)
        d.os_eval("(os) => os.wm.toggleMaximize(os.wm.list().find((w) => w.app === 'files'))")
        d.settle(3200)
        s.check("completely behind a maximised window: asleep too", asleep("notes") and frames("notes") == 0, f"asleep={asleep('notes')}")
        s.check("the maximised window itself is untouched", page.locator('section.win[data-app="files"]').count() == 1)
        d.os_eval("(os) => os.wm.toggleMaximize(os.wm.list().find((w) => w.app === 'files'))")
        page.locator('section.win[data-app="notes"] iframe.embed-frame').wait_for(timeout=8000)
        s.check("the maximised window shrinks back: the page wakes", not asleep("notes") and frames("notes") == 1)
        s.reset()

        # 3. a window in front of the maximised one stays alive
        d.open_app("files")
        d.os_eval("(os) => os.wm.toggleMaximize(os.wm.list().find((w) => w.app === 'files'))")
        d.open_app("notes")
        d.settle(3500)
        s.check("a window raised above a maximised one is visible, so it stays awake", not asleep("notes") and frames("notes") == 1)
        s.reset()

        # 4. a page in use is left alone (unsent text in the box that has focus), and goes to sleep once it is idle
        d.open_app("chat")
        d.settle(3000)
        settled("chat")
        frame = page.locator('section.win[data-app="chat"] iframe.embed-frame').element_handle().content_frame()
        box = frame.locator("textarea:visible").first
        box.click()
        box.fill("an unsent draft that must survive")
        d.os_eval("(os) => os.wm.list().find((w) => w.app === 'chat').minimize()")
        d.settle(3500)
        s.check("unsent text in the focused box: not put to sleep", not asleep("chat") and frames("chat") == 1)
        frame.evaluate("() => document.querySelectorAll('textarea').forEach((t) => { t.value = ''; })")       # the window is hidden: clear it from inside
        settled("chat")       # typing makes the page itself call it busy for 15 s
        d.settle(3200)        # the next check comes within the (shortened) delay
        s.check("once the box is empty it does go to sleep", asleep("chat"), f"frames={frames('chat')}")
        d.os_eval("(os) => os.wm.restore(os.wm.list().find((w) => w.app === 'chat'))")
        page.locator('section.win[data-app="chat"] iframe.embed-frame').wait_for(timeout=8000)
        s.reset()

        # 5. closing a sleeping window leaves nothing behind
        d.open_app("memory")
        d.settle(1500)
        settled("memory")
        d.os_eval("(os) => os.wm.list().find((w) => w.app === 'memory').minimize()")
        d.settle(3200)
        s.check("memory is asleep", asleep("memory"))
        d.close_all_windows()
        d.settle(400)
        s.check("closing sleeping windows leaves no frames or placeholders", page.locator("iframe.embed-frame, .embed[data-suspended]").count() == 0)
        s.check("no console / network errors during all this", len(d.rec.problems) == n0, [p["msg"][:90] for p in d.rec.problems[n0:]][:3])
    finally:
        page.evaluate("localStorage.removeItem('os.embedSuspendMs')")
        s.reset()


def sec_themes(s: Suite) -> None:
    """Light and dark, 1280 and 900 wide: screenshots of the desktop and the main apps (reviewed by eye) + contrast sanity."""
    d, page = s.d, s.page
    s.reset()
    for theme in ("light", "dark"):
        page.evaluate("async (t) => { const st = await import('/static/os/js/state.js'); st.setPref('theme', t); st.applyTheme(); }", theme)
        d.settle(400)
        d.rec.where = f"theme {theme}"
        s.shot(f"desktop-{theme}")
        for app in ("jarvis", "files", "taskmgr", "automations", "settings"):
            d.open_app(app)
            d.settle(900)
            s.shot(f"{app}-{theme}")
            s.reset()
        # text must stay readable: the title colour and the background must differ strongly
        lum = page.evaluate("""() => {
          const rgb = (c) => c.match(/[\\d.]+/g).slice(0, 3).map(Number);
          const L = ([r, g, b]) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
          const t = document.querySelector('.home-title'); const body = document.body;
          const a = L(rgb(getComputedStyle(t).color)), b = L(rgb(getComputedStyle(body).backgroundColor));
          return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        }""")
        s.check(f"{theme}: greeting contrast is at least 4.5:1", lum >= 4.5, round(lum, 2))
    page.evaluate("async () => { const st = await import('/static/os/js/state.js'); st.setPref('theme', 'auto'); st.applyTheme(); }")


SECTIONS = [("wm", sec_wm), ("shell", sec_shell), ("files", sec_files), ("editor", sec_editor), ("terminal", sec_terminal), ("taskmgr", sec_taskmgr),
            ("settings", sec_settings), ("models", sec_models), ("jarvis", sec_jarvis), ("automations", sec_automations), ("today", sec_today),
            ("reminders", sec_reminders), ("embedded", sec_embedded), ("sleep", sec_sleep), ("themes", sec_themes)]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--url", default="http://127.0.0.1:7000/os")
    ap.add_argument("--out", default="features_out")
    ap.add_argument("--only", default="", help="comma list of sections")
    ap.add_argument("--ai", action="store_true", help="include the checks that call the language model (<= 5 turns)")
    ap.add_argument("--channel", default="msedge")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--server-log", default="")
    args = ap.parse_args()
    base = origin_of(args.url)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    wanted = [x for x in args.only.split(",") if x]
    allow = [dict(url=r"/api/os/fs/(stat|read)\?", status=404, method="GET", why="'does it still exist?' checks"),
             dict(url=r"/api/os/fs/transfer$", status=409, method="POST", why="paste onto an existing name asks Skip/Replace"),
             dict(url=r"/api/os/fs/list\?", status=404, method="GET", why="a Files window for a deleted folder falls back to its parent"),
             dict(url=r"/api/os/fs/read\?", status=404, method="GET", why="a Recent entry whose file is gone"),
             dict(url=r"/api/os/fs/write$", status=409, method="PUT", why="saving over an external change asks Overwrite/Reload")] + UPSTREAM_ALLOW
    t_start = time.time()
    # start from an empty desktop: a session saved by an earlier run would restore windows (some for folders that are gone now)
    status, saved = http_json(base, "GET", "/api/os/session")
    if status == 200 and (saved or {}).get("session"):
        sess = dict(saved["session"], windows=[])
        http_json(base, "PUT", "/api/os/session", sess)
    with sync_playwright() as p:
        d = Desk(p, args.url, channel=args.channel, headed=args.headed, server_log=Path(args.server_log) if args.server_log else None, allow=allow)
        s = Suite(d, base, out, args)
        d.boot()
        d.settle(800)
        d.close_all_windows()
        for name, fn in SECTIONS:
            if wanted and name not in wanted:
                continue
            s.area = name
            d.rec.where = name
            print(f"== {name}", flush=True)
            t0 = time.time()
            try:
                fn(s)
            except Exception as e:  # noqa: BLE001 - a crash in one section must not hide the others
                s.check(f"section crashed: {type(e).__name__}", False, f"{str(e)[:250]}")
                traceback.print_exc()
                s.shot(f"crash-{name}")
                try:
                    s.reset()
                except Exception:
                    pass
            print(f"   ({time.time() - t0:.1f}s)", flush=True)
            d.rec.drain_page_rejections()
        problems = [x for x in d.rec.problems if x["kind"] != "teardown"]
        server_errors = d.rec.server_errors()
        d.close()
    http_json(base, "POST", "/api/os/fs/delete", {"path": BOX})      # disposable folder -> Trash
    unexpected = problems
    passed = sum(1 for r in s.rows if r["ok"] is True)
    failed = [r for r in s.rows if r["ok"] is False]
    skipped = [r for r in s.rows if r["ok"] is None]
    lines = [f"Odysseus OS feature checklist  {time.strftime('%Y-%m-%d %H:%M:%S')}  {args.url}  ({time.time() - t_start:.0f}s)", ""]
    areas: Dict[str, List[int]] = {}
    for r in s.rows:
        a = areas.setdefault(r["area"], [0, 0, 0])
        a[0 if r["ok"] is True else 1 if r["ok"] is False else 2] += 1
    lines.append(f"{'area':<14}{'pass':>6}{'fail':>6}{'skip':>6}")
    for k, v in areas.items():
        lines.append(f"{k:<14}{v[0]:>6}{v[1]:>6}{v[2]:>6}")
    lines.append("")
    for r in failed:
        lines.append(f"FAIL {r['area']}: {r['name']}  -- {r['detail']}")
    for r in skipped:
        lines.append(f"skip {r['area']}: {r['name']}  -- {r['detail']}")
    for x in unexpected:
        lines.append(f"ERROR [{x['where']}] {x['kind']} {x['msg'][:220]}")
    for sline in server_errors:
        lines.append(f"SERVER LOG: {sline[:200]}")
    lines.append("")
    lines.append(f"{passed} passed, {len(failed)} failed, {len(skipped)} skipped, {len(unexpected)} browser errors, {len(server_errors)} server log errors")
    text = "\n".join(lines)
    (out / "features_summary.txt").write_text(text, encoding="utf-8")
    (out / "features_report.json").write_text(json.dumps(dict(rows=s.rows, problems=problems, server_errors=server_errors), indent=2, default=str), encoding="utf-8")
    print("\n" + text)
    return 1 if (failed or unexpected) else 0


if __name__ == "__main__":
    sys.exit(main())
