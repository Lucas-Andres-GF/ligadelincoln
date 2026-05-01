#!/bin/bash
# Runner para generar placas de resultados
# Uso: ./generar_placas_resultados.sh [--fecha 11] [--categoria primera] [--force]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

source "$PROJECT_DIR/backend/.env" 2>/dev/null || true

export SUPABASE_URL
export SUPABASE_KEY
export OUTPUT_HOST="$PROJECT_DIR/placares_generados"
export ESCUDOS_HOST="$PROJECT_DIR/frontend/public/escudos_hd"

cd "$SCRIPT_DIR/generador-placas"

pip install --break-system-packages -q -r requirements.txt
python3 -m playwright install chromium >/dev/null

python3 generar_placas_resultados.py "$@"
