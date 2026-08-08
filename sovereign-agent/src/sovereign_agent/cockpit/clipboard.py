"""clipboard — read the system clipboard, so pasting a secret is one click.

Terminals are the one place "paste" is unobvious: Ctrl+V doesn't work, and
the working combo (usually Ctrl+Shift+V, or right-click) differs by
terminal. For the Key Vault that friction lands exactly where we least want
it — while Kevin is holding a secret. So the vault gets a 📋 button that
reads the clipboard directly.

Reading uses the standard system tools, tried in order (covers both display
servers): `wl-paste` (Wayland) → `xclip` (X11) → `xsel` (X11). No new
Python dependency; the runner is injectable so tests never touch a real
clipboard. Never raises; on failure the detail string says exactly which
tools were tried, so the fix ("install wl-clipboard or xclip") is obvious.
"""
from __future__ import annotations

import subprocess

__all__ = ["read_clipboard", "CLIPBOARD_TOOLS"]

CLIPBOARD_TOOLS: tuple[list[str], ...] = (
    ["wl-paste", "--no-newline"],                 # Wayland
    ["xclip", "-selection", "clipboard", "-o"],   # X11
    ["xsel", "--clipboard", "--output"],          # X11 (alt)
)


def read_clipboard(runner=None) -> tuple[str | None, str]:
    """Return (text, detail). text is None when nothing could be read;
    detail names what worked or everything that was tried. Never raises."""

    def _default_runner(cmd):  # pragma: no cover - exercised via injection
        return subprocess.run(cmd, capture_output=True, timeout=3.0)

    run = runner or _default_runner
    tried: list[str] = []
    for cmd in CLIPBOARD_TOOLS:
        try:
            proc = run(cmd)
            if getattr(proc, "returncode", 1) == 0:
                raw = proc.stdout
                text = (raw.decode("utf-8", "replace")
                        if isinstance(raw, bytes) else str(raw or ""))
                if text.strip():
                    return text, f"via {cmd[0]}"
                tried.append(f"{cmd[0]}: clipboard empty")
            else:
                tried.append(f"{cmd[0]}: exit {getattr(proc, 'returncode', '?')}")
        except FileNotFoundError:
            tried.append(f"{cmd[0]}: not installed")
        except Exception as exc:  # noqa: BLE001
            tried.append(f"{cmd[0]}: {type(exc).__name__}")
    return None, "; ".join(tried) if tried else "no clipboard tool available"
