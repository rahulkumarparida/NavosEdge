#pragma once

// ============================================================================
// NavosEdge — NodeMCU ESP-32S V1.1 Alert Light & Buzzer Configuration
// ============================================================================

// Target Hardware: NodeMCU ESP-32S V1.1 (Classic ESP32, USB-C, 3.3V GPIO logic)
// Physical Pin Assignments:
//   - ESP32 GPIO25 -> Alert LED / Bulb (active-HIGH by default; set false for active-LOW relay)
//   - UNO Q Pin D9  -> Primary Synchronized Alarm Buzzer (configured in Hardware/mcu_display/mcu_display.ino)
//   - ESP32 GPIO26 -> Optional auxiliary buzzer pin on ESP32
#define ALERT_LIGHT_PIN 25
#define ALERT_LIGHT_GPIO ALERT_LIGHT_PIN
#define ALERT_LIGHT_ACTIVE_HIGH true

#define ALERT_BUZZER_ENABLED true
#define ALERT_BUZZER_PIN 26
#define ALERT_BUZZER_GPIO ALERT_BUZZER_PIN
#define ALERT_BUZZER_ACTIVE_HIGH true
#define ALERT_BUZZER_PASSIVE_TONE true  // Set true for passive 2-pin piezo buzzer using tone()
#define ALERT_BUZZER_TONE_HZ 2400

// GPIO25 (bulb) + GPIO26 (buzzer) armed; both are initialized OFF at top of setup() before Serial/Wi-Fi.
#define PHYSICAL_DRIVER_VERIFIED true

// Wi-Fi Credentials (update before flashing)
// CENTRAL LIBRARY BUILDING -2ND FL / Heheheheheh
// nopassword@ / 0987654321
#define WIFI_SSID "Heheheheheh"
#define WIFI_PASSWORD "0987654321"

// UNO Q Intelligence Server endpoint
#define UNOQ_SERVER_HOST "10.81.210.140"
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
