#pragma once
/**
 * NavosEdgeState.h — Shared application state for the display GUI.
 *
 * Consumed by the 4-screen GUI renderer (NavosEdgeGUI).
 * Populated from Intelligence Server's IntelligenceResult.
 */

#include "../platform.h"

#define NAVOS_MAX_ACTIONS 8
#define NAVOS_MAX_STRING_LEN 200
#define NAVOS_MAX_FORECAST_STEPS 4

struct NavosEdgeState {
    // --- Screen 1: Environment ---
    float aqi;
    float pm1_0;
    float pm2_5;
    float pm10;
    float temperature;
    float humidity;

    // --- Screen 2: Advisory & Actions ---
    char severity[32];               // "NORMAL", "MODERATE", "HIGH", "SEVERE", "CRITICAL"
    char advice[NAVOS_MAX_STRING_LEN]; // Primary advisory text
    char weather_advice[NAVOS_MAX_STRING_LEN]; // Retained for state compatibility
    char actions[NAVOS_MAX_ACTIONS][NAVOS_MAX_STRING_LEN];
    uint8_t action_count;

    // --- Screen 3: Forecast ---
    char forecast_trend[16];          // "RISING", "FALLING", "STABLE", "UNKNOWN"
    float forecast_confidence;        // 0.0 to 1.0 (-1.0 if unavailable)
    float forecast_pm2_5_pred[NAVOS_MAX_FORECAST_STEPS]; // Future PM2.5 horizon steps
    uint8_t forecast_pm2_5_count;     // Number of available forecast steps
    char forecast_outlook[NAVOS_MAX_STRING_LEN]; // Human-readable outlook summary

    // --- Screen 4: Intelligence ---
    char source_value[32];            // "TRAFFIC", "HEAVY_DUST", "CONSTRUCTION", "COMBUSTION", "INDUSTRIAL", "INDOOR_ACTIVITY", "UNKNOWN"
    float source_confidence;          // 0.0 to 1.0 (-1.0 if unavailable)
    char anomaly_status[32];          // "NORMAL", "ANOMALOUS", "CLEAN"
    float anomaly_score;              // Anomaly confidence/score (-1.0 if unavailable)

    // --- Metadata ---
    bool valid;                       // true once at least one successful fetch/update
    unsigned long last_update_ms;     // millis() timestamp of last update
};

/**
 * Initialize a NavosEdgeState to safe defaults.
 */
inline void navosStateInit(NavosEdgeState& s) {
    s.aqi = 0.0f;
    s.pm1_0 = 0.0f;
    s.pm2_5 = 0.0f;
    s.pm10 = 0.0f;
    s.temperature = 0.0f;
    s.humidity = 0.0f;

    s.severity[0] = '\0';
    s.advice[0] = '\0';
    s.weather_advice[0] = '\0';

    s.action_count = 0;
    for (uint8_t i = 0; i < NAVOS_MAX_ACTIONS; i++) {
        s.actions[i][0] = '\0';
    }

    strncpy(s.forecast_trend, "STABLE", sizeof(s.forecast_trend) - 1);
    s.forecast_trend[sizeof(s.forecast_trend) - 1] = '\0';
    s.forecast_confidence = -1.0f;
    s.forecast_pm2_5_count = 0;
    for (uint8_t i = 0; i < NAVOS_MAX_FORECAST_STEPS; i++) {
        s.forecast_pm2_5_pred[i] = 0.0f;
    }
    s.forecast_outlook[0] = '\0';

    strncpy(s.source_value, "UNKNOWN", sizeof(s.source_value) - 1);
    s.source_value[sizeof(s.source_value) - 1] = '\0';
    s.source_confidence = -1.0f;

    strncpy(s.anomaly_status, "NORMAL", sizeof(s.anomaly_status) - 1);
    s.anomaly_status[sizeof(s.anomaly_status) - 1] = '\0';
    s.anomaly_score = 0.0f;

    s.valid = false;
    s.last_update_ms = 0;
}

/**
 * Compare two states to detect if displayed data changed.
 */
inline bool navosStateChanged(const NavosEdgeState& a, const NavosEdgeState& b) {
    if (a.aqi != b.aqi) return true;
    if (a.pm1_0 != b.pm1_0) return true;
    if (a.pm2_5 != b.pm2_5) return true;
    if (a.pm10 != b.pm10) return true;
    if (a.temperature != b.temperature) return true;
    if (a.humidity != b.humidity) return true;
    if (strcmp(a.advice, b.advice) != 0) return true;
    if (strcmp(a.weather_advice, b.weather_advice) != 0) return true;
    if (strcmp(a.severity, b.severity) != 0) return true;
    if (a.action_count != b.action_count) return true;
    for (uint8_t i = 0; i < a.action_count && i < NAVOS_MAX_ACTIONS; i++) {
        if (strcmp(a.actions[i], b.actions[i]) != 0) return true;
    }
    if (strcmp(a.forecast_trend, b.forecast_trend) != 0) return true;
    if (a.forecast_confidence != b.forecast_confidence) return true;
    if (a.forecast_pm2_5_count != b.forecast_pm2_5_count) return true;
    for (uint8_t i = 0; i < a.forecast_pm2_5_count && i < NAVOS_MAX_FORECAST_STEPS; i++) {
        if (a.forecast_pm2_5_pred[i] != b.forecast_pm2_5_pred[i]) return true;
    }
    if (strcmp(a.forecast_outlook, b.forecast_outlook) != 0) return true;
    if (strcmp(a.source_value, b.source_value) != 0) return true;
    if (a.source_confidence != b.source_confidence) return true;
    if (strcmp(a.anomaly_status, b.anomaly_status) != 0) return true;
    return false;
}
