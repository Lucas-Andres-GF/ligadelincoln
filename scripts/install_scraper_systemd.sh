#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install -m 0644 "$SCRIPT_DIR/scraper-resultados.service" /etc/systemd/system/scraper-resultados.service
install -m 0644 "$SCRIPT_DIR/scraper-resultados.timer" /etc/systemd/system/scraper-resultados.timer

systemctl daemon-reload
systemctl enable --now scraper-resultados.timer
systemctl list-timers --all | grep scraper || true
