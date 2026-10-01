# NavosEdge — Operations & Execution Guide

This document provides a quick reference on how to run, monitor, test, and interact with the NavosEdge edge intelligence platform. 

The system is optimized for the **Arduino UNO Q** and operates 100% offline using a custom NumPy inference backend.

---

## 1. Quick Start: Simulation Mode

If you don't have physical sensors connected, you can run the complete pipeline using the built-in simulator. The simulator feeds realistic environmental data directly into the edge server.

**Start the simulator:**
```bash
# General syntax: bash scripts/run_simulation.sh [scenario] [node_id] [interval_seconds]
bash scripts/run_simulation.sh
```

**Available Scenarios:**
You can test how the AI pipeline reacts to different environments by providing a scenario name:
- `clean_indoor` (Default)
- `traffic` (High PM, moderate gas)
- `dust_construction` (Extreme PM10)
- `combustion_smoke` (High MQ2, high PM)
- `high_humidity` (Normal pollution, >85% humidity)
- `pm_spike` / `gas_spike` (Sudden anomalies)
- `mixed_pollution` / `sensor_fault` / `stable`

*Example: Simulate a traffic pollution event:*
```bash
bash scripts/run_simulation.sh traffic
```

---

## 2. Real-Time Dashboard (TUI)

You can monitor the live intelligence pipeline locally using the curses-based Terminal User Interface (TUI). This does NOT require a browser or external internet connection.

Open a **second terminal** and run:
```bash
# Make sure you are in the project root
source Intelligence/Server/venv/bin/activate
python3 scripts/unoq_tui.py
```
*Press `q` to exit the dashboard.*

---

## 3. Running the Test Suites

To ensure the hardware and software are ready for deployment, use the following built-in test commands.

**1. Full System Test Suite** (Validates schemas, anomaly engine, AI outputs, and routing):
```bash
bash scripts/run_all_tests.sh
```

**2. Model Precision Validation** (Ensures NumPy math perfectly matches PyTorch):
```bash
source Intelligence/Server/venv/bin/activate
python3 tests/test_torch_vs_numpy.py
```

**3. Resource Profiling** (Tests memory leaks, latency, and footprint):
```bash
source Intelligence/Server/venv/bin/activate
python3 scripts/unoq_resource_test.py
```

**4. UNO Q Preflight Check** (Checks architecture, RAM, Debian OS, and dependencies):
```bash
bash scripts/unoq_preflight.sh
```

---

## 4. Custom API Commands (cURL)

You can manually interact with the FastAPI server running on `http://127.0.0.1:8420`.

### A. Check System Health
```bash
curl -s http://127.0.0.1:8420/health | jq
```

### B. Manually Submit Sensor Data
Simulate a hardware node sending data via HTTP POST:
```bash
curl -X POST http://127.0.0.1:8420/api/v1/nodes/custom-node-1/readings \
     -H "Content-Type: application/json" \
     -d '{
       "node_id": "custom-node-1",
       "timestamp": "2026-09-27T12:00:00Z",
       "environment": {"temperature_C": 28.5, "humidity_pct": 55.0},
       "particulate_matter": {"PM1_0": 15.0, "PM2_5": 45.0, "PM10": 80.0},
       "gas_sensors": {
         "MQ2": {"raw_adc": 300, "voltage_V": 1.5},
         "MQ9": {"raw_adc": 250, "voltage_V": 1.2},
         "MQ135": {"raw_adc": 350, "voltage_V": 1.8}
       }
     }' | jq
```

### C. Get Latest Intelligence Result
```bash
curl -s http://127.0.0.1:8420/api/v1/nodes/custom-node-1/latest | jq
```

### D. Listen to Hardware Events (SSE)
Keep a terminal open to see real-time streaming events (like heartbeats and config changes) sent back to the hardware:
```bash
curl -N -H "Accept: text/event-stream" http://127.0.0.1:8420/api/v1/nodes/custom-node-1/events
```

---

## 5. Model Management (Development Only)

If you retrain the TinyGasNet model on your laptop/workstation using `Training/mq_train.py`, you must export it for the UNO Q edge runtime:

```bash
# This requires PyTorch to be installed on your workstation
source Intelligence/Server/venv/bin/activate
python3 Training/export_gasnet.py
```
This extracts the heavy `.pt` file into a highly optimized NumPy `.npz` archive located in `Intelligence/Server/artifacts/`.
