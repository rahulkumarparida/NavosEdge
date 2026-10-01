#pragma once

/**
 * sensor_validator.hpp — Validates SensorData against physical sensor bounds.
 *
 * Used by both MockSensorSource and SerialSensorSource to ensure data
 * integrity before the reading is transmitted to the Intelligence Server.
 */

#include <string>
#include <vector>
#include <cmath>
#include <iostream>

#include "sensor.hpp"
#include "constants.hpp"

namespace navos {

struct ValidationResult {
    bool valid = true;
    std::vector<std::string> warnings;
    std::vector<std::string> errors;

    void warn(const std::string& msg) {
        warnings.push_back(msg);
    }

    void error(const std::string& msg) {
        errors.push_back(msg);
        valid = false;
    }

    void print_summary() const {
        for (const auto& w : warnings) {
            std::cerr << "[VALIDATE] WARN: " << w << "\n";
        }
        for (const auto& e : errors) {
            std::cerr << "[VALIDATE] ERROR: " << e << "\n";
        }
    }
};

class SensorValidator {
public:
    // ADC bounds (10-bit: 0-1023)
    static constexpr int ADC_MIN = constants::ADC_MIN;
    static constexpr int ADC_MAX = constants::ADC_MAX;

    // Voltage bounds (5V reference)
    static constexpr double VOLTAGE_MIN = constants::VOLTAGE_MIN;
    static constexpr double VOLTAGE_MAX = constants::VOLTAGE_MAX;

    // DHT22 operating range
    static constexpr double TEMP_MIN = constants::TEMP_MIN;
    static constexpr double TEMP_MAX = constants::TEMP_MAX;
    static constexpr double HUM_MIN  = constants::HUM_MIN;
    static constexpr double HUM_MAX  = constants::HUM_MAX;

    // PM max sane value (µg/m³) — WHO says >500 is extreme
    static constexpr double PM_MAX = constants::PM_MAX;

    // PM ordering tolerance (matches Python schema)
    static constexpr double PM_TOLERANCE = constants::PM_TOLERANCE;

    /**
     * Validate a SensorData reading.
     * Returns ValidationResult with detailed error/warning messages.
     * Invalid readings should NOT be transmitted to the server.
     */
    static ValidationResult validate(const SensorData& d) {
        ValidationResult r;

        // --- NaN / Inf checks ---
        if (!is_finite(d.pm1_0))   r.error("PM1.0 is NaN/Inf");
        if (!is_finite(d.pm2_5))   r.error("PM2.5 is NaN/Inf");
        if (!is_finite(d.pm10))    r.error("PM10 is NaN/Inf");
        if (!is_finite(d.mq2_voltage_v))   r.error("MQ2 voltage is NaN/Inf");
        if (!is_finite(d.mq9_voltage_v))   r.error("MQ9 voltage is NaN/Inf");
        if (!is_finite(d.mq135_voltage_v)) r.error("MQ135 voltage is NaN/Inf");
        if (!is_finite(d.temperature_c))   r.error("Temperature is NaN/Inf");
        if (!is_finite(d.humidity_pct))    r.error("Humidity is NaN/Inf");

        // Stop early if we have NaN/Inf — range checks would be meaningless
        if (!r.valid) return r;

        // --- MQ sensor ADC range ---
        validate_adc(r, "MQ2",   d.mq2_raw_adc);
        validate_adc(r, "MQ9",   d.mq9_raw_adc);
        validate_adc(r, "MQ135", d.mq135_raw_adc);

        // --- MQ sensor voltage range ---
        validate_voltage(r, "MQ2",   d.mq2_voltage_v);
        validate_voltage(r, "MQ9",   d.mq9_voltage_v);
        validate_voltage(r, "MQ135", d.mq135_voltage_v);

        // --- ADC ↔ Voltage consistency ---
        validate_adc_voltage_consistency(r, "MQ2",   d.mq2_raw_adc,   d.mq2_voltage_v);
        validate_adc_voltage_consistency(r, "MQ9",   d.mq9_raw_adc,   d.mq9_voltage_v);
        validate_adc_voltage_consistency(r, "MQ135", d.mq135_raw_adc, d.mq135_voltage_v);

        // --- Temperature ---
        if (d.temperature_c < TEMP_MIN || d.temperature_c > TEMP_MAX) {
            r.error("Temperature " + std::to_string(d.temperature_c) +
                    "°C out of range [" + std::to_string(TEMP_MIN) +
                    ", " + std::to_string(TEMP_MAX) + "]");
        }

        // --- Humidity ---
        if (d.humidity_pct < HUM_MIN || d.humidity_pct > HUM_MAX) {
            r.error("Humidity " + std::to_string(d.humidity_pct) +
                    "% out of range [" + std::to_string(HUM_MIN) +
                    ", " + std::to_string(HUM_MAX) + "]");
        }

        // --- PM values: non-negative ---
        if (d.pm1_0 < 0.0) r.error("PM1.0 is negative: " + std::to_string(d.pm1_0));
        if (d.pm2_5 < 0.0) r.error("PM2.5 is negative: " + std::to_string(d.pm2_5));
        if (d.pm10  < 0.0) r.error("PM10 is negative: "  + std::to_string(d.pm10));

        // --- PM values: upper bound ---
        if (d.pm1_0 > PM_MAX) r.warn("PM1.0 exceeds " + std::to_string(PM_MAX) + " µg/m³");
        if (d.pm2_5 > PM_MAX) r.warn("PM2.5 exceeds " + std::to_string(PM_MAX) + " µg/m³");
        if (d.pm10  > PM_MAX) r.warn("PM10 exceeds "  + std::to_string(PM_MAX) + " µg/m³");

        // --- PM ordering: PM1.0 <= PM2.5 <= PM10 ---
        if (d.pm1_0 > d.pm2_5 + PM_TOLERANCE) {
            r.error("PM ordering violated: PM1.0 (" + std::to_string(d.pm1_0) +
                    ") > PM2.5 (" + std::to_string(d.pm2_5) + ")");
        }
        if (d.pm2_5 > d.pm10 + PM_TOLERANCE) {
            r.error("PM ordering violated: PM2.5 (" + std::to_string(d.pm2_5) +
                    ") > PM10 (" + std::to_string(d.pm10) + ")");
        }

        // --- Metadata ---
        if (d.node_id.empty()) {
            r.error("node_id is empty");
        }
        if (d.timestamp.empty()) {
            r.error("timestamp is empty");
        }

        return r;
    }

    /**
     * Clamp a SensorData to valid ranges (used for partial recovery).
     * Returns a copy with values clamped.
     */
    static SensorData clamp(const SensorData& d) {
        SensorData out = d;

        out.mq2_raw_adc   = clamp_int(d.mq2_raw_adc, ADC_MIN, ADC_MAX);
        out.mq9_raw_adc   = clamp_int(d.mq9_raw_adc, ADC_MIN, ADC_MAX);
        out.mq135_raw_adc = clamp_int(d.mq135_raw_adc, ADC_MIN, ADC_MAX);

        out.mq2_voltage_v   = clamp_double(d.mq2_voltage_v, VOLTAGE_MIN, VOLTAGE_MAX);
        out.mq9_voltage_v   = clamp_double(d.mq9_voltage_v, VOLTAGE_MIN, VOLTAGE_MAX);
        out.mq135_voltage_v = clamp_double(d.mq135_voltage_v, VOLTAGE_MIN, VOLTAGE_MAX);

        out.temperature_c = clamp_double(d.temperature_c, TEMP_MIN, TEMP_MAX);
        out.humidity_pct  = clamp_double(d.humidity_pct, HUM_MIN, HUM_MAX);

        out.pm1_0 = std::max(0.0, d.pm1_0);
        out.pm2_5 = std::max(out.pm1_0, std::max(0.0, d.pm2_5));
        out.pm10  = std::max(out.pm2_5, std::max(0.0, d.pm10));

        return out;
    }

private:
    static bool is_finite(double v) {
        return std::isfinite(v);
    }

    static int clamp_int(int v, int lo, int hi) {
        if (v < lo) return lo;
        if (v > hi) return hi;
        return v;
    }

    static double clamp_double(double v, double lo, double hi) {
        if (!std::isfinite(v)) return lo;
        if (v < lo) return lo;
        if (v > hi) return hi;
        return v;
    }

    static void validate_adc(ValidationResult& r, const std::string& name, int adc) {
        if (adc < ADC_MIN || adc > ADC_MAX) {
            r.error(name + " ADC value " + std::to_string(adc) +
                    " out of range [0, 1023]");
        }
    }

    static void validate_voltage(ValidationResult& r, const std::string& name, double v) {
        if (v < VOLTAGE_MIN || v > VOLTAGE_MAX) {
            r.error(name + " voltage " + std::to_string(v) +
                    "V out of range [0.0, 5.0]");
        }
    }

    static void validate_adc_voltage_consistency(ValidationResult& r,
                                                  const std::string& name,
                                                  int adc, double voltage) {
        // Expected voltage = adc * (5.0 / 1023.0)
        double expected = static_cast<double>(adc) * (5.0 / 1023.0);
        double diff = std::abs(voltage - expected);
        if (diff > 0.05) {
            r.warn(name + " ADC/voltage mismatch: ADC=" + std::to_string(adc) +
                   " → expected " + std::to_string(expected) +
                   "V, got " + std::to_string(voltage) + "V");
        }
    }
};

} // namespace navos
