#pragma once

/**
 * mcu_bridge.hpp — MPU (Linux) ↔ MCU MessagePack-RPC Client via Arduino Router
 *
 * Fault-tolerant MessagePack-RPC client over Unix domain socket (/var/run/arduino-router.sock).
 * Manages connection lifecycle (DISCONNECTED, CONNECTING, CONNECTED), non-blocking retry with backoff,
 * rate-limited diagnostic logging, and automatic state re-transmission upon MCU reconnection.
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
#include <algorithm>
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
                    std::cout << "[MCU] AQI=" << latest_state_.aqi
                              << " PM2.5=" << latest_state_.pm2_5
                              << " TEMP=" << latest_state_.temperature
                              << " HUM=" << latest_state_.humidity << "\n";
                    transmit_rpc(latest_state_);
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

        return transmit_rpc(latest_state_);
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
        state_ = BridgeState::DISCONNECTED;
    }

private:
    bool open_socket_internal() {
        if (fd_ >= 0) {
            close(fd_);
            fd_ = -1;
        }

        fd_ = socket(AF_UNIX, SOCK_STREAM, 0);
        if (fd_ < 0) {
            return false;
        }

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

    bool transmit_rpc(const NavosEdgeState& s) {
        if (fd_ < 0) return false;

        std::string actions_csv = "";
        for (uint8_t i = 0; i < s.action_count && i < NAVOS_MAX_ACTIONS; i++) {
            if (i > 0) actions_csv += ";";
            actions_csv += s.actions[i];
        }

        nlohmann::json params = nlohmann::json::array({
            s.aqi,
            s.pm1_0,
            s.pm2_5,
            s.pm10,
            s.temperature,
            s.humidity,
            std::string(s.severity),
            std::string(s.advice),
            std::string(s.weather_advice),
            actions_csv
        });

        // MsgPack RPC Request format: [0, msgid, "method", params]
        nlohmann::json rpc_req = nlohmann::json::array({
            0,
            msg_id_++,
            "update_display",
            params
        });

        std::vector<uint8_t> msgpack_bytes = nlohmann::json::to_msgpack(rpc_req);

        ssize_t bytes_written = write(fd_, msgpack_bytes.data(), msgpack_bytes.size());
        if (bytes_written < 0) {
            auto now = std::chrono::steady_clock::now();
            auto elapsed_log = std::chrono::duration_cast<std::chrono::seconds>(now - last_unavailable_log_time_).count();
            if (elapsed_log >= 5) {
                std::cout << "[MCU] Router RPC disconnected\n";
                last_unavailable_log_time_ = now;
            }
            close_socket();
            retry_interval_sec_ = 1;
            return false;
        }

        std::cout << "[MCU] Display state sent via RPC\n";
        std::cout << "[MCU] AQI=" << s.aqi << " PM2.5=" << s.pm2_5 << " TEMP=" << s.temperature << " HUM=" << s.humidity << "\n";
        return true;
    }

    std::string socket_path_;
    int fd_;
    uint32_t msg_id_;
    BridgeState state_;
    int retry_interval_sec_;
    std::chrono::steady_clock::time_point last_connect_attempt_time_;
    std::chrono::steady_clock::time_point last_unavailable_log_time_;
    NavosEdgeState latest_state_;
    bool has_latest_state_;
};

} // namespace navos
