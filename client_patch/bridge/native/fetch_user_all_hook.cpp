#include "cocos_response_abi.hpp"
#include "fetch_user_all_url.hpp"

#include <android/log.h>
#include <jni.h>

#include <dlfcn.h>
#include <link.h>
#include <sys/mman.h>
#include <unistd.h>

#include <cstddef>
#include <cstdint>
#include <cstring>
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

bool isFetchUserAllOnStack(std::uintptr_t base) {
    auto* frame = reinterpret_cast<std::uintptr_t*>(__builtin_frame_address(0));
    for (int depth = 0; frame != nullptr && depth < 48; ++depth) {
        const std::uintptr_t caller = frame[1];
        if (caller >= base + cocos_abi::kFetchUserAllStart
                && caller < base + cocos_abi::kFetchUserAllEnd) {
            return true;
        }

        auto* next = reinterpret_cast<std::uintptr_t*>(frame[0]);
        const auto currentAddress = reinterpret_cast<std::uintptr_t>(frame);
        const auto nextAddress = reinterpret_cast<std::uintptr_t>(next);
        if (next == nullptr || nextAddress <= currentAddress
                || nextAddress - currentAddress > 1024u * 1024u) {
            break;
        }
        frame = next;
    }
    return false;
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

jclass findGameApiBridgeClass(JNIEnv* env) {
    if (env == nullptr) {
        return nullptr;
    }

    jclass bridge = env->FindClass(
            "com/bandainamcoent/saomdeu/GameApiBridge");
    if (bridge != nullptr && !env->ExceptionCheck()) {
        return bridge;
    }
    if (env->ExceptionCheck()) {
        env->ExceptionClear();
    }

    // Native-attached threads are not guaranteed to inherit the app class
    // loader. Resolve the Application's ClassLoader as a safe fallback.
    jclass activityThread = env->FindClass("android/app/ActivityThread");
    if (activityThread == nullptr || env->ExceptionCheck()) {
        if (env->ExceptionCheck()) env->ExceptionClear();
        return nullptr;
    }
    jmethodID currentApplication = env->GetStaticMethodID(
            activityThread,
            "currentApplication",
            "()Landroid/app/Application;");
    if (currentApplication == nullptr || env->ExceptionCheck()) {
        if (env->ExceptionCheck()) env->ExceptionClear();
        return nullptr;
    }
    jobject application = env->CallStaticObjectMethod(
            activityThread, currentApplication);
    if (application == nullptr || env->ExceptionCheck()) {
        if (env->ExceptionCheck()) env->ExceptionClear();
        return nullptr;
    }

    jclass contextClass = env->FindClass("android/content/Context");
    if (contextClass == nullptr || env->ExceptionCheck()) {
        if (env->ExceptionCheck()) env->ExceptionClear();
        return nullptr;
    }
    jmethodID getClassLoader = env->GetMethodID(
            contextClass,
            "getClassLoader",
            "()Ljava/lang/ClassLoader;");
    if (getClassLoader == nullptr || env->ExceptionCheck()) {
        if (env->ExceptionCheck()) env->ExceptionClear();
        return nullptr;
    }
    jobject classLoader = env->CallObjectMethod(application, getClassLoader);
    if (classLoader == nullptr || env->ExceptionCheck()) {
        if (env->ExceptionCheck()) env->ExceptionClear();
        return nullptr;
    }

    jclass classLoaderClass = env->FindClass("java/lang/ClassLoader");
    if (classLoaderClass == nullptr || env->ExceptionCheck()) {
        if (env->ExceptionCheck()) env->ExceptionClear();
        return nullptr;
    }
    jmethodID loadClass = env->GetMethodID(
            classLoaderClass,
            "loadClass",
            "(Ljava/lang/String;)Ljava/lang/Class;");
    if (loadClass == nullptr || env->ExceptionCheck()) {
        if (env->ExceptionCheck()) env->ExceptionClear();
        return nullptr;
    }
    jstring className = env->NewStringUTF(
            "com.bandainamcoent.saomdeu.GameApiBridge");
    if (className == nullptr || env->ExceptionCheck()) {
        if (env->ExceptionCheck()) env->ExceptionClear();
        return nullptr;
    }
    jobject loaded = env->CallObjectMethod(classLoader, loadClass, className);
    if (loaded == nullptr || env->ExceptionCheck()) {
        if (env->ExceptionCheck()) env->ExceptionClear();
        return nullptr;
    }
    return static_cast<jclass>(loaded);
}

bool callJavaFetchUserAll(
        const std::string& uid,
        void* httpClient,
        void* httpRequest) {
    if (uid.empty() || uid.size() > 128) {
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
    if (env->PushLocalFrame(16) == JNI_OK) {
        jclass bridge = findGameApiBridgeClass(env);
        if (bridge != nullptr) {
            jmethodID dispatch = env->GetStaticMethodID(
                    bridge,
                    "dispatchFetchUserAll",
                    "(Ljava/lang/String;JJ)Ljava/lang/String;");
            if (dispatch != nullptr && !env->ExceptionCheck()) {
                jstring javaUid = env->NewStringUTF(uid.c_str());
                if (javaUid != nullptr && !env->ExceptionCheck()) {
                    jobject requestId = env->CallStaticObjectMethod(
                            bridge,
                            dispatch,
                            javaUid,
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

    if (isFetchUserAllOnStack(base) && httpRequest != nullptr) {
        auto* requestBytes = static_cast<std::byte*>(httpRequest);
        std::string url;
        std::string uid;
        const bool urlOk = fetch_user_all::readPinnedLibcppString(
                requestBytes + cocos_abi::kHttpRequestUrlOffset, &url);
        const bool uidOk = urlOk
                && fetch_user_all::extractUidFromUserUrl(url, &uid);
        if (uidOk && callJavaFetchUserAll(uid, httpClient, httpRequest)) {
            __android_log_print(
                    ANDROID_LOG_INFO,
                    "SAOCBBridge",
                    "fetchUserAll dispatched through SAO-CB bridge uid=%s",
                    uid.c_str());
            return;
        }
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "fetchUserAll bridge dispatch failed (url=%d uid=%d); retaining original Cocos send",
                urlOk ? 1 : 0,
                uidOk ? 1 : 0);
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

__attribute__((constructor)) void installFetchUserAllHook() {
    // This bridge is loaded as a DT_NEEDED dependency of the pinned Cocos
    // library. Its constructor runs before the first RealDriver request.
    if (installHook()) {
        __android_log_print(
                ANDROID_LOG_INFO,
                "SAOCBBridge",
                "Pinned ARM64 fetchUserAll submit hook installed");
    } else {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "Pinned ARM64 submit sites did not match; no call sites were changed");
    }
}

}  // namespace
