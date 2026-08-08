#!/usr/bin/env bash
# apply_movie_series.sh — Movie Studio Phase 3 (Series/Season, episode
# render session, character bible, quality gate, frame continuity, and
# Phase C's ffmpeg assembly tool). Flat modules directly under
# src/sovereign_agent/ (matching movie_projects.py's existing convention),
# not a subpackage. Phase C ships ONE tool (assemble_movie_episode), so
# this apply script now also patches tools/__init__.py (anchored, idempotent).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$REPO_ROOT"
STAGING="$REPO_ROOT/aria-movie-series"; BACKUP_DIR="$STAGING/backups/$(date +%Y%m%d_%H%M%S)"
VENV_PY="$REPO_ROOT/.venv/bin/python"; TOOLS_INIT="$REPO_ROOT/src/sovereign_agent/tools/__init__.py"
SRC="$REPO_ROOT/src/sovereign_agent"

MODULES=(movie_series.py movie_character_bible.py movie_episode_render.py
         movie_clip_quality_gate.py movie_video_continuity.py
         movie_clip_generation.py movie_episode_render_runner.py)
TOOLS=(assemble_movie_episode.py)
TESTS=(test_movie_series.py test_movie_character_bible.py test_movie_episode_render.py
       test_movie_clip_quality_gate.py test_movie_video_continuity.py
       test_movie_episode_render_runner.py test_assemble_movie_episode.py)

echo "=== aria-movie-series apply ==="
if pgrep -af "cockpit" 2>/dev/null | grep -E "bin/sovereign cockpit|sovereign_agent.*cockpit|[s]overeign cockpit" | grep -vE "pgrep|grep|apply_|bash -c" >/dev/null; then
  echo "ERROR: cockpit running. Stop it first."; exit 1
fi
[[ -f "$VENV_PY" ]] || { echo "ERROR: venv missing."; exit 1; }

mkdir -p "$BACKUP_DIR"
for m in "${MODULES[@]}"; do
  [[ -f "$SRC/$m" ]] && cp "$SRC/$m" "$BACKUP_DIR/$m.bak"
done
for t in "${TOOLS[@]}"; do
  [[ -f "$SRC/tools/$t" ]] && cp "$SRC/tools/$t" "$BACKUP_DIR/$t.bak"
done
cp "$TOOLS_INIT" "$BACKUP_DIR/tools_init.py.bak"

echo "→ Copying payload modules..."
for m in "${MODULES[@]}"; do
  cp "$STAGING/payload/src/sovereign_agent/$m" "$SRC/$m"
done
for t in "${TOOLS[@]}"; do
  cp "$STAGING/payload/src/sovereign_agent/tools/$t" "$SRC/tools/$t"
done

echo "→ Registering AssembleMovieEpisodeTool..."
"$VENV_PY" - "$TOOLS_INIT" <<'PYEOF'
import sys
from pathlib import Path
p = Path(sys.argv[1]); t = p.read_text()
if "# movie-focus-d-import" in t:
    print("SKIP: already patched")
else:
    anchor = next(l for l in t.splitlines() if "movie-studio-d Phase 2" in l)
    t = t.replace(
        anchor,
        anchor + "\nfrom .assemble_movie_episode import AssembleMovieEpisodeTool  # movie-focus-d-import",
        1,
    )
    allk = next(l for l in t.splitlines() if '"GenerateMovieClipTool"' in l)
    t = t.replace(
        allk,
        allk + '\n    "AssembleMovieEpisodeTool",  # movie-focus-d-all',
        1,
    )
    p.write_text(t)
    print("Patched tools/__init__.py")
PYEOF

echo "→ Compile check..."
"$VENV_PY" -m py_compile "${MODULES[@]/#/$SRC/}" "${TOOLS[@]/#/$SRC/tools/}" "$TOOLS_INIT"

echo "→ Copying tests..."
for t in "${TESTS[@]}"; do
  cp "$STAGING/tests/$t" "$REPO_ROOT/tests/$t"
done

echo "→ Running tests..."
"$VENV_PY" -m pytest "${TESTS[@]/#/$REPO_ROOT/tests/}" -q || {
  echo "APPLY-FAIL: applied tests did not pass"; exit 1;
}

echo "=== aria-movie-series applied. Reversible: backups at $BACKUP_DIR 💛 ==="
