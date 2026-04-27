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
from psycopg2 import pool as pg_pool

from src.config import DATABASE_URL

# ==================== CONNECTION POOL ====================

_connection_pool = None
def _init_pool():
    """Initialize the PostgreSQL connection pool."""
    global _connection_pool
    if _connection_pool is None:
        print("[DB] Iniciando intento de conexión a Supabase...")
        try:
            start_time = time.time()
            _connection_pool = pg_pool.SimpleConnectionPool(
                1, 10, 
                DATABASE_URL,
                sslmode="require",
                connect_timeout=10
            )
            print(f"[DB] ¡POOL CREADO EXITOSAMENTE! Tiempo: {time.time() - start_time:.2f}s")
        except Exception as e:
            print(f"[DB ERROR] No se pudo crear el pool: {str(e)}")

def _get_connection():
    """Get a connection from the pool."""
    _init_pool()
    return _connection_pool.getconn()


def _put_connection(conn):
    """Return a connection to the pool."""
    if _connection_pool:
        _connection_pool.putconn(conn)


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
                fecha_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_combate_atacante ON combates_tb(id_atacante);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_combate_defensor ON combates_tb(id_defensor);")

        # Internal role system
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roles_tb (
                id_user BIGINT PRIMARY KEY REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                role INTEGER NOT NULL DEFAULT 1 CHECK (role IN (1, 2, 3))
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
            "precio": 100,
            "imagen": "img_items/collar.png",
            "descripcion": "Un bonito collar para poner a alguien especial",
            "mensaje": "😈 {sender_username} le ha puesto un collar muy bonito a {receptor_username} 😍\n ¡Qué envidiaaa!",
        },
        {
            "nombre": "Latigo",
            "precio": 150,
            "imagen": "img_items/latigo.png",
            "descripcion": "Un látigo para los que se portan mal",
            "mensaje": "😱 {sender_username} ha azotado con un látigo a {receptor_username} \n ... Eso va a dejar marca 🫦",
        },
        {
            "nombre": "Fusta",
            "precio": 120,
            "imagen": "img_items/fusta.png",
            "descripcion": "Fusta de adiestramiento profesional",
            "mensaje": "🤩 {sender_username} está adiestrando a {receptor_username} con su fusta favorita 😈\n ¿Porqué parece que {receptor_username} lo disfruta?... 🫦",
        },
        {
            "nombre": "Galleta",
            "precio": 50,
            "imagen": "img_items/galleta.png",
            "descripcion": "Una galleta para premiar el buen comportamiento",
            "mensaje": "❤ {sender_username} le ha regalado a {receptor_username} una galleta 🍪\n Parece que se ha portado muy bien 🤤",
        },
        {
            "nombre": "Bola mordaza",
            "precio": 200,
            "imagen": "img_items/bola_mordaza.png",
            "descripcion": "Para cuando alguien habla demasiado",
            "mensaje": "🤏 {sender_username} Le ha puesto una bola mordaza a {receptor_username}\n Que bien te ves sin poder hablar 😖",
        },
        {
            "nombre": "Sorpresa",
            "precio": 300,
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
                    "UPDATE items_tb SET descripcion = %s, mensaje = %s WHERE nombre = %s",
                    (item["descripcion"], item["mensaje"], item["nombre"]),
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


def update_perfil(id_user: int, **datos) -> bool:
    """Update user profile fields."""
    columnas_validas = {
        "nombre", "username", "rol", "orientacion_sexual",
        "genero", "ubicacion", "edad",
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
    """Add points to a user's balance."""
    saldo_actual = get_campo_usuario(id_user, "saldo") or 0
    return update_saldo(id_user, saldo_actual + cantidad)


def quitar_puntos(id_user: int, cantidad: int) -> bool:
    """Remove points from a user's balance."""
    saldo_actual = get_campo_usuario(id_user, "saldo") or 0
    nuevo_saldo = max(0, saldo_actual - cantidad)
    return update_saldo(id_user, nuevo_saldo)


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

def restart_all_combats():
    """Reset all active combats to 'cancelado' on startup."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE combates_tb SET estado = 'cancelado' WHERE estado = 'activo'")
        affected = cursor.rowcount
        conn.commit()
        if affected > 0:
            print(f"[INIT] Reset {affected} active combats")
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
