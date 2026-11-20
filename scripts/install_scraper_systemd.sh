#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ${1:-} == --user-disciplina || ${1:-} == --user-goleadores ]]; then
    if [[ $(id -un) != gallardo || $(loginctl show-user gallardo -p Linger --value) != yes ]]; then
        echo 'Se requiere la sesión de gallardo con Linger habilitado.' >&2
        exit 1
    fi
    units=(scraper-amarillas scraper-boletines)
    if [[ $1 == --user-goleadores ]]; then
        units=(scraper-goleadores)
    fi
    timers=("${units[@]/%/.timer}")
    for unit in "${units[@]}"; do
        if [[ $(systemctl show "$unit.timer" -p LoadState --value) == loaded ]]; then
            echo "Ya existe el temporizador de sistema $unit.timer." >&2
            exit 1
        fi
    done
    unit_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    install -d -m 0755 "$unit_dir"
    for unit in "${units[@]}"; do
        sed '/^User=/d; /^Group=/d' "$SCRIPT_DIR/$unit.service" > "$unit_dir/$unit.service"
        install -m 0644 "$SCRIPT_DIR/$unit.timer" "$unit_dir/$unit.timer"
    done
    systemctl --user daemon-reload
    systemctl --user enable --now "${timers[@]}"
    systemctl --user list-timers --all "${timers[@]}"
    exit
fi

install -m 0644 "$SCRIPT_DIR/scraper-resultados.service" /etc/systemd/system/scraper-resultados.service
install -m 0644 "$SCRIPT_DIR/scraper-resultados.timer" /etc/systemd/system/scraper-resultados.timer
install -m 0644 "$SCRIPT_DIR/scraper-alineaciones.service" /etc/systemd/system/scraper-alineaciones.service
install -m 0644 "$SCRIPT_DIR/scraper-alineaciones.timer" /etc/systemd/system/scraper-alineaciones.timer
install -m 0644 "$SCRIPT_DIR/scraper-suspensiones.service" /etc/systemd/system/scraper-suspensiones.service
install -m 0644 "$SCRIPT_DIR/scraper-suspensiones.timer" /etc/systemd/system/scraper-suspensiones.timer
install -m 0644 "$SCRIPT_DIR/scraper-worker.service" /etc/systemd/system/scraper-worker.service

user_units="/home/gallardo/.config/systemd/user/timers.target.wants"
system_timers=()
for unit in scraper-amarillas scraper-boletines scraper-goleadores; do
    if [[ -L "$user_units/$unit.timer" ]]; then
        echo "Se conserva el temporizador de usuario $unit.timer."
        continue
    fi
    install -m 0644 "$SCRIPT_DIR/$unit.service" "/etc/systemd/system/$unit.service"
    install -m 0644 "$SCRIPT_DIR/$unit.timer" "/etc/systemd/system/$unit.timer"
    system_timers+=("$unit.timer")
done

systemctl daemon-reload
systemctl enable --now scraper-resultados.timer
systemctl enable --now scraper-alineaciones.timer
systemctl enable --now scraper-suspensiones.timer
systemctl enable --now scraper-worker.service
if (( ${#system_timers[@]} )); then
    systemctl enable --now "${system_timers[@]}"
fi
systemctl list-timers --all | grep scraper || true
systemctl --no-pager --full status scraper-worker.service || true
