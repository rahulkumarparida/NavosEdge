# NavosEdge — Arduino UNO Q Deployment & End-to-End Guide

This guide provides complete instructions for deploying, flashing, and executing **NavosEdge** on the **Arduino UNO Q** paired with the **MPI3501 3.5" (480×320) TFT Display**.

---

## 1. System Overview & Architecture

NavosEdge separates high-level MPU Linux workloads (sensor data ingestion, real-time ML inference, environmental intelligence, advisory calculations, and SSE event streaming) from physical MCU display rendering.

Linux and MCU communicate using the official **Arduino UNO Q Router MessagePack-RPC protocol** over the Unix domain socket `/var/run/arduino-router.sock`.

```text
+---------------------------------------------------------------------------------------------------+
|                                        ARDUINO UNO Q                                              |
|                                                                                                   |
|  [ Linux Side ]                                                                                   |
|  +------------------------+     POST /hardware/data      +-------------------------------------+  |
|  | MockSensorSource (C++) | ---------------------------> | Intelligence Server (Python)        |  |
|  |  - Synthetic PMs       |                              |  - GasNet ML Inference Model        |  |
|  |  - MQ Gas Voltages     |                              |  - Anomaly & AQI Engine             |  |
|  |  - Temp / Humidity     |                              |  - Source Classifier & Advisory     |  |
|  +------------------------+                              +-------------------------------------+  |
|               ^                                                             |                     |
|               | SSE Event Stream ("intelligence_update")                    |                     |
|               +-------------------------------------------------------------+                     |
|                                                                             |                     |
|                                          | Formats State                    v                     |
|                                +-------------------+           +--------------------------+       |
|                                | McuBridge (C++)   | --------> | /var/run/arduino-router  |       |
|                                +-------------------+ (RPC)     | (.sock MessagePack-RPC)  |       |
|                                                                +--------------------------+       |
| ============================================================================|==================== |
|  [ MCU Side (Zephyr / STM32U5) ]                                            v                     |
|                                +-------------------+           +--------------------------+       |
|                                | mcu_display.ino   | <-------- | Arduino_RouterBridge     |       |
|                                +-------------------+ (RPC)     +--------------------------+       |
|                                          |                                                        |
|                                          v Updates NavosEdgeState                                 |
|                                +-------------------+                                              |
|                                | NavosEdgeGUI (C++)| (3-screen 10s non-blocking rotation)           |
|                                +-------------------+                                              |
|                                          | Hardware SPI (MOSI=D11, SCK=D13, CS=D10, DC=D2)        |
|                                          v                                                        |
|                              +-----------------------+                                            |
|                              | MPI3501 3.5" Display  | (Physical 480x320 ILI9486 Display)         |
|                              +-----------------------+                                            |
+---------------------------------------------------------------------------------------------------+
```

### Runtime Architecture Rules
- **Physical GUI Execution**: The GUI runs on the UNO Q MCU (`mcu_display.ino`) and renders on the physical MPI3501 LCD via `UNOQ_MPI3501`.
- **Router MessagePack-RPC Transport**: Linux application connects to `/var/run/arduino-router.sock` and invokes the `update_display` method registered by `Arduino_RouterBridge` on the MCU.
- **Portability**: All scripts (`flash_display.sh`, `run_display_simulation.sh`) dynamically resolve paths and libraries without hardcoded username paths (`/home/rahulroxx`).
- **Terminal Cleanliness**: Terminals display operational logs (`[HW]`, `[INTELLIGENCE]`, `[MCU]`). Console `[TFT]` print statements are disabled.
- **Non-Blocking Rotation**: Screen rotation occurs every **10 seconds** independently on MCU using `millis()`.

---

## 2. Prerequisites & Hardware Wiring

### A. Hardware SPI Connections
Wire the MPI3501 3.5" display pins to the Arduino UNO Q:
- **SPI Bus**: `MOSI = D11`, `MISO = D12`, `SCK = D13`
- **Control Pins**: `CS = D10`, `DC = D2`, `RST = D3`
- **Power**: `VCC = 5V`, `GND = GND`

### B. Linux Environment Requirements
On the UNO Q Linux environment (user `arduino`):
```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv cmake make g++ libcurl4-openssl-dev
```

---

## 3. Step-by-Step Deployment & Execution

### Step 1: Clone or Open Workspace
```bash
ssh arduino@UNO-Q
cd ~/NavosEdge
```

### Step 2: Compile and Flash the MCU Display Application
Compiles `mcu_display.ino` with `arduino-cli` using repository-local third-party libraries (`Hardware/third_party/`) and flashes the MCU (`arduino:zephyr:unoq`):

```bash
./flash_display.sh
```

Expected log snippet:
```text
============================================================
 NavosEdge — MCU Physical Display Flasher
============================================================
  Current User:       arduino
  Home Directory:     /home/arduino
  Target Board FQBN:  arduino:zephyr:unoq
============================================================
[FLASH] Compiling MCU display sketch...
Sketch uses 109300 bytes (13%) of program storage space.
[FLASH] Deploying firmware to Arduino UNO Q MCU...
============================================================
 [FLASH] SUCCESS: MCU display firmware flashed and active!
============================================================
```

### Step 3: Verify MessagePack-RPC Transport (Optional)
Test MPU ↔ MCU MessagePack-RPC state transfer standalone:

```bash
./Hardware/build/navos_hardware_bridge --test-rpc
```

Expected log output:
```text
[MCU] Standalone RPC test mode
[MCU] Router connected
[MCU] Display state sent via RPC
[MCU] AQI=63.41 PM2.5=18 TEMP=28.5
```

### Step 4: Launch End-to-End Pipeline
Run the synthetic sensor source, Intelligence Server, and C++ RPC Bridge:

```bash
./run_display_simulation.sh
```

---

## 4. Testing Options & Flags

### Fast Verification Mode (5-Second Update Interval)
```bash
./run_display_simulation.sh --interval 5
```

### Environmental Simulation Scenarios
```bash
# Traffic scenario (elevated vehicular gases & PM)
./run_display_simulation.sh --scenario traffic --interval 5

# Dust scenario (high PM10 and PM2.5 levels)
./run_display_simulation.sh --scenario dust --interval 5

# High PM scenario (severe particulate matter spike)
./run_display_simulation.sh --scenario high_pm --interval 5

# Normal baseline
./run_display_simulation.sh --scenario normal --interval 5
```

---

## 5. Troubleshooting Guide

| Issue | Cause | Resolution |
|---|---|---|
| `[MCU] Warning: Unable to connect to socket` | `arduino-router.service` inactive | Run `sudo systemctl status arduino-router` and ensure router is active |
| `arduino-cli not found` | Tool path not exported | Export `ARDUINO_CLI=/path/to/arduino-cli` or ensure it is in `PATH` |
| Intelligence Server health timeout | Port 8420 held by stale process | Run `fuser -k 8420/tcp` to free port |
