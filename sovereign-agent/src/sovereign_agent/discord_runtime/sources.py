"""sources — what a bot watches, and how fast it's allowed to watch it.

A `Source` is one thing to monitor (an RSS feed, an API/JSON endpoint, a
page). Crucially it carries `allowed_min_interval_s` — the fastest polling
the source itself permits. That number is a ceiling the `RateContract` must
respect (see contracts.py), so respecting each source's allowed rate is
structural, not a promise.

Fetching is pluggable via the `Fetcher` protocol. The DEFAULT is
`NullFetcher` — it reaches no network and returns nothing, so an
unconfigured runtime is inert and safe. A real HTTP fetcher is opt-in and
takes an injectable opener so it's fully testable without a live network.

Storage: one `sources.json` (a list) per project under
`<data>/bot_projects/<slug>/`. Atomic + fsync, corrupt-file-resilient.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from sovereign_agent.bot_projects import slugify

__all__ = [
    "Source",
    "Item",
    "Fetcher",
    "NullFetcher",
    "HttpJsonFetcher",
    "sources_path",
    "add_source",
    "list_sources",
    "remove_source",
    "set_source_enabled",
    "set_sources_enabled_where",
    "set_reddit_sources_enabled",
]

# The floor no source may go below, regardless of what's declared — a hard
# civility limit so a bot can never hammer any endpoint.
MIN_ALLOWED_INTERVAL_S = 15.0


@dataclass
class Source:
    """One monitored source, the rate it permits, and its alert filters.

    Filters (external pattern matching — R3): case-insensitive substring by
    default; prefix a pattern with `re:` for a regex. A bad regex is treated
    as a literal (warn-don't-break). Semantics:
      • include_patterns non-empty → an item must match AT LEAST ONE to alert
        ("only PS5, not accessories").
      • exclude_patterns → an item matching ANY is suppressed (wins over
        include).
    """
    name: str
    url: str = ""
    kind: str = "http"                 # http | api | rss | scrape | manual
    allowed_min_interval_s: float = 60.0
    enabled: bool = True
    include_patterns: list[str] = None  # type: ignore[assignment]
    exclude_patterns: list[str] = None  # type: ignore[assignment]
    # post-intent gate (Kevin, 2026-07-18: "we want AVAILABLE items, not
    # showcase posts"). Empty list = the default policy (available +
    # unknown). Name intents explicitly (e.g. ["available", "unknown",
    # "selling"]) to widen a source — a #marketplace-radar lane would.
    allowed_intents: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.allowed_min_interval_s < MIN_ALLOWED_INTERVAL_S:
            # clamp up, never down — respect the civility floor
            self.allowed_min_interval_s = MIN_ALLOWED_INTERVAL_S
        if self.include_patterns is None:
            self.include_patterns = []
        if self.exclude_patterns is None:
            self.exclude_patterns = []
        if self.allowed_intents is None:
            self.allowed_intents = []

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def item_passes(self, text: str) -> bool:
        """Does an item's text pass this source's include/exclude filters?"""
        t = (text or "").lower()
        if self.exclude_patterns and any(_pat_hit(p, t) for p in self.exclude_patterns):
            return False
        if self.include_patterns:
            return any(_pat_hit(p, t) for p in self.include_patterns)
        return True


def _pat_hit(pattern: str, lowered_text: str) -> bool:
    """One filter pattern against lowered text. `re:`-prefixed = regex
    (case-insensitive, compiled+cached); bad regex degrades to literal."""
    p = (pattern or "").strip()
    if not p:
        return False
    if p.startswith("re:"):
        rx = _compiled(p[3:])
        if rx is not None:
            return bool(rx.search(lowered_text))
        p = p[3:]                      # bad regex → literal fallback
    return p.lower() in lowered_text


def _compiled(expr: str):
    import re as _re
    cached = _REGEX_CACHE.get(expr)
    if cached is not None:
        return cached if cached is not False else None
    try:
        rx = _re.compile(expr, _re.IGNORECASE)
        _REGEX_CACHE[expr] = rx
        return rx
    except _re.error:
        _REGEX_CACHE[expr] = False     # remember it's bad; don't retry
        return None


_REGEX_CACHE: dict[str, Any] = {}


@dataclass(frozen=True)
class Item:
    """One thing fetched from a source. `id` is what dedup keys on; `url`
    is the real click-through when the id isn't itself a URL (scout-d:
    Slickdeals uses a non-URL guid for dedup but carries the deal link).

    panel-d (Kevin, 2026-07-27): `embed`, when set, is a rich Discord
    embed dict (already `clamp_embed()`-safe) delivered ALONGSIDE `text`
    — optional and additive, so every existing fetcher/tracker (which
    never sets it) behaves exactly as before."""
    id: str
    text: str
    url: str = ""
    embed: dict | None = None


class Fetcher(Protocol):
    def fetch(self, source: Source) -> list[Item]:  # pragma: no cover - protocol
        ...


class NullFetcher:
    """The safe default: reaches nothing, returns nothing."""

    def fetch(self, source: Source) -> list[Item]:  # noqa: ARG002
        return []


class HttpJsonFetcher:
    """Opt-in real fetcher for JSON/API sources — official HTTP only.

    `opener` is injectable (defaults to urllib) so this is testable without
    a live network. `extract` maps a decoded JSON body to a list of Items.
    Kept deliberately minimal; richer parsers (RSS, HTML) are extension
    points, not smuggled in here.
    """

    def __init__(self, opener=None, extract=None, timeout: float = 10.0,
                 on_outcome=None) -> None:
        self._opener = opener
        self._extract = extract or _default_extract
        self._timeout = timeout
        self._on_outcome = on_outcome

    def _report(self, source: "Source", ok: bool, detail: str) -> None:
        if self._on_outcome is None:
            return
        try:
            self._on_outcome(source.name, ok, detail)
        except Exception:  # noqa: BLE001
            pass

    def fetch(self, source: Source) -> list[Item]:
        if not source.url:
            self._report(source, False, "no url configured")
            return []
        opener = self._opener
        if opener is None:  # lazy import; only touch the network when truly used
            from urllib.request import urlopen
            opener = urlopen
        try:
            with opener(source.url, timeout=self._timeout) as resp:  # type: ignore[misc]
                raw = resp.read()
            body = json.loads(raw)
        except Exception as exc:  # noqa: BLE001 — a flaky source must never crash the loop
            code = getattr(exc, "code", None)
            self._report(source, False,
                         f"HTTP {code}" if code is not None else type(exc).__name__)
            return []
        try:
            items = list(self._extract(body))
            self._report(source, True, f"{len(items)} item(s)")
            return items
        except Exception:  # noqa: BLE001
            self._report(source, False, "extract failed (unexpected JSON shape)")
            return []


def _default_extract(body: Any) -> list[Item]:
    """Best-effort: a list of dicts → Items keyed on id/title."""
    items: list[Item] = []
    seq = body if isinstance(body, list) else body.get("items", []) if isinstance(body, dict) else []
    for entry in seq:
        if not isinstance(entry, dict):
            continue
        ident = str(entry.get("id") or entry.get("guid") or entry.get("url")
                    or entry.get("title") or "")
        if not ident:
            continue
        text = str(entry.get("title") or entry.get("text") or entry.get("name") or ident)
        items.append(Item(id=ident, text=text))
    return items


# ── store ───────────────────────────────────────────────────────────────
def _project_dir(data_dir: Path, project_name: str) -> Path:
    from sovereign_agent.bot_projects import projects_dir
    d = projects_dir(data_dir) / slugify(project_name)
    d.mkdir(parents=True, exist_ok=True)
    return d


def sources_path(data_dir: Path, project_name: str) -> Path:
    return _project_dir(data_dir, project_name) / "sources.json"


def list_sources(data_dir: Path, project_name: str) -> list[Source]:
    path = sources_path(data_dir, project_name)
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    out: list[Source] = []
    for entry in raw if isinstance(raw, list) else []:
        try:
            known = {f for f in Source(name="x").as_dict()}
            out.append(Source(**{k: v for k, v in entry.items() if k in known}))
        except Exception:  # noqa: BLE001
            continue
    return out


def _write_sources(data_dir: Path, project_name: str, sources: list[Source]) -> Path:
    path = sources_path(data_dir, project_name)
    tmp = path.with_suffix(".json.tmp")
    payload = json.dumps([s.as_dict() for s in sources], indent=2, ensure_ascii=False)
    tmp.write_text(payload, encoding="utf-8")
    with open(tmp, "r+", encoding="utf-8") as fh:
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(path)
    return path


def add_source(data_dir: Path, project_name: str, source: Source) -> Path:
    sources = [s for s in list_sources(data_dir, project_name) if s.name != source.name]
    sources.append(source)
    return _write_sources(data_dir, project_name, sources)


def remove_source(data_dir: Path, project_name: str, source_name: str) -> bool:
    sources = list_sources(data_dir, project_name)
    kept = [s for s in sources if s.name != source_name]
    if len(kept) == len(sources):
        return False
    _write_sources(data_dir, project_name, kept)
    return True


def set_source_enabled(data_dir: Path, project_name: str, source_name: str,
                       enabled: bool) -> bool:
    """source-toggle-d (Kevin, 2026-07-27): "a control panel where I can
    turn sources on and off." `Source.enabled` already existed and was
    already respected by `BotRuntime.poll_once()` (a disabled source is
    skipped every tick) — nothing let an operator flip it. Preserves
    every other field. Returns False if no such source exists."""
    sources = list_sources(data_dir, project_name)
    found = False
    for s in sources:
        if s.name == source_name:
            s.enabled = enabled
            found = True
    if not found:
        return False
    _write_sources(data_dir, project_name, sources)
    return True


def set_sources_enabled_where(data_dir: Path, project_name: str,
                              predicate, enabled: bool) -> int:
    """Bulk toggle every source in one project matching `predicate(source)
    -> bool`. Returns how many actually changed."""
    sources = list_sources(data_dir, project_name)
    changed = 0
    for s in sources:
        if predicate(s) and s.enabled != enabled:
            s.enabled = enabled
            changed += 1
    if changed:
        _write_sources(data_dir, project_name, sources)
    return changed


def set_reddit_sources_enabled(data_dir: Path, enabled: bool, *,
                               project_name: str | None = None) -> dict[str, int]:
    """Kevin: "I want to toggle reddit off." Every reddit.com-hosted
    source, across one project or the whole fleet (`project_name=None`).
    Returns {project_name: count_changed} for projects that had something
    to change — an empty dict means nothing needed to move."""
    from sovereign_agent.bot_projects import list_all as _list_projects
    projects = ([project_name] if project_name else
               [p.project_name for p in _list_projects(data_dir)])
    changed: dict[str, int] = {}
    for proj in projects:
        n = set_sources_enabled_where(
            data_dir, proj, lambda s: "reddit.com" in (s.url or ""), enabled)
        if n:
            changed[proj] = n
    return changed
