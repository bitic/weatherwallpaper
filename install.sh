#!/usr/bin/env bash
set -e

# Path to project directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

echo "=== Installing Systemd user services ==="
mkdir -p "$SYSTEMD_USER_DIR"

# Create symbolic links to project directory
ln -sf "$PROJECT_DIR/systemd/synoptic-bg.service" "$SYSTEMD_USER_DIR/synoptic-bg.service"
ln -sf "$PROJECT_DIR/systemd/synoptic-bg.timer" "$SYSTEMD_USER_DIR/synoptic-bg.timer"

echo "Symlinks created at $SYSTEMD_USER_DIR:"
ls -l "$SYSTEMD_USER_DIR/synoptic-bg."*

# Reload systemd user daemon and enable timer
systemctl --user daemon-reload
systemctl --user enable --now synoptic-bg.timer

echo ""
echo "=== Timer successfully activated! ==="
systemctl --user list-timers synoptic-bg.timer
