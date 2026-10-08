#!/usr/bin/env bash
# ==============================================================================
# NavosEdge — Network IP Detection & .env Update Script
# ==============================================================================
# Automatically detects the connected network IP (Wi-Fi or Ethernet)
# and updates NAVOS_UNO_Q_IP, NAVOS_UNO_Q_URL, and UNO_Q_HOST_DEFAULT in .env.
#
# Usage:
#   ./scripts/update_env_ip.sh
#   ./scripts/update_env_ip.sh --ip 192.168.1.100
#   ./scripts/update_env_ip.sh --detect-only
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Run python implementation if python3 is available
if command -v python3 &>/dev/null; then
    exec python3 "$SCRIPT_DIR/update_env_ip.py" "$@"
fi

# Fallback pure-bash detection if python3 is not available
detect_ip_bash() {
    local detected_ip=""
    if command -v ip &>/dev/null; then
        detected_ip=$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}')
    fi
    if [ -z "$detected_ip" ] && command -v hostname &>/dev/null; then
        for ip in $(hostname -I 2>/dev/null); do
            if [[ ! "$ip" =~ ^127\. ]] && [[ ! "$ip" =~ ^172\.17\. ]] && [[ ! "$ip" =~ ^169\.254\. ]]; then
                detected_ip="$ip"
                break
            fi
        done
    fi
    echo "${detected_ip:-127.0.0.1}"
}

IP=$(detect_ip_bash)
echo "[NAVOS] Detected Network IP (bash fallback): $IP"

ENV_FILE="$REPO_ROOT/.env"
if [ ! -f "$ENV_FILE" ] && [ -f "$REPO_ROOT/.env.example" ]; then
    cp "$REPO_ROOT/.env.example" "$ENV_FILE"
fi

if [ -f "$ENV_FILE" ]; then
    sed -i "s/^NAVOS_UNO_Q_IP=.*/NAVOS_UNO_Q_IP=$IP/" "$ENV_FILE"
    sed -i "s|^NAVOS_UNO_Q_URL=.*|NAVOS_UNO_Q_URL=http://$IP:8420|" "$ENV_FILE"
    sed -i "s/^UNO_Q_HOST_DEFAULT=.*/UNO_Q_HOST_DEFAULT=$IP/" "$ENV_FILE"
    echo "[NAVOS] Updated $ENV_FILE with IP $IP"
fi
