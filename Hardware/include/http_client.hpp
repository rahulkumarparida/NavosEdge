#pragma once

#include <string>
#include <iostream>
#include <curl/curl.h>

namespace navos {

struct HttpResponse {
    int         status_code = 0;
    std::string body;
    bool        success     = false;
    std::string error_msg;
};

class HttpClient {
public:
    explicit HttpClient(int timeout_seconds = 10)
        : timeout_seconds_(timeout_seconds)
    {
        curl_global_init(CURL_GLOBAL_DEFAULT);
    }

    ~HttpClient() {
        curl_global_cleanup();
    }

    // Non-copyable
    HttpClient(const HttpClient&) = delete;
    HttpClient& operator=(const HttpClient&) = delete;

    HttpResponse get(const std::string& url) {
        HttpResponse resp;
        CURL* curl = curl_easy_init();
        if (!curl) {
            resp.error_msg = "Failed to initialize CURL";
            return resp;
        }

        std::string response_body;
        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, static_cast<long>(timeout_seconds_));
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, static_cast<long>(timeout_seconds_));
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_body);
        curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);

        CURLcode res = curl_easy_perform(curl);
        if (res != CURLE_OK) {
            resp.error_msg = curl_easy_strerror(res);
            resp.success = false;
        } else {
            long http_code = 0;
            curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
            resp.status_code = static_cast<int>(http_code);
            resp.body = response_body;
            resp.success = true;
        }

        curl_easy_cleanup(curl);
        return resp;
    }

    HttpResponse post_json(const std::string& url, const std::string& json_body) {
        HttpResponse resp;
        CURL* curl = curl_easy_init();
        if (!curl) {
            resp.error_msg = "Failed to initialize CURL";
            return resp;
        }

        std::string response_body;

        struct curl_slist* headers = nullptr;
        headers = curl_slist_append(headers, "Content-Type: application/json");
        headers = curl_slist_append(headers, "Accept: application/json");

        curl_easy_setopt(curl, CURLOPT_URL, url.c_str());
        curl_easy_setopt(curl, CURLOPT_POST, 1L);
        curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_body.c_str());
        curl_easy_setopt(curl, CURLOPT_POSTFIELDSIZE, static_cast<long>(json_body.size()));
        curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
        curl_easy_setopt(curl, CURLOPT_TIMEOUT, static_cast<long>(timeout_seconds_));
        curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, static_cast<long>(timeout_seconds_));
        curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);
        curl_easy_setopt(curl, CURLOPT_WRITEDATA, &response_body);
        curl_easy_setopt(curl, CURLOPT_NOSIGNAL, 1L);

        CURLcode res = curl_easy_perform(curl);
        if (res != CURLE_OK) {
            resp.error_msg = curl_easy_strerror(res);
            resp.success = false;
        } else {
            long http_code = 0;
            curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &http_code);
            resp.status_code = static_cast<int>(http_code);
            resp.body = response_body;
            resp.success = true;
        }

        curl_slist_free_all(headers);
        curl_easy_cleanup(curl);
        return resp;
    }

private:
    int timeout_seconds_;

    static size_t write_callback(char* ptr, size_t size, size_t nmemb, void* userdata) {
        auto* body = static_cast<std::string*>(userdata);
        body->append(ptr, size * nmemb);
        return size * nmemb;
    }
};

} // namespace navos
