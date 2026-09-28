#pragma once
/**
 * NavosEdgeGUI.h — Display renderer for the MPI3501 3.5" 480×320 screen.
 *
 * Uses the UNOQ_MPI3501 library API exclusively:
 *   - begin(), setRotation(1)
 *   - fillScreen(), fillRect(), drawRect()
 *   - drawString(x, y, str, color, bg, size)
 *   - drawFastHLine(), drawFastVLine()
 *   - drawLine()
 *   - width(), height()
 *
 * Three screens rotate every 10 seconds using non-blocking millis():
 *   Screen 0: Environment (AQI, PM, Temp, Humidity)
 *   Screen 1: Advice (advisory text)
 *   Screen 2: Actions (actionable recommendations)
 */

#include "../state/NavosEdgeState.h"

#ifdef ARDUINO
#include <UNOQ_MPI3501.h>
#else
// Desktop simulation — stub the display class
#include <cstdio>
#include <cstdint>
#include <cstring>
#endif

// Screen rotation interval (milliseconds)
#ifndef NAVOS_SCREEN_ROTATE_MS
#define NAVOS_SCREEN_ROTATE_MS 10000
#endif

// ─────────────────────────────────────────────────────────────
// Color palette (RGB565 — matching UNOQ_MPI3501 defines)
// ─────────────────────────────────────────────────────────────
#define GUI_BLACK        0x0000
#define GUI_WHITE        0xFFFF
#define GUI_RED          0xF800
#define GUI_GREEN        0x07E0
#define GUI_BLUE         0x001F
#define GUI_CYAN         0x07FF
#define GUI_YELLOW       0xFFE0
#define GUI_ORANGE       0xFD20
#define GUI_DARK_GREEN   0x03E0
#define GUI_DARK_GREY    0x7BEF
#define GUI_LIGHT_GREY   0xC618

// Custom colors for the dashboard
#define GUI_BG_COLOR     0x10A2   // Dark navy background
#define GUI_HEADER_BG    0x2945   // Slightly lighter header
#define GUI_CARD_BG      0x2124   // Card background
#define GUI_ACCENT       0x07FF   // Cyan accent
#define GUI_GOOD_GREEN   0x07E0   // Good AQI
#define GUI_WARN_YELLOW  0xFFE0   // Moderate AQI
#define GUI_WARN_ORANGE  0xFD20   // Unhealthy for sensitive
#define GUI_BAD_RED      0xF800   // Unhealthy / Hazardous

// Screen dimensions (landscape)
#define GUI_WIDTH  480
#define GUI_HEIGHT 320

// Total number of screens
#define GUI_NUM_SCREENS 3

class NavosEdgeGUI {
public:
    NavosEdgeGUI();

    /**
     * Initialize the display hardware.
     * Call once in setup().
     */
    void begin();

    /**
     * Non-blocking update. Call every loop().
     * Handles screen rotation timing and redraws when needed.
     * Pass the current state; redraws only if data changed or screen rotated.
     */
    void update(const NavosEdgeState& state);

    /**
     * Force a full redraw of the current screen.
     */
    void forceRedraw(const NavosEdgeState& state);

    /**
     * Get the current screen index (0-2).
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

    // ─── Screen renderers ───
    void drawScreen0_Environment(const NavosEdgeState& state);
    void drawScreen1_Advice(const NavosEdgeState& state);
    void drawScreen2_Actions(const NavosEdgeState& state);

    // ─── UI helpers ───
    void drawHeader(const char* title, uint16_t accentColor);
    void drawFooter(const NavosEdgeState& state);
    void drawCard(int16_t x, int16_t y, int16_t w, int16_t h,
                  const char* label, const char* value, uint16_t valueColor);
    void drawProgressBar(int16_t x, int16_t y, int16_t w, int16_t h,
                         float value, float maxVal, uint16_t color);

    /**
     * Draw a string that word-wraps to fit within maxWidth pixels.
     * Returns the Y position after the last line drawn.
     */
    int16_t drawWrappedString(int16_t x, int16_t y, const char* str,
                               uint16_t color, uint16_t bg, uint8_t size,
                               int16_t maxWidth);

    /**
     * Get the AQI severity color.
     */
    uint16_t aqiColor(float aqi);

    /**
     * Get the severity color from the severity string.
     */
    uint16_t severityColor(const char* severity);

    // ─── Low-level display wrappers ───
    // These wrap the UNOQ_MPI3501 API on Arduino or print to console on desktop
    void tftFillScreen(uint16_t color);
    void tftFillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color);
    void tftDrawRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color);
    void tftDrawString(int16_t x, int16_t y, const char* str,
                       uint16_t color, uint16_t bg, uint8_t size);
    void tftDrawFastHLine(int16_t x, int16_t y, int16_t w, uint16_t color);
    void tftDrawFastVLine(int16_t x, int16_t y, int16_t h, uint16_t color);
};
