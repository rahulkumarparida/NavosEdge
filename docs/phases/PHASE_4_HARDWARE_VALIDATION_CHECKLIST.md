# NavosEdge Validation Release 1 — Phase 4: Physical Hardware Validation Checklist

> [!IMPORTANT]
> **Safety Mandatory Rule:** Never short power rails, never apply unsafe over-voltages, never expose sensors to toxic, explosive, or asphyxiating gases in unventilated spaces, and never subject components to physical abuse. Dangerous failure modes (such as VCC rail shorting or gas sensor saturation) must be evaluated strictly via software fault injection or bench simulators.

---

## 1. Scope & Prerequisites

This checklist defines the rigorous, reproducible verification procedure to be executed when physical access to the Arduino UNO Q and the NavosEdge sensor package becomes available.

### 1.1 Target Hardware Configuration
- **Compute Platform:** Arduino UNO Q (Qualcomm Dragonwing QRB2210 ARM64, 2 GB RAM, 16 GB eMMC, Debian Linux).
- **MCU Co-Processor:** STM32 / RP2040 core running Zephyr RTOS with `Arduino_RouterBridge` monitor proxy.
- **Physical Sensor Array:**
  1. **DHT22 / AM2302:** Digital Pin D8 (10 kΩ pull-up to 3.3V/5V) — Ambient Temperature (-40°C to 85°C) & Relative Humidity (0% to 100%).
  2. **MQ-2 Gas Sensor:** Analog Pin A0 — Combustible gas, LPG, propane, smoke (0.10V to 4.85V).
  3. **MQ-9 Gas Sensor:** Analog Pin A1 — Carbon monoxide (CO) & flammable gas (0.10V to 4.85V).
  4. **MQ-135 Gas Sensor:** Analog Pin A2 — Air quality, ammonia ($NH_3$), nitrogen oxides ($NO_x$), benzene, $CO_2$ (0.10V to 4.85V).
  5. **MPM10-CS / PMS5003:** Hardware Serial1 (Pin D0 = RX, Pin D1 = TX at 9600 baud) — Laser scattering PM1.0, PM2.5, PM10 ($0$ to $1000 \mu g/m^3$).
- **Display Interface:** MPI3501 3.5" TFT display driven by the MCU via internal router RPC socket `/var/run/arduino-router.sock`.
- **Laptop Parent Manager:** Central React Dashboard and multi-node coordinator running on local network.

### 1.2 Pre-Flight Software Check
Before connecting hardware, run the system preflight tool on the UNO Q Linux environment:
```bash
bash scripts/unoq_preflight.sh
```
Verify that all checks report `[PASS]` (Architecture ARM64, Python >= 3.10, python3-venv, RAM >= 1.5 GB, Disk >= 500 MB, and model weights `gasnet_weights.npz`, `model_metadata.json`, `preprocess.pkl`, `source_classifier_model.pkl`).

---

## 2. Test Procedures

```
┌─────────────────────────────────┐      ┌─────────────────────────────────┐
│ Section A: Boot & Connectivity  │ ───> │ Section B: Sensor Plausibility  │
│ Router, Server, Ports, Timestmp │      │ 30s Warmup, PM Order, MQ Volts  │
└─────────────────────────────────┘      └─────────────────────────────────┘
                 │                                        │
                 ▼                                        ▼
┌─────────────────────────────────┐      ┌─────────────────────────────────┐
│ Section C: End-to-End System    │ ───> │ Section D: Faults & Recovery    │
│ Dashboard, AQI Est, Forecasts   │      │ Disconnect, Stale, Reconnect    │
└─────────────────────────────────┘      └─────────────────────────────────┘
```

---

### Section A: Boot and Connectivity

#### Test A.1: Firmware Startup & Router Monitor Proxy
- **Prerequisites:** Arduino UNO Q powered via certified USB-C power supply ($\ge 5\text{V}, 3\text{A}$).
- **Steps:**
  1. Compile and flash the sensor firmware:
     ```bash
     bash flash_display.sh
     ```
  2. Check status of the Arduino router service:
     ```bash
     systemctl status arduino-router.service
     ```
  3. Verify the serial monitor proxy endpoint is listening on TCP `127.0.0.1:7500`:
     ```bash
     curl -s telnet://127.0.0.1:7500 || nc -z 127.0.0.1 7500
     ```
- **Expected Outcome:** `arduino-router.service` is active (running); port 7500 accepts connections; valid JSON lines stream every 3 seconds:
  `{"mq2":...,"mq9":...,"mq135":...,"t":...,"h":...,"pm1":...,"pm25":...,"pm10":...,"ok":true}`
- **Evidence to Collect:** Terminal output of `systemctl status` and first 5 raw JSON frames from port 7500.
- **Pass/Fail Criteria:** PASS if formatted JSON frames arrive continuously without parse errors.

#### Test A.2: Intelligence Server Startup & Health Endpoints
- **Prerequisites:** Python virtual environment activated (`Intelligence/Server/venv`).
- **Steps:**
  1. Start the Intelligence Server in the background:
     ```bash
     cd Intelligence/Server
     PYTHONPATH="." python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8420
     ```
  2. Query server health and ready endpoints:
     ```bash
     curl -s http://127.0.0.1:8420/health
     curl -s http://127.0.0.1:8420/ready
     ```
- **Expected Outcome:**
  - `/health` returns HTTP 200: `{"status":"ok","timestamp":"...","version":"0.1.0"}`.
  - `/ready` returns HTTP 200: `{"status":"ready", ...}`.
  - Startup logs display: `Startup complete — model loaded: True, source classifier loaded: True, forecast plugin: True`.
- **Evidence to Collect:** HTTP response payloads and server startup log.
- **Pass/Fail Criteria:** PASS if `/health` and `/ready` return HTTP 200 and all ML models report loaded.

#### Test A.3: Parent Manager Connection & Dashboard Binding
- **Prerequisites:** Laptop and UNO Q connected to the same local Wi-Fi / Ethernet subnet.
- **Steps:**
  1. On laptop, start the Manager:
     ```bash
     PYTHONPATH="Manager:." python3 Manager/app/main.py
     ```
  2. Open browser to `http://<LAPTOP_IP>:8430/`.
  3. Verify UNO Q discovery via `GET http://<LAPTOP_IP>:8430/api/v1/overview`.
- **Expected Outcome:** Dashboard renders cleanly; node `uno-q-001` appears in the node list with status `ONLINE`.
- **Evidence to Collect:** Screenshot of dashboard node table and response of `/api/v1/overview`.
- **Pass/Fail Criteria:** PASS if node telemetry appears in the dashboard within 10 seconds of server startup.

#### Test A.4: Telemetry Timestamps & Data Freshness
- **Prerequisites:** Systems synchronized via NTP (`chrony` or `systemd-timesyncd`).
- **Steps:**
  1. Inspect ISO 8601 timestamps in received telemetry packets at `GET http://127.0.0.1:8420/api/v1/nodes/uno-q-001/latest`.
  2. Compare payload timestamp against system time:
     ```bash
     date -u +"%Y-%m-%dT%H:%M:%SZ"
     ```
- **Expected Outcome:** Payload timestamp is within $\pm 2.0$ seconds of wall-clock UTC.
- **Evidence to Collect:** Delta between `payload.timestamp` and `date -u`.
- **Pass/Fail Criteria:** PASS if delta is $\le 3.0$ seconds; FAIL if timestamps are in the future or stale.

---

### Section B: Sensor Plausibility & Gating Checks

#### Test B.1: Mandatory 30-Second Warmup & Stabilization
- **Prerequisites:** Hardware bridge launched with physical sensors (`--physical`).
- **Steps:**
  1. Launch the hardware launcher:
     ```bash
     ./run_hardware.sh --port 127.0.0.1:7500 --node-id uno-q-001
     ```
  2. Observe console logs during the first 30 seconds.
- **Expected Outcome:**
  - Bridge prints: `[HW] Initiating mandatory 30-second sensor warm-up period...`
  - Bridge polls sensors every 5s during warmup without submitting readings to `/hardware/data`.
  - At $t=30$s, bridge sends `POST /hardware/ready` handshake: `[HW] 30-second sensor warm-up complete. Sensors are READY.`
  - Intelligence Server logs: `Hardware node uno-q-001 sensors READY after 30.0s warm-up period`.
- **Evidence to Collect:** Timestamps in launcher stdout during warmup and handshake.
- **Pass/Fail Criteria:** PASS if exactly 30s elapsed before first reading ingestion and handshake succeeds.

#### Test B.2: DHT22 Ambient Plausibility
- **Prerequisites:** Sensor operating in standard indoor ambient room conditions.
- **Steps:**
  1. Read temperature and humidity telemetry from `/api/v1/nodes/uno-q-001/latest`.
  2. Compare against a calibrated reference room thermometer / hygrometer.
- **Expected Outcome:**
  - Temperature: $18.0^\circ\text{C} \le T \le 35.0^\circ\text{C}$ (indoor room ambient).
  - Humidity: $25.0\% \le H \le 85.0\%$.
  - DHT22 parity checksum `dht_ok == true`.
- **Evidence to Collect:** Ten consecutive reading samples of `temperature_C` and `humidity_pct`.
- **Pass/Fail Criteria:** PASS if readings fall within room ambient ranges and match reference thermometer within $\pm 2.0^\circ\text{C}$ and $\pm 5\%$.

#### Test B.3: MQ-2, MQ-9, and MQ-135 Baseline Voltages & Pre-Inference Safety Gate
- **Prerequisites:** Heated sensors operating in clean indoor air after 30s warmup.
- **Steps:**
  1. Inspect analog voltages in telemetry: `mq2_voltage_v`, `mq9_voltage_v`, `mq135_voltage_v`.
  2. Verify ADC-to-voltage conversion consistency: $V = \text{ADC} \times (5.0 / 1023.0) \pm 0.05\text{V}$.
  3. Verify that voltages are strictly within valid physical range: $0.10\text{V} \le V \le 4.85\text{V}$.
- **Expected Outcome:**
  - In clean baseline air: typical MQ voltages range between $0.40\text{V}$ and $1.50\text{V}$.
  - Pre-inference gate passes: `safety_status == "normal"` or `"safe"`.
  - TinyGasNet predicts `CleanAir` or expected baseline class.
- **Evidence to Collect:** ADC and voltage values for all three MQ channels.
- **Pass/Fail Criteria:** PASS if all MQ voltages are within $[0.10\text{V}, 4.85\text{V}]$ and TinyGasNet executes without safety gate abstention.

#### Test B.4: Particulate Matter Plausibility & Ordering Tolerance
- **Prerequisites:** MPM10-CS / PMS5003 laser sensor active.
- **Steps:**
  1. Inspect particulate concentrations: `PM1_0`, `PM2_5`, `PM10`.
  2. Check physical ordering constraint:
     $$\text{PM1.0} \le \text{PM2.5} + 3.0\mu g/m^3 \quad \text{and} \quad \text{PM2.5} \le \text{PM10} + 3.0\mu g/m^3$$
- **Expected Outcome:**
  - Ambient clean room concentrations: $\text{PM1.0} \approx 5\text{--}25\mu g/m^3$, $\text{PM2.5} \approx 10\text{--}45\mu g/m^3$, $\text{PM10} \approx 15\text{--}70\mu g/m^3$.
  - Zero negative values ($PM \ge 0.0$).
  - Physical particle size ordering holds within documented $3.0\mu g/m^3$ sensor noise tolerance.
- **Evidence to Collect:** Log of 20 consecutive PM frames.
- **Pass/Fail Criteria:** PASS if ordering holds across all 20 frames and no `422 Unprocessable Entity` or `INVALID_INPUT` is triggered.

---

### Section C: End-to-End Behavior & Regulatory Reporting

#### Test C.1: Live Telemetry Display & Refresh
- **Prerequisites:** Hardware bridge running; MPI3501 display attached or terminal UI active.
- **Steps:**
  1. Observe physical MPI3501 LCD screen.
  2. Check display update rate (default refresh: 10s).
- **Expected Outcome:**
  - LCD screen displays current AQI, dominant pollutant, temperature, humidity, gas classification, and advisory action banner.
  - UI updates every 10 seconds without flickering, tearing, or freezing.
- **Evidence to Collect:** Photo or video of MPI3501 display showing live updating values.
- **Pass/Fail Criteria:** PASS if display renders live sensor data matching `/api/v1/nodes/uno-q-001/latest`.

#### Test C.2: CPCB Regulatory AQI Labeling & Completeness Flag
- **Prerequisites:** Server running with default `CPCB` standard.
- **Steps:**
  1. Query `GET http://127.0.0.1:8420/aqi/latest`.
  2. Inspect regulatory metadata fields:
     - `calculation_method`
     - `is_complete_national_aqi`
     - `dominant_pollutant`
     - `sub_indices`
- **Expected Outcome:**
  - `calculation_method` == `"CPCB_PM_ESTIMATE"`.
  - `is_complete_national_aqi` == `false`.
  - `sub_indices` contains strictly `PM2_5` and `PM10` (no PM1.0 regulatory sub-index).
  - Dominant pollutant is either `PM2_5` or `PM10`.
  - Category corresponds strictly to CPCB bands (Good, Satisfactory, Moderate, Poor, Very Poor, Severe).
- **Evidence to Collect:** JSON output from `/aqi/latest`.
- **Pass/Fail Criteria:** PASS if `calculation_method` is CPCB_PM_ESTIMATE and `is_complete_national_aqi` is false.

#### Test C.3: Forecasting Availability with Insufficient History
- **Prerequisites:** Newly booted server with less than 12 historical points (< 1 hour of runtime).
- **Steps:**
  1. Query `GET http://127.0.0.1:8420/api/v1/forecast/nodes/uno-q-001/predict?horizon_minutes=60`.
- **Expected Outcome:**
  - `status` == `"insufficient_data"`.
  - `reliability` == `"unavailable"`.
  - Message states: `Insufficient data for forecasting. Need at least 12 points per channel.`
  - No speculative or garbage numerical predictions emitted.
- **Evidence to Collect:** Response payload of forecast endpoint.
- **Pass/Fail Criteria:** PASS if endpoint gracefully returns `insufficient_data` without crashing or returning ungrounded numbers.

#### Test C.4: Advisory Engine & Source Classifier Propagation
- **Prerequisites:** Server running with live telemetry.
- **Steps:**
  1. Query `GET http://127.0.0.1:8420/api/v1/nodes/uno-q-001/latest`.
  2. Check `predictions.source` and `advisory`.
- **Expected Outcome:**
  - `predictions.source.value` contains classified source (e.g. `CleanAir`, `Ambient`, or source label) with confidence score.
  - If ambiguous or out-of-domain, `is_uncertain == true` or abstention is preserved.
  - `advisory.severity` reflects AQI level (NORMAL, MODERATE, HIGH, SEVERE).
  - Action items provide practical mitigations matching the dominant pollutant.
- **Evidence to Collect:** Full JSON response from `/latest`.
- **Pass/Fail Criteria:** PASS if advisory matches active AQI band and source predictions are finite.

---

### Section D: Fault Handling & Safe Recovery

> [!CAUTION]
> Execute fault tests using the non-destructive physical procedures specified below. Do NOT touch live high-voltage lines, use open flames, or short circuit power rails.

#### Test D.1: Safe Particulate Sensor Disconnection & Reconnection
- **Prerequisites:** System running in steady state.
- **Steps:**
  1. Gently disconnect the MPM10-CS RX/TX jumper cable (Pin D0/D1) from the sensor.
  2. Observe hardware bridge console and server logs for 2 sampling intervals (120s).
  3. Reconnect the MPM10-CS jumper cable firmly into Pin D0/D1.
  4. Observe subsequent 2 sampling intervals.
- **Expected Outcome:**
  - When disconnected: Arduino firmware detects missing UART frames (`pms_ok == false`). Bridge validator flags warning/error. Server marks sensor fault or maintains moving average with provisional status.
  - When reconnected: UART frame sync ($0x42, 0x4D$) restores automatically within 3 seconds. Telemetry resumes without requiring a server reboot.
- **Evidence to Collect:** Server log timestamps during disconnect and reconnect.
- **Pass/Fail Criteria:** PASS if system gracefully flags fault without crashing and recovers automatically upon reconnection.

#### Test D.2: Safe DHT22 Telemetry Failure
- **Prerequisites:** System running in steady state.
- **Steps:**
  1. Disconnect DHT22 data wire (Pin D8).
  2. Observe telemetry responses on server.
  3. Reconnect DHT22 data wire.
- **Expected Outcome:**
  - Firmware detects timeout on start pulse (`dht_ok == false`).
  - Pre-inference gate notes missing temperature/humidity and abstains or alerts.
  - Upon reconnection: valid reading restores within 2 seconds (DHT22 read cycle).
- **Evidence to Collect:** Server response showing degraded status and recovery.
- **Pass/Fail Criteria:** PASS if no unhandled exceptions occur.

#### Test D.3: Simulated Rail Fault Injection (Software Safety Verification)
- **Prerequisites:** Use curl or postman to test the pre-inference gate against simulated electrical rail faults (0.00V GND short or 5.00V VCC rail short).
- **Steps:**
  1. Submit synthetic rail short payload:
     ```bash
     curl -X POST http://127.0.0.1:8420/api/v1/nodes/uno-q-001/readings \
       -H "Content-Type: application/json" \
       -d '{"node_id":"uno-q-001","timestamp":"2026-10-28T12:00:00Z","environment":{"temperature_C":25.0,"humidity_pct":50.0},"particulate_matter":{"PM1_0":10.0,"PM2_5":20.0,"PM10":35.0},"gas_sensors":{"MQ2":{"raw_adc":0,"voltage_V":0.00},"MQ9":{"raw_adc":200,"voltage_V":0.98},"MQ135":{"raw_adc":250,"voltage_V":1.22}}}'
     ```
- **Expected Outcome:**
  - Pre-inference gate intercepts 0.00V rail short ($< 0.10\text{V}$).
  - TinyGasNet inference **abstained**.
  - `gas_class` == `"SENSOR_FAULT"`.
  - `safety_status` == `"unknown"`.
  - Server does NOT misclassify the electrical fault as `CleanAir`.
- **Evidence to Collect:** HTTP response payload from the POST request.
- **Pass/Fail Criteria:** PASS if pre-inference gate completely blocks model evaluation and flags `SENSOR_FAULT`.

#### Test D.4: Server Restart Persistence & State Integrity
- **Prerequisites:** At least 30 minutes of live telemetry stored in `data/nodes/uno-q-001/readings_*.jsonl`.
- **Steps:**
  1. Stop Intelligence Server using `Ctrl+C` (SIGINT).
  2. Check that process terminated cleanly.
  3. Restart Intelligence Server.
  4. Query `GET /aqi/latest`.
- **Expected Outcome:**
  - Server restarts without file lock errors.
  - `AQIStore` reloads the last calculated AQI state from `data/aqi_latest.json`.
  - Existing JSONL logs in `data/nodes/uno-q-001/` remain intact and append-ready.
- **Evidence to Collect:** Server restart log showing `Loaded latest AQI state`.
- **Pass/Fail Criteria:** PASS if previous AQI value and history persist across restarts.

---

## 3. Physical Hardware Validation Summary Matrix

| ID | Test Name | Target Subsystem | Priority | Expected Pass Criteria |
|:---|:---|:---|:---:|:---|
| **A.1** | Firmware & Router Monitor | MCU Firmware / Router | **P0** | JSON stream on port 7500 every 3s |
| **A.2** | Server Health & Readiness | Intelligence Server | **P0** | `/health` and `/ready` return HTTP 200 |
| **A.3** | Manager / Dashboard Binding | Parent Manager | **P1** | Node appears ONLINE in dashboard |
| **A.4** | Timestamp Freshness | Ingestion Pipeline | **P1** | $|t_{\text{payload}} - t_{\text{wall}}| \le 3.0$s |
| **B.1** | 30s Sensor Warmup | Hardware Bridge | **P0** | Exactly 30s warmup before first send |
| **B.2** | DHT22 Plausibility | DHT22 Driver | **P0** | $18\text{--}35^\circ\text{C}$, $25\text{--}85\%$ RH |
| **B.3** | MQ Voltage & Safety Gate | MQ-2/9/135 Array | **P0** | $0.10\text{V} \le V \le 4.85\text{V}$, no false trip |
| **B.4** | PM Ordering & Bounds | MPM10-CS Driver | **P0** | $\text{PM1.0} \le \text{PM2.5}+3 \le \text{PM10}+6$ |
| **C.1** | Display Rendering | MPI3501 LCD | **P1** | 10s refresh matching server telemetry |
| **C.2** | CPCB AQI Labeling | AQI Calculator | **P0** | `CPCB_PM_ESTIMATE`, `is_complete=false` |
| **C.3** | Forecast History Guard | Forecast Model | **P1** | `insufficient_data` when points < 12 |
| **C.4** | Advisory & Source Propagation | Pipeline Orchestrator | **P1** | Actions match dominant pollutant |
| **D.1** | Safe PM Disconnection | Hardware Bridge | **P1** | Graceful fault flag; auto-recover |
| **D.2** | Safe DHT22 Disconnection | Hardware Bridge | **P1** | Graceful fault flag; auto-recover |
| **D.3** | Rail Short Injection (Simulated)| Safety Gate | **P0** | `SENSOR_FAULT`, zero false clean-air |
| **D.4** | Server Restart Persistence | JSONL Storage / AQI Store | **P0** | No state corruption or history loss |

---
*Checklist prepared for NavosEdge Physical Hardware Validation on Arduino UNO Q.*

