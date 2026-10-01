"""
Database management module for PiBot.

This module handles all PostgreSQL database operations including:
- User and profile management
- Item catalog and inventory management
- Balance and points operations
- Role management (User=1, Admin=2, BotMaster=3)
- Combat/battle management
- Text normalization and cleaning utilities

Uses PostgreSQL via psycopg2 for persistent storage on Railway.
"""

import re
import unicodedata
from typing import Optional, Dict, List, Any

import psycopg2
import time
import threading
from psycopg2 import pool as pg_pool

from src.config import DATABASE_URL

# ==================== CONNECTION POOL ====================

_connection_pool = None
_pool_lock = threading.Lock()


def _init_pool():
    """Initialize the PostgreSQL connection pool once, safely across threads."""
    global _connection_pool
    if _connection_pool is not None:
        return

    with _pool_lock:
        if _connection_pool is not None:
            return
        print("[DB] Iniciando intento de conexión a Supabase...")
        try:
            start_time = time.time()
            candidate = pg_pool.ThreadedConnectionPool(
                1, 10,
                DATABASE_URL,
                sslmode="require",
                connect_timeout=10
            )
            _connection_pool = candidate
            print(f"[DB] ¡POOL CREADO EXITOSAMENTE! Tiempo: {time.time() - start_time:.2f}s")
        except Exception as e:
            # Keep None so a later request can retry initialization.
            _connection_pool = None
            print(f"[DB ERROR] No se pudo crear el pool: {str(e)}")


def _get_connection():
    """Get a live connection, discarding stale pooled connections when needed."""
    _init_pool()
    if _connection_pool is None:
        raise ConnectionError("PostgreSQL connection pool is unavailable")

    last_error = None
    for _ in range(2):
        conn = None
        try:
            conn = _connection_pool.getconn()
            if conn.closed:
                raise psycopg2.InterfaceError("pooled PostgreSQL connection is closed")
            # A tiny round-trip prevents handing a stale TCP connection to a handler.
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            return conn
        except (psycopg2.InterfaceError, psycopg2.OperationalError) as exc:
            last_error = exc
            if conn is not None:
                try:
                    _connection_pool.putconn(conn, close=True)
                except Exception:
                    pass

    raise ConnectionError(f"PostgreSQL connection unavailable after retry: {last_error}")


def _put_connection(conn):
    """Return a clean connection to the pool; discard broken connections.

    psycopg2 starts a transaction even for plain SELECTs. Several read helpers in
    PiBot intentionally do not call commit/rollback, so returning those sessions
    as-is can leave an old transaction (and potentially row locks/snapshots) in
    the pool. Always reset an open transaction before reusing the connection.
    Explicit writes already commit before reaching this function.
    """
    if conn is None or _connection_pool is None:
        return
    try:
        if not conn.closed:
            try:
                if conn.status != psycopg2.extensions.STATUS_READY:
                    conn.rollback()
            except (psycopg2.InterfaceError, psycopg2.OperationalError):
                _connection_pool.putconn(conn, close=True)
                return
        _connection_pool.putconn(conn, close=bool(conn.closed))
    except (psycopg2.InterfaceError, psycopg2.OperationalError):
        try:
            conn.close()
        except Exception:
            pass


# ==================== INITIALIZATION ====================

def create_database():
    """No-op for PostgreSQL — the database is provisioned by Railway."""
    pass


def create_tables():
    """
    Create all necessary database tables with proper schema and constraints.

    Tables created:
    - usuarios_tb: User accounts and balance
    - items_tb: Item catalog
    - items_usuarios_tb: User inventory (many-to-many relationship)
    - perfiles_tb: User profile information
    - combates_tb: Combat/battle records
    - roles_tb: Internal role system
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios_tb (
                id_user BIGINT PRIMARY KEY,
                saldo INTEGER DEFAULT 0,
                suerte INTEGER NOT NULL DEFAULT 2 CHECK (suerte IN (1, 2, 3))
            );
        """)

        # Add suerte column if missing (existing tables)
        cursor.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'usuarios_tb' AND column_name = 'suerte'
                ) THEN
                    ALTER TABLE usuarios_tb ADD COLUMN suerte INTEGER NOT NULL DEFAULT 2 CHECK (suerte IN (1, 2, 3));
                END IF;
            END $$;
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items_tb (
                id_item SERIAL PRIMARY KEY,
                nombre TEXT NOT NULL UNIQUE,
                precio INTEGER NOT NULL,
                imagen TEXT NOT NULL,
                descripcion TEXT,
                mensaje TEXT
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS items_usuarios_tb (
                id SERIAL PRIMARY KEY,
                id_user BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                id_item INTEGER NOT NULL REFERENCES items_tb(id_item) ON DELETE CASCADE,
                cantidad INTEGER NOT NULL DEFAULT 1,
                UNIQUE(id_user, id_item)
            );
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_usuario ON items_usuarios_tb(id_user);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_item ON items_usuarios_tb(id_item);")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS perfiles_tb (
                id_user BIGINT PRIMARY KEY REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                username TEXT UNIQUE,
                nombre TEXT NOT NULL,
                rol TEXT,
                orientacion_sexual TEXT,
                genero TEXT,
                ubicacion TEXT,
                edad INTEGER
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS combates_tb (
                id_combate SERIAL PRIMARY KEY,
                id_atacante BIGINT NOT NULL REFERENCES usuarios_tb(id_user),
                id_defensor BIGINT NOT NULL REFERENCES usuarios_tb(id_user),
                username_atacante TEXT NOT NULL,
                username_defensor TEXT NOT NULL,
                apuesta INTEGER NOT NULL DEFAULT 0,
                hp_atacante INTEGER NOT NULL DEFAULT 20,
                hp_defensor INTEGER NOT NULL DEFAULT 20,
                turno INTEGER NOT NULL DEFAULT 1,
                es_turno_atacante INTEGER NOT NULL DEFAULT 1,
                estado TEXT NOT NULL DEFAULT 'activo',
                ganador BIGINT REFERENCES usuarios_tb(id_user),
                fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                chat_id BIGINT,
                message_thread_id BIGINT
            );
        """)
        # Migración aditiva para instalaciones existentes. No toca saldos ni combates históricos.
        cursor.execute("ALTER TABLE combates_tb ADD COLUMN IF NOT EXISTS chat_id BIGINT;")
        cursor.execute("ALTER TABLE combates_tb ADD COLUMN IF NOT EXISTS message_thread_id BIGINT;")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_combate_atacante ON combates_tb(id_atacante);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_combate_defensor ON combates_tb(id_defensor);")

        # Internal role system
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roles_tb (
                id_user BIGINT PRIMARY KEY REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                role INTEGER NOT NULL DEFAULT 1 CHECK (role IN (1, 2, 3))
            );
        """)

        # Persistent daily command limits. Additive table: does not modify existing user balances.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usos_diarios_tb (
                id_user BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                comando TEXT NOT NULL,
                fecha DATE NOT NULL,
                veces INTEGER NOT NULL DEFAULT 0 CHECK (veces >= 0),
                PRIMARY KEY (id_user, comando, fecha)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_usos_diarios_fecha ON usos_diarios_tb(fecha);")

        # Durable casino settlements. One row per accepted wager prevents a
        # winner/refund from being applied twice after callbacks, timeouts or restarts.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS apuestas_casino_tb (
                apuesta_id TEXT PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                thread_id BIGINT NOT NULL,
                apostador_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user),
                rival_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user),
                cantidad INTEGER NOT NULL CHECK (cantidad > 0),
                estado TEXT NOT NULL DEFAULT 'reservada',
                resultado TEXT,
                fecha_creacion TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                fecha_resolucion TIMESTAMP
            );
        """)
        # Phase 14: persist dice too, so accepted wagers survive bot restarts.
        cursor.execute("ALTER TABLE apuestas_casino_tb ADD COLUMN IF NOT EXISTS dado_apostador INTEGER")
        cursor.execute("ALTER TABLE apuestas_casino_tb ADD COLUMN IF NOT EXISTS dado_rival INTEGER")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_apuestas_casino_contexto ON apuestas_casino_tb(chat_id, thread_id, estado);")

        # Social economy: collectible titles, gifts, market and BANKIU pawn collateral.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS social_assets_tb (
                asset_id BIGSERIAL PRIMARY KEY,
                asset_type TEXT NOT NULL CHECK (asset_type IN ('titulo','regalo')),
                code TEXT NOT NULL,
                nombre TEXT NOT NULL,
                rareza TEXT NOT NULL DEFAULT 'comun',
                serial_no INTEGER,
                serial_total INTEGER,
                valor_base INTEGER NOT NULL CHECK (valor_base >= 0),
                propietario_id BIGINT REFERENCES usuarios_tb(id_user) ON DELETE SET NULL,
                origen TEXT NOT NULL DEFAULT 'tienda',
                transferible BOOLEAN NOT NULL DEFAULT TRUE,
                estado TEXT NOT NULL DEFAULT 'disponible',
                creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(code, serial_no, origen)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_social_assets_owner ON social_assets_tb(propietario_id, asset_type, estado);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_social_assets_code ON social_assets_tb(code, estado);")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS social_asset_history_tb (
                id BIGSERIAL PRIMARY KEY, asset_id BIGINT NOT NULL REFERENCES social_assets_tb(asset_id) ON DELETE CASCADE,
                de_user BIGINT, a_user BIGINT, accion TEXT NOT NULL, precio INTEGER, creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS social_market_tb (
                listing_id BIGSERIAL PRIMARY KEY, asset_id BIGINT NOT NULL UNIQUE REFERENCES social_assets_tb(asset_id) ON DELETE CASCADE,
                vendedor_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user), precio INTEGER NOT NULL CHECK(precio > 0),
                estado TEXT NOT NULL DEFAULT 'activo', creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(), vendido_en TIMESTAMPTZ
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_social_market_active ON social_market_tb(estado, creado_en DESC);")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bankiu_pawns_tb (
                pawn_id BIGSERIAL PRIMARY KEY, asset_id BIGINT NOT NULL UNIQUE REFERENCES social_assets_tb(asset_id),
                user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user), principal INTEGER NOT NULL CHECK(principal > 0),
                payoff INTEGER NOT NULL CHECK(payoff >= principal), estado TEXT NOT NULL DEFAULT 'activo',
                creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(), vence_en TIMESTAMPTZ NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bankiu_pawns_user ON bankiu_pawns_tb(user_id, estado);")
        # User auctions: one active auction in Eventos, with bids reserved atomically.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_auctions_tb (
                auction_id BIGSERIAL PRIMARY KEY, chat_id BIGINT NOT NULL, thread_id BIGINT,
                subastado_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user), subastado_nombre TEXT NOT NULL,
                puja_actual INTEGER NOT NULL DEFAULT 0 CHECK (puja_actual >= 0), postor_id BIGINT REFERENCES usuarios_tb(id_user),
                estado TEXT NOT NULL DEFAULT 'activa', creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
                actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now(), termina_en TIMESTAMPTZ NOT NULL,
                recordatorio_5m BOOLEAN NOT NULL DEFAULT FALSE, cerrada_en TIMESTAMPTZ, cerrada_por BIGINT,
                pago_subastado INTEGER NOT NULL DEFAULT 0, comision_kiu INTEGER NOT NULL DEFAULT 0
            );
        """)
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_user_auction_active_location ON user_auctions_tb(chat_id, COALESCE(thread_id,0)) WHERE estado='activa';")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_auctions_due ON user_auctions_tb(estado, termina_en);")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auction_bids_tb (
                bid_id BIGSERIAL PRIMARY KEY, auction_id BIGINT NOT NULL REFERENCES user_auctions_tb(auction_id) ON DELETE CASCADE,
                postor_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user), monto INTEGER NOT NULL CHECK (monto > 0),
                creado_en TIMESTAMPTZ NOT NULL DEFAULT now()
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_auction_bids_auction ON auction_bids_tb(auction_id, creado_en DESC);")

        # BANKIU loans. Existing balances are never recalculated; money moves only in explicit transactions.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bankiu_loans_tb (
                loan_id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                principal INTEGER NOT NULL CHECK(principal > 0),
                interes_pct INTEGER NOT NULL CHECK(interes_pct >= 0),
                saldo_pendiente INTEGER NOT NULL CHECK(saldo_pendiente >= 0),
                estado TEXT NOT NULL DEFAULT 'activo' CHECK(estado IN ('activo','vencido','pagado','cancelado')),
                creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                vence_en TIMESTAMPTZ NOT NULL,
                pagado_en TIMESTAMPTZ
            );
        """)
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_bankiu_one_open_loan ON bankiu_loans_tb(user_id) WHERE estado IN ('activo','vencido');")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bankiu_due ON bankiu_loans_tb(estado,vence_en);")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bankiu_payments_tb (
                payment_id BIGSERIAL PRIMARY KEY,
                loan_id BIGINT NOT NULL REFERENCES bankiu_loans_tb(loan_id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                monto INTEGER NOT NULL CHECK(monto > 0),
                tipo TEXT NOT NULL,
                creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_bankiu_payments_user ON bankiu_payments_tb(user_id,creado_en DESC);")
        # Quincenal participation ranking. Scores are batched in memory and flushed periodically.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS participation_cycles_tb (
                cycle_id BIGSERIAL PRIMARY KEY,
                starts_at TIMESTAMPTZ NOT NULL,
                ends_at TIMESTAMPTZ NOT NULL,
                estado TEXT NOT NULL DEFAULT 'activo' CHECK(estado IN ('activo','cerrado'))
            );
        """)
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_participation_active_cycle ON participation_cycles_tb(estado) WHERE estado='activo';")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS participation_scores_tb (
                cycle_id BIGINT NOT NULL REFERENCES participation_cycles_tb(cycle_id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                puntos INTEGER NOT NULL DEFAULT 0 CHECK(puntos >= 0),
                PRIMARY KEY(cycle_id,user_id)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_participation_leaderboard ON participation_scores_tb(cycle_id,puntos DESC);")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS participation_awards_tb (
                cycle_id BIGINT NOT NULL REFERENCES participation_cycles_tb(cycle_id) ON DELETE CASCADE,
                position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 3),
                user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                asset_id BIGINT NOT NULL REFERENCES social_assets_tb(asset_id),
                puntos INTEGER NOT NULL,
                creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY(cycle_id,position), UNIQUE(asset_id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS title_rotations_tb (
                rotation_key TEXT PRIMARY KEY, starts_at TIMESTAMPTZ NOT NULL, ends_at TIMESTAMPTZ NOT NULL,
                creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS title_rotation_stock_tb (
                rotation_key TEXT NOT NULL REFERENCES title_rotations_tb(rotation_key) ON DELETE CASCADE,
                code TEXT NOT NULL, nombre TEXT NOT NULL, rareza TEXT NOT NULL, precio INTEGER NOT NULL,
                stock_total INTEGER, stock_vendido INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(rotation_key, code)
            );
        """)
        cursor.execute("ALTER TABLE perfiles_tb ADD COLUMN IF NOT EXISTS titulo_equipado_id BIGINT;")
        cursor.execute("ALTER TABLE perfiles_tb ADD COLUMN IF NOT EXISTS marco_equipado_id BIGINT;")
        cursor.execute("ALTER TABLE perfiles_tb ADD COLUMN IF NOT EXISTS insignia_equipada_id BIGINT;")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS profile_cosmetics_tb (
                cosmetic_id BIGSERIAL PRIMARY KEY,
                code TEXT NOT NULL,
                nombre TEXT NOT NULL,
                cosmetic_type TEXT NOT NULL CHECK (cosmetic_type IN ('marco','insignia')),
                rareza TEXT NOT NULL DEFAULT 'comun',
                precio_compra INTEGER NOT NULL CHECK (precio_compra >= 0),
                owner_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                season_key TEXT,
                creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(owner_id, code)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_profile_cosmetics_owner ON profile_cosmetics_tb(owner_id, cosmetic_type);")
        # Perfil social/BDSM: all fields are voluntary and edited only by the owner in private chat.
        cursor.execute("ALTER TABLE perfiles_tb ADD COLUMN IF NOT EXISTS experiencia TEXT;")
        cursor.execute("ALTER TABLE perfiles_tb ADD COLUMN IF NOT EXISTS gustos TEXT;")
        cursor.execute("ALTER TABLE perfiles_tb ADD COLUMN IF NOT EXISTS relacion TEXT;")
        cursor.execute("ALTER TABLE perfiles_tb ADD COLUMN IF NOT EXISTS bio TEXT;")
        cursor.execute("ALTER TABLE perfiles_tb ADD COLUMN IF NOT EXISTS frase TEXT;")
        cursor.execute("ALTER TABLE perfiles_tb ADD COLUMN IF NOT EXISTS limites TEXT;")
        cursor.execute("ALTER TABLE perfiles_tb ADD COLUMN IF NOT EXISTS perfil_publico BOOLEAN NOT NULL DEFAULT TRUE;")
        cursor.execute("ALTER TABLE social_assets_tb ADD COLUMN IF NOT EXISTS regalo_anonimo BOOLEAN NOT NULL DEFAULT FALSE;")
        cursor.execute("ALTER TABLE social_assets_tb ADD COLUMN IF NOT EXISTS regalo_privado BOOLEAN NOT NULL DEFAULT FALSE;")
        cursor.execute("ALTER TABLE social_assets_tb ADD COLUMN IF NOT EXISTS regalado_por BIGINT;")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_social_assets_equipped ON social_assets_tb(asset_id, propietario_id, estado);")
        # Social game: Asesino. State is durable and scoped to chat + topic.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assassin_games_tb (
                game_id BIGSERIAL PRIMARY KEY, chat_id BIGINT NOT NULL, thread_id BIGINT, host_id BIGINT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'lobby', asesino_id BIGINT, ronda INTEGER NOT NULL DEFAULT 1,
                creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(), iniciado_en TIMESTAMPTZ, cerrado_en TIMESTAMPTZ
            );
        """)
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_assassin_active_location ON assassin_games_tb(chat_id,COALESCE(thread_id,0)) WHERE estado IN ('lobby','jugando','votacion');")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assassin_players_tb (
                game_id BIGINT NOT NULL REFERENCES assassin_games_tb(game_id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE, nombre TEXT NOT NULL,
                vivo BOOLEAN NOT NULL DEFAULT TRUE, joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(game_id,user_id)
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assassin_votes_tb (
                game_id BIGINT NOT NULL REFERENCES assassin_games_tb(game_id) ON DELETE CASCADE, ronda INTEGER NOT NULL,
                voter_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user), target_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user),
                creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(game_id,ronda,voter_id)
            );
        """)
        # Channel purchases are recorded atomically; delivery is provider/admin-configurable.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channel_purchases_tb (
                purchase_id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                channel_code TEXT NOT NULL, channel_name TEXT NOT NULL, precio INTEGER NOT NULL CHECK(precio>0),
                estado TEXT NOT NULL DEFAULT 'pagado', creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(), entregado_en TIMESTAMPTZ
            );
        """)
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_channel_purchase_paid ON channel_purchases_tb(user_id,channel_code) WHERE estado IN ('pagado','entregado');")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS global_events_tb (
                event_key TEXT PRIMARY KEY, ejecutado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                afectados INTEGER NOT NULL DEFAULT 0, total_pipesos BIGINT NOT NULL DEFAULT 0
            );
        """)

        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Failed to create tables: {e}")
    finally:
        _put_connection(conn)


def seed_items():
    """
    Seed the item catalog with default items if not already present.
    Idempotent — skips items that already exist.
    """
    items = [
        {
            "nombre": "Collar",
            "precio": 2000,
            "imagen": "img_items/collar.png",
            "descripcion": "Un bonito collar para poner a alguien especial",
            "mensaje": "😈 {sender_username} le ha puesto un collar muy bonito a {receptor_username} 😍\n ¡Qué envidiaaa!",
        },
        {
            "nombre": "Latigo",
            "precio": 2000,
            "imagen": "img_items/latigo.png",
            "descripcion": "Un látigo para los que se portan mal",
            "mensaje": "😱 {sender_username} ha azotado con un látigo a {receptor_username} \n ... Eso va a dejar marca 🫦",
        },
        {
            "nombre": "Fusta",
            "precio": 2000,
            "imagen": "img_items/fusta.png",
            "descripcion": "Fusta de adiestramiento profesional",
            "mensaje": "🤩 {sender_username} está adiestrando a {receptor_username} con su fusta favorita 😈\n ¿Porqué parece que {receptor_username} lo disfruta?... 🫦",
        },
        {
            "nombre": "Galleta",
            "precio": 2000,
            "imagen": "img_items/galleta.png",
            "descripcion": "Una galleta para premiar el buen comportamiento",
            "mensaje": "❤ {sender_username} le ha regalado a {receptor_username} una galleta 🍪\n Parece que se ha portado muy bien 🤤",
        },
        {
            "nombre": "Bola mordaza",
            "precio": 2000,
            "imagen": "img_items/bola_mordaza.png",
            "descripcion": "Para cuando alguien habla demasiado",
            "mensaje": "🤏 {sender_username} Le ha puesto una bola mordaza a {receptor_username}\n Que bien te ves sin poder hablar 😖",
        },
        {
            "nombre": "Sorpresa",
            "precio": 2000,
            "imagen": "img_items/sorpresa.jpg",
            "descripcion": "Un artículo misterioso... ¿te atreves?",
            "mensaje": "😈 {sender_username} ha decidido modelarle algo de su lencería sexy a {receptor_username}\n Le queda muy bien, aunque no esperaba que {sender_username} hiciera eso frente a todos 👁👄👁",
        },
    ]

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        for item in items:
            cursor.execute("SELECT 1 FROM items_tb WHERE nombre = %s", (item["nombre"],))
            if cursor.fetchone() is None:
                cursor.execute(
                    "INSERT INTO items_tb (nombre, precio, imagen, descripcion, mensaje) VALUES (%s, %s, %s, %s, %s)",
                    (item["nombre"], item["precio"], item["imagen"], item["descripcion"], item["mensaje"]),
                )
                print(f"[SEED] Item '{item['nombre']}' inserted.")
            else:
                # Update existing items to fix any corrupted text
                cursor.execute(
                    "UPDATE items_tb SET precio = %s, descripcion = %s, mensaje = %s WHERE nombre = %s",
                    (item["precio"], item["descripcion"], item["mensaje"], item["nombre"]),
                )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Failed to seed items: {e}")
    finally:
        _put_connection(conn)


def init_botmaster_roles(botmaster_ids: list):
    """
    Ensure BotMaster users have role=3 in the database.
    Called at startup to bootstrap the role system.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        for uid in botmaster_ids:
            # Ensure user exists in usuarios_tb
            cursor.execute("SELECT 1 FROM usuarios_tb WHERE id_user = %s", (uid,))
            if cursor.fetchone() is None:
                cursor.execute("INSERT INTO usuarios_tb (id_user, saldo) VALUES (%s, 0)", (uid,))
                cursor.execute(
                    "INSERT INTO perfiles_tb (id_user, username, nombre) VALUES (%s, %s, %s)",
                    (uid, None, "BotMaster"),
                )
            # Upsert role
            cursor.execute(
                "INSERT INTO roles_tb (id_user, role) VALUES (%s, 3) "
                "ON CONFLICT (id_user) DO UPDATE SET role = 3",
                (uid,),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Failed to init botmaster roles: {e}")
    finally:
        _put_connection(conn)


# ==================== USER OPERATIONS ====================

def insert_user(id_user: int, saldo: int = 0, username: Optional[str] = None,
                nombre: Optional[str] = None) -> bool:
    """Create a new user account, profile, and default role."""
    if not id_user:
        print("[ERROR DB] Cannot insert user without valid ID")
        return False

    if not nombre or nombre.strip() == "":
        print("[ERROR DB] User must have at least a name")
        return False

    conn = _get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO usuarios_tb (id_user, saldo) VALUES (%s, %s)",
            (id_user, saldo),
        )
        cursor.execute(
            "INSERT INTO perfiles_tb (id_user, username, nombre) VALUES (%s, %s, %s)",
            (id_user, username, nombre),
        )
        # Default role = 1 (User)
        cursor.execute(
            "INSERT INTO roles_tb (id_user, role) VALUES (%s, 1)",
            (id_user,),
        )

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Failed to insert user: {e}")
        return False
    finally:
        _put_connection(conn)


def get_campo_usuario(id_user: int, columna: str) -> Optional[Any]:
    """Retrieve a specific field from a user's profile or balance."""
    columnas_validas = {
        "nombre", "username", "rol", "orientacion_sexual",
        "genero", "ubicacion", "edad", "saldo", "id_user",
    }

    if columna not in columnas_validas:
        print(f"[ERROR DB] Invalid column: {columna}")
        return None

    tabla = "usuarios_tb" if columna == "saldo" else "perfiles_tb"

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT {columna} FROM {tabla} WHERE id_user = %s", (id_user,))
        resultado = cursor.fetchone()
        return resultado[0] if resultado else None
    except Exception as e:
        print(f"[ERROR DB] Error retrieving user field: {e}")
        return None
    finally:
        _put_connection(conn)


def get_usuario_resumen(id_user: int) -> Optional[Dict[str, Any]]:
    """Fetch the fields most handlers need in one round-trip.

    Read-only helper: it never creates, updates or normalizes user data.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT u.id_user, u.saldo, p.username, p.nombre
            FROM usuarios_tb u
            LEFT JOIN perfiles_tb p ON p.id_user = u.id_user
            WHERE u.id_user = %s
            """,
            (id_user,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {"id_user": row[0], "saldo": row[1], "username": row[2], "nombre": row[3]}
    except Exception as e:
        print(f"[ERROR DB] Error retrieving user summary: {e}")
        return None
    finally:
        _put_connection(conn)


def update_perfil(id_user: int, **datos) -> bool:
    """Update user profile fields."""
    columnas_validas = {
        "nombre", "username", "rol", "orientacion_sexual",
        "genero", "ubicacion", "edad", "experiencia", "gustos", "relacion",
        "bio", "limites", "perfil_publico", "titulo_equipado_id",
    }

    if not datos:
        print("[ERROR DB] No data provided for update")
        return False

    for col in datos.keys():
        if col not in columnas_validas:
            print(f"[ERROR DB] Invalid column: {col}")
            return False

    conn = _get_connection()
    try:
        cursor = conn.cursor()

        columnas = ", ".join([f"{col} = %s" for col in datos.keys()])
        valores = list(datos.values()) + [id_user]

        cursor.execute(f"UPDATE perfiles_tb SET {columnas} WHERE id_user = %s", valores)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error updating profile: {e}")
        return False
    finally:
        _put_connection(conn)


# ==================== BALANCE OPERATIONS ====================

def update_saldo(id_user: int, saldo: int) -> bool:
    """Set user's balance to a specific value."""
    if saldo < 0:
        print("[ERROR DB] Balance cannot be negative")
        return False

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usuarios_tb SET saldo = %s WHERE id_user = %s",
            (saldo, id_user),
        )
        if cursor.rowcount == 0:
            print("[ERROR DB] User not found")
            conn.rollback()
            return False
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error updating balance: {e}")
        return False
    finally:
        _put_connection(conn)


def dar_puntos(id_user: int, cantidad: int) -> bool:
    """Add points atomically, without a read/modify/write race."""
    if cantidad < 0:
        return quitar_puntos(id_user, -cantidad)
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usuarios_tb SET saldo = saldo + %s WHERE id_user = %s",
            (cantidad, id_user),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return False
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error adding balance: {e}")
        return False
    finally:
        _put_connection(conn)


def quitar_puntos(id_user: int, cantidad: int) -> bool:
    """Remove points atomically only when the full amount is available."""
    if cantidad < 0:
        return dar_puntos(id_user, -cantidad)
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usuarios_tb SET saldo = saldo - %s WHERE id_user = %s AND saldo >= %s",
            (cantidad, id_user, cantidad),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return False
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error removing balance: {e}")
        return False
    finally:
        _put_connection(conn)


def reservar_apuesta_doble(id_a: int, id_b: int, cantidad: int) -> bool:
    """Atomically reserve the same wager from two users."""
    if cantidad <= 0 or id_a == id_b:
        return False
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        # Deterministic lock order avoids deadlocks when requests cross.
        ids = sorted((id_a, id_b))
        cursor.execute(
            "SELECT id_user, saldo FROM usuarios_tb WHERE id_user IN (%s, %s) ORDER BY id_user FOR UPDATE",
            (ids[0], ids[1]),
        )
        rows = cursor.fetchall()
        if len(rows) != 2 or any(row[1] < cantidad for row in rows):
            conn.rollback()
            return False
        cursor.execute(
            "UPDATE usuarios_tb SET saldo = saldo - %s WHERE id_user IN (%s, %s)",
            (cantidad, id_a, id_b),
        )
        if cursor.rowcount != 2:
            conn.rollback()
            return False
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error reserving double wager: {e}")
        return False
    finally:
        _put_connection(conn)


def reembolsar_apuesta_doble(id_a: int, id_b: int, cantidad: int) -> bool:
    """Refund a previously reserved two-player wager in one transaction."""
    if cantidad <= 0 or id_a == id_b:
        return False
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usuarios_tb SET saldo = saldo + %s WHERE id_user IN (%s, %s)",
            (cantidad, id_a, id_b),
        )
        if cursor.rowcount != 2:
            conn.rollback()
            return False
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error refunding double wager: {e}")
        return False
    finally:
        _put_connection(conn)


def reservar_apuesta_persistente(apuesta_id: str, chat_id: int, thread_id: int, id_a: int, id_b: int, cantidad: int) -> bool:
    """Reserve both stakes and persist the accepted wager in ONE transaction."""
    if not apuesta_id or cantidad <= 0 or id_a == id_b:
        return False
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        ids = sorted((id_a, id_b))
        cursor.execute(
            "SELECT id_user, saldo FROM usuarios_tb WHERE id_user IN (%s, %s) ORDER BY id_user FOR UPDATE",
            (ids[0], ids[1]),
        )
        rows = cursor.fetchall()
        if len(rows) != 2 or any(int(row[1]) < cantidad for row in rows):
            conn.rollback()
            return False
        cursor.execute(
            "UPDATE usuarios_tb SET saldo = saldo - %s WHERE id_user IN (%s, %s)",
            (cantidad, id_a, id_b),
        )
        if cursor.rowcount != 2:
            conn.rollback()
            return False
        cursor.execute(
            """INSERT INTO apuestas_casino_tb
               (apuesta_id, chat_id, thread_id, apostador_id, rival_id, cantidad, estado)
               VALUES (%s, %s, %s, %s, %s, %s, 'reservada')""",
            (apuesta_id, chat_id, thread_id, id_a, id_b, cantidad),
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error reserving persistent wager: {e}")
        return False
    finally:
        _put_connection(conn)


def liquidar_apuesta_persistente(apuesta_id: str, resultado: str, ganador_id: Optional[int] = None) -> str:
    """Settle a reserved wager exactly once. Returns paid/refunded/already/error."""
    if resultado not in ("ganador", "empate", "cancelada"):
        return "error"
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT apostador_id, rival_id, cantidad, estado
               FROM apuestas_casino_tb WHERE apuesta_id = %s FOR UPDATE""",
            (apuesta_id,),
        )
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return "error"
        id_a, id_b, cantidad, estado = row
        if estado != "reservada":
            conn.rollback()
            return "already"
        if resultado == "ganador":
            if ganador_id not in (id_a, id_b):
                conn.rollback()
                return "error"
            cursor.execute("UPDATE usuarios_tb SET saldo = saldo + %s WHERE id_user = %s", (cantidad * 2, ganador_id))
            if cursor.rowcount != 1:
                conn.rollback()
                return "error"
        else:
            cursor.execute("UPDATE usuarios_tb SET saldo = saldo + %s WHERE id_user IN (%s, %s)", (cantidad, id_a, id_b))
            if cursor.rowcount != 2:
                conn.rollback()
                return "error"
        cursor.execute(
            """UPDATE apuestas_casino_tb SET estado='liquidada', resultado=%s,
               fecha_resolucion=CURRENT_TIMESTAMP WHERE apuesta_id=%s""",
            (resultado, apuesta_id),
        )
        conn.commit()
        return "paid" if resultado == "ganador" else "refunded"
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error settling persistent wager: {e}")
        return "error"
    finally:
        _put_connection(conn)



def registrar_dado_apuesta(apuesta_id: str, id_user: int, valor: int) -> str:
    """Persist one player's die exactly once. Returns saved/already/error."""
    if not 1 <= int(valor) <= 6:
        return "error"
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT apostador_id, rival_id, dado_apostador, dado_rival, estado
               FROM apuestas_casino_tb WHERE apuesta_id=%s FOR UPDATE""",
            (apuesta_id,),
        )
        row = cursor.fetchone()
        if not row or row[4] != "reservada":
            conn.rollback(); return "error"
        id_a, id_b, dado_a, dado_b, _ = row
        if id_user == id_a:
            if dado_a is not None:
                conn.rollback(); return "already"
            cursor.execute("UPDATE apuestas_casino_tb SET dado_apostador=%s WHERE apuesta_id=%s", (valor, apuesta_id))
        elif id_user == id_b:
            if dado_b is not None:
                conn.rollback(); return "already"
            cursor.execute("UPDATE apuestas_casino_tb SET dado_rival=%s WHERE apuesta_id=%s", (valor, apuesta_id))
        else:
            conn.rollback(); return "error"
        conn.commit(); return "saved"
    except Exception as e:
        conn.rollback(); print(f"[ERROR DB] Error persisting wager die: {e}"); return "error"
    finally:
        _put_connection(conn)


def obtener_apuestas_reservadas() -> List[Dict[str, Any]]:
    """Load accepted, unsettled wagers for restart recovery."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.apuesta_id, a.chat_id, a.thread_id, a.apostador_id, a.rival_id,
                   a.cantidad, a.dado_apostador, a.dado_rival, a.fecha_creacion,
                   COALESCE(NULLIF(u1.username,''), u1.nombre, a.apostador_id::text),
                   COALESCE(NULLIF(u2.username,''), u2.nombre, a.rival_id::text)
            FROM apuestas_casino_tb a
            LEFT JOIN usuarios_tb u1 ON u1.id_user=a.apostador_id
            LEFT JOIN usuarios_tb u2 ON u2.id_user=a.rival_id
            WHERE a.estado='reservada'
            ORDER BY a.fecha_creacion
        """)
        rows = cursor.fetchall()
        return [{
            "apuesta_id": r[0], "chat_id": r[1], "thread_id": r[2],
            "apostador_id": r[3], "rival_id": r[4], "cantidad": r[5],
            "dado_apostador": r[6], "dado_rival": r[7], "fecha_creacion": r[8],
            "apostador_username": r[9], "rival_username": r[10],
        } for r in rows]
    except Exception as e:
        print(f"[ERROR DB] Error loading reserved wagers: {e}"); return []
    finally:
        _put_connection(conn)

def comprar_item_atomico(id_user: int, id_item: int, precio: int) -> bool:
    """Charge and deliver an item as one PostgreSQL transaction."""
    if precio < 0:
        return False
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usuarios_tb SET saldo = saldo - %s WHERE id_user = %s AND saldo >= %s",
            (precio, id_user, precio),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return False
        cursor.execute(
            """INSERT INTO items_usuarios_tb (id_user, id_item, cantidad) VALUES (%s, %s, 1)
               ON CONFLICT (id_user, id_item) DO UPDATE
               SET cantidad = items_usuarios_tb.cantidad + 1""",
            (id_user, id_item),
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Atomic purchase failed: {e}")
        return False
    finally:
        _put_connection(conn)


# ==================== LUCK (SUERTE) OPERATIONS ====================

def get_suerte(id_user: int) -> int:
    """Get a user's luck value (1, 2, or 3). Returns 2 (default) if not found."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT suerte FROM usuarios_tb WHERE id_user = %s", (id_user,))
        resultado = cursor.fetchone()
        return resultado[0] if resultado else 2
    except Exception as e:
        print(f"[ERROR DB] Error getting suerte: {e}")
        return 2
    finally:
        _put_connection(conn)


def set_suerte(id_user: int, valor: int) -> bool:
    """Set a user's luck value (1, 2, or 3)."""
    if valor not in (1, 2, 3):
        print(f"[ERROR DB] Invalid suerte value: {valor}")
        return False

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usuarios_tb SET suerte = %s WHERE id_user = %s",
            (valor, id_user),
        )
        if cursor.rowcount == 0:
            print("[ERROR DB] User not found")
            conn.rollback()
            return False
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error setting suerte: {e}")
        return False
    finally:
        _put_connection(conn)


def consumir_uso_diario(id_user: int, comando: str, fecha: str, limite: int) -> Optional[int]:
    """Atomically consume one daily use and return the new count; None if limit/error."""
    if not comando or limite <= 0:
        return None
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO usos_diarios_tb (id_user, comando, fecha, veces)
            VALUES (%s, %s, %s, 1)
            ON CONFLICT (id_user, comando, fecha) DO UPDATE
            SET veces = usos_diarios_tb.veces + 1
            WHERE usos_diarios_tb.veces < %s
            RETURNING veces
            """,
            (id_user, comando, fecha, limite),
        )
        row = cursor.fetchone()
        if row is None:
            conn.rollback()
            return None
        conn.commit()
        return int(row[0])
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error consuming daily use: {e}")
        return None
    finally:
        _put_connection(conn)


def transferir_puntos_atomico(id_origen: int, id_destino: int, cantidad: int) -> bool:
    """Transfer an exact positive amount atomically without allowing overdrafts."""
    if cantidad <= 0 or id_origen == id_destino:
        return False
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        ids = sorted((id_origen, id_destino))
        cursor.execute(
            "SELECT id_user, saldo FROM usuarios_tb WHERE id_user IN (%s, %s) ORDER BY id_user FOR UPDATE",
            (ids[0], ids[1]),
        )
        rows = dict(cursor.fetchall())
        if id_origen not in rows or id_destino not in rows or int(rows[id_origen]) < cantidad:
            conn.rollback()
            return False
        cursor.execute("UPDATE usuarios_tb SET saldo = saldo - %s WHERE id_user = %s", (cantidad, id_origen))
        cursor.execute("UPDATE usuarios_tb SET saldo = saldo + %s WHERE id_user = %s", (cantidad, id_destino))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error transferring balance: {e}")
        return False
    finally:
        _put_connection(conn)


def transferir_robo_atomico(id_ladron: int, id_victima: int, cantidad_maxima: int) -> Optional[int]:
    """Transfer up to cantidad_maxima from victim to thief atomically; return actual amount."""
    if cantidad_maxima <= 0 or id_ladron == id_victima:
        return 0
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        ids = sorted((id_ladron, id_victima))
        cursor.execute(
            "SELECT id_user, saldo FROM usuarios_tb WHERE id_user IN (%s, %s) ORDER BY id_user FOR UPDATE",
            (ids[0], ids[1]),
        )
        rows = dict(cursor.fetchall())
        if id_ladron not in rows or id_victima not in rows:
            conn.rollback()
            return None
        cantidad = min(int(cantidad_maxima), max(0, int(rows[id_victima])))
        if cantidad == 0:
            conn.commit()
            return 0
        cursor.execute("UPDATE usuarios_tb SET saldo = saldo - %s WHERE id_user = %s", (cantidad, id_victima))
        cursor.execute("UPDATE usuarios_tb SET saldo = saldo + %s WHERE id_user = %s", (cantidad, id_ladron))
        conn.commit()
        return cantidad
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error transferring robbery balance: {e}")
        return None
    finally:
        _put_connection(conn)


# ==================== ITEM OPERATIONS ====================

def insert_item(nombre: str, precio: int, ruta_imagen: str,
                descripcion: Optional[str] = None, mensaje: Optional[str] = None) -> bool:
    """Add a new item to the catalog."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO items_tb (nombre, precio, imagen, descripcion, mensaje) VALUES (%s, %s, %s, %s, %s)",
            (nombre, precio, ruta_imagen, descripcion, mensaje),
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Failed to insert item: {e}")
        return False
    finally:
        _put_connection(conn)


def get_campo_item(id_item: int, columna: str) -> Optional[Any]:
    """Retrieve a specific field from an item."""
    columnas_validas = {"id_item", "nombre", "precio", "imagen", "descripcion", "mensaje"}

    if columna not in columnas_validas:
        print(f"[ERROR DB] Invalid column: {columna}")
        return None

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT {columna} FROM items_tb WHERE id_item = %s", (id_item,))
        resultado = cursor.fetchone()
        return resultado[0] if resultado else None
    except Exception as e:
        print(f"[ERROR DB] Error retrieving item: {e}")
        return None
    finally:
        _put_connection(conn)


def update_item(id_item: int, **datos) -> bool:
    """Update item fields."""
    columnas_validas = {"nombre", "precio", "imagen", "descripcion", "mensaje"}

    if not datos:
        return False

    for col in datos.keys():
        if col not in columnas_validas:
            print(f"[ERROR DB] Invalid column: {col}")
            return False

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        columnas = ", ".join([f"{col} = %s" for col in datos.keys()])
        valores = list(datos.values()) + [id_item]
        cursor.execute(f"UPDATE items_tb SET {columnas} WHERE id_item = %s", valores)
        if cursor.rowcount == 0:
            print("[ERROR DB] Item not found")
            conn.rollback()
            return False
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error updating item: {e}")
        return False
    finally:
        _put_connection(conn)


def get_id_item(nombre: str) -> Optional[int]:
    """Get an item ID by its normalized name."""
    nombre_normalizado = to_plain_text(nombre, True).capitalize()

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id_item FROM items_tb WHERE nombre = %s", (nombre_normalizado,))
        resultado = cursor.fetchone()
        return resultado[0] if resultado else None
    except Exception as e:
        print(f"[ERROR DB] Error getting item ID: {e}")
        return None
    finally:
        _put_connection(conn)


def delete_item(id_item: int) -> bool:
    """Delete an item from catalog (cascading delete)."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM items_tb WHERE id_item = %s", (id_item,))
        success = cursor.rowcount > 0
        conn.commit()
        return success
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error deleting item: {e}")
        return False
    finally:
        _put_connection(conn)


# ==================== INVENTORY OPERATIONS ====================

def insert_user_item(id_user: int, id_item: int, cantidad: int = 1) -> bool:
    """Add an item to user's inventory or increase quantity."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            "SELECT cantidad FROM items_usuarios_tb WHERE id_user = %s AND id_item = %s",
            (id_user, id_item),
        )
        resultado = cursor.fetchone()

        if resultado:
            nueva_cantidad = resultado[0] + cantidad
            cursor.execute(
                "UPDATE items_usuarios_tb SET cantidad = %s WHERE id_user = %s AND id_item = %s",
                (nueva_cantidad, id_user, id_item),
            )
        else:
            cursor.execute(
                "INSERT INTO items_usuarios_tb (id_user, id_item, cantidad) VALUES (%s, %s, %s)",
                (id_user, id_item, cantidad),
            )

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error adding item to inventory: {e}")
        return False
    finally:
        _put_connection(conn)


def get_items(id_user: int) -> List[Dict[str, Any]]:
    """Get all items in a user's inventory."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                items_tb.id_item,
                items_tb.nombre,
                items_tb.precio,
                items_tb.imagen,
                items_usuarios_tb.cantidad
            FROM items_usuarios_tb
            INNER JOIN items_tb ON items_tb.id_item = items_usuarios_tb.id_item
            WHERE items_usuarios_tb.id_user = %s
            ORDER BY items_tb.nombre
        """, (id_user,))

        filas = cursor.fetchall()
        return [
            {
                "id_item": fila[0],
                "nombre": fila[1],
                "precio": fila[2],
                "imagen": fila[3],
                "cantidad": fila[4],
            }
            for fila in filas
        ]
    except Exception as e:
        print(f"[ERROR DB] Error retrieving items: {e}")
        return []
    finally:
        _put_connection(conn)


def get_cantidad_item_inventario(id_user: int, id_item: int) -> int:
    """Get the quantity of a specific item in user's inventory."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT cantidad FROM items_usuarios_tb WHERE id_item = %s AND id_user = %s",
            (id_item, id_user),
        )
        resultado = cursor.fetchone()
        return resultado[0] if resultado else 0
    except Exception as e:
        print(f"[ERROR DB] Error getting item quantity: {e}")
        return 0
    finally:
        _put_connection(conn)


def reservar_item_usuario(id_user: int, id_item: int) -> bool:
    """Atomically reserve one inventory item. Safe against double-click/concurrent /usar calls."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE items_usuarios_tb SET cantidad = cantidad - 1 "
            "WHERE id_user = %s AND id_item = %s AND cantidad > 0 RETURNING cantidad",
            (id_user, id_item),
        )
        row = cursor.fetchone()
        if row is None:
            conn.rollback()
            return False
        if int(row[0]) == 0:
            cursor.execute(
                "DELETE FROM items_usuarios_tb WHERE id_user = %s AND id_item = %s AND cantidad = 0",
                (id_user, id_item),
            )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error reserving inventory item: {e}")
        return False
    finally:
        _put_connection(conn)


def devolver_item_usuario(id_user: int, id_item: int) -> bool:
    """Return one previously reserved item, used when Telegram delivery fails."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO items_usuarios_tb (id_user, id_item, cantidad) VALUES (%s, %s, 1) "
            "ON CONFLICT (id_user, id_item) DO UPDATE SET cantidad = items_usuarios_tb.cantidad + 1",
            (id_user, id_item),
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error returning inventory item: {e}")
        return False
    finally:
        _put_connection(conn)


def update_cantidad(user_id: int, item_id: int, cantidad: int) -> bool:
    """Update the quantity of an item in user's inventory."""
    if cantidad < 0:
        print("[ERROR DB] Quantity cannot be negative")
        return False

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE items_usuarios_tb SET cantidad = %s WHERE id_user = %s AND id_item = %s",
            (cantidad, user_id, item_id),
        )
        if cursor.rowcount == 0:
            print("[ERROR DB] Item not found in user inventory")
            conn.rollback()
            return False
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error updating quantity: {e}")
        return False
    finally:
        _put_connection(conn)


def delete_item_user(id_user: int, id_item: int) -> bool:
    """Remove an item from user's inventory."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM items_usuarios_tb WHERE id_user = %s AND id_item = %s",
            (id_user, id_item),
        )
        if cursor.rowcount == 0:
            print("[ERROR DB] Item not found in user inventory")
            conn.rollback()
            return False
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error deleting item: {e}")
        return False
    finally:
        _put_connection(conn)


# ==================== USER DELETE ====================

def delete_user(id_user: int) -> bool:
    """Delete a user and all associated data (cascading delete)."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usuarios_tb WHERE id_user = %s", (id_user,))
        success = cursor.rowcount > 0
        conn.commit()
        return success
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error deleting user: {e}")
        return False
    finally:
        _put_connection(conn)


# ==================== USER LOOKUP ====================

def get_id_user(username: str) -> Optional[int]:
    """Get user ID by username."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id_user FROM perfiles_tb WHERE username = %s",
            (username,),
        )
        resultado = cursor.fetchone()
        return resultado[0] if resultado else None
    except Exception as e:
        print(f"[ERROR DB] Error getting user ID: {e}")
        return None
    finally:
        _put_connection(conn)


# ==================== ROLE OPERATIONS ====================

def get_user_role(id_user: int) -> int:
    """
    Get a user's internal role level.

    Returns:
        1 = User (default), 2 = Admin, 3 = BotMaster
        Returns 0 if user not found.
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM roles_tb WHERE id_user = %s", (id_user,))
        resultado = cursor.fetchone()
        return resultado[0] if resultado else 0
    except Exception as e:
        print(f"[ERROR DB] Error getting user role: {e}")
        return 0
    finally:
        _put_connection(conn)


def set_user_role(id_user: int, role: int) -> bool:
    """
    Set a user's internal role.

    Args:
        id_user: User's Telegram ID
        role: 1=User, 2=Admin, 3=BotMaster
    """
    if role not in (1, 2, 3):
        print(f"[ERROR DB] Invalid role: {role}")
        return False

    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO roles_tb (id_user, role) VALUES (%s, %s) "
            "ON CONFLICT (id_user) DO UPDATE SET role = %s",
            (id_user, role, role),
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error setting user role: {e}")
        return False
    finally:
        _put_connection(conn)


def check_permission(id_user: int, min_role: int) -> bool:
    """
    Check if user has at least the specified role level.

    Args:
        id_user: User's Telegram ID
        min_role: Minimum required role (2=Admin, 3=BotMaster)
    """
    return get_user_role(id_user) >= min_role


# ==================== COMBAT OPERATIONS ====================


def is_botmaster(id_user: int) -> bool:
    """Role 3 is the universal in-bot superuser."""
    try:
        return get_user_role(int(id_user)) >= 3
    except Exception:
        return False

def restart_all_combats():
    """Cancel active combats on startup and refund their already-reserved wagers atomically."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id_combate, id_atacante, id_defensor, apuesta FROM combates_tb WHERE estado = 'activo' FOR UPDATE"
        )
        rows = cursor.fetchall()
        for id_combate, id_atacante, id_defensor, apuesta in rows:
            if apuesta > 0:
                cursor.execute(
                    "UPDATE usuarios_tb SET saldo = saldo + %s WHERE id_user IN (%s, %s)",
                    (apuesta, id_atacante, id_defensor),
                )
                if cursor.rowcount != 2:
                    raise RuntimeError(f"No se pudo reembolsar el combate {id_combate}")
            cursor.execute(
                "UPDATE combates_tb SET estado = 'cancelado' WHERE id_combate = %s AND estado = 'activo'",
                (id_combate,),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"No se pudo cancelar el combate {id_combate}")
        conn.commit()
        if rows:
            print(f"[INIT] Reset {len(rows)} active combats and refunded reserved wagers")
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error restarting combats: {e}")
    finally:
        _put_connection(conn)


# ==================== TEXT UTILITY FUNCTIONS ====================

def normalizar_nombre(first_name: str, last_name: str = "") -> str:
    """Normalize and clean user names."""
    nombre_completo = f"{to_plain_text(first_name) or ''} {to_plain_text(last_name) or ''}".strip()
    nombre_completo = re.sub(r'[^A-Za-z0-9\u00C1\u00C9\u00CD\u00D3\u00DA\u00E1\u00E9\u00ED\u00F3\u00FA\u00D1\u00F1\u00DC\u00FC ]+', '', nombre_completo)
    nombre_completo = unicodedata.normalize("NFKD", nombre_completo)
    nombre_completo = ''.join(
        c for c in nombre_completo
        if not unicodedata.combining(c)
    )
    nombre_completo = re.sub(r'\s+', ' ', nombre_completo).strip().lower()
    return nombre_completo


def to_plain_text(s: str, keep_space: bool = False) -> str:
    """Convert text to plain ASCII, removing accents and special characters."""
    if not isinstance(s, str):
        return ""

    out_chars = []
    try:
        for ch in s:
            ch_nfd = unicodedata.normalize("NFKD", ch)
            for ch2 in ch_nfd:
                cat = unicodedata.category(ch2)
                if cat.startswith("M"):
                    continue
                if cat in ("Cc", "Cf"):
                    continue
                if '0' <= ch2 <= '9' or 'A' <= ch2 <= 'Z' or 'a' <= ch2 <= 'z':
                    out_chars.append(ch2)
                    continue
                try:
                    name = unicodedata.name(ch2)
                except ValueError:
                    name = ""
                if "LATIN" in name and "LETTER" in name:
                    m = re.search(r"LETTER\s+([A-Z]+[A-Z0-9]*)$", name)
                    if m:
                        for c in m.group(1):
                            if 'A' <= c <= 'Z':
                                out_chars.append(c)
                        continue
                if cat.startswith("Z"):
                    out_chars.append(" ")

        text = "".join(out_chars)
        if keep_space:
            text = re.sub(r"\s+", " ", text).strip()
            text = re.sub(r"[^0-9A-Za-z ]+", "", text)
        else:
            text = re.sub(r"[^0-9A-Za-z]+", "", text)
        return reemplazar_acentos(text.lower())
    except TypeError:
        return ""


def reemplazar_acentos(cadena: str) -> str:
    """Replace accented characters with their base forms."""
    reemplazos = (
        ("\u00e1", "a"), ("\u00e9", "e"), ("\u00ed", "i"), ("\u00f3", "o"), ("\u00fa", "u"),
        ("\u00c1", "A"), ("\u00c9", "E"), ("\u00cd", "I"), ("\u00d3", "O"), ("\u00da", "U"),
    )
    for acentuada, normalizada in reemplazos:
        cadena = cadena.replace(acentuada, normalizada)
    return cadena
