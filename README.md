# NavosEdge — Edge AI Environmental Monitoring & Multi-Node Architecture

NavosEdge is an offline-first, multi-node edge artificial intelligence system designed for real-time environmental monitoring, air quality index (AQI) calculation, machine learning pollution source classification, short-term forecasting, dynamic advisory generation, and physical TFT display rendering.

It runs locally on the **Arduino UNO Q** microcomputer (combining a Linux MPU and an STM32U5 Zephyr MCU) paired with an **MPI3501 3.5" (480×320) TFT Display**, and communicates with a **Parent Edge Manager Web Dashboard** over a local Wi-Fi network.

---

## 🏛️ System Architecture

```text
+---------------------------------------------------------------------------------------------------------+
|                                        LAPTOP / PARENT SERVER                                           |
|                                                                                                         |
|  +---------------------------------------------------------------------------------------------------+  |
|  | Parent Edge Manager (FastAPI + React Dashboard)                                                  |  |
|  |  - Dynamic Wi-Fi Node Discovery (.env configuration)                                             |  |
|  |  - Non-blocking Hourly Poller (GET /api/v1/nodes/{id}/latest)                                    |  |
|  |  - Fault-Tolerant Reachability Handling (Mark Inactive on failure, Auto-Recover)                |  |
|  |  - Real-time React Web Dashboard (Telemetry, Source Breakdown, Forecast, Map View)              |  |
|  +---------------------------------------------------------------------------------------------------+  |
+---------------------------------------------------+-----------------------------------------------------+
                                                    |
                                                    | Local Wi-Fi Network (HTTP Polling)
                                                    v
+---------------------------------------------------------------------------------------------------------+
|                                           ARDUINO UNO Q                                                 |
|                                                                                                         |
|  [ MPU / Linux Side ]                                                                                   |
|  +-------------------------------------+      POST /hardware/ready      +--------------------------------+  |
|  | Hardware C++ Bridge                 | -----------------------------> | Intelligence Server (FastAPI)  |  |
|  | (navos_hardware_bridge)             |                                |  - EPA AQI Engine              |  |
|  |  - Sensor Provider / Sampler      |      POST /hardware/data       |  - Anomaly Engine (EWMA/Z-Score|  |
|  |  - 30s Mandatory Warm-Up Period     | -----------------------------> |  - GasNet ML Model (NumPy/PyT) |  |
|  |  - 60s Acquisition Cycle            |                                |  - PM Forecast Plugin          |  |
|  |  - HTTP / SSE Client (libcurl)      | <----------------------------- |  - Dynamic Advisory Engine     |  |
|  +-------------------------------------+   SSE ("request_data" /        +--------------------------------+  |
|                     |                       "intelligence_update")                                      |
|                     | Formats Display State                                                             |
|                     v                                                                                   |
|  +-------------------------------------+                             +--------------------------------+  |
|  | McuBridge (C++ RPC Client)          | --------------------------> | /var/run/arduino-router        |  |
|  +-------------------------------------+ (MessagePack-RPC)           | (.sock Unix Domain Socket)     |  |
|                                                                      +--------------------------------+  |
| ======================================================================================================= |
|  [ MCU Side (Zephyr / STM32U5) ]                                                     |                  |
|                                                                                      v                  |
|  +-------------------------------------+                             +--------------------------------+  |
|  | mcu_display.ino Sketch              | <-------------------------- | Arduino_RouterBridge           |  |
|  +-------------------------------------+ (RPC Handlers)              +--------------------------------+  |
|                     |                                                                                   |
|                     v Updates NavosEdgeState                                                            |
|  +-------------------------------------+                                                                |
|  | NavosEdgeGUI Renderer (C++)         | (3-Screen 10s Non-blocking Rotation)                             |
|  +-------------------------------------+                                                                |
|                     | Hardware SPI (MOSI=D11, SCK=D13, CS=D10, DC=D2)                                   |
|                     v                                                                                   |
|  +-------------------------------------+                                                                |
|  | MPI3501 3.5" TFT Display (ILI9486)   | (Physical 480x320 Resolution)                                   |
|  +-------------------------------------+                                                                |
+---------------------------------------------------------------------------------------------------------+
```

---

## 🧩 Core Sub-Systems & Implementation Details

### 1. Intelligence Server (`Intelligence/Server/`)
A lightweight FastAPI application running on the UNO Q Linux MPU:
- **EPA AQI Engine**: Calculates standard Air Quality Index values and categorizations (`Good`, `Moderate`, `Unhealthy for Sensitive Groups`, `Unhealthy`, `Very Unhealthy`, `Hazardous`) based on PM2.5 and PM10 concentrations.
- **Anomaly Engine**: Applies Exponentially Weighted Moving Average (EWMA) and dynamic Z-score filtering to flag sudden environmental spikes or sensor anomalies.
- **GasNet ML Model**: Neural network for air pollution source classification (`Clean Indoor`, `Traffic`, `Dust / Construction`, `Combustion / Smoke`, `High Humidity`). Features a dual-backend architecture:
  - **PyTorch Backend**: Used for model training and development.
  - **NumPy Edge Backend**: Pure NumPy matrix math engine (`.npz` weights) providing zero-dependency, ultra-fast inference on resource-constrained edge hardware without PyTorch overhead.
- **Forecast Plugin**: Generates short-term PM2.5 trend projections using Holt-Winters exponential smoothing.
- **Advisory Engine**: Synthesizes AQI metrics, detected anomalies, and predicted pollution sources into actionable public health recommendations.
- **SSE Stream (`GET /hardware/stream`)**: Pushes `request_data` trigger events to hardware and broadcasts `intelligence_update` events upon inference completion.

### 2. Hardware C++ Bridge (`Hardware/`)
High-performance C++ executable (`navos_hardware_bridge`) running on the UNO Q Linux MPU:
- **30-Second Sensor Warm-Up**: Enforces a mandatory 30-second sensor stabilization window upon startup before transmitting telemetry for inference.
- **Handshake Sequence**: Sends `POST /hardware/ready` signal to Intelligence Server once sensors are warm.
- **60-Second Acquisition Loop**: Listens for SSE `request_data` events, samples PM, MQ gas (MQ2, MQ3, MQ4, MQ6, MQ7, MQ8, MQ135), temperature, and humidity sensors every 60 seconds, and posts payload to `POST /hardware/data`.
- **MessagePack-RPC Client**: Listens for `intelligence_update` events, formats screen display state, and transmits RPC calls (`update_environment`, `update_advice`, `update_actions`) to the MCU over `/var/run/arduino-router.sock`.

### 3. MCU Physical Display Driver (`Hardware/mcu_display/`)
Firmware sketch running on the STM32U5 Zephyr MCU:
- **RPC Receiver**: Listens for incoming MessagePack-RPC commands from the MPU via `Arduino_RouterBridge`.
- **`NavosEdgeGUI` Renderer**: Formats and draws real-time data across 3 dedicated UI screens:
  - **Screen 1**: Real-time AQI, primary PM values, temperature/humidity, and anomaly status.
  - **Screen 2**: Pollution source classification breakdown and short-term PM forecast.
  - **Screen 3**: Actionable health advisories and safety recommendations.
- **Non-Blocking Rotation**: Rotates through display screens every 10 seconds using non-blocking timer loops (`millis()`) without interrupting hardware RPC reception.
- **`UNOQ_MPI3501` Driver**: Low-level hardware SPI driver driving the 3.5" (480x320 ILI9486) display.

### 4. Parent Edge Manager (`Manager/`)
Laptop/Server parent node aggregator and Web Dashboard:
- **FastAPI Parent Server**: Central telemetry hub collecting data from multiple UNO Q edge nodes over local Wi-Fi.
- **Dynamic `.env` Configuration**: Reads target node host/port (`UNO_Q_HOST`, `UNO_Q_PORT`) and polling intervals (`UNO_Q_POLL_INTERVAL_SECONDS`) dynamically without code changes.
- **Non-Blocking Background Poller**: Periodically polls the connected UNO Q node (default interval: 1 hour / 3600s) via `GET /api/v1/nodes/{id}/latest`.
- **Fault-Tolerant Status Tracking**: Gracefully marks nodes as `inactive` when unreachable without crashing or generating fake telemetry, and automatically restores node status when connectivity is re-established.
- **React Web Dashboard (`Manager/web/`)**: Interactive Tailwind CSS + Vite web dashboard displaying node reachability, AQI metrics, historical graphs, source distribution, and manual poll trigger buttons.

### 5. Model Training & Export Pipeline (`Training/`)
- Synthetic dataset generation scripts (`mq_generator.py`) simulating real-world sensor profiles.
- PyTorch training script (`mq_train.py`) producing `gasnet.pt`.
- Export script (`export_gasnet.py`) generating lightweight `.npz` weight matrices (`gasnet_weights.npz`) and scaling metadata (`preprocess.pkl`) for PyTorch-free NumPy edge inference.

---

## 🔄 Phase 13 Runtime Sequence

```text
[ Hardware ]                  [ Intelligence Server ]                [ MCU Display ]
     |                                   |                                  |
     |--- 1. Sensor Warm-Up (30s) ------>|                                  |
     |    (No telemetry sent)            |                                  |
     |                                   |                                  |
     |--- 2. POST /hardware/ready ------>|                                  |
     |                                   |                                  |
     |<-- 3. SSE "request_data" ---------|  (Every 60 Seconds)              |
     |                                   |                                  |
     |--- 4. POST /hardware/data ------->|                                  |
     |    (PM, MQ, Temp, Humidity)       |--- 5. Run ML Pipeline ---------->|
     |                                   |    (AQI, Anomaly, GasNet,       |
     |                                   |     Forecast, Advisory)          |
     |                                   |                                  |
     |<-- 6. SSE "intelligence_update" --|                                  |
     |                                   |                                  |
     |--- 7. MessagePack-RPC (/var/run/arduino-router.sock) -------------->|
     |                                                                      |--- 8. Update TFT
     |                                                                      |    (10s 3-Screen
     |                                                                      |     Rotation)
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python**: 3.10+
- **C++ Compiler**: GCC / G++ (supporting C++17), CMake 3.16+
- **Node.js**: 18+ & npm (for Parent Manager React frontend)
- **Arduino CLI / Zephyr Tools** (for flashing physical UNO Q MCU)

---

### 1. Launch UNO Q Edge Node
Start the local Python Intelligence Server and C++ Hardware Application on the UNO Q:

```bash
./run_navosedge.sh
```

To specify custom node credentials or simulation scenarios:

```bash
./run_navosedge.sh --node-id uno-q-001 --scenario traffic --interval 60
```

---

### 2. Launch Parent Manager Dashboard
Start the Laptop Parent Manager server and React dashboard:

```bash
./Manager/run_manager.sh
```

- **Manager REST API**: `http://localhost:8430/api/v1/overview`
- **React Web Dashboard**: `http://localhost:8430/`

---

### 3. Flash MCU Display Firmware (Physical UNO Q)
To compile and flash the physical MPI3501 display driver sketch onto the Arduino UNO Q MCU (`arduino:zephyr:unoq`):

```bash
./flash_display.sh
```

---

### 4. Run Interactive Simulation Suite
Test sensor scenarios (`clean_indoor`, `traffic`, `dust_construction`, `combustion_smoke`, `high_humidity`, `stable`) with real-time hardware execution and Intelligence streaming:

```bash
./run_display_simulation.sh --scenario combustion_smoke --interval 5
```

Check system status (Intelligence server, router socket, MCU RPC availability, C++ bridge):

```bash
./run_display_simulation.sh --status
```

---

### 5. Run Full Verification Test Suite
Run the complete automated test suite (including Pytest integration tests, sensor validation, NumPy vs PyTorch backend verification, and Manager E2E flow):

```bash
./scripts/run_all_tests.sh
```

---

## ⚙️ Environment Configuration (`.env`)

Create or update `.env` in the project root:

```ini
# UNO Q Edge Node Configuration
NAVOS_HOST=127.0.0.1
NAVOS_PORT=8420
NAVOS_NODE_ID=uno-q-001
NAVOS_SCENARIO=traffic
NAVOS_INTERVAL=60

# Parent Edge Manager Configuration
NAVOS_MANAGER_HOST=127.0.0.1
NAVOS_MANAGER_PORT=8430

# Parent Manager ↔ UNO Q Integration
UNO_Q_HOST=127.0.0.1
UNO_Q_PORT=8420
UNO_Q_POLL_INTERVAL_SECONDS=3600
```

---

## 📚 Documentation Directory Index

All technical documentation and phase development runbooks are consolidated in [docs/phases/](docs/phases/):

- 📘 [Comprehensive Sensor & Hardware Wiring Guide](WIRING_GUIDE.md) — Complete pinout, schematic, power budget, and troubleshooting for Arduino UNO Q.
- 📘 [Phase 13 Runtime Flow Specification](docs/phases/phase13RuntimeFlow.md) — 30s warm-up, `READY` handshake, 60s cycle, fault recovery, and shutdown flow.
- 📘 [Parent Manager Integration Guide](docs/phases/UNO_Q_MANAGER_INTEGRATION.md) — Wi-Fi network setup, `.env` configuration, and polling specs.
- 📘 [UNO Q Deployment Manual](docs/phases/UNO_Q_DEPLOYMENT.md) — Comprehensive guide for deploying on physical Arduino UNO Q hardware.
- 📘 [Phase 10 Display Integration](docs/phases/phase10DisplayIntegration.md) — Architectural breakdown of physical MPI3501 display & MessagePack-RPC bridge.
- 📘 [Phase 9 Parent Manager Architecture](docs/phases/phase9Manager.md) — Multi-node aggregator design and React frontend specs.
- 📘 [Complete Project Phase Runbook](docs/phases/PHASE_RUNBOOK.md) — Comprehensive development log for all phases (Phases 1 to 13).
