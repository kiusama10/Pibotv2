# ARM64 client bridge patch status

## Verified target

- Base APK: `com.bandainamcoent.saomdeu`, version `3.0.2` / versionCode `555`.
- ARM64 split library: `lib/arm64-v8a/libcocos2dcpp.so`, SHA-256
  `1f8407eb34b857828f028b293aaf49c8597ea2a5a638982bac96648b2cc49170`.
- `RealDriver::fetchUserAll`: virtual/file offset `0x12D9834`, unwind range
  `0x12D9834..0x12D9E30`; vtable slot 44.
- Success adapter `RealDriver::fetchUserAll::$_33`: virtual/file offset
  `0x1359184`, unwind range `0x1359184..0x135A258`.
- Success callable ABI:
  `void(HttpClient*, const unordered_map<string, cocos2d::Value>&, ResponseValue)`.
  Failure adapter `$_34` takes
  `void(HttpClient*, ResponseValue, string)`. The public fetch callback takes
  `void(const BaseDriver::UserAllData&, bool, string)`.
- None of those callbacks carries a request ID. The existing
  `AppActivity.onServiceMessage(int, int, String)` is not a substitute: its
  integer arguments are already used by the security-check Messenger.
- Do not modify the existing V4 bootstrap/save code or route gameplay through
  `AppActivity.sendMessage`.

See `../FINDINGS.md` for the parser fields, the verified callback chain, and
the limits of the native hook verification.

## Implemented response bridge

- `bridge/android/GameApiBridge.java` performs asynchronous POSTs of a supplied
  `/api/v4/dispatch` envelope. It validates that the response echoes the same
  `request_id`, rejects duplicate in-flight IDs, applies a deadline, and sends
  one completion to JNI for success, HTTP error, timeout, cancellation, or
  transport failure.
- `bridge/native/jni_bridge.cpp` provides JNI entry points to register the
  original response callback and complete a request by ID.
- `bridge/native/request_registry.*` stores native callbacks under the ID and
  removes each entry before invoking it, so late/duplicate replies do not call
  it twice.
- `bridge/native/cocos_response_bridge.*` copies the original typed
  `HttpRequest::responseCallback` at `+0x70`, retains the request while the
  response is pending, constructs the response through the pinned Cocos
  constructor using the real request pointer, and delivers it on the Cocos
  scheduler. The copied request callback wrapper calls
  `GameApiHelper::onHttpRequestCallBack` and its original response parser, so
  the bridge never fabricates a `ValueMap` or constructs `ResponseValue`.
- The Cocos offsets and callback field are pinned to the library SHA-256 above.
  The original callback copy invokes the actual `std::function` object; it
  never casts or calls `0x1359184` directly.

`bridge/native/fetch_user_all_hook.cpp` adds the ARM64 call-site patch. It
replaces only the two pinned Cocos submit calls; a frame-chain check forwards
all other requests to their original Cocos send functions. A matched
The native hook reads the verified URL std::string at `HttpRequest+0x10`,
extracts the UID from the original `user/{uid}` route, and passes the live
`HttpClient*`/`HttpRequest*` to Java. It deliberately does not parse the
retail request body. The Java bridge builds:

- `route`: `user/{x_uid}`
- `method`: `POST` (the SAO-CB bridge contract only)
- `game_user`: the original request's `x_uid`
- `payload`: exactly `x_uid`, `sub_character`, `is_search`, `is_dungeon`, and
  `is_sortie`, with the four numeric flags set to zero

`dispatchNative` adds `request_id`; it is not taken from the original callback.
The dispatcher forwards to the aggregate API's `POST /api/user/{uid}` and
returns its full JSON response in `data`. The copied Cocos callback continues
through the original `HttpResponse` → `GameApiHelper` parser path. No V4
bootstrap/save implementation or `$_33` callback address is patched or called.

The packaging script adds `libsaocb_bridge.so` as a `DT_NEEDED` dependency of
the pinned Cocos library so the hook constructor runs. It also checks the
original library hash before patching. This source-level hook and the host
bridge tests are in place, but Android compilation, APK construction, and
in-game request/parser execution remain unverified in this environment.

## Reproduce the bridge tests

Inspect the original DEX and native offsets:

```sh
uv run --project . python tools/inspect_apk.py \
  .local/conversation-workspace/files/attached_assets/base_1791852701558.apk \
  .local/conversation-workspace/files/attached_assets/split_config.arm64_v8a_1791852701557.apk
```

Verify the callback RTTI and exact library hash:

```sh
uv run --project . python tools/verify_fetch_user_all_abi.py \
  .local/conversation-workspace/files/attached_assets/split_config.arm64_v8a_1791852701557.apk
```

Run the host-side request-ID registry tests:

```sh
sh client_patch/bridge/native/test_request_registry.sh
```

The script prints separate PASS lines for the request registry and Cocos
response bridge tests. It tests the original callback-copy/scheduling and
request-reference lifecycle against a fake runtime; it cannot execute the
retail parser in the game process.

## Rebuild the bridge payload and unsigned APKs externally

The current environment has no Java, CMake, Android SDK/NDK, `zipalign`, or
`patchelf`, so the APK rebuild cannot run here. On a machine with an Android
SDK, NDK, CMake, Python 3, `patchelf`, and `zipalign`, run:

```sh
ANDROID_NDK_HOME=/path/to/android-ndk \
ANDROID_HOME=/path/to/android-sdk \
PATCHELF=/path/to/patchelf \
sh client_patch/rebuild_unsigned_apks.sh \
  base.apk \
  split_config.arm64_v8a.apk \
  ./unsigned-output
```

`build_bridge.sh` compiles `libsaocb_bridge.so` for `arm64-v8a` and converts
`GameApiBridge.java` to DEX. The packager inserts that DEX into the next free
`classesN.dex` slot in the base APK, adds the `DT_NEEDED` entry to
`libcocos2dcpp.so`, inserts the bridge library into the ARM64 split, checks the
original library SHA-256, strips stale V1 signatures, rebuilds the ZIPs, and
aligns both output APKs. It writes
`base.unsigned.apk` and `split_config.arm64_v8a.unsigned.apk`; it does not sign
them.

The APK outputs are unsigned. The script prints the SHA-256 of the patched
`libcocos2dcpp.so`; signing, installation, and in-game validation are not
performed.

## Verification completed

- `uv run --project . python tools/verify_fetch_user_all_abi.py <arm64-split>`
  — PASS; split/library hash and both RTTI callback signatures match.
- `sh client_patch/bridge/native/test_request_registry.sh` — PASS; duplicate
  registration, one-shot completion, cancellation, concurrent completion,
  original callback copy, Cocos-thread delivery, and retained-request lifetime
  covered.
- `uv run --project . python -m pytest -q` — PASS, 8 tests.
- `tools/inspect_apk.py` was run against the attached base and ARM64 split and
  confirmed the ELF offsets/FDE ranges listed above.
- Java/JNI Android build and APK round-trip checks remain pending because the
  Android SDK/NDK, `patchelf`, and `zipalign` are not available in this runtime.
