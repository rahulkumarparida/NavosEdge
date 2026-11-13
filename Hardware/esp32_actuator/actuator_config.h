#pragma once

// ============================================================================
// NavosEdge Phase 3 — NodeMCU ESP-32S V1.1 Actuator Configuration
// ============================================================================

// Target Hardware: NodeMCU ESP-32S V1.1 (Classic ESP32, USB-C, 3.3V GPIO logic)
// Safe non-strapping GPIO pin for external NPN low-side transistor driver:
#define FAN_PIN 25
#define FAN_CONTROL_GPIO FAN_PIN

// CRITICAL HARDWARE SAFETY INTERLOCK:
// Leave `PHYSICAL_DRIVER_VERIFIED` as `false` until you have:
//   1. Measured the DC fan steady-state and stall/inrush current on a bench PSU
//      and confirmed the NPN transistor rating (Ic, Vce, hFE, base resistor).
//   2. Verified the external NPN low-side transistor driver circuit:
//      GPIO25 -> base resistor -> NPN base, NPN emitter -> GND,
//      NPN collector -> fan negative terminal, fan positive -> external supply,
//      flyback diode across the fan terminals, and common GND with ESP32.
//   3. Confirmed the fan is NEVER connected directly to GPIO25 or ESP32 5V pin.
//
// While `false`, GPIO25 remains hardware-locked LOW (OFF) and the firmware
// reports `output_state: "SAFE_LOCKED_OFF"`.
#define PHYSICAL_DRIVER_VERIFIED false

// Wi-Fi Credentials (update before flashing)
//  CENTRAL LIBRARY BUILDING -2ND FL
// nopassword@
#define WIFI_SSID "NavosEdge_LAN"
#define WIFI_PASSWORD "CHANGE_ME"

// UNO Q Intelligence Server endpoint
#define UNOQ_SERVER_HOST "10.245.249.140"
#define UNOQ_SERVER_PORT 8420

// Device Identity (must match EmergencyDatabase registration)
#define ACTUATOR_ID "esp32-fan-01"
#define ASSOCIATED_NODE_ID "node-01"
#define ACTUATOR_TYPE "ESP32_FAN_5V_UNFILTERED"
#define ACTUATOR_DEVICE_NAME "NodeMCU ESP-32S V1.1 Fan Actuator"
#define FIRMWARE_VERSION "navos-esp32-actuator-v1.0.0"

// Local HTTP server port on the ESP32
#define ACTUATOR_HTTP_PORT 8080

// Timing & Watchdog Defaults
#define HEARTBEAT_INTERVAL_MS 15000UL
#define WIFI_RECONNECT_INTERVAL_MS 10000UL
#define DEFAULT_LEASE_SECONDS 60UL
#define COMMAND_HISTORY_RING_SIZE 16

