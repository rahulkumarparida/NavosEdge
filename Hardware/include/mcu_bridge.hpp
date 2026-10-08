#pragma once

/**
 * mcu_bridge.hpp — MPU (Linux) ↔ MCU Modular MessagePack-RPC Client via Arduino Router
 *
 * Transmits NavosEdgeState over Unix domain socket (/var/run/arduino-router.sock)
 * using 3 small, modular RPC calls:
 *   1. update_environment (aqi, pm1_0, pm2_5, pm10, temp, hum)  [~48 bytes]
 *   2. update_advice (severity, advice, weather_advice)        [~320 bytes]
 *   3. update_actions (actions_csv)                             [~340 bytes]
 *
 * Every individual RPC payload is safely below the Arduino RPClite 1024-byte buffer limit.
 */

#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <fcntl.h>
#include <string>
#include <iostream>
#include <vector>
#include <cstring>
#include <chrono>
#include <thread>
#include <algorithm>
#include <cerrno>
#include <nlohmann/json.hpp>
#include "../display/state/NavosEdgeState.h"

namespace navos {

enum class BridgeState {
    DISCONNECTED,
    CONNECTING,
    CONNECTED
};

class McuBridge {
public:
    McuBridge(const std::string& socket_path = "/var/run/arduino-router.sock")
        : socket_path_(socket_path)
        , fd_(-1)
        , msg_id_(1)
        , state_(BridgeState::DISCONNECTED)
        , retry_interval_sec_(1)
        , last_connect_attempt_time_(std::chrono::steady_clock::now() - std::chrono::seconds(10))
        , last_unavailable_log_time_(std::chrono::steady_clock::now() - std::chrono::seconds(10))
        , has_latest_state_(false)
    {
        navosStateInit(latest_state_);
    }

    ~McuBridge() {
        close_socket();
    }

    BridgeState get_state() const {
        return state_;
    }

    bool is_connected() const {
        return state_ == BridgeState::CONNECTED && fd_ >= 0;
    }

    // Non-blocking tick called periodically from main loop to handle reconnects
    void tick() {
        if (state_ == BridgeState::CONNECTED && fd_ >= 0) {
            return;
        }

        auto now = std::chrono::steady_clock::now();
        auto elapsed_retry = std::chrono::duration_cast<std::chrono::seconds>(now - last_connect_attempt_time_).count();

        if (elapsed_retry >= retry_interval_sec_) {
            last_connect_attempt_time_ = now;
            state_ = BridgeState::CONNECTING;

            if (open_socket_internal()) {
                bool is_reconnect = has_latest_state_;
                state_ = BridgeState::CONNECTED;
                retry_interval_sec_ = 1;

                if (is_reconnect) {
                    std::cout << "[MCU] Router RPC reconnected\n";
                } else {
                    std::cout << "[MCU] Router connected\n";
                }

                if (has_latest_state_ && latest_state_.valid) {
                    std::cout << "[MCU] Resending latest display state\n";
                    send_state_rpc_all(latest_state_);
                }
            } else {
                state_ = BridgeState::DISCONNECTED;
                retry_interval_sec_ = std::min(retry_interval_sec_ * 2, 5); // 1s -> 2s -> 5s max

                auto elapsed_log = std::chrono::duration_cast<std::chrono::seconds>(now - last_unavailable_log_time_).count();
                if (elapsed_log >= 5) {
                    std::cout << "[MCU] Display MCU unavailable; retrying...\n";
                    last_unavailable_log_time_ = now;
                }
            }
        }
    }

    bool send_state(const NavosEdgeState& s) {
        latest_state_ = s;
        latest_state_.valid = true;
        has_latest_state_ = true;

        if (state_ != BridgeState::CONNECTED || fd_ < 0) {
            tick();
            return false;
        }

        return send_state_rpc_all(latest_state_);
    }

    bool open_socket() {
        tick();
        return is_connected();
    }

    void close_socket() {
        if (fd_ >= 0) {
            close(fd_);
            fd_ = -1;
        }
        rx_stream_buffer_.clear();
        state_ = BridgeState::DISCONNECTED;
    }

private:
    bool open_socket_internal() {
        if (fd_ >= 0) {
            close(fd_);
            fd_ = -1;
        }
        rx_stream_buffer_.clear();

        fd_ = socket(AF_UNIX, SOCK_STREAM, 0);
        if (fd_ < 0) {
            return false;
        }

        // Set socket timeouts (2 seconds)
        struct timeval tv;
        tv.tv_sec = 2;
        tv.tv_usec = 0;
        setsockopt(fd_, SOL_SOCKET, SO_RCVTIMEO, (const char*)&tv, sizeof(tv));
        setsockopt(fd_, SOL_SOCKET, SO_SNDTIMEO, (const char*)&tv, sizeof(tv));

        struct sockaddr_un addr;
        std::memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        std::strncpy(addr.sun_path, socket_path_.c_str(), sizeof(addr.sun_path) - 1);

        if (connect(fd_, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            close(fd_);
            fd_ = -1;
            return false;
        }

        return true;
    }

    bool send_state_rpc_all(const NavosEdgeState& s) {
        auto t0 = std::chrono::steady_clock::now();
        bool env_ok = send_rpc_environment(s);
        std::this_thread::sleep_for(std::chrono::milliseconds(15));
        bool adv_ok = send_rpc_advice(s);
        std::this_thread::sleep_for(std::chrono::milliseconds(15));
        bool act_ok = send_rpc_actions(s);
        std::this_thread::sleep_for(std::chrono::milliseconds(15));
        bool pred_ok = send_rpc_predictions(s);

        auto t1 = std::chrono::steady_clock::now();
        double total_ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
        log_periodic_timings(total_ms);

        return env_ok && adv_ok && act_ok && pred_ok;
    }

    bool send_rpc_environment(const NavosEdgeState& s) {
        nlohmann::json params = nlohmann::json::array({
            s.aqi,
            s.pm1_0,
            s.pm2_5,
            s.pm10,
            s.temperature,
            s.humidity
        });

        if (send_rpc_call("update_environment", params, 0)) {
            std::cout << "[MCU] Environment RPC sent\n";
            return true;
        }
        return false;
    }

    bool send_rpc_advice(const NavosEdgeState& s) {
        std::string severity = truncate_string(s.severity, 20);
        std::string advice = truncate_string(s.advice, 90);
        std::string weather_advice = "";

        nlohmann::json params = nlohmann::json::array({
            severity,
            advice,
            weather_advice
        });

        if (send_rpc_call("update_advice", params, 1)) {
            std::cout << "[MCU] Advice RPC sent\n";
            return true;
        }
        return false;
    }

    bool send_rpc_actions(const NavosEdgeState& s) {
        std::string actions_csv = "";
        uint8_t count = std::min(s.action_count, (uint8_t)4);
        for (uint8_t i = 0; i < count; i++) {
            if (i > 0) actions_csv += ";";
            actions_csv += truncate_string(s.actions[i], 35);
        }

        nlohmann::json params = nlohmann::json::array({
            actions_csv
        });

        if (send_rpc_call("update_actions", params, 2)) {
            std::cout << "[MCU] Actions RPC sent\n";
            return true;
        }
        return false;
    }

    bool send_rpc_predictions(const NavosEdgeState& s) {
        std::string source = truncate_string(s.source_value, 25);
        float source_conf = s.source_confidence;
        std::string trend = truncate_string(s.forecast_trend, 12);
        float forecast_conf = s.forecast_confidence;
        float pm25_0 = s.forecast_pm2_5_count > 0 ? s.forecast_pm2_5_pred[0] : 0.0f;
        float pm25_1 = s.forecast_pm2_5_count > 1 ? s.forecast_pm2_5_pred[1] : 0.0f;
        std::string anomaly = truncate_string(s.anomaly_status, 15);

        nlohmann::json params = nlohmann::json::array({
            source,
            source_conf,
            trend,
            forecast_conf,
            pm25_0,
            pm25_1,
            anomaly
        });

        if (send_rpc_call("update_predictions", params, 3)) {
            std::cout << "[MCU] Predictions RPC sent\n";
            return true;
        }
        return false;
    }

    bool send_rpc_call(const std::string& method_name, const nlohmann::json& params, int method_idx = -1) {
        if (fd_ < 0) return false;

        auto t_start = std::chrono::steady_clock::now();
        uint32_t req_id = msg_id_++;

        // MessagePack-RPC Request format: [0, msg_id, method, params]
        nlohmann::json rpc_req = nlohmann::json::array({
            0,
            req_id,
            method_name,
            params
        });

        std::vector<uint8_t> msgpack_bytes = nlohmann::json::to_msgpack(rpc_req);

        // 1. Send Request
        ssize_t bytes_written = write(fd_, msgpack_bytes.data(), msgpack_bytes.size());
        if (bytes_written < 0) {
            log_rpc_failure("socket send error (" + std::string(std::strerror(errno)) + ")");
            close_socket();
            return false;
        }

        // 2. Stream-framed Read: accumulate bytes and unpack MessagePack frames
        constexpr int timeout_ms = 2000;
        auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);

        while (true) {
            // First, attempt to decode any complete MessagePack object already in rx_stream_buffer_
            if (!rx_stream_buffer_.empty()) {
                auto res_j = nlohmann::json::from_msgpack(rx_stream_buffer_.data(),
                                                          rx_stream_buffer_.data() + rx_stream_buffer_.size(),
                                                          false, false);
                if (!res_j.is_discarded()) {
                    // Frame parsed successfully — calculate and consume exact byte length
                    size_t consumed = nlohmann::json::to_msgpack(res_j).size();
                    if (consumed > 0 && consumed <= rx_stream_buffer_.size()) {
                        rx_stream_buffer_.erase(rx_stream_buffer_.begin(), rx_stream_buffer_.begin() + consumed);
                    } else {
                        rx_stream_buffer_.clear();
                    }

                    if (res_j.is_array() && res_j.size() >= 4) {
                        int type = res_j[0].is_number_integer() ? res_j[0].get<int>() : -1;
                        uint32_t resp_id = res_j[1].is_number_unsigned() ? res_j[1].get<uint32_t>() :
                                          (res_j[1].is_number_integer() ? (uint32_t)res_j[1].get<int>() : 0);

                        if (type == 1) { // RPC response
                            if (resp_id < req_id) {
                                // Stale response from earlier timed-out RPC; drop and keep waiting
                                continue;
                            } else if (resp_id == req_id) {
                                // Match!
                                auto t_end = std::chrono::steady_clock::now();
                                double dur_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();
                                record_timing(method_idx, dur_ms, true);

                                if (!res_j[2].is_null()) {
                                    std::string rpc_err = res_j[2].is_string() ? res_j[2].get<std::string>() : res_j[2].dump();
                                    log_rpc_failure(rpc_err);
                                    return false;
                                }
                                return true;
                            } else {
                                // Future response ID
                                auto t_end = std::chrono::steady_clock::now();
                                double dur_ms = std::chrono::duration<double, std::milli>(t_end - t_start).count();
                                record_timing(method_idx, dur_ms, true);
                                return true;
                            }
                        }
                    }
                    continue; // Check if more frames can be parsed from buffer
                }
            }

            // Need more data from socket
            auto now = std::chrono::steady_clock::now();
            if (now >= deadline) {
                log_rpc_failure("receive timeout (method: " + method_name + ")");
                record_timing(method_idx, timeout_ms, false);
                return false;
            }

            int remaining_ms = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - now).count();
            fd_set fds;
            FD_ZERO(&fds);
            FD_SET(fd_, &fds);
            struct timeval tv;
            tv.tv_sec = remaining_ms / 1000;
            tv.tv_usec = (remaining_ms % 1000) * 1000;

            int sel = select(fd_ + 1, &fds, nullptr, nullptr, &tv);
            if (sel < 0) {
                if (errno == EINTR) continue;
                log_rpc_failure("select error: " + std::string(std::strerror(errno)));
                close_socket();
                return false;
            }
            if (sel == 0) {
                log_rpc_failure("receive timeout (method: " + method_name + ")");
                record_timing(method_idx, timeout_ms, false);
                return false;
            }

            uint8_t rx_tmp[1024];
            ssize_t bytes_read = recv(fd_, rx_tmp, sizeof(rx_tmp), 0);
            if (bytes_read <= 0) {
                if (bytes_read == 0) {
                    log_rpc_failure("connection closed by router");
                } else if (errno != EAGAIN && errno != EWOULDBLOCK) {
                    log_rpc_failure("socket receive error (" + std::string(std::strerror(errno)) + ")");
                }
                close_socket();
                record_timing(method_idx, 0, false);
                return false;
            }

            rx_stream_buffer_.insert(rx_stream_buffer_.end(), rx_tmp, rx_tmp + bytes_read);
            // Cap buffer size to prevent memory leaks
            if (rx_stream_buffer_.size() > 8192) {
                rx_stream_buffer_.erase(rx_stream_buffer_.begin(), rx_stream_buffer_.end() - 2048);
            }
        }
    }

    void record_timing(int method_idx, double dur_ms, bool success) {
        if (method_idx >= 0 && method_idx < 4) {
            rpc_timing_[method_idx].call_count++;
            if (success) {
                rpc_timing_[method_idx].success_count++;
                rpc_timing_[method_idx].total_duration_ms += dur_ms;
                if (dur_ms > rpc_timing_[method_idx].max_duration_ms) {
                    rpc_timing_[method_idx].max_duration_ms = dur_ms;
                }
            } else {
                rpc_timing_[method_idx].failure_count++;
            }
        }
    }

    void log_periodic_timings(double total_batch_ms) {
        auto now = std::chrono::steady_clock::now();
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(now - last_timing_log_time_).count();
        if (elapsed >= 30) {
            last_timing_log_time_ = now;
            std::cout << "[MCU] RPC Duration Metrics (last batch: " << std::fixed << std::setprecision(1) << total_batch_ms << "ms):\n";
            const char* names[4] = {"env", "advice", "actions", "pred"};
            for (int i = 0; i < 4; i++) {
                double avg_ms = (rpc_timing_[i].success_count > 0) ?
                    (rpc_timing_[i].total_duration_ms / rpc_timing_[i].success_count) : 0.0;
                std::cout << "      • " << names[i] << ": avg=" << avg_ms << "ms, max="
                          << rpc_timing_[i].max_duration_ms << "ms, success="
                          << rpc_timing_[i].success_count << "/" << rpc_timing_[i].call_count << "\n";
            }
        }
    }

    void log_rpc_failure(const std::string& reason) {
        auto now = std::chrono::steady_clock::now();
        auto elapsed_log = std::chrono::duration_cast<std::chrono::seconds>(now - last_unavailable_log_time_).count();
        if (elapsed_log >= 5) {
            std::cout << "[MCU] RPC call failed: " << reason << "\n";
            last_unavailable_log_time_ = now;
        }
    }

    static std::string truncate_string(const char* src, size_t max_len) {
        if (!src) return "";
        std::string s(src);
        if (s.length() > max_len) {
            s = s.substr(0, max_len);
        }
        return s;
    }

    struct RpcMethodStats {
        uint32_t call_count = 0;
        uint32_t success_count = 0;
        uint32_t failure_count = 0;
        double total_duration_ms = 0.0;
        double max_duration_ms = 0.0;
    };

    std::string socket_path_;
    int fd_;
    uint32_t msg_id_;
    BridgeState state_;
    int retry_interval_sec_;
    std::chrono::steady_clock::time_point last_connect_attempt_time_;
    std::chrono::steady_clock::time_point last_unavailable_log_time_;
    std::chrono::steady_clock::time_point last_timing_log_time_;
    NavosEdgeState latest_state_;
    bool has_latest_state_;
    std::vector<uint8_t> rx_stream_buffer_;
    RpcMethodStats rpc_timing_[4];
};

} // namespace navos
