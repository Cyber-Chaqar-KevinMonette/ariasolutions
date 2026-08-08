"""auto_crown.py — Timed autonomous operation (M43).

AutoCrownStore: backed by auto_crown.json in data_dir.
Trust tiers: 1=1hr, 2=2hr, 3=4hr, 4=12hr.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# duration-ceiling-raise-d (Kevin, 2026-07-25): "I need more auto hours
# because my system is slower... we will have to increase it to 12 hours
# max." Tier 4 raised 8.0 -> 12.0. Public (not _-prefixed) because
# tools/auto_tools.py and cockpit/tier_screen.py each used to hardcode
# their OWN copy of this exact dict -- three independent copies that
# could silently drift apart. One source now, imported everywhere.
TRUST_TIER_MAX_HOURS: dict[int, float] = {
    1: 1.0,
    2: 2.0,
    3: 4.0,
    4: 12.0,
}
# Back-compat alias -- keep the old private name working for anything
# still importing it directly.
_TRUST_TIER_MAX_HOURS = TRUST_TIER_MAX_HOURS


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

    def get_max_trust_tier(self) -> int:  # tier-expiry-d
        """The approved ceiling -- but a TIMED elevation (tier > 1) that
        has run past its own expires_at auto-reverts to tier 1 right
        here, on read. Kevin, 2026-07-20/21: "when tier 3 ends if it is
        timed it should go back to tier 1" -- before this, an elevated
        ceiling had no expiry at all and stayed elevated until a manual
        kill switch. Lazy revert-on-read matches this codebase's existing
        pattern (interrupts.py's flags, the sentinel caches) -- no
        background timer/thread needed."""
        try:
            if self._trust_path.exists():
                data = json.loads(self._trust_path.read_text())
                tier = int(data.get("max_tier", 1))
                expires_at = data.get("expires_at")
                if tier > 1 and expires_at is not None and time.time() > expires_at:
                    self._trust_path.write_text(
                        json.dumps({"max_tier": 1, "expires_at": None}, indent=2)
                    )
                    return 1
                return tier
        except Exception:  # noqa: BLE001
            pass
        return 1

    def trust_tier_remaining_seconds(self) -> int:  # tier-expiry-d
        """Kevin, 2026-07-21: "have a timer show when elevated tiers
        end." 0 when tier 1 (no timer, the permanent baseline) or when
        there's no expiry recorded; the countdown otherwise. Read-only —
        mirrors modes_crown.profiles.lease_remaining_seconds()'s shape."""
        try:
            if not self._trust_path.exists():
                return 0
            data = json.loads(self._trust_path.read_text())
            tier = int(data.get("max_tier", 1))
            expires_at = data.get("expires_at")
            if tier <= 1 or expires_at is None:
                return 0
            return max(0, int(expires_at - time.time()))
        except Exception:  # noqa: BLE001
            return 0

    def set_trust_tier(self, tier: int, *, expires_in_hours: float | None = None) -> None:
        """Raise or lower the approved ceiling. Kevin, 2026-07-21: "we
        agreed to change it to switch to tier three then approve 3
        hours" -- raising a tier now carries its OWN timed expiry by
        default (that tier's own hour allowance from
        _TRUST_TIER_MAX_HOURS, the same number already shown in the
        Tier screen's list), so the ceremony is exactly "pick the tier,
        it's timed" with no separate duration prompt needed. Tier 1 (or
        an explicit expires_in_hours=0) is the permanent baseline —
        never expires, matching the kill switch's instant/permanent
        drop."""
        if tier not in _TRUST_TIER_MAX_HOURS:
            raise ValueError(f"Invalid trust tier {tier}. Valid: 1-4.")
        expires_at = None
        if tier > 1:
            hours = (_TRUST_TIER_MAX_HOURS[tier] if expires_in_hours is None
                     else expires_in_hours)
            if hours:
                expires_at = time.time() + hours * 3600
        self._trust_path.write_text(
            json.dumps({"max_tier": tier, "expires_at": expires_at}, indent=2)
        )

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

    def extend(self, additional_hours: float) -> AutoSession:  # mid-session-add-time-d
        """Add time to the currently active session WITHOUT interrupting
        the running loop -- this only edits the stored session record
        (expires_at + duration_hours); the loop just reads a later
        deadline on its next budget check, same as it always does.

        Kevin, 2026-07-25: "I should be able to change the hours of auto
        mid work flow... without stopping her from work." Factored out of
        ExtendAutoTool's execute() (which used to reach into the private
        _write() directly from another module) so the cockpit's own
        add-time button/command can call the same real logic instead of
        a second copy."""
        s = self._read()
        if s is None or s.status != "active":
            raise ValueError("no active auto session to extend")
        s.expires_at += additional_hours * 3600
        s.duration_hours += additional_hours
        self._write(s)
        return s

    def extend_trust_tier(self, additional_hours: float) -> bool:  # add-time-tier-sync-d
        """+1h's other half. Kevin, 2026-07-25: "the plus one hour should
        take effect for the Auto and for the tier that is activated, not
        just for one of them." `extend()` above only ever touched the auto
        SESSION's own expires_at (auto_crown.json); the elevated trust
        tier lives in a completely separate file (auto_trust_tier.json,
        see set_trust_tier/get_max_trust_tier) with its own independent
        countdown -- untouched by extend(), it could revert Aria back to
        tier 1 mid-session even while "Auto" still reads as active.

        No-op (returns False) when there's nothing timed to extend: tier 1
        is the permanent baseline (no timer, matches
        trust_tier_remaining_seconds()'s own "0 when tier 1" rule) and an
        untimed elevation (expires_at is None) never expires either."""
        try:
            if not self._trust_path.exists():
                return False
            data = json.loads(self._trust_path.read_text())
            tier = int(data.get("max_tier", 1))
            expires_at = data.get("expires_at")
            if tier <= 1 or expires_at is None:
                return False
            data["expires_at"] = expires_at + additional_hours * 3600
            self._trust_path.write_text(json.dumps(data, indent=2))
            return True
        except Exception:  # noqa: BLE001
            return False

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
