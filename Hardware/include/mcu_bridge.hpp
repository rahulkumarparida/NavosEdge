#pragma once

/**
 * mcu_bridge.hpp — Linux ↔ MCU Serial Communication Bridge
 *
 * Transmits NavosEdgeState JSON objects over the Arduino UNO Q serial port
 * (/dev/ttyACM0) to the MCU display application running on the STM32 MCU.
 */

#include <fcntl.h>
#include <termios.h>
#include <unistd.h>
#include <string>
#include <iostream>
#include <nlohmann/json.hpp>
#include "../display/state/NavosEdgeState.h"

namespace navos {

class McuBridge {
public:
    McuBridge(const std::string& device_path = "/dev/ttyACM0", int baud = 115200)
        : device_path_(device_path), baud_(baud), fd_(-1) {}

    ~McuBridge() {
        close_port();
    }

    bool open_port() {
        if (fd_ >= 0) return true;

        fd_ = open(device_path_.c_str(), O_RDWR | O_NOCTTY | O_NDELAY);
        if (fd_ < 0) {
            std::cerr << "[MCU] Warning: Unable to open MCU serial port " << device_path_ << "\n";
            return false;
        }

        fcntl(fd_, F_SETFL, 0);

        struct termios options;
        tcgetattr(fd_, &options);

        cfsetispeed(&options, B115200);
        cfsetospeed(&options, B115200);

        options.c_cflag &= ~PARENB;
        options.c_cflag &= ~CSTOPB;
        options.c_cflag &= ~CSIZE;
        options.c_cflag |= CS8;
        options.c_cflag |= (CLOCAL | CREAD);

        options.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);
        options.c_oflag &= ~OPOST;

        tcsetattr(fd_, TCSANOW, &options);

        std::cout << "[MCU] Serial bridge connected to MCU on " << device_path_ << "\n";
        return true;
    }

    void close_port() {
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
            if (!open_port()) return false;
        }

        nlohmann::json j;
        j["aqi"] = s.aqi;
        j["pm1_0"] = s.pm1_0;
        j["pm2_5"] = s.pm2_5;
        j["pm10"] = s.pm10;
        j["temperature"] = s.temperature;
        j["humidity"] = s.humidity;
        j["severity"] = s.severity;
        j["advice"] = s.advice;
        j["weather_advice"] = s.weather_advice;

        nlohmann::json actions_arr = nlohmann::json::array();
        for (uint8_t i = 0; i < s.action_count && i < NAVOS_MAX_ACTIONS; i++) {
            actions_arr.push_back(s.actions[i]);
        }
        j["actions"] = actions_arr;

        std::string msg = j.dump() + "\n";
        ssize_t bytes_written = write(fd_, msg.c_str(), msg.length());
        if (bytes_written < 0) {
            std::cerr << "[MCU] Serial write error on " << device_path_ << "\n";
            close_port();
            return false;
        }

        std::cout << "[MCU] Display state sent to MCU over " << device_path_
                  << " (AQI: " << s.aqi << " | PM2.5: " << s.pm2_5
                  << " | Temp: " << s.temperature << "C)\n";
        return true;
    }

private:
    std::string device_path_;
    int baud_;
    int fd_;
};

} // namespace navos
