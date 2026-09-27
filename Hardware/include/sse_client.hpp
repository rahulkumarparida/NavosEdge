#pragma once

#include <string>
#include <functional>
#include <thread>
#include <atomic>
#include <iostream>
#include <algorithm>
#include <chrono>
#include <curl/curl.h>

namespace navos {

struct SseParser {
    std::string buffer;
    std::string current_event;
    std::string current_data;

    template <typename Callback>
    void feed(const char* data, size_t len, Callback&& cb) {
        buffer.append(data, len);
        size_t pos = 0;
        while ((pos = buffer.find('\n')) != std::string::npos) {
            std::string line = buffer.substr(0, pos);
            buffer.erase(0, pos + 1);

            if (!line.empty() && line.back() == '\r') {
                line.pop_back();
            }

            if (line.empty()) {
                if (!current_event.empty() || !current_data.empty()) {
                    cb(current_event.empty() ? "message" : current_event, current_data);
                    current_event.clear();
                    current_data.clear();
                }
            } else if (line.rfind("event:", 0) == 0) {
                current_event = trim(line.substr(6));
            } else if (line.rfind("data:", 0) == 0) {
                current_data = trim(line.substr(5));
            }
        }
    }

    static std::string trim(const std::string& str) {
        size_t first = str.find_first_not_of(" \t");
        if (first == std::string::npos) return "";
        size_t last = str.find_last_not_of(" \t");
        return str.substr(first, (last - first + 1));
    }
};

class SseClient {
public:
    using EventCallback = std::function<void(const std::string& event, const std::string& data_json)>;

    SseClient(std::string server_url, std::string node_id, EventCallback callback)
        : server_url_(std::move(server_url))
        , node_id_(std::move(node_id))
        , callback_(std::move(callback))
        , running_(false)
    {}

    ~SseClient() {
        stop();
    }

    // Non-copyable
    SseClient(const SseClient&) = delete;
    SseClient& operator=(const SseClient&) = delete;

    void start() {
        if (running_.load()) return;
        running_ = true;
        thread_ = std::thread(&SseClient::run_loop, this);
    }

    void stop() {
        if (!running_.load()) return;
        running_ = false;
        if (thread_.joinable()) {
            thread_.join();
        }
    }

    bool is_running() const {
        return running_.load();
    }

private:
    std::string server_url_;
    std::string node_id_;
    EventCallback callback_;
    std::atomic<bool> running_;
    std::thread thread_;

    struct WriteContext {
        SseParser parser;
        EventCallback callback;
        std::atomic<bool>* running;
    };

    static size_t write_callback(char* ptr, size_t size, size_t nmemb, void* userdata) {
        auto* ctx = static_cast<WriteContext*>(userdata);
        if (ctx && ctx->running && ctx->running->load()) {
            size_t total = size * nmemb;
            ctx->parser.feed(ptr, total, ctx->callback);
            return total;
        }
        return 0; // Abort transfer
    }

    static int progress_callback(void* clientp, curl_off_t, curl_off_t, curl_off_t, curl_off_t) {
        auto* running = static_cast<std::atomic<bool>*>(clientp);
        if (running && !running->load()) {
            return 1; // Abort transfer immediately
        }
        return 0;
    }

    void run_loop() {
        std::string sse_url = server_url_ + "/hardware/events?node_id=" + node_id_;
        int retry_attempt = 0;

        while (running_.load()) {
            std::cout << "[NAVOS] [SSE] Connecting to control channel: " << sse_url << "\n";

            CURL* curl = curl_easy_init();
            if (!curl) {
                std::cerr << "[NAVOS] [SSE] Failed to initialize CURL\n";
                std::this_thread::sleep_for(std::chrono::seconds(2));
                continue;
            }

            WriteContext ctx;
            ctx.callback = callback_;
            ctx.running = &running_;

            struct curl_slist* headers = nullptr;
            headers = curl_slist_append(headers, "Accept: text/event-stream");
            headers = curl_slist_append(headers, "Cache-Control: no-cache");

            curl_easy_setopt(curl, CURLOPT_URL, sse_url.c_str());
            curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
            curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
            curl_easy_setopt(curl, CURLOPT_WRITEDATA, &ctx);
            curl_easy_setopt(curl, CURLOPT_NOPROGRESS, 0L);
            curl_easy_setopt(curl, CURLOPT_XFERINFOFUNCTION, progress_callback);
            curl_easy_setopt(curl, CURLOPT_XFERINFODATA, &running_);
            curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);
            curl_easy_setopt(curl, CURLOPT_TCP_KEEPALIVE, 1L);

            CURLcode res = curl_easy_perform(curl);
            curl_slist_free_all(headers);
            curl_easy_cleanup(curl);

            if (!running_.load()) {
                break;
            }

            ++retry_attempt;
            int backoff = std::min(1 << std::min(retry_attempt, 5), 30);
            std::cerr << "[NAVOS] [SSE] Connection lost (" << curl_easy_strerror(res)
                      << "). Reconnecting in " << backoff << "s...\n";

            for (int i = 0; i < backoff * 2 && running_.load(); ++i) {
                std::this_thread::sleep_for(std::chrono::milliseconds(500));
            }
        }

        std::cout << "[NAVOS] [SSE] Control channel listener stopped.\n";
    }
};

} // namespace navos
