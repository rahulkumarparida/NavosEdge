# Phase 10 — Synthetic Hardware → Intelligence → MPI3501 Physical Display Integration

## Executive Summary

Phase 10 establishes the end-to-end local synthetic hardware pipeline for the **NavosEdge** edge node running on the **Arduino UNO Q** paired with the **MPI3501 3.5" (480×320) TFT Display**.

The **NavosEdge GUI rendering runs directly on the Arduino UNO Q MCU (Zephyr / STM32U5)** via the `UNOQ_MPI3501` driver over hardware SPI. The Linux environment runs synthetic sensor generation, HTTP telemetry POST, machine learning inference, advisory generation, and SSE event streaming. Linux transmits structured display state updates over the **Arduino UNO Q Router MessagePack-RPC** protocol (`/var/run/arduino-router.sock`) to the MCU (`Arduino_RouterBridge`), while Linux SSH terminals strictly display system diagnostic and operational logs.

---

## Hardware / MCU Architecture

```text
+---------------------------------------------------------------------------------------------------+
|                                        ARDUINO UNO Q                                              |
|                                                                                                   |
|  [ MPU / Linux Side ]                                                                             |
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

---

## Key Features & Compliance

1. **Physical LCD Display Execution**:
   - The MPI3501 GUI executes physically on the UNO Q MCU (`mcu_display.ino`).
   - Terminal outputs contain useful operational logs (`[HW]`, `[INTELLIGENCE]`, `[MCU]`).
   - Console `[TFT]` print statements have been removed from the physical display execution path.

2. **Authorized Display Driver**:
   - Built exclusively using the official `UNOQ_MPI3501` repository/library (`UNOQ_MPI3501.h` / `UNOQ_MPI3501.cpp`).
   - Operating in landscape 480×320 mode (ILI9486 over SPI).

3. **3-Screen Non-Blocking GUI Rotation**:
   - **Screen 0**: Environment Dashboard (AQI index box, PM1.0, PM2.5, PM10, Temperature, Humidity, PM progress bars).
   - **Screen 1**: Advisory (Severity badge, advice text, weather advice).
   - **Screen 2**: Actions (Numbered list of actionable recommendations).
   - Rotates screens every **10 seconds** using non-blocking `millis()` logic without `delay()`.

4. **Linux ↔ MCU Router MessagePack-RPC Transport**:
   - Communication uses MessagePack-RPC over `/var/run/arduino-router.sock`.
   - Requests are split into 3 modular sub-calls to keep each payload safely under the 1024-byte RPClite decoder limit:
     - `update_environment`: `[0, msgid, "update_environment", [aqi, pm1_0, pm2_5, pm10, temp, hum]]`
     - `update_advice`: `[0, msgid, "update_advice", [severity, advice, weather_advice]]`
     - `update_actions`: `[0, msgid, "update_actions", [actions_csv]]`
   - MCU registers all three RPC handlers via `Bridge.provide_safe(...)`.

5. **Dedicated Flashing & Simulation Scripts**:
   - `./flash_display.sh`: Compiles `Hardware/mcu_display` using `arduino-cli` and deploys it to the UNO Q MCU (`arduino:zephyr:unoq`). Fully portable across users.
   - `./run_display_simulation.sh`: Starts Python Intelligence Server, launches C++ synthetic hardware bridge, connects Router MessagePack-RPC bridge, and streams live data updates.

---

## Files Created & Modified

| File Path | Status | Description |
|---|---|---|
| [`flash_display.sh`](flash_display.sh) | **Modified** | Dynamic, portable MCU display flashing script |
| [`Hardware/mcu_display/mcu_display.ino`](Hardware/mcu_display/mcu_display.ino) | **Modified** | MCU sketch registering `Arduino_RouterBridge` RPC handler & driving MPI3501 GUI |
| [`Hardware/mcu_display/NavosEdgeGUI.h`](Hardware/mcu_display/NavosEdgeGUI.h) | **Created** | MCU display renderer header using `UNOQ_MPI3501` driver |
| [`Hardware/mcu_display/NavosEdgeGUI.cpp`](Hardware/mcu_display/NavosEdgeGUI.cpp) | **Created** | MCU display renderer implementation |
| [`Hardware/mcu_display/NavosEdgeState.h`](Hardware/mcu_display/NavosEdgeState.h) | **Created** | Shared MCU display state structure |
| [`Hardware/include/mcu_bridge.hpp`](Hardware/include/mcu_bridge.hpp) | **Modified** | Linux C++ MessagePack-RPC client transmitting state over `/var/run/arduino-router.sock` |
| [`Hardware/include/bridge.hpp`](Hardware/include/bridge.hpp) | **Modified** | Integrated `McuBridge` socket transport |
| [`Hardware/src/main.cpp`](Hardware/src/main.cpp) | **Modified** | Added `--test-rpc` standalone testing argument |
| [`run_display_simulation.sh`](run_display_simulation.sh) | **Modified** | Updated launcher script to run pipeline without repeated MCU flashing |

---

## How to Flash and Run

### Step 1: Flash the MCU Display Application
```bash
./flash_display.sh
```

### Step 2: Standalone MessagePack-RPC Test (Optional)
```bash
./Hardware/build/navos_hardware_bridge --test-rpc
```

### Step 3: Run the Simulation Pipeline
```bash
# Default mode (normal scenario, 60s sensor interval, 10s display rotation)
./run_display_simulation.sh

# Fast verification mode (traffic scenario, 5s sensor interval)
./run_display_simulation.sh --scenario traffic --interval 5
```
