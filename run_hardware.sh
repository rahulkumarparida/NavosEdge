#!/usr/bin/env bash
# ==============================================================================
# NavosEdge — Physical Hardware Mode Launcher (run_hardware.sh)
# ==============================================================================
# One-command startup for deployment WITH physical sensors connected.
#
# Flow:
#   Environment check → Python venv → pip install → C++ build →
#   Display build/flash → Intelligence Server → Health check →
#   C++ Hardware (real sensors on serial port) → Sensor warm-up →
#   READY → Data → Intelligence → SSE → MPI3501 display
#
# IMPORTANT:
#   Physical sensor drivers must be implemented and sensors connected
#   before this mode is usable. If hardware mode is not yet functional,
#   this script will fail with a clear message.
#
# Usage:
#   ./run_hardware.sh
#   ./run_hardware.sh --node-id navos-prod-01
#   ./run_hardware.sh --interval 30 --port /dev/ttyACM1
#   ./run_hardware.sh --help
# ==============================================================================

set -euo pipefail

# ── Resolve repository root from script location ──────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# ── Load .env if present ──────────────────────────────────────────────────────
if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$REPO_ROOT/.env"
    set +a
fi

# ── Defaults (from .env or fallback) ─────────────────────────────────────────
INTEL_HOST="${NAVOS_HOST:-127.0.0.1}"
INTEL_PORT="${NAVOS_PORT:-8420}"
NODE_ID="${NAVOS_NODE_ID:-uno-q-001}"
INTERVAL="${NAVOS_SENSOR_INTERVAL:-60}"
SERIAL_PORT="${ARDUINO_PORT:-/dev/ttyACM0}"
SKIP_FLASH=false
NO_BUILD=false

# ── Parse CLI arguments ──────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --interval|-i)    INTERVAL="$2";      shift 2 ;;
        --node-id|-n)     NODE_ID="$2";       shift 2 ;;
        --port|-p)        SERIAL_PORT="$2";   shift 2 ;;
        --skip-flash)     SKIP_FLASH=true;    shift ;;
        --no-build)       NO_BUILD=true; SKIP_FLASH=true; shift ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --interval, -i <sec>    Sampling interval in seconds (default: $INTERVAL)"
            echo "  --node-id,  -n <id>     Node identifier (default: $NODE_ID)"
            echo "  --port,     -p <dev>    Serial port for sensors (default: $SERIAL_PORT)"
            echo "  --skip-flash            Skip MCU display flashing step"
            echo "  --no-build              Skip venv creation, pip install, C++ compile & display flash (for boot service)"
            echo "  --help, -h              Show this help"
            exit 0
            ;;
        *) echo "[WARN] Unknown option: $1"; shift ;;
    esac
done

# ── Process management ────────────────────────────────────────────────────────
PIDS=()
COMPONENT_NAMES=()

cleanup() {
    echo ""
    echo "========================================"
    echo "  NAVOSEDGE SHUTDOWN"
    echo "========================================"
    local i
    for (( i=${#PIDS[@]}-1; i>=0; i-- )); do
        local pid="${PIDS[$i]}"
        local name="${COMPONENT_NAMES[$i]:-unknown}"
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "[STOP] $name (PID $pid)"
            kill "$pid" 2>/dev/null || true
        fi
    done
    sleep 1
    for pid in "${PIDS[@]}"; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
    done
    wait 2>/dev/null || true
    echo "[DONE] All processes stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

register_pid() {
    PIDS+=("$1")
    COMPONENT_NAMES+=("$2")
}

free_port() {
    local port=$1
    local pids
    pids=$(fuser "$port/tcp" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "[WARN] Port $port in use (PID: $pids). Freeing..."
        kill -9 $pids 2>/dev/null || true
        sleep 1
    fi
}

# ── Step counter ──────────────────────────────────────────────────────────────
TOTAL_STEPS=8
STEP=0
step() {
    STEP=$((STEP + 1))
    echo ""
    echo "[$STEP/$TOTAL_STEPS] $1"
    echo "────────────────────────────────────────"
}

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "   NAVOSEDGE PHYSICAL HARDWARE MODE"
echo "========================================"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Check system dependencies
# ══════════════════════════════════════════════════════════════════════════════
step "Checking environment..."

MISSING_DEPS=()

check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        MISSING_DEPS+=("$1")
        echo "  [MISS] $1 — $2"
    else
        echo "  [ OK ] $1"
    fi
}

check_cmd python3  "sudo apt install python3"
check_cmd cmake    "sudo apt install cmake"
check_cmd make     "sudo apt install build-essential"
check_cmd gcc      "sudo apt install gcc"
check_cmd g++      "sudo apt install g++"
check_cmd curl     "sudo apt install curl"
check_cmd git      "sudo apt install git"

if ! python3 -c "import venv" 2>/dev/null; then
    MISSING_DEPS+=("python3-venv")
    echo "  [MISS] python3-venv — sudo apt install python3-venv"
else
    echo "  [ OK ] python3-venv"
fi

if ! pkg-config --exists libcurl 2>/dev/null; then
    if [ ! -f /usr/include/curl/curl.h ] && [ ! -f /usr/include/x86_64-linux-gnu/curl/curl.h ]; then
        echo "  [WARN] libcurl-dev may be missing — sudo apt install libcurl4-openssl-dev"
    else
        echo "  [ OK ] libcurl-dev"
    fi
else
    echo "  [ OK ] libcurl-dev"
fi

if [ ${#MISSING_DEPS[@]} -gt 0 ]; then
    echo ""
    echo "  [ERROR] Missing required dependencies: ${MISSING_DEPS[*]}"
    echo "  Install them and re-run this script."
    exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Verify physical hardware prerequisites
# ══════════════════════════════════════════════════════════════════════════════
step "Checking physical hardware..."

# Check serial port
if [ -e "$SERIAL_PORT" ]; then
    echo "  [ OK ] Serial device found: $SERIAL_PORT"
else
    echo "  [WARN] Serial device not found: $SERIAL_PORT"
    echo "         Ensure sensors are connected and the correct port is specified."
    echo "         Use: $0 --port /dev/ttyACMx"
fi

# Check that hardware_config.json has mock_mode=false or can be overridden
HW_CONFIG="$REPO_ROOT/Hardware/config/hardware_config.json"
if [ -f "$HW_CONFIG" ]; then
    if grep -q '"mock_mode": true' "$HW_CONFIG"; then
        echo "  [INFO] hardware_config.json has mock_mode=true"
        echo "         The C++ binary will be launched with mock_mode=false via CLI override."
    fi
fi

echo "  Serial Port:  $SERIAL_PORT"
echo "  Interval:     ${INTERVAL}s"
echo "  Node ID:      $NODE_ID"

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Python virtual environment & dependencies
# ══════════════════════════════════════════════════════════════════════════════
step "Preparing Python environment..."

SERVER_DIR="$REPO_ROOT/Intelligence/Server"
VENV_DIR="$SERVER_DIR/venv"
PYTHON_BIN="$VENV_DIR/bin/python3"
REQUIREMENTS_FILE="$REPO_ROOT/requirements/unoq.txt"

if [ ! -f "$REQUIREMENTS_FILE" ]; then
    REQUIREMENTS_FILE="$SERVER_DIR/requirements.txt"
fi

if [ "$NO_BUILD" = "true" ]; then
    if [ ! -d "$VENV_DIR" ] || [ ! -f "$PYTHON_BIN" ]; then
        echo "  [ERROR] Python virtual environment not found at $VENV_DIR."
        echo "  Run './run_hardware.sh' without --no-build first to perform setup."
        exit 1
    fi
    echo "  [ OK ] Virtual environment verified (NO_BUILD mode)."
else
    if [ ! -d "$VENV_DIR" ]; then
        echo "  Creating virtual environment at $VENV_DIR ..."
        python3 -m venv "$VENV_DIR"
        echo "  Installing Python dependencies..."
        "$PYTHON_BIN" -m pip install --quiet --upgrade pip
        "$PYTHON_BIN" -m pip install --quiet -r "$REQUIREMENTS_FILE"
        echo "  [DONE] Virtual environment created and dependencies installed."
    else
        if ! "$PYTHON_BIN" -c "import fastapi" 2>/dev/null; then
            echo "  Dependencies missing in existing venv. Installing..."
            "$PYTHON_BIN" -m pip install --quiet -r "$REQUIREMENTS_FILE"
        else
            echo "  [DONE] Virtual environment exists and dependencies OK."
        fi
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Build C++ Hardware application
# ══════════════════════════════════════════════════════════════════════════════
step "Building C++ Hardware application..."

HW_BUILD_DIR="$REPO_ROOT/Hardware/build"
HW_BINARY="$HW_BUILD_DIR/navos_hardware_bridge"

if [ "$NO_BUILD" = "true" ]; then
    if [ ! -f "$HW_BINARY" ]; then
        echo "  [ERROR] C++ binary navos_hardware_bridge not found at $HW_BINARY."
        echo "  Run './run_hardware.sh' without --no-build first to compile."
        exit 1
    fi
    echo "  [ OK ] navos_hardware_bridge binary verified (NO_BUILD mode)."
else
    mkdir -p "$HW_BUILD_DIR"
    if [ ! -f "$HW_BINARY" ] || [ "$REPO_ROOT/Hardware/CMakeLists.txt" -nt "$HW_BINARY" ] || \
       [ "$REPO_ROOT/Hardware/src/main.cpp" -nt "$HW_BINARY" ]; then
        echo "  Running cmake..."
        cmake -S "$REPO_ROOT/Hardware" -B "$HW_BUILD_DIR" -DCMAKE_BUILD_TYPE=Release > /dev/null 2>&1
        echo "  Compiling..."
        make -C "$HW_BUILD_DIR" -j"$(nproc 2>/dev/null || echo 1)" > /dev/null 2>&1
        echo "  [DONE] navos_hardware_bridge built."
    else
        echo "  [DONE] navos_hardware_bridge is up to date."
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: Build/flash MPI3501 display
# ══════════════════════════════════════════════════════════════════════════════
step "Display build/flash..."

if [ "$SKIP_FLASH" != "true" ]; then
    if command -v arduino-cli &>/dev/null || \
       [ -x "$HOME/.local/bin/arduino-cli" ] || \
       [ -x "/usr/local/bin/arduino-cli" ]; then
        echo "  Flashing MCU display firmware..."
        if bash "$REPO_ROOT/flash_display.sh"; then
            echo "  [DONE] MCU display firmware flashed."
        else
            echo "  [ERROR] MCU flash failed."
            echo "  Physical deployment requires a working MPI3501 display."
            echo "  Fix the issue and re-run, or use --skip-flash if display is already programmed."
            exit 1
        fi
    else
        echo "  [ERROR] arduino-cli not found."
        echo "  Physical deployment requires arduino-cli to flash the MPI3501 display."
        echo ""
        echo "  Install arduino-cli:"
        echo "    curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh"
        echo ""
        echo "  Or skip if display is already flashed:"
        echo "    $0 --skip-flash"
        exit 1
    fi
else
    echo "  [SKIP] Display flashing skipped (--skip-flash / --no-build)."
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 6: Verify model artifacts
# ══════════════════════════════════════════════════════════════════════════════
step "Verifying model artifacts..."

ARTIFACTS_DIR="$SERVER_DIR/artifacts"

for artifact in gasnet_weights.npz model_metadata.json; do
    if [ -f "$ARTIFACTS_DIR/$artifact" ]; then
        echo "  [ OK ] $artifact"
    else
        echo "  [WARN] $artifact not found — inference runs in degraded mode"
    fi
done

for artifact in preprocess.pkl source_classifier_model.pkl; do
    if [ -f "$ARTIFACTS_DIR/$artifact" ]; then
        echo "  [ OK ] $artifact"
    else
        echo "  [WARN] $artifact not found — source classification unavailable"
    fi
done

# ══════════════════════════════════════════════════════════════════════════════
# STEP 7: Start Intelligence Server & wait for readiness
# ══════════════════════════════════════════════════════════════════════════════
step "Starting Intelligence Server..."
echo "[NAVOSEDGE] Starting"
echo "[INTELLIGENCE] Starting"

if curl -s "http://${INTEL_HOST}:${INTEL_PORT}/health" 2>/dev/null | grep -q "ok"; then
    echo "  Intelligence Server already running on http://${INTEL_HOST}:${INTEL_PORT}"
    echo "[INTELLIGENCE] READY"
else
    free_port "$INTEL_PORT"
    echo "  Launching on http://${INTEL_HOST}:${INTEL_PORT} ..."

    cd "$SERVER_DIR"
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="$SERVER_DIR" \
    NAVOS_DATA_DIR="$REPO_ROOT/data" \
    NAVOS_ARTIFACTS_DIR="$ARTIFACTS_DIR" \
        "$PYTHON_BIN" -m uvicorn \
            --host "$INTEL_HOST" \
            --port "$INTEL_PORT" \
            --log-level warning \
            app.main:app > /tmp/navos_server.log 2>&1 &
    register_pid $! "Intelligence Server"
    cd "$REPO_ROOT"

    echo "  Waiting for /health ..."
    READY=0
    for i in $(seq 1 60); do
        if curl -s "http://127.0.0.1:${INTEL_PORT}/health" 2>/dev/null | grep -q "ok"; then
            READY=1
            break
        fi
        sleep 1
        if [ $((i % 10)) -eq 0 ]; then
            echo "  ... still waiting ($i seconds)"
        fi
    done

    if [ $READY -ne 1 ]; then
        echo "  [ERROR] Intelligence Server failed to start within 60 seconds."
        exit 1
    fi
    echo "  [DONE] Intelligence Server READY."
    echo "[INTELLIGENCE] READY"
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 8: Start C++ Hardware (physical sensors)
# ══════════════════════════════════════════════════════════════════════════════
step "Starting Physical Hardware..."
echo "[HARDWARE] Starting"

echo "  Mode:         PHYSICAL SENSORS"
echo "  Serial Port:  $SERIAL_PORT"
echo "  Interval:     ${INTERVAL}s"
echo "  Node ID:      $NODE_ID"

# Create a temporary config override with mock_mode=false
HW_RUNTIME_CONFIG=$(mktemp /tmp/navos_hw_config_XXXXXX.json)
cat > "$HW_RUNTIME_CONFIG" <<EOF
{
    "server_url": "http://localhost:${INTEL_PORT}",
    "node_id": "${NODE_ID}",
    "sampling_interval_seconds": ${INTERVAL},
    "retry_max_attempts": 5,
    "retry_base_delay_seconds": 2,
    "http_timeout_seconds": 10,
    "mock_mode": false,
    "scenario": "normal",
    "serial_port": "${SERIAL_PORT}",
    "serial_baud": 115200,
    "serial_timeout_ms": 5000
}
EOF

echo ""
echo "  Sensor warm-up period: 30 seconds..."
echo "[HARDWARE] Warming sensors"
echo "  (MQ-series gas sensors need time to stabilize)"

"$HW_BINARY" \
    --config "$HW_RUNTIME_CONFIG" \
    --node-id "$NODE_ID" \
    --interval "$INTERVAL" &
register_pid $! "Physical Hardware"

# Warm-up countdown
for i in $(seq 30 -5 5); do
    sleep 5
    if ! kill -0 "${PIDS[-1]}" 2>/dev/null; then
        echo ""
        echo "  [ERROR] Physical hardware process exited during warm-up."
        echo ""
        echo "  Possible causes:"
        echo "    • Serial port $SERIAL_PORT is not accessible (permissions?)"
        echo "    • Physical sensors are not connected"
        echo "    • Sensor driver not yet implemented"
        echo ""
        echo "  If sensors are not yet available, use simulation mode instead:"
        echo "    ./run_simulation.sh"
        rm -f "$HW_RUNTIME_CONFIG"
        exit 1
    fi
    echo "  ... warm-up: ${i}s remaining"
done

echo "  [DONE] Sensor warm-up complete. READY."
echo "[HARDWARE] READY"
echo "[SSE] Connected"
echo "[DISPLAY] Ready"

# Clean up temp config
rm -f "$HW_RUNTIME_CONFIG"

# ══════════════════════════════════════════════════════════════════════════════
# Running
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo "========================================"
echo "  NAVOSEDGE IS RUNNING (HARDWARE MODE)"
echo "========================================"
echo "[NAVOSEDGE] Edge application running"
echo ""
echo "  Intelligence : http://127.0.0.1:${INTEL_PORT}"
echo "  Hardware     : PHYSICAL SENSORS"
echo "  Serial Port  : ${SERIAL_PORT}"
echo "  Display      : MPI3501"
echo "  Interval     : ${INTERVAL}s"
echo "  Node ID      : ${NODE_ID}"
echo ""
echo "  API Endpoints:"
echo "    Health:     http://127.0.0.1:${INTEL_PORT}/health"
echo "    Latest AQI: http://127.0.0.1:${INTEL_PORT}/api/v1/nodes/${NODE_ID}/latest"
echo "    SSE Events: http://127.0.0.1:${INTEL_PORT}/hardware/events?node_id=${NODE_ID}"
echo ""
echo "  Press Ctrl+C to stop."
echo ""

wait

