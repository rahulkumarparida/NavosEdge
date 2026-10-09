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

// ─── Peripheral Interaction Isolation Switches ────────────────────
#ifndef ENABLE_MQ_SENSORS
#define ENABLE_MQ_SENSORS 1
#endif

#ifndef ENABLE_MPM10_SENSOR
#define ENABLE_MPM10_SENSOR 1
#endif

// ─── RAII Interrupt Lock for Zephyr RTOS ──────────────────────────
struct InterruptLock {
  InterruptLock() { noInterrupts(); }
  ~InterruptLock() { interrupts(); }
};

// ─── DHT22 Diagnostic Tracking Structure ──────────────────────────
struct DHT22Diagnostic {
  bool gpio_configured;
  bool gpio_direction_switch;
  bool start_pulse;
  bool response_detected;
  unsigned long response_timing_us;
  bool frame_received;
  uint8_t bits_received;
  bool checksum_pass;
  float temperature;
  float humidity;
  const char* failure_reason;
};

static DHT22Diagnostic dht_diag;
static unsigned long last_dht_sample_ms = 0;

// ─── Diagnostic Reporting Helper ──────────────────────────────────
static void report_dht22_diagnostics(const DHT22Diagnostic &diag) {
  Serial.println(F("[DHT22] ----- DHT22 DIAGNOSTIC AUDIT -----"));
  Serial.print(F("[DHT22] GPIO configured: "));
  Serial.println(diag.gpio_configured ? F("PASS") : F("FAIL"));
  Serial.print(F("[DHT22] GPIO direction switch: "));
  Serial.println(diag.gpio_direction_switch ? F("PASS") : F("FAIL"));
  Serial.print(F("[DHT22] Start pulse: "));
  Serial.println(diag.start_pulse ? F("PASS") : F("FAIL"));
  Serial.print(F("[DHT22] Sensor response detected: "));
  Serial.println(diag.response_detected ? F("YES") : F("NO"));
  Serial.print(F("[DHT22] Response timing: "));
  Serial.print(diag.response_timing_us);
  Serial.println(F(" us"));
  Serial.print(F("[DHT22] 40-bit frame received: "));
  Serial.println(diag.frame_received ? F("YES") : F("NO"));
  Serial.print(F("[DHT22] Bits received: "));
  Serial.print(diag.bits_received);
  Serial.println(F(" / 40"));
  Serial.print(F("[DHT22] Checksum: "));
  Serial.println(diag.checksum_pass ? F("PASS") : F("FAIL"));
  Serial.print(F("[DHT22] raw temperature="));
  Serial.print(diag.temperature, 2);
  Serial.println(F(" °C"));
  Serial.print(F("[DHT22] raw humidity="));
  Serial.print(diag.humidity, 2);
  Serial.println(F(" %"));
  Serial.print(F("[DHT22] status="));
  Serial.println(diag.failure_reason);
  Serial.println(F("[DHT22] ----------------------------------"));
}

// ─── DHT22 Bit-Bang Reader (UNO Q STM32U585 / Zephyr-Optimized) ───
bool readDHT22(float &temp, float &hum, DHT22Diagnostic *diag = nullptr) {
  uint8_t data[5] = {0};

  if (diag) {
    diag->gpio_configured = false;
    diag->gpio_direction_switch = false;
    diag->start_pulse = false;
    diag->response_detected = false;
    diag->response_timing_us = 0;
    diag->frame_received = false;
    diag->bits_received = 0;
    diag->checksum_pass = false;
    diag->temperature = 0.0f;
    diag->humidity = 0.0f;
    diag->failure_reason = "INITIALIZING";
  }

#if defined(portInputRegister) && defined(digitalPinToPinIndex)
  volatile uint32_t *idr = (volatile uint32_t *)&portInputRegister(DHT22_PIN);
  uint32_t pin_mask = (1U << digitalPinToPinIndex(DHT22_PIN));
  auto readPin = [idr, pin_mask]() -> bool {
    return (*idr & pin_mask) != 0;
  };
#elif defined(digitalPinToPort) && defined(digitalPinToPinIndex)
  GPIO_TypeDef* port = digitalPinToPort(DHT22_PIN);
  uint32_t pin_index = digitalPinToPinIndex(DHT22_PIN);
  uint32_t pin_mask = (1U << pin_index);
  auto readPin = [port, pin_mask]() -> bool {
    if (port) {
      return (port->IDR & pin_mask) != 0;
    }
    return digitalRead(DHT22_PIN) == HIGH;
  };
#else
  auto readPin = []() -> bool {
    return digitalRead(DHT22_PIN) == HIGH;
  };
#endif

  // 1. Initial line state: ensure internal pull-up is active (prevents floating line)
  pinMode(DHT22_PIN, INPUT_PULLUP);
  delayMicroseconds(50);
  if (diag) diag->gpio_configured = true;

  // 2. Start signal: drive LOW for 2000µs (guaranteed >= 1ms on Zephyr RTOS without sleep jitter)
  pinMode(DHT22_PIN, OUTPUT);
  digitalWrite(DHT22_PIN, LOW);
  if (diag) diag->gpio_direction_switch = true;
  delayMicroseconds(2000); // 2ms low pulse (AM2302 requires 1ms-10ms)
  if (diag) diag->start_pulse = true;

  // 3. Release line: brief high (15µs) then switch to INPUT_PULLUP for open-drain response
  digitalWrite(DHT22_PIN, HIGH);
  delayMicroseconds(15);
  pinMode(DHT22_PIN, INPUT_PULLUP);

  // 4. Critical Section removed globally to prevent RouterBridge UART overrun.

    // 5. Wait for sensor response: line pulled LOW (typically within 20-40µs)
    unsigned long timeout = micros() + 200;
    unsigned long t_start = micros();
    while (readPin()) {
      if (micros() > timeout) {
        if (diag) diag->failure_reason = "TIMEOUT_RESPONSE_LOW";
        return false;
      }
    }
    if (diag) {
      diag->response_detected = true;
      diag->response_timing_us = micros() - t_start;
    }

    // 6. Sensor holds LOW for ~80µs
    timeout = micros() + 200;
    while (!readPin()) {
      if (micros() > timeout) {
        if (diag) diag->failure_reason = "TIMEOUT_RESPONSE_LOW_HOLD";
        return false;
      }
    }

    // 7. Sensor holds HIGH for ~80µs
    timeout = micros() + 200;
    while (readPin()) {
      if (micros() > timeout) {
        if (diag) diag->failure_reason = "TIMEOUT_RESPONSE_HIGH_HOLD";
        return false;
      }
    }

    // 8. Read 40 data bits (5 bytes)
    for (uint8_t i = 0; i < 40; i++) {
      // Wait for 50µs LOW leading pulse before bit
      timeout = micros() + 150;
      while (!readPin()) {
        if (micros() > timeout) {
          if (diag) {
            diag->bits_received = i;
            diag->failure_reason = "TIMEOUT_BIT_LOW";
          }
          return false;
        }
      }

      // Measure HIGH pulse width: '0' is 26-28µs, '1' is 70µs
      unsigned long t0 = micros();
      timeout = t0 + 150;
      noInterrupts();
      while (readPin()) {
        if (micros() > timeout) {
          interrupts();
          if (diag) {
            diag->bits_received = i;
            diag->failure_reason = "TIMEOUT_BIT_HIGH";
          }
          return false;
        }
      }
      unsigned long dur = micros() - t0;
      interrupts();

      data[i / 8] <<= 1;
      // 45µs is optimal midpoint between 27µs and 70µs
      if (dur > 45) {
        data[i / 8] |= 1;
      }
    }

  if (diag) {
    diag->frame_received = true;
    diag->bits_received = 40;
  }

  // 9. Verify checksum (sum of first 4 bytes == 5th byte)
  uint8_t checksum = (data[0] + data[1] + data[2] + data[3]) & 0xFF;
  if (checksum != data[4]) {
    if (diag) {
      diag->checksum_pass = false;
      diag->failure_reason = "CHECKSUM_ERROR";
    }
    return false;
  }
  if (diag) diag->checksum_pass = true;

  // 10. Parse humidity (unsigned 16-bit, 0.1% resolution)
  uint16_t raw_hum = ((uint16_t)data[0] << 8) | data[1];
  hum = raw_hum * 0.1f;

  // 11. Parse temperature (signed 16-bit, 0.1°C resolution, bit 15 indicates negative)
  uint16_t raw_temp = ((uint16_t)data[2] << 8) | data[3];
  if (raw_temp & 0x8000) {
    temp = -((raw_temp & 0x7FFF) * 0.1f);
  } else {
    temp = raw_temp * 0.1f;
  }

  // Physical sensor validity limits
  if (temp < -40.0f || temp > 85.0f || hum < 0.0f || hum > 100.0f) {
    if (diag) diag->failure_reason = "VALUE_OUT_OF_RANGE";
    return false;
  }

  if (diag) {
    diag->temperature = temp;
    diag->humidity = hum;
    diag->failure_reason = "HEALTHY";
  }

  return true;
}

// ─── PMS (MPM10-CS) Non-Blocking Frame Stream Parser ──────────────
static unsigned long last_pms_rx_ms = 0;

static bool parsePMSByte(uint8_t b, float &pm1, float &pm25, float &pm10_val) {
  static uint8_t buf[PMS_FRAME_LEN];
  static uint8_t idx = 0;
  static uint8_t parse_state = 0; // 0=wait high, 1=wait low, 2=read payload

  if (parse_state == 0) {
    if (b == PMS_HEADER_HIGH) {
      buf[0] = b;
      idx = 1;
      parse_state = 1;
    }
    return false;
  } else if (parse_state == 1) {
    if (b == PMS_HEADER_LOW) {
      buf[1] = b;
      idx = 2;
      parse_state = 2;
    } else {
      parse_state = (b == PMS_HEADER_HIGH) ? 1 : 0;
      idx = (b == PMS_HEADER_HIGH) ? 1 : 0;
      if (idx == 1) buf[0] = b;
    }
    return false;
  } else { // parse_state == 2
    buf[idx++] = b;
    if (idx >= PMS_FRAME_LEN) {
      parse_state = 0;
      idx = 0;

      // Verify frame length field (standard PMS frame length payload is 28)
      uint16_t frame_len = ((uint16_t)buf[2] << 8) | buf[3];
      if (frame_len != (PMS_FRAME_LEN - 4)) return false;

      // Verify checksum: sum of bytes 0..29 equals 16-bit word at bytes 30..31
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
    return false;
  }
}

static void pollPMS() {
#if ENABLE_MPM10_SENSOR
  while (pmsSerial.available() > 0) {
    uint8_t b = pmsSerial.read();
    float p1, p25, p10;
    if (parsePMSByte(b, p1, p25, p10)) {
      state.pm1_0 = p1;
      state.pm2_5 = p25;
      state.pm10  = p10;
      state.pms_ok = true;
      last_pms_rx_ms = millis();
    }
  }
  // If sensor stops communicating for >10 seconds, flag unhealthy
  if (last_pms_rx_ms > 0 && (millis() - last_pms_rx_ms) > 10000) {
    state.pms_ok = false;
  }
#else
  state.pms_ok = false;
#endif
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
#if ENABLE_MPM10_SENSOR
  pmsSerial.begin(PMS_BAUD);
#endif

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
  // 1. Non-blocking MPM10 UART stream polling (consumes <5µs per loop)
  pollPMS();

  unsigned long now = millis();

  if ((now - last_sample_ms) < SAMPLE_INTERVAL) return;
  last_sample_ms = now;

  // Check MQ warm-up status
  state.mq_warmed = (now - boot_ms) >= MQ_WARMUP_MS;

#if ENABLE_MQ_SENSORS
  // Read MQ sensors
  state.mq2_adc   = readMQ(MQ2_PIN);
  state.mq9_adc   = readMQ(MQ9_PIN);
  state.mq135_adc = readMQ(MQ135_PIN);
#else
  state.mq2_adc   = 0;
  state.mq9_adc   = 0;
  state.mq135_adc = 0;
#endif

  // Read DHT22: respect 2-second rate limit
  if ((now - last_dht_sample_ms) >= DHT_MIN_INTERVAL) {
    last_dht_sample_ms = now;
    float t_val = 0.0f, h_val = 0.0f;
    if (readDHT22(t_val, h_val, &dht_diag)) {
      state.temperature = t_val;
      state.humidity = h_val;
      state.dht_ok = true;
    } else {
      state.dht_ok = false;
      report_dht22_diagnostics(dht_diag);
    }
  }

  transmitJSON();
}
