#pragma once

#include <string>
#include <memory>
#include <atomic>
#include <thread>
#include <iostream>
#include <algorithm>
#include <csignal>
#include <iomanip>
#include <cmath>
#include <nlohmann/json.hpp>

#include "config.hpp"
#include "sensor.hpp"
#include "sensor_validator.hpp"
#include "http_client.hpp"
#include "sse_client.hpp"
#include "mcu_bridge.hpp"
#include "../display/state/NavosEdgeState.h"

namespace navos {

class HardwareBridge {
public:
    HardwareBridge(HardwareConfig cfg,
                   std::unique_ptr<SensorSource> sensor,
                   HttpClient& http)
        : cfg_(std::move(cfg))
        , sensor_(std::move(sensor))
        , http_(http)
        , mcu_bridge_("/var/run/arduino-router.sock")
        , running_(true)
        , consecutive_failures_(0)
        , sampling_interval_seconds_(cfg_.sampling_interval_seconds)
        , reading_count_(0)
        , is_warmup_complete_(false)
        , is_ready_ack_(false)
    {
        navosStateInit(app_state_);
    }

    ~HardwareBridge() {
        stop();
    }

    void run() {
        std::cout << "[HW] Starting node: " << cfg_.node_id << "\n";

        // Connect to MCU physical display bridge via Arduino Router
        mcu_bridge_.open_socket();

        // Phase 1: Wait for server health & readiness
        if (!wait_for_server()) {
            std::cerr << "[HW] Server health/readiness check failed. Exiting.\n";
            return;
        }

        std::cout << "[HW] Server: connected\n";

        // Phase 2: Start SSE Control Channel
        SseClient sse(cfg_.server_url, cfg_.node_id, [this](const std::string& event, const std::string& data) {
            handle_sse_event(event, data);
        });
        
        std::cout << "[HW] SSE connected\n";
        sse.start();

        // Phase 3: Mandatory 30-Second Sensor Warm-up Period
        std::cout << "[HW] Initiating mandatory 30-second sensor warm-up period...\n";
        std::cout << "[HW] Sensors warming up (PM, MQ2, MQ9, MQ135, DHT22)... Data transmission deferred.\n";

        constexpr int warmup_seconds = 30;
        for (int i = 0; i < warmup_seconds * 2 && running_.load(); ++i) {
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
        }

        if (!running_.load()) {
            sse.stop();
            mcu_bridge_.close_socket();
            return;
        }

        is_warmup_complete_.store(true);
        std::cout << "[HW] 30-second sensor warm-up complete. Sensors are READY.\n";

        // Phase 4: Send READY handshake signal to Intelligence Server
        if (!send_ready_signal()) {
            std::cerr << "[HW] Initial READY handshake deferred. Retrying in main cycle...\n";
        }

        // Phase 5: Main non-blocking 60-second acquisition & display loop
        auto last_transmit_time = std::chrono::steady_clock::now();

        while (running_.load()) {
            auto now = std::chrono::steady_clock::now();
            int current_interval = sampling_interval_seconds_.load();
            auto elapsed_sec = std::chrono::duration_cast<std::chrono::seconds>(now - last_transmit_time).count();

            if (elapsed_sec >= current_interval) {
                if (is_warmup_complete_.load() && is_ready_ack_.load()) {
                    transmit_reading();
                    last_transmit_time = std::chrono::steady_clock::now();
                } else if (is_warmup_complete_.load() && !is_ready_ack_.load()) {
                    send_ready_signal();
                }
            }

            // Periodic non-blocking MCU router RPC tick/reconnect
            mcu_bridge_.tick();

            // Yield CPU (~50ms)
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }

        sse.stop();
        mcu_bridge_.close_socket();
        std::cout << "[HW] Node " << cfg_.node_id << " stopped gracefully.\n";
    }


    void stop() {
        running_.store(false);
    }

    bool is_running() const {
        return running_.load();
    }

    int get_sampling_interval() const {
        return sampling_interval_seconds_.load();
    }

    int get_reading_count() const {
        return reading_count_.load();
    }

    // Build the JSON payload matching the Python SensorPayload schema exactly
    static std::string build_payload(const SensorData& d) {
        nlohmann::json j;
        j["node_id"]   = d.node_id;
        j["timestamp"] = d.timestamp;

        j["environment"] = {
            {"temperature_C", round_dp(d.temperature_c, 2)},
            {"humidity_pct",  round_dp(d.humidity_pct, 2)}
        };

        j["particulate_matter"] = {
            {"PM1_0", round_dp(d.pm1_0, 2)},
            {"PM2_5", round_dp(d.pm2_5, 2)},
            {"PM10",  round_dp(d.pm10, 2)}
        };

        j["gas_sensors"] = {
            {"MQ2",   {{"raw_adc", d.mq2_raw_adc},   {"voltage_V", round_dp(d.mq2_voltage_v, 3)}}},
            {"MQ9",   {{"raw_adc", d.mq9_raw_adc},   {"voltage_V", round_dp(d.mq9_voltage_v, 3)}}},
            {"MQ135", {{"raw_adc", d.mq135_raw_adc}, {"voltage_V", round_dp(d.mq135_voltage_v, 3)}}}
        };

        return j.dump();
    }

    // Global signal handler — sets the running flag to false
    static void signal_handler(int signum) {
        std::cout << "\n[HW] Received signal " << signum << ". Shutting down...\n";
        if (instance_) {
            instance_->stop();
        }
    }

    // Register this bridge instance for signal handling
    static void register_instance(HardwareBridge* bridge) {
        instance_ = bridge;
    }

private:
    HardwareConfig cfg_;
    std::unique_ptr<SensorSource> sensor_;
    HttpClient& http_;
    McuBridge mcu_bridge_;
    NavosEdgeState app_state_;
    std::atomic<bool> running_;
    int consecutive_failures_;
    std::atomic<int> sampling_interval_seconds_;
    std::atomic<int> reading_count_;
    std::atomic<bool> is_warmup_complete_;
    std::atomic<bool> is_ready_ack_;

    static inline HardwareBridge* instance_ = nullptr;

    void handle_sse_event(const std::string& event, const std::string& data_json) {
        if (event == "connected") {
            std::cout << "[HW] SSE connected\n";
        } else if (event == "heartbeat") {
            // Heartbeat keeps SSE alive
        } else if (event == "config") {
            try {
                auto j = nlohmann::json::parse(data_json);
                if (j.contains("sampling_interval")) {
                    int new_interval = j["sampling_interval"].get<int>();
                    if (new_interval > 0) {
                        sampling_interval_seconds_.store(new_interval);
                        std::cout << "[HW] SSE: config updated -> sampling_interval = "
                                  << new_interval << "s\n";
                    }
                }
            } catch (const std::exception& e) {
                std::cerr << "[HW] SSE: config parse error: " << e.what() << "\n";
            }
        } else if (event == "request_data" || event == "poll_sensor") {
            std::cout << "[HW] SSE request_data event received from Intelligence Server.\n";
            if (is_warmup_complete_.load() && is_ready_ack_.load()) {
                transmit_reading();
            } else if (is_warmup_complete_.load() && !is_ready_ack_.load()) {
                send_ready_signal();
            } else {
                std::cout << "[HW] Data request received during 30s warm-up — deferred until warm-up finishes.\n";
            }
        } else if (event == "intelligence_update" || event == "new_reading") {
            try {
                if (event == "intelligence_update") {
                    std::cout << "[HW] SSE intelligence_update received\n";
                }
                auto j = nlohmann::json::parse(data_json);
                update_display_state(j);
            } catch (const std::exception& e) {
                std::cerr << "[HW] SSE: intelligence result parse error: " << e.what() << "\n";
            }
        } else {
            std::cout << "[HW] SSE: event received [" << event << "]: " << data_json << "\n";
        }
    }


    bool send_ready_signal() {
        if (!is_warmup_complete_.load()) return false;
        nlohmann::json j;
        j["node_id"] = cfg_.node_id;
        j["status"] = "READY";
        j["warmup_duration_s"] = 30.0;

        std::string post_url = cfg_.server_url + "/hardware/ready";
        std::cout << "[HW] Sending READY handshake signal to Intelligence Server (" << post_url << ")...\n";

        auto resp = http_.post_json(post_url, j.dump());
        if (resp.success && (resp.status_code == 200 || resp.status_code == 201)) {
            is_ready_ack_.store(true);
            std::cout << "[HW] READY handshake ACK received from Intelligence Server.\n";
            return true;
        } else {
            is_ready_ack_.store(false);
            std::cerr << "[HW] READY handshake failed (HTTP " << resp.status_code << "): " << resp.error_msg << "\n";
            return false;
        }
    }


    void update_display_state(const nlohmann::json& j) {
        if (j.contains("aqi") && !j["aqi"].is_null()) {
            app_state_.aqi = j["aqi"].get<float>();
        }
        if (j.contains("pm") && j["pm"].is_object()) {
            auto pm = j["pm"];
            if (pm.contains("PM1_0") && !pm["PM1_0"].is_null()) app_state_.pm1_0 = pm["PM1_0"].get<float>();
            if (pm.contains("PM2_5") && !pm["PM2_5"].is_null()) app_state_.pm2_5 = pm["PM2_5"].get<float>();
            if (pm.contains("PM10")  && !pm["PM10"].is_null())  app_state_.pm10  = pm["PM10"].get<float>();
        }
        if (j.contains("temperature_C") && !j["temperature_C"].is_null()) {
            app_state_.temperature = j["temperature_C"].get<float>();
        }
        if (j.contains("humidity_pct") && !j["humidity_pct"].is_null()) {
            app_state_.humidity = j["humidity_pct"].get<float>();
        }
        if (j.contains("gas_sensors") && j["gas_sensors"].is_object()) {
            auto gs = j["gas_sensors"];
            if (gs.contains("MQ2") && gs["MQ2"].is_object()) {
                if (gs["MQ2"].contains("raw_adc") && !gs["MQ2"]["raw_adc"].is_null()) app_state_.mq2_adc = gs["MQ2"]["raw_adc"].get<uint16_t>();
                if (gs["MQ2"].contains("voltage_V") && !gs["MQ2"]["voltage_V"].is_null()) app_state_.mq2_voltage = gs["MQ2"]["voltage_V"].get<float>();
            }
            if (gs.contains("MQ9") && gs["MQ9"].is_object()) {
                if (gs["MQ9"].contains("raw_adc") && !gs["MQ9"]["raw_adc"].is_null()) app_state_.mq9_adc = gs["MQ9"]["raw_adc"].get<uint16_t>();
                if (gs["MQ9"].contains("voltage_V") && !gs["MQ9"]["voltage_V"].is_null()) app_state_.mq9_voltage = gs["MQ9"]["voltage_V"].get<float>();
            }
            if (gs.contains("MQ135") && gs["MQ135"].is_object()) {
                if (gs["MQ135"].contains("raw_adc") && !gs["MQ135"]["raw_adc"].is_null()) app_state_.mq135_adc = gs["MQ135"]["raw_adc"].get<uint16_t>();
                if (gs["MQ135"].contains("voltage_V") && !gs["MQ135"]["voltage_V"].is_null()) app_state_.mq135_voltage = gs["MQ135"]["voltage_V"].get<float>();
            }
        }
        if (j.contains("advisory") && j["advisory"].is_object()) {
            auto adv = j["advisory"];
            if (adv.contains("severity") && adv["severity"].is_string()) {
                std::string sev = adv["severity"].get<std::string>();
                strncpy(app_state_.severity, sev.c_str(), sizeof(app_state_.severity) - 1);
                app_state_.severity[sizeof(app_state_.severity) - 1] = '\0';
            }
            if (adv.contains("advice") && adv["advice"].is_string()) {
                std::string advice_str = adv["advice"].get<std::string>();
                strncpy(app_state_.advice, advice_str.c_str(), sizeof(app_state_.advice) - 1);
                app_state_.advice[sizeof(app_state_.advice) - 1] = '\0';
            }
            if (adv.contains("weather_advice") && adv["weather_advice"].is_string()) {
                std::string wa_str = adv["weather_advice"].get<std::string>();
                strncpy(app_state_.weather_advice, wa_str.c_str(), sizeof(app_state_.weather_advice) - 1);
                app_state_.weather_advice[sizeof(app_state_.weather_advice) - 1] = '\0';
            }
            if (adv.contains("actions") && adv["actions"].is_array()) {
                app_state_.action_count = 0;
                for (const auto& act : adv["actions"]) {
                    if (app_state_.action_count >= NAVOS_MAX_ACTIONS) break;
                    if (act.is_string()) {
                        std::string a_str = act.get<std::string>();
                        strncpy(app_state_.actions[app_state_.action_count], a_str.c_str(), NAVOS_MAX_STRING_LEN - 1);
                        app_state_.actions[app_state_.action_count][NAVOS_MAX_STRING_LEN - 1] = '\0';
                        app_state_.action_count++;
                    }
                }
            }
        }
        if (j.contains("predictions") && j["predictions"].is_object()) {
            auto preds = j["predictions"];
            if (preds.contains("source") && preds["source"].is_object()) {
                auto src = preds["source"];
                if (src.contains("value") && src["value"].is_string()) {
                    std::string s_val = src["value"].get<std::string>();
                    strncpy(app_state_.source_value, s_val.c_str(), sizeof(app_state_.source_value) - 1);
                    app_state_.source_value[sizeof(app_state_.source_value) - 1] = '\0';
                }
                if (src.contains("confidence") && src["confidence"].is_number()) {
                    app_state_.source_confidence = src["confidence"].get<float>();
                }
            }
            if (preds.contains("forecast") && preds["forecast"].is_object()) {
                auto fc = preds["forecast"];
                if (fc.contains("confidence") && fc["confidence"].is_number()) {
                    app_state_.forecast_confidence = fc["confidence"].get<float>();
                }
                if (fc.contains("value") && fc["value"].is_object()) {
                    auto fv = fc["value"];
                    if (fv.contains("PM2_5") && fv["PM2_5"].is_array()) {
                        app_state_.forecast_pm2_5_count = 0;
                        for (const auto& v : fv["PM2_5"]) {
                            if (app_state_.forecast_pm2_5_count >= NAVOS_MAX_FORECAST_STEPS) break;
                            if (v.is_number()) {
                                app_state_.forecast_pm2_5_pred[app_state_.forecast_pm2_5_count++] = v.get<float>();
                            }
                        }
                    }
                }
            }
        }
        if (app_state_.forecast_pm2_5_count > 0 && app_state_.pm2_5 > 0.0f) {
            float lastP = app_state_.forecast_pm2_5_pred[app_state_.forecast_pm2_5_count - 1];
            if (lastP >= app_state_.pm2_5 * 1.10f && (lastP - app_state_.pm2_5) >= 2.0f) {
                strncpy(app_state_.forecast_trend, "RISING", sizeof(app_state_.forecast_trend) - 1);
                snprintf(app_state_.forecast_outlook, sizeof(app_state_.forecast_outlook),
                         "PM2.5 forecasted to increase (+%.1f ug/m3) over next hour.", lastP - app_state_.pm2_5);
            } else if (lastP <= app_state_.pm2_5 * 0.90f && (app_state_.pm2_5 - lastP) >= 2.0f) {
                strncpy(app_state_.forecast_trend, "FALLING", sizeof(app_state_.forecast_trend) - 1);
                snprintf(app_state_.forecast_outlook, sizeof(app_state_.forecast_outlook),
                         "PM2.5 forecasted to improve (-%.1f ug/m3) over next hour.", app_state_.pm2_5 - lastP);
            } else {
                strncpy(app_state_.forecast_trend, "STABLE", sizeof(app_state_.forecast_trend) - 1);
                snprintf(app_state_.forecast_outlook, sizeof(app_state_.forecast_outlook),
                         "PM2.5 expected to remain stable near %.1f ug/m3.", app_state_.pm2_5);
            }
        }
        app_state_.valid = true;
        app_state_.last_update_ms = millis();
        std::cout << "[DISPLAY] State updated\n";
        std::cout << "[HW] Shared NavosEdgeState updated via SSE (AQI: " << app_state_.aqi
                  << " | PM2.5: " << app_state_.pm2_5 << " | Temp: " << app_state_.temperature << "C)\n";

        // Forward state to MCU display over serial bridge
        mcu_bridge_.send_state(app_state_);
    }

    // Wait for the server to respond to /health and /ready
    bool wait_for_server() {
        std::string health_url = cfg_.server_url + "/health";
        std::string ready_url  = cfg_.server_url + "/ready";
        int attempt = 0;

        while (running_.load()) {
            ++attempt;
            auto health_resp = http_.get(health_url);

            if (health_resp.success && health_resp.status_code == 200) {
                auto ready_resp = http_.get(ready_url);
                if (ready_resp.success && ready_resp.status_code == 200) {
                    try {
                        auto j_ready = nlohmann::json::parse(ready_resp.body);
                        bool is_ready = j_ready.contains("ready") && j_ready["ready"].get<bool>();
                        bool storage_ok = j_ready.contains("storage_ok") && j_ready["storage_ok"].get<bool>();
                        if (is_ready || storage_ok) {
                            return true;
                        }
                    } catch (...) {}
                }
            }

            int delay = compute_backoff(attempt);
            std::cout << "[HW] Server not ready yet. Retrying in " << delay << "s...\n";
            sleep_interruptible(delay);
        }

        return false;
    }

    void transmit_reading() {
        SensorData data = sensor_->read();
        app_state_.mq2_adc = (uint16_t)data.mq2_raw_adc;
        app_state_.mq2_voltage = (float)data.mq2_voltage_v;
        app_state_.mq9_adc = (uint16_t)data.mq9_raw_adc;
        app_state_.mq9_voltage = (float)data.mq9_voltage_v;
        app_state_.mq135_adc = (uint16_t)data.mq135_raw_adc;
        app_state_.mq135_voltage = (float)data.mq135_voltage_v;

        // Validate sensor data before transmission
        auto validation = SensorValidator::validate(data);
        if (!validation.valid) {
            std::cerr << "[HW] Invalid sensor reading — skipping transmission\n";
            validation.print_summary();
            return;
        }
        if (!validation.warnings.empty()) {
            validation.print_summary();
        }

        std::string payload = build_payload(data);
        std::string post_url = cfg_.server_url + "/hardware/data";

        int current_count = ++reading_count_;
        std::cout << "[HW] Sending sensor reading #" << current_count << "\n";

        auto resp = http_.post_json(post_url, payload);

        if (!resp.success) {
            ++consecutive_failures_;
            std::cerr << "[HW] Connection error: " << resp.error_msg << "\n";
            handle_failure();
            return;
        }

        std::cout << "[HW] POST /hardware/data -> " << resp.status_code << "\n";

        if (resp.status_code == 201 || resp.status_code == 200) {
            consecutive_failures_ = 0;
        } else if (resp.status_code == 422) {
            std::cerr << "[HW] Validation error (422): " << resp.body << "\n";
        } else {
            ++consecutive_failures_;
            handle_failure();
        }
    }

    void handle_failure() {
        if (consecutive_failures_ >= cfg_.retry_max_attempts) {
            std::cerr << "[HW] Max retries reached. Intelligence Server connection lost. Re-checking server health...\n";
            consecutive_failures_ = 0;
            is_ready_ack_.store(false);
            if (wait_for_server()) {
                std::cout << "[HW] Intelligence Server recovered. Re-sending READY handshake...\n";
                send_ready_signal();
            }
        } else {
            int delay = compute_backoff(consecutive_failures_);
            std::cout << "[HW] Connection error. Reconnecting in " << delay << "s...\n";
            sleep_interruptible(delay);
        }
    }


    int compute_backoff(int attempt) const {
        int delay = cfg_.retry_base_delay_seconds;
        for (int i = 1; i < attempt && delay < 60; ++i) {
            delay *= 2;
        }
        return std::min(delay, 60);
    }

    void sleep_interruptible(int seconds) {
        for (int i = 0; i < seconds * 2 && running_.load(); ++i) {
            std::this_thread::sleep_for(std::chrono::milliseconds(500));
        }
    }

    static double round_dp(double val, int dp) {
        double factor = std::pow(10.0, dp);
        return std::round(val * factor) / factor;
    }
};

} // namespace navos
