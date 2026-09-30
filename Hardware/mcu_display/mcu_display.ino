/**
 * mcu_display.ino — NavosEdge MCU Physical Display Application
 *
 * Runs on Arduino UNO Q MCU (arduino:zephyr:unoq).
 * Initializes UNOQ_MPI3501 display (480x320 landscape).
 * Receives structured JSON state updates from Linux over Serial (/dev/ttyACM0).
 * Rotates 3 NavosEdge screens non-blockingly every 10 seconds using millis().
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <UNOQ_MPI3501.h>
#include "NavosEdgeState.h"
#include "NavosEdgeGUI.h"

NavosEdgeGUI gui;
NavosEdgeState state;

static char rxBuffer[1024];
static size_t rxIndex = 0;

void setup() {
    Serial.begin(115200);
    navosStateInit(state);
    gui.begin();
    gui.showStatus("NavosEdge MCU", "Waiting for Linux...");
}

void processJsonState(const char* jsonStr) {
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, jsonStr);
    if (err) {
        return;
    }

    if (doc.containsKey("aqi")) {
        state.aqi = doc["aqi"].as<float>();
    }
    if (doc.containsKey("pm1_0")) {
        state.pm1_0 = doc["pm1_0"].as<float>();
    }
    if (doc.containsKey("pm2_5")) {
        state.pm2_5 = doc["pm2_5"].as<float>();
    }
    if (doc.containsKey("pm10")) {
        state.pm10 = doc["pm10"].as<float>();
    }
    if (doc.containsKey("temperature")) {
        state.temperature = doc["temperature"].as<float>();
    }
    if (doc.containsKey("humidity")) {
        state.humidity = doc["humidity"].as<float>();
    }
    if (doc.containsKey("severity")) {
        const char* sev = doc["severity"];
        if (sev) {
            strncpy(state.severity, sev, sizeof(state.severity) - 1);
            state.severity[sizeof(state.severity) - 1] = '\0';
        }
    }
    if (doc.containsKey("advice")) {
        const char* adv = doc["advice"];
        if (adv) {
            strncpy(state.advice, adv, sizeof(state.advice) - 1);
            state.advice[sizeof(state.advice) - 1] = '\0';
        }
    }
    if (doc.containsKey("weather_advice")) {
        const char* wadv = doc["weather_advice"];
        if (wadv) {
            strncpy(state.weather_advice, wadv, sizeof(state.weather_advice) - 1);
            state.weather_advice[sizeof(state.weather_advice) - 1] = '\0';
        }
    }
    if (doc.containsKey("actions") && doc["actions"].is<JsonArray>()) {
        JsonArray actions = doc["actions"].as<JsonArray>();
        state.action_count = 0;
        for (JsonVariant v : actions) {
            if (state.action_count >= NAVOS_MAX_ACTIONS) break;
            const char* actStr = v.as<const char*>();
            if (actStr) {
                strncpy(state.actions[state.action_count], actStr, NAVOS_MAX_STRING_LEN - 1);
                state.actions[state.action_count][NAVOS_MAX_STRING_LEN - 1] = '\0';
                state.action_count++;
            }
        }
    }

    state.valid = true;
    state.last_update_ms = millis();
}

void loop() {
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n' || c == '\r') {
            if (rxIndex > 0) {
                rxBuffer[rxIndex] = '\0';
                processJsonState(rxBuffer);
                rxIndex = 0;
            }
        } else {
            if (rxIndex < sizeof(rxBuffer) - 1) {
                rxBuffer[rxIndex++] = c;
            } else {
                rxIndex = 0;
            }
        }
    }

    gui.update(state);
}
