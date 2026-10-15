#pragma once

#include <string_view>

namespace saocb {
namespace bridge {

enum class SubmitRoute {
    kBridge,
    kOriginalCocos,
    kFailClosed,
};

inline bool isPinnedGameApiUrl(std::string_view url) noexcept {
    const std::size_t scheme = url.find("://");
    if (scheme == std::string_view::npos || scheme == 0) {
        return false;
    }

    const std::size_t authorityStart = scheme + 3;
    const std::size_t authorityEnd = url.find_first_of("/?#", authorityStart);
    const std::string_view authority = url.substr(
            authorityStart,
            authorityEnd == std::string_view::npos
                    ? std::string_view::npos
                    : authorityEnd - authorityStart);
    if (authority.empty()) {
        return false;
    }

    const std::size_t userInfo = authority.rfind('@');
    const std::string_view hostPort = userInfo == std::string_view::npos
            ? authority
            : authority.substr(userInfo + 1);
    const std::size_t port = hostPort.find(':');
    std::string_view host = hostPort.substr(0, port);
    if (!host.empty() && host.back() == '.') {
        host.remove_suffix(1);
    }
    constexpr std::string_view pinnedHost = "api-defrag-eu.wrightflyer.net";
    if (host.size() != pinnedHost.size()) {
        return false;
    }
    for (std::size_t index = 0; index < host.size(); ++index) {
        char value = host[index];
        if (value >= 'A' && value <= 'Z') {
            value = static_cast<char>(value - 'A' + 'a');
        }
        if (value != pinnedHost[index]) {
            return false;
        }
    }
    return true;
}

inline std::string_view gameApiRouteForLog(std::string_view url) noexcept {
    const std::size_t scheme = url.find("://");
    if (scheme == std::string_view::npos || scheme == 0) {
        return "<unparsed>";
    }
    const std::size_t authorityStart = scheme + 3;
    const std::size_t pathStart = url.find('/', authorityStart);
    if (pathStart == std::string_view::npos) {
        return "/";
    }
    const std::size_t pathEnd = url.find_first_of("?#", pathStart);
    std::string_view path = url.substr(
            pathStart,
            pathEnd == std::string_view::npos
                    ? std::string_view::npos
                    : pathEnd - pathStart);
    constexpr std::string_view userPrefix = "/api/user/";
    if (path.size() > userPrefix.size()
            && path.substr(0, userPrefix.size()) == userPrefix
            && path.substr(userPrefix.size()) != "register") {
        return "/api/user/{uid}";
    }
    if (path.size() > 160) {
        path = path.substr(0, 160);
    }
    return path;
}

inline SubmitRoute classifySubmitRoute(
        bool requestUrlReadable,
        std::string_view url) noexcept {
    if (!requestUrlReadable) {
        return SubmitRoute::kFailClosed;
    }
    return isPinnedGameApiUrl(url)
            ? SubmitRoute::kBridge
            : SubmitRoute::kOriginalCocos;
}

inline bool shouldUseOriginalCocosTransport(SubmitRoute route) noexcept {
    return route == SubmitRoute::kOriginalCocos;
}

}  // namespace bridge
}  // namespace saocb
