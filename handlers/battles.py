"""
Battle/Combat system handler for PiBot.

Refactored battle system with:
- Challenge phase (/lucha [@usuario] [cantidad])
- 60-second acceptance phase (/aceptar lucha)
- Turn-based combat with dice rolls
- Dice emoji as damage system
"""

import asyncio
import random
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from src.database.database import (
    get_campo_usuario, update_saldo, dar_puntos, quitar_puntos,
    _get_connection, _put_connection, reservar_apuesta_doble, reembolsar_apuesta_doble
)


# ==================== IN-MEMORY BATTLE STATE ====================
# Pending challenges preserve the group/topic where /lucha was created.
pending_challenges = {}


# ==================== DATABASE OPERATIONS ====================

def crear_combate(id_atacante: int, id_defensor: int, username_atacante: str,
                  username_defensor: str, apuesta: int, chat_id: int = None,
                  message_thread_id: int = None) -> int:
    """
    Create a new battle in the database.
    
    Returns:
        Combat ID or -1 if failed
    """
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO combates_tb 
            (id_atacante, id_defensor, username_atacante, username_defensor, apuesta, hp_atacante, hp_defensor, chat_id, message_thread_id)
            VALUES (%s, %s, %s, %s, %s, 20, 20, %s, %s)
            RETURNING id_combate
        """, (id_atacante, id_defensor, username_atacante, username_defensor, apuesta, chat_id, message_thread_id))
        
        combat_id = cursor.fetchone()[0]
        conn.commit()
        return combat_id
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Failed to create battle: {e}")
        return -1
    finally:
        _put_connection(conn)


def get_combate_activo(id_user: int) -> dict:
    """Get active combat for a user (as attacker or defender)."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM combates_tb 
            WHERE (id_atacante = %s OR id_defensor = %s) 
            AND estado = 'activo'
            LIMIT 1
        """, (id_user, id_user))
        
        resultado = cursor.fetchone()
        
        if not resultado:
            return None
        
        return {
            'id_combate': resultado[0],
            'id_atacante': resultado[1],
            'id_defensor': resultado[2],
            'username_atacante': resultado[3],
            'username_defensor': resultado[4],
            'apuesta': resultado[5],
            'hp_atacante': resultado[6],
            'hp_defensor': resultado[7],
            'turno': resultado[8],
            'es_turno_atacante': resultado[9],
            'estado': resultado[10],
            'ganador': resultado[11],
            'fecha_inicio': resultado[12],
            'chat_id': resultado[13] if len(resultado) > 13 else None,
            'message_thread_id': resultado[14] if len(resultado) > 14 else None
        }
    except Exception as e:
        print(f"[ERROR DB] Error getting active combat: {e}")
        return None
    finally:
        _put_connection(conn)


def actualizar_combate(id_combate: int, **datos) -> bool:
    """Update combat fields."""
    columnas_validas = {
        "hp_atacante", "hp_defensor", "turno", "es_turno_atacante", "estado", "ganador"
    }
    
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
        valores = list(datos.values()) + [id_combate]
        
        cursor.execute(f"UPDATE combates_tb SET {columnas} WHERE id_combate = %s", valores)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error updating combat: {e}")
        return False
    finally:
        _put_connection(conn)


def terminar_combate(id_combate: int, id_ganador: int) -> bool:
    """Finalize an active combat and pay its reserved pot exactly once."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT apuesta, id_atacante, id_defensor, estado FROM combates_tb WHERE id_combate = %s FOR UPDATE",
            (id_combate,),
        )
        row = cursor.fetchone()
        if not row:
            conn.rollback()
            return False
        apuesta, id_atacante, id_defensor, estado = row
        if estado != "activo" or id_ganador not in (id_atacante, id_defensor):
            conn.rollback()
            return False
        cursor.execute(
            "UPDATE combates_tb SET estado = 'finalizado', ganador = %s WHERE id_combate = %s AND estado = 'activo'",
            (id_ganador, id_combate),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return False
        if apuesta > 0:
            cursor.execute(
                "UPDATE usuarios_tb SET saldo = saldo + %s WHERE id_user = %s",
                (apuesta * 2, id_ganador),
            )
            if cursor.rowcount != 1:
                conn.rollback()
                return False
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[ERROR DB] Error ending combat: {e}")
        return False
    finally:
        _put_connection(conn)


def get_combate_by_id(id_combate: int) -> dict:
    """Get combat by ID."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM combates_tb WHERE id_combate = %s", (id_combate,))
        resultado = cursor.fetchone()
        
        if not resultado:
            return None
        
        return {
            'id_combate': resultado[0],
            'id_atacante': resultado[1],
            'id_defensor': resultado[2],
            'username_atacante': resultado[3],
            'username_defensor': resultado[4],
            'apuesta': resultado[5],
            'hp_atacante': resultado[6],
            'hp_defensor': resultado[7],
            'turno': resultado[8],
            'es_turno_atacante': resultado[9],
            'estado': resultado[10],
            'ganador': resultado[11],
            'fecha_inicio': resultado[12],
            'chat_id': resultado[13] if len(resultado) > 13 else None,
            'message_thread_id': resultado[14] if len(resultado) > 14 else None
        }
    except Exception as e:
        print(f"[ERROR DB] Error getting combat by ID: {e}")
        return None
    finally:
        _put_connection(conn)


# ==================== BATTLE COMMANDS ====================

async def lucha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Start a battle challenge with another user.
    Syntax: /lucha [@username] [cantidad]
    
    The opponent has 60 seconds to accept with /aceptar lucha
    """
    sender = update.effective_user
    sender_username = sender.username or f"Usuario{sender.id}"
    
    # Check if sender already has a pending challenge or active combat
    if sender.id in pending_challenges:
        await update.message.reply_text(
            "⚔️ Ya tienes un desafío pendiente.\n"
            "Espera a que sea aceptado o rechazado."
        )
        return
    
    if get_combate_activo(sender.id):
        await update.message.reply_text(
            "⚔️ Ya estás en un combate activo.\n"
            "Termina el combate antes de retarme a otro."
        )
        return
    
    # Parse arguments
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📋 Uso: /lucha @usuario cantidad\n"
            "Ejemplo: /lucha @juan 50\n\n"
            "⚔️ Cómo funciona:\n"
            "1️⃣ Retar a alguien (tiene 60s para aceptar)\n"
            "2️⃣ Si acepta, inicia el combate\n"
            "3️⃣ Lanzan dados por turnos alternados\n"
            "4️⃣ Lanza el dado 🎲 (el resultado es el daño)\n"
            "5️⃣ Primero en llegar a 0 HP pierde\n"
            "💰 El ganador se queda con la apuesta doble"
        )
        return
    
    # Get opponent username
    opponent_username = context.args[0].replace("@", "")
    
    # Get opponent ID
    from src.database.database import get_id_user
    opponent_id = get_id_user(opponent_username)
    
    if not opponent_id:
        await update.message.reply_text(f"❌ No encontré a @{opponent_username}")
        return
    
    if opponent_id == sender.id:
        await update.message.reply_text("❌ No puedes retarte a ti mismo")
        return
    
    # Check if opponent already has a pending challenge or active combat
    if opponent_id in pending_challenges or get_combate_activo(opponent_id):
        await update.message.reply_text(
            f"❌ @{opponent_username} ya está en un combate o tiene un desafío pendiente"
        )
        return
    
    # Get bet amount
    try:
        apuesta = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ La apuesta debe ser un número")
        return
    
    if apuesta <= 0:
        await update.message.reply_text("❌ La apuesta debe ser mayor a 0")
        return
    
    # Check balance
    saldo_atacante = get_campo_usuario(sender.id, "saldo") or 0
    saldo_defensor = get_campo_usuario(opponent_id, "saldo") or 0
    
    if saldo_atacante < apuesta:
        await update.message.reply_text(
            f"❌ Saldo insuficiente\n"
            f"Tienes: {saldo_atacante} PiPesos | Necesitas: {apuesta}"
        )
        return
    
    if saldo_defensor < apuesta:
        await update.message.reply_text(
            f"❌ @{opponent_username} no tiene suficientes PiPesos\n"
            f"Tiene: {saldo_defensor} | Necesita: {apuesta}"
        )
        return
    
    # Reserve both bets atomically. No partial charge is possible.
    if not reservar_apuesta_doble(sender.id, opponent_id, apuesta):
        await update.message.reply_text(
            "❌ No se pudo reservar la apuesta. Verifica que ambos sigan teniendo saldo suficiente."
        )
        return
    
    # Store challenge in memory
    pending_challenges[sender.id] = {
        "opponent_id": opponent_id,
        "opponent_username": opponent_username,
        "apuesta": apuesta,
        "timestamp": datetime.now(),
        "chat_id": update.effective_chat.id,
        "message_thread_id": update.message.message_thread_id
    }
    
    # Send challenge message to opponent
    challenge_msg = (
        f"⚔️ **¡DESAFÍO DE LUCHA!**\n\n"
        f"🥊 {sender_username} te reta a batalla\n"
        f"💰 Apuesta: {apuesta} PiPesos para cada uno\n\n"
        f"⏱️ Tienes 60 segundos para aceptar\n"
        f"Escribe: /aceptarlucha"
    )
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        message_thread_id=update.message.message_thread_id,
        text=challenge_msg,
        parse_mode='Markdown'
    )
    
    # Setup 60-second timeout
    async def timeout_challenge():
        await asyncio.sleep(60)
        if sender.id in pending_challenges:
            # Challenge expired
            del pending_challenges[sender.id]
            
            # Return both reserved bets atomically
            reembolsar_apuesta_doble(sender.id, opponent_id, apuesta)
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                message_thread_id=update.message.message_thread_id,
                text=f"⏱️ @{opponent_username} no aceptó el desafío de {sender_username}. Se devolvieron {apuesta} PiPesos a cada jugador."
            )
    
    asyncio.create_task(timeout_challenge())


async def aceptar_lucha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Accept a battle challenge.
    Syntax: /aceptarlucha
    """
    user = update.effective_user
    user_id = user.id
    user_username = user.username or f"Usuario{user_id}"
    
    # Check if there's a challenge for this user
    challenge = None
    challenger_id = None
    
    for chall_id, chall_data in pending_challenges.items():
        if chall_data["opponent_id"] == user_id:
            challenge = chall_data
            challenger_id = chall_id
            break
    
    if not challenge:
        await update.message.reply_text(
            "❌ No tienes ningún desafío pendiente\n"
            "Alguien debe retarte primero con /lucha"
        )
        return

    # A challenge can only be accepted in the exact chat/topic where it was created.
    if (update.effective_chat.id != challenge.get("chat_id") or
            update.message.message_thread_id != challenge.get("message_thread_id")):
        await update.message.reply_text("⚠️ Debes aceptar la lucha en el mismo tema donde te retaron.")
        return
    
    # Check timeout (60 seconds)
    time_elapsed = datetime.now() - challenge["timestamp"]
    if time_elapsed > timedelta(seconds=60):
        # Challenge expired
        if challenger_id in pending_challenges:
            del pending_challenges[challenger_id]
        
        reembolsar_apuesta_doble(challenger_id, user_id, challenge["apuesta"])
        await update.message.reply_text("⏱️ Este desafío ya expiró. Las apuestas fueron devueltas.")
        return
    
    # Remove challenge from pending
    del pending_challenges[challenger_id]
    
    # Get challenger info
    challenger_username = get_campo_usuario(challenger_id, "username")
    if not challenger_username:
        challenger_username = f"Usuario{challenger_id}"
    
    apuesta = challenge["apuesta"]
    
    # Create combat
    combat_id = crear_combate(
        challenger_id, user_id,
        challenger_username,
        user_username,
        apuesta,
        challenge.get("chat_id"),
        challenge.get("message_thread_id")
    )
    
    if combat_id == -1:
        await update.message.reply_text("❌ Error al crear el combate")
        # Refund both reserved bets as one transaction
        reembolsar_apuesta_doble(challenger_id, user_id, apuesta)
        return
    
    # Get combat details
    combate = get_combate_by_id(combat_id)
    
    # Start combat message
    start_msg = (
        f"⚔️ **¡COMBATE INICIADO!**\n\n"
        f"🥊 {combate['username_atacante']} vs {combate['username_defensor']}\n"
        f"❤️ HP: 20 vs 20\n"
        f"💰 Apuesta: {apuesta} PiPesos para cada jugador\n\n"
        f"📊 Primer turno: @{combate['username_atacante']}\n"
        f"🎲 Lanza el dado 🎲 para atacar"
    )
    
    # El combate vive en el mismo chat/tema donde se creó el desafío.
    await context.bot.send_message(
        chat_id=challenge["chat_id"],
        message_thread_id=challenge.get("message_thread_id"),
        text=start_msg,
        parse_mode='Markdown'
    )




# Keep old 'ataque' function for compatibility (unused now)
async def ataque(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsolete - use dice emoji 🎲 instead"""
    await update.message.reply_text("Este comando ya no se usa. Lanza un dado 🎲 en tu turno.")

