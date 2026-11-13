#!/bin/bash
# ==============================================================================
# NavosEdge — Parent Manager Server Launcher (Linux / macOS / Windows Git Bash)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVER_VENV="$PROJECT_DIR/Intelligence/Server/venv"

PYTHON_BIN=""
for cand in \
    "$SCRIPT_DIR/.venv/Scripts/python.exe" \
    "$SCRIPT_DIR/.venv/bin/python3" \
    "$SCRIPT_DIR/venv/Scripts/python.exe" \
    "$SCRIPT_DIR/venv/bin/python3" \
    "$SERVER_VENV/Scripts/python.exe" \
    "$SERVER_VENV/bin/python3" \
    "$PROJECT_DIR/Intelligence/Server/.venv/Scripts/python.exe" \
    "$PROJECT_DIR/Intelligence/Server/.venv/bin/python3"; do
    if [ -x "$cand" ] || [ -f "$cand" ]; then
        PYTHON_BIN="$cand"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    for cmd in python3 python; do
        if command -v "$cmd" >/dev/null 2>&1 && "$cmd" -c "import sys" >/dev/null 2>&1; then
            PYTHON_BIN="$cmd"
            break
        fi
    done
fi

if [ -z "$PYTHON_BIN" ]; then
    echo "[ERROR] No working Python interpreter found. Install Python 3.10+ or create a venv."
    exit 1
fi

PORT="${NAVOS_MANAGER_PORT:-8430}"
HOST="${NAVOS_MANAGER_HOST:-0.0.0.0}"
DISPLAY_HOST="$HOST"
if [ "$DISPLAY_HOST" = "0.0.0.0" ]; then
    DISPLAY_HOST="127.0.0.1"
fi

case "$(uname -s 2>/dev/null || echo unknown)" in
    MINGW*|MSYS*|CYGWIN*)
        if command -v cygpath >/dev/null 2>&1; then
            PY_SCRIPT_DIR="$(cygpath -w "$SCRIPT_DIR")"
            PY_PROJECT_DIR="$(cygpath -w "$PROJECT_DIR")"
        else
            PY_SCRIPT_DIR="$SCRIPT_DIR"
            PY_PROJECT_DIR="$PROJECT_DIR"
        fi
        MANAGER_PYTHONPATH="$PY_SCRIPT_DIR;$PY_PROJECT_DIR"
        ;;
    *)
        MANAGER_PYTHONPATH="$SCRIPT_DIR:$PROJECT_DIR"
        ;;
esac

echo "============================================================"
echo "      NavosEdge Parent Manager Server & Web Dashboard"
echo "============================================================"
echo "  * Python:            $PYTHON_BIN"
echo "  * Manager API:       http://$DISPLAY_HOST:$PORT/api/v1/overview"
echo "  * React Dashboard:   http://$DISPLAY_HOST:$PORT/"
echo "============================================================"

cd "$PROJECT_DIR"
PYTHONPATH="$MANAGER_PYTHONPATH" "$PYTHON_BIN" Manager/app/main.py
