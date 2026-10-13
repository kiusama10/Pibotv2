#define _GNU_SOURCE

#include "cocos_runtime_android.hpp"

#include <link.h>

#include <cstdint>
#include <cstring>

namespace saocb {
namespace bridge {
namespace {

struct RuntimeContext {
    std::uintptr_t libraryBase = 0;
    const void* allocatorTag = nullptr;
};

struct LibrarySearch {
    std::uintptr_t base = 0;
};

int findCocosLibrary(dl_phdr_info* info, std::size_t, void* opaque) {
    if (info->dlpi_name != nullptr
            && std::strstr(info->dlpi_name, "libcocos2dcpp.so") != nullptr) {
        static_cast<LibrarySearch*>(opaque)->base =
                static_cast<std::uintptr_t>(info->dlpi_addr);
        return 1;
    }
    return 0;
}

template <typename Function>
Function at(const RuntimeContext& context, std::uintptr_t offset) {
    return reinterpret_cast<Function>(context.libraryBase + offset);
}

void retainCocosObject(void* opaque, void* object) {
    auto* context = static_cast<RuntimeContext*>(opaque);
    using Retain = void (*)(void*);
    at<Retain>(*context, cocos_abi::kCocosRetainOffset)(object);
}

void* createHttpResponse(
        void* opaque,
        cocos2d::network::HttpRequest* originalRequest) {
    auto* context = static_cast<RuntimeContext*>(opaque);
    using Allocate = void* (*)(std::size_t, const void*);
    using Constructor = void (*)(void*, void*);

    auto* response = at<Allocate>(
            *context, cocos_abi::kCocosAllocateOffset)(
            cocos_abi::kHttpResponseObjectSize, context->allocatorTag);
    if (response == nullptr) {
        return nullptr;
    }
    at<Constructor>(
            *context, cocos_abi::kHttpResponseConstructorOffset)(
            response, originalRequest);
    return response;
}

void releaseCocosObject(void* opaque, void* object) {
    auto* context = static_cast<RuntimeContext*>(opaque);
    using Release = void (*)(void*);
    at<Release>(*context, cocos_abi::kCocosReleaseOffset)(object);
}

bool scheduleOnCocosThread(
        void* opaque,
        cocos2d::network::HttpClient* client,
        const cocos_abi::CocosThreadTask& task) {
    if (client == nullptr) {
        return false;
    }
    auto* bytes = reinterpret_cast<std::byte*>(client);
    void* scheduler = *reinterpret_cast<void**>(
            bytes + cocos_abi::kHttpClientSchedulerOffset);
    if (scheduler == nullptr) {
        return false;
    }

    auto* context = static_cast<RuntimeContext*>(opaque);
    using QueueTask =
            void (*)(void*, const cocos_abi::CocosThreadTask&);
    at<QueueTask>(*context, cocos_abi::kSchedulerQueueFunctionOffset)(
            scheduler, task);
    return true;
}

}  // namespace

const CocosRuntime* loadedCocosRuntime() {
    static RuntimeContext context = [] {
        LibrarySearch search;
        dl_iterate_phdr(findCocosLibrary, &search);
        RuntimeContext result;
        result.libraryBase = search.base;
        if (result.libraryBase != 0) {
            result.allocatorTag = *reinterpret_cast<const void* const*>(
                    result.libraryBase
                    + cocos_abi::kAllocatorTagPointerOffset);
        }
        return result;
    }();

    static const CocosRuntime runtime{
            &context,
            retainCocosObject,
            createHttpResponse,
            releaseCocosObject,
            scheduleOnCocosThread,
    };
    return context.libraryBase == 0 || context.allocatorTag == nullptr
            ? nullptr
            : &runtime;
}

}  // namespace bridge
}  // namespace saocb
