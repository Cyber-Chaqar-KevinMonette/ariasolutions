"""model_trainer.py — the "AI creator": LoRA fine-tune a small base model
on Aria's own curated, hardened history.

Kevin, 2026-07-21: "Yes and let's create an AI creator somehow." Part of
the fine-tuning project (training_data.py did the curation + hardening
half; this is the actual training half).

Design decisions, stated plainly rather than assumed:
  - QLoRA (4-bit NF4 quantization via bitsandbytes + `peft` LoRA), not a
    full fine-tune or plain fp16 LoRA. hardware-liberation-d (Kevin,
    2026-07-25: "read the files before extracting the zips"):
    `Plans/p-plans-hardware-liberation/Files/` contained real, verified
    research specific to this exact GPU. Confirmed directly on this
    machine (not assumed): loading Qwen2.5-1.5B-Instruct in 4-bit NF4
    used ~1.15 GB VRAM vs ~3 GB for the plain-fp16 approach this module
    used before — real headroom recovered, not a theoretical gain.
  - fp16 compute dtype, not bf16. This machine's GPU is a GTX 1070 —
    Pascal, compute capability 6.1 (confirmed via
    `torch.cuda.get_device_capability`). Pascal has no real bf16
    tensor-core path; bf16 either silently emulates (slow) or misbehaves
    depending on op. fp16 is the correct, well-supported choice here —
    the quantization storage is 4-bit NF4, but all compute happens in
    fp16 (`bnb_4bit_compute_dtype=torch.float16`).
  - Standard `transformers` + `peft` + `bitsandbytes`, not Unsloth.
    Unsloth's fused kernels target Turing+ (RTX 20-series and up); this
    card predates that. Plain HF/PEFT training has no such floor.
  - Base model default: `Qwen/Qwen2.5-1.5B-Instruct` — NOT phi4-mini
    (3.8B), despite that family being proven live elsewhere in this
    system. The first REAL run on phi4-mini OOM'd: loading its frozen
    fp16 weights alone took 6.87 GiB of the 7.92 GiB card, leaving no
    room to actually train. A 1.5B model's weights are ~3GB in fp16 (now
    ~0.87GB quantized), leaving genuine headroom.
  - Gradient checkpointing, always on, with `use_reentrant=False`
    (verified more reliable than the reentrant default alongside
    `prepare_model_for_kbit_training` for a quantized model —
    per the same hardware-liberation-d research). Trades some compute
    time for a real cut in activation memory during the backward pass.
  - Assistant-only loss masking. loss-masking-fix-d (found 2026-07-25,
    same research pass): the PREVIOUS version of this module tokenized
    the whole "### Instruction:\n...\n\n### Response:\n..." string as one
    block and trained the loss over ALL of it, including the instruction
    and template scaffolding — a real quality bug, not just an
    inefficiency (the model was being taught to predict the instruction
    text back, not just to answer it). Labels for every token before the
    response are now set to -100 (ignored by the loss), matching the
    standard supervised-fine-tuning practice this research confirmed.

Honest scope: this module produces a trained LoRA ADAPTER — small,
real, loadable back onto the base model. Turning that into a new
Ollama-servable tag (merge + convert to GGUF + `ollama create`) is a
further, separate step needing llama.cpp's own conversion tooling, not
yet part of this codebase — named here so it's not lost, not silently
implied as already done.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_BASE_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_LORA_R = 8
DEFAULT_LORA_ALPHA = 16
DEFAULT_LORA_DROPOUT = 0.05
# Phi/Qwen-family attention + MLP projections — the standard LoRA
# target set for these architectures.
DEFAULT_TARGET_MODULES = ("q_proj", "k_proj", "v_proj", "o_proj",
                          "gate_proj", "up_proj", "down_proj")

# loss-masking-fix-d: split into a PREFIX (instruction + scaffolding, gets
# masked out of the loss) and the response (the only part actually
# supervised) — a single joined template can't express that split.
_PROMPT_PREFIX_TEMPLATE = "### Instruction:\n{instruction}\n\n### Response:\n"


@dataclass
class TrainingReport:
    example_count: int = 0
    base_model: str = ""
    output_dir: str = ""
    epochs: int = 0
    final_loss: float | None = None
    ok: bool = False
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "example_count": self.example_count, "base_model": self.base_model,
            "output_dir": self.output_dir, "epochs": self.epochs,
            "final_loss": self.final_loss, "ok": self.ok, "error": self.error,
        }


def load_training_rows(dataset_path: Path) -> list[dict]:
    """Read the JSONL training_data.py produced. Never raises — a
    missing/corrupt file degrades to an empty list; the caller decides
    whether that's enough to train on (it usually isn't)."""
    rows: list[dict] = []
    path = Path(dataset_path)
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if "instruction" in row and "output" in row:
            rows.append(row)
    return rows


def format_example(row: dict) -> str:
    """One training row -> the exact text the model trains on (display
    purposes / backward-compat). The real tokenization path
    (_tokenize_example) needs the prefix/response split separately, not
    just this joined string, to mask the instruction out of the loss."""
    return _PROMPT_PREFIX_TEMPLATE.format(instruction=row["instruction"]) + row["output"]


def _tokenize_example(row: dict, tokenizer, *, max_length: int) -> dict | None:
    """Tokenize one row with assistant-only loss masking: the instruction
    (and template scaffolding) is masked with -100 so the model only ever
    learns to predict the response, not memorize/echo the prompt. Returns
    None for a row that doesn't fit (too long, or the tokenizer merged
    tokens across the prefix/response boundary differently, which would
    mask incorrectly) — the caller filters these out rather than train on
    a bad example.
    """
    prefix = _PROMPT_PREFIX_TEMPLATE.format(instruction=row["instruction"])
    full = prefix + row["output"]

    prefix_ids = tokenizer(prefix, add_special_tokens=False)["input_ids"]
    full_ids = tokenizer(full, add_special_tokens=False)["input_ids"]

    if len(full_ids) <= len(prefix_ids) or len(full_ids) > max_length:
        return None
    if full_ids[:len(prefix_ids)] != prefix_ids:
        return None

    eos_id = tokenizer.eos_token_id
    if eos_id is not None:
        full_ids = full_ids + [eos_id]

    labels = [-100] * len(prefix_ids) + full_ids[len(prefix_ids):]
    return {
        "input_ids": full_ids,
        "labels": labels,
        "attention_mask": [1] * len(full_ids),
    }


def build_quantization_config():
    """QLoRA's 4-bit NF4 quantization config. Isolated into its own
    function, matching build_lora_config()'s pattern, so the choice is
    testable/inspectable without loading a real model. hardware-liberation-d:
    confirmed directly on this GPU (compute capability 6.1) — ~1.15 GB to
    load Qwen2.5-1.5B-Instruct, vs ~3 GB unquantized fp16."""
    import torch
    from transformers import BitsAndBytesConfig

    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,  # Pascal (6.1): fp16, not bf16
    )


def build_lora_config(
    *,
    r: int = DEFAULT_LORA_R,
    lora_alpha: int = DEFAULT_LORA_ALPHA,
    lora_dropout: float = DEFAULT_LORA_DROPOUT,
    target_modules: tuple[str, ...] = DEFAULT_TARGET_MODULES,
):
    """The peft LoRA config, isolated into its own function so the
    hyperparameter choices are testable without loading a real model."""
    from peft import LoraConfig, TaskType

    return LoraConfig(
        r=r, lora_alpha=lora_alpha, lora_dropout=lora_dropout,
        target_modules=list(target_modules), bias="none",
        task_type=TaskType.CAUSAL_LM,
    )


def train_lora(
    dataset_path: Path,
    *,
    base_model: str = DEFAULT_BASE_MODEL,
    output_dir: Path,
    epochs: int = 3,
    learning_rate: float = 2e-4,
    batch_size: int = 1,
    min_examples: int = 20,
    max_length: int = 1024,
) -> TrainingReport:
    """Run a real QLoRA fine-tuning pass. Never raises past this point --
    a training failure (OOM, missing dependency, bad data) comes back as
    TrainingReport(ok=False, error=...), not a crash mid-run.

    `min_examples` is a real floor, not decoration: fine-tuning on a
    handful of examples doesn't teach anything and just burns GPU time --
    refuses honestly rather than pretending a 5-example "fine-tune" did
    something. Checked twice: once on the raw row count (fast, no model
    load needed), and again after tokenization (a row that doesn't
    survive masking-safe tokenization doesn't count).
    """
    rows = load_training_rows(dataset_path)
    report = TrainingReport(
        example_count=len(rows), base_model=base_model,
        output_dir=str(output_dir), epochs=epochs,
    )
    if len(rows) < min_examples:
        report.error = (
            f"only {len(rows)} training examples (need >= {min_examples}) "
            f"-- refusing to train on too little data to teach anything real"
        )
        return report

    try:
        import torch
        from datasets import Dataset
        from peft import get_peft_model, prepare_model_for_kbit_training
        from transformers import (
            AutoModelForCausalLM, AutoTokenizer, DataCollatorForSeq2Seq,
            Trainer, TrainingArguments,
        )

        tokenizer = AutoTokenizer.from_pretrained(base_model)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        examples = [
            ex for ex in (
                _tokenize_example(r, tokenizer, max_length=max_length) for r in rows
            )
            if ex is not None
        ]
        report.example_count = len(examples)
        if len(examples) < min_examples:
            report.error = (
                f"only {len(examples)} examples survived masking-safe "
                f"tokenization (need >= {min_examples}) -- refusing to "
                f"train on too little real data"
            )
            return report

        dataset = Dataset.from_list(examples)

        model = AutoModelForCausalLM.from_pretrained(
            base_model,
            quantization_config=build_quantization_config(),
            dtype=torch.float16,
            device_map="auto",
        )
        model.config.use_cache = False
        # gradient-checkpointing-d: cuts activation memory during the
        # backward pass. prepare_model_for_kbit_training() is the
        # standard QLoRA prep step (casts norm layers to fp32, enables
        # input grads, etc.) — checkpointing is enabled separately, right
        # after, with use_reentrant=False (more reliable alongside a
        # quantized model per hardware-liberation-d's research).
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=False)
        try:
            model.gradient_checkpointing_enable(
                gradient_checkpointing_kwargs={"use_reentrant": False}
            )
        except TypeError:
            model.gradient_checkpointing_enable()
        model.enable_input_require_grads()
        model = get_peft_model(model, build_lora_config())

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        args = TrainingArguments(
            output_dir=str(output_dir),
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            learning_rate=learning_rate,
            fp16=True,
            logging_steps=max(1, len(examples) // 10),
            save_strategy="no",  # we save the adapter explicitly below
            report_to=[],
        )
        trainer = Trainer(
            model=model, args=args, train_dataset=dataset,
            data_collator=DataCollatorForSeq2Seq(
                tokenizer=tokenizer, padding=True, label_pad_token_id=-100,
                return_tensors="pt",
            ),
        )
        result = trainer.train()

        model.save_pretrained(str(output_dir))
        tokenizer.save_pretrained(str(output_dir))

        report.final_loss = float(result.training_loss)
        report.ok = True
        return report
    except Exception as exc:  # noqa: BLE001 — a training failure is a result, not a crash
        report.error = f"{type(exc).__name__}: {exc}"
        return report


__all__ = [
    "DEFAULT_BASE_MODEL", "TrainingReport",
    "load_training_rows", "format_example", "build_quantization_config",
    "build_lora_config", "train_lora",
]
