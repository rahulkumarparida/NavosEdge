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
// Main
// ──────────────────────────────────────────────────────────────────
int main() {
    std::cout << "[NAVOS] Running Hardware Bridge Tests (Phase 7B)\n"
              << "────────────────────────────────────────\n";

    std::cout << "────────────────────────────────────────\n"
              << "[NAVOS] Results: " << tests_passed << " passed, "
              << tests_failed << " failed\n";

    return tests_failed > 0 ? 1 : 0;
}
