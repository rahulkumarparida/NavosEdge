# NavosEdge — Arduino UNO Q & Parent Manager Integration Guide

This document details the lightweight Wi-Fi network integration between the **Arduino UNO Q Edge Device** (running Intelligence Server + Hardware stack) and the **Parent Manager Server** (running on the laptop).

---

## 1. Architectural Overview

```text
┌─────────────────────────────────────────────────────────┐
│                     LAPTOP                              │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Parent Manager Server (FastAPI Port 8430)         │  │
│  │   • Non-blocking Hourly Background Poller         │  │
│  │   • Telemetry Ingest & Regional Aggregator        │  │
│  │   • ReactJS Web Dashboard (Served on /)           │  │
│  └────────────────────────▲──────────────────────────┘  │
└───────────────────────────│─────────────────────────────┘
                            │ HTTP Polling over Wi-Fi
                            │ GET /api/v1/nodes
                            │ GET /api/v1/nodes/{id}/latest
┌───────────────────────────│─────────────────────────────┐
│ ARDUINO UNO Q EDGE NODE   │                             │
│  ┌────────────────────────┴──────────────────────────┐  │
│  │ Intelligence Server (FastAPI Port 8420)           │  │
│  │   • TinyGasNet Model Inference (Gas Sensors)      │  │
│  │   • Anomaly Engine & Source Classifier            │  │
│  │   • AQI Breakpoint Service & Forecast Plugin      │  │
│  └────────────────────────▲──────────────────────────┘  │
│                           │                             │
│  ┌────────────────────────┴──────────────────────────┐  │
│  │ C++ Hardware Bridge / Sensor Drivers              │  │
│  │   • MQ2, MQ9, MQ135 Gas Sensors                   │  │
│  │   • PM1.0, PM2.5, PM10 Particulate Matter         │  │
│  │   • DHT22 Temperature & Humidity                  │  │
│  │   • MPI3501 3.5" Display GUI                      │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Configuration via `.env`

The Manager communicates with the UNO Q over the local Wi-Fi network using the IP address and port configured in `.env`.

To configure the target UNO Q node, add or modify the following variables in `.env`:

```env
# ------------------------------------------------------------------
# Parent Manager & UNO Q Polling Configuration
# ------------------------------------------------------------------
NAVOS_MANAGER_HOST=0.0.0.0
NAVOS_MANAGER_PORT=8430

# Option A: Specify UNO Q Local IP + Port
NAVOS_UNO_Q_IP=192.168.1.50
NAVOS_UNO_Q_PORT=8420

# Option B: Direct URL Override (takes precedence if provided)
# NAVOS_UNO_Q_URL=http://192.168.1.50:8420

# Polling Interval (in seconds, default: 3600 = 1 hour)
NAVOS_POLL_INTERVAL_S=3600

# Enable/Disable automatic background polling (default: true)
NAVOS_POLL_ENABLED=true
```

> **Note**: For local development or single-machine testing, set `NAVOS_UNO_Q_IP=127.0.0.1`.

---

## 3. Endpoints Used

The integration reuses existing Intelligence Server endpoints and provides runtime configuration management:

1. **Node Discovery**:
   - `GET http://<UNO_Q_IP>:8420/api/v1/nodes`
   - Returns list of active edge node IDs registered on the UNO Q.

2. **Latest Telemetry & Model Output Retrieval**:
   - `GET http://<UNO_Q_IP>:8420/api/v1/nodes/{node_id}/latest`
   - Returns the latest `IntelligenceResult` containing AQI, PM breakdown, temperature, humidity, gas source predictions, and health advisory.

3. **Manual Sync Trigger (Manager API)**:
   - `POST http://<MANAGER_IP>:8430/api/v1/nodes/poll`
   - Forces an immediate poll of the configured UNO Q device on demand.

4. **Dynamic IP Configuration (Manager Dashboard API)**:
   - `GET http://<MANAGER_IP>:8430/api/v1/config/ip`
     - Returns current target IP, port, base URL, auto-detected network IP, and reachable status.
   - `POST http://<MANAGER_IP>:8430/api/v1/config/ip`
     - Changes target IP & port at runtime, updates `.env`, and triggers an immediate poll.
   - `POST http://<MANAGER_IP>:8430/api/v1/nodes/{node_id}/ip`
     - Allows updating node IP directly from individual node cards.

---

## 4. Automatic Network IP Detection & Dashboard Configuration

### A. Automatic UNO Q Startup IP Detection
When UNO Q runs `./run_hardware.sh`, `./run_navosedge.sh`, or `./run_simulation.sh` (or boots via `navosedge.service`):
- It automatically detects the active Wi-Fi / Ethernet interface IP address (with retry support on boot).
- It writes the detected IP to `NAVOS_UNO_Q_IP`, `NAVOS_UNO_Q_URL`, and `UNO_Q_HOST_DEFAULT` in `.env`.
- It displays the detected IP and loads it into the environment without manual editing.
- Optional overrides: `--ip <custom_ip>` or `--no-ip-detect` to disable auto-detection.

### B. Live IP Configuration via Manager Web Dashboard
- **Global IP Configuration Card**: Positioned above the Monitored Nodes section, providing target endpoint inspection, reachability status badge ("Reachable" / "Offline"), detected local network IP helper, and full endpoint update form.
- **Per-Node Inline IP Editing**: Each monitored node card in the multi-node grid displays its current IP/port with a globe icon and an inline **Change IP** button. Clicking this button toggles an inline form directly on the card, enabling instant IP reconfiguration without scrolling away from the node.
- Changing the IP dynamically reconfigures the background poller, updates `.env` on disk, updates persisted state, and broadcasts live updates over SSE to all connected dashboard tabs.

---

## 5. Polling & Connection Failure Behavior

- **Non-Blocking Background Poller**: Polling runs in an asynchronous background loop inside the FastAPI `lifespan` manager and does not block the Manager or React Web Dashboard.
- **Dynamic Node Discovery**: Nodes are displayed on the Web Dashboard only when the configured UNO Q IP is reachable and responds with valid node telemetry.
- **Graceful Failure Handling**: If the UNO Q device becomes unreachable (e.g. Wi-Fi disconnection or power loss), Manager logs a warning message without crashing and updates the node status to `"inactive"` until connectivity is restored.

---

## 5. Running and Testing

### Run All Integration & E2E Tests
```bash
./Intelligence/Server/venv/bin/pytest tests/test_uno_q_manager_integration.py
./Intelligence/Server/venv/bin/python tests/test_manager_e2e.py
bash scripts/run_all_tests.sh
```

### Launch Integrated System
```bash
# 1. On Arduino UNO Q: Start Intelligence Server & C++ Hardware Bridge
./run_navosedge.sh

# 2. On Laptop: Start Parent Manager Server & Web Dashboard
bash Manager/run_manager.sh
```
Open `http://localhost:8430/` in your browser to view real-time aggregated telemetry and node statuses.
