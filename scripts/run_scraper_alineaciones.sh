#!/bin/bash
# Scheduled mutation runner for tournament Primera lineup updates.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="${SCRAPER_LOG_DIR:-/home/gallardo/logs}"
LOG_FILE="$LOG_DIR/scraper_alineaciones.log"

if [[ -f "$PROJECT_DIR/backend/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/backend/.env"
    set +a
fi

resolve_python() {
    local candidate

    if [[ -n "${LIGA_PYTHON:-}" ]]; then
        candidate="$LIGA_PYTHON"
        if [[ ! -f "$candidate" && "$candidate" != /* ]]; then
            candidate="$PROJECT_DIR/$candidate"
        fi
        if [[ -f "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
        echo "ERROR: LIGA_PYTHON no existe o no es un archivo: $candidate" >&2
        return 1
    fi

    for candidate in \
        "$PROJECT_DIR/backend/venv/Scripts/python.exe" \
        "$PROJECT_DIR/backend/venv/bin/python"; do
        if [[ -f "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done

    echo "ERROR: no se encontró Python en backend/venv/Scripts/python.exe ni backend/venv/bin/python" >&2
    return 1
}

mkdir -p -- "$LOG_DIR"

ACTIVE_TORNEO_ID="${ACTIVE_TORNEO_ID:-}"
if [[ ! "$ACTIVE_TORNEO_ID" =~ ^[0-9]+$ || "$ACTIVE_TORNEO_ID" =~ ^0+$ ]]; then
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') === ERROR: ACTIVE_TORNEO_ID debe ser un entero decimal positivo" >> "$LOG_FILE" 2>&1
    exit 2
fi

PYTHON_BIN="$(resolve_python)"

HOUR="$(date +%H)"
DAY="$(date +%w)"

if [[ "${LIGA_FORCE:-}" != "1" ]]; then
    if [[ "$DAY" != "6" && "$DAY" != "0" ]]; then
        echo "=== $(date '+%Y-%m-%d %H:%M:%S') === No es día de partido (sáb/dom), omitiendo (usá LIGA_FORCE=1 para forzar)" >> "$LOG_FILE" 2>&1
        exit 0
    fi

    if [[ "$HOUR" -lt 13 || "$HOUR" -ge 22 ]]; then
        echo "=== $(date '+%Y-%m-%d %H:%M:%S') === Fuera de horario (13-22hs ARG), omitiendo" >> "$LOG_FILE" 2>&1
        exit 0
    fi
fi

echo "=== $(date '+%Y-%m-%d %H:%M:%S') === Ejecutando scraper de alineaciones para torneo $ACTIVE_TORNEO_ID" >> "$LOG_FILE" 2>&1
if "$PYTHON_BIN" "$PROJECT_DIR/backend/scripts/scraper_alineaciones.py" \
    --torneo-id "$ACTIVE_TORNEO_ID" \
    --execute >> "$LOG_FILE" 2>&1; then
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') === Scraper de alineaciones completado" >> "$LOG_FILE" 2>&1
else
    status=$?
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') === ERROR: scraper de alineaciones falló con código $status" >> "$LOG_FILE" 2>&1
    exit "$status"
fi
