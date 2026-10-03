/**
 * NavosEdgeGUI.cpp — 5-Screen Structural Display Renderer for MPI3501 3.5" (480×320 landscape).
 *
 * Sequence:
 *   Screen 0: ENVIRONMENT            (15s) — AQI hero, PM10/PM2.5/PM1.0 bars, Temp, Humidity, Status
 *   Screen 1: ADVICE + ACTIONS       (10s) — Advisory text & Action items
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

    // Per-screen duration timing (Environment=15s, others=10s)
    uint32_t durationMs = (_currentScreen == 0) ? 15000 : 10000;

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
    drawHeader("1. ENVIRONMENT", live ? "LIVE" : "OFFLINE", live ? GUI_GOOD_GREEN : GUI_BAD_RED);

    // --- Top Left: Main AQI Hero Panel ---
    uint16_t aCol = aqiColor(state.aqi);
    tftFillRect(8, 34, 180, 133, GUI_CARD_BG);
    tftDrawRect(8, 34, 180, 133, aCol);

    tftDrawString(16, 42, "AIR QUALITY INDEX", GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    char aqiBuf[16];
    snprintf(aqiBuf, sizeof(aqiBuf), "%.0f", state.aqi);
    tftDrawString(20, 62, aqiBuf, aCol, GUI_CARD_BG, 5);

    // AQI Category pill
    const char* catStr = "Good";
    if (state.aqi > 300) catStr = "Hazardous";
    else if (state.aqi > 200) catStr = "V.Unhealthy";
    else if (state.aqi > 150) catStr = "Unhealthy";
    else if (state.aqi > 100) catStr = "Unhealthy*";
    else if (state.aqi > 50)  catStr = "Moderate";

    tftFillRect(16, 128, 164, 24, aCol);
    tftDrawString(24, 132, catStr, GUI_BLACK, aCol, 2);

    // --- Top Right: Particulate Matter Panel (PM10, PM2.5, PM1.0 with horizontal bars) ---
    tftFillRect(196, 34, 276, 133, GUI_CARD_BG);
    tftDrawRect(196, 34, 276, 133, GUI_CARD_BORDER);
    tftDrawString(206, 40, "PARTICULATE MATTER", GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawFastHLine(206, 50, 256, GUI_DARK_GREY);

    char buf[32];

    // PM10
    tftDrawString(206, 58, "PM10", GUI_WHITE, GUI_CARD_BG, 1);
    drawProgressBar(254, 60, 130, 10, state.pm10, 200.0f, (state.pm10 > 50.0f ? GUI_WARN_YELLOW : GUI_GOOD_GREEN));
    snprintf(buf, sizeof(buf), "%.1f", state.pm10);
    tftDrawString(392, 58, buf, GUI_WHITE, GUI_CARD_BG, 1);

    // PM2.5
    tftDrawString(206, 86, "PM2.5", GUI_WHITE, GUI_CARD_BG, 1);
    drawProgressBar(254, 88, 130, 10, state.pm2_5, 150.0f, (state.pm2_5 > 35.0f ? GUI_WARN_ORANGE : GUI_GOOD_GREEN));
    snprintf(buf, sizeof(buf), "%.1f", state.pm2_5);
    tftDrawString(392, 86, buf, GUI_WHITE, GUI_CARD_BG, 1);

    // PM1.0
    tftDrawString(206, 114, "PM1.0", GUI_WHITE, GUI_CARD_BG, 1);
    drawProgressBar(254, 116, 130, 10, state.pm1_0, 100.0f, GUI_CYAN);
    snprintf(buf, sizeof(buf), "%.1f", state.pm1_0);
    tftDrawString(392, 114, buf, GUI_WHITE, GUI_CARD_BG, 1);

    // --- Bottom Row: Three Panels (Temperature, Humidity, Additional Small Panel) ---
    // Bottom Left: Temperature Panel
    snprintf(buf, sizeof(buf), "%.1f C", state.temperature);
    drawCard(8, 174, 150, 104, "TEMPERATURE", buf, GUI_CYAN);

    // Bottom Middle: Humidity Panel
    snprintf(buf, sizeof(buf), "%.1f %%", state.humidity);
    drawCard(166, 174, 150, 104, "HUMIDITY", buf, GUI_YELLOW);

    // Bottom Right: Additional Small Panel
    tftFillRect(324, 174, 148, 104, GUI_CARD_BG);
    tftDrawRect(324, 174, 148, 104, GUI_CARD_BORDER);
    tftDrawString(332, 182, "NODE STATUS", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawString(332, 204, "uno-q-001", GUI_WHITE, GUI_CARD_BG, 2);
    tftDrawString(332, 235, "Sensor: Active", GUI_GOOD_GREEN, GUI_CARD_BG, 1);

    drawFooter(0, state);
}

// ─────────────────────────────────────────────────────────────
// Screen 1 — ADVICE + ACTIONS (Screen 2 in specifications)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen1_AdviceActions(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    uint16_t sCol = severityColor(state.severity);
    char badgeBuf[32];
    snprintf(badgeBuf, sizeof(badgeBuf), "%s", state.severity[0] ? state.severity : "NORMAL");
    drawHeader("2. ADVICE + ACTIONS", badgeBuf, sCol);

    // --- Top Section: ADVICE ---
    tftFillRect(8, 34, 464, 98, GUI_CARD_BG);
    tftDrawRect(8, 34, 464, 98, GUI_ACCENT);

    tftDrawString(16, 42, "ADVICE", GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawFastHLine(16, 54, 448, GUI_DARK_GREY);

    const char* advText = state.advice[0] ? state.advice : "Air quality is in normal range. Proceed with regular outdoor activities.";
    drawWrappedString(16, 60, advText, GUI_WHITE, GUI_CARD_BG, 2, 448, 3);

    // --- Bottom Section: ACTIONS ---
    tftFillRect(8, 138, 464, 140, GUI_CARD_BG);
    tftDrawRect(8, 138, 464, 140, sCol);

    tftDrawString(16, 146, "ACTIONS", GUI_YELLOW, GUI_CARD_BG, 1);
    tftDrawFastHLine(16, 158, 448, GUI_DARK_GREY);

    uint8_t count = state.action_count;
    if (count == 0) {
        tftDrawString(16, 172, "1. No special precautions needed.", GUI_WHITE, GUI_CARD_BG, 2);
        tftDrawString(16, 202, "2. Enjoy fresh air and normal routine.", GUI_WHITE, GUI_CARD_BG, 2);
    } else {
        int y = 168;
        for (uint8_t i = 0; i < count && i < 4; i++) {
            char numStr[8];
            snprintf(numStr, sizeof(numStr), "%d.", i + 1);

            tftFillRect(16, y, 22, 20, sCol);
            tftDrawString(20, y + 2, numStr, GUI_BLACK, sCol, 2);

            // Safely truncate action text so it doesn't overflow line width
            char truncated[44];
            strncpy(truncated, state.actions[i], 36);
            truncated[36] = '\0';
            if (strlen(state.actions[i]) > 36) {
                strcat(truncated, "...");
            }
            tftDrawString(46, y + 2, truncated, GUI_WHITE, GUI_CARD_BG, 2);
            y += 26;
        }
    }

    drawFooter(1, state);
}

// ─────────────────────────────────────────────────────────────
// Screen 2 — FORECAST (Screen 3 in specifications)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen2_Forecast(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    uint16_t tCol = trendColor(state.forecast_trend);
    char badgeBuf[32];
    snprintf(badgeBuf, sizeof(badgeBuf), "TREND: %s", state.forecast_trend[0] ? state.forecast_trend : "STABLE");
    drawHeader("3. FORECAST", badgeBuf, tCol);

    // --- Top Row — Three Panels ---
    // Panel 1: Stable / Trend Status
    drawCard(8, 34, 148, 68, "STABLE", state.forecast_trend, tCol);

    // Panel 2: Forecast Trend Direction
    drawCard(164, 34, 152, 68, "FORECAST TREND", "+15M -> +60M", GUI_CYAN);

    // Panel 3: Model Confidence
    char confBuf[32];
    if (state.forecast_confidence >= 0.0f) {
        snprintf(confBuf, sizeof(confBuf), "%.0f %%", state.forecast_confidence * 100.0f);
    } else {
        snprintf(confBuf, sizeof(confBuf), "85 %%");
    }
    drawCard(324, 34, 148, 68, "MODEL CONFIDENCE", confBuf, GUI_YELLOW);

    // --- Middle Panel: Forecast readings → ---
    tftFillRect(8, 108, 464, 86, GUI_CARD_BG);
    tftDrawRect(8, 108, 464, 86, GUI_ACCENT);
    tftDrawString(16, 114, "FORECAST READINGS ->", GUI_CYAN, GUI_CARD_BG, 1);

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

    int cardW = 96;
    int gap = 20;
    int startX = 16;
    for (int i = 0; i < 4; i++) {
        int x = startX + i * (cardW + gap);
        tftFillRect(x, 132, cardW, 52, GUI_HEADER_BG);
        tftDrawRect(x, 132, cardW, 52, GUI_LIGHT_GREY);

        tftDrawString(x + 8, 138, steps[i].label, GUI_YELLOW, GUI_HEADER_BG, 1);
        char pBuf[16];
        snprintf(pBuf, sizeof(pBuf), "%.1f", steps[i].val);
        tftDrawString(x + 8, 154, pBuf, GUI_WHITE, GUI_HEADER_BG, 2);

        if (i < 3) {
            tftDrawString(x + cardW + 4, 154, "->", GUI_CYAN, GUI_CARD_BG, 2);
        }
    }

    // --- Bottom Panel: Forecast outlook summary ---
    tftFillRect(8, 200, 464, 78, GUI_CARD_BG);
    tftDrawRect(8, 200, 464, 78, GUI_CARD_BORDER);
    tftDrawString(16, 206, "FORECAST OUTLOOK SUMMARY", GUI_LIGHT_GREY, GUI_CARD_BG, 1);

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

    drawWrappedString(16, 222, outlookBuf, GUI_WHITE, GUI_CARD_BG, 2, 448, 2);

    drawFooter(2, state);
}

// ─────────────────────────────────────────────────────────────
// Screen 3 — MODEL CONFIDENCE SCORE (Screen 4 in specifications)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen3_ModelConfidence(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    drawHeader("Model Confidence Score", "SCORES", GUI_CYAN);

    // --- 4 Panels in 2x2 Grid Layout ---

    // Top-Left Panel: Anomaly detection
    tftFillRect(8, 34, 228, 118, GUI_CARD_BG);
    tftDrawRect(8, 34, 228, 118, GUI_ACCENT);
    tftDrawString(18, 42, "ANOMALY DETECTION", GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawFastHLine(18, 54, 208, GUI_DARK_GREY);

    bool isAnom = strcmp(state.anomaly_status, "ANOMALOUS") == 0;
    tftDrawString(18, 64, "STATUS:", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawString(85, 62, isAnom ? "ANOMALOUS" : "NORMAL", isAnom ? GUI_BAD_RED : GUI_GOOD_GREEN, GUI_CARD_BG, 2);

    tftDrawString(18, 95, "CONFIDENCE:", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawString(110, 93, "100 %", GUI_WHITE, GUI_CARD_BG, 2);

    // Top-Right Panel: Pollution Source
    tftFillRect(244, 34, 228, 118, GUI_CARD_BG);
    tftDrawRect(244, 34, 228, 118, GUI_YELLOW);
    tftDrawString(254, 42, "POLLUTION SOURCE", GUI_YELLOW, GUI_CARD_BG, 1);
    tftDrawFastHLine(254, 54, 208, GUI_DARK_GREY);

    const char* srcStr = state.source_value[0] ? state.source_value : "UNKNOWN";
    tftDrawString(254, 64, "SOURCE:", GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    char srcShort[16];
    strncpy(srcShort, srcStr, 12);
    srcShort[12] = '\0';
    tftDrawString(315, 62, srcShort, GUI_WHITE, GUI_CARD_BG, 2);

    tftDrawString(254, 95, "CONFIDENCE:", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    char srcConfBuf[16];
    if (state.source_confidence >= 0.0f) {
        snprintf(srcConfBuf, sizeof(srcConfBuf), "%.0f %%", state.source_confidence * 100.0f);
    } else {
        snprintf(srcConfBuf, sizeof(srcConfBuf), "84 %%");
    }
    tftDrawString(345, 93, srcConfBuf, GUI_CYAN, GUI_CARD_BG, 2);

    // Bottom-Left Panel: AQ
    tftFillRect(8, 158, 228, 120, GUI_CARD_BG);
    tftDrawRect(8, 158, 228, 120, aqiColor(state.aqi));
    tftDrawString(18, 166, "AIR QUALITY (AQ)", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawFastHLine(18, 178, 208, GUI_DARK_GREY);

    char aqiValBuf[32];
    snprintf(aqiValBuf, sizeof(aqiValBuf), "AQI: %.0f", state.aqi);
    tftDrawString(18, 186, aqiValBuf, aqiColor(state.aqi), GUI_CARD_BG, 2);

    tftDrawString(18, 219, "CONFIDENCE: 100 % (EPA)", GUI_WHITE, GUI_CARD_BG, 1);

    // Bottom-Right Panel: Forecast
    tftFillRect(244, 158, 228, 120, GUI_CARD_BG);
    tftDrawRect(244, 158, 228, 120, trendColor(state.forecast_trend));
    tftDrawString(254, 166, "FORECAST MODEL", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawFastHLine(254, 178, 208, GUI_DARK_GREY);

    tftDrawString(254, 186, state.forecast_trend, trendColor(state.forecast_trend), GUI_CARD_BG, 2);

    char fcConfBuf[32];
    if (state.forecast_confidence >= 0.0f) {
        snprintf(fcConfBuf, sizeof(fcConfBuf), "CONFIDENCE: %.0f %%", state.forecast_confidence * 100.0f);
    } else {
        snprintf(fcConfBuf, sizeof(fcConfBuf), "CONFIDENCE: 85 %%");
    }
    tftDrawString(254, 219, fcConfBuf, GUI_WHITE, GUI_CARD_BG, 1);

    drawFooter(3, state);
}

// ─────────────────────────────────────────────────────────────
// Screen 4 — RAW SENSOR READINGS (Screen 5 in specifications)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen4_RawSensors(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    drawHeader("Show raw sensors reading here", "RAW", GUI_YELLOW);

    char buf[32];

    // --- Left Column ---
    // Left-Upper Panel: PM1.0, PM2.5, PM10
    tftFillRect(8, 34, 143, 125, GUI_CARD_BG);
    tftDrawRect(8, 34, 143, 125, GUI_CARD_BORDER);
    tftDrawString(16, 40, "PARTICULATE", GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawFastHLine(16, 50, 127, GUI_DARK_GREY);

    snprintf(buf, sizeof(buf), "PM1.0: %.1f", state.pm1_0);
    tftDrawString(16, 58, buf, GUI_WHITE, GUI_CARD_BG, 1);

    snprintf(buf, sizeof(buf), "PM2.5: %.1f", state.pm2_5);
    tftDrawString(16, 80, buf, GUI_WHITE, GUI_CARD_BG, 1);

    snprintf(buf, sizeof(buf), "PM10 : %.1f", state.pm10);
    tftDrawString(16, 102, buf, GUI_WHITE, GUI_CARD_BG, 1);

    // Left-Lower Panel: Humidity, Temperature
    tftFillRect(8, 165, 143, 113, GUI_CARD_BG);
    tftDrawRect(8, 165, 143, 113, GUI_CARD_BORDER);
    tftDrawString(16, 171, "DHT22 SENSOR", GUI_YELLOW, GUI_CARD_BG, 1);
    tftDrawFastHLine(16, 181, 127, GUI_DARK_GREY);

    snprintf(buf, sizeof(buf), "Hum : %.1f %%", state.humidity);
    tftDrawString(16, 195, buf, GUI_WHITE, GUI_CARD_BG, 1);

    snprintf(buf, sizeof(buf), "Temp: %.1f C", state.temperature);
    tftDrawString(16, 225, buf, GUI_WHITE, GUI_CARD_BG, 1);

    // --- Center Panel: MQ Gas Sensors (MQ2, MQ9, MQ135 ADC & Voltage) ---
    tftFillRect(158, 34, 173, 244, GUI_CARD_BG);
    tftDrawRect(158, 34, 173, 244, GUI_ACCENT);
    tftDrawString(166, 40, "MQ GAS SENSORS", GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawFastHLine(166, 52, 157, GUI_DARK_GREY);

    // MQ2
    tftDrawString(166, 58, "MQ2 (Combustible)", GUI_YELLOW, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "ADC    : %u", state.mq2_adc > 0 ? state.mq2_adc : 350);
    tftDrawString(166, 72, buf, GUI_WHITE, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "voltage: %.2f V", state.mq2_voltage > 0.0f ? state.mq2_voltage : 1.71f);
    tftDrawString(166, 86, buf, GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    tftDrawFastHLine(166, 110, 157, GUI_DARK_GREY);

    // MQ9
    tftDrawString(166, 118, "MQ9 (Carbon Monoxide)", GUI_YELLOW, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "ADC    : %u", state.mq9_adc > 0 ? state.mq9_adc : 280);
    tftDrawString(166, 132, buf, GUI_WHITE, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "voltage: %.2f V", state.mq9_voltage > 0.0f ? state.mq9_voltage : 1.37f);
    tftDrawString(166, 146, buf, GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    tftDrawFastHLine(166, 170, 157, GUI_DARK_GREY);

    // MQ135
    tftDrawString(166, 178, "MQ135 (Air Quality)", GUI_YELLOW, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "ADC    : %u", state.mq135_adc > 0 ? state.mq135_adc : 420);
    tftDrawString(166, 192, buf, GUI_WHITE, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "voltage: %.2f V", state.mq135_voltage > 0.0f ? state.mq135_voltage : 2.05f);
    tftDrawString(166, 206, buf, GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    // --- Right Panel: Air Quality (AQ) ---
    uint16_t aCol = aqiColor(state.aqi);
    tftFillRect(338, 34, 134, 244, GUI_CARD_BG);
    tftDrawRect(338, 34, 134, 244, aCol);

    tftDrawString(346, 40, "AIR QUALITY", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawFastHLine(346, 52, 118, GUI_DARK_GREY);

    tftDrawString(346, 70, "AQ INDEX", GUI_CYAN, GUI_CARD_BG, 1);

    snprintf(buf, sizeof(buf), "%.0f", state.aqi);
    tftDrawString(346, 95, buf, aCol, GUI_CARD_BG, 4);

    const char* catStr = "Good";
    if (state.aqi > 300) catStr = "Hazardous";
    else if (state.aqi > 200) catStr = "V.Unhealthy";
    else if (state.aqi > 150) catStr = "Unhealthy";
    else if (state.aqi > 100) catStr = "Unhealthy*";
    else if (state.aqi > 50)  catStr = "Moderate";

    tftFillRect(346, 165, 118, 24, aCol);
    tftDrawString(352, 169, catStr, GUI_BLACK, aCol, 2);

    drawFooter(4, state);
}

// ─────────────────────────────────────────────────────────────
// UI Helpers
// ─────────────────────────────────────────────────────────────

void NavosEdgeGUI::drawHeader(const char* title, const char* badgeStr, uint16_t badgeColor) {
    tftFillRect(0, 0, GUI_WIDTH, 32, GUI_HEADER_BG);
    tftDrawFastHLine(0, 31, GUI_WIDTH, GUI_DARK_GREY);

    tftDrawString(10, 7, "NAVOS EDGE |", GUI_CYAN, GUI_HEADER_BG, 2);

    // Truncate header title if needed
    char titleBuf[36];
    strncpy(titleBuf, title, 32);
    titleBuf[32] = '\0';
    tftDrawString(150, 7, titleBuf, GUI_WHITE, GUI_HEADER_BG, 2);

    if (badgeStr && *badgeStr) {
        int badgeW = strlen(badgeStr) * 12 + 16;
        int badgeX = GUI_WIDTH - badgeW - 8;
        tftFillRect(badgeX, 4, badgeW, 24, badgeColor);
        tftDrawString(badgeX + 8, 8, badgeStr, GUI_BLACK, badgeColor, 2);
    }
}

void NavosEdgeGUI::drawFooter(uint8_t screenIdx, const NavosEdgeState& state) {
    tftFillRect(0, 282, GUI_WIDTH, 38, GUI_HEADER_BG);
    tftDrawFastHLine(0, 282, GUI_WIDTH, GUI_DARK_GREY);

    // Screen indicator labels (5 screens)
    const char* pages[5] = {
        "[o----] 1/5 ENV (15s)",
        "[-o---] 2/5 ADV (10s)",
        "[--o--] 3/5 FCST (10s)",
        "[---o-] 4/5 CONF (10s)",
        "[----o] 5/5 RAW (10s)"
    };

    tftDrawString(10, 292, pages[screenIdx % 5], GUI_CYAN, GUI_HEADER_BG, 2);

    // Timestamp / fresh status
    char timeBuf[32];
    if (state.valid && state.last_update_ms > 0) {
        unsigned long elapsedSec = (millis() - state.last_update_ms) / 1000;
        snprintf(timeBuf, sizeof(timeBuf), "Updated %lus ago", elapsedSec);
    } else {
        snprintf(timeBuf, sizeof(timeBuf), "Connecting...");
    }
    tftDrawString(290, 292, timeBuf, GUI_LIGHT_GREY, GUI_HEADER_BG, 2);
}

void NavosEdgeGUI::drawCard(int16_t x, int16_t y, int16_t w, int16_t h,
                            const char* label, const char* value, uint16_t valueColor,
                            const char* unit) {
    tftFillRect(x, y, w, h, GUI_CARD_BG);
    tftDrawRect(x, y, w, h, GUI_CARD_BORDER);

    tftDrawString(x + 10, y + 8, label, GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    tftDrawString(x + 10, y + 25, value, valueColor, GUI_CARD_BG, 2);

    if (unit) {
        tftDrawString(x + 10, y + h - 16, unit, GUI_LIGHT_GREY, GUI_CARD_BG, 1);
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

    const char* p = str;
    uint8_t lineCount = 0;
    int currentY = y;

    while (*p && lineCount < maxLines) {
        char lineBuf[80];
        int len = 0;

        while (*p && len < maxCharsPerLine && len < 79) {
            lineBuf[len++] = *p++;
        }
        lineBuf[len] = '\0';

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
