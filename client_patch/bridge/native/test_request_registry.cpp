#include "request_registry.hpp"

#include <atomic>
#include <cassert>
#include <string>
#include <thread>
#include <vector>

using saocb::bridge::RequestRegistry;

int main() {
    RequestRegistry registry;
    int observedStatus = 0;
    std::string observedBody;

    assert(registry.registerRequest(
            "req-success",
            [&observedStatus, &observedBody](int status, const std::string& body) {
                observedStatus = status;
                observedBody = body;
            }));
    assert(!registry.registerRequest(
            "req-success",
            [](int, const std::string&) {}));
    assert(registry.complete("req-success", 200, "{\"request_id\":\"req-success\"}"));
    assert(!registry.complete("req-success", 200, "duplicate"));
    assert(observedStatus == 200);
    assert(observedBody == "{\"request_id\":\"req-success\"}");

    assert(registry.registerRequest("req-cancel", [](int status, const std::string&) {
        assert(status == 499);
    }));
    assert(registry.cancel("req-cancel"));
    assert(!registry.cancel("req-cancel"));

    std::atomic<int> calls(0);
    assert(registry.registerRequest("req-race", [&calls](int, const std::string&) {
        ++calls;
    }));
    std::vector<std::thread> workers;
    for (int index = 0; index < 8; ++index) {
        workers.emplace_back([&registry]() {
            registry.complete("req-race", 200, "race");
        });
    }
    for (std::thread& worker : workers) {
        worker.join();
    }
    assert(calls == 1);
    assert(registry.size() == 0);
    return 0;
}
