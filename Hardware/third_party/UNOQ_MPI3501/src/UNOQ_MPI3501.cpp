/**
 * @file UNOQ_MPI3501.cpp
 * @brief Native Arduino UNO Q driver for MPI3501 RPi display (ILI9486).
 *
 * Protocol verified against:
 *   - TFT_eSPI/Processors/TFT_eSPI_Generic.h (RPI_DISPLAY_TYPE macros)
 *   - TFT_eSPI/TFT_Drivers/ILI9486_Init.h (init sequence)
 *   - fbtft/fb_ili9486.c (PiScreen init sequence)
 *   - TFT_eSPI/TFT_Drivers/ILI9486_Rotation.h (MADCTL values)
 *
 * ALL code is native Arduino UNO Q. No ESP32/Linux dependencies.
 */

#include "UNOQ_MPI3501.h"

// ============================================================================
// Built-in 5x7 font (ASCII 32-126) — stored in PROGMEM
// ============================================================================

static const uint8_t font5x7[] PROGMEM = {
    0x00, 0x00, 0x00, 0x00, 0x00, // (space)
    0x00, 0x00, 0x5F, 0x00, 0x00, // !
    0x00, 0x07, 0x00, 0x07, 0x00, // "
    0x14, 0x7F, 0x14, 0x7F, 0x14, // #
    0x24, 0x2A, 0x7F, 0x2A, 0x12, // $
    0x23, 0x13, 0x08, 0x64, 0x62, // %
    0x36, 0x49, 0x55, 0x22, 0x50, // &
    0x00, 0x05, 0x03, 0x00, 0x00, // '
    0x00, 0x1C, 0x22, 0x41, 0x00, // (
    0x00, 0x41, 0x22, 0x1C, 0x00, // )
    0x08, 0x2A, 0x1C, 0x2A, 0x08, // *
    0x08, 0x08, 0x3E, 0x08, 0x08, // +
    0x00, 0x50, 0x30, 0x00, 0x00, // ,
    0x08, 0x08, 0x08, 0x08, 0x08, // -
    0x00, 0x60, 0x60, 0x00, 0x00, // .
    0x20, 0x10, 0x08, 0x04, 0x02, // /
    0x3E, 0x51, 0x49, 0x45, 0x3E, // 0
    0x00, 0x42, 0x7F, 0x40, 0x00, // 1
    0x42, 0x61, 0x51, 0x49, 0x46, // 2
    0x21, 0x41, 0x45, 0x4B, 0x31, // 3
    0x18, 0x14, 0x12, 0x7F, 0x10, // 4
    0x27, 0x45, 0x45, 0x45, 0x39, // 5
    0x3C, 0x4A, 0x49, 0x49, 0x30, // 6
    0x01, 0x71, 0x09, 0x05, 0x03, // 7
    0x36, 0x49, 0x49, 0x49, 0x36, // 8
    0x06, 0x49, 0x49, 0x29, 0x1E, // 9
    0x00, 0x36, 0x36, 0x00, 0x00, // :
    0x00, 0x56, 0x36, 0x00, 0x00, // ;
    0x00, 0x08, 0x14, 0x22, 0x41, // <
    0x14, 0x14, 0x14, 0x14, 0x14, // =
    0x41, 0x22, 0x14, 0x08, 0x00, // >
    0x02, 0x01, 0x51, 0x09, 0x06, // ?
    0x32, 0x49, 0x79, 0x41, 0x3E, // @
    0x7E, 0x11, 0x11, 0x11, 0x7E, // A
    0x7F, 0x49, 0x49, 0x49, 0x36, // B
    0x3E, 0x41, 0x41, 0x41, 0x22, // C
    0x7F, 0x41, 0x41, 0x22, 0x1C, // D
    0x7F, 0x49, 0x49, 0x49, 0x41, // E
    0x7F, 0x09, 0x09, 0x01, 0x01, // F
    0x3E, 0x41, 0x41, 0x51, 0x32, // G
    0x7F, 0x08, 0x08, 0x08, 0x7F, // H
    0x00, 0x41, 0x7F, 0x41, 0x00, // I
    0x20, 0x40, 0x41, 0x3F, 0x01, // J
    0x7F, 0x08, 0x14, 0x22, 0x41, // K
    0x7F, 0x40, 0x40, 0x40, 0x40, // L
    0x7F, 0x02, 0x04, 0x02, 0x7F, // M
    0x7F, 0x04, 0x08, 0x10, 0x7F, // N
    0x3E, 0x41, 0x41, 0x41, 0x3E, // O
    0x7F, 0x09, 0x09, 0x09, 0x06, // P
    0x3E, 0x41, 0x51, 0x21, 0x5E, // Q
    0x7F, 0x09, 0x19, 0x29, 0x46, // R
    0x46, 0x49, 0x49, 0x49, 0x31, // S
    0x01, 0x01, 0x7F, 0x01, 0x01, // T
    0x3F, 0x40, 0x40, 0x40, 0x3F, // U
    0x1F, 0x20, 0x40, 0x20, 0x1F, // V
    0x7F, 0x20, 0x18, 0x20, 0x7F, // W
    0x63, 0x14, 0x08, 0x14, 0x63, // X
    0x03, 0x04, 0x78, 0x04, 0x03, // Y
    0x61, 0x51, 0x49, 0x45, 0x43, // Z
    0x00, 0x00, 0x7F, 0x41, 0x41, // [
    0x02, 0x04, 0x08, 0x10, 0x20, // (backslash)
    0x41, 0x41, 0x7F, 0x00, 0x00, // ]
    0x04, 0x02, 0x01, 0x02, 0x04, // ^
    0x40, 0x40, 0x40, 0x40, 0x40, // _
    0x00, 0x01, 0x02, 0x04, 0x00, // `
    0x20, 0x54, 0x54, 0x54, 0x78, // a
    0x7F, 0x48, 0x44, 0x44, 0x38, // b
    0x38, 0x44, 0x44, 0x44, 0x20, // c
    0x38, 0x44, 0x44, 0x48, 0x7F, // d
    0x38, 0x54, 0x54, 0x54, 0x18, // e
    0x08, 0x7E, 0x09, 0x01, 0x02, // f
    0x08, 0x14, 0x54, 0x54, 0x3C, // g
    0x7F, 0x08, 0x04, 0x04, 0x78, // h
    0x00, 0x44, 0x7D, 0x40, 0x00, // i
    0x20, 0x40, 0x44, 0x3D, 0x00, // j
    0x00, 0x7F, 0x10, 0x28, 0x44, // k
    0x00, 0x41, 0x7F, 0x40, 0x00, // l
    0x7C, 0x04, 0x18, 0x04, 0x78, // m
    0x7C, 0x08, 0x04, 0x04, 0x78, // n
    0x38, 0x44, 0x44, 0x44, 0x38, // o
    0x7C, 0x14, 0x14, 0x14, 0x08, // p
    0x08, 0x14, 0x14, 0x18, 0x7C, // q
    0x7C, 0x08, 0x04, 0x04, 0x08, // r
    0x48, 0x54, 0x54, 0x54, 0x20, // s
    0x04, 0x3F, 0x44, 0x40, 0x20, // t
    0x3C, 0x40, 0x40, 0x20, 0x7C, // u
    0x1C, 0x20, 0x40, 0x20, 0x1C, // v
    0x3C, 0x40, 0x30, 0x40, 0x3C, // w
    0x44, 0x28, 0x10, 0x28, 0x44, // x
    0x0C, 0x50, 0x50, 0x50, 0x3C, // y
    0x44, 0x64, 0x54, 0x4C, 0x44, // z
    0x00, 0x08, 0x36, 0x41, 0x00, // {
    0x00, 0x00, 0x7F, 0x00, 0x00, // |
    0x00, 0x41, 0x36, 0x08, 0x00, // }
    0x08, 0x08, 0x2A, 0x1C, 0x08, // ->
    0x08, 0x1C, 0x2A, 0x08, 0x08, // <-
};

// ============================================================================
// Constructor
// ============================================================================

UNOQ_MPI3501::UNOQ_MPI3501(int8_t cs, int8_t dc, int8_t rst)
    : _cs(cs), _dc(dc), _rst(rst), _width(MPI3501_WIDTH),
      _height(MPI3501_HEIGHT), _rotation(0),
      _spiSettings(LCD_SPI_FREQ, MSBFIRST, SPI_MODE0) {}

// ============================================================================
// SPI transaction management
// ============================================================================

void UNOQ_MPI3501::spiBegin(void) {
  SPI.beginTransaction(_spiSettings);
  csLow();
}

void UNOQ_MPI3501::spiEnd(void) {
  csHigh();
  SPI.endTransaction();
}

// ============================================================================
// Low-level command/data primitives
// ============================================================================
// These implement the 16-bit SPI framing for RPi-style displays.
// Verified: TFT_eSPI/Processors/TFT_eSPI_Generic.h, RPI_DISPLAY_TYPE macros.

void UNOQ_MPI3501::writeCommand(uint8_t cmd) {
  dcCommand();        // DC LOW = command mode
  spiWrite8as16(cmd); // tft_Write_8: spi.transfer(C); spi.transfer(C)
}

void UNOQ_MPI3501::writeData8(uint8_t data) {
  dcData();            // DC HIGH = data mode
  spiWrite8as16(data); // tft_Write_8: spi.transfer(C); spi.transfer(C)
}

void UNOQ_MPI3501::writeData16(uint16_t data) {
  dcData();         // DC HIGH = data mode
  spiWrite16(data); // tft_Write_16: spi.transfer(hi); spi.transfer(lo)
}

// ============================================================================
// Hardware reset
// ============================================================================

void UNOQ_MPI3501::reset(void) {
  if (_rst >= 0) {
    digitalWrite(_rst, HIGH);
    delay(5);
    digitalWrite(_rst, LOW);  // Assert reset (active LOW)
    delay(20);                // Hold reset for 20ms
    digitalWrite(_rst, HIGH); // Release reset
    delay(150);               // Wait for ILI9486 to come out of reset
  }
}

// ============================================================================
// ILI9486 initialization sequence
// ============================================================================
// Derived from:
//   - fbtft/fb_ili9486.c (PiScreen default_init_sequence)
//   - TFT_eSPI/TFT_Drivers/ILI9486_Init.h
//
// Pixel format: 0x55 = RGB565 (16-bit)
//   Confirmed by TFT_eSPI ILI9486_Init.h:
//     #if defined (RPI_DISPLAY_TYPE)
//       writedata(0x55);  // 16-bit colour interface
//     #endif

void UNOQ_MPI3501::initSequence(void) {

  spiBegin();

  // Software Reset
  writeCommand(ILI9486_SWRESET);
  spiEnd();
  delay(120);

  spiBegin();

  // Sleep Out
  writeCommand(ILI9486_SLPOUT);
  spiEnd();
  delay(120);

  spiBegin();

  // Interface Mode Control
  writeCommand(ILI9486_IFMODE);
  writeData8(0x00);

  // Pixel Format: 16-bit RGB565
  // 0x55 for RPI_DISPLAY_TYPE (verified TFT_eSPI ILI9486_Init.h)
  writeCommand(ILI9486_PIXFMT);
  writeData8(0x55);

  // Power Control 3
  writeCommand(ILI9486_PWCTR3);
  writeData8(0x44);

  // VCOM Control 1
  writeCommand(ILI9486_VMCTR1);
  writeData8(0x00);
  writeData8(0x00);
  writeData8(0x00);
  writeData8(0x00);

  // Positive Gamma Correction (from fbtft PiScreen sequence)
  writeCommand(ILI9486_PGAMMA);
  writeData8(0x0F);
  writeData8(0x1F);
  writeData8(0x1C);
  writeData8(0x0C);
  writeData8(0x0F);
  writeData8(0x08);
  writeData8(0x48);
  writeData8(0x98);
  writeData8(0x37);
  writeData8(0x0A);
  writeData8(0x13);
  writeData8(0x04);
  writeData8(0x11);
  writeData8(0x0D);
  writeData8(0x00);

  // Negative Gamma Correction (from fbtft PiScreen sequence)
  writeCommand(ILI9486_NGAMMA);
  writeData8(0x0F);
  writeData8(0x32);
  writeData8(0x2E);
  writeData8(0x0B);
  writeData8(0x0D);
  writeData8(0x05);
  writeData8(0x47);
  writeData8(0x75);
  writeData8(0x37);
  writeData8(0x06);
  writeData8(0x10);
  writeData8(0x03);
  writeData8(0x24);
  writeData8(0x20);
  writeData8(0x00);

  // Display Inversion OFF
  // Try ILI9486_INVON (0x21) if colors look wrong on your panel
  writeCommand(ILI9486_INVOFF);

  // Memory Access Control — default portrait orientation
  // Verified: TFT_eSPI ILI9486_Rotation.h case 0: MADCTL_MX | MADCTL_BGR
  writeCommand(ILI9486_MADCTL);
  writeData8(MADCTL_MX | MADCTL_BGR);

  // Display ON
  writeCommand(ILI9486_DISPON);

  spiEnd();
  delay(25);
}

// ============================================================================
// begin()
// ============================================================================

void UNOQ_MPI3501::begin(void) {
  // Configure control pins as outputs
  pinMode(_cs, OUTPUT);
  pinMode(_dc, OUTPUT);
  if (_rst >= 0) {
    pinMode(_rst, OUTPUT);
  }

  // Start with CS HIGH (deselected)
  csHigh();

  // Initialize hardware SPI
  SPI.begin();

  // Hardware reset
  reset();

  // ILI9486 initialization command sequence
  initSequence();

  // Default to landscape (480x320) — most common orientation
  setRotation(1);
}

// ============================================================================
// setRotation()
// ============================================================================
// Verified against TFT_eSPI/TFT_Drivers/ILI9486_Rotation.h:
//   case 0: writedata(TFT_MAD_BGR | TFT_MAD_MX);       // Portrait
//   case 1: writedata(TFT_MAD_BGR | TFT_MAD_MV);        // Landscape (90° CW)
//   case 2: writedata(TFT_MAD_BGR | TFT_MAD_MY);        // Portrait inverted
//   case 3: writedata(TFT_MAD_BGR | TFT_MAD_MX | TFT_MAD_MY | TFT_MAD_MV); //
//   Landscape inv

void UNOQ_MPI3501::setRotation(uint8_t r) {
  _rotation = r % 4;

  spiBegin();
  writeCommand(ILI9486_MADCTL);

  switch (_rotation) {
  case 0: // Portrait (320x480)
    writeData8(MADCTL_MX | MADCTL_BGR);
    _width = MPI3501_WIDTH;
    _height = MPI3501_HEIGHT;
    break;

  case 1: // Landscape (480x320) — 90° CW
    writeData8(MADCTL_MV | MADCTL_BGR);
    _width = MPI3501_HEIGHT;
    _height = MPI3501_WIDTH;
    break;

  case 2: // Portrait inverted (180°)
    writeData8(MADCTL_MY | MADCTL_BGR);
    _width = MPI3501_WIDTH;
    _height = MPI3501_HEIGHT;
    break;

  case 3: // Landscape inverted (270°)
    writeData8(MADCTL_MX | MADCTL_MY | MADCTL_MV | MADCTL_BGR);
    _width = MPI3501_HEIGHT;
    _height = MPI3501_WIDTH;
    break;
  }

  spiEnd();
}

// ============================================================================
// setAddrWindow() — set the active drawing region
// ============================================================================
// After this call, the DC line is left HIGH (data mode) so subsequent
// SPI writes go directly to RAMWR as pixel data.

void UNOQ_MPI3501::setAddrWindow(uint16_t x0, uint16_t y0, uint16_t x1,
                                 uint16_t y1) {
  // // Column Address Set (CASET)
  // writeCommand(ILI9486_CASET);
  // writeData16(x0);
  // writeData16(x1);

  // // Page/Row Address Set (PASET)
  // writeCommand(ILI9486_PASET);
  // writeData16(y0);
  // writeData16(y1);

  // // Memory Write (RAMWR) — subsequent data = pixel colors
  // writeCommand(ILI9486_RAMWR);
  // dcData();  // Stay in data mode for pixel streaming
  // Column Address Set (CASET)

  // changed code
  // ADD THIS SWAP LOGIC:
  // If in Landscape mode (1 or 3), swap X and Y to bypass the hardware limits!
    // Column Address Set (CASET)
    writeCommand(ILI9486_CASET);
    writeData8(x0 >> 8);   // Start X High Byte
    writeData8(x0 & 0xFF); // Start X Low Byte
    writeData8(x1 >> 8);   // End X High Byte
    writeData8(x1 & 0xFF); // End X Low Byte
    // Page/Row Address Set (PASET)
    writeCommand(ILI9486_PASET);
    writeData8(y0 >> 8);   // Start Y High Byte
    writeData8(y0 & 0xFF); // Start Y Low Byte
    writeData8(y1 >> 8);   // End Y High Byte
    writeData8(y1 & 0xFF); // End Y Low Byte
    // Memory Write (RAMWR) — subsequent data = pixel colors
    writeCommand(ILI9486_RAMWR);
    dcData(); // Stay in data mode for pixel streaming
}
// ============================================================================
// Pixel output
// ============================================================================

void UNOQ_MPI3501::pushColor(uint16_t color) {
  spiBegin();
  spiWrite16(color);
  spiEnd();
}

void UNOQ_MPI3501::pushColors(const uint16_t *colors, uint32_t count) {
  dcData();
  spiBegin();
  uint8_t chunk_buf[128];
  while (count > 0) {
    uint32_t chunk = count < 64 ? count : 64;
    for (uint32_t i = 0; i < chunk; i++) {
      chunk_buf[i * 2]     = (colors[i] >> 8) & 0xFF;
      chunk_buf[i * 2 + 1] = colors[i] & 0xFF;
    }
    SPI.transfer(chunk_buf, chunk * 2);
    colors += chunk;
    count -= chunk;
  }
  spiEnd();
}

// ============================================================================
// drawPixel
// ============================================================================

void UNOQ_MPI3501::drawPixel(int16_t x, int16_t y, uint16_t color) {
  if (x < 0 || x >= _width || y < 0 || y >= _height)
    return;

  spiBegin();
  setAddrWindow(x, y, x, y);
  spiWrite16(color);
  spiEnd();
}

// ============================================================================
// fillScreen
// ============================================================================

void UNOQ_MPI3501::fillScreen(uint16_t color) {
  fillRect(0, 0, _width, _height, color);
}

// ============================================================================
// fillRect
// ============================================================================

void UNOQ_MPI3501::fillRect(int16_t x, int16_t y, int16_t w, int16_t h,
                            uint16_t color) {
  // Clip to display bounds
  if (x >= _width || y >= _height || w <= 0 || h <= 0)
    return;
  if (x < 0) {
    w += x;
    x = 0;
  }
  if (y < 0) {
    h += y;
    y = 0;
  }
  if ((x + w) > _width)
    w = _width - x;
  if ((y + h) > _height)
    h = _height - y;
  if (w <= 0 || h <= 0)
    return;

  spiBegin();
  setAddrWindow(x, y, x + w - 1, y + h - 1);

  uint8_t hi = color >> 8;
  uint8_t lo = color & 0xFF;
  uint32_t total = (uint32_t)w * (uint32_t)h;

  // Optimized chunked transfer: 128 bytes (64 pixels) per syscall
  // Note: SPI.transfer() on Zephyr RTOS is full-duplex and writes MISO bytes
  // into chunk_buf. We must repopulate chunk_buf in each chunk iteration to
  // avoid corrupting transfers longer than 64 pixels.
  uint8_t chunk_buf[128];
  uint32_t remaining = total;
  while (remaining > 0) {
    uint32_t pixels = remaining < 64 ? remaining : 64;
    for (uint32_t i = 0; i < pixels * 2; i += 2) {
      chunk_buf[i]     = hi;
      chunk_buf[i + 1] = lo;
    }
    SPI.transfer(chunk_buf, pixels * 2);
    remaining -= pixels;
  }

  spiEnd();
}

// ============================================================================
// drawRect — outlined rectangle
// ============================================================================

void UNOQ_MPI3501::drawRect(int16_t x, int16_t y, int16_t w, int16_t h,
                            uint16_t color) {
  drawFastHLine(x, y, w, color);
  drawFastHLine(x, y + h - 1, w, color);
  drawFastVLine(x, y, h, color);
  drawFastVLine(x + w - 1, y, h, color);
}

// ============================================================================
// drawFastHLine
// ============================================================================

void UNOQ_MPI3501::drawFastHLine(int16_t x, int16_t y, int16_t w,
                                 uint16_t color) {
  fillRect(x, y, w, 1, color);
}

// ============================================================================
// drawFastVLine
// ============================================================================

void UNOQ_MPI3501::drawFastVLine(int16_t x, int16_t y, int16_t h,
                                 uint16_t color) {
  fillRect(x, y, 1, h, color);
}

// ============================================================================
// drawLine — Bresenham's line algorithm
// ============================================================================

void UNOQ_MPI3501::drawLine(int16_t x0, int16_t y0, int16_t x1, int16_t y1,
                            uint16_t color) {
  if (y0 == y1) {
    drawFastHLine(min(x0, x1), y0, abs(x1 - x0) + 1, color);
    return;
  }
  if (x0 == x1) {
    drawFastVLine(x0, min(y0, y1), abs(y1 - y0) + 1, color);
    return;
  }

  bool steep = abs(y1 - y0) > abs(x1 - x0);
  if (steep) {
    int16_t t = x0;
    x0 = y0;
    y0 = t;
    t = x1;
    x1 = y1;
    y1 = t;
  }
  if (x0 > x1) {
    int16_t t = x0;
    x0 = x1;
    x1 = t;
    t = y0;
    y0 = y1;
    y1 = t;
  }

  int16_t dx = x1 - x0;
  int16_t dy = abs(y1 - y0);
  int16_t err = dx / 2;
  int16_t ystep = (y0 < y1) ? 1 : -1;

  for (; x0 <= x1; x0++) {
    if (steep)
      drawPixel(y0, x0, color);
    else
      drawPixel(x0, y0, color);
    err -= dy;
    if (err < 0) {
      y0 += ystep;
      err += dx;
    }
  }
}

// ============================================================================
// drawBitmap
// ============================================================================

void UNOQ_MPI3501::drawBitmap(int16_t x, int16_t y, int16_t w, int16_t h,
                              const uint16_t *bitmap) {
  if (x >= _width || y >= _height || w <= 0 || h <= 0)
    return;

  spiBegin();
  setAddrWindow(x, y, x + w - 1, y + h - 1);
  uint32_t total = (uint32_t)w * (uint32_t)h;
  pushColors(bitmap, total);
  spiEnd();
}

// ============================================================================
// drawChar
// ============================================================================

void UNOQ_MPI3501::drawChar(int16_t x, int16_t y, char c, uint16_t color,
                            uint16_t bg, uint8_t size) {
  if (x >= _width || y >= _height || (x + 6 * size) <= 0 || (y + 8 * size) <= 0)
    return;
  if (c < 32 || c > 126)
    c = '?';
  uint8_t idx = c - 32;

  for (uint8_t col = 0; col < 5; col++) {
    uint8_t line = pgm_read_byte(&font5x7[idx * 5 + col]);
    for (uint8_t row = 0; row < 7; row++) {
      uint16_t pixColor = (line & (1 << row)) ? color : bg;
      if (size == 1) {
        drawPixel(x + col, y + row, pixColor);
      } else {
        fillRect(x + col * size, y + row * size, size, size, pixColor);
      }
    }
  }
  // Inter-character gap
  if (size == 1) {
    drawFastVLine(x + 5, y, 7, bg);
  } else {
    fillRect(x + 5 * size, y, size, 7 * size, bg);
  }
}

// ============================================================================
// drawString
// ============================================================================

void UNOQ_MPI3501::drawString(int16_t x, int16_t y, const char *str,
                              uint16_t color, uint16_t bg, uint8_t size) {
  int16_t cursorX = x;
  while (*str) {
    if (cursorX >= _width)
      break;
    drawChar(cursorX, y, *str, color, bg, size);
    cursorX += 6 * size;
    str++;
  }
}

// ============================================================================
// Display control
// ============================================================================

void UNOQ_MPI3501::invertDisplay(bool invert) {
  spiBegin();
  writeCommand(invert ? ILI9486_INVON : ILI9486_INVOFF);
  spiEnd();
}

void UNOQ_MPI3501::displayOn(void) {
  spiBegin();
  writeCommand(ILI9486_DISPON);
  spiEnd();
}

void UNOQ_MPI3501::displayOff(void) {
  spiBegin();
  writeCommand(ILI9486_DISPOFF);
  spiEnd();
}

// ============================================================================
// Diagnostics
// ============================================================================

void UNOQ_MPI3501::printDiagnostics(void) {
  Serial.println(F("========================================"));
  Serial.println(F("  UNOQ_MPI3501 Diagnostics"));
  Serial.println(F("========================================"));
  Serial.println(F("  Controller: ILI9486 (RPi 16-bit SPI bridge)"));
  Serial.println(F("  Module:     MPI3501 / 3.5\" RPi Display"));

  Serial.println(F("--- Pins ---"));
  Serial.print(F("  LCD CS  (Pin 24): D"));
  Serial.println(_cs);
  Serial.print(F("  LCD DC  (Pin 18): D"));
  Serial.println(_dc);
  Serial.print(F("  LCD RST (Pin 22): D"));
  Serial.println(_rst);
  Serial.print(F("  MOSI    (Pin 19): D"));
  Serial.println(LCD_MOSI_PIN);
  Serial.print(F("  MISO    (Pin 21): D"));
  Serial.println(LCD_MISO_PIN);
  Serial.print(F("  SCK     (Pin 23): D"));
  Serial.println(LCD_SCK_PIN);

  Serial.println(F("--- Display ---"));
  Serial.print(F("  Size:     "));
  Serial.print(_width);
  Serial.print('x');
  Serial.println(_height);
  Serial.print(F("  Rotation: "));
  Serial.println(_rotation);
  Serial.println(F("  Pixel:    RGB565"));

  Serial.println(F("--- SPI ---"));
  Serial.print(F("  Freq:     "));
  Serial.print(LCD_SPI_FREQ / 1000000UL);
  Serial.println(F(" MHz"));
  Serial.println(F("  Mode:     0 (CPOL=0 CPHA=0)"));
  Serial.println(F("  Order:    MSB first"));
  Serial.println(F("  Framing:  16-bit (RPi bridge)"));

  Serial.println(F("--- Checks ---"));
  if (_cs == _dc || _cs == _rst || (_dc == _rst && _rst >= 0))
    Serial.println(F("  ERROR: Pin conflict!"));
  else
    Serial.println(F("  OK: No pin conflicts"));

  if (LCD_SPI_FREQ > 20000000UL)
    Serial.println(F("  WARN: SPI > 20 MHz may be unstable"));
  else
    Serial.println(F("  OK: SPI freq in range"));

  Serial.println(F("========================================"));
}
