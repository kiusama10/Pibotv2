#!/bin/sh
set -eu

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 BASE_APK ARM64_SPLIT_APK OUTPUT_DIR" >&2
  exit 2
fi

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
BASE_APK=$1
ARM64_SPLIT_APK=$2
OUTPUT_DIR=$3
ALIGN=${ZIPALIGN:-}
PATCHELF=${PATCHELF:-$(command -v patchelf || true)}
SDK=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}

if [ -z "$PATCHELF" ] || [ ! -x "$PATCHELF" ]; then
  echo "Set PATCHELF or install patchelf; the bridge must be loaded by libcocos2dcpp.so." >&2
  exit 2
fi
if [ -z "$ALIGN" ]; then
  if [ -z "$SDK" ] || [ ! -d "$SDK/build-tools" ]; then
    echo "Set ZIPALIGN or ANDROID_HOME to an Android SDK installation." >&2
    exit 2
  fi
  ALIGN=$(find "$SDK/build-tools" -mindepth 2 -maxdepth 2 \
    -type f -name zipalign | sort -V | tail -n 1)
fi
if [ -z "$ALIGN" ] || [ ! -x "$ALIGN" ]; then
  echo "No executable zipalign found; set ZIPALIGN explicitly." >&2
  exit 2
fi

ANDROID_NDK_HOME=${ANDROID_NDK_HOME:-${ANDROID_NDK_ROOT:-}} \
ANDROID_HOME=${ANDROID_HOME:-${ANDROID_SDK_ROOT:-}} \
  "$ROOT/build_bridge.sh"

mkdir -p "$OUTPUT_DIR"
python3 "$ROOT/package_unsigned_apks.py" \
  --base-apk "$BASE_APK" \
  --arm64-split-apk "$ARM64_SPLIT_APK" \
  --bridge-dex "$ROOT/build/dex/classes.dex" \
  --bridge-so "$ROOT/build/cmake-arm64-v8a/libsaocb_bridge.so" \
  --output-dir "$ROOT/build/un-aligned" \
  --patchelf "$PATCHELF"

"$ALIGN" -f 4 \
  "$ROOT/build/un-aligned/base.unsigned.apk" \
  "$OUTPUT_DIR/base.unsigned.apk"
"$ALIGN" -f 4 \
  "$ROOT/build/un-aligned/split_config.arm64_v8a.unsigned.apk" \
  "$OUTPUT_DIR/split_config.arm64_v8a.unsigned.apk"
printf 'Unsigned APKs written to %s\n' "$OUTPUT_DIR"
