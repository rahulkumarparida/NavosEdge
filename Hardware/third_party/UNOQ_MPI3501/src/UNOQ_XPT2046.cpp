/**
 * @file UNOQ_XPT2046.cpp
 * @brief Native Arduino UNO Q driver for XPT2046/HR2046 touch controller.
 *
 * Standard 8-bit SPI protocol — NOT 16-bit like the LCD.
 * Manages SPI bus sharing with the LCD via separate CS pins.
 */

#include "UNOQ_XPT2046.h"

// ============================================================================
// Constructor
// ============================================================================

UNOQ_XPT2046::UNOQ_XPT2046(int8_t touchCs, int8_t irqPin, int8_t lcdCs)
    : _touchCs(touchCs), _irqPin(irqPin), _lcdCs(lcdCs),
      _rotation(1),
      _dispWidth(480), _dispHeight(320),
      _calXMin(TOUCH_CAL_X_MIN), _calXMax(TOUCH_CAL_X_MAX),
      _calYMin(TOUCH_CAL_Y_MIN), _calYMax(TOUCH_CAL_Y_MAX),
      _spiSettings(TOUCH_SPI_FREQ, MSBFIRST, SPI_MODE0)
{
}

// ============================================================================
// begin()
// ============================================================================

void UNOQ_XPT2046::begin(void) {
    pinMode(_touchCs, OUTPUT);
    digitalWrite(_touchCs, HIGH);  // Deselect touch

    // Ensure LCD CS is deselected
    if (_lcdCs >= 0) {
        pinMode(_lcdCs, OUTPUT);
        digitalWrite(_lcdCs, HIGH);
    }

    // IRQ pin: XPT2046 PENIRQ is open-drain, active LOW when touched
    if (_irqPin >= 0) {
        pinMode(_irqPin, INPUT_PULLUP);
    }
}

// ============================================================================
// Low-level SPI transfer
// ============================================================================
// XPT2046 protocol:
//   1. Assert touch CS LOW (LCD CS must be HIGH)
//   2. Send 8-bit control byte
//   3. Read 12-bit ADC result from next 16 clocks (MSB first)
//   4. Deassert touch CS HIGH

uint16_t UNOQ_XPT2046::spiTransfer(uint8_t cmd) {
    // CRITICAL: Ensure LCD is deselected
    if (_lcdCs >= 0) {
        digitalWrite(_lcdCs, HIGH);
    }

    SPI.beginTransaction(_spiSettings);
    digitalWrite(_touchCs, LOW);

    SPI.transfer(cmd);

    uint8_t hi = SPI.transfer(0x00);
    uint8_t lo = SPI.transfer(0x00);

    digitalWrite(_touchCs, HIGH);
    SPI.endTransaction();

    // Result is in bits [14:3] of the 16-bit response
    uint16_t result = ((uint16_t)hi << 8) | lo;
    result >>= 3;
    result &= 0x0FFF;

    return result;
}

// ============================================================================
// isTouched()
// ============================================================================

bool UNOQ_XPT2046::isTouched(void) {
    if (_irqPin >= 0) {
        return (digitalRead(_irqPin) == LOW);
    }
    return (readRawZ() > 50);
}

// ============================================================================
// Raw readings (8-sample averaged for noise rejection)
// ============================================================================

uint16_t UNOQ_XPT2046::readRawX(void) {
    uint32_t sum = 0;
    const uint8_t samples = 8;
    for (uint8_t i = 0; i < samples; i++) {
        sum += spiTransfer(XPT2046_CMD_X);
    }
    return (uint16_t)(sum / samples);
}

uint16_t UNOQ_XPT2046::readRawY(void) {
    uint32_t sum = 0;
    const uint8_t samples = 8;
    for (uint8_t i = 0; i < samples; i++) {
        sum += spiTransfer(XPT2046_CMD_Y);
    }
    return (uint16_t)(sum / samples);
}

uint16_t UNOQ_XPT2046::readRawZ(void) {
    uint16_t z1 = spiTransfer(XPT2046_CMD_Z1);
    // Simple pressure: higher z1 = more pressure
    return z1;
}

// ============================================================================
// read() — complete touch point with mapping and rotation
// ============================================================================

TouchPoint UNOQ_XPT2046::read(void) {
    TouchPoint tp;
    tp.pressed = isTouched();

    if (tp.pressed) {
        tp.rawX = readRawX();
        tp.rawY = readRawY();
        tp.z = readRawZ();

        // Map raw ADC to pixel coordinates
        tp.x = mapRawToScreen(tp.rawX, _calXMin, _calXMax, _dispWidth);
        tp.y = mapRawToScreen(tp.rawY, _calYMin, _calYMax, _dispHeight);

        // Apply rotation
        applyRotation(tp.x, tp.y);

        // Clamp to display bounds
        if (tp.x < 0) tp.x = 0;
        if (tp.y < 0) tp.y = 0;
        if (tp.x >= _dispWidth)  tp.x = _dispWidth - 1;
        if (tp.y >= _dispHeight) tp.y = _dispHeight - 1;
    } else {
        tp.rawX = tp.rawY = tp.x = tp.y = 0;
        tp.z = 0;
    }

    return tp;
}

// ============================================================================
// Calibration
// ============================================================================

void UNOQ_XPT2046::setCalibration(uint16_t xMin, uint16_t xMax, uint16_t yMin, uint16_t yMax) {
    _calXMin = xMin;
    _calXMax = xMax;
    _calYMin = yMin;
    _calYMax = yMax;
}

void UNOQ_XPT2046::setRotation(uint8_t rotation) {
    _rotation = rotation % 4;
    if (_rotation == 0 || _rotation == 2) {
        _dispWidth  = 320;
        _dispHeight = 480;
    } else {
        _dispWidth  = 480;
        _dispHeight = 320;
    }
}

void UNOQ_XPT2046::setDisplaySize(int16_t w, int16_t h) {
    _dispWidth = w;
    _dispHeight = h;
}

// ============================================================================
// Coordinate mapping
// ============================================================================

int16_t UNOQ_XPT2046::mapRawToScreen(uint16_t raw, uint16_t rawMin, uint16_t rawMax, int16_t screenSize) {
    if (rawMin > rawMax) {
        uint16_t tmp = rawMin; rawMin = rawMax; rawMax = tmp;
        if (raw < rawMin) raw = rawMin;
        if (raw > rawMax) raw = rawMax;
        return (int16_t)map(raw, rawMin, rawMax, screenSize - 1, 0);
    }
    if (raw < rawMin) raw = rawMin;
    if (raw > rawMax) raw = rawMax;
    return (int16_t)map(raw, rawMin, rawMax, 0, screenSize - 1);
}

// ============================================================================
// Rotation transform
// ============================================================================

void UNOQ_XPT2046::applyRotation(int16_t &x, int16_t &y) {
    int16_t temp;
    switch (_rotation) {
        case 0: break;
        case 1:
            temp = x;
            x = y;
            y = _dispHeight - 1 - temp;
            break;
        case 2:
            x = _dispWidth  - 1 - x;
            y = _dispHeight - 1 - y;
            break;
        case 3:
            temp = x;
            x = _dispWidth - 1 - y;
            y = temp;
            break;
    }
}

// ============================================================================
// Diagnostics
// ============================================================================

void UNOQ_XPT2046::printDiagnostics(void) {
    Serial.println(F("========================================"));
    Serial.println(F("  UNOQ_XPT2046 Diagnostics"));
    Serial.println(F("========================================"));
    Serial.println(F("  IC: XPT2046 / HR2046"));
    Serial.println(F("  Protocol: Standard 8-bit SPI"));

    Serial.println(F("--- Pins ---"));
    Serial.print(F("  Touch CS  (Pin 26): D")); Serial.println(_touchCs);
    Serial.print(F("  Touch IRQ (Pin 11): D")); Serial.println(_irqPin);
    Serial.print(F("  LCD CS    (Pin 24): D")); Serial.println(_lcdCs);

    Serial.println(F("--- SPI ---"));
    Serial.print(F("  Freq: ")); Serial.print(TOUCH_SPI_FREQ / 1000UL); Serial.println(F(" kHz"));
    Serial.println(F("  Mode: 0"));

    Serial.println(F("--- Calibration ---"));
    Serial.print(F("  X: ")); Serial.print(_calXMin); Serial.print(F("-")); Serial.println(_calXMax);
    Serial.print(F("  Y: ")); Serial.print(_calYMin); Serial.print(F("-")); Serial.println(_calYMax);
    Serial.print(F("  Rotation: ")); Serial.println(_rotation);
    Serial.print(F("  Display:  ")); Serial.print(_dispWidth); Serial.print('x'); Serial.println(_dispHeight);

    Serial.println(F("--- Status ---"));
    if (_irqPin >= 0) {
        Serial.print(F("  IRQ: "));
        Serial.println(digitalRead(_irqPin) == LOW ? F("TOUCHED") : F("idle"));
    }
    uint16_t rx = readRawX();
    uint16_t ry = readRawY();
    uint16_t rz = readRawZ();
    Serial.print(F("  Raw: X=")); Serial.print(rx);
    Serial.print(F(" Y=")); Serial.print(ry);
    Serial.print(F(" Z=")); Serial.println(rz);
    Serial.println(F("========================================"));
}
