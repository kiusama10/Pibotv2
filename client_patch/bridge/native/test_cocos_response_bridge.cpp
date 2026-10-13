#include "cocos_response_bridge.hpp"

#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <new>
#include <string>
#include <utility>
#include <vector>

using saocb::bridge::CocosRuntime;
using saocb::bridge::RequestRegistry;
using saocb::bridge::cocos_abi::HttpResponseCallback;

namespace {

struct FakeRequest {
    std::array<std::byte,
               saocb::bridge::cocos_abi::kHttpRequestResponseCallbackOffset>
            prefix{};
    HttpResponseCallback callback;
    int references = 1;
};

struct FakeResponse {
    alignas(16) std::array<std::byte,
                           saocb::bridge::cocos_abi::
                                   kHttpResponseObjectSize>
            bytes{};
    bool bodyConstructed = false;
    FakeRequest* request = nullptr;
};

struct FakeRuntime {
    std::vector<saocb::bridge::cocos_abi::CocosThreadTask> tasks;
    int releases = 0;
    bool callbackCalled = false;
    std::string receivedBody;
    int receivedStatus = 0;
    bool receivedSuccess = false;
    FakeResponse response;
    FakeRequest* expectedRequest = nullptr;
    bool schedulerUsedBeforeCallback = false;
};

void retainObject(void* opaque, void* object) {
    auto* runtime = static_cast<FakeRuntime*>(opaque);
    assert(object == runtime->expectedRequest);
    ++runtime->expectedRequest->references;
}

void* createResponse(void* opaque, cocos2d::network::HttpRequest* request) {
    auto* runtime = static_cast<FakeRuntime*>(opaque);
    assert(reinterpret_cast<void*>(request) == runtime->expectedRequest);
    runtime->response.request = runtime->expectedRequest;
    ++runtime->response.request->references;  // Mimic HttpResponse's retain.
    auto* body = new (runtime->response.bytes.data()
                      + saocb::bridge::cocos_abi::
                              kHttpResponseDataVectorOffset)
            std::vector<char>();
    runtime->response.bodyConstructed = body != nullptr;
    return runtime->response.bytes.data();
}

void releaseObject(void* opaque, void* response) {
    auto* runtime = static_cast<FakeRuntime*>(opaque);
    if (response == runtime->response.bytes.data()) {
        auto* body = std::launder(reinterpret_cast<std::vector<char>*>(
                runtime->response.bytes.data()
                + saocb::bridge::cocos_abi::kHttpResponseDataVectorOffset));
        body->~vector<char>();
        runtime->response.bodyConstructed = false;
        --runtime->response.request->references;  // Mimic HttpResponse dtor.
        runtime->response.request = nullptr;
        ++runtime->releases;
        return;
    }

    assert(response == runtime->expectedRequest);
    --runtime->expectedRequest->references;
}

bool scheduleTask(
        void* opaque,
        cocos2d::network::HttpClient*,
        const saocb::bridge::cocos_abi::CocosThreadTask& task) {
    auto* runtime = static_cast<FakeRuntime*>(opaque);
    runtime->schedulerUsedBeforeCallback = !runtime->callbackCalled;
    runtime->tasks.push_back(task);
    return true;
}

}  // namespace

int main() {
    FakeRuntime runtime;
    FakeRequest request;
    runtime.expectedRequest = &request;
    assert(reinterpret_cast<std::byte*>(&request.callback)
                    - reinterpret_cast<std::byte*>(&request)
            == static_cast<std::ptrdiff_t>(
                    saocb::bridge::cocos_abi::
                            kHttpRequestResponseCallbackOffset));
    auto* fakeClient =
            reinterpret_cast<cocos2d::network::HttpClient*>(0x1234);
    request.callback = [&runtime, fakeClient](
                               cocos2d::network::HttpClient* client,
                               cocos2d::network::HttpResponse* response) {
        assert(client == fakeClient);
        assert(response == reinterpret_cast<cocos2d::network::HttpResponse*>(
                                   runtime.response.bytes.data()));
        assert(runtime.response.request == runtime.expectedRequest);
        assert(runtime.expectedRequest->references >= 2);
        const auto* bytes = reinterpret_cast<const std::byte*>(response);
        runtime.receivedSuccess = *reinterpret_cast<const std::uint8_t*>(
                                          bytes + saocb::bridge::cocos_abi::
                                                          kHttpResponseSucceededOffset)
                != 0;
        runtime.receivedStatus = *reinterpret_cast<const std::int32_t*>(
                bytes + saocb::bridge::cocos_abi::kHttpResponseCodeOffset);
        const auto* body = std::launder(
                reinterpret_cast<const std::vector<char>*>(
                        bytes + saocb::bridge::cocos_abi::
                                        kHttpResponseDataVectorOffset));
        runtime.receivedBody.assign(body->begin(), body->end());
        runtime.callbackCalled = true;
    };

    const CocosRuntime api{
            &runtime,
            retainObject,
            createResponse,
            releaseObject,
            scheduleTask,
    };
    RequestRegistry registry;
    assert(saocb::bridge::registerCocosResponse(
            registry,
            "bridge-test-1",
            fakeClient,
            &request,
            api));
    request.callback = {};
    --request.references;  // HttpClient relinquishes its original ownership.
    assert(request.references == 1);
    assert(!runtime.callbackCalled);
    assert(registry.complete("bridge-test-1", 200, "{\"user\":{}}"));
    assert(!runtime.callbackCalled);
    assert(runtime.tasks.size() == 1);
    assert(runtime.schedulerUsedBeforeCallback);
    assert(request.references == 1);

    runtime.tasks.front()();
    assert(runtime.callbackCalled);
    assert(runtime.receivedSuccess);
    assert(runtime.receivedStatus == 200);
    assert(runtime.receivedBody == "{\"user\":{}}");
    assert(runtime.releases == 1);
    assert(request.references == 1);
    runtime.tasks.clear();
    assert(request.references == 0);
    return 0;
}
