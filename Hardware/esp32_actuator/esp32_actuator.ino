/*
 * NavosEdge Phase 3 — NodeMCU ESP-32S V1.1 Wireless Actuator Firmware
 *
 * Protocol: HTTP REST JSON over Wi-Fi LAN (port 8080)
 * Output Pin: GPIO25 (P25) -> External NPN Low-Side Transistor Driver
 *
 * Safety Guarantees:
 *   1. GPIO25 is configured as OUTPUT and driven LOW immediately at boot.
 *   2. PHYSICAL_DRIVER_VERIFIED defaults to false (SAFE_LOCKED_OFF).
 *   3. Lease watchdog automatically forces GPIO25 LOW (FAILSAFE_OFF) if
 *      communication with the UNO Q Intelligence Server is lost.
 */

#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include "actuator_config.h"

WebServer server(ACTUATOR_HTTP_PORT);

// Runtime Actuator State
static bool fanLogicalOn = false;
static bool failsafeTriggered = false;
static unsigned long activeLeaseMs = DEFAULT_LEASE_SECONDS * 1000UL;
static unsigned long lastLeaseRenewMs = 0;
static unsigned long lastHeartbeatMs = 0;
static unsigned long lastWifiRetryMs = 0;

// Ring buffer for duplicate command_id protection
struct CommandCacheEntry {
  String commandId;
  String ackJson;
};
static CommandCacheEntry commandCache[COMMAND_HISTORY_RING_SIZE];
static size_t commandCacheIndex = 0;

// ---------------------------------------------------------------------------
// Hardware Output Control
// ---------------------------------------------------------------------------

static void applyHardwareOutput(bool turnOn) {
#if PHYSICAL_DRIVER_VERIFIED
  digitalWrite(FAN_CONTROL_GPIO, turnOn ? HIGH : LOW);
  fanLogicalOn = turnOn;
  if (turnOn) {
    failsafeTriggered = false;
  }
#else
  // Hardware safety interlock: keep GPIO25 strictly LOW until bench verified
  digitalWrite(FAN_CONTROL_GPIO, LOW);
  fanLogicalOn = false;
#endif
}

static const char* currentOutputStateString() {
#if !PHYSICAL_DRIVER_VERIFIED
  return "SAFE_LOCKED_OFF";
#else
  if (failsafeTriggered) {
    return "FAILSAFE_OFF";
  }
  return fanLogicalOn ? "ON" : "OFF";
#endif
}

// ---------------------------------------------------------------------------
// Minimal Self-Contained JSON Helpers (no external JSON library required)
// ---------------------------------------------------------------------------

static String extractJsonString(const String& body, const char* key) {
  String pattern = String("\"") + key + "\"";
  int keyIdx = body.indexOf(pattern);
  if (keyIdx < 0) return "";
  int colonIdx = body.indexOf(':', keyIdx + pattern.length());
  if (colonIdx < 0) return "";
  int firstQuote = body.indexOf('"', colonIdx + 1);
  if (firstQuote < 0) return "";
  int secondQuote = body.indexOf('"', firstQuote + 1);
  if (secondQuote < 0) return "";
  return body.substring(firstQuote + 1, secondQuote);
}

static unsigned long extractJsonULong(const String& body, const char* key, unsigned long fallback) {
  String pattern = String("\"") + key + "\"";
  int keyIdx = body.indexOf(pattern);
  if (keyIdx < 0) return fallback;
  int colonIdx = body.indexOf(':', keyIdx + pattern.length());
  if (colonIdx < 0) return fallback;
  int start = colonIdx + 1;
  while (start < (int)body.length() && (body[start] == ' ' || body[start] == '\t')) {
    start++;
  }
  String numStr = "";
  while (start < (int)body.length() && isDigit(body[start])) {
    numStr += body[start];
    start++;
  }
  if (numStr.length() == 0) return fallback;
  unsigned long val = strtoul(numStr.c_str(), nullptr, 10);
  return val > 0 ? val : fallback;
}

static String buildAckJson(
    const String& commandId,
    const char* statusStr,
    const char* outputStateStr,
    const String& errorDetails = "") {
  String json = "{";
  json += "\"command_id\":\"" + commandId + "\",";
  json += "\"actuator_id\":\"" + String(ACTUATOR_ID) + "\",";
  json += "\"status\":\"" + String(statusStr) + "\",";
  json += "\"output_state\":\"" + String(outputStateStr) + "\",";
  json += "\"physical_driver_verified\":" + String(PHYSICAL_DRIVER_VERIFIED ? "true" : "false") + ",";
  json += "\"uptime_ms\":" + String(millis());
  if (errorDetails.length() > 0) {
    json += ",\"error_details\":\"" + errorDetails + "\"";
  } else {
    json += ",\"error_details\":null";
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
  unsigned long leaseSec = extractJsonULong(body, "lease_seconds", DEFAULT_LEASE_SECONDS);

  if (commandId.length() == 0 || command.length() == 0) {
    server.send(400, "application/json",
                buildAckJson("unknown", "REJECTED", currentOutputStateString(), "Missing command_id or command"));
    return;
  }

  // Device identity validation
  if (targetActuatorId != String(ACTUATOR_ID)) {
    Serial.printf("[ACTUATOR] Rejected command %s: actuator_id mismatch (%s)\n",
                  commandId.c_str(), targetActuatorId.c_str());
    server.send(403, "application/json",
                buildAckJson(commandId, "REJECTED", currentOutputStateString(), "actuator_id mismatch"));
    return;
  }

  // Duplicate command_id idempotency check
  String cached = findCachedAck(commandId);
  if (cached.length() > 0) {
    Serial.printf("[ACTUATOR] Duplicate command_id %s — returning cached ack\n", commandId.c_str());
    server.send(200, "application/json", cached);
    return;
  }

  String ackJson;
  if (command == "FAN_ON") {
    activeLeaseMs = leaseSec * 1000UL;
    lastLeaseRenewMs = millis();
    applyHardwareOutput(true);
#if PHYSICAL_DRIVER_VERIFIED
    Serial.printf("[ACTUATOR] EXECUTED FAN_ON (GPIO%d HIGH, lease=%lus)\n", FAN_CONTROL_GPIO, leaseSec);
    ackJson = buildAckJson(commandId, "EXECUTED", currentOutputStateString());
#else
    Serial.printf("[ACTUATOR] ACKNOWLEDGED FAN_ON (SAFE_LOCKED_OFF: PHYSICAL_DRIVER_VERIFIED=false)\n");
    ackJson = buildAckJson(commandId, "ACKNOWLEDGED", "SAFE_LOCKED_OFF",
                           "Hardware output locked OFF pending NPN transistor/current bench verification");
#endif
  } else if (command == "FAN_OFF" || command == "EMERGENCY_STOP") {
    applyHardwareOutput(false);
    failsafeTriggered = false;
    Serial.printf("[ACTUATOR] EXECUTED %s (GPIO%d LOW)\n", command.c_str(), FAN_CONTROL_GPIO);
    ackJson = buildAckJson(commandId, "EXECUTED", currentOutputStateString());
  } else if (command == "GET_STATUS") {
    ackJson = buildAckJson(commandId, "EXECUTED", currentOutputStateString());
  } else {
    Serial.printf("[ACTUATOR] Unknown command: %s\n", command.c_str());
    ackJson = buildAckJson(commandId, "REJECTED", currentOutputStateString(), "Unsupported command");
    server.send(400, "application/json", ackJson);
    return;
  }

  cacheAck(commandId, ackJson);
  server.send(200, "application/json", ackJson);
}

// ---------------------------------------------------------------------------
// UNO Q Registration & Heartbeat
// ---------------------------------------------------------------------------

static void sendHeartbeatToUnoQ() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  HTTPClient http;
  String url = String("http://") + UNOQ_SERVER_HOST + ":" + String(UNOQ_SERVER_PORT) +
               "/api/v1/actuators/heartbeat";
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(3000);

  String payload = "{";
  payload += "\"actuator_id\":\"" + String(ACTUATOR_ID) + "\",";
  payload += "\"associated_node_id\":\"" + String(ASSOCIATED_NODE_ID) + "\",";
  payload += "\"actuator_type\":\"" + String(ACTUATOR_TYPE) + "\",";
  payload += "\"device_name\":\"" + String(ACTUATOR_DEVICE_NAME) + "\",";
  payload += "\"ip_address\":\"" + WiFi.localIP().toString() + "\",";
  payload += "\"output_state\":\"" + String(currentOutputStateString()) + "\",";
  payload += "\"physical_driver_verified\":" + String(PHYSICAL_DRIVER_VERIFIED ? "true" : "false") + ",";
  payload += "\"gpio_pin\":" + String(FAN_CONTROL_GPIO) + ",";
  payload += "\"firmware_version\":\"" + String(FIRMWARE_VERSION) + "\"";
  payload += "}";

  int code = http.POST(payload);
  if (code > 0) {
    Serial.printf("[HEARTBEAT] UNO Q responded HTTP %d (state=%s)\n",
                  code, currentOutputStateString());
  } else {
    Serial.printf("[HEARTBEAT] Failed to reach UNO Q: %s\n",
                  http.errorToString(code).c_str());
  }
  http.end();
}

static void ensureWifiConnected() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }
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
  // 1. Safe GPIO initialization BEFORE anything else
  pinMode(FAN_CONTROL_GPIO, OUTPUT);
  digitalWrite(FAN_CONTROL_GPIO, LOW);
  fanLogicalOn = false;

  Serial.begin(115200);
  delay(200);
  Serial.println();
  Serial.println("====================================================");
  Serial.println(" NavosEdge Phase 3 — NodeMCU ESP-32S V1.1 Actuator");
  Serial.printf(" Actuator ID: %s | Node: %s | GPIO: %d\n",
                ACTUATOR_ID, ASSOCIATED_NODE_ID, FAN_CONTROL_GPIO);
  Serial.printf(" PHYSICAL_DRIVER_VERIFIED: %s\n",
                PHYSICAL_DRIVER_VERIFIED ? "true (ARMED)" : "false (SAFE_LOCKED_OFF)");
  Serial.println("====================================================");

  ensureWifiConnected();
  unsigned long startWait = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startWait < 10000UL) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[WIFI] Connected! IP=%s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("[WIFI] Initial connection pending; will retry in loop()");
  }

  server.on("/actuator/status", HTTP_GET, handleGetStatus);
  server.on("/actuator/command", HTTP_POST, handlePostCommand);
  server.begin();
  Serial.printf("[HTTP] Actuator server listening on port %d\n", ACTUATOR_HTTP_PORT);

  sendHeartbeatToUnoQ();
  lastHeartbeatMs = millis();
}

void loop() {
  ensureWifiConnected();
  server.handleClient();

  unsigned long now = millis();

  // Lease watchdog: revert fan OFF if lease expires without renewal
  if (fanLogicalOn && (now - lastLeaseRenewMs > activeLeaseMs)) {
    Serial.println("[WATCHDOG] Command lease expired — forcing GPIO25 LOW (FAILSAFE_OFF)");
    applyHardwareOutput(false);
    failsafeTriggered = true;
  }

  // Periodic heartbeat to UNO Q
  if (now - lastHeartbeatMs >= HEARTBEAT_INTERVAL_MS) {
    lastHeartbeatMs = now;
    sendHeartbeatToUnoQ();
  }
}

