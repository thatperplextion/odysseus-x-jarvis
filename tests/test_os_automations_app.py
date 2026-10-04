"""Odysseus OS Automations app: wiring checks plus the pure schedule maths (run under node).

The browser behaviour (templates, edit, run now, history, filters, keyboard, open args) was driven with
Playwright against a real server; these tests keep the cheap, deterministic parts from regressing.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
OS_DIR = ROOT / "static" / "os"
APP_DIR = OS_DIR / "js" / "apps"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_assistant_may_open_automations():
    from routes.os_routes import OS_APPS
    assert "automations" in OS_APPS


def test_app_is_registered_styled_and_pinned():
    main = _read(OS_DIR / "js" / "main.js")
    assert "import * as automationsApp from './apps/automations.js';" in main
    assert "register(automationsApp);" in main
    assert "/static/os/automations.css" in _read(OS_DIR / "index.html")
    state = _read(OS_DIR / "js" / "state.js")
    dock = re.search(r"dock:\s*\[([^\]]*)\]", state).group(1)
    assert "'automations'" in dock
    app = _read(APP_DIR / "automations.js")
    assert "id: 'automations'" in app and "singleton: true" in app
    assert "onReuse" in app          # open args reach an already-open window


def test_classic_tasks_page_stays_available_under_its_own_name():
    embeds = _read(APP_DIR / "odysseus.js")
    assert "id: 'tasks', name: 'Tasks (classic)'" in embeds


def test_no_innerhtml_or_eval_in_automations_code():
    files = [APP_DIR / "automations.js", *(APP_DIR / "automations").glob("*.js")]
    assert len(files) >= 5
    for f in files:
        text = _read(f)
        assert "innerHTML" not in text, f.name
        assert "eval(" not in text and "new Function" not in text, f.name
        assert "insertAdjacentHTML" not in text, f.name


def test_automations_use_only_the_scheduler_api():
    """It is a front-end for /api/tasks; it must not grow a scheduler of its own."""
    for f in (APP_DIR / "automations").glob("*.js"):
        for url in re.findall(r"['`\"](/api/[a-z\-/${}.A-Za-z]+)", _read(f)):
            assert url.startswith(("/api/tasks", "/api/model-endpoints")) or "${T}" in url, (f.name, url)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_schedule_maths_under_node():
    result = subprocess.run(
        ["node", "--no-warnings", str(ROOT / "tests" / "js" / "automations_schedule_check.mjs")],
        capture_output=True, text=True, timeout=60, cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert "all schedule checks passed" in result.stdout
