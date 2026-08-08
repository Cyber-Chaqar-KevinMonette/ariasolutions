"""Persistence package — the bones of Aria's durable state.

ErebloStore is the foundation. ChatSessionsManager and ProjectsManager
sit on top. All three share the same SQLite database.
"""
from sovereign_agent.persistence.store import ErebloStore, SCHEMA_VERSION
from sovereign_agent.persistence.sessions import (
    ChatSessionsManager, Chat, Message, ChatStatus, Role,
)
from sovereign_agent.persistence.projects import (
    ProjectsManager, Project, Task, ProjectStatus, TaskStatus,
)

__all__ = [
    "ErebloStore", "SCHEMA_VERSION",
    "ChatSessionsManager", "Chat", "Message", "ChatStatus", "Role",
    "ProjectsManager", "Project", "Task", "ProjectStatus", "TaskStatus",
]
