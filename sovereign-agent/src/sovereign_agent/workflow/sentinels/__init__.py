"""Workflow sentinels — structured workflows Aria can run for herself.

Each sentinel encapsulates a recurring multi-step pattern (install/update,
sync, backup, etc.) with operator-confirmation discipline and rollback.
"""
from sovereign_agent.workflow.sentinels.self_update import (
    SelfUpdateWorkflowSentinel,
    UpdatePackage, UpdatePreview, UpdateOutcome,
    terminal_confirm, auto_approve_all,
)
__all__ = [
    "SelfUpdateWorkflowSentinel",
    "UpdatePackage", "UpdatePreview", "UpdateOutcome",
    "terminal_confirm", "auto_approve_all",
]
