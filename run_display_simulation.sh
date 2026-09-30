#!/usr/bin/env bash
# ==============================================================================
# NavosEdge — Synthetic Hardware → Intelligence → MPI3501 Display Test Launcher
# ==============================================================================
# Usage:
#   ./run_display_simulation.sh
#   ./run_display_simulation.sh --scenario traffic
#   ./run_display_simulation.sh --scenario dust --interval 5
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

NODE_ID="uno-q-001"
SCENARIO="normal"
INTERVAL=60

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
    --help|-h)
      echo "Usage: $0 [--scenario normal|high_pm|traffic|dust] [--interval <seconds>] [--node-id <id>]"
      exit 0
      ;;
    *)
      shift
      ;;
  esac
done

PIDS=()

cleanup() {
    echo ""
    echo "[NAVOS] Shutting down simulation pipeline cleanly..."
    for pid in "${PIDS[@]}"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    echo "[NAVOS] Shutdown complete."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

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
echo " NavosEdge — Synthetic Hardware → Intelligence → MPI3501"
echo "============================================================"
echo "  Node ID:   $NODE_ID"
echo "  Scenario:  $SCENARIO"
echo "  Interval:  ${INTERVAL}s (default 60s)"
echo "============================================================"

SERVER_DIR="$SCRIPT_DIR/Intelligence/Server"
PYTHON_BIN="$SERVER_DIR/venv/bin/python3"

if [ ! -d "$SERVER_DIR/venv" ]; then
    echo "[NAVOS] Creating Python virtual environment..."
    python3 -m venv "$SERVER_DIR/venv"
    "$PYTHON_BIN" -m pip install -r "$SERVER_DIR/requirements/unoq.txt" # CHANGE THIS TO requirements/unoq.txt
fi

INTEL_HOST="127.0.0.1"
INTEL_PORT="8420"

# 1. Check/Start Python Intelligence Server
if ! curl -s "http://$INTEL_HOST:$INTEL_PORT/health" > /dev/null 2>&1; then
    echo "[NAVOS] Starting Python Intelligence Server..."
    free_port $INTEL_PORT
    cd "$SERVER_DIR"
    PYTHONPATH="$SERVER_DIR" "$PYTHON_BIN" -m uvicorn --host $INTEL_HOST --port $INTEL_PORT --log-level warning app.main:app &
    INTEL_PID=$!
    PIDS+=($INTEL_PID)
    cd "$SCRIPT_DIR"
else
    echo "[NAVOS] Python Intelligence Server already running on http://$INTEL_HOST:$INTEL_PORT"
fi

# 2. Wait for Intelligence Server health & readiness
echo "[NAVOS] Waiting for Intelligence Server readiness..."
READY=0
for i in {1..30}; do
    if curl -s "http://$INTEL_HOST:$INTEL_PORT/health" | grep -q "ok" 2>/dev/null; then
        READY=1
        echo "[NAVOS] Intelligence Server READY"
        break
    fi
    sleep 1
done

if [ $READY -ne 1 ]; then
    echo "[NAVOS] ERROR: Intelligence Server failed to become ready."
    exit 1
fi

# 3. Build C++ Hardware Bridge target if necessary
echo "[NAVOS] Checking C++ Hardware application build..."
cd Hardware
mkdir -p build && cd build
if [ ! -f "navos_hardware_bridge" ]; then
    echo "[NAVOS] Building navos_hardware_bridge target..."
    cmake .. -DCMAKE_BUILD_TYPE=Release > /dev/null
    make navos_hardware_bridge -j$(nproc 2>/dev/null || echo 1) > /dev/null
fi
cd "$SCRIPT_DIR"

# 4. Launch C++ Hardware application (Mock Sensor + HTTP POST + SSE + MPI3501 GUI)
echo "[NAVOS] Launching C++ Hardware application..."
./Hardware/build/navos_hardware_bridge --config Hardware/config/hardware_config.json --node-id "$NODE_ID" --scenario "$SCENARIO" --interval "$INTERVAL" &
HW_PID=$!
PIDS+=($HW_PID)

echo "============================================================"
echo "          End-to-End Pipeline Active"
echo "============================================================"
echo "  • Node ID:               $NODE_ID"
echo "  • Scenario:              $SCENARIO"
echo "  • Sensor update:         every ${INTERVAL}s"
echo "  • Display rotation:      every 10s"
echo "============================================================"
echo "[NAVOS] Press Ctrl+C to stop."
echo ""

wait
