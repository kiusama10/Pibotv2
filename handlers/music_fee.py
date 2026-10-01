"""Idempotent PiPeso fee for music posts in one explicitly configured topic."""
import re
from telegram import Update
from telegram.ext import ContextTypes
from src.config.settings import MUSIC_THREAD_ID, MUSIC_POST_PRICE
from src.database.database import _get_connection, _put_connection

MAIN_CHAT_ID=-1003290179217
LINK_RE=re.compile(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be|music\.youtube\.com|open\.spotify\.com)/\S+", re.I)


def ensure_music_tables():
    conn=_get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS music_post_charges_tb(
                chat_id BIGINT NOT NULL, message_id BIGINT NOT NULL, user_id BIGINT NOT NULL,
                amount INTEGER NOT NULL CHECK(amount>0), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY(chat_id,message_id))""")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:_put_connection(conn)


def _charge_once(chat_id,message_id,user_id,amount):
    conn=_get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM music_post_charges_tb WHERE chat_id=%s AND message_id=%s",(chat_id,message_id))
            if cur.fetchone(): conn.commit(); return 'already'
            cur.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s FOR UPDATE",(user_id,))
            row=cur.fetchone()
            if not row or row[0] < amount: conn.rollback(); return 'insufficient'
            cur.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s",(amount,user_id))
            cur.execute("INSERT INTO music_post_charges_tb(chat_id,message_id,user_id,amount) VALUES(%s,%s,%s,%s)",(chat_id,message_id,user_id,amount))
        conn.commit(); return 'charged'
    except Exception as exc:
        conn.rollback(); print('[MUSICA] charge error',exc); return 'error'
    finally:_put_connection(conn)


def _is_music(msg):
    if msg.audio: return True
    if msg.video: return True
    text=(msg.text or msg.caption or '')
    return bool(LINK_RE.search(text))


async def paid_music_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Safety: no configured topic means zero charging anywhere.
    if MUSIC_THREAD_ID is None or not update.effective_message or not update.effective_user:
        return
    msg=update.effective_message
    if update.effective_chat.id != MAIN_CHAT_ID or msg.message_thread_id != MUSIC_THREAD_ID or not _is_music(msg):
        return
    result=_charge_once(update.effective_chat.id,msg.message_id,update.effective_user.id,MUSIC_POST_PRICE)
    if result=='insufficient':
        try: await msg.delete()
        except Exception: pass
        try:
            await context.bot.send_message(update.effective_user.id, f"🎵 Esa publicación cuesta {MUSIC_POST_PRICE:,} PiPesos y no tienes saldo suficiente.")
        except Exception: pass
    elif result=='charged':
        # Keep the topic clean: no public receipt for every song.
        pass
