"""Tests for v0.2.14 — the modular memory channel system, Aria identity,
financial ledger, appendix, horizon scan."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


# ─── Shared fixture: a minimal atoms.db without sqlite-vec ──────────────────


@pytest.fixture
def conn(tmp_path):
    """Minimal atoms.db connection — no sqlite-vec extension required."""
    db_path = tmp_path / "atoms.db"
    c = sqlite3.connect(str(db_path), isolation_level=None)
    c.executescript("""
        PRAGMA journal_mode = WAL;
        PRAGMA foreign_keys = ON;
        CREATE TABLE atoms (
            atom_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            scope_path TEXT, scope_tags TEXT,
            summary TEXT NOT NULL,
            content_ref TEXT NOT NULL,
            claims TEXT NOT NULL, parents TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            parent_atom_id TEXT REFERENCES atoms(atom_id),
            policy TEXT NOT NULL DEFAULT 'local_only',
            confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
            created_at TEXT NOT NULL, created_by TEXT NOT NULL,
            superseded_at TEXT, superseded_by TEXT REFERENCES atoms(atom_id)
        ) STRICT;
    """)
    yield c
    c.close()


# ════════════════════════════════════════════════════════════════════════════
# Channel registry
# ════════════════════════════════════════════════════════════════════════════


class TestChannelRegistry:
    def test_all_thirteen_channels_register(self):
        from sovereign_agent import mem_channels  # noqa: F401
        from sovereign_agent.channels import list_channels
        names = {s.name for s in list_channels()}
        for required in (
            "financial", "goals", "context", "specialist", "humor",
            "emotions", "intuition", "intention", "lessons", "ritual",
            "identity", "trust", "personalities",
        ):
            assert required in names, f"missing channel: {required}"

    def test_authority_tiers_assigned(self):
        from sovereign_agent import mem_channels  # noqa: F401
        from sovereign_agent.channels import list_channels
        for spec in list_channels():
            assert spec.authority_tier in (0, 1, 2, 3, 4)

    def test_get_channel_unknown_raises(self, conn):
        from sovereign_agent.channels import get_channel
        with pytest.raises(KeyError):
            get_channel("nonexistent", conn)

    def test_register_duplicate_class_is_idempotent(self):
        from sovereign_agent.channels import register_channel
        from sovereign_agent.mem_channels.financial import FinancialChannel
        # Re-registering the same class is fine
        register_channel(FinancialChannel)
        register_channel(FinancialChannel)

    def test_register_conflicting_class_raises(self):
        from sovereign_agent.channels import (
            ChannelSpec, MemoryChannel, register_channel,
        )

        class FakeFinancial(MemoryChannel):
            spec = ChannelSpec(
                name="financial",
                description="conflicting",
                authority_tier=0,
            )

        with pytest.raises(ValueError, match="already registered"):
            register_channel(FakeFinancial)


# ════════════════════════════════════════════════════════════════════════════
# Financial channel — Tier 3, idempotency, ROI ranking
# ════════════════════════════════════════════════════════════════════════════


class TestFinancialChannel:
    def _channel(self, conn):
        from sovereign_agent.mem_channels.financial import FinancialChannel
        return FinancialChannel(conn)

    def test_record_invest(self, conn):
        fc = self._channel(conn)
        e = fc.record(
            project="genesis-seeds", kind="invest", amount=500.0,
            idempotency_id="inv-001", note="initial seed",
        )
        assert e.project == "genesis-seeds"
        assert e.amount == 500.0
        assert e.kind == "invest"
        assert e.atom_id  # companion atom written

    def test_idempotency_returns_existing(self, conn):
        fc = self._channel(conn)
        e1 = fc.record(
            project="alpha", kind="invest", amount=100.0,
            idempotency_id="x-001",
        )
        e2 = fc.record(
            project="alpha", kind="invest", amount=999.0,  # different amount!
            idempotency_id="x-001",
        )
        # Idempotent on idempotency_id — second call returns first result
        assert e1.entry_id == e2.entry_id
        assert e2.amount == 100.0  # original amount

    def test_idempotency_required(self, conn):
        fc = self._channel(conn)
        with pytest.raises(ValueError, match="idempotency_id"):
            fc.record(
                project="alpha", kind="invest", amount=100.0,
                idempotency_id="",  # empty
            )

    def test_negative_amount_rejected(self, conn):
        fc = self._channel(conn)
        with pytest.raises(ValueError, match="amount must be"):
            fc.record(
                project="alpha", kind="invest", amount=-1.0,
                idempotency_id="bad-1",
            )

    def test_invalid_kind_rejected(self, conn):
        fc = self._channel(conn)
        with pytest.raises(ValueError, match="invalid kind"):
            fc.record(
                project="alpha", kind="vibes", amount=10.0,  # type: ignore[arg-type]
                idempotency_id="bad-2",
            )

    def test_invalid_project_name_rejected(self, conn):
        fc = self._channel(conn)
        with pytest.raises(ValueError, match="invalid project name"):
            fc.record(
                project="has spaces", kind="invest", amount=1.0,
                idempotency_id="bad-3",
            )

    def test_revert_requires_target(self, conn):
        fc = self._channel(conn)
        with pytest.raises(ValueError, match="reverts_entry_id"):
            fc.record(
                project="alpha", kind="revert", amount=1.0,
                idempotency_id="rev-1",
            )

    def test_balance_default_zero(self, conn):
        fc = self._channel(conn)
        bal = fc.project_balance("never-touched")
        assert bal.invested == 0.0
        assert bal.earned == 0.0
        assert bal.net == 0.0
        assert bal.roi_ratio is None

    def test_roi_calculation(self, conn):
        fc = self._channel(conn)
        fc.record(project="alpha", kind="invest", amount=100.0, idempotency_id="i1")
        fc.record(project="alpha", kind="earn", amount=250.0, idempotency_id="e1")
        bal = fc.project_balance("alpha")
        assert bal.invested == 100.0
        assert bal.earned == 250.0
        assert bal.net == 150.0
        assert bal.roi_ratio == 2.5

    def test_revert_subtracts(self, conn):
        fc = self._channel(conn)
        e1 = fc.record(project="alpha", kind="earn", amount=100.0,
                       idempotency_id="e-1")
        bal_before = fc.project_balance("alpha")
        assert bal_before.earned == 100.0

        # Revert the earn
        fc.record(project="alpha", kind="revert", amount=100.0,
                  idempotency_id="r-1", reverts_entry_id=e1.entry_id)
        bal_after = fc.project_balance("alpha")
        assert bal_after.earned == 0.0

    def test_ranking_by_roi(self, conn):
        fc = self._channel(conn)
        # alpha: $100 in, $200 out (2.0x)
        fc.record(project="alpha", kind="invest", amount=100, idempotency_id="a1")
        fc.record(project="alpha", kind="earn", amount=200, idempotency_id="a2")
        # beta: $50 in, $200 out (4.0x)
        fc.record(project="beta", kind="invest", amount=50, idempotency_id="b1")
        fc.record(project="beta", kind="earn", amount=200, idempotency_id="b2")
        # gamma: $0 in, $50 out (None ROI, sorted last)
        fc.record(project="gamma", kind="earn", amount=50, idempotency_id="g1")

        rank = fc.ranking(by="roi")
        assert rank[0].project == "beta"     # 4.0x
        assert rank[1].project == "alpha"    # 2.0x
        assert rank[2].project == "gamma"    # None

    def test_ranking_by_net(self, conn):
        fc = self._channel(conn)
        fc.record(project="big", kind="invest", amount=1000, idempotency_id="big1")
        fc.record(project="big", kind="earn", amount=1500, idempotency_id="big2")
        fc.record(project="small", kind="invest", amount=10, idempotency_id="sm1")
        fc.record(project="small", kind="earn", amount=20, idempotency_id="sm2")

        rank = fc.ranking(by="net")
        assert rank[0].project == "big"   # +500
        assert rank[1].project == "small"  # +10


# ════════════════════════════════════════════════════════════════════════════
# Goals channel
# ════════════════════════════════════════════════════════════════════════════


class TestGoalsChannel:
    def _channel(self, conn):
        from sovereign_agent.mem_channels.goals import GoalsChannel
        return GoalsChannel(conn)

    def test_declare_and_list(self, conn):
        gc = self._channel(conn)
        gc.declare(goal="Ship v1", timeframe="3-month")
        active = gc.list_active()
        assert len(active) == 1
        assert "Ship v1" in active[0]["summary"]

    def test_invalid_timeframe(self, conn):
        gc = self._channel(conn)
        with pytest.raises(ValueError, match="invalid timeframe"):
            gc.declare(goal="x", timeframe="forever")  # type: ignore[arg-type]

    def test_status_update_supersedes_original(self, conn):
        gc = self._channel(conn)
        atom_id = gc.declare(goal="Ship v1", timeframe="3-month")
        new_id = gc.update_status(
            original_atom_id=atom_id, new_status="achieved",
            note="shipped early",
        )
        assert new_id != atom_id
        # Original should be marked superseded
        row = conn.execute(
            "SELECT superseded_at, superseded_by FROM atoms WHERE atom_id = ?",
            (atom_id,),
        ).fetchone()
        assert row[0] is not None    # superseded_at set
        assert row[1] == new_id       # points at new

    def test_filter_by_timeframe(self, conn):
        gc = self._channel(conn)
        gc.declare(goal="A", timeframe="3-month")
        gc.declare(goal="B", timeframe="3-year")
        active = gc.list_active(timeframe="3-month")
        assert len(active) == 1


# ════════════════════════════════════════════════════════════════════════════
# Identity channel + Aria state
# ════════════════════════════════════════════════════════════════════════════


class TestIdentityAndAria:
    def test_identity_declare(self, conn):
        from sovereign_agent.mem_channels.identity import IdentityChannel
        idc = IdentityChannel(conn)
        atom_id = idc.declare(
            kind="mood", text="focused-and-careful",
            idempotency_id="m-2026-05-09",
        )
        assert atom_id

    def test_identity_invalid_kind(self, conn):
        from sovereign_agent.mem_channels.identity import IdentityChannel
        idc = IdentityChannel(conn)
        with pytest.raises(ValueError, match="invalid identity kind"):
            idc.declare(kind="vibes", text="x",  # type: ignore[arg-type]
                        idempotency_id="x-1")

    def test_aria_state_picks_up_mood(self, conn):
        from sovereign_agent.aria import load_state
        from sovereign_agent.mem_channels.identity import IdentityChannel
        IdentityChannel(conn).declare(
            kind="mood", text="curious", idempotency_id="m-1",
        )
        state = load_state(conn)
        assert state.current_mood == "curious"

    def test_aria_state_picks_up_self_narrative(self, conn):
        from sovereign_agent.aria import load_state
        from sovereign_agent.mem_channels.identity import IdentityChannel
        IdentityChannel(conn).declare(
            kind="self-narrative",
            text="This week we built channels.",
            idempotency_id="sn-1",
        )
        state = load_state(conn)
        assert "channels" in state.self_narrative

    def test_aria_renders_card(self, conn):
        from sovereign_agent.aria import load_state
        state = load_state(conn)
        card = state.render_card()
        assert "Aria-Sovereign-V1" in card
        assert "Structure enough to channel" in card
        assert "Core commitments" in card
        # All seven core commitments present
        for i in range(1, 8):
            assert f"  {i}." in card

    def test_aria_kernel_constants(self):
        from sovereign_agent.aria import (
            CORE_COMMITMENTS, CORE_DESIGNATION, CORE_TAGLINE,
        )
        assert CORE_DESIGNATION == "Aria-Sovereign-V1"
        assert "Structure enough" in CORE_TAGLINE
        assert len(CORE_COMMITMENTS) == 7    # the seven kernel commitments


# ════════════════════════════════════════════════════════════════════════════
# Appendix system
# ════════════════════════════════════════════════════════════════════════════


class TestAppendix:
    def test_write_doc(self, conn, tmp_path):
        from sovereign_agent.appendix import write_doc
        doc = write_doc(
            conn, appendix_dir=tmp_path,
            kind="plan", title="Q3 plan",
            body="# Q3 plan\n\nFinish v0.2.14, ship to family.",
        )
        assert doc.kind == "plan"
        assert Path(doc.file_path).exists()
        assert "Finish v0.2.14" in Path(doc.file_path).read_text()

    def test_invalid_kind_rejected(self, conn, tmp_path):
        from sovereign_agent.appendix import write_doc
        with pytest.raises(ValueError, match="invalid appendix kind"):
            write_doc(conn, appendix_dir=tmp_path, kind="vibes",
                      title="x", body="y")

    def test_attached_to_atom(self, conn, tmp_path):
        from sovereign_agent.appendix import (
            list_docs_for_atom, write_doc,
        )
        from sovereign_agent.mem_channels.goals import GoalsChannel

        atom_id = GoalsChannel(conn).declare(goal="Big plan",
                                              timeframe="3-month")
        doc = write_doc(
            conn, appendix_dir=tmp_path, kind="note",
            title="Notes on the plan", body="Body text",
            atom_id=atom_id,
        )
        attached = list_docs_for_atom(conn, atom_id)
        assert len(attached) == 1
        assert attached[0].doc_id == doc.doc_id

    def test_read_body_missing_file_returns_empty(self, conn, tmp_path):
        from sovereign_agent.appendix import read_body, write_doc
        doc = write_doc(conn, appendix_dir=tmp_path, kind="note",
                        title="x", body="hello")
        # Delete file out from under the record
        Path(doc.file_path).unlink()
        # Should return empty, not crash
        assert read_body(doc) == ""

    def test_list_recent_filters_by_kind(self, conn, tmp_path):
        from sovereign_agent.appendix import list_recent, write_doc
        write_doc(conn, appendix_dir=tmp_path, kind="plan",
                  title="P", body="x")
        write_doc(conn, appendix_dir=tmp_path, kind="note",
                  title="N", body="x")
        plans = list_recent(conn, kind="plan")
        assert len(plans) == 1
        assert plans[0].kind == "plan"


# ════════════════════════════════════════════════════════════════════════════
# Horizon scan
# ════════════════════════════════════════════════════════════════════════════


class TestHorizon:
    def test_render_includes_all_horizons(self):
        from sovereign_agent.horizon import HorizonInputs, render
        out = render(HorizonInputs(
            label="test", decision="ship v1",
            three_month="must hit 90% test coverage",
            twelve_month="model costs may double",
            three_year="quantum compute changes embedding game",
            seventh_generation="don't build the cage",
            best_forward_path="ship v0.2.14, watch metrics",
        ))
        assert "## 3-month" in out
        assert "## 12-month" in out
        assert "## 3-year" in out
        assert "## 7th-generation" in out
        assert "ship v1" in out
        assert "Best forward path" in out
        assert "Aria-Sovereign-V1" in out

    def test_render_handles_empty_fields(self):
        from sovereign_agent.horizon import HorizonInputs, render
        out = render(HorizonInputs(label="x", decision="y"))
        assert "(none specified)" in out
        assert "(none yet identified)" in out

    def test_save_through_appendix(self, conn, tmp_path):
        from sovereign_agent.horizon import (
            HorizonInputs, save_through_appendix,
        )
        doc = save_through_appendix(
            conn, appendix_dir=tmp_path,
            inputs=HorizonInputs(
                label="dream-start", decision="start trillion-dollar dream",
                three_month="model must produce ≥1 valid cycle",
                best_forward_path="bounded test first",
            ),
        )
        assert doc.kind == "horizon"
        assert "trillion-dollar" in Path(doc.file_path).read_text()


# ════════════════════════════════════════════════════════════════════════════
# Universal recall (smoke — full requires sqlite-vec + embeddings)
# ════════════════════════════════════════════════════════════════════════════


class TestUniversalRecall:
    def test_returns_dict_shape(self, conn):
        # Without sqlite-vec/embeddings we can't test full retrieval, but
        # the function should at minimum not crash on an empty store and
        # should return a dict.
        from sovereign_agent.channels import universal_recall
        # Patch: hybrid_search would fail without vec backend, so each
        # channel's search call will raise, get caught, and produce empty
        # output. The function should still return a dict.
        out = universal_recall(conn, "anything")
        assert isinstance(out, dict)


# ════════════════════════════════════════════════════════════════════════════
# Integration — financial events feed into Aria's state
# ════════════════════════════════════════════════════════════════════════════


class TestAriaFinancialIntegration:
    def test_aria_sees_tracked_projects_after_financial_record(self, conn):
        from sovereign_agent.aria import load_state
        from sovereign_agent.mem_channels.financial import FinancialChannel
        fc = FinancialChannel(conn)
        fc.record(project="alpha", kind="invest", amount=10,
                  idempotency_id="a-1")
        fc.record(project="beta", kind="invest", amount=20,
                  idempotency_id="b-1")
        state = load_state(conn)
        assert state.tracked_projects == 2
