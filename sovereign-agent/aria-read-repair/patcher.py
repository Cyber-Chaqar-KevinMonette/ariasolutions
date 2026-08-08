"""patcher.py — FABLE II M3: the shared tolerant reader replaces every
hand-rolled ndjson loop (chunks, qa, results, dispositions, beliefs,
uncertainties, field notes) and the sessions listing learns counted skips.

Anchored transforms only; MARK-idempotent; a moved anchor raises loudly."""
from __future__ import annotations

MARK = "read-repair-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected 1 anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def _mk(anchor: str, new: str, label: str):
    def patch(text: str) -> tuple[str, bool]:
        if MARK in text:
            return text, False
        return _replace_once(text, anchor, new, label=label), True
    return patch


# ── 1. checkpoint_chunks/store.py — all_chunks ───────────────────────────

CHUNKS_ANCHOR = """        out: list[ChunkRecord] = []
        if not self.log.exists():
            return out
        for raw in self.log.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = ChunkRecord(**json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                continue
            if session_id is not None and record.session_id != session_id:
                continue
            out.append(record)
        return out
"""

CHUNKS_NEW = f"""        out: list[ChunkRecord] = []
        # {MARK} — counted skips, never a wedge, never a crash
        from sovereign_agent.read_repair import read_ndjson_tolerant

        for rec in read_ndjson_tolerant(self.log, store="chunks").records:
            try:
                record = ChunkRecord(**rec)
            except TypeError:
                continue
            if session_id is not None and record.session_id != session_id:
                continue
            out.append(record)
        return out
"""

patch_chunk_store = _mk(CHUNKS_ANCHOR, CHUNKS_NEW, "chunks all_chunks")


# ── 2. curiosity.py — recent_qas ─────────────────────────────────────────

QA_ANCHOR = """    path = _qa_dir(data_dir) / "qa.ndjson"
    if not path.exists():
        return []
    out: list[QARecord] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(raw)
            out.append(QARecord(**{k: d.get(k, "") for k in (
                "qa_id", "asked_at", "seed_kind", "seed", "question",
                "answer", "next_check", "topic")} | {
                "confidence": float(d.get("confidence", 0.0))}))
        except Exception:  # noqa: BLE001
            continue
    return out[-n:]
"""

QA_NEW = f"""    path = _qa_dir(data_dir) / "qa.ndjson"
    # {MARK} — counted skips, never a wedge, never a crash
    from sovereign_agent.read_repair import read_ndjson_tolerant

    out: list[QARecord] = []
    for d in read_ndjson_tolerant(path, store="qa").records:
        try:
            out.append(QARecord(**{{k: d.get(k, "") for k in (
                "qa_id", "asked_at", "seed_kind", "seed", "question",
                "answer", "next_check", "topic")}} | {{
                "confidence": float(d.get("confidence", 0.0))}}))
        except Exception:  # noqa: BLE001
            continue
    return out[-n:]
"""

patch_curiosity = _mk(QA_ANCHOR, QA_NEW, "curiosity recent_qas")


# ── 3. proving_ground/runner.py — latest_scores ──────────────────────────

RESULTS_ANCHOR = """    path = _results_path(data_dir)
    if not path.exists():
        return []
    out = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(raw))
        except Exception:  # noqa: BLE001
            continue
    return out[-n:]
"""

RESULTS_NEW = f"""    path = _results_path(data_dir)
    # {MARK} — counted skips, never a wedge, never a crash
    from sovereign_agent.read_repair import read_ndjson_tolerant

    return read_ndjson_tolerant(path, store="proving-results").records[-n:]
"""

patch_proving = _mk(RESULTS_ANCHOR, RESULTS_NEW, "proving latest_scores")


# ── 4. loose_threads/ledger.py — dispositions ────────────────────────────

LEDGER_ANCHOR = """        out: dict[str, dict] = {}
        if not self.path.exists():
            return out
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(raw)
                out[rec["symbol"]] = rec
            except Exception:  # noqa: BLE001
                continue
        return out
"""

LEDGER_NEW = f"""        out: dict[str, dict] = {{}}
        # {MARK} — counted skips, never a wedge, never a crash
        from sovereign_agent.read_repair import read_ndjson_tolerant

        for rec in read_ndjson_tolerant(self.path, store="loose-threads").records:
            if rec.get("symbol"):
                out[rec["symbol"]] = rec
        return out
"""

patch_loose_threads = _mk(LEDGER_ANCHOR, LEDGER_NEW, "loose-threads dispositions")


# ── 5+6. epistemic_ledger/ledger.py — all_beliefs + _state ───────────────

BELIEFS_ANCHOR = """        out: list[Belief] = []
        if not self.log.exists():
            return out
        for raw in self.log.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(Belief(**json.loads(raw)))
            except (json.JSONDecodeError, TypeError):
                continue
        return out
"""

BELIEFS_NEW = f"""        out: list[Belief] = []
        # {MARK} — counted skips, never a wedge, never a crash
        from sovereign_agent.read_repair import read_ndjson_tolerant

        for rec in read_ndjson_tolerant(self.log, store="epistemic-beliefs").records:
            try:
                out.append(Belief(**rec))
            except TypeError:
                continue
        return out
"""

STATE_ANCHOR = """        state: dict[str, Uncertainty] = {}
        if not self.log.exists():
            return state
        for raw in self.log.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                u = Uncertainty(**json.loads(raw))
                state[u.uncertainty_id] = u
            except (json.JSONDecodeError, TypeError):
                continue
        return state
"""

STATE_NEW = f"""        state: dict[str, Uncertainty] = {{}}
        # {MARK} — counted skips, never a wedge, never a crash
        from sovereign_agent.read_repair import read_ndjson_tolerant

        for rec in read_ndjson_tolerant(self.log, store="uncertainties").records:
            try:
                u = Uncertainty(**rec)
            except TypeError:
                continue
            state[u.uncertainty_id] = u
        return state
"""


def patch_epistemic(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, BELIEFS_ANCHOR, BELIEFS_NEW, label="all_beliefs")
    text = _replace_once(text, STATE_ANCHOR, STATE_NEW, label="_state")
    return text, True


# ── 7. stewardship/field_notes.py — iter_all ─────────────────────────────

NOTES_ANCHOR = """    def iter_all(self) -> Iterable[FieldNote]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield self._from_dict(data)
"""

NOTES_NEW = f"""    def iter_all(self) -> Iterable[FieldNote]:
        # {MARK} — counted skips, never a wedge, never a crash
        from sovereign_agent.read_repair import read_ndjson_tolerant

        for data in read_ndjson_tolerant(self.path, store="field-notes").records:
            yield self._from_dict(data)
"""

patch_field_notes = _mk(NOTES_ANCHOR, NOTES_NEW, "field_notes iter_all")


# ── 8. agent_session.py — SessionStore.list_all counted skips ────────────

SESSIONS_ANCHOR = """        out: list[SessionState] = []
        for p in sorted(self.root.glob("*.json"), reverse=True):
            try:
                s = self.load(p.stem)
            except SessionError:
                continue   # skip corrupt files; status can surface them later
            if status is None or s.status == status:
                out.append(s)
        return out
"""

SESSIONS_NEW = f"""        out: list[SessionState] = []
        corrupt = 0  # {MARK} — counted skips, surfaced, never a wedge
        for p in sorted(self.root.glob("*.json"), reverse=True):
            if p.name.endswith(".scope.json"):
                continue   # scope contracts live beside sessions; not sessions
            try:
                s = self.load(p.stem)
            except SessionError:
                corrupt += 1
                continue
            if status is None or s.status == status:
                out.append(s)
        if corrupt:
            try:
                emit_event("corrupt-lines-d", plane="control",
                           trace_id="read-repair-sessions",
                           payload={{"store": "sessions",
                                    "file": str(self.root),
                                    "skipped": corrupt,
                                    "total_lines": corrupt + len(out)}})
            except Exception:  # noqa: BLE001
                pass
        return out
"""

patch_sessions = _mk(SESSIONS_ANCHOR, SESSIONS_NEW, "sessions list_all")


ALL_PATCHES = {
    "checkpoint_chunks/store.py": patch_chunk_store,
    "curiosity.py": patch_curiosity,
    "proving_ground/runner.py": patch_proving,
    "loose_threads/ledger.py": patch_loose_threads,
    "epistemic_ledger/ledger.py": patch_epistemic,
    "stewardship/field_notes.py": patch_field_notes,
    "agent_session.py": patch_sessions,
}
