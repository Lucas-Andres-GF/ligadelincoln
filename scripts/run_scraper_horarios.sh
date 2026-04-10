#!/bin/bash
# Runner para ejecutar scraper de horarios
# Uso: ./run_scraper_horarios.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR/backend/scripts"

source "$PROJECT_DIR/backend/.env" 2>/dev/null || true

export SUPABASE_URL
export SUPABASE_KEY

pip install -q requests beautifulsoup4 supabase python-dotenv

python3 scraper_horarios.py