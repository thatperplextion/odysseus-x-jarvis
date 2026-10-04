"""Focus-session log behind the desktop's pomodoro widget (``<data dir>/os/focus.json``).

A tiny JSON file, written atomically (``fs.atomic_write_bytes``) under a lock so two tabs finishing a
session at the same time can't clobber each other. Sessions are per user; the day boundaries used for
"today" and the 7-day strip come from the caller's UTC offset (JS ``getTimezoneOffset``: UTC minus local).
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from services.os_shell.fs import atomic_write_bytes

MAX_SESSIONS = 5000          # keep the file small; the newest entries win
MAX_MINUTES = 240.0

_lock = threading.Lock()


class FocusStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    # ------------------------------------------------------------------ storage
    def _read(self) -> List[Dict[str, Any]]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        items = data.get("sessions") if isinstance(data, dict) else None
        return [s for s in items if isinstance(s, dict)] if isinstance(items, list) else []

    def _write(self, sessions: List[Dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"version": 1, "sessions": sessions[-MAX_SESSIONS:]}, separators=(",", ":")).encode("utf-8")
        atomic_write_bytes(self.path, payload)

    # --------------------------------------------------------------------- api
    def log(self, user: str, minutes: float, label: str = "", completed: bool = True, ts: Optional[float] = None) -> Dict[str, Any]:
        minutes = float(minutes)
        if not (0 < minutes <= MAX_MINUTES):
            raise ValueError(f"minutes must be between 0 and {int(MAX_MINUTES)}")
        entry = {
            "id": uuid.uuid4().hex[:12],
            "ts": float(ts if ts is not None else time.time()),
            "minutes": round(minutes, 2),
            "label": (label or "").strip()[:120],
            "completed": bool(completed),
            "user": user or "",
        }
        with _lock:
            sessions = self._read()
            sessions.append(entry)
            self._write(sessions)
        return entry

    def stats(self, user: str, tz_offset_min: int = 0, now: Optional[float] = None) -> Dict[str, Any]:
        off = timedelta(minutes=int(tz_offset_min))
        now_dt = datetime.fromtimestamp(now if now is not None else time.time(), tz=timezone.utc).replace(tzinfo=None) - off
        today = now_dt.date()
        days = [today - timedelta(days=i) for i in range(6, -1, -1)]
        by_day: Dict[Any, Dict[str, Any]] = {d: {"date": d.isoformat(), "minutes": 0.0, "sessions": 0, "started": 0} for d in days}
        for s in self._read():
            if (s.get("user") or "") != (user or ""):
                continue
            try:
                local = datetime.fromtimestamp(float(s["ts"]), tz=timezone.utc).replace(tzinfo=None) - off
                mins = float(s.get("minutes") or 0)
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                continue
            row = by_day.get(local.date())
            if row is None:
                continue
            row["minutes"] += mins
            row["started"] += 1
            if s.get("completed"):
                row["sessions"] += 1
        week = [{"date": r["date"], "minutes": round(r["minutes"], 1), "sessions": r["sessions"]} for r in by_day.values()]
        t = by_day[today]
        return {
            "today": {"minutes": round(t["minutes"], 1), "sessions": t["sessions"], "started": t["started"]},
            "week": week,
            "week_minutes": round(sum(r["minutes"] for r in by_day.values()), 1),
        }
