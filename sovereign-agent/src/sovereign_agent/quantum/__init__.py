"""sovereign_agent.quantum — the non-classical advisory layer (quantum-inspired, pure-Python).

Distilled from Kevin Monette's Genesis-Seeds research. Quantum-INSPIRED, NOT physics, NOT a
consciousness claim, NOT substrate independence. ADVISORY only — never gates actions, never
raises authority, never self-modifies. See Genesis-Seeds/distilled/blocks/LEGO_BLOCKS.md.
"""
from .field import QuantumNode, brotherhood_gate
from .globe import Globe
from .memory import PersonalUniverse, SharedLayer
from .coherence_gate import coherence_mode
from .maturity import ego_maturity, institutional_impulse_maturity
from .council import consult_council

__all__ = [
    "QuantumNode", "brotherhood_gate", "Globe",
    "PersonalUniverse", "SharedLayer", "coherence_mode",
    "ego_maturity", "institutional_impulse_maturity", "consult_council",
]
