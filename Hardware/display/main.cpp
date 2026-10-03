/**
 * NavosEdge Display GUI — Main Entry Point
 *
 * Three-screen dashboard for the Arduino UNO Q + MPI3501 3.5" display.
 * Fetches intelligence results from the NavosEdge server and renders:
 *   Screen 1: Environment (AQI, PM, Temp, Humidity)
 *   Screen 2: Advisory text
 *   Screen 3: Actions from the Advisory Engine
 *
 * Screens auto-rotate every 10 seconds using non-blocking millis().
 * Server data is polled periodically (default 10s).
 *
 * Build targets:
 *   Arduino UNO Q:  Upload via Arduino IDE / PlatformIO
 *   Desktop sim:    cmake && make  (uses libcurl, prints to console)
 */

#ifdef ARDUINO
// ═════════════════════════════════════════════════════════════
// Arduino Entry Point
// ═════════════════════════════════════════════════════════════
#include "gui/NavosEdgeGUI.h"
#include "network/ServerClient.h"
#include "state/NavosEdgeState.h"

NavosEdgeGUI gui;
ServerClient server;
NavosEdgeState appState;

void setup() {
    Serial.begin(115200);
    while (!Serial) { ; } // Wait for serial (UNO Q USB)

    Serial.println(F("[NAVOS] NavosEdge Display GUI starting..."));

    // Initialize shared state
    navosStateInit(appState);

    // Initialize display
    gui.begin();
    gui.showStatus("NavosEdge", "Connecting...");

    // Initialize network
    server.begin();

    // Attempt first data fetch
    Serial.println(F("[NAVOS] Fetching initial data..."));
    bool ok = server.fetchNow(appState);

    if (ok) {
        Serial.println(F("[NAVOS] Initial data received."));
    } else {
        Serial.println(F("[NAVOS] Server unavailable. Showing placeholder."));
        gui.showStatus("NavosEdge", "No server data yet");
    }

    // Force initial render
    gui.forceRedraw(appState);

    Serial.println(F("[NAVOS] GUI ready. Screen rotation: 10s"));
}

void loop() {
    // Non-blocking server poll
    bool newData = server.update(appState);

    if (newData) {
        Serial.println(F("[NAVOS] New data received."));
    }

    // Non-blocking GUI update (handles screen rotation + redraw)
    gui.update(appState);
}

#else
// ═════════════════════════════════════════════════════════════
// Desktop Simulation Entry Point
// ═════════════════════════════════════════════════════════════
#include "gui/NavosEdgeGUI.h"
#include "network/ServerClient.h"
#include "state/NavosEdgeState.h"

#include <cstdio>
#include <cstring>
#include <csignal>
#include <unistd.h>

static volatile bool g_running = true;

void signalHandler(int sig) {
    (void)sig;
    printf("\n[NAVOS] Shutting down display simulation...\n");
    g_running = false;
}


int main(int argc, char* argv[]) {
    printf("═══════════════════════════════════════════════════\n");
    printf("  NavosEdge Display GUI — Desktop Simulation\n");
    printf("  Server: %s\n", NAVOS_SERVER_URL);
    printf("  Node:   %s\n", NAVOS_NODE_ID);
    printf("  Screen rotate: %d ms\n", NAVOS_SCREEN_ROTATE_MS);
    printf("  Fetch interval: %d ms\n", NAVOS_FETCH_INTERVAL_MS);
    printf("═══════════════════════════════════════════════════\n\n");

    signal(SIGINT, signalHandler);
    signal(SIGTERM, signalHandler);

    NavosEdgeGUI gui;
    ServerClient server;
    NavosEdgeState appState;

    navosStateInit(appState);

    gui.begin();
    gui.showStatus("NavosEdge", "Connecting...");

    server.begin();

    // Initial fetch
    printf("[NAVOS] Fetching initial data...\n");
    bool ok = server.fetchNow(appState);
    if (ok) {
        printf("[NAVOS] Initial data received. AQI=%.0f PM2.5=%.1f Temp=%.1f\n",
               appState.aqi, appState.pm2_5, appState.temperature);
    } else {
        printf("[NAVOS] Server unavailable. Displaying placeholder.\n");
    }

    gui.forceRedraw(appState);

    printf("\n[NAVOS] Entering main loop (Ctrl+C to stop)...\n\n");

    uint8_t lastScreen = 255;

    while (g_running) {
        // Non-blocking server poll
        bool newData = server.update(appState);
        if (newData) {
            printf("\n[NAVOS] === NEW DATA ===\n");
            printf("  AQI=%.0f  PM1=%.1f  PM2.5=%.1f  PM10=%.1f\n",
                   appState.aqi, appState.pm1_0, appState.pm2_5, appState.pm10);
            printf("  Temp=%.1fC  Humidity=%.1f%%\n",
                   appState.temperature, appState.humidity);
            printf("  Severity: %s\n", appState.severity);
            printf("  Actions: %d\n", appState.action_count);
            printf("========================\n\n");
        }

        // Non-blocking GUI update
        gui.update(appState);

        // Log screen transitions
        uint8_t curScreen = gui.getCurrentScreen();
        if (curScreen != lastScreen) {
            const char* names[] = {"ENVIRONMENT", "ADVICE + ACTIONS", "FORECAST", "MODEL CONFIDENCE SCORE", "RAW SENSOR READINGS"};
            printf("\n──── SCREEN %d: %s ────\n\n", curScreen + 1,
                   curScreen < 5 ? names[curScreen] : "?");
            lastScreen = curScreen;
        }

        // Small sleep to avoid CPU spin (50ms = ~20 FPS equivalent)
        usleep(50000);
    }

    printf("[NAVOS] Display simulation stopped.\n");
    return 0;
}

#endif // ARDUINO
