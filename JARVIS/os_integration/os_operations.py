"""
OS Operations Module for Jarvis OS
Filesystem and command execution for the autonomous agents and the legacy
``/api/jarvis/os/*`` endpoints.

All paths go through the shared :class:`services.os_shell.sandbox.Sandbox`:
nothing outside an explicitly mounted folder is reachable, symlinks cannot lead
out of a mount, and read-only mounts reject writes. (The previous implementation
treated "no allowed paths configured" as "allow everything" and compared paths
with ``str.startswith``, so ``/data/safe`` admitted ``/data/safe-evil``.)

Methods are synchronous and may block on disk or a subprocess: from async code
call them through ``asyncio.to_thread``.
"""

import logging
import os
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from services.os_shell.command_guard import check_command
from services.os_shell.fs import FileSystem, atomic_write_bytes
from services.os_shell.procs import run_capped
from services.os_shell.sandbox import HOME_MOUNT, Sandbox, SandboxError, _norm

logger = logging.getLogger(__name__)

MAX_READ_BYTES = 5 * 1024 * 1024
MAX_LIST_ENTRIES = 10_000
MAX_OUTPUT_BYTES = 1024 * 1024
MAX_COMMAND_SECONDS = 600


@dataclass
class OSOperationResult:
    """Result of an OS operation"""
    success: bool
    operation: str
    data: Any = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "operation": self.operation,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp.isoformat()
        }


class OSOperations:
    """
    OS Operations Manager for Jarvis.

    ``fs`` (optional) is the shared :class:`FileSystem`; when present, deletes go to
    the recoverable Trash instead of being permanent. ``audit`` (optional) is called
    as ``audit(event_type, details)`` for every mutating operation.
    """

    def __init__(self, fs: Optional[FileSystem] = None, sandbox: Optional[Sandbox] = None,
                 audit: Optional[Callable[[str, Dict[str, Any]], None]] = None):
        self.fs = fs
        self.sandbox: Sandbox = fs.sandbox if fs else (sandbox or Sandbox())
        self.audit = audit
        # Summaries only: keeping each result's full file content here leaked memory.
        self.operation_history: Deque[OSOperationResult] = deque(maxlen=500)
        logger.info("OS Operations Manager initialized")

    # ------------------------------------------------------------ legacy shims
    def add_allowed_path(self, path: str, read_only: bool = False):
        """Mount ``path`` (idempotent). Kept for callers written against the old API."""
        real = os.path.realpath(os.path.expanduser(path))
        for m in self.sandbox.mounts:
            if _norm(m.root) == _norm(real):
                return
        base = re.sub(r"[^A-Za-z0-9 _.-]", "_", os.path.basename(real.rstrip("\\/")) or "root")[:28] or "folder"
        name, i = base, 2
        while self.sandbox.get_mount(name):
            name = f"{base}{i}"
            i += 1
        self.sandbox.add_mount(name, real, readonly=read_only)
        logger.info(f"Mounted {real} as /{name} (read_only={read_only})")

    def is_path_allowed(self, path: str, write_operation: bool = False) -> bool:
        try:
            self.sandbox.resolve(path, write=write_operation)
            return True
        except SandboxError:
            return False

    def is_command_safe(self, command: str):
        reason = check_command(command)
        return (reason is None), reason

    # ----------------------------------------------------------------- helpers
    def _result(self, operation: str, target: str, fn: Callable[[], Any], mutating: bool = False) -> OSOperationResult:
        try:
            data = fn()
            result = OSOperationResult(True, operation, data=data)
            if mutating and self.audit:
                self._safe_audit(operation, {"target": target})
        except SandboxError as e:
            result = OSOperationResult(False, operation, error=str(e))
        except PermissionError:
            result = OSOperationResult(False, operation, error=f"Permission denied: {target}")
        except FileNotFoundError:
            result = OSOperationResult(False, operation, error=f"Not found: {target}")
        except UnicodeDecodeError as e:
            result = OSOperationResult(False, operation, error=f"Not valid text: {e.reason}")
        except Exception as e:  # noqa: BLE001 - surface any failure as a result, never raise into the agent
            logger.exception("%s failed for %s", operation, target)
            result = OSOperationResult(False, operation, error=str(e))
        # History keeps a summary, not the payload.
        self.operation_history.append(OSOperationResult(
            result.success, operation, data={"target": target}, error=result.error, timestamp=result.timestamp))
        return result

    def _safe_audit(self, event: str, details: Dict[str, Any]) -> None:
        try:
            self.audit(event, details)  # type: ignore[misc]
        except Exception:  # noqa: BLE001
            logger.debug("audit hook failed", exc_info=True)

    # -------------------------------------------------------------- operations
    def read_file(self, file_path: str, encoding: str = 'utf-8') -> OSOperationResult:
        """Read a text file"""
        def run():
            r = self.sandbox.resolve(file_path)
            if not r.path.exists():
                raise FileNotFoundError(file_path)
            if not r.path.is_file():
                raise SandboxError(f"Path is not a file: {file_path}")
            size = r.path.stat().st_size
            if size > MAX_READ_BYTES:
                raise SandboxError(f"File is {size} bytes; limit is {MAX_READ_BYTES}")
            content = r.path.read_text(encoding=encoding)
            return {"path": str(r.path), "virtual_path": r.vpath, "content": content,
                    "size": len(content), "encoding": encoding}
        return self._result("read_file", file_path, run)

    def write_file(self, file_path: str, content: str, encoding: str = 'utf-8',
                   create_dirs: bool = True) -> OSOperationResult:
        """Write text to a file (atomically)"""
        def run():
            r = self.sandbox.resolve(file_path, write=True)
            if r.is_mount_root:
                raise SandboxError("Cannot write to a mount root")
            if create_dirs:
                r.path.parent.mkdir(parents=True, exist_ok=True)
            if r.path.is_dir():
                raise SandboxError(f"Path is a directory: {file_path}")
            data = content.encode(encoding)
            atomic_write_bytes(r.path, data)
            return {"path": str(r.path), "virtual_path": r.vpath, "size": len(content), "encoding": encoding}
        return self._result("write_file", file_path, run, mutating=True)

    def list_directory(self, dir_path: str, recursive: bool = False) -> OSOperationResult:
        """List contents of a directory"""
        def run():
            r = self.sandbox.resolve(dir_path)
            if not r.path.exists():
                raise FileNotFoundError(dir_path)
            if not r.path.is_dir():
                raise SandboxError(f"Path is not a directory: {dir_path}")
            items: List[Dict[str, Any]] = []
            if recursive:
                for root, dirs, files in os.walk(r.path, followlinks=False):
                    for name in dirs + files:
                        if len(items) >= MAX_LIST_ENTRIES:
                            break
                        items.append(self._item(Path(root) / name))
                    if len(items) >= MAX_LIST_ENTRIES:
                        break
            else:
                for child in r.path.iterdir():
                    if len(items) >= MAX_LIST_ENTRIES:
                        break
                    items.append(self._item(child))
            return {"path": str(r.path), "virtual_path": r.vpath, "items": items, "count": len(items),
                    "truncated": len(items) >= MAX_LIST_ENTRIES}
        return self._result("list_directory", dir_path, run)

    @staticmethod
    def _item(p: Path) -> Dict[str, Any]:
        try:
            is_dir = p.is_dir()
            size = 0 if is_dir else p.stat().st_size
        except OSError:
            is_dir, size = False, 0
        return {"name": p.name, "path": str(p), "type": "directory" if is_dir else "file", "size": size}

    def delete_file(self, file_path: str) -> OSOperationResult:
        """Delete a file or folder. Goes to the recoverable Trash when the shared FileSystem is attached."""
        def run():
            r = self.sandbox.resolve(file_path, write=True, follow_final=False)
            if not os.path.lexists(r.path):
                raise FileNotFoundError(file_path)
            if r.is_mount_root:
                raise SandboxError("Cannot delete a mount root")
            if self.fs is not None:
                meta = self.fs.delete(r.vpath)
                return {"path": str(r.path), "virtual_path": r.vpath, "trash_id": meta["id"], "recoverable": True}
            if r.path.is_dir() and not r.path.is_symlink():
                raise SandboxError("Path is a directory; attach the shared FileSystem to delete folders")
            r.path.unlink()
            return {"path": str(r.path), "virtual_path": r.vpath, "recoverable": False}
        return self._result("delete_file", file_path, run, mutating=True)

    def execute_command(self, command: str, timeout: int = 30,
                        working_dir: Optional[str] = None) -> OSOperationResult:
        """Run a shell command (non-interactive callers only; see ``command_guard``).

        The working directory must be inside a mount (default: Home). Blocking:
        call from a worker thread.
        """
        def run():
            reason = check_command(command)
            if reason:
                raise SandboxError(reason)
            cwd = self._command_cwd(working_dir)
            secs = max(1, min(int(timeout), MAX_COMMAND_SECONDS))
            res = run_capped(command, cwd=cwd, timeout=secs, max_bytes=MAX_OUTPUT_BYTES)
            if res.timed_out:
                raise TimeoutError(f"Command timed out after {secs} seconds")
            return {"command": command, "return_code": res.returncode, "stdout": res.stdout,
                    "stderr": res.stderr, "working_dir": cwd}
        result = self._result("execute_command", command, run, mutating=True)
        if result.success and result.data["return_code"] != 0:
            result.success = False
            result.error = (result.data["stderr"] or f"Exit code {result.data['return_code']}").strip()
        return result

    def _command_cwd(self, working_dir: Optional[str]) -> str:
        if working_dir:
            r = self.sandbox.resolve(working_dir)
            if not r.path.is_dir():
                raise SandboxError(f"Working directory is not a folder: {working_dir}")
            return str(r.path)
        home = self.sandbox.get_mount(HOME_MOUNT)
        mounts = self.sandbox.mounts
        if home is not None:
            return str(home.root)
        if mounts:
            return str(mounts[0].root)
        raise SandboxError("No folders are mounted; mount one before running commands")

    def get_file_info(self, file_path: str) -> OSOperationResult:
        """Get detailed information about a file or directory"""
        def run():
            r = self.sandbox.resolve(file_path)
            if not r.path.exists():
                raise FileNotFoundError(file_path)
            st = r.path.stat()
            return {
                "path": str(r.path), "virtual_path": r.vpath, "name": r.path.name,
                "type": "directory" if r.path.is_dir() else "file", "size": st.st_size,
                "created": st.st_ctime, "modified": st.st_mtime, "accessed": st.st_atime,
                "is_readable": os.access(r.path, os.R_OK), "is_writable": os.access(r.path, os.W_OK),
                "is_executable": os.access(r.path, os.X_OK),
            }
        return self._result("get_file_info", file_path, run)

    def search_files(self, dir_path: str, pattern: str, recursive: bool = True) -> OSOperationResult:
        """Search for files matching a glob pattern"""
        def run():
            r = self.sandbox.resolve(dir_path)
            if not r.path.exists():
                raise FileNotFoundError(dir_path)
            if not r.path.is_dir():
                raise SandboxError(f"Path is not a directory: {dir_path}")
            matches = r.path.rglob(pattern) if recursive else r.path.glob(pattern)
            results: List[Dict[str, Any]] = []
            for m in matches:
                if len(results) >= MAX_LIST_ENTRIES:
                    break
                if self.sandbox.virtual_for(m) is None:
                    continue  # a link that leads out of every mount
                results.append(self._item(m))
            return {"directory": str(r.path), "pattern": pattern, "matches": results, "count": len(results)}
        return self._result("search_files", dir_path, run)

    def create_directory(self, dir_path: str) -> OSOperationResult:
        """Create a directory (and parents)"""
        def run():
            r = self.sandbox.resolve(dir_path, write=True)
            r.path.mkdir(parents=True, exist_ok=True)
            return {"path": str(r.path), "virtual_path": r.vpath}
        return self._result("create_directory", dir_path, run, mutating=True)

    def get_operation_history(self, limit: int = 100) -> List[OSOperationResult]:
        """Get recent operation summaries"""
        return list(self.operation_history)[-limit:]

    def clear_history(self):
        """Clear operation history"""
        self.operation_history.clear()
        logger.info("Operation history cleared")

    async def health_check(self) -> str:
        """Health check for OS operations"""
        return f"healthy ({len(self.operation_history)} operations, {len(self.sandbox.mounts)} mounted folders)"

    async def shutdown(self):
        """Shutdown OS operations manager"""
        logger.info("OS Operations Manager shutting down")
