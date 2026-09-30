# NavosEdge — Edge AI Environmental Monitoring & MCU Physical Display

NavosEdge is an offline-first edge artificial intelligence system running on the **Arduino UNO Q** paired with an **MPI3501 3.5" (480×320) TFT Display**.

It combines synthetic/physical environmental sensor telemetry, real-time machine learning inference, dynamic advisory generation, and hardware-accelerated physical TFT rendering.

---

## 🏛️ System Architecture

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

### Key Responsibilities
- **Linux (MPU)**: Sensor sampling, Python Intelligence Server (FastAPI + PyTorch/NumPy ML models + AQI & Advisory Engines), SSE control stream, and MessagePack-RPC socket client over `/var/run/arduino-router.sock`.
- **MCU (STM32U5)**: `Arduino_RouterBridge` RPC handler (`update_display`), `NavosEdgeGUI` renderer utilizing `UNOQ_MPI3501` hardware SPI display driver, and non-blocking 10-second 3-screen display rotation (`millis()`).

---

## 🚀 Quick Start Guide

### 1. Flash the MCU Display Application
Compile and flash the physical MPI3501 display firmware to the UNO Q MCU (`arduino:zephyr:unoq`):

```bash
./flash_display.sh
```

### 2. Standalone MessagePack-RPC Test (Optional)
Test the MPU ↔ MCU MessagePack-RPC communication without starting the Intelligence Server:

```bash
./Hardware/build/navos_hardware_bridge --test-rpc
```

### 3. Launch the Full Pipeline
Run the synthetic sensor pipeline, Intelligence Server, and RPC display bridge:

```bash
./run_display_simulation.sh --scenario traffic --interval 5
```

### 4. Check System Status
Check status of Intelligence Server, Router Socket, MCU RPC availability, and C++ Bridge:

```bash
./run_display_simulation.sh --status
```

---

## 📚 Documentation & Modules

- [UNO Q Deployment & Setup Guide](./UNO_Q_DEPLOYMENT.md) - Complete flashing and execution manual for user `arduino`.
- [Intelligence Server](./Intelligence/Server/README.md) - Python backend processing, model inference, and event streaming.
- [Phase 10 Display Integration](./phase10DisplayIntegration.md) - Detailed breakdown of physical MPI3501 integration.
- [Pipeline Flow Trace](./docs/NAVOSEDGE_RUNTIME_FLOW.md) - Runtime step-by-step pipeline trace.
