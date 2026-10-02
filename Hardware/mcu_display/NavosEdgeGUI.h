#pragma once
/**
 * NavosEdgeGUI.h — 4-Screen Display renderer for the MPI3501 3.5" 480×320 screen.
 *
 * Sequence:
 *   Screen 0: ENVIRONMENT  (15s) — Observe (AQI, PM1.0, PM2.5, PM10, Temp, Humidity)
 *   Screen 1: ADVISORY     (10s) — Decide  (Severity, Primary Advice, Actions)
 *   Screen 2: FORECAST     (10s) — Predict (Current -> Predicted PM2.5, Trend, Outlook)
 *   Screen 3: INTELLIGENCE (10s) — Explain (Anomaly, Source, Forecast, AQI summary)
 */

#include "NavosEdgeState.h"

#ifdef ARDUINO
#include <UNOQ_MPI3501.h>
#else
#include <cstdio>
#include <cstdint>
#include <cstring>
#endif

// Color palette (RGB565 — matching UNOQ_MPI3501 defines)
#define GUI_BLACK        0x0000
#define GUI_WHITE        0xFFFF
#define GUI_RED          0xF800
#define GUI_GREEN        0x07E0
#define GUI_BLUE         0x001F
#define GUI_CYAN         0x07FF
#define GUI_YELLOW       0xFFE0
#define GUI_ORANGE       0xFD20
#define GUI_PURPLE       0x780F
#define GUI_DARK_GREEN   0x03E0
#define GUI_DARK_GREY    0x39E7
#define GUI_LIGHT_GREY   0xC618

// Custom colors for dashboard
#define GUI_BG_COLOR     0x0842   // Dark slate/navy background
#define GUI_HEADER_BG    0x18C6   // Header background
#define GUI_CARD_BG      0x10A4   // Card background
#define GUI_ACCENT       0x07FF   // Cyan accent
#define GUI_GOOD_GREEN   0x07E0   // Good AQI
#define GUI_WARN_YELLOW  0xFFE0   // Moderate AQI
#define GUI_WARN_ORANGE  0xFD20   // Unhealthy for sensitive
#define GUI_BAD_RED      0xF800   // Unhealthy / Hazardous

// Screen dimensions (landscape)
#define GUI_WIDTH  480
#define GUI_HEIGHT 320

// Total number of screens
#define GUI_NUM_SCREENS 4

class NavosEdgeGUI {
public:
    NavosEdgeGUI();

    /**
     * Initialize the display hardware. Call once in setup().
     */
    void begin();

    /**
     * Non-blocking update. Call every loop().
     * Rotates screens (15s for Env, 10s for others) using millis().
     */
    void update(const NavosEdgeState& state);

    /**
     * Force a full redraw of the current screen.
     */
    void forceRedraw(const NavosEdgeState& state);

    /**
     * Get the current screen index (0-3).
     */
    uint8_t getCurrentScreen() const;

    /**
     * Show a connection status message (for startup/errors).
     */
    void showStatus(const char* line1, const char* line2 = nullptr);

private:
    uint8_t _currentScreen;
    unsigned long _lastRotateMs;
    NavosEdgeState _lastDrawnState;
    uint8_t _lastDrawnScreen;
    bool _needsFullRedraw;

#ifdef ARDUINO
    UNOQ_MPI3501 _tft;
#endif

    // ─── 4 Screen renderers ───
    void drawScreen0_Environment(const NavosEdgeState& state);
    void drawScreen1_Advisory(const NavosEdgeState& state);
    void drawScreen2_Forecast(const NavosEdgeState& state);
    void drawScreen3_Intelligence(const NavosEdgeState& state);

    // ─── UI helpers ───
    void drawHeader(const char* title, const char* badgeStr, uint16_t badgeColor);
    void drawFooter(uint8_t screenIdx, const NavosEdgeState& state);
    void drawCard(int16_t x, int16_t y, int16_t w, int16_t h,
                  const char* label, const char* value, uint16_t valueColor,
                  const char* unit = nullptr);
    int16_t drawWrappedString(int16_t x, int16_t y, const char* str,
                              uint16_t color, uint16_t bg, uint8_t size,
                              int16_t maxWidth, uint8_t maxLines = 4);

    uint16_t aqiColor(float aqi);
    uint16_t severityColor(const char* severity);
    uint16_t trendColor(const char* trend);

    // ─── Low-level display wrappers ───
    void tftFillScreen(uint16_t color);
    void tftFillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color);
    void tftDrawRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color);
    void tftDrawString(int16_t x, int16_t y, const char* str,
                       uint16_t color, uint16_t bg, uint8_t size);
    void tftDrawFastHLine(int16_t x, int16_t y, int16_t w, uint16_t color);
    void tftDrawFastVLine(int16_t x, int16_t y, int16_t h, uint16_t color);
};
