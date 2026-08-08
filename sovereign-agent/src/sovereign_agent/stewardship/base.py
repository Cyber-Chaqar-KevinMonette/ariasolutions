"""
╔══════════════════════════════════════════════════════════════════════════╗
║  stewardship/base.py — the unified Sentinel contract                    ║
║                                                                           ║
║  Every sentinel obeys the same shape. That shape mirrors the top-level  ║
║  charter (SIGNAL.md) at a smaller scale. Self-similar / fractal:         ║
║                                                                           ║
║    CHARTER (SIGNAL.md)                                                   ║
║      ↳ MANIFEST (each Sentinel's articles + hash)                       ║
║          ↳ CATALOGS (each scan's persisted output)                      ║
║              ↳ ATOMS (individual entries inside each catalog)            ║
║                                                                           ║
║  Same machinery at every depth: hash-bound integrity, audit trail,       ║
║  kill switch, integrity check. Going inward instead of outward.         ║
║                                                                           ║
║  What every Sentinel gets for free                                      ║
║                                                                           ║
║    • Manifest persistence — `<data_dir>/sentinels/<id>/manifest.json`   ║
║    • Catalog directory     — `<data_dir>/sentinels/<id>/catalogs/`      ║
║    • Notification channel  — emits events to events.jsonl AND to        ║
║                              `<data_dir>/sentinels/<id>/inbox.jsonl`    ║
║      (the inbox is for unread notifications the operator/Aria sees)    ║
║    • Kill switch           — per-sentinel env var (e.g., SOV_NO_CACHE_  ║
║                              SENTINEL) AND a master switch             ║
║                              (SOV_NO_SENTINELS) that disables all of   ║
║                              them at once for diagnostic isolation.    ║
║    • Voice slot            — reserved fields for future LLM-driven     ║
║                              communication. v0.2.34: scaffolded but   ║
║                              never invoked. v0.2.35+: Aria can dial    ║
║                              individual sentinels when she needs them. ║
║                                                                           ║
║  What every concrete Sentinel must implement                            ║
║                                                                           ║
║    • scan()           → SentinelReport                                   ║
║    • health_status()  → HealthStatus                                     ║
║    • articles()       → list[str]  (its own self-constitution)         ║
║                                                                           ║
║  Optional but encouraged                                                ║
║                                                                           ║
║    • proposals(catalog)    → list[Proposal]                             ║
║    • coverage_gaps(catalog) → list[Gap]                                 ║
║    • heal(proposal)         → ApplyResult  (most sentinels don't        ║
║                                              implement this — Tier 1   ║
║                                              proposes, operator acts)   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import json
import os
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


# ─── Common types ────────────────────────────────────────────────────────

Severity = Literal["info", "warning", "alert"]
HealthLevel = Literal["ok", "warning", "error", "unknown"]


@dataclass
class SentinelManifest:
    """Each Sentinel's self-constitution. Hash-bound.

    Mirrors SIGNAL.md at sentinel scale. The articles list IS the contract
    the sentinel binds itself to. The hash is recomputed on every load; if
    it doesn't match the stored hash, the sentinel reports its own
    integrity broken (a sentinel must be honest about itself first).
    """
    id: str                              # 'cache', 'glyphs', etc.
    title: str
    tier: int = 1                        # stewardship tier per charter
    articles: list[str] = field(default_factory=list)
    kill_switch_env: str = ""             # per-sentinel kill switch
    voice_model: str = ""                 # reserved: preferred LLM (v0.2.35+)
    voice_persona: str = ""               # reserved: persona prompt (v0.2.35+)
    created_at: str = ""
    manifest_hash: str = ""              # sha256 of articles+title (excluding self)

    def compute_hash(self) -> str:
        """Compute the hash over the binding contract (NOT including the hash itself)."""
        blob = json.dumps({
            "id": self.id, "title": self.title, "tier": self.tier,
            "articles": self.articles,
        }, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()

    def verify_hash(self) -> bool:
        return self.manifest_hash == self.compute_hash()

    def seal(self) -> None:
        """Compute and stamp the current hash. Called on first creation."""
        self.manifest_hash = self.compute_hash()


@dataclass
class HealthStatus:
    """A sentinel's snapshot health.

    The doctor consults this; the cockpit can surface it; Aria can ask
    for it. Each sentinel decides what 'healthy' means for itself.
    """
    sentinel_id: str
    level: HealthLevel
    summary: str
    detail: str = ""
    observed_at: str = ""


@dataclass
class SentinelReport:
    """One scan's full result.

    Catalogs persist to disk (one JSON per catalog name); the report is
    the in-memory bundle returned to callers.
    """
    sentinel_id: str
    observed_at: str
    catalog_name: str
    findings_count: int
    summary: str
    catalog_path: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Notification:
    """One notification from a sentinel — to Aria, to the operator, or both.

    Lives in the sentinel's inbox.jsonl. Each line is one Notification.
    Stays unread until `sov sentinels notifications --ack` marks it
    consumed.
    """
    sentinel_id: str
    severity: Severity
    title: str
    message: str
    observed_at: str
    acknowledged: bool = False
    addressed_to: str = "operator"       # 'operator', 'aria', or 'both'
    data: dict[str, Any] = field(default_factory=dict)


# ─── The Sentinel ABC ────────────────────────────────────────────────────

# Master kill switch disables ALL sentinels at once. For diagnostic
# isolation when something feels wrong with the framework itself.
MASTER_KILL_SWITCH_ENV = "SOV_NO_SENTINELS"


class Sentinel(ABC):
    """Base class every concrete sentinel inherits.

    Lifecycle:
      sentinel = MySentinel(data_dir)
      sentinel.bootstrap()        # seals manifest if first run
      if sentinel.is_enabled():
          report = sentinel.scan()
          for proposal in sentinel.proposals(report):
              # operator decides whether to act
      sentinel.notify("info", "...", "...")
      health = sentinel.health_status()
    """

    # ── Required subclass attributes (defaults raise on direct use) ─────

    @property
    @abstractmethod
    def id(self) -> str:
        """Stable short id like 'cache' or 'glyphs'. Used as dir name."""

    @property
    @abstractmethod
    def title(self) -> str: ...

    @property
    def tier(self) -> int:
        return 1

    @property
    def kill_switch_env(self) -> str:
        return f"SOV_NO_{self.id.upper().replace('-', '_')}_SENTINEL"

    @property
    def voice_model(self) -> str:
        return ""

    @property
    def voice_persona(self) -> str:
        return ""

    # ── Required behavior ────────────────────────────────────────────────

    @abstractmethod
    def articles(self) -> list[str]:
        """The self-constitution: short binding statements this sentinel obeys."""

    @abstractmethod
    def scan(self) -> SentinelReport:
        """Walk the world this sentinel watches. Return a report; catalog is persisted."""

    @abstractmethod
    def health_status(self) -> HealthStatus:
        """A snapshot suitable for the doctor or cockpit panel."""

    # ── Optional behavior (defaults are sensible no-ops) ────────────────

    def proposals(self, report: SentinelReport) -> list[dict]:
        """Actionable suggestions derived from the latest scan."""
        return []

    def coverage_gaps(self, report: SentinelReport) -> list[dict]:
        """Areas the sentinel can't reach yet — opportunities to extend coverage."""
        return []

    # ── Boilerplate the base class provides ─────────────────────────────

    def __init__(self, data_dir: Path):
        self._data_dir = Path(data_dir)

    @property
    def sentinel_dir(self) -> Path:
        """data_dir/sentinels/<id>/"""
        p = self._data_dir / "sentinels" / self.id
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def catalogs_dir(self) -> Path:
        p = self.sentinel_dir / "catalogs"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def manifest_path(self) -> Path:
        return self.sentinel_dir / "manifest.json"

    @property
    def inbox_path(self) -> Path:
        return self.sentinel_dir / "inbox.jsonl"

    # ── Kill switch + bootstrap ─────────────────────────────────────────

    def is_enabled(self) -> bool:
        """True unless master OR per-sentinel kill switch is set."""
        if os.environ.get(MASTER_KILL_SWITCH_ENV):
            return False
        if self.kill_switch_env and os.environ.get(self.kill_switch_env):
            return False
        return True

    def bootstrap(self) -> SentinelManifest:
        """Create or load this sentinel's manifest. Idempotent.

        On first run: composes the manifest, seals it (hashes), persists.
        On subsequent runs: loads, verifies hash, returns.
        If the hash doesn't match → the manifest has been tampered with;
        the sentinel reports its own integrity broken.
        """
        if self.manifest_path.is_file():
            try:
                data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                m = SentinelManifest(**data)
                # If articles have evolved in code, re-seal (constitutional
                # amendments are normal; manifest tracks the current truth)
                expected = m.compute_hash()
                code_articles = self.articles()
                if list(m.articles) != list(code_articles) or m.manifest_hash != expected:
                    m.articles = code_articles
                    m.title = self.title
                    m.tier = self.tier
                    m.kill_switch_env = self.kill_switch_env
                    m.voice_model = self.voice_model
                    m.voice_persona = self.voice_persona
                    m.seal()
                    self.manifest_path.write_text(
                        json.dumps(asdict(m), indent=2, sort_keys=True),
                        encoding="utf-8",
                    )
                return m
            except (json.JSONDecodeError, TypeError, KeyError):
                pass  # fall through to fresh create
        m = SentinelManifest(
            id=self.id,
            title=self.title,
            tier=self.tier,
            articles=self.articles(),
            kill_switch_env=self.kill_switch_env,
            voice_model=self.voice_model,
            voice_persona=self.voice_persona,
            created_at=_iso_now(),
        )
        m.seal()
        self.manifest_path.write_text(
            json.dumps(asdict(m), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return m

    # ── Catalog persistence ─────────────────────────────────────────────

    def catalog_path(self, name: str = "default") -> Path:
        return self.catalogs_dir / f"{name}.json"

    def save_catalog(self, data: dict, name: str = "default") -> Path:
        """Persist a catalog. Returns the path.

        Each sentinel can have many catalogs (e.g., cache sentinel may
        have 'venv-state', 'lockfile-state', 'wheel-cache'). The default
        is just 'default'.
        """
        p = self.catalog_path(name)
        p.write_text(
            json.dumps(data, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        return p

    def load_catalog(self, name: str = "default") -> dict | None:
        p = self.catalog_path(name)
        if not p.is_file():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    # ── Notification channel ────────────────────────────────────────────

    def notify(
        self,
        severity: Severity,
        title: str,
        message: str,
        addressed_to: str = "operator",
        data: dict[str, Any] | None = None,
    ) -> Notification:
        """Emit a notification.

        Writes to TWO places:
          1. The sentinel's inbox.jsonl (operator/aria can review)
          2. events.jsonl via emit_event (audit trail)

        Failures emitting to events.jsonl don't break the inbox write —
        the inbox is the durable source of truth; events.jsonl is the
        cross-cutting audit log.
        """
        notification = Notification(
            sentinel_id=self.id,
            severity=severity,
            title=title,
            message=message,
            observed_at=_iso_now(),
            addressed_to=addressed_to,
            data=data or {},
        )
        # Inbox append
        try:
            with self.inbox_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(notification), default=str) + "\n")
        except OSError:
            pass
        # Events log — best effort
        try:
            from ..events import emit_event
            from ulid import ULID
            emit_event(
                flag=f"sentinel_notify_{self.id}",
                plane="meta",
                trace_id=str(ULID()),
                payload={
                    "sentinel_id": self.id,
                    "severity": severity,
                    "title": title,
                    "message": message[:500],
                    "addressed_to": addressed_to,
                },
            )
        except Exception:
            pass
        return notification

    def read_inbox(self, only_unread: bool = True) -> list[Notification]:
        """Return notifications from the inbox."""
        if not self.inbox_path.is_file():
            return []
        out: list[Notification] = []
        try:
            for line in self.inbox_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    n = Notification(**data)
                    if only_unread and n.acknowledged:
                        continue
                    out.append(n)
                except (json.JSONDecodeError, TypeError):
                    continue
        except OSError:
            pass
        return out

    def acknowledge_all(self) -> int:
        """Mark every notification in inbox as acknowledged. Returns count touched."""
        if not self.inbox_path.is_file():
            return 0
        lines = self.inbox_path.read_text(encoding="utf-8").splitlines()
        count = 0
        out_lines = []
        for line in lines:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                if not data.get("acknowledged"):
                    count += 1
                data["acknowledged"] = True
                out_lines.append(json.dumps(data, default=str))
            except json.JSONDecodeError:
                out_lines.append(line)
        self.inbox_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        return count


# ─── Utility ─────────────────────────────────────────────────────────────


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = [
    "Severity", "HealthLevel",
    "SentinelManifest", "HealthStatus", "SentinelReport", "Notification",
    "Sentinel", "MASTER_KILL_SWITCH_ENV",
]
