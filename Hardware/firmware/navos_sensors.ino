/**
 * NavosEdge Sensor Firmware — Arduino UNO Q
 *
 * Reads all five sensor types and transmits compact JSON over USB serial:
 *   - MQ2   (Analog A0) — Combustible gas / smoke
 *   - MQ9   (Analog A1) — CO / flammable gas
 *   - MQ135 (Analog A2) — Air quality (NH3, NOx, benzene, CO2)
 *   - DHT22 (Digital D8) — Temperature & humidity
 *   - MPM10-CS (Hardware Serial1: D0 RX, D1 TX) — PM1.0, PM2.5, PM10
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

// ─── Pin Configuration ───────────────────────────────────────────
#define MQ2_PIN    A0
#define MQ9_PIN    A1
#define MQ135_PIN  A2
#define DHT22_PIN  8
// MPM10-CS uses hardware Serial1 (D0/RX, D1/TX) — no pin defines needed

// ─── Timing ──────────────────────────────────────────────────────
#define SERIAL_BAUD       115200
#define PMS_BAUD          9600
#define SAMPLE_INTERVAL   3000   // ms between readings
#define DHT_MIN_INTERVAL  2000   // DHT22 minimum 2s between reads
#define MQ_WARMUP_MS      30000  // 30s warm-up for MQ sensors
#define PMS_FRAME_TIMEOUT 3000   // ms to wait for a PMS frame

// ─── PMS Protocol Constants ─────────────────────────────────────
#define PMS_HEADER_HIGH 0x42
#define PMS_HEADER_LOW  0x4D
#define PMS_FRAME_LEN   32     // Total frame length for PMS-type sensors

// ─── DHT22 Manual Protocol ─────────────────────────────────────
// We implement DHT22 bit-banging directly to avoid library dependency
// issues on constrained boards. This keeps the firmware self-contained.

// MPM10-CS on hardware Serial1 (D0=RX, D1=TX)
#define pmsSerial Serial1

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
    // Wait for LOW→HIGH transition (bit start)
    timeout = micros() + 100;
    while (digitalRead(DHT22_PIN) == LOW) {
      if (micros() > timeout) return false;
    }
    // Measure HIGH duration: >40µs = '1', <40µs = '0'
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

  // Sanity bounds
  if (temp < -40.0f || temp > 85.0f) return false;
  if (hum < 0.0f || hum > 100.0f) return false;

  return true;
}

// ─── PMS (MPM10-CS) Frame Reader ────────────────────────────────
bool readPMS(float &pm1, float &pm25, float &pm10_val) {
  unsigned long start = millis();
  uint8_t buf[PMS_FRAME_LEN];
  int idx = 0;
  bool header_found = false;

  // Drain any stale bytes
  while (pmsSerial.available()) pmsSerial.read();

  // Wait for a complete frame
  while ((millis() - start) < PMS_FRAME_TIMEOUT) {
    if (!pmsSerial.available()) continue;

    uint8_t b = pmsSerial.read();

    if (!header_found) {
      if (b == PMS_HEADER_HIGH) {
        buf[0] = b;
        idx = 1;
        // Look for second header byte
        unsigned long h2_timeout = millis() + 100;
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

  // Verify checksum: sum of bytes 0..(N-3) == last 2 bytes
  uint16_t calc_check = 0;
  for (int i = 0; i < PMS_FRAME_LEN - 2; i++) {
    calc_check += buf[i];
  }
  uint16_t recv_check = ((uint16_t)buf[PMS_FRAME_LEN - 2] << 8) | buf[PMS_FRAME_LEN - 1];
  if (calc_check != recv_check) return false;

  // Extract atmospheric environment PM values (bytes 10-15)
  // Standard particle: bytes 4-9; Atmospheric: bytes 10-15
  pm1   = (float)(((uint16_t)buf[10] << 8) | buf[11]);
  pm25  = (float)(((uint16_t)buf[12] << 8) | buf[13]);
  pm10_val = (float)(((uint16_t)buf[14] << 8) | buf[15]);

  // Sanity: PM values should be non-negative and PM1 <= PM2.5 <= PM10
  if (pm1 < 0 || pm25 < 0 || pm10_val < 0) return false;
  if (pm1 > 1000 || pm25 > 1000 || pm10_val > 1000) return false;

  return true;
}

// ─── MQ Analog Read with Oversampling ───────────────────────────
int readMQ(int pin) {
  // Average 4 samples to reduce ADC noise on UNO Q
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
  // Use manual print to avoid String class heap fragmentation on UNO Q
  Serial.print(F("{\"mq2\":"));
  Serial.print(state.mq2_adc);
  Serial.print(F(",\"mq9\":"));
  Serial.print(state.mq9_adc);
  Serial.print(F(",\"mq135\":"));
  Serial.print(state.mq135_adc);
  Serial.print(F(",\"t\":"));
  Serial.print(state.temperature, 2);
  Serial.print(F(",\"h\":"));
  Serial.print(state.humidity, 2);
  Serial.print(F(",\"pm1\":"));
  Serial.print(state.pm1_0, 1);
  Serial.print(F(",\"pm25\":"));
  Serial.print(state.pm2_5, 1);
  Serial.print(F(",\"pm10\":"));
  Serial.print(state.pm10, 1);
  Serial.print(F(",\"dht_ok\":"));
  Serial.print(state.dht_ok ? F("true") : F("false"));
  Serial.print(F(",\"pms_ok\":"));
  Serial.print(state.pms_ok ? F("true") : F("false"));
  Serial.print(F(",\"ok\":"));
  Serial.print((state.dht_ok && state.pms_ok && state.mq_warmed) ? F("true") : F("false"));
  Serial.println(F("}"));
}

// ─── Arduino Setup ──────────────────────────────────────────────
void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial1.begin(PMS_BAUD);   // Hardware UART for MPM10-CS (D0/RX, D1/TX)

  pinMode(MQ2_PIN, INPUT);
  pinMode(MQ9_PIN, INPUT);
  pinMode(MQ135_PIN, INPUT);

  memset(&state, 0, sizeof(state));
  boot_ms = millis();

  // Signal boot
  Serial.println(F("{\"status\":\"booting\",\"firmware\":\"navos_sensors\",\"version\":\"1.0.0\"}"));
}

// ─── Arduino Loop ───────────────────────────────────────────────
void loop() {
  unsigned long now = millis();

  if ((now - last_sample_ms) < SAMPLE_INTERVAL) return;
  last_sample_ms = now;

  // Check MQ warm-up status
  state.mq_warmed = (now - boot_ms) >= MQ_WARMUP_MS;

  // Read MQ sensors (always read, but flag if not warmed)
  state.mq2_adc   = readMQ(MQ2_PIN);
  state.mq9_adc   = readMQ(MQ9_PIN);
  state.mq135_adc = readMQ(MQ135_PIN);

  // Read DHT22
  state.dht_ok = readDHT22(state.temperature, state.humidity);
  if (!state.dht_ok) {
    // Retain last known values, flag as not ok
    // (temperature and humidity keep their previous values)
  }

  // Read PMS (MPM10-CS)
  state.pms_ok = readPMS(state.pm1_0, state.pm2_5, state.pm10);
  if (!state.pms_ok) {
    // Retain last known values, flag as not ok
  }

  transmitJSON();
}
