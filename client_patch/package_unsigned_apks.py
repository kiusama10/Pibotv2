#!/usr/bin/env python3
"""Add the bridge payload to the original base and ARM64 split APKs."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

EXPECTED_ARM64_LIBRARY_SHA256 = (
    "1f8407eb34b857828f028b293aaf49c8597ea2a5a638982bac96648b2cc49170"
)
ARM64_LIBRARY_MEMBER = "lib/arm64-v8a/libcocos2dcpp.so"
BRIDGE_LIBRARY_MEMBER = "lib/arm64-v8a/libsaocb_bridge.so"
BRIDGE_LIBRARY_NEEDED = "libsaocb_bridge.so"


def without_v1_signature(name: str) -> bool:
    upper = name.upper()
    if not upper.startswith("META-INF/"):
        return False
    return upper.endswith(
        (".SF", ".RSA", ".DSA", ".EC", "MANIFEST.MF")
    )


def next_dex_name(names: set[str]) -> str:
    occupied = {
        int(match.group(1) or "1")
        for name in names
        if (match := re.fullmatch(r"classes(\d*)\.dex", name))
    }
    index = 1
    while index in occupied:
        index += 1
    return "classes.dex" if index == 1 else f"classes{index}.dex"


def rewrite_apk(
    source_path: Path,
    output_path: Path,
    additions: dict[str, tuple[bytes, int]],
    replacements: dict[str, bytes] | None = None,
) -> None:
    replacements = replacements or {}
    with zipfile.ZipFile(source_path, "r") as source:
        existing = {item.filename for item in source.infolist()}
        collisions = existing.intersection(additions)
        if collisions:
            raise ValueError(
                "Refusing to overwrite existing APK members: "
                + ", ".join(sorted(collisions))
            )
        missing_replacements = set(replacements).difference(existing)
        if missing_replacements:
            raise ValueError(
                "Cannot replace missing APK members: "
                + ", ".join(sorted(missing_replacements))
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_path, "w") as output:
            output.comment = source.comment
            for item in source.infolist():
                if without_v1_signature(item.filename):
                    continue
                output.writestr(
                    item,
                    replacements[item.filename]
                    if item.filename in replacements
                    else source.read(item.filename),
                )
            for name, (data, compression) in additions.items():
                output.writestr(name, data, compress_type=compression)

    with zipfile.ZipFile(output_path, "r") as output:
        corrupt_member = output.testzip()
        if corrupt_member is not None:
            output_path.unlink(missing_ok=True)
            raise ValueError(f"Output APK failed ZIP verification at {corrupt_member}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-apk", required=True, type=Path)
    parser.add_argument("--arm64-split-apk", required=True, type=Path)
    parser.add_argument("--bridge-dex", required=True, type=Path)
    parser.add_argument("--bridge-so", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--patchelf",
        default=shutil.which("patchelf"),
        help="patchelf executable (or set PATCHELF); required to load the hook.",
    )
    args = parser.parse_args()

    for path in (
        args.base_apk,
        args.arm64_split_apk,
        args.bridge_dex,
        args.bridge_so,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    with zipfile.ZipFile(args.arm64_split_apk, "r") as split:
        try:
            library = split.read(ARM64_LIBRARY_MEMBER)
        except KeyError as error:
            raise ValueError(
                f"The split does not contain {ARM64_LIBRARY_MEMBER}"
            ) from error
    digest = hashlib.sha256(library).hexdigest()
    if digest != EXPECTED_ARM64_LIBRARY_SHA256:
        raise ValueError(
            "Refusing to apply ARM64-only offsets to an unknown game library: "
            f"{digest}"
        )
    if not args.patchelf:
        raise RuntimeError(
            "patchelf is required to add libsaocb_bridge.so as a dependency of "
            "libcocos2dcpp.so; set PATCHELF or install patchelf."
        )

    with zipfile.ZipFile(args.base_apk, "r") as base:
        dex_member = next_dex_name({item.filename for item in base.infolist()})

    args.output_dir.mkdir(parents=True, exist_ok=True)
    base_output = args.output_dir / "base.unsigned.apk"
    split_output = args.output_dir / "split_config.arm64_v8a.unsigned.apk"
    with tempfile.TemporaryDirectory(prefix="saocb-patchelf-") as temporary:
        patched_library = Path(temporary) / "libcocos2dcpp.so"
        patched_library.write_bytes(library)
        needed = subprocess.run(
            [args.patchelf, "--print-needed", str(patched_library)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        if BRIDGE_LIBRARY_NEEDED not in needed:
            subprocess.run(
                [
                    args.patchelf,
                    "--add-needed",
                    BRIDGE_LIBRARY_NEEDED,
                    str(patched_library),
                ],
                check=True,
            )
        confirmed_needed = subprocess.run(
            [args.patchelf, "--print-needed", str(patched_library)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        if BRIDGE_LIBRARY_NEEDED not in confirmed_needed:
            raise RuntimeError("patchelf did not add the bridge DT_NEEDED entry.")
        patched_bytes = patched_library.read_bytes()

    rewrite_apk(
        args.base_apk,
        base_output,
        {
            dex_member: (
                args.bridge_dex.read_bytes(),
                zipfile.ZIP_DEFLATED,
            )
        },
    )
    rewrite_apk(
        args.arm64_split_apk,
        split_output,
        {
            BRIDGE_LIBRARY_MEMBER: (
                args.bridge_so.read_bytes(),
                zipfile.ZIP_STORED,
            )
        },
        replacements={ARM64_LIBRARY_MEMBER: patched_bytes},
    )
    print(f"base_dex_member={dex_member}")
    print(f"base_apk={base_output}")
    print(f"arm64_split_apk={split_output}")
    print("signing=unsigned")
    print(f"original_libcocos_sha256={digest}")
    print(f"hooked_libcocos_sha256={hashlib.sha256(patched_bytes).hexdigest()}")
    print("hook=DT_NEEDED loads the bridge; its constructor patches the pinned ARM64 submit sites")


if __name__ == "__main__":
    main()
