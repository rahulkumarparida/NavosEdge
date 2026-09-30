#!/usr/bin/env bash
# ==============================================================================
# NavosEdge — MCU Display Firmware Flashing Script
# ==============================================================================
# Portable script to compile and deploy the NavosEdge physical MPI3501 GUI
# application onto the Arduino UNO Q MCU (arduino:zephyr:unoq).
# Dynamic environment, config, and library resolution across all Linux users.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CURRENT_USER="$(id -un 2>/dev/null || echo "$USER")"
HOME_DIR="${HOME:-/home/$CURRENT_USER}"

# 1. Locate arduino-cli binary dynamically
ARDUINO_CLI_BIN=""

if [ -n "$ARDUINO_CLI" ] && command -v "$ARDUINO_CLI" >/dev/null 2>&1; then
    ARDUINO_CLI_BIN="$ARDUINO_CLI"
elif command -v arduino-cli >/dev/null 2>&1; then
    ARDUINO_CLI_BIN="$(command -v arduino-cli)"
elif [ -x "$HOME_DIR/.local/bin/arduino-cli" ]; then
    ARDUINO_CLI_BIN="$HOME_DIR/.local/bin/arduino-cli"
elif [ -x "$HOME_DIR/.local/share/arduino_applab_workspace/resources/arduino/arduino-cli/arduino-cli" ]; then
    ARDUINO_CLI_BIN="$HOME_DIR/.local/share/arduino_applab_workspace/resources/arduino/arduino-cli/arduino-cli"
elif [ -x "/usr/local/bin/arduino-cli" ]; then
    ARDUINO_CLI_BIN="/usr/local/bin/arduino-cli"
elif [ -x "/usr/bin/arduino-cli" ]; then
    ARDUINO_CLI_BIN="/usr/bin/arduino-cli"
else
    echo "[FLASH] ERROR: arduino-cli tool not found in PATH or standard user directories."
    echo "[FLASH] Please install arduino-cli or export ARDUINO_CLI=/path/to/arduino-cli."
    exit 1
fi

# 2. Locate Arduino Config Directory dynamically
CONFIG_DIR=""
CONFIG_ARG=()

if [ -n "$ARDUINO_CONFIG_DIR" ] && [ -d "$ARDUINO_CONFIG_DIR" ]; then
    CONFIG_DIR="$ARDUINO_CONFIG_DIR"
elif [ -d "$HOME_DIR/.local/share/arduino_applab_workspace/arduino15/data" ]; then
    CONFIG_DIR="$HOME_DIR/.local/share/arduino_applab_workspace/arduino15/data"
elif [ -d "$HOME_DIR/.arduino15" ]; then
    CONFIG_DIR="$HOME_DIR/.arduino15"
else
    CONFIG_DIR="$HOME_DIR/.arduino15"
    mkdir -p "$CONFIG_DIR"
fi

if [ -n "$CONFIG_DIR" ] && [ -d "$CONFIG_DIR" ]; then
    CONFIG_ARG=(--config-dir "$CONFIG_DIR")
fi

# 3. Ensure required third-party dependencies exist (auto-installed on demand)
THIRD_PARTY_DIR="$SCRIPT_DIR/Hardware/third_party"
mkdir -p "$THIRD_PARTY_DIR"

ensure_lib() {
    local lib_name="$1"
    local repo_url="$2"
    local target_dir="$THIRD_PARTY_DIR/$lib_name"

    if [ ! -d "$target_dir" ] && \
       [ ! -d "$HOME_DIR/Arduino/libraries/$lib_name" ] && \
       [ ! -d "$CONFIG_DIR/user/libraries/$lib_name" ]; then
        echo "[FLASH] Library '$lib_name' not found locally. Auto-downloading directly on device..."
        git clone --depth 1 "$repo_url" "$target_dir"
    fi
}

ensure_lib "UNOQ_MPI3501" "https://github.com/jagdishtripathy/UNOQ_MPI3501.git"
ensure_lib "ArduinoJson" "https://github.com/bblanchon/ArduinoJson.git"
ensure_lib "Arduino_RouterBridge" "https://github.com/arduino-libraries/Arduino_RouterBridge.git"
ensure_lib "Arduino_RPClite" "https://github.com/arduino-libraries/Arduino_RPClite.git"
ensure_lib "ArxContainer" "https://github.com/hideakitai/ArxContainer.git"
ensure_lib "ArxTypeTraits" "https://github.com/hideakitai/ArxTypeTraits.git"
ensure_lib "DebugLog" "https://github.com/hideakitai/DebugLog.git"
ensure_lib "MsgPack" "https://github.com/hideakitai/MsgPack.git"

# 4. Assemble library search paths
LIB_ARGS=()
LIB_PATHS_DISPLAY=""

add_lib_dir() {
    local dir="$1"
    if [ -d "$dir" ]; then
        LIB_ARGS+=(--libraries "$dir")
        if [ -z "$LIB_PATHS_DISPLAY" ]; then
            LIB_PATHS_DISPLAY="$dir"
        else
            LIB_PATHS_DISPLAY="$LIB_PATHS_DISPLAY, $dir"
        fi
    fi
}

add_lib_dir "$THIRD_PARTY_DIR"
add_lib_dir "$CONFIG_DIR/user/libraries"
add_lib_dir "$HOME_DIR/Arduino/libraries"

# 5. Target Board & Port Configuration
FQBN="${ARDUINO_FQBN:-${FQBN:-arduino:zephyr:unoq}}"
PORT="${ARDUINO_PORT:-${PORT:-/dev/ttyACM0}}"
SKETCH_DIR="$SCRIPT_DIR/Hardware/mcu_display"

PORT_ARGS=()
if [ -e "$PORT" ]; then
    PORT_ARGS=(-p "$PORT")
fi

# 6. Diagnostics Header
echo "============================================================"
echo " NavosEdge — MCU Physical Display Flasher"
echo "============================================================"
echo "  Current User:       $CURRENT_USER"
echo "  Home Directory:     $HOME_DIR"
echo "  Arduino CLI Path:   $ARDUINO_CLI_BIN"
echo "  Config Directory:   ${CONFIG_DIR:-"(default)"}"
echo "  Library Paths:      ${LIB_PATHS_DISPLAY:-"(default)"}"
echo "  Target Board FQBN:  $FQBN"
echo "  Serial Port:        ${PORT}${PORT_ARGS:+" (active)"}"
echo "  Sketch Location:    $SKETCH_DIR"
echo "============================================================"

# 7. Compile MCU Display Sketch
echo "[FLASH] Compiling MCU display sketch..."
if ! "$ARDUINO_CLI_BIN" "${CONFIG_ARG[@]}" "${LIB_ARGS[@]}" compile --fqbn "$FQBN" "$SKETCH_DIR"; then
    echo "[FLASH] ERROR: MCU sketch compilation failed."
    exit 1
fi

# 8. Deploy Firmware to MCU
echo "[FLASH] Deploying firmware to Arduino UNO Q MCU..."
if ! "$ARDUINO_CLI_BIN" "${CONFIG_ARG[@]}" upload "${PORT_ARGS[@]}" --discovery-timeout 5s --fqbn "$FQBN" "$SKETCH_DIR"; then
    echo "[FLASH] ERROR: Firmware deployment to MCU failed."
    exit 1
fi

echo "============================================================"
echo " [FLASH] SUCCESS: MCU display firmware flashed and active!"
echo "============================================================"
