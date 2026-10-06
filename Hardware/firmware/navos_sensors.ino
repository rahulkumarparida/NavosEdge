/**
 * NavosEdge Sensor Firmware — Arduino UNO Q
 *
 * Reads all five sensor types and transmits compact JSON over Arduino Serial:
 *   - MQ2   (Analog A0) — Combustible gas / smoke
 *   - MQ9   (Analog A1) — CO / flammable gas
 *   - MQ135 (Analog A2) — Air quality (NH3, NOx, benzene, CO2)
 *   - DHT22 (Digital D8) — Temperature & humidity
 *   - MPM10-CS (Hardware Serial1: D0 RX, D1 TX) — PM1.0, PM2.5, PM10
 *
 * Transport on Arduino UNO Q:
 *   Serial output is managed by Arduino_RouterBridge (BridgeMonitor) over internal
 *   high-speed UART (/dev/ttyHS1) and mirrored by arduino-router.service to its
 *   Monitor Proxy on TCP 127.0.0.1:7500. On external USB boards, it emits over USB CDC.
 *
 * Output format (one JSON line per reading):
 *   {"mq2":350,"mq9":280,"mq135":420,"t":28.50,"h":65.00,"pm1":12.0,"pm25":18.0,"pm10":25.0,"ok":true}
 *
 * Wiring:
 *   MQ2   AOUT → A0
 *   MQ9   AOUT → A1
 *   MQ135 AOUT → A2
 *   DHT22 DATA → D8  (10kΩ pull-up to VCC)
 *   MPM10-CS TX → D0 (RX on Serial1)
 *   MPM10-CS RX → D1 (TX on Serial1, optional for SET/RESET)
 */

#include <Arduino.h>
#if __has_include(<Arduino_RouterBridge.h>)
#include <Arduino_RouterBridge.h>
#endif

// ─── Diagnostic Mode Switch ───────────────────────────────────────
#ifndef NAVOS_DIAGNOSTIC_MODE
#define NAVOS_DIAGNOSTIC_MODE 0
#endif

// ─── Pin Configuration ───────────────────────────────────────────
#define MQ2_PIN    A0
#define MQ9_PIN    A1
#define MQ135_PIN  A2
#define DHT22_PIN  8
#define pmsSerial  Serial1   // MPM10-CS on hardware Serial1 (D0=RX, D1=TX)

// ─── Timing ──────────────────────────────────────────────────────
#define SERIAL_BAUD       115200
#define PMS_BAUD          9600
#define SAMPLE_INTERVAL   3000   // ms between readings
#define DHT_MIN_INTERVAL  2000   // DHT22 minimum 2s between reads
#define MQ_WARMUP_MS      30000  // 30s warm-up for MQ sensors
#define PMS_FRAME_TIMEOUT 50     // ms non-blocking check timeout

// ─── PMS Protocol Constants ─────────────────────────────────────
#define PMS_HEADER_HIGH 0x42
#define PMS_HEADER_LOW  0x4D
#define PMS_FRAME_LEN   32

// Sensor state
struct SensorState {
  int    mq2_adc;
  int    mq9_adc;
  int    mq135_adc;
  float  temperature;
  float  humidity;
  float  pm1_0;
  float  pm2_5;
  float  pm10;
  bool   dht_ok;
  bool   pms_ok;
  bool   mq_warmed;
};

static SensorState state;
static unsigned long last_sample_ms = 0;
static unsigned long boot_ms = 0;

// ─── DHT22 Bit-Bang Reader ─────────────────────────────────────
bool readDHT22(float &temp, float &hum) {
  uint8_t data[5] = {0};

  // Send start signal: pull LOW for 1ms, then HIGH for 30µs
  pinMode(DHT22_PIN, OUTPUT);
  digitalWrite(DHT22_PIN, LOW);
  delay(1);
  digitalWrite(DHT22_PIN, HIGH);
  delayMicroseconds(30);
  pinMode(DHT22_PIN, INPUT);

  // Wait for sensor response: LOW 80µs then HIGH 80µs
  unsigned long timeout = micros() + 200;
  while (digitalRead(DHT22_PIN) == HIGH) {
    if (micros() > timeout) return false;
  }
  timeout = micros() + 100;
  while (digitalRead(DHT22_PIN) == LOW) {
    if (micros() > timeout) return false;
  }
  timeout = micros() + 100;
  while (digitalRead(DHT22_PIN) == HIGH) {
    if (micros() > timeout) return false;
  }

  // Read 40 bits (5 bytes)
  for (uint8_t i = 0; i < 40; i++) {
    timeout = micros() + 100;
    while (digitalRead(DHT22_PIN) == LOW) {
      if (micros() > timeout) return false;
    }
    unsigned long t0 = micros();
    timeout = t0 + 100;
    while (digitalRead(DHT22_PIN) == HIGH) {
      if (micros() > timeout) return false;
    }
    unsigned long dur = micros() - t0;
    data[i / 8] <<= 1;
    if (dur > 40) {
      data[i / 8] |= 1;
    }
  }

  // Verify checksum
  uint8_t checksum = data[0] + data[1] + data[2] + data[3];
  if (checksum != data[4]) return false;

  // Parse humidity (unsigned 16-bit, ×0.1)
  uint16_t raw_hum = ((uint16_t)data[0] << 8) | data[1];
  hum = raw_hum * 0.1f;

  // Parse temperature (signed 16-bit, ×0.1; bit 15 = sign)
  uint16_t raw_temp = ((uint16_t)data[2] << 8) | data[3];
  if (raw_temp & 0x8000) {
    temp = -((raw_temp & 0x7FFF) * 0.1f);
  } else {
    temp = raw_temp * 0.1f;
  }

  if (temp < -40.0f || temp > 85.0f) return false;
  if (hum < 0.0f || hum > 100.0f) return false;

  return true;
}

// ─── PMS (MPM10-CS) Frame Reader ────────────────────────────────
bool readPMS(float &pm1, float &pm25, float &pm10_val) {
  if (!pmsSerial.available()) return false;

  unsigned long start = millis();
  uint8_t buf[PMS_FRAME_LEN];
  int idx = 0;
  bool header_found = false;

  while ((millis() - start) < PMS_FRAME_TIMEOUT) {
    if (!pmsSerial.available()) continue;
    uint8_t b = pmsSerial.read();

    if (!header_found) {
      if (b == PMS_HEADER_HIGH) {
        buf[0] = b;
        idx = 1;
        unsigned long h2_timeout = millis() + 20;
        while (millis() < h2_timeout) {
          if (pmsSerial.available()) {
            uint8_t b2 = pmsSerial.read();
            if (b2 == PMS_HEADER_LOW) {
              buf[1] = b2;
              idx = 2;
              header_found = true;
            }
            break;
          }
        }
      }
      continue;
    }

    buf[idx++] = b;
    if (idx >= PMS_FRAME_LEN) break;
  }

  if (idx < PMS_FRAME_LEN) return false;

  // Verify frame length field
  uint16_t frame_len = ((uint16_t)buf[2] << 8) | buf[3];
  if (frame_len != (PMS_FRAME_LEN - 4)) return false;

  // Verify checksum
  uint16_t calc_check = 0;
  for (int i = 0; i < PMS_FRAME_LEN - 2; i++) {
    calc_check += buf[i];
  }
  uint16_t recv_check = ((uint16_t)buf[PMS_FRAME_LEN - 2] << 8) | buf[PMS_FRAME_LEN - 1];
  if (calc_check != recv_check) return false;

  // Extract atmospheric environment PM values (bytes 10-15)
  pm1      = (float)(((uint16_t)buf[10] << 8) | buf[11]);
  pm25     = (float)(((uint16_t)buf[12] << 8) | buf[13]);
  pm10_val = (float)(((uint16_t)buf[14] << 8) | buf[15]);

  if (pm1 < 0.0f || pm25 < 0.0f || pm10_val < 0.0f) return false;
  if (pm1 > 1000.0f || pm25 > 1000.0f || pm10_val > 1000.0f) return false;

  return true;
}

// ─── MQ Analog Read with Oversampling ───────────────────────────
int readMQ(int pin) {
  long sum = 0;
  for (int i = 0; i < 4; i++) {
    sum += analogRead(pin);
    delayMicroseconds(250);
  }
  int val = (int)(sum / 4);
  return constrain(val, 0, 1023);
}

// ─── Transmit JSON Frame ────────────────────────────────────────
void transmitJSON() {
#if NAVOS_DIAGNOSTIC_MODE == 1
  Serial.println(F("NAVOSEDGE_MCU_TEST"));
  char diag_buf[256];
  snprintf(diag_buf, sizeof(diag_buf),
           "{\"mq2\":100,\"mq9\":110,\"mq135\":120,\"t\":25.00,\"h\":50.00,"
           "\"pm1\":10.0,\"pm25\":20.0,\"pm10\":30.0,"
           "\"dht_ok\":true,\"pms_ok\":true,\"ok\":true}");
  Serial.println(diag_buf);
#else
  bool is_ready = state.dht_ok && state.pms_ok && state.mq_warmed;
  char json_buf[256];
  snprintf(json_buf, sizeof(json_buf),
           "{\"mq2\":%d,\"mq9\":%d,\"mq135\":%d,\"t\":%.2f,\"h\":%.2f,"
           "\"pm1\":%.1f,\"pm25\":%.1f,\"pm10\":%.1f,"
           "\"dht_ok\":%s,\"pms_ok\":%s,\"ok\":%s}",
           state.mq2_adc, state.mq9_adc, state.mq135_adc,
           state.temperature, state.humidity,
           state.pm1_0, state.pm2_5, state.pm10,
           state.dht_ok ? "true" : "false",
           state.pms_ok ? "true" : "false",
           is_ready ? "true" : "false");
  Serial.println(json_buf);
#endif
}

// ─── Arduino Setup ──────────────────────────────────────────────
void setup() {
#if __has_include(<Arduino_RouterBridge.h>)
  Bridge.begin();
#endif
  Serial.begin(SERIAL_BAUD);
  pmsSerial.begin(PMS_BAUD);

  pinMode(MQ2_PIN, INPUT);
  pinMode(MQ9_PIN, INPUT);
  pinMode(MQ135_PIN, INPUT);

  memset(&state, 0, sizeof(state));
  boot_ms = millis();

  Serial.println(F("[MCU] NAVOSEDGE_MCU_BOOT_OK"));
  Serial.println(F("{\"status\":\"booting\",\"firmware\":\"navos_sensors\",\"version\":\"1.1.0\"}"));
}

// ─── Arduino Loop ───────────────────────────────────────────────
void loop() {
  unsigned long now = millis();

  if ((now - last_sample_ms) < SAMPLE_INTERVAL) return;
  last_sample_ms = now;

  // Check MQ warm-up status
  state.mq_warmed = (now - boot_ms) >= MQ_WARMUP_MS;

  // Read MQ sensors
  state.mq2_adc   = readMQ(MQ2_PIN);
  state.mq9_adc   = readMQ(MQ9_PIN);
  state.mq135_adc = readMQ(MQ135_PIN);

  // Read DHT22
  state.dht_ok = readDHT22(state.temperature, state.humidity);

  // Read PMS (MPM10-CS)
  state.pms_ok = readPMS(state.pm1_0, state.pm2_5, state.pm10);

  transmitJSON();
}
