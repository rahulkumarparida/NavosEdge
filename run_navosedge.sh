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

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "[NAVOS] Loading configuration from .env"
    set -a
    source .env
    set +a
fi

INTEL_HOST="${NAVOS_HOST:-127.0.0.1}"
INTEL_PORT="${NAVOS_PORT:-8420}"
MANAGER_HOST="${NAVOS_MANAGER_HOST:-127.0.0.1}"
MANAGER_PORT="${NAVOS_MANAGER_PORT:-8430}"

NODE_ID="${NAVOS_NODE_ID:-navos-01}"
SCENARIO="${NAVOS_SCENARIO:-traffic}"
INTERVAL="${NAVOS_INTERVAL:-3}"

# Parse command line flags/arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
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
    *)
      shift
      ;;
  esac
done

PIDS=()

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

echo "============================================================"
echo "          NavosEdge — UNO Q Edge Node Launcher"
echo "============================================================"
echo " Node ID:  $NODE_ID"
echo " Scenario: $SCENARIO"
echo " Interval: ${INTERVAL}s"
echo "============================================================"

# Absolute paths for virtual environment binaries
SERVER_DIR="$SCRIPT_DIR/Intelligence/Server"
PYTHON_BIN="$SERVER_DIR/venv/bin/python3"

if [ ! -d "$SERVER_DIR/venv" ]; then
    echo "[NAVOS] Creating virtual environment..."
    python3 -m venv "$SERVER_DIR/venv"
    "$PYTHON_BIN" -m pip install -r "$SERVER_DIR/requirements.txt"
fi

# 1. Start Python Intelligence Server on UNO Q
echo "[NAVOS] [1/3] Starting Python Intelligence Server..."
free_port $INTEL_PORT
cd "$SERVER_DIR"
PYTHONPATH="$SERVER_DIR" NAVOS_MANAGER_URL="http://$MANAGER_HOST:$MANAGER_PORT" "$PYTHON_BIN" -m uvicorn --host $INTEL_HOST --port $INTEL_PORT --log-level warning app.main:app &
INTEL_PID=$!
PIDS+=($INTEL_PID)
cd "$SCRIPT_DIR"

# 2. Wait for Python Intelligence Server health/readiness
echo "[NAVOS] Waiting for Intelligence Server readiness on http://$INTEL_HOST:$INTEL_PORT/health ..."
READY=0
for i in {1..30}; do
    if curl -s "http://$INTEL_HOST:$INTEL_PORT/health" > /dev/null 2>&1; then
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

# 3. Build & Launch C++ Hardware Application
echo "[NAVOS] [2/3] Building C++ Hardware Application..."
cd Hardware
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release > /dev/null
make -j$(nproc 2>/dev/null || echo 1) > /dev/null
cd "$SCRIPT_DIR"

echo "[NAVOS] [3/3] Launching C++ Hardware Application..."
./Hardware/build/navos_hardware_bridge --node-id "$NODE_ID" --scenario "$SCENARIO" --interval "$INTERVAL" &
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
