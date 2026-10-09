/**
 * NavosEdge Hardware Bridge — Entry Point
 *
 * Reads sensor data (mock or physical) and POSTs it to the
 * NavosEdge Intelligence Server at /hardware/data, while listening
 * for control events on /hardware/events via SSE.
 *
 * Usage:
 *   ./navos_hardware_bridge [--config <path>] [--node-id <id>] [--scenario normal|high_pm|traffic|dust] [--interval <sec>]
 */

#include <iostream>
#include <memory>
#include <string>
#include <csignal>

#include "config.hpp"
#include "sensor.hpp"
#include "serial_sensor.hpp"
#include "sensor_validator.hpp"
#include "http_client.hpp"
#include "bridge.hpp"

int main(int argc, char* argv[]) {
    std::string config_path = "config/hardware_config.json";
    std::string override_node_id;
    std::string override_scenario;
    std::string override_port;
    int override_interval = 0;
    int override_baud = 0;
    bool override_mock_set = false;
    bool override_mock = false;

    bool test_rpc = false;

    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if ((arg == "--config" || arg == "-c") && i + 1 < argc) {
            config_path = argv[++i];
        } else if ((arg == "--node-id" || arg == "-n") && i + 1 < argc) {
            override_node_id = argv[++i];
        } else if ((arg == "--scenario" || arg == "-s") && i + 1 < argc) {
            override_scenario = argv[++i];
        } else if ((arg == "--interval" || arg == "-i") && i + 1 < argc) {
            override_interval = std::stoi(argv[++i]);
        } else if ((arg == "--port" || arg == "-p") && i + 1 < argc) {
            override_port = argv[++i];
        } else if ((arg == "--baud" || arg == "-b") && i + 1 < argc) {
            override_baud = std::stoi(argv[++i]);
        } else if (arg == "--mock") {
            override_mock = true;
            override_mock_set = true;
        } else if (arg == "--physical") {
            override_mock = false;
            override_mock_set = true;
        } else if (arg == "--test-rpc" || arg == "--test-mcu-rpc") {
            test_rpc = true;
        } else if (arg == "--help" || arg == "-h") {
            std::cout << "Usage: " << argv[0] << " [options]\n"
                      << "  --config, -c <path>     Path to config JSON (default: config/hardware_config.json)\n"
                      << "  --node-id, -n <id>      Override node ID\n"
                      << "  --scenario, -s <mode>   Simulation scenario: normal, high_pm, traffic, dust\n"
                      << "  --interval, -i <sec>    Override sampling interval seconds\n"
                      << "  --port, -p <endpoint>   Override serial port / monitor proxy endpoint (e.g. 127.0.0.1:7500)\n"
                      << "  --baud, -b <rate>       Override serial baud rate (default: 115200)\n"
                      << "  --mock                  Force mock sensor simulation mode\n"
                      << "  --physical              Force physical hardware sensor mode\n"
                      << "  --test-mcu-rpc          Send test state over Router RPC and exit\n"
                      << "  --help, -h              Show this help\n";
            return 0;
        }
    }

    if (test_rpc) {
        std::cout << "[MCU] Standalone RPC test mode\n";
        navos::McuBridge mcu_bridge;
        if (!mcu_bridge.open_socket()) {
            std::cerr << "[MCU] Failed to connect to router socket\n";
            return 1;
        }

        NavosEdgeState state;
        navosStateInit(state);
        state.aqi = 63.41f;
        state.pm1_0 = 12.0f;
        state.pm2_5 = 18.0f;
        state.pm10 = 25.0f;
        state.temperature = 28.5f;
        state.humidity = 65.0f;
        std::strncpy(state.severity, "MODERATE", sizeof(state.severity) - 1);
        std::strncpy(state.advice, "Air quality is moderate. Sensitive groups should minimize outdoor exposure.", sizeof(state.advice) - 1);
        std::strncpy(state.weather_advice, "Warm & humid. Stay hydrated.", sizeof(state.weather_advice) - 1);
        
        std::strncpy(state.actions[0], "Close windows during high PM hours", NAVOS_MAX_STRING_LEN - 1);
        std::strncpy(state.actions[1], "Use indoor air purifier", NAVOS_MAX_STRING_LEN - 1);
        std::strncpy(state.actions[2], "Wear N95 mask near traffic", NAVOS_MAX_STRING_LEN - 1);
        state.action_count = 3;
        state.valid = true;

        bool ok = mcu_bridge.send_state(state);
        return ok ? 0 : 1;
    }

    // Load configuration
    navos::HardwareConfig cfg;
    try {
        cfg = navos::load_config(config_path);
    } catch (const std::exception& e) {
        if (config_path == "config/hardware_config.json") {
            try {
                cfg = navos::load_config("Hardware/config/hardware_config.json");
            } catch (...) {
                std::cerr << e.what() << "\n";
                return 1;
            }
        } else {
            std::cerr << e.what() << "\n";
            return 1;
        }
    }

    if (!override_node_id.empty()) {
        cfg.node_id = override_node_id;
    }
    if (!override_scenario.empty()) {
        cfg.scenario = override_scenario;
    }
    if (override_interval > 0) {
        cfg.sampling_interval_seconds = override_interval;
    }
    if (override_mock_set) {
        cfg.mock_mode = override_mock;
    }
    if (!override_port.empty()) {
        cfg.serial_port = override_port;
    }
    if (override_baud > 0) {
        cfg.serial_baud = override_baud;
    }

    auto scenario_enum = navos::parse_scenario(cfg.scenario);

    // Create sensor source
    std::unique_ptr<navos::SensorSource> sensor;
    if (cfg.mock_mode) {
        sensor = std::make_unique<navos::MockSensorSource>(cfg.node_id, scenario_enum);
        std::cout << "[HW] Mock sensor initialized (scenario: " << cfg.scenario << ")\n";
    } else {
        sensor = std::make_unique<navos::SerialSensorSource>(
            cfg.node_id, cfg.serial_port, cfg.serial_baud, cfg.serial_timeout_ms);
        std::cout << "[HW] Physical sensor initialized on " << cfg.serial_port
                  << " @ " << cfg.serial_baud << " baud\n";
        std::cout << "[HW] Monitored physical sensors: MQ-2 (Combustible/Smoke), MQ-9 (CO/Gas), "
                  << "MQ-135 (Air Quality), DHT22 (Temp/Humidity), MPM10-CS (PM1.0/PM2.5/PM10)\n";
    }

    // Create HTTP client
    navos::HttpClient http(cfg.http_timeout_seconds);

    // Create and configure bridge
    navos::HardwareBridge bridge(cfg, std::move(sensor), http);
    navos::HardwareBridge::register_instance(&bridge);

    // Register signal handlers for graceful shutdown and socket resilience
    std::signal(SIGINT,  navos::HardwareBridge::signal_handler);
    std::signal(SIGTERM, navos::HardwareBridge::signal_handler);
    std::signal(SIGPIPE, SIG_IGN);

    // Run the main loop
    bridge.run();

    return 0;
}
// Force rebuild v4 -- Continuous MCU loop + warm-up caching + display live-binding
