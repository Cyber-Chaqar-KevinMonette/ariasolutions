"""Tests for hardware-liberation-d / loss-masking-fix-d — the QLoRA +
assistant-only-loss-masking upgrade to model_trainer.py.

Found 2026-07-25 reading Plans/p-plans-hardware-liberation/Files/ (per
Kevin's own sequencing: read the files before touching the 225 zips).
Two real, verified gaps in the previous version: (1) it used plain fp16
LoRA, not real QLoRA (4-bit NF4) -- confirmed directly on this GPU that
4-bit quantization uses ~1.15 GB vs ~3 GB unquantized; (2) it trained
loss over the WHOLE instruction+response text, not just the response --
a real quality bug, not just an inefficiency.
"""
from __future__ import annotations

from unittest.mock import MagicMock


class _FakeTokenizer:
    """A minimal, deterministic word-level tokenizer -- fast, no real
    model download needed to test the masking logic itself."""

    eos_token_id = 999

    def __call__(self, text, add_special_tokens=False):
        # one "token" per character -- simple, deterministic, easy to
        # reason about prefix/full alignment in assertions.
        return {"input_ids": [ord(c) for c in text]}


def test_build_quantization_config_uses_4bit_nf4_fp16_compute():
    import torch
    from sovereign_agent.model_trainer import build_quantization_config

    cfg = build_quantization_config()
    assert cfg.load_in_4bit is True
    assert cfg.bnb_4bit_quant_type == "nf4"
    assert cfg.bnb_4bit_compute_dtype == torch.float16


def test_tokenize_example_masks_the_instruction_not_the_response():
    from sovereign_agent.model_trainer import _tokenize_example

    row = {"instruction": "hi", "output": "yo"}
    tok = _FakeTokenizer()
    ex = _tokenize_example(row, tok, max_length=1000)

    assert ex is not None
    prefix_len = len(
        "### Instruction:\nhi\n\n### Response:\n"
    )
    # every label up to the response must be masked
    assert all(l == -100 for l in ex["labels"][:prefix_len])
    # the response tokens (plus the appended eos) must NOT be masked
    assert ex["labels"][prefix_len] != -100
    assert ex["labels"][-1] == tok.eos_token_id  # eos appended, supervised


def test_tokenize_example_appends_eos_and_supervises_it():
    from sovereign_agent.model_trainer import _tokenize_example

    row = {"instruction": "a", "output": "b"}
    tok = _FakeTokenizer()
    ex = _tokenize_example(row, tok, max_length=1000)

    assert ex["input_ids"][-1] == tok.eos_token_id
    assert ex["labels"][-1] == tok.eos_token_id


def test_tokenize_example_rejects_examples_over_max_length():
    from sovereign_agent.model_trainer import _tokenize_example

    row = {"instruction": "a" * 100, "output": "b" * 100}
    tok = _FakeTokenizer()
    ex = _tokenize_example(row, tok, max_length=10)
    assert ex is None


def test_tokenize_example_input_ids_and_labels_are_same_length():
    from sovereign_agent.model_trainer import _tokenize_example

    row = {"instruction": "summarize this", "output": "a short summary"}
    tok = _FakeTokenizer()
    ex = _tokenize_example(row, tok, max_length=1000)
    assert len(ex["input_ids"]) == len(ex["labels"]) == len(ex["attention_mask"])


def test_format_example_still_matches_the_documented_shape():
    """format_example()'s existing contract (instruction before response,
    both present) must survive the rewrite -- other tests/tooling may
    still call it for display purposes."""
    from sovereign_agent.model_trainer import format_example

    text = format_example({"instruction": "summarize X", "output": "X is Y"})
    assert "### Instruction:" in text
    assert "summarize X" in text
    assert "### Response:" in text
    assert "X is Y" in text
    assert text.index("summarize X") < text.index("X is Y")


def test_train_lora_still_refuses_below_floor_before_loading_any_model(tmp_path):
    """The cheap, pre-model-load refusal path must still work exactly as
    before -- no regression from the masking/quantization changes."""
    import json
    from sovereign_agent.model_trainer import train_lora

    path = tmp_path / "dataset.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"instruction": f"do thing {i}", "output": f"did thing {i}"})
            for i in range(5)
        ) + "\n",
        encoding="utf-8",
    )
    report = train_lora(path, output_dir=tmp_path / "out", min_examples=20)
    assert report.ok is False
    assert "only 5 training examples" in report.error
