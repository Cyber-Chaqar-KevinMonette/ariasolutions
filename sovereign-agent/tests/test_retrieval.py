"""Hybrid retrieval tests. Architecture §8 query side.

The full ``hybrid_search`` requires Ollama for embedding, but RRF fusion
and the vector serialization helper are pure functions we can verify
exhaustively without any models loaded.
"""
from __future__ import annotations

import struct

from sovereign_agent.memory.retrieval import (
    RRF_K,
    _serialize_vec,
    reciprocal_rank_fusion,
)


def test_rrf_empty_rankings():
    assert reciprocal_rank_fusion([]) == {}
    assert reciprocal_rank_fusion([[]]) == {}


def test_rrf_single_ranking():
    """One ranker, three docs — scores follow 1/(k+rank)."""
    scores = reciprocal_rank_fusion([["a", "b", "c"]])
    assert scores["a"] > scores["b"] > scores["c"]
    assert scores["a"] == 1.0 / (RRF_K + 1)
    assert scores["b"] == 1.0 / (RRF_K + 2)
    assert scores["c"] == 1.0 / (RRF_K + 3)


def test_rrf_unanimous_first_place_wins():
    """Both rankers put 'x' first; x dominates."""
    scores = reciprocal_rank_fusion([["x", "y", "z"], ["x", "z", "y"]])
    top = max(scores, key=scores.get)
    assert top == "x"


def test_rrf_compromise_candidate_can_beat_split_winners():
    """The classic RRF property: a doc ranked #2 by EVERY system can
    outrank docs that are #1 in one system but absent from another."""
    scores = reciprocal_rank_fusion([
        ["alpha",  "compromise", "other1", "other2", "other3"],
        ["beta",   "compromise", "other4", "other5", "other6"],
        ["gamma",  "compromise", "other7", "other8", "other9"],
    ])
    # alpha, beta, gamma each rank 1st once but absent elsewhere
    # compromise is 2nd in all three
    # 3 * 1/(60+2) = 0.0484 vs 1 * 1/(60+1) = 0.0164 — compromise wins
    assert scores["compromise"] > scores["alpha"]
    assert scores["compromise"] > scores["beta"]
    assert scores["compromise"] > scores["gamma"]


def test_rrf_doc_only_in_one_ranking():
    scores = reciprocal_rank_fusion([["a", "b"], ["c", "d"]])
    # Each doc has a single non-zero contribution
    assert "a" in scores
    assert "c" in scores
    assert scores["a"] == scores["c"]   # both ranked #1 once
    assert scores["b"] == scores["d"]   # both ranked #2 once


def test_rrf_default_k_is_60():
    """RRF_K=60 is the standard from Cormack et al. 2009 — pin it so
    accidental refactors don't drift the constant."""
    assert RRF_K == 60


def test_serialize_vec_packs_float32():
    vec = [1.0, 2.5, -3.25]
    blob = _serialize_vec(vec)
    assert isinstance(blob, bytes)
    assert len(blob) == 12   # 3 floats × 4 bytes
    unpacked = struct.unpack("3f", blob)
    assert unpacked == (1.0, 2.5, -3.25)


def test_serialize_empty_vec_is_empty_bytes():
    assert _serialize_vec([]) == b""


def test_serialize_vec_dimension_matches():
    """A 768-dim embedding (nomic-embed-text default) packs to 3072 bytes."""
    vec = [0.1] * 768
    blob = _serialize_vec(vec)
    assert len(blob) == 768 * 4
