"""referrals.py — 🤝 referral codes, usage-credits, and the earnings ledger.

Kevin's design (2026-07-18):
  • Every member gets a **unique referral code** the moment Aria profiles
    them (minted here, deterministic from their stable Discord ID).
  • A successful referral rewards BOTH sides with **usage credits** — each
    credit buys one extra answer from Aria past her cooldown (cheap, no
    money moves). Marketers instead earn a recurring cash split (the money
    half lives in `payouts.py`, built with the Stripe reconciler — this
    module only *tracks* earnings so it's ready).
  • Earnings/credits are tracked **per user, keyed by Discord ID** — the
    same durable identity Aria uses in `members.py`. `/earnings` shows a
    person their own numbers.

Financial-integrity note: money fields (`earned/paid/pending`) are carried
here as an audited **append-only ledger** (the truth) with the per-user
record as a derived read-model, so the payout engine plugs in without ever
mutating a balance in place. This module never moves money — it only
records credits and *attributed* earnings; `payouts.py` does the paying,
conservatively, later.

Hardening round (Kevin, 2026-07-19: "harden her reward systems... use
the best science"):
  • **Sybil resistance, propose-not-deny** (H1a). `redeem()` is directly
    user-invocable (`/refer use:<code>`) with no defense beyond same-ID
    and already-referred checks — the classic referral-farm vector
    (spin up alt accounts, redeem each other's codes). Discord IDs are
    Snowflakes (42-bit ms timestamp since the Discord epoch
    2015-01-01T00:00:00Z, extracted via `id >> 22` — Discord's own
    documented format, no network call needed), so account age is a
    free signal. Graph+behavior-hybrid Sybil-detection literature
    (e.g. Kumar & Bhat, "User behavior-based and graph-based hybrid
    approach for detection of Sybil Attack in online social networks",
    2022) names account age + referral velocity as the practical,
    cheap layer beneath full graph analysis — that's what `SybilPolicy`
    checks. A below-threshold referral is HELD (ledgered
    `referral-held`, never silently rejected) so a legitimate new
    member is never blocked — the project's whole propose-don't-deny
    doctrine, applied here.
  • **Ledger reconciliation** (H1b). The docstring above claims "the
    ledger is the truth" but nothing ever proved the derived `credits`/
    `earned_cents` fields actually match it — `verify_ledger_consistency`
    replays the ledger and reports drift (the event-sourcing
    reconciliation pattern: Kleppmann, *Designing Data-Intensive
    Applications*, ch. 11 — "the log is the source of truth; the
    materialized view must be rebuilt from it and checked against it").
  • **Write-failure visibility** (H1c). Every store write used to
    swallow ALL exceptions silently (`except Exception: pass`) — a
    dropped credit grant left zero trace. `_report_write_failure` opens
    a `diagnosis.ConflictCatalog` case (type="omission" — a write
    silently didn't happen) so it becomes visible instead of tribal
    memory; if even THAT fails, it falls back to stdlib `logging` so a
    trace always exists somewhere.
  • **Idempotency + a credit ceiling** (H1d). `grant_credits` takes an
    optional `idempotency_key` (Stripe's own well-known pattern — this
    project's own `STRIPE_LOCKIN.md` already leans on it) so a retried
    Discord interaction can never double-grant; plus `MAX_CREDITS`, a
    sane per-profile ceiling.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from pathlib import Path

_LOG = logging.getLogger(__name__)

# Discord's Snowflake epoch (2015-01-01T00:00:00.000Z), in ms since Unix epoch.
DISCORD_EPOCH_MS = 1420070400000

# member usage-credit reward (both sides of a referral)
CREDIT_PER_REFERRAL = 10
# marketer cash split (used by the deferred payout engine)
MARKETER_PCT = 0.25
MARKETER_MONTHS = 6
# H1d — a sane ceiling; grant_credits clamps to it rather than growing
# unbounded (a bug or abuse loop can never mint an unlimited balance).
MAX_CREDITS = 5000

ROLE_MEMBER = "member"
ROLE_MARKETER = "marketer"

# 🎮 the game: friendly ranks you climb by growing a kind community.
# (threshold of referrals, title). Sharing = building the circle, not a grind.
RANKS: list[tuple[int, str]] = [
    (0, "🌱 Newcomer"),
    (1, "🤝 Friend"),
    (3, "🔗 Connector"),
    (5, "⭐ Ambassador"),
    (10, "🌟 Community Legend"),
    (25, "👑 Founder's Circle"),
]


# ── H1a: sybil resistance ────────────────────────────────────────────────────
def account_age_days(user_id: str, *, now: float | None = None) -> float:
    """Age of a Discord account in days, decoded from its Snowflake ID alone
    (no network call). Discord IDs encode a 42-bit ms timestamp in the high
    bits: ``created_ms = (id >> 22) + DISCORD_EPOCH_MS``. A non-numeric or
    malformed ID returns 0.0 (treated as brand-new — the conservative,
    never-trust-by-default default)."""
    now = time.time() if now is None else now
    digits = "".join(c for c in str(user_id) if c.isdigit())
    if not digits:
        return 0.0
    try:
        snowflake = int(digits)
    except ValueError:
        return 0.0
    created_s = ((snowflake >> 22) + DISCORD_EPOCH_MS) / 1000.0
    age = (now - created_s) / 86400.0
    return max(0.0, age)


class SybilPolicy:
    """H1a's thresholds. A referral failing either check is HELD, never
    silently denied — a legitimate new member is never blocked, just
    flagged for review (the project's propose-don't-deny doctrine)."""

    def __init__(self, min_account_age_days: float = 3.0,
                max_referrals_per_window: int = 5,
                window_hours: float = 24.0) -> None:
        self.min_account_age_days = min_account_age_days
        self.max_referrals_per_window = max_referrals_per_window
        self.window_hours = window_hours


DEFAULT_SYBIL_POLICY = SybilPolicy()


def _recent_referral_count(data_dir: Path, referrer_id: str, *,
                           window_hours: float, now: float) -> int:
    """How many `referral` events this referrer has RECEIVED CREDIT FOR
    in the trailing window, read from the append-only ledger (the truth,
    never the mutable profile — can't be gamed by editing a JSON file)."""
    cutoff = now - window_hours * 3600.0
    count = 0
    try:
        with _ledger_path(data_dir).open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    ev = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if (ev.get("kind") == "referral"
                        and ev.get("referrer") == referrer_id
                        and float(ev.get("ts", 0)) >= cutoff):
                    count += 1
    except OSError:
        return 0
    return count


def rank_for(referred: int) -> dict:
    """Current title + progress to the next rank — the game HUD."""
    referred = int(referred)
    title = RANKS[0][1]
    nxt = None
    for i, (need, name) in enumerate(RANKS):
        if referred >= need:
            title = name
            nxt = RANKS[i + 1] if i + 1 < len(RANKS) else None
        else:
            break
    to_next = (nxt[0] - referred) if nxt else 0
    return {"title": title, "next_title": nxt[1] if nxt else None,
            "next_at": nxt[0] if nxt else None, "to_next": to_next}


def _bar(cur: int, target: int, width: int = 10) -> str:
    if not target:
        return "█" * width + " MAXED 🎉"
    filled = max(0, min(width, round(width * cur / target)))
    return "█" * filled + "░" * (width - filled)


# ── paths ────────────────────────────────────────────────────────────────────
def _dir(data_dir: Path) -> Path:
    return Path(data_dir) / "community" / "referrals"


def _rec_path(data_dir: Path, user_id: str) -> Path:
    return _dir(data_dir) / f"{_safe_id(user_id)}.json"


def _index_path(data_dir: Path) -> Path:
    return _dir(data_dir) / "codes.json"          # code -> user_id


def _ledger_path(data_dir: Path) -> Path:
    return _dir(data_dir) / "ledger.ndjson"       # append-only truth


def _safe_id(user_id: str) -> str:
    return "".join(c for c in str(user_id) if c.isdigit()) or "unknown"


# ── the deterministic code ───────────────────────────────────────────────────
def ref_code_for(user_id: str) -> str:
    """A stable, unique code derived from the Discord ID — same ID always
    yields the same code, so minting is idempotent and needs no counter."""
    h = hashlib.sha256(_safe_id(user_id).encode()).digest()[:5]
    tag = base64.b32encode(h).decode().rstrip("=")[:7]
    return "REF-" + tag


# ── low-level store (atomic, corrupt-safe) ──────────────────────────────────
def _blank(user_id: str, now: float) -> dict:
    return {"id": _safe_id(user_id), "code": ref_code_for(user_id),
            "role": ROLE_MEMBER, "credits": 0,
            "referred_by": None, "referred_at": None, "referred": [],
            "earned_cents": 0, "paid_cents": 0, "pending_cents": 0,
            "created": now}


def _load(data_dir: Path, user_id: str) -> dict | None:
    try:
        return json.loads(_rec_path(data_dir, user_id).read_text("utf-8"))
    except Exception:  # noqa: BLE001
        return None


# ── H1c: write-failure visibility ───────────────────────────────────────────
def _report_write_failure(data_dir: Path, where: str, detail: str,
                          impacted: str = "") -> None:
    """A store write just failed — this must never be silent (Kevin's own
    doctrine, written elsewhere in this plan for payouts: 'never tell me it
    paid when it didn't'). Opens a diagnosis.py Conflict case (type
    'omission' — a write silently didn't happen) so it becomes a visible,
    shared note instead of tribal memory. If EVEN THAT fails (the same
    disk problem could plausibly take it down too), fall back to stdlib
    logging so a trace exists somewhere no matter what."""
    try:
        from sovereign_agent.diagnosis import ConflictCatalog

        cat = ConflictCatalog(Path(data_dir) / "diagnoses")
        cat.open_conflict(
            type="omission", actor="aria", severity="medium",
            trigger_event=f"referrals.{where} failed: {detail}",
            impacted=[impacted] if impacted else [],
        )
    except Exception:  # noqa: BLE001
        _LOG.error("referrals write failure (diagnosis catalog also "
                  "unavailable): %s: %s", where, detail)


def _write(data_dir: Path, rec: dict) -> None:
    p = _rec_path(data_dir, rec.get("id", "?"))
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception as exc:  # noqa: BLE001
        _report_write_failure(data_dir, "_write", repr(exc),
                              impacted=str(rec.get("id", "")))


def _load_index(data_dir: Path) -> dict:
    try:
        d = json.loads(_index_path(data_dir).read_text("utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _save_index(data_dir: Path, idx: dict) -> None:
    p = _index_path(data_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception as exc:  # noqa: BLE001
        _report_write_failure(data_dir, "_save_index", repr(exc))


def _append_ledger(data_dir: Path, event: dict) -> None:
    """Append-only audit truth — every credit/earning event, never edited."""
    event = {"ts": time.time(), **event}
    p = _ledger_path(data_dir)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
    except Exception as exc:  # noqa: BLE001
        _report_write_failure(data_dir, "_append_ledger", repr(exc),
                              impacted=str(event.get("user", "")))


# ── public API ───────────────────────────────────────────────────────────────
def ensure_profile(data_dir: Path, user_id: str, *,
                   now: float | None = None) -> dict:
    """Mint a member's referral profile + code on first contact (idempotent).
    Registers the code→id index so redemptions can resolve it."""
    now = time.time() if now is None else now
    rec = _load(data_dir, user_id)
    if rec is None:
        rec = _blank(user_id, now)
        _write(data_dir, rec)
    # keep the code index in sync (self-heals if the file was lost)
    idx = _load_index(data_dir)
    if idx.get(rec["code"]) != rec["id"]:
        idx[rec["code"]] = rec["id"]
        _save_index(data_dir, idx)
    return rec


def resolve_code(data_dir: Path, code: str) -> str | None:
    """code → the owner's Discord ID (None if unknown)."""
    code = (code or "").strip().upper()
    if not code.startswith("REF-"):
        code = "REF-" + code.lstrip("-")
    return _load_index(data_dir).get(code)


def _ledger_has_key(data_dir: Path, idempotency_key: str) -> bool:
    """H1d: has this idempotency key already been ledgered? Scanned from
    the ledger itself — the truth — never a mutable in-profile flag."""
    try:
        with _ledger_path(data_dir).open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    ev = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if ev.get("idempotency_key") == idempotency_key:
                    return True
    except OSError:
        return False
    return False


def grant_credits(data_dir: Path, user_id: str, n: int, reason: str, *,
                  idempotency_key: str | None = None) -> dict:
    """Grant (or spend, n<0) credits, clamped to MAX_CREDITS (H1d — a bug
    or abuse loop can never mint an unbounded balance). If
    ``idempotency_key`` is given and already appears in the ledger, this
    is a no-op — a retried Discord interaction can never double-grant
    (Stripe's own idempotency-key pattern, already used elsewhere in this
    project's Stripe integration)."""
    if idempotency_key and _ledger_has_key(data_dir, idempotency_key):
        return ensure_profile(data_dir, user_id)
    rec = ensure_profile(data_dir, user_id)
    before = int(rec.get("credits", 0))
    after = min(MAX_CREDITS, max(0, before + int(n)))
    rec["credits"] = after
    _write(data_dir, rec)
    event = {"kind": "credit", "user": rec["id"],
            "delta": after - before, "reason": reason}
    if idempotency_key:
        event["idempotency_key"] = idempotency_key
    _append_ledger(data_dir, event)
    return rec


def try_spend_credit(data_dir: Path, user_id: str, n: int = 1) -> bool:
    """Spend n credits if available → True (used to buy a bonus answer past
    the cooldown). Never goes negative; safe to call on the chat hot path."""
    try:
        rec = _load(data_dir, user_id)
        if not rec or int(rec.get("credits", 0)) < n:
            return False
        rec["credits"] = int(rec["credits"]) - n
        _write(data_dir, rec)
        _append_ledger(data_dir, {"kind": "credit", "user": rec["id"],
                                  "delta": -n, "reason": "bonus-ask"})
        return True
    except Exception:  # noqa: BLE001
        return False


def credits_of(data_dir: Path, user_id: str) -> int:
    rec = _load(data_dir, user_id)
    return int(rec.get("credits", 0)) if rec else 0


def _hold_referral(data_dir: Path, referrer_id: str, newbie_id: str,
                   hold_reason: str) -> None:
    """H1a: a referral failed the sybil policy — HELD, never silently
    denied. Ledgered distinctly (never counted as a normal referral) and
    opened as a visible diagnosis.py case (type 'ambiguity' — exactly
    what this is: legitimate or farm, a human call) so it surfaces in
    `sov diagnosis` instead of sitting invisibly in a ledger file."""
    _append_ledger(data_dir, {"kind": "referral-held", "referrer": referrer_id,
                              "referee": newbie_id, "hold_reason": hold_reason})
    try:
        from sovereign_agent.diagnosis import ConflictCatalog

        ConflictCatalog(Path(data_dir) / "diagnoses").open_conflict(
            type="ambiguity", actor="aria", severity="low",
            trigger_event=f"referral held for review ({hold_reason}): "
                          f"referrer={referrer_id} referee={newbie_id}",
            impacted=[referrer_id, newbie_id],
        )
    except Exception:  # noqa: BLE001
        _LOG.error("referral held but diagnosis catalog unavailable: "
                  "referrer=%s referee=%s reason=%s",
                  referrer_id, newbie_id, hold_reason)


def redeem(data_dir: Path, new_user_id: str, code: str, *,
           now: float | None = None,
           sybil_policy: SybilPolicy | None = None) -> dict:
    """A new member arrives with a referral code. Rewards BOTH sides with
    usage credits — exactly once per new member, never a self-referral.
    H1a: a referral failing the sybil policy (account too new, or the
    referrer over their velocity window) is HELD, not denied — no credits
    move, nothing is silently dropped, and it's visible for review.
    Returns {ok, reason, referrer_id?}."""
    now = time.time() if now is None else now
    policy = sybil_policy or DEFAULT_SYBIL_POLICY
    newbie = ensure_profile(data_dir, new_user_id, now=now)
    if newbie.get("referred_by"):
        return {"ok": False, "reason": "already-referred"}
    referrer_id = resolve_code(data_dir, code)
    if not referrer_id:
        return {"ok": False, "reason": "unknown-code"}
    if referrer_id == newbie["id"]:
        return {"ok": False, "reason": "self-referral"}
    age = account_age_days(new_user_id, now=now)
    if age < policy.min_account_age_days:
        _hold_referral(data_dir, referrer_id, newbie["id"],
                       f"account age {age:.1f}d < "
                       f"{policy.min_account_age_days}d minimum")
        return {"ok": False, "reason": "held-for-review",
                "referrer_id": referrer_id}
    recent = _recent_referral_count(data_dir, referrer_id,
                                    window_hours=policy.window_hours, now=now)
    if recent >= policy.max_referrals_per_window:
        _hold_referral(data_dir, referrer_id, newbie["id"],
                       f"referrer velocity {recent}/{policy.window_hours}h "
                       f">= cap {policy.max_referrals_per_window}")
        return {"ok": False, "reason": "held-for-review",
                "referrer_id": referrer_id}
    referrer = ensure_profile(data_dir, referrer_id, now=now)
    # link both directions
    newbie["referred_by"] = referrer_id
    # affiliate-commissions-d: WHEN the referral happened, so a later
    # purchase can be checked against MARKETER_MONTHS -- older profiles
    # (created before this field existed) read as None, treated as
    # "outside the window" by the attribution bridge, never as "forever".
    newbie["referred_at"] = now
    _write(data_dir, newbie)
    if newbie["id"] not in referrer["referred"]:
        referrer["referred"].append(newbie["id"])
        _write(data_dir, referrer)
    # reward both (credits, idempotent per referee — H1d) + audit
    grant_credits(data_dir, referrer_id, CREDIT_PER_REFERRAL,
                  f"referred {newbie['id']}",
                  idempotency_key=f"referral-reward:{referrer_id}:{newbie['id']}")
    grant_credits(data_dir, new_user_id, CREDIT_PER_REFERRAL,
                  f"joined via {referrer['code']}",
                  idempotency_key=f"referral-joined:{newbie['id']}")
    _append_ledger(data_dir, {"kind": "referral", "referrer": referrer_id,
                              "referee": newbie["id"], "code": referrer["code"]})
    return {"ok": True, "reason": "ok", "referrer_id": referrer_id}


def set_marketer(data_dir: Path, user_id: str, on: bool = True) -> dict:
    rec = ensure_profile(data_dir, user_id)
    rec["role"] = ROLE_MARKETER if on else ROLE_MEMBER
    _write(data_dir, rec)
    return rec


def record_earning(data_dir: Path, user_id: str, cents: int,
                   source: str) -> dict:
    """Attributed marketer earning (called by the reconciler, later). Adds to
    the append-only ledger AND the pending balance — the payout engine reads
    this; it NEVER pays here."""
    rec = ensure_profile(data_dir, user_id)
    rec["earned_cents"] = int(rec.get("earned_cents", 0)) + int(cents)
    rec["pending_cents"] = int(rec.get("pending_cents", 0)) + int(cents)
    _write(data_dir, rec)
    _append_ledger(data_dir, {"kind": "earning", "user": rec["id"],
                              "cents": int(cents), "source": source})
    return rec


def mark_paid(data_dir: Path, user_id: str, cents: int, *, transfer_id: str) -> dict:
    """payouts-d (Kevin, 2026-07-25): the OTHER half of record_earning — a
    real Stripe Transfer just moved money, so pending → paid. Idempotent
    by `transfer_id` (Stripe's own idempotency-key pattern, same
    `_ledger_has_key` mechanism `grant_credits` already uses) — re-running
    a payout pass can never move the same transfer's money twice, even if
    `payouts.py`'s own ledger check were ever bypassed."""
    key = f"payout:{transfer_id}"
    if _ledger_has_key(data_dir, key):
        return ensure_profile(data_dir, user_id)
    rec = ensure_profile(data_dir, user_id)
    cents = int(cents)
    rec["pending_cents"] = max(0, int(rec.get("pending_cents", 0)) - cents)
    rec["paid_cents"] = int(rec.get("paid_cents", 0)) + cents
    _write(data_dir, rec)
    _append_ledger(data_dir, {"kind": "paid", "user": rec["id"], "cents": cents,
                              "transfer_id": transfer_id, "idempotency_key": key})
    return rec


def list_profiles(data_dir: Path) -> list[dict]:
    out: list[dict] = []
    try:
        for p in _dir(data_dir).glob("*.json"):
            if p.name == "codes.json":
                continue
            try:
                out.append(json.loads(p.read_text("utf-8")))
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return []
    out.sort(key=lambda r: (-len(r.get("referred", [])),
                            -int(r.get("credits", 0))))
    return out


# ── H1b: ledger reconciliation ──────────────────────────────────────────────
def verify_ledger_consistency(data_dir: Path) -> dict:
    """Replay `ledger.ndjson` (the claimed truth) and cross-check it
    against every profile's DERIVED `credits`/`earned_cents` — the
    event-sourcing reconciliation pattern (Kleppmann, *Designing Data-
    Intensive Applications*, ch. 11: a materialized view must be
    rebuildable from its log and checked against it, never just trusted).
    Returns {"consistent": bool, "checked": N, "drift": [...]} — drift
    entries never mutate anything; a human decides what to do with them.
    A corrupt/partial trailing ledger line is skipped, never fatal."""
    # Chronological replay, applying the SAME transition grant_credits uses
    # live (clamp to [0, MAX_CREDITS] at every step, not just the final
    # sum) — the append-only file is already in write order, so a single
    # forward pass IS the correct rebuild (Kleppmann's actual pattern:
    # replay events through the live transition function, don't just sum).
    credit_running: dict[str, int] = {}
    earning_sum: dict[str, int] = {}
    try:
        with _ledger_path(data_dir).open("r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    ev = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                kind = ev.get("kind")
                user = ev.get("user")
                if kind == "credit" and user:
                    cur = credit_running.get(user, 0)
                    credit_running[user] = max(
                        0, min(MAX_CREDITS, cur + int(ev.get("delta", 0))))
                elif kind == "earning" and user:
                    earning_sum[user] = earning_sum.get(user, 0) + int(
                        ev.get("cents", 0))
    except OSError:
        return {"consistent": True, "checked": 0, "drift": [],
                "note": "no ledger file yet"}
    drift: list[dict] = []
    for rec in list_profiles(data_dir):
        uid = rec.get("id", "")
        expect_credits = credit_running.get(uid, 0)
        actual_credits = int(rec.get("credits", 0))
        if expect_credits != actual_credits:
            drift.append({"user": uid, "field": "credits",
                         "ledger_sum": expect_credits,
                         "profile_value": actual_credits,
                         "drift": actual_credits - expect_credits})
        expect_earned = earning_sum.get(uid, 0)
        actual_earned = int(rec.get("earned_cents", 0))
        if expect_earned != actual_earned:
            drift.append({"user": uid, "field": "earned_cents",
                         "ledger_sum": expect_earned,
                         "profile_value": actual_earned,
                         "drift": actual_earned - expect_earned})
    return {"consistent": not drift, "checked": len(credit_running) +
           len(earning_sum), "drift": drift}


# ── composers (Discord surfaces) ─────────────────────────────────────────────
def _usd(cents: int) -> str:
    return f"${int(cents)/100:,.2f}"


def compose_refer(data_dir: Path, user_id: str, *,
                  invite: str = "https://discord.gg/5xm44GRfmG") -> str:
    rec = ensure_profile(data_dir, user_id)
    n = len(rec["referred"])
    r = rank_for(n)
    prog = (f"→ **{r['to_next']}** more to **{r['next_title']}** "
            f"`{_bar(n, r['next_at'])}`" if r["next_title"]
            else "you've maxed the ladder — a true Founder. 👑")
    return ("🤝 **Grow the circle — your code:** `" + rec["code"] + "`\n"
            f"Rank: **{r['title']}**  ·  {prog}\n\n"
            "Share your code. When a friend joins and uses it, **you both "
            f"earn {CREDIT_PER_REFERRAL} ✨ credits** — each credit = one extra "
            "moment with Aria past her cooldown. Every share grows a kinder, "
            "warmer community. 💛\n\n"
            f"**Invite:** {invite}\n"
            f"**They redeem with:** `/refer use {rec['code']}`\n\n"
            f"So far: **{n}** referred · **{rec['credits']} ✨** credits. "
            "Full card: `/earnings` · see the champions: `/leaderboard`.")


def compose_earnings(data_dir: Path, user_id: str) -> str:
    rec = ensure_profile(data_dir, user_id)
    n = len(rec["referred"])
    r = rank_for(n)
    lines = ["📊 **Your account** (private to you)",
             f"• Rank: **{r['title']}**",
             f"• Friends brought in: **{n}**"]
    if r["next_title"]:
        lines.append(f"   `{_bar(n, r['next_at'])}` {r['to_next']} to "
                     f"**{r['next_title']}**")
    lines.append(f"• Referral code: `{rec['code']}`")
    lines.append(f"• ✨ Usage credits: **{rec['credits']}** "
                 "(each = one bonus question to Aria)")
    if rec.get("role") == ROLE_MARKETER or rec.get("earned_cents"):
        lines += [
            "",
            "💵 **Marketer earnings** — from Stripe truth, verified before a "
            "cent is ever paid (never a false 'paid'):",
            f"• Earned to date: **{_usd(rec.get('earned_cents', 0))}**",
            f"• Paid (confirmed): **{_usd(rec.get('paid_cents', 0))}**",
            f"• Pending: **{_usd(rec.get('pending_cents', 0))}**"]
    lines += ["", "Climb higher by sharing your code — `/refer`. 💛"]
    return "\n".join(lines)


def compose_leaderboard(data_dir: Path, *, top: int = 10) -> str:
    """A friendly, kind leaderboard — community champions, not a grind."""
    profs = [p for p in list_profiles(data_dir) if p.get("referred")]
    if not profs:
        lines = ["🏆 **Community Champions**", "",
                 "The board's wide open — be the first to grow the circle! "
                 "Grab your code with `/refer`. 💛"]
        return "\n".join(lines)
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 **Community Champions** — thank you for growing a kind, "
             "warm home. 💛", ""]
    for i, p in enumerate(profs[:top]):
        n = len(p["referred"])
        mark = medals[i] if i < 3 else f"`#{i+1}`"
        title = rank_for(n)["title"]
        lines.append(f"{mark} **{n}** referred · {title}")
    lines += ["", "Your spot's waiting — `/refer` to climb. 🌱"]
    return "\n".join(lines)


def publish_affiliate_section(data_dir: Path, *, live: bool = False,
                              webhook_env: str = "DISCORD_AFFILIATE_WEBHOOK_URL",
                              fallback_env: str = "DISCORD_WEBHOOK_URL"):
    """affiliate-section-d (Kevin, 2026-07-25): "add an affiliates section
    in the discord." A dedicated channel, same webhook-publish pattern as
    `shop.publish_storefront` — the program pitch (how to get a code, what
    credits/marketer status mean) plus the live leaderboard, so the
    referral program has a real home instead of only surfacing through
    slash commands someone has to already know to run. Dry-run unless
    `live` and a webhook resolves."""
    import os
    from sovereign_agent.discord_runtime.delivery import WebhookDelivery

    pitch = (
        "💛 **Aria's Referral Program**\n\n"
        "Bring friends in, everyone wins: `/refer` gets you a code — "
        "sharing it earns YOU and your friend usage credits the moment "
        "they redeem it. Grow it further and become a **marketer**: earn "
        "25% of what your referrals spend for their first 6 months, paid "
        "out automatically once it's real, verified income — never a "
        "moment before.\n\n"
        "`/refer` — your code · `/earnings` — your account · "
        "`/leaderboard` — community champions"
    )
    env = webhook_env if (os.environ.get(webhook_env) or "").strip() else fallback_env
    delivery = WebhookDelivery(env, live=live)
    result = delivery.send(pitch, username="Aria's Referral Program")
    if live and not result.sent:
        return result
    board = compose_leaderboard(data_dir)
    return delivery.send(board, username="Aria's Referral Program")


__all__ = [
    "CREDIT_PER_REFERRAL", "MARKETER_PCT", "MARKETER_MONTHS", "MAX_CREDITS",
    "DISCORD_EPOCH_MS", "ROLE_MEMBER", "ROLE_MARKETER", "RANKS", "rank_for",
    "ref_code_for", "account_age_days", "SybilPolicy", "DEFAULT_SYBIL_POLICY",
    "ensure_profile", "resolve_code", "grant_credits", "try_spend_credit",
    "credits_of", "redeem", "set_marketer", "record_earning", "mark_paid",
    "list_profiles", "verify_ledger_consistency", "compose_refer",
    "compose_earnings", "compose_leaderboard", "publish_affiliate_section",
]
