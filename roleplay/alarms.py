"""Persistent, single-user scheduled reminders for roleplay conversations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from uuid import uuid4
from zoneinfo import ZoneInfo

from config import ALARM_FILE, APP_TIMEZONE


_LOCK = threading.Lock()
_STATUSES = frozenset({"pending", "delivered", "cancelled"})


@dataclass(frozen=True)
class Alarm:
    """One scheduled reminder stored in UTC and displayed in the app timezone."""

    id: str
    role_id: str
    text: str
    due_at: str
    status: str
    created_at: str
    delivered_at: str | None = None

    @property
    def due_datetime(self) -> datetime:
        """Return the stored UTC timestamp as an aware datetime."""
        return datetime.fromisoformat(self.due_at).astimezone(timezone.utc)


def create_alarm(role_id: str, text: str, due_at: datetime, *, path: Path = ALARM_FILE) -> Alarm:
    """Create a future alarm, interpreting naïve input in the configured timezone."""
    cleaned_text = text.strip()
    if not cleaned_text:
        raise ValueError("alarm text must not be blank")
    if len(cleaned_text) > 500:
        raise ValueError("alarm text must contain at most 500 characters")
    local_due = due_at.replace(tzinfo=ZoneInfo(APP_TIMEZONE)) if due_at.tzinfo is None else due_at
    utc_due = local_due.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if utc_due <= now:
        raise ValueError("alarm time must be in the future")
    alarm = Alarm(
        id=uuid4().hex,
        role_id=role_id,
        text=cleaned_text,
        due_at=utc_due.isoformat(),
        status="pending",
        created_at=now.isoformat(),
    )
    with _LOCK:
        alarms = _load(path)
        alarms.append(alarm)
        _save(path, alarms)
    return alarm


def list_alarms(role_id: str | None = None, *, path: Path = ALARM_FILE) -> list[Alarm]:
    """List alarms in stable chronological order, optionally for one role."""
    with _LOCK:
        alarms = _load(path)
    filtered = [alarm for alarm in alarms if role_id is None or alarm.role_id == role_id]
    return sorted(filtered, key=lambda alarm: (alarm.due_at, alarm.created_at))


def cancel_alarm(alarm_id: str, *, path: Path = ALARM_FILE) -> Alarm | None:
    """Cancel one pending alarm, retaining it as an auditable record."""
    with _LOCK:
        alarms = _load(path)
        for index, alarm in enumerate(alarms):
            if alarm.id != alarm_id:
                continue
            if alarm.status != "pending":
                return alarm
            cancelled = Alarm(**{**asdict(alarm), "status": "cancelled"})
            alarms[index] = cancelled
            _save(path, alarms)
            return cancelled
    return None


def delete_alarm_history(alarm_id: str, *, path: Path = ALARM_FILE) -> Alarm | None:
    """Permanently remove a delivered or cancelled reminder record."""
    with _LOCK:
        alarms = _load(path)
        for index, alarm in enumerate(alarms):
            if alarm.id != alarm_id:
                continue
            if alarm.status == "pending":
                raise ValueError("pending alarms must be cancelled before deletion")
            alarms.pop(index)
            _save(path, alarms)
            return alarm
    return None


def claim_due_alarms(now: datetime | None = None, *, path: Path = ALARM_FILE) -> list[Alarm]:
    """Atomically mark due alarms delivered and return exactly those alarms."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    claimed: list[Alarm] = []
    with _LOCK:
        alarms = _load(path)
        updated: list[Alarm] = []
        for alarm in alarms:
            if alarm.status == "pending" and alarm.due_datetime <= current:
                delivered = Alarm(
                    **{**asdict(alarm), "status": "delivered", "delivered_at": current.isoformat()}
                )
                updated.append(delivered)
                claimed.append(delivered)
            else:
                updated.append(alarm)
        if claimed:
            _save(path, updated)
    return claimed


def reminder_text(alarm: Alarm) -> str:
    """Render a neutral, visible reminder without requiring a model call."""
    local_due = alarm.due_datetime.astimezone(ZoneInfo(APP_TIMEZONE))
    return f"【提醒 · {local_due:%H:%M}】{alarm.text}"


def _load(path: Path) -> list[Alarm]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    alarms: list[Alarm] = []
    for item in raw:
        try:
            alarm = Alarm(**item)
        except (TypeError, ValueError):
            continue
        if alarm.status in _STATUSES:
            alarms.append(alarm)
    return alarms


def _save(path: Path, alarms: list[Alarm]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(alarm) for alarm in alarms], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
