"""Path confinement for the OS shell sandbox (security regression tests)."""

import os
import subprocess

import pytest

from services.os_shell.sandbox import (
    InvalidPath,
    MountError,
    PathNotAllowed,
    ReadOnlyMount,
    Sandbox,
    SandboxConfig,
)

pytestmark = pytest.mark.area_security


def _link_dir(link, target):
    """Create a directory symlink (POSIX) or junction (Windows, no privilege needed)."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        if os.name != "nt":
            raise
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True
    )
    if result.returncode != 0:
        pytest.skip(f"cannot create link on this machine: {result.stderr.strip()}")


@pytest.fixture
def box(tmp_path):
    safe = tmp_path / "safe"
    safe.mkdir()
    (safe / "docs").mkdir()
    (safe / "docs" / "a.txt").write_text("hi")
    (tmp_path / "safe-evil").mkdir()
    (tmp_path / "safe-evil" / "secret.txt").write_text("nope")
    (tmp_path / "outside.txt").write_text("outside")
    sb = Sandbox()
    sb.add_mount("Home", str(safe))
    return sb, safe, tmp_path


def test_virtual_path_resolves_inside_mount(box):
    sb, safe, _ = box
    r = sb.resolve("/Home/docs/a.txt")
    assert r.path == (safe / "docs" / "a.txt").resolve()
    assert r.vpath == "/Home/docs/a.txt"


def test_virtual_path_accepts_backslashes_and_any_case_for_mount(box):
    sb, safe, _ = box
    assert sb.resolve("home\\docs\\a.txt").vpath == "/Home/docs/a.txt"


def test_mount_root_resolves_and_is_flagged(box):
    sb, safe, _ = box
    r = sb.resolve("/Home")
    assert r.is_mount_root
    assert r.vpath == "/Home"


def test_real_absolute_path_inside_mount_is_accepted(box):
    sb, safe, _ = box
    r = sb.resolve(str(safe / "docs" / "a.txt"))
    assert r.vpath == "/Home/docs/a.txt"


def test_real_absolute_path_outside_every_mount_is_denied(box):
    sb, _, tmp = box
    with pytest.raises(PathNotAllowed):
        sb.resolve(str(tmp / "outside.txt"))


@pytest.mark.parametrize("bad", ["/Home/../outside.txt", "/Home/docs/../../outside.txt", "Home/.."])
def test_dotdot_segments_are_rejected_outright(box, bad):
    sb, _, _ = box
    with pytest.raises(InvalidPath):
        sb.resolve(bad)


def test_dotdot_in_real_absolute_path_is_rejected(box):
    sb, safe, _ = box
    with pytest.raises(InvalidPath):
        sb.resolve(str(safe) + os.sep + ".." + os.sep + "outside.txt")


def test_sibling_directory_sharing_a_prefix_is_not_inside_the_mount(box):
    """The old OSOperations used str.startswith: /data/safe admitted /data/safe-evil."""
    sb, _, tmp = box
    with pytest.raises(PathNotAllowed):
        sb.resolve(str(tmp / "safe-evil" / "secret.txt"))


def test_link_inside_mount_cannot_lead_outside(box):
    sb, safe, tmp = box
    _link_dir(safe / "escape", tmp / "safe-evil")
    with pytest.raises(PathNotAllowed):
        sb.resolve("/Home/escape/secret.txt")
    with pytest.raises(PathNotAllowed):
        sb.resolve("/Home/escape")


def test_link_to_a_location_inside_the_same_mount_is_fine(box):
    sb, safe, _ = box
    _link_dir(safe / "alias", safe / "docs")
    r = sb.resolve("/Home/alias/a.txt")
    assert r.vpath == "/Home/docs/a.txt"  # canonicalised through the link


def test_unknown_mount_is_denied(box):
    sb, _, _ = box
    with pytest.raises(PathNotAllowed):
        sb.resolve("/Nope/x.txt")


def test_relative_path_without_a_mount_is_denied(box):
    sb, _, _ = box
    with pytest.raises(PathNotAllowed):
        sb.resolve("docs/a.txt")


def test_virtual_root_alone_is_not_a_path(box):
    sb, _, _ = box
    with pytest.raises(PathNotAllowed):
        sb.resolve("/")


@pytest.mark.parametrize("bad", ["", "   ", "/Home/a\x00b", "/Home/a|b", "/Home/a?b", "/Home/a*b", "/Home/a\x1fb"])
def test_invalid_characters_are_rejected(box, bad):
    sb, _, _ = box
    with pytest.raises((InvalidPath, PathNotAllowed)):
        sb.resolve(bad)


def test_alternate_data_stream_syntax_is_rejected(box):
    sb, _, _ = box
    with pytest.raises(InvalidPath):
        sb.resolve("/Home/docs/a.txt:hidden")


@pytest.mark.parametrize("bad", ["/Home/docs/a.txt.", "/Home/docs/a.txt ", "/Home/docs /a.txt"])
def test_trailing_dot_or_space_segments_are_rejected(box, bad):
    sb, _, _ = box
    with pytest.raises(InvalidPath):
        sb.resolve(bad)


@pytest.mark.skipif(os.name != "nt", reason="reserved device names are a Windows concern")
@pytest.mark.parametrize("name", ["con", "NUL", "com1.txt", "LPT9"])
def test_windows_reserved_device_names_are_rejected(box, name):
    sb, _, _ = box
    with pytest.raises(InvalidPath):
        sb.resolve(f"/Home/{name}")


def test_write_to_readonly_mount_is_denied_but_read_is_allowed(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    (ro / "f.txt").write_text("x")
    sb = Sandbox()
    sb.add_mount("Ref", str(ro), readonly=True)
    assert sb.resolve("/Ref/f.txt").vpath == "/Ref/f.txt"
    with pytest.raises(ReadOnlyMount):
        sb.resolve("/Ref/f.txt", write=True)


def test_readonly_is_enforced_when_reaching_the_file_by_real_path(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    sb = Sandbox()
    sb.add_mount("Ref", str(ro), readonly=True)
    with pytest.raises(ReadOnlyMount):
        sb.resolve(str(ro / "new.txt"), write=True)


def test_nested_mounts_use_the_most_specific_one_for_real_paths(tmp_path):
    outer = tmp_path / "outer"
    inner = outer / "inner"
    inner.mkdir(parents=True)
    sb = Sandbox()
    sb.add_mount("Outer", str(outer), readonly=True)
    sb.add_mount("Inner", str(inner), readonly=False)
    r = sb.resolve(str(inner / "x.txt"), write=True)
    assert r.mount.name == "Inner"


def test_add_mount_validation(tmp_path):
    sb = Sandbox()
    sb.add_mount("Docs", str(tmp_path))
    with pytest.raises(MountError):
        sb.add_mount("docs", str(tmp_path))  # duplicate, case-insensitive
    with pytest.raises(MountError):
        sb.add_mount("../x", str(tmp_path))
    with pytest.raises(MountError):
        sb.add_mount("Missing", str(tmp_path / "does-not-exist"))
    with pytest.raises(MountError):
        sb.add_mount("Root", os.path.abspath(os.sep))  # a filesystem root is too broad


def test_home_mount_cannot_be_removed(tmp_path):
    sb = Sandbox()
    sb.add_mount("Home", str(tmp_path))
    with pytest.raises(MountError):
        sb.remove_mount("home")


def test_config_first_run_creates_home_with_default_folders(tmp_path):
    cfg = SandboxConfig(tmp_path)
    sb = cfg.load()
    home = sb.get_mount("Home")
    assert home is not None
    for sub in ("Documents", "Downloads", "Desktop", "Pictures", "Music", "Projects"):
        assert (tmp_path / "home" / sub).is_dir()


def test_config_does_not_recreate_folders_the_user_deleted(tmp_path):
    cfg = SandboxConfig(tmp_path)
    cfg.load()
    (tmp_path / "home" / "Music").rmdir()
    cfg.load()
    assert not (tmp_path / "home" / "Music").exists()


def test_config_roundtrips_mounts_and_skips_vanished_folders(tmp_path):
    keep = tmp_path / "keep"
    gone = tmp_path / "gone"
    keep.mkdir()
    gone.mkdir()
    cfg = SandboxConfig(tmp_path / "data")
    sb = cfg.load()
    sb.add_mount("Keep", str(keep), readonly=True)
    sb.add_mount("Gone", str(gone))
    cfg.save(sb)
    gone.rmdir()

    reloaded = SandboxConfig(tmp_path / "data").load()
    names = {m.name for m in reloaded.mounts}
    assert names == {"Home", "Keep"}
    assert reloaded.get_mount("Keep").readonly is True
