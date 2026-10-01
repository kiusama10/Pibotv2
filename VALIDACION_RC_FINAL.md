# PiBot — validación RC final

Esta versión fue revisada sin conectarse a la base de datos de producción ni modificar saldos reales.

## Mapa de ubicación comprobado

| Sistema | Chat/tema esperado | Protección en código |
|---|---|---|
| Presentaciones | `-1003290179217`, General original renombrado; `thread_id=None` | Watchdog solo en el chat principal; PiBot no envía bienvenida |
| General / Quiz BDSM | `-1003290179217`, `thread_id=435` | Quiz automático fijado a ese chat y tema |
| Juegos / Casino clásico | tema `528` según comunidad | `/apostar`, `/jugar`, `/robar` validan `theme_juegosYcasino` |
| Tortugas / Blackjack | `-1003290179217`, `thread_id=528` | Chat y tema fijados; dados de Tortugas también validan ambos |
| Eventos / Subastas | `-1003290179217`, `thread_id=335263` | Crear, pujar, cancelar y liquidar fijados a Eventos |
| Exhibicionismo | `thread_id=324185` en comunidad principal | Recompensas enrutan por configuración de comunidad |
| NSFW | `thread_id=2` en comunidad principal | Recompensas enrutan por configuración de comunidad |
| Multimedia | `thread_id=688` en comunidad principal | Recompensas enrutan por configuración de comunidad |
| Dibuja y Adivina | chat + tema donde se crea | La partida persiste `chat_id + thread_id`; respuestas y rondas vuelven allí |
| Asesino | chat + tema donde se crea | La partida persiste `chat_id + thread_id`; secretos van por PV |
| Música | chat principal + `MUSIC_THREAD_ID` | Desactivado si el ID está vacío; no cobra fuera de la ubicación exacta |
| Perfil/vestidor/tienda/inventario | PV cuando corresponde | Editores y cosméticos fuerzan privado; tienda/inventario redirigen a PV |

## Correcciones adicionales de esta revisión

- `/usar` ya no descuenta dos veces el mismo ítem. Reserva una unidad atómicamente y la devuelve si Telegram falla al enviar el efecto.
- Tortugas y Blackjack ya no pueden arrancar accidentalmente en otro grupo que reutilice el número de tema 528.
- `/jugar` no anuncia 1,000 PiPesos si la base no confirmó el abono.
- `/pagarbanco 0` y cantidades negativas se rechazan; ya no pueden interpretarse como “pagar todo”.
- Los privilegios especiales dejaron de depender de un BotMaster numérico incrustado en código y usan `BOTMASTER_IDS`.
- Se añadió el comando `/comandos`, además del botón existente.
- Botones inactivos de paginación de inventario ahora responden y no dejan el spinner de Telegram abierto.
- Se eliminaron instaladores/ejecutables/PDF/JPG ajenos que estaban dentro de `gifs_items/sorpresa`; esa carpeta queda limitada a GIFs usados por el bot.
- `.env.example` refleja PostgreSQL/Supabase y las variables realmente usadas por esta versión.
- `procfile` usa proceso `web`, necesario para exponer el lienzo HTTP cuando el despliegue se guía por Procfile.

## Validación local ejecutada

- Parseo AST de los 34 archivos Python: OK.
- `compileall`/byte-compilation: OK.
- Auditoría estática de rutas, movimientos de saldo y callbacks principales: realizada.
- No se ejecutaron transacciones contra Supabase de producción.
- El import dinámico completo no se pudo ejecutar en el contenedor de auditoría porque allí no está instalada la dependencia `python-telegram-bot`; `requirements.txt` sí la declara (`22.5`).

## Configuración que sigue siendo obligatoria

1. `BOT_TOKEN` y `DATABASE_URL` reales en Render.
2. `BOTMASTER_IDS` con Kiu como primer ID si se usará la comisión de subastas.
3. `WEBAPP_BASE_URL`/`RENDER_EXTERNAL_URL` HTTPS para Dibuja y Adivina.
4. `MUSIC_THREAD_ID` real antes de activar el cobro de 500 PiPesos. Vacío = cobro desactivado.
5. `PIBOT_CHANNEL_CATALOG` con nombres/precios reales si se habilitará compra de canales. Vacío = no hay compras ni cobros.
6. Confirmar `BANKIU_INTEREST_PERCENT` y `BANKIU_TERM_DAYS`; los defaults actuales son 10% y 7 días.

## Prueba mínima antes de abrirlo a todo el grupo

Usar cuentas de prueba y anotar saldo inicial. Probar compra de tienda, `/usar`, `/dar`, `/jugar`, `/robar`, apuesta con timeout, Tortugas, Blackjack, Quiz, Dibuja, BANKIU, mercado y subasta. En cada operación comprobar saldo antes/después, doble clic y reinicio de Render en una operación pendiente. No habilitar Música hasta conocer su `thread_id` real.
