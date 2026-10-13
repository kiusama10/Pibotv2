#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <new>
#include <string>
#include <vector>

namespace cocos2d {
namespace network {
class HttpClient;
class HttpRequest;
class HttpResponse;
}  // namespace network
}  // namespace cocos2d

namespace saocb {
namespace bridge {
namespace cocos_abi {

// Verified against libcocos2dcpp.so SHA-256
// 1f8407eb34b857828f028b293aaf49c8597ea2a5a638982bac96648b2cc49170.
constexpr std::size_t kHttpRequestResponseCallbackOffset = 0x70;
constexpr std::size_t kHttpRequestUrlOffset = 0x10;
constexpr std::size_t kHttpClientSchedulerOffset = 0x90;
constexpr std::size_t kHttpResponseObjectSize = 0x88;
constexpr std::size_t kHttpResponseSucceededOffset = 0x18;
constexpr std::size_t kHttpResponseDataVectorOffset = 0x38;
constexpr std::size_t kHttpResponseCodeOffset = 0x50;

constexpr std::uintptr_t kCocosAllocateOffset = 0x96eb50;
constexpr std::uintptr_t kCocosRetainOffset = 0x18097d8;
constexpr std::uintptr_t kHttpResponseConstructorOffset = 0x1767a58;
constexpr std::uintptr_t kCocosReleaseOffset = 0x18097e8;
constexpr std::uintptr_t kSchedulerQueueFunctionOffset = 0x180ce10;
constexpr std::uintptr_t kAllocatorTagPointerOffset = 0x2487900;

constexpr std::uintptr_t kRequestBuilderStart = 0xe42e64;
constexpr std::uintptr_t kRequestBuilderEnd = 0xe43bf4;
constexpr std::uintptr_t kRequestSubmitCallA = 0xe4396c;
constexpr std::uintptr_t kRequestSubmitCallB = 0xe4397c;
constexpr std::uint32_t kRequestSubmitCallAInstruction = 0x9424945a;
constexpr std::uint32_t kRequestSubmitCallBInstruction = 0x94249419;
constexpr std::uintptr_t kFetchUserAllStart = 0x12d9834;
constexpr std::uintptr_t kFetchUserAllEnd = 0x12d9e30;
constexpr std::uintptr_t kRequestSubmitTargetA = 0x1768ad4;
constexpr std::uintptr_t kRequestSubmitTargetB = 0x17689e0;
constexpr std::uintptr_t kRequestResponseLambdaStart = 0xe4a414;
constexpr std::uintptr_t kResponseParserStart = 0xe46df0;
constexpr std::uintptr_t kNetworkResponseQueueStart = 0x1767d98;
constexpr std::uintptr_t kNetworkResponseLambdaStart = 0x1769034;

using HttpResponseCallback =
        std::function<void(cocos2d::network::HttpClient*,
                           cocos2d::network::HttpResponse*)>;
using CocosThreadTask = std::function<void()>;

// ARM64 evidence in the pinned library:
// - the shared request builder stores the HttpRequest URL std::string at +0x10;
// - fetchUserAll builds the HttpRequest response std::function at request +0x70
//   and calls the original request callback wrapper at 0xe4a414.
// - that wrapper calls GameApiHelper::onHttpRequestCallBack at 0xe46df0.
// Copy this while the original HttpRequest is live. std::function's copy
// constructor retains the original lambda captures.
inline HttpResponseCallback copyHttpResponseCallback(void* request) {
    if (request == nullptr) {
        return {};
    }
    auto* bytes = static_cast<std::byte*>(request);
    auto* callback = reinterpret_cast<HttpResponseCallback*>(
            bytes + kHttpRequestResponseCallbackOffset);
    return *callback;
}

// Call only on an HttpResponse constructed by the pinned game's original
// constructor (0x1767a58). That constructor initializes the vector subobject.
// The high-level GameApiHelper parser reads exactly these response fields.
inline bool populateConstructedHttpResponse(
        void* response,
        int httpStatus,
        const std::string& jsonBody) noexcept {
    if (response == nullptr) {
        return false;
    }

    auto* bytes = static_cast<std::byte*>(response);
    auto* body = std::launder(reinterpret_cast<std::vector<char>*>(
            bytes + kHttpResponseDataVectorOffset));
    try {
        body->assign(jsonBody.begin(), jsonBody.end());
    } catch (...) {
        body->clear();
        *reinterpret_cast<std::uint8_t*>(
                bytes + kHttpResponseSucceededOffset) = 0;
        *reinterpret_cast<std::int32_t*>(
                bytes + kHttpResponseCodeOffset) = 502;
        return false;
    }

    *reinterpret_cast<std::uint8_t*>(
            bytes + kHttpResponseSucceededOffset) =
            httpStatus == 200 ? 1 : 0;
    *reinterpret_cast<std::int32_t*>(
            bytes + kHttpResponseCodeOffset) = httpStatus;
    return true;
}

#if defined(__ANDROID__)
static_assert(sizeof(HttpResponseCallback) == 0x30,
              "Cocos std::__1::function ABI mismatch; do not build this bridge "
              "with a different C++ standard-library ABI");
static_assert(sizeof(CocosThreadTask) == 0x30,
              "Cocos std::__1::function ABI mismatch");
static_assert(sizeof(std::vector<char>) == 0x18,
              "Cocos std::__1::vector ABI mismatch");
#endif

}  // namespace cocos_abi
}  // namespace bridge
}  // namespace saocb
