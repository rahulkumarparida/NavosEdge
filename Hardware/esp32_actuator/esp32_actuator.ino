/*
 * NavosEdge — NodeMCU ESP-32S V1.1 Alert Bulb + Buzzer Firmware
 *
 * Protocol: HTTP REST JSON over Wi-Fi LAN (port 8080)
 * Output Pins:
 *   - GPIO25 (P25) -> Alert Bulb / LED driver (relay/MOSFET/LED + resistor)
 *   - GPIO26 (P26) -> Synchronized Buzzer (rings whenever alert bulb is ON)
 *
 * Safety & Recovery Guarantees:
 *   1. GPIO25 (bulb) and GPIO26 (buzzer) are configured as OUTPUT and driven OFF
 *      immediately at boot before Serial or Wi-Fi initialization.
 *   2. Only light/alarm control commands (LIGHT_ON, LIGHT_OFF, GET_STATUS,
 *      EMERGENCY_STOP) are executed; legacy fan commands (FAN_ON/FAN_OFF) are
 *      explicitly rejected with HTTP 400.
 *   3. Every 15s heartbeat parses UNO Q's authoritative `desired_state` and
 *      `system_ready` flags so reboots, missed commands, and reconnects stay
 *      synchronized with active environmental alerts.
 *   4. Communication-loss watchdog forces bulb & buzzer OFF (FAILSAFE_OFF) only if
 *      UNO Q becomes unreachable for longer than STALE_COMM_TIMEOUT_MS (75s),
 *      preventing premature shutoff during sustained active hazards.
 */

#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include "actuator_config.h"

WebServer server(ACTUATOR_HTTP_PORT);

// Runtime Alert Bulb & Buzzer State
static bool lightLogicalOn = false;
static bool buzzerLogicalOn = false;
static bool commLossTriggered = false;
static bool hasBackendContact = false;
static bool lastSystemReady = false;
static bool wasWifiConnected = false;

static unsigned long lastBackendContactMs = 0;
static unsigned long lastHeartbeatMs = 0;
static unsigned long lastWifiRetryMs = 0;

static String activeEventId = "";
static String activeSeverity = "";
static String activeAlertType = "";

// Ring buffer for duplicate command_id protection
struct CommandCacheEntry {
  String commandId;
  String ackJson;
};
static CommandCacheEntry commandCache[COMMAND_HISTORY_RING_SIZE];
static size_t commandCacheIndex = 0;

// Forward declaration
static void sendHeartbeatToUnoQ(bool allowFollowupSync = true);

// ---------------------------------------------------------------------------
// Hardware Output Control
// ---------------------------------------------------------------------------

static void applyHardwareOutput(bool turnOn) {
#if PHYSICAL_DRIVER_VERIFIED
  #if ALERT_LIGHT_ACTIVE_HIGH
  digitalWrite(ALERT_LIGHT_GPIO, turnOn ? HIGH : LOW);
  #else
  digitalWrite(ALERT_LIGHT_GPIO, turnOn ? LOW : HIGH);
  #endif

  #if ALERT_BUZZER_ENABLED
    #if ALERT_BUZZER_PASSIVE_TONE
  if (turnOn) {
    tone(ALERT_BUZZER_GPIO, ALERT_BUZZER_TONE_HZ);
  } else {
    noTone(ALERT_BUZZER_GPIO);
    digitalWrite(ALERT_BUZZER_GPIO, ALERT_BUZZER_ACTIVE_HIGH ? LOW : HIGH);
  }
    #else
      #if ALERT_BUZZER_ACTIVE_HIGH
  digitalWrite(ALERT_BUZZER_GPIO, turnOn ? HIGH : LOW);
      #else
  digitalWrite(ALERT_BUZZER_GPIO, turnOn ? LOW : HIGH);
      #endif
    #endif
  #endif

  lightLogicalOn = turnOn;
  buzzerLogicalOn = (ALERT_BUZZER_ENABLED && turnOn);
  if (turnOn) {
    commLossTriggered = false;
  }
#else
  digitalWrite(ALERT_LIGHT_GPIO, LOW);
  #if ALERT_BUZZER_ENABLED
    #if ALERT_BUZZER_PASSIVE_TONE
  noTone(ALERT_BUZZER_GPIO);
    #endif
  digitalWrite(ALERT_BUZZER_GPIO, ALERT_BUZZER_ACTIVE_HIGH ? LOW : HIGH);
  #endif
  lightLogicalOn = false;
  buzzerLogicalOn = false;
#endif
}

static const char* currentOutputStateString() {
#if !PHYSICAL_DRIVER_VERIFIED
  return "SAFE_LOCKED_OFF";
#else
  if (commLossTriggered) {
    return "FAILSAFE_OFF";
  }
  return lightLogicalOn ? "ON" : "OFF";
#endif
}

// ---------------------------------------------------------------------------
// Self-Contained JSON Helpers (handles strings, nulls, booleans, and integers)
// ---------------------------------------------------------------------------

static int findJsonValueStart(const String& body, const char* key) {
  String pattern = String("\"") + key + "\"";
  int searchFrom = 0;
  while (searchFrom < (int)body.length()) {
    int keyIdx = body.indexOf(pattern, searchFrom);
    if (keyIdx < 0) {
      return -1;
    }

    // Ensure key token boundary on the left
    if (keyIdx > 0) {
      char prevCh = body[keyIdx - 1];
      if (prevCh != '{' && prevCh != ',' && prevCh != ' ' &&
          prevCh != '\t' && prevCh != '\r' && prevCh != '\n') {
        searchFrom = keyIdx + pattern.length();
        continue;
      }
    }

    int afterKey = keyIdx + pattern.length();
    while (afterKey < (int)body.length() &&
           (body[afterKey] == ' ' || body[afterKey] == '\t' ||
            body[afterKey] == '\r' || body[afterKey] == '\n')) {
      afterKey++;
    }
    if (afterKey >= (int)body.length() || body[afterKey] != ':') {
      searchFrom = afterKey;
      continue;
    }

    int valStart = afterKey + 1;
    while (valStart < (int)body.length() &&
           (body[valStart] == ' ' || body[valStart] == '\t' ||
            body[valStart] == '\r' || body[valStart] == '\n')) {
      valStart++;
    }
    return valStart < (int)body.length() ? valStart : -1;
  }
  return -1;
}

static String extractJsonString(const String& body, const char* key) {
  int valStart = findJsonValueStart(body, key);
  if (valStart < 0 || body[valStart] != '"') {
    return "";
  }
  String out = "";
  for (int i = valStart + 1; i < (int)body.length(); ++i) {
    char ch = body[i];
    if (ch == '\\' && (i + 1) < (int)body.length()) {
      out += body[++i];
      continue;
    }
    if (ch == '"') {
      return out;
    }
    out += ch;
  }
  return "";
}

static bool extractJsonBool(const String& body, const char* key, bool fallback) {
  int valStart = findJsonValueStart(body, key);
  if (valStart < 0) {
    return fallback;
  }
  if (body.substring(valStart, min((int)body.length(), valStart + 4)) == "true") {
    return true;
  }
  if (body.substring(valStart, min((int)body.length(), valStart + 5)) == "false") {
    return false;
  }
  return fallback;
}

static unsigned long extractJsonULong(
    const String& body, const char* key, unsigned long fallback) {
  int valStart = findJsonValueStart(body, key);
  if (valStart < 0 || !isDigit(body[valStart])) {
    return fallback;
  }
  String numStr = "";
  int idx = valStart;
  while (idx < (int)body.length() && isDigit(body[idx])) {
    numStr += body[idx];
    idx++;
  }
  if (numStr.length() == 0) {
    return fallback;
  }
  return strtoul(numStr.c_str(), nullptr, 10);
}

static String jsonEscape(const String& raw) {
  String out = "";
  out.reserve(raw.length());
  for (int i = 0; i < (int)raw.length(); ++i) {
    char ch = raw[i];
    if (ch == '"' || ch == '\\') {
      out += '\\';
      out += ch;
    } else if (ch == '\n' || ch == '\r' || ch == '\t') {
      out += ' ';
    } else {
      out += ch;
    }
  }
  return out;
}

static String buildAckJson(
    const String& commandId,
    const char* statusStr,
    const char* outputStateStr,
    const String& errorDetails = "") {
  String json = "{";
  json += "\"command_id\":\"" + jsonEscape(commandId) + "\",";
  json += "\"actuator_id\":\"" + String(ACTUATOR_ID) + "\",";
  json += "\"actuator_type\":\"" + String(ACTUATOR_TYPE) + "\",";
  json += "\"status\":\"" + String(statusStr) + "\",";
  json += "\"output_state\":\"" + String(outputStateStr) + "\",";
  json += "\"physical_driver_verified\":" + String(PHYSICAL_DRIVER_VERIFIED ? "true" : "false") + ",";
  json += "\"gpio_pin\":" + String(ALERT_LIGHT_GPIO) + ",";
  json += "\"buzzer_gpio\":" + String(ALERT_BUZZER_GPIO) + ",";
  json += "\"buzzer_active\":" + String(buzzerLogicalOn ? "true" : "false") + ",";
  json += "\"wifi_connected\":" + String(WiFi.status() == WL_CONNECTED ? "true" : "false") + ",";
  json += "\"system_ready\":" + String(lastSystemReady ? "true" : "false") + ",";
  json += "\"uptime_ms\":" + String(millis()) + ",";
  if (activeEventId.length() > 0) {
    json += "\"active_event_id\":\"" + jsonEscape(activeEventId) + "\",";
  } else {
    json += "\"active_event_id\":null,";
  }
  if (errorDetails.length() > 0) {
    json += "\"error_details\":\"" + jsonEscape(errorDetails) + "\"";
  } else {
    json += "\"error_details\":null";
  }
  json += "}";
  return json;
}

static String findCachedAck(const String& commandId) {
  for (size_t i = 0; i < COMMAND_HISTORY_RING_SIZE; ++i) {
    if (commandCache[i].commandId == commandId) {
      return commandCache[i].ackJson;
    }
  }
  return "";
}

static void cacheAck(const String& commandId, const String& ackJson) {
  commandCache[commandCacheIndex].commandId = commandId;
  commandCache[commandCacheIndex].ackJson = ackJson;
  commandCacheIndex = (commandCacheIndex + 1) % COMMAND_HISTORY_RING_SIZE;
}

// ---------------------------------------------------------------------------
// HTTP Handlers
// ---------------------------------------------------------------------------

static void handleGetStatus() {
  String json = buildAckJson("status-poll", "EXECUTED", currentOutputStateString());
  server.send(200, "application/json", json);
}

static void handlePostCommand() {
  if (!server.hasArg("plain")) {
    server.send(400, "application/json",
                buildAckJson("unknown", "REJECTED", currentOutputStateString(), "Empty request body"));
    return;
  }

  String body = server.arg("plain");
  String commandId = extractJsonString(body, "command_id");
  String targetActuatorId = extractJsonString(body, "actuator_id");
  String command = extractJsonString(body, "command");
  String eventId = extractJsonString(body, "event_id");

  if (commandId.length() == 0 || command.length() == 0) {
    server.send(400, "application/json",
                buildAckJson("unknown", "REJECTED", currentOutputStateString(),
                             "Missing command_id or command"));
    return;
  }

  // Device identity validation
  if (targetActuatorId != String(ACTUATOR_ID)) {
    Serial.printf("[ACTUATOR] Rejected command %s: actuator_id mismatch (%s)\n",
                  commandId.c_str(), targetActuatorId.c_str());
    server.send(403, "application/json",
                buildAckJson(commandId, "REJECTED", currentOutputStateString(),
                             "actuator_id mismatch"));
    return;
  }

  // Refresh UNO Q contact clock on authenticated command arrival
  hasBackendContact = true;
  lastBackendContactMs = millis();

  // Duplicate command_id idempotency check
  String cached = findCachedAck(commandId);
  if (cached.length() > 0) {
    Serial.printf("[ACTUATOR] Duplicate command_id %s — returning cached ack\n", commandId.c_str());
    server.send(200, "application/json", cached);
    return;
  }

  String ackJson;
  if (command == "LIGHT_ON") {
    commLossTriggered = false;
    if (eventId.length() > 0) {
      activeEventId = eventId;
    }
    applyHardwareOutput(true);
#if PHYSICAL_DRIVER_VERIFIED
    Serial.printf("[ACTUATOR] EXECUTED LIGHT_ON (bulb=GPIO%d ON, buzzer=GPIO%d %s, event=%s)\n",
                  ALERT_LIGHT_GPIO,
                  ALERT_BUZZER_GPIO,
                  ALERT_BUZZER_ENABLED ? "ON" : "DISABLED",
                  activeEventId.length() > 0 ? activeEventId.c_str() : "none");
    ackJson = buildAckJson(commandId, "EXECUTED", currentOutputStateString());
#else
    Serial.println("[ACTUATOR] ACKNOWLEDGED LIGHT_ON (SAFE_LOCKED_OFF: PHYSICAL_DRIVER_VERIFIED=false)");
    ackJson = buildAckJson(commandId, "ACKNOWLEDGED", "SAFE_LOCKED_OFF",
                           "Hardware output locked OFF because PHYSICAL_DRIVER_VERIFIED=false");
#endif
  } else if (command == "LIGHT_OFF" || command == "EMERGENCY_STOP") {
    commLossTriggered = false;
    applyHardwareOutput(false);
    activeEventId = "";
    activeSeverity = "";
    activeAlertType = "";
    Serial.printf("[ACTUATOR] EXECUTED %s (bulb=GPIO%d OFF, buzzer=GPIO%d OFF)\n",
                  command.c_str(), ALERT_LIGHT_GPIO, ALERT_BUZZER_GPIO);
    ackJson = buildAckJson(commandId, "EXECUTED", currentOutputStateString());
  } else if (command == "GET_STATUS") {
    ackJson = buildAckJson(commandId, "EXECUTED", currentOutputStateString());
  } else if (command == "FAN_ON" || command == "FAN_OFF") {
    Serial.printf("[ACTUATOR] Rejected non-light command %s on %s\n",
                  command.c_str(), ACTUATOR_TYPE);
    ackJson = buildAckJson(commandId, "REJECTED", currentOutputStateString(),
                           "Unsupported fan command on ESP32_ALERT_LIGHT");
    cacheAck(commandId, ackJson);
    server.send(400, "application/json", ackJson);
    return;
  } else {
    Serial.printf("[ACTUATOR] Unknown command: %s\n", command.c_str());
    ackJson = buildAckJson(commandId, "REJECTED", currentOutputStateString(),
                           "Unsupported command");
    cacheAck(commandId, ackJson);
    server.send(400, "application/json", ackJson);
    return;
  }

  cacheAck(commandId, ackJson);
  server.send(200, "application/json", ackJson);
}

// ---------------------------------------------------------------------------
// UNO Q Registration, Heartbeat & Desired-State Sync
// ---------------------------------------------------------------------------

static void sendHeartbeatToUnoQ(bool allowFollowupSync) {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  HTTPClient http;
  String url = String("http://") + UNOQ_SERVER_HOST + ":" + String(UNOQ_SERVER_PORT) +
               "/api/v1/actuators/heartbeat";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);

  String payload = "{";
  payload += "\"actuator_id\":\"" + String(ACTUATOR_ID) + "\",";
  payload += "\"associated_node_id\":\"" + String(ASSOCIATED_NODE_ID) + "\",";
  payload += "\"actuator_type\":\"" + String(ACTUATOR_TYPE) + "\",";
  payload += "\"device_name\":\"" + String(ACTUATOR_DEVICE_NAME) + "\",";
  payload += "\"ip_address\":\"" + WiFi.localIP().toString() + "\",";
  payload += "\"output_state\":\"" + String(currentOutputStateString()) + "\",";
  payload += "\"physical_driver_verified\":" + String(PHYSICAL_DRIVER_VERIFIED ? "true" : "false") + ",";
  payload += "\"gpio_pin\":" + String(ALERT_LIGHT_GPIO) + ",";
  payload += "\"firmware_version\":\"" + String(FIRMWARE_VERSION) + "\"";
  payload += "}";

  int code = http.POST(payload);
  String respBody = (code == 200) ? http.getString() : "";
  http.end();

  if (code == 200) {
    hasBackendContact = true;
    lastBackendContactMs = millis();

    bool systemReady = extractJsonBool(respBody, "system_ready", false);
    String desiredState = extractJsonString(respBody, "desired_state");
    String eventId = extractJsonString(respBody, "active_event_id");
    unsigned long activeCount = extractJsonULong(respBody, "active_event_count", 0);
    String severity = extractJsonString(respBody, "severity");
    String alertType = extractJsonString(respBody, "alert_type");

    lastSystemReady = systemReady;

    if (desiredState == "ON" || desiredState == "OFF") {
      String prevStateStr = String(currentOutputStateString());
      bool shouldBeOn = (systemReady && desiredState == "ON");

      if (shouldBeOn) {
        activeEventId = eventId;
        activeSeverity = severity;
        activeAlertType = alertType;
      } else {
        activeEventId = "";
        activeSeverity = "";
        activeAlertType = "";
        commLossTriggered = false;
      }

      if (shouldBeOn != lightLogicalOn) {
        applyHardwareOutput(shouldBeOn);
        Serial.printf("[SYNC] Desired state applied via heartbeat -> GPIO%d %s (ready=%s, events=%lu, id=%s, sev=%s)\n",
                      ALERT_LIGHT_GPIO,
                      currentOutputStateString(),
                      systemReady ? "true" : "false",
                      activeCount,
                      activeEventId.length() > 0 ? activeEventId.c_str() : "none",
                      activeSeverity.length() > 0 ? activeSeverity.c_str() : "none");
      } else {
        commLossTriggered = false;
      }

      if (allowFollowupSync && String(currentOutputStateString()) != prevStateStr) {
        sendHeartbeatToUnoQ(false);
      }
    }

    Serial.printf("[HEARTBEAT] UNO Q HTTP 200 (state=%s, desired=%s, ready=%s, events=%lu)\n",
                  currentOutputStateString(),
                  desiredState.length() > 0 ? desiredState.c_str() : "unknown",
                  systemReady ? "true" : "false",
                  activeCount);
  } else if (code > 0) {
    Serial.printf("[HEARTBEAT] UNO Q responded HTTP %d (state=%s)\n",
                  code, currentOutputStateString());
  } else {
    Serial.printf("[HEARTBEAT] Failed to reach UNO Q: %s\n",
                  http.errorToString(code).c_str());
  }
}

static void ensureWifiConnected() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wasWifiConnected) {
      wasWifiConnected = true;
      Serial.printf("[WIFI] Connected! IP=%s — resyncing with UNO Q\n",
                    WiFi.localIP().toString().c_str());
      sendHeartbeatToUnoQ(true);
      lastHeartbeatMs = millis();
    }
    return;
  }

  wasWifiConnected = false;
  unsigned long now = millis();
  if (now - lastWifiRetryMs < WIFI_RECONNECT_INTERVAL_MS) {
    return;
  }
  lastWifiRetryMs = now;
  Serial.printf("[WIFI] Connecting to %s...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
}

// ---------------------------------------------------------------------------
// Arduino Lifecycle
// ---------------------------------------------------------------------------

void setup() {
  // 1. Safe GPIO initialization BEFORE Serial or Wi-Fi (bulb & buzzer forced OFF)
  pinMode(ALERT_LIGHT_GPIO, OUTPUT);
#if ALERT_LIGHT_ACTIVE_HIGH
  digitalWrite(ALERT_LIGHT_GPIO, LOW);
#else
  digitalWrite(ALERT_LIGHT_GPIO, HIGH);
#endif

#if ALERT_BUZZER_ENABLED
  pinMode(ALERT_BUZZER_GPIO, OUTPUT);
  digitalWrite(ALERT_BUZZER_GPIO, ALERT_BUZZER_ACTIVE_HIGH ? LOW : HIGH);
#endif
  lightLogicalOn = false;
  buzzerLogicalOn = false;
  commLossTriggered = false;

  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println("====================================================");
  Serial.println(" NavosEdge — NodeMCU ESP-32S V1.1 Alert Bulb & Buzzer");
  Serial.printf(" Actuator ID: %s | Node: %s | Type: %s\n",
                ACTUATOR_ID, ASSOCIATED_NODE_ID, ACTUATOR_TYPE);
  Serial.printf(" Bulb GPIO: %d (%s) | Buzzer GPIO: %d (%s) | ARMED: %s\n",
                ALERT_LIGHT_GPIO,
                ALERT_LIGHT_ACTIVE_HIGH ? "active-HIGH" : "active-LOW relay",
                ALERT_BUZZER_GPIO,
                ALERT_BUZZER_ENABLED ? (ALERT_BUZZER_PASSIVE_TONE ? "passive-tone" : "active-level") : "disabled",
                PHYSICAL_DRIVER_VERIFIED ? "true" : "false (SAFE_LOCKED_OFF)");
  Serial.println("====================================================");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWifiRetryMs = millis();

  unsigned long startWait = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startWait < 10000UL) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    wasWifiConnected = true;
    Serial.printf("[WIFI] Connected! IP=%s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("[WIFI] Initial connection pending; will retry in loop()");
  }

  server.on("/actuator/status", HTTP_GET, handleGetStatus);
  server.on("/health", HTTP_GET, handleGetStatus);
  server.on("/actuator/command", HTTP_POST, handlePostCommand);
  server.begin();
  Serial.printf("[HTTP] Alert light server listening on port %d\n", ACTUATOR_HTTP_PORT);

  sendHeartbeatToUnoQ(true);
  lastHeartbeatMs = millis();
}

void loop() {
  ensureWifiConnected();
  server.handleClient();

  unsigned long now = millis();

  // Communication-loss watchdog: only force LOW if UNO Q has been unreachable > 75s
  if (lightLogicalOn && hasBackendContact &&
      (now - lastBackendContactMs > STALE_COMM_TIMEOUT_MS)) {
    Serial.printf("[WATCHDOG] UNO Q unreachable for >%lus — forcing GPIO%d LOW (FAILSAFE_OFF)\n",
                  STALE_COMM_TIMEOUT_MS / 1000UL, ALERT_LIGHT_GPIO);
    applyHardwareOutput(false);
    commLossTriggered = true;
  }

  // Periodic heartbeat & desired-state sync with UNO Q
  if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatMs = now;
    sendHeartbeatToUnoQ(true);
  }
}
