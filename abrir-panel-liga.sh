#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

PANEL_SCRIPT="$SCRIPT_DIR/scripts/control-panel/app.py"

if command -v pgrep >/dev/null 2>&1; then
  pgrep -f "$PANEL_SCRIPT" | while IFS= read -r pid; do
    if [ "${pid:-}" != "$$" ]; then
      kill "$pid" 2>/dev/null || true
    fi
  done
fi

if [ -x "$SCRIPT_DIR/backend/venv/bin/python" ]; then
  PYTHON="$SCRIPT_DIR/backend/venv/bin/python"
else
  PYTHON="$(command -v python3 || command -v python)"
fi

exec "$PYTHON" "$PANEL_SCRIPT"
