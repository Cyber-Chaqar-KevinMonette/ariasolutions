"""mead_profiles.py — 🍯🎯 the world-class mixologist: taste profiles.

Kevin's ask (2026-07-17): "she remembers every member's favorite recipes
and flavors, builds a taste profile over time, and always suggests the
best recipes per member — or guesses a great one, or stems from a
generalized idea, or makes several suggestions. An advanced suggestion
system."

Each member's palate is a durable record (keyed by stable Discord ID,
like the client DB): flavors they LIKE / DISLIKE, per-recipe RATINGS
(1-5, which sharpen the profile over time), favorites, and free notes.
The suggester scores every recipe against the palate and explains WHY —
and when there's no profile yet, it either takes a one-off idea
("something fruity and strong") or offers a diverse tasting flight.

Pure + tested; no Discord imports. Reuses mead_recipes.RECIPES/FLAVORS.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from sovereign_agent.mead_recipes import FLAVORS, RECIPES, get_recipe


def _dir(data_dir: Path) -> Path:
    return Path(data_dir) / "community" / "mead_profiles"


def _path(data_dir: Path, user_id: str) -> Path:
    uid = re.sub(r"[^0-9]", "", str(user_id)) or "unknown"
    return _dir(data_dir) / f"{uid}.json"


def _blank(user_id: str) -> dict:
    return {"id": str(user_id), "likes": [], "dislikes": [], "ratings": {},
            "notes": "", "updated_ts": time.time()}


def load_profile(data_dir: Path, user_id: str) -> dict:
    try:
        d = json.loads(_path(data_dir, user_id).read_text(encoding="utf-8"))
        if isinstance(d, dict):
            return {**_blank(user_id), **d}
    except Exception:  # noqa: BLE001
        pass
    return _blank(user_id)


def _save(data_dir: Path, prof: dict) -> None:
    prof["updated_ts"] = time.time()
    p = _path(data_dir, prof["id"])
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(prof, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception:  # noqa: BLE001
        pass


def _clean_flavors(flavors) -> list[str]:
    seen, out = set(), []
    for f in flavors or []:
        f = str(f).strip().lower()
        if f in FLAVORS and f not in seen:
            seen.add(f)
            out.append(f)
    return out


def set_taste(data_dir: Path, user_id: str, *, likes=None,
              dislikes=None) -> dict:
    """Set/merge a member's liked + disliked flavors (the palate)."""
    prof = load_profile(data_dir, user_id)
    if likes is not None:
        prof["likes"] = _clean_flavors(likes)
    if dislikes is not None:
        prof["dislikes"] = _clean_flavors(dislikes)
    # a flavor can't be both — likes win
    prof["dislikes"] = [f for f in prof["dislikes"] if f not in prof["likes"]]
    _save(data_dir, prof)
    return prof


def rate_recipe(data_dir: Path, user_id: str, style: str, stars: int) -> dict:
    """Rate a recipe 1-5 — this is how the palate SHARPENS over time. A
    high rating pulls its flavors toward 'likes'; a low one toward
    'dislikes' (gently, so one rating never dominates)."""
    r = get_recipe(style)
    prof = load_profile(data_dir, user_id)
    if r is None:
        return prof
    stars = max(1, min(int(stars), 5))
    prof["ratings"][r.slug] = stars
    # learn: 4-5 nudges flavors into likes; 1-2 into dislikes
    if stars >= 4:
        for f in r.flavors:
            if f not in prof["likes"]:
                prof["likes"].append(f)
        prof["dislikes"] = [f for f in prof["dislikes"]
                            if f not in r.flavors]
    elif stars <= 2:
        for f in r.flavors:
            if f not in prof["likes"] and f not in prof["dislikes"]:
                prof["dislikes"].append(f)
    _save(data_dir, prof)
    return prof


def set_note(data_dir: Path, user_id: str, note: str) -> dict:
    prof = load_profile(data_dir, user_id)
    prof["notes"] = str(note or "")[:400]
    _save(data_dir, prof)
    return prof


# ── the mixologist: score + suggest ─────────────────────────────────────────
def parse_idea(text: str) -> list[str]:
    """Turn a free idea ('something fruity and strong, not too sweet') into
    flavor tags. Simple + honest — only tags actually in the vocabulary."""
    t = (text or "").lower()
    hits = [f for f in FLAVORS if f in t]
    # a couple of friendly synonyms
    syn = {"light": "session", "boozy": "strong", "high abv": "strong",
           "berry": "fruity", "fruit": "fruity", "spice": "spiced",
           "honey-forward": "traditional", "not sweet": "dry"}
    for word, tag in syn.items():
        if word in t and tag not in hits:
            hits.append(tag)
    return hits


def score_recipe(recipe, likes, dislikes, ratings) -> float:
    fl = set(recipe.flavors)
    s = 2.0 * len(fl & set(likes)) - 3.0 * len(fl & set(dislikes))
    if recipe.slug in (ratings or {}):
        s += (int(ratings[recipe.slug]) - 3)      # 5→+2, 1→−2
    return s


def suggest(data_dir: Path, user_id: str = "", *, idea: str = "",
            n: int = 3) -> list[dict]:
    """Ranked suggestions with a REASON each. Priority of signal:
    an explicit idea > the member's saved palate > a diverse flight."""
    likes: list[str] = []
    dislikes: list[str] = []
    ratings: dict = {}
    source = "flight"
    if idea:
        likes = parse_idea(idea)
        source = "your idea"
    elif user_id:
        prof = load_profile(data_dir, user_id)
        likes, dislikes, ratings = prof["likes"], prof["dislikes"], prof["ratings"]
        if likes or dislikes or ratings:
            source = "your taste profile"
    scored = sorted(
        RECIPES,
        key=lambda r: (score_recipe(r, likes, dislikes, ratings),
                       -len(r.flavors)),
        reverse=True)
    if source == "flight":            # no signal → a spread across styles
        scored = _diverse_flight()
    out = []
    for r in scored[:max(1, n)]:
        matched = sorted(set(r.flavors) & set(likes))
        if matched:
            why = f"matches your {', '.join(matched)}"
        elif source == "flight":
            why = f"a great {r.difficulty} {'/'.join(r.flavors[:2])} start"
        else:
            why = f"{r.difficulty} · {', '.join(r.flavors[:3])}"
        out.append({"slug": r.slug, "name": r.name, "abv": r.abv,
                    "why": why, "source": source})
    return out


def _diverse_flight() -> list:
    """One recipe per broad style, for a first-timer with no palate yet."""
    want = ("session", "sweet", "dry", "fruity")
    picked, used = [], set()
    for tag in want:
        for r in RECIPES:
            if tag in r.flavors and r.slug not in used:
                picked.append(r)
                used.add(r.slug)
                break
    for r in RECIPES:                 # top up if short
        if r.slug not in used:
            picked.append(r)
            used.add(r.slug)
    return picked


def render_suggestions(data_dir: Path, user_id: str = "", *, idea: str = "",
                       n: int = 3) -> str:
    sugg = suggest(data_dir, user_id, idea=idea, n=n)
    src = sugg[0]["source"] if sugg else "flight"
    head = {"your idea": "🍯 Stemming from your idea",
            "your taste profile": "🍯 Tuned to your taste profile",
            "flight": "🍯 A tasting flight to find your palate"}.get(src, "🍯")
    lines = [f"{head} — top {len(sugg)}:", ""]
    for s in sugg:
        lines.append(f"• **{s['name']}** ({s['abv']}) — {s['why']}")
        lines.append(f"    → full recipe: /mead-recipe {s['slug']}")
    lines.append("")
    lines.append("Rate one you try with /mead-rate — the more you rate, the "
                 "sharper I get for you. 🍯")
    return "\n".join(lines)


def compose_palate(data_dir: Path, user_id: str) -> str:
    """Her read of a member's palate — the taste profile at a glance."""
    p = load_profile(data_dir, user_id)
    if not (p["likes"] or p["dislikes"] or p["ratings"]):
        return ("🍯 I don't know your palate yet! Set it with /mead-taste, "
                "or just try /mead-suggest and rate what you like.")
    lines = ["🍯 Your mead palate:"]
    if p["likes"]:
        lines.append("  loves: " + ", ".join(p["likes"]))
    if p["dislikes"]:
        lines.append("  avoids: " + ", ".join(p["dislikes"]))
    if p["ratings"]:
        rated = ", ".join(f"{k} {v}★" for k, v in p["ratings"].items())
        lines.append("  rated: " + rated)
    if p["notes"]:
        lines.append("  notes: " + p["notes"])
    return "\n".join(lines)


__all__ = ["load_profile", "set_taste", "rate_recipe", "set_note",
           "parse_idea", "score_recipe", "suggest", "render_suggestions",
           "compose_palate"]
