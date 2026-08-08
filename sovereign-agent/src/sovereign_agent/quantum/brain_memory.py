"""quantum/brain_memory.py — Retention for the nested brain (she forgets nothing).

Persists the brain's learned state — word↔phase lexicon, node phases, corpus/vocab, and the learning
curve summary — to data_dir/quantum/brain_state.json, so what she learns is RETAINED across sessions.
Teaching accumulates: new corpora extend her lexicon. Pure-Python stdlib. Bounded, advisory.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .brain import NestedBrain, DEFAULT_CORPUS, DEFAULT_VOCAB


def _state_path(data_dir: Path) -> Path:
    p = Path(data_dir) / "quantum" / "brain_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state(data_dir: Path) -> dict:
    """Load the persisted brain state (empty default if none)."""
    p = _state_path(data_dir)
    if not p.exists():
        return {"corpus": "", "vocab": [], "word_phase": {}, "node_phases": {},
                "lessons": 0, "final_word_acc": None, "trained_at": None}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"corpus": "", "vocab": [], "word_phase": {}, "node_phases": {},
                "lessons": 0, "final_word_acc": None, "trained_at": None}


def teach(data_dir: Path, *, corpus: str, vocab: list[str] | None = None,
          epochs: int = 60, seed: int = 2026) -> dict:
    """Teach the brain a corpus, persist the learned state (accumulating), return the curve summary."""
    prev = load_state(data_dir)
    # Accumulate: merge new corpus/vocab with what she already knows (retention).
    merged_corpus = (prev.get("corpus", "") + " " + corpus).strip()
    prev_vocab = set(prev.get("vocab", []))
    new_vocab = set(w.lower() for w in (vocab or [])) | {
        "".join(c for c in w if c.isalpha()) for w in corpus.lower().split()
    }
    merged_vocab = sorted(prev_vocab | new_vocab | set(DEFAULT_VOCAB))

    brain = NestedBrain(corpus=merged_corpus or DEFAULT_CORPUS,
                        vocab=merged_vocab, seed=seed)
    curve = brain.train(epochs=epochs)

    state = {
        "corpus": merged_corpus,
        "vocab": merged_vocab,
        "word_phase": brain.semantic.word_phase,
        "node_phases": {nd.name: round(nd.phase, 6) for nd in brain.nodes},
        "lessons": prev.get("lessons", 0) + 1,
        "final_word_acc": curve[-1]["word_acc"],
        "first_word_acc": curve[0]["word_acc"],
        "epochs": epochs,
        "trained_at": _now(),
    }
    _state_path(data_dir).write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    return {
        "lessons": state["lessons"],
        "vocab_size": len(merged_vocab),
        "learning_curve": {"first": curve[0]["word_acc"], "mid": curve[len(curve)//2]["word_acc"],
                           "final": curve[-1]["word_acc"]},
        "learned": curve[-1]["word_acc"] > curve[0]["word_acc"],
        "sample_speech": brain.speak(length=70, temp=0.18),
        "trained_at": state["trained_at"],
    }


def recall(data_dir: Path, word: str | None = None) -> dict:
    """Recall a word's learned phase, or the whole lexicon summary."""
    state = load_state(data_dir)
    wp = state.get("word_phase", {})
    if word:
        w = word.lower()
        return {"word": w, "phase": wp.get(w), "known": w in wp}
    return {
        "lessons": state.get("lessons", 0),
        "vocab_size": len(state.get("vocab", [])),
        "known_words": sorted(wp)[:50],
        "final_word_acc": state.get("final_word_acc"),
        "trained_at": state.get("trained_at"),
    }
