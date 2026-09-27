#!/usr/bin/env bash
# NavosEdge Phase 7C — Local End-to-End Simulation Runner
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

SCENARIO="${1:-normal}"
NODE_ID="${2:-navos-node-01}"

echo "=================================================="
echo " NavosEdge End-to-End Hardware Simulation Test"
echo " Scenario: $SCENARIO | Node ID: $NODE_ID"
echo "=================================================="

# 1. Build C++ Hardware Bridge
echo "[E2E] Building C++ Hardware Bridge..."
cd Hardware
mkdir -p build && cd build
cmake .. > /dev/null
make -j$(nproc) > /dev/null
cd "$PROJECT_ROOT"

# 2. Check Python Intelligence Server
SERVER_URL="http://localhost:8420"
if ! curl -s "$SERVER_URL/health" > /dev/null 2>&1; then
    echo "[E2E] Starting Python Intelligence Server on port 8420..."
    bash -c "source Intelligence/Server/venv/bin/activate && cd Intelligence/Server && uvicorn app.main:app --host 0.0.0.0 --port 8420" > /tmp/navos_server.log 2>&1 &
    SERVER_PID=$!
    echo "[E2E] Waiting for server startup (loading PyTorch ML models)..."
    for i in $(seq 1 40); do
        sleep 3
        if curl -s "$SERVER_URL/health" | grep -q "ok" 2>/dev/null; then
            echo "[E2E] Server is up and ready!"
            break
        fi
        echo -n "."
    done
    echo ""
else
    echo "[E2E] Python Intelligence Server is already running on port 8420."
fi

# 3. Launch C++ Hardware Simulator
echo "[E2E] Launching C++ Hardware Simulator..."
./Hardware/build/navos_hardware_bridge --config Hardware/config/hardware_config.json --node-id "$NODE_ID" --scenario "$SCENARIO" --interval 2 &
HW_PID=$!

# Let it run for 8 seconds to transmit multiple readings over SSE & HTTP POST
sleep 8

# 4. Trigger SSE Config Event
echo "[E2E] Publishing SSE config update to $NODE_ID (setting interval to 1s)..."
curl -s -X POST "$SERVER_URL/hardware/config" \
    -H "Content-Type: application/json" \
    -d "{\"node_id\": \"$NODE_ID\", \"sampling_interval\": 1}"
echo ""

sleep 4

# 5. Retrieve Latest Intelligence Result
echo "[E2E] Retrieving Latest Intelligence Result for node: $NODE_ID"
echo "--------------------------------------------------"
curl -s "$SERVER_URL/api/v1/nodes/$NODE_ID/latest" | python3 -m json.tool || curl -s "$SERVER_URL/api/v1/nodes/$NODE_ID/latest"
echo "--------------------------------------------------"

# Cleanup Hardware Bridge process
kill $HW_PID 2>/dev/null || true
echo "[E2E] Simulation test completed successfully."
