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


def cancelar_combate_activo_atomico(id_combate: int, actor_id: int):
    conn=_get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT id_atacante,id_defensor,apuesta,estado FROM combates_tb WHERE id_combate=%s FOR UPDATE",(id_combate,))
            row=cursor.fetchone()
            if not row: conn.rollback(); return "missing"
            atacante,defensor,apuesta,estado=row
            if actor_id not in (atacante,defensor): conn.rollback(); return "forbidden"
            if estado != "activo": conn.rollback(); return "closed"
            cursor.execute("UPDATE combates_tb SET estado='cancelado' WHERE id_combate=%s AND estado='activo'",(id_combate,))
            if cursor.rowcount != 1: conn.rollback(); return "closed"
            if apuesta > 0:
                cursor.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(apuesta,atacante))
                if cursor.rowcount != 1: conn.rollback(); return "error"
                cursor.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(apuesta,defensor))
                if cursor.rowcount != 1: conn.rollback(); return "error"
        conn.commit(); return "cancelled"
    except Exception as exc:
        conn.rollback(); print(f"[ERROR DB] Error cancelling combat: {exc}"); return "error"
    finally: _put_connection(conn)


# ==================== BATTLE COMMANDS ====================

async def lucha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Abre una lucha pública en el tema. Uso: /lucha cantidad."""
    sender=update.effective_user; name=sender.username or sender.first_name or f"Usuario{sender.id}"
    if sender.id in pending_challenges: return await update.message.reply_text("⚔️ Ya tienes un desafío abierto. Usa /cancelarlucha o espera 60 segundos.")
    if get_combate_activo(sender.id): return await update.message.reply_text("⚔️ Ya estás en un combate activo.")
    if not context.args: return await update.message.reply_text("📋 Uso: /lucha cantidad\nEjemplo: /lucha 1000\n\n⚔️ Queda abierta 60 segundos y cualquier otra persona del mismo tema puede entrar con /aceptarlucha.")
    try: apuesta=int(str(context.args[0]).replace(',',''))
    except Exception: apuesta=0
    if apuesta<=0: return await update.message.reply_text("❌ La apuesta debe ser un número mayor a 0.")
    if (get_campo_usuario(sender.id,"saldo") or 0)<apuesta: return await update.message.reply_text("💸 No tienes saldo suficiente para esa apuesta.")
    chat=update.effective_chat.id; thread=update.message.message_thread_id
    if any(x.get("chat_id")==chat and x.get("message_thread_id")==thread for x in pending_challenges.values()): return await update.message.reply_text("⚔️ Ya hay una lucha abierta en este tema. Acéptala con /aceptarlucha.")
    stamp=datetime.now(); pending_challenges[sender.id]={"opponent_id":None,"apuesta":apuesta,"timestamp":stamp,"chat_id":chat,"message_thread_id":thread,"challenger_name":name}
    await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f"⚔️ ¡DESAFÍO ABIERTO!\n\n🥊 {name} abre una batalla\n💰 Apuesta: {apuesta:,} PiPesos por jugador\n⏱️ 60 segundos\n\nCualquier otra persona puede entrar con /aceptarlucha")
    async def timeout_challenge():
        await asyncio.sleep(60); cur=pending_challenges.get(sender.id)
        if cur and cur.get("timestamp")==stamp:
            pending_challenges.pop(sender.id,None)
            try: await context.bot.send_message(chat_id=chat,message_thread_id=thread,text="⏱️ Nadie aceptó la lucha. Se cerró sin cobrar PiPesos.")
            except Exception: pass
    asyncio.create_task(timeout_challenge())


async def cancelar_lucha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; chat=update.effective_chat.id; thread=update.message.message_thread_id
    challenge=pending_challenges.get(uid)
    if challenge is not None:
        if chat!=challenge.get("chat_id") or thread!=challenge.get("message_thread_id"): return await update.message.reply_text("⚠️ Cancela la lucha en el mismo tema donde fue creada.")
        pending_challenges.pop(uid,None); return await update.message.reply_text("🛑 Desafío cancelado. No se había cobrado ningún PiPeso.")
    combate=get_combate_activo(uid)
    if not combate: return await update.message.reply_text("ℹ️ No tienes una lucha pendiente ni un combate activo.")
    if chat!=combate.get("chat_id") or thread!=combate.get("message_thread_id"): return await update.message.reply_text("⚠️ Cancela la lucha en el mismo tema donde está ocurriendo.")
    result=cancelar_combate_activo_atomico(combate["id_combate"],uid)
    if result=="cancelled": return await update.message.reply_text(f"🛑 Combate cancelado. Se devolvieron {combate['apuesta']:,} PiPesos a cada jugador.")
    if result=="closed": return await update.message.reply_text("ℹ️ Esa lucha ya terminó o fue cancelada.")
    await update.message.reply_text("⚠️ No pude cancelar la lucha de forma segura; no se hizo ningún reembolso parcial.")


async def aceptar_lucha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user=update.effective_user; uid=user.id; chat=update.effective_chat.id; thread=update.message.message_thread_id
    challenge=None; challenger_id=None
    for cid,data in list(pending_challenges.items()):
        if data.get("chat_id")==chat and data.get("message_thread_id")==thread: challenge=data; challenger_id=cid; break
    if not challenge: return await update.message.reply_text("❌ No hay una lucha abierta en este tema. Alguien debe usar /lucha cantidad primero.")
    if challenger_id==uid: return await update.message.reply_text("😂 No puedes aceptar tu propia lucha.")
    if datetime.now()-challenge["timestamp"]>timedelta(seconds=60): pending_challenges.pop(challenger_id,None); return await update.message.reply_text("⏱️ Ese desafío ya expiró.")
    if get_combate_activo(uid): return await update.message.reply_text("⚔️ Ya estás en un combate activo.")
    apuesta=challenge["apuesta"]
    if not reservar_apuesta_doble(challenger_id,uid,apuesta): return await update.message.reply_text("💸 No se pudo reservar la apuesta: uno de los dos ya no tiene saldo suficiente.")
    pending_challenges.pop(challenger_id,None)
    challenger_name=challenge.get("challenger_name") or get_campo_usuario(challenger_id,"username") or f"Usuario{challenger_id}"
    user_name=user.username or user.first_name or f"Usuario{uid}"
    combat_id=crear_combate(challenger_id,uid,challenger_name,user_name,apuesta,chat,thread)
    if combat_id==-1:
        reembolsar_apuesta_doble(challenger_id,uid,apuesta); return await update.message.reply_text("⚠️ No pude crear el combate. La reserva fue devuelta.")
    await update.message.reply_text(f"⚔️ ¡LUCHA ACEPTADA!\n🥊 {challenger_name} vs {user_name}\n💰 Pozo: {apuesta*2:,} PiPesos\n❤️ 20 HP cada uno\n\n🎲 Turno de {challenger_name}. Lanza el dado de Telegram.")






# Keep old 'ataque' function for compatibility (unused now)
async def ataque(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Obsolete - use dice emoji 🎲 instead"""
    await update.message.reply_text("Este comando ya no se usa. Lanza un dado 🎲 en tu turno.")

