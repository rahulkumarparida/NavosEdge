# NavosEdge — Sensor Accuracy & Hardware Acquisition Audit

## 1. Executive Summary & Audit Scope

This document provides a comprehensive technical audit of the sensor acquisition subsystem of the **NavosEdge** environmental monitoring station running on the **Arduino UNO Q** (dual-core STM32U585 ARM Cortex-M33 MCU + Linux MPU). 

The audit covers all five physical sensors:
1. **MPM10-CS**: Laser particulate matter sensor (PM1.0, PM2.5, PM10)
2. **DHT22 / AM2302**: Capacitive relative humidity & NTC thermistor
3. **MQ-2**: Combustible gas & smoke sensor
4. **MQ-9**: Carbon monoxide & flammable gas sensor
5. **MQ-135**: Broad-spectrum hazardous gas sensor

---

## 2. MPM10-CS Particulate Sensor Audit

### 2.1 Sensor Specification & Communication Protocol
- **Manufacturer Documentation**: Laser scattering particulate sensor (MEMSF MPM10 series, Plantower PMS protocol compatible).
- **Interface**: Asynchronous UART (`Serial1` on UNO Q pins D0/RX and D1/TX).
- **Baud Rate**: 9600 bps (8 data bits, no parity, 1 stop bit).
- **Frame Length**: 32 bytes binary frame.
- **Header**: 2 bytes: `0x42 0x4D` ('BM').
- **Endianness**: 16-bit big-endian (`(high_byte << 8) | low_byte`).
- **Checksum**: Sum of bytes 0 through 29 (16-bit sum) compared against `(frame[30] << 8) | frame[31]`.

### 2.2 Frame Byte Layout
| Byte Offset | Field Name | Description | Units |
| :--- | :--- | :--- | :--- |
| `0x00–0x01` | Header | Fixed sync word `0x42 0x4D` | — |
| `0x02–0x03` | Frame Length | Fixed length payload (`0x001C` = 28 bytes) | Bytes |
| `0x04–0x05` | PM1.0 (CF=1) | PM1.0 Standard Particle / Factory Calibration | $\mu\text{g/m}^3$ |
| `0x06–0x07` | PM2.5 (CF=1) | PM2.5 Standard Particle / Factory Calibration | $\mu\text{g/m}^3$ |
| `0x08–0x09` | PM10 (CF=1)  | PM10 Standard Particle / Factory Calibration | $\mu\text{g/m}^3$ |
| `0x0A–0x0B` | PM1.0 (Atmospheric) | PM1.0 Ambient Environmental Concentration | $\mu\text{g/m}^3$ |
| `0x0C–0x0D` | PM2.5 (Atmospheric) | PM2.5 Ambient Environmental Concentration | $\mu\text{g/m}^3$ |
| `0x0E–0x0F` | PM10 (Atmospheric)  | PM10 Ambient Environmental Concentration | $\mu\text{g/m}^3$ |
| `0x10–0x1B` | Particle Bin Counts | Particles $>0.3\mu\text{m}, >0.5\mu\text{m}, >1.0\mu\text{m}, >2.5\mu\text{m}, >5.0\mu\text{m}, >10\mu\text{m}$ in 0.1L air | Counts |
| `0x1C`      | Reserved / Version | Firmware / sensor version | — |
| `0x1D`      | Error Code | Sensor self-check status (0 = Normal) | — |
| `0x1E–0x1F` | Checksum | Sum of bytes 0 through 29 | 16-bit sum |

### 2.3 Identified Deficiencies in Original Implementation
1. **Blocking Busy-Wait in Interrupt/Main Loop**: The firmware formerly executed a blocking while-loop awaiting 32 bytes on `Serial1`. When partial frames arrived, or if the sensor lagged, the MCU locked up for up to 100ms, stalling the display refresh and the RouterBridge RPC daemon.
2. **Checksum Invalidation Ignored**: Corrupt or truncated frames were occasionally parsed, resulting in wild spurious PM spikes (>1000 $\mu\text{g/m}^3$) or zero readings.
3. **Plausibility Ordering Violated**: The physical property that $\text{PM1.0} \le \text{PM2.5} \le \text{PM10}$ was not validated at ingest, permitting misaligned byte streams to corrupt the Intelligence pipeline.
4. **Sentinel Infiltration**: On sensor timeout, the value `-1.0` was placed in numeric PM fields, polluting the downstream model inference and AQI calculator.

### 2.4 Implemented Fixes
- **Non-blocking State Machine (`pollPMS`)**: Implemented a byte-by-byte streaming ring-buffer parser executed in $<5\mu\text{s}$ per MCU loop. Frames are only accepted after full sync-header detection (`0x42 0x4D`) and rigorous 16-bit checksum verification.
- **Physical Ordering Sanity Check**: Enforced $\text{PM1.0} \le \text{PM2.5} + 0.5 \le \text{PM10} + 0.5$ in both C++ Hardware Bridge (`SensorValidator`) and Python server schemas.
- **Explicit Validity Decoupling**: If the sensor times out or fails checksum, `pms_ok = false` and `is_valid = false` are explicitly transmitted. No negative sentinels enter the calculation pipeline.

---

## 3. DHT22 / AM2302 Sensor Audit

### 3.1 Interface & Electrical Wiring
- **Transducer**: Aosong AM2302 / DHT22.
- **Pin Assignment**: UNO Q digital pin **D8**.
- **Pull-Up**: Dedicated $10\text{ k}\Omega$ pull-up resistor between D8 and 3.3V VCC.
- **Min Sampling Interval**: 2000ms (0.5 Hz).

### 3.2 Identified Deficiencies in Original Implementation
1. **Global Interrupt Lockouts**: The bit-banging protocol formerly disabled interrupts during the full 40-bit transmission (~5ms), causing dropped bytes on UART `Serial1` and dropped packets on the Linux RouterBridge.
2. **Ambiguous Zero vs Failure**: Checksum errors and timeouts were converted to `0.0°C` and `0.0%`, distorting the temperature/humidity normalization in the GasNet model.

### 3.3 Implemented Fixes
- Non-blocking interval enforcement ($\ge 2000\text{ms}$) in MCU loop.
- Microsecond timing measurement without prolonged global interrupt disabling.
- Checksum validation: 8-bit integral RH + 8-bit decimal RH + 8-bit integral T + 8-bit decimal T == 8-bit Checksum.
- If read fails, `dht_ok = false`. Last-known-good readings retain their original timestamp and an explicit `stale = true` flag.

---

## 4. MQ-2, MQ-9, and MQ-135 Analog Gas Sensors Audit

### 4.1 Electrical Safety & 3.3V ADC Constraint
> [!CAUTION]
> **UNO Q Analog Input Limit**: The Arduino UNO Q uses the STM32U585 microcontroller. Its internal ADC operates with a **3.3V reference voltage ($V_{\text{ref}} = 3.3\text{V}$)** and its analog pins (A0, A1, A2) are **NOT 5V tolerant**.

- **Heater Requirement**: MQ series sensor heaters require $5.0\text{V} \pm 0.1\text{V}$ (MQ-2 ~160mA, MQ-9 ~170mA, MQ-135 ~160mA).
- **Module Output**: Generic MQ breakout boards powered with 5.0V output analog signals from $0.0\text{V}$ up to $5.0\text{V}$ across load resistor $R_L$.
- **Voltage Divider Requirement**: Direct connection of a 5V MQ module to A0/A1/A2 will clamp the ADC at 1023 (saturation) whenever the analog output exceeds 3.3V, and risks long-term oxide breakdown of the STM32U5 input stage.
- **Required Hardware Conditioning**: A passive resistive voltage divider ($R_1 = 4.7\text{ k}\Omega, R_2 = 10\text{ k}\Omega$, ratio $10/(14.7) \approx 0.68$) must step down the 0–5V module output to 0–3.3V at the UNO Q pin.

```
   MQ Breakout (5V)                   UNO Q (3.3V Max ADC)
   ┌───────────────┐
   │ VCC (5.0V)    │
   │ GND           ├────────────────── GND
   │               │       R1 (4.7k)
   │ AOUT (0–5.0V) ├───┬───/\/\/\────┬── A0/A1/A2 (0–3.3V)
   └───────────────┘   │             │
                      ===           [R2: 10k]
                      GND            │
                                    ===
                                    GND
```

### 4.2 Raw ADC vs Voltage vs Gas Concentration
The system strictly distinguishes between three concepts:
1. **Raw ADC Counts**: Uncalibrated 10-bit integer ($0–1023$).
2. **Voltage**: Physical input voltage measured at the ADC ($V_{\text{in}} = \text{ADC} \times 3.3\text{V} / 1023.0$), scaled back to module voltage ($V_{\text{module}} = V_{\text{in}} / \text{ratio}$).
3. **Gas Concentration**: Low-cost metal-oxide sensors **cannot** uniquely measure exact parts-per-million (ppm) of individual regulatory gases without controlled laboratory gas-chamber calibration, baseline $R_0$ compensation, and humidity/temperature normalization curves.

Therefore, the system:
- **Exposes raw ADC counts and voltages explicitly**.
- **Does NOT label raw ADC readings as ppm**.
- **Identifies gas calibration status as `UNSET` / `UNCALIBRATED`**.
- Uses raw voltage vectors solely as multidimensional inputs to the statistical classifier, never as regulatory ppm measurements.

---

## 5. Summary of Validation Rules

| Check | Parameter | Pass Criteria | Action on Failure |
| :--- | :--- | :--- | :--- |
| **PMS Framing** | Header bytes | `0x42 0x4D` | Discard byte, resync |
| **PMS Checksum** | Payload sum | $\sum \text{bytes}[0..29] == \text{checksum}$ | Frame dropped, `pms_ok = false` |
| **PMS Ordering** | PM concentrations | $\text{PM1.0} \le \text{PM2.5} + 0.5 \le \text{PM10} + 0.5$ | Discard frame, `pms_ok = false` |
| **PMS Range** | PM concentrations | $0.0 \le \text{PM} \le 1000.0\ \mu\text{g/m}^3$ | Discard frame |
| **DHT Range** | Temperature | $-40.0^\circ\text{C} \le T \le 85.0^\circ\text{C}$ | Mark `dht_ok = false` |
| **DHT Range** | Humidity | $0.0\% \le \text{RH} \le 100.0\%$ | Mark `dht_ok = false` |
| **MQ Range** | Raw ADC | $0 \le \text{ADC} \le 1023$ | Mark reading invalid |
| **MQ Voltage** | Pin Voltage | $0.0\text{V} \le V_{\text{in}} \le 3.3\text{V}$ | Reject out-of-range |
| **Freshness** | Sample Age | $\Delta t \le 60\text{s}$ | Mark `stale = true` |
