"""Static guard for the desktop's stylesheets (no browser needed).

QA found `.au-run { width: 26px }` in dashboard.css (the dashboard's "run now" button) silently squeezing the
Automations app's run-history rows (`<details class="au-run">`) to 26 px. Per-component class names must not be defined
by two different stylesheets: every sheet below owns its prefix, and the few shared names are listed explicitly.
"""

import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "static" / "os"
SHEETS = ["os.css", "apps.css", "jarvis.css", "models.css", "automations.css", "dashboard.css", "net.css"]
# deliberately layered on top of another sheet's rule (a modifier or an override), reviewed by hand
SHARED = {"dot", "home-actions", "home-recent", "home-sub", "mb-pulse", "win", "is-approved", "is-denied", "is-expired"}


def _classes(sheet: str):
    text = re.sub(r"/\*.*?\*/", "", (CSS / sheet).read_text(encoding="utf-8"), flags=re.S)
    found = set()
    for m in re.finditer(r"([^{};]+)\{", text):
        for sel in m.group(1).split(","):
            c = re.match(r"\s*\.([A-Za-z0-9_-]+)", sel)
            if c and not sel.strip().startswith("@"):
                found.add(c.group(1))
    return found


def test_no_class_is_styled_by_two_different_sheets():
    owner = {}
    clashes = {}
    for sheet in SHEETS:
        for cls in _classes(sheet):
            if cls in owner and owner[cls] != sheet and cls not in SHARED:
                clashes[cls] = (owner[cls], sheet)
            owner.setdefault(cls, sheet)
    assert not clashes, f"class names styled by two sheets (one leaks into the other's component): {clashes}"


def test_the_dashboard_run_button_does_not_use_the_automations_run_class():
    js = (CSS / "js" / "dashboard" / "automations.js").read_text(encoding="utf-8")
    assert not re.search(r"['\"\s]au-(run|row)\b", js), "dashboard widget classes must be prefixed dau-, not au- (that is the Automations app)"
