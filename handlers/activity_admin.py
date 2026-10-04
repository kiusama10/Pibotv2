"""Manual group activity review.

Keeps a lightweight, group-scoped member registry from messages PiBot can see.
Shows last message + message count and gives admins an explicit kick button for
each member. Nothing is automatic.
"""
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection
from src.utils.root_owner import is_root_identity

PAGE_SIZE = 8


def ensure_member_activity_table():
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS group_member_activity_tb(
                chat_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                username TEXT,
                display_name TEXT,
                first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_message_at TIMESTAMPTZ,
                message_count BIGINT NOT NULL DEFAULT 0,
                member_state TEXT NOT NULL DEFAULT 'known',
                PRIMARY KEY(chat_id,user_id)
            )""")
            cur.execute("ALTER TABLE group_member_activity_tb ADD COLUMN IF NOT EXISTS member_state TEXT NOT NULL DEFAULT 'known'")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_group_member_activity_chat_last ON group_member_activity_tb(chat_id,last_message_at)")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        _put_connection(conn)


def _is_real_user_message(msg):
    if not msg: return False
    # Service membership events are observations, not a message written by the member.
    if msg.new_chat_members or msg.left_chat_member: return False
    return True


async def member_activity_observer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat, user, msg = update.effective_chat, update.effective_user, update.effective_message
    if not chat or chat.type == 'private' or not user or user.is_bot: return
    name = " ".join(x for x in (user.first_name, user.last_name) if x).strip() or None
    wrote = _is_real_user_message(msg)
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            if wrote:
                cur.execute("""INSERT INTO group_member_activity_tb
                    (chat_id,user_id,username,display_name,last_message_at,message_count)
                    VALUES(%s,%s,%s,%s,NOW(),1)
                    ON CONFLICT(chat_id,user_id) DO UPDATE SET
                      username=EXCLUDED.username, display_name=EXCLUDED.display_name,
                      last_seen=NOW(), last_message_at=NOW(),
                      message_count=group_member_activity_tb.message_count+1, member_state='inside'""",
                    (chat.id,user.id,user.username,name))
            else:
                cur.execute("""INSERT INTO group_member_activity_tb(chat_id,user_id,username,display_name)
                    VALUES(%s,%s,%s,%s)
                    ON CONFLICT(chat_id,user_id) DO UPDATE SET
                      username=EXCLUDED.username, display_name=EXCLUDED.display_name,last_seen=NOW(), member_state='inside'""",
                    (chat.id,user.id,user.username,name))
        conn.commit()
    except Exception as exc:
        conn.rollback(); print(f"[ACTIVIDAD REGISTRY] {type(exc).__name__}: {exc}")
    finally:
        _put_connection(conn)


def _rows(chat_id: int):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            # Union the permanent activity registry with identities DANTE has already
            # observed, so existing known members are not lost during the upgrade.
            cur.execute("""
                WITH known AS (
                    SELECT chat_id,user_id,username,display_name,last_message_at,message_count
                      FROM group_member_activity_tb WHERE chat_id=%s AND member_state <> 'outside'
                    UNION ALL
                    SELECT d.chat_id,d.user_id,d.username,d.display_name,NULL::timestamptz,0::bigint
                      FROM dante_identity_tb d
                     WHERE d.chat_id=%s
                       AND NOT EXISTS (SELECT 1 FROM group_member_activity_tb a WHERE a.chat_id=d.chat_id AND a.user_id=d.user_id)
                )
                SELECT user_id,COALESCE(NULLIF(username,''),NULLIF(display_name,''),'Miembro'),
                       message_count,last_message_at
                  FROM known
              ORDER BY last_message_at ASC NULLS FIRST, message_count ASC, user_id ASC
            """, (chat_id,chat_id))
            return list(cur.fetchall())
    except Exception:
        return []
    finally:
        _put_connection(conn)


async def _is_admin(chat, user):
    if is_root_identity(user): return True
    try:
        m=await chat.get_member(user.id); return m.status in ('administrator','creator')
    except Exception: return False


def _ago(dt):
    if not dt: return "Nunca registrado"
    now=datetime.now(timezone.utc)
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    sec=max(0,int((now-dt).total_seconds()))
    if sec < 60: return "Ahora"
    if sec < 3600: return f"Hace {sec//60} min"
    if sec < 86400: return f"Hace {sec//3600} h"
    days=sec//86400
    if days < 30: return f"Hace {days} d"
    if days < 365: return f"Hace {days//30} mes" + ("es" if days//30 != 1 else "")
    years=days//365; return f"Hace {years} año" + ("s" if years != 1 else "")


def _label(name,count,last):
    clean=str(name or 'Miembro').replace('\n',' ')[:18]
    return f"🥾 {clean} · {int(count)} msg · {_ago(last)}"[:64]


async def actividad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat,user,msg=update.effective_chat,update.effective_user,update.effective_message
    if not chat or chat.type=='private' or not user or not msg: return
    if not await _is_admin(chat,user): return await msg.reply_text("Este panel es solo para administradores.")
    await _show(msg,chat.id,0,edit=False)


async def _show(message,chat_id:int,page:int,edit=True):
    rows=_rows(chat_id)
    if not rows:
        text="📊 Aún no tengo miembros registrados de este grupo."
        return await (message.edit_text(text) if edit else message.reply_text(text))
    pages=max(1,(len(rows)+PAGE_SIZE-1)//PAGE_SIZE); page=max(0,min(page,pages-1))
    part=rows[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
    kb=[[InlineKeyboardButton(_label(name,count,last),callback_data=f"act:k:{chat_id}:{uid}:{page}")] for uid,name,count,last in part]
    nav=[]
    if page>0: nav.append(InlineKeyboardButton("◀️",callback_data=f"act:p:{chat_id}:{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{pages}",callback_data="act:no"))
    if page<pages-1: nav.append(InlineKeyboardButton("▶️",callback_data=f"act:p:{chat_id}:{page+1}"))
    kb.append(nav)
    text=(f"📊 <b>Actividad del grupo</b>\n\n👥 <b>{len(rows)} usuarios registrados por PiBot</b>\n"
          "Primero aparecen quienes nunca han escrito o llevan más tiempo sin hacerlo.\n\n"
          "Cada fila es un miembro: 🥾 nombre · mensajes · último mensaje.\n"
          "Tócalo para revisar el kick. <b>Nadie se expulsa automáticamente.</b>")
    markup=InlineKeyboardMarkup(kb)
    if edit: await message.edit_text(text,parse_mode='HTML',reply_markup=markup)
    else: await message.reply_text(text,parse_mode='HTML',reply_markup=markup)


async def actividad_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if not q:return
    data=q.data or ''
    if data=='act:no': return await q.answer()
    parts=data.split(':')
    try: action=parts[1];chat_id=int(parts[2]);page=int(parts[-1])
    except Exception:return
    try: chat=await context.bot.get_chat(chat_id)
    except Exception:return
    if not await _is_admin(chat,q.from_user): return await q.answer("Solo administradores.",show_alert=True)
    await q.answer()
    if action=='p': return await _show(q.message,chat_id,page,edit=True)
    if action=='k':
        uid=int(parts[3])
        try:
            member=await context.bot.get_chat_member(chat_id,uid)
            if member.status in ('administrator','creator'): return await q.answer("No puedes expulsar a un administrador desde aquí.",show_alert=True)
            u=member.user;name=(('@'+u.username) if u.username else (u.full_name or 'Miembro'))
        except Exception:name='este miembro'
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("🥾 Sí, expulsar",callback_data=f"act:y:{chat_id}:{uid}:{page}"),InlineKeyboardButton("Cancelar",callback_data=f"act:p:{chat_id}:{page}")]])
        return await q.message.edit_text(f"¿Expulsar a <b>{name}</b>?\n\nEsta acción solo ocurre si tú la confirmas.",parse_mode='HTML',reply_markup=kb)
    if action=='y':
        uid=int(parts[3])
        if uid==q.from_user.id:return await q.answer("No te voy a dejar expulsarte tú mismo 😂",show_alert=True)
        try:
            member=await context.bot.get_chat_member(chat_id,uid)
            if member.status in ('administrator','creator'):return await q.answer("No puedo expulsar a un administrador.",show_alert=True)
            u=member.user;name=(('@'+u.username) if u.username else (u.full_name or 'Miembro'))
            await context.bot.ban_chat_member(chat_id,uid);await context.bot.unban_chat_member(chat_id,uid,only_if_banned=True)
            await q.answer("Expulsado.",show_alert=True)
            await q.message.edit_text(f"🥾 <b>{name}</b> fue retirado manualmente por un administrador.",parse_mode='HTML')
        except Exception: await q.answer("No pude expulsarlo. Revisa que PiBot sea administrador.",show_alert=True)
