#pragma once

/**
 * constants.hpp — Centralized Hardware module constants for NavosEdge C++ Bridge.
 * Single source of truth for configuration defaults, physical sensor bounds, and hardware specs.
 */

#include <string>

namespace navos {
namespace constants {

// Default Network & Node Settings
inline const std::string DEFAULT_SERVER_URL               = "http://localhost:8420";
inline const std::string DEFAULT_NODE_ID                  = "uno-q-001";
constexpr int DEFAULT_SAMPLING_INTERVAL_SECONDS           = 60;
constexpr int DEFAULT_SENSOR_WARMUP_SECONDS               = 30;
constexpr int DEFAULT_RETRY_MAX_ATTEMPTS               = 5;
constexpr int DEFAULT_RETRY_BASE_DELAY_SECONDS         = 2;
constexpr int DEFAULT_HTTP_TIMEOUT_SECONDS             = 10;
constexpr bool DEFAULT_MOCK_MODE                          = true;
inline const std::string DEFAULT_SCENARIO                 = "normal";


// Sensor Transport Defaults (Arduino UNO Q Router Monitor Proxy / Serial Fallback)
inline const std::string DEFAULT_SERIAL_PORT              = "127.0.0.1:7500";
inline const std::string DEFAULT_ROUTER_MONITOR_HOST      = "127.0.0.1";
constexpr int DEFAULT_ROUTER_MONITOR_PORT                 = 7500;
constexpr int DEFAULT_SERIAL_BAUD                         = 115200;
constexpr int DEFAULT_SERIAL_TIMEOUT_MS                   = 5000;
constexpr int SERIAL_BUFFER_SIZE                          = 512;

// Physical Sensor Bounds (10-bit ADC, 5V reference)
constexpr int ADC_MIN                                     = 0;
constexpr int ADC_MAX                                     = 1023;
constexpr double VOLTAGE_MIN                              = 0.0;
constexpr double VOLTAGE_MAX                              = 5.0;
constexpr double ADC_VREF                                 = 5.0;

// DHT22 Temperature & Humidity Limits
constexpr double TEMP_MIN                                 = -40.0;
constexpr double TEMP_MAX                                 = 85.0;
constexpr double HUM_MIN                                  = 0.0;
constexpr double HUM_MAX                                  = 100.0;

// Particulate Matter Limits & Tolerances
constexpr double PM_MAX                                   = 1000.0;
constexpr double PM_TOLERANCE                             = 0.5;

// MCU Display Defaults
constexpr int DISPLAY_BAUD_RATE                           = 115200;
constexpr int DISPLAY_REFRESH_FPS                         = 30;

} // namespace constants
} // namespace navos
