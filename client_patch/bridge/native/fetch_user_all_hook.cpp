#include "cocos_response_abi.hpp"
#include "fetch_user_all_url.hpp"

#include <android/log.h>
#include <jni.h>

#include <atomic>
#include <cerrno>
#include <dlfcn.h>
#include <link.h>
#include <pthread.h>
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

std::atomic<std::uintptr_t> gCocosLibraryBase{0};

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
                const auto address = reinterpret_cast<std::uintptr_t>(fixed);
                if (isBranchReachable(target, address)) {
                    return fixed;
                }
                munmap(fixed, pageSize);
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

bool replaceCodePageWithAnonymousExec(
        std::uintptr_t codePageAddress,
        std::size_t pageSize,
        std::uintptr_t siteA,
        std::uintptr_t siteB,
        std::uintptr_t thunkA,
        std::uintptr_t thunkB) {
    auto* const codePage = reinterpret_cast<void*>(codePageAddress);
    const std::uintptr_t offsetA = siteA - codePageAddress;
    const std::uintptr_t offsetB = siteB - codePageAddress;

    if (offsetA > pageSize - sizeof(std::uint32_t)
            || offsetB > pageSize - sizeof(std::uint32_t)) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "submit offsets are outside Cocos code page");
        return false;
    }

    // Android/SELinux rejected execmod on the file-backed Cocos page.
    // Build an exact anonymous copy, patch it while RW, make it RX, then move
    // that already-executable anonymous mapping over the original virtual page.
    void* shadowPage = mmap(
            nullptr,
            pageSize,
            PROT_READ | PROT_WRITE,
            MAP_PRIVATE | MAP_ANONYMOUS,
            -1,
            0);
    if (shadowPage == MAP_FAILED) {
        const int error = errno;
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "anonymous Cocos shadow mmap failed errno=%d (%s)",
                error,
                std::strerror(error));
        return false;
    }

    std::memcpy(shadowPage, codePage, pageSize);

    auto* const shadowBytes = static_cast<std::byte*>(shadowPage);
    const std::uint32_t patchedA = encodeBl(siteA, thunkA);
    const std::uint32_t patchedB = encodeBl(siteB, thunkB);

    std::memcpy(
            shadowBytes + offsetA,
            &patchedA,
            sizeof(patchedA));
    std::memcpy(
            shadowBytes + offsetB,
            &patchedB,
            sizeof(patchedB));

    __builtin___clear_cache(
            reinterpret_cast<char*>(shadowPage),
            reinterpret_cast<char*>(shadowPage) + pageSize);

    std::uint32_t shadowA = 0;
    std::uint32_t shadowB = 0;
    std::memcpy(
            &shadowA,
            shadowBytes + offsetA,
            sizeof(shadowA));
    std::memcpy(
            &shadowB,
            shadowBytes + offsetB,
            sizeof(shadowB));

    if (shadowA != patchedA || shadowB != patchedB) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "anonymous Cocos shadow verification failed");
        munmap(shadowPage, pageSize);
        return false;
    }

    if (mprotect(shadowPage, pageSize, PROT_READ | PROT_EXEC) != 0) {
        const int error = errno;
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "anonymous Cocos shadow RX failed errno=%d (%s)",
                error,
                std::strerror(error));
        munmap(shadowPage, pageSize);
        return false;
    }

    __android_log_print(
            ANDROID_LOG_INFO,
            "SAOCBBridge",
            "anonymous Cocos shadow ready RX page=%p",
            shadowPage);

    errno = 0;
    void* moved = mremap(
            shadowPage,
            pageSize,
            pageSize,
            MREMAP_MAYMOVE | MREMAP_FIXED,
            codePage);
    if (moved == MAP_FAILED) {
        const int error = errno;
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "mremap anonymous Cocos page failed errno=%d (%s); original page untouched",
                error,
                std::strerror(error));
        munmap(shadowPage, pageSize);
        return false;
    }

    __builtin___clear_cache(
            reinterpret_cast<char*>(codePage),
            reinterpret_cast<char*>(codePage) + pageSize);

    const auto installedA =
            *reinterpret_cast<const std::uint32_t*>(siteA);
    const auto installedB =
            *reinterpret_cast<const std::uint32_t*>(siteB);

    __android_log_print(
            ANDROID_LOG_INFO,
            "SAOCBBridge",
            "anonymous Cocos page installed page=%p A=0x%08x B=0x%08x",
            codePage,
            static_cast<unsigned int>(installedA),
            static_cast<unsigned int>(installedB));

    if (installedA != patchedA || installedB != patchedB) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "installed anonymous Cocos page verification failed");
        return false;
    }

    return true;
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
    const std::uintptr_t base =
            gCocosLibraryBase.load(std::memory_order_acquire);
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

bool installHook(std::uintptr_t base) {
    const long pageSizeResult = sysconf(_SC_PAGESIZE);
    if (base == 0) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "installHook called with cocos base=0");
        return false;
    }
    if (pageSizeResult <= 0) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "sysconf(_SC_PAGESIZE) failed value=%ld",
                pageSizeResult);
        return false;
    }

    const auto pageSize = static_cast<std::size_t>(pageSizeResult);
    const auto siteA = runtimeAddress(base, cocos_abi::kRequestSubmitCallA);
    const auto siteB = runtimeAddress(base, cocos_abi::kRequestSubmitCallB);

    __android_log_print(
            ANDROID_LOG_INFO,
            "SAOCBBridge",
            "cocos ready base=%p page=%zu siteA=%p siteB=%p",
            reinterpret_cast<void*>(base),
            pageSize,
            reinterpret_cast<void*>(siteA),
            reinterpret_cast<void*>(siteB));

    if ((siteA & ~(pageSize - 1)) != (siteB & ~(pageSize - 1))) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "submit call sites are on different pages");
        return false;
    }

    const auto actualA = *reinterpret_cast<const std::uint32_t*>(siteA);
    const auto actualB = *reinterpret_cast<const std::uint32_t*>(siteB);
    __android_log_print(
            ANDROID_LOG_INFO,
            "SAOCBBridge",
            "submit words A=0x%08x expected=0x%08x B=0x%08x expected=0x%08x",
            static_cast<unsigned int>(actualA),
            static_cast<unsigned int>(cocos_abi::kRequestSubmitCallAInstruction),
            static_cast<unsigned int>(actualB),
            static_cast<unsigned int>(cocos_abi::kRequestSubmitCallBInstruction));

    if (actualA != cocos_abi::kRequestSubmitCallAInstruction
            || actualB != cocos_abi::kRequestSubmitCallBInstruction) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "submit instruction mismatch; no call sites were changed");
        return false;
    }

    void* thunkPage = mapNear(siteA, pageSize);
    if (thunkPage == MAP_FAILED) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "mapNear failed; no call sites were changed");
        return false;
    }

    auto* thunkBytes = static_cast<std::byte*>(thunkPage);
    writeThunk(thunkBytes, 0, reinterpret_cast<std::uintptr_t>(&submitHook));
    writeThunk(thunkBytes + 24, 1, reinterpret_cast<std::uintptr_t>(&submitHook));
    __builtin___clear_cache(
            reinterpret_cast<char*>(thunkPage),
            reinterpret_cast<char*>(thunkPage) + 48);

    const auto thunkA = reinterpret_cast<std::uintptr_t>(thunkPage);
    const auto thunkB = thunkA + 24;
    const bool reachableA = isBranchReachable(siteA, thunkA);
    const bool reachableB = isBranchReachable(siteB, thunkB);
    __android_log_print(
            ANDROID_LOG_INFO,
            "SAOCBBridge",
            "thunk page=%p reachableA=%d reachableB=%d",
            thunkPage,
            reachableA ? 1 : 0,
            reachableB ? 1 : 0);

    if (!reachableA || !reachableB) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "thunk is outside ARM64 BL range; no call sites were changed");
        munmap(thunkPage, pageSize);
        return false;
    }

    if (mprotect(thunkPage, pageSize, PROT_READ | PROT_EXEC) != 0) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "mprotect thunk RX failed; no call sites were changed");
        munmap(thunkPage, pageSize);
        return false;
    }

    const auto codePageAddress =
            siteA & ~(static_cast<std::uintptr_t>(pageSize) - 1);

    // Publish before the final page replacement. Once the two BL instructions
    // become live, submitHook already has the correct Cocos base.
    gCocosLibraryBase.store(base, std::memory_order_release);

    if (!replaceCodePageWithAnonymousExec(
                codePageAddress,
                pageSize,
                siteA,
                siteB,
                thunkA,
                thunkB)) {
        gCocosLibraryBase.store(0, std::memory_order_release);
        munmap(thunkPage, pageSize);
        return false;
    }

    __android_log_print(
            ANDROID_LOG_INFO,
            "SAOCBBridge",
            "Pinned ARM64 fetchUserAll submit hook installed");
    return true;
}

void* installHookWorker(void*) {
    constexpr int kMaxAttempts = 200;
    constexpr unsigned int kRetryDelayUs = 10000;

    __android_log_print(
            ANDROID_LOG_INFO,
            "SAOCBBridge",
            "deferred hook worker started; waiting for libcocos2dcpp.so");

    for (int attempt = 1; attempt <= kMaxAttempts; ++attempt) {
        const std::uintptr_t base = cocosBase();
        if (base != 0) {
            __android_log_print(
                    ANDROID_LOG_INFO,
                    "SAOCBBridge",
                    "libcocos2dcpp.so visible to bridge on attempt=%d base=%p",
                    attempt,
                    reinterpret_cast<void*>(base));
            if (!installHook(base)) {
                __android_log_print(
                        ANDROID_LOG_ERROR,
                        "SAOCBBridge",
                        "deferred fetchUserAll hook installation failed");
            }
            return nullptr;
        }
        usleep(kRetryDelayUs);
    }

    __android_log_print(
            ANDROID_LOG_ERROR,
            "SAOCBBridge",
            "timed out waiting for libcocos2dcpp.so; hook not installed");
    return nullptr;
}

__attribute__((constructor)) void installFetchUserAllHook() {
    // libsaocb_bridge.so is a DT_NEEDED dependency of libcocos2dcpp.so. A
    // dependency constructor can run while the parent DSO is still being loaded,
    // so patch Cocos from a detached worker after the linker finishes that load.
    pthread_t worker{};
    const int createResult = pthread_create(
            &worker,
            nullptr,
            &installHookWorker,
            nullptr);
    if (createResult != 0) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "SAOCBBridge",
                "pthread_create for deferred hook failed rc=%d",
                createResult);
        return;
    }
    pthread_detach(worker);
}

}  // namespace
