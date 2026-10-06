# NavosEdge — Complete Hardware & Deployment Guide (`HOW.md`)

This guide provides end-to-end instructions for running NavosEdge with **actual physical hardware sensors**, explains the Arduino UNO Q dual-core transport architecture, details why mock mode was previously running even after executing `./run_hardware.sh`, and provides step-by-step methods to verify that your system is actively ingesting real physical sensor readings.

---

## Table of Contents
1. [Understanding the Arduino UNO Q Hardware Transport](#1-understanding-the-arduino-uno-q-hardware-transport)
2. [The "Mock Mode Still Alive" Issue Explained & Fixed](#2-the-mock-mode-still-alive-issue-explained--fixed)
3. [Hardware Wiring & Sensor Pinout](#3-hardware-wiring--sensor-pinout)
4. [Step 1: Flashing the Arduino Sensor Firmware](#4-step-1-flashing-the-arduino-sensor-firmware)
5. [Step 2: Testing the Raw Sensor Data Stream](#5-step-2-testing-the-raw-sensor-data-stream)
6. [Step 3: Configuring the System for Real Sensors](#6-step-3-configuring-the-system-for-real-sensors)
7. [Step 4: Running the Entire Project](#7-step-4-running-the-entire-project)
8. [How to Know For Sure It Is Running Real Data vs Mock Mode](#8-how-to-know-for-sure-it-is-running-real-data-vs-mock-mode)
9. [Verifying Sensor Readings via API & Files](#9-verifying-sensor-readings-via-api--files)
10. [Troubleshooting Guide](#10-troubleshooting-guide)

---

## 1. Understanding the Arduino UNO Q Hardware Transport

The Arduino UNO Q features a dual-core architecture:
- **Linux MPU (Qualcomm):** Runs Debian Linux, the Python Intelligence Server (`:8420`), and the C++ Hardware Bridge.
- **Microcontroller MCU (STM32U5):** Directly hosts the physical GPIO, analog, and UART pins where sensors are wired.

```
       Physical Sensors (MQ2, MQ9, MQ135, DHT22, MPM10-CS)
                             │
                             ▼
┌───────────────────────────────────────────────────────────────┐
│  Arduino UNO Q — MCU Core (STM32U5 / Zephyr)                  │
│  Firmware: Hardware/firmware/navos_sensors.ino                │
│  Serial.println(json) ──► mon/write MessagePack-RPC           │
└────────────────────────────┬──────────────────────────────────┘
                             │ Internal High-Speed UART (/dev/ttyHS1)
                             ▼
┌───────────────────────────────────────────────────────────────┐
│  Arduino UNO Q — Linux MPU (Qualcomm / Debian)                │
│                                                               │
│  arduino-router.service (Exclusive owner of /dev/ttyHS1)      │
│     ├─── Monitor Proxy (TCP 127.0.0.1:7500)                   │
│     │          │                                              │
│     │          ▼                                              │
│     │     C++ Hardware Bridge (SerialSensorSource)            │
│     │          │                                              │
│     │          ▼ HTTP POST                                    │
│     │     Python Intelligence Server (:8420)                  │
│     │          │ SSE Stream                                   │
│     │          ▼                                              │
│     │     C++ Hardware Bridge (McuBridge)                     │
│     │          │                                              │
│     └─── MessagePack-RPC Socket (/var/run/arduino-router.sock)│
│                │                                              │
│                ▼                                              │
│  MPI3501 LCD Display (Dashboard rendered on MCU)              │
└───────────────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **Why `127.0.0.1:7500` instead of `/dev/ttyACM0` or `/dev/ttyHS1`?**
> - On the native UNO Q Linux system, there is **no `/dev/ttyACM0` or `/dev/ttyUSB0`** device because the MCU is wired internally directly to the processor board.
> - `/dev/ttyHS1` is the raw hardware UART connected to the STM32U5 core, but it is **exclusively managed** by `arduino-router.service`. Attempting to open `/dev/ttyHS1` directly causes bus collisions and breaks display RPC calls.
> - `/dev/ttyMSM0` is reserved as the Linux kernel serial console.
> - Instead, `arduino-router` mirrors all MCU `Serial.println()` streams to its **Monitor Proxy** on **`127.0.0.1:7500`**. The C++ bridge connects to `127.0.0.1:7500` to stream real sensor frames, while using `/var/run/arduino-router.sock` to send display state RPCs.
> - If you connect a secondary external Arduino via USB on a desktop development PC, standard USB serial (`/dev/ttyACM0` or `/dev/ttyUSB0`) remains fully supported via runtime transport auto-detection.

---

## 2. The "Mock Mode Still Alive" Issue Explained & Fixed

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
4. **Result:** The C++ binary initialized `MockSensorSource` instead of `SerialSensorSource`, producing synthetic sinusoidal data rather than reading from the physical sensors.

### What was done to fix it?

1. **`run_hardware.sh` updated:** The script now explicitly launches the C++ binary with `NAVOS_SENSOR_MODE=physical` and `--physical`, ensuring environment overrides cannot force mock mode during hardware launch.
2. **`Hardware/src/main.cpp` updated:** Added explicit `--physical` and `--mock` CLI flags and `--port` overrides.
3. **Configuration defaults updated:** `Hardware/config/hardware_config.json` now defaults to `"mock_mode": false` and `"serial_port": "127.0.0.1:7500"`.

---

## 3. Hardware Wiring & Sensor Pinout

Before running hardware mode, ensure your sensors are wired to your **Arduino UNO Q** board headers as defined in [`Hardware/firmware/navos_sensors.ino`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Hardware/firmware/navos_sensors.ino):

| Sensor | Type | MCU Pin | Notes |
|:---|:---|:---|:---|
| **MQ-2** | Analog Gas (Combustible / Smoke / LPG) | **A0** | 5V VCC, GND, Analog OUT to A0 |
| **MQ-9** | Analog Gas (Carbon Monoxide / Flammable Gas) | **A1** | 5V VCC, GND, Analog OUT to A1 |
| **MQ-135** | Analog Gas (Air Quality / NH3 / Benzene / Toxins) | **A2** | 5V VCC, GND, Analog OUT to A2 |
| **DHT22** | Digital Temperature & Humidity | **Pin 8 (D8)** | 5V VCC, GND, DATA to D8 with 10kΩ pull-up resistor to 5V |
| **MPM10-CS** | Particulate Matter (PM1.0, PM2.5, PM10) | **Serial1 (D0=RX, D1=TX)** | MPM10 TX → Arduino D0 (RX); MPM10 RX → Arduino D1 (TX); 9600 baud |

> [!NOTE]
> MQ-series sensors have internal heating elements and require a **30-second initial warm-up** period on power-up to stabilize ADC resistance. The system automatically performs a 30-second warm-up countdown upon boot.

---

## 4. Step 1: Flashing the Arduino Sensor Firmware

The Arduino board that physically samples the sensors must be programmed with the NavosEdge sensor firmware: [`Hardware/firmware/navos_sensors.ino`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Hardware/firmware/navos_sensors.ino).

### Using `arduino-cli`:

```bash
# On Arduino UNO Q (Zephyr core):
arduino-cli compile --fqbn arduino:zephyr:unoq Hardware/firmware/navos_sensors.ino
arduino-cli upload --fqbn arduino:zephyr:unoq Hardware/firmware/navos_sensors.ino

# On standard external USB Arduino (e.g. Uno R3 on PC):
arduino-cli compile --fqbn arduino:avr:uno Hardware/firmware/navos_sensors.ino
arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno Hardware/firmware/navos_sensors.ino
```

---

## 5. Step 2: Testing the Raw Sensor Data Stream

Before launching the server or C++ bridge, run a quick test to prove that your sensor firmware is actively streaming real sensor readings:

### A. On Native Arduino UNO Q (Router Monitor Proxy)

Verify `arduino-router.service` is active:
```bash
systemctl status arduino-router.service
```

Read raw stream from port `7500`:
```bash
# Using netcat:
nc 127.0.0.1 7500

# Or using socat:
socat - TCP:127.0.0.1:7500

# Or using python:
python3 -c "import socket; s=socket.create_connection(('127.0.0.1', 7500)); [print(s.recv(1024).decode(errors='ignore'), end='') for _ in iter(int, 1)]"
```

### B. On External USB Arduino (Desktop PC via USB Cable)

```bash
# Grant serial permissions if needed:
sudo usermod -a -G dialout $USER
sudo chmod 666 /dev/ttyACM0

# Set baud rate to 115200 and stream:
stty -F /dev/ttyACM0 115200 raw -echo
cat /dev/ttyACM0
```

### Expected Output (JSON frame every ~3 seconds):
```json
{"status":"booting","firmware":"navos_sensors","version":"1.0.0"}
{"mq2":324,"mq9":210,"mq135":385,"t":26.80,"h":58.40,"pm1":11.2,"pm25":16.7,"pm10":22.1,"dht_ok":true,"pms_ok":true,"ok":true}
{"mq2":326,"mq9":212,"mq135":387,"t":26.80,"h":58.50,"pm1":11.0,"pm25":16.5,"pm10":22.0,"dht_ok":true,"pms_ok":true,"ok":true}
```
Press `Ctrl+C` once you see these lines streaming.

---

## 6. Step 3: Configuring the System for Real Sensors

Open [`.env`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/.env) in the project root:

```ini
# Change NAVOS_SENSOR_MODE to physical:
NAVOS_SENSOR_MODE=physical

# On Arduino UNO Q (Router Monitor Proxy):
NAVOS_SERIAL_PORT=127.0.0.1:7500

# Or for external USB Arduino on desktop PC:
# NAVOS_SERIAL_PORT=/dev/ttyACM0

NAVOS_SENSOR_INTERVAL=10
```

Verify [`Hardware/config/hardware_config.json`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Hardware/config/hardware_config.json):
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
    "serial_port": "127.0.0.1:7500",
    "serial_baud": 115200,
    "serial_timeout_ms": 5000
}
```

---

## 7. Step 4: Running the Entire Project

### Option A: The One-Command Hardware Launcher (Recommended)

Run [`run_hardware.sh`](file:///home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/run_hardware.sh) with `--skip-flash` (if display is already flashed or in headless mode):

```bash
# On Arduino UNO Q (defaults to 127.0.0.1:7500):
./run_hardware.sh --interval 10 --skip-flash

# On external USB Arduino:
./run_hardware.sh --interval 10 --port /dev/ttyACM0 --skip-flash
```

#### What happens during execution:
1. **[1/8] Checking environment:** Verifies Python 3, CMake, GCC, libcurl.
2. **[2/8] Checking physical hardware:** Confirms `127.0.0.1:7500` monitor proxy or `/dev/ttyACMx` exists.
3. **[3/8] Preparing Python environment:** Sets up `Intelligence/Server/venv`.
4. **[4/8] Building C++ Hardware:** Builds `navos_hardware_bridge`.
5. **[5/8] Display build/flash:** Skipped when `--skip-flash` is passed.
6. **[6/8] Verifying model artifacts:** Checks neural network weights and scalers.
7. **[7/8] Starting Intelligence Server:** Launches FastAPI server on port 8420.
8. **[8/8] Starting Physical Hardware:** Launches C++ bridge in physical mode (`NAVOS_SENSOR_MODE=physical` and `--physical`).
9. **30s Sensor Warm-up:** Probes sensors and counts down 30s while MQ heaters stabilize.
10. **Data Flow Begins:** Periodic readings are acquired from `127.0.0.1:7500`, validated, and POSTed to the Intelligence Server.

---

### Option B: Manual Multi-Terminal Run (For Debugging & Diagnostics)

#### Terminal 1 — Intelligence Server:
```bash
cd /home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Intelligence/Server
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8420 --log-level info
```

#### Terminal 2 — C++ Physical Hardware Bridge:
```bash
cd /home/rahulroxx/MyHDD/NewVolume/Study/Projects/NavosEdge/Hardware/build

# Compile if needed:
cmake .. -DCMAKE_BUILD_TYPE=Release && make -j$(nproc)

# Run with physical sensor endpoint:
./navos_hardware_bridge \
    --node-id uno-q-001 \
    --interval 10 \
    --port 127.0.0.1:7500 \
    --physical
```

---

## 8. How to Know For Sure It Is Running Real Data vs Mock Mode

Here are the concrete indicators that tell you definitively whether you are seeing **real physical readings** or **mock/simulated data**:

### 1. Terminal Startup Message

| Mode | Banner / Initialization Output |
|:---|:---|
| **MOCK MODE** | `[HW] Mock sensor initialized (scenario: normal)` |
| **REAL HARDWARE MODE** | `[HW] Physical sensor initialized on 127.0.0.1:7500 @ 115200 baud`<br>`[HW] Monitored physical sensors: MQ-2, MQ-9, MQ-135, DHT22, MPM10-CS` |

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

In **Mock Mode**, the `[SERIAL] ================= REAL SENSOR READING =================` box **never appears**, because no serial/socket monitor is opened.

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

## 9. Verifying Sensor Readings via API & Files

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
```bash
tail -n 20 data/aqi_latest.json
```

---

## 10. Troubleshooting Guide

### Q1: `[SERIAL] Cannot connect to router monitor proxy at 127.0.0.1:7500 (Connection refused)`
- **Cause:** The `arduino-router.service` system daemon is not running.
- **Solution:** Verify service status and restart:
  ```bash
  sudo systemctl status arduino-router.service
  sudo systemctl restart arduino-router.service
  ```

### Q2: `[SERIAL] Cannot open /dev/ttyACM0: No such file or directory`
- **Cause:** On native Arduino UNO Q, there is no `/dev/ttyACM0`. The MCU is internal and streams over `127.0.0.1:7500`.
- **Solution:** Do not specify `/dev/ttyACM0` on UNO Q. Use the default `127.0.0.1:7500`:
  ```bash
  ./run_hardware.sh --port 127.0.0.1:7500 --skip-flash
  ```
  If using an external USB Arduino on a desktop PC, check `ls /dev/ttyACM* /dev/ttyUSB*` to find the correct device.

### Q3: `DHT22 sensor report: FAULT / UNHEALTHY` in logs
- **Cause:** DHT22 did not respond within the timing threshold.
- **Solution:** Verify the 10kΩ pull-up resistor between DHT22 DATA (pin 8) and VCC (5V). DHT22 sensors require this pull-up to pull the open-drain line high.

### Q4: `MPM10-CS sensor report: FAULT / UNHEALTHY` in logs
- **Cause:** Serial1 is not receiving valid 32-byte PMS frames.
- **Solution:** Check MPM10 TX pin is connected to Arduino D0 (RX). Ensure baud rate is 9600.

### Q5: `Port 8420 in use (PID: ...)`
- **Solution:** `run_hardware.sh` automatically frees the port, or kill it manually:
  ```bash
  fuser -k 8420/tcp
  ```
