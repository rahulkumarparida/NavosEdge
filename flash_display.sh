#!/usr/bin/env bash
# ==============================================================================
# NavosEdge — MCU Display Firmware Flashing Script
# ==============================================================================
# Compiles and deploys the NavosEdge physical MPI3501 GUI application onto the
# Arduino UNO Q MCU (arduino:zephyr:unoq). Automatically fetches/clones the
# UNOQ_MPI3501 library from GitHub if not present.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ARDUINO_CLI_BIN=""

if command -v arduino-cli >/dev/null 2>&1; then
    ARDUINO_CLI_BIN="arduino-cli"
elif [ -x "/home/rahulroxx/.local/share/arduino_applab_workspace/resources/arduino/arduino-cli/arduino-cli" ]; then
    ARDUINO_CLI_BIN="/home/rahulroxx/.local/share/arduino_applab_workspace/resources/arduino/arduino-cli/arduino-cli"
else
    echo "[FLASH] ERROR: arduino-cli tool not found."
    exit 1
fi

LIB_REPO_URL="https://github.com/jagdishtripathy/UNOQ_MPI3501.git"
LOCAL_LIB_DIR="$SCRIPT_DIR/Hardware/third_party/UNOQ_MPI3501"

if [ ! -d "$LOCAL_LIB_DIR" ] && [ ! -d "$HOME/Arduino/libraries/UNOQ_MPI3501" ]; then
    echo "[FLASH] UNOQ_MPI3501 library not found locally. Cloning from $LIB_REPO_URL..."
    mkdir -p "$SCRIPT_DIR/Hardware/third_party"
    git clone "$LIB_REPO_URL" "$LOCAL_LIB_DIR"
    echo "[FLASH] UNOQ_MPI3501 library successfully cloned to $LOCAL_LIB_DIR"
fi

CONFIG_DIR="/home/rahulroxx/.local/share/arduino_applab_workspace/arduino15/data"
LIB_DIR1="/home/rahulroxx/.local/share/arduino_applab_workspace/arduino15/user/libraries"
LIB_DIR2="$SCRIPT_DIR/Hardware/third_party"
LIB_DIR3="$HOME/Arduino/libraries"
PORT="/dev/ttyACM0"
FQBN="arduino:zephyr:unoq"
SKETCH_DIR="Hardware/mcu_display"

echo "============================================================"
echo " NavosEdge — MCU Physical Display Flasher"
echo "============================================================"
echo "  Target Board: $FQBN"
echo "  Port:         $PORT"
echo "  Sketch:       $SKETCH_DIR"
echo "============================================================"

echo "[FLASH] Compiling MCU display sketch..."
if ! "$ARDUINO_CLI_BIN" --config-dir "$CONFIG_DIR" --libraries "$LIB_DIR1" --libraries "$LIB_DIR2" --libraries "$LIB_DIR3" compile --fqbn "$FQBN" "$SKETCH_DIR"; then
    echo "[FLASH] ERROR: Compilation failed."
    exit 1
fi

echo "[FLASH] Deploying firmware to Arduino UNO Q MCU over $PORT..."
if ! "$ARDUINO_CLI_BIN" --config-dir "$CONFIG_DIR" upload -p "$PORT" --discovery-timeout 5s --fqbn "$FQBN" "$SKETCH_DIR"; then
    echo "[FLASH] ERROR: Flashing failed."
    exit 1
fi

echo "============================================================"
echo " [FLASH] SUCCESS: MCU display firmware flashed and active!"
echo "============================================================"
