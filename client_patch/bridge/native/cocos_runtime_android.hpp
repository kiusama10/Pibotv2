#pragma once

#include "cocos_response_bridge.hpp"

namespace saocb {
namespace bridge {

// Returns nullptr unless the pinned ARM64 libcocos2dcpp.so is already loaded.
const CocosRuntime* loadedCocosRuntime();

}  // namespace bridge
}  // namespace saocb
