#!/bin/bash
# ==============================================================================
# NavosEdge — Laptop Parent Manager Server Launcher
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVER_VENV="$PROJECT_DIR/Intelligence/Server/venv"

if [ -d "$SERVER_VENV" ]; then
    PYTHON_BIN="$SERVER_VENV/bin/python3"
else
    PYTHON_BIN="python3"
fi

PORT="${NAVOS_MANAGER_PORT:-8430}"
HOST="${NAVOS_MANAGER_HOST:-0.0.0.0}"

echo "============================================================"
echo "      NavosEdge Parent Manager Server & Web Dashboard"
echo "============================================================"
echo "  • Manager API:       http://$HOST:$PORT/api/v1/overview"
echo "  • React Dashboard:   http://$HOST:$PORT/"
echo "============================================================"

cd "$PROJECT_DIR"
PYTHONPATH="$SCRIPT_DIR:$PROJECT_DIR" "$PYTHON_BIN" Manager/app/main.py
