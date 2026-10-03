# NavosEdge — Run Guide

## Quick Start

```bash
git clone <repository-url>
cd NavosEdge
./run_simulation.sh
```

That's it. The script handles environment setup, dependency installation, building, and launching automatically.

---

## Architecture

```
              UNO Q / Development Machine
┌───────────────────────────────────────────┐
│                                           │
│  Python Intelligence Server (:8420)       │
│         ↑               ↓                 │
│    HTTP POST         SSE stream           │
│         ↑               ↓                 │
│  C++ Hardware Bridge                      │
│         ↑               ↓                 │
│  Sensor Source      MPI3501 Display        │
│  (Mock / Physical)  (GUI / text sim)      │
│                                           │
└───────────────────────────────────────────┘
```

**Data flow:**
1. **Sensors** (mock or physical) generate readings
2. **C++ Hardware Bridge** POSTs sensor data to Intelligence Server via HTTP
3. **Intelligence Server** processes data → AQI, source classification, anomaly detection, forecast, advisory
4. **SSE** streams results back to C++ Hardware Bridge
5. **MPI3501 Display** renders AQI dashboard (3-screen rotation)

---

## Simulation Mode

For development and testing without physical sensors:

```bash
./run_simulation.sh
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--scenario, -s` | `normal` | Simulation scenario |
| `--interval, -i` | `60` | Sampling interval (seconds) |
| `--node-id, -n` | `uno-q-001` | Node identifier |
| `--skip-flash` | — | Skip MCU display flashing |
| `--skip-display-sim` | — | Skip desktop display simulation build |
| `--help, -h` | — | Show usage |

### Available Scenarios

| Scenario | Description |
|----------|-------------|
| `clean_indoor` | Low PM, low gas — normal indoor conditions |
| `traffic` | Elevated PM2.5/PM10, high MQ9 (CO) |
| `dust_construction` | Very high PM10, moderate gases |
| `combustion_smoke` | High PM + high MQ2/MQ9/MQ135 |
| `high_humidity` | Normal PM, humidity 85–98% |
| `pm_spike` | Extreme PM2.5/PM10 event |
| `gas_spike` | Extreme gas sensor readings |
| `mixed_pollution` | Combined PM + gas pollution |
| `stable` | Fixed values with minimal noise |
| `sensor_fault` | Randomly faults a sensor to 0V or 5V |

### Examples

```bash
# Traffic scenario, 10-second intervals
./run_simulation.sh --scenario traffic --interval 10

# Quick test with 3-second intervals
./run_simulation.sh --scenario combustion_smoke --interval 3

# Skip display flash (no arduino-cli needed)
./run_simulation.sh --skip-flash
```

### Startup Sequence

```
[1/7] Checking environment...        — verify python3, cmake, gcc, g++, curl, git
[2/7] Preparing Python environment...— create venv, install deps (first run only)
[3/7] Building C++ Hardware...        — cmake + make (only if sources changed)
[4/7] Display build/flash...          — build display sim + flash MCU (if arduino-cli available)
[5/7] Verifying model artifacts...    — check ML model files
[6/7] Starting Intelligence Server... — launch uvicorn, wait for /health
[7/7] Starting Hardware Simulator...  — launch C++ with mock sensors
```

---

## Physical Hardware Mode

For deployment when physical sensors and the MPI3501 display are connected to the Arduino UNO Q:

### Step 1: Connect Physical Sensors & Board

1. Connect the MQ gas sensors (MQ2, MQ9, MQ135), particulate matter sensor (SDS011 / Plantower), and DHT22 to the Arduino UNO Q board pins.
2. Connect the UNO Q via USB to your system or boot directly on the UNO Q Debian OS.
3. Ensure your Linux user has serial port permissions:
   ```bash
   sudo usermod -a -G dialout $USER
   ```
   *(Note: Log out and log back in for group changes to take effect).*

### Step 2: Run Hardware Deployment Script

```bash
./run_hardware.sh
```

If your sensor board is attached to a non-default serial port (e.g. `/dev/ttyACM1` or `/dev/ttyUSB0`), pass the `--port` flag:

```bash
./run_hardware.sh --port /dev/ttyACM1 --interval 30
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--interval, -i` | `60` | Sampling interval (seconds) |
| `--node-id, -n` | `uno-q-001` | Node identifier |
| `--port, -p` | `/dev/ttyACM0` | Serial port for physical sensors |
| `--skip-flash` | — | Skip MCU display flashing |
| `--help, -h` | — | Show usage |

### Startup Sequence

```
[1/8] Checking environment...         — system dependencies
[2/8] Checking physical hardware...   — verify serial port & hardware configuration
[3/8] Preparing Python environment... — venv + deps
[4/8] Building C++ Hardware...        — cmake + make
[5/8] Display build/flash...          — compile & flash MPI3501 firmware via arduino-cli
[6/8] Verifying model artifacts...    — ML model files
[7/8] Starting Intelligence Server... — uvicorn + health check
[8/8] Starting Physical Hardware...   — C++ with real serial sensors + 30s warm-up
```

> **Note:** MQ-series gas sensors require a 30-second warm-up period on power-up to stabilize heating elements. The script will display a 30s countdown before sending the `READY` handshake to the Intelligence Server.

---

## Single Systemd Boot Service (`navosedge.service`)

For production deployment on the Arduino UNO Q board where NavosEdge automatically starts upon board boot:

### 1. Installation

Build the application binaries first, then run the service installer:

```bash
# Step A: Deploy / build application
./run_hardware.sh --skip-flash

# Step B: Install and enable systemd boot service
sudo ./scripts/install_navosedge_service.sh
```

### 2. Service Architecture & Boot Flow

```
UNO Q Boot
    ↓
systemd
    ↓
navosedge.service
    ↓
run_hardware.sh --no-build  (Master Launcher Entrypoint)
    ↓
┌─────────────────────────────────────────────────────────────┐
│  Check Environment (Verify pre-built binaries & venv)       │
│         ↓                                                   │
│  Start Intelligence Server (:8420) → Wait /health & /ready  │
│         ↓                                                   │
│  Start C++ Hardware Bridge → 30s Sensor Warm-up             │
│         ↓                                                   │
│  Establish SSE Stream & Begin 60s Acquisition Cycle         │
│         ↓                                                   │
│  Update MPI3501 Display Dashboard                           │
└─────────────────────────────────────────────────────────────┘
```

### 3. Service Management Commands

You can control the service using standard `systemctl` / `journalctl` commands or the included helper script:

```bash
# Helper Script
./scripts/navosedge-service.sh status
./scripts/navosedge-service.sh start
./scripts/navosedge-service.sh stop
./scripts/navosedge-service.sh restart
./scripts/navosedge-service.sh logs

# Systemctl Directly
sudo systemctl status navosedge.service
sudo systemctl start navosedge.service
sudo systemctl stop navosedge.service
sudo systemctl restart navosedge.service

# Stream Live Logs
journalctl -u navosedge.service -f -o cat
```

---

## How to Verify Simulation vs. Real Hardware Data

You can verify whether the system is currently using **Simulated (Synthetic)** data or **Original (Physical Hardware)** data using any of the following methods:

### 1. Terminal Startup Banner & Process Logs

When running `./run_simulation.sh`:
- Banner shows: `Hardware : MOCK (simulation)`
- Log displays: `[HW] Mock sensor initialized (scenario: <name>)`

When running `./run_hardware.sh`:
- Banner shows: `Hardware : PHYSICAL SENSORS`
- Log displays: `[HW] Physical sensor initialized on /dev/ttyACM0 @ 115200 baud`

### 2. Configuration File Setting

Inspect `Hardware/config/hardware_config.json` (or `.env`):
- `"mock_mode": true` → **Simulated Data Mode**. The C++ bridge uses `MockSensorSource` to generate synthetic values according to the active scenario profile.
- `"mock_mode": false` → **Physical Hardware Mode**. The C++ bridge uses `SerialSensorSource` to stream live ADC and digital readings from `/dev/ttyACM0`.

### 3. Checking API Responses & Data Logs

Query the latest node state via HTTP API:

```bash
curl -s http://127.0.0.1:8420/api/v1/nodes/uno-q-001/latest | python3 -m json.tool
```

Or inspect raw stored JSON records in `data/readings/`:

- **Simulated Data Characteristics:**
  - Standard scenario profiles (e.g. `clean_indoor`, `traffic`, `dust_construction`, `combustion_smoke`).
  - Smooth baseline values with synthetic gaussian noise applied.
- **Physical Sensor Data Characteristics:**
  - Dynamic analog voltages reflecting real-world room atmosphere.
  - Temperature/humidity from DHT22 sensor and real ADC raw counts (`0-1023` for 10-bit ADC).
  - During the initial 30-second sensor warm-up phase, real sensors report zero/initializing values until heater stabilization completes.

---

## Individual Components

For debugging, you can run components separately.

### Intelligence Server

```bash
cd Intelligence/Server
source venv/bin/activate       # create with: python3 -m venv venv
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8420
```

Verify:
```bash
curl http://127.0.0.1:8420/health
```

### C++ Hardware Bridge

```bash
cd Hardware
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)

# Mock mode (simulation)
./navos_hardware_bridge --config ../config/hardware_config.json --scenario traffic --interval 5

# Physical mode
./navos_hardware_bridge --config ../config/hardware_config.json  # with mock_mode: false in config
```

### Display Simulation (Desktop)

```bash
cd Hardware/display
mkdir -p build && cd build
cmake ..
make
./navos_display_sim
```

### MCU Display Flash

```bash
./flash_display.sh
```

Requires `arduino-cli` with the `arduino:zephyr:unoq` board platform installed.

### Python Sensor Simulator

```bash
cd Intelligence/Server
source venv/bin/activate
cd ../..
python3 -c "
from simulation.sensor_simulator import SensorSimulator
import json
sim = SensorSimulator(scenario='traffic', seed=42)
print(json.dumps(sim.generate(), indent=2))
"
```

### Tests

```bash
# Full test suite
bash scripts/run_all_tests.sh

# Preflight check (verifies system readiness)
bash scripts/unoq_preflight.sh

# End-to-end test (requires running Intelligence Server)
bash run_e2e_test.sh
```

---

## Local Sensor Dataset Logging

NavosEdge automatically persists every valid sensor measurement to daily CSV files in the root `local_dataset/` directory:

```text
local_dataset/
    ↓
daily sensor CSV (YYYY-MM-DD.csv)
    ↓
future model retraining
```

### Flow & Retraining Integration

1. **Automatic Logging**: Every sensor reading is appended to `local_dataset/YYYY-MM-DD.csv` without blocking the real-time Intelligence pipeline.
2. **Retraining Usage**: Accumulated CSV files can be copied to `dataset/MQ_Dataset/` and used to retrain the ML model via `python3 Training/retrain.py`.
3. **Documentation**: See [`phase14LocalDataset.md`](phase14LocalDataset.md) for full details on schema, file format, error handling, and retraining steps.

---

## Configuration

### Environment Variables (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `NAVOS_HOST` | `0.0.0.0` | Intelligence Server bind address |
| `NAVOS_PORT` | `8420` | Intelligence Server port |
| `NAVOS_NODE_ID` | `uno-q-001` | Default node identifier |
| `NAVOS_SENSOR_INTERVAL` | `10` | Default sampling interval (seconds) |
| `NAVOS_SENSOR_MODE` | `mock` | Sensor mode (`mock` or `physical`) |
| `NAVOS_SCENARIO` | `normal` | Default simulation scenario |
| `NAVOS_MANAGER_HOST` | `0.0.0.0` | Parent Manager host |
| `NAVOS_MANAGER_PORT` | `8430` | Parent Manager port |

Copy `.env.example` to `.env` to customize:
```bash
cp .env.example .env
```

### Hardware Configuration (`Hardware/config/hardware_config.json`)

```json
{
    "server_url": "http://localhost:8420",
    "node_id": "uno-q-001",
    "sampling_interval_seconds": 60,
    "mock_mode": true,
    "scenario": "normal",
    "serial_port": "/dev/ttyACM0",
    "serial_baud": 115200
}
```

> CLI flags (`--scenario`, `--interval`, `--node-id`) override config file values.

### Simulation Constants (`simulation/constants.py`)

Scenario profiles, ADC parameters, and default values are defined in
[`simulation/constants.py`](simulation/constants.py).

---

## Troubleshooting

### Python environment missing

```
[MISS] python3 — sudo apt install python3
[MISS] python3-venv — sudo apt install python3-venv
```

**Fix:** Install the listed packages and re-run the script.

### Dependency installation failure

**Fix:** Check internet connectivity. Try manually:
```bash
cd Intelligence/Server
source venv/bin/activate
pip install -r ../../requirements/unoq.txt
```

### C++ build failure

```
[ERROR] cmake or make failed
```

**Fix:** Install build tools:
```bash
sudo apt install cmake build-essential libcurl4-openssl-dev
```

### Display flashing failure

**Fix:** Install `arduino-cli`:
```bash
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh
```
Install the UNO Q board platform:
```bash
arduino-cli core install arduino:zephyr
```

### Intelligence Server not ready

The server has 60 seconds to start. If it times out:
- Check port 8420 is not occupied: `fuser 8420/tcp`
- Run manually to see errors: `cd Intelligence/Server && venv/bin/python3 -m uvicorn app.main:app --port 8420`

### SSE connection failure

The C++ bridge retries SSE connections automatically. If it fails:
- Verify Intelligence Server is running: `curl http://127.0.0.1:8420/health`
- Check firewall rules are not blocking localhost

### Hardware unavailable

```
[ERROR] Physical hardware process exited during warm-up.
```

**Fix:** Physical sensor drivers may not be implemented yet. Use simulation mode:
```bash
./run_simulation.sh
```

### Port already in use

```
[WARN] Port 8420 in use (PID: 12345). Freeing...
```

The scripts automatically free occupied ports. If this fails:
```bash
kill $(fuser 8420/tcp 2>/dev/null)
```

### Permission errors

Serial port access on Linux:
```bash
sudo usermod -a -G dialout $USER
# Log out and back in for the change to take effect
```

---

## File Reference

| File | Purpose |
|------|---------|
| `run_simulation.sh` | One-command simulation launcher |
| `run_hardware.sh` | One-command physical hardware launcher |
| `run_navosedge.sh` | Legacy edge node launcher |
| `run_display_simulation.sh` | Legacy display simulation pipeline |
| `flash_display.sh` | MCU display firmware flasher |
| `scripts/unoq_preflight.sh` | System readiness checker |
| `scripts/run_all_tests.sh` | Full test suite |
| `scripts/run_simulation.sh` | Legacy simulation runner |
| `run_e2e_test.sh` | End-to-end test |
