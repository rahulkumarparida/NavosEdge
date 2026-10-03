#!/usr/bin/env bash
# ==============================================================================
# NavosEdge — Systemd Service Installer (install_navosedge_service.sh)
# ==============================================================================
# Detects repo root, verifies build prerequisites, installs & starts navosedge.service.
#
# Usage:
#   sudo ./scripts/install_navosedge_service.sh
# ==============================================================================

set -euo pipefail

# ── Resolve repository root ──────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

echo "========================================"
echo "  NAVOSEDGE SERVICE INSTALLER"
echo "========================================"
echo "  Repo Root: $REPO_ROOT"
echo ""

# ── Determine service user ───────────────────────────────────────────────────
REAL_USER="${SUDO_USER:-$USER}"
if [ "$REAL_USER" = "root" ]; then
    REAL_USER="$(logname 2>/dev/null || echo "root")"
fi
echo "  Service User: $REAL_USER"

# ── 1. Check prerequisites ───────────────────────────────────────────────────
echo ""
echo "[1/5] Verifying runtime prerequisites..."

MISSING=0

check_file() {
    local path="$1"
    local desc="$2"
    if [ -f "$path" ]; then
        echo "  [ OK ] $desc ($path)"
    else
        echo "  [FAIL] $desc missing ($path)"
        MISSING=1
    fi
}

check_file "$REPO_ROOT/run_hardware.sh" "Master hardware launcher"
check_file "$REPO_ROOT/Intelligence/Server/venv/bin/python3" "Python virtual environment"
check_file "$REPO_ROOT/Hardware/build/navos_hardware_bridge" "C++ Hardware executable"

if [ $MISSING -ne 0 ]; then
    echo ""
    echo "[ERROR] Prerequisites check failed!"
    echo "The systemd service requires pre-built binaries and Python dependencies."
    echo "Please build the application first by running:"
    echo "  ./run_hardware.sh --skip-flash"
    echo "or running C++ build and venv creation."
    exit 1
fi

# ── 2. Create systemd unit file ──────────────────────────────────────────────
echo ""
echo "[2/5] Creating /etc/systemd/system/navosedge.service..."

SERVICE_FILE="/etc/systemd/system/navosedge.service"
TEMPLATE_FILE="$REPO_ROOT/navosedge.service"

if [ ! -f "$TEMPLATE_FILE" ]; then
    echo "[ERROR] Template file $TEMPLATE_FILE not found."
    exit 1
fi

TMP_SERVICE=$(mktemp /tmp/navosedge_service_XXXXXX.service)
sed -e "s|@REPO_ROOT@|$REPO_ROOT|g" \
    -e "s|@SERVICE_USER@|$REAL_USER|g" \
    "$TEMPLATE_FILE" > "$TMP_SERVICE"

if [ "$(id -u)" -eq 0 ]; then
    cp "$TMP_SERVICE" "$SERVICE_FILE"
    chmod 644 "$SERVICE_FILE"
else
    echo "  [INFO] Root privileges required to copy $SERVICE_FILE..."
    sudo cp "$TMP_SERVICE" "$SERVICE_FILE"
    sudo chmod 644 "$SERVICE_FILE"
fi
rm -f "$TMP_SERVICE"

echo "  [DONE] Installed $SERVICE_FILE"

# ── 3. Enable and reload systemd ─────────────────────────────────────────────
echo ""
echo "[3/5] Reloading systemd daemon and enabling service..."

if [ "$(id -u)" -eq 0 ]; then
    systemctl daemon-reload
    systemctl enable navosedge.service
else
    sudo systemctl daemon-reload
    sudo systemctl enable navosedge.service
fi

echo "  [DONE] navosedge.service enabled on boot."

# ── 4. Start service ──────────────────────────────────────────────────────────
echo ""
echo "[4/5] Starting navosedge.service..."

if [ "$(id -u)" -eq 0 ]; then
    systemctl restart navosedge.service
else
    sudo systemctl restart navosedge.service
fi

sleep 3

# ── 5. Verify service health ──────────────────────────────────────────────────
echo ""
echo "[5/5] Verifying service status and health..."

if [ "$(id -u)" -eq 0 ]; then
    systemctl status navosedge.service --no-pager || true
else
    sudo systemctl status navosedge.service --no-pager || true
fi

echo ""
echo "Checking Intelligence health endpoint (http://localhost:8420/health)..."
HEALTH_OK=0
for i in $(seq 1 15); do
    if curl -s "http://localhost:8420/health" 2>/dev/null | grep -q "ok"; then
        HEALTH_OK=1
        break
    fi
    sleep 1
done

if [ $HEALTH_OK -eq 1 ]; then
    echo "  [SUCCESS] Intelligence Server health endpoint responded OK!"
    echo ""
    echo "========================================"
    echo "  NAVOSEDGE BOOT SERVICE INSTALLED"
    echo "========================================"
    echo "Commands to manage service:"
    echo "  ./scripts/navosedge-service.sh status"
    echo "  ./scripts/navosedge-service.sh logs"
    echo "  sudo systemctl stop navosedge.service"
    echo "  sudo systemctl restart navosedge.service"
    echo ""
else
    echo "  [WARN] Intelligence Server health check timed out."
    echo "  Inspect service logs with: journalctl -u navosedge.service -n 50"
fi
