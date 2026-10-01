#include <cstdlib>
#pragma once

#include <string>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <nlohmann/json.hpp>

#include "constants.hpp"

namespace navos {

struct HardwareConfig {
    std::string server_url        = constants::DEFAULT_SERVER_URL;
    std::string node_id           = constants::DEFAULT_NODE_ID;
    int  sampling_interval_seconds = constants::DEFAULT_SAMPLING_INTERVAL_SECONDS;
    int  retry_max_attempts        = constants::DEFAULT_RETRY_MAX_ATTEMPTS;
    int  retry_base_delay_seconds  = constants::DEFAULT_RETRY_BASE_DELAY_SECONDS;
    int  http_timeout_seconds      = constants::DEFAULT_HTTP_TIMEOUT_SECONDS;
    bool mock_mode                 = constants::DEFAULT_MOCK_MODE;
    std::string scenario           = constants::DEFAULT_SCENARIO;

    // Physical sensor serial connection
    std::string serial_port       = constants::DEFAULT_SERIAL_PORT;
    int  serial_baud              = constants::DEFAULT_SERIAL_BAUD;
    int  serial_timeout_ms        = constants::DEFAULT_SERIAL_TIMEOUT_MS;
};

inline HardwareConfig load_config(const std::string& path) {
    std::ifstream ifs(path);
    if (!ifs.is_open()) {
        throw std::runtime_error("[NAVOS] Cannot open config file: " + path);
    }

    nlohmann::json j;
    try {
        ifs >> j;
    } catch (const nlohmann::json::parse_error& e) {
        throw std::runtime_error(
            std::string("[NAVOS] Config parse error: ") + e.what());
    }

    HardwareConfig cfg;

    if (j.contains("server_url"))                cfg.server_url              = j["server_url"].get<std::string>();
    if (j.contains("node_id"))                   cfg.node_id                 = j["node_id"].get<std::string>();
    if (j.contains("sampling_interval_seconds"))   cfg.sampling_interval_seconds = j["sampling_interval_seconds"].get<int>();
    if (j.contains("retry_max_attempts"))         cfg.retry_max_attempts      = j["retry_max_attempts"].get<int>();
    if (j.contains("retry_base_delay_seconds"))   cfg.retry_base_delay_seconds = j["retry_base_delay_seconds"].get<int>();
    if (j.contains("http_timeout_seconds"))       cfg.http_timeout_seconds    = j["http_timeout_seconds"].get<int>();
    if (j.contains("mock_mode"))                  cfg.mock_mode               = j["mock_mode"].get<bool>();
    if (j.contains("scenario"))                   cfg.scenario                = j["scenario"].get<std::string>();
    if (j.contains("serial_port"))                 cfg.serial_port             = j["serial_port"].get<std::string>();
    if (j.contains("serial_baud"))                 cfg.serial_baud             = j["serial_baud"].get<int>();
    if (j.contains("serial_timeout_ms"))           cfg.serial_timeout_ms       = j["serial_timeout_ms"].get<int>();

    // Environment variable overrides (useful for unified deployment via .env)
    if (const char* env_host = std::getenv("NAVOS_HOST")) {
        std::string host = env_host;
        std::string port = "8420";
        if (const char* env_port = std::getenv("NAVOS_PORT")) {
            port = env_port;
        }
        // Assuming no https for local hardware bridge
        cfg.server_url = "http://" + host + ":" + port;
    } else if (const char* env_url = std::getenv("NAVOS_SERVER_URL")) {
        cfg.server_url = env_url;
    }

    if (const char* env_node_id = std::getenv("NAVOS_NODE_ID")) {
        cfg.node_id = env_node_id;
    }

    if (const char* env_interval = std::getenv("NAVOS_SENSOR_INTERVAL")) {
        try {
            cfg.sampling_interval_seconds = std::stoi(env_interval);
        } catch (...) {}
    }

    if (const char* env_mode = std::getenv("NAVOS_SENSOR_MODE")) {
        std::string mode = env_mode;
        cfg.mock_mode = (mode == "mock" || mode == "true" || mode == "1");
    }

    if (const char* env_scenario = std::getenv("NAVOS_SCENARIO")) {
        cfg.scenario = env_scenario;
    }

    if (const char* env_serial = std::getenv("NAVOS_SERIAL_PORT")) {
        cfg.serial_port = env_serial;
    }
    if (const char* env_baud = std::getenv("NAVOS_SERIAL_BAUD")) {
        try { cfg.serial_baud = std::stoi(env_baud); } catch (...) {}
    }

    // Validate
    if (cfg.node_id.empty()) {
        throw std::runtime_error("[NAVOS] node_id must not be empty");
    }
    if (cfg.server_url.empty()) {
        throw std::runtime_error("[NAVOS] server_url must not be empty");
    }
    if (cfg.sampling_interval_seconds <= 0) {
        throw std::runtime_error("[NAVOS] sampling_interval_seconds must be positive");
    }
    if (cfg.http_timeout_seconds <= 0) {
        throw std::runtime_error("[NAVOS] http_timeout_seconds must be positive");
    }

    std::cout << "[NAVOS] Config loaded from: " << path << "\n"
              << "        server_url:    " << cfg.server_url << "\n"
              << "        node_id:       " << cfg.node_id << "\n"
              << "        interval:      " << cfg.sampling_interval_seconds << "s\n"
              << "        timeout:       " << cfg.http_timeout_seconds << "s\n"
              << "        scenario:      " << cfg.scenario << "\n"
              << "        mock_mode:     " << (cfg.mock_mode ? "true" : "false") << "\n"
              << "        serial_port:   " << cfg.serial_port << "\n"
              << "        serial_baud:   " << cfg.serial_baud << "\n"
              << "        max_retries:   " << cfg.retry_max_attempts << "\n";

    return cfg;
}

} // namespace navos
