#pragma once

#include <string>
#include <memory>
#include <atomic>
#include <thread>
#include <iostream>
#include <algorithm>
#include <csignal>
#include <iomanip>
#include <nlohmann/json.hpp>

#include "config.hpp"
#include "sensor.hpp"
#include "http_client.hpp"
#include "sse_client.hpp"

namespace navos {

class HardwareBridge {
public:
    HardwareBridge(HardwareConfig cfg,
                   std::unique_ptr<SensorSource> sensor,
                   HttpClient& http)
        : cfg_(std::move(cfg))
        , sensor_(std::move(sensor))
        , http_(http)
        , running_(true)
        , consecutive_failures_(0)
        , sampling_interval_seconds_(cfg_.sampling_interval_seconds)
        , reading_count_(0)
    {}

    ~HardwareBridge() {
        stop();
    }

    void run() {
        std::cout << "[HW] Starting node: " << cfg_.node_id << "\n";

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
        
        std::cout << "[HW] SSE: connected\n";
        sse.start();

        // Phase 3: Main sensor read → POST loop
        while (running_.load()) {
            transmit_reading();
            int current_interval = sampling_interval_seconds_.load();
            sleep_interruptible(current_interval);
        }

        sse.stop();
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
    std::atomic<bool> running_;
    int consecutive_failures_;
    std::atomic<int> sampling_interval_seconds_;
    std::atomic<int> reading_count_;

    static inline HardwareBridge* instance_ = nullptr;

    void handle_sse_event(const std::string& event, const std::string& data_json) {
        if (event == "connected") {
            std::cout << "[HW] SSE: registration confirmed\n";
        } else if (event == "heartbeat") {
            std::cout << "[HW] SSE: heartbeat received\n";
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
        } else {
            std::cout << "[HW] SSE: event received [" << event << "]: " << data_json << "\n";
        }
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

        std::cout << "[HW] POST /hardware/data → " << resp.status_code << "\n";

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
            std::cerr << "[HW] Max retries reached. Re-checking server health...\n";
            consecutive_failures_ = 0;
            wait_for_server();
        } else {
            int delay = compute_backoff(consecutive_failures_);
            std::cout << "[HW] Reconnecting in " << delay << "s...\n";
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
