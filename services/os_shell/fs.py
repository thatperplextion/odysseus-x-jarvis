"""Sandboxed file operations for the OS shell (Files, Editor, Viewer, assistant).

Everything here goes through :class:`~services.os_shell.sandbox.Sandbox`, so a
caller can only touch what an admin mounted. Functions are synchronous; routes
call them via ``asyncio.to_thread``.
"""

from __future__ import annotations

import codecs
import fnmatch
import hashlib
import json
import mimetypes
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .sandbox import (
    InvalidPath,
    Resolved,
    Sandbox,
    SandboxError,
    _check_segment,
    _contains,
)

DEFAULT_MAX_TEXT_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_UPLOAD_BYTES = 200 * 1024 * 1024
LIST_LIMIT = 5000
_FILE_ATTRIBUTE_HIDDEN = 0x2
_FILE_ATTRIBUTE_SYSTEM = 0x4

# Served inline ("preview"). Anything else is forced to download: an HTML/SVG
# file served inline from the app origin would run script with admin rights.
_INLINE_TYPES = {
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/avif", "image/bmp",
    "audio/mpeg", "audio/wav", "audio/ogg", "audio/mp4", "audio/flac", "audio/webm",
    "video/mp4", "video/webm", "video/ogg",
}


class FsError(SandboxError):
    status = 400


class NotFound(FsError):
    status = 404


class Exists(FsError):
    status = 409


class Conflict(FsError):
    status = 409


class TooLarge(FsError):
    status = 413


class NotText(FsError):
    status = 415


_HASH_LIMIT = 32 * 1024 * 1024


def content_version(path: Path) -> str:
    """Opaque change token for optimistic-concurrency saves (a string, for JS).

    Based on *content*, not mtime: two writes inside one filesystem clock tick
    (common on Windows) leave size and mtime identical, which would let a stale
    editor save silently clobber someone else's edit. Files too large to hash
    cheaply fall back to size + mtime.
    """
    st = path.stat()
    if st.st_size > _HASH_LIMIT:
        return f"s{st.st_size}-{st.st_mtime_ns}"
    h = hashlib.sha1(usedforsecurity=False)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return f"{st.st_size}-{h.hexdigest()[:16]}"


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _is_hidden(name: str, st: Optional[os.stat_result]) -> bool:
    if name.startswith("."):
        return True
    attrs = getattr(st, "st_file_attributes", 0) if st is not None else 0
    return bool(attrs & (_FILE_ATTRIBUTE_HIDDEN | _FILE_ATTRIBUTE_SYSTEM))


def check_name(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise InvalidPath("a name is required")
    if "/" in name or "\\" in name:
        raise InvalidPath("names cannot contain slashes")
    if name in (".", ".."):
        raise InvalidPath("invalid name")
    _check_segment(name)
    if len(name) > 255:
        raise InvalidPath("name too long")
    return name


def unique_name(directory: Path, name: str) -> str:
    """``name`` if free, else ``stem (2).ext``, ``stem (3).ext`` ..."""
    if not (directory / name).exists():
        return name
    stem, ext = os.path.splitext(name)
    for i in range(2, 10_000):
        candidate = f"{stem} ({i}){ext}"
        if not (directory / candidate).exists():
            return candidate
    raise Exists("could not find a free name")


def atomic_write_bytes(target: Path, data: bytes) -> None:
    """Write ``data`` to ``target`` via a sibling temp file + ``os.replace`` so readers
    never see a half-written file and a crash can't truncate the original."""
    tmp = target.with_name(f".{target.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if target.exists():
            try:
                shutil.copymode(target, tmp)
            except OSError:
                pass
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


class FileSystem:
    def __init__(
        self,
        sandbox: Sandbox,
        trash_dir: str | Path,
        max_text_bytes: int = DEFAULT_MAX_TEXT_BYTES,
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    ):
        self.sandbox = sandbox
        self.trash_dir = Path(trash_dir)
        self.max_text_bytes = max_text_bytes
        self.max_upload_bytes = max_upload_bytes

    # ---------------------------------------------------------------- queries
    def roots(self) -> List[Dict[str, Any]]:
        out = []
        for m in self.sandbox.mounts:
            item: Dict[str, Any] = {
                "name": m.name,
                "path": f"/{m.name}",
                "readonly": m.readonly,
                "real_path": str(m.root),
            }
            try:
                usage = shutil.disk_usage(str(m.root))
                item.update(total=usage.total, free=usage.free)
            except OSError:
                pass
            out.append(item)
        return out

    def _existing(self, vpath: str, *, write: bool = False, follow: bool = True) -> Resolved:
        r = self.sandbox.resolve(vpath, write=write, follow_final=follow)
        if not os.path.lexists(r.path):
            raise NotFound(f"not found: {r.vpath}")
        return r

    def _describe(self, r: Resolved, st: os.stat_result, *, link: bool = False, restricted: bool = False) -> Dict[str, Any]:
        is_dir = os.path.isdir(r.path)
        name = r.path.name if not r.is_mount_root else r.mount.name
        return {
            "name": name,
            "path": r.vpath,
            "type": "dir" if is_dir else "file",
            "size": 0 if is_dir else st.st_size,
            "modified": _iso(st.st_mtime),
            "hidden": _is_hidden(r.path.name, st),
            "link": link,
            "restricted": restricted,
            "readonly": r.mount.readonly,
        }

    def stat(self, vpath: str) -> Dict[str, Any]:
        r = self._existing(vpath)
        info = self._describe(r, r.path.stat())
        info["mime"] = mimetypes.guess_type(r.path.name)[0] or "application/octet-stream"
        info["created"] = _iso(r.path.stat().st_ctime)
        return info

    def list_dir(self, vpath: str, show_hidden: bool = False, limit: int = LIST_LIMIT) -> Dict[str, Any]:
        r = self._existing(vpath)
        if not r.path.is_dir():
            raise FsError(f"not a folder: {r.vpath}")
        entries: List[Dict[str, Any]] = []
        truncated = False
        with os.scandir(r.path) as it:
            for de in it:
                if len(entries) >= limit:
                    truncated = True
                    break
                try:
                    is_link = de.is_symlink() or (hasattr(de, "is_junction") and de.is_junction())
                    st = de.stat(follow_symlinks=False)
                    child_v = r.vpath.rstrip("/") + "/" + de.name
                    restricted = False
                    if is_link:
                        target_v = self.sandbox.virtual_for(de.path)
                        restricted = target_v is None
                        is_dir = (not restricted) and os.path.isdir(de.path)
                    else:
                        is_dir = de.is_dir(follow_symlinks=False)
                    hidden = _is_hidden(de.name, st)
                    if hidden and not show_hidden:
                        continue
                    entries.append({
                        "name": de.name,
                        "path": child_v,
                        "type": "dir" if is_dir else "file",
                        "size": 0 if is_dir else st.st_size,
                        "modified": _iso(st.st_mtime),
                        "hidden": hidden,
                        "link": is_link,
                        "restricted": restricted,
                    })
                except OSError:
                    continue  # vanished or unreadable; skip rather than fail the listing
        entries.sort(key=lambda e: (e["type"] != "dir", e["name"].lower()))
        return {
            "path": r.vpath,
            "name": r.mount.name if r.is_mount_root else r.path.name,
            "readonly": r.mount.readonly,
            "entries": entries,
            "truncated": truncated,
        }

    def search(self, vpath: str, query: str, limit: int = 200, timeout: float = 5.0) -> Dict[str, Any]:
        r = self._existing(vpath)
        if not r.path.is_dir():
            raise FsError(f"not a folder: {r.vpath}")
        q = (query or "").strip()
        if not q:
            raise InvalidPath("a search query is required")
        glob = any(c in q for c in "*?[")
        ql = q.lower()
        deadline = time.monotonic() + timeout
        results: List[Dict[str, Any]] = []
        timed_out = False
        for dirpath, dirnames, filenames in os.walk(r.path, followlinks=False):
            if time.monotonic() > deadline:
                timed_out = True
                break
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in dirnames + filenames:
                hit = fnmatch.fnmatch(name.lower(), ql) if glob else ql in name.lower()
                if not hit:
                    continue
                full = Path(dirpath) / name
                v = self.sandbox.virtual_for(full)
                if v is None:
                    continue
                try:
                    st = full.lstat()
                except OSError:
                    continue
                results.append({
                    "name": name,
                    "path": v,
                    "type": "dir" if full.is_dir() else "file",
                    "size": st.st_size if not full.is_dir() else 0,
                    "modified": _iso(st.st_mtime),
                })
                if len(results) >= limit:
                    return {"query": q, "results": results, "truncated": True}
        return {"query": q, "results": results, "truncated": timed_out}

    # ------------------------------------------------------------------- text
    def read_text(self, vpath: str, max_bytes: Optional[int] = None) -> Dict[str, Any]:
        r = self._existing(vpath)
        if not r.path.is_file():
            raise FsError(f"not a file: {r.vpath}")
        limit = max_bytes or self.max_text_bytes
        st = r.path.stat()
        if st.st_size > limit:
            raise TooLarge(f"file is {st.st_size} bytes; the text editor opens up to {limit}")
        data = r.path.read_bytes()
        if b"\x00" in data[:8192]:
            raise NotText("binary file")
        bom = data.startswith(codecs.BOM_UTF8)
        try:
            text = data.decode("utf-8-sig")
            encoding = "utf-8"
        except UnicodeDecodeError:
            text = data.decode("latin-1")
            encoding = "latin-1"
            if any(ord(c) < 32 and c not in "\t\r\n\f\b" for c in text[:8192]):
                raise NotText("binary file")
        crlf = text.count("\r\n")
        lf = text.count("\n") - crlf
        eol = "crlf" if crlf > lf else "lf"
        if crlf:
            text = text.replace("\r\n", "\n")
        return {
            "path": r.vpath,
            "content": text,
            "encoding": encoding,
            "bom": bom,
            "eol": eol,
            "size": st.st_size,
            "version": content_version(r.path),
            "readonly": r.mount.readonly,
        }

    def write_text(
        self,
        vpath: str,
        content: str,
        *,
        expected_version: Optional[str] = None,
        encoding: str = "utf-8",
        bom: bool = False,
        eol: str = "lf",
        create: bool = True,
    ) -> Dict[str, Any]:
        if not isinstance(content, str):
            raise InvalidPath("content must be text")
        r = self.sandbox.resolve(vpath, write=True)
        exists = r.path.exists()
        if r.is_mount_root:
            raise FsError("cannot write to a mount root")
        if exists and not r.path.is_file():
            raise FsError(f"not a file: {r.vpath}")
        if not exists and not create:
            raise NotFound(f"not found: {r.vpath}")
        if not exists and not r.path.parent.is_dir():
            raise NotFound(f"folder does not exist: {os.path.dirname(r.vpath)}")
        if exists and expected_version is not None and content_version(r.path) != expected_version:
            raise Conflict("the file changed on disk since you opened it")

        text = content.replace("\r\n", "\n")
        if eol == "crlf":
            text = text.replace("\n", "\r\n")
        try:
            data = text.encode(encoding if encoding in ("utf-8", "latin-1") else "utf-8")
        except UnicodeEncodeError:
            data = text.encode("utf-8")  # typed a character the old encoding can't hold
            encoding = "utf-8"
        if bom and encoding == "utf-8":
            data = codecs.BOM_UTF8 + data
        if len(data) > self.max_text_bytes * 4:
            raise TooLarge("content too large")

        atomic_write_bytes(r.path, data)
        st = r.path.stat()
        return {"path": r.vpath, "size": st.st_size, "version": content_version(r.path), "encoding": encoding, "created": not exists}

    # ----------------------------------------------------------------- upload
    def begin_upload(self, vpath: str, overwrite: bool = False) -> "UploadWriter":
        r = self.sandbox.resolve(vpath, write=True)
        if r.is_mount_root:
            raise FsError("cannot write to a mount root")
        if not r.path.parent.is_dir():
            raise NotFound(f"folder does not exist: {os.path.dirname(r.vpath)}")
        if r.path.exists() and not overwrite:
            raise Exists(f"already exists: {r.vpath}")
        return UploadWriter(r, self.max_upload_bytes)

    # ---------------------------------------------------------- structure ops
    def mkdir(self, vpath: str) -> Dict[str, Any]:
        r = self.sandbox.resolve(vpath, write=True)
        if r.path.exists():
            raise Exists(f"already exists: {r.vpath}")
        if not r.path.parent.is_dir():
            raise NotFound(f"folder does not exist: {os.path.dirname(r.vpath)}")
        r.path.mkdir()
        return self._describe(self.sandbox.resolve(vpath), r.path.stat())

    def create_file(self, vpath: str) -> Dict[str, Any]:
        r = self.sandbox.resolve(vpath, write=True)
        if os.path.lexists(r.path):
            raise Exists(f"already exists: {r.vpath}")
        return self.write_text(vpath, "", create=True)

    def transfer(
        self,
        src: str,
        dst_dir: str,
        name: Optional[str] = None,
        *,
        copy: bool = False,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Move or copy ``src`` into folder ``dst_dir`` (optionally under a new name)."""
        # Moving acts on a symlink/junction itself; copying reads through it, which the
        # sandbox only allows if the target is inside a mount.
        s = self._existing(src, write=not copy, follow=copy)
        if s.is_mount_root:
            raise FsError("cannot move or copy a mount root")
        s_is_link = s.path.is_symlink() or (hasattr(s.path, "is_junction") and s.path.is_junction())
        d = self._existing(dst_dir, write=True)
        if not d.path.is_dir():
            raise FsError(f"destination is not a folder: {d.vpath}")
        new_name = check_name(name) if name is not None else s.path.name
        target = d.path / new_name

        if s.path.is_dir() and not s_is_link and _contains(s.path, d.path):
            raise FsError("cannot move or copy a folder into itself")

        case_only_rename = (
            not copy
            and os.path.normcase(str(target)) == os.path.normcase(str(s.path))
            and str(target) != str(s.path)
        )
        if os.path.normcase(str(target)) == os.path.normcase(str(s.path)) and not case_only_rename:
            if not copy:
                raise FsError("source and destination are the same")
            new_name = unique_name(d.path, new_name)  # duplicate in place -> "name (2).ext"
            target = d.path / new_name
        elif target.exists() and not case_only_rename:
            if not overwrite:
                raise Exists(f"already exists: {d.vpath.rstrip('/')}/{new_name}")
            if target.is_dir() or s.path.is_dir():
                raise Exists("overwriting a folder is not supported; delete it first")

        if case_only_rename:
            os.rename(s.path, target)
        elif copy:
            if s.path.is_dir():
                shutil.copytree(s.path, target, symlinks=True)  # keep links as links: never read through them
            else:
                shutil.copy2(s.path, target)
        else:
            if target.exists():  # overwrite=True and both files
                os.replace(s.path, target)
            else:
                shutil.move(str(s.path), str(target))
        out = self.sandbox.resolve(d.vpath.rstrip("/") + "/" + new_name)
        return self._describe(out, out.path.lstat())

    def rename(self, vpath: str, new_name: str) -> Dict[str, Any]:
        s = self._existing(vpath, write=True, follow=False)
        if s.is_mount_root:
            raise FsError("cannot rename a mount root")
        parent_v = s.vpath.rsplit("/", 1)[0] or f"/{s.mount.name}"
        return self.transfer(s.vpath, parent_v, new_name)

    # ------------------------------------------------------------------ trash
    def delete(self, vpath: str) -> Dict[str, Any]:
        """Move to Trash (recoverable). Use :meth:`trash_empty` to purge."""
        r = self._existing(vpath, write=True, follow=False)  # a link is trashed, not its target
        if r.is_mount_root:
            raise FsError("cannot delete a mount root")
        item_id = uuid.uuid4().hex[:12]
        slot = self.trash_dir / item_id
        slot.mkdir(parents=True)
        is_dir = os.path.isdir(r.path)
        size = 0 if is_dir else r.path.lstat().st_size
        meta = {
            "id": item_id,
            "name": r.path.name,
            "original": r.vpath,
            "type": "dir" if is_dir else "file",
            "size": size,
            "deleted_at": _iso(time.time()),
        }
        try:
            shutil.move(str(r.path), str(slot / r.path.name))
            (slot / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        except Exception:
            shutil.rmtree(slot, ignore_errors=True)
            raise
        return meta

    def trash_list(self) -> List[Dict[str, Any]]:
        items = []
        if self.trash_dir.is_dir():
            for slot in self.trash_dir.iterdir():
                try:
                    items.append(json.loads((slot / "meta.json").read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    continue
        items.sort(key=lambda m: m.get("deleted_at", ""), reverse=True)
        return items

    def trash_restore(self, item_id: str) -> Dict[str, Any]:
        slot = self._slot(item_id)
        meta = json.loads((slot / "meta.json").read_text(encoding="utf-8"))
        original = self.sandbox.resolve(meta["original"], write=True)  # mount may be gone / read-only now
        parent = original.path.parent
        if not parent.is_dir():
            raise NotFound("the original folder no longer exists")
        name = unique_name(parent, meta["name"])
        shutil.move(str(slot / meta["name"]), str(parent / name))
        shutil.rmtree(slot, ignore_errors=True)
        restored = self.sandbox.resolve(os.path.dirname(original.vpath) + "/" + name)
        return self._describe(restored, restored.path.lstat())

    def trash_purge(self, item_id: str) -> None:
        shutil.rmtree(self._slot(item_id))

    def trash_empty(self) -> int:
        count = 0
        if self.trash_dir.is_dir():
            for slot in list(self.trash_dir.iterdir()):
                shutil.rmtree(slot, ignore_errors=True)
                count += 1
        return count

    def _slot(self, item_id: str) -> Path:
        if not isinstance(item_id, str) or not item_id.isalnum() or len(item_id) > 32:
            raise InvalidPath("invalid trash id")
        slot = self.trash_dir / item_id
        if not slot.is_dir():
            raise NotFound("not in trash")
        return slot

    # --------------------------------------------------------------- download
    def open_for_download(self, vpath: str) -> Tuple[Path, str, str, bool]:
        """Returns ``(real_path, filename, media_type, inline_ok)``."""
        r = self._existing(vpath)
        if not r.path.is_file():
            raise FsError(f"not a file: {r.vpath}")
        mime = mimetypes.guess_type(r.path.name)[0] or "application/octet-stream"
        return r.path, r.path.name, mime, mime in _INLINE_TYPES


class UploadWriter:
    """Streams an upload into a temp file next to the target, then renames it into place."""

    def __init__(self, target: Resolved, max_bytes: int):
        self.target = target
        self.max_bytes = max_bytes
        self.written = 0
        self._tmp = target.path.with_name(f".{target.path.name}.{uuid.uuid4().hex[:8]}.upload")
        self._fh = open(self._tmp, "wb")

    def write(self, chunk: bytes) -> None:
        self.written += len(chunk)
        if self.written > self.max_bytes:
            self.abort()
            raise TooLarge(f"upload exceeds the {self.max_bytes // (1024 * 1024)} MB limit")
        self._fh.write(chunk)

    def commit(self) -> Dict[str, Any]:
        self._fh.flush()
        os.fsync(self._fh.fileno())
        self._fh.close()
        os.replace(self._tmp, self.target.path)
        st = self.target.path.stat()
        return {"path": self.target.vpath, "size": st.st_size}

    def abort(self) -> None:
        try:
            self._fh.close()
        except OSError:
            pass
        try:
            self._tmp.unlink()
        except OSError:
            pass
