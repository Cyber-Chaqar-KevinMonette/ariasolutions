"""Runtime configuration. Single source of paths and tunables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _xdg_config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _xdg_data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")


@dataclass(frozen=True)
class Paths:
    """All filesystem paths the agent uses. Created on first run."""

    config_dir: Path = field(default_factory=lambda: _xdg_config_home() / "sovereign-agent")
    data_dir: Path = field(default_factory=lambda: _xdg_data_home() / "sovereign-agent")

    @property
    def sandbox_dir(self) -> Path:
        return self.data_dir / "sandbox"

    @property
    def events_dir(self) -> Path:
        return self.data_dir / "events"

    @property
    def events_jsonl(self) -> Path:
        # Daily-rotated; current day's file. Rotation handled by events.py.
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.events_dir / f"events-{today}.jsonl"

    @property
    def events_db(self) -> Path:
        return self.data_dir / "events.db"

    @property
    def atoms_db(self) -> Path:
        return self.data_dir / "atoms.db"

    @property
    def blobs_dir(self) -> Path:
        # Content-addressed blob store for oversized event payloads / atom content
        return self.data_dir / "blobs"

    @property
    def review_queue_dir(self) -> Path:
        return self.data_dir / "review-queue"

    @property
    def approvals_dir(self) -> Path:
        return self.config_dir / "approvals"

    @property
    def secret_key_file(self) -> Path:
        return self.config_dir / "secret.key"

    @property
    def halt_flag(self) -> Path:
        return self.config_dir / "HALT"

    @property
    def backlog_yaml(self) -> Path:
        return self.config_dir / "backlog.yaml"

    @property
    def continuations_dir(self) -> Path:
        # Re-trigger architecture state (one YAML per task). v0.2.5+
        return self.data_dir / "continuations"

    @property
    def palace_db(self) -> Path:
        # Structured layer over atoms.db: rooms, closets, triples. v0.2.7+
        return self.data_dir / "palace.db"

    @property
    def proposals_dir(self) -> Path:
        # Self-reflection loop: durable proposals awaiting approval. v0.2.9+
        return self.data_dir / "proposals"

    @property
    def dream_sessions_dir(self) -> Path:
        # Infinite trillion-dollar builder: per-session metadata YAML. v0.2.12+
        return self.data_dir / "dream-sessions"

    @property
    def dreams_work_dir(self) -> Path:
        # Per-dream working directories: cycle output files. v0.2.12+
        return self.data_dir / "dreams"

    @property
    def projects_dir(self) -> Path:
        # Named project snapshots for change tracking. v0.2.12+
        return self.data_dir / "projects"

    def ensure(self) -> None:
        for p in (
            self.config_dir,
            self.data_dir,
            self.sandbox_dir,
            self.events_dir,
            self.blobs_dir,
            self.review_queue_dir,
            self.approvals_dir,
            self.continuations_dir,
            self.proposals_dir,
            self.dream_sessions_dir,
            self.dreams_work_dir,
            self.projects_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)
        self.config_dir.chmod(0o700)


@dataclass(frozen=True)
class Settings:
    """Runtime tunables. All env-overridable."""

    paths: Paths = field(default_factory=Paths)

    # Ollama
    ollama_host: str = field(
        default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    )
    # Model Corps round (2026-07-06): defaults now point at the hardened
    # aria-<role> models (Model Corps — see docs/model_corps_2026-07-06/),
    # each `FROM` a 100% Apache-2.0/MIT open-weight base (qwen3:8b,
    # qwen2.5-coder:7b, phi4-mini:3.8b, qwen3-vl:4b) with a shared god-tier
    # persona baked in via model_corps.persona. Previous defaults pointed at
    # the bare base tags (and had a real bug: "phi-4-mini" — the actual
    # Ollama tag has no hyphen, "phi4-mini").
    orchestrator_model: str = field(
        default_factory=lambda: os.environ.get("AGENT_ORCHESTRATOR_MODEL", "aria-orchestrator:latest")
    )
    coder_model: str = field(
        default_factory=lambda: os.environ.get("AGENT_CODER_MODEL", "aria-coder:latest")
    )
    embed_model: str = field(
        default_factory=lambda: os.environ.get("AGENT_EMBED_MODEL", "nomic-embed-text")
    )
    fast_model: str = field(
        default_factory=lambda: os.environ.get("AGENT_FAST_MODEL", "aria-fast:latest")
    )
    reflector_model: str = field(
        default_factory=lambda: os.environ.get("AGENT_REFLECTOR_MODEL", "aria-reflector:latest")
    )
    # Interpreter model — v0.2.19.0+. Classifies operator messages into
    # one of {conversation, work, recall, ambiguous}. Small/fast model
    # is ideal: this runs on every operator turn, latency matters more
    # than depth. Defaults to fast_model's same base (phi4-mini:3.8b) so a
    # single download covers both the reflector and interpreter on
    # constrained hardware (GTX 1070 / 8GB VRAM).
    interpreter_model: str = field(
        default_factory=lambda: os.environ.get(
            "AGENT_INTERPRETER_MODEL", "aria-interpreter:latest"
        )
    )
    # Vision model for image-inventory planner (v0.2.6+).
    # Pull with: ollama pull qwen3-vl:4b   (~2.8 GB on disk, Apache 2.0 —
    # replaces llava:7b, which is research-use-only per its own license).
    vision_model: str = field(
        default_factory=lambda: os.environ.get("AGENT_VISION_MODEL", "aria-vision:latest")
    )
    num_ctx: int = 16384

    # Thinking-mode policy (architecture §6, §V assumption 2b)
    # one of: "always", "never", "plan_only"
    think_mode: str = field(default_factory=lambda: os.environ.get("AGENT_THINK", "plan_only"))

    # Events durability (architecture §8a)
    event_fsync_every_n: int = 10
    event_fsync_every_seconds: float = 2.0
    event_max_inline_bytes: int = 4096  # PIPE_BUF; larger payloads go to blob store

    # Approval (architecture §7a)
    approval_default_expiry_seconds: int = 300

    @classmethod
    def load(cls) -> Settings:
        s = cls()
        s.paths.ensure()
        return s


SETTINGS = Settings.load()
