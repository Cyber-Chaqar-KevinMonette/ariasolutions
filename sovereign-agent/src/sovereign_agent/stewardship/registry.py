"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/registry.py — the sentinel registry                        ║
║                                                                           ║
║  A single source of truth for "which sentinels exist." Doctor calls    ║
║  it. CLI calls it. Cockpit (future panel) calls it. Aria calls it      ║
║  when she wants to speak with one.                                      ║
║                                                                           ║
║  Sentinels register themselves via the @register_sentinel decorator    ║
║  applied at module-import time. The discovery import in this module's   ║
║  __init__ ensures every concrete sentinel is loaded.                    ║
║                                                                           ║
║  Registration is class-based (not instance-based) so each consumer     ║
║  constructs their own instance bound to their data_dir. This keeps    ║
║  tests isolated and avoids singleton-state confusion.                  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

from pathlib import Path
from typing import Type

from .base import HealthStatus, Notification, Sentinel, SentinelReport


# Class-level registry: id → Sentinel subclass
_REGISTRY: dict[str, Type[Sentinel]] = {}


def register_sentinel(cls: Type[Sentinel]) -> Type[Sentinel]:
    """Decorator. Apply to a Sentinel subclass to register it globally.

    @register_sentinel
    class MySentinel(Sentinel):
        ...
    """
    # Use a temporary instance just to read the .id property
    # (id is a property requiring instantiation; we use a sentinel data_dir)
    try:
        probe = cls(Path("/tmp"))
        sentinel_id = probe.id
    except Exception:
        raise ValueError(f"sentinel class {cls.__name__} has no usable .id property")
    if not sentinel_id:
        raise ValueError(f"sentinel class {cls.__name__} returned empty id")
    if sentinel_id in _REGISTRY:
        # Re-registration (likely test reload) — just overwrite, last wins
        pass
    _REGISTRY[sentinel_id] = cls
    return cls


def registered_ids() -> list[str]:
    return sorted(_REGISTRY.keys())


def get_sentinel_class(sentinel_id: str) -> Type[Sentinel] | None:
    return _REGISTRY.get(sentinel_id)


def instantiate(sentinel_id: str, data_dir: Path) -> Sentinel | None:
    """Build a Sentinel instance bound to data_dir, or None if id unknown."""
    cls = _REGISTRY.get(sentinel_id)
    if cls is None:
        return None
    return cls(data_dir)


def instantiate_all(data_dir: Path) -> list[Sentinel]:
    """Build one instance per registered sentinel, in id-sorted order."""
    return [_REGISTRY[sid](data_dir) for sid in sorted(_REGISTRY.keys())]


# ─── Aggregate operations ────────────────────────────────────────────────


def gather_health(data_dir: Path) -> list[HealthStatus]:
    """Health snapshot of every sentinel. Used by doctor + cockpit panel."""
    out: list[HealthStatus] = []
    for sentinel in instantiate_all(data_dir):
        try:
            sentinel.bootstrap()
            if not sentinel.is_enabled():
                out.append(HealthStatus(
                    sentinel_id=sentinel.id,
                    level="unknown",
                    summary="disabled via kill switch",
                ))
                continue
            out.append(sentinel.health_status())
        except Exception as e:
            out.append(HealthStatus(
                sentinel_id=sentinel.id,
                level="error",
                summary=f"health_status raised: {type(e).__name__}",
                detail=str(e)[:200],
            ))
    return out


def list_sentinel_warnings(data_dir: Path, *, limit: int = 10) -> list[HealthStatus]:
    """sentinel-warnings-detail-d (Kevin, 2026-07-25): "she said 3 sentinels
    are showing warnings... when I asked her which 3 she could not say."
    gather_health() already carries every sentinel's id + summary — the
    data was never vague. doctor.check_sentinels_roster and self_report
    each independently truncated it to "the first one" or nothing before
    it reached a reply. One shared function, worst-first (errors before
    warnings), so "which ones?" is answerable the same way everywhere."""
    healths = gather_health(data_dir)
    warns = [h for h in healths if getattr(h, "level", "") in ("warning", "error")]
    warns.sort(key=lambda h: 0 if h.level == "error" else 1)
    return warns[:limit]


def gather_unread_notifications(data_dir: Path) -> list[Notification]:
    """Every unread notification across every sentinel, newest-first within sentinel."""
    out: list[Notification] = []
    for sentinel in instantiate_all(data_dir):
        try:
            out.extend(sentinel.read_inbox(only_unread=True))
        except Exception:
            continue
    out.sort(key=lambda n: n.observed_at, reverse=True)
    return out


def scan_all(data_dir: Path) -> list[SentinelReport]:
    """Run every enabled sentinel's scan. Failures don't stop the loop."""
    out: list[SentinelReport] = []
    for sentinel in instantiate_all(data_dir):
        try:
            sentinel.bootstrap()
            if not sentinel.is_enabled():
                continue
            out.append(sentinel.scan())
        except Exception as e:
            # Soft fail — emit a meta notification so the operator sees it
            try:
                sentinel.notify(
                    severity="alert",
                    title="sentinel scan crashed",
                    message=f"{type(e).__name__}: {e}",
                    addressed_to="operator",
                )
            except Exception:
                pass
    return out


SENTINEL_REGISTRY = _REGISTRY  # public alias for external consumers  # sentinel-registry-alias-d

__all__ = [
    "SENTINEL_REGISTRY",
    "register_sentinel", "registered_ids", "get_sentinel_class",
    "instantiate", "instantiate_all",
    "gather_health", "gather_unread_notifications", "scan_all",
]
