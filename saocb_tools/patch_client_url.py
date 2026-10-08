from pathlib import Path
import sys, hashlib
OLD=b'https://api-defrag-eu.wrightflyer.net/api'
if len(sys.argv)!=4:
    print('Uso: python patch_client_url.py ORIGINAL.so https://TU-SERVIDOR.onrender.com/api SALIDA.so'); raise SystemExit(2)
src=Path(sys.argv[1]); url=sys.argv[2].encode(); dst=Path(sys.argv[3])
if not url.startswith(b'https://'): raise SystemExit('La URL debe usar https://')
if len(url)>len(OLD): raise SystemExit(f'URL demasiado larga: {len(url)} bytes; maximo {len(OLD)}')
b=bytearray(src.read_bytes()); n=b.count(OLD)
if n!=1: raise SystemExit(f'Se esperaba 1 URL original; encontradas {n}')
pos=b.find(OLD); repl=url+b'\0'*(len(OLD)-len(url)); b[pos:pos+len(OLD)]=repl
dst.write_bytes(b)
print('OK offset',hex(pos)); print('URL',url.decode()); print('SHA256',hashlib.sha256(b).hexdigest())
