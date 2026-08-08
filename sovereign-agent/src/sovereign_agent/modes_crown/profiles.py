"""modes_crown/profiles.py — the mode crown: declarative operator modes.
(FABLE II · M6 · modes-crown-d)

Every mode is a PROFILE — {base mode, tier ceiling, lease seconds,
wondering, work allowed, garden required, typed confirmation} — not a
scatter of flags. The crown composes what already exists rather than
inventing authority:

  · base mode        → cockpit_modes (chat/work — the enforcement root
                       every consumer already reads)
  · leases           → work_interval.start_work_interval (Workstream N)
                       + session_bridge.arm_lease (M5's record_action
                       wire: dispatches observable, expiry refuses)
  · countdown        → auto_crown.json (the status bar already renders it)
  · trust ceilings   → AutoCrownStore trust tiers (auto-3h additionally
                       needs the existing T3-approved tier unlock)

PROTOCOL-ZERO / `/halt` / `/rest` are untouched and identical in every
mode. Auto modes NEVER self-extend: a lease ends → the bridge refuses new
goals → re-arming is a fresh, explicit operator act.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

MARK = "modes-crown-d"

# The exact phrase that arms the highest workflow lease. Typing it is the
# Tier-3-spirit confirmation — deliberate, unambiguous, unfakeable by a
# stray keypress.
AUTO3H_CONFIRMATION = "I approve 3 hours of autonomy"


class CrownError(Exception):
    pass


@dataclass(frozen=True)
class ModeProfile:
    mode_id: str
    title: str
    base: str                    # cockpit_modes base: "chat" | "work"
    tier_ceiling: int            # the queue-level intent, stated plainly
    description: str
    lease_seconds: int = 0       # >0 → arming creates a bounded lease
    wondering: bool = False      # autonomous wondering allowed?
    work_allowed: bool = False   # may the bridge start goal sessions?
    garden_required: bool = False
    typed_confirmation: str = "" # phrase required to arm ("" = none)
    trust_tier: int = 1          # AutoCrownStore tier the lease needs

    def as_dict(self) -> dict:
        return asdict(self)


PROFILES: dict[str, ModeProfile] = {
    "chat": ModeProfile(
        "chat", "Chat", base="chat", tier_ceiling=1,
        description="The default. Conversational; no autonomous loops; "
                    "tools only when asked."),
    "work": ModeProfile(
        "work", "Work", base="work", tier_ceiling=1, work_allowed=True,
        wondering=True,
        description="High leverage: planned queues, mid-run extension, "
                    "autonomous wondering — inside every standing gate."),
    "auto-1h": ModeProfile(
        "auto-1h", "Auto · 1 hour", base="work", tier_ceiling=1,
        work_allowed=True, wondering=True, lease_seconds=3600, trust_tier=1,
        description="Work + a 1-hour lease: queued goals run back-to-back; "
                    "the lease boundary pauses everything for re-approval."),
    "auto-3h": ModeProfile(
        "auto-3h", "Auto · 3 hours", base="work", tier_ceiling=1,
        work_allowed=True, wondering=True, lease_seconds=3 * 3600,
        trust_tier=3, typed_confirmation=AUTO3H_CONFIRMATION,
        description="The highest workflows: a 3-hour lease. Arming requires "
                    "the typed confirmation AND the T3-unlocked trust tier."),
    "focus": ModeProfile(
        "focus", "Focus", base="work", tier_ceiling=1, work_allowed=True,
        wondering=False, garden_required=True,
        description="Deep work: ONE goal, garden REQUIRED, wondering muted, "
                    "notifications muted."),
    "companion": ModeProfile(
        "companion", "Companion", base="chat", tier_ceiling=1,
        wondering=True,
        description="Presence: conversation and wondering — no work "
                    "sessions."),
    "guardian": ModeProfile(
        "guardian", "Guardian", base="chat", tier_ceiling=0,
        description="Read-only watch: sentinels and observation only; the "
                    "bridge refuses all work."),
}

DEFAULT_MODE = "chat"


def _crown_path(data_dir: Path | None = None) -> Path:
    if data_dir is None:
        from sovereign_agent.config import SETTINGS

        data_dir = SETTINGS.paths.data_dir
    return Path(data_dir) / "mode_crown.json"


def crown_armed(data_dir: Path | None = None) -> bool:
    """True only once the operator has explicitly picked a crown mode
    (mode_crown.json exists). The crown gate is a no-op until then — a
    fresh install or an operator who has never touched F2/`/modes` keeps
    TODAY'S behavior (the base chat/work pair only ever gated autonomous
    loops, never an explicit `/work` dispatch)."""
    try:
        return _crown_path(data_dir).exists()
    except Exception:  # noqa: BLE001
        return False


def current_profile(data_dir: Path | None = None) -> ModeProfile:
    """The active crown profile. Falls back to the base cockpit mode when
    the crown was never set (fully backward compatible)."""
    try:
        path = _crown_path(data_dir)
        if path.exists():
            record = json.loads(path.read_text(encoding="utf-8"))
            mode_id = record.get("mode_id", "")
            if mode_id in PROFILES:
                return PROFILES[mode_id]
            # custom-auto-hours-d — an ad-hoc profile (e.g. auto-custom)
            # rides along in the record itself; reconstruct it rather
            # than silently losing the real armed hours/tier.
            stored = record.get("profile")
            if stored:
                return ModeProfile(**stored)
    except Exception:  # noqa: BLE001
        pass
    try:
        from sovereign_agent.cockpit_modes import is_work_mode

        return PROFILES["work"] if is_work_mode() else PROFILES[DEFAULT_MODE]
    except Exception:  # noqa: BLE001
        return PROFILES[DEFAULT_MODE]


def crown_state(data_dir: Path | None = None) -> dict:
    try:
        path = _crown_path(data_dir)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        pass
    return {}


def crown_wondering_allowed(data_dir: Path | None = None) -> bool | None:
    """Tri-state for curiosity.py: True/False when a crown mode is set,
    None when the crown was never armed (→ today's behavior)."""
    try:
        path = _crown_path(data_dir)
        if not path.exists():
            return None
        record = json.loads(path.read_text(encoding="utf-8"))
        mode_id = record.get("mode_id", "")
        profile = PROFILES.get(mode_id)
        if profile is None:
            stored = record.get("profile")  # custom-auto-hours-d
            profile = ModeProfile(**stored) if stored else None
        return None if profile is None else profile.wondering
    except Exception:  # noqa: BLE001
        return None


def set_crown_mode(mode_id: str, *, confirm: str = "", reason: str = "",
                   data_dir: Path | None = None) -> ModeProfile:
    """Arm a mode. Operator-only, explicit, evented. Auto modes create a
    bounded lease; every other mode disarms whatever lease was live."""
    profile = PROFILES.get(mode_id)
    if profile is None:
        raise CrownError(f"unknown mode {mode_id!r} — one of {sorted(PROFILES)}")
    if profile.typed_confirmation and confirm.strip() != profile.typed_confirmation:
        raise CrownError(
            f"mode {mode_id!r} arms only with the typed confirmation: "
            f"{profile.typed_confirmation!r}")
    return _arm_profile(profile, mode_id, reason, data_dir)


def custom_hours_trust_tier(hours: float) -> int:  # custom-auto-hours-d
    """The lowest trust tier whose ceiling covers `hours`. Reused by
    arm_custom_hours() and by the cockpit UI so a picker can show which
    tier a chosen duration will need BEFORE arming."""
    from sovereign_agent.auto_crown import TRUST_TIER_MAX_HOURS

    for tier in sorted(TRUST_TIER_MAX_HOURS):
        if hours <= TRUST_TIER_MAX_HOURS[tier]:
            return tier
    return max(TRUST_TIER_MAX_HOURS)


def arm_custom_hours(hours: float, *, reason: str = "",
                     data_dir: Path | None = None) -> ModeProfile:  # custom-auto-hours-d
    """custom-auto-hours-d (Kevin, 2026-07-25): "a drop down menu for
    hours. Max 12. Min 1." The two named auto-* profiles (auto-1h,
    auto-3h) stay as-is — this adds a THIRD path for any duration in
    between/beyond them, composing with the exact same trust-tier
    ceiling enforcement (_arm_lease -> AutoCrownStore.start()) rather
    than inventing a parallel safety check. No profile-specific typed
    confirmation of its own (auto-3h's is a deliberate EXTRA ceremony
    for that one named preset, not a general rule) — the tier ceremony
    (approval_phrase, when the tier must be raised) is the real gate,
    same as auto-1h needs no extra phrase at tier 1."""
    if not (0.1 <= hours <= 12.0):
        raise CrownError(f"hours must be between 0.1 and 12, got {hours}")
    profile = ModeProfile(
        "auto-custom", f"Auto · {hours:g}h", base="work", tier_ceiling=1,
        work_allowed=True, wondering=True, lease_seconds=int(hours * 3600),
        trust_tier=custom_hours_trust_tier(hours),
        description=f"Work + a {hours:g}-hour lease, picked directly.",
    )
    return _arm_profile(profile, "auto-custom", reason, data_dir)


def _arm_profile(profile: ModeProfile, mode_id: str, reason: str,
                 data_dir: Path | None) -> ModeProfile:  # custom-auto-hours-d
    """The shared body of arming ANY profile (named or ad-hoc): disarm
    whatever lease was live, set the base mode, arm a new lease if the
    profile wants one, persist + event. Factored out of set_crown_mode
    so arm_custom_hours() (an ad-hoc ModeProfile, not one of the fixed
    PROFILES entries) reuses the exact same sequence instead of a
    parallel, driftable copy."""
    # 1. whatever lease was live ends now — modes never stack leases
    _disarm_lease(reason=f"mode change → {mode_id}")

    # 2. the base mode every existing consumer reads
    from sovereign_agent.cockpit_modes import CockpitMode, set_mode

    set_mode(CockpitMode(profile.base), reason=f"crown:{mode_id}"
             + (f" — {reason}" if reason else ""))

    # 3. auto modes: a bounded, observable lease
    lease_id = ""
    if profile.lease_seconds:
        lease_id = _arm_lease(profile)

    # 4. persist + event
    path = _crown_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({
        "mode_id": mode_id,
        "set_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lease_session_id": lease_id,
        "reason": reason[:200],
        # custom-auto-hours-d: ad-hoc profiles (auto-custom) aren't in the
        # static PROFILES dict, so the full profile rides along here --
        # current_profile() reconstructs from this when the mode_id isn't
        # a known preset, instead of silently falling back to "work" and
        # losing the actual armed hours/tier.
        "profile": profile.as_dict(),
    }, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    try:
        from sovereign_agent.events import emit_event

        emit_event("mode-crown-d", plane="control", trace_id="mode-crown",
                   payload={"mode": mode_id, "lease_seconds": profile.lease_seconds,
                            "lease_session_id": lease_id,
                            "reason": reason[:200] or "(none)"})
    except Exception:  # noqa: BLE001
        pass
    return profile


def _arm_lease(profile: ModeProfile) -> str:
    """Compose work_interval + auto_crown + the M5 bridge wire. The
    operator's set_crown_mode call IS the explicit approval act."""
    from sovereign_agent import session_bridge
    from sovereign_agent.auto_crown import get_auto_crown_store
    from sovereign_agent.work_interval import WorkIntervalConfig, start_work_interval

    store = get_auto_crown_store()
    hours = profile.lease_seconds / 3600.0
    # The trust-tier ceiling is the EXISTING T3-gated unlock — honored, not
    # bypassed. auto-3h on a tier-1 vessel refuses with the unlock path.
    lease = start_work_interval(
        f"crown-{profile.mode_id}",
        config=WorkIntervalConfig(interval_seconds=profile.lease_seconds),
        approved=True,
    )
    try:
        store.start(duration_hours=hours, trust_tier=profile.trust_tier,
                    reason=f"crown mode {profile.mode_id}",
                    session_id=lease.session_id)
    except ValueError as exc:
        raise CrownError(
            f"{exc} — unlock via the existing T3 approval "
            f"(set_auto_trust_tier), then re-arm.") from exc
    # tier-auto-duration-sync-d (Kevin, 2026-07-25): "the tier is 4 hours and
    # the auto is 3 hours but they need to match so the timer at the top
    # shows." The elevated tier carries its OWN countdown (auto_trust_tier
    # .json), timed independently of this lease -- left alone, it defaults
    # to that tier's generic MAX ceiling (e.g. 4h for tier 3) regardless of
    # what duration is actually being armed here. Re-pin it to THIS lease's
    # own hours every time one arms, whether the tier ceiling was just
    # freshly raised or was already sufficient (no confirmation ceremony
    # fired) -- one authoritative place, covers every arming path.
    if profile.trust_tier > 1:
        store.set_trust_tier(profile.trust_tier, expires_in_hours=hours)
    session_bridge.arm_lease(lease)
    return lease.session_id


def _disarm_lease(*, reason: str) -> None:
    try:
        from sovereign_agent import session_bridge

        if session_bridge.active_lease() is not None:
            session_bridge.disarm_lease()
    except Exception:  # noqa: BLE001
        pass
    try:
        from sovereign_agent.auto_crown import get_auto_crown_store

        store = get_auto_crown_store()
        s = store.status()
        if s is not None and s.status == "active":
            store.cancel(reason)
    except Exception:  # noqa: BLE001
        pass


def lease_remaining_seconds() -> int:
    """Seconds left on the armed lease (0 when none). The bridge refusal is
    the enforcement; this is the observability read."""
    try:
        from sovereign_agent import session_bridge
        from sovereign_agent.autonomy.session import time_remaining

        lease = session_bridge.active_lease()
        return time_remaining(lease) if lease is not None else 0
    except Exception:  # noqa: BLE001
        return 0
