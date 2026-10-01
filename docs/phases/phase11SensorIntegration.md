# Phase 11 — Sensor Integration: C++ → Python Pipeline

**Date:** October 2026  
**Status:** Complete  
**Scope:** Physical sensor acquisition, C++ validation, serial protocol, and end-to-end data flow from Arduino UNO Q hardware through the Intelligence Server pipeline.

---

## 1. Overview

Phase 11 closes the final gap in the NavosEdge sensor pipeline. Prior to this phase, the C++ Hardware Bridge only supported **mock sensors** — any attempt to set `mock_mode=false` caused a hard exit. This phase implements the complete physical sensor path:

```
Arduino UNO Q (Firmware)
    │
    │  USB Serial @ 115200 baud
    │  JSON frames: {"mq2":350,"mq9":280,...}
    ▼
Linux C++ Bridge (SerialSensorSource)
    │
    │  SensorValidator checks all bounds
    │
    │  HTTP POST JSON to /hardware/data
    ▼
Intelligence Server (Python FastAPI :8420)
    │
    ├─ SensorPayload schema validation (Pydantic)
    ├─ GasNet inference (NumPy MLP)
    ├─ Anomaly detection engine
    ├─ Source classifier (scikit-learn)
    ├─ PM forecast plugin
    ├─ AQI calculator (EPA standard)
    ├─ Advisory engine (rule-based)
    │
    │  SSE intelligence_update event
    ▼
C++ Bridge receives advisory via SSE
    │
    │  MessagePack-RPC over Unix socket
    ▼
MCU Display (Arduino Router → OLED/TFT)
```

---

## 2. New Files Created

| File | Purpose |
|:---|:---|
| [`Hardware/firmware/navos_sensors.ino`](../../Hardware/firmware/navos_sensors.ino) | Arduino firmware — reads MQ2, MQ9, MQ135, DHT22, MPM10-CS and transmits JSON over serial |
| [`Hardware/include/serial_sensor.hpp`](../../Hardware/include/serial_sensor.hpp) | `SerialSensorSource` — Linux-side serial port reader, JSON parser, error recovery |
| [`Hardware/include/sensor_validator.hpp`](../../Hardware/include/sensor_validator.hpp) | `SensorValidator` — validates all sensor readings against physical bounds |

## 3. Modified Files

| File | Changes |
|:---|:---|
| [`Hardware/src/main.cpp`](../../Hardware/src/main.cpp) | Instantiates `SerialSensorSource` when `mock_mode=false`; added includes |
| [`Hardware/include/config.hpp`](../../Hardware/include/config.hpp) | Added `serial_port`, `serial_baud`, `serial_timeout_ms` fields + env overrides |
| [`Hardware/include/bridge.hpp`](../../Hardware/include/bridge.hpp) | Validates every reading via `SensorValidator` before POST; skips invalid data |
| [`Hardware/config/hardware_config.json`](../../Hardware/config/hardware_config.json) | Added serial port configuration fields |

## 4. Unchanged (Reused As-Is)

The Python backend required **zero changes**. The existing pipeline handles everything:

| Component | Why No Changes Needed |
|:---|:---|
| `POST /hardware/data` endpoint | Already accepts exactly the JSON the C++ bridge produces |
| `SensorPayload` Pydantic schema | Already validates PM ordering, ADC bounds, timestamps |
| `ProcessingService` pipeline | Already runs inference, anomaly, source, forecast, AQI, advisory |
| `EventService` SSE | Already publishes `intelligence_update` events back to C++ |
| `IntelligenceResult` response | Already formats advisory for display |
| Advisory Engine | Rule-based — not ML; no modifications needed |

---

## 5. Sensor Specifications

### 5.1 MQ2 — Combustible Gas & Smoke

| Parameter | Value |
|:---|:---|
| Type | Analog (10-bit ADC) |
| Arduino Pin | A0 |
| ADC Range | 0–1023 |
| Voltage Range | 0.0–5.0V |
| Detects | LPG, propane, methane, hydrogen, alcohol, smoke |
| Warm-up | 30 seconds minimum |

### 5.2 MQ9 — Carbon Monoxide & Flammable Gas

| Parameter | Value |
|:---|:---|
| Type | Analog (10-bit ADC) |
| Arduino Pin | A1 |
| ADC Range | 0–1023 |
| Voltage Range | 0.0–5.0V |
| Detects | CO, methane, LPG |
| Warm-up | 30 seconds minimum |

### 5.3 MQ135 — Air Quality

| Parameter | Value |
|:---|:---|
| Type | Analog (10-bit ADC) |
| Arduino Pin | A2 |
| ADC Range | 0–1023 |
| Voltage Range | 0.0–5.0V |
| Detects | NH3, NOx, benzene, CO2, alcohol, smoke |
| Warm-up | 30 seconds minimum |

### 5.4 DHT22 — Temperature & Humidity

| Parameter | Value |
|:---|:---|
| Type | Digital (bit-bang protocol) |
| Arduino Pin | D2 (10kΩ pull-up to VCC) |
| Temperature Range | -40°C to +85°C (±0.5°C accuracy) |
| Humidity Range | 0–100% RH (±2–5% accuracy) |
| Min Interval | 2 seconds between reads |

### 5.5 MPM10-CS — Particulate Matter

| Parameter | Value |
|:---|:---|
| Type | UART (9600 baud) |
| Arduino Pins | D4 (RX), D5 (TX) via SoftwareSerial |
| Protocol | PMS binary (32-byte frames, checksum verified) |
| Outputs | PM1.0, PM2.5, PM10 (µg/m³) |
| Constraint | PM1.0 ≤ PM2.5 ≤ PM10 (tolerance ±0.5) |

---

## 6. Serial Protocol

### 6.1 Arduino → Linux Frame Format

One JSON line per `\n`, transmitted every 3 seconds (configurable):

```json
{"mq2":350,"mq9":280,"mq135":420,"t":28.50,"h":65.00,"pm1":12.0,"pm25":18.0,"pm10":25.0,"dht_ok":true,"pms_ok":true,"ok":true}
```

| Field | Type | Description |
|:---|:---|:---|
| `mq2` | int | MQ2 raw ADC (0–1023) |
| `mq9` | int | MQ9 raw ADC (0–1023) |
| `mq135` | int | MQ135 raw ADC (0–1023) |
| `t` | float | Temperature (°C) |
| `h` | float | Humidity (%) |
| `pm1` | float | PM1.0 (µg/m³) |
| `pm25` | float | PM2.5 (µg/m³) |
| `pm10` | float | PM10 (µg/m³) |
| `dht_ok` | bool | DHT22 read success |
| `pms_ok` | bool | PMS frame read success |
| `ok` | bool | All sensors healthy AND warmed up |

### 6.2 Boot Message

On power-up, the Arduino sends:
```json
{"status":"booting","firmware":"navos_sensors","version":"1.0.0"}
```
The `SerialSensorSource` recognizes `"status"` messages and skips them.

### 6.3 Serial Configuration

| Setting | Default | Env Override |
|:---|:---|:---|
| Port | `/dev/ttyACM0` | `NAVOS_SERIAL_PORT` |
| Baud | 115200 | `NAVOS_SERIAL_BAUD` |
| Timeout | 5000ms | Config JSON `serial_timeout_ms` |

---

## 7. Validation Pipeline

### 7.1 C++ Layer (`SensorValidator`)

Every reading passes through validation **before** HTTP transmission:

```
SensorSource::read()
    │
    ▼
SensorValidator::validate(data)
    │
    ├─ NaN / Inf checks (all doubles)
    ├─ ADC range: 0 ≤ raw_adc ≤ 1023
    ├─ Voltage range: 0.0 ≤ V ≤ 5.0
    ├─ ADC↔Voltage consistency (±0.05V)
    ├─ Temperature: -40°C ≤ T ≤ 85°C
    ├─ Humidity: 0% ≤ H ≤ 100%
    ├─ PM non-negative
    ├─ PM ordering: PM1.0 ≤ PM2.5 ≤ PM10 (±0.5)
    ├─ node_id non-empty
    └─ timestamp non-empty
    │
    ├─ VALID → build_payload() → POST
    └─ INVALID → log errors, skip transmission
```

### 7.2 Python Layer (`SensorPayload`)

Server-side Pydantic schema provides a second validation barrier:

- `node_id`: regex `^[a-zA-Z0-9_-]+$`, max 64 chars
- `timestamp`: ISO8601, not >24h in the future
- `gas_sensors.*.raw_adc`: 0–1023
- `gas_sensors.*.voltage_V`: 0.0–5.0
- `environment.temperature_C`: -40 to 85
- `environment.humidity_pct`: 0–100
- `particulate_matter`: PM1.0 ≤ PM2.5 ≤ PM10 (±0.5)

---

## 8. Error Handling

### 8.1 Hardware Errors (Arduino Side)

| Error | Behavior |
|:---|:---|
| DHT22 read failure | `dht_ok: false`, retains last known T/H values |
| PMS frame timeout | `pms_ok: false`, retains last known PM values |
| PMS checksum error | `pms_ok: false`, frame discarded |
| MQ not warmed up | `ok: false` for first 30s after boot |

### 8.2 Serial Errors (C++ Bridge Side)

| Error | Behavior |
|:---|:---|
| Port not available | Logs error, returns zero-value `SensorData` |
| Read timeout | Increments error counter; after 5 consecutive → reconnect |
| JSON parse failure | Logged, reading skipped |
| Validation failure | Attempts clamp recovery; if still invalid → skip |
| Port disconnected | Detects via `read()=0`, closes and re-opens |

### 8.3 Network Errors (HTTP/SSE)

| Error | Behavior |
|:---|:---|
| POST connection failure | Exponential backoff (2s → 4s → 8s → ... → 60s max) |
| POST 422 (validation) | Logged, no retry (data is bad) |
| Max retries exceeded | Re-runs `wait_for_server()` health check |
| SSE disconnect | Auto-reconnect with exponential backoff |

---

## 9. JSON Payload — C++ to Python

The C++ `HardwareBridge::build_payload()` produces this exact structure:

```json
{
  "node_id": "uno-q-001",
  "timestamp": "2026-10-01T17:41:30Z",
  "environment": {
    "temperature_C": 28.50,
    "humidity_pct": 65.00
  },
  "particulate_matter": {
    "PM1_0": 12.00,
    "PM2_5": 18.00,
    "PM10": 25.00
  },
  "gas_sensors": {
    "MQ2":   { "raw_adc": 350, "voltage_V": 1.711 },
    "MQ9":   { "raw_adc": 280, "voltage_V": 1.369 },
    "MQ135": { "raw_adc": 420, "voltage_V": 2.053 }
  }
}
```

This maps **1:1** to the Python `SensorPayload` Pydantic model.

---

## 10. How to Start Listening

### 10.1 Mock Mode (Development/Testing)

```bash
# Terminal 1: Start the Intelligence Server
cd Intelligence/Server
python -m app.main
# Server starts on http://localhost:8420

# Terminal 2: Build and run the C++ Hardware Bridge in mock mode
cd Hardware
mkdir -p build && cd build
cmake .. && make
./navos_hardware_bridge --scenario normal --interval 5
# Sends mock sensor data every 5 seconds to the Intelligence Server
```

### 10.2 Physical Mode (Arduino UNO Q Deployment)

**Step 1: Flash the Arduino firmware**
```bash
# Using Arduino CLI (recommended for UNO Q)
arduino-cli compile --fqbn arduino:avr:uno Hardware/firmware/navos_sensors.ino
arduino-cli upload --port /dev/ttyACM0 --fqbn arduino:avr:uno Hardware/firmware/navos_sensors.ino
```

**Step 2: Verify serial output**
```bash
# Quick check that the Arduino is sending data
stty -F /dev/ttyACM0 115200
cat /dev/ttyACM0
# Should see JSON lines every ~3 seconds
```

**Step 3: Start the Intelligence Server**
```bash
cd Intelligence/Server
python -m app.main
```

**Step 4: Start the C++ Bridge in physical mode**
```bash
cd Hardware/build
./navos_hardware_bridge --config ../config/hardware_config.json
# Ensure hardware_config.json has: "mock_mode": false
```

Or use environment variables:
```bash
NAVOS_SENSOR_MODE=physical \
NAVOS_SERIAL_PORT=/dev/ttyACM0 \
NAVOS_SERIAL_BAUD=115200 \
./navos_hardware_bridge
```

### 10.3 Environment Variable Reference

| Variable | Default | Description |
|:---|:---|:---|
| `NAVOS_HOST` | `localhost` | Intelligence Server host |
| `NAVOS_PORT` | `8420` | Intelligence Server port |
| `NAVOS_NODE_ID` | `uno-q-001` | Hardware node identifier |
| `NAVOS_SENSOR_MODE` | `mock` | `mock` or `physical` |
| `NAVOS_SENSOR_INTERVAL` | `10` | Seconds between readings |
| `NAVOS_SCENARIO` | `normal` | Mock scenario: `normal`, `high_pm`, `traffic`, `dust` |
| `NAVOS_SERIAL_PORT` | `/dev/ttyACM0` | Serial port for physical sensors |
| `NAVOS_SERIAL_BAUD` | `115200` | Serial baud rate |
| `NAVOS_MANAGER_URL` | `http://127.0.0.1:8430` | Manager Server URL |

### 10.4 Full Stack Launch (All Components)

```bash
# Terminal 1: Intelligence Server
cd Intelligence/Server
pip install -r requirements.txt
python -m app.main

# Terminal 2: Manager Server (optional — multi-node dashboard)
cd Manager
pip install -r requirements.txt
python -m app.main

# Terminal 3: Hardware Bridge
cd Hardware/build
cmake .. && make
./navos_hardware_bridge --interval 10

# Terminal 4: (Optional) Monitor SSE events
curl -N http://localhost:8420/hardware/events?node_id=uno-q-001
```

### 10.5 Verifying the Pipeline

```bash
# Check server health
curl http://localhost:8420/health

# Check server readiness
curl http://localhost:8420/ready

# Check latest AQI
curl http://localhost:8420/aqi/latest

# Check node status
curl http://localhost:8420/nodes

# Monitor live intelligence updates via SSE
curl -N -H "Accept: text/event-stream" \
     http://localhost:8420/hardware/events?node_id=uno-q-001
```

---

## 11. Wiring Diagram

```
Arduino UNO Q
┌──────────────────────────────┐
│                              │
│  A0 ◄── MQ2 (AOUT)          │
│  A1 ◄── MQ9 (AOUT)          │
│  A2 ◄── MQ135 (AOUT)        │
│                              │
│  D2 ◄── DHT22 (DATA)        │
│         ├── 10kΩ ── VCC      │
│                              │
│  D4 ◄── MPM10-CS (TX)       │
│  D5 ──► MPM10-CS (RX)       │
│                              │
│  USB ──► Linux Host          │
│         (/dev/ttyACM0)       │
└──────────────────────────────┘

Power:
  MQ2, MQ9, MQ135 → 5V + GND (heater + analog out)
  DHT22 → 3.3V or 5V + GND
  MPM10-CS → 5V + GND
```

---

## 12. Files Consolidated to `docs/phases/`

All phase documentation, research, and runbooks have been consolidated from their scattered locations into `docs/phases/`:

| File | Original Location |
|:---|:---|
| `RESEARCH.md` | Root |
| `RUN.md` | Root |
| `UNO_Q_DEPLOYMENT.md` | Root |
| `assumedata.md` | Root |
| `phase7Hardware.md` | Root |
| `phase9Architecture.md` | Root |
| `phase10DisplayIntegration.md` | Root |
| `phase_display_simulation.md` | Root |
| `DATA_FLOW.md` | Intelligence/Server/Phases/ |
| `PROJECT_GUIDE.md` | Intelligence/Server/Phases/ |
| `phase4ForecastModel.md` | Intelligence/Server/Phases/ |
| `phase5simulator.md` | Intelligence/Server/Phases/ |
| `phase6endToEnd.md` | Intelligence/Server/Phases/ |
| `PHASE_RUNBOOK.md` | Intelligence/Phases/ |
| `FINAL_PROMPT.md` | Intelligence/ |
| `Intelligence_RUN.md` | Intelligence/ |
| `phase9Manager.md` | Manager/ |
| `FINAL_UNOQ_READINESS_REPORT.md` | docs/ |
| `NAVOSEDGE_RUNTIME_FLOW.md` | docs/ |
| `UNOQ_DEPENDENCY_AUDIT.md` | docs/ |
| `Simulator.md` | Intelligence/Server/Simulator/ |

`README.md` remains at the project root — it was not moved.
