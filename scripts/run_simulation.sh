#!/bin/bash
# ==============================================================================
# NavosEdge — Run Simulation
# ==============================================================================
# Starts the complete NavosEdge system in simulation mode:
# 1. Intelligence Server (FastAPI)
# 2. Sensor Simulator (feeds data to server)
# 3. TUI Display (optional)
#
# Usage: bash scripts/run_simulation.sh [--scenario normal|traffic|dust|smoke]
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVER_DIR="$PROJECT_DIR/Intelligence/Server"
SCENARIO="${1:-clean_indoor}"
NODE_ID="${2:-NAVOS-SIM-001}"
INTERVAL="${3:-5}"
PIDS=()

cleanup() {
    echo ""
    echo "[NAVOS] Shutting down..."
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null
    echo "[NAVOS] Shutdown complete."
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "============================================================"
echo "NavosEdge — Simulation Mode"
echo "============================================================"
echo "  Scenario:  $SCENARIO"
echo "  Node ID:   $NODE_ID"
echo "  Interval:  ${INTERVAL}s"
echo "============================================================"

# Check for virtual environment
if [ ! -d "$SERVER_DIR/venv" ]; then
    echo "[NAVOS] Creating virtual environment..."
    python3 -m venv "$SERVER_DIR/venv"
fi

source "$SERVER_DIR/venv/bin/activate"

# Install dependencies if needed
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo "[NAVOS] Installing dependencies..."
    if [ -f "$PROJECT_DIR/requirements/unoq.txt" ]; then
        pip install -q -r "$PROJECT_DIR/requirements/unoq.txt"
    else
        pip install -q -r "$SERVER_DIR/requirements.txt"
    fi
fi

# Start Intelligence Server
echo "[NAVOS] Starting Intelligence Server..."
cd "$SERVER_DIR"
uvicorn app.main:app --host 127.0.0.1 --port 8420 --log-level warning &
SERVER_PID=$!
PIDS+=($SERVER_PID)

# Wait for server
echo "[NAVOS] Waiting for server..."
for i in $(seq 1 30); do
    if curl -s http://127.0.0.1:8420/health >/dev/null 2>&1; then
        echo "[NAVOS] Server ready."
        break
    fi
    if [ $i -eq 30 ]; then
        echo "[NAVOS] ERROR: Server failed to start."
        cleanup
    fi
    sleep 1
done

# Start Sensor Simulator
echo "[NAVOS] Starting sensor simulator (scenario: $SCENARIO)..."
cd "$PROJECT_DIR"
python3 -c "
import sys, time, json
sys.path.insert(0, 'Intelligence/Server')
sys.path.insert(0, '.')

from simulation.sensor_simulator import SensorSimulator
import urllib.request

sim = SensorSimulator(node_id='$NODE_ID', scenario='$SCENARIO', seed=42)
url = 'http://127.0.0.1:8420/hardware/data'
count = 0

print('[SIM] Simulator started. Sending readings every ${INTERVAL}s...')
print('[SIM] Press Ctrl+C to stop.')

while True:
    try:
        reading = sim.generate()
        payload = json.dumps(reading).encode()
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
        resp = urllib.request.urlopen(req, timeout=5)
        count += 1
        status = resp.getcode()

        # Parse response for key info
        body = json.loads(resp.read())
        aqi = body.get('aqi', 'N/A')
        source = body.get('predictions', {}).get('source', {}).get('value', 'N/A')

        print(f'[SIM] Reading #{count} → HTTP {status} | AQI: {aqi} | Source: {source}')
    except KeyboardInterrupt:
        break
    except Exception as e:
        print(f'[SIM] Error: {e}')

    time.sleep($INTERVAL)

print(f'[SIM] Total readings sent: {count}')
" &
SIM_PID=$!
PIDS+=($SIM_PID)

echo "[NAVOS] Simulation running. Press Ctrl+C to stop."
echo ""

# Wait for processes
wait "${PIDS[@]}" 2>/dev/null
