#!/usr/bin/env bash
set -euo pipefail
ADB=${ADB:-adb}
"$ADB" logcat -c
"$ADB" logcat -v time SAOCBBridge:I AndroidRuntime:E '*:S'
