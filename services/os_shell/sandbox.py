"""Filesystem sandbox shared by the Jarvis desktop and ``OSOperations``.

The OS shell does not expose the host filesystem directly. It exposes *mounts*:
named directories (``/Home``, ``/Projects`` ...) that an admin chose to expose,
each optionally read-only. Every path that arrives from a client, from the
assistant, or from the legacy ``/api/jarvis/os/*`` endpoints goes through
:meth:`Sandbox.resolve`, which:

* accepts a virtual path (``/Home/Documents/a.txt``) or an absolute real path
  that lies inside a mount,
* follows symlinks/junctions *before* checking containment (so a link inside a
  mount cannot lead out of it),
* compares real path components (``commonpath``), never string prefixes
  (``/data/safe`` must not admit ``/data/safe-evil``),
* rejects ``..`` segments, NUL/control characters, Windows alternate data
  streams (``file.txt:hidden``), reserved device names and trailing dot/space
  segments, and
* enforces read-only mounts for write operations.

This is a guardrail for the file APIs, not a jail: a process that can already
write inside a mount (e.g. the admin-only terminal) is outside its threat model.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from core.atomic_io import atomic_write_json

HOME_MOUNT = "Home"
MOUNT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,31}$")
_BAD_SEGMENT_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_WIN_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.IGNORECASE)
_IS_WINDOWS = os.name == "nt"


class SandboxError(Exception):
    """Base class; ``status`` is the HTTP status a route should answer with."""

    status = 400


class InvalidPath(SandboxError):
    status = 400


class PathNotAllowed(SandboxError):
    status = 403


class ReadOnlyMount(SandboxError):
    status = 403


class MountError(SandboxError):
    status = 400


@dataclass(frozen=True)
class Mount:
    name: str
    root: Path  # fully resolved (symlinks followed)
    readonly: bool = False


@dataclass(frozen=True)
class Resolved:
    path: Path  # real path on disk, symlinks followed
    mount: Mount
    vpath: str  # canonical virtual path, e.g. "/Home/Documents/a.txt"

    @property
    def is_mount_root(self) -> bool:
        return _same(self.path, self.mount.root)


def _norm(p: str | Path) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def _same(a: str | Path, b: str | Path) -> bool:
    return _norm(a) == _norm(b)


def _contains(root: Path, target: Path) -> bool:
    r, t = _norm(root), _norm(target)
    try:
        return os.path.commonpath([r, t]) == r
    except ValueError:  # different drives, or mixed absolute/relative
        return False


def _realpath(p: str | Path) -> Path:
    return Path(os.path.realpath(str(p)))


def _check_segment(seg: str) -> None:
    if seg == "..":
        raise InvalidPath("'..' is not allowed in paths")
    if _BAD_SEGMENT_CHARS.search(seg):
        raise InvalidPath(f"invalid character in path segment: {seg!r}")
    if seg != seg.rstrip(" ."):
        # Win32 silently strips trailing dots/spaces, so "foo. " aliases "foo".
        raise InvalidPath(f"path segment may not end with a dot or space: {seg!r}")
    if _IS_WINDOWS and _WIN_RESERVED.match(seg):
        raise InvalidPath(f"reserved device name: {seg!r}")


class Sandbox:
    """A set of named mounts plus the rules for resolving paths against them."""

    def __init__(self, mounts: Optional[List[Mount]] = None):
        self._lock = threading.RLock()
        self._mounts: Dict[str, Mount] = {}
        for m in mounts or []:
            self._mounts[m.name.lower()] = m

    # ------------------------------------------------------------------ mounts
    @property
    def mounts(self) -> List[Mount]:
        with self._lock:
            return list(self._mounts.values())

    def get_mount(self, name: str) -> Optional[Mount]:
        with self._lock:
            return self._mounts.get(name.lower())

    def add_mount(self, name: str, path: str, readonly: bool = False) -> Mount:
        if not MOUNT_NAME_RE.match(name or ""):
            raise MountError("mount name must be 1-32 chars: letters, digits, space, _ . -")
        if not isinstance(path, str) or "\x00" in path or not path.strip():
            raise MountError("invalid mount path")
        root = _realpath(os.path.expanduser(path.strip()))
        if not root.is_dir():
            raise MountError(f"not a directory: {path}")
        if root.parent == root:
            raise MountError("refusing to mount a filesystem root; mount a specific folder")
        with self._lock:
            if name.lower() in self._mounts:
                raise MountError(f"a mount named {name!r} already exists")
            mount = Mount(name=name, root=root, readonly=bool(readonly))
            self._mounts[name.lower()] = mount
            return mount

    def remove_mount(self, name: str) -> None:
        if name.lower() == HOME_MOUNT.lower():
            raise MountError("the Home mount cannot be removed")
        with self._lock:
            if name.lower() not in self._mounts:
                raise MountError(f"no such mount: {name}")
            del self._mounts[name.lower()]

    def set_readonly(self, name: str, readonly: bool) -> Mount:
        with self._lock:
            m = self._mounts.get(name.lower())
            if not m:
                raise MountError(f"no such mount: {name}")
            updated = Mount(m.name, m.root, bool(readonly))
            self._mounts[name.lower()] = updated
            return updated

    # --------------------------------------------------------------- resolving
    def resolve(self, user_path: str, *, write: bool = False, follow_final: bool = True) -> Resolved:
        """Map a client-supplied path to a real path inside a mount, or raise.

        ``follow_final=False`` resolves only the *parent* directory and leaves the
        last component alone, so delete/rename/move can act on a symlink or
        junction itself rather than on whatever it points at.
        """
        if not isinstance(user_path, str) or not user_path.strip():
            raise InvalidPath("path is required")
        if "\x00" in user_path:
            raise InvalidPath("invalid path")

        raw = user_path  # deliberately not stripped: " a.txt " is not "a.txt"
        segments =[s for s in raw.replace("\\", "/").split("/") if s not in ("", ".")]

        # Virtual path: the first segment names a mount in *this* sandbox.
        mount: Optional[Mount] = self.get_mount(segments[0]) if segments else None
        if mount is not None:
            for seg in segments[1:]:
                _check_segment(seg)
            candidate = mount.root.joinpath(*segments[1:])
        elif _is_absolute(raw):
            # Absolute real path: only valid if it lands inside some mount.
            for seg in Path(raw).parts[1:]:
                _check_segment(seg)
            candidate = Path(raw)
        else:
            raise PathNotAllowed("use a path inside a mount, e.g. /Home/notes.txt")

        if follow_final or candidate.parent == candidate:
            real = _realpath(candidate)
        else:
            real = _realpath(candidate.parent) / candidate.name

        if mount is None:
            mount = self._mount_containing(real)
            if mount is None:
                raise PathNotAllowed("path is outside every mounted folder")
        elif not _contains(mount.root, real):
            # A symlink/junction inside the mount led somewhere else.
            raise PathNotAllowed("path escapes its mount")

        if write and mount.readonly:
            raise ReadOnlyMount(f"{mount.name} is mounted read-only")

        return Resolved(path=real, mount=mount, vpath=self._virtual(mount, real))

    def _mount_containing(self, real: Path) -> Optional[Mount]:
        best: Optional[Mount] = None
        with self._lock:
            for m in self._mounts.values():
                if _contains(m.root, real) and (best is None or len(_norm(m.root)) > len(_norm(best.root))):
                    best = m
        return best

    @staticmethod
    def _virtual(mount: Mount, real: Path) -> str:
        rel = os.path.relpath(str(real), str(mount.root))
        if rel == ".":
            return f"/{mount.name}"
        return "/" + mount.name + "/" + rel.replace("\\", "/")

    def virtual_for(self, real: str | Path) -> Optional[str]:
        """Virtual path for a real path, or None if it is not inside any mount."""
        rp = _realpath(real)
        m = self._mount_containing(rp)
        return self._virtual(m, rp) if m else None


_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def _is_absolute(p: str) -> bool:
    """A drive path (C:\\x), a UNC path (\\\\server\\share) or a POSIX absolute path."""
    return bool(_DRIVE_RE.match(p)) or p.startswith("\\\\") or (
        not _IS_WINDOWS and p.startswith("/")
    )


# --------------------------------------------------------------- persistence
class SandboxConfig:
    """Loads/saves the mount table (``<jarvis data>/os_config.json``)."""

    def __init__(self, jarvis_data_dir: str | Path):
        self.base = Path(jarvis_data_dir)
        self.config_path = self.base / "os_config.json"
        self.home_path = self.base / "home"

    def load(self) -> Sandbox:
        first_run = not self.home_path.exists()
        self.home_path.mkdir(parents=True, exist_ok=True)
        if first_run:
            for sub in ("Documents", "Downloads", "Desktop", "Pictures", "Music", "Projects"):
                (self.home_path / sub).mkdir(exist_ok=True)

        sandbox = Sandbox([Mount(HOME_MOUNT, _realpath(self.home_path), False)])
        for entry in self._read().get("mounts", []):
            try:
                sandbox.add_mount(entry["name"], entry["path"], bool(entry.get("readonly", False)))
            except (SandboxError, KeyError, TypeError):
                # A configured folder may have been deleted or renamed; skip it
                # rather than refusing to boot the OS.
                continue
        return sandbox

    def save(self, sandbox: Sandbox) -> None:
        extra = [
            {"name": m.name, "path": str(m.root), "readonly": m.readonly}
            for m in sandbox.mounts
            if m.name.lower() != HOME_MOUNT.lower()
        ]
        data = self._read()
        data["mounts"] = extra
        atomic_write_json(str(self.config_path), data, indent=2)

    def _read(self) -> dict:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def get(self, key: str, default=None):
        return self._read().get(key, default)

    def set(self, key: str, value) -> None:
        data = self._read()
        data[key] = value
        atomic_write_json(str(self.config_path), data, indent=2)
