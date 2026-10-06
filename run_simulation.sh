#!/usr/bin/env bash
# ==============================================================================
# NavosEdge — Simulation Mode Launcher (run_simulation.sh)
# ==============================================================================
# One-command startup for development/testing WITHOUT physical sensors.
#
# Flow:
#   Environment check → Python venv → pip install → C++ build →
#   Display build/flash → Intelligence Server → Health check →
#   C++ Hardware (mock sensors) → SSE → MPI3501 display
#
# Usage:
#   ./run_simulation.sh
#   ./run_simulation.sh --scenario traffic
#   ./run_simulation.sh --scenario dust_construction --interval 10
#   ./run_simulation.sh --skip-flash
#   ./run_simulation.sh --help
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
SCENARIO="${NAVOS_SCENARIO:-normal}"
INTERVAL="${NAVOS_SENSOR_INTERVAL:-60}"
SKIP_FLASH=false
SKIP_DISPLAY_SIM=false

# ── Parse CLI arguments ──────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scenario|-s)    SCENARIO="$2";  shift 2 ;;
        --interval|-i)    INTERVAL="$2";  shift 2 ;;
        --node-id|-n)     NODE_ID="$2";   shift 2 ;;
        --skip-flash)     SKIP_FLASH=true; shift ;;
        --skip-display-sim) SKIP_DISPLAY_SIM=true; shift ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --scenario, -s <name>   Simulation scenario (default: $SCENARIO)"
            echo "                          Available: clean_indoor, traffic, dust_construction,"
            echo "                          combustion_smoke, high_humidity, pm_spike, gas_spike,"
            echo "                          mixed_pollution, stable, sensor_fault"
            echo "  --interval, -i <sec>    Sampling interval in seconds (default: $INTERVAL)"
            echo "  --node-id,  -n <id>     Node identifier (default: $NODE_ID)"
            echo "  --skip-flash            Skip MCU display flashing step"
            echo "  --skip-display-sim      Skip desktop display simulation build"
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
    # Give processes a moment to exit gracefully
    sleep 1
    # Force-kill anything still alive
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
TOTAL_STEPS=7
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
echo "     NAVOSEDGE SIMULATION MODE"
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

# Check python3-venv
if ! python3 -c "import venv" 2>/dev/null; then
    MISSING_DEPS+=("python3-venv")
    echo "  [MISS] python3-venv — sudo apt install python3-venv"
else
    echo "  [ OK ] python3-venv"
fi

# Check libcurl-dev (needed for C++ build)
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
# STEP 2: Python virtual environment & dependencies
# ══════════════════════════════════════════════════════════════════════════════
step "Preparing Python environment..."

SERVER_DIR="$REPO_ROOT/Intelligence/Server"
VENV_DIR="$SERVER_DIR/venv"
PYTHON_BIN="$VENV_DIR/bin/python3"
REQUIREMENTS_FILE="$REPO_ROOT/requirements/unoq.txt"

# Fallback to server-local requirements if unoq.txt doesn't exist
if [ ! -f "$REQUIREMENTS_FILE" ]; then
    REQUIREMENTS_FILE="$SERVER_DIR/requirements.txt"
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "  Creating virtual environment at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    echo "  Installing Python dependencies..."
    "$PYTHON_BIN" -m pip install --quiet --upgrade pip
    "$PYTHON_BIN" -m pip install --quiet -r "$REQUIREMENTS_FILE"
    echo "  [DONE] Virtual environment created and dependencies installed."
else
    # Check if key dependency is installed; reinstall if missing
    if ! "$PYTHON_BIN" -c "import fastapi" 2>/dev/null; then
        echo "  Dependencies missing in existing venv. Installing..."
        "$PYTHON_BIN" -m pip install --quiet -r "$REQUIREMENTS_FILE"
    else
        echo "  [DONE] Virtual environment exists and dependencies OK."
    fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Build C++ Hardware application
# ══════════════════════════════════════════════════════════════════════════════
step "Building C++ Hardware application..."

HW_BUILD_DIR="$REPO_ROOT/Hardware/build"
HW_BINARY="$HW_BUILD_DIR/navos_hardware_bridge"

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

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Build/flash MPI3501 display
# ══════════════════════════════════════════════════════════════════════════════
step "Display build/flash..."

# 4a. Build desktop display simulation (text-based TFT sim)
if [ "$SKIP_DISPLAY_SIM" != "true" ]; then
    DISPLAY_BUILD_DIR="$REPO_ROOT/Hardware/display/build"
    DISPLAY_BINARY="$DISPLAY_BUILD_DIR/navos_display_sim"
    mkdir -p "$DISPLAY_BUILD_DIR"

    if [ ! -f "$DISPLAY_BINARY" ] || \
       [ "$REPO_ROOT/Hardware/display/CMakeLists.txt" -nt "$DISPLAY_BINARY" ] || \
       [ "$REPO_ROOT/Hardware/display/main.cpp" -nt "$DISPLAY_BINARY" ]; then
        echo "  Building desktop display simulation..."
        cmake -S "$REPO_ROOT/Hardware/display" -B "$DISPLAY_BUILD_DIR" -DCMAKE_BUILD_TYPE=Release > /dev/null 2>&1
        make -C "$DISPLAY_BUILD_DIR" -j"$(nproc 2>/dev/null || echo 1)" > /dev/null 2>&1
        echo "  [DONE] navos_display_sim built."
    else
        echo "  [DONE] navos_display_sim is up to date."
    fi
else
    echo "  [SKIP] Desktop display simulation build skipped."
fi

# 4b. Flash MCU display firmware (arduino-cli)
if [ "$SKIP_FLASH" != "true" ]; then
    if command -v arduino-cli &>/dev/null || \
       [ -x "$HOME/.local/bin/arduino-cli" ] || \
       [ -x "/usr/local/bin/arduino-cli" ]; then
        echo "  Flashing MCU display firmware..."
        if bash "$REPO_ROOT/flash_display.sh"; then
            echo "  [DONE] MCU display firmware flashed."
        else
            echo "  [WARN] MCU flash failed. Display may not update on physical MPI3501."
            echo "         The simulation will still run (C++ text output mode)."
        fi
    else
        echo "  [SKIP] arduino-cli not found. MCU display flash skipped."
        echo "         Install: curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh"
        echo "         Or: ./flash_display.sh  (after installing arduino-cli)"
    fi
else
    echo "  [SKIP] Display flashing skipped (--skip-flash)."
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: Verify model artifacts
# ══════════════════════════════════════════════════════════════════════════════
step "Verifying model artifacts..."

ARTIFACTS_DIR="$SERVER_DIR/artifacts"
ARTIFACT_WARN=false

for artifact in gasnet_weights.npz model_metadata.json; do
    if [ -f "$ARTIFACTS_DIR/$artifact" ]; then
        echo "  [ OK ] $artifact"
    else
        echo "  [WARN] $artifact not found — inference will run in degraded mode"
        ARTIFACT_WARN=true
    fi
done

for artifact in preprocess.pkl source_classifier_model.pkl; do
    if [ -f "$ARTIFACTS_DIR/$artifact" ]; then
        echo "  [ OK ] $artifact"
    else
        echo "  [WARN] $artifact not found — source classification unavailable"
        ARTIFACT_WARN=true
    fi
done

if [ "$ARTIFACT_WARN" = "true" ]; then
    echo "  AQI calculation and advisory still work without ML models."
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 6: Start Intelligence Server & wait for readiness
# ══════════════════════════════════════════════════════════════════════════════
step "Starting Intelligence Server..."

# Check if already running
if curl -s "http://${INTEL_HOST}:${INTEL_PORT}/health" 2>/dev/null | grep -q "ok"; then
    echo "  Intelligence Server already running on http://${INTEL_HOST}:${INTEL_PORT}"
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
        echo "  Check logs or run manually:"
        echo "    cd Intelligence/Server && ../venv/bin/python3 -m uvicorn app.main:app --port $INTEL_PORT"
        exit 1
    fi
    echo "  [DONE] Intelligence Server READY."
fi

# ══════════════════════════════════════════════════════════════════════════════
# STEP 7: Start C++ Hardware Simulator (mock sensors)
# ══════════════════════════════════════════════════════════════════════════════
step "Starting Hardware Simulator..."

echo "  Mode:     MOCK (simulation)"
echo "  Scenario: $SCENARIO"
echo "  Interval: ${INTERVAL}s"
echo "  Node ID:  $NODE_ID"

NAVOS_SENSOR_MODE=mock \
"$HW_BINARY" \
    --config "$REPO_ROOT/Hardware/config/hardware_config.json" \
    --node-id "$NODE_ID" \
    --scenario "$SCENARIO" \
    --interval "$INTERVAL" &
register_pid $! "Hardware Simulator"

# Give C++ bridge a moment to initialize
sleep 2

# Verify C++ started
if ! kill -0 "${PIDS[-1]}" 2>/dev/null; then
    echo "  [ERROR] Hardware simulator exited immediately."
    echo "  Try running manually: $HW_BINARY --config Hardware/config/hardware_config.json --scenario $SCENARIO"
    exit 1
fi

# ══════════════════════════════════════════════════════════════════════════════
# Running
# ══════════════════════════════════════════════════════════════════════════════
echo ""
echo "========================================"
echo "  NAVOSEDGE IS RUNNING"
echo "========================================"
echo ""
echo "  Intelligence : http://127.0.0.1:${INTEL_PORT}"
echo "  Hardware     : MOCK (simulation)"
echo "  Display      : MPI3501 / text sim"
echo "  Scenario     : ${SCENARIO}"
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
