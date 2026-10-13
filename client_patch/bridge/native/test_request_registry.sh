#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM

c++ -std=c++17 -Wall -Wextra -Werror -pthread \
  -I"$root" \
  "$root/request_registry.cpp" \
  "$root/test_request_registry.cpp" \
  -o "$tmp/request_registry_test"
"$tmp/request_registry_test"
printf '%s\n' "request_registry_test: PASS"

c++ -std=c++17 -Wall -Wextra -Werror -pthread \
  -I"$root" \
  "$root/request_registry.cpp" \
  "$root/cocos_response_bridge.cpp" \
  "$root/test_cocos_response_bridge.cpp" \
  -o "$tmp/cocos_response_bridge_test"
"$tmp/cocos_response_bridge_test"
printf '%s\n' "cocos_response_bridge_test: PASS"
