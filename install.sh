#!/usr/bin/env bash
set -e

# Path al directori del projecte
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"

echo "=== Instal·lant serveis de Systemd per a l'usuari ==="
mkdir -p "$SYSTEMD_USER_DIR"

# Crear els enllaços simbòlics cap a la carpeta del projecte
ln -sf "$PROJECT_DIR/systemd/synoptic-bg.service" "$SYSTEMD_USER_DIR/synoptic-bg.service"
ln -sf "$PROJECT_DIR/systemd/synoptic-bg.timer" "$SYSTEMD_USER_DIR/synoptic-bg.timer"

echo "Enllaços creats a $SYSTEMD_USER_DIR:"
ls -l "$SYSTEMD_USER_DIR/synoptic-bg."*

# Recarregar systemd de l'usuari i activar el temporitzador
systemctl --user daemon-reload
systemctl --user enable --now synoptic-bg.timer

echo ""
echo "=== Temporitzador activat correctament! ==="
systemctl --user list-timers synoptic-bg.timer
