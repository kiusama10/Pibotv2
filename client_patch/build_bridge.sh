#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
NDK=${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-}}
SDK=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}
OUT="$ROOT/build"

if [ -z "$NDK" ] || [ ! -f "$NDK/build/cmake/android.toolchain.cmake" ]; then
  echo "Set ANDROID_NDK_HOME to an installed Android NDK." >&2
  exit 2
fi
if [ -z "$SDK" ] || [ ! -d "$SDK/platforms" ] || [ ! -d "$SDK/build-tools" ]; then
  echo "Set ANDROID_HOME or ANDROID_SDK_ROOT to an installed Android SDK." >&2
  exit 2
fi
command -v cmake >/dev/null 2>&1 || {
  echo "cmake is required to build the native bridge." >&2
  exit 2
}
command -v javac >/dev/null 2>&1 || {
  echo "javac is required to compile GameApiBridge.java." >&2
  exit 2
}
command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required to select the SDK build tools." >&2
  exit 2
}

ANDROID_JAR=${ANDROID_JAR:-}
if [ -z "$ANDROID_JAR" ]; then
  ANDROID_JAR=$(find "$SDK/platforms" -mindepth 2 -maxdepth 2 \
    -type f -name android.jar | sort -V | tail -n 1)
fi
if [ -z "$ANDROID_JAR" ] || [ ! -f "$ANDROID_JAR" ]; then
  echo "No Android platform android.jar found; set ANDROID_JAR explicitly." >&2
  exit 2
fi

D8=${D8:-}
if [ -z "$D8" ]; then
  D8=$(find "$SDK/build-tools" -mindepth 2 -maxdepth 2 \
    -type f -name d8 | sort -V | tail -n 1)
fi
if [ -z "$D8" ] || [ ! -x "$D8" ]; then
  echo "No executable d8 found; set D8 to the Android SDK build-tools d8." >&2
  exit 2
fi

cmake -S "$ROOT/bridge/native" -B "$OUT/cmake-arm64-v8a" \
  -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
  -DANDROID_ABI=arm64-v8a \
  -DANDROID_PLATFORM=android-23 \
  -DANDROID_STL=c++_static \
  -DCMAKE_BUILD_TYPE=Release
cmake --build "$OUT/cmake-arm64-v8a" --target saocb_bridge --parallel

mkdir -p "$OUT/classes" "$OUT/dex"
javac -source 8 -target 8 -bootclasspath "$ANDROID_JAR" \
  -d "$OUT/classes" "$ROOT/bridge/android/GameApiBridge.java"
find "$OUT/classes" -type f -name '*.class' -print0 \
  | xargs -0 "$D8" --min-api 23 --lib "$ANDROID_JAR" --output "$OUT/dex"

test -f "$OUT/cmake-arm64-v8a/libsaocb_bridge.so"
test -f "$OUT/dex/classes.dex"
printf 'Native bridge: %s\n' "$OUT/cmake-arm64-v8a/libsaocb_bridge.so"
printf 'Java bridge DEX: %s\n' "$OUT/dex/classes.dex"
