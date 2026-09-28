/**
 * ServerClient.cpp — Network layer implementation.
 *
 * Fetches the latest intelligence result from the NavosEdge server
 * at GET /api/v1/nodes/{node_id}/latest and parses it into
 * the shared NavosEdgeState structure.
 *
 * JSON parsing uses ArduinoJson (v6/v7) which is designed for
 * constrained environments. On desktop simulation, we use a
 * minimal parser or ArduinoJson's desktop-compatible headers.
 */

#include "ServerClient.h"

#ifdef ARDUINO
// ─────────────────────────────────────────────────────────────
// Arduino (UNO Q) implementation using WiFiClient + ArduinoJson
// ─────────────────────────────────────────────────────────────
#include <WiFiS3.h>        // UNO Q WiFi (Renesas RA4M1)
#include <ArduinoHttpClient.h>
#include <ArduinoJson.h>

static WiFiClient wifiClient;
static HttpClient* httpClient = nullptr;

// Extract host and port from NAVOS_SERVER_URL
static void parseUrl(const char* url, char* host, int& port) {
    // Skip "http://"
    const char* p = url;
    if (strncmp(p, "http://", 7) == 0) p += 7;

    // Find port separator or end
    const char* colon = strchr(p, ':');
    const char* slash = strchr(p, '/');

    if (colon && (!slash || colon < slash)) {
        int hostLen = colon - p;
        strncpy(host, p, hostLen);
        host[hostLen] = '\0';
        port = atoi(colon + 1);
    } else {
        int hostLen = slash ? (slash - p) : strlen(p);
        strncpy(host, p, hostLen);
        host[hostLen] = '\0';
        port = 80;
    }
}

ServerClient::ServerClient()
    : _lastFetchMs(0), _connected(false), _failureCount(0) {}

void ServerClient::begin() {
    char host[64];
    int port = 80;
    parseUrl(NAVOS_SERVER_URL, host, port);
    httpClient = new HttpClient(wifiClient, host, port);
    httpClient->setHttpResponseTimeout(NAVOS_HTTP_TIMEOUT_MS);
}

bool ServerClient::update(NavosEdgeState& state) {
    unsigned long now = millis();
    if (now - _lastFetchMs < NAVOS_FETCH_INTERVAL_MS) {
        return false;
    }
    _lastFetchMs = now;
    return doFetch(state);
}

bool ServerClient::fetchNow(NavosEdgeState& state) {
    _lastFetchMs = millis();
    return doFetch(state);
}

bool ServerClient::isConnected() const { return _connected; }
int ServerClient::getFailureCount() const { return _failureCount; }

bool ServerClient::doFetch(NavosEdgeState& state) {
    if (!httpClient) {
        _connected = false;
        _failureCount++;
        return false;
    }

    // Build path: /api/v1/nodes/{node_id}/latest
    char path[128];
    snprintf(path, sizeof(path), "/api/v1/nodes/%s/latest", NAVOS_NODE_ID);

    httpClient->get(path);
    int statusCode = httpClient->responseStatusCode();
    String body = httpClient->responseBody();

    if (statusCode != 200) {
        _connected = false;
        _failureCount++;
        Serial.print(F("[DISPLAY] HTTP error: "));
        Serial.println(statusCode);
        return false;
    }

    bool ok = parseResponse(body.c_str(), state);
    if (ok) {
        _connected = true;
        _failureCount = 0;
        state.valid = true;
        state.last_update_ms = millis();
    } else {
        _failureCount++;
    }
    return ok;
}

bool ServerClient::parseResponse(const char* jsonBody, NavosEdgeState& state) {
    // ArduinoJson StaticJsonDocument sized for the IntelligenceResult
    StaticJsonDocument<2048> doc;
    DeserializationError err = deserializeJson(doc, jsonBody);

    if (err) {
        Serial.print(F("[DISPLAY] JSON parse error: "));
        Serial.println(err.c_str());
        return false;
    }

    // AQI (nullable)
    state.aqi = doc["aqi"] | 0.0f;

    // PM values from "pm" object
    JsonObject pm = doc["pm"];
    state.pm1_0 = pm["PM1_0"] | 0.0f;
    state.pm2_5 = pm["PM2_5"] | 0.0f;
    state.pm10  = pm["PM10"]  | 0.0f;

    // Environment
    state.temperature = doc["temperature_C"] | 0.0f;
    state.humidity    = doc["humidity_pct"]   | 0.0f;

    // Advisory
    JsonObject advisory = doc["advisory"];
    if (advisory) {
        const char* sev = advisory["severity"] | "";
        strncpy(state.severity, sev, sizeof(state.severity) - 1);
        state.severity[sizeof(state.severity) - 1] = '\0';

        const char* adv = advisory["advice"] | "";
        strncpy(state.advice, adv, sizeof(state.advice) - 1);
        state.advice[sizeof(state.advice) - 1] = '\0';

        const char* wa = advisory["weather_advice"] | "";
        strncpy(state.weather_advice, wa, sizeof(state.weather_advice) - 1);
        state.weather_advice[sizeof(state.weather_advice) - 1] = '\0';

        // Actions array
        JsonArray acts = advisory["actions"];
        state.action_count = 0;
        for (JsonVariant v : acts) {
            if (state.action_count >= NAVOS_MAX_ACTIONS) break;
            const char* a = v.as<const char*>();
            if (a) {
                strncpy(state.actions[state.action_count], a,
                        NAVOS_MAX_STRING_LEN - 1);
                state.actions[state.action_count][NAVOS_MAX_STRING_LEN - 1] = '\0';
                state.action_count++;
            }
        }
    }

    return true;
}

#else
// ─────────────────────────────────────────────────────────────
// Desktop simulation using libcurl + nlohmann/json
// (for testing the GUI without physical hardware)
// ─────────────────────────────────────────────────────────────
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <string>
#include <curl/curl.h>


static size_t curlWriteCallback(char* ptr, size_t size, size_t nmemb, void* userdata) {
    std::string* body = static_cast<std::string*>(userdata);
    body->append(ptr, size * nmemb);
    return size * nmemb;
}

ServerClient::ServerClient()
    : _lastFetchMs(0), _connected(false), _failureCount(0) {}

void ServerClient::begin() {
    curl_global_init(CURL_GLOBAL_DEFAULT);
}

bool ServerClient::update(NavosEdgeState& state) {
    unsigned long now = millis();
    if (now - _lastFetchMs < NAVOS_FETCH_INTERVAL_MS) {
        return false;
    }
    _lastFetchMs = now;
    return doFetch(state);
}

bool ServerClient::fetchNow(NavosEdgeState& state) {
    _lastFetchMs = millis();
    return doFetch(state);
}

bool ServerClient::isConnected() const { return _connected; }
int ServerClient::getFailureCount() const { return _failureCount; }

bool ServerClient::doFetch(NavosEdgeState& state) {
    CURL* curl = curl_easy_init();
    if (!curl) {
        _connected = false;
        _failureCount++;
        return false;
    }

    char url[256];
    snprintf(url, sizeof(url), "%s/api/v1/nodes/%s/latest",
             NAVOS_SERVER_URL, NAVOS_NODE_ID);

    std::string responseBody;
    curl_easy_setopt(curl, CURLOPT_URL, url);
    curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, (long)NAVOS_HTTP_TIMEOUT_MS);
    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT_MS, (long)NAVOS_HTTP_TIMEOUT_MS);
    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, curlWriteCallback);
    curl_easy_setopt(curl, CURLOPT_WRITEDATA, &responseBody);
    curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);

    CURLcode res = curl_easy_perform(curl);
    if (res != CURLE_OK) {
        fprintf(stderr, "[DISPLAY] CURL error: %s\n", curl_easy_strerror(res));
        _connected = false;
        _failureCount++;
        curl_easy_cleanup(curl);
        return false;
    }

    long httpCode = 0;
    curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &httpCode);
    curl_easy_cleanup(curl);

    if (httpCode != 200) {
        fprintf(stderr, "[DISPLAY] HTTP error: %ld\n", httpCode);
        _connected = false;
        _failureCount++;
        return false;
    }

    bool ok = parseResponse(responseBody.c_str(), state);
    if (ok) {
        _connected = true;
        _failureCount = 0;
        state.valid = true;
        state.last_update_ms = millis();
    } else {
        _failureCount++;
    }
    return ok;
}

// Minimal JSON parsing for desktop simulation
// Uses a simple approach since nlohmann/json may not be available
// in the display project. This is a lightweight field extractor.
#include <cmath>

// Helper: extract a float value for a given key from a JSON string
static bool jsonGetFloat(const char* json, const char* key, float& out) {
    char searchKey[64];
    snprintf(searchKey, sizeof(searchKey), "\"%s\"", key);
    const char* pos = strstr(json, searchKey);
    if (!pos) return false;
    pos += strlen(searchKey);
    // Skip whitespace and colon
    while (*pos && (*pos == ' ' || *pos == ':' || *pos == '\t')) pos++;
    if (!*pos) return false;
    // Handle null
    if (strncmp(pos, "null", 4) == 0) { out = 0.0f; return true; }
    out = (float)atof(pos);
    return true;
}

// Helper: extract a string value for a given key from a JSON string
static bool jsonGetString(const char* json, const char* key, char* out, int maxLen) {
    char searchKey[64];
    snprintf(searchKey, sizeof(searchKey), "\"%s\"", key);
    const char* pos = strstr(json, searchKey);
    if (!pos) return false;
    pos += strlen(searchKey);
    // Skip whitespace and colon
    while (*pos && (*pos == ' ' || *pos == ':' || *pos == '\t')) pos++;
    if (*pos != '"') return false;
    pos++; // skip opening quote
    int i = 0;
    while (*pos && *pos != '"' && i < maxLen - 1) {
        if (*pos == '\\' && *(pos + 1)) {
            pos++; // skip escape
        }
        out[i++] = *pos++;
    }
    out[i] = '\0';
    return true;
}

// Helper: find and extract an array of strings from "actions": [...]
static int jsonGetStringArray(const char* json, const char* key,
                               char out[][NAVOS_MAX_STRING_LEN], int maxItems) {
    char searchKey[64];
    snprintf(searchKey, sizeof(searchKey), "\"%s\"", key);
    const char* pos = strstr(json, searchKey);
    if (!pos) return 0;
    pos += strlen(searchKey);
    while (*pos && *pos != '[') pos++;
    if (*pos != '[') return 0;
    pos++; // skip '['

    int count = 0;
    while (*pos && *pos != ']' && count < maxItems) {
        // Skip whitespace and commas
        while (*pos && (*pos == ' ' || *pos == ',' || *pos == '\t' || *pos == '\n' || *pos == '\r')) pos++;
        if (*pos == ']') break;
        if (*pos == '"') {
            pos++; // skip opening quote
            int i = 0;
            while (*pos && *pos != '"' && i < NAVOS_MAX_STRING_LEN - 1) {
                if (*pos == '\\' && *(pos + 1)) pos++;
                out[count][i++] = *pos++;
            }
            out[count][i] = '\0';
            if (*pos == '"') pos++; // skip closing quote
            count++;
        } else {
            break; // unexpected
        }
    }
    return count;
}

bool ServerClient::parseResponse(const char* jsonBody, NavosEdgeState& state) {
    if (!jsonBody || !*jsonBody) return false;

    // Top-level fields
    jsonGetFloat(jsonBody, "aqi", state.aqi);

    // Find "pm" object — search for the PM values within it
    const char* pmObj = strstr(jsonBody, "\"pm\"");
    if (pmObj) {
        jsonGetFloat(pmObj, "PM1_0", state.pm1_0);
        jsonGetFloat(pmObj, "PM2_5", state.pm2_5);
        jsonGetFloat(pmObj, "PM10",  state.pm10);
    }

    jsonGetFloat(jsonBody, "temperature_C", state.temperature);
    jsonGetFloat(jsonBody, "humidity_pct",  state.humidity);

    // Advisory object
    const char* advObj = strstr(jsonBody, "\"advisory\"");
    if (advObj) {
        jsonGetString(advObj, "severity", state.severity, sizeof(state.severity));
        jsonGetString(advObj, "advice", state.advice, sizeof(state.advice));
        jsonGetString(advObj, "weather_advice", state.weather_advice, sizeof(state.weather_advice));
        state.action_count = jsonGetStringArray(advObj, "actions",
                                                 state.actions, NAVOS_MAX_ACTIONS);
    }

    return true;
}

#endif // ARDUINO
