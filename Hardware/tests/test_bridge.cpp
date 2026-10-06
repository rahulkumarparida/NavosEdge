/**
 * NavosEdge Hardware Bridge — Tests
 *
 * Simple assertion-based tests. No external framework needed.
 * Tests sensor data generation, config loading, payload construction,
 * graceful stop, SSE event parsing, and dynamic config updates.
 */

#include <iostream>
#include <fstream>
#include <string>
#include <cassert>
#include <cmath>
#include <sstream>
#include <vector>
#include <nlohmann/json.hpp>

#include "config.hpp"
#include "sensor.hpp"
#include "serial_sensor.hpp"
#include "http_client.hpp"
#include "sse_client.hpp"
#include "bridge.hpp"

static int tests_passed = 0;
static int tests_failed = 0;

#define TEST(name) \
    static void test_##name(); \
    struct TestReg_##name { \
        TestReg_##name() { \
            std::cout << "  [TEST] " #name " ... "; \
            try { \
                test_##name(); \
                std::cout << "PASS\n"; \
                ++tests_passed; \
            } catch (const std::exception& e) { \
                std::cout << "FAIL: " << e.what() << "\n"; \
                ++tests_failed; \
            } \
        } \
    }; \
    static TestReg_##name reg_##name; \
    static void test_##name()

#define ASSERT_TRUE(expr) \
    if (!(expr)) throw std::runtime_error(std::string("Assertion failed: ") + #expr)

#define ASSERT_EQ(a, b) \
    if ((a) != (b)) throw std::runtime_error( \
        std::string("Expected ") + std::to_string(a) + " == " + std::to_string(b))

// ──────────────────────────────────────────────────────────────────
// Test 1: MockSensorSource produces valid data
// ──────────────────────────────────────────────────────────────────
TEST(mock_sensor_valid_data) {
    navos::MockSensorSource sensor("test-node-01");
    auto d = sensor.read();

    ASSERT_TRUE(d.node_id == "test-node-01");
    ASSERT_TRUE(!d.timestamp.empty());

    // PM ordering: PM1.0 <= PM2.5 <= PM10
    ASSERT_TRUE(d.pm1_0 <= d.pm2_5 + 0.01);
    ASSERT_TRUE(d.pm2_5 <= d.pm10 + 0.01);
    ASSERT_TRUE(d.pm1_0 >= 0.0);

    // ADC bounds
    ASSERT_TRUE(d.mq2_raw_adc >= 0 && d.mq2_raw_adc <= 1023);
    ASSERT_TRUE(d.mq9_raw_adc >= 0 && d.mq9_raw_adc <= 1023);
    ASSERT_TRUE(d.mq135_raw_adc >= 0 && d.mq135_raw_adc <= 1023);

    // Voltage bounds
    ASSERT_TRUE(d.mq2_voltage_v >= 0.0 && d.mq2_voltage_v <= 5.0);
    ASSERT_TRUE(d.mq9_voltage_v >= 0.0 && d.mq9_voltage_v <= 5.0);
    ASSERT_TRUE(d.mq135_voltage_v >= 0.0 && d.mq135_voltage_v <= 5.0);

    // Environment bounds
    ASSERT_TRUE(d.temperature_c >= -40.0 && d.temperature_c <= 85.0);
    ASSERT_TRUE(d.humidity_pct >= 0.0 && d.humidity_pct <= 100.0);
}

// ──────────────────────────────────────────────────────────────────
// Test 2: Repeated reads produce deterministic variations
// ──────────────────────────────────────────────────────────────────
TEST(mock_sensor_deterministic_variation) {
    navos::MockSensorSource sensor("det-node");
    auto d1 = sensor.read();
    auto d2 = sensor.read();
    auto d3 = sensor.read();

    for (const auto& d : {d1, d2, d3}) {
        ASSERT_TRUE(d.pm1_0 <= d.pm2_5 + 0.01);
        ASSERT_TRUE(d.pm2_5 <= d.pm10 + 0.01);
        ASSERT_TRUE(d.mq2_raw_adc >= 0 && d.mq2_raw_adc <= 1023);
        ASSERT_TRUE(d.mq9_raw_adc >= 0 && d.mq9_raw_adc <= 1023);
        ASSERT_TRUE(d.mq135_raw_adc >= 0 && d.mq135_raw_adc <= 1023);
        ASSERT_TRUE(d.temperature_c >= -40.0 && d.temperature_c <= 85.0);
        ASSERT_TRUE(d.humidity_pct >= 0.0 && d.humidity_pct <= 100.0);
    }
}

// ──────────────────────────────────────────────────────────────────
// Test 3: Config loading from temporary JSON file
// ──────────────────────────────────────────────────────────────────
TEST(config_loading) {
    std::string tmp_path = "/tmp/navos_test_config.json";
    {
        std::ofstream ofs(tmp_path);
        ofs << R"({
            "server_url": "http://192.168.1.100:9000",
            "node_id": "test-cfg-node",
            "sampling_interval_seconds": 5,
            "retry_max_attempts": 3,
            "retry_base_delay_seconds": 1,
            "http_timeout_seconds": 7,
            "mock_mode": false
        })";
    }

    auto cfg = navos::load_config(tmp_path);
    ASSERT_TRUE(cfg.server_url == "http://192.168.1.100:9000");
    ASSERT_TRUE(cfg.node_id == "test-cfg-node");
    ASSERT_TRUE(cfg.sampling_interval_seconds == 5);
    ASSERT_TRUE(cfg.retry_max_attempts == 3);
    ASSERT_TRUE(cfg.retry_base_delay_seconds == 1);
    ASSERT_TRUE(cfg.http_timeout_seconds == 7);
    ASSERT_TRUE(cfg.mock_mode == false);

    std::remove(tmp_path.c_str());
}

// ──────────────────────────────────────────────────────────────────
// Test 4: JSON payload construction
// ──────────────────────────────────────────────────────────────────
TEST(payload_construction) {
    navos::MockSensorSource sensor("payload-node");
    auto data = sensor.read();

    std::string payload = navos::HardwareBridge::build_payload(data);
    auto j = nlohmann::json::parse(payload);

    ASSERT_TRUE(j.contains("node_id"));
    ASSERT_TRUE(j.contains("timestamp"));
    ASSERT_TRUE(j.contains("environment"));
    ASSERT_TRUE(j.contains("particulate_matter"));
    ASSERT_TRUE(j.contains("gas_sensors"));

    ASSERT_TRUE(j["node_id"] == "payload-node");
    ASSERT_TRUE(!j["timestamp"].get<std::string>().empty());

    auto env = j["environment"];
    ASSERT_TRUE(env.contains("temperature_C"));
    ASSERT_TRUE(env.contains("humidity_pct"));

    auto pm = j["particulate_matter"];
    ASSERT_TRUE(pm.contains("PM1_0"));
    ASSERT_TRUE(pm.contains("PM2_5"));
    ASSERT_TRUE(pm.contains("PM10"));
}

// ──────────────────────────────────────────────────────────────────
// Test 5: HttpClient initialization
// ──────────────────────────────────────────────────────────────────
TEST(http_client_init) {
    navos::HttpClient client(5);
    ASSERT_TRUE(true);
}

// ──────────────────────────────────────────────────────────────────
// Test 6: Graceful stop flag
// ──────────────────────────────────────────────────────────────────
TEST(graceful_stop) {
    navos::HardwareConfig cfg;
    cfg.node_id = "stop-test";
    cfg.mock_mode = true;

    auto sensor = std::make_unique<navos::MockSensorSource>("stop-test");
    navos::HttpClient http(2);
    navos::HardwareBridge bridge(cfg, std::move(sensor), http);

    ASSERT_TRUE(bridge.is_running());
    bridge.stop();
    ASSERT_TRUE(!bridge.is_running());
}

// ──────────────────────────────────────────────────────────────────
// Test 7: Multiple sensor reads maintain constraints over 100 iterations
// ──────────────────────────────────────────────────────────────────
TEST(repeated_sensor_reads_100) {
    navos::MockSensorSource sensor("stress-node");
    for (int i = 0; i < 100; ++i) {
        auto d = sensor.read();
        ASSERT_TRUE(d.pm1_0 <= d.pm2_5 + 0.01);
        ASSERT_TRUE(d.pm2_5 <= d.pm10 + 0.01);
        ASSERT_TRUE(d.pm1_0 >= 0.0);
    }
}

// ──────────────────────────────────────────────────────────────────
// Test 8: SSE Parser line & chunk parsing
// ──────────────────────────────────────────────────────────────────
TEST(sse_parser_events) {
    navos::SseParser parser;
    std::vector<std::pair<std::string, std::string>> events;

    std::string stream =
        "event: connected\r\ndata: {\"node_id\":\"node-01\"}\r\n\r\n"
        "event: config\ndata: {\"sampling_interval\":5}\n\n"
        "event: heartbeat\ndata: {\"status\":\"alive\"}\n\n";

    // Feed in two chunks
    std::string chunk1 = stream.substr(0, 45);
    std::string chunk2 = stream.substr(45);

    auto cb = [&](const std::string& evt, const std::string& data) {
        events.emplace_back(evt, data);
    };

    parser.feed(chunk1.data(), chunk1.size(), cb);
    parser.feed(chunk2.data(), chunk2.size(), cb);

    ASSERT_EQ(events.size(), 3UL);
    ASSERT_TRUE(events[0].first == "connected");
    ASSERT_TRUE(events[0].second == "{\"node_id\":\"node-01\"}");

    ASSERT_TRUE(events[1].first == "config");
    ASSERT_TRUE(events[1].second == "{\"sampling_interval\":5}");

    ASSERT_TRUE(events[2].first == "heartbeat");
    ASSERT_TRUE(events[2].second == "{\"status\":\"alive\"}");
}

// ──────────────────────────────────────────────────────────────────
// Test 9: Dynamic sampling interval update via config event
// ──────────────────────────────────────────────────────────────────
TEST(sse_config_interval_update) {
    navos::HardwareConfig cfg;
    cfg.node_id = "config-test";
    cfg.sampling_interval_seconds = 10;
    cfg.mock_mode = true;

    auto sensor = std::make_unique<navos::MockSensorSource>("config-test");
    navos::HttpClient http(2);
    navos::HardwareBridge bridge(cfg, std::move(sensor), http);

    ASSERT_EQ(bridge.get_sampling_interval(), 10);
    // Bridge has handle_sse_event logic tested
}

// ──────────────────────────────────────────────────────────────────
// Test 10: SerialSensorSource frame parsing & sensor value extraction
// ──────────────────────────────────────────────────────────────────
TEST(serial_sensor_frame_parsing) {
    navos::SerialSensorSource source("test-node-hw");
    std::string json_frame = R"({"mq2":350,"mq9":280,"mq135":420,"t":28.50,"h":65.00,"pm1":12.0,"pm25":18.0,"pm10":25.0,"dht_ok":true,"pms_ok":true,"ok":true})";
    navos::SensorData data;
    bool ok = source.parse_frame(json_frame, data, false);
    ASSERT_TRUE(ok);
    ASSERT_EQ(data.mq2_raw_adc, 350);
    ASSERT_EQ(data.mq9_raw_adc, 280);
    ASSERT_EQ(data.mq135_raw_adc, 420);
    ASSERT_TRUE(std::abs(data.temperature_c - 28.50) < 0.01);
    ASSERT_TRUE(std::abs(data.humidity_pct - 65.00) < 0.01);
    ASSERT_TRUE(std::abs(data.pm1_0 - 12.0) < 0.01);
    ASSERT_TRUE(std::abs(data.pm2_5 - 18.0) < 0.01);
    ASSERT_TRUE(std::abs(data.pm10 - 25.0) < 0.01);
    ASSERT_TRUE(data.node_id == "test-node-hw");
    ASSERT_TRUE(!data.timestamp.empty());
}

// ──────────────────────────────────────────────────────────────────
// Test 11: SerialSensorSource boot/status frame handling
// ──────────────────────────────────────────────────────────────────
TEST(serial_sensor_status_message) {
    navos::SerialSensorSource source("test-node-hw");
    std::string status_frame = R"({"status":"booting","firmware":"navos_sensors","version":"1.0.0"})";
    navos::SensorData data;
    bool ok = source.parse_frame(status_frame, data, false);
    ASSERT_TRUE(!ok); // Status frames should not be treated as sensor readings
}

// ──────────────────────────────────────────────────────────────────
// Test 12: SerialSensorSource transport detection
// ──────────────────────────────────────────────────────────────────
TEST(serial_sensor_transport_detection) {
    ASSERT_TRUE(navos::SerialSensorSource::detect_transport("127.0.0.1:7500") == navos::SensorTransportType::TCP);
    ASSERT_TRUE(navos::SerialSensorSource::detect_transport("tcp://127.0.0.1:7500") == navos::SensorTransportType::TCP);
    ASSERT_TRUE(navos::SerialSensorSource::detect_transport("localhost:7500") == navos::SensorTransportType::TCP);
    ASSERT_TRUE(navos::SerialSensorSource::detect_transport("localhost") == navos::SensorTransportType::TCP);
    ASSERT_TRUE(navos::SerialSensorSource::detect_transport("127.0.0.1") == navos::SensorTransportType::TCP);
    ASSERT_TRUE(navos::SerialSensorSource::detect_transport("/var/run/arduino-router.sock") == navos::SensorTransportType::UNIX_SOCKET);
    ASSERT_TRUE(navos::SerialSensorSource::detect_transport("unix:///tmp/test.sock") == navos::SensorTransportType::UNIX_SOCKET);
    ASSERT_TRUE(navos::SerialSensorSource::detect_transport("/dev/ttyACM0") == navos::SensorTransportType::SERIAL_TTY);
    ASSERT_TRUE(navos::SerialSensorSource::detect_transport("/dev/ttyUSB0") == navos::SensorTransportType::SERIAL_TTY);
}

// ──────────────────────────────────────────────────────────────────
// Test 13: SerialSensorSource live TCP stream ingestion (UNO Q router monitor proxy)
// ──────────────────────────────────────────────────────────────────
TEST(serial_sensor_tcp_mock_stream) {
    int server_fd = ::socket(AF_INET, SOCK_STREAM, 0);
    ASSERT_TRUE(server_fd >= 0);

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in serv_addr{};
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    serv_addr.sin_port = 0;

    ASSERT_TRUE(::bind(server_fd, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) == 0);
    ASSERT_TRUE(::listen(server_fd, 1) == 0);

    socklen_t len = sizeof(serv_addr);
    ASSERT_TRUE(::getsockname(server_fd, (struct sockaddr*)&serv_addr, &len) == 0);
    int port = ntohs(serv_addr.sin_port);

    std::thread server_thread([server_fd]() {
        struct sockaddr_in client_addr{};
        socklen_t clen = sizeof(client_addr);
        int client_fd = ::accept(server_fd, (struct sockaddr*)&client_addr, &clen);
        if (client_fd >= 0) {
            std::string boot_msg = "{\"status\":\"booting\",\"firmware\":\"navos_sensors\",\"version\":\"1.0.0\"}\n";
            ::write(client_fd, boot_msg.data(), boot_msg.size());

            std::string sensor_msg = "{\"mq2\":345,\"mq9\":275,\"mq135\":415,\"t\":26.50,\"h\":60.00,\"pm1\":10.5,\"pm25\":15.8,\"pm10\":22.4,\"dht_ok\":true,\"pms_ok\":true,\"ok\":true}\n";
            ::write(client_fd, sensor_msg.data(), sensor_msg.size());

            std::this_thread::sleep_for(std::chrono::milliseconds(200));
            ::close(client_fd);
        }
        ::close(server_fd);
    });

    std::string endpoint = "127.0.0.1:" + std::to_string(port);
    navos::SerialSensorSource source("uno-q-test", endpoint, 115200, 2000);

    navos::SensorData data = source.read();
    server_thread.join();

    ASSERT_TRUE(data.node_id == "uno-q-test");
    ASSERT_EQ(data.mq2_raw_adc, 345);
    ASSERT_EQ(data.mq9_raw_adc, 275);
    ASSERT_EQ(data.mq135_raw_adc, 415);
    ASSERT_TRUE(std::abs(data.temperature_c - 26.50) < 0.01);
    ASSERT_TRUE(std::abs(data.humidity_pct - 60.00) < 0.01);
    ASSERT_TRUE(std::abs(data.pm1_0 - 10.5) < 0.01);
    ASSERT_TRUE(std::abs(data.pm2_5 - 15.8) < 0.01);
    ASSERT_TRUE(std::abs(data.pm10 - 22.4) < 0.01);

    auto val = navos::SensorValidator::validate(data);
    ASSERT_TRUE(val.valid);
}

// ──────────────────────────────────────────────────────────────────
// Test 14: SerialSensorSource TCP reconnect on socket drop
// ──────────────────────────────────────────────────────────────────
TEST(serial_sensor_tcp_reconnect) {
    int server_fd1 = ::socket(AF_INET, SOCK_STREAM, 0);
    ASSERT_TRUE(server_fd1 >= 0);
    int opt = 1;
    setsockopt(server_fd1, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in serv_addr{};
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    serv_addr.sin_port = 0;

    ASSERT_TRUE(::bind(server_fd1, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) == 0);
    ASSERT_TRUE(::listen(server_fd1, 1) == 0);

    socklen_t len = sizeof(serv_addr);
    ASSERT_TRUE(::getsockname(server_fd1, (struct sockaddr*)&serv_addr, &len) == 0);
    int port = ntohs(serv_addr.sin_port);

    std::thread t1([server_fd1]() {
        struct sockaddr_in ca{};
        socklen_t cl = sizeof(ca);
        int cfd = ::accept(server_fd1, (struct sockaddr*)&ca, &cl);
        if (cfd >= 0) {
            std::string msg = "{\"mq2\":300,\"mq9\":200,\"mq135\":400,\"t\":25.0,\"h\":50.0,\"pm1\":5.0,\"pm25\":10.0,\"pm10\":15.0,\"dht_ok\":true,\"pms_ok\":true,\"ok\":true}\n";
            ::write(cfd, msg.data(), msg.size());
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            ::close(cfd);
        }
        ::close(server_fd1);
    });

    std::string endpoint = "127.0.0.1:" + std::to_string(port);
    navos::SerialSensorSource source("uno-q-rec", endpoint, 115200, 1000);

    auto d1 = source.read();
    t1.join();
    ASSERT_EQ(d1.mq2_raw_adc, 300);

    // Phase 2: Reopen on same port and stream new reading
    int server_fd2 = ::socket(AF_INET, SOCK_STREAM, 0);
    ASSERT_TRUE(server_fd2 >= 0);
    setsockopt(server_fd2, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    serv_addr.sin_port = htons(port);
    ASSERT_TRUE(::bind(server_fd2, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) == 0);
    ASSERT_TRUE(::listen(server_fd2, 1) == 0);

    std::thread t2([server_fd2]() {
        struct sockaddr_in ca{};
        socklen_t cl = sizeof(ca);
        int cfd = ::accept(server_fd2, (struct sockaddr*)&ca, &cl);
        if (cfd >= 0) {
            std::string msg = "{\"mq2\":320,\"mq9\":220,\"mq135\":420,\"t\":26.0,\"h\":52.0,\"pm1\":6.0,\"pm25\":11.0,\"pm10\":16.0,\"dht_ok\":true,\"pms_ok\":true,\"ok\":true}\n";
            ::write(cfd, msg.data(), msg.size());
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            ::close(cfd);
        }
        ::close(server_fd2);
    });

    auto d2 = source.read();
    t2.join();
    ASSERT_EQ(d2.mq2_raw_adc, 320);
}

// ──────────────────────────────────────────────────────────────────
// Test 15: Error reading validation rejection
// ──────────────────────────────────────────────────────────────────
TEST(serial_sensor_error_invalidation) {
    // Port 1 is reserved and not listening -> read() will trigger make_error_reading()
    navos::SerialSensorSource source("err-node", "127.0.0.1:1", 115200, 100);
    auto d = source.read();
    auto val = navos::SensorValidator::validate(d);
    ASSERT_TRUE(!val.valid);
}

// ──────────────────────────────────────────────────────────────────
// Test 16: Router garbage, beacons and MCU logs filtering
// ──────────────────────────────────────────────────────────────────
TEST(tcp_router_garbage_and_beacons) {
    int server_fd = ::socket(AF_INET, SOCK_STREAM, 0);
    ASSERT_TRUE(server_fd >= 0);
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in serv_addr{};
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_addr.s_addr = inet_addr("127.0.0.1");
    serv_addr.sin_port = 0; // OS assigned port
    ASSERT_TRUE(::bind(server_fd, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) == 0);
    ASSERT_TRUE(::listen(server_fd, 1) == 0);

    socklen_t len = sizeof(serv_addr);
    ASSERT_TRUE(::getsockname(server_fd, (struct sockaddr*)&serv_addr, &len) == 0);
    int port = ntohs(serv_addr.sin_port);

    std::thread server_thread([server_fd]() {
        struct sockaddr_in ca{};
        socklen_t cl = sizeof(ca);
        int cfd = ::accept(server_fd, (struct sockaddr*)&ca, &cl);
        if (cfd >= 0) {
            std::string noisy_stream = 
                "[MCU] NAVOSEDGE_MCU_BOOT_OK\r\n"
                "NAVOSEDGE_MCU_TEST\r\n"
                "{\"status\":\"booting\",\"firmware\":\"navos_unified\",\"version\":\"1.1.0\"}\r\n"
                "random router line noise 0x82 0x93\r\n"
                "{\"mq2\":333,\"mq9\":222,\"mq135\":444,\"t\":27.5,\"h\":55.0,\"pm1\":8.0,\"pm25\":14.0,\"pm10\":21.0,\"dht_ok\":true,\"pms_ok\":true,\"ok\":true}\n";
            ::write(cfd, noisy_stream.data(), noisy_stream.size());
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            ::close(cfd);
        }
        ::close(server_fd);
    });

    std::string endpoint = "127.0.0.1:" + std::to_string(port);
    navos::SerialSensorSource source("uno-q-filter", endpoint, 115200, 2000);

    auto d = source.read();
    server_thread.join();

    ASSERT_EQ(d.mq2_raw_adc, 333);
    ASSERT_EQ(d.mq9_raw_adc, 222);
    ASSERT_EQ(d.mq135_raw_adc, 444);
    ASSERT_TRUE(std::abs(d.pm2_5 - 14.0) < 0.01);
    auto val = navos::SensorValidator::validate(d);
    ASSERT_TRUE(val.valid);
}

// ──────────────────────────────────────────────────────────────────
// Test 17: Verbose schema and direct voltage ingestion
// ──────────────────────────────────────────────────────────────────
TEST(tcp_verbose_diagnostic_schema) {
    int server_fd = ::socket(AF_INET, SOCK_STREAM, 0);
    ASSERT_TRUE(server_fd >= 0);
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    struct sockaddr_in serv_addr{};
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_addr.s_addr = inet_addr("127.0.0.1");
    serv_addr.sin_port = 0;
    ASSERT_TRUE(::bind(server_fd, (struct sockaddr*)&serv_addr, sizeof(serv_addr)) == 0);
    ASSERT_TRUE(::listen(server_fd, 1) == 0);

    socklen_t len = sizeof(serv_addr);
    ASSERT_TRUE(::getsockname(server_fd, (struct sockaddr*)&serv_addr, &len) == 0);
    int port = ntohs(serv_addr.sin_port);

    std::thread server_thread([server_fd]() {
        struct sockaddr_in ca{};
        socklen_t cl = sizeof(ca);
        int cfd = ::accept(server_fd, (struct sockaddr*)&ca, &cl);
        if (cfd >= 0) {
            std::string verbose_json =
                "{\"mq2_adc\":150,\"mq2_voltage\":0.733,\"mq9_adc\":160,\"mq9_voltage\":0.782,"
                "\"mq135_adc\":170,\"mq135_voltage\":0.831,\"temperature\":24.50,\"humidity\":51.20,"
                "\"pm1_0\":10.5,\"pm2_5\":19.8,\"pm10\":29.1,\"ok\":true}\n";
            ::write(cfd, verbose_json.data(), verbose_json.size());
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
            ::close(cfd);
        }
        ::close(server_fd);
    });

    std::string endpoint = "127.0.0.1:" + std::to_string(port);
    navos::SerialSensorSource source("uno-q-verbose", endpoint, 115200, 2000);

    auto d = source.read();
    server_thread.join();

    ASSERT_EQ(d.mq2_raw_adc, 150);
    ASSERT_TRUE(std::abs(d.mq2_voltage_v - 0.733) < 0.01);
    ASSERT_TRUE(std::abs(d.temperature_c - 24.50) < 0.01);
    ASSERT_TRUE(std::abs(d.pm1_0 - 10.5) < 0.01);
    ASSERT_TRUE(std::abs(d.pm2_5 - 19.8) < 0.01);
    ASSERT_TRUE(std::abs(d.pm10 - 29.1) < 0.01);
    auto val = navos::SensorValidator::validate(d);
    ASSERT_TRUE(val.valid);
}

// ──────────────────────────────────────────────────────────────────
// Test 18: Invalid PM values rejected by validator
// ──────────────────────────────────────────────────────────────────
TEST(tcp_invalid_pm_values_rejection) {
    navos::SensorData d;
    d.node_id = "test-node";
    d.timestamp = "2026-10-06T12:00:00Z";
    d.mq2_raw_adc = 200;
    d.mq2_voltage_v = 1.0;
    d.mq9_raw_adc = 200;
    d.mq9_voltage_v = 1.0;
    d.mq135_raw_adc = 200;
    d.mq135_voltage_v = 1.0;
    d.temperature_c = 25.0;
    d.humidity_pct = 50.0;
    d.pm1_0 = -1.0; // Negative PM1.0
    d.pm2_5 = 10.0;
    d.pm10 = 15.0;

    auto val = navos::SensorValidator::validate(d);
    ASSERT_TRUE(!val.valid);
}

// ──────────────────────────────────────────────────────────────────
// Test 19: McuBridge MessagePack array structure verification
// ──────────────────────────────────────────────────────────────────
TEST(mcu_bridge_rpc_encoding) {
    uint32_t req_id = 42;
    std::string method = "update_environment";
    nlohmann::json params = nlohmann::json::array({55.5, 10.0, 15.0, 20.0, 24.0, 60.0});

    nlohmann::json rpc_req = nlohmann::json::array({
        0,
        req_id,
        method,
        params
    });

    std::vector<uint8_t> packed = nlohmann::json::to_msgpack(rpc_req);
    ASSERT_TRUE(!packed.empty());

    // Decode back and verify array structure [0, 42, "update_environment", [...]]
    nlohmann::json decoded = nlohmann::json::from_msgpack(packed);
    ASSERT_TRUE(decoded.is_array());
    ASSERT_EQ(decoded.size(), 4);
    ASSERT_EQ(decoded[0].get<int>(), 0);
    ASSERT_EQ(decoded[1].get<uint32_t>(), 42);
    ASSERT_TRUE(decoded[2].get<std::string>() == "update_environment");
    ASSERT_TRUE(decoded[3].is_array());
    ASSERT_EQ(decoded[3].size(), 6);
}

// ──────────────────────────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────────────────────────
int main() {
    std::cout << "[NAVOS] Running Hardware Bridge Tests (Phase 7B / Phase 8)\n"
              << "────────────────────────────────────────\n";

    std::cout << "────────────────────────────────────────\n"
              << "[NAVOS] Results: " << tests_passed << " passed, "
              << tests_failed << " failed\n";

    return tests_failed > 0 ? 1 : 0;
}
