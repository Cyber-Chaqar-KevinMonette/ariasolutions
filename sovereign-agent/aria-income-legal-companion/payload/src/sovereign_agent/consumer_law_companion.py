"""consumer_law_companion.py — informational (NOT legal advice) answers
about consumer-protection law, deterministic and keyword-routed like
real_estate_strategy.py rather than free-form LLM generation.

Kevin (2026-08-01): "consumer law companion" — clarified as "informational
Q&A only... clearly labeled as information, not legal advice." Deliberately
NOT an open-ended LLM legal advisor: statute names, summaries, and source
URLs are verified facts baked in here (researched 2026-08-01: CFPB/FTC
plain-language sources, correct statute names/citations), not re-derived by
a model on every question. This matters more here than almost anywhere else
in this codebase — a wrong statute name or a confidently-wrong "your rights
are X" answer is a real harm a stale retail-tracker price never is.

Every answer carries the same disclaimer, modeled on the pattern real
informational (non-lawyer) consumer tools actually use (CFPB/FTC/legal-aid
sites converge on this shape).
"""
from __future__ import annotations

from dataclasses import dataclass


__all__ = ["ConsumerLawAnswer", "answer_consumer_law_question", "DISCLAIMER", "TOPICS"]

DISCLAIMER = (
    "This is general, educational information — not legal advice, and it "
    "doesn't create an attorney-client relationship. Laws vary by state "
    "and change over time. For advice about your specific situation, "
    "consult a licensed attorney or contact a legal aid organization."
)


@dataclass(frozen=True)
class ConsumerLawTopic:
    name: str
    statute: str
    summary: str
    sources: tuple[str, ...]
    keywords: tuple[str, ...]


# Verified 2026-08-01 (CFPB consumerfinance.gov + FTC consumer.ftc.gov) —
# do not add a topic here without a real, checked source URL.
TOPICS: tuple[ConsumerLawTopic, ...] = (
    ConsumerLawTopic(
        name="Debt collection",
        statute="FDCPA — Fair Debt Collection Practices Act (15 U.S.C. §1692 et seq.)",
        summary=("Bans abusive, deceptive, and unfair debt collection practices — no "
                 "calls before 8am or after 9pm, no contact after you send a written "
                 "cease request, must send a written validation notice, no threats "
                 "of action they don't intend to take, no contacting your employer "
                 "about the debt without permission."),
        sources=("https://www.consumerfinance.gov/consumer-tools/debt-collection/",
                 "https://consumer.ftc.gov/articles/debt-collection-faqs"),
        keywords=("debt collect", "collector", "collection call", "garnish",
                  "validation notice", "cease and desist"),
    ),
    ConsumerLawTopic(
        name="Credit reporting",
        statute="FCRA — Fair Credit Reporting Act",
        summary=("Governs the accuracy of your credit report and your right to see "
                 "and dispute it — you can get free reports, dispute errors with the "
                 "bureau AND the furnisher, and they must investigate within 30 days."),
        sources=("https://www.consumerfinance.gov/consumer-tools/credit-reports-and-scores/",),
        keywords=("credit report", "credit score", "credit bureau", "experian",
                  "equifax", "transunion", "dispute my credit"),
    ),
    ConsumerLawTopic(
        name="Loan/credit disclosure",
        statute="TILA — Truth in Lending Act",
        summary=("Requires lenders to clearly disclose loan costs and terms before "
                 "you're bound — APR, finance charges, payment schedule — in a "
                 "standard format so loans are comparable."),
        sources=("https://www.consumerfinance.gov/consumer-tools/",),
        keywords=("apr", "loan disclosure", "finance charge", "truth in lending",
                  "hidden fees on my loan"),
    ),
    ConsumerLawTopic(
        name="Credit card billing disputes",
        statute="FCBA — Fair Credit Billing Act",
        summary=("Gives you the right to dispute billing errors on open-end (credit "
                 "card) accounts — write within 60 days of the statement, and the "
                 "issuer must acknowledge within 30 days and resolve within 90."),
        sources=("https://consumer.ftc.gov/articles/disputing-credit-card-charges",),
        keywords=("billing error", "dispute a charge", "credit card charge",
                  "chargeback", "unauthorized charge"),
    ),
    ConsumerLawTopic(
        name="Credit discrimination",
        statute="ECOA — Equal Credit Opportunity Act",
        summary=("Bans credit discrimination based on race, color, religion, "
                 "national origin, sex, marital status, age, or receiving public "
                 "assistance income — applies to any part of a credit transaction."),
        sources=("https://www.consumerfinance.gov/consumer-tools/",),
        keywords=("credit discrimination", "denied credit because", "equal credit"),
    ),
)

_FALLBACK_SOURCES = (
    "https://www.consumerfinance.gov/consumer-tools/",
    "https://consumer.ftc.gov/",
)


@dataclass(frozen=True)
class ConsumerLawAnswer:
    topic: str
    statute: str
    summary: str
    sources: tuple[str, ...]
    disclaimer: str = DISCLAIMER

    def as_text(self) -> str:
        parts = [f"**{self.topic}** ({self.statute})", self.summary]
        if self.sources:
            parts.append("Sources: " + " | ".join(self.sources))
        parts.append(f"⚖️ {self.disclaimer}")
        return "\n\n".join(parts)


def answer_consumer_law_question(question: str) -> ConsumerLawAnswer:
    """Deterministic keyword match — first topic whose keyword appears in
    the question wins (ordered most-specific-first in TOPICS, mirroring
    real_estate_strategy.py's rule-table discipline). No match still
    returns a real, useful answer (general CFPB/FTC pointers), never a
    bare "I don't know"."""
    lowered = (question or "").lower()
    for topic in TOPICS:
        if any(kw in lowered for kw in topic.keywords):
            return ConsumerLawAnswer(
                topic=topic.name, statute=topic.statute, summary=topic.summary,
                sources=topic.sources,
            )
    return ConsumerLawAnswer(
        topic="General consumer protection",
        statute="CFPB / FTC consumer resources",
        summary=("I don't have a specific matched topic for that, but the CFPB and "
                 "FTC cover debt collection, credit reports, loan disclosures, "
                 "billing disputes, and credit discrimination in plain language — "
                 "worth a look, or try rephrasing with more detail."),
        sources=_FALLBACK_SOURCES,
    )
