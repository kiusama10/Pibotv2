# PiBot 2.0 + DANTE 1.0

Bot de Telegram para gestión, economía, juegos y administración de comunidades, con sistema privado de registro e investigación DANTE.

## Sistemas principales

### PiBot

- Economía virtual con PiPesos
- Tienda, inventario, regalos y títulos
- Juegos y casino
- Peleas y apuestas
- Perfiles
- Eventos y recompensas
- Subastas
- Sistemas multimedia
- Moderación y herramientas administrativas
- Persistencia mediante PostgreSQL

### DANTE 1.0

DANTE es un módulo independiente de registro e investigación.

Permite:

- Historial de nombres y usernames observados
- Registro de entradas, salidas y reapariciones
- Historial de cambios de identidad
- Vigilancia de cuentas
- Búsqueda histórica
- Comparación de cuentas
- Casos y expedientes
- Registro de evidencia
- SHA-256 para integridad de archivos
- Líneas temporales
- Registro de interacciones observables
- Análisis de coincidencias y filtraciones
- Exportación de casos
- Panel privado
- Estado y diagnóstico

DANTE trabaja únicamente con información que PiBot puede observar legítimamente.

DANTE no banea, expulsa, silencia, restringe, acepta ni rechaza usuarios automáticamente.

Las decisiones de moderación corresponden al BotMaster.

## Presentaciones

PiBot incorpora verificación opcional de presentaciones mediante nota de voz.

Flujo:

1. Rose publica la bienvenida.
2. PiBot espera el tiempo configurado.
3. PiBot proporciona una frase aleatoria para esa entrada.
4. El usuario realiza su presentación mediante nota de voz.
5. PiBot utiliza el sistema existente de control de presentaciones.

El sistema completo puede activarse o desactivarse:

```text
/presentaciones on
/presentaciones off
/presentaciones estado
```

DANTE es independiente del sistema de presentaciones. Si Presentaciones está OFF y DANTE está ON, DANTE continúa registrando los eventos disponibles normalmente.

## Identificación de usuarios

PiBot utiliza internamente el Telegram `user_id` para mantener una identidad estable.

En mensajes normales:

- Si existe username → `@username`
- Si no existe username → nombre de Telegram
- El ID numérico no se utiliza como sustituto visible del nombre

Los IDs pueden conservarse internamente y en documentación técnica cuando sean necesarios.

## Menciones

`/todos`

Menciona a los usuarios conocidos por PiBot en el grupo.

`/todos mensaje`

Realiza las menciones acompañadas del mensaje indicado.

## DANTE

Comandos principales:

```text
/dante
/dante buscar
/dante comparar
/dante vigilar
/dante nota
/dante caso
/dante evidencia
/dante exportar
/dante estado
```

Las funciones sensibles de DANTE están restringidas al usuario autorizado y su información se entrega por privado.

## Rendimiento

DANTE está diseñado para permanecer aislado del funcionamiento principal de PiBot.

Incluye:

- consultas PostgreSQL indexadas
- caché de identidad
- deduplicación de eventos
- procesamiento selectivo
- paginación
- persistencia
- aislamiento de errores

Un fallo de DANTE no debería detener PiBot.

## Stack tecnológico

| Componente | Tecnología |
|---|---|
| Framework | python-telegram-bot 22.5 |
| Base de datos | PostgreSQL |
| Lenguaje | Python 3.11+ |
| Deployment | Render |
| DANTE | 1.0.0 |

## Variables de entorno

Variables principales existentes:

```text
BOT_TOKEN
DATABASE_URL
BOT_USERNAME
BOTMASTER_IDS
```

Variables añadidas:

```text
DANTE_ENABLED=true
PRESENTATION_PROMPT_DELAY_SECONDS=8
```

`DANTE_ENABLED` permite desactivar DANTE sin detener PiBot.

`PRESENTATION_PROMPT_DELAY_SECONDS` controla cuánto espera PiBot después de una entrada antes de enviar la verificación de presentación, permitiendo que Rose publique primero su bienvenida.

## Seguridad

No publiques en el repositorio:

- `BOT_TOKEN`
- `DATABASE_URL` con credenciales
- contraseñas
- claves privadas
- archivos `.env` de producción

Utiliza las variables privadas de Render para estos valores.

## Ejecución

```bash
pip install -r requirements.txt
python main.py
```

## Versiones

- PiBot: 2.0
- DANTE: 1.0.0
