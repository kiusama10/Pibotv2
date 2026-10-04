"""Admin-only /todos.

Uses PiBot's group-scoped member registry, verifies membership at send time, and
mentions every still-present known member without printing a wall of usernames.
Telegram does not expose an arbitrary complete member list to bots.
"""
import asyncio
import html
from telegram import Update
from telegram.error import RetryAfter
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection
from src.utils.root_owner import is_root_identity

MAX_HTML = 3600
CHECK_CONCURRENCY = 8


def _known_members(chat_id):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT user_id,username,display_name FROM (
                    SELECT user_id,username,display_name,last_seen FROM group_member_activity_tb
                     WHERE chat_id=%s AND member_state <> 'outside'
                    UNION ALL
                    SELECT d.user_id,d.username,d.display_name,d.last_seen FROM dante_identity_tb d
                     WHERE d.chat_id=%s AND NOT EXISTS (
                         SELECT 1 FROM group_member_activity_tb a
                          WHERE a.chat_id=d.chat_id AND a.user_id=d.user_id
                     )
                ) x ORDER BY last_seen DESC
            """, (chat_id,chat_id))
            return list(cur.fetchall())
    except Exception:
        return []
    finally:
        _put_connection(conn)


def _save_membership(chat_id, uid, username, name, inside):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO group_member_activity_tb
                (chat_id,user_id,username,display_name,member_state)
                VALUES(%s,%s,%s,%s,%s)
                ON CONFLICT(chat_id,user_id) DO UPDATE SET
                  username=COALESCE(EXCLUDED.username,group_member_activity_tb.username),
                  display_name=COALESCE(EXCLUDED.display_name,group_member_activity_tb.display_name),
                  last_seen=NOW(), member_state=EXCLUDED.member_state""",
                (chat_id,uid,username,name,'inside' if inside else 'outside'))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        _put_connection(conn)


def _mention(uid):
    # Hidden-looking bullet is the actual Telegram text mention; works without @username.
    return f'<a href="tg://user?id={int(uid)}">•</a>'


async def _membership(bot, chat_id, uid, fallback_username=None, fallback_name=None):
    """Return (inside, username, name). Unknown API failures are not marked outside."""
    for attempt in range(2):
        try:
            member = await bot.get_chat_member(chat_id, uid)
            status = member.status
            inside = status not in ('left', 'kicked')
            u = member.user
            username = u.username if u else fallback_username
            name = (u.full_name if u else None) or fallback_name
            _save_membership(chat_id, uid, username, name, inside)
            return inside, username, name
        except RetryAfter as exc:
            if attempt == 0:
                await asyncio.sleep(float(exc.retry_after) + 0.2)
                continue
            return None, fallback_username, fallback_name
        except Exception:
            return None, fallback_username, fallback_name


async def todos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    msg = update.effective_message
    if not chat or chat.type == 'private' or not user or not msg:
        return

    member = await chat.get_member(user.id)
    if member.status not in ('administrator', 'creator') and not is_root_identity(user):
        return

    rows = _known_members(chat.id)
    known = {int(uid): (username, name) for uid, username, name in rows}
    try:
        for admin in await chat.get_administrators():
            u = admin.user
            if u and not u.is_bot:
                known[int(u.id)] = (u.username, u.full_name or None)
    except Exception:
        pass

    if not known:
        await msg.reply_text("Aún no tengo miembros conocidos de este grupo para mencionar.")
        return

    # Verify the locally-known registry against Telegram. A bounded semaphore keeps
    # large groups from firing hundreds of API requests simultaneously.
    sem = asyncio.Semaphore(CHECK_CONCURRENCY)
    async def check(uid, data):
        async with sem:
            return uid, await _membership(context.bot, chat.id, uid, data[0], data[1])

    checked = await asyncio.gather(*(check(uid, data) for uid, data in known.items()))
    inside = []
    outside = 0
    unverifiable = 0
    for uid, (state, _username, _name) in checked:
        if state is True:
            inside.append(uid)
        elif state is False:
            outside += 1
        else:
            # Do not mention someone whose current membership could not be verified.
            unverifiable += 1

    if not inside:
        await msg.reply_text(
            f"No encontré miembros registrados que pudiera confirmar dentro del grupo.\n"
            f"🚪 Ya no están: {outside}\n⚠️ No pude verificar: {unverifiable}"
        )
        return

    extra = html.escape(" ".join(context.args or []).strip())
    prefix = ((extra + "\n\n") if extra else "📢 <b>Aviso para todos</b>\n\n")

    chunks=[]; current=prefix; count=0
    for uid in inside:
        token=_mention(uid)
        if len(current)+len(token)+1 > MAX_HTML:
            chunks.append((current.rstrip(),count)); current="🔔 "; count=0
        current += token; count += 1
    if count: chunks.append((current.rstrip(),count))

    mentioned=0
    for chunk,n in chunks:
        await msg.reply_text(chunk,parse_mode='HTML',disable_web_page_preview=True)
        mentioned += n
        if len(chunks)>1: await asyncio.sleep(0.15)

    summary=(f"✅ Notificación terminada\n"
             f"🔔 Notificados: {mentioned}\n"
             f"🚪 Ya no están en el grupo: {outside}")
    if unverifiable:
        summary += f"\n⚠️ No pude verificar: {unverifiable}"
    await msg.reply_text(summary)
