"""model_ladder.py — 🪜 prove-then-promote: bigger minds only when proven.

Kevin's direction (2026-07-17, after studying colibrì): configure BIGGER
models into the system, but they only become slot defaults if the vessel
PROVES it can carry them — otherwise she falls back to the smaller model
that already works. Colibrì's `coli plan` / `coli doctor` shape, applied
to her Ollama slots.

The contract (constructed, never assumed):
  • every slot (orchestrator/coder/fast/...) has a LADDER — rung 0 is the
    configured, known-good model; higher rungs are bigger candidates.
  • a candidate NEVER becomes the default by being installed. It must pass
    a bounded PROOF TRIAL on this exact hardware: load within MAX_LOAD_S,
    generate at ≥ MIN_TOK_S, answer non-empty. keep_alive=0 — a trial can
    never zombify VRAM.
  • proofs are pinned to a hardware fingerprint. New GPU / more RAM →
    old proofs no longer vouch; the ladder re-proves before promoting.
  • promotion is EXPLICIT (`sov models promote <slot>` writes the
    AGENT_<SLOT>_MODEL line into the vault) — propose-don't-act holds.
  • everything degrades honestly: no GPU, no Ollama, corrupt files →
    reports say so; nothing crashes, nothing silently changes.
"""
from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

# model-ladder-threshold-d (Kevin, 2026-07-21): "I am comfortable with the
# .5 token loss for the 7 billion parameter extra quality" -> then, after
# qwen3:14b (orchestrator candidate) settled at a real, repeatable 3.7
# tok/s across 3 clean trials (nothing else on the GPU): "3.7 is fine.
# Just 3.0 is the lowest." Lowered again, 4.0 -> 3.0 -- his explicit,
# twice-stated floor, not a default drifting downward on its own.
MIN_TOK_S = 3.0       # below this, a slot default feels broken, not bigger
MAX_LOAD_S = 180.0    # a default must come up in reasonable time
_PROVE_PROMPT = ("Reply with one short sentence: what is the most important "
                 "quality of a reliable assistant?")
_PROVE_TOKENS = 48
_TIMEOUT_S = 600.0    # the trial request itself (big model, cold disk)

SLOTS = ("orchestrator", "coder", "fast", "reflector", "interpreter", "vision")


# ── hardware truth ──────────────────────────────────────────────────────────
def probe_hardware(runner=None) -> dict:
    """Measure, don't assume: VRAM (nvidia-smi) + RAM (/proc/meminfo).
    Missing GPU or tooling → zeros with a note, never an exception."""
    import subprocess

    def _default_runner(cmd: list[str]) -> str:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=10).stdout

    run = runner or _default_runner
    hw = {"vram_total_mb": 0, "vram_free_mb": 0, "gpu": "",
          "ram_total_mb": 0, "ram_available_mb": 0}
    try:
        out = run(["nvidia-smi", "--query-gpu=name,memory.total,memory.free",
                   "--format=csv,noheader,nounits"])
        first = (out or "").strip().splitlines()
        if first:
            name, total, free = [p.strip() for p in first[0].split(",")[:3]]
            hw.update(gpu=name, vram_total_mb=int(float(total)),
                      vram_free_mb=int(float(free)))
    except Exception:  # noqa: BLE001 — no GPU is a fact, not an error
        pass
    try:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
        for line in meminfo.splitlines():
            if line.startswith("MemTotal:"):
                hw["ram_total_mb"] = int(line.split()[1]) // 1024
            elif line.startswith("MemAvailable:"):
                hw["ram_available_mb"] = int(line.split()[1]) // 1024
    except Exception:  # noqa: BLE001
        pass
    return hw


def hw_fingerprint(hw: dict) -> str:
    """What a proof is pinned to — capacity, not the moment's free space."""
    return f"{hw.get('gpu', '')}|{hw.get('vram_total_mb', 0)}MB|" \
           f"{hw.get('ram_total_mb', 0)}MB"


# ── the ladder store ────────────────────────────────────────────────────────
def _dir(data_dir: Path) -> Path:
    return Path(data_dir) / "model_ladder"


def ladder_path(data_dir: Path) -> Path:
    return _dir(data_dir) / "ladder.json"


def proofs_path(data_dir: Path) -> Path:
    return _dir(data_dir) / "proofs.ndjson"


def _base_models() -> dict[str, str]:
    """Rung 0 per slot = the configured, known-good model."""
    try:
        from sovereign_agent.config import SETTINGS
        return {
            "orchestrator": SETTINGS.orchestrator_model,
            "coder": SETTINGS.coder_model,
            "fast": SETTINGS.fast_model,
            "reflector": SETTINGS.reflector_model,
            "interpreter": SETTINGS.interpreter_model,
            "vision": SETTINGS.vision_model,
        }
    except Exception:  # noqa: BLE001
        return {s: "" for s in SLOTS}


def load_ladder(data_dir: Path) -> dict[str, list[str]]:
    """{slot: [rung0, rung1, ...]} — rung 0 is always the configured base
    (refreshed live so a config change can't orphan the ladder)."""
    stored: dict = {}
    try:
        stored = json.loads(ladder_path(data_dir).read_text(encoding="utf-8"))
        if not isinstance(stored, dict):
            stored = {}
    except Exception:  # noqa: BLE001
        stored = {}
    bases = _base_models()
    out: dict[str, list[str]] = {}
    for slot in SLOTS:
        rungs = [str(m) for m in stored.get(slot, []) if str(m).strip()]
        base = bases.get(slot, "")
        if base and base not in rungs:
            rungs.insert(0, base)
        out[slot] = rungs
    return out


def save_ladder(data_dir: Path, ladder: dict[str, list[str]]) -> None:
    d = _dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    tmp = ladder_path(data_dir).with_suffix(".tmp")
    tmp.write_text(json.dumps(ladder, indent=2), encoding="utf-8")
    tmp.replace(ladder_path(data_dir))


def add_rung(data_dir: Path, slot: str, model: str) -> str:
    """Register a bigger candidate on a slot's ladder (top of the ladder)."""
    slot = slot.strip().lower()
    if slot not in SLOTS:
        return f"unknown slot '{slot}' — slots: {', '.join(SLOTS)}"
    ladder = load_ladder(data_dir)
    if model in ladder[slot]:
        return f"{model} is already on the {slot} ladder"
    ladder[slot].append(model)
    save_ladder(data_dir, ladder)
    return (f"🪜 {model} added to the {slot} ladder (rung "
            f"{len(ladder[slot]) - 1}) — unproven until `sov models prove "
            f"{model}` passes on this hardware")


# ── proof trials ────────────────────────────────────────────────────────────
@dataclass
class ProofRecord:
    model: str
    ts: float
    fingerprint: str
    ok: bool
    load_s: float = 0.0
    tok_s: float = 0.0
    note: str = ""
    extra: dict = field(default_factory=dict)


def _default_post(url: str, payload: dict) -> dict:  # pragma: no cover - network
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))


def _default_get(url: str) -> dict:  # pragma: no cover - network
    with urllib.request.urlopen(url, timeout=_TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))


def _host() -> str:
    try:
        from sovereign_agent.config import SETTINGS
        return SETTINGS.ollama_host.rstrip("/")
    except Exception:  # noqa: BLE001
        return "http://127.0.0.1:11434"


# ── no-GPU-offload policy (Kevin, 2026-07-28) ───────────────────────────────
# "We want no gpu off loading allowed." Ollama/llama.cpp decide the GPU/CPU
# layer split ONCE, at load time, from the model's weight size + the
# configured num_ctx's KV-cache reservation -- NOT dynamically as a
# conversation fills up. There is no in-flight "about to offload" moment to
# detect and gracefully wrap up from; the split is already fixed before the
# first token generates. So the real fix is structural, not a runtime
# monitor: confirm 100% GPU residency via /api/ps BEFORE trusting a speed
# measurement, and search for the largest num_ctx that keeps a model fully
# GPU-resident before ever dressing a slot onto it.
_GPU_CHECK_PROMPT = "hi"
_GPU_CHECK_KEEP_ALIVE = "20s"     # long enough to land the /api/ps check right after
_NO_OFFLOAD_CTX_CANDIDATES = (16384, 12288, 8192, 6144, 4096, 3072, 2048, 1536, 1024, 512)


def _gpu_fraction(model: str, ps_response: dict) -> float | None:
    """Real GPU-resident fraction (0.0-1.0) for `model` from Ollama's own
    `/api/ps` response (`size_vram / size` -- the same math `ollama ps`
    itself displays as "X% GPU" / "Y%/Z% CPU/GPU"). None if the model
    isn't in the response at all (not loaded, or already unloaded)."""
    for m in (ps_response or {}).get("models", []) or []:
        if m.get("name") == model or m.get("model") == model:
            size = float(m.get("size", 0)) or 1.0
            size_vram = float(m.get("size_vram", 0))
            return size_vram / size
    return None


def _probe_gpu_fraction(model: str, *, num_ctx: int | None,
                        poster, getter) -> float | None:
    """Briefly load `model` (short keep_alive, 1 token -- cheap) and read
    back its real GPU-resident fraction. Shared by `prove_model`'s
    pre-check and `find_max_no_offload_ctx`'s search."""
    options: dict = {"num_predict": 1}
    if num_ctx is not None:
        options["num_ctx"] = num_ctx
    poster(f"{_host()}/api/generate", {
        "model": model, "prompt": _GPU_CHECK_PROMPT, "stream": False,
        "think": False, "options": options, "keep_alive": _GPU_CHECK_KEEP_ALIVE})
    ps = getter(f"{_host()}/api/ps")
    return _gpu_fraction(model, ps)


def find_max_no_offload_ctx(model: str, *, poster=None, getter=None,
                            candidates: tuple[int, ...] = _NO_OFFLOAD_CTX_CANDIDATES,
                            ) -> int | None:
    """The largest num_ctx (checked biggest-first) that keeps `model`
    100% GPU-resident on this hardware right now. None if even the
    smallest candidate still offloads -- the model itself doesn't fit on
    this card at any usable context size, full stop."""
    post = poster or _default_post
    get = getter or _default_get
    for ctx in candidates:
        frac = _probe_gpu_fraction(model, num_ctx=ctx, poster=post, getter=get)
        if frac is not None and frac >= 1.0:
            return ctx
    return None


def dress_slot_no_offload(data_dir: Path, slot: str, model: str, *,
                          poster=None, getter=None) -> str:
    """The ONE path that assigns a slot's base model -- shared by
    `promote_slot` and the `set-base` CLI command, so "no GPU offloading
    allowed" is enforced no matter which door a model comes in through.
    Refuses outright (never calls set_base/create_model at all) if no
    context size keeps `model` fully GPU-resident on this hardware."""
    ctx = find_max_no_offload_ctx(model, poster=poster, getter=getter)
    if ctx is None:
        return (f"refused — {model} can't run 100% on GPU at any usable "
                f"context size on this hardware. No-offload policy blocks it.")
    from sovereign_agent.model_corps import create_model, set_base
    set_base(slot, model, num_ctx=ctx)
    result = create_model(slot)
    if not result.ok:
        return f"couldn't rebuild aria-{slot}: {result.detail}"
    note = "" if ctx == max(_NO_OFFLOAD_CTX_CANDIDATES) else \
        f" (context capped at {ctx} to keep it 100% GPU)"
    return (f"🪜 {slot} set to {model}{note} — aria-{slot} rebuilt and "
           f"dressed with her persona, 100% GPU. Live now.")


def prove_model(model: str, *, hw: dict | None = None,
                poster=None, getter=None) -> ProofRecord:
    """One bounded trial: load, generate ~48 tokens, measure, unload
    (keep_alive=0). Pass/fail against MIN_TOK_S + MAX_LOAD_S. Never raises.

    no-offloading-d (Kevin, 2026-07-28): "no GPU offloading allowed" --
    BEFORE any speed measurement, confirms 100% GPU residency via
    /api/ps. Anything less fails the trial outright, regardless of
    tok/s -- a model that spills to CPU can never pass this trial again,
    no matter how fast the CPU-assisted number looks.

    model-ladder-thinking-fix-d (Kevin, 2026-07-21): hybrid-reasoning
    models (Qwen3 and its family) stream a SEPARATE "thinking" block
    before the real answer in newer Ollama, and used to burn the whole
    _PROVE_TOKENS budget on that reasoning, leaving `response` empty --
    confirmed directly against qwen3:14b (`done_reason: "length"`, full
    `thinking` field, empty `response`). That's a bug in the TRIAL, not a
    real capability failure: the same prompt with `think: false` answers
    cleanly in one line. think=false also matches what a prove trial
    should measure -- direct answer throughput, not reasoning-mode
    latency, since model_corps Modelfiles don't ask for chain-of-thought
    either. Non-reasoning models simply ignore an unrecognized `think`
    field, so this is safe for every model, not just Qwen3.
    """
    post = poster or _default_post
    get = getter or _default_get
    hw = hw or probe_hardware()
    fp = hw_fingerprint(hw)
    try:
        frac = _probe_gpu_fraction(model, num_ctx=None, poster=post, getter=get)
        if frac is not None and frac < 1.0:
            pct = round(frac * 100)
            return ProofRecord(model, time.time(), fp, False,
                               note=f"offloads to CPU ({pct}% GPU) — "
                                    f"no-offload policy rejects it")
        t0 = time.monotonic()
        resp = post(f"{_host()}/api/generate", {
            "model": model, "prompt": _PROVE_PROMPT, "stream": False,
            "think": False,
            "options": {"num_predict": _PROVE_TOKENS}, "keep_alive": 0})
        wall = time.monotonic() - t0
        load_s = float(resp.get("load_duration", 0)) / 1e9
        eval_n = int(resp.get("eval_count", 0))
        eval_ns = float(resp.get("eval_duration", 0)) or 1.0
        tok_s = eval_n / (eval_ns / 1e9)
        text = str(resp.get("response", "")).strip()
        ok = bool(text) and tok_s >= MIN_TOK_S and load_s <= MAX_LOAD_S
        note = "passed" if ok else (
            "empty answer" if not text else
            f"too slow ({tok_s:.1f} tok/s < {MIN_TOK_S})" if tok_s < MIN_TOK_S
            else f"load too slow ({load_s:.0f}s > {MAX_LOAD_S:.0f}s)")
        return ProofRecord(model, time.time(), fp, ok, round(load_s, 2),
                           round(tok_s, 2), note,
                           {"wall_s": round(wall, 2), "eval_count": eval_n})
    except Exception as exc:  # noqa: BLE001 — a failed trial is a result
        return ProofRecord(model, time.time(), fp, False,
                           note=f"trial failed: {type(exc).__name__}: {exc}")


# ── prefill benchmark (flash-attention-d, Kevin+GLM 5.2, 2026-07-28) ───────
# "Enabling OLLAMA_FLASH_ATTENTION=1 on Pascal won't move decode tok/s
# (bandwidth-bound at batch size 1) but should move prefill tok/s + peak
# VRAM during long-context ingestion." `prove_model`'s short one-sentence
# prompt can't show that -- it barely touches the KV cache. This is a
# SEPARATE diagnostic, not folded into the promotion-gating ProofRecord:
# prefill speed isn't a promotion criterion, just a one-off measurement
# for this specific investigation.
_PREFILL_PARAGRAPH = (
    "The trading floor of warframe.market never truly sleeps: orders for "
    "vaulted relics and freshly listed prime sets scroll past in a steady "
    "stream, each one a small bet by an in-game trader hoping the platinum "
    "moves before the listing goes stale. A patient scanner watches the "
    "spread between the cheapest live sell and the highest live buy, "
    "filters out anyone who has gone offline, and waits for the moment "
    "the two prices cross far enough to be worth the risk. ")
_PREFILL_PROMPT = ("Summarize the following passage in one short sentence.\n\n"
                   + _PREFILL_PARAGRAPH * 40)   # ~1,800-2,000 tokens of prompt
_PREFILL_PREDICT_TOKENS = 16   # just enough for a decode cross-check, not the point


@dataclass
class PrefillProbe:
    model: str
    ts: float
    ok: bool
    load_s: float = 0.0
    prefill_tok_s: float = 0.0
    decode_tok_s: float = 0.0
    prompt_tokens: int = 0
    note: str = ""


def prove_prefill(model: str, *, poster=None) -> PrefillProbe:
    """One long-prompt trial: measures real prompt-eval (prefill) tok/s
    alongside a decode-tok/s cross-check, from Ollama's own
    `prompt_eval_count`/`prompt_eval_duration` fields. keep_alive=0 --
    same never-zombify-VRAM rule as `prove_model`.

    Ollama reports `prompt_eval_duration: 0` when the prompt hit its own
    prefix cache -- a real signal (this run measured nothing), not a
    divide-by-zero to paper over. Reported as `ok=False` with a note
    telling the operator to vary the prompt or restart Ollama and retry,
    rather than a fabricated tok/s."""
    post = poster or _default_post
    try:
        resp = post(f"{_host()}/api/generate", {
            "model": model, "prompt": _PREFILL_PROMPT, "stream": False,
            "think": False,
            "options": {"num_predict": _PREFILL_PREDICT_TOKENS}, "keep_alive": 0})
        load_s = float(resp.get("load_duration", 0)) / 1e9
        prompt_n = int(resp.get("prompt_eval_count", 0))
        prompt_ns = float(resp.get("prompt_eval_duration", 0))
        eval_n = int(resp.get("eval_count", 0))
        eval_ns = float(resp.get("eval_duration", 0)) or 1.0
        decode_tok_s = eval_n / (eval_ns / 1e9)
        if prompt_ns <= 0:
            return PrefillProbe(model, time.time(), False, round(load_s, 2),
                                0.0, round(decode_tok_s, 2), prompt_n,
                                "prompt_eval_duration=0 — prompt was served "
                                "from Ollama's own cache, not a cold prefill; "
                                "vary the prompt or restart ollama and retry")
        prefill_tok_s = prompt_n / (prompt_ns / 1e9)
        text = str(resp.get("response", "")).strip()
        ok = bool(text)
        return PrefillProbe(model, time.time(), ok, round(load_s, 2),
                            round(prefill_tok_s, 2), round(decode_tok_s, 2),
                            prompt_n, "measured" if ok else "empty answer")
    except Exception as exc:  # noqa: BLE001 — a failed trial is a result
        return PrefillProbe(model, time.time(), False,
                            note=f"trial failed: {type(exc).__name__}: {exc}")


def record_proof(data_dir: Path, proof: ProofRecord) -> None:
    d = _dir(data_dir)
    d.mkdir(parents=True, exist_ok=True)
    with proofs_path(data_dir).open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(proof)) + "\n")


def latest_proof(data_dir: Path, model: str,
                 fingerprint: str) -> ProofRecord | None:
    """Newest proof for this model ON THIS HARDWARE — proofs from another
    machine shape never vouch here."""
    best = None
    try:
        for line in proofs_path(data_dir).read_text(
                encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if r.get("model") == model and r.get("fingerprint") == fingerprint:
                if best is None or float(r.get("ts", 0)) >= best["ts"]:
                    best = r
    except Exception:  # noqa: BLE001
        return None
    if best is None:
        return None
    known = {k: best.get(k) for k in
             ("model", "ts", "fingerprint", "ok", "load_s", "tok_s", "note")}
    return ProofRecord(extra=best.get("extra", {}) or {}, **known)


# ── resolution: who actually gets the slot ─────────────────────────────────
def _already_dressed_on(slot: str, model: str) -> bool:
    """True if model_corps.bases already records `model` as this slot's
    current base -- i.e. a `promote_slot()` call already folded this
    candidate INTO aria-<slot> itself, so it's no longer a separate
    pending choice."""
    try:
        from sovereign_agent.model_corps import load_bases
        return load_bases().get(slot, {}).get("model") == model
    except Exception:  # noqa: BLE001
        return False


def resolve_slot(data_dir: Path, slot: str, *,
                 fingerprint: str) -> tuple[str, str]:
    """Walk the ladder top-down: the highest rung with a PASSING proof on
    this hardware wins; nothing proven above rung 0 → the base model.
    Returns (model, reason).

    model-corps-unify-d: a candidate already folded into rung 0 via
    `promote_slot()` (recorded in model_corps.bases) is reported as the
    BASE resolving, annotated with what it's dressed on -- not as a
    separate, still-pending "you could promote this" suggestion. Fixes
    the exact confusing display this session found: `sov models status`
    showing "→ qwen3:14b" as if promoting orchestrator hadn't happened
    yet, when aria-orchestrator:latest was already rebuilt on it.
    """
    ladder = load_ladder(data_dir)
    rungs = ladder.get(slot, [])
    if not rungs:
        return "", "no ladder for this slot"
    for model in reversed(rungs[1:]):        # biggest candidates first
        proof = latest_proof(data_dir, model, fingerprint)
        if proof is not None and proof.ok:
            if _already_dressed_on(slot, model):
                return rungs[0], (f"base model — already dressed on {model} "
                                  f"({proof.tok_s:.1f} tok/s, proven)")
            return model, (f"proven on this hardware "
                           f"({proof.tok_s:.1f} tok/s, load {proof.load_s:.0f}s)")
    return rungs[0], ("base model (no bigger rung has a passing proof "
                      "on this hardware)")


def promote_slot(data_dir: Path, slot: str, *, poster=None, getter=None) -> str:
    """Dress + rebuild aria-<slot> on the proven model — the explicit
    consent step. Refuses when only the base resolves (no silent
    'promotion' to what's already running).

    model-corps-unify-d (Kevin, 2026-07-21): "rebuild the entire models
    system if you have to and make it nice." This used to write the RAW
    proven model straight into the vault (AGENT_<SLOT>_MODEL), bypassing
    the god-tier persona entirely -- confirmed as a real bug this session
    (promoting the coder briefly stripped its persona until caught and
    fixed by hand). Now it goes through model_corps.bases: records the
    new base durably (so a future `regen_model_corps.sh` run can't
    silently regress it), then actually rebuilds aria-<slot> dressed with
    her persona on the new base. No vault write needed at all --
    AGENT_<SLOT>_MODEL already defaults to aria-<slot>:latest, and that's
    exactly the tag this rebuilds. Live immediately, not "next launch".
    """
    slot = slot.strip().lower()
    if slot not in SLOTS:
        return f"unknown slot '{slot}' — slots: {', '.join(SLOTS)}"
    fp = hw_fingerprint(probe_hardware())
    model, reason = resolve_slot(data_dir, slot, fingerprint=fp)
    if not model:
        return f"nothing to promote — {reason}"
    rungs = load_ladder(data_dir).get(slot, [])
    if rungs and model == rungs[0]:
        return (f"{slot} stays on its base model {model} — {reason}. "
                f"Prove a bigger rung first: sov models prove <model>")
    try:
        outcome = dress_slot_no_offload(data_dir, slot, model,
                                        poster=poster, getter=getter)
    except Exception as exc:  # noqa: BLE001
        return f"couldn't dress/rebuild aria-{slot} ({type(exc).__name__}: {exc})"
    if outcome.startswith("refused"):
        return outcome
    if outcome.startswith("couldn't"):
        return outcome
    return f"🪜 promoting {slot} ({reason}) — {outcome}"


# ── the report ─────────────────────────────────────────────────────────────
def render_ladder_report(data_dir: Path) -> str:
    hw = probe_hardware()
    fp = hw_fingerprint(hw)
    lines = ["🪜 Model Ladder — prove-then-promote", ""]
    if hw["vram_total_mb"]:
        lines.append(f"vessel: {hw['gpu']} {hw['vram_total_mb']} MB VRAM "
                     f"({hw['vram_free_mb']} MB free) · "
                     f"RAM {hw['ram_total_mb']} MB "
                     f"({hw['ram_available_mb']} MB available)")
    else:
        lines.append(f"vessel: no GPU detected · RAM {hw['ram_total_mb']} MB")
    lines.append("")
    ladder = load_ladder(data_dir)
    for slot in SLOTS:
        rungs = ladder.get(slot, [])
        if not rungs:
            continue
        resolved, reason = resolve_slot(data_dir, slot, fingerprint=fp)
        lines.append(f"{slot}: → {resolved or '(none)'}")
        lines.append(f"   {reason}")
        for i, model in enumerate(rungs):
            proof = latest_proof(data_dir, model, fp)
            if i == 0:
                status = "base (always trusted)"
            elif proof is None:
                status = "unproven — sov models prove " + model
            elif proof.ok and _already_dressed_on(slot, model):
                status = f"PROVEN {proof.tok_s:.1f} tok/s — folded into {slot}'s base (promoted)"
            elif proof.ok:
                status = f"PROVEN {proof.tok_s:.1f} tok/s"
            else:
                status = f"failed: {proof.note}"
            mark = "▸" if model == resolved else " "
            lines.append(f"   {mark} rung {i}: {model} — {status}")
        lines.append("")
    lines.append("add a bigger candidate: sov models add <slot> <model> · "
                 "trial it: sov models prove <model> · "
                 "make it the default: sov models promote <slot>")
    return "\n".join(lines)


__all__ = ["MIN_TOK_S", "MAX_LOAD_S", "SLOTS", "ProofRecord", "PrefillProbe",
           "probe_hardware", "hw_fingerprint", "load_ladder", "save_ladder",
           "add_rung", "prove_model", "prove_prefill", "record_proof",
           "latest_proof", "resolve_slot", "promote_slot",
           "render_ladder_report", "find_max_no_offload_ctx",
           "dress_slot_no_offload"]
