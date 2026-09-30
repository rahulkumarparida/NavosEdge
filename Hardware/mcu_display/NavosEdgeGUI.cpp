/**
 * NavosEdgeGUI.cpp — Display renderer for the MPI3501 3.5" 480×320 screen on MCU.
 *
 * Renders three screens using the UNOQ_MPI3501 standalone driver:
 *   Screen 0: Environment dashboard (AQI, PM values, Temp, Humidity)
 *   Screen 1: Advisory text (severity, advice, weather advice)
 *   Screen 2: Actions (actionable recommendations list)
 *
 * All display functions verified against the UNOQ_MPI3501 API:
 *   begin(), setRotation(), fillScreen(), fillRect(), drawRect(),
 *   drawString(), drawFastHLine(), drawFastVLine(), drawLine()
 *
 * Font: Built-in 5×7 monospace. size=1→6px wide, size=2→12px, size=3→18px
 */

#include "NavosEdgeGUI.h"
#include <stdio.h>
#include <string.h>

// ─────────────────────────────────────────────────────────────
// Constructor
// ─────────────────────────────────────────────────────────────
NavosEdgeGUI::NavosEdgeGUI()
    : _currentScreen(0)
    , _lastRotateMs(0)
    , _lastDrawnScreen(255) // Force initial draw
    , _needsFullRedraw(true)
{
    navosStateInit(_lastDrawnState);
}

// ─────────────────────────────────────────────────────────────
// Initialization
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::begin() {
#ifdef ARDUINO
    _tft.begin();           // Initialize ILI9486 via SPI
    _tft.setRotation(1);    // Landscape: 480×320
#else
    printf("[GUI] Display initialized (simulation mode: %dx%d)\n",
           GUI_WIDTH, GUI_HEIGHT);
#endif
    tftFillScreen(GUI_BG_COLOR);
    _lastRotateMs = millis();
}

// ─────────────────────────────────────────────────────────────
// Main update loop (non-blocking)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::update(const NavosEdgeState& state) {
    if (!state.valid) {
        if (_needsFullRedraw || _lastDrawnScreen != 254) {
            showStatus("NavosEdge MCU", "Waiting for NavosEdge...");
            _lastDrawnScreen = 254;
            _needsFullRedraw = false;
        }
        return;
    }

    if (_lastDrawnScreen == 254) {
        _needsFullRedraw = true;
    }

    unsigned long now = millis();

    // Check if it's time to rotate screens
    if (now - _lastRotateMs >= NAVOS_SCREEN_ROTATE_MS) {
        _lastRotateMs = now;
        _currentScreen = (_currentScreen + 1) % GUI_NUM_SCREENS;
        _needsFullRedraw = true;
    }

    // Check if data changed for the current screen
    bool dataChanged = navosStateChanged(state, _lastDrawnState);

    // Only redraw if screen changed or data changed
    if (_needsFullRedraw || (_currentScreen == _lastDrawnScreen && dataChanged)) {
        forceRedraw(state);
    }
}

void NavosEdgeGUI::forceRedraw(const NavosEdgeState& state) {
#ifdef ARDUINO
    Serial.println(F("[DISPLAY] MPI3501 rendering new data"));
#else
    printf("[DISPLAY] MPI3501 rendering new data\n");
#endif
    tftFillScreen(GUI_BG_COLOR);

    switch (_currentScreen) {
        case 0: drawScreen0_Environment(state); break;
        case 1: drawScreen1_Advice(state);      break;
        case 2: drawScreen2_Actions(state);     break;
    }

    drawFooter(state);

    // Remember what we drew
    memcpy(&_lastDrawnState, &state, sizeof(NavosEdgeState));
    _lastDrawnScreen = _currentScreen;
    _needsFullRedraw = false;
}

uint8_t NavosEdgeGUI::getCurrentScreen() const {
    return _currentScreen;
}

// ─────────────────────────────────────────────────────────────
// Show status message (for startup / errors)
// ─────────────────────────────────────────────────────────────
void NavosEdgeGUI::showStatus(const char* line1, const char* line2) {
    tftFillScreen(GUI_BG_COLOR);
    tftDrawString(20, 130, line1, GUI_WHITE, GUI_BG_COLOR, 2);
    if (line2) {
        tftDrawString(20, 160, line2, GUI_LIGHT_GREY, GUI_BG_COLOR, 2);
    }
}

// ═════════════════════════════════════════════════════════════
// SCREEN 0 — Environment Dashboard
// ═════════════════════════════════════════════════════════════
void NavosEdgeGUI::drawScreen0_Environment(const NavosEdgeState& state) {
    drawHeader("ENVIRONMENT", GUI_ACCENT);

    // ── AQI — large prominent display ──
    char buf[32];

    // AQI value box
    tftFillRect(10, 40, 140, 80, GUI_CARD_BG);
    tftDrawRect(10, 40, 140, 80, aqiColor(state.aqi));
    tftDrawString(20, 45, "AQI", GUI_LIGHT_GREY, GUI_CARD_BG, 2);
    snprintf(buf, sizeof(buf), "%.0f", state.aqi);
    tftDrawString(30, 72, buf, aqiColor(state.aqi), GUI_CARD_BG, 3);

    // ── PM Values — right side cards ──
    // PM1.0
    snprintf(buf, sizeof(buf), "%.1f", state.pm1_0);
    drawCard(160, 40, 150, 36, "PM1.0", buf, GUI_CYAN);

    // PM2.5
    snprintf(buf, sizeof(buf), "%.1f", state.pm2_5);
    drawCard(160, 82, 150, 36, "PM2.5", buf, GUI_YELLOW);

    // PM10
    snprintf(buf, sizeof(buf), "%.1f", state.pm10);
    drawCard(320, 40, 150, 36, "PM10", buf, GUI_ORANGE);

    // ── Temp & Humidity — bottom row ──
    // Temperature card
    tftFillRect(10, 135, 225, 70, GUI_CARD_BG);
    tftDrawRect(10, 135, 225, 70, GUI_DARK_GREY);
    tftDrawString(20, 142, "TEMPERATURE", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "%.1f C", state.temperature);
    tftDrawString(20, 160, buf, GUI_WHITE, GUI_CARD_BG, 3);

    // Draw a small degree symbol approximation
    tftFillRect(20 + (int)(strlen(buf) - 2) * 18, 158, 4, 4, GUI_WHITE);
    tftDrawRect(20 + (int)(strlen(buf) - 2) * 18, 158, 4, 4, GUI_CARD_BG);

    // Humidity card
    tftFillRect(245, 135, 225, 70, GUI_CARD_BG);
    tftDrawRect(245, 135, 225, 70, GUI_DARK_GREY);
    tftDrawString(255, 142, "HUMIDITY", GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    snprintf(buf, sizeof(buf), "%.1f %%", state.humidity);
    tftDrawString(255, 160, buf, GUI_CYAN, GUI_CARD_BG, 3);

    // ── PM Progress bars ──
    int barY = 215;
    tftDrawString(10, barY, "PM 2.5", GUI_LIGHT_GREY, GUI_BG_COLOR, 1);
    drawProgressBar(70, barY + 2, 170, 8, state.pm2_5, 300.0f, GUI_YELLOW);

    tftDrawString(260, barY, "PM 10", GUI_LIGHT_GREY, GUI_BG_COLOR, 1);
    drawProgressBar(310, barY + 2, 160, 8, state.pm10, 500.0f, GUI_ORANGE);

    // ── Unit labels ──
    tftDrawString(10, 230, "ug/m3", GUI_DARK_GREY, GUI_BG_COLOR, 1);
}

// ═════════════════════════════════════════════════════════════
// SCREEN 1 — Advice
// ═════════════════════════════════════════════════════════════
void NavosEdgeGUI::drawScreen1_Advice(const NavosEdgeState& state) {
    uint16_t sevColor = severityColor(state.severity);
    drawHeader("ADVISORY", sevColor);

    // Severity badge
    int badgeW = strlen(state.severity) * 12 + 20;
    if (badgeW < 80) badgeW = 80;
    tftFillRect(10, 40, badgeW, 28, sevColor);
    tftDrawString(20, 45, state.severity, GUI_BLACK, sevColor, 2);

    // Main advice text — word-wrapped
    int16_t textY = 80;
    if (state.advice[0]) {
        tftDrawString(10, textY, "Advice:", GUI_LIGHT_GREY, GUI_BG_COLOR, 1);
        textY += 12;
        textY = drawWrappedString(10, textY, state.advice,
                                   GUI_WHITE, GUI_BG_COLOR, 2, 460);
        textY += 10;
    }

    // Separator line
    tftDrawFastHLine(10, textY, 460, GUI_DARK_GREY);
    textY += 8;

    // Weather advice — word-wrapped
    if (state.weather_advice[0]) {
        tftDrawString(10, textY, "Weather:", GUI_LIGHT_GREY, GUI_BG_COLOR, 1);
        textY += 12;
        drawWrappedString(10, textY, state.weather_advice,
                          GUI_CYAN, GUI_BG_COLOR, 2, 460);
    }
}

// ═════════════════════════════════════════════════════════════
// SCREEN 2 — Actions
// ═════════════════════════════════════════════════════════════
void NavosEdgeGUI::drawScreen2_Actions(const NavosEdgeState& state) {
    drawHeader("ACTIONS", GUI_GREEN);

    if (state.action_count == 0) {
        tftDrawString(20, 100, "No actions available", GUI_LIGHT_GREY, GUI_BG_COLOR, 2);
        tftDrawString(20, 130, "Waiting for server...", GUI_DARK_GREY, GUI_BG_COLOR, 2);
        return;
    }

    // Calculate spacing — fit actions evenly
    int availableHeight = 260;    // 320 - header(36) - footer(24)
    int itemHeight = availableHeight / (state.action_count > 6 ? 6 : state.action_count);
    if (itemHeight < 30) itemHeight = 30;
    if (itemHeight > 50) itemHeight = 50;

    int16_t y = 42;
    for (uint8_t i = 0; i < state.action_count && i < 6; i++) {
        // Action number badge
        char numBuf[4];
        snprintf(numBuf, sizeof(numBuf), "%d", i + 1);
        tftFillRect(10, y, 24, 24, GUI_GREEN);
        tftDrawString(14, y + 4, numBuf, GUI_BLACK, GUI_GREEN, 2);

        // Action text — truncate to fit one line if needed
        char truncated[42];
        int maxChars = 37;
        if ((int)strlen(state.actions[i]) > maxChars) {
            strncpy(truncated, state.actions[i], maxChars - 3);
            truncated[maxChars - 3] = '.';
            truncated[maxChars - 2] = '.';
            truncated[maxChars - 1] = '.';
            truncated[maxChars] = '\0';
        } else {
            strncpy(truncated, state.actions[i], sizeof(truncated) - 1);
            truncated[sizeof(truncated) - 1] = '\0';
        }

        tftDrawString(42, y + 4, truncated, GUI_WHITE, GUI_BG_COLOR, 2);

        // Subtle separator
        if (i < state.action_count - 1) {
            tftDrawFastHLine(42, y + itemHeight - 4, 420, GUI_DARK_GREY);
        }

        y += itemHeight;
    }

    // Show overflow indicator if more than 6 actions
    if (state.action_count > 6) {
        char moreBuf[24];
        snprintf(moreBuf, sizeof(moreBuf), "+%d more actions", state.action_count - 6);
        tftDrawString(42, y + 4, moreBuf, GUI_DARK_GREY, GUI_BG_COLOR, 1);
    }
}

// ═════════════════════════════════════════════════════════════
// UI Component Helpers
// ═════════════════════════════════════════════════════════════

void NavosEdgeGUI::drawHeader(const char* title, uint16_t accentColor) {
    // Header background
    tftFillRect(0, 0, GUI_WIDTH, 34, GUI_HEADER_BG);

    // Accent bar at top
    tftFillRect(0, 0, GUI_WIDTH, 3, accentColor);

    // Title
    tftDrawString(10, 10, title, GUI_WHITE, GUI_HEADER_BG, 2);

    // NavosEdge branding — right aligned
    tftDrawString(350, 14, "NavosEdge", GUI_DARK_GREY, GUI_HEADER_BG, 1);

    // Screen indicator dots
    for (uint8_t i = 0; i < GUI_NUM_SCREENS; i++) {
        int dotX = 440 + i * 12;
        if (i == _currentScreen) {
            tftFillRect(dotX, 14, 8, 8, accentColor);
        } else {
            tftDrawRect(dotX, 14, 8, 8, GUI_DARK_GREY);
        }
    }
}

void NavosEdgeGUI::drawFooter(const NavosEdgeState& state) {
    int footerY = GUI_HEIGHT - 22;

    // Footer separator
    tftDrawFastHLine(0, footerY - 2, GUI_WIDTH, GUI_DARK_GREY);

    // Connection status
    if (state.valid) {
        tftFillRect(10, footerY + 2, 8, 8, GUI_GREEN);
        tftDrawString(22, footerY + 2, "LIVE", GUI_GREEN, GUI_BG_COLOR, 1);
    } else {
        tftFillRect(10, footerY + 2, 8, 8, GUI_RED);
        tftDrawString(22, footerY + 2, "OFFLINE", GUI_RED, GUI_BG_COLOR, 1);
    }

    // Data age indicator
    if (state.valid && state.last_update_ms > 0) {
        unsigned long age = (millis() - state.last_update_ms) / 1000;
        char ageBuf[24];
        if (age < 60) {
            snprintf(ageBuf, sizeof(ageBuf), "%lus ago", age);
        } else {
            snprintf(ageBuf, sizeof(ageBuf), "%lum ago", age / 60);
        }
        tftDrawString(380, footerY + 2, ageBuf, GUI_DARK_GREY, GUI_BG_COLOR, 1);
    }

    // Screen indicator text
    char screenBuf[12];
    snprintf(screenBuf, sizeof(screenBuf), "%d/%d", _currentScreen + 1, GUI_NUM_SCREENS);
    tftDrawString(220, footerY + 2, screenBuf, GUI_DARK_GREY, GUI_BG_COLOR, 1);
}

void NavosEdgeGUI::drawCard(int16_t x, int16_t y, int16_t w, int16_t h,
                             const char* label, const char* value,
                             uint16_t valueColor) {
    tftFillRect(x, y, w, h, GUI_CARD_BG);
    tftDrawRect(x, y, w, h, GUI_DARK_GREY);
    tftDrawString(x + 8, y + 4, label, GUI_LIGHT_GREY, GUI_CARD_BG, 1);
    tftDrawString(x + 8, y + 16, value, valueColor, GUI_CARD_BG, 2);
}

void NavosEdgeGUI::drawProgressBar(int16_t x, int16_t y, int16_t w, int16_t h,
                                    float value, float maxVal, uint16_t color) {
    // Background
    tftFillRect(x, y, w, h, GUI_DARK_GREY);
    // Filled portion
    int fillW = (int)(value / maxVal * w);
    if (fillW > w) fillW = w;
    if (fillW < 0) fillW = 0;
    if (fillW > 0) {
        tftFillRect(x, y, fillW, h, color);
    }
}

int16_t NavosEdgeGUI::drawWrappedString(int16_t x, int16_t y, const char* str,
                                         uint16_t color, uint16_t bg, uint8_t size,
                                         int16_t maxWidth) {
    if (!str || !*str) return y;

    int charWidth = 6 * size;  // 5px char + 1px gap, scaled by size
    int lineHeight = 8 * size; // 7px char + 1px gap, scaled
    int maxChars = maxWidth / charWidth;

    if (maxChars < 1) maxChars = 1;

    int len = strlen(str);
    int pos = 0;

    while (pos < len && y < GUI_HEIGHT - 30) {
        // Find break point — prefer word boundary
        int lineEnd = pos + maxChars;
        if (lineEnd >= len) {
            lineEnd = len;
        } else {
            // Try to break at last space within maxChars
            int lastSpace = -1;
            for (int i = pos; i < lineEnd && i < len; i++) {
                if (str[i] == ' ') lastSpace = i;
            }
            if (lastSpace > pos) {
                lineEnd = lastSpace + 1; // Include space but break after
            }
        }

        // Copy this line segment
        char lineBuf[80];
        int lineLen = lineEnd - pos;
        if (lineLen > (int)sizeof(lineBuf) - 1) lineLen = sizeof(lineBuf) - 1;
        strncpy(lineBuf, str + pos, lineLen);
        lineBuf[lineLen] = '\0';

        // Trim trailing spaces for display
        while (lineLen > 0 && lineBuf[lineLen - 1] == ' ') {
            lineBuf[--lineLen] = '\0';
        }

        tftDrawString(x, y, lineBuf, color, bg, size);
        y += lineHeight + 2;
        pos = lineEnd;
    }

    return y;
}

// ─────────────────────────────────────────────────────────────
// Color Helpers
// ─────────────────────────────────────────────────────────────

uint16_t NavosEdgeGUI::aqiColor(float aqi) {
    if (aqi <= 50)  return GUI_GOOD_GREEN;
    if (aqi <= 100) return GUI_WARN_YELLOW;
    if (aqi <= 150) return GUI_WARN_ORANGE;
    return GUI_BAD_RED;
}

uint16_t NavosEdgeGUI::severityColor(const char* severity) {
    if (!severity || !*severity) return GUI_DARK_GREY;
    if (strstr(severity, "good") || strstr(severity, "Good") ||
        strstr(severity, "GOOD") || strstr(severity, "low") ||
        strstr(severity, "Low")) {
        return GUI_GOOD_GREEN;
    }
    if (strstr(severity, "moderate") || strstr(severity, "Moderate") ||
        strstr(severity, "MODERATE") || strstr(severity, "medium") ||
        strstr(severity, "Medium")) {
        return GUI_WARN_YELLOW;
    }
    if (strstr(severity, "unhealthy") || strstr(severity, "Unhealthy") ||
        strstr(severity, "high") || strstr(severity, "High")) {
        return GUI_WARN_ORANGE;
    }
    if (strstr(severity, "hazardous") || strstr(severity, "Hazardous") ||
        strstr(severity, "very") || strstr(severity, "Very") ||
        strstr(severity, "critical") || strstr(severity, "Critical")) {
        return GUI_BAD_RED;
    }
    return GUI_WARN_YELLOW; // default fallback
}

// ═════════════════════════════════════════════════════════════
// Low-Level Display Wrappers
// ═════════════════════════════════════════════════════════════

#ifdef ARDUINO
// ── Real hardware: delegate to UNOQ_MPI3501 ──

void NavosEdgeGUI::tftFillScreen(uint16_t color) {
    _tft.fillScreen(color);
}

void NavosEdgeGUI::tftFillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) {
    _tft.fillRect(x, y, w, h, color);
}

void NavosEdgeGUI::tftDrawRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) {
    _tft.drawRect(x, y, w, h, color);
}

void NavosEdgeGUI::tftDrawString(int16_t x, int16_t y, const char* str,
                                  uint16_t color, uint16_t bg, uint8_t size) {
    _tft.drawString(x, y, str, color, bg, size);
}

void NavosEdgeGUI::tftDrawFastHLine(int16_t x, int16_t y, int16_t w, uint16_t color) {
    _tft.drawFastHLine(x, y, w, color);
}

void NavosEdgeGUI::tftDrawFastVLine(int16_t x, int16_t y, int16_t h, uint16_t color) {
    _tft.drawFastVLine(x, y, h, color);
}

#else
// ── Desktop simulation: print to console ──

void NavosEdgeGUI::tftFillScreen(uint16_t color) {
    (void)color;
}

void NavosEdgeGUI::tftFillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) {
    (void)x; (void)y; (void)w; (void)h; (void)color;
}

void NavosEdgeGUI::tftDrawRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) {
    (void)x; (void)y; (void)w; (void)h; (void)color;
}

void NavosEdgeGUI::tftDrawString(int16_t x, int16_t y, const char* str,
                                  uint16_t color, uint16_t bg, uint8_t size) {
    (void)x; (void)y; (void)str; (void)color; (void)bg; (void)size;
}

void NavosEdgeGUI::tftDrawFastHLine(int16_t x, int16_t y, int16_t w, uint16_t color) {
    (void)x; (void)y; (void)w; (void)color;
}

void NavosEdgeGUI::tftDrawFastVLine(int16_t x, int16_t y, int16_t h, uint16_t color) {
    (void)x; (void)y; (void)h; (void)color;
}

#endif
