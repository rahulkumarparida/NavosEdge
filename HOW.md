# NavosEdge — Complete Hardware & Deployment Guide (`HOW.md`)

This guide provides end-to-end instructions for running NavosEdge with **actual physical hardware sensors**, explains why mock mode was previously running even after executing `./run_hardware.sh`, and details how to verify and confirm that your system is actively ingesting real physical sensor readings.

---

## Table of Contents
1. [The "Mock Mode Still Alive" Issue Explained & Fixed](#1-the-mock-mode-still-alive-issue-explained--fixed)
2. [Hardware Wiring & Sensor Pinout](#2-hardware-wiring--sensor-pinout)
3. [Step 1: Flashing the Arduino Sensor Firmware](#3-step-1-flashing-the-arduino-sensor-firmware)
4. [Step 2: Grant Linux Serial Permissions & Test Raw Serial Stream](#4-step-2-grant-linux-serial-permissions--test-raw-serial-stream)
5. [Step 3: Configuring the System for Real Sensors](#5-step-3-configuring-the-system-for-real-sensors)
6. [Step 4: Running the Entire Project](#6-step-4-running-the-entire-project)
7. [How to Know For Sure It Is Running Real Data vs Mock Mode](#7-how-to-know-for-sure-it-is-running-real-data-vs-mock-mode)
8. [Verifying Sensor Readings via API & Files](#8-verifying-sensor-readings-via-api--files)
9. [Troubleshooting Guide](#9-troubleshooting-guide)

---

## 1. The "Mock Mode Still Alive" Issue Explained & Fixed

### Why was Mock Mode still running after `./run_hardware.sh`?

If you ran `./run_hardware.sh` and suspected that mock/simulated data was still being generated, **your observation was 100% correct**. Here is the exact technical reason why that happened:

1. **The `.env` configuration file** contained:
   ```bash
   NAVOS_SENSOR_MODE=mock
   ```
2. **`run_hardware.sh` sources `.env` with `set -a`**:
   At the start of `run_hardware.sh`, the script loads `.env` and exports all variables into the shell environment:
   ```bash
   set -a
   source "$REPO_ROOT/.env"
   set +a
   ```
   This exported `NAVOS_SENSOR_MODE="mock"` into the process environment.
3. **The C++ binary config loader priority (`Hardware/include/config.hpp`)**:
   Although `run_hardware.sh` generated a temporary runtime config JSON with `"mock_mode": false`, the C++ configuration parser checks environment variables **after** reading the JSON file:
   ```cpp
   if (const char* env_mode = std::getenv("NAVOS_SENSOR_MODE")) {
       std::string mode = env_mode;
       cfg.mock_mode = (mode == "mock" || mode == "true" || mode == "1");
   }
   ```
   Because `NAVOS_SENSOR_MODE=mock` was exported from `.env`, the environment variable **overrode** the JSON file and set `cfg.mock_mode = true`!
4. **Result:** The C++ binary initialized `MockSensorSource` instead of `SerialSensorSource`, producing synthetic sinusoidal data rather than reading from `/dev/ttyACM0`.

### What was done to fix it?

1. **`run_hardware.sh` updated:** The script now explicitly launches the C++ binary with `NAVOS_SENSOR_MODE=physical` and `NAVOS_SERIAL_PORT="$SERIAL_PORT"`, ensuring environment overrides cannot force mock mode during hardware launch.
2. **Configuration instructions below:** You can also set `NAVOS_SENSOR_MODE=physical` directly in your `.env` and `"mock_mode": false` in `Hardware/config/hardware_config.json`.

---

## 2. Hardware Wiring & Sensor Pinout

Before running hardware mode, ensure your sensors are wired to your **Arduino UNO Q** (or sensor-gathering MCU board) as defined in [`Hardware/firmware/navos_sensors.ino`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Hardware/firmware/navos_sensors.ino):

| Sensor | Type | MCU Pin | Notes |
|:---|:---|:---|:---|
| **MQ-2** | Analog Gas (Smoke / LPG / Propane) | **A0** | 5V VCC, GND, Analog OUT to A0 |
| **MQ-9** | Analog Gas (Carbon Monoxide / Gas) | **A1** | 5V VCC, GND, Analog OUT to A1 |
| **MQ-135** | Analog Gas (Air Quality / NH3 / Toxins) | **A2** | 5V VCC, GND, Analog OUT to A2 |
| **DHT22** | Digital Temperature & Humidity | **Pin 8 (D8)** | 5V VCC, GND, DATA to D8 with 10kΩ pull-up resistor to 5V |
| **MPM10-CS** | Particulate Matter (PM1.0, PM2.5, PM10) | **Serial1 (D0=RX, D1=TX)** | MPM10 TX → Arduino D0 (RX); MPM10 RX → Arduino D1 (TX); 9600 baud |

> [!NOTE]
> MQ-series sensors have internal heating elements and require a **30-second initial warm-up** period on power-up to stabilize ADC resistance. The system automatically performs a 30-second warm-up countdown upon boot.

---

## 3. Step 1: Flashing the Arduino Sensor Firmware

The Arduino board that physically samples the sensors must be programmed with the NavosEdge sensor firmware: [`Hardware/firmware/navos_sensors.ino`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Hardware/firmware/navos_sensors.ino).

### Using `arduino-cli`:

```bash
# 1. Compile the sensor firmware
arduino-cli compile --fqbn arduino:avr:uno Hardware/firmware/navos_sensors.ino

# 2. Upload to the connected Arduino board (adjust /dev/ttyACM0 if needed)
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno Hardware/firmware/navos_sensors.ino
```

*(If using an Arduino UNO Q core, replace `arduino:avr:uno` with `arduino:zephyr:unoq`).*

### Or using the Arduino IDE:
1. Open [`Hardware/firmware/navos_sensors.ino`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Hardware/firmware/navos_sensors.ino).
2. Select your board and port (e.g., `/dev/ttyACM0`).
3. Click **Upload**.

---

## 4. Step 2: Grant Linux Serial Permissions & Test Raw Serial Stream

On Linux, serial access to `/dev/ttyACM0` or `/dev/ttyUSB0` requires dialout group membership.

### 1. Grant serial permissions:
```bash
sudo usermod -a -G dialout $USER
```
*(Log out and log back in, or run `sudo chmod 666 /dev/ttyACM0` for immediate temporary access).*

### 2. Verify raw serial data stream directly:
Before launching the server or C++ bridge, run this quick test to prove that your Arduino is actively streaming real sensor readings:

```bash
# Set baud rate to 115200
stty -F /dev/ttyACM0 115200 raw -echo

# Read raw lines directly from the serial port
cat /dev/ttyACM0
```

**Expected output (new JSON line every ~3 seconds):**
```json
{"status":"booting","firmware":"navos_sensors","version":"1.0.0"}
{"mq2":324,"mq9":210,"mq135":385,"t":26.80,"h":58.40,"pm1":11.2,"pm25":16.7,"pm10":22.1,"dht_ok":true,"pms_ok":true,"ok":true}
{"mq2":326,"mq9":212,"mq135":387,"t":26.80,"h":58.50,"pm1":11.0,"pm25":16.5,"pm10":22.0,"dht_ok":true,"pms_ok":true,"ok":true}
```
Press `Ctrl+C` once you see these lines streaming.

---

## 5. Step 3: Configuring the System for Real Sensors

Open [`.env`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/.env) in the project root:

```ini
# Change NAVOS_SENSOR_MODE to physical:
NAVOS_SENSOR_MODE=physical

# Set your serial port and sampling interval (in seconds):
NAVOS_SERIAL_PORT=/dev/ttyACM0
NAVOS_SENSOR_INTERVAL=10
```

Also verify [`Hardware/config/hardware_config.json`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Hardware/config/hardware_config.json):
```json
{
    "server_url": "http://localhost:8420",
    "node_id": "uno-q-001",
    "sampling_interval_seconds": 10,
    "retry_max_attempts": 5,
    "retry_base_delay_seconds": 2,
    "http_timeout_seconds": 10,
    "mock_mode": false,
    "scenario": "normal",
    "serial_port": "/dev/ttyACM0",
    "serial_baud": 115200,
    "serial_timeout_ms": 5000
}
```

---

## 6. Step 4: Running the Entire Project

### Option A: The One-Command Hardware Launcher (Recommended)

Run [`run_hardware.sh`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/run_hardware.sh) with `--skip-flash` (if display is already flashed or if using headless mode):

```bash
./run_hardware.sh --interval 10 --port /dev/ttyACM0 --skip-flash
```

#### What happens during execution:
1. **[1/8] Checking environment:** Verifies Python 3, CMake, GCC, libcurl.
2. **[2/8] Checking physical hardware:** Confirms `/dev/ttyACM0` exists.
3. **[3/8] Preparing Python environment:** Sets up `Intelligence/Server/venv`.
4. **[4/8] Building C++ Hardware:** Builds `navos_hardware_bridge`.
5. **[5/8] Display build/flash:** Skipped when `--skip-flash` is passed.
6. **[6/8] Verifying model artifacts:** Checks neural network weights and scalers.
7. **[7/8] Starting Intelligence Server:** Launches FastAPI server on port 8420.
8. **[8/8] Starting Physical Hardware:** Launches C++ bridge in physical mode (`NAVOS_SENSOR_MODE=physical`).
9. **30s Sensor Warm-up:** Probes sensors and counts down 30s while MQ heaters stabilize.
10. **Data Flow Begins:** Periodic readings are acquired from `/dev/ttyACM0`, validated, and POSTed to the Intelligence Server.

---

### Option B: Manual Multi-Terminal Run (For Debugging & Diagnostics)

If you prefer to see each component in its own dedicated terminal:

#### Terminal 1 — Intelligence Server:
```bash
cd /home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8420 --log-level info
```

#### Terminal 2 — C++ Physical Hardware Bridge:
```bash
cd /home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Hardware/build

# Compile if not already compiled:
cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(nproc)

# Run with physical sensor environment overrides:
NAVOS_SENSOR_MODE=physical \
NAVOS_SERIAL_PORT=/dev/ttyACM0 \
NAVOS_SENSOR_INTERVAL=10 \
./navos_hardware_bridge --node-id uno-q-001 --interval 10
```

---

## 7. How to Know For Sure It Is Running Real Data vs Mock Mode

Here are the concrete indicators that tell you definitively whether you are seeing **real physical readings** or **mock/simulated data**:

### 1. Terminal Startup Message

| Mode | Banner / Initialization Output |
|:---|:---|
| **MOCK MODE** | `[HW] Mock sensor initialized (scenario: normal)` |
| **REAL HARDWARE MODE** | `[HW] Physical sensor initialized on /dev/ttyACM0 @ 115200 baud`<br>`[HW] Monitored physical sensors: MQ-2, MQ-9, MQ-135, DHT22, MPM10-CS` |

---

### 2. Live Reading Console Output

In **Real Hardware Mode**, every reading cycle prints the detailed `[SERIAL]` inspection block directly from the serial parser, followed by the transmission block:

```text
[SERIAL] ================= REAL SENSOR READING =================
[SERIAL] Hardware Node : uno-q-001
[SERIAL] Timestamp     : 2026-10-06T14:35:12Z
[SERIAL] --------------------------------------------------------
[SERIAL] Sensor 1 | MQ-2   (Combustible Gas & Smoke) :
[SERIAL]          Raw ADC = 328 / 1023 | Voltage = 1.603 V
[SERIAL] Sensor 2 | MQ-9   (CO & Flammable Gas)      :
[SERIAL]          Raw ADC = 214 / 1023 | Voltage = 1.046 V
[SERIAL] Sensor 3 | MQ-135 (Air Quality & Toxins)    :
[SERIAL]          Raw ADC = 391 / 1023 | Voltage = 1.911 V
[SERIAL] Sensor 4 | DHT22  (Temperature & Humidity)  :
[SERIAL]          Temperature = 27.20 °C | Humidity = 61.40 % [Status: HEALTHY]
[SERIAL] Sensor 5 | MPM10-CS (Particulate Matter)    :
[SERIAL]          PM1.0 = 10.5 ug/m3 | PM2.5 = 15.8 ug/m3 | PM10 = 21.4 ug/m3 [Status: HEALTHY]
[SERIAL] Overall State : READY (Sensors stabilized)
[SERIAL] ========================================================

[HW] Sending sensor reading #1 (node: uno-q-001):
     • MQ-2   (Combustible/Smoke)  : ADC=328 (1.603V)
     • MQ-9   (CO/Flammable Gas)   : ADC=214 (1.046V)
     • MQ-135 (Air Quality/Toxins) : ADC=391 (1.911V)
     • DHT22  (Temp & Humidity)    : Temp=27.20 °C, Hum=61.40 %
     • MPM10  (Particulate Matter) : PM1.0=10.5, PM2.5=15.8, PM10=21.4 ug/m3
```

In **Mock Mode**, the `[SERIAL] ================= REAL SENSOR READING =================` box **never appears**, because no serial port is ever opened.

---

### 3. Physical Stimulus Tests (Definitive Proof)

To verify beyond any doubt that live sensor data is flowing:

1. **The Breath / Humidity Test:**
   - Gently exhale warm breath directly onto the DHT22 sensor grill.
   - **Real Sensor:** In the next reading, humidity will jump from ~55% up to 80–90%+, and temperature will increase slightly.
   - **Mock Mode:** Values will continue smooth sinusoidal cycles unaffected by your breath.
2. **The Gas / Lighter Test:**
   - Take an unlit cigarette lighter, hold the button down for 1 second near the MQ-2 sensor to release a tiny burst of butane gas (do NOT ignite a flame).
   - **Real Sensor:** MQ-2 ADC reading will jump sharply from ~300 to 700+, and voltage will rise above 3.5V.
   - **Mock Mode:** MQ-2 ADC stays fixed around baseline (~350).
3. **The Particle / Airflow Test:**
   - Wave your hand or blow air gently into the MPM10-CS intake.
   - **Real Sensor:** PM2.5 / PM10 readings will fluctuate immediately.
   - **Mock Mode:** PM readings follow mathematical formula patterns.

---

## 8. Verifying Sensor Readings via API & Files

While NavosEdge is running, open another terminal and query the system:

### 1. Query the Latest Sensor & AI Reading:
```bash
curl -s http://127.0.0.1:8420/api/v1/nodes/uno-q-001/latest | python3 -m json.tool
```

You will see:
- Live `environment` (temperature & humidity)
- `particulate_matter` (PM1.0, PM2.5, PM10)
- `gas_sensors` (MQ2, MQ9, MQ135 ADC & voltage)
- Computed `aqi` and EPA air quality category
- AI `source_classification` (traffic, clean indoor, etc.)
- GasNet anomaly detection results

### 2. Listen to Real-Time SSE Stream:
```bash
curl -N http://127.0.0.1:8420/hardware/events?node_id=uno-q-001
```
Every time a new reading arrives and is processed, an `intelligence_update` event is pushed down this connection in real-time.

### 3. Check Stored Raw Readings:
Recorded readings are persisted to disk in the data directory:
```bash
tail -n 20 data/aqi_latest.json
```

---

## 9. Troubleshooting Guide

### Q1: `[SERIAL] Cannot open /dev/ttyACM0: Permission denied`
- **Solution:** Add your user to the `dialout` group and apply permissions:
  ```bash
  sudo usermod -a -G dialout $USER
  sudo chmod 666 /dev/ttyACM0
  ```

### Q2: `[SERIAL] Cannot open /dev/ttyACM0: No such file or directory`
- **Solution:** Your board might be mapped to `/dev/ttyACM1` or `/dev/ttyUSB0`.
  Find the active serial device:
  ```bash
  ls /dev/ttyACM* /dev/ttyUSB*
  ```
  Then specify the port with `--port`:
  ```bash
  ./run_hardware.sh --port /dev/ttyUSB0 --skip-flash
  ```

### Q3: `DHT22 sensor report: FAULT / UNHEALTHY` in logs
- **Cause:** DHT22 did not respond within the timing threshold.
- **Solution:** Verify the 10kΩ pull-up resistor between DHT22 DATA (pin 8) and VCC (5V). DHT22 sensors require this pull-up to pull the open-drain line high.

### Q4: `MPM10-CS sensor report: FAULT / UNHEALTHY` in logs
- **Cause:** Serial1 is not receiving valid 32-byte PMS frames.
- **Solution:** Check MPM10 TX pin is connected to Arduino D0 (RX). Ensure baud rate is 9600.

### Q5: `Port 8420 in use (PID: ...)`
- **Solution:** `run_hardware.sh` automatically frees the port, or you can kill it manually:
  ```bash
  fuser -k 8420/tcp
  ```
