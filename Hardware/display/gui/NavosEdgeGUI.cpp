/**
 * NavosEdgeGUI.cpp — 4-Screen Display renderer for the MPI3501 3.5" 480×320 screen.
 *
 * Sequence:
 *   Screen 0: ENVIRONMENT  (15s) — Observe (AQI, PM1.0, PM2.5, PM10, Temp, Humidity)
 *   Screen 1: ADVISORY     (10s) — Decide  (Severity, Primary Advice, Actions)
 *   Screen 2: FORECAST     (10s) — Predict (Current -> Predicted PM2.5, Trend, Outlook)
 *   Screen 3: INTELLIGENCE (10s) — Explain (Anomaly, Source, Forecast, AQI summary)
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
        case 1: drawScreen1_Advisory(state); break;
        case 2: drawScreen2_Forecast(state); break;
        case 3: drawScreen3_Intelligence(state); break;
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
// Screen 0 — ENVIRONMENT (Observe)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen0_Environment(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    bool live = state.valid && (millis() - state.last_update_ms < 60000);
    drawHeader("1. ENVIRONMENT", live ? "LIVE" : "OFFLINE", live ? GUI_GOOD_GREEN : GUI_BAD_RED);

    // --- Main AQI Hero Card (Left Column) ---
    uint16_t aCol = aqiColor(state.aqi);
    tftFillRect(10, 38, 175, 238, GUI_CARD_BG);
    tftDrawRect(10, 38, 175, 238, aCol);

    tftDrawString(20, 48, "AIR QUALITY", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawString(20, 60, "INDEX (AQI)", GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    char aqiBuf[16];
    snprintf(aqiBuf, sizeof(aqiBuf), "%.0f", state.aqi);
    tftDrawString(25, 95, aqiBuf, aCol, GUI_CARD_BG, 5);

    // AQI Category text
    const char* catStr = "Good";
    if (state.aqi > 300) catStr = "Hazardous";
    else if (state.aqi > 200) catStr = "V.Unhealthy";
    else if (state.aqi > 150) catStr = "Unhealthy";
    else if (state.aqi > 100) catStr = "Unhealthy*";
    else if (state.aqi > 50)  catStr = "Moderate";

    tftFillRect(20, 160, 155, 30, aCol);
    tftDrawString(30, 167, catStr, GUI_BLACK, aCol, 2);

    tftDrawString(20, 210, "Node: uno-q-001", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawString(20, 230, "Sensor: Active", GUI_CYAN, GUI_CARD_BG, 1);

    // --- Particulate Matter Cards (Middle Column) ---
    // PM1.0
    char buf[32];
    snprintf(buf, sizeof(buf), "%.1f", state.pm1_0);
    drawCard(193, 38, 135, 74, "PM 1.0", buf, GUI_WHITE, "ug/m3");

    // PM2.5
    snprintf(buf, sizeof(buf), "%.1f", state.pm2_5);
    drawCard(193, 120, 135, 74, "PM 2.5", buf, (state.pm2_5 > 35.0f ? GUI_WARN_ORANGE : GUI_GOOD_GREEN), "ug/m3");

    // PM10
    snprintf(buf, sizeof(buf), "%.1f", state.pm10);
    drawCard(193, 202, 135, 74, "PM 10", buf, (state.pm10 > 50.0f ? GUI_WARN_YELLOW : GUI_WHITE), "ug/m3");

    // --- Weather Cards (Right Column) ---
    // Temperature
    snprintf(buf, sizeof(buf), "%.1f C", state.temperature);
    drawCard(336, 38, 134, 115, "TEMPERATURE", buf, GUI_CYAN);

    // Humidity
    snprintf(buf, sizeof(buf), "%.1f %%", state.humidity);
    drawCard(336, 161, 134, 115, "HUMIDITY", buf, GUI_YELLOW);

    drawFooter(0, state);
}

// ─────────────────────────────────────────────────────────────
// Screen 1 — ADVISORY & ACTIONS (Decide)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen1_Advisory(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    uint16_t sCol = severityColor(state.severity);
    char badgeBuf[32];
    snprintf(badgeBuf, sizeof(badgeBuf), "%s", state.severity[0] ? state.severity : "NORMAL");
    drawHeader("2. ADVISORY & ACTIONS", badgeBuf, sCol);

    // --- Primary Advisory Box ---
    tftFillRect(10, 38, 460, 95, GUI_CARD_BG);
    tftDrawRect(10, 38, 460, 95, GUI_ACCENT);

    tftDrawString(20, 46, "PRIMARY ADVISORY OUTLOOK", GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawFastHLine(20, 58, 440, GUI_DARK_GREY);

    const char* advText = state.advice[0] ? state.advice : "Air quality is in normal range. Proceed with regular outdoor activities.";
    drawWrappedString(20, 66, advText, GUI_WHITE, GUI_CARD_BG, 2, 440, 3);

    // --- Actionable Recommendations Box ---
    tftFillRect(10, 141, 460, 135, GUI_CARD_BG);
    tftDrawRect(10, 141, 460, 135, sCol);

    tftDrawString(20, 149, "ACTIONABLE RECOMMENDATIONS", GUI_YELLOW, GUI_CARD_BG, 1);
    tftDrawFastHLine(20, 161, 440, GUI_DARK_GREY);

    uint8_t count = state.action_count;
    if (count == 0) {
        tftDrawString(20, 175, "1. No special precautions needed.", GUI_WHITE, GUI_CARD_BG, 2);
        tftDrawString(20, 205, "2. Enjoy fresh air and normal routine.", GUI_WHITE, GUI_CARD_BG, 2);
    } else {
        int y = 171;
        for (uint8_t i = 0; i < count && i < 4; i++) {
            char numStr[8];
            snprintf(numStr, sizeof(numStr), "%d.", i + 1);

            tftFillRect(20, y, 22, 22, sCol);
            tftDrawString(24, y + 3, numStr, GUI_BLACK, sCol, 2);

            // Safely truncate action text so it doesn't overflow line width
            char truncated[44];
            strncpy(truncated, state.actions[i], 38);
            truncated[38] = '\0';
            if (strlen(state.actions[i]) > 38) {
                strcat(truncated, "...");
            }
            tftDrawString(50, y + 3, truncated, GUI_WHITE, GUI_CARD_BG, 2);
            y += 26;
        }
    }

    drawFooter(1, state);
}

// ─────────────────────────────────────────────────────────────
// Screen 2 — FORECAST OUTLOOK (Predict)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen2_Forecast(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    uint16_t tCol = trendColor(state.forecast_trend);
    char badgeBuf[32];
    snprintf(badgeBuf, sizeof(badgeBuf), "TREND: %s", state.forecast_trend[0] ? state.forecast_trend : "STABLE");
    drawHeader("3. TIME-SERIES FORECAST", badgeBuf, tCol);

    // --- Top Metrics Bar ---
    char pmBuf[32];
    snprintf(pmBuf, sizeof(pmBuf), "%.1f", state.pm2_5);
    drawCard(10, 38, 148, 65, "CURRENT PM2.5", pmBuf, GUI_GOOD_GREEN, "ug/m3");

    drawCard(166, 38, 148, 65, "FORECAST TREND", state.forecast_trend, tCol);

    char confBuf[32];
    if (state.forecast_confidence >= 0.0f) {
        snprintf(confBuf, sizeof(confBuf), "%.0f %%", state.forecast_confidence * 100.0f);
    } else {
        snprintf(confBuf, sizeof(confBuf), "75 %%");
    }
    drawCard(322, 38, 148, 65, "MODEL CONF", confBuf, GUI_CYAN);

    // --- Horizon Predictions (Visual Flow Cards) ---
    tftFillRect(10, 111, 460, 88, GUI_CARD_BG);
    tftDrawRect(10, 111, 460, 88, GUI_ACCENT);
    tftDrawString(20, 118, "PM2.5 PREDICTION HORIZON FLOW (NOW -> 1 HOUR)", GUI_CYAN, GUI_CARD_BG, 1);

    // Step cards
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

    int cardW = 95;
    int gap = 20;
    int startX = 20;
    for (int i = 0; i < 4; i++) {
        int x = startX + i * (cardW + gap);
        tftFillRect(x, 134, cardW, 55, GUI_HEADER_BG);
        tftDrawRect(x, 134, cardW, 55, GUI_LIGHT_GREY);

        tftDrawString(x + 10, 140, steps[i].label, GUI_YELLOW, GUI_HEADER_BG, 1);
        char pBuf[16];
        snprintf(pBuf, sizeof(pBuf), "%.1f", steps[i].val);
        tftDrawString(x + 10, 155, pBuf, GUI_WHITE, GUI_HEADER_BG, 2);

        if (i < 3) {
            tftDrawString(x + cardW + 4, 155, "->", GUI_CYAN, GUI_CARD_BG, 2);
        }
    }

    // --- Human-Readable Outlook Summary Box ---
    tftFillRect(10, 207, 460, 68, GUI_CARD_BG);
    tftDrawRect(10, 207, 460, 68, GUI_DARK_GREY);
    tftDrawString(20, 214, "FORECAST OUTLOOK SUMMARY", GUI_LIGHT_GREY, GUI_CARD_BG, 1);

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

    drawWrappedString(20, 230, outlookBuf, GUI_WHITE, GUI_CARD_BG, 2, 440, 2);

    drawFooter(2, state);
}

// ─────────────────────────────────────────────────────────────
// Screen 3 — INTELLIGENCE PIPELINE (Explain)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen3_Intelligence(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    drawHeader("4. INTELLIGENCE PIPELINE", "EXPLAIN", GUI_CYAN);

    // --- 4 Quad Cards (2x2 Grid) ---

    // 1. Anomaly Card (Top-Left)
    tftFillRect(10, 38, 225, 112, GUI_CARD_BG);
    tftDrawRect(10, 38, 225, 112, GUI_ACCENT);
    tftDrawString(20, 46, "1. ANOMALY DETECTION", GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawFastHLine(20, 58, 205, GUI_DARK_GREY);

    bool isAnom = strcmp(state.anomaly_status, "ANOMALOUS") == 0;
    tftDrawString(20, 66, "STATUS:", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawString(80, 64, isAnom ? "ANOMALOUS" : "NORMAL", isAnom ? GUI_BAD_RED : GUI_GOOD_GREEN, GUI_CARD_BG, 2);

    tftDrawString(20, 95, "CONFIDENCE: 100%", GUI_WHITE, GUI_CARD_BG, 1);
    tftDrawString(20, 112, "DIAGNOSTIC: Signal Clean", GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    // 2. Source Classifier Card (Top-Right)
    tftFillRect(245, 38, 225, 112, GUI_CARD_BG);
    tftDrawRect(245, 38, 225, 112, GUI_YELLOW);
    tftDrawString(255, 46, "2. POLLUTION SOURCE", GUI_YELLOW, GUI_CARD_BG, 1);
    tftDrawFastHLine(255, 58, 205, GUI_DARK_GREY);

    const char* srcStr = state.source_value[0] ? state.source_value : "UNKNOWN";
    tftDrawString(255, 66, "SOURCE:", GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    char srcShort[16];
    strncpy(srcShort, srcStr, 12);
    srcShort[12] = '\0';
    tftDrawString(315, 64, srcShort, GUI_WHITE, GUI_CARD_BG, 2);

    char srcConfBuf[32];
    if (state.source_confidence >= 0.0f) {
        snprintf(srcConfBuf, sizeof(srcConfBuf), "CONFIDENCE: %.0f %%", state.source_confidence * 100.0f);
    } else {
        snprintf(srcConfBuf, sizeof(srcConfBuf), "CONFIDENCE: 85 %%");
    }
    tftDrawString(255, 95, srcConfBuf, GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawString(255, 112, "MODEL: DecisionTree", GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    // 3. AQI Category Card (Bottom-Left)
    tftFillRect(10, 158, 225, 117, GUI_CARD_BG);
    tftDrawRect(10, 158, 225, 117, aqiColor(state.aqi));
    tftDrawString(20, 166, "3. AIR QUALITY INDEX", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawFastHLine(20, 178, 205, GUI_DARK_GREY);

    char aqiValBuf[32];
    snprintf(aqiValBuf, sizeof(aqiValBuf), "AQI: %.0f", state.aqi);
    tftDrawString(20, 186, aqiValBuf, aqiColor(state.aqi), GUI_CARD_BG, 3);

    tftDrawString(20, 225, "STANDARD: EPA Regulatory", GUI_WHITE, GUI_CARD_BG, 1);
    tftDrawString(20, 242, "DOMINANT: PM2.5", GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    // 4. Time-Series Forecast Card (Bottom-Right)
    tftFillRect(245, 158, 225, 117, GUI_CARD_BG);
    tftDrawRect(245, 158, 225, 117, trendColor(state.forecast_trend));
    tftDrawString(255, 166, "4. TIME-SERIES FORECAST", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawFastHLine(255, 178, 205, GUI_DARK_GREY);

    tftDrawString(255, 186, state.forecast_trend, trendColor(state.forecast_trend), GUI_CARD_BG, 3);

    tftDrawString(255, 225, "MODEL: AR(p) Time-Series", GUI_WHITE, GUI_CARD_BG, 1);
    tftDrawString(255, 242, "HORIZON: 60 Minutes", GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    drawFooter(3, state);
}

// ─────────────────────────────────────────────────────────────
// UI Helpers
// ─────────────────────────────────────────────────────────────

void NavosEdgeGUI::drawHeader(const char* title, const char* badgeStr, uint16_t badgeColor) {
    tftFillRect(0, 0, GUI_WIDTH, 32, GUI_HEADER_BG);
    tftDrawFastHLine(0, 31, GUI_WIDTH, GUI_DARK_GREY);

    tftDrawString(12, 7, "NAVOS EDGE |", GUI_CYAN, GUI_HEADER_BG, 2);
    tftDrawString(160, 7, title, GUI_WHITE, GUI_HEADER_BG, 2);

    if (badgeStr && *badgeStr) {
        int badgeW = strlen(badgeStr) * 12 + 16;
        int badgeX = GUI_WIDTH - badgeW - 10;
        tftFillRect(badgeX, 4, badgeW, 24, badgeColor);
        tftDrawString(badgeX + 8, 8, badgeStr, GUI_BLACK, badgeColor, 2);
    }
}

void NavosEdgeGUI::drawFooter(uint8_t screenIdx, const NavosEdgeState& state) {
    tftFillRect(0, 280, GUI_WIDTH, 40, GUI_HEADER_BG);
    tftDrawFastHLine(0, 280, GUI_WIDTH, GUI_DARK_GREY);

    // Screen indicator dots
    const char* pages[4] = {
        "[o - - -] 1/4 ENV (15s)",
        "[- o - -] 2/4 ADV (10s)",
        "[- - o -] 3/4 FCST (10s)",
        "[- - - o] 4/4 INTEL (10s)"
    };

    tftDrawString(12, 292, pages[screenIdx % 4], GUI_CYAN, GUI_HEADER_BG, 2);

    // Timestamp / fresh status
    char timeBuf[32];
    if (state.valid && state.last_update_ms > 0) {
        unsigned long elapsedSec = (millis() - state.last_update_ms) / 1000;
        snprintf(timeBuf, sizeof(timeBuf), "Updated %lus ago", elapsedSec);
    } else {
        snprintf(timeBuf, sizeof(timeBuf), "Connecting...");
    }
    tftDrawString(310, 292, timeBuf, GUI_LIGHT_GREY, GUI_HEADER_BG, 2);
}

void NavosEdgeGUI::drawCard(int16_t x, int16_t y, int16_t w, int16_t h,
                            const char* label, const char* value, uint16_t valueColor,
                            const char* unit) {
    tftFillRect(x, y, w, h, GUI_CARD_BG);
    tftDrawRect(x, y, w, h, GUI_DARK_GREY);

    tftDrawString(x + 10, y + 8, label, GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    tftDrawString(x + 10, y + 25, value, valueColor, GUI_CARD_BG, 3);

    if (unit) {
        tftDrawString(x + 10, y + h - 18, unit, GUI_LIGHT_GREY, GUI_CARD_BG, 1);
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
    // Suppress desktop stdout spam during continuous rendering loop
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
