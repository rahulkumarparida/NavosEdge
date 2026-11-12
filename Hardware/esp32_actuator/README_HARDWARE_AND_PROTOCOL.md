# NavosEdge Phase 3 — NodeMCU ESP-32S V1.1 Hardware & Protocol Guide

## 1. Target Hardware & GPIO Selection

- **Controller Board:** NodeMCU ESP-32S V1.1 (Classic ESP32, USB-C, 3.3V GPIO logic)
- **Control Output Pin:** **`GPIO25` (`P25`)**
  - Selected because `GPIO25` is a clean, non-strapping general-purpose output pin on the Classic ESP32 (avoiding boot-strapping pins `GPIO0`, `GPIO2`, `GPIO5`, `GPIO12`, `GPIO15` and input-only pins `GPIO34–GPIO39`).
- **Controlled Load:** External DC fan switched via an NPN low-side transistor driver (transistor model and fan current rating not yet bench-verified).

---

## 2. Mandatory Electrical Isolation & Driver Circuit

> **WARNING:** Never connect the fan directly to `GPIO25` (3.3V max, ~12 mA safe continuous source current) or to the ESP32 board's 5V pin. The fan must always be powered through its external supply and NPN transistor driver.

Required NPN low-side switching circuit between `GPIO25` and the DC fan (`GPIO25 HIGH` = transistor ON = fan ON; `GPIO25 LOW` = transistor OFF = fan OFF):

```text
  External Fan Power Supply (+V)
         |
         +--------------------+
         |                    | (Cathode / Band)
      [ DC Fan ]          [ 1N5819 / 1N4007 Flyback Diode ]
         |                    | (Anode)
         +--------------------+
         |
         C (Collector)
  GPIO25 --[ Base Resistor ]--+-- B (Base)   NPN Transistor (Low-Side Switch)
                              |
                           [ 10k Ohm Pulldown (optional/recommended) ]
                              |
                              E (Emitter)
                              |
  ESP32 GND ------------------+------------ External Supply GND (Common Ground)
```

### Bench Verification Checklist (Required Before Setting `PHYSICAL_DRIVER_VERIFIED = true`)

1. Confirm the NPN transistor part number and verify its collector current (`Ic`), collector-emitter voltage (`Vce`), and base resistor value against the fan's steady-state and startup/stall current on a bench power supply.
2. Verify the external fan supply can deliver $\ge 2\times$ the fan startup current without brownout.
3. Confirm `GPIO25` remains `LOW` during ESP32 boot/reset and the transistor stays **OFF** at boot.
4. Confirm flyback diode polarity across the fan terminals (cathode to `+V`, anode to NPN collector).
5. Confirm common ground (`GND`) between the ESP32 and the external fan supply.
6. Only after passing steps 1–5, set `#define PHYSICAL_DRIVER_VERIFIED true` in `actuator_config.h` and re-flash.

---

## 3. Selected Communication Protocol: HTTP REST over Wi-Fi LAN

- **Why HTTP REST over Wi-Fi LAN:** The UNO Q Intelligence Server already runs FastAPI (`uvicorn` on port `8420`) with `httpx` installed, and the NodeMCU ESP-32S V1.1 includes `WiFi.h`, `WebServer.h`, and `HTTPClient.h` in the standard Arduino-ESP32 core—eliminating any external MQTT broker dependency on the edge node.

### 3.1 ESP32 $\rightarrow$ UNO Q Heartbeat & Registration

`POST http://<UNO_Q_HOST>:8420/api/v1/actuators/heartbeat`

```json
{
  "actuator_id": "esp32-fan-01",
  "associated_node_id": "node-01",
  "actuator_type": "ESP32_FAN_5V_UNFILTERED",
  "device_name": "NodeMCU ESP-32S V1.1 Fan Actuator",
  "ip_address": "192.168.1.142",
  "output_state": "SAFE_LOCKED_OFF",
  "physical_driver_verified": false,
  "gpio_pin": 25,
  "firmware_version": "navos-esp32-actuator-v1.0.0"
}
```

### 3.2 UNO Q $\rightarrow$ ESP32 Command Dispatch

`POST http://<ESP32_IP>:8080/actuator/command`

```json
{
  "command_id": "cmd-a1b2c3d4e5f6",
  "node_id": "node-01",
  "actuator_id": "esp32-fan-01",
  "command": "FAN_ON",
  "event_id": "emg-123456789abc",
  "control_mode": "DEMO_MODE",
  "lease_seconds": 60,
  "timestamp": "2026-11-12T18:30:00Z"
}
```

### 3.3 ESP32 $\rightarrow$ UNO Q Acknowledgement

```json
{
  "command_id": "cmd-a1b2c3d4e5f6",
  "actuator_id": "esp32-fan-01",
  "status": "ACKNOWLEDGED",
  "output_state": "SAFE_LOCKED_OFF",
  "physical_driver_verified": false,
  "uptime_ms": 48120,
  "error_details": "Hardware output locked OFF pending NPN transistor/current bench verification"
}
```

---

## 4. Environmental Safety Policy Distinction

- **`PROTECTION_MODE` (Default):** Real environmental monitoring mode. An `ESP32_FAN_5V_UNFILTERED` device is **never** automatically activated during particulate or gas pollution events. Automated `FAN_ON` is permitted only for actuators registered with a filtration-capable type (`ESP32_HEPA_PURIFIER`, `HEPA_PURIFIER`, `FILTRATION_UNIT`, `FILTERED_EXHAUST_FAN`).
- **`DEMO_MODE` / `MANUAL_OVERRIDE`:** Explicit operator/demonstration trigger via `POST /api/v1/actuators/{actuator_id}/command`, clearly logged as `DEMO_MODE` or `MANUAL_OVERRIDE` in `actuator_command_logs`.

