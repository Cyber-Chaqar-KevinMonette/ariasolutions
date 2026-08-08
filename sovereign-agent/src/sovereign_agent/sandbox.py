"""bwrap sandbox wrapper. Architecture §12.

Builds a bwrap command line for file-touching tools. The key safety property
is that $PROJECT_DIR is bound read-only when mode == BUSY, read-write otherwise
(architecture §12, third layer of BUSY safety).

This module returns the argv; the caller exec()s it. We don't use shell=True.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .config import SETTINGS
from .modes import Mode


def bwrap_available() -> bool:
    return shutil.which("bwrap") is not None


def build_bwrap_argv(
    *,
    mode: Mode,
    project_dir: Path | None,
    inner_argv: list[str],
    network: bool = False,
) -> list[str]:
    """Construct the full bwrap invocation as an argv list.

    Args:
        mode: active run mode (controls $PROJECT_DIR bind direction)
        project_dir: optional project directory to expose
        inner_argv: the command to run inside the sandbox
        network: if False, use --unshare-net; if True, leave network namespace alone.
                 web_fetch is the only tool that should set this True; others get
                 fully network-isolated.
    """
    home = Path.home()
    sandbox = SETTINGS.paths.sandbox_dir
    sandbox.mkdir(parents=True, exist_ok=True)

    argv: list[str] = ["bwrap"]
    # Read-only system binds for runtime
    for src in ("/usr", "/lib", "/lib64", "/etc/resolv.conf", "/etc/ssl"):
        if Path(src).exists():
            argv += ["--ro-bind", src, src]

    argv += [
        "--tmpfs", "/tmp",
        "--proc", "/proc",
        "--dev", "/dev",
    ]

    # Sandbox dir — always read-write. This is the agent's writable scope.
    argv += ["--bind", str(sandbox), str(home / "work")]

    # Project dir — mode-conditional
    if project_dir is not None:
        bind_flag = "--ro-bind" if mode == Mode.BUSY else "--bind"
        argv += [bind_flag, str(project_dir), str(project_dir)]

    # Mask sensitive directories with /dev/null
    for sensitive in (".ssh", ".gnupg", ".aws", ".config/gh", ".docker"):
        target = home / sensitive
        argv += ["--ro-bind-try", "/dev/null", str(target)]

    # Namespace isolation
    argv += [
        "--unshare-pid",
        "--unshare-uts",
        "--unshare-ipc",
        "--unshare-cgroup-try",
        "--new-session",
        "--die-with-parent",
    ]
    if not network:
        argv += ["--unshare-net"]

    argv += ["--"]
    argv += inner_argv
    return argv
