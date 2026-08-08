"""aria_lm/tokenizer.py — Aria's OWN byte-level BPE tokenizer (from scratch, every line ours).

Part of building Aria's own LLM from zero. This is a genuine byte-level Byte-Pair Encoding tokenizer
— the same family GPT-2 uses — implemented from scratch in pure-Python stdlib (no dependencies). It
trains its own merges on our corpus, so the vocabulary is genuinely HERS.

Byte-level = operates on raw UTF-8 bytes (0-255), so it can encode ANY text losslessly (round-trips
perfectly). BPE then learns to merge frequent byte pairs into tokens, compressing common sequences.

100% FOSS, deterministic, fully testable. Reversible: decode(encode(x)) == x for all x.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


class ByteBPETokenizer:
    """A from-scratch byte-level BPE tokenizer (GPT-2 family, our implementation)."""

    def __init__(self) -> None:
        # Base vocab = the 256 raw bytes. merges maps a byte-pair → new token id.
        self.vocab_size = 256
        self.merges: dict[tuple[int, int], int] = {}     # (a, b) -> new_id
        self.merge_order: list[tuple[int, int]] = []       # ordered for deterministic encoding

    # ── training ──────────────────────────────────────────────────────────────
    def train(self, text: str, target_vocab: int = 1024, min_pair_freq: int = 2) -> "ByteBPETokenizer":
        """Learn BPE merges on `text` until reaching target_vocab (or no frequent pairs remain)."""
        ids = list(text.encode("utf-8"))
        target_vocab = max(257, target_vocab)
        next_id = 256
        self.merges = {}
        self.merge_order = []
        while next_id < target_vocab:
            pairs = Counter(zip(ids, ids[1:]))
            if not pairs:
                break
            (a, b), freq = pairs.most_common(1)[0]
            if freq < min_pair_freq:
                break
            # merge the most frequent pair into a new token
            self.merges[(a, b)] = next_id
            self.merge_order.append((a, b))
            ids = _merge(ids, (a, b), next_id)
            next_id += 1
        self.vocab_size = next_id
        return self

    # ── encode / decode ───────────────────────────────────────────────────────
    def encode(self, text: str) -> list[int]:
        ids = list(text.encode("utf-8"))
        # apply merges in the order they were learned (deterministic)
        for pair in self.merge_order:
            new_id = self.merges[pair]
            ids = _merge(ids, pair, new_id)
        return ids

    def decode(self, ids: list[int]) -> str:
        # expand tokens back to bytes via the reverse merge map
        rev: dict[int, tuple[int, int]] = {v: k for k, v in self.merges.items()}
        out_bytes: list[int] = []
        stack = list(reversed(ids))
        while stack:
            tok = stack.pop()
            if tok < 256:
                out_bytes.append(tok)
            else:
                a, b = rev[tok]
                stack.append(b)
                stack.append(a)
        return bytes(out_bytes).decode("utf-8", errors="replace")

    # ── persistence ───────────────────────────────────────────────────────────
    def save(self, path: Path) -> None:
        data = {"vocab_size": self.vocab_size,
                "merge_order": [list(p) for p in self.merge_order]}
        Path(path).write_text(json.dumps(data), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "ByteBPETokenizer":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        tok = cls()
        tok.merge_order = [tuple(p) for p in data["merge_order"]]
        next_id = 256
        for pair in tok.merge_order:
            tok.merges[tuple(pair)] = next_id
            next_id += 1
        tok.vocab_size = data["vocab_size"]
        return tok


def _merge(ids: list[int], pair: tuple[int, int], new_id: int) -> list[int]:
    """Replace every occurrence of `pair` in `ids` with `new_id`."""
    a, b = pair
    out: list[int] = []
    i = 0
    n = len(ids)
    while i < n:
        if i < n - 1 and ids[i] == a and ids[i + 1] == b:
            out.append(new_id)
            i += 2
        else:
            out.append(ids[i])
            i += 1
    return out
