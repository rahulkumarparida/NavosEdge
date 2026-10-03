#!/usr/bin/env bash
# ==============================================================================
# NavosEdge — Service Control Helper (navosedge-service.sh)
# ==============================================================================
# Convenient wrapper to manage navosedge.service via systemctl & journalctl.
#
# Usage:
#   ./scripts/navosedge-service.sh start
#   ./scripts/navosedge-service.sh stop
#   ./scripts/navosedge-service.sh restart
#   ./scripts/navosedge-service.sh status
#   ./scripts/navosedge-service.sh logs
# ==============================================================================

set -euo pipefail

SERVICE_NAME="navosedge.service"

CMD="${1:-status}"

run_sudo_cmd() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

case "$CMD" in
    start)
        echo "[NAVOSEDGE] Starting $SERVICE_NAME..."
        run_sudo_cmd systemctl start "$SERVICE_NAME"
        echo "[DONE] Started."
        ;;
    stop)
        echo "[NAVOSEDGE] Stopping $SERVICE_NAME..."
        run_sudo_cmd systemctl stop "$SERVICE_NAME"
        echo "[DONE] Stopped."
        ;;
    restart)
        echo "[NAVOSEDGE] Restarting $SERVICE_NAME..."
        run_sudo_cmd systemctl restart "$SERVICE_NAME"
        echo "[DONE] Restarted."
        ;;
    status)
        run_sudo_cmd systemctl status "$SERVICE_NAME" --no-pager
        ;;
    logs)
        echo "[NAVOSEDGE] Tailing logs for $SERVICE_NAME (Ctrl+C to exit)..."
        run_sudo_cmd journalctl -u "$SERVICE_NAME" -f -o cat
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
