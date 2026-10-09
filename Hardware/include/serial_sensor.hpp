#pragma once

/**
 * serial_sensor.hpp — Physical sensor source via Arduino serial (USB UART).
 *
 * Reads compact JSON frames from the Arduino firmware over /dev/ttyACM0:
 *   {"mq2":350,"mq9":280,"mq135":420,"t":28.50,"h":65.00,"pm1":12.0,"pm25":18.0,"pm10":25.0,"ok":true}
 *
 * Converts each frame into a validated SensorData struct.
 *
 * Design for Arduino UNO Q deployment:
 *   - Linux-side termios serial at 115200 baud
 *   - Line-delimited JSON (one frame per \n)
 *   - Automatic reconnection on port loss
 *   - Graceful degradation on partial sensor failure
 */

#include <string>
#include <chrono>
#include <iostream>
#include <cstring>
#include <cerrno>
#include <algorithm>

// Linux serial and socket headers
#include <fcntl.h>
#include <unistd.h>
#include <termios.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <netdb.h>

#include <nlohmann/json.hpp>

#include "constants.hpp"
#include "sensor.hpp"
#include "sensor_validator.hpp"

namespace navos {

enum class SensorTransportType {
    TCP,
    UNIX_SOCKET,
    SERIAL_TTY
};

class SerialSensorSource : public SensorSource {
public:
    SerialSensorSource(const std::string& node_id,
                       const std::string& serial_port = constants::DEFAULT_SERIAL_PORT,
                       int baud_rate = constants::DEFAULT_SERIAL_BAUD,
                       int timeout_ms = constants::DEFAULT_SERIAL_TIMEOUT_MS)
        : node_id_(node_id)
        , serial_port_(serial_port)
        , baud_rate_(baud_rate)
        , timeout_ms_(timeout_ms)
        , fd_(-1)
        , consecutive_errors_(0)
        , total_reads_(0)
        , valid_reads_(0)
    {
    }

    ~SerialSensorSource() {
        close_port();
    }

    void set_scenario(SimulationScenario) override {
        // Physical sensors don't support scenario switching
    }

    SensorData read() override {
        ++total_reads_;

        // Ensure serial port is open
        if (fd_ < 0) {
            if (!open_port()) {
                return make_error_reading("Serial port not available: " + serial_port_);
            }
        }

        // Read a complete JSON line from the Arduino
        std::string line;
        if (!read_line(line)) {
            // If the port was closed due to peer disconnect during read_line,
            // attempt an immediate reconnect
            if (fd_ < 0 && open_port()) {
                read_line(line);
            }
        }

        if (line.empty()) {
            ++consecutive_errors_;
            if (consecutive_errors_ >= 5) {
                std::cerr << "[SERIAL] Too many consecutive errors, reconnecting...\n";
                close_port();
                consecutive_errors_ = 0;
            }
            return make_error_reading("Sensor read timeout/error");
        }

        // Parse the JSON frame
        SensorData data;
        if (!parse_frame(line, data)) {
            ++consecutive_errors_;
            return make_error_reading("JSON parse failed: " + line.substr(0, 80));
        }

        // Validate the parsed data
        auto validation = SensorValidator::validate(data);
        if (!validation.valid) {
            validation.print_summary();

            // Attempt recovery by clamping
            data = SensorValidator::clamp(data);
            auto recheck = SensorValidator::validate(data);
            if (!recheck.valid) {
                ++consecutive_errors_;
                return make_error_reading("Validation failed after clamping");
            }
            std::cout << "[SERIAL] Recovered reading via clamping\n";
        }

        // Success
        consecutive_errors_ = 0;
        ++valid_reads_;
        return data;
    }

    bool is_connected() const { return fd_ >= 0; }
    int get_total_reads() const { return total_reads_; }
    int get_valid_reads() const { return valid_reads_; }

    /**
     * Parse compact JSON from Arduino into SensorData.
     *
     * Expected format:
     *   {"mq2":350,"mq9":280,"mq135":420,"t":28.50,"h":65.00,
     *    "pm1":12.0,"pm25":18.0,"pm10":25.0,"dht_ok":true,"pms_ok":true,"ok":true}
     */
    bool parse_frame(const std::string& json_str, SensorData& out, bool print_log = true) {
        try {
            auto j = nlohmann::json::parse(json_str);

            // Check if this is a status/boot message, not a sensor reading
            if (j.contains("status")) {
                std::cout << "[SERIAL] Arduino hardware message: " << j.dump() << "\n";
                return false;
            }

            // Check for sensor error flags
            bool dht_ok = j.value("dht_ok", true);
            bool pms_ok = j.value("pms_ok", true);
            bool all_ok = j.value("ok", true);

            if (!dht_ok) {
                std::cerr << "[SERIAL] [WARN] DHT22 sensor report: FAULT / UNHEALTHY\n";
            }
            if (!pms_ok) {
                std::cerr << "[SERIAL] [WARN] MPM10-CS sensor report: FAULT / UNHEALTHY\n";
            }

            out.dht_ok = dht_ok;
            out.pms_ok = pms_ok;

            // Extract MQ values (support both compact and verbose keys)
            out.mq2_raw_adc   = j.value("mq2", j.value("mq2_adc", 0));
            out.mq9_raw_adc   = j.value("mq9", j.value("mq9_adc", 0));
            out.mq135_raw_adc = j.value("mq135", j.value("mq135_adc", 0));

            // Convert ADC to voltage (or use direct voltage if provided in diagnostic frames)
            if (j.contains("mq2_voltage") && j["mq2_voltage"].is_number()) {
                out.mq2_voltage_v = j["mq2_voltage"].get<double>();
            } else {
                out.mq2_voltage_v = adc_to_voltage(out.mq2_raw_adc);
            }

            if (j.contains("mq9_voltage") && j["mq9_voltage"].is_number()) {
                out.mq9_voltage_v = j["mq9_voltage"].get<double>();
            } else {
                out.mq9_voltage_v = adc_to_voltage(out.mq9_raw_adc);
            }

            if (j.contains("mq135_voltage") && j["mq135_voltage"].is_number()) {
                out.mq135_voltage_v = j["mq135_voltage"].get<double>();
            } else {
                out.mq135_voltage_v = adc_to_voltage(out.mq135_raw_adc);
            }

            // DHT22 (support both compact 't'/'h' and verbose 'temperature'/'humidity')
            out.temperature_c = j.value("t", j.value("temperature", 0.0));
            out.humidity_pct  = j.value("h", j.value("humidity", 0.0));

            // PMS / MPM10-CS (support both compact 'pm1'/'pm25' and verbose 'pm1_0'/'pm2_5')
            out.pm1_0 = j.value("pm1", j.value("pm1_0", 0.0));
            out.pm2_5 = j.value("pm25", j.value("pm2_5", 0.0));
            out.pm10  = j.value("pm10", 0.0);

            // Metadata
            out.node_id   = node_id_;
            out.timestamp = now_iso8601();

            if (print_log) {
                std::ostringstream oss;
                oss << "\n[SERIAL] ================= REAL SENSOR READING ================="
                    << "\n[SERIAL] Hardware Node : " << out.node_id
                    << "\n[SERIAL] Timestamp     : " << out.timestamp
                    << "\n[SERIAL] --------------------------------------------------------"
                    << "\n[SERIAL] Sensor 1 | MQ-2   (Combustible Gas & Smoke) :"
                    << "\n[SERIAL]          Raw ADC = " << out.mq2_raw_adc << " / 1023"
                    << " | Voltage = " << std::fixed << std::setprecision(3) << out.mq2_voltage_v << " V"
                    << "\n[SERIAL] Sensor 2 | MQ-9   (CO & Flammable Gas)      :"
                    << "\n[SERIAL]          Raw ADC = " << out.mq9_raw_adc << " / 1023"
                    << " | Voltage = " << std::fixed << std::setprecision(3) << out.mq9_voltage_v << " V"
                    << "\n[SERIAL] Sensor 3 | MQ-135 (Air Quality & Toxins)    :"
                    << "\n[SERIAL]          Raw ADC = " << out.mq135_raw_adc << " / 1023"
                    << " | Voltage = " << std::fixed << std::setprecision(3) << out.mq135_voltage_v << " V"
                    << "\n[SERIAL] Sensor 4 | DHT22  (Temperature & Humidity)  :"
                    << "\n[SERIAL]          Temperature = " << std::fixed << std::setprecision(2) << out.temperature_c << " °C"
                    << " | Humidity = " << out.humidity_pct << " %"
                    << " [Status: " << (dht_ok ? "HEALTHY" : "FAULT") << "]"
                    << "\n[SERIAL] Sensor 5 | MPM10-CS (Particulate Matter)    :"
                    << "\n[SERIAL]          PM1.0 = " << std::fixed << std::setprecision(1) << out.pm1_0 << " ug/m3"
                    << " | PM2.5 = " << out.pm2_5 << " ug/m3"
                    << " | PM10 = " << out.pm10 << " ug/m3"
                    << " [Status: " << (pms_ok ? "HEALTHY" : "FAULT") << "]"
                    << "\n[SERIAL] Overall State : " << (all_ok ? "READY (Sensors stabilized)" : "WARMING UP (Sensors stabilizing)")
                    << "\n[SERIAL] ========================================================\n";
                std::cout << oss.str() << std::flush;
            }

            return true;

        } catch (const std::exception& e) {
            std::cerr << "[SERIAL] JSON parse error: " << e.what() << "\n";
            return false;
        }
    }

    static SensorTransportType detect_transport(const std::string& endpoint) {
        if (endpoint.rfind("tcp://", 0) == 0) return SensorTransportType::TCP;
        if (endpoint.rfind("unix://", 0) == 0) return SensorTransportType::UNIX_SOCKET;
        if (endpoint.rfind("/dev/", 0) == 0) return SensorTransportType::SERIAL_TTY;
        if (endpoint.find(".sock") != std::string::npos ||
           (!endpoint.empty() && endpoint.front() == '/' && endpoint.find(':') == std::string::npos)) {
            return SensorTransportType::UNIX_SOCKET;
        }
        if (endpoint.find(':') != std::string::npos || endpoint == "localhost" || endpoint == "127.0.0.1") {
            return SensorTransportType::TCP;
        }
        return SensorTransportType::SERIAL_TTY;
    }

private:
    std::string node_id_;
    std::string serial_port_;
    int baud_rate_;
    int timeout_ms_;
    int fd_;
    SensorTransportType transport_type_;
    int consecutive_errors_;
    int total_reads_;
    int valid_reads_;
    std::string read_buffer_;

    bool open_port() {
        transport_type_ = detect_transport(serial_port_);
        switch (transport_type_) {
            case SensorTransportType::TCP:
                return open_tcp();
            case SensorTransportType::UNIX_SOCKET:
                return open_unix_socket();
            case SensorTransportType::SERIAL_TTY:
            default:
                return open_serial_tty();
        }
    }

    bool open_tcp() {
        std::string ep = serial_port_;
        if (ep.rfind("tcp://", 0) == 0) {
            ep = ep.substr(6);
        }
        std::string host = constants::DEFAULT_ROUTER_MONITOR_HOST;
        int port = constants::DEFAULT_ROUTER_MONITOR_PORT;
        auto colon = ep.find(':');
        if (colon != std::string::npos) {
            host = ep.substr(0, colon);
            try {
                port = std::stoi(ep.substr(colon + 1));
            } catch (...) {
                port = constants::DEFAULT_ROUTER_MONITOR_PORT;
            }
        } else if (!ep.empty()) {
            host = ep;
        }

        if (host.empty() || host == "localhost") {
            host = constants::DEFAULT_ROUTER_MONITOR_HOST;
        }

        fd_ = ::socket(AF_INET, SOCK_STREAM, 0);
        if (fd_ < 0) {
            std::cerr << "[SERIAL] Cannot create TCP socket: " << std::strerror(errno) << "\n";
            return false;
        }

        struct timeval tv;
        tv.tv_sec = timeout_ms_ / 1000;
        tv.tv_usec = (timeout_ms_ % 1000) * 1000;
        setsockopt(fd_, SOL_SOCKET, SO_RCVTIMEO, (const char*)&tv, sizeof(tv));
        setsockopt(fd_, SOL_SOCKET, SO_SNDTIMEO, (const char*)&tv, sizeof(tv));

        struct sockaddr_in addr;
        std::memset(&addr, 0, sizeof(addr));
        addr.sin_family = AF_INET;
        addr.sin_port = htons(port);

        if (inet_pton(AF_INET, host.c_str(), &addr.sin_addr) <= 0) {
            struct hostent* he = gethostbyname(host.c_str());
            if (!he || !he->h_addr_list[0]) {
                std::cerr << "[SERIAL] Cannot resolve host " << host << "\n";
                close_port();
                return false;
            }
            std::memcpy(&addr.sin_addr, he->h_addr_list[0], sizeof(addr.sin_addr));
        }

        if (::connect(fd_, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            std::cerr << "[SERIAL] Cannot connect to router monitor proxy at "
                      << host << ":" << port << " (" << std::strerror(errno) << ")\n";
            close_port();
            return false;
        }

        std::cout << "[SERIAL] Connected to router monitor proxy at "
                  << host << ":" << port << "\n";
        std::cout << "[SERIAL] Ready to receive sensor data via UNO Q monitor bridge\n";
        return true;
    }

    bool open_unix_socket() {
        std::string ep = serial_port_;
        if (ep.rfind("unix://", 0) == 0) {
            ep = ep.substr(7);
        }

        fd_ = ::socket(AF_UNIX, SOCK_STREAM, 0);
        if (fd_ < 0) {
            std::cerr << "[SERIAL] Cannot create Unix domain socket: " << std::strerror(errno) << "\n";
            return false;
        }

        struct timeval tv;
        tv.tv_sec = timeout_ms_ / 1000;
        tv.tv_usec = (timeout_ms_ % 1000) * 1000;
        setsockopt(fd_, SOL_SOCKET, SO_RCVTIMEO, (const char*)&tv, sizeof(tv));
        setsockopt(fd_, SOL_SOCKET, SO_SNDTIMEO, (const char*)&tv, sizeof(tv));

        struct sockaddr_un addr;
        std::memset(&addr, 0, sizeof(addr));
        addr.sun_family = AF_UNIX;
        std::strncpy(addr.sun_path, ep.c_str(), sizeof(addr.sun_path) - 1);

        if (::connect(fd_, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
            std::cerr << "[SERIAL] Cannot connect to Unix socket at " << ep
                      << ": " << std::strerror(errno) << "\n";
            close_port();
            return false;
        }

        std::cout << "[SERIAL] Connected to Unix socket at " << ep << "\n";
        std::cout << "[SERIAL] Ready to receive sensor data\n";
        return true;
    }

    bool open_serial_tty() {
        fd_ = ::open(serial_port_.c_str(), O_RDWR | O_NOCTTY | O_NONBLOCK);
        if (fd_ < 0) {
            std::cerr << "[SERIAL] Cannot open " << serial_port_
                      << ": " << std::strerror(errno) << "\n";
            return false;
        }

        // Clear O_NONBLOCK after open (we use select() for timeout control)
        int flags = fcntl(fd_, F_GETFL, 0);
        fcntl(fd_, F_SETFL, flags & ~O_NONBLOCK);

        struct termios tty;
        std::memset(&tty, 0, sizeof(tty));

        if (tcgetattr(fd_, &tty) != 0) {
            std::cerr << "[SERIAL] tcgetattr failed: " << std::strerror(errno) << "\n";
            close_port();
            return false;
        }

        // Set baud rate
        speed_t baud = baud_to_speed(baud_rate_);
        cfsetispeed(&tty, baud);
        cfsetospeed(&tty, baud);

        // 8N1, no hardware flow control
        tty.c_cflag &= ~PARENB;
        tty.c_cflag &= ~CSTOPB;
        tty.c_cflag &= ~CSIZE;
        tty.c_cflag |= CS8;
        tty.c_cflag &= ~CRTSCTS;
        tty.c_cflag |= CREAD | CLOCAL;

        // Raw input mode
        tty.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);
        tty.c_iflag &= ~(IXON | IXOFF | IXANY);
        tty.c_iflag &= ~(IGNBRK | BRKINT | PARMRK | ISTRIP | INLCR | IGNCR | ICRNL);

        // Raw output
        tty.c_oflag &= ~OPOST;

        // Read settings: VMIN=0, VTIME=10 (1 second timeout per read() call)
        tty.c_cc[VMIN]  = 0;
        tty.c_cc[VTIME] = 10;

        if (tcsetattr(fd_, TCSANOW, &tty) != 0) {
            std::cerr << "[SERIAL] tcsetattr failed: " << std::strerror(errno) << "\n";
            close_port();
            return false;
        }

        // Flush any stale data
        tcflush(fd_, TCIOFLUSH);

        // Wait for Arduino bootloader reset (typically ~2 seconds)
        std::cout << "[SERIAL] Port " << serial_port_ << " opened at "
                  << baud_rate_ << " baud. Waiting for Arduino boot...\n";

        // Drain initial bootloader output
        drain_initial(3000);

        std::cout << "[SERIAL] Ready to receive sensor data\n";
        return true;
    }

    void close_port() {
        if (fd_ >= 0) {
            ::close(fd_);
            fd_ = -1;
        }
    }

    void drain_initial(int ms) {
        auto start = std::chrono::steady_clock::now();
        char buf[256];
        while (true) {
            auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - start).count();
            if (elapsed >= ms) break;

            fd_set fds;
            FD_ZERO(&fds);
            FD_SET(fd_, &fds);
            struct timeval tv;
            tv.tv_sec = 0;
            tv.tv_usec = 100000; // 100ms
            int ret = select(fd_ + 1, &fds, nullptr, nullptr, &tv);
            if (ret > 0) {
                ::read(fd_, buf, sizeof(buf));
            }
        }
    }

    void drain_pending() {
        if (fd_ < 0) return;
        while (true) {
            fd_set fds;
            FD_ZERO(&fds);
            FD_SET(fd_, &fds);
            struct timeval tv{0, 0};
            int ret = select(fd_ + 1, &fds, nullptr, nullptr, &tv);
            if (ret <= 0) break;

            char buf[512];
            ssize_t n = ::read(fd_, buf, sizeof(buf));
            if (n <= 0) {
                if (n == 0) {
                    close_port();
                }
                break;
            }
            read_buffer_.append(buf, n);
            if (read_buffer_.size() > 8192) {
                read_buffer_ = read_buffer_.substr(read_buffer_.size() - 4096);
                break;
            }
        }
    }

    /**
     * Read a complete \n-terminated line from serial, with timeout.
     * Consumes pending bytes and advances to the freshest valid sensor frame.
     */
    bool read_line(std::string& line) {
        if (fd_ < 0) return false;
        drain_pending();
        if (fd_ < 0) return false;

        auto start = std::chrono::steady_clock::now();

        while (true) {
            // Check if buffer already contains a complete line
            auto pos = read_buffer_.find('\n');
            if (pos != std::string::npos) {
                std::string candidate = read_buffer_.substr(0, pos);
                read_buffer_.erase(0, pos + 1);
                // Strip \r if present
                if (!candidate.empty() && candidate.back() == '\r') {
                    candidate.pop_back();
                }
                // Skip empty lines or malformed lines
                if (candidate.empty() || candidate[0] != '{') {
                    if (candidate.find("NAVOSEDGE_MCU_TEST") != std::string::npos) {
                        std::cout << "[SERIAL] Diagnostic beacon received: " << candidate << "\n";
                    } else if (candidate.find("[MCU]") != std::string::npos) {
                        std::cout << "[SERIAL] MCU log received: " << candidate << "\n";
                    }
                    continue; // Try next line
                }
                // If this is an Arduino hardware status/boot message, log it immediately
                if (candidate.find("\"status\"") != std::string::npos) {
                    std::cout << "[SERIAL] Arduino hardware message: " << candidate << "\n";
                    continue; // Continue to read actual sensor frame
                }

                // If another complete line is already queued, discard the older sensor frame
                // to ensure the application always processes the freshest real-time reading
                if (read_buffer_.find('\n') != std::string::npos) {
                    continue;
                }

                line = std::move(candidate);
                return true;
            }

            if (fd_ < 0) return false;

            // Read more bytes from serial
            auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                std::chrono::steady_clock::now() - start).count();
            if (elapsed >= timeout_ms_) {
                std::cerr << "[SERIAL] Read timeout after " << timeout_ms_ << "ms\n";
                return false;
            }

            fd_set fds;
            FD_ZERO(&fds);
            FD_SET(fd_, &fds);
            struct timeval tv;
            int remaining = timeout_ms_ - static_cast<int>(elapsed);
            tv.tv_sec  = remaining / 1000;
            tv.tv_usec = (remaining % 1000) * 1000;

            int ret = select(fd_ + 1, &fds, nullptr, nullptr, &tv);
            if (ret < 0) {
                if (errno == EINTR) continue;
                std::cerr << "[SERIAL] select() error: " << std::strerror(errno) << "\n";
                return false;
            }
            if (ret == 0) {
                // Timeout in select
                continue;
            }

            char buf[512];
            ssize_t n = ::read(fd_, buf, sizeof(buf));
            if (n <= 0) {
                if (n == 0) {
                    std::cerr << "[SERIAL] Port closed\n";
                    close_port();
                } else if (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR) {
                    std::cerr << "[SERIAL] Read error: " << std::strerror(errno) << "\n";
                    close_port();
                }
                return false;
            }
            read_buffer_.append(buf, n);
            drain_pending();
        }
    }

    SensorData make_error_reading(const std::string& reason) {
        std::cerr << "[SERIAL] Error reading: " << reason << "\n";
        SensorData d;
        d.node_id = node_id_;
        d.timestamp = now_iso8601();
        d.dht_ok = false;
        d.pms_ok = false;
        // Return valid empty structure for upstream handling, no fake physical sentinels.
        return d;
    }

    static double adc_to_voltage(int raw_adc) {
        return static_cast<double>(raw_adc) * (constants::ADC_VREF / static_cast<double>(constants::ADC_MAX));
    }

    static std::string now_iso8601() {
        auto now = std::chrono::system_clock::now();
        auto time_t_now = std::chrono::system_clock::to_time_t(now);
        std::tm tm_buf{};
        gmtime_r(&time_t_now, &tm_buf);

        char buf[32];
        std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm_buf);
        return std::string(buf);
    }

    static speed_t baud_to_speed(int baud) {
        switch (baud) {
            case 9600:   return B9600;
            case 19200:  return B19200;
            case 38400:  return B38400;
            case 57600:  return B57600;
            case 115200: return B115200;
            case 230400: return B230400;
            case 460800: return B460800;
            default:     return B115200;
        }
    }
};

} // namespace navos
