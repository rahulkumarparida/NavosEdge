/**
 * @file UNOQ_MPI3501.h
 * @brief Native Arduino UNO Q driver for 3.5" RPi ILI9486 display (MPI3501).
 *
 * PROTOCOL — VERIFIED against TFT_eSPI RPI_DISPLAY_TYPE:
 *
 * The MPI3501 RPi display has an onboard shift-register bridge
 * (74HC04D + 74HC4040 x3) that converts serial SPI into a 16-bit
 * parallel interface for the ILI9486 controller.
 *
 * From TFT_eSPI/Processors/TFT_eSPI_Generic.h:
 *   #if defined (RPI_DISPLAY_TYPE)
 *     // RPi TFT type always needs 16-bit transfers
 *     #define tft_Write_8(C)  spi.transfer(C); spi.transfer(C)
 *     #define tft_Write_16(C) spi.transfer((uint8_t)((C)>>8)); spi.transfer((uint8_t)((C)>>0))
 *   #endif
 *
 * Every 8-bit command/parameter is sent as a duplicated 16-bit word.
 * 16-bit pixel data (RGB565) is sent as two bytes (high, low).
 *
 * PIN MAPPING — VERIFIED against LCDWiki, TFT_eSPI Setup11, ianlunam/esp32-mpi3501:
 *
 *   Display Pin 18 (GPIO24) = LCD_RS / DC  (Data/Command select)
 *   Display Pin 22 (GPIO25) = RST          (LCD module reset)
 *   Display Pin 24 (GPIO8)  = LCD_CS       (LCD chip select)
 *   Display Pin 19 (GPIO10) = SPI MOSI     (shared)
 *   Display Pin 21 (GPIO9)  = SPI MISO     (shared)
 *   Display Pin 23 (GPIO11) = SPI SCLK     (shared)
 *   Display Pin 26 (GPIO7)  = TP_CS        (touch chip select)
 *   Display Pin 11 (GPIO17) = TP_IRQ       (touch interrupt)
 *
 * Hardware: Arduino UNO Q (3.3V logic, hardware SPI)
 * Display:  480x320, RGB565, ILI9486 controller
 */

#ifndef UNOQ_MPI3501_H
#define UNOQ_MPI3501_H

#include <Arduino.h>
#include <SPI.h>

// ============================================================================
// Default pin configuration — Arduino UNO Q
// ============================================================================

#ifndef LCD_CS_PIN
  #define LCD_CS_PIN    10   // Display Pin 24 → LCD chip select (active LOW)
#endif

#ifndef LCD_DC_PIN
  #define LCD_DC_PIN    2    // Display Pin 18 → LCD_RS / DC (HIGH=data, LOW=command)
#endif

#ifndef LCD_RST_PIN
  #define LCD_RST_PIN   3    // Display Pin 22 → RST (active LOW)
#endif

// SPI bus pins (hardware SPI on UNO Q — fixed pins, documented here for reference)
#define LCD_MOSI_PIN  11   // Display Pin 19 → SPI MOSI
#define LCD_MISO_PIN  12   // Display Pin 21 → SPI MISO
#define LCD_SCK_PIN   13   // Display Pin 23 → SPI SCLK

// ============================================================================
// SPI frequency configuration
// ============================================================================
// TFT_eSPI uses up to 27MHz for ESP32. Start conservative for UNO Q.

#ifndef LCD_SPI_FREQ
  #define LCD_SPI_FREQ  10000000UL  // 10 MHz optimized for UNO Q
#endif

// ============================================================================
// Display geometry
// ============================================================================

#define MPI3501_WIDTH   320
#define MPI3501_HEIGHT  480

// ============================================================================
// ILI9486 command definitions
// ============================================================================

#define ILI9486_NOP        0x00
#define ILI9486_SWRESET    0x01
#define ILI9486_SLPIN      0x10
#define ILI9486_SLPOUT     0x11
#define ILI9486_INVOFF     0x20
#define ILI9486_INVON      0x21
#define ILI9486_DISPOFF    0x28
#define ILI9486_DISPON     0x29
#define ILI9486_CASET      0x2A  // Column Address Set
#define ILI9486_PASET      0x2B  // Page Address Set (Row)
#define ILI9486_RAMWR      0x2C  // Memory Write
#define ILI9486_MADCTL     0x36  // Memory Access Control
#define ILI9486_PIXFMT     0x3A  // Pixel Format Set
#define ILI9486_IFMODE     0xB0  // Interface Mode Control
#define ILI9486_FRMCTR1    0xB1
#define ILI9486_INVCTR     0xB4
#define ILI9486_DFUNCTR    0xB6  // Display Function Control
#define ILI9486_PWCTR1     0xC0
#define ILI9486_PWCTR2     0xC1
#define ILI9486_PWCTR3     0xC2
#define ILI9486_VMCTR1     0xC5  // VCOM Control
#define ILI9486_PGAMMA     0xE0  // Positive Gamma
#define ILI9486_NGAMMA     0xE1  // Negative Gamma

// MADCTL bit definitions
#define MADCTL_MY    0x80  // Row Address Order
#define MADCTL_MX    0x40  // Column Address Order
#define MADCTL_MV    0x20  // Row/Column Exchange
#define MADCTL_ML    0x10  // Vertical Refresh Order
#define MADCTL_BGR   0x08  // BGR color order
#define MADCTL_MH    0x04  // Horizontal Refresh Order

// ============================================================================
// RGB565 color definitions
// ============================================================================

#define COLOR_BLACK       0x0000
#define COLOR_WHITE       0xFFFF
#define COLOR_RED         0xF800
#define COLOR_GREEN       0x07E0
#define COLOR_BLUE        0x001F
#define COLOR_CYAN        0x07FF
#define COLOR_MAGENTA     0xF81F
#define COLOR_YELLOW      0xFFE0
#define COLOR_ORANGE      0xFD20
#define COLOR_DARK_GREEN  0x03E0
#define COLOR_DARK_GREY   0x7BEF
#define COLOR_LIGHT_GREY  0xC618

#define COLOR565(r, g, b) (((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3))

// ============================================================================
// UNOQ_MPI3501 class
// ============================================================================

class UNOQ_MPI3501 {
public:
    UNOQ_MPI3501(int8_t cs = LCD_CS_PIN, int8_t dc = LCD_DC_PIN, int8_t rst = LCD_RST_PIN);

    // Core lifecycle
    void begin(void);
    void reset(void);

    // Orientation
    void setRotation(uint8_t r);
    int16_t width(void) const  { return _width; }
    int16_t height(void) const { return _height; }
    uint8_t getRotation(void) const { return _rotation; }

    // Drawing area
    void setAddrWindow(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1);

    // Pixel output
    void pushColor(uint16_t color);
    void pushColors(const uint16_t *colors, uint32_t count);

    // Drawing primitives
    void drawPixel(int16_t x, int16_t y, uint16_t color);
    void fillScreen(uint16_t color);
    void fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color);
    void drawRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color);
    void drawFastHLine(int16_t x, int16_t y, int16_t w, uint16_t color);
    void drawFastVLine(int16_t x, int16_t y, int16_t h, uint16_t color);
    void drawLine(int16_t x0, int16_t y0, int16_t x1, int16_t y1, uint16_t color);

    // Bitmap
    void drawBitmap(int16_t x, int16_t y, int16_t w, int16_t h, const uint16_t *bitmap);

    // Text (built-in 5x7 font)
    void drawChar(int16_t x, int16_t y, char c, uint16_t color, uint16_t bg, uint8_t size);
    void drawString(int16_t x, int16_t y, const char *str, uint16_t color, uint16_t bg, uint8_t size);

    // Display control
    void invertDisplay(bool invert);
    void displayOn(void);
    void displayOff(void);

    // Diagnostics
    void printDiagnostics(void);

    // SPI helpers (public for advanced use / touch bus sharing)
    void spiBegin(void);
    void spiEnd(void);

private:
    int8_t  _cs, _dc, _rst;
    int16_t _width, _height;
    uint8_t _rotation;
    SPISettings _spiSettings;

    // GPIO helpers
    inline void csLow(void)      { digitalWrite(_cs, LOW); }
    inline void csHigh(void)     { digitalWrite(_cs, HIGH); }
    inline void dcCommand(void)  { digitalWrite(_dc, LOW); }
    inline void dcData(void)     { digitalWrite(_dc, HIGH); }

    /**
     * Send an 8-bit value as a 16-bit SPI word (byte duplicated).
     *
     * PROVEN by TFT_eSPI source (Processors/TFT_eSPI_Generic.h):
     *   #define tft_Write_8(C) spi.transfer(C); spi.transfer(C)
     *
     * The onboard 74HC4040 shift registers need 16 SPI clocks
     * to fill the ILI9486's 16-bit parallel data bus.
     */
    inline void spiWrite8as16(uint8_t val) {
        SPI.transfer(val);
        SPI.transfer(val);
    }

    /**
     * Send a native 16-bit value (e.g., RGB565 pixel).
     *
     * PROVEN by TFT_eSPI source:
     *   #define tft_Write_16(C) spi.transfer((uint8_t)((C)>>8)); spi.transfer((uint8_t)((C)>>0))
     */
    inline void spiWrite16(uint16_t val) {
        SPI.transfer(val >> 8);
        SPI.transfer(val & 0xFF);
    }

    // Command and data helpers
    void writeCommand(uint8_t cmd);
    void writeData8(uint8_t data);
    void writeData16(uint16_t data);

    void initSequence(void);
};

#endif // UNOQ_MPI3501_H
