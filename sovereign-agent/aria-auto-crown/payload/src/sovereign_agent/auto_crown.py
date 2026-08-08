"""auto_crown.py — Timed autonomous operation (M43).

AutoCrownStore: backed by auto_crown.json in data_dir.
Trust tiers: 1=1hr, 2=2hr, 3=4hr, 4=8hr.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_TRUST_TIER_MAX_HOURS: dict[int, float] = {
    1: 1.0,
    2: 2.0,
    3: 4.0,
    4: 8.0,
}


@dataclass
class AutoSession:
    session_id: str
    started_at: str          # ISO UTC
    duration_hours: float
    expires_at: float        # unix timestamp
    trust_tier: int          # 1-4
    reason: str
    status: str              # active | completed | cancelled | expired
    work_done_summary: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)

    def remaining_seconds(self) -> float:
        return max(0.0, self.expires_at - time.time())

    def remaining_minutes(self) -> float:
        return self.remaining_seconds() / 60.0


class AutoCrownStore:
    def __init__(self, data_dir: Optional[Path] = None) -> None:
        from sovereign_agent.config import SETTINGS
        self._data_dir = data_dir or SETTINGS.paths.data_dir
        self._path = self._data_dir / "auto_crown.json"
        self._trust_path = self._data_dir / "auto_trust_tier.json"

    def _read(self) -> Optional[AutoSession]:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text())
            return AutoSession(**data)
        except Exception:  # noqa: BLE001
            return None

    def _write(self, session: AutoSession) -> None:
        self._path.write_text(json.dumps(session.as_dict(), indent=2))

    def get_max_trust_tier(self) -> int:
        try:
            if self._trust_path.exists():
                data = json.loads(self._trust_path.read_text())
                return int(data.get("max_tier", 1))
        except Exception:  # noqa: BLE001
            pass
        return 1

    def set_trust_tier(self, tier: int) -> None:
        if tier not in _TRUST_TIER_MAX_HOURS:
            raise ValueError(f"Invalid trust tier {tier}. Valid: 1-4.")
        self._trust_path.write_text(json.dumps({"max_tier": tier}, indent=2))

    def start(
        self,
        duration_hours: float,
        trust_tier: int,
        reason: str,
        session_id: str,
    ) -> AutoSession:
        max_tier = self.get_max_trust_tier()
        if trust_tier > max_tier:
            raise ValueError(
                f"Trust tier {trust_tier} exceeds max allowed ({max_tier}). "
                "Use set_auto_trust_tier() with T3 approval to unlock higher tiers."
            )
        max_hours = _TRUST_TIER_MAX_HOURS.get(trust_tier, 1.0)
        if duration_hours > max_hours:
            raise ValueError(
                f"Duration {duration_hours}h exceeds max for trust tier {trust_tier} ({max_hours}h)."
            )
        now = time.time()
        session = AutoSession(
            session_id=session_id,
            started_at=datetime.now(timezone.utc).isoformat(),
            duration_hours=duration_hours,
            expires_at=now + duration_hours * 3600,
            trust_tier=trust_tier,
            reason=reason,
            status="active",
        )
        self._write(session)
        return session

    def status(self) -> Optional[AutoSession]:
        return self._read()

    def is_expired(self) -> bool:
        s = self._read()
        if s is None or s.status != "active":
            return False
        return time.time() >= s.expires_at

    def cancel(self, reason: str) -> None:
        s = self._read()
        if s is not None:
            s.status = "cancelled"
            s.work_done_summary = reason
            self._write(s)

    def complete(self, summary: Optional[str] = None) -> None:
        s = self._read()
        if s is not None:
            s.status = "completed"
            if summary:
                s.work_done_summary = summary
            self._write(s)

    def expire(self) -> None:
        s = self._read()
        if s is not None:
            s.status = "expired"
            self._write(s)


_auto_crown_store: Optional[AutoCrownStore] = None


def get_auto_crown_store() -> AutoCrownStore:
    global _auto_crown_store
    if _auto_crown_store is None:
        _auto_crown_store = AutoCrownStore()
    return _auto_crown_store
