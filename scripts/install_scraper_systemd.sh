#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install -m 0644 "$SCRIPT_DIR/scraper-resultados.service" /etc/systemd/system/scraper-resultados.service
install -m 0644 "$SCRIPT_DIR/scraper-resultados.timer" /etc/systemd/system/scraper-resultados.timer
install -m 0644 "$SCRIPT_DIR/scraper-alineaciones.service" /etc/systemd/system/scraper-alineaciones.service
install -m 0644 "$SCRIPT_DIR/scraper-alineaciones.timer" /etc/systemd/system/scraper-alineaciones.timer
install -m 0644 "$SCRIPT_DIR/scraper-worker.service" /etc/systemd/system/scraper-worker.service

systemctl daemon-reload
systemctl enable --now scraper-resultados.timer
systemctl enable --now scraper-alineaciones.timer
systemctl enable --now scraper-worker.service
systemctl list-timers --all | grep scraper || true
systemctl --no-pager --full status scraper-worker.service || true
