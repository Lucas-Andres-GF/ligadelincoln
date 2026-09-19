#!/bin/bash
# Scheduled mutation runner for tournament schedule updates.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

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

ACTIVE_TORNEO_ID="${ACTIVE_TORNEO_ID:-}"
if [[ ! "$ACTIVE_TORNEO_ID" =~ ^[0-9]+$ || "$ACTIVE_TORNEO_ID" =~ ^0+$ ]]; then
    echo "ERROR: ACTIVE_TORNEO_ID debe ser un entero decimal positivo" >&2
    exit 2
fi

PYTHON_BIN="$(resolve_python)"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') === Ejecutando scraper de horarios para torneo $ACTIVE_TORNEO_ID"
"$PYTHON_BIN" "$PROJECT_DIR/backend/scripts/scraper_horarios.py" \
    --torneo-id "$ACTIVE_TORNEO_ID" \
    --execute
