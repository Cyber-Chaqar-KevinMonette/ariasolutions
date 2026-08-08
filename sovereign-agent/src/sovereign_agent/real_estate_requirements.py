"""real_estate_requirements.py — Kevin's own buy-box criteria.

Kevin, 2026-07-29: "channel and what my requirements would be" — set
once via plain key=value text in the dedicated #requirements channel,
read back on every real-estate lead to decide what's worth surfacing.
Same atomic-write/fsync JSON pattern as `discord_runtime/sources.py`'s
`sources.json` — one small settings file, not a database.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional


__all__ = [
    "BuyBoxRequirements",
    "requirements_path",
    "load_requirements",
    "save_requirements",
    "apply_command",
    "requirement_passes",
    "summarize",
]


@dataclass
class BuyBoxRequirements:
    zip_codes: list[str] = field(default_factory=list)
    radius_miles: float = 25.0
    property_types: list[str] = field(default_factory=list)  # empty = no filter
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    min_cash_flow_monthly: Optional[float] = None
    min_cap_rate_pct: Optional[float] = None
    min_cash_on_cash_pct: Optional[float] = None
    financing_preference: str = "any"
    notes: str = ""

    def as_dict(self) -> dict:
        return {
            "zip_codes": self.zip_codes,
            "radius_miles": self.radius_miles,
            "property_types": self.property_types,
            "price_min": self.price_min,
            "price_max": self.price_max,
            "min_cash_flow_monthly": self.min_cash_flow_monthly,
            "min_cap_rate_pct": self.min_cap_rate_pct,
            "min_cash_on_cash_pct": self.min_cash_on_cash_pct,
            "financing_preference": self.financing_preference,
            "notes": self.notes,
        }


def requirements_path(data_dir) -> Path:
    return Path(data_dir) / "real_estate" / "requirements.json"


def load_requirements(data_dir) -> BuyBoxRequirements:
    path = requirements_path(data_dir)
    if not path.is_file():
        return BuyBoxRequirements()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return BuyBoxRequirements()
    known = {f for f in BuyBoxRequirements().as_dict()}
    try:
        return BuyBoxRequirements(**{k: v for k, v in raw.items() if k in known})
    except Exception:  # noqa: BLE001
        return BuyBoxRequirements()


def save_requirements(data_dir, requirements: BuyBoxRequirements) -> Path:
    path = requirements_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps(requirements.as_dict(), indent=2, ensure_ascii=False)
    tmp.write_text(payload, encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)
    return path


_FIELD_ALIASES = {
    "zip": "zip_codes", "zips": "zip_codes", "zip_codes": "zip_codes",
    "radius": "radius_miles", "radius_miles": "radius_miles",
    "type": "property_types", "types": "property_types",
    "property_types": "property_types",
    "price_min": "price_min", "min_price": "price_min",
    "price_max": "price_max", "max_price": "price_max",
    "min_cash_flow": "min_cash_flow_monthly", "cash_flow": "min_cash_flow_monthly",
    "min_cap_rate": "min_cap_rate_pct", "cap_rate": "min_cap_rate_pct",
    "min_cash_on_cash": "min_cash_on_cash_pct", "cash_on_cash": "min_cash_on_cash_pct",
    "financing": "financing_preference",
    "notes": "notes",
}
_LIST_FIELDS = {"zip_codes", "property_types"}
_FLOAT_FIELDS = {"radius_miles", "price_min", "price_max", "min_cash_flow_monthly",
                 "min_cap_rate_pct", "min_cash_on_cash_pct"}


def apply_command(existing: BuyBoxRequirements, text: str) -> BuyBoxRequirements:
    """Deterministic key=value parser — the first tier (mirrors this
    repo's two-tier dispatch pattern elsewhere). Unrecognized tokens are
    silently ignored rather than raising, since a chat message may mix
    plain words with key=value pairs; a fuller natural-language fallback
    (the same bounded agent_loop() primitive used elsewhere in this
    codebase) is the second tier for freeform sentences, wired at the
    call site, not in this pure parser."""
    updated = replace(existing)
    for token in (text or "").split():
        if "=" not in token:
            continue
        key, _, value = token.partition("=")
        field_name = _FIELD_ALIASES.get(key.strip().lower())
        value = value.strip()
        if field_name is None or not value:
            continue
        if field_name in _LIST_FIELDS:
            setattr(updated, field_name, [v.strip() for v in value.split(",") if v.strip()])
        elif field_name in _FLOAT_FIELDS:
            try:
                setattr(updated, field_name, float(value))
            except ValueError:
                continue
        else:
            setattr(updated, field_name, value)
    return updated


def requirement_passes(
    *, data_dir, item_location: str = "", price: Optional[float] = None,
    analysis=None, requirements: BuyBoxRequirements, getter=None,
) -> bool:
    """The gate: does this lead clear Kevin's buy-box? `analysis`, if
    given, is a `real_estate_deal_analyzer.DealAnalysis` — its "mid" rent
    scenario is checked against the cash-flow/cap-rate/cash-on-cash
    floors. Location is only checked when zip_codes is actually set
    (optional per Kevin's "easiest and free path" steer — a tracker
    that's never given a zip/radius never filters on it); an item whose
    location can't be resolved never silently passes (`geo.is_nearby`'s
    own honesty rule)."""
    if requirements.zip_codes and requirements.radius_miles:
        from sovereign_agent import geo
        area = {"zips": requirements.zip_codes, "radius_mi": requirements.radius_miles}
        if not geo.is_nearby(data_dir, item_location, area, getter=getter):
            return False

    if price is not None:
        if requirements.price_min is not None and price < requirements.price_min:
            return False
        if requirements.price_max is not None and price > requirements.price_max:
            return False

    if analysis is not None:
        mid = next((s for s in analysis.scenarios if s.scenario.label == "mid"), None)
        if mid is not None:
            if (requirements.min_cash_flow_monthly is not None
                    and mid.monthly_cash_flow < requirements.min_cash_flow_monthly):
                return False
            if (requirements.min_cap_rate_pct is not None
                    and mid.cap_rate_pct < requirements.min_cap_rate_pct):
                return False
            if (requirements.min_cash_on_cash_pct is not None
                    and (mid.cash_on_cash_pct or 0.0) < requirements.min_cash_on_cash_pct):
                return False

    return True


def summarize(requirements: BuyBoxRequirements) -> str:
    """Human-readable confirmation for the #requirements channel reply."""
    parts = [f"📋 Buy-box requirements updated:"]
    if requirements.zip_codes:
        parts.append(f"  zips: {', '.join(requirements.zip_codes)} (±{requirements.radius_miles}mi)")
    if requirements.property_types:
        parts.append(f"  property types: {', '.join(requirements.property_types)}")
    if requirements.price_min is not None or requirements.price_max is not None:
        lo = requirements.price_min if requirements.price_min is not None else "any"
        hi = requirements.price_max if requirements.price_max is not None else "any"
        parts.append(f"  price: {lo} - {hi}")
    if requirements.min_cash_flow_monthly is not None:
        parts.append(f"  min cash flow: ${requirements.min_cash_flow_monthly}/mo")
    if requirements.min_cap_rate_pct is not None:
        parts.append(f"  min cap rate: {requirements.min_cap_rate_pct}%")
    if requirements.min_cash_on_cash_pct is not None:
        parts.append(f"  min cash-on-cash: {requirements.min_cash_on_cash_pct}%")
    parts.append(f"  financing preference: {requirements.financing_preference}")
    if requirements.notes:
        parts.append(f"  notes: {requirements.notes}")
    return "\n".join(parts)
