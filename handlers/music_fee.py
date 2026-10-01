"""Idempotent PiPeso fee for music posts in a BotMaster-configured Telegram topic."""
import re
from telegram import Update
from telegram.ext import ContextTypes
from src.config import BOTMASTER_IDS
from src.config.settings import MUSIC_POST_PRICE
from src.database.database import _get_connection, _put_connection, is_botmaster

MAIN_CHAT_ID=-1003290179217
LINK_RE=re.compile(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be|music\.youtube\.com|open\.spotify\.com)/\S+",re.I)

def ensure_music_tables():
    conn=_get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS music_post_charges_tb(
                chat_id BIGINT NOT NULL,message_id BIGINT NOT NULL,user_id BIGINT NOT NULL,
                amount INTEGER NOT NULL CHECK(amount>0),created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY(chat_id,message_id))""")
            cur.execute("""CREATE TABLE IF NOT EXISTS music_topic_config_tb(
                chat_id BIGINT PRIMARY KEY,thread_id BIGINT,enabled BOOLEAN NOT NULL DEFAULT TRUE,
                price INTEGER NOT NULL DEFAULT 500 CHECK(price>0),configured_by BIGINT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:_put_connection(conn)

def _config(chat_id):
    conn=_get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT thread_id,enabled,price FROM music_topic_config_tb WHERE chat_id=%s",(chat_id,))
            return cur.fetchone()
    except Exception as exc:
        print("[MUSICA] config error",exc); return None
    finally:_put_connection(conn)

def _save(chat_id,thread_id,user_id,enabled,price):
    conn=_get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO music_topic_config_tb(chat_id,thread_id,enabled,price,configured_by)
            VALUES(%s,%s,%s,%s,%s) ON CONFLICT(chat_id) DO UPDATE SET
            thread_id=EXCLUDED.thread_id,enabled=EXCLUDED.enabled,price=EXCLUDED.price,
            configured_by=EXCLUDED.configured_by,updated_at=NOW()""",
            (chat_id,thread_id,enabled,price,user_id))
        conn.commit(); return True
    except Exception as exc:
        conn.rollback(); print("[MUSICA] save error",exc); return False
    finally:_put_connection(conn)

def _reward_once(chat_id,message_id,user_id,amount):
    """Award a music post exactly once. No debit and no insufficient-balance path."""
    conn=_get_connection()
    try:
        with conn.cursor() as cur:
            # The existing table is kept for compatibility; amount now records the reward granted.
            cur.execute("SELECT 1 FROM music_post_charges_tb WHERE chat_id=%s AND message_id=%s FOR UPDATE",(chat_id,message_id))
            if cur.fetchone():
                conn.commit()
                return "already"
            cur.execute("SELECT 1 FROM usuarios_tb WHERE id_user=%s FOR UPDATE",(user_id,))
            if not cur.fetchone():
                conn.rollback()
                return "unknown_user"
            cur.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(amount,user_id))
            cur.execute("INSERT INTO music_post_charges_tb(chat_id,message_id,user_id,amount) VALUES(%s,%s,%s,%s)",
                        (chat_id,message_id,user_id,amount))
        conn.commit()
        return "rewarded"
    except Exception as exc:
        conn.rollback()
        print("[MUSICA] reward error",exc)
        return "error"
    finally:
        _put_connection(conn)

def _is_music(msg):
    if msg.audio or msg.video:return True
    return bool(LINK_RE.search(msg.text or msg.caption or ""))

async def activarmusica(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not is_botmaster(update.effective_user.id):
        return await update.effective_message.reply_text("❌ Solo un BotMaster puede configurar Música.")
    if update.effective_chat.id!=MAIN_CHAT_ID:
        return await update.effective_message.reply_text("❌ Configura Música dentro de la comunidad principal.")
    msg=update.effective_message
    if msg.message_thread_id is None:
        return await msg.reply_text("❌ Ejecuta /activarmusica dentro del tema de Música.")
    price=MUSIC_POST_PRICE
    if context.args:
        try:
            price=int(context.args[0].replace(",",""))
            if price<=0:raise ValueError
        except ValueError:
            return await msg.reply_text("Uso: /activarmusica 500")
    if _save(update.effective_chat.id,msg.message_thread_id,update.effective_user.id,True,price):
        await msg.reply_text(f"🎵 MÚSICA ACTIVADA\n\n💰 Premio: +{price:,} PiPesos por publicación musical válida.\n🔗 YouTube · YouTube Music · Spotify\n🎧 Audio o video directo\n\n✅ Este tema quedó guardado incluso después de reiniciar PiBot.")
    else: await msg.reply_text("⚠️ No pude guardar la configuración.")

async def desactivarmusica(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not is_botmaster(update.effective_user.id):
        return await update.effective_message.reply_text("❌ Solo un BotMaster puede desactivar Música.")
    cfg=_config(update.effective_chat.id)
    if not cfg:return await update.effective_message.reply_text("ℹ️ No hay un tema de Música configurado.")
    thread_id,_,price=cfg
    if _save(update.effective_chat.id,thread_id,update.effective_user.id,False,price):
        await update.effective_message.reply_text("🔇 Cobro de Música desactivado.")

async def paid_music_post(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_user:return
    msg=update.effective_message
    if update.effective_chat.id!=MAIN_CHAT_ID or not _is_music(msg):return
    cfg=_config(update.effective_chat.id)
    if not cfg:return
    thread_id,enabled,price=cfg
    if not enabled or msg.message_thread_id!=thread_id:return
    result=_reward_once(update.effective_chat.id,msg.message_id,update.effective_user.id,price)
    if result=="rewarded":
        try:await msg.reply_text(f"🎵 Publicación musical · +{price:,} PiPesos")
        except Exception:pass
