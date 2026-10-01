# NavosEdge — End-to-End Synthetic Hardware → Intelligence → MPI3501 Display Test

## Overview

This document describes the synthetic end-to-end simulation and physical display integration test pipeline for NavosEdge on the **Arduino UNO Q** paired with the **MPI3501 3.5" (480×320) TFT display**.

The pipeline validates that synthetic hardware sensor telemetry streams from C++ to the local Python Intelligence Server, passes through all machine learning and advisory services, returns to C++ over Server-Sent Events (SSE), and updates the active MPI3501 GUI display state over **Arduino Router MessagePack-RPC** without restarting or reflashing the display application.

---

## 1. Complete Architecture & Data Flow

```text
[ MockSensorSource (C++) ]
        │ (Synthetic PM1.0, PM2.5, PM10, MQ2, MQ9, MQ135, Temp, Humidity)
        ▼
[ HTTP POST /hardware/data ]
        │
        ▼
[ Python Intelligence Server (Port 8420) ]
        ├── GasNet ML Model / Inference Adapter
        ├── Modular Pipeline / Anomaly Engine
        ├── Source Classifier (DecisionTree)
        ├── Forecast Plugin (Autoregressive AR(p))
        ├── AQI Calculator Service
        └── Advisory Engine (Rules & Recommendations)
        │
        ▼
[ SSE Event Service (GET /hardware/events) ]
        │ Event: "intelligence_update"
        ▼
[ HardwareBridge SSE Client (C++) ]
        │ Updates in-memory NavosEdgeState
        ▼
[ McuBridge MessagePack-RPC Client (C++) ]
        │ Sends RPC Requests (update_environment, update_advice, update_actions) over /var/run/arduino-router.sock
        ▼
[ Arduino_RouterBridge (MCU Zephyr/STM32U5) ]
        │ Dispatches calls to update_environment(), update_advice(), update_actions()
        ▼
[ NavosEdgeGUI Renderer (C++) ]
        │ Redraws current screen non-blockingly (10s millis() rotation)
        ▼
[ MPI3501 Physical Display (480×320) ]
```

---

## 2. Component Details

### A. Synthetic Sensor Data Generator (`MockSensorSource`)
- Generates synthetic readings for:
  - `PM1.0`, `PM2.5`, `PM10` (µg/m³)
  - `MQ2`, `MQ9`, `MQ135` (ADC & Voltage)
  - `Temperature` (°C), `Humidity` (%)
- Supports multiple scenarios: `normal`, `traffic`, `dust`, `high_pm`.

### B. C++ Hardware Bridge (`navos_hardware_bridge`)
- Posts readings to `http://localhost:8420/hardware/data` at the configured update interval (default: **60 seconds**).
- Subscribes to the SSE control stream (`GET /hardware/events?node_id=uno-q-001`).
- Listens for `intelligence_update` events and immediately forwards AQI, particulate matter, temperature, humidity, advisory level, text advice, weather advice, and action items over MessagePack-RPC (`/var/run/arduino-router.sock`).

### C. MPI3501 Display GUI (`NavosEdgeGUI`)
- Uses the official `UNOQ_MPI3501` library API (`begin()`, `setRotation(1)`, `fillScreen()`, `fillRect()`, `drawRect()`, `drawString()`, `drawFastHLine()`, `drawFastVLine()`).
- Rotates through 3 screens every **10 seconds** using non-blocking `millis()` timing:
  1. **Screen 0 — Environment Dashboard**: AQI, PM1.0, PM2.5, PM10, Temperature, Humidity, PM Progress Bars.
  2. **Screen 1 — Advisory**: Severity badge, wrapped advice text, weather advice.
  3. **Screen 2 — Measurable Actions**: Action items list with badges.
- Reflects newly arrived SSE intelligence results on the active screen instantly without clearing or restarting GUI rotation loops.

---

## 3. Setup Requirements

### Hardware Requirements
- **Arduino UNO Q**
- **MPI3501 3.5" 480×320 TFT Display** connected via SPI (`CS=D10, DC=D2, RST=D3`).

### Software Requirements
- C++17 Compiler & CMake 3.10+
- `libcurl` developer headers (`libcurl4-openssl-dev`)
- Python 3.10+ with `requirements.txt` installed in `Intelligence/Server/venv`.
- Active `arduino-router.service` system daemon.

---

## 4. How to Run the Test

Run the complete pipeline using the single unified launcher:

```bash
./run_display_simulation.sh
```

### Scenario Options
```bash
# Traffic scenario (elevated MQ gas & PM values)
./run_display_simulation.sh --scenario traffic

# Dust scenario (high PM10 and PM2.5)
./run_display_simulation.sh --scenario dust

# High PM scenario (severe PM values across all channels)
./run_display_simulation.sh --scenario high_pm

# Normal / clean indoor scenario
./run_display_simulation.sh --scenario normal
```

### Fast Test Mode (Development / Verification)
To run faster test cycles than the 60-second default (e.g. 5 seconds per cycle):

```bash
./run_display_simulation.sh --scenario traffic --interval 5
```

---

## 5. Expected Pipeline Execution Logs

When running, the system produces visible logs tracking every step of the end-to-end flow:

```text
============================================================
 NavosEdge — Synthetic Hardware → Intelligence → MCU Display
============================================================
  Node ID:            uno-q-001
  Scenario:           traffic
  Interval:           60s (default 60s)
  Arduino Router RPC: /var/run/arduino-router.sock
============================================================
[NAVOS] Intelligence Server READY
[HW] Mock sensor initialized
[HW] Starting node: uno-q-001
[MCU] Router connected
[HW] Server: connected
[HW] SSE connected
[HW] Sending sensor reading #1
[HW] SSE intelligence_update received
[DISPLAY] State updated
[HW] Shared NavosEdgeState updated via SSE (AQI: 63.41 | PM2.5: 18 | Temp: 28.5C)
[MCU] Environment RPC sent
[MCU] Advice RPC sent
[MCU] Actions RPC sent
[MCU] AQI=63.41 PM2.5=18 TEMP=28.5
```
