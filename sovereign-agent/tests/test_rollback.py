"""Tests for rollback — pre-staged undo plans for Tier-3 actions.

Coverage:
  • Registry: register_generator, is_registered, known_kinds
  • generate_rollback: unknown kind → UnknownActionKind, no rollback path → NoRollbackPath
  • file_write generator: pre-existing file, new file, unreadable file
  • atom_insert generator: with and without id
  • snapshot_create generator
  • draft_archive generator
  • RollbackStore: save → load → list → archive → gc round-trip
  • RollbackStore: path traversal defense
  • RollbackStore: GC of expired plans
  • write_compensating_plan_template: structure + frontmatter shape
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from sovereign_agent.rollback import (
    NoRollbackPath,
    ReversibilityClass,
    RollbackError,
    RollbackPlan,
    RollbackStore,
    UnknownActionKind,
    generate_rollback,
    is_registered,
    known_kinds,
    register_generator,
    write_compensating_plan_template,
)


# ─────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────


class TestRegistry:
    def test_curated_set_is_registered(self):
        """The four roadmap-named action kinds register on import."""
        kinds = known_kinds()
        assert "file_write" in kinds
        assert "atom_insert" in kinds
        assert "snapshot_create" in kinds
        assert "draft_archive" in kinds

    def test_is_registered_returns_true_for_known(self):
        assert is_registered("file_write") is True

    def test_is_registered_returns_false_for_unknown(self):
        assert is_registered("definitely_not_registered") is False

    def test_register_then_unregister_round_trip(self):
        def gen(_args):  # noqa: ARG001
            return RollbackPlan.reversible(
                action_kind="custom_test_kind",
                action_args={},
                commands=[],
            )

        # Use a unique name so we don't clobber anything real
        register_generator("custom_test_kind_for_unit_test", gen)
        assert is_registered("custom_test_kind_for_unit_test")
        # Removing isn't a public API but we can re-register with a noop
        # to verify last-write-wins
        def gen2(_args):  # noqa: ARG001
            return RollbackPlan.compensatable(
                action_kind="custom_test_kind_for_unit_test",
                action_args={},
                manual_steps=["call the operator"],
            )

        register_generator("custom_test_kind_for_unit_test", gen2)
        plan = generate_rollback("custom_test_kind_for_unit_test", {})
        assert plan.reversibility_class == ReversibilityClass.COMPENSATABLE.value


# ─────────────────────────────────────────────────────────────────────────
# generate_rollback dispatch
# ─────────────────────────────────────────────────────────────────────────


class TestGenerateRollback:
    def test_unknown_kind_raises(self):
        with pytest.raises(UnknownActionKind, match="no rollback generator"):
            generate_rollback("not_a_real_action_kind", {})

    def test_known_kind_returns_plan(self, tmp_path: Path):
        plan = generate_rollback(
            "file_write",
            {"path": str(tmp_path / "new.txt"), "content": "hello"},
        )
        assert isinstance(plan, RollbackPlan)
        assert plan.action_kind == "file_write"


# ─────────────────────────────────────────────────────────────────────────
# file_write generator
# ─────────────────────────────────────────────────────────────────────────


class TestFileWriteGenerator:
    def test_new_file_rollback_is_delete(self, tmp_path: Path):
        target = tmp_path / "new.txt"
        # File does NOT exist yet
        plan = generate_rollback("file_write", {"path": str(target)})

        assert plan.reversibility_class == ReversibilityClass.REVERSIBLE.value
        assert len(plan.commands) == 1
        assert plan.commands[0]["kind"] == "delete_file"
        assert plan.commands[0]["path"] == str(target)

    def test_existing_file_rollback_captures_prior_bytes(self, tmp_path: Path):
        target = tmp_path / "existing.txt"
        target.write_bytes(b"prior content")

        plan = generate_rollback("file_write", {"path": str(target)})

        assert plan.reversibility_class == ReversibilityClass.REVERSIBLE.value
        assert len(plan.commands) == 1
        cmd = plan.commands[0]
        assert cmd["kind"] == "restore_bytes"
        assert bytes.fromhex(cmd["bytes_hex"]) == b"prior content"
        assert cmd["size"] == 13

    def test_missing_path_arg_raises_no_rollback_path(self):
        with pytest.raises(NoRollbackPath, match="missing 'path'"):
            generate_rollback("file_write", {})

    def test_unreadable_existing_file_raises_no_rollback_path(self, tmp_path: Path):
        target = tmp_path / "secret.txt"
        target.write_bytes(b"secret")
        try:
            target.chmod(0o000)  # owner cannot read
            # Skip if running as root (root can read anyway)
            if target.read_bytes() == b"secret":
                pytest.skip("running as root; chmod doesn't restrict")
        except (OSError, PermissionError):
            pytest.skip("chmod not supported here")

        try:
            with pytest.raises(NoRollbackPath, match="cannot read prior"):
                generate_rollback("file_write", {"path": str(target)})
        finally:
            target.chmod(0o644)   # cleanup


# ─────────────────────────────────────────────────────────────────────────
# atom_insert generator
# ─────────────────────────────────────────────────────────────────────────


class TestAtomInsertGenerator:
    def test_with_atom_id_produces_delete_command(self):
        plan = generate_rollback(
            "atom_insert", {"atom_id": "atom_abc123"}
        )
        assert plan.reversibility_class == ReversibilityClass.REVERSIBLE.value
        assert plan.commands[0]["kind"] == "delete_atom"
        assert plan.commands[0]["atom_id"] == "atom_abc123"
        # The chain-integrity guard must be set
        assert plan.commands[0]["guard"] == "no_children"

    def test_accepts_legacy_id_arg(self):
        plan = generate_rollback("atom_insert", {"id": "atom_xyz"})
        assert plan.commands[0]["atom_id"] == "atom_xyz"

    def test_missing_id_raises(self):
        with pytest.raises(NoRollbackPath, match="missing 'atom_id'"):
            generate_rollback("atom_insert", {})


# ─────────────────────────────────────────────────────────────────────────
# snapshot_create + draft_archive
# ─────────────────────────────────────────────────────────────────────────


class TestSnapshotGenerator:
    def test_produces_delete_file_command(self):
        plan = generate_rollback(
            "snapshot_create",
            {"snapshot_path": "/var/data/snap-2026-05-20.db"},
        )
        assert plan.commands[0]["kind"] == "delete_file"
        assert plan.commands[0]["path"] == "/var/data/snap-2026-05-20.db"

    def test_missing_path_raises(self):
        with pytest.raises(NoRollbackPath, match="missing 'snapshot_path'"):
            generate_rollback("snapshot_create", {})


class TestDraftArchiveGenerator:
    def test_restores_prior_status(self):
        plan = generate_rollback(
            "draft_archive",
            {"draft_id": "d_001", "prior_status": "active"},
        )
        assert plan.commands[0]["kind"] == "set_draft_status"
        assert plan.commands[0]["status"] == "active"

    def test_defaults_prior_status_to_active(self):
        plan = generate_rollback("draft_archive", {"draft_id": "d_001"})
        assert plan.commands[0]["status"] == "active"

    def test_missing_id_raises(self):
        with pytest.raises(NoRollbackPath, match="missing 'draft_id'"):
            generate_rollback("draft_archive", {})


# ─────────────────────────────────────────────────────────────────────────
# RollbackStore
# ─────────────────────────────────────────────────────────────────────────


class TestRollbackStore:
    def test_save_and_load_pending(self, tmp_path: Path):
        store = RollbackStore(root=tmp_path)
        plan = RollbackPlan.reversible(
            action_kind="file_write",
            action_args={"path": "/tmp/x"},
            commands=[{"kind": "delete_file", "path": "/tmp/x"}],
        )
        path = store.save_pending("cont_abc", plan)
        assert path.exists()

        loaded = store.load_pending("cont_abc", plan.plan_id)
        assert loaded.plan_id == plan.plan_id
        assert loaded.action_kind == "file_write"

    def test_save_is_atomic(self, tmp_path: Path):
        store = RollbackStore(root=tmp_path)
        plan = RollbackPlan.reversible(
            action_kind="atom_insert", action_args={"atom_id": "x"},
            commands=[{"kind": "delete_atom", "atom_id": "x"}],
        )
        store.save_pending("cont_abc", plan)
        # No leftover tmp file
        cont_dir = tmp_path / "cont_abc"
        tmps = list(cont_dir.glob("*.tmp"))
        assert tmps == []

    def test_load_pending_nonexistent_raises(self, tmp_path: Path):
        store = RollbackStore(root=tmp_path)
        with pytest.raises(RollbackError, match="not found"):
            store.load_pending("cont_abc", "rb_does_not_exist")

    def test_list_pending(self, tmp_path: Path):
        store = RollbackStore(root=tmp_path)
        p1 = RollbackPlan.reversible(action_kind="k1", action_args={},
                                     commands=[])
        p2 = RollbackPlan.reversible(action_kind="k2", action_args={},
                                     commands=[])
        store.save_pending("cont_xyz", p1)
        store.save_pending("cont_xyz", p2)

        listed = store.list_pending("cont_xyz")
        assert len(listed) == 2
        kinds = {p.action_kind for p in listed}
        assert kinds == {"k1", "k2"}

    def test_path_traversal_rejected(self, tmp_path: Path):
        store = RollbackStore(root=tmp_path)
        with pytest.raises(RollbackError, match="invalid continuation_id"):
            store._continuation_dir("../etc")
        with pytest.raises(RollbackError, match="invalid continuation_id"):
            store._continuation_dir("a/b/c")

    def test_archive_moves_file_and_sets_expires(self, tmp_path: Path):
        store = RollbackStore(root=tmp_path, window_seconds=60)
        plan = RollbackPlan.reversible(
            action_kind="file_write", action_args={"path": "/tmp/x"},
            commands=[{"kind": "delete_file", "path": "/tmp/x"}],
        )
        store.save_pending("cont_abc", plan)

        archived_path = store.archive("cont_abc", plan.plan_id)
        assert archived_path.exists()
        assert "archive" in str(archived_path)

        # Original location should no longer have the file
        original = tmp_path / "cont_abc" / f"{plan.plan_id}.json"
        assert not original.exists()

        # Archived plan has expires_at set
        archived = json.loads(archived_path.read_text())
        assert archived["expires_at"] is not None

    def test_archive_unknown_plan_raises(self, tmp_path: Path):
        store = RollbackStore(root=tmp_path)
        with pytest.raises(RollbackError, match="not pending"):
            store.archive("cont_abc", "rb_unknown")

    def test_gc_deletes_expired_archives(self, tmp_path: Path):
        store = RollbackStore(root=tmp_path, window_seconds=1)
        plan = RollbackPlan.reversible(
            action_kind="atom_insert", action_args={"atom_id": "x"},
            commands=[],
        )
        store.save_pending("cont_abc", plan)
        store.archive("cont_abc", plan.plan_id)

        # Wait > window for expiration
        time.sleep(1.1)
        deleted = store.gc_expired()
        assert deleted == 1

        archive_dir = tmp_path / "cont_abc" / "archive"
        assert list(archive_dir.glob("*.json")) == []

    def test_gc_keeps_fresh_archives(self, tmp_path: Path):
        store = RollbackStore(root=tmp_path, window_seconds=3600)
        plan = RollbackPlan.reversible(
            action_kind="atom_insert", action_args={"atom_id": "y"},
            commands=[],
        )
        store.save_pending("cont_abc", plan)
        store.archive("cont_abc", plan.plan_id)

        deleted = store.gc_expired()
        assert deleted == 0

    def test_list_skips_corrupt_files(self, tmp_path: Path):
        store = RollbackStore(root=tmp_path)
        cont_dir = store._continuation_dir("cont_abc")
        (cont_dir / "rb_bad.json").write_text("{not json")
        plan = RollbackPlan.reversible(
            action_kind="file_write", action_args={"path": "/tmp/y"},
            commands=[],
        )
        store.save_pending("cont_abc", plan)

        listed = store.list_pending("cont_abc")
        assert len(listed) == 1
        assert listed[0].plan_id == plan.plan_id


# ─────────────────────────────────────────────────────────────────────────
# Compensating-action plan template
# ─────────────────────────────────────────────────────────────────────────


class TestCompensatingPlanTemplate:
    def test_writes_file_with_yaml_frontmatter(self, tmp_path: Path):
        target = tmp_path / "plan.md"
        write_compensating_plan_template(
            action_kind="send_email",
            action_args={"to": "user@example.com", "subject": "hi"},
            output_path=target,
        )
        assert target.exists()
        text = target.read_text()
        # Frontmatter present
        assert text.startswith("---\n")
        # Has action_kind and signature slots
        assert "action_kind: send_email" in text
        assert 'signed_by: ""' in text
        assert 'signed_at: ""' in text
        # Has the four required sections
        assert "What action is being approved" in text
        assert "Why this is irreversible" in text
        assert "What we will do if this turns out wrong" in text
        assert "Operator confirmation" in text

    def test_creates_parent_directories(self, tmp_path: Path):
        target = tmp_path / "nested" / "dir" / "plan.md"
        write_compensating_plan_template(
            action_kind="api_call",
            action_args={"endpoint": "/v1/pay"},
            output_path=target,
        )
        assert target.exists()


# ─────────────────────────────────────────────────────────────────────────
# RollbackPlan constructors
# ─────────────────────────────────────────────────────────────────────────


class TestRollbackPlanConstructors:
    def test_reversible_classmethod_sets_class(self):
        plan = RollbackPlan.reversible(
            action_kind="x", action_args={}, commands=[{"kind": "noop"}],
        )
        assert plan.reversibility_class == ReversibilityClass.REVERSIBLE.value
        assert plan.plan_id.startswith("rb_")
        assert plan.created_at  # populated

    def test_compensatable_classmethod_sets_class(self):
        plan = RollbackPlan.compensatable(
            action_kind="x", action_args={},
            manual_steps=["step 1", "step 2"],
        )
        assert plan.reversibility_class == ReversibilityClass.COMPENSATABLE.value
        assert plan.manual_steps == ["step 1", "step 2"]
        assert plan.commands == []   # empty list, not None
