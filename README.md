# PiBot 2.0

Bot de Telegram para gestión de comunidades BDSM con economía virtual, gamificación, tienda de ítems y sistema de castigos.

## Características

- **Economía Virtual** — Los usuarios ganan y gastan PiPesos a través de actividades y transacciones.
- **Tienda e Inventario** — Sistema de compra y uso de ítems (collar, látigo, fusta, galleta, bola mordaza, sorpresa).
- **Juegos y Casino** — Apuestas entre usuarios, dados, robos y juegos diarios.
- **Sistema de Combate** — Peleas por turnos con dados, HP y apuestas.
- **Recompensas Automáticas** — Gana PiPesos por publicar en temas específicos.
- **Sistema de Castigos** — Los DOM pueden confinar usuarios al "rincón del castigo".
- **Roles Internos** — Sistema de 3 niveles: Usuario (1), Admin (2), BotMaster (3).
- **Multi-Comunidad** — Soporte para múltiples comunidades con configuraciones independientes.

## Stack Tecnológico

| Componente | Tecnología |
|---|---|
| Framework | python-telegram-bot 22.5 |
| Base de Datos | PostgreSQL (psycopg2-binary) |
| Lenguaje | Python 3.11+ |
| Deployment | Railway |

## Variables de Entorno

| Variable | Requerida | Descripción |
|---|---|---|
| `BOT_TOKEN` | Sí | Token de Telegram de @BotFather |
| `DATABASE_URL` | Sí | URL de PostgreSQL (Railway lo provee automáticamente) |
| `BOT_USERNAME` | Sí | Username del bot sin @ (para deep links) |
| `BOTMASTER_IDS` | Sí | IDs de usuario separados por coma para rol BotMaster |

## Comandos

| Comando | Descripción | Permisos |
|---|---|---|
| `/start` | Menú principal (solo privado) | Todos |
| `/ver` | Ver saldo de PiPesos | Todos |
| `/dar <cant> @user` | Transferir PiPesos | Todos |
| `/tienda` | Abrir tienda (solo privado) | Todos |
| `/inventario` | Ver inventario (solo privado) | Todos |
| `/usar <item> @user` | Usar ítem en otro usuario | Todos |
| `/apostar <cant>` | Crear apuesta (tema juegos) | Todos |
| `/aceptar` | Aceptar apuesta | Todos |
| `/cancelar` | Cancelar apuesta | Todos |
| `/jugar` | Dado diario (max 5/día) | Todos |
| `/robar @user` | Intentar robar (max 3/día) | Todos |
| `/lucha @user <cant>` | Retar a combate | Todos |
| `/aceptarlucha` | Aceptar reto de combate | Todos |
| `/NumAzar N1 N2` | Número aleatorio | Todos |
| `/regalar <cant> @user` | Regalar PiPesos | Admin+ |
| `/quitar <cant>` | Quitar PiPesos | Admin+ |
| `/castigar @user` | Confinar al rincón | DOM |
| `/perdonar @user` | Liberar del rincón | DOM |
| `/AsignarRol @user [1\|2\|3]` | Cambiar rol de usuario | BotMaster |
| `/Suerte @user [1\|2\|3]` | Cambiar suerte de usuario (prob. robo) | BotMaster |
| `/MiRol` | Ver tu rol actual | Todos |

## Instalación Local

```bash
git clone https://github.com/aleisnthere31/Pibotv2.git
cd PiBot2.0
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

Crea un archivo `.env`:
```
BOT_TOKEN=tu_token_aquí
DATABASE_URL=postgresql://user:pass@host:5432/dbname
BOT_USERNAME=tu_bot_username
BOTMASTER_IDS=123456789
```

```bash
python main.py
```

## Documentación

- [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md) — Guía de despliegue en Railway
- [CHANGELOG.md](CHANGELOG.md) — Historial de cambios
- [Agents.md](Agents.md) — Documentación técnica completa para agentes AI
