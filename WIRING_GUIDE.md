# NavosEdge — Complete Hardware & Sensor Wiring Guide

Comprehensive electrical wiring specification for the **NavosEdge** edge environmental monitoring station running on the **Arduino UNO Q** microcomputer.

---

## 1. System Overview & Architecture

The NavosEdge node integrates five environmental sensors and a 3.5" TFT display with the **Arduino UNO Q** dual-core architecture:
- **STM32U5 Microcontroller (MCU)**: Collects sensor telemetry via ADC, 1-Wire bit-banging, and hardware UART, driving the local SPI TFT display.
- **Linux Microprocessor (MPU)**: Ingests normalized JSON stream over USB Serial (`/dev/ttyACM0` @ 115200 baud) for AI inference, EPA/CPCB AQI computation, short-term forecasting, and Parent Manager reporting.

---

## 2. Master Pinout Reference Table

| Peripheral | Sensor Model | Target Pin (UNO Q) | Pin Mode / Interface | Signal Description | Power Requirement |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Combustible Gas / Smoke** | MQ2 | **A0** | Analog Input (ADC) | 0–5V analog voltage proportional to gas | 5V @ ~160mA (Heater) |
| **Carbon Monoxide (CO)** | MQ9 | **A1** | Analog Input (ADC) | 0–5V analog voltage proportional to CO | 5V @ ~170mA (Heater) |
| **Air Quality (NH3, NOx)** | MQ135 | **A2** | Analog Input (ADC) | 0–5V analog voltage for broad VOCs/CO2 | 5V @ ~160mA (Heater) |
| **Particulate Matter (TX)** | MPM10-CS | **D0 / RX** | Hardware `Serial1` (RX) | Sensor TX transmits 32-byte PMS binary frame | 5V @ ~100mA (Laser/Fan) |
| **Particulate Matter (RX)** | MPM10-CS | **D1 / TX** | Hardware `Serial1` (TX) | Optional: Sleep/Active commands | Shared with MPM10 VCC |
| **Temperature & Humidity** | DHT22 (AM2302) | **D8** | Digital Bidirectional | Single-wire bit-banged timing (10kΩ pull-up) | 3.3V or 5V @ ~2.5mA |
| **TFT Display — Data/Command** | MPI3501 (ILI9486) | **D2** | Digital Output | D/C register select pin for TFT controller | 3.3V / 5V |
| **TFT Display — Chip Select** | MPI3501 (ILI9486) | **D10** | Digital Output | SPI Chip Select (Active Low) | 3.3V / 5V |
| **TFT Display — SPI MOSI** | MPI3501 (ILI9486) | **D11** | Hardware SPI | Master Out Slave In | 3.3V / 5V |
| **TFT Display — SPI MISO** | MPI3501 (ILI9486) | **D12** | Hardware SPI | Master In Slave Out (Touch / Read) | 3.3V / 5V |
| **TFT Display — SPI SCK** | MPI3501 (ILI9486) | **D13** | Hardware SPI | Serial SPI Clock line | 3.3V / 5V |
| **Telemetry to Linux MPU** | Onboard Bridge | **USB** | CDC Serial @ 115200 | Transmits JSON lines to `/dev/ttyACM0` | Powered via board bus |

> [!IMPORTANT]
> **Why DHT22 is assigned to Pin D8 instead of Pin D2:**
> Pin **D2** is reserved by the hardware SPI TFT display shield for the **Data/Command (D/C)** line. Placing DHT22 on **D8** eliminates pin collision and guarantees clean bit-bang signal timings.
>
> **Why MPM10-CS uses Hardware `Serial1` (D0/D1) instead of `SoftwareSerial`:**
> The Arduino UNO Q MCU is a 32-bit ARM Cortex-M33 (STM32U5). `SoftwareSerial` cycle bit-banging is unreliable on high-clock ARM architectures and causes checksum drops. Pins **D0** and **D1** map to the STM32U5 hardware UART (`Serial1`), ensuring lossless 9600-baud frame capture.

---

## 3. Individual Sensor Wiring Diagrams

### 3.1 MQ2 — Flammable Gas & Smoke Sensor
```
      MQ2 Breakout Board               Arduino UNO Q
   ┌───────────────────────┐        ┌─────────────────┐
   │ VCC                   ├────────┤ 5V              │
   │ GND                   ├────────┤ GND             │
   │ AOUT (Analog Signal)  ├────────┤ A0 (ADC Input)  │
   │ DOUT (Digital Out)    │ (N/C)  │                 │
   └───────────────────────┘        └─────────────────┘
```
- **AOUT → A0**: Outputs continuous voltage 0.0V–5.0V (mapped to ADC 0–1023 in firmware).
- **DOUT**: Leave unconnected (digital comparator threshold is not used).
- **Warm-Up Note**: Requires a mandatory **30-second warm-up** period upon boot for the internal heater coil to stabilize.

---

### 3.2 MQ9 — Carbon Monoxide & Flammable Gas Sensor
```
      MQ9 Breakout Board               Arduino UNO Q
   ┌───────────────────────┐        ┌─────────────────┐
   │ VCC                   ├────────┤ 5V              │
   │ GND                   ├────────┤ GND             │
   │ AOUT (Analog Signal)  ├────────┤ A1 (ADC Input)  │
   │ DOUT (Digital Out)    │ (N/C)  │                 │
   └───────────────────────┘        └─────────────────┘
```
- **AOUT → A1**: ADC reading 0–1023.
- **DOUT**: Leave unconnected.
- **Warm-Up Note**: Requires a 30-second thermal stabilization cycle.

---

### 3.3 MQ135 — Hazardous Gas & Air Quality Sensor
```
     MQ135 Breakout Board              Arduino UNO Q
   ┌───────────────────────┐        ┌─────────────────┐
   │ VCC                   ├────────┤ 5V              │
   │ GND                   ├────────┤ GND             │
   │ AOUT (Analog Signal)  ├────────┤ A2 (ADC Input)  │
   │ DOUT (Digital Out)    │ (N/C)  │                 │
   └───────────────────────┘        └─────────────────┘
```
- **AOUT → A2**: Used by the GasNet machine learning model for VOC, NH3, benzene, and CO2 source discrimination.
- **DOUT**: Leave unconnected.

---

### 3.4 DHT22 / AM2302 — Temperature & Humidity Sensor
```
       DHT22 Sensor                    Arduino UNO Q
   ┌───────────────────────┐        ┌─────────────────┐
   │ Pin 1: VCC            ├────┬───┤ 5V (or 3.3V)    │
   │                       │    │   │                 │
   │ Pin 2: DATA           ├──┬─┴───┤ D8              │
   │                       │  │     │                 │
   │ Pin 3: N/C (No Conn)  │ [10kΩ] │                 │
   │                       │ Pullup │                 │
   │ Pin 4: GND            ├────────┤ GND             │
   └───────────────────────┘        └─────────────────┘
```
- **DATA → D8**: Connect DATA directly to digital pin **D8**.
- **Pull-Up Resistor**: Solder or breadboard a **10kΩ resistor** between **VCC** and **DATA** (amplify idle high state for bit-bang handshake).
- **Sampling Constraint**: The DHT22 capacitive element requires at least **2.0 seconds** between consecutive read queries (`DHT_MIN_INTERVAL 2000`).

---

### 3.5 MPM10-CS — Particulate Matter Sensor (PM1.0, PM2.5, PM10)
```
     MPM10-CS / PMS Sensor             Arduino UNO Q
   ┌───────────────────────┐        ┌─────────────────┐
   │ VCC (5V Power)        ├────────┤ 5V              │
   │ GND                   ├────────┤ GND             │
   │ TX (Data Output)      ├────────┤ D0 (Serial1 RX) │ <── Cross connection
   │ RX (Data Input)       ├────────┤ D1 (Serial1 TX) │ <── Optional / Control
   │ RESET / SET           │ (N/C)  │ (Internal Pull) │
   └───────────────────────┘        └─────────────────┘
```
- **TX → D0**: Sensor **TX** (Transmit) connects to Arduino **D0 / RX** (Receive).
- **RX → D1**: Sensor **RX** connects to Arduino **D1 / TX** (optional, enables standby commands).
- **Baud Rate**: Initialized at **9600 baud** in `navos_sensors.ino` via `Serial1.begin(9600)`.

---

## 4. Full System Interconnection Schematic

```
                                      ARDUINO UNO Q
                      ┌───────────────────────────────────────────┐
                      │                                           │
  MQ2 [AOUT] ─────────┤ A0                                     5V ├───┬───┬───┬───┬─── 5V VCC Rail
  MQ9 [AOUT] ─────────┤ A1                                    GND ├──┬┼───┼───┼───┼───┼── Common GND Rail
  MQ135 [AOUT] ───────┤ A2                                        │  ││   │   │   │   │
                      │ A3 (Available)                            │  ││   │   │   │   │
                      │ A4 (Available)                            │  ││   │   │   │   │
                      │ A5 (Available)                            │  ││   │   │   │   │
                      │                                           │  ││   │   │   │   │
  MPM10-CS [TX] ──────┤ D0 (Hardware Serial1 RX)                  │  ││   │   │   │   │
  MPM10-CS [RX] ──────┤ D1 (Hardware Serial1 TX)                  │  ││   │   │   │   │
  TFT Display [DC] ───┤ D2 (Reserved for Display Command/Data)    │  ││   │   │   │   │
                      │ D3..D7 (Available for Expansion)          │  ││   │   │   │   │
  DHT22 [DATA] ───────┤ D8 (Bit-Bang I/O)                         │  ││   │   │   │   │
                      │    │                                      │  ││   │   │   │   │
                      │    └── [ 10kΩ Pull-Up Resistor ] ─────────┼──┼┴───┼───┼───┼───┘
                      │                                           │  ││   │   │   │
  TFT Display [CS] ───┤ D10 (SPI Chip Select)                     │  ││   │   │   │
  TFT Display [MOSI] ─┤ D11 (SPI MOSI)                            │  ││   │   │   │
  TFT Display [MISO] ─┤ D12 (SPI MISO)                            │  ││   │   │   │
  TFT Display [SCK] ──┤ D13 (SPI Clock)                           │  ││   │   │   │
                      │                                           │  ││   │   │   │
                      │ USB-C Port ──► Linux MPU (/dev/ttyACM0)   │  ││   │   │   │
                      └───────────────────────────────────────────┘  ││   │   │   │
                                                                     ││   │   │   │
  Power Distribution Connections:                                    ││   │   │   │
    • MQ2   VCC & GND ───────────────────────────────────────────────┘│   │   │   │
    • MQ9   VCC & GND ────────────────────────────────────────────────┘   │   │   │
    • MQ135 VCC & GND ────────────────────────────────────────────────────┘   │   │
    • DHT22 VCC & GND ────────────────────────────────────────────────────────┘   │
    • MPM10 VCC & GND ────────────────────────────────────────────────────────────┘
```

---

## 5. Power Budget & Electrical Guidelines

> [!CAUTION]
> **Heater Current Warning**: 
> Gas sensors MQ2, MQ9, and MQ135 each contain internal heating elements consuming **150mA–180mA** at 5V. 
> - Total gas sensor current: ~**500mA**
> - MPM10-CS fan & laser diode: ~**100mA**
> - Arduino UNO Q base draw & TFT display: ~**250mA**
> - **Total Node Power Requirement**: **~850mA – 1.0A peak**
>
> **Recommendations:**
> 1. Use a high-quality **5V / 2.5A (or 3A)** USB-C power adapter connected directly to the Arduino UNO Q.
> 2. Avoid running sensors from unpowered USB hub ports or passive laptop ports that limit output to 500mA, as this causes voltage sag on the ADC lines and inaccurate MQ gas readings.
> 3. Connect sensor grounds directly to the common ground rail to prevent floating ADC offset errors.

---

## 6. Software & Firmware Configuration Alignment

All pins configured above match [`Hardware/firmware/navos_sensors.ino`](Hardware/firmware/navos_sensors.ino):

```cpp
// navos_sensors.ino Pin Definitions
#define MQ2_PIN    A0
#define MQ9_PIN    A1
#define MQ135_PIN  A2
#define DHT22_PIN  8

// MPM10-CS uses hardware Serial1 on pins D0 (RX) and D1 (TX)
#define pmsSerial  Serial1
```

### Serial Output Verification
Every 3 seconds (`SAMPLE_INTERVAL 3000`), the firmware emits a single-line JSON string over USB Serial at **115200 baud**:
```json
{"mq2":350,"mq9":280,"mq135":420,"t":28.50,"h":65.00,"pm1":12.0,"pm25":18.0,"pm10":25.0,"dht_ok":true,"pms_ok":true,"ok":true}
```

The Linux C++ hardware bridge reads this line via [`Hardware/include/serial_sensor.hpp`](Hardware/include/serial_sensor.hpp), validates the ranges via [`Hardware/include/sensor_validator.hpp`](Hardware/include/sensor_validator.hpp), and posts telemetry to the Intelligence Server.

---

## 7. Troubleshooting Checklist

| Symptom | Root Cause | Solution |
| :--- | :--- | :--- |
| `"dht_ok": false` in JSON | Missing pull-up resistor or wrong pin | Verify DATA is on **D8** and check the 10kΩ resistor between VCC and DATA. |
| `"pms_ok": false` in JSON | Reversed serial TX/RX lines | Swap sensor pins: Sensor **TX** must go to **D0 (RX)** and Sensor **RX** to **D1 (TX)**. |
| MQ values consistently 0 or 1023 | Bad connection or reversed VCC/GND | Verify analog wiring to **A0, A1, A2**. Ensure board ground is shared. |
| MQ values fluctuate wildly | Insufficient power supply current | Replace power source with a dedicated 5V 2.5A+ USB-C supply. |
| Display is blank / white screen | SPI conflict with sensor | Ensure DHT22 is moved to **D8**, leaving **D2** free for the TFT DC line. |
