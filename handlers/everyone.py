"""Admin-only /todos using members PiBot has actually observed."""
from telegram import Update
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection
from src.utils.root_owner import is_root_identity

async def todos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat or update.effective_chat.type == 'private': return
    member=await update.effective_chat.get_member(update.effective_user.id)
    if member.status not in ('administrator','creator') and not is_root_identity(update.effective_user): return
    conn=_get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id,username,display_name FROM dante_identity_tb WHERE chat_id=%s ORDER BY last_seen DESC LIMIT 1000",(update.effective_chat.id,))
            rows=cur.fetchall()
    except Exception:
        rows=[]
    finally: _put_connection(conn)
    if not rows:
        await update.effective_message.reply_text("Aún no tengo miembros observados suficientes para /todos."); return
    extra=" ".join(context.args or []).strip()
    mentions=[]
    for uid,username,name in rows:
        if username: mentions.append('@'+username)
        elif name: mentions.append(f'<a href="tg://user?id={uid}">{name}</a>')
    chunks=[]; current=(extra+'\n\n' if extra else '')
    for m in mentions:
        if len(current)+len(m)+1>3800:
            chunks.append(current.rstrip()); current=''
        current += m+' '
    if current.strip(): chunks.append(current.rstrip())
    for chunk in chunks[:10]: await update.effective_message.reply_text(chunk,parse_mode='HTML',disable_web_page_preview=True)
