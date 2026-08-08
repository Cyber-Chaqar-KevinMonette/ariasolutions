"""Atom versioning tests — append-only chain pattern from mos_knowledge."""
from __future__ import annotations

import pytest

from sovereign_agent.db import open_atoms_db
from sovereign_agent.memory import Atom, extend_atom, head_of_chain, write_atom


def _make_atom(summary: str, conf: float = 0.7) -> Atom:
    return Atom(
        type="snippet",
        summary=summary,
        content_ref={"kind": "inline", "content": summary},
        claims=[],
        parents=["01HABC0000000000000000ULID"],
        confidence=conf,
        created_by={"actor": "test", "model": "test", "version": "0.2.0"},
    )


def test_write_atom_basic():
    conn = open_atoms_db()
    a = _make_atom("first version")
    aid = write_atom(conn, a)
    conn.commit()
    assert aid == a.atom_id

    row = conn.execute(
        "SELECT version, parent_atom_id, superseded_at FROM atoms WHERE atom_id = ?",
        (aid,),
    ).fetchone()
    assert row[0] == 1
    assert row[1] is None
    assert row[2] is None
    conn.close()


def test_extend_atom_preserves_parent():
    conn = open_atoms_db()
    parent = _make_atom("v1 content")
    write_atom(conn, parent)
    conn.commit()

    new_id = extend_atom(
        conn,
        parent_atom_id=parent.atom_id,
        summary="v2 content with corrections",
        content_ref={"kind": "inline", "content": "extended"},
        claims=[],
        parents=["01HABC0000000000000000ULID"],
        confidence=0.85,
        created_by={"actor": "test", "model": "test", "version": "0.2.0"},
    )
    conn.commit()

    p_row = conn.execute(
        "SELECT summary, version, superseded_at, superseded_by FROM atoms WHERE atom_id = ?",
        (parent.atom_id,),
    ).fetchone()
    assert p_row[0] == "v1 content"
    assert p_row[1] == 1
    assert p_row[2] is not None
    assert p_row[3] == new_id

    n_row = conn.execute(
        "SELECT summary, version, parent_atom_id FROM atoms WHERE atom_id = ?",
        (new_id,),
    ).fetchone()
    assert n_row[0] == "v2 content with corrections"
    assert n_row[1] == 2
    assert n_row[2] == parent.atom_id
    conn.close()


def test_head_of_chain_walks_to_latest():
    conn = open_atoms_db()
    a = _make_atom("v1")
    write_atom(conn, a)
    b_id = extend_atom(
        conn, parent_atom_id=a.atom_id, summary="v2",
        content_ref={"kind": "inline", "content": "v2"}, claims=[],
        parents=["01HABC0000000000000000ULID"], confidence=0.7,
        created_by={"actor": "test", "model": "test", "version": "0.2.0"},
    )
    c_id = extend_atom(
        conn, parent_atom_id=b_id, summary="v3",
        content_ref={"kind": "inline", "content": "v3"}, claims=[],
        parents=["01HABC0000000000000000ULID"], confidence=0.9,
        created_by={"actor": "test", "model": "test", "version": "0.2.0"},
    )
    conn.commit()

    assert head_of_chain(conn, a.atom_id) == c_id
    assert head_of_chain(conn, b_id) == c_id
    assert head_of_chain(conn, c_id) == c_id
    conn.close()


def test_extend_unknown_parent_raises():
    conn = open_atoms_db()
    with pytest.raises(ValueError, match="parent atom not found"):
        extend_atom(
            conn, parent_atom_id="01HFAKE0000000000000000000",
            summary="ghost", content_ref={"kind": "inline", "content": "x"},
            claims=[], parents=["01HABC0000000000000000ULID"],
            confidence=0.5,
            created_by={"actor": "test", "model": "test", "version": "0.2.0"},
        )
    conn.close()


def test_atom_schema_violations_caught():
    with pytest.raises(ValueError, match="at least one parent"):
        Atom(
            type="x", summary="x", content_ref={}, claims=[], parents=[],
            confidence=0.5, created_by={},
        )
    with pytest.raises(ValueError, match=r"confidence"):
        Atom(
            type="x", summary="x", content_ref={}, claims=[],
            parents=["01HX"], confidence=1.5, created_by={},
        )
    with pytest.raises(ValueError, match="parent_atom_id"):
        Atom(
            type="x", summary="x", content_ref={}, claims=[],
            parents=["01HX"], confidence=0.5, created_by={},
            version=2, parent_atom_id=None,
        )
