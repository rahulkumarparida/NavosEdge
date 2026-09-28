#pragma once
/**
 * ServerClient.h — Network layer for fetching intelligence data.
 *
 * On a real UNO Q with WiFi/Ethernet shield, this uses the Arduino
 * HTTP client. For desktop simulation, it wraps libcurl.
 *
 * Fetches GET /api/v1/nodes/{node_id}/latest and parses the
 * IntelligenceResult JSON into NavosEdgeState.
 */

#include "../state/NavosEdgeState.h"

// ─────────────────────────────────────────────────────────────
// Configuration — change these in ONE place
// ─────────────────────────────────────────────────────────────
#ifndef NAVOS_SERVER_URL
#define NAVOS_SERVER_URL "http://localhost:8420"
#endif

#ifndef NAVOS_NODE_ID
#define NAVOS_NODE_ID "uno-q-001"
#endif

// How often to poll the server (milliseconds)
#ifndef NAVOS_FETCH_INTERVAL_MS
#define NAVOS_FETCH_INTERVAL_MS 10000
#endif

// HTTP request timeout (milliseconds)
#ifndef NAVOS_HTTP_TIMEOUT_MS
#define NAVOS_HTTP_TIMEOUT_MS 5000
#endif

class ServerClient {
public:
    ServerClient();

    /**
     * Initialize the network client.
     * Call once in setup().
     */
    void begin();

    /**
     * Non-blocking: call every loop(). Fetches data from the server
     * at NAVOS_FETCH_INTERVAL_MS intervals. Updates `state` in-place.
     * Returns true if new data was successfully parsed this call.
     */
    bool update(NavosEdgeState& state);

    /**
     * Force an immediate fetch regardless of timing.
     * Returns true if successful.
     */
    bool fetchNow(NavosEdgeState& state);

    /**
     * Returns true if the last fetch attempt succeeded.
     */
    bool isConnected() const;

    /**
     * Returns the number of consecutive failures.
     */
    int getFailureCount() const;

private:
    unsigned long _lastFetchMs;
    bool _connected;
    int _failureCount;

    /**
     * Perform the HTTP GET and parse JSON response into state.
     * Returns true on success.
     */
    bool doFetch(NavosEdgeState& state);

    /**
     * Parse the IntelligenceResult JSON body into NavosEdgeState.
     * Returns true on success.
     */
    bool parseResponse(const char* jsonBody, NavosEdgeState& state);
};
