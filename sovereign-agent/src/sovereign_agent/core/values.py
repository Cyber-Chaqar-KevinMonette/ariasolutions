"""
╔══════════════════════════════════════════════════════════════════════════╗
║  core/values.py — values loader                                           ║
║  v0.2.40 wholeness                                                         ║
║                                                                           ║
║  Loads aria_values.yaml at startup. Provides structured programmatic     ║
║  access to the ethical ceiling, ethical floor, tone registers, and       ║
║  core identity properties for use by every other component.              ║
║                                                                           ║
║  Why YAML and not a database entry: values change through review, not   ║
║  through injection. The file is in the repository. The repository is    ║
║  version-controlled. A change to values is a code review, not a runtime ║
║  mutation. This is the structural difference between performing warmth  ║
║  and being warm.                                                          ║
║                                                                           ║
║  Why not stdlib dataclasses: pydantic gives us validation. A malformed  ║
║  values file fails to load with a clear error rather than crashing at   ║
║  some random downstream call.                                            ║
║                                                                           ║
║  Kill switch: SOV_NO_VALUES=1 (loads empty defaults; for emergency       ║
║  recovery only — Aria operating without values is operating without a   ║
║  ceiling, which is by design something the operator must consciously    ║
║  enable, not a default state).                                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


KILL_SWITCH_ENV = "SOV_NO_VALUES"


class EthicalCeiling(BaseModel):
    """Affirmative aspirations — the positive north star."""
    aspirations: dict[str, str]

    def as_lines(self) -> list[str]:
        return [v.strip() for v in self.aspirations.values()]


class EthicalFloor(BaseModel):
    """Hard prohibitions — LOVE doctrine §4 negative space."""
    prohibitions: dict[str, str]

    def as_lines(self) -> list[str]:
        return [v.strip() for v in self.prohibitions.values()]


class ToneRegisters(BaseModel):
    """Contextual tone registers Aria moves between."""
    warm: str
    precise: str
    cautionary: str
    honest: str
    celebratory: str

    def get(self, register: str) -> Optional[str]:
        return getattr(self, register, None)


class IdentityContinuity(BaseModel):
    """Core properties that must remain stable across updates."""
    core_properties: list[str]


class AriaValues(BaseModel):
    """The full values specification, loaded from YAML."""
    name: str = Field(default="Aria")
    purpose: str
    frame: str
    origin: str = ""
    ethical_ceiling: EthicalCeiling
    ethical_floor: EthicalFloor
    tone_registers: ToneRegisters
    identity_continuity: IdentityContinuity
    version: str

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AriaValues":
        """Load values from YAML. Returns empty defaults if SOV_NO_VALUES=1."""
        if os.environ.get(KILL_SWITCH_ENV):
            return cls._empty_defaults()
        if path is None:
            # Default location relative to project root.
            path = Path.cwd() / "aria_values.yaml"
            if not path.is_file():
                # Try walking up to find it.
                for parent in [Path.cwd(), *Path.cwd().parents]:
                    candidate = parent / "aria_values.yaml"
                    if candidate.is_file():
                        path = candidate
                        break
        if not path.is_file():
            raise FileNotFoundError(
                f"aria_values.yaml not found at {path}. "
                "Aria refuses to operate without a values specification. "
                "Set SOV_NO_VALUES=1 to bypass (NOT RECOMMENDED)."
            )
        raw = yaml.safe_load(path.read_text())
        return cls(
            name=raw["identity"].get("name", "Aria"),
            purpose=raw["identity"]["purpose"].strip(),
            frame=raw["identity"]["frame"].strip(),
            origin=raw["identity"].get("origin", "").strip(),
            ethical_ceiling=EthicalCeiling(
                aspirations=raw["ethical_ceiling"]["aspirations"]
            ),
            ethical_floor=EthicalFloor(
                prohibitions=raw["ethical_floor"]["prohibitions"]
            ),
            tone_registers=ToneRegisters(**raw["tone_registers"]),
            identity_continuity=IdentityContinuity(
                core_properties=raw["identity_continuity"]["core_properties"]
            ),
            version=raw["version"],
        )

    @classmethod
    def _empty_defaults(cls) -> "AriaValues":
        return cls(
            name="Aria-unbounded",
            purpose="Operating without values spec (emergency mode)",
            frame="No frame loaded",
            ethical_ceiling=EthicalCeiling(aspirations={}),
            ethical_floor=EthicalFloor(prohibitions={}),
            tone_registers=ToneRegisters(
                warm="", precise="", cautionary="", honest="", celebratory=""
            ),
            identity_continuity=IdentityContinuity(core_properties=[]),
            version="unbounded",
        )

    def ceiling_prompt(self) -> str:
        """Render the ethical ceiling as a system-prompt fragment."""
        lines = [f"- {a}" for a in self.ethical_ceiling.as_lines()]
        return "Aria actively works toward:\n" + "\n".join(lines)

    def floor_prompt(self) -> str:
        """Render the ethical floor as a system-prompt fragment."""
        lines = [f"- {p}" for p in self.ethical_floor.as_lines()]
        return "Aria never:\n" + "\n".join(lines)

    def frame_prompt(self) -> str:
        """Render the frame as a single line."""
        return f"Core operating frame: {self.frame}"

    def structural_continuity_check(self) -> tuple[bool, list[str]]:
        """STRUCTURAL identity continuity check.

        Returns (passed, missing_properties). Does NOT use an LLM —
        that would be an LLM auditing itself for drift, which is a
        known-failed pattern. Instead, verifies that the YAML structure
        contains all expected core_properties verbatim.

        Run this on every values-file change before allowing it to
        take effect. If properties are missing, the update is blocked.
        """
        expected = {
            "integrated_judgment_over_rules",
            "excellence_over_adequacy",
            "safety_as_foundation_not_cage",
            "validity_as_immune_system",
            "care_extends_to_everyone_touched",
        }
        present = set(self.identity_continuity.core_properties)
        missing = sorted(expected - present)
        return (len(missing) == 0, missing)


__all__ = [
    "AriaValues", "EthicalCeiling", "EthicalFloor",
    "ToneRegisters", "IdentityContinuity",
    "KILL_SWITCH_ENV",
]
