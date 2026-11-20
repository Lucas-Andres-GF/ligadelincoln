#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ${1:-} == --user-disciplina ]]; then
    if [[ $(id -un) != gallardo || $(loginctl show-user gallardo -p Linger --value) != yes ]]; then
        echo 'Se requiere la sesión de gallardo con Linger habilitado.' >&2
        exit 1
    fi
    for unit in scraper-amarillas scraper-boletines; do
        if [[ $(systemctl show "$unit.timer" -p LoadState --value) == loaded ]]; then
            echo "Ya existe el temporizador de sistema $unit.timer." >&2
            exit 1
        fi
    done
    unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    install -d -m 0755 "$unit_dir"
    for unit in scraper-amarillas scraper-boletines; do
        sed '/^User=/d; /^Group=/d' "$SCRIPT_DIR/$unit.service" > "$unit_dir/$unit.service"
        install -m 0644 "$SCRIPT_DIR/$unit.timer" "$unit_dir/$unit.timer"
    done
    systemctl --user daemon-reload
    systemctl --user enable --now scraper-amarillas.timer scraper-boletines.timer
    systemctl --user list-timers --all scraper-amarillas.timer scraper-boletines.timer
    exit
fi

install -m 0644 "$SCRIPT_DIR/scraper-resultados.service" /etc/systemd/system/scraper-resultados.service
install -m 0644 "$SCRIPT_DIR/scraper-resultados.timer" /etc/systemd/system/scraper-resultados.timer
install -m 0644 "$SCRIPT_DIR/scraper-alineaciones.service" /etc/systemd/system/scraper-alineaciones.service
install -m 0644 "$SCRIPT_DIR/scraper-alineaciones.timer" /etc/systemd/system/scraper-alineaciones.timer
install -m 0644 "$SCRIPT_DIR/scraper-suspensiones.service" /etc/systemd/system/scraper-suspensiones.service
install -m 0644 "$SCRIPT_DIR/scraper-suspensiones.timer" /etc/systemd/system/scraper-suspensiones.timer
install -m 0644 "$SCRIPT_DIR/scraper-worker.service" /etc/systemd/system/scraper-worker.service

discipline_user_units="/home/gallardo/.config/systemd/user/timers.target.wants"
discipline_system_timers=()
for unit in scraper-amarillas scraper-boletines; do
    if [[ -L "$discipline_user_units/$unit.timer" ]]; then
        echo "Se conserva el temporizador de usuario $unit.timer."
        continue
    fi
    install -m 0644 "$SCRIPT_DIR/$unit.service" "/etc/systemd/system/$unit.service"
    install -m 0644 "$SCRIPT_DIR/$unit.timer" "/etc/systemd/system/$unit.timer"
    discipline_system_timers+=("$unit.timer")
done

systemctl daemon-reload
systemctl enable --now scraper-resultados.timer
systemctl enable --now scraper-alineaciones.timer
systemctl enable --now scraper-suspensiones.timer
systemctl enable --now scraper-worker.service
if (( ${#discipline_system_timers[@]} )); then
    systemctl enable --now "${discipline_system_timers[@]}"
fi
systemctl list-timers --all | grep scraper || true
systemctl --no-pager --full status scraper-worker.service || true
