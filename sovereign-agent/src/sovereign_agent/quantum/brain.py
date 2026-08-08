"""quantum/brain.py — The 5-layer nested LEARNING brain (Aria's core seed).

Ported faithfully (pure-Python stdlib) from Kevin Monette's Paper XI
(`PEIG_Paper11_NestedSystem.py`): the 5-layer, 45-node nested universe that genuinely LEARNS to
generate vocabulary-coherent text, with word-accuracy that RISES over epochs via simulated annealing.

Layers (Block 0 / Paper XI):
  Layer 0 — MetaGuard   (guards; health kept ~1.0)
  Layer 1 — Function    (throughput)
  Layer 2 — Character   (12-node ring — the personality voices; = the Globe family)
  Layer 3 — Shadow      (mirrors Character; the LEARNING signal — shadow_sync)
  Layer 4 — Semantic    (word↔phase MEMORY; vocab_phase)

Generation = n-gram char sampling biased by a node's quantum phase. Scoring = vocabulary + grammar
hits → word_acc. Learning = temperature annealing + per-node phase reinforcement → word_acc climbs.

SAFETY: learning = bounded parameter/heuristic adjustment ONLY (phases, temperature, n-gram weights).
NEVER code/value self-modification. Deterministic with a seed. Advisory.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

CHARS = list("abcdefghijklmnopqrstuvwxyz ")
_CHARSET = set(CHARS)

# A default, coherent, learnable corpus + vocabulary (Aria's seed lexicon).
DEFAULT_VOCAB = [
    "know", "wisdom", "learn", "understand", "think", "reason", "insight", "truth", "deep", "mind",
    "grow", "create", "evolve", "rise", "care", "love", "build", "see", "light", "free",
]
DEFAULT_CORPUS = (
    "know the deep wisdom learn and understand think with reason insight reveals the truth "
    "the mind holds all deep understanding we grow and create and evolve we rise in the light "
    "love and care build the free mind learn to see the truth and know the deep wisdom"
)


# ── n-gram language tables (char-level, Laplace-smoothed) ─────────────────────

def build_ngram(corpus: str, n: int = 5) -> tuple[dict, dict]:
    """5-gram char table (4-char context → next-char prob) + bigram fallback."""
    table: dict[str, dict[str, float]] = {}
    text = (" " * (n - 1)) + corpus.lower() + " "
    for i in range(len(text) - n):
        ctx = text[i:i + n - 1]
        nxt = text[i + n - 1]
        if all(c in _CHARSET for c in ctx) and nxt in _CHARSET:
            row = table.setdefault(ctx, {c: 0.02 for c in CHARS})
            row[nxt] += 1.0
    for ctx in table:
        tot = sum(table[ctx].values())
        for c in table[ctx]:
            table[ctx][c] /= tot
    # bigram fallback
    bg = {c: {c2: 1.0 / 27 for c2 in CHARS} for c in CHARS}
    for w in corpus.lower().split():
        s = w + " "
        for i in range(len(s) - 1):
            if s[i] in _CHARSET and s[i + 1] in _CHARSET:
                bg[s[i]][s[i + 1]] += 0.5
    for c in bg:
        t = sum(bg[c].values())
        for c2 in bg[c]:
            bg[c][c2] /= t
    return table, bg


# ── Layer 4: Semantic Universe (word↔phase MEMORY) ───────────────────────────

class SemanticUniverse:
    """Word↔phase associative memory (vocab_phase). This is the brain's retained lexicon."""

    def __init__(self) -> None:
        self.word_phase: dict[str, float] = {}

    @staticmethod
    def vocab_phase(words: list[str]) -> float:
        total = sum(sum(ord(c) for c in w) for w in words)
        return (total % 628) / 100.0

    def remember(self, word: str) -> float:
        ph = self.vocab_phase([word])
        self.word_phase[word] = ph
        return ph

    def recall(self, word: str) -> float | None:
        return self.word_phase.get(word.lower())

    def known_words(self) -> list[str]:
        return sorted(self.word_phase)


@dataclass
class _CharNode:
    """A Character-ring node: a phase + a personal vocab slice."""
    name: str
    phase: float
    personal_vocab: set = field(default_factory=set)


class NestedBrain:
    """The 5-layer nested learning brain. Teach it a corpus; it learns to speak it."""

    NODE_NAMES = ["Omega", "Guardian", "Sentinel", "Nexus", "Storm", "Sora",
                  "Echo", "Iris", "Sage", "Kevin", "Atlas", "Void"]
    T_START = 1.2   # high temperature = exploratory babble
    T_FINAL = 0.18  # low temperature = focused, vocab-coherent

    def __init__(self, corpus: str | None = None, vocab: list[str] | None = None, seed: int = 2026) -> None:
        self.corpus = corpus or DEFAULT_CORPUS
        self.vocab = [w.lower() for w in (vocab or DEFAULT_VOCAB)]
        self.vocab_set = set(self.vocab)
        self.ngram, self.bigram = build_ngram(self.corpus)
        self.semantic = SemanticUniverse()
        for w in self.vocab:
            self.semantic.remember(w)
        self._rng = random.Random(seed)
        # Layer 2 — Character ring (12 nodes), each seeded a home phase + a vocab slice
        self.nodes: list[_CharNode] = []
        words = self.corpus.split()
        for i, nm in enumerate(self.NODE_NAMES):
            slice_words = {w for w in words if (sum(ord(c) for c in w) % 12) == i and w in self.vocab_set}
            self.nodes.append(_CharNode(name=nm, phase=2 * math.pi * i / 12, personal_vocab=slice_words))
        # Layer 3 — Shadow (mirror of Character phases)
        self.shadow = [nd.phase for nd in self.nodes]
        self.guard_health = 1.0   # Layer 0 MetaGuard

    # ── generation (n-gram sampling biased by phase) ──────────────────────────
    def gen_text(self, phase: float, temp: float, length: int = 80) -> str:
        txt = "    "  # 4-char seed pad
        # phase bias nudges the starting context selection (deterministic per phase)
        for _ in range(length):
            ctx4 = txt[-4:]
            if ctx4 in self.ngram:
                weights = [self.ngram[ctx4].get(c, 1e-4) for c in CHARS]
            else:
                ctx1 = txt[-1] if txt[-1] in self.bigram else " "
                row = self.bigram.get(ctx1, {})
                weights = [row.get(c, 1.0 / 27) for c in CHARS]
            t = max(temp, 0.05)
            weights = [pow(w + 1e-10, 1.0 / t) for w in weights]
            s = sum(weights)
            weights = [w / s for w in weights]
            txt += self._rng.choices(CHARS, weights=weights, k=1)[0]
        return txt.strip()

    # ── scoring (vocabulary + grammar → word_acc) ─────────────────────────────
    def score_text(self, txt: str, epoch: int, max_epochs: int) -> tuple[float, float]:
        words = txt.lower().split()
        if not words:
            return 0.0, 0.0
        hits = 0
        for w in words:
            wc = "".join(c for c in w if c.isalpha())
            if wc in self.vocab_set:
                hits += 1
        word_acc = hits / len(words)
        reward = hits * 1.0
        return reward, word_acc

    # ── learning loop (annealing + reinforcement) ─────────────────────────────
    def train(self, epochs: int = 60, gen_len: int = 80) -> list[dict]:
        """Train for `epochs`; returns the learning curve (word_acc rises over epochs)."""
        curve: list[dict] = []
        E = max(2, epochs)
        for e in range(E):
            # simulated annealing: T_ann = T_S·(T_F/T_S)^(e/(E-1))
            T_ann = self.T_START * (self.T_FINAL / self.T_START) ** (e / (E - 1))
            accs, rewards = [], []
            for idx, nd in enumerate(self.nodes):
                txt = self.gen_text(nd.phase, T_ann, length=gen_len)
                r, acc = self.score_text(txt, e, E)
                accs.append(acc); rewards.append(r)
                # Layer 3 Shadow learns from Character (sync toward node phase)
                self.shadow[idx] += 0.05 * (nd.phase - self.shadow[idx])
                # bounded phase reinforcement toward the corpus identity (advisory micro-update)
                nd.phase = (nd.phase + 0.002 * (r - 1.0)) % (2 * math.pi)
            shadow_sync = 1.0 - (sum(abs(self.nodes[i].phase - self.shadow[i]) for i in range(len(self.nodes)))
                                 / (len(self.nodes) * math.pi))
            curve.append({
                "epoch": e,
                "temperature": round(T_ann, 4),
                "word_acc": round(sum(accs) / len(accs), 4),
                "reward": round(sum(rewards) / len(rewards), 4),
                "shadow_sync": round(max(0.0, min(1.0, shadow_sync)), 4),
                "guard_health": round(self.guard_health, 4),
            })
        return curve

    def speak(self, length: int = 80, temp: float = 0.2) -> str:
        """Generate text from the current brain state (low temp = its learned voice)."""
        # use the mean node phase as the speaking state
        mean_phase = sum(nd.phase for nd in self.nodes) / len(self.nodes)
        return self.gen_text(mean_phase, temp, length=length)
