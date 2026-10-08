/**
 * NavosEdgeGUI.cpp — 5-Screen Structural Display Renderer for MPI3501 3.5" (480×320 landscape).
 *
 * Sequence:
 *   Screen 0: ENVIRONMENT            (20s) — AQI hero, PM bars, Temp, Humidity, Status, dust anim
 *   Screen 1: ADVICE + ACTIONS       (15s) — Advisory text & Action items list
 *   Screen 2: FORECAST               (15s) — Trend, Forecast Trend, Model Confidence, Step Flow, Outlook
 *   Screen 3: MODEL CONFIDENCE SCORE (15s) — 2x2 grid: Anomaly, Source, AQ, Forecast
 *   Screen 4: RAW SENSOR READINGS    (15s) — Debugging view: PMs, DHT22, MQ2/MQ9/MQ135 ADC+Volt, AQ
 */

#include "NavosEdgeGUI.h"
#include <stdio.h>
#include <string.h>

NavosEdgeGUI::NavosEdgeGUI()
    : _currentScreen(0),
      _lastRotateMs(0),
      _lastDrawnScreen(255),
      _needsFullRedraw(true),
      _dustCount(0),
      _dustLastMs(0),
      _dustRng(12345) {
    navosStateInit(_lastDrawnState);
    for (uint8_t i = 0; i < DUST_MAX_PARTICLES; i++) {
        _dust[i].active = false;
        _dustPrevX[i] = 0;
        _dustPrevY[i] = 0;
    }
}

void NavosEdgeGUI::setYieldCallback(void (*cb)()) {
    _yieldCb = cb;
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

    unsigned long now = millis();

    if (_lastDrawnScreen == 254) {
        _needsFullRedraw = true;
        _lastRotateMs = now; // Reset rotation timer on startup so Screen 0 gets its full duration
    }

    // Per-screen duration timing (User requested 40 seconds per screen)
    uint32_t durationMs = 40000;

    if (now - _lastRotateMs >= durationMs) {
        _currentScreen = (_currentScreen + 1) % GUI_NUM_SCREENS;
        _lastRotateMs = now;
        _needsFullRedraw = true;
    }

    bool screenChanged = (_currentScreen != _lastDrawnScreen);

    if (_needsFullRedraw || screenChanged) {
        forceRedraw(state);
    }

    // Non-blocking dust particle animation on the Environment screen
    if (_currentScreen == 0 && _dustCount > 0) {
        if (now - _dustLastMs >= DUST_ANIM_INTERVAL_MS) {
            _dustLastMs = now;
            dustTick();
        }
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
// Dust Particle System (lightweight procedural animation)
// ─────────────────────────────────────────────────────────────

uint16_t NavosEdgeGUI::dustRand() {
    _dustRng ^= _dustRng << 7;
    _dustRng ^= _dustRng >> 9;
    _dustRng ^= _dustRng << 8;
    return (uint16_t)(_dustRng & 0xFFFF);
}

void NavosEdgeGUI::dustInit(float aqi) {
    // Determine particle count from AQI
    uint8_t target = 0;
    if (aqi <= 30.0f) {
        target = 0;           // very clean — no particles
    } else if (aqi <= 50.0f) {
        target = 2;           // good — barely visible
    } else if (aqi <= 100.0f) {
        target = 6;           // moderate — sparse
    } else if (aqi <= 150.0f) {
        target = 12;          // unhealthy-sensitive — visible
    } else if (aqi <= 200.0f) {
        target = 18;          // unhealthy — noticeable
    } else if (aqi <= 300.0f) {
        target = 24;          // very unhealthy — dense
    } else {
        target = DUST_MAX_PARTICLES; // hazardous — maximum
    }

    if (target > DUST_MAX_PARTICLES) target = DUST_MAX_PARTICLES;
    _dustCount = target;

    // Seed initial positions spread across the background area (y=34..319)
    _dustRng = (uint32_t)(aqi * 137 + millis());
    for (uint8_t i = 0; i < DUST_MAX_PARTICLES; i++) {
        if (i < _dustCount) {
            _dust[i].active = true;
            _dust[i].x = dustRand() % GUI_WIDTH;
            _dust[i].y = 34 + (dustRand() % (GUI_HEIGHT - 34));
            // Random slow drift direction
            _dust[i].dx = (int8_t)((dustRand() % 3) - 1);  // -1, 0, +1
            _dust[i].dy = (int8_t)((dustRand() % 3) - 1);
            if (_dust[i].dx == 0 && _dust[i].dy == 0) _dust[i].dx = 1;
        } else {
            _dust[i].active = false;
        }
        _dustPrevX[i] = _dust[i].x;
        _dustPrevY[i] = _dust[i].y;
    }

    _dustLastMs = millis();
}

void NavosEdgeGUI::dustTick() {
    for (uint8_t i = 0; i < _dustCount; i++) {
        if (!_dust[i].active) continue;

        // Erase old position with background color (single pixel)
        tftDrawPixel(_dustPrevX[i], _dustPrevY[i], GUI_BG_COLOR);

        // Move particle
        _dust[i].x += _dust[i].dx;
        _dust[i].y += _dust[i].dy;

        // Wrap around display edges (below header y=34)
        if (_dust[i].x < 0) _dust[i].x = GUI_WIDTH - 1;
        if (_dust[i].x >= GUI_WIDTH) _dust[i].x = 0;
        if (_dust[i].y < 34) _dust[i].y = GUI_HEIGHT - 1;
        if (_dust[i].y >= GUI_HEIGHT) _dust[i].y = 34;

        // Occasionally change direction for natural drift
        if ((dustRand() % 12) == 0) {
            _dust[i].dx = (int8_t)((dustRand() % 3) - 1);
            _dust[i].dy = (int8_t)((dustRand() % 3) - 1);
            if (_dust[i].dx == 0 && _dust[i].dy == 0) _dust[i].dy = 1;
        }

        // Save for next erase
        _dustPrevX[i] = _dust[i].x;
        _dustPrevY[i] = _dust[i].y;

        // Draw new position (single pixel)
        tftDrawPixel(_dust[i].x, _dust[i].y, GUI_DUST_COLOR);
    }
}

void NavosEdgeGUI::dustErase() {
    for (uint8_t i = 0; i < DUST_MAX_PARTICLES; i++) {
        if (_dust[i].active) {
            tftDrawPixel(_dustPrevX[i], _dustPrevY[i], GUI_BG_COLOR);
        }
        _dust[i].active = false;
    }
    _dustCount = 0;
}

// ─────────────────────────────────────────────────────────────
// Screen 0 — ENVIRONMENT (Screen 1 in specifications)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::drawScreen0_Environment(const NavosEdgeState& state) {
    tftFillScreen(GUI_BG_COLOR);

    bool live = state.valid && (millis() - state.last_update_ms < 60000);
    drawHeader("ENVIRONMENT");

    // Initialize dust particles based on AQI
    dustInit(state.aqi);

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

    if (_yieldCb) _yieldCb();

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
    // Bottom Left: Temperature Panel — LABEL stays small, VALUE is large
    snprintf(buf, sizeof(buf), "%.1f C", state.temperature);
    drawLargeValueCard(6, 185, 150, 130, "TEMPERATURE", buf, GUI_CYAN, "Celsius");

    if (_yieldCb) _yieldCb();

    // Bottom Middle: Humidity Panel — LABEL stays small, VALUE is large
    snprintf(buf, sizeof(buf), "%.1f %%", state.humidity);
    drawLargeValueCard(165, 185, 150, 130, "HUMIDITY", buf, GUI_YELLOW, "Relative Hum");

    // Bottom Right: Additional Small Panel
    tftFillRect(324, 185, 150, 130, GUI_CARD_BG);
    tftDrawRect(324, 185, 150, 130, GUI_CARD_BORDER);
    tftDrawString(334, 193, "NODE STATUS", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawString(334, 215, "uno-q-001", GUI_WHITE, GUI_CARD_BG, 2);
    tftDrawString(334, 250, live ? "Active" : "Offline", live ? GUI_GOOD_GREEN : GUI_BAD_RED, GUI_CARD_BG, 2);
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
    // Advisory text: size 1 for slightly smaller, clean, compact display
    uint8_t advSize = 1;
    drawWrappedString(16, 58, advText, GUI_WHITE, GUI_CARD_BG, advSize, 448, 4);

    if (_yieldCb) _yieldCb();

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
    // STATUS card: label stays size 1, trend VALUE is enlarged to size 3
    {
        int16_t cx = 6, cy = 34, cw = 150, ch = 68;
        tftFillRect(cx, cy, cw, ch, GUI_CARD_BG);
        tftDrawRect(cx, cy, cw, ch, GUI_CARD_BORDER);

        // Small label
        tftDrawString(cx + 10, cy + 6, "STATUS", GUI_LIGHT_GREY, GUI_CARD_BG, 1);

        // Large trend value (size 3, adaptive fallback)
        const char* trendVal = state.forecast_trend[0] ? state.forecast_trend : "STABLE";
        drawAdaptiveString(cx + 10, cy + 24, trendVal, tCol, GUI_CARD_BG, 3, cw - 20, 30);
    }

    drawCard(165, 34, 150, 68, "TREND DIRECTION", "+15M -> +60M", GUI_CYAN);

    char confBuf[32];
    if (state.forecast_confidence >= 0.0f) {
        snprintf(confBuf, sizeof(confBuf), "%.0f %%", state.forecast_confidence * 100.0f);
    } else {
        snprintf(confBuf, sizeof(confBuf), "-- %%");
    }
    drawCard(324, 34, 150, 68, "MODEL CONFIDENCE", confBuf, GUI_YELLOW);

    if (_yieldCb) _yieldCb();

    // --- Middle Panel: Forecast readings → ---
    tftFillRect(6, 108, 468, 100, GUI_CARD_BG);
    tftDrawRect(6, 108, 468, 100, GUI_ACCENT);
    tftDrawString(16, 114, "FORECAST READINGS (PM2.5 ug/m3)", GUI_CYAN, GUI_CARD_BG, 1);

    float val0 = state.pm2_5;
    float val1 = (state.forecast_pm2_5_count > 0 && state.forecast_pm2_5_pred[0] >= 0.0f) ? state.forecast_pm2_5_pred[0] : -1.0f;
    float val2 = (state.forecast_pm2_5_count > 1 && state.forecast_pm2_5_pred[1] >= 0.0f) ? state.forecast_pm2_5_pred[1] : -1.0f;
    float val3 = (state.forecast_pm2_5_count > 2 && state.forecast_pm2_5_pred[2] >= 0.0f) ? state.forecast_pm2_5_pred[2] : -1.0f;

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
        if (steps[i].val >= 0.0f) {
            snprintf(pBuf, sizeof(pBuf), "%.1f", steps[i].val);
        } else {
            snprintf(pBuf, sizeof(pBuf), "--");
        }
        drawAdaptiveString(x + 6, 154, pBuf, GUI_WHITE, GUI_HEADER_BG, 2, boxW - 12, 16);

        if (i < 3) {
            tftDrawString(x + boxW + 4, 154, "->", GUI_CYAN, GUI_CARD_BG, 2);
        }
    }

    if (_yieldCb) _yieldCb();

    // --- Bottom Panel: Forecast outlook summary ---
    tftFillRect(6, 214, 468, 101, GUI_CARD_BG);
    tftDrawRect(6, 214, 468, 101, GUI_CARD_BORDER);
    tftDrawString(16, 220, "FORECAST OUTLOOK SUMMARY", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawFastHLine(16, 232, 448, GUI_DARK_GREY);

    char outlookBuf[160];
    if (state.forecast_outlook[0]) {
        snprintf(outlookBuf, sizeof(outlookBuf), "%s", state.forecast_outlook);
    } else if (val3 >= 0.0f && strcmp(state.forecast_trend, "RISING") == 0) {
        snprintf(outlookBuf, sizeof(outlookBuf), "PM2.5 forecasted to increase by +%.1f ug/m3 over next hour. Early precautions recommended.", val3 - val0);
    } else if (val3 >= 0.0f && strcmp(state.forecast_trend, "FALLING") == 0) {
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
// DO NOT MODIFY — left exactly as-is per requirement
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

    if (_yieldCb) _yieldCb();

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
        snprintf(srcConfBuf, sizeof(srcConfBuf), "-- %%");
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
        snprintf(fcConfBuf, sizeof(fcConfBuf), "CONFIDENCE: -- %%");
    }
    drawAdaptiveString(254, 245, fcConfBuf, GUI_WHITE, GUI_CARD_BG, 1, 208, 16);

    drawStatusBadge("SCORES", GUI_CYAN);
}

// ─────────────────────────────────────────────────────────────
// Screen 4 — RAW SENSOR READINGS (Screen 5 in specifications)
// Labels stay size 1.  Values bumped to size 2 with adaptive fallback.
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

    // Label size 1, value size 2 (on separate lines)
    tftDrawString(14, 60, "PM1.0", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "%.1f", state.pm1_0);
    drawAdaptiveString(14, 72, buf, GUI_WHITE, GUI_CARD_BG, 2, 129, 20);

    tftDrawString(14, 96, "PM2.5", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "%.1f", state.pm2_5);
    drawAdaptiveString(14, 108, buf, GUI_WHITE, GUI_CARD_BG, 2, 129, 20);

    tftDrawString(14, 132, "PM10", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "%.1f", state.pm10);
    drawAdaptiveString(14, 144, buf, GUI_WHITE, GUI_CARD_BG, 2, 129, 20);

    // Left-Lower Panel: Humidity, Temperature
    tftFillRect(6, 176, 145, 136, GUI_CARD_BG);
    tftDrawRect(6, 176, 145, 136, GUI_CARD_BORDER);
    tftDrawString(14, 184, "DHT22 SENSOR", GUI_YELLOW, GUI_CARD_BG, 1);
    tftDrawFastHLine(14, 196, 129, GUI_DARK_GREY);

    tftDrawString(14, 204, "Humidity", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "%.1f %%", state.humidity);
    drawAdaptiveString(14, 216, buf, GUI_WHITE, GUI_CARD_BG, 2, 129, 20);

    tftDrawString(14, 244, "Temperature", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "%.1f C", state.temperature);
    drawAdaptiveString(14, 256, buf, GUI_WHITE, GUI_CARD_BG, 2, 129, 20);

    // --- Center Panel: MQ Gas Sensors (MQ2, MQ9, MQ135 ADC & Voltage) ---
    tftFillRect(157, 34, 168, 278, GUI_CARD_BG);
    tftDrawRect(157, 34, 168, 278, GUI_ACCENT);
    tftDrawString(165, 42, "MQ GAS SENSORS", GUI_CYAN, GUI_CARD_BG, 1);
    tftDrawFastHLine(165, 54, 152, GUI_DARK_GREY);

    // MQ2 — label size 1, values size 2
    tftDrawString(165, 62, "MQ2 (Combustible)", GUI_YELLOW, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "ADC: %u", state.mq2_adc);
    drawAdaptiveString(165, 76, buf, GUI_WHITE, GUI_CARD_BG, 2, 152, 16);
    snprintf(buf, sizeof(buf), "V: %.2f", state.mq2_voltage);
    drawAdaptiveString(165, 96, buf, GUI_LIGHT_GREY, GUI_CARD_BG, 2, 152, 16);

    tftDrawFastHLine(165, 116, 152, GUI_DARK_GREY);

    // MQ9 — label size 1, values size 2
    tftDrawString(165, 124, "MQ9 (Carbon Mono)", GUI_YELLOW, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "ADC: %u", state.mq9_adc);
    drawAdaptiveString(165, 138, buf, GUI_WHITE, GUI_CARD_BG, 2, 152, 16);
    snprintf(buf, sizeof(buf), "V: %.2f", state.mq9_voltage);
    drawAdaptiveString(165, 158, buf, GUI_LIGHT_GREY, GUI_CARD_BG, 2, 152, 16);

    tftDrawFastHLine(165, 178, 152, GUI_DARK_GREY);

    // MQ135 — label size 1, values size 2
    tftDrawString(165, 186, "MQ135 (Air Qual)", GUI_YELLOW, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "ADC: %u", state.mq135_adc);
    drawAdaptiveString(165, 200, buf, GUI_WHITE, GUI_CARD_BG, 2, 152, 16);
    snprintf(buf, sizeof(buf), "V: %.2f", state.mq135_voltage);
    drawAdaptiveString(165, 220, buf, GUI_LIGHT_GREY, GUI_CARD_BG, 2, 152, 16);

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

void NavosEdgeGUI::drawLargeValueCard(int16_t x, int16_t y, int16_t w, int16_t h,
                                      const char* label, const char* value, uint16_t valueColor,
                                      const char* unit) {
    tftFillRect(x, y, w, h, GUI_CARD_BG);
    tftDrawRect(x, y, w, h, GUI_CARD_BORDER);

    // Label stays size 1
    tftDrawString(x + 10, y + 8, label, GUI_LIGHT_GREY, GUI_CARD_BG, 1);

    // Value rendered at size 3, with adaptive fallback to 2 then 1
    drawAdaptiveString(x + 10, y + 28, value, valueColor, GUI_CARD_BG, 3, w - 20, 30);

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
    // 320 rows total. If 320 rows take ~10.2s, 1 row takes ~32ms.
    // Chunking by 1 row guarantees we yield every ~32ms, well within 50ms safety margin.
    for (int16_t y = 0; y < GUI_HEIGHT; y += 1) {
        _tft.fillRect(0, y, GUI_WIDTH, 1, color);
        if (_yieldCb) _yieldCb();
    }
#else
    (void)color;
#endif
}

void NavosEdgeGUI::tftFillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) {
#ifdef ARDUINO
    for (int16_t r = 0; r < h; r++) {
        _tft.fillRect(x, y + r, w, 1, color);
        if (_yieldCb) _yieldCb();
    }
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

void NavosEdgeGUI::tftDrawPixel(int16_t x, int16_t y, uint16_t color) {
#ifdef ARDUINO
    _tft.drawPixel(x, y, color);
#else
    (void)x; (void)y; (void)color;
#endif
}
