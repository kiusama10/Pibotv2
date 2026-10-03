"""Silent 30-minute presentation watchdog for the main community.

Rose owns welcome messages. PiBot only records genuinely new users before the
legacy auto-registration handler runs, marks a presentation when the existing
presentation flow sees it, and removes overdue newcomers.
"""
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes

from src.database.database import _get_connection, _put_connection, get_usuario_resumen

MAIN_CHAT_ID = -1003290179217
TIMEOUT_MINUTES = 30


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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_presentation_pending_deadline ON presentation_watchdog_tb(status, deadline_at)")
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
                INSERT INTO presentation_watchdog_tb(chat_id,user_id,deadline_at,status)
                VALUES (%s,%s,NOW() + (%s || ' minutes')::interval,'pending')
                ON CONFLICT (chat_id,user_id) DO UPDATE SET
                    joined_at=NOW(), deadline_at=EXCLUDED.deadline_at, status='pending',
                    presented_at=NULL, removed_at=NULL
            """, (chat_id, user_id, TIMEOUT_MINUTES))
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


async def silent_new_member_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or update.effective_chat.id != MAIN_CHAT_ID:
        return
    for member in (msg.new_chat_members or []):
        if not member.is_bot:
            _create_pending_if_new(MAIN_CHAT_ID, member.id)
    # Deliberately sends no welcome/message. Rose handles that.



async def detect_presentation_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mark a pending newcomer as presented from a real user message in Presentaciones.

    In the main community Presentaciones is Telegram's original General topic, so
    message_thread_id is None. Commands and service messages do not count.
    The existing image reward remains separate: presenting does not itself award money.
    """
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    if not msg or not chat or not user or user.is_bot or chat.id != MAIN_CHAT_ID:
        return
    if getattr(msg, "message_thread_id", None) is not None:
        return
    # A presentation can be text or media, but not a command/service-only update.
    has_content = bool(msg.text or msg.caption or msg.photo or msg.video or msg.animation or msg.document or msg.voice or msg.audio)
    if not has_content:
        return
    if msg.text and msg.text.startswith("/"):
        return
    mark_presented(chat.id, user.id)

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
    for chat_id,user_id in _claim_overdue():
        ok = False
        try:
            # ban+unban = remove from group while allowing a future rejoin.
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
            ok = True
            try:
                notice=await context.bot.send_message(chat_id=chat_id,text=f'🚪 PiBot retiró al usuario {user_id} por no completar su presentación a tiempo.')
                context.job_queue.run_once(_delete_notice_job, when=120, data={'chat_id':chat_id,'message_id':notice.message_id}, name=f'presentation_notice_{chat_id}_{notice.message_id}')
            except Exception as exc:
                print(f'[PRESENTACION AVISO] {exc}')
        except Exception as exc:
            print(f"[PRESENTACION] No pude retirar a {user_id}: {exc}")
        _finish_removal(chat_id,user_id,ok)
