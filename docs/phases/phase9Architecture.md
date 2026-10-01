# NavosEdge — Final Edge-Node + Parent Manager Architecture

## 1. Executive Architecture Overview

NavosEdge implements an autonomous **Edge Node + Parent Manager Architecture**.

* **Arduino UNO Q Edge Node**: A fully autonomous edge computing unit running both C++ hardware interfacing / MPI3501 display GUI and the Python Intelligence Server (AQI, Source Classifier, Forecast, Advisory Engine).
* **Laptop Parent Manager**: A central network manager and multi-node dashboard running separately on the laptop over the local Wi-Fi network.

```text
                    SAME Wi-Fi NETWORK
                         │
          ┌──────────────┴──────────────┐
          │                             │
     ARDUINO UNO Q                   LAPTOP
       EDGE NODE                    PARENT
          │                             │
    ┌─────┴─────┐                 ┌────┴─────┐
    │           │                 │          │
   C++        Python            Manager   Dashboard
 Hardware   Intelligence
    │           │
    │      AQI / Classifier
    │      Forecast / Advisory
    │           │
    │           │
    └─────┬─────┘
          │
       MPI3501
        Display
```

---

## 2. Component Responsibilities

### Arduino UNO Q Edge Node

The UNO Q operates completely independently. It contains:

1. **`Hardware/` C++ Application**:
   * Sensor provider abstraction (currently using simulated sensor acquisition; physical drivers plug in seamlessly).
   * Sensor payload transmission via `POST /hardware/data` to local Python Intelligence.
   * Persistent SSE connection listener for control and real-time intelligence state updates (`/hardware/events`).
   * Shared `NavosEdgeState` state management.
   * Non-blocking 3-screen MPI3501 display GUI renderer (Environment → Advice → Actions).

2. **`Intelligence/` Python Intelligence Server**:
   * Runs local ML models and analytical engines:
     * AQI calculation engine
     * GasNet / Source Classification model
     * Particulate Matter Forecast engine
     * Anomaly detection & Advisory Engine
   * Returns instant responses and publishes real-time SSE events (`intelligence_update`).
   * Asynchronously forwards the final intelligence result to Parent Manager over network.

### Laptop Parent Manager

The Parent Manager runs inside `Manager/` on the laptop:

* Central multi-node tracking (active/inactive status, last-seen timestamps, locations).
* Aggregates intelligence telemetry from multiple UNO Q edge nodes.
* Serves the React Web Dashboard SPA.
* **Does NOT run intelligence models or process raw sensor data.**

---

## 3. Communication Protocols & Data Flow

### A. Local Edge Node Pipeline (UNO Q)

```text
Sensor Data Provider (Mock/Physical)
        ↓
HTTP POST /hardware/data
        ↓
Python Intelligence Server (Port 8420)
  ├── AQI Calculation
  ├── Source Classifier
  ├── Anomaly Detection
  ├── PM Forecast
  └── Advisory Engine
        ↓
SSE Event ("intelligence_update") on /hardware/events
        ↓
C++ SSE Client
        ↓
Shared NavosEdgeState
        ↓
MPI3501 GUI Renderer (Non-blocking 10s Screen Rotation)
```

### B. UNO Q → Parent Manager Telemetry (Wi-Fi)

```text
Python Intelligence Server (UNO Q)
        │
        │ HTTP POST /api/v1/nodes/{node_id}/telemetry
        ▼
Parent Manager Server (Laptop: Port 8430)
        │
        │ Server-Sent Events (SSE broadcast)
        ▼
Web Dashboard (React SPA)
```

---

## 4. Display & Non-Blocking Timing

The 3.5" MPI3501 display GUI cycles through 3 screens:

1. **Screen 1: Environment** (AQI, PM1.0, PM2.5, PM10, Temperature, Humidity)
2. **Screen 2: Advice** (Severity level, primary advisory, weather advisory)
3. **Screen 3: Actions** (Targeted health and environmental action list)

Rotation occurs on a non-blocking 10-second timer (`millis()` / monotonic clock). Real-time intelligence updates arriving via SSE immediately refresh the shared `NavosEdgeState` without interrupting screen rotation.

---

## 5. Fault Tolerance & Network Disconnection Behavior

* **Laptop / Wi-Fi Disconnection**: UNO Q continues all local operations, AQI calculation, ML classification, forecast, advisory generation, and screen rendering uninterrupted.
* **Python Intelligence Unavailable**: C++ Hardware application retains the last valid `NavosEdgeState`, continues rendering last known data without crashing, and automatically retries connection.
* **Manager Server Unavailable**: UNO Q Intelligence Server catches network failures silently, continues local processing and SSE updates, and retries Manager telemetry forwarding on each reading.

---

## 6. Sensor Abstraction & Future Physical Driver Integration

The sensor acquisition layer is abstracted behind the C++ `SensorSource` interface (`include/sensor.hpp`).

* **Current Implementation**: `MockSensorSource` / simulator generating realistic gas ADC values, PM levels, and environmental readings.
* **Future Hardware Integration**: Physical sensor drivers (MQ2, MQ9, MQ135, DHT22, MPM10) will implement `SensorSource::read()` without modifying the C++ bridge, SSE client, display GUI, or Python intelligence pipeline.

---

## 7. Execution Commands

### 1. UNO Q Edge Node (Single Command Startup)

Run on the UNO Q:

```bash
./run_navosedge.sh
```

Options:
```bash
./run_navosedge.sh --node-id navos-01 --scenario traffic --interval 3
```

### 2. Laptop Parent Manager (Single Command Startup)

Run on the laptop:

```bash
./Manager/run_manager.sh
```

### 3. Individual Component Launch Commands

* **Python Intelligence Server (UNO Q)**:
  ```bash
  cd Intelligence/Server
  ./venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8420
  ```

* **C++ Hardware Application (UNO Q)**:
  ```bash
  cd Hardware/build
  ./navos_hardware_bridge --node-id navos-01 --scenario traffic --interval 3
  ```

* **Parent Manager Server (Laptop)**:
  ```bash
  cd Manager
  PYTHONPATH=. ../Intelligence/Server/venv/bin/python3 app/main.py
  ```

* **React Web Dashboard Build (Laptop)**:
  ```bash
  cd Manager/web
  npm run build
  ```
