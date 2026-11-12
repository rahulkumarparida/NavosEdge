#!/bin/bash
# ==============================================================================
# NavosEdge — ngrok Webhook Tunnel Helper
# ==============================================================================
# Starts an ngrok HTTP tunnel for the Intelligence Server port (default 8420),
# waits for the public HTTPS URL from http://127.0.0.1:4040/api/tunnels, and
# optionally updates NAVOS_PUBLIC_WEBHOOK_BASE_URL in .env.
#
# Usage (standalone):
#   bash scripts/start_ngrok_tunnel.sh [port]
# ==============================================================================

PORT="${1:-8420}"
NGROK_LOG="${NAVOS_NGROK_LOG:-/tmp/navosedge_ngrok.log}"

if ! command -v ngrok >/dev/null 2>&1; then
    echo "[NGROK] ngrok is not installed on PATH. Skipping public webhook tunnel." >&2
    exit 1
fi

echo "[NGROK] Starting ngrok tunnel on port ${PORT}..."
ngrok http "${PORT}" --log=stdout > "${NGROK_LOG}" 2>&1 &
NGROK_PID=$!

PUBLIC_URL=""
for _ in $(seq 1 30); do
    if ! kill -0 "${NGROK_PID}" 2>/dev/null; then
        echo "[NGROK] ngrok exited prematurely. Check ${NGROK_LOG}" >&2
        exit 1
    fi
    PUBLIC_URL="$(python3 -c '
import json, urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1) as r:
        data = json.load(r)
    for t in data.get("tunnels", []):
        u = t.get("public_url", "")
        if u.startswith("https://"):
            print(u)
            break
except Exception:
    pass
' 2>/dev/null)"
    if [ -n "${PUBLIC_URL}" ]; then
        break
    fi
    sleep 0.5
done

if [ -z "${PUBLIC_URL}" ]; then
    echo "[NGROK] Timed out waiting for ngrok HTTPS URL. Check ${NGROK_LOG}" >&2
    kill "${NGROK_PID}" 2>/dev/null || true
    exit 1
fi

echo "[NGROK] Tunnel active (PID ${NGROK_PID}): ${PUBLIC_URL}"
echo "[NGROK] Twilio SMS webhook:   ${PUBLIC_URL}/api/v1/webhooks/twilio/sms"
echo "[NGROK] Twilio Voice gather:  ${PUBLIC_URL}/api/v1/webhooks/twilio/voice/gather"
echo "[NGROK] Twilio Status hook:   ${PUBLIC_URL}/api/v1/webhooks/twilio/status"
echo "${NGROK_PID}|${PUBLIC_URL}"

