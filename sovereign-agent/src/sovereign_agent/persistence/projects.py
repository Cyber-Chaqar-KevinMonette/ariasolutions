"""
╔══════════════════════════════════════════════════════════════════════════╗
║  persistence/projects.py — project profiles + task graph                 ║
║  v0.2.37 — skeleton drop                                                  ║
║                                                                           ║
║  A project is the durable, long-lived context. Chats can come and go;   ║
║  projects persist. Aria's project-aware workflows always begin by       ║
║  loading a project profile and its open tasks.                          ║
║                                                                           ║
║  Profile fields                                                          ║
║                                                                           ║
║    name, description, repo_path, status, profile_json (free-form         ║
║    structured data — tech stack, owner, invariants, key designs),       ║
║    summary, timestamps.                                                  ║
║                                                                           ║
║  Tasks                                                                   ║
║                                                                           ║
║    Each task belongs to a project. Tasks form a tree via                ║
║    parent_task_id. Status flows planned → in_progress → done            ║
║    (or blocked, or abandoned). outcome_json captures what happened     ║
║    when the task executed: artifacts created, errors hit, decisions    ║
║    made.                                                                 ║
║                                                                           ║
║  No vector indexes yet                                                  ║
║                                                                           ║
║    Embedding-backed semantic retrieval is queued for v0.2.38+. This    ║
║    module gives you exact-match search on names + descriptions, which  ║
║    is honest and sufficient for the skeleton. The bones support the   ║
║    muscle.                                                               ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from ulid import ULID

from sovereign_agent.persistence.store import ErebloStore, _iso_now


ProjectStatus = Literal["active", "paused", "archived"]
TaskStatus = Literal["planned", "in_progress", "done", "blocked", "abandoned"]


# ─── Records ─────────────────────────────────────────────────────────────


@dataclass
class Project:
    project_id: str
    name: str
    description: str
    repo_path: str
    status: ProjectStatus
    profile: dict[str, Any]          # parsed from profile_json
    summary: str
    created_at: str
    updated_at: str


@dataclass
class Task:
    task_id: str
    project_id: str
    parent_task_id: Optional[str]
    title: str
    description: str
    status: TaskStatus
    ordinal: int
    outcome: dict[str, Any]          # parsed from outcome_json
    created_at: str
    updated_at: str


def _row_to_project(row) -> Project:
    d = dict(row)
    profile = json.loads(d.pop("profile_json") or "{}")
    return Project(profile=profile, **d)


def _row_to_task(row) -> Task:
    d = dict(row)
    outcome = json.loads(d.pop("outcome_json") or "{}")
    return Task(outcome=outcome, **d)


# ─── Manager ─────────────────────────────────────────────────────────────


class ProjectsManager:
    """Owns the projects + tasks tables."""

    def __init__(self, store: ErebloStore):
        self._store = store

    # ─── Project CRUD ───────────────────────────────────────────────────

    def create_project(
        self,
        name: str,
        description: str = "",
        repo_path: str = "",
        profile: Optional[dict[str, Any]] = None,
    ) -> str:
        project_id = str(ULID())
        now = _iso_now()
        self._store.execute(
            "INSERT INTO projects(project_id, name, description, repo_path, "
            "status, profile_json, summary, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'active', ?, '', ?, ?)",
            (project_id, name, description, repo_path,
             json.dumps(profile or {}), now, now),
        )
        return project_id

    def get_project(self, project_id: str) -> Optional[Project]:
        row = self._store.query_one(
            "SELECT * FROM projects WHERE project_id = ?", (project_id,)
        )
        return _row_to_project(row) if row else None

    def get_project_by_name(self, name: str) -> Optional[Project]:
        row = self._store.query_one(
            "SELECT * FROM projects WHERE name = ?", (name,)
        )
        return _row_to_project(row) if row else None

    def list_projects(self, status: Optional[ProjectStatus] = "active") -> list[Project]:
        if status:
            rows = self._store.query_all(
                "SELECT * FROM projects WHERE status = ? "
                "ORDER BY updated_at DESC", (status,)
            )
        else:
            rows = self._store.query_all(
                "SELECT * FROM projects ORDER BY updated_at DESC"
            )
        return [_row_to_project(r) for r in rows]

    def update_project_profile(
        self, project_id: str, profile: dict[str, Any]
    ) -> None:
        self._store.execute(
            "UPDATE projects SET profile_json = ?, updated_at = ? "
            "WHERE project_id = ?",
            (json.dumps(profile), _iso_now(), project_id),
        )

    def update_project_summary(self, project_id: str, summary: str) -> None:
        self._store.execute(
            "UPDATE projects SET summary = ?, updated_at = ? "
            "WHERE project_id = ?",
            (summary, _iso_now(), project_id),
        )

    def set_project_status(self, project_id: str, status: ProjectStatus) -> None:
        self._store.execute(
            "UPDATE projects SET status = ?, updated_at = ? WHERE project_id = ?",
            (status, _iso_now(), project_id),
        )

    # ─── Task CRUD ──────────────────────────────────────────────────────

    def add_task(
        self,
        project_id: str,
        title: str,
        description: str = "",
        parent_task_id: Optional[str] = None,
        ordinal: int = 0,
    ) -> str:
        task_id = str(ULID())
        now = _iso_now()
        self._store.execute(
            "INSERT INTO tasks(task_id, project_id, parent_task_id, title, "
            "description, status, ordinal, outcome_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'planned', ?, '{}', ?, ?)",
            (task_id, project_id, parent_task_id, title, description,
             ordinal, now, now),
        )
        return task_id

    def get_task(self, task_id: str) -> Optional[Task]:
        row = self._store.query_one(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        )
        return _row_to_task(row) if row else None

    def list_tasks(
        self,
        project_id: str,
        status: Optional[TaskStatus] = None,
        parent_task_id: Optional[str] = None,
    ) -> list[Task]:
        clauses = ["project_id = ?"]
        params: list[Any] = [project_id]
        if status:
            clauses.append("status = ?")
            params.append(status)
        if parent_task_id is not None:
            clauses.append("parent_task_id = ?")
            params.append(parent_task_id)
        rows = self._store.query_all(
            f"SELECT * FROM tasks WHERE {' AND '.join(clauses)} "
            f"ORDER BY ordinal ASC, created_at ASC",
            tuple(params),
        )
        return [_row_to_task(r) for r in rows]

    def set_task_status(
        self, task_id: str, status: TaskStatus,
        outcome: Optional[dict[str, Any]] = None,
    ) -> None:
        now = _iso_now()
        if outcome is None:
            self._store.execute(
                "UPDATE tasks SET status = ?, updated_at = ? "
                "WHERE task_id = ?", (status, now, task_id),
            )
        else:
            self._store.execute(
                "UPDATE tasks SET status = ?, outcome_json = ?, updated_at = ? "
                "WHERE task_id = ?",
                (status, json.dumps(outcome), now, task_id),
            )

    def update_task_description(self, task_id: str, description: str) -> None:
        self._store.execute(
            "UPDATE tasks SET description = ?, updated_at = ? WHERE task_id = ?",
            (description, _iso_now(), task_id),
        )

    # ─── Project-scoped views ───────────────────────────────────────────

    def open_tasks(self, project_id: str) -> list[Task]:
        return [
            t for t in self.list_tasks(project_id)
            if t.status in ("planned", "in_progress")
        ]

    def completed_tasks(self, project_id: str) -> list[Task]:
        return self.list_tasks(project_id, status="done")


__all__ = [
    "ProjectsManager", "Project", "Task",
    "ProjectStatus", "TaskStatus",
]
