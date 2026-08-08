"""
sovereign_agent.mem_channels — concrete memory channels.

Importing this package registers all bundled channels with the channel
registry. Aria's startup imports this package once.

To add a new channel:
  1. Create a new module here (e.g., dreams.py)
  2. Define a class `MyChannel(MemoryChannel)` with `spec = ChannelSpec(...)`
  3. Decorate or call `register_channel(MyChannel)`
  4. Add it to the import list below

The channel is then visible to ``sov channels list`` and to
``universal_recall``.
"""
from __future__ import annotations

# Import each channel module — registration happens at import time.
from . import (
    commitments,
    context,
    emotions,
    episodes,
    financial,
    gaps,
    goals,
    heartbeat,
    humor,
    identity,
    insights,
    intention,
    intuition,
    lessons,
    people,
    people_health,  # people-health-privacy-d
    personalities,
    reasoning,
    recall,
    relationships,
    reward,
    ritual,
    specialist,
    task,
    trust,
)

__all__ = [
    "commitments",
    "context",
    "emotions",
    "episodes",
    "financial",
    "gaps",
    "goals",
    "heartbeat",
    "humor",
    "identity",
    "insights",
    "intention",
    "intuition",
    "lessons",
    "people",
    "personalities",
    "reasoning",
    "recall",
    "relationships",
    "reward",
    "ritual",
    "specialist",
    "task",
    "trust",
]
