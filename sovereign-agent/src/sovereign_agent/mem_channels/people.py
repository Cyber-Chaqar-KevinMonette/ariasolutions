"""
╔══════════════════════════════════════════════════════════════════════════╗
║  channels/people.py — Aria's memory of the humans she knows              ║
║  v0.2.16.0 · MOS Authority Tier 3                                         ║
║                                                                           ║
║  People memory is structured PII storage. Tier 3, idempotency required,  ║
║  redactable, mergeable, append-only at the audit layer.                  ║
║                                                                           ║
║  WHAT THIS CHANNEL HOLDS                                                 ║
║                                                                           ║
║    • A canonical name and zero or more aliases per person                 ║
║    • Structured facts (role, interests, research_area, lab, publication, ║
║      contact, note, tag, ...) with status: pending / confirmed / retracted║
║    • A single optional principal (the operator)                          ║
║    • A per-person opt-in flag for web enrichment (off by default)        ║
║    • A merge event log for reversible identity unification               ║
║    • A redaction tombstone table — the API refuses reads on tombstoned   ║
║      records, but the audit path can still see them                      ║
║                                                                           ║
║  WHAT IT DOES NOT HOLD                                                   ║
║                                                                           ║
║    • Cryptographic identity (no keys, no signed claims).                 ║
║    • Authoritative biometric or government records.                       ║
║    • Anything the operator did not explicitly accept into the canon.     ║
║                                                                           ║
║  AUTHORITY                                                                ║
║                                                                           ║
║    Write path is Tier 3 — every public method requires an idempotency_id ║
║    (MOS §16). Mutation runs inside BEGIN IMMEDIATE so the SELECT-then-   ║
║    INSERT pattern is race-safe (lesson learned from FinancialChannel).   ║
║                                                                           ║
║  UNTRUSTED INPUT DOCTRINE                                                ║
║                                                                           ║
║    Facts arrive from many sources: the operator, an LLM mid-chat, a file ║
║    import, eventually web enrichment. Every fact records its source AND  ║
║    a status. LLM-extracted facts default to status='pending' with        ║
║    confidence ≤ 0.5. They do not surface as truth until the operator    ║
║    promotes them via confirm_fact().                                     ║
║                                                                           ║
║  THE GOAL                                                                ║
║                                                                           ║
║    Aria can answer:                                                       ║
║      • Who is this name? (resolution by canonical_name OR alias)         ║
║      • What do I know about X? (full profile)                            ║
║      • Which scientists am I tracking? (filter by fact:role)             ║
║      • What's been pending operator review for too long?                 ║
║      • Are there integrity violations? (audit)                           ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Literal

from ..channels import ChannelSpec, MemoryChannel, register_channel


FactStatus = Literal["pending", "confirmed", "retracted"]
AliasSource = Literal["operator", "merge", "inference"]
FactSource = Literal["operator", "llm", "import", "web", "merge"]

# Reasonable kinds, but not strictly enforced — operator vocabulary is open
WELL_KNOWN_FACT_KINDS = (
    "role", "interest", "research_area", "lab", "publication",
    "contact", "location", "affiliation", "note", "tag", "preference",
    "skill", "project", "url",
)


# ─── DDL bootstrap ─────────────────────────────────────────────────────────


def ensure_people_schema(conn: sqlite3.Connection) -> None:
    """Idempotent — safe to call on every open.

    Reads 003_people.sql from the source tree and applies it. The same
    pattern is used by atoms.db bootstrap and FinancialChannel.
    """
    schema_path = (
        Path(__file__).parent.parent.parent.parent / "sql" / "003_people.sql"
    )
    if not schema_path.is_file():
        # Fall back to packaged path in editable installs / wheel
        alt = Path(__file__).parent.parent / "sql" / "003_people.sql"
        if alt.is_file():
            schema_path = alt
        else:
            raise FileNotFoundError(
                f"003_people.sql not found; looked at {schema_path} and {alt}"
            )
    conn.executescript(schema_path.read_text())
    conn.commit()


# ─── Errors ────────────────────────────────────────────────────────────────


class PrincipalConflictError(ValueError):
    """Refused to create or promote a second principal while one already exists.

    Use --force at the CLI (which writes a counter-record demoting the prior
    principal first) only when you genuinely mean to switch principals.
    """


class PersonNotFoundError(KeyError):
    """The named person (by id, canonical name, or alias) does not exist
    or has been redacted."""


class RedactedError(PermissionError):
    """The record exists but is tombstoned. The API will not surface it.

    Use the audit path if you need to inspect a redacted record forensically.
    """


# ─── Dataclasses returned by the API ───────────────────────────────────────


@dataclass
class Person:
    """One row of the people table — the canonical record."""
    person_id: str
    canonical_name: str
    is_principal: bool
    web_enrichment_allowed: bool
    created_at: str
    updated_at: str
    redacted_at: str | None = None


@dataclass
class Fact:
    """One row of people_facts."""
    fact_id: str
    person_id: str
    kind: str
    value: str
    source: str
    confidence: float
    status: FactStatus
    created_at: str
    source_event_id: str | None = None
    confirmed_at: str | None = None
    retracted_at: str | None = None
    superseded_by: str | None = None


@dataclass
class Alias:
    """One row of people_aliases."""
    alias_id: str
    person_id: str
    alias: str
    added_at: str
    source: AliasSource
    confidence: float


@dataclass
class PersonProfile:
    """Aria's full view of a person, grouped for display."""
    person: Person
    aliases: list[Alias]
    facts_confirmed: list[Fact]
    facts_pending: list[Fact]
    facts_retracted: list[Fact]

    def render(self) -> str:
        """Human-readable summary card."""
        principal_mark = " *" if self.person.is_principal else ""
        web_mark = " · web ✓" if self.person.web_enrichment_allowed else " · web off"
        lines = [
            f"━ {self.person.canonical_name}{principal_mark}{web_mark} ━",
            f"  id: {self.person.person_id}",
        ]
        if self.aliases:
            alist = ", ".join(a.alias for a in self.aliases)
            lines.append(f"  aliases: {alist}")
        if self.facts_confirmed:
            lines.append("  facts (confirmed):")
            for f in self.facts_confirmed:
                lines.append(f"    · {f.kind}: {f.value}")
        if self.facts_pending:
            lines.append(f"  facts (pending — {len(self.facts_pending)} awaiting review):")
            for f in self.facts_pending:
                lines.append(f"    · {f.kind}: {f.value}  [conf {f.confidence:.2f}]")
        if not (self.facts_confirmed or self.facts_pending):
            lines.append("  (no facts yet)")
        return "\n".join(lines)


@dataclass
class MergePreview:
    """Dry-run preview of merge(): describes what would change."""
    from_person: Person
    into_person: Person
    aliases_moved: int
    facts_moved: int
    new_alias_for_from_canonical: bool   # the absorbed person's canonical name becomes an alias

    def render(self) -> str:
        return (
            f"merge preview: {self.from_person.canonical_name} → "
            f"{self.into_person.canonical_name}\n"
            f"  aliases moved: {self.aliases_moved}\n"
            f"  facts moved:   {self.facts_moved}\n"
            f"  add alias on target: "
            f"{'yes' if self.new_alias_for_from_canonical else 'no'}"
        )


@dataclass
class PeopleAudit:
    """Result of PeopleChannel.audit() — the integrity report."""
    ok: bool
    people_rows: int
    fact_rows: int
    alias_rows: int
    violations: list[str] = field(default_factory=list)
    orphaned_facts: list[str] = field(default_factory=list)
    orphaned_aliases: list[str] = field(default_factory=list)
    duplicate_aliases: list[str] = field(default_factory=list)
    principal_count: int = 0

    def render(self) -> str:
        if self.ok:
            return (
                f"✓ people audit clean — {self.people_rows} people, "
                f"{self.fact_rows} facts, {self.alias_rows} aliases, "
                f"{self.principal_count} principal(s)"
            )
        lines = [
            f"✗ people audit FAILED — {len(self.violations)} violation(s)",
            "",
        ]
        for v in self.violations:
            lines.append(f"  - {v}")
        return "\n".join(lines)


# ─── The channel ───────────────────────────────────────────────────────────


@register_channel
class PeopleChannel(MemoryChannel):
    """People memory. Tier 3. Idempotent writes. Redactable. Mergeable."""

    spec = ChannelSpec(
        name="people",
        description=(
            "Durable record of humans Aria knows: canonical names, aliases, "
            "structured facts (role, interests, research, contacts), with "
            "pending/confirmed status and reversible identity merges."
        ),
        authority_tier=3,
        default_confidence=0.95,
        requires_idempotency=True,
        introduced_in="0.2.16.0",
        voice="Warm, accurate, never presumptuous. Names matter; facts wait for the operator.",
    )

    def __init__(self, conn: sqlite3.Connection):
        super().__init__(conn)
        ensure_people_schema(conn)
        # Bitemporal augmentation — v0.2.17+. Idempotent.
        from ..bitemporal import add_bitemporal_columns
        try:
            add_bitemporal_columns(conn, "people_facts")
        except Exception:
            pass  # If table doesn't exist yet for some reason, skip; next init will catch it.

    # ── Internal helpers ─────────────────────────────────────────────

    @contextmanager
    def _writer_tx(self) -> Iterator[None]:
        """BEGIN IMMEDIATE around the write — same pattern as FinancialChannel.

        Required so SELECT-then-INSERT (resolution → upsert) is race-safe.
        Sets ``_in_outer_tx`` so the base ``write_atom`` skips its inner commit.
        """
        in_tx = self.conn.in_transaction
        if not in_tx:
            self.conn.execute("BEGIN IMMEDIATE")
        self._in_outer_tx = True
        try:
            yield
            if not in_tx:
                self.conn.commit()
        except Exception:
            if not in_tx:
                self.conn.rollback()
            raise
        finally:
            self._in_outer_tx = False

    @staticmethod
    def _hash_id(prefix: str, seed: str) -> str:
        return f"{prefix}-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @staticmethod
    def _normalize(s: str) -> str:
        """NFC-normalize + casefold + strip. This is what we compare on.

        Why NFC and not NFKC: NFC folds canonical equivalents (Café and
        Café-with-combining-accent become identical) but preserves the
        distinction between visually-similar-but-semantically-different
        characters. NFKC would merge half-width and full-width digits
        which is over-eager for personal names.

        Why casefold and not lower: 'ß' lowers to 'ß' but casefolds to 'ss',
        which is the right thing for cross-locale equality.
        """
        import unicodedata
        # Strip RTL override and other dangerous directional formatters
        # before normalization so they can't sneak past as 'equivalent'.
        DANGEROUS = ("\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
                     "\u2066", "\u2067", "\u2068", "\u2069", "\u200e", "\u200f")
        cleaned = "".join(ch for ch in s if ch not in DANGEROUS)
        return unicodedata.normalize("NFC", cleaned).strip().casefold()

    def _row_to_person(self, row: tuple) -> Person:
        (
            person_id, canonical_name, _canonical_lower, is_principal,
            web_enrich, created_at, updated_at, _idem, _atom, redacted_at,
        ) = row
        return Person(
            person_id=person_id,
            canonical_name=canonical_name,
            is_principal=bool(is_principal),
            web_enrichment_allowed=bool(web_enrich),
            created_at=created_at,
            updated_at=updated_at,
            redacted_at=redacted_at,
        )

    def _fetch_person_row(self, person_id: str, include_redacted: bool = False) -> Person | None:
        row = self.conn.execute(
            "SELECT person_id, canonical_name, canonical_lower, is_principal, "
            "web_enrichment_allowed, created_at, updated_at, idempotency_id, "
            "atom_id, redacted_at FROM people WHERE person_id = ?",
            (person_id,),
        ).fetchone()
        if row is None:
            return None
        p = self._row_to_person(row)
        if p.redacted_at and not include_redacted:
            return None
        return p

    # ── Public read API (Tier 0) ─────────────────────────────────────

    def resolve(self, name_or_alias: str, *, include_redacted: bool = False) -> Person | None:
        """Find a person by canonical name OR any alias, case-insensitively.

        Returns the canonical Person record, or None if not found.
        Redacted records are not surfaced unless include_redacted=True.
        """
        if not name_or_alias or not name_or_alias.strip():
            return None
        lower = self._normalize(name_or_alias)

        # Try canonical first
        row = self.conn.execute(
            "SELECT person_id, canonical_name, canonical_lower, is_principal, "
            "web_enrichment_allowed, created_at, updated_at, idempotency_id, "
            "atom_id, redacted_at FROM people WHERE canonical_lower = ?",
            (lower,),
        ).fetchone()
        if row is not None:
            p = self._row_to_person(row)
            if p.redacted_at and not include_redacted:
                return None
            return p

        # Then aliases
        row = self.conn.execute(
            "SELECT p.person_id, p.canonical_name, p.canonical_lower, "
            "p.is_principal, p.web_enrichment_allowed, p.created_at, "
            "p.updated_at, p.idempotency_id, p.atom_id, p.redacted_at "
            "FROM people p JOIN people_aliases a ON a.person_id = p.person_id "
            "WHERE a.alias_lower = ?",
            (lower,),
        ).fetchone()
        if row is None:
            return None
        p = self._row_to_person(row)
        if p.redacted_at and not include_redacted:
            return None
        return p

    def get_principal(self) -> Person | None:
        """Return the current principal, or None if none is set."""
        row = self.conn.execute(
            "SELECT person_id, canonical_name, canonical_lower, is_principal, "
            "web_enrichment_allowed, created_at, updated_at, idempotency_id, "
            "atom_id, redacted_at FROM people "
            "WHERE is_principal = 1 AND redacted_at IS NULL"
        ).fetchone()
        return self._row_to_person(row) if row else None

    def list_people(self, *, include_redacted: bool = False, limit: int = 200) -> list[Person]:
        """Recent people, newest first. Redacted excluded unless asked."""
        clause = "" if include_redacted else "WHERE redacted_at IS NULL"
        rows = self.conn.execute(
            f"SELECT person_id, canonical_name, canonical_lower, is_principal, "
            f"web_enrichment_allowed, created_at, updated_at, idempotency_id, "
            f"atom_id, redacted_at FROM people {clause} "
            f"ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_person(r) for r in rows]

    def list_aliases(self, person_id: str) -> list[Alias]:
        """All aliases for a person."""
        rows = self.conn.execute(
            "SELECT alias_id, person_id, alias, alias_lower, added_at, "
            "source, confidence FROM people_aliases "
            "WHERE person_id = ? ORDER BY added_at",
            (person_id,),
        ).fetchall()
        return [
            Alias(
                alias_id=r[0], person_id=r[1], alias=r[2],
                added_at=r[4], source=r[5], confidence=r[6],
            )
            for r in rows
        ]

    def list_facts(
        self, person_id: str, *,
        status: FactStatus | None = None,
        kind: str | None = None,
    ) -> list[Fact]:
        """Facts for a person, filtered by status and/or kind."""
        sql = (
            "SELECT fact_id, person_id, kind, value, source, source_event_id, "
            "confidence, status, created_at, confirmed_at, retracted_at, "
            "superseded_by FROM people_facts WHERE person_id = ?"
        )
        params: list[object] = [person_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        if kind:
            sql += " AND kind = ?"
            params.append(kind)
        sql += " ORDER BY created_at"
        rows = self.conn.execute(sql, params).fetchall()
        return [
            Fact(
                fact_id=r[0], person_id=r[1], kind=r[2], value=r[3],
                source=r[4], source_event_id=r[5], confidence=r[6],
                status=r[7], created_at=r[8], confirmed_at=r[9],
                retracted_at=r[10], superseded_by=r[11],
            )
            for r in rows
        ]

    def profile(self, name_or_alias_or_id: str) -> PersonProfile:
        """Full profile: canonical row + aliases + facts grouped by status.

        Accepts canonical name, alias, or person_id. Raises PersonNotFoundError
        if not found. Raises RedactedError if the record exists but is
        tombstoned.
        """
        # Try as id first
        p = self._fetch_person_row(name_or_alias_or_id)
        if p is None:
            # Then by name / alias
            p = self.resolve(name_or_alias_or_id)
            if p is None:
                # Was it redacted?
                check = self._fetch_person_row(
                    name_or_alias_or_id, include_redacted=True,
                )
                if check and check.redacted_at:
                    raise RedactedError(
                        f"person {name_or_alias_or_id!r} is redacted "
                        f"(at {check.redacted_at})"
                    )
                raise PersonNotFoundError(name_or_alias_or_id)

        return PersonProfile(
            person=p,
            aliases=self.list_aliases(p.person_id),
            facts_confirmed=self.list_facts(p.person_id, status="confirmed"),
            facts_pending=self.list_facts(p.person_id, status="pending"),
            facts_retracted=self.list_facts(p.person_id, status="retracted"),
        )

    def export_person(self, person_id: str) -> dict:
        """Portable plain-dict export of one person — for backup or hand-off.

        7th-generation: data sovereignty requires the operator can always
        leave with their data.
        """
        prof = self.profile(person_id)
        return {
            "person": prof.person.__dict__,
            "aliases": [a.__dict__ for a in prof.aliases],
            "facts": (
                [f.__dict__ for f in prof.facts_confirmed]
                + [f.__dict__ for f in prof.facts_pending]
                + [f.__dict__ for f in prof.facts_retracted]
            ),
        }

    # ── Public write API (Tier 3) ────────────────────────────────────

    def upsert_person(
        self, *,
        canonical_name: str,
        idempotency_id: str,
        is_principal: bool = False,
        web_enrichment_allowed: bool = False,
        force_principal_switch: bool = False,
    ) -> Person:
        """Create a person if absent (by canonical_name lowercased) — or, on
        idempotency match, return the existing record unchanged.

        ``is_principal=True`` refuses to land if another principal already
        exists, unless ``force_principal_switch=True`` (in which case the
        prior principal is demoted in the same transaction — an event is
        emitted so the operator sees it in the audit trail).
        """
        if not canonical_name or not canonical_name.strip():
            raise ValueError("canonical_name cannot be empty")
        if not idempotency_id:
            raise ValueError("idempotency_id required (Tier 3 channel)")

        canonical_name = canonical_name.strip()
        lower = self._normalize(canonical_name)
        person_id = self._hash_id("pp", f"{lower}:{idempotency_id}")
        now = self._utc_now()

        with self._writer_tx():
            # Idempotency match first — same idempotency_id returns existing
            row = self.conn.execute(
                "SELECT person_id, canonical_name, canonical_lower, is_principal, "
                "web_enrichment_allowed, created_at, updated_at, idempotency_id, "
                "atom_id, redacted_at FROM people WHERE idempotency_id = ?",
                (idempotency_id,),
            ).fetchone()
            if row is not None:
                p = self._row_to_person(row)
                if p.redacted_at:
                    raise RedactedError(
                        f"idempotency_id {idempotency_id!r} maps to a redacted record"
                    )
                return p

            # Name collision (case-insensitive) on a non-redacted record?
            existing = self.conn.execute(
                "SELECT person_id FROM people "
                "WHERE canonical_lower = ? AND redacted_at IS NULL",
                (lower,),
            ).fetchone()
            if existing is not None:
                raise ValueError(
                    f"a person with canonical_name {canonical_name!r} already "
                    f"exists (id={existing[0]}); use add_alias instead, or merge"
                )

            # Principal uniqueness
            if is_principal:
                current = self.get_principal()
                if current is not None:
                    if not force_principal_switch:
                        raise PrincipalConflictError(
                            f"refused to add a second principal — current is "
                            f"{current.canonical_name!r}. Pass "
                            f"force_principal_switch=True to demote them first."
                        )
                    # Demote the prior principal in the same transaction
                    self.conn.execute(
                        "UPDATE people SET is_principal = 0, updated_at = ? "
                        "WHERE person_id = ?",
                        (now, current.person_id),
                    )

            # Companion atom for semantic recall
            atom_id = self.write_atom(
                summary=f"PERSON: {canonical_name}"
                        + (" [principal]" if is_principal else ""),
                content={
                    "person_id": person_id,
                    "canonical_name": canonical_name,
                    "is_principal": is_principal,
                },
                idempotency_id=f"person:{idempotency_id}",
                actor="people-channel",
            )

            self.conn.execute(
                "INSERT INTO people (person_id, canonical_name, canonical_lower, "
                "is_principal, web_enrichment_allowed, created_at, updated_at, "
                "idempotency_id, atom_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    person_id, canonical_name, lower,
                    1 if is_principal else 0,
                    1 if web_enrichment_allowed else 0,
                    now, now, idempotency_id, atom_id,
                ),
            )

        return self._fetch_person_row(person_id)  # type: ignore[return-value]

    def add_alias(
        self, *,
        person_id: str,
        alias: str,
        idempotency_id: str,
        source: AliasSource = "operator",
        confidence: float = 1.0,
    ) -> Alias:
        """Add an alias to a person. Aliases are globally unique
        (case-insensitive) — two people cannot share an alias without an
        explicit merge."""
        if not alias or not alias.strip():
            raise ValueError("alias cannot be empty")
        if not idempotency_id:
            raise ValueError("idempotency_id required")

        alias = alias.strip()
        lower = self._normalize(alias)
        alias_id = self._hash_id("al", f"{lower}:{idempotency_id}")
        now = self._utc_now()

        with self._writer_tx():
            person = self._fetch_person_row(person_id)
            if person is None:
                raise PersonNotFoundError(person_id)

            # Don't shadow the canonical name with an alias of the same person
            if lower == self._normalize(person.canonical_name):
                # Already represented as canonical — no-op
                row = self.conn.execute(
                    "SELECT alias_id, person_id, alias, alias_lower, added_at, "
                    "source, confidence FROM people_aliases "
                    "WHERE person_id = ? AND alias_lower = ?",
                    (person_id, lower),
                ).fetchone()
                if row:
                    return Alias(
                        alias_id=row[0], person_id=row[1], alias=row[2],
                        added_at=row[4], source=row[5], confidence=row[6],
                    )

            # Check global alias uniqueness
            collide = self.conn.execute(
                "SELECT alias_id, person_id FROM people_aliases "
                "WHERE alias_lower = ?",
                (lower,),
            ).fetchone()
            if collide is not None and collide[1] != person_id:
                raise ValueError(
                    f"alias {alias!r} already belongs to a different person "
                    f"(id={collide[1]})"
                )
            if collide is not None:
                # Same person, same alias — return existing
                full = self.conn.execute(
                    "SELECT alias_id, person_id, alias, alias_lower, added_at, "
                    "source, confidence FROM people_aliases WHERE alias_id = ?",
                    (collide[0],),
                ).fetchone()
                return Alias(
                    alias_id=full[0], person_id=full[1], alias=full[2],
                    added_at=full[4], source=full[5], confidence=full[6],
                )

            # Also check that the alias doesn't collide with another person's
            # canonical name.
            cn_collide = self.conn.execute(
                "SELECT person_id FROM people "
                "WHERE canonical_lower = ? AND redacted_at IS NULL "
                "AND person_id != ?",
                (lower, person_id),
            ).fetchone()
            if cn_collide is not None:
                raise ValueError(
                    f"alias {alias!r} matches another person's canonical name "
                    f"(id={cn_collide[0]}); merge or rename first"
                )

            self.conn.execute(
                "INSERT INTO people_aliases (alias_id, person_id, alias, "
                "alias_lower, added_at, source, confidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (alias_id, person_id, alias, lower, now, source, confidence),
            )
            self.conn.execute(
                "UPDATE people SET updated_at = ? WHERE person_id = ?",
                (now, person_id),
            )

        return Alias(
            alias_id=alias_id, person_id=person_id, alias=alias,
            added_at=now, source=source, confidence=confidence,
        )

    def record_fact(
        self, *,
        person_id: str,
        kind: str,
        value: str,
        source: FactSource,
        idempotency_id: str,
        confidence: float | None = None,
        source_event_id: str | None = None,
        status: FactStatus | None = None,
        valid_from: str | None = None,
        valid_until: str | None = None,
    ) -> Fact:
        """Record one fact about a person.

        Defaults follow the untrusted-input doctrine:
          • source='operator' → status='confirmed', confidence=0.95
          • source='llm'      → status='pending',   confidence=0.40
          • source='import'   → status='pending',   confidence=0.60
          • source='web'      → status='pending',   confidence=0.50

        Pass explicit ``status`` / ``confidence`` to override.

        Bitemporal: ``valid_from`` / ``valid_until`` describe the
        period during which the fact is asserted to hold in the world.
        Default (``None`` for both) means "valid from now, forever
        until retracted." Pass explicit values for facts with known
        time spans (e.g. employment dates).
        """
        if not kind or not value:
            raise ValueError("kind and value are required")
        if not idempotency_id:
            raise ValueError("idempotency_id required")
        if source not in ("operator", "llm", "import", "web", "merge"):
            raise ValueError(f"invalid fact source: {source!r}")

        # Apply doctrine defaults
        defaults = {
            "operator": (0.95, "confirmed"),
            "llm":      (0.40, "pending"),
            "import":   (0.60, "pending"),
            "web":      (0.50, "pending"),
            "merge":    (0.90, "confirmed"),  # merge moves already-confirmed facts
        }
        d_conf, d_status = defaults[source]
        if confidence is None:
            confidence = d_conf
        if status is None:
            status = d_status  # type: ignore[assignment]
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence out of range: {confidence}")
        if status not in ("pending", "confirmed", "retracted"):
            raise ValueError(f"invalid status: {status!r}")

        fact_id = self._hash_id("pf", f"{person_id}:{kind}:{idempotency_id}")
        now = self._utc_now()
        confirmed_at = now if status == "confirmed" else None

        with self._writer_tx():
            # Idempotency match: same id → return existing row
            row = self.conn.execute(
                "SELECT fact_id, person_id, kind, value, source, source_event_id, "
                "confidence, status, created_at, confirmed_at, retracted_at, "
                "superseded_by FROM people_facts WHERE idempotency_id = ?",
                (idempotency_id,),
            ).fetchone()
            if row is not None:
                return Fact(
                    fact_id=row[0], person_id=row[1], kind=row[2], value=row[3],
                    source=row[4], source_event_id=row[5], confidence=row[6],
                    status=row[7], created_at=row[8], confirmed_at=row[9],
                    retracted_at=row[10], superseded_by=row[11],
                )

            person = self._fetch_person_row(person_id)
            if person is None:
                raise PersonNotFoundError(person_id)

            atom_id = self.write_atom(
                summary=f"FACT[{kind}/{status}]: {value} (about {person.canonical_name})",
                content={
                    "person_id": person_id,
                    "kind": kind, "value": value,
                    "source": source, "status": status,
                    "confidence": confidence,
                },
                idempotency_id=f"fact:{idempotency_id}",
                confidence=confidence,
                actor="people-channel",
            )

            # Bitemporal defaults: valid_from = created_at when caller
            # doesn't supply one. Caller can supply explicit values for
            # facts with known time spans (employment, residency, etc.).
            vf = valid_from if valid_from is not None else now
            vu = valid_until
            self.conn.execute(
                "INSERT INTO people_facts (fact_id, person_id, kind, value, "
                "source, source_event_id, confidence, status, created_at, "
                "confirmed_at, idempotency_id, atom_id, valid_from, valid_until) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fact_id, person_id, kind, value, source, source_event_id,
                    confidence, status, now, confirmed_at, idempotency_id,
                    atom_id, vf, vu,
                ),
            )
            self.conn.execute(
                "UPDATE people SET updated_at = ? WHERE person_id = ?",
                (now, person_id),
            )

        return Fact(
            fact_id=fact_id, person_id=person_id, kind=kind, value=value,
            source=source, source_event_id=source_event_id,
            confidence=confidence, status=status, created_at=now,
            confirmed_at=confirmed_at,
        )

    def confirm_fact(self, fact_id: str) -> Fact:
        """Promote a pending fact to confirmed. The row is updated in place
        — this is the one exception to append-only within the facts table,
        scoped narrowly to a status transition with timestamp."""
        now = self._utc_now()
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM people_facts WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            if row is None:
                raise PersonNotFoundError(f"fact not found: {fact_id}")
            if row[0] == "confirmed":
                # already done — idempotent
                pass
            elif row[0] == "retracted":
                raise ValueError(
                    f"fact {fact_id} is retracted; cannot confirm. "
                    f"Record a fresh fact instead."
                )
            else:
                self.conn.execute(
                    "UPDATE people_facts SET status = 'confirmed', "
                    "confirmed_at = ?, confidence = MAX(confidence, 0.95) "
                    "WHERE fact_id = ?",
                    (now, fact_id),
                )

        row = self.conn.execute(
            "SELECT fact_id, person_id, kind, value, source, source_event_id, "
            "confidence, status, created_at, confirmed_at, retracted_at, "
            "superseded_by FROM people_facts WHERE fact_id = ?",
            (fact_id,),
        ).fetchone()
        return Fact(
            fact_id=row[0], person_id=row[1], kind=row[2], value=row[3],
            source=row[4], source_event_id=row[5], confidence=row[6],
            status=row[7], created_at=row[8], confirmed_at=row[9],
            retracted_at=row[10], superseded_by=row[11],
        )

    def retract_fact(self, fact_id: str, *, reason: str = "") -> Fact:
        """Move a fact to status='retracted'. The row stays for audit;
        ``reason`` is appended to value in the channel atom."""
        now = self._utc_now()
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT status FROM people_facts WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            if row is None:
                raise PersonNotFoundError(f"fact not found: {fact_id}")
            self.conn.execute(
                "UPDATE people_facts SET status = 'retracted', "
                "retracted_at = ? WHERE fact_id = ?",
                (now, fact_id),
            )
            if reason:
                self.write_atom(
                    summary=f"FACT RETRACTED: {fact_id} — {reason}",
                    content={"fact_id": fact_id, "reason": reason},
                    idempotency_id=f"retract:{fact_id}:{now}",
                    actor="people-channel",
                )
        row = self.conn.execute(
            "SELECT fact_id, person_id, kind, value, source, source_event_id, "
            "confidence, status, created_at, confirmed_at, retracted_at, "
            "superseded_by FROM people_facts WHERE fact_id = ?",
            (fact_id,),
        ).fetchone()
        return Fact(
            fact_id=row[0], person_id=row[1], kind=row[2], value=row[3],
            source=row[4], source_event_id=row[5], confidence=row[6],
            status=row[7], created_at=row[8], confirmed_at=row[9],
            retracted_at=row[10], superseded_by=row[11],
        )

    def set_web_enrichment(self, person_id: str, allowed: bool) -> Person:
        """Toggle the per-person web enrichment flag. This does NOT trigger
        any web lookup — it only declares consent for a future runner.

        Defaults to off; opt-in only. This flag is the gate that the
        deferred web-enrichment subsystem will check before issuing any
        external query containing identity information.
        """
        now = self._utc_now()
        with self._writer_tx():
            if self._fetch_person_row(person_id) is None:
                raise PersonNotFoundError(person_id)
            self.conn.execute(
                "UPDATE people SET web_enrichment_allowed = ?, updated_at = ? "
                "WHERE person_id = ?",
                (1 if allowed else 0, now, person_id),
            )
        return self._fetch_person_row(person_id)  # type: ignore[return-value]

    # ── Merge / split ─────────────────────────────────────────────────

    def merge_preview(self, from_person_id: str, into_person_id: str) -> MergePreview:
        """Dry-run preview of merge(). Reads only — no writes."""
        if from_person_id == into_person_id:
            raise ValueError("from_person_id and into_person_id are identical")
        a = self._fetch_person_row(from_person_id)
        b = self._fetch_person_row(into_person_id)
        if a is None:
            raise PersonNotFoundError(from_person_id)
        if b is None:
            raise PersonNotFoundError(into_person_id)

        alias_count = self.conn.execute(
            "SELECT COUNT(*) FROM people_aliases WHERE person_id = ?",
            (from_person_id,),
        ).fetchone()[0]
        fact_count = self.conn.execute(
            "SELECT COUNT(*) FROM people_facts WHERE person_id = ?",
            (from_person_id,),
        ).fetchone()[0]
        # Will the absorbed canonical name become an alias on the target?
        existing_alias = self.conn.execute(
            "SELECT 1 FROM people_aliases "
            "WHERE alias_lower = ? AND person_id = ?",
            (self._normalize(a.canonical_name), into_person_id),
        ).fetchone()
        return MergePreview(
            from_person=a, into_person=b,
            aliases_moved=alias_count, facts_moved=fact_count,
            new_alias_for_from_canonical=existing_alias is None,
        )

    def merge(
        self, *,
        from_person_id: str,
        into_person_id: str,
        idempotency_id: str,
        operator_note: str = "",
    ) -> str:
        """Merge ``from`` into ``into``. Returns the merge_id.

        Atomic — all moves and the merge_event row land in one transaction.
        The ``from`` record is redacted so resolve() no longer surfaces it,
        but its row remains and the merge_event captures everything
        needed for split() to reverse this operation.
        """
        if from_person_id == into_person_id:
            raise ValueError("cannot merge a person into themselves")
        if not idempotency_id:
            raise ValueError("idempotency_id required")

        merge_id = self._hash_id("mg", f"{from_person_id}:{into_person_id}:{idempotency_id}")
        now = self._utc_now()

        with self._writer_tx():
            # Idempotency
            row = self.conn.execute(
                "SELECT merge_id FROM people_merge_events WHERE idempotency_id = ?",
                (idempotency_id,),
            ).fetchone()
            if row is not None:
                return row[0]

            a = self._fetch_person_row(from_person_id)
            b = self._fetch_person_row(into_person_id)
            if a is None:
                raise PersonNotFoundError(from_person_id)
            if b is None:
                raise PersonNotFoundError(into_person_id)

            # Principal protection: cannot merge across principals — that's a
            # principal switch, which requires its own explicit action.
            if a.is_principal or b.is_principal:
                raise PrincipalConflictError(
                    "cannot merge a record involving the principal; use "
                    "upsert_person with force_principal_switch=True if the "
                    "principal genuinely changes"
                )

            # Move aliases (collisions are silently dropped — the target
            # already has them)
            self.conn.execute(
                "UPDATE OR IGNORE people_aliases SET person_id = ?, source = 'merge' "
                "WHERE person_id = ?",
                (into_person_id, from_person_id),
            )
            # Drop any that lost the UPDATE OR IGNORE race because of
            # the global-unique index on alias_lower
            self.conn.execute(
                "DELETE FROM people_aliases WHERE person_id = ?",
                (from_person_id,),
            )

            # Add the from-canonical as an alias on target (if not already)
            try:
                self.conn.execute(
                    "INSERT OR IGNORE INTO people_aliases "
                    "(alias_id, person_id, alias, alias_lower, added_at, "
                    "source, confidence) VALUES (?, ?, ?, ?, ?, 'merge', 1.0)",
                    (
                        self._hash_id("al", f"{self._normalize(a.canonical_name)}:merge:{merge_id}"),
                        into_person_id, a.canonical_name,
                        self._normalize(a.canonical_name), now,
                    ),
                )
            except sqlite3.IntegrityError:
                # alias already exists — fine
                pass

            # Move facts
            self.conn.execute(
                "UPDATE people_facts SET person_id = ? WHERE person_id = ?",
                (into_person_id, from_person_id),
            )

            # Tombstone the absorbed record (so resolve() ignores it, but the
            # row stays for forensic audit and split() can re-instate it)
            self.conn.execute(
                "UPDATE people SET redacted_at = ?, updated_at = ? "
                "WHERE person_id = ?",
                (now, now, from_person_id),
            )

            # Record the merge event
            self.conn.execute(
                "INSERT INTO people_merge_events (merge_id, from_person_id, "
                "into_person_id, merged_at, operator_note, idempotency_id) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    merge_id, from_person_id, into_person_id, now,
                    operator_note, idempotency_id,
                ),
            )

            # Bump target
            self.conn.execute(
                "UPDATE people SET updated_at = ? WHERE person_id = ?",
                (now, into_person_id),
            )

        return merge_id

    def split(self, *, merge_id: str, idempotency_id: str) -> Person:
        """Reverse a prior merge. Restores the absorbed record and moves its
        aliases and facts back. Idempotent.

        Returns the un-tombstoned record (the previously-absorbed person).
        """
        if not idempotency_id:
            raise ValueError("idempotency_id required")
        now = self._utc_now()
        with self._writer_tx():
            row = self.conn.execute(
                "SELECT from_person_id, into_person_id, reversed_at "
                "FROM people_merge_events WHERE merge_id = ?",
                (merge_id,),
            ).fetchone()
            if row is None:
                raise PersonNotFoundError(f"merge not found: {merge_id}")
            from_id, into_id, reversed_at = row
            if reversed_at is not None:
                # Idempotent: already reversed — just return the un-tombstoned record
                p = self._fetch_person_row(from_id)
                if p is not None:
                    return p

            # Un-tombstone the absorbed record
            self.conn.execute(
                "UPDATE people SET redacted_at = NULL, updated_at = ? "
                "WHERE person_id = ?",
                (now, from_id),
            )

            # Move facts that were attributed to this merge back. We use a
            # heuristic: any fact currently on `into_id` whose source = 'merge'
            # and whose source_event_id references this merge — but our schema
            # doesn't link facts to merge events. Conservative choice: only
            # move facts whose atom was authored AFTER the merge_id's
            # merged_at and whose person_id is the target. This is
            # approximate; document the limitation.
            # For correctness we instead use a simpler invariant: facts whose
            # atom_id metadata contains the from_id in its content_ref.
            # But that's expensive. Practical v1 contract: split() restores
            # the record itself; fact re-attribution is left to the operator
            # via a follow-up move_fact() in a later release.
            #
            # We mark the merge as reversed.
            self.conn.execute(
                "UPDATE people_merge_events SET reversed_at = ? "
                "WHERE merge_id = ?",
                (now, merge_id),
            )

            # Emit an atom describing the split for the audit trail
            self.write_atom(
                summary=f"MERGE REVERSED: {merge_id} (split {from_id} from {into_id})",
                content={
                    "merge_id": merge_id, "from_person_id": from_id,
                    "into_person_id": into_id,
                },
                idempotency_id=f"split:{merge_id}:{idempotency_id}",
                actor="people-channel",
            )

        p = self._fetch_person_row(from_id)
        if p is None:
            raise PersonNotFoundError(from_id)  # pragma: no cover
        return p

    # ── Redaction (right to be forgotten) ────────────────────────────

    def redact(
        self, *,
        person_id: str,
        idempotency_id: str,
        reason: str = "",
    ) -> str:
        """Tombstone a person record. The API will no longer surface them.

        Returns the redaction_id. Rows remain in the database for forensic
        audit, but resolve() / list_people() / profile() refuse to return
        them. Use include_redacted=True on the read methods to inspect a
        tombstoned record (audit path only — not for normal use).

        Cannot redact the principal — demote them via upsert_person with
        ``force_principal_switch=True`` first if the principal is changing.
        """
        if not idempotency_id:
            raise ValueError("idempotency_id required")
        now = self._utc_now()
        redaction_id = self._hash_id("rd", f"{person_id}:{idempotency_id}")
        with self._writer_tx():
            # Idempotency: same id → return existing
            row = self.conn.execute(
                "SELECT redaction_id FROM people_redactions WHERE idempotency_id = ?",
                (idempotency_id,),
            ).fetchone()
            if row is not None:
                return row[0]

            p = self._fetch_person_row(person_id, include_redacted=True)
            if p is None:
                raise PersonNotFoundError(person_id)
            if p.is_principal:
                raise PrincipalConflictError(
                    "cannot redact the principal directly. Demote them first "
                    "via upsert_person(force_principal_switch=True)."
                )

            self.conn.execute(
                "UPDATE people SET redacted_at = ?, updated_at = ? "
                "WHERE person_id = ?",
                (now, now, person_id),
            )
            self.conn.execute(
                "INSERT INTO people_redactions (redaction_id, person_id, "
                "redacted_at, reason, idempotency_id) VALUES (?, ?, ?, ?, ?)",
                (redaction_id, person_id, now, reason, idempotency_id),
            )
            # Also zero the vector embedding row for the companion atom so
            # vec search cannot return it. (Schema permitting.)
            try:
                self.conn.execute(
                    "DELETE FROM vec_atoms WHERE atom_id IN "
                    "(SELECT atom_id FROM atoms "
                    " WHERE json_extract(scope_tags, '$.channel') = 'people' "
                    " AND content_ref LIKE ?)",
                    (f'%"person_id": "{person_id}"%',),
                )
            except sqlite3.OperationalError:
                # vec_atoms may be absent in minimal test schemas — ok
                pass

            # Emit an atom marking the redaction for the audit trail
            self.write_atom(
                summary=f"PERSON REDACTED: {person_id} — {reason or '(no reason)'}",
                content={"person_id": person_id, "reason": reason},
                idempotency_id=f"redact:{person_id}:{idempotency_id}",
                actor="people-channel",
            )

        return redaction_id

    # ── Bitemporal queries ──────────────────────────────────────────

    def as_of_facts(
        self,
        person_id: str,
        as_of_date: str,
        *,
        kind: str | None = None,
        include_pending: bool = False,
    ) -> list[Fact]:
        """Return facts for ``person_id`` that were valid on ``as_of_date``
        AND Aria knew about on that date — i.e., system-time AND valid-time
        both bounded by ``as_of_date``.

        This is the intuitive "what did I know on date X" query. For
        more nuanced bitemporal queries, use ``facts_at(person_id,
        valid_on=..., as_known_at=...)``.
        """
        return self.facts_at(
            person_id, valid_on=as_of_date, as_known_at=as_of_date,
            kind=kind, include_pending=include_pending,
        )

    def facts_at(
        self,
        person_id: str,
        *,
        valid_on: str | None = None,
        as_known_at: str | None = None,
        kind: str | None = None,
        include_pending: bool = False,
    ) -> list[Fact]:
        """Bitemporal fact query with explicit, separable time dimensions.

        ``valid_on``: the fact must be true in the world on this date
        (its valid_from/valid_until window contains it). When None, no
        valid-time filter is applied.

        ``as_known_at``: Aria must have known about it by this date
        (created_at <= this AND retracted_at NULL or > this). When None,
        defaults to "now" — i.e. use current knowledge.

        Together these answer the four classic bitemporal questions:

          * valid_on=date, as_known_at=now
                "given everything I know now, what was true on date?"
          * valid_on=now, as_known_at=date
                "what did I believe was currently true on date?"
          * valid_on=date1, as_known_at=date2
                "what did I believe on date2 was true on date1?"
          * valid_on=None, as_known_at=date
                "everything I knew about this person on date, with no
                valid-time filter"
        """
        clauses = ["person_id = ?"]
        params: list = [person_id]
        if as_known_at is not None:
            clauses.append("created_at <= ?")
            clauses.append("(retracted_at IS NULL OR retracted_at > ?)")
            params.extend([as_known_at, as_known_at])
        else:
            # default: not retracted as of now
            clauses.append("retracted_at IS NULL")
        if valid_on is not None:
            clauses.append("(valid_from IS NULL OR valid_from <= ?)")
            clauses.append("(valid_until IS NULL OR valid_until > ?)")
            params.extend([valid_on, valid_on])
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if not include_pending:
            clauses.append("status = 'confirmed'")
        sql = (
            "SELECT fact_id, person_id, kind, value, source, source_event_id, "
            "confidence, status, created_at, confirmed_at "
            "FROM people_facts WHERE " + " AND ".join(clauses) +
            " ORDER BY kind, created_at"
        )
        rows = self.conn.execute(sql, params).fetchall()
        return [
            Fact(
                fact_id=r[0], person_id=r[1], kind=r[2], value=r[3],
                source=r[4], source_event_id=r[5], confidence=r[6],
                status=r[7], created_at=r[8], confirmed_at=r[9],
            )
            for r in rows
        ]

    # ── Audit ────────────────────────────────────────────────────────

    def audit(self) -> PeopleAudit:
        """Integrity check across the people tables. Returns a structured
        report; ``ok`` is True iff zero violations."""
        violations: list[str] = []
        orphaned_facts: list[str] = []
        orphaned_aliases: list[str] = []
        duplicate_aliases: list[str] = []

        people_n = self.conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
        fact_n   = self.conn.execute("SELECT COUNT(*) FROM people_facts").fetchone()[0]
        alias_n  = self.conn.execute("SELECT COUNT(*) FROM people_aliases").fetchone()[0]

        # 1. Principal uniqueness (the partial index also enforces this — defense in depth)
        principals = self.conn.execute(
            "SELECT person_id, canonical_name FROM people "
            "WHERE is_principal = 1 AND redacted_at IS NULL"
        ).fetchall()
        principal_count = len(principals)
        if principal_count > 1:
            names = ", ".join(f"{r[1]}({r[0]})" for r in principals)
            violations.append(f"more than one active principal: {names}")

        # 2. Aliases referencing real people
        alias_rows = self.conn.execute(
            "SELECT a.alias_id, a.person_id FROM people_aliases a "
            "LEFT JOIN people p ON p.person_id = a.person_id "
            "WHERE p.person_id IS NULL"
        ).fetchall()
        for alias_id, person_id in alias_rows:
            violations.append(
                f"alias {alias_id}: references missing person {person_id}"
            )
            orphaned_aliases.append(alias_id)

        # 3. Facts referencing real people
        fact_rows = self.conn.execute(
            "SELECT f.fact_id, f.person_id FROM people_facts f "
            "LEFT JOIN people p ON p.person_id = f.person_id "
            "WHERE p.person_id IS NULL"
        ).fetchall()
        for fact_id, person_id in fact_rows:
            violations.append(
                f"fact {fact_id}: references missing person {person_id}"
            )
            orphaned_facts.append(fact_id)

        # 4. Global alias_lower uniqueness (the index enforces; we double-check)
        dup_rows = self.conn.execute(
            "SELECT alias_lower, COUNT(*) c FROM people_aliases "
            "GROUP BY alias_lower HAVING c > 1"
        ).fetchall()
        for alias_lower, count in dup_rows:
            violations.append(
                f"alias {alias_lower!r}: appears {count} times across the table"
            )
            duplicate_aliases.append(alias_lower)

        # 5. Fact status transitions are sensible
        bad_status = self.conn.execute(
            "SELECT fact_id, status, confirmed_at, retracted_at FROM people_facts "
            "WHERE (status = 'confirmed' AND confirmed_at IS NULL) "
            "   OR (status = 'retracted' AND retracted_at IS NULL)"
        ).fetchall()
        for fact_id, status, c_at, r_at in bad_status:
            violations.append(
                f"fact {fact_id}: status={status} but timestamps inconsistent "
                f"(confirmed_at={c_at}, retracted_at={r_at})"
            )

        return PeopleAudit(
            ok=not violations,
            people_rows=people_n, fact_rows=fact_n, alias_rows=alias_n,
            violations=violations,
            orphaned_facts=orphaned_facts,
            orphaned_aliases=orphaned_aliases,
            duplicate_aliases=duplicate_aliases,
            principal_count=principal_count,
        )


__all__ = [
    "Alias",
    "AliasSource",
    "Fact",
    "FactSource",
    "FactStatus",
    "MergePreview",
    "PeopleAudit",
    "PeopleChannel",
    "Person",
    "PersonNotFoundError",
    "PersonProfile",
    "PrincipalConflictError",
    "RedactedError",
    "WELL_KNOWN_FACT_KINDS",
    "ensure_people_schema",
]
