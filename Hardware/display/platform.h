#pragma once
/**
 * platform.h — Platform abstraction for Arduino vs Desktop builds.
 *
 * Provides millis() and other Arduino-like functions for desktop simulation.
 */

#ifdef ARDUINO
#include <Arduino.h>
#else

#include <cstdint>
#include <cstring>
#include <cstdio>
#include <ctime>

// Desktop millis() using CLOCK_MONOTONIC
inline unsigned long millis() {
    static unsigned long start = 0;
    static bool initialized = false;
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    unsigned long now = ts.tv_sec * 1000UL + ts.tv_nsec / 1000000UL;
    if (!initialized) {
        start = now;
        initialized = true;
    }
    return now - start;
}

// Arduino-like Serial stub for desktop
struct SerialStub {
    void begin(int) {}
    void println(const char* s) { printf("%s\n", s); }
    void print(const char* s) { printf("%s", s); }
    void println(int v) { printf("%d\n", v); }
    void print(int v) { printf("%d", v); }
    operator bool() const { return true; }
};
// F() macro stub
#define F(s) (s)

#endif // ARDUINO
