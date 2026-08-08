"""model_release — free the GPU when she's done (no more zombie VRAM).

Kevin's find: after exiting a chat, `nvidia`/the cockpit still showed ~71%
VRAM in use. That's Ollama's keep-alive doing its job TOO well — the model
stays resident for the configured window (~30 min here) so the next call is
instant, even though nobody is coming back. On an 8GB card that's most of
the GPU held hostage.

The honest fix is Ollama's own API, not process games:

  • `loaded_models()` — GET `/api/ps`: what's resident right now.
  • `release_models()` — POST `/api/generate` with `keep_alive: 0` per
    loaded model: Ollama unloads it immediately and VRAM returns. This is
    the documented unload mechanism (same as `ollama stop`), zero risk —
    the next real call simply reloads (a few seconds on this card).

Wired in two places:
  • `sov vram free` — see + release on demand.
  • cockpit exit — best-effort release, so closing her actually
    frees the machine. Fire-and-forget: an Ollama hiccup never blocks quit.
"""
from __future__ import annotations

import json
import urllib.request

__all__ = ["loaded_models", "release_models", "release_all", "render_vram_report"]

_TIMEOUT_S = 6.0


def _host() -> str:
    try:
        from sovereign_agent.config import SETTINGS
        return SETTINGS.ollama_host.rstrip("/")
    except Exception:  # noqa: BLE001
        return "http://127.0.0.1:11434"


def _default_get(url: str) -> dict:  # pragma: no cover - network
    with urllib.request.urlopen(url, timeout=_TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))


def _default_post(url: str, payload: dict) -> None:  # pragma: no cover - network
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S):
        pass


def loaded_models(getter=None) -> list[dict]:
    """What's resident in VRAM right now: [{name, size_mb, until}]. Never
    raises — no Ollama just means nothing is loaded."""
    get = getter or _default_get
    try:
        data = get(f"{_host()}/api/ps")
        out = []
        for m in data.get("models", []) or []:
            out.append({
                "name": str(m.get("name") or m.get("model") or "?"),
                "size_mb": int(int(m.get("size_vram") or m.get("size") or 0)
                               / (1024 * 1024)),
                "until": str(m.get("expires_at") or ""),
            })
        return out
    except Exception:  # noqa: BLE001
        return []


def release_models(names: list[str], poster=None) -> list[tuple[str, bool]]:
    """Ask Ollama to unload each model NOW (keep_alive=0). Returns
    [(name, released?)]. Never raises."""
    post = poster or _default_post
    results: list[tuple[str, bool]] = []
    for name in names:
        try:
            post(f"{_host()}/api/generate",
                 {"model": name, "keep_alive": 0})
            results.append((name, True))
        except Exception:  # noqa: BLE001
            results.append((name, False))
    return results


def release_all(getter=None, poster=None) -> list[tuple[str, bool]]:
    """Release every resident model. The cockpit calls this on exit."""
    return release_models([m["name"] for m in loaded_models(getter)], poster)


def render_vram_report(getter=None) -> str:
    models = loaded_models(getter)
    if not models:
        return "🎮 VRAM: no models resident — the GPU is free."
    lines = ["🎮 Models resident in VRAM:"]
    for m in models:
        until = f" (kept until {m['until'][:19]})" if m["until"] else ""
        lines.append(f"  • {m['name']} — {m['size_mb']} MB{until}")
    lines.append("Free them now: `sov vram free` (they reload on next use).")
    return "\n".join(lines)
