"""Silent 30-minute presentation watchdog for the main community.

Rose owns welcome messages. PiBot only records genuinely new users before the
legacy auto-registration handler runs, marks a presentation when the existing
presentation flow sees it, and removes overdue newcomers.
"""
from datetime import datetime, timezone
import random
import os
from telegram import Update
from telegram.ext import ContextTypes

from src.database.database import _get_connection, _put_connection, get_usuario_resumen
from src.config import KIU_ROOT_ID, KIU_ROOT_USERNAME
from src.utils.display_name import visible_user

MAIN_CHAT_ID = -1003290179217
TIMEOUT_MINUTES = 30
PROMPT_DELAY_SECONDS = max(2, int(os.getenv("PRESENTATION_PROMPT_DELAY_SECONDS", "8")))


def ensure_presentation_tables():
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS presentation_watchdog_tb (
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    deadline_at TIMESTAMPTZ NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','presented','removed','cancelled')),
                    presented_at TIMESTAMPTZ,
                    removed_at TIMESTAMPTZ,
                    PRIMARY KEY (chat_id, user_id)
                )
            """)
            cur.execute("ALTER TABLE presentation_watchdog_tb ADD COLUMN IF NOT EXISTS verification_phrase TEXT")
            cur.execute("""CREATE TABLE IF NOT EXISTS presentation_settings_tb (
                chat_id BIGINT PRIMARY KEY,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_presentation_pending_deadline ON presentation_watchdog_tb(status, deadline_at)")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        _put_connection(conn)


def _presentation_enabled(chat_id: int) -> bool:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT enabled FROM presentation_settings_tb WHERE chat_id=%s", (chat_id,))
            row = cur.fetchone()
            return True if row is None else bool(row[0])
    except Exception:
        return True
    finally:
        _put_connection(conn)


def _new_phrase() -> str:
    starts = ["Una buena conversación", "La confianza", "Una noche tranquila", "Conocer gente nueva", "Una historia interesante", "Una comunidad sana"]
    ends = ["empieza con respeto", "se construye poco a poco", "siempre deja algo bueno", "merece un buen comienzo", "también necesita paciencia", "comienza escuchando"]
    return f"{random.choice(starts)} {random.choice(ends)} {random.randint(10, 99)}"


def _set_presentations_enabled(chat_id: int, enabled: bool):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO presentation_settings_tb(chat_id,enabled) VALUES(%s,%s)
                           ON CONFLICT(chat_id) DO UPDATE SET enabled=EXCLUDED.enabled,updated_at=NOW()""", (chat_id, enabled))
            if not enabled:
                cur.execute("UPDATE presentation_watchdog_tb SET status='cancelled' WHERE chat_id=%s AND status='pending'", (chat_id,))
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        _put_connection(conn)


def _create_pending_if_new(chat_id: int, user_id: int) -> bool:
    # Cada entrada/reentrada inicia un plazo nuevo de 30 minutos.
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO presentation_watchdog_tb(chat_id,user_id,deadline_at,status,verification_phrase)
                VALUES (%s,%s,NOW() + (%s || ' minutes')::interval,'pending',%s)
                ON CONFLICT (chat_id,user_id) DO UPDATE SET
                    joined_at=NOW(), deadline_at=EXCLUDED.deadline_at, status='pending',
                    presented_at=NULL, removed_at=NULL, verification_phrase=EXCLUDED.verification_phrase
            """, (chat_id, user_id, TIMEOUT_MINUTES, _new_phrase()))
        conn.commit(); return True
    except Exception:
        conn.rollback(); return False
    finally:
        _put_connection(conn)


def mark_presented(chat_id: int, user_id: int) -> bool:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE presentation_watchdog_tb
                   SET status='presented', presented_at=NOW()
                 WHERE chat_id=%s AND user_id=%s AND status='pending'
            """, (chat_id, user_id))
            changed = cur.rowcount == 1
        conn.commit(); return changed
    except Exception:
        conn.rollback(); return False
    finally:
        _put_connection(conn)


def _get_phrase(chat_id: int, user_id: int):
    conn=_get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT verification_phrase FROM presentation_watchdog_tb WHERE chat_id=%s AND user_id=%s AND status='pending'",(chat_id,user_id))
            row=cur.fetchone(); return row[0] if row else None
    finally: _put_connection(conn)


async def _send_voice_prompt(context: ContextTypes.DEFAULT_TYPE):
    data=context.job.data or {}; chat_id=data.get('chat_id'); user_id=data.get('user_id')
    if not chat_id or not user_id or not _presentation_enabled(chat_id): return
    phrase=_get_phrase(chat_id,user_id)
    if not phrase: return
    label=visible_user(user_id=user_id)
    try:
        await context.bot.send_message(chat_id=chat_id, text=(
            f"🎙️ {label}, para completar tu presentación envíala como nota de voz siguiendo los datos indicados por Rose.\n\n"
            f"Al final di esta frase:\n«{phrase}»\n\nTienes {TIMEOUT_MINUTES} minutos desde tu entrada."
        ))
    except Exception as exc: print(f"[PRESENTACION VOZ] {exc}")


async def presentaciones_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user=update.effective_user
    is_owner = bool(user and ((KIU_ROOT_ID and user.id == KIU_ROOT_ID) or (not KIU_ROOT_ID and KIU_ROOT_USERNAME and (user.username or '').lower() == KIU_ROOT_USERNAME)))
    if not is_owner: return
    chat_id=MAIN_CHAT_ID
    arg=(context.args[0].lower() if context.args else 'estado')
    if arg in ('on','activar','encender'):
        _set_presentations_enabled(chat_id,True); text='🟢 Presentaciones ACTIVADAS. Voz, frase y control de 30 minutos activos.'
    elif arg in ('off','desactivar','apagar'):
        _set_presentations_enabled(chat_id,False); text='🔴 Presentaciones DESACTIVADAS. No se pedirán voces ni se retirará a nadie por presentación. DANTE sigue independiente.'
    else:
        text=f"🚪 Presentaciones: {'ACTIVADAS' if _presentation_enabled(chat_id) else 'DESACTIVADAS'}"
    await update.effective_message.reply_text(text)


async def silent_new_member_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or update.effective_chat.id != MAIN_CHAT_ID:
        return
    # DANTE remains independent; presentation control may be switched off.
    if not _presentation_enabled(MAIN_CHAT_ID):
        return
    for member in (msg.new_chat_members or []):
        if not member.is_bot and _create_pending_if_new(MAIN_CHAT_ID, member.id):
            # Rose welcomes first. PiBot follows shortly after without blocking update handling.
            context.job_queue.run_once(_send_voice_prompt, when=PROMPT_DELAY_SECONDS, data={'chat_id': MAIN_CHAT_ID, 'user_id': member.id}, name=f'presentation_voice_{MAIN_CHAT_ID}_{member.id}')
    # Deliberately no general welcome: Rose owns it.



async def detect_presentation_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Complete presentation only from a fresh Telegram voice note in Presentaciones."""
    msg=update.effective_message; chat=update.effective_chat; user=update.effective_user
    if not msg or not chat or not user or user.is_bot or chat.id != MAIN_CHAT_ID or not _presentation_enabled(chat.id): return
    if getattr(msg,'message_thread_id',None) is not None or not msg.voice: return
    # Telegram marks true forwards through forward_origin. Re-recorded audio cannot be reliably detected.
    if getattr(msg,'forward_origin',None) is not None:
        try:
            from handlers.dante import record_system_event
            record_system_event(chat.id,user.id,'presentation_forward_rejected')
        except Exception: pass
        await msg.reply_text(f"🎙️ {visible_user(user=user)}, la nota reenviada no cuenta como presentación. Envía una nota de voz nueva.")
        return
    if mark_presented(chat.id,user.id):
        try:
            from handlers.dante import record_system_event
            record_system_event(chat.id,user.id,'presentation_completed',{'voice':True})
        except Exception: pass
        await msg.reply_text(f"✅ Presentación registrada, {visible_user(user=user)}.")


def _claim_overdue():
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT chat_id,user_id FROM presentation_watchdog_tb
                 WHERE status='pending' AND deadline_at <= NOW()
                 ORDER BY deadline_at
                 FOR UPDATE SKIP LOCKED LIMIT 50
            """)
            rows = cur.fetchall()
            # 'cancelled' is a short claim state; failures below restore pending.
            for chat_id,user_id in rows:
                cur.execute("UPDATE presentation_watchdog_tb SET status='cancelled' WHERE chat_id=%s AND user_id=%s AND status='pending'", (chat_id,user_id))
        conn.commit(); return rows
    except Exception:
        conn.rollback(); return []
    finally:
        _put_connection(conn)


def _finish_removal(chat_id, user_id, ok):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            if ok:
                cur.execute("UPDATE presentation_watchdog_tb SET status='removed',removed_at=NOW() WHERE chat_id=%s AND user_id=%s AND status='cancelled'",(chat_id,user_id))
            else:
                cur.execute("UPDATE presentation_watchdog_tb SET status='pending' WHERE chat_id=%s AND user_id=%s AND status='cancelled'",(chat_id,user_id))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        _put_connection(conn)



async def _delete_notice_job(context: ContextTypes.DEFAULT_TYPE):
    data=context.job.data or {}
    try: await context.bot.delete_message(chat_id=data['chat_id'],message_id=data['message_id'])
    except Exception: pass

async def presentation_watchdog_job(context: ContextTypes.DEFAULT_TYPE):
    if not _presentation_enabled(MAIN_CHAT_ID): return
    for chat_id,user_id in _claim_overdue():
        ok = False
        try:
            # ban+unban = remove from group while allowing a future rejoin.
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
            ok = True
            try:
                notice=await context.bot.send_message(chat_id=chat_id,text=f'🚪 PiBot retiró a {visible_user(user_id=user_id)} por no completar su presentación a tiempo.')
                context.job_queue.run_once(_delete_notice_job, when=120, data={'chat_id':chat_id,'message_id':notice.message_id}, name=f'presentation_notice_{chat_id}_{notice.message_id}')
            except Exception as exc:
                print(f'[PRESENTACION AVISO] {exc}')
        except Exception as exc:
            print(f"[PRESENTACION] No pude retirar a {user_id}: {exc}")
        _finish_removal(chat_id,user_id,ok)
