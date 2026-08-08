"""
╔══════════════════════════════════════════════════════════════════════════╗
║  workflow/handlers/natural_language.py — natural-language workflows      ║
║  v0.2.39 language drop                                                    ║
║                                                                           ║
║  The bridge between "Kevin types a goal in plain English" and "Aria    ║
║  executes a workflow." Routes through the intent maturity scorer before║
║  the AgenticLoop ever calls a handler.                                  ║
║                                                                           ║
║  Two pieces                                                              ║
║                                                                           ║
║    1. NaturalLanguagePlanner — takes a goal string and the available   ║
║       handler kinds, produces a PlanStep list. Currently a structured  ║
║       rule-based planner; LLM-backed planning slots in later by         ║
║       replacing this class while keeping the same interface.            ║
║                                                                           ║
║    2. GatedAgenticRun — wraps the AgenticLoop with intent maturity     ║
║       gating. M2/M3 → execute. M1 → simulate + report. M0 → ask for   ║
║       clarification, don't execute. Per the canon's safe degradation   ║
║       principle.                                                        ║
║                                                                           ║
║  This is the SKELETON of natural language. It's deterministic, not    ║
║  LLM-driven. That's intentional: it gives Aria reliable handling of   ║
║  the common patterns ("write a file with X", "run command Y", "send  ║
║  a birthday message at Z") without depending on an LLM call for every║
║  workflow. When LLM handlers wire in (v0.2.40+), they'll register     ║
║  here too, and the planner can defer to them for goals that don't    ║
║  match a known pattern.                                                ║
║                                                                           ║
║  Recognized patterns (initial set)                                     ║
║                                                                           ║
║    "write FILE with CONTENT"        → file_write step                ║
║    "create FILE containing CONTENT" → file_write step                ║
║    "run COMMAND"                    → shell step                      ║
║    "execute COMMAND"                → shell step                      ║
║    "read FILE"                      → file_read step                 ║
║    "show me FILE"                   → file_read step                 ║
║    "remind me at TIME to MESSAGE"   → timer step (one_shot)          ║
║    "every X seconds, do Y"          → recurring timer step           ║
║                                                                           ║
║  Unrecognized goals fall through to a single 'note' step that         ║
║  records the goal verbatim — useful for journaling/scratch workflows. ║
║                                                                           ║
║  Kill switch: SOV_NO_NL_PLANNER=1                                       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from sovereign_agent.intent.maturity import (
    IntentMaturityScorer, MaturityAssessment,
)
from sovereign_agent.workflow.agentic_loop import (
    AgenticLoop, PlanStep,
)

logger = logging.getLogger(__name__)


def _emit(
    flag: str,
    *,
    trace_id: str,
    parent_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Emit a workflow lifecycle event, swallowing any logging failure.

    Mirrors the helper in agentic_loop: observability must never break the
    run. Returns the event ULID or None.
    """
    try:
        from sovereign_agent.events import emit_event
        return emit_event(flag, plane="control", trace_id=trace_id,
                          parent_id=parent_id, payload=payload or {})
    except Exception as exc:  # noqa: BLE001
        logger.debug("workflow event %s failed to emit: %r", flag, exc)
        return None


def _new_trace_id() -> str:
    """A standalone trace id for runs that never create a workflow (M0/refused)."""
    try:
        from ulid import ULID
        return str(ULID())
    except Exception:  # noqa: BLE001
        import uuid
        return uuid.uuid4().hex


# Action kinds the agentic loop has handlers for. The LLM planner is only
# ever allowed to emit these; anything else is demoted to a 'note' so a
# hallucinated kind can never reach an unguarded execution path.
ALLOWED_ACTION_KINDS: frozenset[str] = frozenset(
    {"note", "shell", "file_write", "file_read", "timer_schedule"}
)


KILL_SWITCH_ENV = "SOV_NO_NL_PLANNER"


# ─── Result types ────────────────────────────────────────────────────────


@dataclass
class GatedRunResult:
    """Result of running a natural-language goal through the gate."""
    goal: str
    assessment: MaturityAssessment
    decision: str               # 'executed' | 'simulated' | 'asked' | 'refused'
    workflow_id: Optional[str] = None
    plan_summary: list[str] = field(default_factory=list)
    final_status: Optional[dict[str, Any]] = None
    clarifying_questions: list[str] = field(default_factory=list)
    refusal_reason: str = ""


# ─── The planner ─────────────────────────────────────────────────────────


class NaturalLanguagePlanner:
    """Maps a goal string to a list of PlanSteps using rule-based patterns.

    Deterministic and inspectable. Extend by adding patterns in
    self._patterns. LLM-backed planners can subclass and override
    .plan() to defer for goals that don't match.
    """

    def __init__(self):
        # Each tuple: (compiled regex, generator function producing PlanSteps)
        self._patterns: list[tuple[re.Pattern[str], Any]] = [
            (
                re.compile(
                    r"^(?:write|create|make)\s+(?:a\s+)?file\s+(?:at\s+|named\s+)?"
                    r"['\"]?(?P<path>[^'\"]+?)['\"]?\s+"
                    r"(?:with|containing)\s+(?:content\s+)?['\"]?(?P<content>.+?)['\"]?$",
                    re.IGNORECASE,
                ),
                self._make_file_write,
            ),
            (
                re.compile(
                    r"^(?:run|execute)\s+['\"]?(?P<cmd>.+?)['\"]?$",
                    re.IGNORECASE,
                ),
                self._make_shell,
            ),
            (
                re.compile(
                    r"^(?:read|show\s+me)\s+(?:the\s+)?(?:contents?\s+of\s+)?"
                    r"(?:file\s+)?['\"]?(?P<path>[^'\"]+?)['\"]?$",
                    re.IGNORECASE,
                ),
                self._make_file_read,
            ),
            (
                re.compile(
                    r"^remind\s+me\s+in\s+(?P<seconds>\d+)\s+"
                    r"(?P<unit>seconds?|minutes?|hours?)\s+to\s+(?P<msg>.+)$",
                    re.IGNORECASE,
                ),
                self._make_timer,
            ),
        ]

    def plan(self, goal: str) -> list[PlanStep]:
        """Convert a goal string to a list of PlanSteps."""
        matched = self._match_patterns(goal)
        if matched is not None:
            return matched
        # No match — record as a journaling note.
        return [self._note_step(goal)]

    def _match_patterns(self, goal: str) -> Optional[list[PlanStep]]:
        """Try the regex patterns. Returns steps on a match, else None.

        Split out from plan() so LLM-backed planners can reuse the
        deterministic fast-path verbatim and only fall back to an LLM when
        nothing here matches.
        """
        goal_stripped = goal.strip()
        for pattern, generator in self._patterns:
            m = pattern.match(goal_stripped)
            if m:
                return generator(m.groupdict(), goal_stripped)
        return None

    def _note_step(
        self, goal: str, reason: str = "unrecognized goal recorded verbatim"
    ) -> PlanStep:
        """The safe-degradation step: record the goal verbatim as a note.

        ``reason`` is surfaced in the step so an operator (or the cockpit)
        can see *why* the goal was not turned into actions — e.g. no pattern
        matched, or the LLM planner was unavailable.
        """
        goal_stripped = goal.strip()
        return PlanStep(
            title=f"note: {goal_stripped[:60]}",
            description=reason,
            action_kind="note",
            action_input={"raw_goal": goal_stripped, "reason": reason},
        )

    def _make_file_write(self, groups: dict, _raw: str) -> list[PlanStep]:
        return [PlanStep(
            title=f"write {groups['path']}",
            description=f"natural-language file write",
            action_kind="file_write",
            action_input={
                "path": groups["path"].strip(),
                "content": groups["content"].strip() + "\n",
            },
        )]

    def _make_shell(self, groups: dict, _raw: str) -> list[PlanStep]:
        # Split the command on whitespace for argv. This is a SAFE-DEFAULT
        # split — handlers' allowlist still gates whether it runs.
        argv = groups["cmd"].strip().split()
        return [PlanStep(
            title=f"run {argv[0] if argv else 'command'}",
            description="natural-language shell command",
            action_kind="shell",
            action_input={"argv": argv},
        )]

    def _make_file_read(self, groups: dict, _raw: str) -> list[PlanStep]:
        return [PlanStep(
            title=f"read {groups['path']}",
            description="natural-language file read",
            action_kind="file_read",
            action_input={"path": groups["path"].strip()},
        )]

    def _make_timer(self, groups: dict, _raw: str) -> list[PlanStep]:
        seconds = int(groups["seconds"])
        unit = groups["unit"].lower()
        if unit.startswith("minute"):
            seconds *= 60
        elif unit.startswith("hour"):
            seconds *= 3600
        return [PlanStep(
            title=f"timer: {groups['msg'][:40]}",
            description=f"reminder in {seconds}s",
            action_kind="timer_schedule",
            action_input={
                "delay_sec": seconds,
                "message": groups["msg"].strip(),
            },
        )]


# ─── LLM-backed planner ──────────────────────────────────────────────────


LLM_KILL_SWITCH_ENV = "SOV_NO_LLM_PLANNER"


def _plan_task_context(goal: str, max_steps: int) -> str:
    """The structured-output instruction appended to Aria's identity prompt."""
    return (
        "You are planning a workflow from a single operator goal stated in "
        "plain English. Decompose it into an ordered list of concrete steps.\n\n"
        "Respond with ONLY a JSON array — no prose, no markdown fences. Each "
        "element is an object: "
        '{"title": str, "description": str, "action_kind": str, "action_input": object}\n\n'
        "action_kind must be exactly one of:\n"
        '  - "shell": run a command. action_input {"argv": [program, arg, ...]}\n'
        '  - "file_write": write a file. action_input {"path": str, "content": str}\n'
        '  - "file_read": read a file. action_input {"path": str}\n'
        '  - "timer_schedule": a reminder. action_input {"delay_sec": int, "message": str}\n'
        '  - "note": record a thought, no side effect. action_input {"text": str}\n\n'
        "Rules:\n"
        f"  - Prefer the fewest steps that accomplish the goal. At most {max_steps} steps.\n"
        '  - If the goal is reflective, ambiguous, or has no safe concrete action, '
        'return a single "note" step.\n'
        "  - Never invent an action_kind outside the list above.\n"
        "  - Commands and file writes are gated downstream; propose only what the "
        "goal actually needs.\n\n"
        f"Operator goal:\n{goal.strip()}"
    )


class LLMNaturalLanguagePlanner(NaturalLanguagePlanner):
    """Regex-first, LLM-backed planner.

    The deterministic patterns in the base class stay the *fast path*: a goal
    like "run ls" or "write a file foo.txt with bar" never pays for an LLM
    call. Only when no pattern matches does this planner ask the local model
    (via OllamaClient) to decompose the goal into a structured plan, using a
    system prompt sourced from Aria's values (the same ``aria_values.yaml`` the
    rest of the system reads — no second source of identity truth).

    Safe degradation is total. If Ollama is unreachable, the values file can't
    be loaded, or the model returns anything that doesn't validate into known
    action kinds, this planner returns exactly what the deterministic base
    would have: a single ``note`` step recording the goal verbatim — now with a
    ``reason`` so the failure is visible rather than silent.

    Authority note: this planner only *proposes* steps. Execution still flows
    through GatedAgenticRun's maturity gate (M0 ask / M1 simulate / M2-3 run)
    and each handler's own gate (shell allowlist, lease-gated writes). An
    LLM-proposed shell step cannot run unless it also clears those.

    Kill switch: SOV_NO_LLM_PLANNER=1 forces pure deterministic behavior.
    """

    def __init__(
        self,
        client: Any = None,
        model: Optional[str] = None,
        values_path: Any = None,
        *,
        max_steps: int = 8,
        temperature: float = 0.2,
    ):
        super().__init__()
        self._client = client          # OllamaClient | None (lazy-built)
        self._model = model            # defaults to SETTINGS.orchestrator_model
        self._values_path = values_path
        self._values_cache: Any = None
        self._max_steps = max_steps
        self._temperature = temperature

    @property
    def llm_disabled(self) -> bool:
        return bool(os.environ.get(LLM_KILL_SWITCH_ENV))

    def plan(self, goal: str) -> list[PlanStep]:
        # 1. Deterministic fast path — unchanged behavior, no LLM cost.
        matched = self._match_patterns(goal)
        if matched is not None:
            return matched

        # 2. Kill switch → behave exactly like the deterministic base.
        if self.llm_disabled:
            return [self._note_step(goal, reason="llm planner disabled (SOV_NO_LLM_PLANNER)")]

        # 3. LLM fallback, with total safe degradation.
        try:
            system_prompt = self._build_system_prompt(goal)
        except Exception as exc:  # noqa: BLE001 — values unavailable etc.
            logger.debug("llm planner: prompt build failed: %r", exc)
            return [self._note_step(goal, reason=f"llm planner unavailable: {type(exc).__name__}")]

        try:
            raw = self._chat(system_prompt, goal.strip())
        except Exception as exc:  # noqa: BLE001 — Ollama unreachable / transport error
            logger.debug("llm planner: chat failed: %r", exc)
            return [self._note_step(goal, reason=f"ollama unavailable: {type(exc).__name__}")]

        steps = self._parse_plan(raw, goal)
        if steps:
            return steps
        return [self._note_step(goal, reason="llm returned no usable plan")]

    # ─── internals ──────────────────────────────────────────────────────

    def _get_client(self) -> Any:
        if self._client is None:
            from sovereign_agent.ollama_client import OllamaClient
            self._client = OllamaClient()
        return self._client

    def _get_model(self) -> str:
        if self._model is None:
            from sovereign_agent.config import SETTINGS
            self._model = SETTINGS.orchestrator_model
        return self._model

    def _load_values(self) -> Any:
        if self._values_cache is None:
            from sovereign_agent.core.values import AriaValues
            self._values_cache = AriaValues.load(self._values_path)
        return self._values_cache

    def _build_system_prompt(self, goal: str) -> str:
        from sovereign_agent.core.prompt_builder import build_system_prompt
        values = self._load_values()
        return build_system_prompt(
            values,
            task_context=_plan_task_context(goal, self._max_steps),
            tone_register="precise",
            include_ceiling=False,   # lean: keep structured-output adherence high
            include_floor=True,      # safety prohibitions stay present
            include_frame=True,
        )

    def _chat(self, system_prompt: str, goal: str) -> str:
        from sovereign_agent.ollama_client import CallKind
        client = self._get_client()
        model = self._get_model()

        async def _go() -> dict[str, Any]:
            return await client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": goal},
                ],
                call_kind=CallKind.PLAN,
                temperature=self._temperature,
            )

        response = self._run_sync(_go())
        msg = response.get("message") if isinstance(response, dict) else None
        content = (msg or {}).get("content", "") if isinstance(msg, dict) else ""
        return content or ""

    @staticmethod
    def _run_sync(coro: Any) -> Any:
        """Run an async coroutine from sync code, whether or not a loop runs.

        CLI/tests/threaded workers have no running loop → asyncio.run. If a
        loop is already running (e.g. a Textual async worker), offload to a
        one-shot worker thread so we never call asyncio.run inside a loop.
        """
        import asyncio
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(asyncio.run, coro).result()

    def _parse_plan(self, text: str, goal: str) -> list[PlanStep]:
        """Parse + validate the model's JSON into PlanSteps.

        Returns [] on any structural problem so the caller falls back to a
        note. Unknown action_kinds are demoted to notes rather than dropped,
        so a partially-good plan still does no harm.
        """
        items = self._extract_json_items(text)
        if not items:
            return []

        steps: list[PlanStep] = []
        for raw_item in items[: self._max_steps]:
            if not isinstance(raw_item, dict):
                continue
            step = self._coerce_step(raw_item, goal)
            if step is not None:
                steps.append(step)
        return steps

    @staticmethod
    def _extract_json_items(text: str) -> list[Any]:
        """Best-effort extraction of a JSON array (or {"steps": [...]}, or a
        single step object) from a possibly-fenced model response."""
        if not text:
            return []
        s = text.strip()
        # Strip ``` / ```json fences if present.
        if s.startswith("```"):
            s = re.sub(r"^```[a-zA-Z0-9]*\s*", "", s)
            s = re.sub(r"\s*```$", "", s).strip()

        def _as_items(obj: Any) -> list[Any]:
            if isinstance(obj, list):
                return obj
            if isinstance(obj, dict):
                if isinstance(obj.get("steps"), list):
                    return obj["steps"]
                if "action_kind" in obj:  # a single step object
                    return [obj]
            return []

        # Try whole-string parse first.
        try:
            return _as_items(json.loads(s))
        except (json.JSONDecodeError, TypeError):
            pass

        # Fallback: carve out the outermost [ ... ] span.
        start, end = s.find("["), s.rfind("]")
        if 0 <= start < end:
            try:
                return _as_items(json.loads(s[start : end + 1]))
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    def _coerce_step(self, item: dict, goal: str) -> Optional[PlanStep]:
        """Validate/normalize one step dict into a safe PlanStep.

        Unknown or malformed kinds become notes; they never reach an
        execution handler as a side-effecting action.
        """
        kind = str(item.get("action_kind", "note")).strip()
        title = str(item.get("title") or kind or "step").strip()[:80]
        desc = str(item.get("description") or "natural-language plan step").strip()[:300]
        ai = item.get("action_input")
        ai = ai if isinstance(ai, dict) else {}

        def _note(reason: str) -> PlanStep:
            text = str(ai.get("text") or item.get("title") or goal).strip()
            return PlanStep(title=f"note: {text[:60]}", description=reason,
                            action_kind="note",
                            action_input={"text": text, "reason": reason})

        if kind not in ALLOWED_ACTION_KINDS:
            return _note(f"demoted: unsupported action_kind {kind!r}")

        if kind == "note":
            text = str(ai.get("text") or ai.get("raw_goal") or desc).strip()
            return PlanStep(title=title or "note", description=desc,
                            action_kind="note",
                            action_input={"text": text})

        if kind == "shell":
            argv = ai.get("argv")
            if isinstance(argv, str):
                argv = argv.split()
            elif isinstance(argv, list):
                argv = [str(a) for a in argv if str(a).strip()]
            else:
                cmd = ai.get("command") or ai.get("cmd")
                argv = str(cmd).split() if cmd else []
            if not argv:
                return _note("demoted: shell step had no command")
            return PlanStep(title=title, description=desc, action_kind="shell",
                            action_input={"argv": argv})

        if kind == "file_write":
            path = str(ai.get("path") or "").strip()
            if not path:
                return _note("demoted: file_write had no path")
            content = ai.get("content", "")
            content = content if isinstance(content, str) else json.dumps(content)
            if not content.endswith("\n"):
                content += "\n"
            return PlanStep(title=title, description=desc, action_kind="file_write",
                            action_input={"path": path, "content": content})

        if kind == "file_read":
            path = str(ai.get("path") or "").strip()
            if not path:
                return _note("demoted: file_read had no path")
            return PlanStep(title=title, description=desc, action_kind="file_read",
                            action_input={"path": path})

        if kind == "timer_schedule":
            try:
                delay = int(ai.get("delay_sec"))
            except (TypeError, ValueError):
                return _note("demoted: timer had no valid delay_sec")
            message = str(ai.get("message") or "").strip()
            if delay < 0 or not message:
                return _note("demoted: timer missing message or negative delay")
            return PlanStep(title=title, description=desc, action_kind="timer_schedule",
                            action_input={"delay_sec": delay, "message": message})

        return _note(f"demoted: unhandled kind {kind!r}")


# ─── Gated run ───────────────────────────────────────────────────────────


class GatedAgenticRun:
    """Runs a natural-language goal through the intent maturity gate then
    the AgenticLoop. Per the canon's safe-degradation cascade:

      M3, M2  → execute
      M1      → simulate (write the plan, mark blocked, don't execute)
      M0      → ask for clarification (don't write a plan)
    """

    def __init__(
        self,
        loop: AgenticLoop,
        planner: Optional[NaturalLanguagePlanner] = None,
        scorer: Optional[IntentMaturityScorer] = None,
    ):
        self._loop = loop
        # Default to the LLM-backed planner: it runs the regex fast-path
        # first and only reaches Ollama when no pattern matches, falling
        # back to a deterministic 'note' step on any failure. Callers can
        # still inject a plain NaturalLanguagePlanner for offline/test use.
        self._planner = planner or LLMNaturalLanguagePlanner()
        self._scorer = scorer or IntentMaturityScorer()

    @property
    def is_disabled(self) -> bool:
        return bool(os.environ.get(KILL_SWITCH_ENV))

    def run(
        self,
        goal: str,
        project_id: str,
        *,
        context_hint: Optional[str] = None,
    ) -> GatedRunResult:
        """The flagship method. Score → plan → gate → execute (or not)."""
        if self.is_disabled:
            _emit(
                "workflow-refused-d",
                trace_id=_new_trace_id(),
                payload={"goal": goal, "reason": "kill-switch (SOV_NO_NL_PLANNER)"},
            )
            return GatedRunResult(
                goal=goal,
                assessment=self._scorer.assess(goal),
                decision="refused",
                refusal_reason="natural-language planner disabled (SOV_NO_NL_PLANNER)",
            )

        assessment = self._scorer.assess(goal, context_hint=context_hint)

        # M0: ask for clarification, don't write a plan
        if assessment.band == "M0":
            _emit(
                "workflow-clarify-d",
                trace_id=_new_trace_id(),
                payload={
                    "goal": goal,
                    "band": assessment.band,
                    "questions": assessment.suggested_clarifications,
                },
            )
            return GatedRunResult(
                goal=goal,
                assessment=assessment,
                decision="asked",
                clarifying_questions=assessment.suggested_clarifications,
            )

        # Plan the goal regardless — even M1 gets a plan written for review
        steps = self._planner.plan(goal)

        # M1: write the plan but don't execute. Mark workflow blocked
        # with "awaiting maturity escalation" so the operator can see what
        # would have happened.
        workflow_id = self._loop.intake(project_id, goal)
        self._loop.write_plan(workflow_id, steps)
        intake_evt = _emit(
            "workflow-intake-d",
            trace_id=workflow_id,
            payload={
                "goal": goal,
                "band": assessment.band,
                "steps": [s.title for s in steps],
            },
        )

        if assessment.band == "M1":
            from sovereign_agent.persistence.projects import ProjectsManager
            # Mark workflow as needs-review
            self._loop.summarize(
                workflow_id,
                summary=(
                    f"M1 (vague-but-benign) — plan written, not executed. "
                    f"Concerning dimensions: {assessment.concerning_dimensions}"
                ),
                succeeded=False,
            )
            _emit(
                "workflow-simulated-d",
                trace_id=workflow_id,
                parent_id=intake_evt,
                payload={
                    "band": assessment.band,
                    "plan": [s.title for s in steps],
                    "concerning_dimensions": assessment.concerning_dimensions,
                },
            )
            return GatedRunResult(
                goal=goal,
                assessment=assessment,
                decision="simulated",
                workflow_id=workflow_id,
                plan_summary=[s.title for s in steps],
            )

        # M2/M3: execute
        final = self._loop.run_to_completion(workflow_id)
        self._loop.summarize(
            workflow_id,
            summary=f"M{assessment.band[1]} natural-language run complete",
            succeeded=final["complete"],
        )
        _emit(
            "workflow-complete-d",
            trace_id=workflow_id,
            parent_id=intake_evt,
            payload={
                "band": assessment.band,
                "succeeded": final["complete"],
                "total_steps": final.get("total_steps"),
                "by_status": final.get("by_status"),
            },
        )

        return GatedRunResult(
            goal=goal,
            assessment=assessment,
            decision="executed",
            workflow_id=workflow_id,
            plan_summary=[s.title for s in steps],
            final_status=final,
        )


__all__ = [
    "NaturalLanguagePlanner",
    "LLMNaturalLanguagePlanner",
    "GatedAgenticRun",
    "GatedRunResult",
    "KILL_SWITCH_ENV",
    "LLM_KILL_SWITCH_ENV",
    "ALLOWED_ACTION_KINDS",
]
