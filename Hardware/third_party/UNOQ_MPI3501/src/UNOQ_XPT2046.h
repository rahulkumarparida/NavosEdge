/**
 * @file UNOQ_XPT2046.h
 * @brief Native Arduino UNO Q driver for XPT2046/HR2046 touch controller.
 *
 * The XPT2046 uses standard 8-bit SPI (NOT 16-bit framing like the LCD).
 * This driver manages chip-select arbitration with the LCD.
 *
 * NOTE: The XPT2046 does NOT require a separate hardware reset pin.
 * It initializes via SPI communication and resets at power-on.
 * Display Pin 22 is the LCD module reset, not a touch-specific reset.
 *
 * Hardware: Arduino UNO Q (3.3V logic, hardware SPI)
 */

#ifndef UNOQ_XPT2046_H
#define UNOQ_XPT2046_H

#include <Arduino.h>
#include <SPI.h>

// ============================================================================
// Default pin configuration
// ============================================================================

#ifndef TOUCH_CS_PIN
  #define TOUCH_CS_PIN    4    // Display Pin 26 → Touch chip select
#endif

#ifndef TOUCH_IRQ_PIN
  #define TOUCH_IRQ_PIN   5    // Display Pin 11 → Touch pen-down interrupt
#endif

// LCD CS pin — must be deselected when reading touch
#ifndef TOUCH_LCD_CS_PIN
  #define TOUCH_LCD_CS_PIN  10
#endif

// ============================================================================
// Touch SPI frequency
// ============================================================================
// XPT2046 max clock during conversion is ~2 MHz.
// Use 1 MHz for reliability.

#ifndef TOUCH_SPI_FREQ
  #define TOUCH_SPI_FREQ  1000000UL
#endif

// ============================================================================
// XPT2046 control byte definitions
// ============================================================================
// Format: S | A2 A1 A0 | MODE | SER/DFR | PD1 PD0
// S=1 (start), MODE=0 (12-bit), SER/DFR=0 (differential)

#define XPT2046_CMD_X      0xD0  // 1101 0000 — X position, differential, 12-bit
#define XPT2046_CMD_Y      0x90  // 1001 0000 — Y position, differential, 12-bit
#define XPT2046_CMD_Z1     0xB0  // 1011 0000 — Z1 (pressure)
#define XPT2046_CMD_Z2     0xC0  // 1100 0000 — Z2 (pressure)

// ============================================================================
// Calibration defaults (typical — MUST be calibrated per unit)
// ============================================================================

#ifndef TOUCH_CAL_X_MIN
  #define TOUCH_CAL_X_MIN  300
#endif
#ifndef TOUCH_CAL_X_MAX
  #define TOUCH_CAL_X_MAX  3800
#endif
#ifndef TOUCH_CAL_Y_MIN
  #define TOUCH_CAL_Y_MIN  300
#endif
#ifndef TOUCH_CAL_Y_MAX
  #define TOUCH_CAL_Y_MAX  3800
#endif

// ============================================================================
// Data structures
// ============================================================================

struct TouchPoint {
    int16_t x;         // Mapped pixel X
    int16_t y;         // Mapped pixel Y
    uint16_t rawX;     // Raw ADC X (0-4095)
    uint16_t rawY;     // Raw ADC Y (0-4095)
    uint16_t z;        // Pressure estimate
    bool pressed;      // True if pen is down
};

struct CalibrationPoint {
    int16_t  screenX;
    int16_t  screenY;
    uint16_t rawX;
    uint16_t rawY;
};

// ============================================================================
// UNOQ_XPT2046 class
// ============================================================================

class UNOQ_XPT2046 {
public:
    UNOQ_XPT2046(int8_t touchCs = TOUCH_CS_PIN,
                  int8_t irqPin  = TOUCH_IRQ_PIN,
                  int8_t lcdCs   = TOUCH_LCD_CS_PIN);

    void begin(void);

    // Touch reading
    bool isTouched(void);
    TouchPoint read(void);

    // Raw readings (8-sample averaged)
    uint16_t readRawX(void);
    uint16_t readRawY(void);
    uint16_t readRawZ(void);

    // Calibration
    void setCalibration(uint16_t xMin, uint16_t xMax, uint16_t yMin, uint16_t yMax);
    void setRotation(uint8_t rotation);
    void setDisplaySize(int16_t w, int16_t h);

    uint16_t getCalXMin(void) const { return _calXMin; }
    uint16_t getCalXMax(void) const { return _calXMax; }
    uint16_t getCalYMin(void) const { return _calYMin; }
    uint16_t getCalYMax(void) const { return _calYMax; }

    // Diagnostics
    void printDiagnostics(void);

private:
    int8_t  _touchCs, _irqPin, _lcdCs;
    uint8_t _rotation;
    int16_t _dispWidth, _dispHeight;
    uint16_t _calXMin, _calXMax, _calYMin, _calYMax;
    SPISettings _spiSettings;

    uint16_t spiTransfer(uint8_t cmd);
    int16_t mapRawToScreen(uint16_t raw, uint16_t rawMin, uint16_t rawMax, int16_t screenSize);
    void applyRotation(int16_t &x, int16_t &y);
};

#endif // UNOQ_XPT2046_H
