# Phase 10 — Synthetic Hardware → Intelligence → MPI3501 Physical Display Integration

## Executive Summary

Phase 10 establishes the end-to-end local hardware and desktop simulation pipeline for the **NavosEdge** edge node running on the **Arduino UNO Q** paired with the **MPI3501 3.5" (480×320) TFT Display**.

The display is structured into a clean, 4-screen visual storytelling flow: **Observe → Decide → Predict → Explain**.

The **NavosEdge GUI rendering runs directly on the Arduino UNO Q MCU (Zephyr / STM32U5)** via the `UNOQ_MPI3501` driver over hardware SPI (and in desktop simulation via `navos_display_sim`). Linux handles telemetry generation, HTTP data POST, machine learning inference, advisory generation, time-series forecasting, and SSE streaming. Structured display state updates are transmitted over the **Arduino UNO Q Router MessagePack-RPC** protocol (`/var/run/arduino-router.sock`) to the MCU (`Arduino_RouterBridge`).

---

## Final 4-Screen GUI Architecture

The display application automatically cycles non-blockingly across 4 screens using `millis()`:

```text
[Screen 1: ENVIRONMENT] (15s)  --->  [Screen 2: ADVISORY] (10s)
          ^                                        |
          |                                        v
[Screen 4: INTELLIGENCE] (10s) <---  [Screen 3: FORECAST] (10s)
```

### Screen Breakdown & Narrative Flow

| Screen | Name | Duration | Story Role | Display Contents |
|---|---|---|---|---|
| **Screen 1** | **ENVIRONMENT** | **15 seconds** | **Observe** | • Large AQI card with color severity coding (`Good`, `Moderate`, `Unhealthy`, `Hazardous`)<br>• Particulate Matter cards ($\text{PM}_{1.0}$, $\text{PM}_{2.5}$, $\text{PM}_{10}$ in $\mu\text{g/m}^3$)<br>• Ambient Temperature (°C) and Humidity (%)<br>• Real-time `[LIVE]` / `[OFFLINE]` system connection status |
| **Screen 2** | **ADVISORY** | **10 seconds** | **Decide** | • Severity Badge (`NORMAL`, `MODERATE`, `HIGH`, `SEVERE`, `CRITICAL`)<br>• Primary Advisory Outlook text block (`state.advice`)<br>• 3–4 Actionable Bullet Recommendations (`state.actions`)<br>• Weather text is hidden on this screen to focus on local pollution decisions |
| **Screen 3** | **FORECAST** | **10 seconds** | **Predict** | • Current $\text{PM}_{2.5}$ value vs Forecast Trend (`RISING ↑`, `FALLING ↓`, `STABLE →`)<br>• Model Confidence percentage<br>• Visual step horizon flow cards ($\text{NOW} \rightarrow +15\text{m} \rightarrow +30\text{m} \rightarrow +60\text{m}$)<br>• Human-readable forecast outlook summary |
| **Screen 4** | **INTELLIGENCE** | **10 seconds** | **Explain** | • 4 Quad Conclusion Cards explaining **WHY** the system reached its decision:<br>  1. **Anomaly Detection**: Status (`NORMAL` / `ANOMALOUS`) & confidence<br>  2. **Pollution Source**: ML classified source (`TRAFFIC`, `DUST`, `CONSTRUCTION`, `COMBUSTION`, `INDUSTRIAL`, `INDOOR_ACTIVITY`) & confidence<br>  3. **Air Quality Index**: Calculated AQI score & EPA breakpoint category<br>  4. **Time-Series Forecast**: AR(p) model trend & horizon |

---

## Hardware / MCU Architecture & Data Flow

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
|                                | NavosEdgeGUI (C++)| (4-screen non-blocking rotation)             |
|                                +-------------------+                                              |
|                                          | Hardware SPI (MOSI=D11, SCK=D13, CS=D10, DC=D2)        |
|                                          v                                                        |
|                              +-----------------------+                                            |
|                              | MPI3501 3.5" Display  | (Physical 480x320 ILI9486 Display)         |
|                              +-----------------------+                                            |
+---------------------------------------------------------------------------------------------------+
```

---

## Router MessagePack-RPC Specification

Communication from Linux MPU to MCU uses **4 lightweight, non-blocking MessagePack-RPC methods** over `/var/run/arduino-router.sock`:

1. `update_environment(aqi, pm1_0, pm2_5, pm10, temp, hum)`
2. `update_advice(severity, advice, weather_advice)`
3. `update_actions(actions_csv)`
4. `update_predictions(source, source_conf, forecast_trend, forecast_conf, pm25_pred0, pm25_pred1, anomaly_status)`

Each message payload is safely constrained under 350 bytes, far below the Arduino RPClite 1024-byte buffer threshold.

---

## File Registry

| File Path | Status | Description |
|---|---|---|
| [`Hardware/mcu_display/NavosEdgeState.h`](Hardware/mcu_display/NavosEdgeState.h) | **Updated** | Shared state struct supporting 4-screen intelligence payload |
| [`Hardware/display/state/NavosEdgeState.h`](Hardware/display/state/NavosEdgeState.h) | **Updated** | Desktop simulation state struct |
| [`Hardware/mcu_display/NavosEdgeGUI.h`](Hardware/mcu_display/NavosEdgeGUI.h) | **Updated** | 4-screen MCU renderer header with non-blocking timing |
| [`Hardware/mcu_display/NavosEdgeGUI.cpp`](Hardware/mcu_display/NavosEdgeGUI.cpp) | **Updated** | 4-screen MCU renderer implementation (Observe → Decide → Predict → Explain) |
| [`Hardware/display/gui/NavosEdgeGUI.h`](Hardware/display/gui/NavosEdgeGUI.h) | **Updated** | Desktop simulation GUI header |
| [`Hardware/display/gui/NavosEdgeGUI.cpp`](Hardware/display/gui/NavosEdgeGUI.cpp) | **Updated** | Desktop simulation GUI implementation |
| [`Hardware/mcu_display/mcu_display.ino`](Hardware/mcu_display/mcu_display.ino) | **Updated** | Arduino sketch with `update_predictions` RPC handler |
| [`Hardware/include/mcu_bridge.hpp`](Hardware/include/mcu_bridge.hpp) | **Updated** | Linux C++ socket client sending environment, advisory, actions, and predictions RPCs |
| [`Hardware/include/bridge.hpp`](Hardware/include/bridge.hpp) | **Updated** | Parses predictions object from Intelligence Server SSE / HTTP response |
| [`Hardware/display/network/ServerClient.cpp`](Hardware/display/network/ServerClient.cpp) | **Updated** | Desktop simulation HTTP parser for prediction objects |
| [`flash_display.sh`](flash_display.sh) | **Maintained** | Portable Arduino CLI firmware build & upload script |
| [`run_display_simulation.sh`](run_display_simulation.sh) | **Maintained** | Pipeline execution & simulation launcher |

---

## How to Build, Upload & Run

### 1. Flash the MCU Display Application to Arduino UNO Q
```bash
./flash_display.sh
```

### 2. Build C++ Desktop Simulation / Hardware Targets
```bash
cd Hardware/build
cmake .. -DCMAKE_BUILD_TYPE=Release
make navos_hardware_bridge -j$(nproc)

cd ../display/build
cmake .. -DCMAKE_BUILD_TYPE=Release
make navos_display_sim -j$(nproc)
```

### 3. Run the End-to-End Simulation Pipeline
```bash
# Default pipeline (normal scenario, 60s sensor interval)
./run_display_simulation.sh

# Fast verification mode (traffic scenario, 5s sensor update)
./run_display_simulation.sh --scenario traffic --interval 5
```
