#pragma once

#include "cocos_response_abi.hpp"
#include "request_registry.hpp"

namespace saocb {
namespace bridge {

struct CocosRuntime {
    void* context = nullptr;
    void (*retain)(void* context, void* object) = nullptr;
    void* (*createHttpResponse)(
            void* context,
            cocos2d::network::HttpRequest* originalRequest) = nullptr;
    void (*release)(void* context, void* object) = nullptr;
    bool (*scheduleOnCocosThread)(
            void* context,
            cocos2d::network::HttpClient* client,
            const cocos_abi::CocosThreadTask& task) = nullptr;
};

// Copies HttpRequest::responseCallback at +0x70 and stores it under requestId.
// Completion is always queued through the Cocos scheduler before constructing
// an HttpResponse and invoking that original callback.
bool registerCocosResponse(
        RequestRegistry& registry,
        const std::string& requestId,
        cocos2d::network::HttpClient* client,
        void* request,
        CocosRuntime runtime);

}  // namespace bridge
}  // namespace saocb
