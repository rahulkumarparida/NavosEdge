# NavosEdge — Phase 13: Intelligence ↔ Hardware End-to-End Runtime Flow

This document details the validated architecture, execution sequence, timing parameters, display pipeline, fault recovery, and testing procedures for the **Intelligence Server ↔ C++ Hardware Bridge** runtime connection on the Arduino UNO Q.

---

## 1. Runtime Sequence Architecture

```text
┌─────────────────────────┐                 ┌─────────────────────────┐                 ┌─────────────────────────┐
│ C++ Hardware Bridge     │                 │ Intelligence Server     │                 │ Arduino UNO Q Display   │
│ (Sensors & SSE Client)  │                 │ (FastAPI & Models)      │                 │ (MPI3501 & McuBridge)   │
└───────────┬─────────────┘                 └───────────┬─────────────┘                 └───────────┬─────────────┘
            │                                           │                                           │
            │  1. Check /health & /ready                │                                           │
            ├──────────────────────────────────────────►│                                           │
            │  200 OK (Server Ready)                    │                                           │
            │◄──────────────────────────────────────────┤                                           │
            │                                           │                                           │
            │  2. Connect SSE /hardware/events          │                                           │
            ├──────────────────────────────────────────►│                                           │
            │  3. Mandatory 30-Sec Sensor Warm-up       │                                           │
            │     (No data sent for inference)          │                                           │
            │                                           │                                           │
            │  4. POST /hardware/ready (Status: READY)  │                                           │
            ├──────────────────────────────────────────►│                                           │
            │  200 ACK (Handshake Accepted)             │                                           │
            │◄──────────────────────────────────────────┤                                           │
            │                                           │                                           │
  ┌─────────┴───────────────────────────────────────────┴─────────────────────────────────────────┴─────────┐
  │  60-SECOND RECURRING DATA ACQUISITION & DISPLAY UPDATE CYCLE                                           │
  └─────────┬───────────────────────────────────────────┬─────────────────────────────────────────┬─────────┘
            │                                           │                                           │
            │  5. SSE Request Event ("request_data")    │                                           │
            │◄──────────────────────────────────────────┤ (Triggered by Intelligence every 60s)    │
            │                                           │                                           │
            │  6. Read Sensors (PM, MQ, DHT22)          │                                           │
            │  7. POST /hardware/data                   │                                           │
            ├──────────────────────────────────────────►│                                           │
            │                                           │ 8. Run Intelligence Pipeline              │
            │                                           │    • AQI Standard Breakpoints             │
            │                                           │    • TinyGasNet Model Inference           │
            │                                           │    • Anomaly Engine & Source Classifier   │
            │                                           │    • Forecast Plugin & Advisory Engine    │
            │                                           │                                           │
            │  9. SSE Event ("intelligence_update")     │                                           │
            │◄──────────────────────────────────────────┤                                           │
            │                                           │                                           │
            │ 10. Update NavosEdgeState struct          │                                           │
            │ 11. Send state via Router RPC             │                                           │
            ├──────────────────────────────────────────────────────────────────────────────────────►│
            │                                           │                                           │ Render GUI
            │  12. Repeat cycle every 60 seconds...     │                                           │ (MPI3501 3-screen)
            │                                           │                                           │
```

---

## 2. Sequence Specifications

### 1. Hardware Startup & Discovery
- **Server Health Check**: `HardwareBridge` polls `http://localhost:8420/health` and `/ready` with interruptible exponential backoff (1s, 2s, 4s, 8s, 16s, max 60s) until Intelligence Server is initialized.
- **SSE Control Channel**: `HardwareBridge` starts a persistent `SseClient` listener thread connected to `GET /hardware/events?node_id=uno-q-001`.

### 2. Mandatory 30-Second Sensor Warm-up
- **Warm-Up Period**: Connected sensors (MQ2, MQ9, MQ135 gas sensors, PM1.0/PM2.5/PM10 laser particle counter, DHT22 ambient sensors) undergo a mandatory 30-second thermal & electrical stabilization warm-up period (`DEFAULT_SENSOR_WARMUP_SECONDS = 30`).
- **Data Deferral**: Sensor readings are read locally but **never transmitted for model inference** during the 30-second warm-up window.

### 3. READY Handshake
- **Handshake Signal**: Upon completing the 30-second warm-up, `HardwareBridge` POSTs a `READY` payload to `POST /hardware/ready`:
  ```json
  {
    "node_id": "uno-q-001",
    "status": "READY",
    "warmup_duration_s": 30.0
  }
  ```
- **Intelligence ACK**: Intelligence Server registers node readiness in `NodeRegistry` and responds with `{"status": "ACK", "ready": true}`. Intelligence immediately publishes an initial `request_data` SSE event to trigger the first acquisition cycle.

### 4. 60-Second Data Acquisition & Inference Cycle
- **Cycle Control**: Intelligence controls data acquisition timing. Every 60 seconds (`DEFAULT_SAMPLING_INTERVAL_SECONDS = 60`), Intelligence publishes a `request_data` SSE control event.
- **Data Transmission**: `HardwareBridge` receives `request_data`, validates sensor readings via `SensorValidator`, constructs `SensorPayload`, and POSTs to `POST /hardware/data`.
- **Intelligence Processing**: Intelligence runs the complete multi-stage pipeline:
  1. **AQI Calculation**: Standardbreakpoint mapping (PM1.0, PM2.5, PM10).
  2. **TinyGasNet Inference**: Gas classification & safety level.
  3. **Anomaly Engine**: Temporal residual analysis.
  4. **Source Classifier**: Environmental pollution source identification.
  5. **Forecast Plugin**: Trend projection.
  6. **Advisory Engine**: Public health guidance and action recommendations.

### 5. C++ Display GUI Update Pipeline
- **SSE Intelligence Event**: Intelligence publishes `intelligence_update` event containing the `IntelligenceResult` over `/hardware/events`.
- **Non-Blocking State Update**: `HardwareBridge` receives the event and updates the shared C++ `NavosEdgeState` structure without blocking:
  - AQI, PM levels, Temperature, Humidity
  - Advisory severity, primary advice string, weather advice, recommended action list
- **Display Driver Update**: State is forwarded to the `McuBridge` (`/var/run/arduino-router.sock`), updating the MPI3501 3-screen display rotation.

---

## 3. Failure Recovery & Graceful Shutdown

- **Intelligence Server Offline**:
  - If Intelligence becomes unreachable, `HardwareBridge` catches HTTP errors and enters interruptible exponential backoff without crashing or spamming requests.
  - When Intelligence recovers, `HardwareBridge` detects health recovery, re-initiates the `READY` handshake, and resumes the 60-second cycle.
- **Hardware Disconnect**:
  - If Hardware disconnects from SSE, `SseClient` automatically reconnects in a background thread.
  - Intelligence handles missing hardware subscribers cleanly without throwing exceptions.
- **Graceful Shutdown**:
  - Catching `SIGINT` / `SIGTERM` signals in `HardwareBridge::signal_handler` sets the atomic `running_` flag to `false`.
  - `SseClient` thread is joined and stopped cleanly.
  - `McuBridge` socket is closed cleanly.
  - Pending resources are flushed and processes terminate with exit code `0`.

---

## 4. How to Run and Test

### 1. Run Complete Test Suite
```bash
# Run Phase 13 End-to-End Runtime Flow Test
./Intelligence/Server/venv/bin/pytest tests/test_phase13_runtime_flow.py -s

# Run All Project Tests
bash scripts/run_all_tests.sh
```

### 2. Standalone MCU Display RPC Test
```bash
./Hardware/build/navos_hardware_bridge --test-mcu-rpc
```

### 3. Launch UNO Q Production Flow
```bash
# Starts Python Intelligence Server + C++ Hardware Application
./run_navosedge.sh
```
