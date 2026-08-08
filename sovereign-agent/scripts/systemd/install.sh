#!/usr/bin/env bash
# install.sh — Aria's never-dies runtime (systemd user units)
# ===========================================================
# Installs + starts aria-bot.service and aria-duty.service, and retires
# the OLD sovereign-agent.service (2-day-old venv, pre-dates the shop —
# Kevin approved replacing it). Safe to re-run anytime.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"

echo "🛠 installing units → $UNIT_DIR"
cp "$HERE/aria-bot.service" "$HERE/aria-duty.service" \
   "$HERE/aria-backup.service" "$HERE/aria-backup.timer" "$UNIT_DIR/"
systemctl --user daemon-reload

# retire the old runner (old venv, old code) — Kevin-approved replacement
if systemctl --user list-unit-files | grep -q '^sovereign-agent.service'; then
  echo "🌙 retiring old sovereign-agent.service (replaced by aria-bot/duty)"
  systemctl --user disable --now sovereign-agent.service || true
fi

systemctl --user enable --now aria-bot.service aria-duty.service
systemctl --user enable --now aria-backup.timer
# keep user services alive after logout/reboot
loginctl enable-linger "$USER" 2>/dev/null || true

echo
systemctl --user --no-pager --plain status aria-bot.service aria-duty.service \
  | grep -E "aria-|Active:" || true
echo
echo "✅ Aria survives logouts + reboots now."
echo "   watch her:  journalctl --user -u aria-bot -f"
echo "   stop fast:  systemctl --user stop aria-duty aria-bot"
