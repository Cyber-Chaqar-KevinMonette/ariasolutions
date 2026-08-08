"""apply_screen.py — Cockpit modal for running staged aria-*/apply_*.sh scripts.

Ctrl+A opens this dashboard. Two views:
  Run Queue — select a pending/applied module and stream its apply script output.
  Catalog   — read-only record of every module: what it added and its invariants.

Scripts are idempotent — safe to re-run. After a successful apply, use the
"Quit Cockpit" button to exit cleanly, then restart to load new Python code.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from textual import work
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, RichLog, Rule, Static


# ── Module catalog ────────────────────────────────────────────────────────────


@dataclass
class _ModuleInfo:
    label: str
    description: str
    added: list[str] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)


_CATALOG: dict[str, _ModuleInfo] = {
    "aria-birth-records": _ModuleInfo(
        label="M75 · Birth Records & Lineage Tool",
        description="Writes Aria's founding atoms and adds the lineage query tool.",
        added=[
            "src/sovereign_agent/tools/lineage_tool.py  (T0, read-only)",
            "6 founding atoms in atoms.ndjson  (tags: birth-record, milestone, founding)",
        ],
        invariants=[
            "Idempotent: script run twice → still exactly 6 founding atoms, no duplicates",
            "All founding atoms: confidence=1.0, ≥1 evidence_ref, ≥50-char claim",
            "lineage(birth_only=True) → only atoms tagged 'founding'",
            "lineage(milestones=True) → exactly 3 milestone atoms",
            "Atoms returned chronologically (oldest-first by ts_created)",
            "Empty atom store → ok=True with guidance note (never raises an error)",
        ],
    ),
    "aria-self-portrait": _ModuleInfo(
        label="M76 · Self-Portrait Synthesis Tool",
        description=(
            "Living mirror — synthesises identity, growth trajectory, readiness, "
            "and a natural-language narrative from 6 live data sources."
        ),
        added=[
            "src/sovereign_agent/tools/self_portrait_tool.py  (T0, read-only)",
            "Tool: self_portrait(include_narrative, days_for_trend)",
        ],
        invariants=[
            "Portrait always completes — any single source failure returns safe defaults",
            "identity section always present (designation + tagline from kernel constants)",
            "trajectory one of: 'improving' | 'stable' | 'declining' | 'insufficient_data'",
            "No LLM calls — template-driven synthesis from real data",
            "Tier 0: zero writes, zero side effects",
        ],
    ),
    "aria-conductor-vault-hardening": _ModuleInfo(
        label="M77 · Conductor & Vault Resilience (16 tests)",
        description=(
            "Stress-tests the two most safety-critical infrastructure modules "
            "at every known failure path."
        ),
        added=[
            "tests/test_conductor_resilience.py  (8 tests)",
            "tests/test_vault_resilience.py  (8 tests)",
        ],
        invariants=[
            "Malformed state.json → conductor starts GREEN, no exception raised",
            "YELLOW crash-resume: DEFCON state persists across conductor restart",
            "Quiesce exception isolation: sentinel.quiesce() failure never propagates",
            "DEFCON progression: warning→YELLOW, alert→ORANGE confirmed by test",
            "BLACK: 3 tampered-manifest incidents rotates writer_token",
            "YELLOW downgrade fires only after QUIET_PERIOD_SECONDS (no premature green)",
            "Vault: blob hash mismatch raises ValueError — no silent data corruption",
            "Merkle chain tamper detected; correct broken snapshot_id returned",
            "Vault key at mode 0o644 → VaultKeyError (must be 0o600 or stricter)",
        ],
    ),
    "aria-autonomy-hardening": _ModuleInfo(
        label="M78 · Autonomy & Execution Resilience (25 tests)",
        description=(
            "Tests dream runner, shell handler, and NL handler at edge cases "
            "that were previously at 0–34% coverage."
        ),
        added=[
            "tests/test_dream_runner.py  (8 tests)",
            "tests/test_shell_handler.py  (7 tests)",
            "tests/test_natural_language_handler.py  (10 tests)",
        ],
        invariants=[
            "Shell handler: timeout_sec enforced, process killed on expiry",
            "Shell handler: >16 KB output truncated, UTF-8-safe (no UnicodeDecodeError)",
            "Shell kill switch: SOV_NO_SHELL_HANDLER=1 → handler-disabled error",
            "Dream runner: idle cycle cap (EC-DREAM-006) auto-pauses on 3 empty cycles",
            "Dream runner: HARD_CAP_CYCLES → status 'exhausted', loop never infinite",
            "NL handler: unrecognised goal → exactly 1 note step, no exception",
            "NL handler: kill switch SOV_NO_NL_PLANNER=1 respected",
            "NL handler: empty / null / oversized / control-char input → graceful fallback",
        ],
    ),
    "aria-honor-calibration": _ModuleInfo(
        label="M79 · Honor & Calibration Tools",
        description=(
            "Character formation: calibration ledger tracks prediction accuracy; "
            "honor log is a structured witness record of integrity moments."
        ),
        added=[
            "src/sovereign_agent/tools/calibration_tools.py",
            "src/sovereign_agent/tools/honor_log_tool.py",
            "Tools: log_prediction (T1), resolve_prediction (T1), calibration_ledger (T0)",
            "Tools: honor_log_read (T0), honor_log_write (T1)",
        ],
        invariants=[
            "log_prediction: entry written with outcome=null (not yet resolved)",
            "resolve_prediction called twice → second call returns already_resolved error",
            "calibration_ledger on empty file → ok=True, total_predictions=0",
            "honor_log_write validates direction and category; rejects empty description",
            "honor_log is append-only: 3 writes → exactly 3 lines in ledger.jsonl",
            "Calibration score tracks per-confidence-bucket accuracy and drift",
        ],
    ),
    "aria-knowledge-atoms": _ModuleInfo(
        label="M80 · Knowledge Atoms (Semantic Memory Seed)",
        description=(
            "Seeds 24 distilled doctrine atoms across 5 domains directly into Aria's "
            "atom store — retrievable via the lineage tool."
        ),
        added=[
            "24 knowledge atoms in atoms.ndjson  (tag: knowledge-seed)",
            "Domains: software-engineering · ai-safety · partnership · codebase · calibration",
        ],
        invariants=[
            "Idempotent: run twice → still exactly 24 knowledge-seed atoms",
            "All atoms: claim ≥100 chars, ≥1 evidence_ref, confidence ≥0.9",
            "Kind diversity: FACT, PATTERN, and RULE all present",
            "5 channels covered: doctrine, safety, partnership, engineering, calibration",
            "No DEFERRED_UNSAFE capability is advocated in any atom claim",
            "All atom titles unique (no duplicates)",
        ],
    ),
    "aria-apply-dashboard": _ModuleInfo(
        label="M81 · Cockpit Apply Dashboard",
        description=(
            "This screen — browse staged modules, run their apply scripts, "
            "and view the module catalog with invariants."
        ),
        added=[
            "src/sovereign_agent/cockpit/apply_screen.py",
            "Ctrl+A binding in cockpit footer",
            "⚙ apply button in cockpit palette (REFERENCE_BUTTONS row)",
        ],
        invariants=[
            "discover_scripts() finds all aria-*/apply_*.sh scripts",
            "Applied detection: module is applied iff tests/test_{slug}.py exists",
            "Discovery is idempotent and results are alphabetically sorted",
            "Script runs in a background thread — UI stays responsive during execution",
            "Escape / q closes dashboard (blocked while a script is actively running)",
        ],
    ),
}


# ── Logic helpers ─────────────────────────────────────────────────────────────


def _extract_script_info(script: Path) -> tuple[str, str]:
    """Parse (label, description) from an apply script's first header comment.  # apply-menu-autoupdate-d

    Expects a line like:
      # apply_foo.sh — Stage M99: Title here
      # apply_foo.sh — Apply M99: Title here
    Returns ("M99 · Title here", "Title here") if pattern matches,
    or (folder_name, "") as fallback.
    """
    try:
        for line in script.read_text().splitlines()[:10]:
            line = line.strip()
            if line.startswith("#") and not line.startswith("#!"):
                content = line.lstrip("#").strip()
                if "—" in content:
                    _, after = content.split("—", 1)
                    after = after.strip()
                    m = re.match(r"(?:Stage|Apply)\s+(M\d+):\s*(.+)", after)
                    if m:
                        mnum, title = m.group(1), m.group(2).strip()
                        return f"{mnum} \u00b7 {title}", title
                    return after, after
    except Exception:
        pass
    return script.parent.name, ""


def _is_applied(repo_root: Path, name: str) -> bool:
    """Heuristic: applied if backups/ dir exists (created by apply script), test file
    exists, or (2026-08-02 fix, mirrors scripts/apply_queue.sh's identical fix) every
    payload .py file is byte-identical to its live counterpart — the slug-named-test
    assumption is false for any module whose payload files are named after what they
    DO, not the aria-<slug> folder (aria-real-estate ships real_estate_gate.py, not
    test_real_estate.py). Without this, the dashboard shows already-applied modules
    as pending forever."""
    if (repo_root / name / "backups").exists():
        return True
    slug = name.removeprefix("aria-").replace("-", "_")
    if (repo_root / "tests" / f"test_{slug}.py").exists():
        return True
    payload = repo_root / name / "payload" / "src" / "sovereign_agent"
    if not payload.is_dir():
        return False
    found = False
    for f in payload.rglob("*.py"):
        found = True
        rel = f.relative_to(payload)
        live = repo_root / "src" / "sovereign_agent" / rel
        if not live.is_file() or f.read_bytes() != live.read_bytes():
            return False
    return found


def discover_scripts(repo_root: Path) -> list[dict]:
    """Return sorted list of {name, script, applied, label, description} for all staging modules."""
    results = []
    for script in sorted(repo_root.glob("aria-*/apply_*.sh")):
        module_name = script.parent.name
        label, description = _extract_script_info(script)
        results.append({
            "name": module_name,
            "script": str(script),
            "applied": _is_applied(repo_root, module_name),
            "label": label,
            "description": description,
        })
    return results


# ── Screen ────────────────────────────────────────────────────────────────────


class ApplyDashboardScreen(ModalScreen):
    """Ctrl+A → browse and run staged aria-*/apply_*.sh scripts.

    Two views:
      Run Queue — module list + live log output.
      Catalog   — read-only record of all modules with invariants.

    Keyboard: Escape / q closes (blocked while a script is running).
    After a successful apply, click "Quit Cockpit" to exit and restart.
    """

    BINDINGS = [
        Binding("escape", "close_apply", "close", show=False),
        Binding("q", "close_apply", "close", show=False),
    ]

    def __init__(self, repo_root: Path) -> None:
        super().__init__()
        self._repo_root = Path(repo_root)
        self._selected_name: str | None = None
        self._selected_path: str | None = None
        self._script_running = False

    # ── actions ───────────────────────────────────────────────────────────────

    def action_close_apply(self) -> None:
        if not self._script_running:
            self.app.pop_screen()

    # ── event handlers ────────────────────────────────────────────────────────

    def on_key(self, event) -> None:
        """Bulletproof escape — works even if a child widget has focus."""
        if event.key in ("escape", "q") and not self._script_running:
            event.stop()
            event.prevent_default()
            self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        btn_id = event.button.id or ""

        if btn_id == "apply-close":
            if not self._script_running:
                self.app.pop_screen()
        elif btn_id == "apply-quit":
            self.app.exit()
        elif btn_id == "apply-run":
            if self._selected_name and self._selected_path and not self._script_running:
                self._run_script(self._selected_name, self._selected_path)
        elif btn_id == "tab-run":
            self._show_view("run")
        elif btn_id == "tab-catalog":
            self._show_view("catalog")
        elif btn_id.startswith("script_"):
            name = event.button.name
            if name:
                self._select(name)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _show_view(self, view: str) -> None:
        self.query_one("#run-view", Vertical).display = (view == "run")
        self.query_one("#catalog-view", VerticalScroll).display = (view == "catalog")
        self.query_one("#tab-run", Button).variant = "primary" if view == "run" else "default"
        self.query_one("#tab-catalog", Button).variant = "primary" if view == "catalog" else "default"

    def _select(self, name: str) -> None:
        scripts = discover_scripts(self._repo_root)
        entry = next((s for s in scripts if s["name"] == name), None)
        if not entry:
            return
        self._selected_name = name
        self._selected_path = entry["script"]
        info = _CATALOG.get(name)
        run_btn = self.query_one("#apply-run", Button)
        run_btn.disabled = False
        label = info.label if info else (entry.get("label") or name)
        run_btn.label = f"Run  {label}"
        for btn in self.query(".script-btn"):
            btn.variant = "default"
        try:
            self.query_one(f"#script_{name.replace('-', '_')}", Button).variant = "warning"
        except Exception:  # noqa: BLE001
            pass

    # ── compose ───────────────────────────────────────────────────────────────

    def compose(self):  # noqa: C901
        scripts = discover_scripts(self._repo_root)
        pending = [s for s in scripts if not s["applied"]]
        applied_list = [s for s in scripts if s["applied"]]

        with Vertical(id="apply-modal"):
            # Title
            yield Static(
                f"Apply Dashboard  "
                f"[dim]({len(pending)} pending · {len(applied_list)} applied · "
                f"{len(scripts)} total)[/dim]",
                id="apply-title",
            )
            # Tab bar
            with Horizontal(id="tab-bar"):
                yield Button("Run Queue", id="tab-run", variant="primary")
                yield Button("Catalog", id="tab-catalog", variant="default")

            yield Rule()

            # ── Run view ──────────────────────────────────────────────────────
            with Vertical(id="run-view"):
                with VerticalScroll(id="apply-list"):
                    if pending:
                        yield Static("[yellow bold]○  Pending[/yellow bold]", classes="list-header")
                        for s in pending:
                            safe_id = f"script_{s['name'].replace('-', '_')}"
                            info = _CATALOG.get(s["name"])
                            btn_label = info.label if info else s.get("label") or s["name"]  # apply-menu-autoupdate-d
                            yield Button(
                                f"○  {btn_label}",
                                id=safe_id,
                                name=s["name"],
                                classes="script-btn pending-btn",
                            )
                    if applied_list:
                        yield Static("[green bold]✓  Applied[/green bold]", classes="list-header")
                        for s in applied_list:
                            safe_id = f"script_{s['name'].replace('-', '_')}"
                            info = _CATALOG.get(s["name"])
                            btn_label = info.label if info else s.get("label") or s["name"]  # apply-menu-autoupdate-d
                            yield Button(
                                f"✓  {btn_label}",
                                id=safe_id,
                                name=s["name"],
                                classes="script-btn applied-btn",
                            )
                    if not scripts:
                        yield Static("[dim]No aria-*/apply_*.sh scripts found.[/dim]")

                yield Static(
                    "[dim]○  Ready — select a module above, then click Run[/dim]",
                    id="apply-status",
                )
                yield RichLog(id="apply-log", highlight=True, markup=True, max_lines=500)

            # ── Catalog view (hidden by default) ──────────────────────────────
            with VerticalScroll(id="catalog-view"):
                yield Static(
                    "[bold]Module Catalog[/bold]  "
                    "[dim]— every module, what it added, and its invariants[/dim]",
                    id="catalog-title",
                )
                yield Rule()
                for s in scripts:
                    name = s["name"]
                    is_app = s["applied"]
                    info = _CATALOG.get(name)
                    sc = "green" if is_app else "yellow"
                    ch = "✓" if is_app else "○"
                    sw = "Applied" if is_app else "Pending"
                    label = info.label if info else s.get("label") or name

                    yield Static(
                        f"[{sc}]{ch}[/{sc}]  [bold]{label}[/bold]  "
                        f"[{sc} dim]{sw}[/{sc} dim]",
                        classes="catalog-module-header",
                    )

                    if info:
                        yield Static(
                            f"  [dim]{info.description}[/dim]",
                            classes="catalog-desc",
                        )
                        if info.added:
                            added_lines = "\n".join(
                                f"  [cyan]+[/cyan] {a}" for a in info.added
                            )
                            yield Static(
                                f"  [bold dim]Added:[/bold dim]\n{added_lines}",
                                classes="catalog-section",
                            )
                        if info.invariants:
                            inv_lines = "\n".join(
                                f"  [green]·[/green] {i}" for i in info.invariants
                            )
                            yield Static(
                                f"  [bold dim]Invariants:[/bold dim]\n{inv_lines}",
                                classes="catalog-section",
                            )
                    else:
                        _auto_desc = s.get("description") or ""
                        _fallback = (
                            f"  [dim]{_auto_desc}[/dim]"
                            if _auto_desc
                            else "  [dim]No catalog entry — see the apply script for details.[/dim]"
                        )
                        yield Static(_fallback, classes="catalog-desc")

                    yield Rule()

            # Footer
            yield Rule()
            with Horizontal(id="apply-footer"):
                yield Button(
                    "Select a module to run",
                    id="apply-run",
                    variant="success",
                    disabled=True,
                )
                yield Button(
                    "Quit Cockpit to load changes",
                    id="apply-quit",
                    variant="warning",
                )
                yield Button("Close (Esc / q)", id="apply-close", variant="primary")

    # ── worker ────────────────────────────────────────────────────────────────

    @work(thread=True)
    def _run_script(self, script_name: str, script_path: str) -> None:
        """Run the apply script in a background thread, streaming output to the log.

        All widget access goes through call_from_thread — never touch the DOM
        directly from a worker thread.
        """
        self._script_running = True

        # Obtain widget references on the main thread before doing any work.
        log: RichLog = self.call_from_thread(self.query_one, "#apply-log", RichLog)
        run_btn: Button = self.call_from_thread(self.query_one, "#apply-run", Button)
        close_btn: Button = self.call_from_thread(self.query_one, "#apply-close", Button)
        quit_btn: Button = self.call_from_thread(self.query_one, "#apply-quit", Button)
        status: Static = self.call_from_thread(self.query_one, "#apply-status", Static)

        def _start() -> None:
            run_btn.disabled = True
            close_btn.disabled = True
            quit_btn.display = False
            status.update(f"[yellow bold]Running {script_name}...[/yellow bold]")
            log.clear()
            log.write(f"[cyan bold]>> bash {script_path}[/cyan bold]")
            log.write("")

        self.call_from_thread(_start)

        rc: int = -1
        try:
            proc = subprocess.Popen(
                ["bash", script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=str(self._repo_root),
            )
            for line in proc.stdout or []:
                self.call_from_thread(log.write, line.rstrip("\n"))
            proc.wait()
            rc = proc.returncode

            def _finish() -> None:
                log.write("")
                if rc == 0:
                    log.write(
                        "[green bold]✓  Script completed successfully.[/green bold]"
                    )
                    log.write(
                        "[dim]  Restart cockpit to load new Python code into the running process.[/dim]"
                    )
                    status.update("[green bold]✓  Done — script completed successfully[/green bold]")
                    # Show the quit button so Kevin can restart cleanly
                    quit_btn.display = True
                    # Update the module's button from Pending to Applied in-place
                    safe_id = f"script_{script_name.replace('-', '_')}"
                    try:
                        btn = self.query_one(f"#{safe_id}", Button)
                        lbl = str(btn.label)
                        if lbl.startswith("○"):
                            btn.label = "✓" + lbl[1:]
                        btn.remove_class("pending-btn")
                        btn.add_class("applied-btn")
                    except Exception:  # noqa: BLE001
                        pass
                else:
                    log.write(f"[red bold]✗  Script exited with code {rc}[/red bold]")
                    status.update(f"[red]✗  Failed — exit code {rc}[/red]")

            self.call_from_thread(_finish)

        except Exception as exc:  # noqa: BLE001
            def _error(e: Exception = exc) -> None:
                log.write(f"[red]Error launching script: {e!r}[/red]")
                status.update(f"[red]✗  Error: {e}[/red]")

            self.call_from_thread(_error)

        finally:
            self._script_running = False

            def _cleanup() -> None:
                run_btn.disabled = False
                close_btn.disabled = False

            self.call_from_thread(_cleanup)

    # ── CSS ───────────────────────────────────────────────────────────────────

    DEFAULT_CSS = """
    ApplyDashboardScreen {
        align: center middle;
        background: $surface 60%;
    }
    #apply-modal {
        width: 110;
        height: 92%;
        padding: 1 2;
        border: thick $primary;
        background: $surface;
    }
    #apply-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #tab-bar {
        height: 3;
    }
    #tab-run {
        width: 18;
        margin-right: 1;
    }
    #tab-catalog {
        width: 14;
    }
    #run-view {
        height: 1fr;
    }
    #apply-list {
        height: 12;
        border: round $surface-lighten-2;
        padding: 0 1;
        margin-top: 1;
    }
    .list-header {
        margin-top: 1;
    }
    .script-btn {
        width: 100%;
        height: 3;
        margin: 0;
    }
    .pending-btn {
        border-left: outer $warning;
    }
    .applied-btn {
        opacity: 0.65;
    }
    #apply-status {
        height: 2;
        padding: 0 1;
        border: round $surface-lighten-1;
        margin-top: 1;
    }
    #apply-log {
        height: 1fr;
        border: round $surface-lighten-2;
        padding: 0 1;
        margin-top: 1;
        min-height: 6;
    }
    #catalog-view {
        height: 1fr;
        display: none;
        padding: 0 1;
        margin-top: 1;
    }
    #catalog-title {
        margin-bottom: 1;
    }
    .catalog-module-header {
        margin-top: 1;
        text-style: bold;
    }
    .catalog-desc {
        margin-left: 2;
        color: $text-muted;
    }
    .catalog-section {
        margin: 0 0 0 2;
    }
    #apply-footer {
        height: 3;
        margin-top: 1;
    }
    #apply-run {
        width: 2fr;
        margin-right: 1;
    }
    #apply-quit {
        width: 2fr;
        margin-right: 1;
        display: none;
    }
    #apply-close {
        width: 1fr;
    }
    """
