#include "request_registry.hpp"
#include "cocos_response_bridge.hpp"
#include "cocos_runtime_android.hpp"

#include <jni.h>

#include <cstdint>
#include <string>

namespace {

void appendUtf8(std::string& output, std::uint32_t codePoint) {
    if (codePoint <= 0x7f) {
        output.push_back(static_cast<char>(codePoint));
    } else if (codePoint <= 0x7ff) {
        output.push_back(static_cast<char>(0xc0 | (codePoint >> 6)));
        output.push_back(static_cast<char>(0x80 | (codePoint & 0x3f)));
    } else if (codePoint <= 0xffff) {
        output.push_back(static_cast<char>(0xe0 | (codePoint >> 12)));
        output.push_back(static_cast<char>(0x80 | ((codePoint >> 6) & 0x3f)));
        output.push_back(static_cast<char>(0x80 | (codePoint & 0x3f)));
    } else {
        output.push_back(static_cast<char>(0xf0 | (codePoint >> 18)));
        output.push_back(static_cast<char>(0x80 | ((codePoint >> 12) & 0x3f)));
        output.push_back(static_cast<char>(0x80 | ((codePoint >> 6) & 0x3f)));
        output.push_back(static_cast<char>(0x80 | (codePoint & 0x3f)));
    }
}

std::string fromJavaString(JNIEnv* env, jstring value) {
    if (value == nullptr) {
        return std::string();
    }
    const jsize length = env->GetStringLength(value);
    const jchar* chars = env->GetStringChars(value, nullptr);
    if (chars == nullptr) {
        return std::string();
    }

    std::string output;
    output.reserve(static_cast<std::size_t>(length) * 3);
    for (jsize index = 0; index < length; ++index) {
        std::uint32_t codePoint = chars[index];
        if (codePoint >= 0xd800 && codePoint <= 0xdbff
                && index + 1 < length
                && chars[index + 1] >= 0xdc00
                && chars[index + 1] <= 0xdfff) {
            codePoint = 0x10000
                    + ((codePoint - 0xd800) << 10)
                    + (chars[++index] - 0xdc00);
        } else if (codePoint >= 0xd800 && codePoint <= 0xdfff) {
            codePoint = 0xfffd;
        }
        appendUtf8(output, codePoint);
    }
    env->ReleaseStringChars(value, chars);
    return output;
}

}  // namespace

extern "C" JNIEXPORT jboolean JNICALL
Java_com_bandainamcoent_saomdeu_GameApiBridge_nativeRegisterResponse(
        JNIEnv* env,
        jclass,
        jstring requestId,
        jlong clientPointer,
        jlong requestPointer) {
    try {
        const std::string id = fromJavaString(env, requestId);
        const auto* runtime = saocb::bridge::loadedCocosRuntime();
        if (runtime == nullptr || clientPointer == 0 || requestPointer == 0) {
            return JNI_FALSE;
        }
        auto* client = reinterpret_cast<cocos2d::network::HttpClient*>(
                static_cast<std::uintptr_t>(clientPointer));
        void* request = reinterpret_cast<void*>(
                static_cast<std::uintptr_t>(requestPointer));
        return saocb::bridge::registerCocosResponse(
                       saocb::bridge::globalRequestRegistry(),
                       id,
                       client,
                       request,
                       *runtime)
                ? JNI_TRUE
                : JNI_FALSE;
    } catch (...) {
        return JNI_FALSE;
    }
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_bandainamcoent_saomdeu_GameApiBridge_nativeOnResponse(
        JNIEnv* env,
        jclass,
        jstring requestId,
        jint httpStatus,
        jstring responseEnvelope) {
    try {
        const std::string id = fromJavaString(env, requestId);
        const std::string body = fromJavaString(env, responseEnvelope);
        return saocb::bridge::globalRequestRegistry().complete(
                       id, static_cast<int>(httpStatus), body)
                ? JNI_TRUE
                : JNI_FALSE;
    } catch (...) {
        // Never allow a C++ exception to cross the JNI boundary.
        return JNI_FALSE;
    }
}
