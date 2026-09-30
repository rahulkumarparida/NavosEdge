#pragma once

/**
 * mcu_bridge.hpp — MPU (Linux) ↔ MCU MessagePack-RPC Client via Arduino Router
 *
 * Transmits NavosEdgeState over the Unix domain socket (/var/run/arduino-router.sock)
 * to arduino-router using the MessagePack-RPC protocol on the Arduino UNO Q.
 */

#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <string>
#include <iostream>
#include <vector>
#include <cstring>
#include <nlohmann/json.hpp>
#include "../display/state/NavosEdgeState.h"

namespace navos {

class McuBridge {
public:
    McuBridge(const std::string& socket_path = "/var/run/arduino-router.sock")
        : socket_path_(socket_path), fd_(-1), msg_id_(1) {}

    ~McuBridge() {
        close_socket();
    }

    bool open_socket() {
        if (fd_ >= 0) return true;

        fd_ = socket(AF_UNIX, SOCK_STREAM, 0);
        if (fd_ < 0) {
            std::cerr << "[MCU] Warning: Unable to create socket\n";
            return false;
        }

        struct sockaddr_un addr;
        std::memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        std::strncpy(addr.sun_path, socket_path_.c_str(), sizeof(addr.sun_path) - 1);

        if (connect(fd_, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            std::cerr << "[MCU] Warning: Unable to connect to Arduino Router socket at " << socket_path_ << "\n";
            close(fd_);
            fd_ = -1;
            return false;
        }

        std::cout << "[MCU] Router connected\n";
        return true;
    }

    void close_socket() {
        if (fd_ >= 0) {
            close(fd_);
            fd_ = -1;
        }
    }

    bool is_connected() const {
        return fd_ >= 0;
    }

    bool send_state(const NavosEdgeState& s) {
        if (fd_ < 0) {
            if (!open_socket()) return false;
        }

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
            std::cerr << "[MCU] Router write error on " << socket_path_ << "\n";
            close_socket();
            return false;
        }

        std::cout << "[MCU] Display state sent via RPC\n";
        std::cout << "[MCU] AQI=" << s.aqi << " PM2.5=" << s.pm2_5 << " TEMP=" << s.temperature << "\n";
        return true;
    }

private:
    std::string socket_path_;
    int fd_;
    uint32_t msg_id_;
};

} // namespace navos
