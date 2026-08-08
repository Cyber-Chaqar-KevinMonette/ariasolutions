"""work_events.py — Workstream A ("Aria's Atelier"): translate a tool's raw
execute() result into a richer "work" event (write / edit / command) for
the cockpit's live work-theater pane.

Reuse, not rewrite: rather than editing every file-mutation/shell tool to
add its own emit_event() call, this hooks the ONE existing dispatch choke
point in loop.py (right after `result = await tool.execute(...)`, where
`tool_name`, the parsed `Args`, and the `ToolResult` are all already in
scope) and derives a payload purely from data that already exists there.
No individual tool file is touched.

Only emits for a small, explicit set of recognized file-mutation/shell
tools, and only on success (`result.ok`) — a failed edit never actually
changed anything, so it would be a phantom entry in a pane whose whole
point is "watch her work," not "watch her attempt things."

Best-effort throughout: `maybe_emit_work_event` never raises and never
blocks the agent loop over a UI nicety — any failure here silently no-ops.
"""
from __future__ import annotations

import difflib
from typing import Any

from .events import emit_event

_DIFF_EXCERPT_LINES = 12

# tool_name -> which "op" bucket it belongs to, for the cockpit pane's
# color convention (green=write, yellow=edit, purple/blue=command).
_WRITE_TOOLS = frozenset({"write_file", "copy_file"})
_EDIT_TOOLS = frozenset({"edit_file", "edit_in_place"})
_COMMAND_TOOLS = frozenset({"run_command", "run_shell", "run_code", "run_tests"})

# full-observability-d (Kevin, 2026-07-26): "if she is making files, working
# on files, making images... making videos, maybe audio files, making
# content files, or whatever she does — I want to know exactly what she is
# doing." File writes/edits/commands already showed up here; the real
# content-generation tools (local diffusion images, speech synth/transcribe)
# never did — a call to generate_image was invisible in the Atelier pane,
# only a bare "-> generate_image T1" line in the live pane with no result.
# tool_name -> human label for the pane.
_MEDIA_TOOLS: dict[str, str] = {
    "generate_image": "image generated",
    "edit_image": "image edited",
    "inpaint_image": "image inpainted",
    "synthesize_speech": "speech synthesized",
    "transcribe_audio": "audio transcribed",
}


def maybe_emit_work_event(
    tool_name: str,
    args: Any,
    result: Any,
    *,
    trace_id: str,
) -> None:
    """Emit a work-write / work-edit / work-command event for the Atelier
    pane if `tool_name` is a recognized file-mutation/shell tool and the
    call succeeded. Silent no-op for everything else (read tools,
    unrecognized tools, failed calls)."""
    if result is None or not getattr(result, "ok", False):
        return
    try:
        payload = _build_payload(tool_name, args, result)
        if payload is None:
            return
        flag = payload.pop("_flag")
        emit_event(flag, plane="work", trace_id=trace_id, payload=payload)
    except Exception:  # noqa: BLE001 — never break the agent loop over a UI nicety
        return


def _diff_excerpt(before: str, after: str) -> tuple[str, int, int]:
    """Unified diff excerpt + (added, removed) line counts."""
    before_lines = before.splitlines(keepends=True)
    after_lines = after.splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(before_lines, after_lines, n=1))
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    excerpt = "".join(diff_lines[:_DIFF_EXCERPT_LINES])
    return excerpt, added, removed


def _build_payload(tool_name: str, args: Any, result: Any) -> dict | None:
    output = getattr(result, "output", None) or {}
    if not isinstance(output, dict):
        output = {}

    if tool_name == "write_file":
        content = getattr(args, "content", "") or ""
        added = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return {
            "_flag": "work-write",
            "op": "write",
            "path": getattr(args, "path", ""),
            "added": added,
            "removed": 0,
            "diff_excerpt": "\n".join(content.splitlines()[:_DIFF_EXCERPT_LINES]),
        }

    if tool_name == "copy_file":
        return {
            "_flag": "work-write",
            "op": "write",
            "path": getattr(args, "dest", ""),
            "added": 0,
            "removed": 0,
            "diff_excerpt": f"copied from {getattr(args, 'source', '')}",
        }

    if tool_name == "edit_file":
        old = getattr(args, "old_str", "") or ""
        new = getattr(args, "new_str", "") or ""
        excerpt, added, removed = _diff_excerpt(old, new)
        return {
            "_flag": "work-edit",
            "op": "edit",
            "path": getattr(args, "path", ""),
            "added": added,
            "removed": removed,
            "diff_excerpt": excerpt,
        }

    if tool_name == "edit_in_place":
        diff = output.get("diff", "") or ""
        excerpt = "\n".join(diff.splitlines()[:_DIFF_EXCERPT_LINES])
        added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
        return {
            "_flag": "work-edit",
            "op": "edit",
            "path": getattr(args, "path", "") or output.get("path", ""),
            "added": added,
            "removed": removed,
            "diff_excerpt": excerpt,
        }

    if tool_name in _COMMAND_TOOLS:
        return {
            "_flag": "work-command",
            "op": "command",
            "path": "",
            "added": 0,
            "removed": 0,
            "cmd": _extract_cmd(tool_name, args),
        }

    if tool_name in _MEDIA_TOOLS:
        return _build_media_payload(tool_name, args, result)

    return None


def _build_media_payload(tool_name: str, args: Any, result: Any) -> dict | None:
    """Content-generation tools (image/audio) don't all shape their
    ToolResult the same way — some put the saved path in `metadata`
    (image tools), some in a plain `output` dict (voice tools). Extract
    defensively rather than assuming one shape."""
    metadata = getattr(result, "metadata", None) or {}
    if not isinstance(metadata, dict):
        metadata = {}
    raw_output = getattr(result, "output", None)
    output_dict = raw_output if isinstance(raw_output, dict) else {}

    path = (metadata.get("path") or output_dict.get("path")
            or output_dict.get("wav_path")
            or (raw_output if isinstance(raw_output, str) else "") or "")

    details: list[str] = []
    prompt = getattr(args, "prompt", "") or metadata.get("prompt", "")
    if prompt:
        details.append(f'"{str(prompt)[:80]}"')
    model = metadata.get("model", "") or output_dict.get("model", "")
    if model:
        details.append(str(model))
    transcript = output_dict.get("transcript", "")
    if transcript:
        details.append(f'"{str(transcript)[:80]}"')
    elapsed = metadata.get("elapsed_seconds")
    if elapsed:
        details.append(f"{elapsed}s")

    return {
        "_flag": "work-media",
        "op": "media",
        "path": path,
        "added": 0,
        "removed": 0,
        "kind": _MEDIA_TOOLS[tool_name],
        "detail": " · ".join(details),
    }


def _extract_cmd(tool_name: str, args: Any) -> str:
    if tool_name == "run_command":
        argv = getattr(args, "argv", None) or []
        return " ".join(argv)
    if tool_name == "run_shell":
        return getattr(args, "command", "") or ""
    if tool_name == "run_code":
        code = getattr(args, "code", "") or ""
        first_line = code.splitlines()[0] if code else ""
        return first_line[:80]
    if tool_name == "run_tests":
        return f"pytest {getattr(args, 'path', '')}"
    return ""
