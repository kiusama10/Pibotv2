#include "request_registry.hpp"

#include <utility>

namespace saocb {
namespace bridge {

bool RequestRegistry::registerRequest(
        const std::string& requestId,
        Callback callback) {
    if (requestId.empty() || !callback) {
        return false;
    }
    std::lock_guard<std::mutex> lock(mutex_);
    return pending_.emplace(requestId, std::move(callback)).second;
}

bool RequestRegistry::complete(
        const std::string& requestId,
        int httpStatus,
        const std::string& responseEnvelope) {
    Callback callback;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        const auto found = pending_.find(requestId);
        if (found == pending_.end()) {
            return false;
        }
        callback = std::move(found->second);
        pending_.erase(found);
    }
    callback(httpStatus, responseEnvelope);
    return true;
}

bool RequestRegistry::cancel(const std::string& requestId) {
    static const std::string cancelled =
            "{\"error\":{\"code\":\"request_cancelled\"}}";
    return complete(requestId, 499, cancelled);
}

std::size_t RequestRegistry::size() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return pending_.size();
}

RequestRegistry& globalRequestRegistry() {
    static RequestRegistry registry;
    return registry;
}

}  // namespace bridge
}  // namespace saocb
