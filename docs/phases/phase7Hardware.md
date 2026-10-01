# NavosEdge Phase 7 Hardware Data & Control Bridge

This document describes the C++ Hardware Data Bridge and SSE Control Channel implemented in Phase 7 (7A Data Ingestion + 7B SSE Control Channel + 7C End-to-End Local Simulation). The hardware bridge is responsible for collecting sensor readings from hardware (or simulated) sensors, sending measurements via HTTP POST, maintaining a persistent Server-Sent Events (SSE) connection to receive real-time control events, and running local end-to-end simulations.

---

## 1. Architecture & What Was Implemented

### 1.1 Phase 7A — Hardware Data Ingestion (C++ → Python)
- Lightweight C++ application (`navos_hardware_bridge`) for Linux/UNO Q.
- Deterministic `MockSensorSource` generator maintaining physically valid sensor bounds (PM1.0 ≤ PM2.5 ≤ PM10, MQ ADC 0-1023, Voltage 0-5V).
- `HttpClient` wrapper built on `libcurl` with configurable HTTP timeout and bounded exponential backoff retries.
- `POST /hardware/data` endpoint on Python Intelligence Server validating `SensorPayload` schema and routing through the Intelligence pipeline.

### 1.2 Phase 7B — SSE Control Channel (Python → C++)
- `GET /hardware/events` SSE endpoint on Python Intelligence Server sending initial registration events (`connected`), periodic heartbeats (`heartbeat`), and server-generated node events (`config`).
- `SseClient` class in C++ running in a dedicated background listener thread using `libcurl` streaming write callbacks and immediate signal-based termination (`CURLOPT_XFERINFOFUNCTION`).
- Automatic reconnection with exponential backoff on network drop.
- Dynamic runtime configuration updating: When a `config` event (e.g., `{"sampling_interval": 3}`) is pushed via SSE, the C++ client dynamically adjusts its POST loop interval without restarting.
- `POST /hardware/config` admin endpoint for publishing control configuration events to specific nodes.

### 1.3 Phase 7C — End-to-End Local Simulation
- Multi-scenario simulation generator (`normal`, `high_pm`, `traffic`, `dust`) in C++ simulator.
- Formatted log stream (`[HW] ...`) matching required hardware output format.
- Automated single-command E2E test runner (`./run_e2e_test.sh`).
- Verified latest intelligence result retrieval via `GET /api/v1/nodes/{node_id}/latest`.

---

## 2. Hardware ↔ Python Data Flow

```text
       [ C++ Hardware Node ]                            [ Python Intelligence Server ]
                 │                                                   │
                 │ ─── 1. Health & Readiness (GET /health & /ready) ►│
                 │ ◄── HTTP 200 OK {"status": "ok", "ready": true} ──│
                 │                                                   │
                 │ ─── 2. Connect SSE (GET /hardware/events) ──────► │ (Persistent Connection)
                 │ ◄── SSE event: connected ──────────────────────── │
                 │ ◄── SSE event: heartbeat (every 15s) ──────────── │
                 │                                                   │
  (Periodic Loop)│ ─── 3. Ingest Data (POST /hardware/data) ───────► │
                 │ ◄── HTTP 201 Created (IntelligenceResult) ─────── │
                 │                                                   │
  (Control Event)│ ◄── 4. SSE event: config {"sampling_interval": 3} ─ │ (Triggered via POST /hardware/config)
                 │                                                   │
  (Dynamic Update) Updates sampling interval to 3s dynamically      │
```

---

## 3. Directory Structure

```text
Hardware/
├── CMakeLists.txt
├── config/
│   └── hardware_config.json      # Client configuration
├── include/
│   ├── bridge.hpp                # Main orchestrator & POST loop
│   ├── config.hpp                # Config loader & struct
│   ├── http_client.hpp           # libcurl HTTP GET/POST wrapper
│   ├── sensor.hpp                # Sensor interface & multi-scenario Mock generator
│   └── sse_client.hpp            # Libcurl SSE streaming client & parser
├── src/
│   └── main.cpp                  # Entry point, CLI args & signal handler
├── tests/
│   └── test_bridge.cpp           # C++ test suite (9 unit tests)
└── third_party/
    └── nlohmann/                 # Header-only JSON parser
run_e2e_test.sh                   # Single-command E2E simulation runner
```

---

## 4. Configuration

Configured via `config/hardware_config.json`:

```json
{
  "server_url": "http://localhost:8420",
  "node_id": "uno-q-001",
  "sampling_interval_seconds": 10,
  "retry_max_attempts": 5,
  "retry_base_delay_seconds": 2,
  "http_timeout_seconds": 10,
  "scenario": "normal",
  "mock_mode": true
}
```

---

## 5. Build Instructions

Requires `cmake` (≥ 3.10), `g++` (C++17), and `libcurl`.

```bash
cd Hardware/
mkdir -p build && cd build
cmake ..
make -j$(nproc)
```

---

## 6. API Endpoints & Payloads

### 6.1 Data Ingestion (`POST /hardware/data`)
- **Request Body**: `SensorPayload` (node_id, timestamp, environment, particulate_matter, gas_sensors).
- **Response**: `HTTP 201 Created` with `IntelligenceResult`.

### 6.2 SSE Control Channel (`GET /hardware/events`)
- **Query Parameter**: `node_id` (e.g., `?node_id=uno-q-001`).
- **Response Stream**: `text/event-stream`

### 6.3 Publish Node Config (`POST /hardware/config`)
- **Request Body**: `{"node_id": "uno-q-001", "sampling_interval": 3}`
- **Response**: `{"status": "published", "subscribers_notified": 1, ...}`

### 6.4 Retrieve Latest Result (`GET /api/v1/nodes/{node_id}/latest`)
- **Response**: Latest processed `IntelligenceResult` for specified node.

---

## 7. Local End-to-End Simulation

### 7.1 Starting the Python Intelligence Server
```bash
cd Intelligence/Server
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8420
```

### 7.2 Running the C++ Hardware Simulator
```bash
./Hardware/build/navos_hardware_bridge --config Hardware/config/hardware_config.json --node-id navos-node-01 --scenario normal --interval 2
```

### 7.3 How Connections & Transmissions Work
1. **Health Check**: Simulator queries `GET /health` and `GET /ready`. Once ready, prints `[HW] Server: connected`.
2. **SSE Connection**: Connects to `GET /hardware/events?node_id=navos-node-01`. Prints `[HW] SSE: connected` and `[HW] SSE: registration confirmed` upon receiving `connected` event.
3. **Data Ingestion**: Periodically POSTs payload to `/hardware/data`. Logs `[HW] Sending sensor reading #N` and `[HW] POST /hardware/data → 201`.
4. **Dynamic Configuration**: Server publishes config via `POST /hardware/config`. Simulator receives `event: config` and updates sampling interval dynamically.

### 7.4 Single-Command End-to-End Test Execution
```bash
./run_e2e_test.sh [scenario] [node_id]
```
Example:
```bash
./run_e2e_test.sh normal navos-node-01
./run_e2e_test.sh high_pm node-high-pm
```

### 7.5 Testing Different Simulation Scenarios
- **Normal**: `./run_e2e_test.sh normal navos-node-01`
- **High-PM**: `./run_e2e_test.sh high_pm node-high-pm`
- **Traffic**: `./run_e2e_test.sh traffic node-traffic`
- **Heavy Dust**: `./run_e2e_test.sh dust node-dust`

### 7.6 Simulating Server Failure / Reconnection
If the Python server is stopped while the C++ simulator is running:
1. HTTP POST requests fail and enter exponential backoff (`[HW] Reconnecting in Ns...`).
2. SSE client detects dropped connection and attempts background reconnection.
3. When the Python server is restarted, the simulator re-establishes `/ready` status, reconnects SSE (`[HW] SSE: registration confirmed`), and resumes data transmission without crashing.

### 7.7 Expected Terminal Output

**C++ Simulator:**
```text
[HW] Starting node: navos-node-01
[HW] Server: connected
[HW] SSE: connected
[HW] SSE: registration confirmed
[HW] Sending sensor reading #1
[HW] POST /hardware/data → 201
[HW] Sending sensor reading #2
[HW] POST /hardware/data → 201
[HW] SSE: config updated -> sampling_interval = 1s
[HW] Sending sensor reading #3
[HW] POST /hardware/data → 201
```

**Retrieving Latest Intelligence Result (`GET /api/v1/nodes/navos-node-01/latest`):**
```json
{
    "aqi": 66.44,
    "pm": {
        "PM1_0": 12.96,
        "PM2_5": 19.44,
        "PM10": 26.92
    },
    "temperature_C": 30.18,
    "humidity_pct": 67.4,
    "predictions": {
        "source": {
            "value": "COOKING_OR_FUEL_COMBUSTION",
            "confidence": 0.7836
        },
        "forecast": {
            "value": {
                "status": "insufficient_data",
                "PM1_0": [],
                "PM2_5": [],
                "PM10": []
            },
            "confidence": 0.0
        }
    },
    "advisory": {
        "severity": "MODERATE",
        "advice": "The air is a little polluted. Prefer open, well-ventilated spaces.",
        "actions": [
            "Prefer well-ventilated, lower-pollution areas.",
            "Use general pollution precautions."
        ],
        "weather_advice": "Conditions are very pleasant."
    }
}
```
