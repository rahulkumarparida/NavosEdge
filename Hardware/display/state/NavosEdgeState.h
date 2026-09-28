#pragma once
/**
 * NavosEdgeState.h — Shared application state for the display GUI.
 *
 * This structure is populated by the network layer (ServerClient)
 * and consumed by the GUI renderer (NavosEdgeGUI). It mirrors
 * the fields from the Intelligence Server's IntelligenceResult.
 */

#include "../platform.h"

// Maximum number of action strings the display can hold.
// Using fixed arrays to avoid dynamic allocation on UNO Q.
#define NAVOS_MAX_ACTIONS 8
#define NAVOS_MAX_STRING_LEN 200

struct NavosEdgeState {
    // --- Screen 1: Environment ---
    float aqi;
    float pm1_0;
    float pm2_5;
    float pm10;
    float temperature;
    float humidity;

    // --- Screen 2: Advice ---
    char severity[32];
    char advice[NAVOS_MAX_STRING_LEN];
    char weather_advice[NAVOS_MAX_STRING_LEN];

    // --- Screen 3: Actions ---
    char actions[NAVOS_MAX_ACTIONS][NAVOS_MAX_STRING_LEN];
    uint8_t action_count;

    // --- Metadata ---
    bool valid;              // true once at least one successful fetch
    unsigned long last_update_ms;  // millis() of last successful parse
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

    s.valid = false;
    s.last_update_ms = 0;
}

/**
 * Compare two states to detect if displayed data changed.
 * Returns true if anything that would affect the display is different.
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
    return false;
}
