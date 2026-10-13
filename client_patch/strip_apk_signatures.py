#!/usr/bin/env python3
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def is_v1_signature(name: str) -> bool:
    upper=name.upper()
    return upper.startswith('META-INF/') and upper.endswith(('.SF','.RSA','.DSA','.EC','MANIFEST.MF'))


def rewrite(source: Path, output: Path) -> None:
    with zipfile.ZipFile(source,'r') as src, zipfile.ZipFile(output,'w') as dst:
        dst.comment=src.comment
        for item in src.infolist():
            if is_v1_signature(item.filename):
                continue
            dst.writestr(item,src.read(item.filename))
    with zipfile.ZipFile(output,'r') as check:
        bad=check.testzip()
        if bad:
            raise RuntimeError(f'corrupt output at {bad}')


def main() -> None:
    ap=argparse.ArgumentParser(description='Rewrite APK ZIP to remove old signing blocks/V1 signature files before re-signing.')
    ap.add_argument('source',type=Path)
    ap.add_argument('output',type=Path)
    args=ap.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    rewrite(args.source,args.output)
    print(args.output)

if __name__=='__main__':
    main()
