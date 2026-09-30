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

# 3. Ensure repository-local third-party dependencies exist
THIRD_PARTY_DIR="$SCRIPT_DIR/Hardware/third_party"
mkdir -p "$THIRD_PARTY_DIR"

MPI3501_LIB_DIR="$THIRD_PARTY_DIR/UNOQ_MPI3501"
if [ ! -d "$MPI3501_LIB_DIR" ] && [ ! -d "$HOME_DIR/Arduino/libraries/UNOQ_MPI3501" ]; then
    echo "[FLASH] UNOQ_MPI3501 library missing locally. Cloning from GitHub..."
    git clone https://github.com/jagdishtripathy/UNOQ_MPI3501.git "$MPI3501_LIB_DIR"
fi

ARDUINOJSON_LIB_DIR="$THIRD_PARTY_DIR/ArduinoJson"
if [ ! -d "$ARDUINOJSON_LIB_DIR" ] && [ ! -d "$HOME_DIR/Arduino/libraries/ArduinoJson" ] && [ ! -d "$CONFIG_DIR/user/libraries/ArduinoJson" ]; then
    echo "[FLASH] ArduinoJson library missing locally. Cloning from GitHub..."
    git clone --depth 1 https://github.com/bblanchon/ArduinoJson.git "$ARDUINOJSON_LIB_DIR"
fi

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
echo "  Serial Port:        $PORT"
echo "  Sketch Location:    $SKETCH_DIR"
echo "============================================================"

# 7. Compile MCU Display Sketch
echo "[FLASH] Compiling MCU display sketch..."
if ! "$ARDUINO_CLI_BIN" "${CONFIG_ARG[@]}" "${LIB_ARGS[@]}" compile --fqbn "$FQBN" "$SKETCH_DIR"; then
    echo "[FLASH] ERROR: MCU sketch compilation failed."
    exit 1
fi

# 8. Deploy Firmware to MCU
echo "[FLASH] Deploying firmware to Arduino UNO Q MCU over $PORT..."
if ! "$ARDUINO_CLI_BIN" "${CONFIG_ARG[@]}" upload -p "$PORT" --discovery-timeout 5s --fqbn "$FQBN" "$SKETCH_DIR"; then
    echo "[FLASH] ERROR: Firmware deployment to MCU failed."
    exit 1
fi

echo "============================================================"
echo " [FLASH] SUCCESS: MCU display firmware flashed and active!"
echo "============================================================"
