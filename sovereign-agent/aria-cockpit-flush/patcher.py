"""patcher.py — Workstream Gym #5: aria-cockpit-flush.

Two anchored, idempotent patches to cockpit/app.py:

  1. A shutdown flush (`on_unmount`): seals any turns still buffered in the
     ChunkRecorder (`seal_now()` existed precisely for this and had ZERO
     shutdown callers — up to 20 conversation turns were silently lost on
     every cockpit exit) and fsyncs pending events (`events.force_fsync()`
     is wired to agent-loop/session exit but was never wired to the
     cockpit's own exit path). All best-effort — shutdown must never fail
     because a flush did.

     Honest scope note: the transcript file itself needs no flush here —
     `_record()` opens/writes/closes per line, so there is no in-process
     buffer at exit; its only loss window is OS-level (power loss), which
     an exit hook can't help with.

  2. The mid-turn conversation error handler surfaces probe_ollama's
     reason_phrase when the failure smells like a backend/connection
     problem — a mid-turn Ollama drop used to render as an opaque
     "conversation error: ..." with no hint that Ollama was the cause,
     even though probe_ollama's actionable messages already existed.
"""
from __future__ import annotations

MARK = "cockpit-flush-d"


class PatchError(Exception):
    pass


def _replace_once(text: str, old: str, new: str, *, label: str) -> str:
    if text.count(old) != 1:
        raise PatchError(f"{label}: expected exactly 1 occurrence, found {text.count(old)}")
    return text.replace(old, new, 1)


# ═══════════════════════════════════════════════════════════════════════
# 1. Shutdown flush
# ═══════════════════════════════════════════════════════════════════════

UNMOUNT_ANCHOR = (
    "    def _refresh_cockpit_strips(self) -> None:  # command-menu-d\n"
)
UNMOUNT_NEW = (
    f"    def on_unmount(self) -> None:  # {MARK}\n"
    '        """Shutdown flush: seal any conversation turns still buffered in\n'
    "        the ChunkRecorder (up to 20 were silently lost on every exit\n"
    "        before this) and fsync pending events. Best-effort — shutdown\n"
    '        must never fail because a flush did."""\n'
    "        try:\n"
    "            if getattr(self, \"_chunk_recorder\", None) is not None:\n"
    "                self._chunk_recorder.seal_now()\n"
    "        except Exception:  # noqa: BLE001\n"
    "            pass\n"
    "        try:\n"
    "            from sovereign_agent.events import force_fsync\n"
    "\n"
    "            force_fsync()\n"
    "        except Exception:  # noqa: BLE001\n"
    "            pass\n"
    "\n"
    "    def _refresh_cockpit_strips(self) -> None:  # command-menu-d\n"
)


# ═══════════════════════════════════════════════════════════════════════
# 2. Ollama-aware mid-turn error message
# ═══════════════════════════════════════════════════════════════════════

ERROR_ANCHOR = (
    "        except Exception as exc:  # noqa: BLE001\n"
    '            self._write_meta(f"[red]conversation error: {exc!r}[/red]")\n'
    "        finally:\n"
    "            self._busy = False\n"
    "            self._proc = None\n"
)
ERROR_NEW = (
    "        except Exception as exc:  # noqa: BLE001\n"
    f"            hint = \"\"  # {MARK}: name the cause when the model backend is down\n"
    "            try:\n"
    "                import httpx\n"
    "\n"
    "                if isinstance(exc, (httpx.HTTPError, ConnectionError, TimeoutError, OSError)):\n"
    "                    from sovereign_agent.ollama_client import probe_ollama\n"
    "\n"
    "                    probe = await probe_ollama()\n"
    "                    if not probe.healthy:\n"
    "                        hint = f\" — {probe.reason_phrase()}\"\n"
    "            except Exception:  # noqa: BLE001\n"
    "                pass\n"
    '            self._write_meta(f"[red]conversation error: {exc!r}{hint}[/red]")\n'
    "        finally:\n"
    "            self._busy = False\n"
    "            self._proc = None\n"
)


def patch_app(text: str) -> tuple[str, bool]:
    if MARK in text:
        return text, False
    text = _replace_once(text, UNMOUNT_ANCHOR, UNMOUNT_NEW, label="app.py on_unmount anchor")
    text = _replace_once(text, ERROR_ANCHOR, ERROR_NEW, label="app.py error-handler anchor")
    return text, True
