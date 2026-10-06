/**
 * mcu_display.ino — NavosEdge Unified MCU Application (Physical Sensors + Display RPC Bridge)
 *
 * Runs on Arduino UNO Q MCU (arduino:zephyr:unoq).
 *
 * Capabilities:
 *   1. Physical Sensor Acquisition & Transmission:
 *      - MQ-2   (Analog A0) — Combustible gas / smoke
 *      - MQ-9   (Analog A1) — CO / flammable gas
 *      - MQ-135 (Analog A2) — Air quality (NH3, NOx, CO2, benzene)
 *      - DHT22  (Digital D8) — Temperature & relative humidity
 *      - MPM10-CS (Hardware Serial1: D0 RX, D1 TX) — PM1.0, PM2.5, PM10
 *      Transmits validated line-delimited JSON over Arduino Serial / Monitor
 *      which is routed by Arduino_RouterBridge over internal UART to arduino-router,
 *      streaming live on TCP 127.0.0.1:7500 for the Linux Hardware bridge.
 *
 *   2. Physical MPI3501 LCD GUI (480x320 landscape):
 *      Rotates 4 NavosEdge screens non-blockingly using millis():
 *        - Screen 1: Environment (15s)
 *        - Screen 2: Advisory (10s)
 *        - Screen 3: Forecast (10s)
 *        - Screen 4: Intelligence (10s)
 *
 *   3. Arduino_RouterBridge RPC Server:
 *      Exposes 5 RPC methods for Linux McuBridge:
 *        - update_environment
 *        - update_advice
 *        - update_actions
 *        - update_predictions
 *        - update_raw_sensors
 */

#include <Arduino.h>
#include <Arduino_RouterBridge.h>
#include <UNOQ_MPI3501.h>
#include "NavosEdgeState.h"
#include "NavosEdgeGUI.h"

// ─── Diagnostic Mode Switch ───────────────────────────────────────
// Set to 1 to enable diagnostic beacon ("NAVOSEDGE_MCU_TEST") and static
// identifiable test values for independent communication-path verification.
// Set to 0 for production physical sensor sampling.
#ifndef NAVOS_DIAGNOSTIC_MODE
#define NAVOS_DIAGNOSTIC_MODE 0
#endif

// ─── Sensor Pin Configuration ─────────────────────────────────────
#define MQ2_PIN    A0
#define MQ9_PIN    A1
#define MQ135_PIN  A2
#define DHT22_PIN  8
#define pmsSerial  Serial1   // Hardware UART for MPM10-CS (D0=RX, D1=TX)

// ─── Timing Constants ─────────────────────────────────────────────
#define SERIAL_BAUD         115200
#define PMS_BAUD            9600
#define SENSOR_SAMPLE_MS    3000   // ms between sensor transmissions
#define MQ_WARMUP_MS        30000  // 30s warm-up period for MQ sensors
#define PMS_FRAME_TIMEOUT   50     // non-blocking frame check timeout (ms)
#define PMS_FRAME_LEN       32
#define PMS_HEADER_HIGH     0x42
#define PMS_HEADER_LOW      0x4D

// ─── Sensor State ─────────────────────────────────────────────────
struct SensorHWState {
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

static NavosEdgeGUI gui;
static NavosEdgeState state;
static SensorHWState hw_sensors;
static unsigned long boot_ms = 0;
static unsigned long last_sensor_sample_ms = 0;

// ─── RPC Methods (Linux -> MCU Display) ───────────────────────────
void update_environment(float aqi, float pm1_0, float pm2_5, float pm10, float temp, float hum) {
    state.aqi = aqi;
    state.pm1_0 = pm1_0;
    state.pm2_5 = pm2_5;
    state.pm10 = pm10;
    state.temperature = temp;
    state.humidity = hum;
    state.valid = true;
    state.last_update_ms = millis();
}

void update_advice(String severity, String advice, String weather_advice) {
    (void)weather_advice;
    strncpy(state.severity, severity.c_str(), sizeof(state.severity) - 1);
    state.severity[sizeof(state.severity) - 1] = '\0';

    strncpy(state.advice, advice.c_str(), sizeof(state.advice) - 1);
    state.advice[sizeof(state.advice) - 1] = '\0';

    state.valid = true;
    state.last_update_ms = millis();
}

void update_actions(String actions_csv) {
    state.action_count = 0;
    int start = 0;
    int len = actions_csv.length();
    while (start < len && state.action_count < NAVOS_MAX_ACTIONS) {
        int end = actions_csv.indexOf(';', start);
        if (end == -1) end = len;
        String actStr = actions_csv.substring(start, end);
        actStr.trim();
        if (actStr.length() > 0) {
            strncpy(state.actions[state.action_count], actStr.c_str(), NAVOS_MAX_STRING_LEN - 1);
            state.actions[state.action_count][NAVOS_MAX_STRING_LEN - 1] = '\0';
            state.action_count++;
        }
        start = end + 1;
    }

    state.valid = true;
    state.last_update_ms = millis();
}

void update_predictions(String source, float source_conf, String forecast_trend, float forecast_conf, float pm25_pred0, float pm25_pred1, String anomaly_status) {
    strncpy(state.source_value, source.c_str(), sizeof(state.source_value) - 1);
    state.source_value[sizeof(state.source_value) - 1] = '\0';
    state.source_confidence = source_conf;

    strncpy(state.forecast_trend, forecast_trend.c_str(), sizeof(state.forecast_trend) - 1);
    state.forecast_trend[sizeof(state.forecast_trend) - 1] = '\0';
    state.forecast_confidence = forecast_conf;

    state.forecast_pm2_5_pred[0] = pm25_pred0;
    state.forecast_pm2_5_pred[1] = pm25_pred1;
    state.forecast_pm2_5_count = (pm25_pred0 > 0.0f || pm25_pred1 > 0.0f) ? 2 : 0;

    strncpy(state.anomaly_status, anomaly_status.c_str(), sizeof(state.anomaly_status) - 1);
    state.anomaly_status[sizeof(state.anomaly_status) - 1] = '\0';

    state.valid = true;
    state.last_update_ms = millis();
}

void update_raw_sensors(int mq2_adc, float mq2_v, int mq9_adc, float mq9_v, int mq135_adc, float mq135_v) {
    state.mq2_adc = (uint16_t)mq2_adc;
    state.mq2_voltage = mq2_v;
    state.mq9_adc = (uint16_t)mq9_adc;
    state.mq9_voltage = mq9_v;
    state.mq135_adc = (uint16_t)mq135_adc;
    state.mq135_voltage = mq135_v;

    state.valid = true;
    state.last_update_ms = millis();
}

// ─── DHT22 Bit-Bang Reader ────────────────────────────────────────
static bool readDHT22(float &temp, float &hum) {
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

// ─── PMS (MPM10-CS) Frame Reader (Non-blocking) ───────────────────
static bool readPMS(float &pm1, float &pm25, float &pm10_val) {
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

// ─── MQ Analog Read with Oversampling ─────────────────────────────
static int readMQ(int pin) {
    long sum = 0;
    for (int i = 0; i < 4; i++) {
        sum += analogRead(pin);
        delayMicroseconds(250);
    }
    int val = (int)(sum / 4);
    return constrain(val, 0, 1023);
}

// ─── Transmit Unified Sensor JSON ─────────────────────────────────
static void sample_and_transmit_sensors(unsigned long now) {
#if NAVOS_DIAGNOSTIC_MODE == 1
    // Diagnostic verification mode: emit clear beacon and identifiable packet
    Serial.println(F("NAVOSEDGE_MCU_TEST"));
    char diag_buf[256];
    snprintf(diag_buf, sizeof(diag_buf),
             "{\"mq2\":100,\"mq9\":110,\"mq135\":120,\"t\":25.00,\"h\":50.00,"
             "\"pm1\":10.0,\"pm25\":20.0,\"pm10\":30.0,"
             "\"dht_ok\":true,\"pms_ok\":true,\"ok\":true}");
    Serial.println(diag_buf);
#else
    // Production physical sensor sampling
    hw_sensors.mq_warmed = (now - boot_ms) >= MQ_WARMUP_MS;

    hw_sensors.mq2_adc   = readMQ(MQ2_PIN);
    hw_sensors.mq9_adc   = readMQ(MQ9_PIN);
    hw_sensors.mq135_adc = readMQ(MQ135_PIN);

    float t_val, h_val;
    if (readDHT22(t_val, h_val)) {
        hw_sensors.temperature = t_val;
        hw_sensors.humidity = h_val;
        hw_sensors.dht_ok = true;
    } else {
        hw_sensors.dht_ok = false;
    }

    float p1, p25, p10;
    if (readPMS(p1, p25, p10)) {
        hw_sensors.pm1_0 = p1;
        hw_sensors.pm2_5 = p25;
        hw_sensors.pm10 = p10;
        hw_sensors.pms_ok = true;
    } else {
        hw_sensors.pms_ok = false;
    }

    bool is_ready = hw_sensors.dht_ok && hw_sensors.pms_ok && hw_sensors.mq_warmed;

    // Build atomic JSON string in a single stack buffer (avoids multi-packet RPC splitting)
    char json_buf[256];
    snprintf(json_buf, sizeof(json_buf),
             "{\"mq2\":%d,\"mq9\":%d,\"mq135\":%d,\"t\":%.2f,\"h\":%.2f,"
             "\"pm1\":%.1f,\"pm25\":%.1f,\"pm10\":%.1f,"
             "\"dht_ok\":%s,\"pms_ok\":%s,\"ok\":%s}",
             hw_sensors.mq2_adc, hw_sensors.mq9_adc, hw_sensors.mq135_adc,
             hw_sensors.temperature, hw_sensors.humidity,
             hw_sensors.pm1_0, hw_sensors.pm2_5, hw_sensors.pm10,
             hw_sensors.dht_ok ? "true" : "false",
             hw_sensors.pms_ok ? "true" : "false",
             is_ready ? "true" : "false");

    Serial.println(json_buf);

    // Keep display state updated with live raw sensor readings
    state.mq2_adc = (uint16_t)hw_sensors.mq2_adc;
    state.mq2_voltage = hw_sensors.mq2_adc * (5.0f / 1023.0f);
    state.mq9_adc = (uint16_t)hw_sensors.mq9_adc;
    state.mq9_voltage = hw_sensors.mq9_adc * (5.0f / 1023.0f);
    state.mq135_adc = (uint16_t)hw_sensors.mq135_adc;
    state.mq135_voltage = hw_sensors.mq135_adc * (5.0f / 1023.0f);
#endif
}

// ─── Arduino Setup ────────────────────────────────────────────────
void setup() {
    Serial.begin(SERIAL_BAUD);
    pmsSerial.begin(PMS_BAUD);

    pinMode(MQ2_PIN, INPUT);
    pinMode(MQ9_PIN, INPUT);
    pinMode(MQ135_PIN, INPUT);

    memset(&hw_sensors, 0, sizeof(hw_sensors));
    navosStateInit(state);
    boot_ms = millis();

    gui.begin();
    gui.showStatus("NavosEdge MCU", "Connecting RPC Bridge...");

    Bridge.begin();
    Bridge.provide_safe("update_environment", update_environment);
    Bridge.provide_safe("update_advice", update_advice);
    Bridge.provide_safe("update_actions", update_actions);
    Bridge.provide_safe("update_predictions", update_predictions);
    Bridge.provide_safe("update_raw_sensors", update_raw_sensors);

    Serial.println(F("[MCU] NAVOSEDGE_MCU_BOOT_OK"));
    Serial.println(F("{\"status\":\"booting\",\"firmware\":\"navos_unified\",\"version\":\"1.1.0\"}"));
    Serial.println(F("[MCU] RPC methods registered: update_environment, update_advice, update_actions, update_predictions, update_raw_sensors"));

    gui.showStatus("NavosEdge MCU", "RPC & Sensors Ready");
}

// ─── Arduino Loop ─────────────────────────────────────────────────
void loop() {
    // 1. Update physical display GUI non-blockingly
    gui.update(state);

    // 2. Periodically sample physical sensors and stream JSON
    unsigned long now = millis();
    if ((now - last_sensor_sample_ms) >= SENSOR_SAMPLE_MS) {
        last_sensor_sample_ms = now;
        sample_and_transmit_sensors(now);
    }
}
