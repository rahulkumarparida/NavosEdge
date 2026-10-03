# Phase 14 — Single Systemd Edge Boot Service (`navosedge.service`)

## 1. Overview & Objective

This module establishes a **single systemd boot service** (`navosedge.service`) to manage the complete NavosEdge air quality intelligence application on the Arduino UNO Q.

Instead of running separate, fragmented services for Python Intelligence and C++ Hardware, systemd supervises **one master process** (`run_hardware.sh --no-build`). The master launcher orchestrates the startup sequence, verifies prerequisites, connects Server-Sent Events (SSE), updates the MPI3501 display, and gracefully cleans up all child processes on shutdown.

---

## 2. Architecture & Boot Lifecycle

```text
               Arduino UNO Q Power On / Boot
                            │
                            ▼
                  systemd Service Manager
                            │
                            ▼
                    navosedge.service
                            │
                            ▼
             run_hardware.sh --no-build
             (Master Hardware Launcher)
                            │
     ┌──────────────────────┴──────────────────────┐
     │                                             │
     ▼                                             ▼
Check Environment                            Verify Binaries
(Verify Python venv)                     (Verify C++ bridge)
     │                                             │
     └──────────────────────┬──────────────────────┘
                            │
                            ▼
                Intelligence Server (:8420)
                            │
                   Wait for /health (OK)
                            │
                            ▼
                   C++ Hardware Bridge
                            │
                   30-Second Sensor Warm-up
                            │
                [HARDWARE] READY & Handshake
                            │
                            ▼
                    SSE Data Stream
                            │
              60-Second Data Acquisition Cycle
                            │
                            ▼
                  MPI3501 Display Dashboard
```

---

## 3. Key Components & Changes Applied

### A. Master Hardware Launcher ([`run_hardware.sh`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/run_hardware.sh))
- **`--no-build` Fast-Boot Mode**: Added a `--no-build` flag for production systemd boot execution. In `--no-build` mode, the script verifies that the Python virtual environment and C++ binaries exist, skipping CMake builds, pip dependency installs, and display reflashing.
- **Structured Journal Logging**: Updated output formatting to use explicit prefix tags:
  - `[NAVOSEDGE] Starting`
  - `[INTELLIGENCE] Starting`
  - `[INTELLIGENCE] READY`
  - `[HARDWARE] Starting`
  - `[HARDWARE] Warming sensors`
  - `[HARDWARE] READY`
  - `[SSE] Connected`
  - `[DISPLAY] Ready`
  - `[NAVOSEDGE] Edge application running`
- **Graceful Shutdown & Signal Traps**: Configured signal handlers (`trap cleanup SIGINT SIGTERM EXIT`) so that stopping the service (`sudo systemctl stop navosedge.service`) cleanly terminates both Uvicorn and the C++ Hardware bridge process group without leaving orphan processes.

### B. Systemd Service Template ([`navosedge.service`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/navosedge.service))
- Defines the single unit file with:
  - `After=network-online.target` & `Wants=network-online.target`
  - `Restart=on-failure` & `RestartSec=10`
  - `KillMode=control-group`
  - Dynamic user and repository root path substitution (`@REPO_ROOT@` and `@SERVICE_USER@`).

### C. Installation Script ([`scripts/install_navosedge_service.sh`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/scripts/install_navosedge_service.sh))
- Verifies that pre-built runtime prerequisites (`run_hardware.sh`, Python venv, and `navos_hardware_bridge`) exist before installing.
- Generates `/etc/systemd/system/navosedge.service` with actual system paths.
- Runs `systemctl daemon-reload`, `systemctl enable navosedge.service`, and `systemctl restart navosedge.service`.
- Polls `http://localhost:8420/health` to confirm startup success.

### D. Service Helper Script ([`scripts/navosedge-service.sh`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/scripts/navosedge-service.sh))
- Wraps common service actions (`start`, `stop`, `restart`, `status`, `logs`) for quick CLI interaction.

### E. Run Documentation ([`RUN.md`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/RUN.md))
- Updated with complete instructions for installation, service control, boot diagrams, and troubleshooting.

---

## 4. Step-by-Step Setup Guide

Follow these steps to set up the systemd boot service on your Arduino UNO Q board:

### Step 1: Clone the Repository & Navigate to Directory
```bash
git clone <repository-url>
cd NavosEdge
```

### Step 2: Build Application Prerequisites (Setup Phase)
Before enabling the boot service, compile the C++ hardware application and set up the Python virtual environment:

```bash
# Build C++ binaries & Python venv (skipping MCU flashing if already programmed)
./run_hardware.sh --skip-flash
```
*Press `Ctrl+C` once the application reaches `[NAVOSEDGE] Edge application running`.*

### Step 3: Install & Enable the Systemd Boot Service
Run the installation script with root privileges:

```bash
sudo ./scripts/install_navosedge_service.sh
```

### Step 4: Verify Service Status & Health Endpoint
Check that the service is active and the Intelligence Server responds:

```bash
# Check systemd service status
./scripts/navosedge-service.sh status

# Test HTTP Health API
curl -s http://localhost:8420/health
```

Expected response: `{"status":"ok", ...}`

### Step 5: View Live Application Logs
Stream live journal output:

```bash
./scripts/navosedge-service.sh logs
```

---

## 5. Service Management Commands

| Action | Helper Command | Direct Systemd Command |
| :--- | :--- | :--- |
| **Check Status** | `./scripts/navosedge-service.sh status` | `sudo systemctl status navosedge.service` |
| **Start Service** | `./scripts/navosedge-service.sh start` | `sudo systemctl start navosedge.service` |
| **Stop Service** | `./scripts/navosedge-service.sh stop` | `sudo systemctl stop navosedge.service` |
| **Restart Service** | `./scripts/navosedge-service.sh restart` | `sudo systemctl restart navosedge.service` |
| **Tail Logs** | `./scripts/navosedge-service.sh logs` | `journalctl -u navosedge.service -f -o cat` |

---

## 6. Crash Recovery & Shutdown Behavior

1. **Graceful Shutdown**:
   Executing `sudo systemctl stop navosedge.service` sends `SIGTERM` to the process group. `run_hardware.sh` intercepts `SIGTERM` in its `cleanup()` trap, shuts down Uvicorn and `navos_hardware_bridge`, and releases serial port handles cleanly.
2. **Automatic Crash Recovery**:
   If Uvicorn or the C++ bridge crashes, systemd detects process termination, waits **10 seconds** (`RestartSec=10`), and automatically restarts `run_hardware.sh --no-build`.

---

## 7. Troubleshooting

### Problem: Installer reports `[ERROR] Prerequisites check failed!`
- **Cause**: Python venv or C++ binary has not been built yet.
- **Fix**: Run `./run_hardware.sh --skip-flash` once to create `Intelligence/Server/venv` and `Hardware/build/navos_hardware_bridge`.

### Problem: `[ERROR] Intelligence Server failed to start`
- **Cause**: Port 8420 is occupied by a stale process.
- **Fix**: Free port 8420: `sudo fuser -k 8420/tcp`, then restart the service: `./scripts/navosedge-service.sh restart`.

### Problem: Serial port permission denied
- **Cause**: The service user lacks permissions to open `/dev/ttyACM0`.
- **Fix**: Add the user to the `dialout` group: `sudo usermod -a -G dialout $USER`, then reboot or restart systemd.
