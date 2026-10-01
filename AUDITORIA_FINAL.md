# PiBot — auditoría económica final (RC1)

## Principios comprobados
- No se recalcula ni reinicia `usuarios_tb.saldo` durante migraciones.
- Las migraciones de esta versión son aditivas (`CREATE TABLE/INDEX IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`).
- Transferencias, apuestas persistentes, mercado, subastas, compras sociales, cosméticos, BANKIU y minijuegos realizan los movimientos de saldo dentro de transacciones PostgreSQL.
- Las apuestas persistentes se liquidan una sola vez mediante estado bloqueado con `FOR UPDATE`.
- Subastas reservan la puja y liquidan 80% a la persona subastada / 20% al BotMaster configurado.
- Navidad usa evento persistente anual y bloqueo transaccional para impedir ejecución concurrente duplicada.
- Las conexiones devueltas al pool se limpian con rollback si quedó una transacción de lectura abierta.

## Correcciones de esta pasada
1. Limpieza obligatoria de transacciones antes de devolver conexiones psycopg2 al pool. Evita reutilizar sesiones con snapshots o locks de lecturas anteriores.
2. Bloqueo advisory transaccional para el regalo global de Navidad antes de acreditar saldos.
3. Callback de compra de canales corregido para no responder dos veces al mismo CallbackQuery.

## Validación local sin tocar producción
- `python -m py_compile` sobre todos los Python: OK.
- Parseo AST sobre 34 archivos Python: OK.
- ZIP generado desde el árbol auditado.

## Pendientes de configuración, no errores
- Música permanece desactivada hasta definir `MUSIC_THREAD_ID` real.
- Catálogo de canales permanece vacío hasta configurar nombres/precios reales.
- BANKIU permite configurar interés/plazo mediante variables de entorno; los valores definitivos deben fijarse antes de producción si se desean distintos a los defaults actuales.
- Premios monetarios del ranking de riqueza y del juego Asesino no se inventaron porque no se fijaron cantidades.

## Antes de desplegar
1. Conservar el backup PostgreSQL ya realizado.
2. No borrar ni reemplazar `usuarios_tb`.
3. Ejecutar primero en Render con las variables de entorno revisadas.
4. Probar movimientos económicos con cuentas de prueba antes de habilitar todas las actividades.

## Revisión RC final posterior
- Corregido `/usar`: eliminada doble resta de inventario; ahora reserva atómica + devolución si falla Telegram.
- Tortugas/Blackjack restringidos al chat principal y tema Juegos 528.
- `/jugar` solo anuncia premio si PostgreSQL confirma el abono.
- `/pagarbanco` rechaza cero/negativos.
- BotMaster centralizado en `BOTMASTER_IDS` para permisos especiales revisados.
- Añadido `/comandos` real y callback inactivo de inventario atendido.
- Liquidación de subasta aborta/rollback si no existen las filas del destinatario o BotMaster, evitando perder una parte del pozo.
- Eliminados archivos ejecutables/instaladores/documentos ajenos de `gifs_items/sorpresa`.
- Actualizados `.env.example` y Procfile para el despliegue actual.
- Ver `VALIDACION_RC_FINAL.md` para mapa de temas y checklist.
