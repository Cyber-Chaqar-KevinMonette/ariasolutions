"""Patch mode_controller.py — M64: emit schedule-inject-error-d instead of silent pass.

Changes line 223-224 from:
    except Exception:  # noqa: BLE001
        pass

To:
    except Exception as _sched_err:  # noqa: BLE001
        emit_event(
            "schedule-inject-error-d",
            plane="control",
            trace_id="controller",
            payload={"error": str(_sched_err)},
        )

The exception is still caught (schedule is non-critical).
The failure is now auditable.
"""
import sys
from pathlib import Path

path = Path(sys.argv[1])
src = path.read_text()

MARKER = "schedule-inject-error-d"
if MARKER in src:
    print("  already patched — skipping")
    sys.exit(0)

OLD = (
    "        except Exception:  # noqa: BLE001\n"
    "            pass\n"
    "\n"
    "        tasks = read_backlog()"
)
NEW = (
    "        except Exception as _sched_err:  # noqa: BLE001\n"
    "            emit_event(\n"
    '                "schedule-inject-error-d",\n'
    '                plane="control",\n'
    '                trace_id="controller",\n'
    "                payload={\"error\": str(_sched_err)},\n"
    "            )\n"
    "\n"
    "        tasks = read_backlog()"
)

if OLD not in src:
    print(f"ERROR: expected pattern not found in {path}", file=sys.stderr)
    print("Snippet around 'except Exception' in cron block:", file=sys.stderr)
    for i, line in enumerate(src.splitlines(), 1):
        if "check_and_inject_due" in line or "BLE001" in line or "pass" in line[:30]:
            print(f"  {i}: {line}", file=sys.stderr)
    sys.exit(1)

patched = src.replace(OLD, NEW, 1)
path.write_text(patched)
print(f"  patched {path}")
