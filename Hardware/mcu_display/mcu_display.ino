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
#define SENSOR_SAMPLE_MS    10000  // ms between sensor transmissions (matches Linux 10s interval)
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

// ─── Peripheral Interaction Isolation Switches ────────────────────
#ifndef ENABLE_MQ_SENSORS
#define ENABLE_MQ_SENSORS 1
#endif

#ifndef ENABLE_MPM10_SENSOR
#define ENABLE_MPM10_SENSOR 1
#endif

static DHT22Diagnostic dht_diag;
static unsigned long last_dht_sample_ms = 0;
static unsigned long last_dht_dur_us = 0;
#define DHT_MIN_INTERVAL 2000

// ─── DHT22 Bit-Bang Reader (UNO Q STM32U585 / Non-blocking to Router/UART) ───
static bool readDHT22(float &temp, float &hum, DHT22Diagnostic *diag = nullptr) {
    uint8_t data[5] = {0};
    unsigned long dht_start_us = micros();

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

    // Direct hardware register pointer caching for single-cycle pin sampling on STM32U5
    GPIO_TypeDef* port = digitalPinToPort(DHT22_PIN);
    uint32_t pin_index = digitalPinToPinIndex(DHT22_PIN);
    uint32_t pin_mask = (1U << pin_index);

    auto readPin = [port, pin_mask]() -> bool {
        if (port) {
            return (port->IDR & pin_mask) != 0;
        }
        return digitalRead(DHT22_PIN) == HIGH;
    };

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

    // 4. Sample response & 40-bit frame with interrupts ENABLED to preserve UART RX & Router RPCs.
    // If an ISR preempts timing, the 8-bit checksum detects it and rejects the corrupted frame cleanly.
    unsigned long t_start = micros();
    while (readPin()) {
        if ((micros() - t_start) > 200) {
            if (diag) diag->failure_reason = "TIMEOUT_RESPONSE_LOW";
            return false;
        }
    }
    if (diag) {
        diag->response_detected = true;
        diag->response_timing_us = micros() - t_start;
    }

    // 5. Sensor holds LOW for ~80µs
    t_start = micros();
    while (!readPin()) {
        if ((micros() - t_start) > 200) {
            if (diag) diag->failure_reason = "TIMEOUT_RESPONSE_LOW_HOLD";
            return false;
        }
    }

    // 6. Sensor holds HIGH for ~80µs
    t_start = micros();
    while (readPin()) {
        if ((micros() - t_start) > 200) {
            if (diag) diag->failure_reason = "TIMEOUT_RESPONSE_HIGH_HOLD";
            return false;
        }
    }

    // 7. Read 40 data bits (5 bytes)
    for (uint8_t i = 0; i < 40; i++) {
        // Wait for 50µs LOW leading pulse before bit
        t_start = micros();
        while (!readPin()) {
            if ((micros() - t_start) > 150) {
                if (diag) {
                    diag->bits_received = i;
                    diag->failure_reason = "TIMEOUT_BIT_LOW";
                }
                return false;
            }
        }

        // Measure HIGH pulse width: '0' is 26-28µs, '1' is 70µs
        unsigned long t0 = micros();
        noInterrupts();
        while (readPin()) {
            if ((micros() - t0) > 150) {
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

    last_dht_dur_us = micros() - dht_start_us;

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

// ─── PMS (MPM10-CS) Non-Blocking Frame Stream Parser ──────────────
static unsigned long last_pms_rx_ms = 0;

static bool parsePMSByte(uint8_t b, float &pm1, float &pm25, float &pm10_val) {
    static uint8_t buf[PMS_FRAME_LEN];
    static uint8_t idx = 0;
    static uint8_t state = 0; // 0=wait high, 1=wait low, 2=read payload

    if (state == 0) {
        if (b == PMS_HEADER_HIGH) {
            buf[0] = b;
            idx = 1;
            state = 1;
        }
        return false;
    } else if (state == 1) {
        if (b == PMS_HEADER_LOW) {
            buf[1] = b;
            idx = 2;
            state = 2;
        } else {
            state = (b == PMS_HEADER_HIGH) ? 1 : 0;
            idx = (b == PMS_HEADER_HIGH) ? 1 : 0;
            if (idx == 1) buf[0] = b;
        }
        return false;
    } else { // state == 2
        buf[idx++] = b;
        if (idx >= PMS_FRAME_LEN) {
            state = 0;
            idx = 0;

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
        return false;
    }
}

static void pollPMS() {
    while (pmsSerial.available() > 0) {
        uint8_t b = pmsSerial.read();
        float p1, p25, p10;
        if (parsePMSByte(b, p1, p25, p10)) {
            hw_sensors.pm1_0 = p1;
            hw_sensors.pm2_5 = p25;
            hw_sensors.pm10 = p10;
            hw_sensors.pms_ok = true;
            last_pms_rx_ms = millis();
        }
    }
    // Sensor validity timeout: mark false if no valid frame for 10 seconds
    if (millis() - last_pms_rx_ms > 10000) {
        hw_sensors.pms_ok = false;
    }
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

#if ENABLE_MQ_SENSORS
    hw_sensors.mq2_adc   = readMQ(MQ2_PIN);
    hw_sensors.mq9_adc   = readMQ(MQ9_PIN);
    hw_sensors.mq135_adc = readMQ(MQ135_PIN);
#else
    hw_sensors.mq2_adc   = 0;
    hw_sensors.mq9_adc   = 0;
    hw_sensors.mq135_adc = 0;
#endif

    // DHT22 sampling: enforce DHT22 minimum interval (2000ms)
    if ((now - last_dht_sample_ms) >= DHT_MIN_INTERVAL) {
        last_dht_sample_ms = now;
        float t_val = 0.0f, h_val = 0.0f;
        if (readDHT22(t_val, h_val, &dht_diag)) {
            hw_sensors.temperature = t_val;
            hw_sensors.humidity = h_val;
            hw_sensors.dht_ok = true;
        } else {
            hw_sensors.dht_ok = false;
            // Report diagnostic failure audit for deep troubleshooting (rate-limited to 30s to prevent flooding monitor)
            static unsigned long last_dht_diag_report_ms = 0;
            if (now - last_dht_diag_report_ms >= 30000) {
                last_dht_diag_report_ms = now;
                report_dht22_diagnostics(dht_diag);
            }
        }
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
void background_yield() {
#if ENABLE_MPM10_SENSOR
    pollPMS();
#endif
    Bridge.update();
}

void setup() {
    Serial.begin(SERIAL_BAUD);
#if ENABLE_MPM10_SENSOR
    pmsSerial.begin(PMS_BAUD);
#endif

    pinMode(MQ2_PIN, INPUT);
    pinMode(MQ9_PIN, INPUT);
    pinMode(MQ135_PIN, INPUT);

    memset(&hw_sensors, 0, sizeof(hw_sensors));
    navosStateInit(state);
    boot_ms = millis();

    gui.setYieldCallback(background_yield);
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
    unsigned long loop_start_us = micros();

    // 0. Non-blocking MPM10 (PMS) UART stream poll
#if ENABLE_MPM10_SENSOR
    pollPMS();
#endif

    // 1. Update physical display GUI non-blockingly
    unsigned long gui_start_us = micros();
    gui.update(state);
    unsigned long gui_dur_us = micros() - gui_start_us;

    // 2. Periodically sample physical sensors and stream JSON
    unsigned long now = millis();
    if ((now - last_sensor_sample_ms) >= SENSOR_SAMPLE_MS) {
        last_sensor_sample_ms = now;
        sample_and_transmit_sensors(now);
    }

    // 3. Periodic timing telemetry (every 30s)
    static unsigned long last_telemetry_ms = 0;
    if (now - last_telemetry_ms >= 30000) {
        last_telemetry_ms = now;
        Serial.print(F("[MCU] Telemetry: loop_us="));
        Serial.print(micros() - loop_start_us);
        Serial.print(F(" gui_us="));
        Serial.print(gui_dur_us);
        Serial.print(F(" dht_us="));
        Serial.print(last_dht_dur_us);
        Serial.print(F(" dht_ok="));
        Serial.print(hw_sensors.dht_ok ? F("1") : F("0"));
        Serial.print(F(" pms_ok="));
        Serial.println(hw_sensors.pms_ok ? F("1") : F("0"));
    }
}
