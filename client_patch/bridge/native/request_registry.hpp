#pragma once

#include <functional>
#include <mutex>
#include <string>
#include <unordered_map>

namespace saocb {
namespace bridge {

class RequestRegistry {
public:
    using Callback = std::function<void(int, const std::string&)>;

    // Returns false for invalid input or a duplicate in-flight request ID.
    bool registerRequest(const std::string& requestId, Callback callback);

    // Removes before invoking so duplicate/late replies can never run twice.
    bool complete(
            const std::string& requestId,
            int httpStatus,
            const std::string& responseEnvelope);

    bool cancel(const std::string& requestId);
    std::size_t size() const;

private:
    mutable std::mutex mutex_;
    std::unordered_map<std::string, Callback> pending_;
};

RequestRegistry& globalRequestRegistry();

}  // namespace bridge
}  // namespace saocb
