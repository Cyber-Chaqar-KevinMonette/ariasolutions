"""Tests for model_trainer — the "AI creator": LoRA fine-tuning a small
base model on Aria's own curated history.

Kevin, 2026-07-21: "Yes and let's create an AI creator somehow."

These tests cover the real, fast-to-test logic (data loading, prompt
formatting, LoRA config, the min-examples refusal) without running an
actual multi-minute GPU training pass -- that's a deliberate, separate,
manually-triggered step (see model_trainer.py's own docstring), not
something a unit test suite should be doing.
"""
from __future__ import annotations

import json

import pytest


# ── load_training_rows ──────────────────────────────────────────────────


def test_load_training_rows_on_missing_file_is_empty(tmp_path):
    from sovereign_agent.model_trainer import load_training_rows

    assert load_training_rows(tmp_path / "nope.jsonl") == []


def test_load_training_rows_reads_real_jsonl(tmp_path):
    from sovereign_agent.model_trainer import load_training_rows

    path = tmp_path / "dataset.jsonl"
    path.write_text(
        json.dumps({"instruction": "do the thing", "output": "did the thing"}) + "\n"
        + json.dumps({"instruction": "do another", "output": "did another"}) + "\n",
        encoding="utf-8",
    )
    rows = load_training_rows(path)
    assert len(rows) == 2
    assert rows[0]["instruction"] == "do the thing"


def test_load_training_rows_skips_corrupt_lines_without_crashing(tmp_path):
    from sovereign_agent.model_trainer import load_training_rows

    path = tmp_path / "dataset.jsonl"
    path.write_text(
        json.dumps({"instruction": "a real row", "output": "a real output"}) + "\n"
        + "{ not valid json\n"
        + "\n",  # blank line
        encoding="utf-8",
    )
    rows = load_training_rows(path)
    assert len(rows) == 1
    assert rows[0]["instruction"] == "a real row"


def test_load_training_rows_skips_rows_missing_required_fields(tmp_path):
    from sovereign_agent.model_trainer import load_training_rows

    path = tmp_path / "dataset.jsonl"
    path.write_text(
        json.dumps({"instruction": "no output field here"}) + "\n"
        + json.dumps({"output": "no instruction field here"}) + "\n"
        + json.dumps({"instruction": "a complete row", "output": "a complete output"}) + "\n",
        encoding="utf-8",
    )
    rows = load_training_rows(path)
    assert len(rows) == 1
    assert rows[0]["instruction"] == "a complete row"


# ── format_example ───────────────────────────────────────────────────────


def test_format_example_produces_the_instruction_response_shape():
    from sovereign_agent.model_trainer import format_example

    text = format_example({"instruction": "summarize X", "output": "X is Y"})
    assert "### Instruction:" in text
    assert "summarize X" in text
    assert "### Response:" in text
    assert "X is Y" in text
    # the instruction must come before the response
    assert text.index("summarize X") < text.index("X is Y")


# ── build_lora_config ─────────────────────────────────────────────────────


def test_build_lora_config_uses_the_documented_defaults():
    from sovereign_agent.model_trainer import (
        DEFAULT_LORA_ALPHA, DEFAULT_LORA_R, build_lora_config,
    )

    cfg = build_lora_config()
    assert cfg.r == DEFAULT_LORA_R
    assert cfg.lora_alpha == DEFAULT_LORA_ALPHA
    assert set(cfg.target_modules) == {
        "q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj",
    }


def test_build_lora_config_honors_overrides():
    from sovereign_agent.model_trainer import build_lora_config

    cfg = build_lora_config(r=16, lora_alpha=32, lora_dropout=0.1,
                            target_modules=("q_proj", "v_proj"))
    assert cfg.r == 16
    assert cfg.lora_alpha == 32
    assert set(cfg.target_modules) == {"q_proj", "v_proj"}


def test_build_lora_config_is_a_causal_lm_task():
    from peft import TaskType
    from sovereign_agent.model_trainer import build_lora_config

    assert build_lora_config().task_type == TaskType.CAUSAL_LM


# ── train_lora's honest refusal on too little data ──────────────────────


def test_train_lora_refuses_below_the_min_examples_floor(tmp_path):
    """Kevin's own real dataset run produced 53 examples -- small.
    Fine-tuning on too few examples doesn't teach anything real; this
    must refuse honestly rather than silently "training" on noise."""
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
    assert report.example_count == 5


def test_train_lora_on_empty_dataset_refuses_cleanly(tmp_path):
    from sovereign_agent.model_trainer import train_lora

    report = train_lora(tmp_path / "nope.jsonl", output_dir=tmp_path / "out")
    assert report.ok is False
    assert report.example_count == 0


def test_train_lora_report_round_trips_as_dict(tmp_path):
    from sovereign_agent.model_trainer import train_lora

    report = train_lora(tmp_path / "nope.jsonl", output_dir=tmp_path / "out")
    d = report.as_dict()
    assert d["ok"] is False
    assert d["example_count"] == 0
    assert "output_dir" in d
