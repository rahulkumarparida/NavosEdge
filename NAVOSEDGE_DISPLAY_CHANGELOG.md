# NavosEdge — Display UI Refinement, Hardware Pipeline & navos_v2 Compatibility Changelog

**Target Branch:** `navos_v2`  
**Base Commit:** `7162faf9a6c7a2fc92a98c7371b0de7eeb9c39c8`  
**Target Hardware:** Arduino UNO Q (Qualcomm QRB2210 ARM64 Linux + STM32U585 MCU)  
**Display:** 3.5″ MPI3501 (ILI9486) SPI TFT Display (480×320 Landscape)  
**Date:** November 2026  

---

## 1. Executive Summary

This changelog documents the complete investigation, root cause diagnosis, driver repair, GUI refinement, and verification of the physical display pipeline on the Arduino UNO Q.

The investigation addressed two interconnected failure modes:
1. **Pipeline & Data Flow Failures:** The physical display previously showed stale or frozen sensor data due to serial port contention on port 7500, unhandled router socket buffers, and missing state mutex protection in the hardware bridge.
2. **Visual & Rendering Defects:** Once live data flowed, the MPI3501 display exhibited severely truncated borders, broken card outlines, holes appearing in text and backgrounds, and leftover artifact pixels during badge updates.

All visual rendering defects, driver performance bottlenecks, and pipeline stability issues have been resolved. The changes maintain strict compatibility with the `navos_v2` branch, preserve chunked SPI transfer optimizations, ensure MCU and Linux display simulator parity, and pass all 286 automated tests across the NavosEdge platform without regression.

---

## 2. Root Cause Analysis & Technical Explanations

### 2.1 Driver Defect: Zephyr SPI Full-Duplex Overwrite Truncating Outlines
- **File:** `Hardware/third_party/UNOQ_MPI3501/src/UNOQ_MPI3501.cpp` (`fillRect()`)
- **Symptom:** Horizontal and vertical card borders, divider lines, and rectangular card fills longer than 64 pixels were abruptly cut off after exactly 64 pixels. A 468px top card border rendered only 64px, leaving the remaining 404px completely unrendered.
- **Root Cause:**
  In `fillRect()`, a 128-byte chunk buffer (`chunk_buf[128]`, holding 64 16-bit RGB565 pixels) was populated with the high and low color bytes once **before** entering the chunked transfer loop `while (remaining > 0)`.
  On Zephyr RTOS (the underlying OS for `arduino:zephyr:unoq`), `SPI.transfer(buf, count)` executes a full-duplex SPI transaction via the Zephyr kernel driver (`spi_transceive`). In full duplex, as bytes are clocked out via MOSI, incoming MISO bytes are simultaneously written back into the same buffer (`buf`).
  Consequently:
  - Iteration 1 clocked out 64 valid color pixels and filled `chunk_buf` with MISO bus noise (typically `0x00` or floating line bytes).
  - Iterations 2 through $N$ clocked out the corrupted MISO bytes rather than the color bytes. The ILI9486 received invalid RGB data, causing borders and fills to appear truncated or invisible after the 64th pixel.
- **Resolution:**
  Moved buffer population inside the `while (remaining > 0)` loop so every chunk—including partial final chunks—is explicitly repopulated with pristine `hi` and `lo` color bytes before invoking `SPI.transfer()`.

### 2.2 GUI Defect: Destructive Dust Particle Animation Punching Holes into UI
- **File:** `Hardware/mcu_display/NavosEdgeGUI.cpp` (`dustTick()`, `dustInit()`)
- **Symptom:** Small random gaps, notches, and holes appeared across card borders, text labels, and card background rectangles, worsening over time.
- **Root Cause:**
  `dustTick()` was called every 120ms to simulate drifting ambient dust particles based on current AQI. It tracked up to 30 active particles across coordinates $x \in [0, 479], y \in [34, 319]$. In each animation frame, it called `tftDrawPixel(_dustPrevX[i], _dustPrevY[i], GUI_BG_COLOR)` to erase each particle before redrawing it.
  Because the card rectangles and borders occupy nearly 100% of this screen coordinate area ($y=34$ to $y=319$), erasing particles with `GUI_BG_COLOR` (deep navy `#0B111E`) literally punched holes directly through card headers, white numeric values, and card borders.
- **Resolution:**
  Disabled particle spawning by setting `_dustCount = 0` in `dustInit()` and adding an immediate guard `if (_dustCount == 0) return;` in `dustTick()`. This eliminates all stray pixel overwriting while preserving the function signatures and loop timing.

### 2.3 Status Badge Transition Artifacts
- **File:** `Hardware/mcu_display/NavosEdgeGUI.cpp` (`updateScreen0_Dynamic()`)
- **Symptom:** When transitioning from "OFFLINE" to "LIVE", the rightmost portion of the "OFFLINE" badge remained visible as stale red pixels next to the green "LIVE" badge.
- **Root Cause:**
  The "OFFLINE" badge is 52px wide, whereas the "LIVE" badge is 34px wide. The dynamic partial update routine called `drawStatusBadge()` directly without clearing the badge's enclosing bounding box on `GUI_CARD_BG`, leaving an 18px artifact band.
- **Resolution:**
  Added `tftFillRect(415, 298, 59, 18, GUI_CARD_BG)` prior to `drawStatusBadge()` in `updateScreen0_Dynamic()` to cleanly wipe the bounding box before drawing the new status.

### 2.4 String Overflow & Text Clipping
- **File:** `Hardware/mcu_display/NavosEdgeGUI.cpp` & `UNOQ_MPI3501.cpp`
- **Symptom:** Long status advisory strings or unexpected sensor labels could overrun card borders and clip into adjacent cards.
- **Root Cause:**
  `drawAdaptiveString()` lacked a character truncation guard if a string exceeded `maxWidth` even after scaling down to font `size = 1`. In `UNOQ_MPI3501.cpp`, `drawChar()` and `drawString()` lacked defensive coordinate bounds checks.
- **Resolution:**
  Added string length truncation in `drawAdaptiveString()`: if `len > maxChars` at `size = 1`, the string is safely truncated to `maxChars`. In `UNOQ_MPI3501.cpp`, added bounds checks to `drawChar()` and `drawString()` to silently ignore characters outside display coordinates $[0, _width) \times [0, _height)$.

### 2.5 Serial Sensor Framing & Stale Frame Elimination
- **File:** `Hardware/include/serial_sensor.hpp` & `bridge.hpp`
- **Symptom:** Sensor readings appeared frozen or delayed; board boots emitted diagnostic logs that disrupted line parsing.
- **Root Cause:**
  When multiple sensor frames accumulated in the TCP/serial buffer, `read_line()` returned the oldest buffered line first, causing the display to lag real-time events. In addition, diagnostic messages like `[MCU]` or `NAVOSEDGE_MCU_TEST` were not filtered cleanly.
- **Resolution:**
  Enhanced `read_line()` in `serial_sensor.hpp` to process all buffered complete lines, filter diagnostic and status messages, and always yield the freshest complete JSON frame. In `bridge.hpp`, added validation to skip telemetry transmission if sensor readings report negative PM values (indicating read timeouts).

---

## 3. Inventory of Modified Files

| File | Subsystem | Nature of Change |
|---|---|---|
| `Hardware/third_party/UNOQ_MPI3501/src/UNOQ_MPI3501.cpp` | Display Driver | Fixed `fillRect` chunk buffer overwrite; optimized `drawBitmap` with `pushColors`; added bounds checks to `drawChar` and `drawString`. |
| `Hardware/third_party/UNOQ_MPI3501/src/UNOQ_MPI3501.h` | Display Driver | Synchronized method declarations. |
| `Hardware/mcu_display/NavosEdgeGUI.cpp` | MCU Firmware GUI | Disabled destructive dust particle erasing; added badge box clearing in dynamic update; added adaptive string length truncation. |
| `Hardware/mcu_display/NavosEdgeGUI.h` | MCU Firmware GUI | Synchronized method declarations. |
| `Hardware/display/gui/NavosEdgeGUI.cpp` | Linux GUI Sim | Synchronized identical GUI rendering improvements with MCU firmware. |
| `Hardware/display/gui/NavosEdgeGUI.h` | Linux GUI Sim | Synchronized method declarations. |
| `Hardware/mcu_display/mcu_display.ino` | MCU Application | Guarded diagnostic DHT22 dumps behind `NAVOS_DIAGNOSTIC_MODE`; retained last known valid environmental reading on transient 1-wire jitter; set `state.valid = true`. |
| `Hardware/include/bridge.hpp` | C++ Bridge | Dropped telemetry transmission on negative PM values to prevent stale/corrupt server updates. |
| `Hardware/include/constants.hpp` | C++ Bridge | Increased `DEFAULT_SERIAL_TIMEOUT_MS` from 5000 to 6000ms. |
| `Hardware/include/mcu_bridge.hpp` | C++ Bridge | Added thread-safe `std::mutex rpc_mutex_` to prevent data races on `latest_state_`. |
| `Hardware/include/serial_sensor.hpp` | C++ Bridge | Drained older buffered lines to deliver freshest frame; robustly filtered MCU logs and beacons. |
| `Hardware/config/hardware_config.json` | Configuration | Synchronized `serial_timeout_ms` to 6000ms. |
| `run_hardware.sh` | Deployment | Resolved port 7500 contention with `arduino-router-serial.service`; restored service on exit; fixed safe dict parsing for source prediction. |
| `.gitignore` | Repository Config | Configured `.gitignore` to track `Hardware/third_party/UNOQ_MPI3501/` while ignoring temporary build directories. |

---

## 4. Layout & Coordinate Verification (480×320 Grid)

The MPI3501 display operates in 480×320 landscape orientation. All UI cards adhere to the following coordinate boundaries:

```
+-------------------------------------------------------------------+ y=0
|  NAVOS // EDGE           [STATUS BADGE]        2026-11-07 15:45   | y=30
+-------------------------------------------------------------------+
|  CARD 1 (AQI)               |  CARD 2 (PARTICULATE MATTER)        | y=34
|  x=6, y=34, w=228, h=135    |  x=240, y=34, w=234, h=135          |
|  - AQI Category (size 2)    |  - PM2.5 / PM10 / PM1.0 bars        |
|  - AQI Numeric Value (sz 4) |  - Sub-index values                 |
|                             |                                     | y=169
+-----------------------------+-------------------------------------+
|  CARD 3 (GAS / VOC)         |  CARD 4 (ENVIRONMENT & SENSORS)     | y=175
|  x=6, y=175, w=228, h=137   |  x=240, y=175, w=234, h=137         |
|  - MQ-2, MQ-9, MQ-135 bars  |  - Temperature (sz 2)               |
|  - Gas voltages & ADC       |  - Humidity (sz 2)                  |
|                             |  - Sensor Status Badge (sz 1)       | y=312
+-----------------------------+-------------------------------------+ y=320
```

- **Margins:** 6px outer margins on left ($x=6$) and right ($x=474$).
- **Gutter:** 6px horizontal gutter between Card 1/3 and Card 2/4 ($x=234$ to $x=240$). 6px vertical gutter ($y=169$ to $y=175$).
- **Card Borders:** 1px borders rendered using `tftDrawRect(x, y, w, h, GUI_BORDER_COLOR)`—now rendered completely without truncation.
- **Screen Rotation:** Screen 0 (Environment Overview) rotates every 15s; Screens 1 (AQI Detail), 2 (Gas Detail), 3 (Forecast), and 4 (System Status) rotate every 15s.

---

## 5. Verification Evidence & Test Results

### 5.1 Physical MCU Deployment & Flashing
Firmware compiled and flashed directly onto the Arduino UNO Q STM32U585 MCU via OpenOCD / Linux GPIOD over ADB:
```
============================================================
 NavosEdge — MCU Physical Display Flasher
============================================================
  Current User:       arduino
  Arduino CLI Path:   /usr/bin/arduino-cli
  Target Board FQBN:  arduino:zephyr:unoq
  Sketch Location:    /home/arduino/navos_v2/NavosEdge/Hardware/mcu_display
============================================================
[FLASH] Compiling MCU display sketch...
Sketch uses 136184 bytes (17%) of program storage space. Maximum is 786432 bytes.
Global variables use 65324 bytes (24%) of dynamic memory, leaving 196820 bytes for local variables.
[FLASH] Deploying firmware to Arduino UNO Q MCU...
Open On-Chip Debugger 0.12.0+dev-ge6a2c12f4
Info : SWD DPIDR 0x0be12477
Info : [stm32u5.cpu] Cortex-M33 r0p4 processor detected
Info : flash size = 2048 KiB
Info : flash mode : dual-bank
============================================================
 [FLASH] SUCCESS: MCU display firmware flashed and active!
============================================================
```

### 5.2 C++ Hardware Bridge Test Suite
Executed natively on the Arduino UNO Q ARM64 Linux processor:
```
  [TEST] mock_sensor_valid_data ... PASS
  [TEST] mock_sensor_deterministic_variation ... PASS
  [TEST] config_loading ... PASS
  [TEST] payload_construction ... PASS
  [TEST] http_client_init ... PASS
  [TEST] repeated_sensor_reads_100 ... PASS
  [TEST] sse_parser_events ... PASS
  [TEST] sse_config_interval_update ... PASS
  [TEST] serial_sensor_frame_parsing ... PASS
  [TEST] serial_sensor_status_message ... PASS
  [TEST] serial_sensor_transport_detection ... PASS
  [TEST] serial_sensor_tcp_mock_stream ... PASS
  [TEST] serial_sensor_tcp_reconnect ... PASS
  [TEST] serial_sensor_error_invalidation ... PASS
  [TEST] tcp_router_garbage_and_beacons ... PASS
  [TEST] tcp_verbose_diagnostic_schema ... PASS
  [TEST] tcp_invalid_pm_values_rejection ... PASS
  [TEST] mcu_bridge_rpc_encoding ... PASS
  [TEST] mcu_bridge_concatenated_stream_framing ... PASS
  [TEST] mcu_bridge_partial_stream_framing ... PASS
────────────────────────────────────────
[NAVOS] Results: 21 passed, 0 failed
```

### 5.3 Desktop Display Simulator Build
Built cleanly with CMake on Debian Linux ARM64:
```
[ 25%] Building CXX object CMakeFiles/navos_display_sim.dir/gui/NavosEdgeGUI.cpp.o
[ 50%] Building CXX object CMakeFiles/navos_display_sim.dir/main.cpp.o
[ 75%] Linking CXX executable navos_display_sim
[100%] Built target navos_display_sim
```

### 5.4 Full Platform Regression Test Suite
All 286 automated tests across the three subsystem test suites pass with zero regressions:
```
============================================================
Simulation Test Suite:         64 passed in 1.07s
Manager Test Suite:            38 passed in 5.04s
Intelligence Server Suite:    184 passed in 14.35s
------------------------------------------------------------
TOTAL TESTS:                  286 passed, 0 failed
============================================================
```

---

## 6. Preflight & Hardware Startup Commands

When launching NavosEdge on the physical Arduino UNO Q:

1. **Preflight Health Check:**
   ```bash
   bash scripts/unoq_preflight.sh
   ```
2. **Flash MCU Display Firmware (if updating MCU binary):**
   ```bash
   bash flash_display.sh
   ```
3. **Launch Physical Hardware Mode:**
   ```bash
   bash run_hardware.sh --node-id uno-q-001 --skip-flash
   ```
   *Note:* The script automatically stops `arduino-router-serial.service` to free port 7500, verifies model artifacts, launches the Intelligence Server on port 8420, connects the hardware bridge to router proxy `127.0.0.1:7500`, and streams live SSE updates to the display.

4. **Run Display Simulator (Headless or SDL2 Desktop):**
   ```bash
   bash run_display_simulation.sh
   ```

---

## 7. Known Limitations & Operating Notes

1. **Indicative Particulate AQI:** As established in Phase 3, AQI calculations represent an indicative CPCB PM-based estimate (`CPCB_PM_ESTIMATE`) derived from PM2.5 and PM10 measurements; uncalibrated MQ sensor voltages do not substitute for certified reference gas analyzers.
2. **Minimum Data Sufficiency:** AQI reports remain provisional until 16 discrete hourly buckets within the rolling 24-hour window contain valid observations.
3. **Router Monitor Port 7500:** The Arduino router proxy port 7500 is shared. `run_hardware.sh` handles service arbitration automatically, but running manual `telnet 127.0.0.1 7500` sessions simultaneously will disconnect the hardware bridge.
4. **Display Particle Effects:** Dust particle simulation has been permanently turned off to preserve outline integrity. Any future particle effects must use a double-buffered display or an off-screen sprite layer rather than direct frame buffer pixel clearing.

