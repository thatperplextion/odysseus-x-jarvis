"""Streaming terminal executor, exercised against the real shells on this machine."""

import asyncio
import os
import sys
import time

import psutil
import pytest

from services.os_shell import terminal

SHELLS = [s["id"] for s in terminal.available_shells()]
pytestmark = pytest.mark.skipif(not SHELLS, reason="no shell available")

# Per-family snippets: (echo unicode, print cwd, exit with 3, sleep seconds-ish long, tick twice)
CMDS = {
    "powershell": dict(
        uni="Write-Output 'héllo ✓ 日本'", pwd="(Get-Location).Path", fail="cmd /c exit 3",
        sleep="Start-Sleep 30", ticks="Write-Output tick1; Start-Sleep -Milliseconds 900; Write-Output tick2",
        err="Write-Output before; Write-Error boom; Write-Output after"),
    "cmd": dict(
        uni="echo héllo ✓ 日本", pwd="cd", fail="cmd /c exit 3",
        sleep="ping -n 30 127.0.0.1 >nul", ticks="echo tick1 & ping -n 2 127.0.0.1 >nul & echo tick2",
        err=None),
    "posix": dict(
        uni="echo 'héllo ✓ 日本'", pwd="pwd", fail="(exit 3)",
        sleep="sleep 30", ticks="echo tick1; sleep 1; echo tick2",
        err="echo before; echo boom 1>&2; echo after"),
}
CMDS["pwsh"] = CMDS["powershell"]


def snippets(shell):
    return CMDS.get(shell, CMDS["posix"])


async def run(shell, command, cwd, timeout=60):
    events = []
    async for ev in terminal.stream_command(command, cwd, shell, timeout=timeout):
        events.append(ev)
    out = "".join(e["d"] for e in events if e["t"] == "out")
    return out, events[-1], events


@pytest.fixture
def home(tmp_path):
    d = tmp_path / "start"
    d.mkdir()
    (tmp_path / "start" / "sub").mkdir()
    return str(d)


@pytest.mark.parametrize("shell", SHELLS)
async def test_unicode_output_survives(shell, home):
    out, exit_ev, _ = await run(shell, snippets(shell)["uni"], home)
    assert "héllo ✓ 日本" in out
    assert exit_ev["code"] == 0


@pytest.mark.parametrize("shell", SHELLS)
async def test_exit_code_is_reported(shell, home):
    _, exit_ev, _ = await run(shell, snippets(shell)["fail"], home)
    assert exit_ev["code"] == 3


@pytest.mark.parametrize("shell", SHELLS)
async def test_cd_is_tracked_so_the_next_command_starts_there(shell, home):
    _, first, _ = await run(shell, "cd sub", home)
    assert os.path.basename(first["cwd"]) == "sub"
    out, second, _ = await run(shell, snippets(shell)["pwd"], first["cwd"])
    assert out.strip().replace("\\", "/").rstrip("/").endswith("/sub")
    assert os.path.basename(second["cwd"]) == "sub"


@pytest.mark.parametrize("shell", SHELLS)
async def test_the_cwd_sentinel_never_leaks_into_output(shell, home):
    out, exit_ev, events = await run(shell, snippets(shell)["uni"], home)
    assert "@@ODY" not in out and ";;" not in out
    assert all("@@ODY" not in e.get("d", "") for e in events)


@pytest.mark.parametrize("shell", SHELLS)
async def test_output_streams_while_the_command_is_still_running(shell, home):
    stamps = []
    started = time.monotonic()
    async for ev in terminal.stream_command(snippets(shell)["ticks"], home, shell):
        if ev["t"] == "out" and "tick1" in ev["d"]:
            stamps.append(time.monotonic() - started)
        if ev["t"] == "exit":
            total = time.monotonic() - started
    assert stamps, "tick1 never arrived"
    assert stamps[0] < total - 0.4, f"tick1 only arrived at {stamps[0]:.2f}s of {total:.2f}s: output is buffered"


@pytest.mark.parametrize("shell", SHELLS)
async def test_timeout_kills_the_command_quickly(shell, home):
    started = time.monotonic()
    _, exit_ev, _ = await run(shell, snippets(shell)["sleep"], home, timeout=1.5)
    assert exit_ev["timeout"] is True and exit_ev["code"] is None
    assert time.monotonic() - started < 8, "command outlived its timeout"


@pytest.mark.parametrize("shell", SHELLS)
async def test_closing_the_stream_kills_the_process_tree(shell, home):
    gen = terminal.stream_command(snippets(shell)["sleep"], home, shell, timeout=60)
    start = await gen.__anext__()
    await asyncio.sleep(0.7)
    await gen.aclose()
    await asyncio.sleep(0.5)
    assert not psutil.pid_exists(start["pid"])
    assert terminal._active == 0


@pytest.mark.parametrize("shell", [s for s in SHELLS if snippets(s)["err"]])
async def test_stderr_is_interleaved_in_order_and_is_plain_text(shell, home):
    out, _, _ = await run(shell, snippets(shell)["err"], home)
    assert out.index("before") < out.index("boom") < out.index("after")
    assert "CLIXML" not in out and "<Objs" not in out


async def test_powershell_errors_do_not_expose_the_temp_script_path(home):
    if "powershell" not in SHELLS:
        pytest.skip("no PowerShell")
    out, _, _ = await run("powershell", "Write-Error boom", home)
    assert "ody-term-" not in out and ".ps1" not in out.replace("<command>", "")


async def test_secrets_and_the_server_venv_are_not_inherited(monkeypatch, home):
    shell = SHELLS[0]
    monkeypatch.setenv("ODY_TEST_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("ODY_TEST_PASSWORD", "hunter2")
    monkeypatch.setenv("ODY_TEST_PLAIN", "visible")
    probe = {
        "powershell": "$env:ODY_TEST_API_KEY; $env:ODY_TEST_PASSWORD; $env:ODY_TEST_PLAIN",
        "pwsh": "$env:ODY_TEST_API_KEY; $env:ODY_TEST_PASSWORD; $env:ODY_TEST_PLAIN",
        "cmd": "echo [%ODY_TEST_API_KEY%][%ODY_TEST_PASSWORD%][%ODY_TEST_PLAIN%]",
    }.get(shell, "echo [$ODY_TEST_API_KEY][$ODY_TEST_PASSWORD][$ODY_TEST_PLAIN]")
    out, _, _ = await run(shell, probe, home)
    assert "sk-should-not-leak" not in out and "hunter2" not in out
    assert "visible" in out


def test_terminal_env_drops_secrets_and_the_venv(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("DB_PASSWORD", "x")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/agent.sock")
    monkeypatch.setenv("VIRTUAL_ENV", "/some/venv")
    monkeypatch.setenv("PYTHONPATH", "/some/path")
    env = terminal.terminal_env()
    for gone in ("OPENAI_API_KEY", "GITHUB_TOKEN", "DB_PASSWORD", "VIRTUAL_ENV", "PYTHONPATH"):
        assert gone not in env
    assert env["SSH_AUTH_SOCK"] == "/tmp/agent.sock"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["NO_COLOR"] == "1"


def test_terminal_env_removes_the_servers_own_venv_from_path(monkeypatch):
    if sys.prefix == getattr(sys, "base_prefix", sys.prefix):
        pytest.skip("not running inside a venv")
    venv_bin = os.path.join(sys.prefix, "Scripts" if os.name == "nt" else "bin")
    monkeypatch.setenv("PATH", venv_bin + os.pathsep + os.environ.get("PATH", ""))
    parts = terminal.terminal_env()["PATH"].split(os.pathsep)
    assert os.path.normcase(venv_bin) not in [os.path.normcase(p) for p in parts]


async def test_output_cap_truncates_and_kills(monkeypatch, home):
    shell = SHELLS[0]
    monkeypatch.setattr(terminal, "MAX_STREAM_BYTES", 2000)
    loop_cmd = {
        "powershell": "while ($true) { Write-Output ('x' * 500) }",
        "pwsh": "while ($true) { Write-Output ('x' * 500) }",
        "cmd": ":a\r\necho xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\r\ngoto a",
    }.get(shell, "while true; do echo xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx; done")
    started = time.monotonic()
    _, exit_ev, _ = await run(shell, loop_cmd, home, timeout=30)
    assert exit_ev["truncated"] is True
    assert time.monotonic() - started < 15


async def test_concurrency_is_capped(monkeypatch, home):
    shell = SHELLS[0]
    monkeypatch.setattr(terminal, "MAX_CONCURRENT", 1)
    first = terminal.stream_command(snippets(shell)["sleep"], home, shell, timeout=30)
    await first.__anext__()
    try:
        with pytest.raises(terminal.TerminalBusy):
            async for _ in terminal.stream_command("echo hi", home, shell):
                pass
    finally:
        await first.aclose()
    assert terminal._active == 0


async def test_bad_working_directory_and_unknown_shell_are_clean_errors(home):
    with pytest.raises(FileNotFoundError):
        async for _ in terminal.stream_command("echo hi", os.path.join(home, "nope"), SHELLS[0]):
            pass
    with pytest.raises(terminal.UnknownShell):
        async for _ in terminal.stream_command("echo hi", home, "definitely-not-a-shell"):
            pass
    assert terminal._active == 0


def test_available_shells_has_exactly_one_default():
    shells = terminal.available_shells()
    assert [s["default"] for s in shells].count(True) == 1
    assert terminal.default_shell_id() == shells[0]["id"]


# ------------------------------------------------------------- cmd "for %i" one-liners (found by the OS QA pass)
def test_cmd_for_variables_are_doubled_for_batch_files():
    f = terminal._cmd_batch_syntax
    assert f("for /L %i in (1,1,3) do @echo n%i") == "for /L %%i in (1,1,3) do @echo n%%i"
    assert f("for %f in (*.txt) do @echo %~nxf and %f") == "for %%f in (*.txt) do @echo %%~nxf and %%f"
    assert f('for /F "tokens=1" %a in (x.txt) do @echo %a') == 'for /F "tokens=1" %%a in (x.txt) do @echo %%a'
    # already batch syntax, environment variables and a loop-less line are left alone
    assert f("for %%i in (a b) do @echo %%i") == "for %%i in (a b) do @echo %%i"
    assert f("echo %PATH% %i") == "echo %PATH% %i"
    assert f("for %i in (a) do @echo %i%USERNAME%") == "for %%i in (a) do @echo %i%USERNAME%"      # %i% is a different (env) syntax


@pytest.mark.skipif("cmd" not in SHELLS, reason="no cmd.exe")
async def test_cmd_for_loop_with_a_single_percent_runs_like_at_a_prompt(home):
    out, exit_ev, _ = await run("cmd", "for /L %i in (1,1,3) do @echo n%i", home)
    assert [ln.strip() for ln in out.splitlines() if ln.strip()] == ["n1", "n2", "n3"], out
    assert exit_ev["code"] == 0
