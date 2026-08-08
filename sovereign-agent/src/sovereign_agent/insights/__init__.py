"""Insight generation. Reflection over facts; writes to the insights channel.

The generator is pluggable: ``InsightSynthesizer`` is the protocol, and
the default ``LocalLLMSynthesizer`` calls the configured Ollama model.
Tests use ``StubSynthesizer`` to make the generator deterministic.

Generation is *always dry-run by default*. The operator promotes insights
to durable atoms only after reviewing them.
"""
from .generator import (
    InsightCandidate,
    InsightReport,
    InsightSynthesizer,
    LocalLLMSynthesizer,
    StubSynthesizer,
    generate_person_insights,
    generate_horizon_insight,
    persist_insights,
)

__all__ = [
    "InsightCandidate",
    "InsightReport",
    "InsightSynthesizer",
    "LocalLLMSynthesizer",
    "StubSynthesizer",
    "generate_horizon_insight",
    "generate_person_insights",
    "persist_insights",
]
