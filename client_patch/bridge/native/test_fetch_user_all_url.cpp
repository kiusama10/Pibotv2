#include "fetch_user_all_url.hpp"

#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <string>

using saocb::bridge::fetch_user_all::extractUidFromUserUrl;
using saocb::bridge::fetch_user_all::readPinnedLibcppString;

int main() {
    {
        std::uint8_t raw[24] = {};
        const char* text = "user/kiu";
        const std::size_t len = std::strlen(text);
        raw[0] = static_cast<std::uint8_t>(len << 1);
        std::memcpy(raw + 1, text, len);
        std::string value;
        assert(readPinnedLibcppString(raw, &value));
        assert(value == text);
        std::string uid;
        assert(extractUidFromUserUrl(value, &uid));
        assert(uid == "kiu");
    }
    {
        const std::string text =
                "https://pibotv2-1.onrender.com/api/user/r4_ffaea3d5a80d92713249fb2b?x=1";
        std::uint8_t raw[24] = {};
        raw[0] = 1;  // long-string marker in the pinned libc++ layout
        const std::size_t len = text.size();
        const char* pointer = text.data();
        std::memcpy(raw + 8, &len, sizeof(len));
        std::memcpy(raw + 16, &pointer, sizeof(pointer));
        std::string value;
        assert(readPinnedLibcppString(raw, &value));
        assert(value == text);
        std::string uid;
        assert(extractUidFromUserUrl(value, &uid));
        assert(uid == "r4_ffaea3d5a80d92713249fb2b");
    }
    {
        std::string uid;
        assert(!extractUidFromUserUrl("https://example/api/quest/1", &uid));
        assert(!extractUidFromUserUrl("https://example/api/user/bad uid", &uid));
        assert(!extractUidFromUserUrl("https://example/api/user/", &uid));
    }
    std::cout << "fetch_user_all_url_test: PASS\n";
    return 0;
}
