#!/usr/bin/env python3
"""Importa asset packs originales de SAO Memory Defrag a un depósito Telegram.

No intenta interpretar datos propietarios a ciegas. Conserva archivos crudos,
extrae imágenes Telegram-compatibles y genera un índice SHA-256 reproducible.
"""
from __future__ import annotations
import argparse, hashlib, json, shutil, zipfile
from pathlib import Path

MEDIA_EXT={'.png','.jpg','.jpeg','.webp','.gif'}
DATA_NAMES={'character.bin','ui_text.bin','localization_info.bin'}

def sha256(p:Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('source',help='Carpeta que contiene split_InstallTimeAssetPack*.apk');ap.add_argument('--out',default='saocb_telegram/imported_assets');a=ap.parse_args()
    src=Path(a.source);out=Path(a.out);raw=out/'raw';media=out/'telegram_media';data=out/'data';
    for d in (raw,media,data):d.mkdir(parents=True,exist_ok=True)
    apks=sorted(src.glob('split_InstallTimeAssetPack*.apk'))
    if not apks:raise SystemExit('No encontré split_InstallTimeAssetPack*.apk en esa carpeta.')
    index=[]
    for apk in apks:
        pack=raw/apk.stem;pack.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(apk) as z:z.extractall(pack)
        for p in pack.rglob('*'):
            if not p.is_file():continue
            rel=p.relative_to(pack).as_posix();rec={'pack':apk.name,'path':rel,'size':p.stat().st_size,'sha256':sha256(p)};index.append(rec)
            if p.name in DATA_NAMES:
                dst=data/f'{apk.stem}__{p.name}';shutil.copy2(p,dst)
            if p.suffix.lower() in MEDIA_EXT:
                dst=media/apk.stem/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
    (out/'asset_index.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Importados {len(apks)} packs, {len(index)} archivos indexados.')
    print(f'Imágenes listas para Telegram: {sum(1 for x in index if Path(x["path"]).suffix.lower() in MEDIA_EXT)}')
    print(f'Datos crudos conservados en: {data}')
if __name__=='__main__':main()
