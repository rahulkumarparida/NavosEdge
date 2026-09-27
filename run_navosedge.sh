#!/bin/bash
# ==============================================================================
# NavosEdge One-Command Launcher (UNO Q Deployment)
# ==============================================================================
set -e

# Load environment variables if .env exists
if [ -f ".env" ]; then
    echo "[NAVOS] Loading configuration from .env"
    set -a
    source .env
    set +a
else
    echo "[NAVOS] Warning: .env file not found. Using defaults. (Copy .env.example to .env to configure)"
fi

# Function to start the Intelligence Server
start_server() {
    echo "[NAVOS] Starting Python Intelligence Server..."
    # Ensure dependencies are installed (optional but good for first run)
    if [ ! -d "Intelligence/Server/venv" ]; then
        echo "[NAVOS] Creating virtual environment..."
        python3 -m venv Intelligence/Server/venv
    fi
    source Intelligence/Server/venv/bin/activate
    
    # Check if fastapi/uvicorn are available
    if ! python -c "import fastapi" &> /dev/null; then
        echo "[NAVOS] Installing Python dependencies..."
        pip install -r Intelligence/Server/requirements.txt
    fi
    
    cd Intelligence/Server
    # Start the server in the background
    uvicorn app.main:app --host ${NAVOS_HOST:-0.0.0.0} --port ${NAVOS_PORT:-8420} &
    SERVER_PID=$!
    cd ../..
    
    # Wait for the server to become ready
    echo "[NAVOS] Waiting for Intelligence Server to start..."
    for i in {1..30}; do
        if curl -s http://${NAVOS_HOST:-127.0.0.1}:${NAVOS_PORT:-8420}/health > /dev/null; then
            echo "[NAVOS] Server is up and running!"
            break
        fi
        sleep 1
    done
}

# Function to build and start the C++ Hardware Client
start_hardware() {
    echo "[NAVOS] Building C++ Hardware Bridge..."
    cd Hardware
    mkdir -p build && cd build
    cmake .. -DCMAKE_BUILD_TYPE=Release
    make -j$(nproc 2>/dev/null || echo 1)
    
    echo "[NAVOS] Starting C++ Hardware Bridge..."
    ./navos_hardware_bridge &
    HW_PID=$!
    cd ../..
}

# Cleanup function to kill background processes on exit
cleanup() {
    echo "[NAVOS] Stopping NavosEdge..."
    if [ ! -z "$HW_PID" ]; then kill $HW_PID 2>/dev/null || true; fi
    if [ ! -z "$SERVER_PID" ]; then kill $SERVER_PID 2>/dev/null || true; fi
    exit 0
}

trap cleanup SIGINT SIGTERM

case "$1" in
    server)
        start_server
        wait $SERVER_PID
        ;;
    hardware)
        start_hardware
        wait $HW_PID
        ;;
    all|"")
        start_server
        start_hardware
        echo "[NAVOS] NavosEdge is running. Press Ctrl+C to stop."
        wait $SERVER_PID $HW_PID
        ;;
    *)
        echo "Usage: $0 {server|hardware|all}"
        exit 1
        ;;
esac
