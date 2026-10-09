#pragma once

#include <string>
#include <cmath>
#include <chrono>
#include <iomanip>
#include <sstream>
#include <algorithm>
#include <iostream>

namespace navos {

enum class SimulationScenario {
    NORMAL,
    HIGH_PM,
    TRAFFIC,
    DUST
};

inline SimulationScenario parse_scenario(const std::string& str) {
    if (str == "high_pm" || str == "high-pm") return SimulationScenario::HIGH_PM;
    if (str == "traffic") return SimulationScenario::TRAFFIC;
    if (str == "dust" || str == "heavy_dust") return SimulationScenario::DUST;
    return SimulationScenario::NORMAL;
}

inline std::string scenario_to_string(SimulationScenario s) {
    switch (s) {
        case SimulationScenario::HIGH_PM: return "high_pm";
        case SimulationScenario::TRAFFIC: return "traffic";
        case SimulationScenario::DUST: return "dust";
        default: return "normal";
    }
}

struct SensorData {
    // Particulate matter (µg/m³)
    double pm1_0   = 0.0;
    double pm2_5   = 0.0;
    double pm10    = 0.0;

    // MQ gas sensors
    int    mq2_raw_adc   = 0;
    double mq2_voltage_v = 0.0;
    int    mq9_raw_adc   = 0;
    double mq9_voltage_v = 0.0;
    int    mq135_raw_adc   = 0;
    double mq135_voltage_v = 0.0;

    // Environment
    double temperature_c = 0.0;
    double humidity_pct  = 0.0;

    // Sensor health & validity flags
    bool   is_valid      = true;
    bool   dht_ok        = true;
    bool   pms_ok        = true;
    bool   mq_ok         = true;
    bool   mq_warmed     = true;

    // Sequence & diagnostics
    uint64_t sample_seq  = 0;
    std::string error_msg;
    std::string gas_calibration_status = "uncalibrated";

    // Metadata
    std::string timestamp;
    std::string node_id;

    std::string to_summary() const {
        std::ostringstream oss;
        oss << "MQ-2=[ADC:" << mq2_raw_adc << ", " << std::fixed << std::setprecision(3) << mq2_voltage_v << "V]"
            << ", MQ-9=[ADC:" << mq9_raw_adc << ", " << mq9_voltage_v << "V]"
            << ", MQ-135=[ADC:" << mq135_raw_adc << ", " << mq135_voltage_v << "V]"
            << ", DHT22=[Temp:" << std::setprecision(2) << temperature_c << " °C, Hum:" << humidity_pct << "%]"
            << ", MPM10=[PM1.0:" << std::setprecision(1) << pm1_0 << ", PM2.5:" << pm2_5 << ", PM10:" << pm10 << " ug/m3]"
            << ", Valid=" << (is_valid ? "YES" : "NO");
        return oss.str();
    }
};

// Abstract sensor source interface
class SensorSource {
public:
    virtual ~SensorSource() = default;
    virtual SensorData read() = 0;
    virtual void set_scenario(SimulationScenario s) = 0;
};

// Generates deterministic mock sensor data for testing
class MockSensorSource : public SensorSource {
public:
    explicit MockSensorSource(const std::string& node_id, SimulationScenario scenario = SimulationScenario::NORMAL)
        : node_id_(node_id), scenario_(scenario), count_(0) {}

    void set_scenario(SimulationScenario s) override {
        scenario_ = s;
    }

    SensorData read() override {
        SensorData d;
        d.node_id = node_id_;
        d.timestamp = now_iso8601();

        double phase = static_cast<double>(count_);
        double base_pm1 = 12.0;
        double base_pm25 = 18.0;
        double base_pm10 = 25.0;

        int base_mq2 = 350;
        int base_mq9 = 280;
        int base_mq135 = 420;

        switch (scenario_) {
            case SimulationScenario::HIGH_PM:
                base_pm1  = 120.0;
                base_pm25 = 180.0;
                base_pm10 = 260.0;
                base_mq2  = 450;
                base_mq9  = 380;
                base_mq135 = 520;
                break;
            case SimulationScenario::TRAFFIC:
                base_pm1  = 45.0;
                base_pm25 = 75.0;
                base_pm10 = 110.0;
                base_mq2  = 650;
                base_mq9  = 580;
                base_mq135 = 620;
                break;
            case SimulationScenario::DUST:
                base_pm1  = 40.0;
                base_pm25 = 110.0;
                base_pm10 = 380.0;
                base_mq2  = 350;
                base_mq9  = 280;
                base_mq135 = 400;
                break;
            case SimulationScenario::NORMAL:
            default:
                break;
        }

        // PM values — deterministic sinusoidal variation, preserving PM1.0 <= PM2.5 <= PM10
        double pm_base1  = base_pm1 + 2.0 * std::sin(phase * 0.1);
        double pm_base25 = base_pm25 + 3.0 * std::sin(phase * 0.1);
        double pm_base10 = base_pm10 + 4.0 * std::sin(phase * 0.1);

        d.pm1_0 = std::max(0.0, pm_base1);
        d.pm2_5 = std::max(d.pm1_0, pm_base25);
        d.pm10  = std::max(d.pm2_5, pm_base10);

        // MQ2
        d.mq2_raw_adc   = clamp_adc(base_mq2 + static_cast<int>(20 * std::sin(phase * 0.15)));
        d.mq2_voltage_v  = adc_to_voltage(d.mq2_raw_adc);

        // MQ9
        d.mq9_raw_adc   = clamp_adc(base_mq9 + static_cast<int>(15 * std::sin(phase * 0.12)));
        d.mq9_voltage_v  = adc_to_voltage(d.mq9_raw_adc);

        // MQ135
        d.mq135_raw_adc   = clamp_adc(base_mq135 + static_cast<int>(25 * std::sin(phase * 0.08)));
        d.mq135_voltage_v  = adc_to_voltage(d.mq135_raw_adc);

        // Environment
        d.temperature_c = 28.5 + 2.0 * std::sin(phase * 0.2);
        d.temperature_c = std::clamp(d.temperature_c, -40.0, 85.0);

        d.humidity_pct = 65.0 + 5.0 * std::sin(phase * 0.1);
        d.humidity_pct = std::clamp(d.humidity_pct, 0.0, 100.0);

        ++count_;
        return d;
    }

private:
    std::string node_id_;
    SimulationScenario scenario_;
    int count_;

    static int clamp_adc(int val) {
        return std::clamp(val, 0, 1023);
    }

    static double adc_to_voltage(int raw_adc) {
        return static_cast<double>(raw_adc) * (5.0 / 1023.0);
    }

    static std::string now_iso8601() {
        auto now = std::chrono::system_clock::now();
        auto time_t_now = std::chrono::system_clock::to_time_t(now);
        std::tm tm_buf{};
        gmtime_r(&time_t_now, &tm_buf);

        std::ostringstream oss;
        oss << std::put_time(&tm_buf, "%Y-%m-%dT%H:%M:%S") << "Z";
        return oss.str();
    }
};

} // namespace navos
