#!/bin/bash
# ==============================================================================
# NavosEdge — UNO Q Preflight Check
# ==============================================================================
# Verifies that the target system meets all requirements for NavosEdge deployment.
# Does NOT modify SSH, networking, security, or system settings.
#
# Usage: bash scripts/unoq_preflight.sh
# ==============================================================================

set -e

PASS=0
FAIL=0
WARN=0

pass() { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
fail() { echo "  [FAIL] $1"; FAIL=$((FAIL + 1)); }
warn() { echo "  [WARN] $1"; WARN=$((WARN + 1)); }

echo "============================================================"
echo "NavosEdge — UNO Q Preflight Check"
echo "============================================================"
echo ""

# 1. Architecture
echo "--- Architecture ---"
ARCH=$(uname -m)
echo "  Architecture: $ARCH"
if [[ "$ARCH" == "aarch64" || "$ARCH" == "arm64" ]]; then
    pass "ARM64 architecture detected"
elif [[ "$ARCH" == "x86_64" ]]; then
    warn "x86_64 detected (development machine — not UNO Q)"
else
    fail "Unsupported architecture: $ARCH"
fi

# 2. OS
echo ""
echo "--- Operating System ---"
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "  OS: $NAME $VERSION_ID"
    if [[ "$ID" == "debian" || "$ID_LIKE" == *"debian"* ]]; then
        pass "Debian-based OS"
    else
        warn "Not Debian-based: $ID"
    fi
else
    warn "Cannot determine OS"
fi

# 3. Python
echo ""
echo "--- Python ---"
if command -v python3 &>/dev/null; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    echo "  Python: $PY_VER"
    PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
    if [[ "$PY_MAJOR" -ge 3 && "$PY_MINOR" -ge 10 ]]; then
        pass "Python >= 3.10"
    else
        fail "Python $PY_VER is too old (need >= 3.10)"
    fi
else
    fail "python3 not found"
fi

if command -v python3 -m venv --help &>/dev/null 2>&1 || python3 -c "import venv" 2>/dev/null; then
    pass "python3-venv available"
else
    fail "python3-venv not available (install with: apt install python3-venv)"
fi

# 4. RAM
echo ""
echo "--- Memory ---"
if [ -f /proc/meminfo ]; then
    TOTAL_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    TOTAL_MB=$((TOTAL_KB / 1024))
    AVAIL_KB=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
    AVAIL_MB=$((AVAIL_KB / 1024))
    echo "  Total RAM:     ${TOTAL_MB} MB"
    echo "  Available RAM: ${AVAIL_MB} MB"
    if [ "$TOTAL_MB" -ge 1500 ]; then
        pass "Sufficient RAM (>= 1.5 GB)"
    else
        fail "Insufficient RAM: ${TOTAL_MB} MB (need >= 1500 MB)"
    fi
    if [ "$AVAIL_MB" -ge 500 ]; then
        pass "Sufficient available RAM (>= 500 MB)"
    else
        warn "Low available RAM: ${AVAIL_MB} MB"
    fi
else
    warn "Cannot read /proc/meminfo"
fi

# 5. Storage
echo ""
echo "--- Storage ---"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DISK_AVAIL_KB=$(df -k "$PROJECT_DIR" 2>/dev/null | tail -1 | awk '{print $4}')
DISK_AVAIL_MB=$((DISK_AVAIL_KB / 1024))
echo "  Available disk: ${DISK_AVAIL_MB} MB"
if [ "$DISK_AVAIL_MB" -ge 500 ]; then
    pass "Sufficient disk space (>= 500 MB)"
elif [ "$DISK_AVAIL_MB" -ge 200 ]; then
    warn "Low disk space: ${DISK_AVAIL_MB} MB (recommended >= 500 MB)"
else
    fail "Insufficient disk space: ${DISK_AVAIL_MB} MB"
fi

# 6. Required system packages
echo ""
echo "--- System Packages ---"
for pkg in gcc g++ cmake make curl; do
    if command -v $pkg &>/dev/null; then
        pass "$pkg available"
    else
        warn "$pkg not found (may be needed for C++ hardware bridge)"
    fi
done

# 7. Model files
echo ""
echo "--- Model Artifacts ---"
ARTIFACTS_DIR="$PROJECT_DIR/Intelligence/Server/artifacts"
for artifact in gasnet_weights.npz model_metadata.json preprocess.pkl source_classifier_model.pkl; do
    if [ -f "$ARTIFACTS_DIR/$artifact" ]; then
        SIZE=$(du -h "$ARTIFACTS_DIR/$artifact" | cut -f1)
        pass "$artifact ($SIZE)"
    elif [ "$artifact" = "gasnet_weights.npz" ] || [ "$artifact" = "model_metadata.json" ]; then
        # These might not exist yet if export hasn't been run
        if [ -f "$ARTIFACTS_DIR/gasnet.pt" ]; then
            warn "$artifact not found (run Training/export_gasnet.py to generate)"
        else
            fail "$artifact not found and gasnet.pt also missing"
        fi
    else
        warn "$artifact not found (classifier will run in degraded mode)"
    fi
done

# 8. Writable directories
echo ""
echo "--- Permissions ---"
for dir in "$PROJECT_DIR/Intelligence/Server/data" "$PROJECT_DIR/Intelligence/Server/artifacts"; do
    mkdir -p "$dir" 2>/dev/null
    if [ -w "$dir" ]; then
        pass "$dir is writable"
    else
        fail "$dir is not writable"
    fi
done

# 9. Network
echo ""
echo "--- Network ---"
if ping -c 1 -W 2 8.8.8.8 &>/dev/null; then
    pass "Internet connectivity available"
else
    warn "No internet (core inference works offline)"
fi

if curl -s --max-time 2 http://localhost:8420/health &>/dev/null; then
    pass "Intelligence Server already running on port 8420"
else
    echo "  [INFO] Intelligence Server not running (normal for preflight)"
fi

# 10. Hardware interfaces
echo ""
echo "--- Hardware Interfaces ---"
if [ -d /sys/class/gpio ]; then
    pass "GPIO available"
else
    warn "No GPIO (simulation mode available)"
fi

if ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -1 &>/dev/null; then
    pass "Serial device detected"
else
    warn "No serial device (use simulation mode)"
fi

# 11. PyTorch check
echo ""
echo "--- PyTorch Status ---"
if python3 -c "import torch" 2>/dev/null; then
    TORCH_SIZE=$(python3 -c "import torch; import os; p=os.path.dirname(torch.__file__); total=sum(os.path.getsize(os.path.join(dp,f)) for dp,dn,fn in os.walk(p) for f in fn); print(f'{total/(1024*1024):.0f}')" 2>/dev/null)
    warn "PyTorch is installed (${TORCH_SIZE:-unknown} MB) — not needed on UNO Q"
else
    pass "PyTorch not installed (correct for UNO Q deployment)"
fi

# Summary
echo ""
echo "============================================================"
echo "PREFLIGHT SUMMARY"
echo "============================================================"
echo "  PASS: $PASS"
echo "  WARN: $WARN"
echo "  FAIL: $FAIL"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "  RESULT: READY FOR DEPLOYMENT"
    exit 0
elif [ "$FAIL" -le 2 ]; then
    echo "  RESULT: MOSTLY READY (resolve $FAIL failure(s) above)"
    exit 1
else
    echo "  RESULT: NOT READY ($FAIL failures)"
    exit 2
fi
