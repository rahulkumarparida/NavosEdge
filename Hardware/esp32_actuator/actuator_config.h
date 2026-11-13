#pragma once

// ============================================================================
// NavosEdge — NodeMCU ESP-32S V1.1 Alert Light Configuration
// ============================================================================

// Target Hardware: NodeMCU ESP-32S V1.1 (Classic ESP32, USB-C, 3.3V GPIO logic)
// Safe non-strapping GPIO pin driving the 3.3V indicator LED + series resistor to GND:
#define ALERT_LIGHT_PIN 25
#define ALERT_LIGHT_GPIO ALERT_LIGHT_PIN

// GPIO25 drives a low-current 3.3V LED + series resistor (active-HIGH).
// Hardware safety: initialized LOW at the very top of setup() before Serial or Wi-Fi.
#define PHYSICAL_DRIVER_VERIFIED true

// Wi-Fi Credentials (update before flashing)
// CENTRAL LIBRARY BUILDING -2ND FL / Heheheheheh
// nopassword@ / 0987654321
#define WIFI_SSID "NavosEdge_LAN"
#define WIFI_PASSWORD "CHANGE_ME"

// UNO Q Intelligence Server endpoint
#define UNOQ_SERVER_HOST "10.103.68.140"
#define UNOQ_SERVER_PORT 8420

// Device Identity (matches UNO Q EmergencyDatabase ESP32_ALERT_LIGHT registration)
#define ACTUATOR_ID "esp32-light-01"
#define ASSOCIATED_NODE_ID "uno-q-001"
#define ACTUATOR_TYPE "ESP32_ALERT_LIGHT"
#define ACTUATOR_DEVICE_NAME "NodeMCU ESP-32S V1.1 Alert Light"
#define FIRMWARE_VERSION "navos-esp32-alert-light-v1.1.0"

// Local HTTP server port on the ESP32
#define ACTUATOR_HTTP_PORT 8080

// Timing & Communication Watchdog Defaults
#define HEARTBEAT_INTERVAL_MS 15000UL
#define WIFI_RECONNECT_INTERVAL_MS 10000UL
#define HTTP_TIMEOUT_MS 5000
#define STALE_COMM_TIMEOUT_MS 75000UL
#define COMMAND_HISTORY_RING_SIZE 16
