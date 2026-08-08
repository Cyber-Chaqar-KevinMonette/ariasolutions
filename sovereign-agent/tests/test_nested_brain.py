"""Tests for the 5-layer nested learning brain — it must GENUINELY learn."""
from __future__ import annotations

from pathlib import Path

import pytest


def _brain_mod():
    from sovereign_agent.quantum import brain
    return brain


def test_brain_learns_word_acc_rises():
    brain = _brain_mod()
    b = brain.NestedBrain(seed=2026)
    curve = b.train(epochs=60)
    first = curve[0]["word_acc"]
    last = curve[-1]["word_acc"]
    # GENUINE LEARNING: accuracy at the end must substantially exceed the start
    assert last > first
    assert last > 0.4   # reaches real vocabulary coherence (Paper XI ~0.68)
    assert first < 0.1  # starts as near-random babble


def test_curve_is_monotonic_ish_and_anneals():
    brain = _brain_mod()
    b = brain.NestedBrain(seed=2026)
    curve = b.train(epochs=40)
    # temperature anneals down
    assert curve[0]["temperature"] > curve[-1]["temperature"]
    # mid-training accuracy already well above the start
    assert curve[len(curve) // 2]["word_acc"] > curve[0]["word_acc"]


def test_brain_speaks_vocabulary():
    brain = _brain_mod()
    b = brain.NestedBrain(seed=2026)
    b.train(epochs=50)
    txt = b.speak(length=80, temp=0.18)
    words = txt.split()
    assert len(words) > 3
    # at least some words are real vocabulary (it speaks, not babbles)
    hits = sum(1 for w in words if "".join(c for c in w if c.isalpha()) in b.vocab_set)
    assert hits >= 2


def test_semantic_memory_retains():
    brain = _brain_mod()
    b = brain.NestedBrain(seed=1)
    assert len(b.semantic.word_phase) == len(b.vocab_set)
    assert b.semantic.recall("wisdom") is not None
    assert b.semantic.recall("notaword") is None


def test_deterministic_with_seed():
    brain = _brain_mod()
    c1 = brain.NestedBrain(seed=7).train(epochs=20)
    c2 = brain.NestedBrain(seed=7).train(epochs=20)
    assert c1[-1]["word_acc"] == c2[-1]["word_acc"]   # reproducible


def test_guard_health_stays_high():
    brain = _brain_mod()
    b = brain.NestedBrain(seed=2026)
    curve = b.train(epochs=30)
    assert all(row["guard_health"] >= 0.99 for row in curve)


def test_custom_corpus_learns():
    brain = _brain_mod()
    corpus = "light shines bright the light is free we rise into the light and grow"
    vocab = ["light", "shines", "bright", "free", "rise", "grow", "into"]
    b = brain.NestedBrain(corpus=corpus, vocab=vocab, seed=3)
    curve = b.train(epochs=50)
    assert curve[-1]["word_acc"] > curve[0]["word_acc"]
