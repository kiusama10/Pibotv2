#include "cocos_response_abi.hpp"
#include "game_api_routing.hpp"

#include <android/log.h>
#include <jni.h>

#include <dlfcn.h>
#include <link.h>
#include <sys/mman.h>
#include <unistd.h>

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string_view>
#include <string>

#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif

namespace {

using namespace saocb::bridge;

std::uintptr_t gCocosLibraryBase = 0;

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

std::uintptr_t cocosBase() {
    LibrarySearch search;
    dl_iterate_phdr(findCocosLibrary, &search);
    return search.base;
}

std::uintptr_t runtimeAddress(
        std::uintptr_t base,
        std::uintptr_t offset) {
    return base + offset;
}

bool isBranchReachable(std::uintptr_t from, std::uintptr_t to) {
    const auto delta = static_cast<std::int64_t>(to)
            - static_cast<std::int64_t>(from);
    return (delta & 3) == 0
            && delta >= -(static_cast<std::int64_t>(1) << 27)
            && delta < (static_cast<std::int64_t>(1) << 27);
}

std::uint32_t encodeBl(std::uintptr_t from, std::uintptr_t to) {
    const auto delta = static_cast<std::int64_t>(to)
            - static_cast<std::int64_t>(from);
    return 0x94000000u
            | (static_cast<std::uint32_t>(delta >> 2) & 0x03ffffffu);
}

void* mapNear(std::uintptr_t target, std::size_t pageSize) {
    const std::uintptr_t pageMask = ~(static_cast<std::uintptr_t>(pageSize) - 1);
    const std::uintptr_t center = target & pageMask;
    constexpr std::uintptr_t kMaxDistance = 120u * 1024u * 1024u;
    constexpr std::uintptr_t kStride = 64u * 1024u;

    for (std::uintptr_t distance = kStride;
            distance < kMaxDistance;
            distance += kStride) {
        const std::uintptr_t candidates[] = {
                center + distance,
                center > distance ? center - distance : 0,
        };
        for (const auto candidate : candidates) {
            if (candidate == 0
                    || !isBranchReachable(target, candidate)) {
                continue;
            }
            void* fixed = mmap(
                    reinterpret_cast<void*>(candidate),
                    pageSize,
                    PROT_READ | PROT_WRITE,
                    MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE,
                    -1,
                    0);
            if (fixed != MAP_FAILED) {
                return fixed;
            }

            // Older Android kernels may not implement MAP_FIXED_NOREPLACE.
            void* hinted = mmap(
                    reinterpret_cast<void*>(candidate),
                    pageSize,
                    PROT_READ | PROT_WRITE,
                    MAP_PRIVATE | MAP_ANONYMOUS,
                    -1,
                    0);
            if (hinted != MAP_FAILED) {
                const auto address = reinterpret_cast<std::uintptr_t>(hinted);
                if (isBranchReachable(target, address)) {
                    return hinted;
                }
                munmap(hinted, pageSize);
            }
        }
    }
    return MAP_FAILED;
}

void writeThunk(std::byte* destination, int mode, std::uintptr_t target) {
    // BL from the game site sets LR. The thunk only changes x2, then branches
    // (not BLRs) to the C++ hook so its return reaches the game's continuation.
    const std::uint32_t instructions[] = {
            0xd2800002u | (static_cast<std::uint32_t>(mode) << 5),  // mov x2,#mode
            0x58000070u,                                            // ldr x16, +12
            0xd61f0200u,                                            // br x16
            0xd503201fu,                                            // nop, align literal
    };
    std::memcpy(destination, instructions, sizeof(instructions));
    std::memcpy(destination + sizeof(instructions), &target, sizeof(target));
}

struct LibcxxStringView {
    const char* data = nullptr;
    std::size_t size = 0;
};

bool readLibcxxString(
        const std::byte* object,
        LibcxxStringView* output) {
    if (object == nullptr || output == nullptr) {
        return false;
    }

    const auto first = static_cast<std::uint8_t>(object[0]);
    if ((first & 1u) == 0) {
        output->size = first >> 1;
        output->data = reinterpret_cast<const char*>(object + 1);
    } else {
        std::memcpy(&output->size, object + sizeof(std::uint64_t), sizeof(output->size));
        std::memcpy(&output->data, object + 2 * sizeof(std::uint64_t), sizeof(output->data));
    }

    return output->size <= 4096
            && (output->size == 0 || output->data != nullptr);
}

const char* requestMethodName(const std::byte* request) {
    std::int32_t type = -1;
    std::memcpy(
            &type,
            request + cocos_abi::kHttpRequestTypeOffset,
            sizeof(type));
    switch (type) {
        case 0:
            return "GET";
        case 1:
            return "POST";
        case 2:
            return "PUT";
        case 3:
            return "DELETE";
        default:
            return nullptr;
    }
}

jint getCreatedJavaVms(JavaVM** vm) {
    using GetCreatedJavaVms = jint (*)(JavaVM**, jsize, jsize*);
    auto function = reinterpret_cast<GetCreatedJavaVms>(
            dlsym(RTLD_DEFAULT, "JNI_GetCreatedJavaVMs"));
    void* artHandle = nullptr;
    if (function == nullptr) {
        artHandle = dlopen("libart.so", RTLD_NOW | RTLD_NOLOAD);
        if (artHandle == nullptr) {
            artHandle = dlopen("libart.so", RTLD_NOW);
        }
        if (artHandle != nullptr) {
            function = reinterpret_cast<GetCreatedJavaVms>(
                    dlsym(artHandle, "JNI_GetCreatedJavaVMs"));
        }
    }
    if (function == nullptr) {
        if (artHandle != nullptr) {
            dlclose(artHandle);
        }
        return JNI_ERR;
    }
    jsize count = 0;
    const jint status = function(vm, 1, &count);
    if (artHandle != nullptr) {
        dlclose(artHandle);
    }
    return status == JNI_OK && count > 0 ? JNI_OK : JNI_ERR;
}

bool callJavaGameApi(
        std::string_view requestUrl,
        const char* requestMethod,
        const char* requestBody,
        std::size_t bodySize,
        void* httpClient,
        void* httpRequest) {
    constexpr std::size_t kMaxRequestBodyBytes = 1024u * 1024u;
    if (requestUrl.empty()
            || requestMethod == nullptr
            || (bodySize != 0 && requestBody == nullptr)
            || bodySize > kMaxRequestBodyBytes
            || httpClient == nullptr
            || httpRequest == nullptr) {
        return false;
    }

    JavaVM* vm = nullptr;
    if (getCreatedJavaVms(&vm) != JNI_OK || vm == nullptr) {
        return false;
    }

    JNIEnv* env = nullptr;
    bool attachedHere = false;
    const jint environmentStatus =
            vm->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6);
    if (environmentStatus == JNI_EDETACHED) {
        if (vm->AttachCurrentThread(&env, nullptr) != JNI_OK) {
            return false;
        }
        attachedHere = true;
    } else if (environmentStatus != JNI_OK || env == nullptr) {
        return false;
    }

    bool accepted = false;
    if (env->PushLocalFrame(12) == JNI_OK) {
        jclass bridge = env->FindClass(
                "com/bandainamcoent/saomdeu/GameApiBridge");
        if (bridge != nullptr) {
            jmethodID dispatch = env->GetStaticMethodID(
                    bridge,
                    "dispatchGameApiRequest",
                    "(Ljava/lang/String;Ljava/lang/String;[BJJ)Ljava/lang/String;");
            if (dispatch != nullptr) {
                const std::string url(requestUrl.data(), requestUrl.size());
                jstring javaUrl = env->NewStringUTF(url.c_str());
                jstring javaMethod = env->NewStringUTF(requestMethod);
                jbyteArray javaBody = env->NewByteArray(static_cast<jsize>(bodySize));
                if (javaUrl != nullptr && javaMethod != nullptr && javaBody != nullptr) {
                    if (bodySize != 0) {
                        env->SetByteArrayRegion(
                                javaBody,
                                0,
                                static_cast<jsize>(bodySize),
                                reinterpret_cast<const jbyte*>(requestBody));
                    }
                }
                if (javaUrl != nullptr
                        && javaMethod != nullptr
                        && javaBody != nullptr
                        && !env->ExceptionCheck()) {
                    jobject requestId = env->CallStaticObjectMethod(
                            bridge,
                            dispatch,
                            javaUrl,
                            javaMethod,
                            javaBody,
                            static_cast<jlong>(
                                    reinterpret_cast<std::uintptr_t>(httpClient)),
                            static_cast<jlong>(
                                    reinterpret_cast<std::uintptr_t>(httpRequest)));
                    accepted = requestId != nullptr && !env->ExceptionCheck();
                }
            }
        }
        if (env->ExceptionCheck()) {
            env->ExceptionClear();
        }
        env->PopLocalFrame(nullptr);
    } else if (env->ExceptionCheck()) {
        env->ExceptionClear();
    }

    if (attachedHere) {
        vm->DetachCurrentThread();
    }
    return accepted;
}

void submitHook(void* httpClient, void* httpRequest, int mode) noexcept {
    const std::uintptr_t base = gCocosLibraryBase;
    if (base == 0) {
        return;
    }

    auto* requestBytes = static_cast<std::byte*>(httpRequest);
    LibcxxStringView requestUrl;
    if (requestBytes == nullptr
            || !readLibcxxString(
                    requestBytes + cocos_abi::kHttpRequestUrlOffset,
                    &requestUrl)) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "GameAPI submit blocked because its original URL could not be read");
        return;
    }

    const std::string_view url(requestUrl.data, requestUrl.size);
    const auto submitRoute = classifySubmitRoute(true, url);
    if (submitRoute == SubmitRoute::kBridge) {
        const std::string_view routeLog = gameApiRouteForLog(url);
        const int routeLength = static_cast<int>(
                routeLog.size() > 160 ? 160 : routeLog.size());
        const char* method = requestMethodName(requestBytes);
        const char* bodyBegin = nullptr;
        const char* bodyEnd = nullptr;
        std::memcpy(
                &bodyBegin,
                requestBytes + cocos_abi::kHttpRequestDataBeginOffset,
                sizeof(bodyBegin));
        std::memcpy(
                &bodyEnd,
                requestBytes + cocos_abi::kHttpRequestDataEndOffset,
                sizeof(bodyEnd));

        std::size_t bodySize = 0;
        if (bodyBegin != nullptr || bodyEnd != nullptr) {
            const auto beginAddress = reinterpret_cast<std::uintptr_t>(bodyBegin);
            const auto endAddress = reinterpret_cast<std::uintptr_t>(bodyEnd);
            if (bodyBegin == nullptr
                    || bodyEnd == nullptr
                    || endAddress < beginAddress) {
                __android_log_print(
                        ANDROID_LOG_ERROR,
                        "SAOCBBridge",
                        "Legacy GameAPI route=%.*s blocked because its body is invalid",
                        routeLength,
                        routeLog.data());
                return;
            }
            bodySize = static_cast<std::size_t>(endAddress - beginAddress);
        }

        if (callJavaGameApi(
                url,
                method,
                bodyBegin,
                bodySize,
                httpClient,
                httpRequest)) {
            __android_log_print(
                    ANDROID_LOG_INFO,
                    "SAOCBBridge",
                    "Legacy GameAPI request diverted to the SAO-CB dispatcher");
            return;
        }

        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "Legacy GameAPI route=%.*s blocked because bridge dispatch failed",
                routeLength,
                routeLog.data());
        return;
    }

    if (!shouldUseOriginalCocosTransport(submitRoute)) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "GameAPI request blocked because its route could not be classified");
        return;
    }

    using OriginalSend = void (*)(void*, void*);
    const std::uintptr_t originalOffset = mode == 0
            ? cocos_abi::kRequestSubmitTargetA
            : cocos_abi::kRequestSubmitTargetB;
    reinterpret_cast<OriginalSend>(base + originalOffset)(
            httpClient, httpRequest);
}

bool installHook() {
    const std::uintptr_t base = cocosBase();
    const long pageSizeResult = sysconf(_SC_PAGESIZE);
    if (base == 0 || pageSizeResult <= 0) {
        return false;
    }
    gCocosLibraryBase = base;
    const auto pageSize = static_cast<std::size_t>(pageSizeResult);
    const auto siteA = runtimeAddress(base, cocos_abi::kRequestSubmitCallA);
    const auto siteB = runtimeAddress(base, cocos_abi::kRequestSubmitCallB);
    if ((siteA & ~(pageSize - 1)) != (siteB & ~(pageSize - 1))) {
        return false;
    }

    void* thunkPage = mapNear(siteA, pageSize);
    if (thunkPage == MAP_FAILED) {
        return false;
    }
    auto* thunkBytes = static_cast<std::byte*>(thunkPage);
    writeThunk(thunkBytes, 0, reinterpret_cast<std::uintptr_t>(&submitHook));
    writeThunk(thunkBytes + 24, 1, reinterpret_cast<std::uintptr_t>(&submitHook));
    __builtin___clear_cache(
            reinterpret_cast<char*>(thunkPage),
            reinterpret_cast<char*>(thunkPage) + 48);
    if (mprotect(thunkPage, pageSize, PROT_READ | PROT_EXEC) != 0) {
        munmap(thunkPage, pageSize);
        return false;
    }

    const auto expectedA = *reinterpret_cast<const std::uint32_t*>(siteA);
    const auto expectedB = *reinterpret_cast<const std::uint32_t*>(siteB);
    const auto thunkA = reinterpret_cast<std::uintptr_t>(thunkPage);
    const auto thunkB = thunkA + 24;
    if (expectedA != cocos_abi::kRequestSubmitCallAInstruction
            || expectedB != cocos_abi::kRequestSubmitCallBInstruction
            || !isBranchReachable(siteA, thunkA)
            || !isBranchReachable(siteB, thunkB)) {
        munmap(thunkPage, pageSize);
        return false;
    }

    const auto codePage = reinterpret_cast<void*>(siteA & ~(pageSize - 1));
    if (mprotect(codePage, pageSize, PROT_READ | PROT_WRITE) != 0) {
        munmap(thunkPage, pageSize);
        return false;
    }
    *reinterpret_cast<std::uint32_t*>(siteA) = encodeBl(siteA, thunkA);
    *reinterpret_cast<std::uint32_t*>(siteB) = encodeBl(siteB, thunkB);
    __builtin___clear_cache(
            reinterpret_cast<char*>(codePage),
            reinterpret_cast<char*>(codePage) + pageSize);
    return mprotect(codePage, pageSize, PROT_READ | PROT_EXEC) == 0;
}

__attribute__((constructor)) void installGameApiHook() {
    // This bridge is loaded as a DT_NEEDED dependency of the pinned Cocos
    // library. Its constructor runs before the first RealDriver request.
    if (installHook()) {
        __android_log_print(
                ANDROID_LOG_INFO,
                "SAOCBBridge",
                "Pinned ARM64 GameAPI submit hook installed");
    } else {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "Pinned ARM64 submit sites did not match; no call sites were changed");
    }
}

}  // namespace
