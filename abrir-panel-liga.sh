#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

PANEL_SCRIPT="$SCRIPT_DIR/scripts/control-panel/app.py"

resolve_python() {
  if [ -n "${LIGA_PYTHON:-}" ]; then
    candidate=$LIGA_PYTHON
    if [ ! -f "$candidate" ]; then
      case "$candidate" in
        /*) ;;
        *) candidate="$SCRIPT_DIR/$candidate" ;;
      esac
    fi
    if [ -f "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
    echo "ERROR: LIGA_PYTHON no existe o no es un archivo: $candidate" >&2
    return 1
  fi

  for candidate in \
    "$SCRIPT_DIR/backend/venv/bin/python" \
    "$SCRIPT_DIR/backend/venv/Scripts/python.exe"; do
    if [ -f "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  echo "ERROR: no se encontró Python en backend/venv/bin/python ni backend/venv/Scripts/python.exe" >&2
  return 1
}

PYTHON=$(resolve_python)

if command -v pgrep >/dev/null 2>&1; then
  pgrep -f "$PANEL_SCRIPT" | while IFS= read -r pid; do
    if [ "${pid:-}" != "$$" ]; then
      kill "$pid" 2>/dev/null || true
    fi
  done
fi

exec "$PYTHON" "$PANEL_SCRIPT"
