#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>

namespace saocb {
namespace bridge {
namespace fetch_user_all {

// Pinned Android libc++ std::string reader for the exact SAO MD ARM64 build.
// Static disassembly of the request builder shows the classic little-endian
// libc++ layout: short strings store (size << 1) in byte 0 and chars at +1;
// long strings set bit 0 and store size at +8 and char* at +16.
inline bool readPinnedLibcppString(
        const void* object,
        std::string* output,
        std::size_t maxLength = 2048) noexcept {
    if (object == nullptr || output == nullptr) {
        return false;
    }

    const auto* bytes = static_cast<const std::uint8_t*>(object);
    const bool isLong = (bytes[0] & 1u) != 0;
    const char* data = nullptr;
    std::size_t size = 0;

    if (!isLong) {
        size = static_cast<std::size_t>(bytes[0] >> 1);
        // The pinned 64-bit libc++ short representation has 23 bytes total:
        // one size byte plus at most 22 chars and a terminator.
        if (size > 22) {
            return false;
        }
        data = reinterpret_cast<const char*>(bytes + 1);
    } else {
        std::memcpy(&size, bytes + 8, sizeof(size));
        std::memcpy(&data, bytes + 16, sizeof(data));
        if (data == nullptr) {
            return false;
        }
    }

    if (size == 0 || size > maxLength) {
        return false;
    }

    try {
        output->assign(data, size);
    } catch (...) {
        output->clear();
        return false;
    }
    return true;
}

inline bool isUidCharacter(char value) noexcept {
    return (value >= 'A' && value <= 'Z')
            || (value >= 'a' && value <= 'z')
            || (value >= '0' && value <= '9')
            || value == '.' || value == '_' || value == '~' || value == '-';
}

inline bool extractUidFromUserUrl(
        const std::string& url,
        std::string* uid) noexcept {
    if (uid == nullptr) {
        return false;
    }
    uid->clear();

    std::size_t route = url.rfind("/user/");
    std::size_t start = std::string::npos;
    if (route != std::string::npos) {
        start = route + 6;
    } else {
        route = url.rfind("user/");
        if (route != std::string::npos) {
            start = route + 5;
        }
    }
    if (start == std::string::npos || start >= url.size()) {
        return false;
    }

    std::size_t end = start;
    while (end < url.size()
            && url[end] != '/'
            && url[end] != '?'
            && url[end] != '#') {
        if (!isUidCharacter(url[end])) {
            return false;
        }
        ++end;
    }

    const std::size_t length = end - start;
    if (length == 0 || length > 128) {
        return false;
    }

    try {
        uid->assign(url.data() + start, length);
    } catch (...) {
        uid->clear();
        return false;
    }
    return true;
}

}  // namespace fetch_user_all
}  // namespace bridge
}  // namespace saocb
