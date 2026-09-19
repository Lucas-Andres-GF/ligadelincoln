#!/bin/bash
# Compatibility entry point; active systemd service calls the runner directly.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec /bin/bash "$SCRIPT_DIR/run_scraper_resultados.sh"
