import os
import threading

_started = False
_lock = threading.Lock()

def _serve():
    try:
        import uvicorn
        from saocb_app import app

        port = int(os.getenv("SAOCB_INTERNAL_PORT", "8091"))
        print(f"[SAOCB-INTERNAL] starting on 127.0.0.1:{port}")

        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        server.run()
    except Exception as exc:
        print(f"[SAOCB-INTERNAL] failed: {type(exc).__name__}: {exc}")

def start_saocb_internal():
    global _started
    with _lock:
        if _started:
            return
        _started = True
        threading.Thread(
            target=_serve,
            daemon=True,
            name="saocb-internal-8091",
        ).start()

# Importing this module is the only change main.py needs.
start_saocb_internal()
