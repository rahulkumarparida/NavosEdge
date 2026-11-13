#!/bin/bash
# ==============================================================================
# NavosEdge — UNO Q Edge Node Launcher
# ==============================================================================
# Starts the complete local pipeline for the UNO Q Edge Node:
# 1. Python Intelligence Server (Port 8420)
# 2. Waits for readiness (/health & /ready)
# 3. C++ Hardware Application (Sensor provider + HTTP Sender + SSE Client + MPI3501 GUI)
#
# Usage:
#   ./run_navosedge.sh
#   ./run_navosedge.sh --node-id navos-01 --scenario traffic --interval 3
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

CUSTOM_IP=""
AUTO_IP=true
NODE_ID="${NAVOS_NODE_ID:-uno-q-001}"
SCENARIO="${NAVOS_SCENARIO:-traffic}"
INTERVAL="${NAVOS_INTERVAL:-3}"
SENSOR_MODE=""
DO_FLASH=false
NGROK_MODE="auto"

# Parse command line flags/arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --ip)
      CUSTOM_IP="$2"
      shift 2
      ;;
    --no-ip-detect)
      AUTO_IP=false
      shift
      ;;
    --node-id|-n)
      NODE_ID="$2"
      shift 2
      ;;
    --scenario|-s)
      SCENARIO="$2"
      shift 2
      ;;
    --interval|-i)
      INTERVAL="$2"
      shift 2
      ;;
    --mock|-m)
      SENSOR_MODE="--mock"
      shift
      ;;
    --physical)
      SENSOR_MODE="--physical"
      shift
      ;;
    --flash)
      DO_FLASH=true
      shift
      ;;
    --ngrok)
      NGROK_MODE="on"
      shift
      ;;
    --no-ngrok)
      NGROK_MODE="off"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

# Auto-detect connected network IP and update .env
if [ "$AUTO_IP" = true ] || [ -n "$CUSTOM_IP" ]; then
    if [ -f "$SCRIPT_DIR/scripts/update_env_ip.sh" ]; then
        if [ -n "$CUSTOM_IP" ]; then
            bash "$SCRIPT_DIR/scripts/update_env_ip.sh" --ip "$CUSTOM_IP"
        else
            bash "$SCRIPT_DIR/scripts/update_env_ip.sh"
        fi
    fi
fi

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "[NAVOS] Loading configuration from .env"
    set -a
    source .env
    set +a
fi

INTEL_HOST="${NAVOS_HOST:-0.0.0.0}"
INTEL_PORT="${NAVOS_PORT:-8420}"
MANAGER_HOST="${NAVOS_MANAGER_HOST:-127.0.0.1}"
MANAGER_PORT="${NAVOS_MANAGER_PORT:-8430}"

PIDS=()

# Optional ngrok public HTTPS tunnel for Twilio webhooks (when LIVE or --ngrok)
if [ "$NGROK_MODE" = "on" ] || { [ "$NGROK_MODE" = "auto" ] && [ "${NAVOS_TWILIO_MODE:-SIMULATED}" = "LIVE" ]; }; then
    if [ -f "$SCRIPT_DIR/scripts/start_ngrok_tunnel.sh" ]; then
        NGROK_OUT="$(bash "$SCRIPT_DIR/scripts/start_ngrok_tunnel.sh" "$INTEL_PORT" | tee /dev/stderr | tail -n 1)"
        NGROK_PID="${NGROK_OUT%%|*}"
        NGROK_URL="${NGROK_OUT#*|}"
        if [ -n "$NGROK_PID" ] && [ "$NGROK_URL" != "$NGROK_OUT" ] && [[ "$NGROK_URL" == https://* ]]; then
            PIDS+=("$NGROK_PID")
            export NAVOS_PUBLIC_WEBHOOK_BASE_URL="$NGROK_URL"
            echo "[NAVOS] Exported NAVOS_PUBLIC_WEBHOOK_BASE_URL=$NAVOS_PUBLIC_WEBHOOK_BASE_URL"
        else
            echo "[NAVOS] WARNING: ngrok tunnel did not start; continuing offline/local mode."
        fi
    fi
fi

cleanup() {
    echo ""
    echo "[NAVOS] Shutting down UNO Q Edge Node cleanly..."
    for pid in "${PIDS[@]}"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "[NAVOS] Stopping process PID $pid"
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    echo "[NAVOS] UNO Q Edge Node stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# Kill existing instances on port if needed to prevent duplicates
free_port() {
    local port=$1
    local pids=$(fuser $port/tcp 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "[NAVOS] Cleaning up existing process on port $port (PID: $pids)..."
        kill -9 $pids 2>/dev/null || true
        sleep 1
    fi
}

MODE_LABEL="Hardware Default (from hardware_config.json)"
if [ "$SENSOR_MODE" = "--mock" ]; then
    MODE_LABEL="Mock Sensor Simulator (Scenario: $SCENARIO)"
elif [ "$SENSOR_MODE" = "--physical" ]; then
    MODE_LABEL="Physical Hardware Sensors (127.0.0.1:7500)"
fi

echo "============================================================"
echo "          NavosEdge — UNO Q Edge Node Launcher"
echo "============================================================"
echo " Node ID:  $NODE_ID"
echo " Mode:     $MODE_LABEL"
echo " Interval: ${INTERVAL}s"
echo "============================================================"

# 1. Build C++ Hardware Application first so diagnostics & bridge are ready
echo "[NAVOS] [1/3] Building C++ Hardware Application..."
cd Hardware
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release > /dev/null
make -j$(nproc 2>/dev/null || echo 1) > /dev/null
cd "$SCRIPT_DIR"

# 2. Verify MCU Display Firmware (Auto-flash if un-flashed or out of sync on UNO Q)
if [ "$DO_FLASH" = true ]; then
    echo "[NAVOS] Explicit flash requested. Flashing MCU display firmware..."
    bash "$SCRIPT_DIR/flash_display.sh"
elif [ -S "/var/run/arduino-router.sock" ] && [ "$SENSOR_MODE" != "--mock" ]; then
    echo "[NAVOS] Verifying MCU display firmware RPC readiness..."
    if ! "$SCRIPT_DIR/Hardware/build/navos_hardware_bridge" --test-mcu-rpc > /dev/null 2>&1; then
        echo "[NAVOS] MCU display firmware not responding or out of sync. Auto-flashing..."
        bash "$SCRIPT_DIR/flash_display.sh"
    else
        echo "[NAVOS] MCU display firmware verified (MPI3501 RPC operational)."
    fi
fi

# Absolute paths for virtual environment binaries
SERVER_DIR="$SCRIPT_DIR/Intelligence/Server"
PYTHON_BIN="$SERVER_DIR/venv/bin/python3"

if [ ! -d "$SERVER_DIR/venv" ]; then
    echo "[NAVOS] Creating virtual environment..."
    python3 -m venv "$SERVER_DIR/venv"
    "$PYTHON_BIN" -m pip install -r "$SERVER_DIR/requirements.txt"
fi

# 3. Start Python Intelligence Server on UNO Q
echo "[NAVOS] [2/3] Starting Python Intelligence Server..."
free_port $INTEL_PORT
cd "$SERVER_DIR"
PYTHONPATH="$SERVER_DIR" NAVOS_MANAGER_URL="http://$MANAGER_HOST:$MANAGER_PORT" "$PYTHON_BIN" -m uvicorn --host $INTEL_HOST --port $INTEL_PORT --log-level warning app.main:app &
INTEL_PID=$!
PIDS+=($INTEL_PID)
cd "$SCRIPT_DIR"

# Wait for Python Intelligence Server health/readiness
HEALTH_CHECK_HOST="$INTEL_HOST"
if [ "$HEALTH_CHECK_HOST" = "0.0.0.0" ]; then
    HEALTH_CHECK_HOST="127.0.0.1"
fi
echo "[NAVOS] Waiting for Intelligence Server readiness on http://$HEALTH_CHECK_HOST:$INTEL_PORT/health ..."
READY=0
for i in {1..30}; do
    if curl -s "http://$HEALTH_CHECK_HOST:$INTEL_PORT/health" > /dev/null 2>&1; then
        READY=1
        echo "[NAVOS] Intelligence Server is READY!"
        break
    fi
    sleep 1
done

if [ $READY -ne 1 ]; then
    echo "[NAVOS] ERROR: Intelligence Server failed to start."
    exit 1
fi

# 4. Launch C++ Hardware Application
echo "[NAVOS] [3/3] Launching C++ Hardware Application..."
HW_CMD=("./Hardware/build/navos_hardware_bridge" "--node-id" "$NODE_ID" "--scenario" "$SCENARIO" "--interval" "$INTERVAL")
if [ -n "$SENSOR_MODE" ]; then
    HW_CMD+=("$SENSOR_MODE")
fi
"${HW_CMD[@]}" &
HW_PID=$!
PIDS+=($HW_PID)

echo "============================================================"
echo "          UNO Q Edge Node Running Successfully"
echo "============================================================"
echo "  • Local Intelligence API: http://$INTEL_HOST:$INTEL_PORT"
echo "  • Node ID:               $NODE_ID"
echo "  • Display GUI:            MPI3501 (3-screen rotation)"
echo "  • Parent Manager URL:     http://$MANAGER_HOST:$MANAGER_PORT"
echo "============================================================"
echo "[NAVOS] Press Ctrl+C to stop the edge node."
echo ""

wait
