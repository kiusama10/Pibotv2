# SAO-CB integrado en PiBot v2

Integración aditiva: PiBot conserva su servidor HTTP público y Telegram polling. SAO-CB corre internamente en 127.0.0.1:8091 y `drawing_web.py` reenvía `/api/*`, `/game/*`, `/admin/*` y los endpoints administrativos de Telegram.

## Render
Mantener las variables actuales de PiBot y añadir:
- `SAOCB_API_SECRET`: secreto largo aleatorio.
- `SAOCB_DB_PATH`: ruta persistente para SAO-CB. NO usar `/tmp` en producción si se desea conservar partidas tras redeploys. Si el servicio tiene Persistent Disk, apuntar aquí (por ejemplo `/var/data/saocb.db`).
- `SAOCB_INTERNAL_URL=http://127.0.0.1:8091` (opcional; ese es el valor por defecto).

No cambiar el comando de inicio: `python main.py`.

## Comprobación pública
Después del deploy:
- `GET /health` comprueba PiBot web.
- `POST /api/user/register` debe llegar al Legacy Adapter SAO-CB.

## Cliente
La URL base del cliente es `https://pibotv2-1.onrender.com/api`.
Usar `BUILD_SAO_CB_FINAL.ps1` del checkpoint SAO-CB para parchear los nueve APK originales localmente y firmarlos con la keystore del propietario.
