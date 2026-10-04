"""Sandboxed file operations behind the OS shell Files/Editor/Viewer apps."""

import os
import subprocess

import pytest

from services.os_shell.fs import (
    Conflict,
    Exists,
    FileSystem,
    FsError,
    NotFound,
    NotText,
    TooLarge,
)
from services.os_shell.sandbox import InvalidPath, ReadOnlyMount, Sandbox


def _link_dir(link, target):
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        if os.name != "nt":
            raise
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip("cannot create link on this machine")


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    ro = tmp_path / "ro"
    home.mkdir()
    ro.mkdir()
    (ro / "ref.txt").write_text("reference")
    sb = Sandbox()
    sb.add_mount("Home", str(home))
    sb.add_mount("Ref", str(ro), readonly=True)
    fs = FileSystem(sb, tmp_path / "trash", max_text_bytes=1000, max_upload_bytes=50)
    return fs, home, ro, tmp_path


# ------------------------------------------------------------------ listing
def test_list_dir_puts_folders_first_and_hides_dotfiles_by_default(env):
    fs, home, *_ = env
    (home / "b.txt").write_text("b")
    (home / "a.txt").write_text("a")
    (home / "Zdir").mkdir()
    (home / ".secret").write_text("s")
    listing = fs.list_dir("/Home")
    assert [e["name"] for e in listing["entries"]] == ["Zdir", "a.txt", "b.txt"]
    assert ".secret" in [e["name"] for e in fs.list_dir("/Home", show_hidden=True)["entries"]]
    assert listing["entries"][0]["path"] == "/Home/Zdir"
    assert listing["readonly"] is False


def test_list_dir_marks_readonly_mount(env):
    fs, *_ = env
    assert fs.list_dir("/Ref")["readonly"] is True


def test_list_dir_flags_a_link_that_leaves_the_mount_as_restricted(env):
    fs, home, _, tmp = env
    outside = tmp / "outside"
    outside.mkdir()
    _link_dir(home / "out", outside)
    entry = next(e for e in fs.list_dir("/Home")["entries"] if e["name"] == "out")
    assert entry["link"] is True and entry["restricted"] is True
    with pytest.raises(Exception):
        fs.list_dir("/Home/out")


def test_list_dir_on_a_file_or_missing_path_fails_cleanly(env):
    fs, home, *_ = env
    (home / "f.txt").write_text("x")
    with pytest.raises(FsError):
        fs.list_dir("/Home/f.txt")
    with pytest.raises(NotFound):
        fs.list_dir("/Home/nope")


# --------------------------------------------------------------------- text
def test_read_write_roundtrip_preserves_crlf_and_bom(env):
    fs, home, *_ = env
    raw = b"\xef\xbb\xbfline1\r\nline2\r\nline3\r\n"
    (home / "win.txt").write_bytes(raw)
    doc = fs.read_text("/Home/win.txt")
    assert doc["bom"] is True and doc["eol"] == "crlf"
    assert "\r" not in doc["content"]  # the browser textarea can't hold CR
    fs.write_text("/Home/win.txt", doc["content"], expected_version=doc["version"], bom=doc["bom"], eol=doc["eol"])
    assert (home / "win.txt").read_bytes() == raw


def test_lf_file_stays_lf(env):
    fs, home, *_ = env
    (home / "u.txt").write_bytes(b"a\nb\n")
    doc = fs.read_text("/Home/u.txt")
    assert doc["eol"] == "lf"
    fs.write_text("/Home/u.txt", "a\nb\nc\n", eol=doc["eol"])
    assert (home / "u.txt").read_bytes() == b"a\nb\nc\n"


def test_latin1_file_is_readable_and_written_back_in_latin1(env):
    fs, home, *_ = env
    (home / "old.txt").write_bytes("café".encode("latin-1"))
    doc = fs.read_text("/Home/old.txt")
    assert doc["encoding"] == "latin-1" and doc["content"] == "café"
    fs.write_text("/Home/old.txt", "café!", encoding="latin-1")
    assert (home / "old.txt").read_bytes() == "café!".encode("latin-1")


def test_latin1_file_upgrades_to_utf8_when_user_types_unencodable_text(env):
    fs, home, *_ = env
    (home / "old.txt").write_bytes("café".encode("latin-1"))
    out = fs.write_text("/Home/old.txt", "café 🚀", encoding="latin-1")
    assert out["encoding"] == "utf-8"
    assert (home / "old.txt").read_text(encoding="utf-8") == "café 🚀"


def test_binary_and_oversized_files_are_refused_by_the_text_reader(env):
    fs, home, *_ = env
    (home / "b.bin").write_bytes(b"\x00\x01\x02binary")
    (home / "big.txt").write_text("x" * 2000)
    with pytest.raises(NotText):
        fs.read_text("/Home/b.bin")
    with pytest.raises(TooLarge):
        fs.read_text("/Home/big.txt")


def test_save_with_a_stale_version_conflicts_and_does_not_overwrite(env):
    fs, home, *_ = env
    (home / "n.txt").write_text("v1")
    opened = fs.read_text("/Home/n.txt")
    (home / "n.txt").write_text("changed elsewhere!")  # another process edits it
    with pytest.raises(Conflict):
        fs.write_text("/Home/n.txt", "my edit", expected_version=opened["version"])
    assert (home / "n.txt").read_text() == "changed elsewhere!"


def test_stale_save_is_caught_even_when_size_and_mtime_are_identical(env):
    """Two writes inside one filesystem clock tick (common on Windows) leave size
    and mtime unchanged; the version token must still differ."""
    fs, home, *_ = env
    target = home / "n.txt"
    target.write_text("v1")
    opened = fs.read_text("/Home/n.txt")
    before = target.stat()
    target.write_text("v2")  # same length
    os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))  # same mtime
    assert target.stat().st_size == before.st_size
    assert target.stat().st_mtime_ns == before.st_mtime_ns
    with pytest.raises(Conflict):
        fs.write_text("/Home/n.txt", "my edit", expected_version=opened["version"])
    assert target.read_text() == "v2"


def test_save_with_current_version_succeeds_and_returns_new_version(env):
    fs, home, *_ = env
    (home / "n.txt").write_text("v1")
    opened = fs.read_text("/Home/n.txt")
    out = fs.write_text("/Home/n.txt", "v2", expected_version=opened["version"])
    assert out["version"] != opened["version"]
    assert (home / "n.txt").read_text() == "v2"


def test_write_creates_new_files_and_leaves_no_temp_files(env):
    fs, home, *_ = env
    out = fs.write_text("/Home/new.txt", "hello")
    assert out["created"] is True
    assert sorted(p.name for p in home.iterdir()) == ["new.txt"]


def test_write_to_missing_folder_or_readonly_mount_or_root_is_refused(env):
    fs, home, *_ = env
    with pytest.raises(NotFound):
        fs.write_text("/Home/missing/x.txt", "x")
    with pytest.raises(ReadOnlyMount):
        fs.write_text("/Ref/ref.txt", "tampered")
    assert fs.read_text("/Ref/ref.txt")["content"] == "reference"
    with pytest.raises(FsError):
        fs.write_text("/Home", "x")


def test_create_file_refuses_to_clobber(env):
    fs, home, *_ = env
    fs.create_file("/Home/a.txt")
    with pytest.raises(Exists):
        fs.create_file("/Home/a.txt")


# ---------------------------------------------------------------- structure
def test_mkdir_and_duplicate(env):
    fs, home, *_ = env
    assert fs.mkdir("/Home/docs")["type"] == "dir"
    with pytest.raises(Exists):
        fs.mkdir("/Home/docs")
    with pytest.raises(NotFound):
        fs.mkdir("/Home/a/b/c")  # no implicit parents


def test_move_and_rename(env):
    fs, home, *_ = env
    (home / "a.txt").write_text("a")
    (home / "d").mkdir()
    fs.transfer("/Home/a.txt", "/Home/d")
    assert (home / "d" / "a.txt").exists() and not (home / "a.txt").exists()
    fs.rename("/Home/d/a.txt", "b.txt")
    assert (home / "d" / "b.txt").exists()


def test_rename_rejects_path_tricks(env):
    fs, home, *_ = env
    (home / "a.txt").write_text("a")
    for bad in ["../x", "x/y", "", "..", "a:b", "bad."]:
        with pytest.raises(InvalidPath):
            fs.rename("/Home/a.txt", bad)


def test_move_refuses_to_clobber_without_overwrite(env):
    fs, home, *_ = env
    (home / "a.txt").write_text("A")
    (home / "d").mkdir()
    (home / "d" / "a.txt").write_text("existing")
    with pytest.raises(Exists):
        fs.transfer("/Home/a.txt", "/Home/d")
    assert (home / "d" / "a.txt").read_text() == "existing"
    fs.transfer("/Home/a.txt", "/Home/d", overwrite=True)
    assert (home / "d" / "a.txt").read_text() == "A"


def test_move_folder_into_itself_is_refused(env):
    fs, home, *_ = env
    (home / "d" / "sub").mkdir(parents=True)
    with pytest.raises(FsError):
        fs.transfer("/Home/d", "/Home/d/sub")


def test_copy_file_and_folder_and_duplicate_in_place(env):
    fs, home, *_ = env
    (home / "d").mkdir()
    (home / "d" / "f.txt").write_text("f")
    (home / "a.txt").write_text("a")
    fs.transfer("/Home/d", "/Home", name="d2", copy=True)
    assert (home / "d2" / "f.txt").read_text() == "f"
    out = fs.transfer("/Home/a.txt", "/Home", copy=True)
    assert out["name"] == "a (2).txt"
    assert (home / "a.txt").exists() and (home / "a (2).txt").read_text() == "a"


def test_cannot_move_out_of_or_into_readonly_mount(env):
    fs, home, ro, _ = env
    (home / "a.txt").write_text("a")
    with pytest.raises(ReadOnlyMount):
        fs.transfer("/Ref/ref.txt", "/Home")  # a move deletes from the read-only source
    with pytest.raises(ReadOnlyMount):
        fs.transfer("/Home/a.txt", "/Ref")
    fs.transfer("/Ref/ref.txt", "/Home", copy=True)  # copying out is fine
    assert (home / "ref.txt").read_text() == "reference"


@pytest.mark.skipif(os.name != "nt", reason="case-only rename quirk is a Windows/macOS concern")
def test_case_only_rename_works(env):
    fs, home, *_ = env
    (home / "note.txt").write_text("n")
    fs.rename("/Home/note.txt", "Note.txt")
    assert [p.name for p in home.iterdir()] == ["Note.txt"]


def test_mount_roots_cannot_be_renamed_moved_or_deleted(env):
    fs, *_ = env
    for op in (lambda: fs.rename("/Home", "x"), lambda: fs.delete("/Home"), lambda: fs.transfer("/Home", "/Home")):
        with pytest.raises(FsError):
            op()


# -------------------------------------------------------------------- trash
def test_delete_moves_to_trash_and_restore_puts_it_back(env):
    fs, home, *_ = env
    (home / "a.txt").write_text("keep me")
    meta = fs.delete("/Home/a.txt")
    assert not (home / "a.txt").exists()
    assert [t["name"] for t in fs.trash_list()] == ["a.txt"]
    fs.trash_restore(meta["id"])
    assert (home / "a.txt").read_text() == "keep me"
    assert fs.trash_list() == []


def test_restore_never_overwrites_a_newer_file(env):
    fs, home, *_ = env
    (home / "a.txt").write_text("old")
    meta = fs.delete("/Home/a.txt")
    (home / "a.txt").write_text("new")
    out = fs.trash_restore(meta["id"])
    assert (home / "a.txt").read_text() == "new"
    assert out["name"] == "a (2).txt" and (home / "a (2).txt").read_text() == "old"


def test_deleting_a_folder_and_emptying_trash(env):
    fs, home, *_ = env
    (home / "d").mkdir()
    (home / "d" / "f.txt").write_text("f")
    fs.delete("/Home/d")
    assert not (home / "d").exists()
    assert fs.trash_empty() == 1
    assert fs.trash_list() == []


def test_deleting_a_link_trashes_the_link_not_its_target(env):
    fs, home, *_ = env
    (home / "docs").mkdir()
    (home / "docs" / "keep.txt").write_text("precious")
    _link_dir(home / "alias", home / "docs")
    fs.delete("/Home/alias")
    assert (home / "docs" / "keep.txt").read_text() == "precious"
    assert not os.path.lexists(home / "alias")


def test_delete_in_readonly_mount_is_refused(env):
    fs, *_ = env
    with pytest.raises(ReadOnlyMount):
        fs.delete("/Ref/ref.txt")


def test_trash_ids_are_validated(env):
    fs, *_ = env
    for bad in ["../x", "a/b", "", "x" * 40]:
        with pytest.raises((InvalidPath, NotFound)):
            fs.trash_restore(bad)


# ------------------------------------------------------------------- search
def test_search_by_substring_and_glob(env):
    fs, home, *_ = env
    (home / "sub").mkdir()
    (home / "sub" / "Report-2026.md").write_text("x")
    (home / "notes.txt").write_text("x")
    assert [r["name"] for r in fs.search("/Home", "report")["results"]] == ["Report-2026.md"]
    assert [r["name"] for r in fs.search("/Home", "*.txt")["results"]] == ["notes.txt"]
    assert fs.search("/Home", "report")["results"][0]["path"] == "/Home/sub/Report-2026.md"


# ------------------------------------------------------------------- upload
def test_upload_commit_and_exists_guard(env):
    fs, home, *_ = env
    w = fs.begin_upload("/Home/up.bin")
    w.write(b"abc")
    w.write(b"def")
    out = w.commit()
    assert out["size"] == 6 and (home / "up.bin").read_bytes() == b"abcdef"
    with pytest.raises(Exists):
        fs.begin_upload("/Home/up.bin")
    fs.begin_upload("/Home/up.bin", overwrite=True).abort()


def test_oversized_upload_is_rejected_and_leaves_nothing_behind(env):
    fs, home, *_ = env
    w = fs.begin_upload("/Home/big.bin")
    w.write(b"x" * 30)
    with pytest.raises(TooLarge):
        w.write(b"x" * 30)
    assert list(home.iterdir()) == []


def test_aborted_upload_leaves_no_temp_file(env):
    fs, home, *_ = env
    w = fs.begin_upload("/Home/x.bin")
    w.write(b"partial")
    w.abort()
    assert list(home.iterdir()) == []


# ----------------------------------------------------------------- download
def test_only_safe_media_types_are_served_inline(env):
    fs, home, *_ = env
    for name in ("pic.png", "page.html", "vector.svg", "script.js", "doc.pdf", "clip.mp4"):
        (home / name).write_bytes(b"x")
    inline = {n: fs.open_for_download(f"/Home/{n}")[3] for n in ("pic.png", "page.html", "vector.svg", "script.js", "doc.pdf", "clip.mp4")}
    assert inline == {
        "pic.png": True,
        "clip.mp4": True,
        # HTML/SVG inline on the app origin would execute with the admin's session.
        "page.html": False,
        "vector.svg": False,
        "script.js": False,
        "doc.pdf": False,
    }


def test_download_of_missing_or_folder_fails(env):
    fs, home, *_ = env
    (home / "d").mkdir()
    with pytest.raises(NotFound):
        fs.open_for_download("/Home/missing.png")
    with pytest.raises(FsError):
        fs.open_for_download("/Home/d")
