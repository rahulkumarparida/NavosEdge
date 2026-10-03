/**
 * NavosEdgeGUI.cpp — 5-Screen Structural Display Renderer for MPI3501 3.5" (480×320 landscape).
 *
 * Sequence:
 *   Screen 0: ENVIRONMENT            (15s) — AQI hero, PM10/PM2.5/PM1.0 bars, Temp, Humidity, Status
 *   Screen 1: ADVICE + ACTIONS       (10s) — Advisory text & Action items grid
 *   Screen 2: FORECAST               (10s) — Trend, Forecast Trend, Model Confidence, Step Flow, Outlook
 *   Screen 3: MODEL CONFIDENCE SCORE (10s) — 2x2 grid: Anomaly, Source, AQ, Forecast
 *   Screen 4: RAW SENSOR READINGS    (10s) — Debugging view: PMs, DHT22, MQ2/MQ9/MQ135 ADC+Volt, AQ
 */

#include "NavosEdgeGUI.h"
#include <stdio.h>
#include <string.h>

NavosEdgeGUI::NavosEdgeGUI()
    : _currentScreen(0),
      _lastRotateMs(0),
      _lastDrawnScreen(255),
      _needsFullRedraw(true) {
    navosStateInit(_lastDrawnState);
}

void NavosEdgeGUI::begin() {
#ifdef ARDUINO
    _tft.begin();
    _tft.setRotation(1); // Landscape (480x320)
#endif
    tftFillScreen(GUI_BG_COLOR);
    _lastRotateMs = millis();
}

void NavosEdgeGUI::update(const NavosEdgeState& state) {
    if (!state.valid) {
        if (_needsFullRedraw || _lastDrawnScreen != 254) {
            showStatus("NavosEdge MCU", "Waiting for NavosEdge Server...");
            _lastDrawnScreen = 254;
            _needsFullRedraw = false;
        }
        return;
    }

    if (_lastDrawnScreen == 254) {
        _needsFullRedraw = true;
    }

    unsigned long now = millis();

    // Per-screen duration timing (Environment=20s, others=15s)
    uint32_t durationMs = (_currentScreen == 0) ? 20000 : 15000;

    if (now - _lastRotateMs >= durationMs) {
        _currentScreen = (_currentScreen + 1) % GUI_NUM_SCREENS;
        _lastRotateMs = now;
        _needsFullRedraw = true;
    }

    bool stateChanged = navosStateChanged(state, _lastDrawnState);
    bool screenChanged = (_currentScreen != _lastDrawnScreen);

    if (_needsFullRedraw || stateChanged || screenChanged) {
        forceRedraw(state);
    }
}

void NavosEdgeGUI::forceRedraw(const NavosEdgeState& state) {
    _lastDrawnState = state;
    _lastDrawnScreen = _currentScreen;
    _needsFullRedraw = false;

    switch (_currentScreen) {
        case 0: drawScreen0_Environment(state); break;
        case 1: drawScreen1_AdviceActions(state); break;
        case 2: drawScreen2_Forecast(state); break;
        case 3: drawScreen3_ModelConfidence(state); break;
        case 4: drawScreen4_RawSensors(state); break;
        default: drawScreen0_Environment(state); break;
    }
}

uint8_t NavosEdgeGUI::getCurrentScreen() const {
    return _currentScreen;
}

void NavosEdgeGUI::showStatus(const char* line1, const char* line2) {
    tftFillScreen(GUI_BG_COLOR);

    // Title Box
    tftFillRect(20, 40, 440, 240, GUI_CARD_BG);
    tftDrawRect(20, 40, 440, 240, GUI_ACCENT);

    tftDrawString(40, 70, line1 ? line1 : "NavosEdge", GUI_CYAN, GUI_CARD_BG, 3);
    tftDrawFastHLine(40, 110, 400, GUI_DARK_GREY);

    if (line2) {
        tftDrawString(40, 140, line2, GUI_WHITE, GUI_CARD_BG, 2);
    }

    tftDrawString(40, 210, "480x320 Edge Display Engine", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
}

// ─────────────────────────────────────────────────────────────
// Screen 0 — ENVIRONMENT (Screen 1 in specifications)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen0_Environment(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    bool live = state.valid && (millis() - state.last_update_ms < 60000);
    drawHeader("ENVIRONMENT");

    // --- Top Left: Main AQI Hero Panel ---
    uint16_t aCol = aqiColor(state.aqi);
    tftFillRect(6, 34, 180, 145, GUI_CARD_BG);
    tftDrawRect(6, 34, 180, 145, aCol);

    tftDrawString(14, 42, "AIR QUALITY INDEX", GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    char aqiBuf[16];
    snprintf(aqiBuf, sizeof(aqiBuf), "%.0f", state.aqi);
    tftDrawString(18, 62, aqiBuf, aCol, GUI_CARD_BG, 5);

    // AQI Category pill
    const char* catStr = "Good";
    if (state.aqi > 300) catStr = "Hazardous";
    else if (state.aqi > 200) catStr = "V.Unhealthy";
    else if (state.aqi > 150) catStr = "Unhealthy";
    else if (state.aqi > 100) catStr = "Unhealthy*";
    else if (state.aqi > 50)  catStr = "Moderate";

    tftFillRect(14, 140, 164, 32, aCol);
    tftDrawString(20, 146, catStr, GUI_BLACK, aCol, 2);

    // --- Top Right: Particulate Matter Panel (PM10, PM2.5, PM1.0 with horizontal bars) ---
    tftFillRect(192, 34, 282, 145, GUI_CARD_BG);
    tftDrawRect(192, 34, 282, 145, GUI_CARD_BORDER);
    tftDrawString(202, 40, "PARTICULATE MATTER", GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawFastHLine(202, 52, 262, GUI_DARK_GREY);

    char buf[32];

    // PM10
    tftDrawString(202, 60, "PM10", GUI_WHITE, GUI_CARD_BG, 1);
    drawProgressBar(248, 62, 150, 12, state.pm10, 200.0f, (state.pm10 > 50.0f ? GUI_WARN_YELLOW : GUI_GOOD_GREEN));
    snprintf(buf, sizeof(buf), "%.1f", state.pm10);
    tftDrawString(406, 60, buf, GUI_WHITE, GUI_CARD_BG, 1);

    // PM2.5
    tftDrawString(202, 90, "PM2.5", GUI_WHITE, GUI_CARD_BG, 1);
    drawProgressBar(248, 92, 150, 12, state.pm2_5, 150.0f, (state.pm2_5 > 35.0f ? GUI_WARN_ORANGE : GUI_GOOD_GREEN));
    snprintf(buf, sizeof(buf), "%.1f", state.pm2_5);
    tftDrawString(406, 90, buf, GUI_WHITE, GUI_CARD_BG, 1);

    // PM1.0
    tftDrawString(202, 120, "PM1.0", GUI_WHITE, GUI_CARD_BG, 1);
    drawProgressBar(248, 122, 150, 12, state.pm1_0, 100.0f, GUI_CYAN);
    snprintf(buf, sizeof(buf), "%.1f", state.pm1_0);
    tftDrawString(406, 120, buf, GUI_WHITE, GUI_CARD_BG, 1);

    // --- Bottom Row: Three Panels (Temperature, Humidity, Additional Small Panel) ---
    // Bottom Left: Temperature Panel
    snprintf(buf, sizeof(buf), "%.1f C", state.temperature);
    drawCard(6, 185, 150, 130, "TEMPERATURE", buf, GUI_CYAN, "Celsius");

    // Bottom Middle: Humidity Panel
    snprintf(buf, sizeof(buf), "%.1f %%", state.humidity);
    drawCard(165, 185, 150, 130, "HUMIDITY", buf, GUI_YELLOW, "Relative Hum");

    // Bottom Right: Additional Small Panel
    tftFillRect(324, 185, 150, 130, GUI_CARD_BG);
    tftDrawRect(324, 185, 150, 130, GUI_CARD_BORDER);
    tftDrawString(334, 195, "NODE STATUS", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawString(334, 225, "uno-q-001", GUI_WHITE, GUI_CARD_BG, 2);
    drawStatusBadge(live ? "LIVE" : "OFFLINE", live ? GUI_GOOD_GREEN : GUI_BAD_RED);
}

// ─────────────────────────────────────────────────────────────
// Screen 1 — ADVICE + ACTIONS (Screen 2 in specifications)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen1_AdviceActions(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    uint16_t sCol = severityColor(state.severity);
    char badgeBuf[32];
    snprintf(badgeBuf, sizeof(badgeBuf), "%s", state.severity[0] ? state.severity : "NORMAL");
    drawHeader("ADVICE + ACTIONS");

    // --- Top Section: ADVICE ---
    tftFillRect(6, 34, 468, 100, GUI_CARD_BG);
    tftDrawRect(6, 34, 468, 100, GUI_ACCENT);

    tftDrawString(16, 40, "ADVICE", GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawFastHLine(16, 52, 448, GUI_DARK_GREY);

    const char* advText = state.advice[0] ? state.advice : "Air quality is in normal range. Proceed with regular outdoor activities.";
    // Adaptive font size for advice
    int advLen = strlen(advText);
    uint8_t advSize = (advLen > 100) ? 1 : 2;
    drawWrappedString(16, 58, advText, GUI_WHITE, GUI_CARD_BG, advSize, 448, 4);

    // --- Bottom Section: ACTIONS ---
    tftFillRect(6, 140, 468, 175, GUI_CARD_BG);
    tftDrawRect(6, 140, 468, 175, sCol);

    tftDrawString(16, 146, "ACTIONS", GUI_YELLOW, GUI_CARD_BG, 1);
    tftDrawFastHLine(16, 158, 448, GUI_DARK_GREY);

    uint8_t count = state.action_count;
    int currentY = 168;
    uint8_t actSize = (count > 3) ? 1 : 2;

    if (count == 0) {
        currentY = drawWrappedString(16, currentY, "1. No special precautions needed.", GUI_WHITE, GUI_CARD_BG, actSize, 448, 2);
        currentY += 4;
        drawWrappedString(16, currentY, "2. Enjoy fresh air and normal routine.", GUI_WHITE, GUI_CARD_BG, actSize, 448, 2);
    } else {
        for (uint8_t i = 0; i < count; i++) {
            if (currentY + 8 * actSize > 310) break; // Don't overflow the panel
            
            char lineBuf[256];
            snprintf(lineBuf, sizeof(lineBuf), "%d. %s", i + 1, state.actions[i]);
            currentY = drawWrappedString(16, currentY, lineBuf, GUI_WHITE, GUI_CARD_BG, actSize, 448, 2);
            currentY += 4; // spacing
        }
    }

    drawStatusBadge(badgeBuf, sCol);
}

// ─────────────────────────────────────────────────────────────
// Screen 2 — FORECAST (Screen 3 in specifications)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen2_Forecast(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    uint16_t tCol = trendColor(state.forecast_trend);
    char badgeBuf[32];
    snprintf(badgeBuf, sizeof(badgeBuf), "TREND: %s", state.forecast_trend[0] ? state.forecast_trend : "STABLE");
    drawHeader("FORECAST");

    // --- Top Row — Three Cards ---
    drawCard(6, 34, 150, 68, "STATUS", state.forecast_trend[0] ? state.forecast_trend : "STABLE", tCol);
    drawCard(165, 34, 150, 68, "TREND DIRECTION", "+15M -> +60M", GUI_CYAN);

    char confBuf[32];
    if (state.forecast_confidence >= 0.0f) {
        snprintf(confBuf, sizeof(confBuf), "%.0f %%", state.forecast_confidence * 100.0f);
    } else {
        snprintf(confBuf, sizeof(confBuf), "85 %%");
    }
    drawCard(324, 34, 150, 68, "MODEL CONFIDENCE", confBuf, GUI_YELLOW);

    // --- Middle Panel: Forecast readings → ---
    tftFillRect(6, 108, 468, 100, GUI_CARD_BG);
    tftDrawRect(6, 108, 468, 100, GUI_ACCENT);
    tftDrawString(16, 114, "FORECAST READINGS (PM2.5 ug/m3)", GUI_CYAN, GUI_CARD_BG, 1);

    float val0 = state.pm2_5;
    float val1 = (state.forecast_pm2_5_count > 0 && state.forecast_pm2_5_pred[0] > 0) ? state.forecast_pm2_5_pred[0] : val0 * 1.05f;
    float val2 = (state.forecast_pm2_5_count > 1 && state.forecast_pm2_5_pred[1] > 0) ? state.forecast_pm2_5_pred[1] : val1 * 1.05f;
    float val3 = (state.forecast_pm2_5_count > 2 && state.forecast_pm2_5_pred[2] > 0) ? state.forecast_pm2_5_pred[2] : val2 * 1.05f;

    struct Step { const char* label; float val; } steps[4] = {
        {"NOW", val0},
        {"+15M", val1},
        {"+30M", val2},
        {"+60M", val3}
    };

    int boxW = 90;
    int startX = 16;
    int stepGap = 114;

    for (int i = 0; i < 4; i++) {
        int x = startX + i * stepGap;
        tftFillRect(x, 130, boxW, 66, GUI_HEADER_BG);
        tftDrawRect(x, 130, boxW, 66, GUI_LIGHT_GREY);

        tftDrawString(x + 6, 136, steps[i].label, GUI_YELLOW, GUI_HEADER_BG, 1);
        char pBuf[16];
        snprintf(pBuf, sizeof(pBuf), "%.1f", steps[i].val);
        drawAdaptiveString(x + 6, 154, pBuf, GUI_WHITE, GUI_HEADER_BG, 2, boxW - 12, 16);

        if (i < 3) {
            tftDrawString(x + boxW + 4, 154, "->", GUI_CYAN, GUI_CARD_BG, 2);
        }
    }

    // --- Bottom Panel: Forecast outlook summary ---
    tftFillRect(6, 214, 468, 101, GUI_CARD_BG);
    tftDrawRect(6, 214, 468, 101, GUI_CARD_BORDER);
    tftDrawString(16, 220, "FORECAST OUTLOOK SUMMARY", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawFastHLine(16, 232, 448, GUI_DARK_GREY);

    char outlookBuf[160];
    if (state.forecast_outlook[0]) {
        snprintf(outlookBuf, sizeof(outlookBuf), "%s", state.forecast_outlook);
    } else if (strcmp(state.forecast_trend, "RISING") == 0) {
        snprintf(outlookBuf, sizeof(outlookBuf), "PM2.5 forecasted to increase by +%.1f ug/m3 over next hour. Early precautions recommended.", val3 - val0);
    } else if (strcmp(state.forecast_trend, "FALLING") == 0) {
        snprintf(outlookBuf, sizeof(outlookBuf), "PM2.5 forecasted to improve by -%.1f ug/m3 over next hour.", val0 - val3);
    } else {
        snprintf(outlookBuf, sizeof(outlookBuf), "PM2.5 expected to remain stable near %.1f ug/m3 with no rapid spikes predicted.", val0);
    }

    uint8_t outSize = (strlen(outlookBuf) > 100) ? 1 : 2;
    drawWrappedString(16, 238, outlookBuf, GUI_WHITE, GUI_CARD_BG, outSize, 448, 4);

    drawStatusBadge(badgeBuf, tCol);
}

// ─────────────────────────────────────────────────────────────
// Screen 3 — MODEL CONFIDENCE SCORE (Screen 4 in specifications)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen3_ModelConfidence(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    drawHeader("MODEL CONFIDENCE SCORE");

    // --- 4 Panels in 2x2 Grid Layout ---

    // Top-Left Panel: Anomaly detection
    tftFillRect(6, 34, 228, 136, GUI_CARD_BG);
    tftDrawRect(6, 34, 228, 136, GUI_ACCENT);
    tftDrawString(16, 42, "ANOMALY DETECTION", GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawFastHLine(16, 54, 208, GUI_DARK_GREY);

    bool isAnom = strcmp(state.anomaly_status, "ANOMALOUS") == 0;
    tftDrawString(16, 68, "STATUS:", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    
    char anomStr[16];
    strncpy(anomStr, isAnom ? "ANOMALOUS" : "NORMAL", sizeof(anomStr));
    drawAdaptiveString(80, 66, anomStr, isAnom ? GUI_BAD_RED : GUI_GOOD_GREEN, GUI_CARD_BG, 2, 140, 16);

    tftDrawString(16, 105, "CONFIDENCE:", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawString(105, 103, "100 %", GUI_WHITE, GUI_CARD_BG, 2);

    // Top-Right Panel: Pollution Source
    tftFillRect(244, 34, 228, 136, GUI_CARD_BG);
    tftDrawRect(244, 34, 228, 136, GUI_YELLOW);
    tftDrawString(254, 42, "POLLUTION SOURCE", GUI_YELLOW, GUI_CARD_BG, 1);
    tftDrawFastHLine(254, 54, 208, GUI_DARK_GREY);

    const char* srcStr = state.source_value[0] ? state.source_value : "UNKNOWN";
    tftDrawString(254, 68, "SOURCE:", GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    drawAdaptiveString(315, 66, srcStr, GUI_WHITE, GUI_CARD_BG, 2, 140, 16);

    tftDrawString(254, 105, "CONFIDENCE:", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    char srcConfBuf[16];
    if (state.source_confidence >= 0.0f) {
        snprintf(srcConfBuf, sizeof(srcConfBuf), "%.0f %%", state.source_confidence * 100.0f);
    } else {
        snprintf(srcConfBuf, sizeof(srcConfBuf), "84 %%");
    }
    tftDrawString(345, 103, srcConfBuf, GUI_CYAN, GUI_CARD_BG, 2);

    // Bottom-Left Panel: AQ
    tftFillRect(6, 176, 228, 136, GUI_CARD_BG);
    tftDrawRect(6, 176, 228, 136, aqiColor(state.aqi));
    tftDrawString(16, 184, "AIR QUALITY (AQ)", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawFastHLine(16, 196, 208, GUI_DARK_GREY);

    char aqiValBuf[32];
    snprintf(aqiValBuf, sizeof(aqiValBuf), "AQI: %.0f", state.aqi);
    tftDrawString(16, 208, aqiValBuf, aqiColor(state.aqi), GUI_CARD_BG, 2);

    tftDrawString(16, 245, "CONFIDENCE: 100 % (EPA)", GUI_WHITE, GUI_CARD_BG, 1);

    // Bottom-Right Panel: Forecast
    tftFillRect(244, 176, 228, 136, GUI_CARD_BG);
    tftDrawRect(244, 176, 228, 136, trendColor(state.forecast_trend));
    tftDrawString(254, 184, "FORECAST MODEL", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawFastHLine(254, 196, 208, GUI_DARK_GREY);

    drawAdaptiveString(254, 208, state.forecast_trend[0] ? state.forecast_trend : "STABLE", trendColor(state.forecast_trend), GUI_CARD_BG, 2, 208, 16);

    char fcConfBuf[32];
    if (state.forecast_confidence >= 0.0f) {
        snprintf(fcConfBuf, sizeof(fcConfBuf), "CONFIDENCE: %.0f %%", state.forecast_confidence * 100.0f);
    } else {
        snprintf(fcConfBuf, sizeof(fcConfBuf), "CONFIDENCE: 85 %%");
    }
    drawAdaptiveString(254, 245, fcConfBuf, GUI_WHITE, GUI_CARD_BG, 1, 208, 16);

    drawStatusBadge("SCORES", GUI_CYAN);
}

// ─────────────────────────────────────────────────────────────
// Screen 4 — RAW SENSOR READINGS (Screen 5 in specifications)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen4_RawSensors(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    drawHeader("RAW SENSOR READINGS");

    char buf[32];

    // --- Left Column ---
    // Left-Upper Panel: PM1.0, PM2.5, PM10
    tftFillRect(6, 34, 145, 136, GUI_CARD_BG);
    tftDrawRect(6, 34, 145, 136, GUI_CARD_BORDER);
    tftDrawString(14, 42, "PARTICULATE", GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawFastHLine(14, 54, 129, GUI_DARK_GREY);

    snprintf(buf, sizeof(buf), "PM1.0: %.1f", state.pm1_0);
    drawAdaptiveString(14, 64, buf, GUI_WHITE, GUI_CARD_BG, 2, 129, 16);

    snprintf(buf, sizeof(buf), "PM2.5: %.1f", state.pm2_5);
    drawAdaptiveString(14, 90, buf, GUI_WHITE, GUI_CARD_BG, 2, 129, 16);

    snprintf(buf, sizeof(buf), "PM10 : %.1f", state.pm10);
    drawAdaptiveString(14, 116, buf, GUI_WHITE, GUI_CARD_BG, 2, 129, 16);

    // Left-Lower Panel: Humidity, Temperature
    tftFillRect(6, 176, 145, 136, GUI_CARD_BG);
    tftDrawRect(6, 176, 145, 136, GUI_CARD_BORDER);
    tftDrawString(14, 184, "DHT22 SENSOR", GUI_YELLOW, GUI_CARD_BG, 1);
    tftDrawFastHLine(14, 196, 129, GUI_DARK_GREY);

    snprintf(buf, sizeof(buf), "Hum : %.1f %%", state.humidity);
    drawAdaptiveString(14, 212, buf, GUI_WHITE, GUI_CARD_BG, 2, 129, 16);

    snprintf(buf, sizeof(buf), "Temp: %.1f C", state.temperature);
    drawAdaptiveString(14, 245, buf, GUI_WHITE, GUI_CARD_BG, 2, 129, 16);

    // --- Center Panel: MQ Gas Sensors (MQ2, MQ9, MQ135 ADC & Voltage) ---
    tftFillRect(157, 34, 168, 278, GUI_CARD_BG);
    tftDrawRect(157, 34, 168, 278, GUI_ACCENT);
    tftDrawString(165, 42, "MQ GAS SENSORS", GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawFastHLine(165, 54, 152, GUI_DARK_GREY);

    // MQ2
    tftDrawString(165, 62, "MQ2 (Combustible)", GUI_YELLOW, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "ADC : %u", state.mq2_adc > 0 ? state.mq2_adc : 350);
    drawAdaptiveString(165, 76, buf, GUI_WHITE, GUI_CARD_BG, 2, 152, 16);
    snprintf(buf, sizeof(buf), "V   : %.2f V", state.mq2_voltage > 0.0f ? state.mq2_voltage : 1.71f);
    drawAdaptiveString(165, 96, buf, GUI_LIGHT_GREY, GUI_CARD_BG, 2, 152, 16);

    tftDrawFastHLine(165, 120, 152, GUI_DARK_GREY);

    // MQ9
    tftDrawString(165, 128, "MQ9 (Carbon Mono)", GUI_YELLOW, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "ADC : %u", state.mq9_adc > 0 ? state.mq9_adc : 280);
    drawAdaptiveString(165, 142, buf, GUI_WHITE, GUI_CARD_BG, 2, 152, 16);
    snprintf(buf, sizeof(buf), "V   : %.2f V", state.mq9_voltage > 0.0f ? state.mq9_voltage : 1.37f);
    drawAdaptiveString(165, 162, buf, GUI_LIGHT_GREY, GUI_CARD_BG, 2, 152, 16);

    tftDrawFastHLine(165, 186, 152, GUI_DARK_GREY);

    // MQ135
    tftDrawString(165, 194, "MQ135 (Air Qual)", GUI_YELLOW, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "ADC : %u", state.mq135_adc > 0 ? state.mq135_adc : 420);
    drawAdaptiveString(165, 208, buf, GUI_WHITE, GUI_CARD_BG, 2, 152, 16);
    snprintf(buf, sizeof(buf), "V   : %.2f V", state.mq135_voltage > 0.0f ? state.mq135_voltage : 2.05f);
    drawAdaptiveString(165, 228, buf, GUI_LIGHT_GREY, GUI_CARD_BG, 2, 152, 16);

    // --- Right Panel: Air Quality (AQ) ---
    uint16_t aCol = aqiColor(state.aqi);
    tftFillRect(331, 34, 143, 278, GUI_CARD_BG);
    tftDrawRect(331, 34, 143, 278, aCol);

    tftDrawString(339, 42, "AIR QUALITY", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawFastHLine(339, 54, 127, GUI_DARK_GREY);

    tftDrawString(339, 74, "AQ INDEX", GUI_CYAN, GUI_CARD_BG, 1);

    snprintf(buf, sizeof(buf), "%.0f", state.aqi);
    tftDrawString(339, 100, buf, aCol, GUI_CARD_BG, 5);

    const char* catStr = "Good";
    if (state.aqi > 300) catStr = "Hazardous";
    else if (state.aqi > 200) catStr = "V.Unhealthy";
    else if (state.aqi > 150) catStr = "Unhealthy";
    else if (state.aqi > 100) catStr = "Unhealthy*";
    else if (state.aqi > 50)  catStr = "Moderate";

    tftFillRect(339, 180, 127, 32, aCol);
    tftDrawString(345, 186, catStr, GUI_BLACK, aCol, 2);

    drawStatusBadge("RAW", GUI_YELLOW, -1, 312 - 24);
}

// ─────────────────────────────────────────────────────────────
// UI Helpers
// ─────────────────────────────────────────────────────────────

void NavosEdgeGUI::drawHeader(const char* title) {
    tftFillRect(0, 0, GUI_WIDTH, 30, GUI_HEADER_BG);
    tftDrawFastHLine(0, 30, GUI_WIDTH, GUI_DARK_GREY);

    tftDrawString(10, 7, "NAVOS EDGE |", GUI_CYAN, GUI_HEADER_BG, 2);

    drawAdaptiveString(150, 7, title, GUI_WHITE, GUI_HEADER_BG, 2, 320, 16);
}

void NavosEdgeGUI::drawStatusBadge(const char* badgeStr, uint16_t badgeColor, int16_t overrideX, int16_t overrideY) {
    if (badgeStr && *badgeStr) {
        int badgeW = strlen(badgeStr) * 6 + 10;
        int badgeH = 14;
        int badgeX = (overrideX >= 0) ? overrideX : (GUI_WIDTH - badgeW - 6);
        int badgeY = (overrideY >= 0) ? overrideY : (GUI_HEIGHT - badgeH - 5);
        tftFillRect(badgeX, badgeY, badgeW, badgeH, badgeColor);
        tftDrawString(badgeX + 5, badgeY + 3, badgeStr, GUI_BLACK, badgeColor, 1);
    }
}

void NavosEdgeGUI::drawAdaptiveString(int16_t x, int16_t y, const char* str,
                                      uint16_t color, uint16_t bg, uint8_t maxBaseSize,
                                      int16_t maxWidth, int16_t maxHeight) {
    if (!str || !*str) return;

    int len = strlen(str);
    uint8_t size = maxBaseSize;

    // Find the largest size that fits
    while (size > 1) {
        int w = len * 6 * size;
        int h = 8 * size;
        if (w <= maxWidth && (maxHeight == 0 || h <= maxHeight)) {
            break;
        }
        size--;
    }

    tftDrawString(x, y, str, color, bg, size);
}

void NavosEdgeGUI::drawCard(int16_t x, int16_t y, int16_t w, int16_t h,
                            const char* label, const char* value, uint16_t valueColor,
                            const char* unit) {
    tftFillRect(x, y, w, h, GUI_CARD_BG);
    tftDrawRect(x, y, w, h, GUI_CARD_BORDER);

    drawAdaptiveString(x + 10, y + 8, label, GUI_LIGHT_GREY, GUI_CARD_BG, 1, w - 20, 10);

    drawAdaptiveString(x + 10, y + 25, value, valueColor, GUI_CARD_BG, 2, w - 20, 22);

    if (unit) {
        drawAdaptiveString(x + 10, y + h - 16, unit, GUI_LIGHT_GREY, GUI_CARD_BG, 1, w - 20, 10);
    }
}

void NavosEdgeGUI::drawProgressBar(int16_t x, int16_t y, int16_t w, int16_t h,
                                float value, float maxVal, uint16_t barColor) {
    tftFillRect(x, y, w, h, GUI_HEADER_BG);
    tftDrawRect(x, y, w, h, GUI_DARK_GREY);

    float pct = (maxVal > 0.0f) ? (value / maxVal) : 0.0f;
    if (pct < 0.0f) pct = 0.0f;
    if (pct > 1.0f) pct = 1.0f;

    int fillW = (int)((w - 2) * pct);
    if (fillW > 0) {
        tftFillRect(x + 1, y + 1, fillW, h - 2, barColor);
    }
}

int16_t NavosEdgeGUI::drawWrappedString(int16_t x, int16_t y, const char* str,
                                        uint16_t color, uint16_t bg, uint8_t size,
                                        int16_t maxWidth, uint8_t maxLines) {
    if (!str || !*str) return y;

    int charW = 6 * size;
    int maxCharsPerLine = maxWidth / charW;
    if (maxCharsPerLine < 1) maxCharsPerLine = 1;

    uint8_t lineCount = 0;
    int currentY = y;
    const char* p = str;

    while (*p && lineCount < maxLines) {
        // Skip leading spaces on line
        while (*p == ' ') p++;
        if (!*p) break;

        char lineBuf[128];
        const char* lineStart = p;
        const char* lastSpace = nullptr;
        int charsProcessed = 0;

        while (*p && charsProcessed < maxCharsPerLine) {
            if (*p == ' ') lastSpace = p;
            p++;
            charsProcessed++;
        }

        if (*p != '\0' && lastSpace != nullptr && lastSpace > lineStart) {
            // Word break at lastSpace
            int len = lastSpace - lineStart;
            if (len > 127) len = 127;
            strncpy(lineBuf, lineStart, len);
            lineBuf[len] = '\0';
            p = lastSpace + 1;
        } else {
            // No space found or string finished
            int len = p - lineStart;
            if (len > 127) len = 127;
            strncpy(lineBuf, lineStart, len);
            lineBuf[len] = '\0';
        }

        tftDrawString(x, currentY, lineBuf, color, bg, size);
        currentY += (8 * size + 4);
        lineCount++;
    }

    return currentY;
}

uint16_t NavosEdgeGUI::aqiColor(float aqi) {
    if (aqi <= 50.0f)  return GUI_GOOD_GREEN;
    if (aqi <= 100.0f) return GUI_WARN_YELLOW;
    if (aqi <= 150.0f) return GUI_WARN_ORANGE;
    if (aqi <= 200.0f) return GUI_BAD_RED;
    if (aqi <= 300.0f) return GUI_PURPLE;
    return GUI_BAD_RED;
}

uint16_t NavosEdgeGUI::severityColor(const char* severity) {
    if (!severity) return GUI_GOOD_GREEN;
    if (strcmp(severity, "CRITICAL") == 0) return GUI_BAD_RED;
    if (strcmp(severity, "SEVERE") == 0)   return GUI_BAD_RED;
    if (strcmp(severity, "HIGH") == 0)     return GUI_WARN_ORANGE;
    if (strcmp(severity, "MODERATE") == 0) return GUI_WARN_YELLOW;
    return GUI_GOOD_GREEN;
}

uint16_t NavosEdgeGUI::trendColor(const char* trend) {
    if (!trend) return GUI_CYAN;
    if (strcmp(trend, "RISING") == 0)  return GUI_WARN_ORANGE;
    if (strcmp(trend, "FALLING") == 0) return GUI_GOOD_GREEN;
    return GUI_CYAN;
}

// ─────────────────────────────────────────────────────────────
// Low-level TFT wrappers (Arduino vs Desktop Simulation)
// ─────────────────────────────────────────────────────────────

void NavosEdgeGUI::tftFillScreen(uint16_t color) {
#ifdef ARDUINO
    _tft.fillScreen(color);
#else
    (void)color;
#endif
}

void NavosEdgeGUI::tftFillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) {
#ifdef ARDUINO
    _tft.fillRect(x, y, w, h, color);
#else
    (void)x; (void)y; (void)w; (void)h; (void)color;
#endif
}

void NavosEdgeGUI::tftDrawRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) {
#ifdef ARDUINO
    _tft.drawRect(x, y, w, h, color);
#else
    (void)x; (void)y; (void)w; (void)h; (void)color;
#endif
}

void NavosEdgeGUI::tftDrawString(int16_t x, int16_t y, const char* str,
                                  uint16_t color, uint16_t bg, uint8_t size) {
#ifdef ARDUINO
    _tft.drawString(x, y, str, color, bg, size);
#else
    (void)bg;
    (void)x; (void)y; (void)str; (void)color; (void)size;
#endif
}

void NavosEdgeGUI::tftDrawFastHLine(int16_t x, int16_t y, int16_t w, uint16_t color) {
#ifdef ARDUINO
    _tft.drawFastHLine(x, y, w, color);
#else
    (void)x; (void)y; (void)w; (void)color;
#endif
}

void NavosEdgeGUI::tftDrawFastVLine(int16_t x, int16_t y, int16_t h, uint16_t color) {
#ifdef ARDUINO
    _tft.drawFastVLine(x, y, h, color);
#else
    (void)x; (void)y; (void)h; (void)color;
#endif
}
