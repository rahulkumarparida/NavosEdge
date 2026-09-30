/**
 * mcu_display.ino — NavosEdge MCU Physical Display Application (Modular Router RPC Bridge)
 *
 * Runs on Arduino UNO Q MCU (arduino:zephyr:unoq).
 * Initializes UNOQ_MPI3501 display (480x320 landscape).
 * Exposes 3 small RPC methods:
 *   - update_environment
 *   - update_advice
 *   - update_actions
 * Rotates 3 NavosEdge screens non-blockingly every 10 seconds using millis().
 */

#include <Arduino.h>
#include <Arduino_RouterBridge.h>
#include <UNOQ_MPI3501.h>
#include "NavosEdgeState.h"
#include "NavosEdgeGUI.h"

NavosEdgeGUI gui;
NavosEdgeState state;

void update_environment(float aqi, float pm1_0, float pm2_5, float pm10, float temp, float hum) {
    state.aqi = aqi;
    state.pm1_0 = pm1_0;
    state.pm2_5 = pm2_5;
    state.pm10 = pm10;
    state.temperature = temp;
    state.humidity = hum;
    state.valid = true;
    state.last_update_ms = millis();
}

void update_advice(String severity, String advice, String weather_advice) {
    strncpy(state.severity, severity.c_str(), sizeof(state.severity) - 1);
    state.severity[sizeof(state.severity) - 1] = '\0';

    strncpy(state.advice, advice.c_str(), sizeof(state.advice) - 1);
    state.advice[sizeof(state.advice) - 1] = '\0';

    strncpy(state.weather_advice, weather_advice.c_str(), sizeof(state.weather_advice) - 1);
    state.weather_advice[sizeof(state.weather_advice) - 1] = '\0';

    state.valid = true;
    state.last_update_ms = millis();
}

void update_actions(String actions_csv) {
    state.action_count = 0;
    int start = 0;
    int len = actions_csv.length();
    while (start < len && state.action_count < NAVOS_MAX_ACTIONS) {
        int end = actions_csv.indexOf(';', start);
        if (end == -1) end = len;
        String actStr = actions_csv.substring(start, end);
        actStr.trim();
        if (actStr.length() > 0) {
            strncpy(state.actions[state.action_count], actStr.c_str(), NAVOS_MAX_STRING_LEN - 1);
            state.actions[state.action_count][NAVOS_MAX_STRING_LEN - 1] = '\0';
            state.action_count++;
        }
        start = end + 1;
    }

    state.valid = true;
    state.last_update_ms = millis();
}

void setup() {
    Serial.begin(115200);
    navosStateInit(state);
    gui.begin();
    gui.showStatus("NavosEdge MCU", "Connecting RPC Bridge...");

    Bridge.begin();
    Bridge.provide_safe("update_environment", update_environment);
    Bridge.provide_safe("update_advice", update_advice);
    Bridge.provide_safe("update_actions", update_actions);

    Serial.println(F("[MCU] Bridge initialized"));
    Serial.println(F("[MCU] RPC methods registered: update_environment, update_advice, update_actions"));

    gui.showStatus("NavosEdge MCU", "RPC Bridge Ready");
}

void loop() {
    gui.update(state);
}
