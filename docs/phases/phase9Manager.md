# NavosEdge — Phase 9: Parent Manager Server & Multi-Node Dashboard

This document provides complete architectural specifications, startup instructions, testing workflows, and API definitions for the **NavosEdge Parent Manager Server** and **ReactJS Web Dashboard**.

---

## 1. Architecture

The NavosEdge Parent Manager operates as a central coordinator and multi-node telemetry aggregator across distributed edge devices (such as Arduino UNO Q nodes).

```text
               ┌─────────────────────────────────┐
               │    Parent Manager Server        │
               │  FastAPI (Port 8430) + Storage  │
               └────────────────┬────────────────┘
                                │
                 ┌──────────────┼──────────────┐
                 │ (SSE Stream) │              │
                 ▼              ▼              ▼
          ┌─────────────┐ ┌───────────┐ ┌─────────────┐
          │ Node 01     │ │ Node 02   │ │ Node N      │
          │ (UNO Q /    │ │ (UNO Q /  │ │ (UNO Q /    │
          │ Sim)        │ │ Sim)      │ │ Sim)        │
          └──────┬──────┘ └─────┬─────┘ └──────┬──────┘
                 │              │              │
                 ▼              ▼              ▼
          ┌─────────────┐ ┌───────────┐ ┌─────────────┐
          │Intelligence │ │Intelligence│ │Intelligence │
          │Server (8420)│ │Server     │ │Server       │
          └──────┬──────┘ └─────┬─────┘ └──────┬──────┘
                 │              │              │
                 └──────────────┼──────────────┘
                                │ (HTTP Telemetry)
                                ▼
                   ┌────────────────────────┐
                   │   ReactJS Web          │
                   │   Dashboard (Port 8430)│
                   └────────────────────────┘
```

### Data Flow Pipeline:
1. **Hardware / UNO Q / Sensor Simulator**: Produces environmental particulate matter (`PM1.0`, `PM2.5`, `PM10`), gas sensor voltages (`MQ2`, `MQ9`, `MQ135`), and ambient temperature & humidity.
2. **Intelligence Server**: Runs offline NumPy inference (TinyGasNet), anomaly detection, source classification, forecast, and AQI standard breakpoint processing.
3. **Parent Manager Server**: Ingests the finalized `IntelligenceResult` schema from each node. It maintains node connection status, calculates regional system aggregations (Max AQI, Average PM, Average Temp & Humidity), persists state to lightweight file storage, and flags inactive nodes.
4. **ReactJS Web Dashboard**: Receives real-time Server-Sent Events (SSE) from Manager on `/stream` to update the multi-node overview, comparative air quality bars, and individual node cards without full page reloads.

---

## 2. Individual Startup Commands

If running components individually during development:

### 1. Intelligence Server
```bash
source Intelligence/Server/venv/bin/activate
cd Intelligence/Server
NAVOS_MANAGER_URL="http://127.0.0.1:8430" uvicorn app.main:app --host 127.0.0.1 --port 8420
```

### 2. Hardware Bridge (C++)
```bash
cd Hardware
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc)
./navos_hardware_bridge
```

### 3. Hardware / Sensor Simulator
To start a single simulated node (`navos-01` in Bhubaneswar):
```bash
source Intelligence/Server/venv/bin/activate
python3 -c "
import sys, time, json, urllib.request
sys.path.insert(0, 'Intelligence/Server')
from simulation.sensor_simulator import SensorSimulator

sim = SensorSimulator(node_id='navos-01', scenario='traffic')
url = 'http://127.0.0.1:8420/hardware/data'
while True:
    payload = json.dumps(sim.generate()).encode()
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req)
    print('[SIM] Sent node reading:', resp.getcode())
    time.sleep(3)
"
```

### 4. Parent Manager Server
```bash
source Intelligence/Server/venv/bin/activate
bash Manager/run_manager.sh
# Server starts at http://127.0.0.1:8430
```

### 5. React Web Dashboard (Standalone Dev Mode)
```bash
cd Manager/web
npm run dev
# Dashboard available at http://localhost:3000
```
*(Note: When Manager server starts via `run_manager.sh`, it automatically serves the production built React dashboard directly at `http://127.0.0.1:8430/`)*

---

## 3. Complete System Startup

To launch the complete multi-node system with a single command:

```bash
./run_navosedge.sh
```

Or explicitly specify the execution mode:

```bash
# Simulation mode (starts Intelligence Server, Manager Server, React Dashboard, and 2 simulated nodes)
./run_navosedge.sh --mode simulation

# Hardware mode (starts Intelligence Server, Manager Server, React Dashboard, and C++ Hardware Bridge)
./run_navosedge.sh --mode hardware
```

### What `run_navosedge.sh` does automatically:
1. Cleans up stale processes bound to ports `8420` and `8430`.
2. Starts the **Intelligence Server** and polls `http://127.0.0.1:8420/health` until ready.
3. Starts the **Parent Manager Server** and polls `http://127.0.0.1:8430/health` until ready.
4. Spawns two simulated edge nodes (`navos-01` in Bhubaneswar, `navos-02` in Cuttack).
5. Displays operational endpoints and listens for `Ctrl+C` to execute a clean multi-process shutdown.

---

## 4. Testing Procedures

### A. Testing Single Node & Node Registration
```bash
curl -X POST http://127.0.0.1:8430/api/v1/nodes/register \
     -H "Content-Type: application/json" \
     -d '{"node_id": "navos-test-01", "location": "Lab Bench 1"}' | jq
```
*Expected Output*: JSON record showing `"status": "active"` and location `"Lab Bench 1"`.

### B. Testing Multi-Node Telemetry Ingestion
Send intelligence payload for Node 1:
```bash
curl -X POST http://127.0.0.1:8430/api/v1/nodes/navos-01/telemetry \
     -H "Content-Type: application/json" \
     -d '{
       "node_id": "navos-01",
       "location": "Bhubaneswar",
       "aqi": 142.0,
       "pm": {"PM1_0": 41.2, "PM2_5": 82.4, "PM10": 141.3},
       "temperature_C": 31.2,
       "humidity_pct": 68.5,
       "predictions": {"source": {"value": "Traffic", "confidence": 0.78}},
       "advisory": {"severity": "MODERATE", "advice": "Limit prolonged outdoor exertion"}
     }' | jq
```

Send intelligence payload for Node 2:
```bash
curl -X POST http://127.0.0.1:8430/api/v1/nodes/navos-02/telemetry \
     -H "Content-Type: application/json" \
     -d '{
       "node_id": "navos-02",
       "location": "Cuttack",
       "aqi": 45.0,
       "pm": {"PM1_0": 5.0, "PM2_5": 12.0, "PM10": 25.0},
       "temperature_C": 26.5,
       "humidity_pct": 52.0,
       "predictions": {"source": {"value": "Clean Indoor", "confidence": 0.95}},
       "advisory": {"severity": "NORMAL", "advice": "Air quality is good."}
     }' | jq
```

### C. Verify System Overview Aggregation
```bash
curl -s http://127.0.0.1:8430/api/v1/overview | jq
```
*Verification*:
- `active_nodes`: 2
- `overall.aqi`: 142.0 (Max AQI among active nodes as per EPA/CPCB regulatory standard)
- `overall.PM2_5`: 47.2 µg/m³ (Average across active nodes)

### D. Verify React Web Dashboard Updates
Open browser at `http://127.0.0.1:8430/`.
- Verify both `navos-01` (Bhubaneswar) and `navos-02` (Cuttack) appear on cards.
- Verify comparative air quality bar chart orders Bhubaneswar (#1, AQI 142) above Cuttack (#2, AQI 45).
- Verify SSE stream status indicator shows "SSE Live Stream".

### E. Verify Inactive Node Detection
Stop telemetry for `navos-02`. Wait 15 seconds (the timeout threshold).
Query `/api/v1/overview`:
- Node `navos-02` status changes to `"inactive"`.
- `active_nodes` becomes `1`, `inactive_nodes` becomes `1`.
- Dashboard status badge for `navos-02` turns red (`INACTIVE`).

### F. Verify Manager Restart & State Recovery
1. Kill Manager Server process.
2. Restart Manager Server (`bash Manager/run_manager.sh`).
3. Query `http://127.0.0.1:8430/api/v1/overview`.
*Verification*: Both `navos-01` and `navos-02` are recovered from `Manager/data/manager_state.json`.

---

## 5. Parent Manager API Documentation

### 1. GET `/health`
Check Manager server operational health.
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-09-28T19:55:00Z",
  "active_nodes": 2,
  "inactive_nodes": 0,
  "total_nodes": 2
}
```

### 2. GET `/overview` or `/api/v1/overview`
Get regional system summary and node details.
```json
{
  "active_nodes": 2,
  "inactive_nodes": 0,
  "total_nodes": 2,
  "overall": {
    "aqi": 142.0,
    "PM1_0": 23.1,
    "PM2_5": 47.2,
    "PM10": 83.2,
    "temperature_C": 28.85,
    "humidity_pct": 60.25
  },
  "nodes": [
    {
      "node_id": "navos-01",
      "location": "Bhubaneswar",
      "status": "active",
      "last_seen": "2026-09-28T19:55:00Z",
      "last_updated_seconds_ago": 1.2,
      "aqi": 142.0,
      "pm": {
        "PM1_0": 41.2,
        "PM2_5": 82.4,
        "PM10": 141.3
      },
      "temperature_C": 31.2,
      "humidity_pct": 68.5,
      "source_prediction": "Traffic",
      "source_confidence": 0.78,
      "advisory": {
        "severity": "MODERATE",
        "advice": "Limit prolonged outdoor exertion"
      }
    }
  ]
}
```

### 3. GET `/nodes` or `/api/v1/nodes`
List all registered nodes and their current state.

### 4. GET `/nodes/{node_id}` or `/api/v1/nodes/{node_id}`
Retrieve stored state for a specific node ID.

### 5. POST `/api/v1/nodes/{node_id}/telemetry`
Ingest final intelligence result from an edge node.

### 6. GET `/stream` or `/api/v1/stream`
Server-Sent Events (SSE) connection broadcasting real-time JSON overview events.
