"""runtime — run a defined bot project, safely, with a full audit trail.

`BotRuntime.poll_once(now)`:
  1. For each due source (RateGate honors each source's allowed interval),
     fetch items via the pluggable Fetcher (default: reaches nothing).
  2. Filter out already-seen items (durable dedup per project).
  3. Turn new items into Alerts and deliver them (default: dry-run, sends
     nothing), throttled by the RateGate's per-minute send ceiling.
  4. Append everything to a durable run log — what was polled, what was
     new, what was (or would be) sent — the transparency trail.

Assembled safe: `build_runtime(project, data_dir)` defaults to a NullFetcher
+ DryRunDelivery, so a runtime does nothing outward until explicitly armed
with `live=True` and a resolvable delivery target.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from typing import Callable

from sovereign_agent.bot_projects import BotProject, slugify

from .breaker import CircuitBreaker
from .contracts import RateContract, RateGate
from .delivery import Delivery, DeliveryResult, DryRunDelivery, build_delivery
from .queue import JobQueue
from .sources import Fetcher, NullFetcher, Source, list_sources

__all__ = ["Alert", "CycleReport", "DrainReport", "BotRuntime", "build_runtime"]


@dataclass(frozen=True)
class Alert:
    source: str
    item_id: str
    content: str            # the delivered, formatted message
    title: str = ""         # scout-d: the RAW item title (what read-layers show)
    url: str = ""           # scout-d: the click-through link
    # panel-d (Kevin, 2026-07-27): an optional rich embed riding beside
    # `content` — additive; every tracker that never sets `item.embed`
    # behaves exactly as before.
    embed: dict | None = None


@dataclass
class CycleReport:
    polled: list[str] = field(default_factory=list)
    skipped_not_due: list[str] = field(default_factory=list)
    new_alerts: list[Alert] = field(default_factory=list)
    deliveries: list[DeliveryResult] = field(default_factory=list)
    queued: int = 0
    throttled: int = 0
    filtered: int = 0          # items suppressed by include/exclude patterns
    # intent -> count of posts suppressed by the post-intent gate (F1):
    # showcase/selling/buying/expired — observable, never silently dropped
    intent_filtered: dict = field(default_factory=dict)
    # actionability-d (Kevin, 2026-07-27): "reddit is a very noisy place
    # that doesn't give direct purchase links or locations" — posts with
    # neither a real link nor a location, suppressed, counted honestly.
    no_signal_filtered: int = 0
    # pre-foreclosure-d: county listings whose sale date already passed
    expired_filtered: int = 0
    live: bool = False

    def summary(self) -> str:
        sent = sum(1 for d in self.deliveries if d.sent)
        dry = sum(1 for d in self.deliveries if d.dry_run)
        mode = "LIVE" if self.live else "dry-run"
        base = (f"[{mode}] polled {len(self.polled)}, "
                f"{len(self.new_alerts)} new, {sent} sent, {dry} dry-run")
        if self.queued:
            base += f", {self.queued} queued"
        if self.throttled:
            base += f", {self.throttled} throttled"
        if self.filtered:
            base += f", {self.filtered} filtered"
        if self.intent_filtered:
            noise = " ".join(f"{k}:{v}" for k, v in
                             sorted(self.intent_filtered.items()))
            base += f" (noise gate: {noise})"
        if self.no_signal_filtered:
            base += f", {self.no_signal_filtered} no-link/no-location"
        if self.expired_filtered:
            base += f", {self.expired_filtered} expired (sale date passed)"
        return base


@dataclass
class DrainReport:
    sent: int = 0
    dry_run: int = 0
    retried: int = 0
    dead_lettered: int = 0
    circuit_open: bool = False
    rate_capped: bool = False

    def summary(self) -> str:
        parts = [f"{self.sent} sent", f"{self.dry_run} dry-run"]
        if self.retried:
            parts.append(f"{self.retried} retry")
        if self.dead_lettered:
            parts.append(f"{self.dead_lettered} dead-letter")
        if self.circuit_open:
            parts.append("circuit OPEN")
        if self.rate_capped:
            parts.append("rate-capped")
        return "drain: " + ", ".join(parts)


class BotRuntime:
    def __init__(self, project: BotProject, sources: list[Source], *,
                 contract: RateContract | None = None,
                 fetcher: Fetcher | None = None,
                 fetcher_factory: Callable[[Source], Fetcher] | None = None,
                 delivery: Delivery | None = None,
                 data_dir: Path | None = None,
                 live: bool = False,
                 queue: JobQueue | None = None,
                 delivery_breaker: CircuitBreaker | None = None) -> None:
        self.project = project
        self.sources = sources
        self.contract = contract or _contract_for(sources)
        # enforce every source's allowed rate against the contract, structurally
        for s in sources:
            self.contract.validate_for_source(s.allowed_min_interval_s)
        self.gate = RateGate(self.contract)
        self.fetcher: Fetcher = fetcher or NullFetcher()
        self._fetcher_factory = fetcher_factory   # per-source fetcher (overrides fetcher)
        self.delivery: Delivery = delivery or DryRunDelivery()
        self.live = live
        self._data_dir = data_dir
        self.queue = queue                        # if set, alerts are queued, not sent inline
        self.breaker = delivery_breaker or CircuitBreaker()
        self._seen: set[str] = self._load_seen()

    def _fetcher_for(self, source: Source) -> Fetcher:
        if self._fetcher_factory is not None:
            return self._fetcher_factory(source)
        return self.fetcher

    # ── dedup persistence ──
    def _proj_dir(self) -> Path | None:
        if self._data_dir is None:
            return None
        from sovereign_agent.bot_projects import projects_dir
        d = projects_dir(self._data_dir) / slugify(self.project.project_name)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _seen_path(self) -> Path | None:
        d = self._proj_dir()
        return None if d is None else d / "seen.json"

    def _load_seen(self) -> set[str]:
        path = self._seen_path()
        if path is None or not path.is_file():
            return set()
        try:
            return set(json.loads(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            return set()

    def _save_seen(self) -> None:
        path = self._seen_path()
        if path is None:
            return
        try:
            tmp = path.with_suffix(".json.tmp")
            # keep the tail bounded so it can't grow without limit
            tmp.write_text(json.dumps(sorted(self._seen)[-5000:]), encoding="utf-8")
            with open(tmp, "r+", encoding="utf-8") as fh:
                fh.flush()
                os.fsync(fh.fileno())
            tmp.replace(path)
        except Exception:  # noqa: BLE001
            pass

    def _audit(self, report: CycleReport, now: float) -> None:
        d = self._proj_dir()
        if d is None:
            return
        try:
            rec = {
                "ts": now,
                "mode": "live" if self.live else "dry-run",
                "summary": report.summary(),
                "polled": report.polled,
                "filtered": report.filtered,
                # scout-d: the RAW title rides along (capped) so read-layers
                # — the Scout Panel, Discord Watch — SHOW clean finds, not
                # the re-formatted alert body
                "new": [{"source": a.source, "id": a.item_id,
                         "text": (a.title or a.content or "")[:300],
                         "url": a.url}
                        for a in report.new_alerts],
                "deliveries": [{"sent": r.sent, "dry_run": r.dry_run,
                                "detail": r.detail} for r in report.deliveries],
            }
            with open(d / "runs.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001
            pass

    # ── the loop ──
    def poll_once(self, now: float | None = None) -> CycleReport:
        now = time.time() if now is None else now
        report = CycleReport(live=self.live)
        for source in self.sources:
            if not source.enabled:
                continue
            if not self.gate.poll_due(source.name, now):
                report.skipped_not_due.append(source.name)
                continue
            self.gate.record_poll(source.name, now)
            report.polled.append(source.name)
            for item in self._fetcher_for(source).fetch(source):
                # external pattern matching (R3): include/exclude filters run
                # BEFORE dedup so an unwanted item never occupies seen-space
                if not source.item_passes(item.text):
                    report.filtered += 1
                    continue
                # post-intent gate (F1, Kevin 2026-07-18): only actionable
                # posts ship — showcase/selling/buying/expired are counted
                # honestly, never posted (unless the source names them in
                # allowed_intents, e.g. a networking lane).
                from sovereign_agent.post_intent import passes_intent
                allowed = (frozenset(source.allowed_intents)
                           if getattr(source, "allowed_intents", None) else None)
                ok, intent = passes_intent(item.text, allowed)
                if not ok:
                    report.filtered += 1
                    report.intent_filtered[intent] = (
                        report.intent_filtered.get(intent, 0) + 1)
                    continue
                # actionability-d (Kevin, 2026-07-27): "reddit is a very
                # noisy place that doesn't give direct purchase links or
                # locations... post with either a purchase link or a
                # location per post." Scoped to discussion-style (rss)
                # sources only — a ChangeFetcher/api item IS the deal
                # itself, already inherently actionable.
                if source.kind == "rss":
                    from sovereign_agent.actionability import is_actionable
                    if not is_actionable(item.text, getattr(item, "url", "") or ""):
                        report.filtered += 1
                        report.no_signal_filtered += 1
                        continue
                # real-estate-gate-d (Kevin, 2026-07-29): a narrow,
                # opt-in hook — only real-estate verticals get deal
                # math + a buy-box gate; every other vertical's poll
                # loop is untouched. Lazy import so a runtime with no
                # real-estate verticals never pays this cost.
                re_strategy_note = ""
                proj_name = getattr(self.project, "project_name", "") or ""
                if proj_name.startswith("scout-realestate-") and self._data_dir is not None:
                    from sovereign_agent.real_estate_gate import process_real_estate_item
                    property_type = proj_name[len("scout-realestate-"):]
                    should_post, _re_analysis, re_strategy_note = process_real_estate_item(
                        text=item.text, url=getattr(item, "url", "") or "",
                        property_type=property_type, data_dir=self._data_dir,
                    )
                    if not should_post:
                        report.filtered += 1
                        continue

                # pre-foreclosure-d (Kevin, 2026-08-03): a county sale
                # date in the PAST is not a lead — that sale already
                # happened. Measured live 2026-08-03: 10 of the 13
                # listings the county pages were serving were for a sale
                # a week gone, so 77% of this feed was noise. The whole
                # no-capital play is reaching an owner who STILL owns
                # the house before their deadline, so the countdown is
                # the signal, not a decoration.
                #
                # Fails OPEN on an unparseable date — an undated listing
                # still reaches a human. Silently swallowing a real lead
                # is the worse failure (see the 23 verticals that read
                # "healthy" while posting nothing).
                if proj_name.startswith("scout-realestate-"):
                    from sovereign_agent.real_estate_sale_urgency import (
                        is_live_lead, label)
                    if not is_live_lead(item.text):
                        report.filtered += 1
                        report.expired_filtered += 1
                        continue
                    _urg = label(item.text)
                    re_strategy_note = (f"{_urg} · {re_strategy_note}"
                                        if re_strategy_note else _urg)
                key = f"{source.name}:{item.id}"
                if key in self._seen:
                    continue
                self._seen.add(key)
                alert_content = _format_alert(self.project, source, item)
                if re_strategy_note:
                    alert_content = f"{alert_content}\n\n💡 {re_strategy_note}"
                alert = Alert(source=source.name, item_id=item.id,
                              content=alert_content,
                              title=item.text,
                              url=getattr(item, "url", "") or "",
                              embed=getattr(item, "embed", None))
                report.new_alerts.append(alert)
                if self.queue is not None:
                    # durable path: enqueue; the drain step delivers with
                    # retry/backoff/dead-letter. Nothing is lost to a hiccup.
                    if self.queue.enqueue(alert.content, key=key, now=now,
                                          embed=alert.embed) is not None:
                        report.queued += 1
                    continue
                # inline path (no queue): deliver now, throttled by the gate
                if not self.gate.send_allowed(now):
                    report.throttled += 1
                    continue
                result = self.delivery.send(
                    alert.content, embeds=[alert.embed] if alert.embed else None)
                report.deliveries.append(result)
                if result.sent or result.dry_run:
                    self.gate.record_send(now)
        self._save_seen()
        self._audit(report, now)
        return report

    def drain(self, now: float | None = None, limit: int = 10) -> DrainReport:
        """Deliver queued alerts with retry/backoff/dead-letter, guarded by
        the rate ceiling and the delivery circuit breaker. Safe to call every
        tick; a no-op when there's no queue."""
        report = DrainReport()
        if self.queue is None:
            return report
        now = time.time() if now is None else now
        self.queue.reclaim(now)
        # circuit breaker: if the target keeps failing, back off entirely
        if not self.breaker.allow(now):
            report.circuit_open = True
            return report
        budget = min(limit, self.gate.remaining_sends(now))
        if budget <= 0:
            report.rate_capped = True
            return report
        for job in self.queue.lease(now, limit=budget):
            job_embed = getattr(job, "embed", None)
            result = self.delivery.send(
                job.content, embeds=[job_embed] if job_embed else None)
            if result.sent or result.dry_run:
                self.queue.complete(job.id)
                self.gate.record_send(now)
                self.breaker.record_success(now)
                if result.sent:
                    report.sent += 1
                else:
                    report.dry_run += 1
            else:  # a real send failure
                outcome = self.queue.fail(job.id, now, result.detail)
                self.breaker.record_failure(now)
                if outcome == "dead":
                    report.dead_lettered += 1
                else:
                    report.retried += 1
                break   # stop this tick; let the breaker/backoff work
        return report

    def run(self, cycles: int = 1, now: float | None = None,
            step_s: float | None = None) -> list[CycleReport]:
        """Run N cycles, advancing a virtual clock by the poll interval each
        time (so tests need no real sleeps). Real scheduling belongs to the
        caller/daemon, not here."""
        now = time.time() if now is None else now
        step = step_s if step_s is not None else self.contract.poll_interval_s
        reports: list[CycleReport] = []
        for _ in range(max(1, cycles)):
            report = self.poll_once(now)
            if self.queue is not None:
                self.drain(now)   # deliver what was just queued
            reports.append(report)
            now += step
        return reports


def _contract_for(sources: list[Source]) -> RateContract:
    """A contract that respects the strictest source's allowed rate."""
    if not sources:
        return RateContract()
    slowest = max(s.allowed_min_interval_s for s in sources)
    return RateContract(poll_interval_s=slowest, max_sends_per_minute=5)


def _item_link(item) -> str:
    """WHERE a find lives: the explicit url (Slickdeals deal link) wins;
    else the id when it's a URL; reddit atom ids (t3_xxx) → comment links."""
    url = str(getattr(item, "url", "") or "")
    if url.startswith("http"):
        return url
    ident = str(getattr(item, "id", "") or "")
    if ident.startswith("http"):
        return ident
    if ident.startswith("t3_"):
        return f"https://www.reddit.com/comments/{ident[3:]}"
    return ""


_PRICE_RE = re.compile(r"\$\s?\d{1,4}(?:[.,]\d{2})?")


def _price_of(text: str) -> str:
    """HOW MUCH, pulled to the front when the title carries a price."""
    m = _PRICE_RE.search(text or "")
    return m.group(0).replace(" ", "") if m else ""


def _format_alert(project: BotProject, source: Source, item) -> str:
    """Kevin's rule: every alert answers WHAT · HOW MUCH · WHERE + how to
    get it (pickup / delivery / both), hours, store locator, item link."""
    bot = project.bot_name or project.project_name
    lines = [f"**{bot}** · {source.name}", f"🔎 {item.text}"]
    price = _price_of(item.text)
    link = _item_link(item)
    tail = " · ".join(x for x in (
        f"💵 {price}" if price else "", f"🔗 {link}" if link else "") if x)
    if tail:
        lines.append(tail)
    try:
        from sovereign_agent.fulfillment import fulfillment_line
        fl = fulfillment_line(item.text)
        if fl:
            lines.append(f"↳ {fl}")
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(lines)


def build_runtime(project: BotProject, data_dir: Path, *, live: bool = False,
                  fetcher: Fetcher | None = None,
                  durable: bool = False,
                  on_live_send=None) -> BotRuntime:
    """Assemble a runtime for a stored project — dry-run unless `live`.

    `fetcher` overrides the per-source real fetchers (tests inject a stub).
    `durable=True` wires the delivery queue (retry/backoff/dead-letter) +
    delivery circuit breaker — the resilient managed path.
    """
    sources = list_sources(data_dir, project.project_name)
    delivery = build_delivery(
        live=live, on_live_send=on_live_send,
        webhook_env=(getattr(project, "webhook_env", "")
                     or "DISCORD_WEBHOOK_URL"))
    factory = None
    if fetcher is None:
        from .bookkeeping import make_outcome_recorder
        from .fetchers import fetcher_for
        recorder = make_outcome_recorder(data_dir, project.project_name)

        def factory(src):                # noqa: ANN001 — Source
            # real fetchers report every fetch outcome → source_health.json,
            # so a dead link becomes visible instead of silently quiet (R5a)
            return fetcher_for(src, on_outcome=recorder)
    queue = None
    if durable:
        queue = JobQueue(_project_queue_dir(data_dir, project.project_name))
    return BotRuntime(project, sources, fetcher=fetcher, fetcher_factory=factory,
                      delivery=delivery, data_dir=data_dir, live=live, queue=queue)


def _project_queue_dir(data_dir: Path, project_name: str) -> Path:
    from sovereign_agent.bot_projects import projects_dir
    return projects_dir(data_dir) / slugify(project_name) / "queue"
