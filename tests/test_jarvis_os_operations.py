"""Jarvis OSOperations: sandboxed file + command execution used by the agents and legacy API."""

import os
import subprocess
import sys

import pytest

from JARVIS.os_integration.os_operations import OSOperations
from services.os_shell.fs import FileSystem
from services.os_shell.sandbox import Sandbox

pytestmark = pytest.mark.area_security

PY = f'"{sys.executable}"'


def _link_dir(link, target):
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        if os.name != "nt":
            raise
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("cannot create link on this machine")


@pytest.fixture
def ops(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    sb = Sandbox()
    sb.add_mount("Home", str(home))
    fs = FileSystem(sb, tmp_path / "trash")
    return OSOperations(fs=fs), home, tmp_path


# ------------------------------------------------------------------ confinement
def test_nothing_is_reachable_until_a_folder_is_mounted(tmp_path):
    """Regression: 'no allowed paths configured' used to mean 'allow everything'."""
    secret = tmp_path / "secret.txt"
    secret.write_text("s3cret")
    bare = OSOperations()
    assert bare.read_file(str(secret)).success is False
    assert bare.write_file(str(tmp_path / "x.txt"), "x").success is False
    assert bare.list_directory(str(tmp_path)).success is False
    assert bare.execute_command("echo hi").success is False  # no mount => no working directory


def test_sibling_folder_with_shared_prefix_is_not_allowed(tmp_path):
    safe, evil = tmp_path / "safe", tmp_path / "safe-evil"
    safe.mkdir()
    evil.mkdir()
    (evil / "loot.txt").write_text("loot")
    o = OSOperations()
    o.add_allowed_path(str(safe))
    assert o.is_path_allowed(str(safe / "ok.txt"))
    assert not o.is_path_allowed(str(evil / "loot.txt"))
    assert o.read_file(str(evil / "loot.txt")).success is False


def test_link_inside_a_mount_cannot_be_used_to_read_outside(ops):
    o, home, tmp = ops
    outside = tmp / "outside"
    outside.mkdir()
    (outside / "x.txt").write_text("x")
    _link_dir(home / "door", outside)
    assert o.read_file(str(home / "door" / "x.txt")).success is False
    assert o.read_file("/Home/door/x.txt").success is False


def test_add_allowed_path_is_idempotent_and_honours_read_only(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    (ro / "f.txt").write_text("f")
    o = OSOperations()
    o.add_allowed_path(str(ro), read_only=True)
    o.add_allowed_path(str(ro), read_only=True)
    assert len(o.sandbox.mounts) == 1
    assert o.read_file(str(ro / "f.txt")).success
    w = o.write_file(str(ro / "f.txt"), "tampered")
    assert w.success is False and "read-only" in w.error
    assert (ro / "f.txt").read_text() == "f"


def test_virtual_paths_work_and_results_report_both_forms(ops):
    o, home, _ = ops
    assert o.write_file("/Home/a.txt", "hello").success
    r = o.read_file("/Home/a.txt")
    assert r.success and r.data["content"] == "hello"
    assert r.data["virtual_path"] == "/Home/a.txt"
    assert r.data["path"] == str(home / "a.txt")


# ---------------------------------------------------------------------- files
def test_write_is_atomic_creates_dirs_and_leaves_no_temp_files(ops):
    o, home, _ = ops
    r = o.write_file("/Home/deep/er/f.txt", "x")
    assert r.success
    assert [p.name for p in (home / "deep" / "er").iterdir()] == ["f.txt"]
    assert o.write_file("/Home/nope/f.txt", "x", create_dirs=False).success is False


def test_cannot_write_to_a_mount_root_or_over_a_directory(ops):
    o, home, _ = ops
    (home / "d").mkdir()
    assert o.write_file("/Home", "x").success is False
    assert o.write_file("/Home/d", "x").success is False


def test_read_errors_are_results_not_exceptions(ops):
    o, home, _ = ops
    (home / "bin.dat").write_bytes(b"\xff\xfe\x00\x80")
    assert o.read_file("/Home/missing.txt").success is False
    assert o.read_file("/Home").success is False
    r = o.read_file("/Home/bin.dat")
    assert r.success is False and r.error


def test_history_keeps_summaries_not_file_contents(ops):
    o, home, _ = ops
    (home / "big.txt").write_text("PAYLOAD" * 1000)
    o.read_file("/Home/big.txt")
    entry = o.get_operation_history()[-1]
    assert entry.operation == "read_file"
    assert "PAYLOAD" not in str(entry.to_dict())


def test_history_is_bounded(ops):
    o, *_ = ops
    for _ in range(700):
        o.read_file("/Home/missing")
    assert len(o.operation_history) == 500


def test_search_and_listing(ops):
    o, home, _ = ops
    (home / "sub").mkdir()
    (home / "sub" / "a.py").write_text("1")
    (home / "b.txt").write_text("2")
    found = o.search_files("/Home", "*.py")
    assert [m["name"] for m in found.data["matches"]] == ["a.py"]
    listed = o.list_directory("/Home")
    assert sorted(i["name"] for i in listed.data["items"]) == ["b.txt", "sub"]
    recursive = o.list_directory("/Home", recursive=True)
    assert recursive.data["count"] == 3


def test_search_hides_links_that_leave_every_mount(ops):
    o, home, tmp = ops
    outside = tmp / "outside"
    outside.mkdir()
    (outside / "leak.py").write_text("x")
    _link_dir(home / "door", outside)
    names = [m["name"] for m in o.search_files("/Home", "*.py").data["matches"]]
    assert "leak.py" not in names


def test_delete_goes_to_trash_when_filesystem_is_attached(ops):
    o, home, _ = ops
    (home / "f.txt").write_text("keep")
    r = o.delete_file("/Home/f.txt")
    assert r.success and r.data["recoverable"] is True
    assert not (home / "f.txt").exists()
    o.fs.trash_restore(r.data["trash_id"])
    assert (home / "f.txt").read_text() == "keep"


def test_delete_without_trash_is_permanent_for_files_and_refuses_folders(tmp_path):
    d = tmp_path / "d"
    d.mkdir()
    (d / "f.txt").write_text("x")
    (d / "sub").mkdir()
    o = OSOperations()
    o.add_allowed_path(str(d))
    assert o.delete_file(str(d / "f.txt")).success
    assert not (d / "f.txt").exists()
    assert o.delete_file(str(d / "sub")).success is False
    assert (d / "sub").exists()


def test_deleting_a_mount_root_is_refused(ops):
    o, home, _ = ops
    assert o.delete_file("/Home").success is False
    assert home.exists()


def test_file_info(ops):
    o, home, _ = ops
    (home / "f.txt").write_text("abc")
    info = o.get_file_info("/Home/f.txt")
    assert info.success and info.data["size"] == 3 and info.data["type"] == "file"


def test_result_dict_shape_is_unchanged_for_legacy_callers(ops):
    o, *_ = ops
    d = o.read_file("/Home/missing").to_dict()
    assert set(d) == {"success", "operation", "data", "error", "timestamp"}


# ------------------------------------------------------------------ commands
def test_commands_run_in_home_by_default_and_capture_output(ops):
    o, home, _ = ops
    r = o.execute_command(f'{PY} -c "import os; print(os.getcwd())"')
    assert r.success, r.error
    assert os.path.realpath(r.data["stdout"].strip()) == os.path.realpath(str(home))


def test_working_dir_must_be_inside_a_mount(ops):
    o, home, tmp = ops
    (home / "d").mkdir()
    assert o.execute_command("echo hi", working_dir="/Home/d").success
    outside = o.execute_command("echo hi", working_dir=str(tmp))
    assert outside.success is False


def test_catastrophic_commands_are_refused_without_running(ops):
    o, home, _ = ops
    marker = home / "survived.txt"
    marker.write_text("x")
    r = o.execute_command("rm -rf /")
    assert r.success is False and "blocked" in r.error
    assert marker.exists()


def test_ordinary_commands_the_old_blocklist_refused_now_work(ops):
    o, *_ = ops
    # 'information' contains the old blocklist's 'format'; 'add' contains its 'dd'
    assert o.execute_command("echo information add").success


def test_nonzero_exit_is_a_failed_result_with_stderr(ops):
    o, *_ = ops
    r = o.execute_command(f'{PY} -c "import sys; sys.stderr.write(\'oops\'); sys.exit(3)"')
    assert r.success is False and "oops" in r.error
    assert r.data["return_code"] == 3


def test_timeout_is_reported_and_the_command_is_killed(ops):
    o, *_ = ops
    r = o.execute_command(f'{PY} -c "import time; time.sleep(60)"', timeout=1)
    assert r.success is False and "timed out" in r.error


# ---------------------------------------------------------------------- audit
def test_mutating_operations_are_audited_and_reads_are_not(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    sb = Sandbox()
    sb.add_mount("Home", str(home))
    events = []
    o = OSOperations(fs=FileSystem(sb, tmp_path / "t"), audit=lambda e, d: events.append((e, d)))
    o.write_file("/Home/a.txt", "x")
    o.read_file("/Home/a.txt")
    o.create_directory("/Home/d")
    o.delete_file("/Home/a.txt")
    o.execute_command("echo hi")
    assert [e for e, _ in events] == ["write_file", "create_directory", "delete_file", "execute_command"]


def test_a_failing_audit_hook_never_breaks_the_operation(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    sb = Sandbox()
    sb.add_mount("Home", str(home))

    def boom(*_):
        raise RuntimeError("audit down")

    o = OSOperations(sandbox=sb, audit=boom)
    assert o.write_file("/Home/a.txt", "x").success
