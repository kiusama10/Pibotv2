import base64
import json
import os
import re
import sys
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen


def _install_saocb_legacy_relay():
    # Surgical compatibility shim for the original SAO-CB client.
    # It is active only when PiBot is launched through main.py on the web service.
    argv0 = os.path.basename(sys.argv[0] or '').lower()
    if argv0 != 'main.py':
        return

    import drawing_web

    if getattr(drawing_web.H, '_saocb_legacy_relay_installed', False):
        return

    original_do_post = drawing_web.H.do_POST
    allowed_methods = {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}
    game_user_re = re.compile(r'^[A-Za-z0-9_.:-]{1,128}$')

    def send_bytes(handler, code, data, ctype='application/json; charset=utf-8'):
        handler.send_response(code)
        handler.send_header('content-type', ctype)
        handler.send_header('content-length', str(len(data)))
        handler.send_header('cache-control', 'no-store')
        handler.end_headers()
        handler.wfile.write(data)

    def relay(handler):
        try:
            length = int(handler.headers.get('content-length', '0') or 0)
            if length <= 0 or length > 2_000_000:
                return send_bytes(handler, 400, b'{"status":400,"error":"bad relay size"}')

            wrapper_raw = handler.rfile.read(length)
            wrapper = json.loads(wrapper_raw.decode('utf-8'))

            legacy_path = str(wrapper.get('legacy_path') or '').strip()
            if not (legacy_path == '/api' or legacy_path.startswith('/api/')):
                return send_bytes(handler, 400, b'{"status":400,"error":"bad legacy path"}')
            if '://' in legacy_path or '..' in legacy_path or '\\' in legacy_path or len(legacy_path) > 512:
                return send_bytes(handler, 400, b'{"status":400,"error":"unsafe legacy path"}')

            method = str(wrapper.get('legacy_method') or 'POST').upper().strip()
            if method not in allowed_methods:
                return send_bytes(handler, 400, b'{"status":400,"error":"bad legacy method"}')

            game_user = str(wrapper.get('game_user') or '').strip()
            if not game_user_re.fullmatch(game_user):
                return send_bytes(handler, 400, b'{"status":400,"error":"bad game user"}')

            query = str(wrapper.get('legacy_query') or '').strip()
            if query.startswith('?'):
                query = query[1:]
            if len(query) > 4096 or '\r' in query or '\n' in query:
                return send_bytes(handler, 400, b'{"status":400,"error":"bad legacy query"}')

            body_b64 = str(wrapper.get('legacy_body_b64') or '')
            if body_b64:
                legacy_body = base64.b64decode(body_b64, validate=True)
            else:
                legacy_body = str(wrapper.get('legacy_body') or '').encode('utf-8')
            if len(legacy_body) > 1_000_000:
                return send_bytes(handler, 413, b'{"status":413,"error":"legacy body too large"}')

            ctype = str(wrapper.get('legacy_content_type') or 'application/json').strip()
            if '\r' in ctype or '\n' in ctype or len(ctype) > 256:
                ctype = 'application/octet-stream'

            target = drawing_web.SAOCB_INTERNAL_URL + legacy_path
            if query:
                target += '?' + query

            headers = {
                'content-type': ctype,
                'accept': 'application/json',
                'x-saocb-user': game_user,
            }
            req = UrlRequest(target, data=legacy_body if legacy_body else None, headers=headers, method=method)
            try:
                upstream = urlopen(req, timeout=30)
                data = upstream.read()
                upstream_ctype = upstream.headers.get('content-type', 'application/json; charset=utf-8')
            except HTTPError as exc:
                data = exc.read()
                upstream_ctype = exc.headers.get('content-type', 'application/json; charset=utf-8')
                if not data:
                    data = json.dumps({'status': exc.code, 'error': 'legacy upstream'}).encode('utf-8')

            print(f'[SAOCB-LEGACY-RELAY] {method} {legacy_path} bytes={len(legacy_body)}')
            # The Android bridge expects the relay transport itself to be HTTP 200.
            # The original game's status stays inside the legacy JSON envelope.
            return send_bytes(handler, 200, data, upstream_ctype)
        except Exception as exc:
            print(f'[SAOCB-LEGACY-RELAY] {type(exc).__name__}: {exc}')
            data = json.dumps({'status': 502, 'error': 'legacy relay failed', 'detail': type(exc).__name__}).encode('utf-8')
            return send_bytes(handler, 200, data)

    def patched_do_post(self):
        if urlparse(self.path).path == '/api/v4/legacy/relay':
            return relay(self)
        return original_do_post(self)

    drawing_web.H.do_POST = patched_do_post
    drawing_web.H._saocb_legacy_relay_installed = True
    print('[SAOCB-SURGICAL] Original-client legacy relay enabled')


try:
    _install_saocb_legacy_relay()
except Exception as exc:
    # The compatibility shim must never prevent PiBot from starting.
    print(f'[SAOCB-SURGICAL] relay disabled safely: {type(exc).__name__}: {exc}')
