#!/bin/bash
# Runner para ejecutar scraper de resultados
# Uso: ./run_scraper_resultados.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR/backend/scripts"

source "$PROJECT_DIR/backend/.env" 2>/dev/null || true

export SUPABASE_URL
export SUPABASE_KEY

HOUR=$(date +%H)
DAY=$(date +%w)

if [[ "$DAY" != "6" && "$DAY" != "0" ]]; then
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') === No es día de partido (sáb/dom), omitiendo" >> /home/gallardo/logs/scraper_resultados.log 2>&1
    exit 0
fi

if [[ "$HOUR" -lt 14 || "$HOUR" -ge 21 ]]; then
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') === Outside horario (14-21hs), omitiendo" >> /home/gallardo/logs/scraper_resultados.log 2>&1
    exit 0
fi

pip install --break-system-packages -q requests beautifulsoup4 supabase

echo "=== $(date '+%Y-%m-%d %H:%M:%S') ===" >> /home/gallardo/logs/scraper_resultados.log 2>&1

python3 scraper_resultados.py >> /home/gallardo/logs/scraper_resultados.log 2>&1