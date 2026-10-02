"""Asesino automático: Kiu inicia/cancela; cada 6 h PiBot elige dos asesinos del grupo."""
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection,_put_connection
from src.utils.root_owner import ensure_root_identity

CYCLE_SECONDS=6*60*60
_seen_members=set()

def ensure_assassin_tables():
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS assassin_auto_tb(
          config_id BIGSERIAL PRIMARY KEY, chat_id BIGINT NOT NULL, thread_id BIGINT,
          owner_id BIGINT NOT NULL, active BOOLEAN NOT NULL DEFAULT FALSE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), next_cycle_at TIMESTAMPTZ,
          UNIQUE(chat_id,thread_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS assassin_group_members_tb(
          chat_id BIGINT NOT NULL,user_id BIGINT NOT NULL,nombre TEXT NOT NULL,
          last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(chat_id,user_id))""")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_assassin_auto_location ON assassin_auto_tb(chat_id,COALESCE(thread_id,0))")
        c.execute("""CREATE TABLE IF NOT EXISTS assassin_cycles_tb(
          cycle_id BIGSERIAL PRIMARY KEY,config_id BIGINT NOT NULL REFERENCES assassin_auto_tb(config_id) ON DELETE CASCADE,
          killer1 BIGINT NOT NULL,killer2 BIGINT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        c.execute("""CREATE TABLE IF NOT EXISTS assassin_choices_tb(
          cycle_id BIGINT NOT NULL REFERENCES assassin_cycles_tb(cycle_id) ON DELETE CASCADE,
          killer_id BIGINT NOT NULL,target_id BIGINT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY(cycle_id,killer_id))""")
        conn.commit()
    except Exception: conn.rollback(); raise
    finally:_put_connection(conn)

def assassin_track_member(update):
    u=update.effective_user; ch=update.effective_chat
    if not u or u.is_bot or not ch or ch.type=='private': return
    key=(ch.id,u.id)
    if key in _seen_members: return
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""INSERT INTO assassin_group_members_tb(chat_id,user_id,nombre,last_seen)
          VALUES(%s,%s,%s,NOW()) ON CONFLICT(chat_id,user_id) DO UPDATE SET nombre=EXCLUDED.nombre,last_seen=NOW()""",
          (ch.id,u.id,u.username or u.full_name or str(u.id))); conn.commit(); _seen_members.add(key)
    except Exception: conn.rollback()
    finally:_put_connection(conn)

def _thread(update):
    m=update.effective_message; return getattr(m,'message_thread_id',None)

async def asesino(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private': return await update.effective_message.reply_text('🔪 Este juego se controla desde el grupo.')
    if not ensure_root_identity(update.effective_user): return await update.effective_message.reply_text('🔒 Solo Kiu puede iniciar o cancelar este evento.')
    chat=update.effective_chat.id; thread=_thread(update); conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT config_id,active FROM assassin_auto_tb WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) LIMIT 1",(chat,thread)); row=c.fetchone()
        if row:
            cid,active=row; c.execute("UPDATE assassin_auto_tb SET owner_id=%s WHERE config_id=%s",(update.effective_user.id,cid))
        else:
            c.execute("INSERT INTO assassin_auto_tb(chat_id,thread_id,owner_id,active) VALUES(%s,%s,%s,FALSE) RETURNING config_id,active",(chat,thread,update.effective_user.id)); cid,active=c.fetchone()
        conn.commit()
    except Exception: conn.rollback(); return await update.effective_message.reply_text('⚠️ No pude abrir el control del Asesino.')
    finally:_put_connection(conn)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('▶️ Empezar juego',callback_data=f'as:auto_start:{cid}'),InlineKeyboardButton('🛑 Cancelar',callback_data=f'as:auto_cancel:{cid}')]])
    state='🟢 Activo' if active else '⚪ Detenido'
    await update.effective_message.reply_text(f'🔪 *JUEGO DEL ASESINO*\n\n{state}\nCada 6 horas PiBot elegirá 2 personas al azar del grupo. No hay lobby, no hay que unirse y nadie tiene que aceptar. Los elegidos reciben por privado a quién pueden matar. 😈',parse_mode='Markdown',reply_markup=kb)

async def _run_cycle(context,cid,manual=False):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,active FROM assassin_auto_tb WHERE config_id=%s FOR UPDATE",(cid,)); cfg=c.fetchone()
        if not cfg or not cfg[2]: conn.rollback(); return False
        chat,thread,_=cfg
        c.execute("SELECT user_id,nombre FROM assassin_group_members_tb WHERE chat_id=%s ORDER BY last_seen DESC",(chat,)); pool=c.fetchall()
        if len(pool)<4:
            c.execute("UPDATE assassin_auto_tb SET next_cycle_at=NOW()+INTERVAL '6 hours' WHERE config_id=%s",(cid,)); conn.commit()
            await context.bot.send_message(chat_id=chat,message_thread_id=thread,text='🔪 El Asesino sigue activo, pero todavía necesito haber visto al menos 4 miembros del grupo para hacer el sorteo.')
            return False
        killers=random.sample(pool,2); k1,k2=killers[0][0],killers[1][0]
        c.execute("INSERT INTO assassin_cycles_tb(config_id,killer1,killer2) VALUES(%s,%s,%s) RETURNING cycle_id",(cid,k1,k2)); cycle=c.fetchone()[0]
        c.execute("UPDATE assassin_auto_tb SET next_cycle_at=NOW()+INTERVAL '6 hours' WHERE config_id=%s",(cid,)); conn.commit()
    except Exception:
        conn.rollback(); return False
    finally:_put_connection(conn)
    sent=[]
    for kid,kname in killers:
        targets=[p for p in pool if p[0]!=kid]
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(f'🎯 {name[:32]}',callback_data=f'as:auto_kill:{cycle}:{uid}')] for uid,name in targets[:40]])
        try:
            await context.bot.send_message(kid,'🔪 *PIBOT TE ELIGIÓ COMO ASESINO*\n\nTú decides a quién matar en este ciclo. Tu elección es secreta hasta atacar:',parse_mode='Markdown',reply_markup=kb); sent.append(kid)
        except Exception: pass
    await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f'🔪 *NUEVO CICLO DEL ASESINO*\n\nPiBot eligió a 2 personas al azar. 😈\nTienen su misión por privado.\n⏳ El próximo sorteo será en 6 horas.',parse_mode='Markdown')
    if len(sent)<2:
        await context.bot.send_message(chat_id=chat,message_thread_id=thread,text='⚠️ Alguno de los elegidos no tiene abierto el privado con PiBot, así que no pudo recibir su misión.')
    return True

async def assassin_cycle_job(context:ContextTypes.DEFAULT_TYPE):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT config_id FROM assassin_auto_tb WHERE active=TRUE AND (next_cycle_at IS NULL OR next_cycle_at<=NOW())"); ids=[r[0] for r in c.fetchall()]
    finally:_put_connection(conn)
    for cid in ids: await _run_cycle(context,cid)

async def assassin_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; p=q.data.split(':'); action=p[1] if len(p)>1 else ''
    if action in ('auto_start','auto_cancel'):
        if not ensure_root_identity(q.from_user): return await q.answer('Solo Kiu puede controlar el juego.',show_alert=True)
        cid=int(p[2]); conn=_get_connection()
        try:
            c=conn.cursor()
            if action=='auto_start': c.execute("UPDATE assassin_auto_tb SET active=TRUE,next_cycle_at=NOW() WHERE config_id=%s",(cid,))
            else: c.execute("UPDATE assassin_auto_tb SET active=FALSE,next_cycle_at=NULL WHERE config_id=%s",(cid,))
            conn.commit()
        except Exception: conn.rollback(); return await q.answer('No pude cambiar el estado.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Juego iniciado.' if action=='auto_start' else 'Juego cancelado.')
        await q.edit_message_text('🔪 Juego del Asesino ACTIVO. Primer sorteo en curso…' if action=='auto_start' else '🛑 Juego del Asesino cancelado.')
        if action=='auto_start': await _run_cycle(context,cid,True)
        return
    if action=='auto_kill':
        cycle=int(p[2]); target=int(p[3]); killer=q.from_user.id; conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT ac.killer1,ac.killer2,a.chat_id,a.thread_id FROM assassin_cycles_tb ac JOIN assassin_auto_tb a ON a.config_id=ac.config_id WHERE ac.cycle_id=%s",(cycle,)); row=c.fetchone()
            if not row or killer not in row[:2]: conn.rollback(); return await q.answer('Esta misión no es tuya.',show_alert=True)
            c.execute("INSERT INTO assassin_choices_tb(cycle_id,killer_id,target_id) VALUES(%s,%s,%s) ON CONFLICT(cycle_id,killer_id) DO NOTHING",(cycle,killer,target))
            if c.rowcount!=1: conn.rollback(); return await q.answer('Ya elegiste una víctima en este ciclo.',show_alert=True)
            c.execute("SELECT nombre FROM assassin_group_members_tb WHERE chat_id=%s AND user_id=%s",(row[2],target)); rr=c.fetchone(); name=rr[0] if rr else str(target); conn.commit(); chat,thread=row[2],row[3]
        except Exception: conn.rollback(); return await q.answer('No pude registrar la víctima.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Víctima elegida. 😈',show_alert=True); await q.edit_message_text(f'🔪 Misión completada. Elegiste a {name}.')
        await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f'☠️ *{name} ha sido víctima del Asesino.*\n¿Quién habrá sido? 👀',parse_mode='Markdown')
