"""
╔══════════════════════════════════════════════════════════════════════════╗
║  directives.py — Plain-English operator entry                            ║
║  v0.2.12                                                                  ║
║                                                                           ║
║  ``sov do "<directive>"`` parses an English sentence into either a       ║
║  planner invocation or a dream-session command. Deterministic, no model. ║
║  When required arguments aren't extractable from the sentence, the       ║
║  parser returns a list of ``Question``s the CLI can render interactively.║
║                                                                           ║
║  Why deterministic, not model-driven?                                    ║
║                                                                           ║
║    The directive is the OPERATOR'S intent, not the agent's. Routing it    ║
║    through a model would (a) introduce latency for short commands, (b)   ║
║    create a non-trivial trust boundary (a misclassifying model could     ║
║    misroute a destructive directive), (c) require Ollama to be up just   ║
║    to type a command. Keyword/pattern matching is sufficient for the     ║
║    handful of intents we actually support, and it's debuggable: when     ║
║    parsing fails, the operator sees exactly which keyword anchored what. ║
║                                                                           ║
║  Supported intents (v0.2.12):                                            ║
║    • Build trillion-dollar software         → `dream start`             ║
║    • Pause / resume / stop a dream          → dream control commands    ║
║    • Continue / resume a continuation        → continue / resume        ║
║    • Inventory / scan files in a directory   → inventory planner         ║
║    • Project scan / project update           → projects subcommand       ║
║    • Check status / show what's happening    → status                    ║
║    • List planners / dreams / continuations  → list commands             ║
║                                                                           ║
║  Anything we don't recognize falls through to a friendly "I think you   ║
║  meant X — confirm?" interaction, never silent dispatch to the wrong     ║
║  thing.                                                                   ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Question:
    """One piece of missing data we need from the operator.

    The CLI shows these one at a time with a fun prompt. Defaults render
    in [brackets] so an empty answer accepts. If the operator types
    ``cancel`` or ``q``, the whole directive aborts cleanly.
    """

    field: str                    # canonical name (used as kwarg)
    prompt: str                   # what to ask
    default: str | None = None
    suggestions: list[str] = field(default_factory=list)
    required: bool = True


@dataclass
class Directive:
    """The parsed result of a plain-English directive.

    ``intent`` is one of:
      "dream"          — start a new dream session (use kwargs.goal, .max_files, .themes)
      "dream_control"  — pause | resume | stop existing dream (kwargs.action, kwargs.dream_id)
      "continue_cont"  — resume a continuation (kwargs.task_id)
      "pause_cont"     — pause a continuation (kwargs.task_id)
      "inventory"      — invoke inventory planner (kwargs.root, .output, .pattern, .exclude)
      "projects"       — projects subcommand (kwargs.action, .name, .root)
      "status"         — show overall status
      "list"           — list things (kwargs.what)
      "help"           — print help
      "unknown"        — couldn't classify; ``confidence_message`` is set

    ``questions`` holds Questions the CLI must answer before dispatching.
    When ``questions`` is empty AND ``intent != 'unknown'`` the directive
    is ready to run.
    """

    intent: str
    kwargs: dict = field(default_factory=dict)
    questions: list[Question] = field(default_factory=list)
    confidence_message: str = ""    # populated for "unknown" intent
    raw: str = ""

    @property
    def is_ready(self) -> bool:
        return self.intent != "unknown" and not self.questions


# ─── Keyword sets ───────────────────────────────────────────────────────────


_DREAM_KEYWORDS = (
    "trillion", "dream", "infinite-builder", "build software",
    "build trillion", "trillion dollar", "trillion-dollar",
    "build forever", "infinite builder", "keep making",
    "keep building", "infinite build", "infinite loop",
)

_PAUSE_KEYWORDS = ("pause", "halt the dream", "stop for now", "stop the dream", "freeze")
_RESUME_KEYWORDS = ("resume", "continue the dream", "wake up", "unpause", "keep going")
_STOP_KEYWORDS = ("stop", "end the dream", "finish", "terminate", "shut down")

_INVENTORY_KEYWORDS = (
    "inventory", "scan files", "scan the", "summarize files",
    "summarize the", "scan all", "list files", "walk the",
    "walk through",
)

_PROJECTS_KEYWORDS = ("project", "projects", "I updated", "i updated", "I've updated",
                       "ive updated", "register", "track")

_STATUS_KEYWORDS = ("status", "what's happening", "whats happening", "where are we",
                    "show progress", "how are things")

_LIST_KEYWORDS = ("list", "show me", "what dreams", "what continuations",
                  "what planners", "list dreams", "list continuations")

_HELP_KEYWORDS = ("help", "what can I do", "what can i do", "how do I", "how do i",
                  "show commands")


# ─── Number / cap extraction ────────────────────────────────────────────────


_FILE_CAP_RE = re.compile(
    r"\b(?:max(?:imum)?|up to|at most|stop at|until)\s+"
    r"(\d{1,7})\s*(?:files?|file)\b",
    re.IGNORECASE,
)
_PLAIN_FILE_CAP_RE = re.compile(
    r"\b(\d{1,7})\s*(?:files?|file)\b", re.IGNORECASE,
)
_CYCLE_CAP_RE = re.compile(
    r"\b(?:max(?:imum)?|up to|at most|stop after)\s+"
    r"(\d{1,5})\s*(?:cycles?|builds?)\b",
    re.IGNORECASE,
)
_PATH_RE = re.compile(
    r"(?:in|under|at|inside|from)\s+(~?[\w./\-]+)",
    re.IGNORECASE,
)
# Also match a path that directly follows certain verbs like "inventory <path>"
# or "scan <path>" — the regex above requires a preposition.
_PATH_AFTER_VERB_RE = re.compile(
    r"\b(?:inventory|scan|walk|index|register|track|look\s+at)\s+(~?[\w./\-]+)",
    re.IGNORECASE,
)
_TASK_ID_RE = re.compile(
    r"\b(cont-[A-Za-z0-9]{16,}|cycle-[a-z0-9]+-\d+|dream-[A-Za-z0-9]{16,})\b"
)
_FOREVER_RE = re.compile(
    r"\b(?:forever|until I pause|until i pause|indefinitely|"
    r"endless|nonstop|non-stop)\b",
    re.IGNORECASE,
)


# ─── Parser ─────────────────────────────────────────────────────────────────


def parse_directive(raw: str) -> Directive:
    """Parse an English directive into a Directive object.

    Forgiving by design: a missing argument becomes an interactive Question,
    not a hard error. Returns intent='unknown' only when we can't even
    classify the verb.
    """
    if not raw or not raw.strip():
        return Directive(
            intent="unknown",
            confidence_message="empty directive — what would you like to do?",
            raw=raw,
        )

    text = raw.strip()
    lower = text.lower()

    # Strip "until I pause" and similar phrases before classifying — these
    # describe an *unbounded run* (a cap phrase), not a pause-the-dream
    # command. Without this, "Keep making trillion dollar softwares until
    # I pause" would parse as dream_control(action=pause) which is the
    # opposite of what the operator means.
    classification_text = re.sub(
        r"\buntil\s+i\s+pause\b", " ", lower, flags=re.IGNORECASE,
    )
    classification_text = re.sub(
        r"\buntil\s+paused\b", " ", classification_text, flags=re.IGNORECASE,
    )

    # ── 1. Dream control (pause/resume/stop) ─────────────────────────────
    # These take precedence over "dream start" because phrases like
    # "pause my trillion-dollar build" contain both keywords.
    task_id_match = _TASK_ID_RE.search(text)
    referenced_id = task_id_match.group(1) if task_id_match else None

    if any(kw in classification_text for kw in _PAUSE_KEYWORDS) and (
        any(kw in lower for kw in _DREAM_KEYWORDS) or
        (referenced_id and referenced_id.startswith("dream-"))
    ):
        return _dream_control_directive("pause", referenced_id, raw)
    if any(kw in classification_text for kw in _RESUME_KEYWORDS) and (
        any(kw in lower for kw in _DREAM_KEYWORDS) or
        (referenced_id and referenced_id.startswith("dream-"))
    ):
        return _dream_control_directive("resume", referenced_id, raw)
    if any(kw in classification_text for kw in _STOP_KEYWORDS) and (
        any(kw in lower for kw in _DREAM_KEYWORDS) or
        (referenced_id and referenced_id.startswith("dream-"))
    ):
        return _dream_control_directive("stop", referenced_id, raw)

    # ── 2. Pause / resume a continuation ─────────────────────────────────
    if referenced_id and (
        referenced_id.startswith("cont-") or referenced_id.startswith("cycle-")
    ):
        if any(kw in classification_text for kw in _PAUSE_KEYWORDS):
            return Directive(
                intent="pause_cont",
                kwargs={"task_id": referenced_id},
                raw=raw,
            )
        if any(kw in classification_text for kw in _RESUME_KEYWORDS) or "continue" in lower:
            return Directive(
                intent="continue_cont",
                kwargs={"task_id": referenced_id},
                raw=raw,
            )

    # ── 3. Dream start ──────────────────────────────────────────────────
    if any(kw in lower for kw in _DREAM_KEYWORDS):
        return _dream_start_directive(text, raw)

    # ── 4. Projects ──────────────────────────────────────────────────────
    if any(kw in lower for kw in _PROJECTS_KEYWORDS):
        return _projects_directive(text, raw)

    # ── 5. Inventory ────────────────────────────────────────────────────
    if any(kw in lower for kw in _INVENTORY_KEYWORDS):
        return _inventory_directive(text, raw)

    # ── 6. Status / list / help ──────────────────────────────────────────
    if any(kw in lower for kw in _STATUS_KEYWORDS):
        return Directive(intent="status", raw=raw)
    if any(kw in lower for kw in _LIST_KEYWORDS):
        what = "dreams" if "dream" in lower else (
            "continuations" if "continuation" in lower else (
                "planners" if "planner" in lower else (
                    "projects" if "project" in lower else "all"
                )
            )
        )
        return Directive(intent="list", kwargs={"what": what}, raw=raw)
    if any(kw in lower for kw in _HELP_KEYWORDS):
        return Directive(intent="help", raw=raw)

    # ── Fallback ────────────────────────────────────────────────────────
    return Directive(
        intent="unknown",
        confidence_message=(
            "I couldn't tell what you meant. I can help with: building "
            "trillion-dollar software, scanning a directory, tracking "
            "projects, pausing or resuming work, or showing status."
        ),
        raw=raw,
    )


# ─── Sub-parsers ────────────────────────────────────────────────────────────


def _dream_control_directive(action: str, referenced_id: str | None, raw: str) -> Directive:
    """Build pause/resume/stop directive — needs a dream_id if not given."""
    questions: list[Question] = []
    kwargs = {"action": action}
    if referenced_id and referenced_id.startswith("dream-"):
        kwargs["dream_id"] = referenced_id
    else:
        questions.append(Question(
            field="dream_id",
            prompt=(
                "Which dream session? "
                "(paste a dream-... id, or 'latest' for your most recent active one)"
            ),
            default="latest",
            required=True,
        ))
    return Directive(
        intent="dream_control", kwargs=kwargs, questions=questions, raw=raw,
    )


def _dream_start_directive(text: str, raw: str) -> Directive:
    """Build a dream-start directive. Extract caps + themes."""
    lower = text.lower()
    kwargs: dict = {}

    # File cap. "Forever" / "indefinitely" → max_files=0 (unbounded).
    forever = bool(_FOREVER_RE.search(text))
    file_match = _FILE_CAP_RE.search(text) or _PLAIN_FILE_CAP_RE.search(text)
    if forever and not file_match:
        kwargs["max_files"] = 0  # unbounded
    elif file_match:
        try:
            kwargs["max_files"] = int(file_match.group(1))
        except ValueError:
            pass

    cycle_match = _CYCLE_CAP_RE.search(text)
    if cycle_match:
        try:
            kwargs["max_cycles"] = int(cycle_match.group(1))
        except ValueError:
            pass

    # Themes / hints — the substring after "about" or "around" or "for"
    themes = _extract_themes(text)
    if themes:
        kwargs["themes"] = themes

    # Goal text — pass the whole sentence through; the dream record stores
    # it for later inspection. Strips leading "build "/"make ".
    goal = text
    for prefix in ("please ", "could you ", "i want you to ", "let's ", "lets "):
        if goal.lower().startswith(prefix):
            goal = goal[len(prefix):]
    kwargs["goal"] = goal.strip()

    questions: list[Question] = []
    if "max_files" not in kwargs:
        questions.append(Question(
            field="max_files",
            prompt=(
                "How many files at most before stopping? "
                "(pick 2000 for a healthy default, 0 for 'until I pause')"
            ),
            default="2000",
            suggestions=["500", "2000", "10000", "0"],
            required=False,
        ))

    return Directive(
        intent="dream", kwargs=kwargs, questions=questions, raw=raw,
    )


def _projects_directive(text: str, raw: str) -> Directive:
    """Build a project-related directive: scan, list, update."""
    lower = text.lower()
    kwargs: dict = {}
    questions: list[Question] = []

    if "list" in lower or "show all" in lower:
        kwargs["action"] = "list"
        return Directive(intent="projects", kwargs=kwargs, raw=raw)

    if "i updated" in lower or "ive updated" in lower or \
       "i've updated" in lower or "rescan" in lower:
        kwargs["action"] = "update"
    elif "register" in lower or "track" in lower or "scan" in lower:
        kwargs["action"] = "scan"
    else:
        kwargs["action"] = "scan"  # safe default

    name = _extract_project_name(text)
    root = _extract_path(text)

    if name:
        kwargs["name"] = name
    elif kwargs["action"] in ("scan", "update"):
        questions.append(Question(
            field="name",
            prompt="What name for this project? (e.g. 'genesis-seeds', 'monorepo')",
            required=True,
        ))

    if kwargs["action"] == "scan":
        if root:
            kwargs["root"] = str(Path(root).expanduser())
        else:
            questions.append(Question(
                field="root",
                prompt="Which directory? (e.g. ~/AA-Erebo/Genesis-Seeds)",
                required=True,
            ))

    return Directive(intent="projects", kwargs=kwargs, questions=questions, raw=raw)


def _inventory_directive(text: str, raw: str) -> Directive:
    """Build an inventory-planner directive."""
    kwargs: dict = {}
    questions: list[Question] = []

    root = _extract_path(text)
    if root:
        kwargs["root"] = str(Path(root).expanduser())
    else:
        questions.append(Question(
            field="root",
            prompt="Which directory should I scan?",
            suggestions=["~/AA-Erebo", "~/projects", "."],
            required=True,
        ))

    # Pattern detection — "markdown" → *.md, "python" → *.py, etc.
    lower = text.lower()
    patterns: list[str] = []
    if "markdown" in lower or " md " in lower or ".md" in lower:
        patterns.append("*.md")
    if "python" in lower or ".py" in lower:
        patterns.append("*.py")
    if "text" in lower or ".txt" in lower:
        patterns.append("*.txt")
    if "code" in lower:
        patterns.extend(["*.py", "*.js", "*.ts", "*.go", "*.rs"])
    if not patterns:
        patterns = ["*.md", "*.txt", "*.rst", "*.py"]
    kwargs["patterns"] = patterns

    # Output path: not extractable in plain English usually; ask.
    if "output" in lower or "to file" in lower or "save to" in lower:
        # Try to find a path after "to" or "into"
        m = re.search(r"(?:to|into|save to|output to)\s+([\w./\-~]+)", text, re.IGNORECASE)
        if m:
            kwargs["output"] = str(Path(m.group(1)).expanduser())
    if "output" not in kwargs:
        questions.append(Question(
            field="output",
            prompt="Where should I write the inventory text file?",
            default="~/AA-Erebo/Genesis-Seeds/distilled/inventory.txt",
            required=True,
        ))

    return Directive(intent="inventory", kwargs=kwargs, questions=questions, raw=raw)


# ─── Helpers ────────────────────────────────────────────────────────────────


def _extract_path(text: str) -> str | None:
    """Pull the first path-shaped token from the text, or None.

    Tries (in order): 'in/under/at <path>', '<verb> <path>'. Rejects a
    handful of obvious non-path words to avoid false positives.
    """
    rejects = {"memory", "background", "place", "case", "files", "the"}
    for pat in (_PATH_RE, _PATH_AFTER_VERB_RE):
        m = pat.search(text)
        if m:
            candidate = m.group(1)
            if candidate.lower() in rejects:
                continue
            return candidate
    return None


def _extract_project_name(text: str) -> str | None:
    """Pull a project name from quotes or the canonical phrase 'project NAME'."""
    # Quoted: "I updated 'genesis-seeds'"
    m = re.search(r"['\"]([\w\-_.]+)['\"]", text)
    if m:
        return m.group(1)
    # Phrase: "project NAME"
    m = re.search(r"project\s+([\w\-_.]+)", text, re.IGNORECASE)
    if m and m.group(1).lower() not in ("the", "a", "an", "my"):
        return m.group(1)
    return None


def _extract_themes(text: str) -> str:
    """Pull thematic hints out of the sentence (after 'about'/'for'/'around')."""
    m = re.search(
        r"(?:about|around|for|focused on|themed)\s+(.+?)(?:\.|until|$)",
        text, re.IGNORECASE,
    )
    if not m:
        return ""
    raw = m.group(1).strip()
    # Strip trailing connectives.
    raw = re.sub(r"\s+(and|with|using)$", "", raw, flags=re.IGNORECASE)
    return raw[:200]


def render_directive_summary(d: Directive) -> str:
    """One-line human summary of what a directive will do, for confirm prompts."""
    if d.intent == "dream":
        cap = d.kwargs.get("max_files")
        cap_str = (
            "no file cap (until you pause)" if cap == 0
            else f"capped at {cap} files" if cap is not None
            else "with default cap"
        )
        return f"Start a new trillion-dollar dream session, {cap_str}."
    if d.intent == "dream_control":
        action = d.kwargs.get("action", "?")
        did = d.kwargs.get("dream_id", "?")
        return f"{action.capitalize()} dream {did}."
    if d.intent == "continue_cont":
        return f"Resume continuation {d.kwargs.get('task_id', '?')}."
    if d.intent == "pause_cont":
        return f"Pause continuation {d.kwargs.get('task_id', '?')}."
    if d.intent == "inventory":
        return (
            f"Inventory {d.kwargs.get('root', '?')} "
            f"(patterns={d.kwargs.get('patterns', [])}) → "
            f"{d.kwargs.get('output', '?')}"
        )
    if d.intent == "projects":
        return f"Project {d.kwargs.get('action', '?')}: {d.kwargs.get('name', '?')}"
    if d.intent == "status":
        return "Show overall status (dreams, continuations, palace, proposals)."
    if d.intent == "list":
        return f"List {d.kwargs.get('what', 'all')}."
    if d.intent == "help":
        return "Show help."
    return f"(unknown — {d.confidence_message})"


__all__ = [
    "Directive",
    "Question",
    "parse_directive",
    "render_directive_summary",
]
