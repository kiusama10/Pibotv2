#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 4 ]; then
  echo "Usage: $0 ORIGINAL_SPLITS_DIR PATCHED_BASE_APK PATCHED_ARM64_APK OUTPUT_DIR [KEYSTORE] [ALIAS]" >&2
  exit 2
fi

ORIGINAL_DIR=$1
PATCHED_BASE=$2
PATCHED_ARM64=$3
OUTPUT_DIR=$4
KEYSTORE=${5:-${SAOCB_KEYSTORE:-}}
ALIAS=${6:-${SAOCB_KEY_ALIAS:-saocb}}
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SDK=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}

if [ -z "$KEYSTORE" ]; then
  echo "Pass the keystore path as argument 5 or set SAOCB_KEYSTORE. Password is intentionally not accepted as an argument." >&2
  exit 2
fi

ZIPALIGN=${ZIPALIGN:-}
APKSIGNER=${APKSIGNER:-}
ADB=${ADB:-}
if [ -n "$SDK" ]; then
  [ -n "$ZIPALIGN" ] || ZIPALIGN=$(find "$SDK/build-tools" -type f -name zipalign | sort -V | tail -n1)
  [ -n "$APKSIGNER" ] || APKSIGNER=$(find "$SDK/build-tools" -type f -name apksigner | sort -V | tail -n1)
  [ -n "$ADB" ] || ADB=$(find "$SDK/platform-tools" -type f -name adb | head -n1)
fi
: "${ZIPALIGN:?Set ZIPALIGN or ANDROID_HOME}"
: "${APKSIGNER:?Set APKSIGNER or ANDROID_HOME}"

mkdir -p "$OUTPUT_DIR/staged" "$OUTPUT_DIR/signed"

# Expected complete backup set. The armv7 split is signed for archival
# consistency but is not installed by the arm64 install helper below.
NAMES=(
  base.apk
  split_config.arm64_v8a.apk
  split_config.armeabi_v7a.apk
  split_config.de.apk
  split_config.en.apk
  split_config.xxhdpi.apk
  split_InstallTimeAssetPack.apk
  split_InstallTimeAssetPack2.apk
  split_InstallTimeAssetPack3.apk
)

for name in "${NAMES[@]}"; do
  source="$ORIGINAL_DIR/$name"
  if [ "$name" = base.apk ]; then source="$PATCHED_BASE"; fi
  if [ "$name" = split_config.arm64_v8a.apk ]; then source="$PATCHED_ARM64"; fi
  test -f "$source" || { echo "Missing $source" >&2; exit 2; }
  unsigned="$OUTPUT_DIR/staged/$name"
  aligned="$OUTPUT_DIR/staged/${name%.apk}.aligned.apk"
  python3 "$ROOT/strip_apk_signatures.py" "$source" "$unsigned" >/dev/null
  "$ZIPALIGN" -f 4 "$unsigned" "$aligned"
  # apksigner prompts securely for the keystore password; do not put it on the command line.
  "$APKSIGNER" sign --ks "$KEYSTORE" --ks-key-alias "$ALIAS" \
    --out "$OUTPUT_DIR/signed/$name" "$aligned"
  "$APKSIGNER" verify --verbose --print-certs "$OUTPUT_DIR/signed/$name" >/dev/null
  echo "signed=$name"
done

python3 - "$OUTPUT_DIR/signed" <<'PY'
from pathlib import Path
import hashlib,sys
root=Path(sys.argv[1])
for p in sorted(root.glob('*.apk')):
    print(hashlib.sha256(p.read_bytes()).hexdigest(),p.name)
PY

cat <<MSG
All 9 APKs are signed with the same keystore.
For an ARM64 phone, install base + ARM64 + resource/asset splits; do NOT install the armeabi_v7a config split together with the ARM64 config split.
MSG

if [ -n "$ADB" ] && [ -x "$ADB" ]; then
  echo "ADB detected: $ADB"
  echo "Install command (ARM64):"
  printf '%q install-multiple -r ' "$ADB"
  for name in "${NAMES[@]}"; do
    [ "$name" = split_config.armeabi_v7a.apk ] && continue
    printf '%q ' "$OUTPUT_DIR/signed/$name"
  done
  echo
fi
