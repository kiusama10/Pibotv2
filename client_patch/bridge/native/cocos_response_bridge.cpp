#include "cocos_response_bridge.hpp"

#include <memory>
#include <stdexcept>
#include <utility>

namespace saocb {
namespace bridge {
namespace {

struct ResponseRelease {
    CocosRuntime runtime;
    void* response;

    ~ResponseRelease() {
        if (response != nullptr && runtime.release != nullptr) {
            runtime.release(runtime.context, response);
        }
    }
};

}  // namespace

bool registerCocosResponse(
        RequestRegistry& registry,
        const std::string& requestId,
        cocos2d::network::HttpClient* client,
        void* request,
        CocosRuntime runtime) {
    if (requestId.empty() || client == nullptr || request == nullptr
            || runtime.createHttpResponse == nullptr
            || runtime.retain == nullptr
            || runtime.release == nullptr
            || runtime.scheduleOnCocosThread == nullptr) {
        return false;
    }

    auto callback = cocos_abi::copyHttpResponseCallback(request);
    if (!callback) {
        return false;
    }

    runtime.retain(runtime.context, request);
    std::shared_ptr<void> retainedRequest(
            request,
            [runtime](void* object) {
                runtime.release(runtime.context, object);
            });

    return registry.registerRequest(
            requestId,
            [runtime,
             client,
             retainedRequest,
             callback = std::move(callback)](
                    int httpStatus, const std::string& jsonBody) mutable {
                cocos_abi::CocosThreadTask task =
                        [runtime,
                         client,
                         retainedRequest,
                         callback = std::move(callback),
                         httpStatus,
                         jsonBody]() mutable {
                            void* response =
                                     runtime.createHttpResponse(
                                             runtime.context,
                                             static_cast<
                                                     cocos2d::network::HttpRequest*>(
                                                     retainedRequest.get()));
                            if (response == nullptr) {
                                return;
                            }

                            ResponseRelease release{runtime, response};
                            cocos_abi::populateConstructedHttpResponse(
                                    response, httpStatus, jsonBody);
                            callback(
                                    client,
                                    reinterpret_cast<
                                            cocos2d::network::HttpResponse*>(
                                            response));
                        };

                if (!runtime.scheduleOnCocosThread(
                            runtime.context, client, task)) {
                    throw std::runtime_error(
                            "Cocos scheduler is unavailable; response was not "
                            "delivered off-thread.");
                }
            });
}

}  // namespace bridge
}  // namespace saocb
