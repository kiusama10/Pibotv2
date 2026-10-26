"""Presentation watchdog for the main community (20-minute deadline).

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
TIMEOUT_MINUTES = 20
MIN_TEXT_WORDS = 4
FAREWELL_GIF_ID = os.getenv("PRESENTATION_FAREWELL_GIF_ID", "").strip()
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
            cur.execute("ALTER TABLE presentation_watchdog_tb ADD COLUMN IF NOT EXISTS prompt_message_id BIGINT")
            cur.execute("""CREATE TABLE IF NOT EXISTS presentation_settings_tb (
                chat_id BIGINT PRIMARY KEY,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""")
            cur.execute("ALTER TABLE presentation_settings_tb ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'voice'")
            cur.execute("""CREATE TABLE IF NOT EXISTS presentation_farewell_gifs_tb (
                chat_id BIGINT NOT NULL,
                file_id TEXT NOT NULL,
                added_by BIGINT,
                added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (chat_id, file_id)
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


def _presentation_mode(chat_id: int) -> str:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT mode FROM presentation_settings_tb WHERE chat_id=%s", (chat_id,))
            row = cur.fetchone()
            return str(row[0]).lower() if row and row[0] in ("voice", "text") else "voice"
    except Exception:
        return "voice"
    finally:
        _put_connection(conn)


def _set_presentation_mode(chat_id: int, mode: str):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO presentation_settings_tb(chat_id,enabled,mode) VALUES(%s,TRUE,%s)
                           ON CONFLICT(chat_id) DO UPDATE SET enabled=TRUE,mode=EXCLUDED.mode,updated_at=NOW()""", (chat_id, mode))
        conn.commit()
    except Exception:
        conn.rollback(); raise
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
    # Cada entrada/reentrada inicia un plazo nuevo de 20 minutos.
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO presentation_watchdog_tb(chat_id,user_id,deadline_at,status,verification_phrase)
                VALUES (%s,%s,NOW() + (%s || ' minutes')::interval,'pending',%s)
                ON CONFLICT (chat_id,user_id) DO UPDATE SET
                    joined_at=NOW(), deadline_at=EXCLUDED.deadline_at, status='pending',
                    presented_at=NULL, removed_at=NULL, verification_phrase=EXCLUDED.verification_phrase,
                    prompt_message_id=NULL
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


def _set_prompt_message_id(chat_id: int, user_id: int, message_id: int):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE presentation_watchdog_tb SET prompt_message_id=%s WHERE chat_id=%s AND user_id=%s AND status='pending'", (message_id, chat_id, user_id))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        _put_connection(conn)


def _get_prompt_message_id(chat_id: int, user_id: int):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT prompt_message_id FROM presentation_watchdog_tb WHERE chat_id=%s AND user_id=%s", (chat_id, user_id))
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        return None
    finally:
        _put_connection(conn)


async def _delete_pibot_prompt(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    message_id = _get_prompt_message_id(chat_id, user_id)
    if not message_id:
        return
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def _send_voice_prompt(context: ContextTypes.DEFAULT_TYPE):
    data=context.job.data or {}; chat_id=data.get('chat_id'); user_id=data.get('user_id')
    if not chat_id or not user_id or not _presentation_enabled(chat_id): return
    phrase=_get_phrase(chat_id,user_id)
    if not phrase: return
    label=visible_user(user_id=user_id)
    try:
        sent = await context.bot.send_message(chat_id=chat_id, text=(
            f"🎙️ {label}, para completar tu presentación envía esta frase por nota de voz:\n\n"
            f"«{phrase}»\n\nTienes {TIMEOUT_MINUTES} minutos desde tu entrada."
        ))
        _set_prompt_message_id(chat_id, user_id, sent.message_id)
    except Exception as exc: print(f"[PRESENTACION VOZ] {exc}")


async def _send_text_prompt(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data or {}; chat_id = data.get('chat_id'); user_id = data.get('user_id')
    if not chat_id or not user_id or not _presentation_enabled(chat_id) or _presentation_mode(chat_id) != 'text':
        return
    if not _get_phrase(chat_id, user_id):
        return
    label = visible_user(user_id=user_id)
    try:
        sent = await context.bot.send_message(chat_id=chat_id, text=(
            f"📝 {label}, preséntate con un mensaje de al menos {MIN_TEXT_WORDS} palabras.\n\n"
            f"Un simple hola o emojis no cuentan. Tienes {TIMEOUT_MINUTES} minutos desde tu entrada."
        ))
        _set_prompt_message_id(chat_id, user_id, sent.message_id)
    except Exception as exc:
        print(f"[PRESENTACION TEXTO] {exc}")


def _save_farewell_gif(chat_id: int, file_id: str, added_by: int):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO presentation_farewell_gifs_tb(chat_id,file_id,added_by)
                           VALUES(%s,%s,%s) ON CONFLICT(chat_id,file_id) DO NOTHING""",
                        (chat_id, file_id, added_by))
            inserted = cur.rowcount == 1
        conn.commit()
        return inserted
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_connection(conn)


def _get_random_farewell_gif(chat_id: int):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT file_id FROM presentation_farewell_gifs_tb WHERE chat_id=%s", (chat_id,))
            rows = cur.fetchall()
        return random.choice([row[0] for row in rows]) if rows else FAREWELL_GIF_ID or None
    except Exception as exc:
        print(f"[PRESENTACION GIFS] No pude leer los GIF: {exc}")
        return FAREWELL_GIF_ID or None
    finally:
        _put_connection(conn)


def _count_farewell_gifs(chat_id: int) -> int:
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM presentation_farewell_gifs_tb WHERE chat_id=%s", (chat_id,))
            row = cur.fetchone()
            return int(row[0]) if row else 0
    finally:
        _put_connection(conn)


async def presentaciones_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_owner = bool(user and ((KIU_ROOT_ID and user.id == KIU_ROOT_ID) or (not KIU_ROOT_ID and KIU_ROOT_USERNAME and (user.username or '').lower() == KIU_ROOT_USERNAME)))
    if not is_owner:
        return
    chat_id = MAIN_CHAT_ID
    arg = (context.args[0].lower() if context.args else 'estado')
    if arg in ('agregar_gif', 'añadir_gif', 'add_gif', 'gif'):
        reply = update.effective_message.reply_to_message
        file_id = None
        if reply:
            if getattr(reply, 'animation', None):
                file_id = reply.animation.file_id
            elif getattr(reply, 'document', None):
                doc = reply.document
                name = (doc.file_name or '').lower()
                mime = (doc.mime_type or '').lower()
                if name.endswith('.gif') or mime == 'image/gif':
                    file_id = doc.file_id
        if not file_id:
            text = '📎 Para guardar un GIF, responde al GIF que subiste con /presentaciones agregar_gif. Puedes guardar varios; al despedir a alguien se elegirá uno al azar.'
        else:
            try:
                added = _save_farewell_gif(chat_id, file_id, user.id)
                count = _count_farewell_gifs(chat_id)
                text = (f'🎞️ GIF guardado. Ya tienes {count} GIF(s) para despedidas; elegiré uno al azar.' if added
                        else f'ℹ️ Ese GIF ya estaba guardado. Tienes {count} GIF(s) disponibles.')
            except Exception as exc:
                print(f'[PRESENTACION GIFS] No pude guardar GIF: {exc}')
                text = '❌ No pude guardar ese GIF en la base de datos.'
    elif arg in ('gifs', 'lista_gifs', 'gif_count'):
        text = f'🎞️ Tienes {_count_farewell_gifs(chat_id)} GIF(s) guardados para despedidas aleatorias.'
    elif arg in ('on', 'activar', 'encender', 'voz'):
        _set_presentation_mode(chat_id, 'voice')
        _set_presentations_enabled(chat_id, True)
        text = f'🟢 Presentaciones por VOZ activadas. Tienen {TIMEOUT_MINUTES} minutos para enviar una nota de voz nueva.'
    elif arg in ('texto', 'text'):
        _set_presentation_mode(chat_id, 'text')
        _set_presentations_enabled(chat_id, True)
        text = f'🟢 Presentaciones por TEXTO activadas. Se aceptan mensajes de al menos {MIN_TEXT_WORDS} palabras. Tienen {TIMEOUT_MINUTES} minutos.'
    elif arg in ('off', 'desactivar', 'apagar'):
        _set_presentations_enabled(chat_id, False)
        text = '🔴 Presentaciones DESACTIVADAS. No se pedirán presentaciones ni se retirará a nadie por este sistema. DANTE sigue independiente.'
    else:
        enabled = _presentation_enabled(chat_id)
        mode = _presentation_mode(chat_id)
        mode_label = 'TEXTO (mínimo 4 palabras)' if mode == 'text' else 'VOZ'
        text = f"🚪 Presentaciones: {'ACTIVADAS' if enabled else 'DESACTIVADAS'}\nModo: {mode_label}\nPlazo: {TIMEOUT_MINUTES} minutos."
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
            prompt_fn = _send_text_prompt if _presentation_mode(MAIN_CHAT_ID) == 'text' else _send_voice_prompt
            context.job_queue.run_once(prompt_fn, when=PROMPT_DELAY_SECONDS, data={'chat_id': MAIN_CHAT_ID, 'user_id': member.id}, name=f'presentation_prompt_{MAIN_CHAT_ID}_{member.id}')
    # Deliberately no general welcome: Rose owns it.



async def detect_presentation_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Accept a fresh voice note or a text presentation, depending on configured mode."""
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user or user.is_bot or chat.id != MAIN_CHAT_ID or not _presentation_enabled(chat.id):
        return
    if getattr(msg, 'message_thread_id', None) is not None:
        return

    mode = _presentation_mode(chat.id)
    if mode == 'text':
        if not msg.text or msg.text.startswith('/'):
            return
        words = [word for word in msg.text.split() if any(ch.isalnum() for ch in word)]
        if len(words) < MIN_TEXT_WORDS:
            return
        if mark_presented(chat.id, user.id):
            await _delete_pibot_prompt(context, chat.id, user.id)
            try:
                from handlers.dante import record_system_event
                record_system_event(chat.id, user.id, 'presentation_completed', {'text': True, 'word_count': len(words)})
            except Exception:
                pass
            try:
                await msg.reply_text(f"✅ Presentación por texto registrada, {visible_user(user=user)}.")
            except Exception:
                pass
        return

    if not msg.voice:
        return
    # Telegram marks true forwards through forward_origin. Re-recorded audio cannot be reliably detected.
    if getattr(msg, 'forward_origin', None) is not None:
        try:
            from handlers.dante import record_system_event
            record_system_event(chat.id, user.id, 'presentation_forward_rejected')
        except Exception:
            pass
        await msg.reply_text(f"🎙️ {visible_user(user=user)}, la nota reenviada no cuenta como presentación. Envía una nota de voz nueva.")
        return
    if mark_presented(chat.id, user.id):
        await _delete_pibot_prompt(context, chat.id, user.id)
        try:
            from handlers.dante import record_system_event
            record_system_event(chat.id, user.id, 'presentation_completed', {'voice': True})
        except Exception:
            pass
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
            await _delete_pibot_prompt(context, chat_id, user_id)
            try:
                farewell_gif_id = _get_random_farewell_gif(chat_id)
                farewell_text = f'👋 {visible_user(user_id=user_id)} no alcanzó a presentarse en {TIMEOUT_MINUTES} minutos. ¡Hasta luego!'
                if farewell_gif_id:
                    await context.bot.send_animation(chat_id=chat_id, animation=farewell_gif_id, caption=farewell_text)
                else:
                    await context.bot.send_message(chat_id=chat_id, text=farewell_text)
            except Exception as exc:
                print(f'[PRESENTACION DESPEDIDA] {exc}')
            try:
                notice=await context.bot.send_message(chat_id=chat_id,text=f'🚪 PiBot retiró a {visible_user(user_id=user_id)} por no completar su presentación a tiempo.')
                context.job_queue.run_once(_delete_notice_job, when=120, data={'chat_id':chat_id,'message_id':notice.message_id}, name=f'presentation_notice_{chat_id}_{notice.message_id}')
            except Exception as exc:
                print(f'[PRESENTACION AVISO] {exc}')
        except Exception as exc:
            print(f"[PRESENTACION] No pude retirar a {user_id}: {exc}")
        _finish_removal(chat_id,user_id,ok)
