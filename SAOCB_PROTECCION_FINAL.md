# SAO-CB — protección final de persistencia

- PiBot permanece en PostgreSQL y no se refactorizan sus tablas existentes.
- SAO-CB conserva su SQLite compatible, pero cada escritura confirmada crea un backup consistente y lo replica a PostgreSQL (`saocb_sqlite_snapshot`).
- En cada arranque, SAO-CB restaura el último snapshot, valida SHA-256 y ejecuta `PRAGMA quick_check` antes de usarlo.
- Si la restauración falla, no sustituye la DB local por un archivo corrupto.
- El proxy público ahora conserva los headers de autenticación de SAO-CB (`X-SAO-CB-Secret`, `X-Telegram-User-Id`, etc.).
- La copia PostgreSQL puede desactivarse solo con `SAOCB_PG_SNAPSHOT=0`.
- `DATABASE_URL` sigue siendo la misma variable persistente de PiBot.

## Render
No hace falta un disco persistente para el save de SAO-CB si `DATABASE_URL` está configurada y `SAOCB_PG_SNAPSHOT=1` (valor predeterminado). El SQLite local funciona como caché/compatibilidad y PostgreSQL como copia durable de recuperación.
