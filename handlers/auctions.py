import random
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import ContextTypes
from src.config import BOTMASTER_IDS, obtener_temas_por_comunidad
from src.database.database import _get_connection, _put_connection, get_user_role

AUCTION_SECONDS = 3600
EVENT_THREAD = 335263
MAIN_CHAT = -1003290179217
LINES = [
    "🔨 ¡Tenemos nueva cifra! ¿Quién da más?",
    "💸 BANKIU está observando estas decisiones financieras con interés.",
    "👀 El silencio del chat empieza a parecer sospechoso… ¿nadie mejora esa oferta?",
    "📣 ¡Sube la puja! Aquí todavía queda cartera por vaciar.",
    "🔔 Una… casi dos… pero todavía pueden arruinarle el presupuesto a alguien.",
    "💰 PiBot confirma: competir por orgullo también cuenta como estrategia económica.",
]

def _event_location(update):
    m=update.effective_message
    return bool(m and update.effective_chat and update.effective_chat.id==MAIN_CHAT and getattr(m,'message_thread_id',None)==EVENT_THREAD)

def _resolve_target(update, context):
    m=update.effective_message
    if m and m.reply_to_message and m.reply_to_message.from_user:
        u=m.reply_to_message.from_user
        return u.id, (("@"+u.username) if u.username else (u.full_name or str(u.id)))
    if not context.args: return None
    raw=context.args[0].lstrip('@')
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT id_user,username,nombre FROM perfiles_tb WHERE lower(username)=lower(%s) LIMIT 1",(raw,)); row=c.fetchone()
        return (row[0],(("@"+row[1].lstrip("@")) if row[1] else (row[2] or raw))) if row else None
    finally:_put_connection(conn)


def _display_name(uid):
    if not uid:
        return "Sin postor"
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT username,nombre FROM perfiles_tb WHERE id_user=%s",(uid,)); r=c.fetchone()
        if r:
            username,nombre=r
            if username: return "@"+str(username).lstrip('@')
            if nombre: return str(nombre)
        return f"Usuario {uid}"
    finally:_put_connection(conn)

def _active_snapshot():
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""SELECT auction_id,subastado_nombre,puja_actual,postor_id,termina_en
          FROM user_auctions_tb WHERE estado='activa' AND chat_id=%s AND thread_id=%s
          ORDER BY auction_id DESC LIMIT 1""",(MAIN_CHAT,EVENT_THREAD)); return c.fetchone()
    finally:_put_connection(conn)

def _create(seller_id,seller_name):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT auction_id FROM user_auctions_tb WHERE estado='activa' AND chat_id=%s AND thread_id=%s FOR UPDATE",(MAIN_CHAT,EVENT_THREAD))
        if c.fetchone(): conn.rollback(); return 'busy',None
        c.execute("INSERT INTO user_auctions_tb(chat_id,thread_id,subastado_id,subastado_nombre,termina_en) VALUES(%s,%s,%s,%s,now()+(%s * interval '1 second')) RETURNING auction_id,termina_en",(MAIN_CHAT,EVENT_THREAD,seller_id,seller_name,AUCTION_SECONDS))
        row=c.fetchone(); conn.commit(); return 'ok',row
    except Exception as e: conn.rollback(); print('[AUCTION] create',e); return 'error',None
    finally:_put_connection(conn)

def _bid(uid,amount):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT auction_id,subastado_id,puja_actual,postor_id FROM user_auctions_tb WHERE estado='activa' AND chat_id=%s AND thread_id=%s AND termina_en>now() FOR UPDATE",(MAIN_CHAT,EVENT_THREAD)); a=c.fetchone()
        if not a: conn.rollback(); return 'none',None
        aid,target,current,old=a; current=current or 0
        if uid==target: conn.rollback(); return 'self',None
        if amount<=current: conn.rollback(); return 'low',current
        # Reserve only the difference for the current leader; otherwise reserve full bid and release old reservation.
        needed=amount-current if old==uid else amount
        c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo>=%s",(needed,uid,needed))
        if c.rowcount!=1: conn.rollback(); return 'money',needed
        if old and old!=uid:
            c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(current,old))
        c.execute("UPDATE user_auctions_tb SET puja_actual=%s,postor_id=%s,actualizado_en=now() WHERE auction_id=%s",(amount,uid,aid))
        c.execute("INSERT INTO auction_bids_tb(auction_id,postor_id,monto) VALUES(%s,%s,%s)",(aid,uid,amount))
        conn.commit(); return 'ok',(aid,current)
    except Exception as e: conn.rollback(); print('[AUCTION] bid',e); return 'error',None
    finally:_put_connection(conn)

def _cancel(actor):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT auction_id,puja_actual,postor_id FROM user_auctions_tb WHERE estado='activa' AND chat_id=%s AND thread_id=%s FOR UPDATE",(MAIN_CHAT,EVENT_THREAD)); row=c.fetchone()
        if not row: conn.rollback(); return False
        aid,amount,bidder=row
        if bidder and amount: c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(amount,bidder))
        c.execute("UPDATE user_auctions_tb SET estado='cancelada',cerrada_en=now(),cerrada_por=%s WHERE auction_id=%s",(actor,aid)); conn.commit(); return True
    except Exception as e: conn.rollback(); print('[AUCTION] cancel',e); return False
    finally:_put_connection(conn)

def _settle_one(aid):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT subastado_id,subastado_nombre,puja_actual,postor_id,recordatorio_5m FROM user_auctions_tb WHERE auction_id=%s AND estado='activa' FOR UPDATE",(aid,)); row=c.fetchone()
        if not row: conn.rollback(); return None
        target,name,amount,bidder,_=row; amount=amount or 0
        if not bidder:
            c.execute("UPDATE user_auctions_tb SET estado='sin_pujas',cerrada_en=now() WHERE auction_id=%s",(aid,)); conn.commit(); return ('empty',name,0,None,0,0)
        kiu=BOTMASTER_IDS[0] if BOTMASTER_IDS else None
        if not kiu: conn.rollback(); return ('config',name,amount,bidder,0,0)
        seller_share=(amount*80)//100; kiu_share=amount-seller_share
        c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(seller_share,target))
        if c.rowcount != 1:
            conn.rollback(); return ('config',name,amount,bidder,0,0)
        c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(kiu_share,kiu))
        if c.rowcount != 1:
            conn.rollback(); return ('config',name,amount,bidder,0,0)
        c.execute("UPDATE user_auctions_tb SET estado='finalizada',cerrada_en=now(),comision_kiu=%s,pago_subastado=%s WHERE auction_id=%s",(kiu_share,seller_share,aid))
        conn.commit(); return ('ok',name,amount,bidder,seller_share,kiu_share)
    except Exception as e: conn.rollback(); print('[AUCTION] settle',e); return None
    finally:_put_connection(conn)

async def subasta(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _event_location(update):
        return await update.effective_message.reply_text("🎉 Las subastas viven exclusivamente en Eventos.")
    if get_user_role(update.effective_user.id)<2:
        return await update.effective_message.reply_text("🔒 Solo administración puede abrir una subasta.")
    target=_resolve_target(update,context)
    if not target: return await update.effective_message.reply_text("Responde al mensaje de la persona o usa /subasta @usuario.")
    st,data=_create(*target)
    if st=='busy': return await update.effective_message.reply_text("🔨 Ya hay una subasta activa. Primero terminemos de vaciar una cartera a la vez. 😂")
    if st!='ok': return await update.effective_message.reply_text("No pude abrir la subasta. Inténtalo de nuevo.")
    await update.effective_message.reply_text(f"🔨 SUBASTA ABIERTA\n\n👤 {target[1]} entra al escaparate social de PiBot.\n⏳ Duración: 1 hora\n💰 Puja con /puja cantidad\n\n🏁 Al cerrar: 80% para la persona subastada y 20% para Kiu.\n\n¿Quién rompe el silencio con la primera oferta? 👀")

async def puja(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _event_location(update): return
    try: amount=int(context.args[0].replace(',','').replace('.',''))
    except Exception: return await update.effective_message.reply_text("💰 Usa /puja 10000, por ejemplo.")
    if amount<100: return await update.effective_message.reply_text("😂 Eso no es una puja, es una propina. Mínimo 100 PiPesos.")
    st,data=_bid(update.effective_user.id,amount)
    if st=='ok': return await update.effective_message.reply_text(f"🔨 ¡{amount:,} PiPesos!\n{random.choice(LINES)}")
    msgs={'none':'No hay una subasta activa.','self':'JAJAJA no puedes pujar por tu propia subasta.','low':f'La puja actual ya es de {data:,} PiPesos. Toca superar eso.','money':'No tienes PiPesos disponibles suficientes para reservar esa puja.'}
    await update.effective_message.reply_text(msgs.get(st,'No pude registrar esa puja.'))


async def versubasta(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _event_location(update):
        return await update.effective_message.reply_text("🎉 Las subastas viven exclusivamente en Eventos.")
    row=_active_snapshot()
    if not row: return await update.effective_message.reply_text("🔨 No hay una subasta activa ahora mismo.")
    aid,name,amount,bidder,end=row; amount=amount or 0
    if end.tzinfo is None: end=end.replace(tzinfo=timezone.utc)
    secs=max(0,int((end-datetime.now(timezone.utc)).total_seconds())); mins,ss=divmod(secs,60); hh,mins=divmod(mins,60)
    leader=_display_name(bidder) if bidder else "Todavía nadie"
    await update.effective_message.reply_text(f"🔨 SUBASTA ACTIVA #{aid}\n\n👤 {name}\n💰 Puja actual: {amount:,} PiPesos\n🏆 Mejor postor: {leader}\n⏳ Tiempo restante: {hh:02d}:{mins:02d}:{ss:02d}\n\nUsa /puja cantidad para superar la oferta.")

async def cancelarsubasta(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _event_location(update): return
    if get_user_role(update.effective_user.id)<2: return
    ok=_cancel(update.effective_user.id)
    await update.effective_message.reply_text("🛑 Subasta cancelada. Las pujas reservadas fueron devueltas." if ok else "No hay una subasta activa.")

async def auction_maintenance_job(context:ContextTypes.DEFAULT_TYPE):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT auction_id,subastado_nombre,puja_actual,termina_en,recordatorio_5m FROM user_auctions_tb WHERE estado='activa' AND chat_id=%s AND thread_id=%s",(MAIN_CHAT,EVENT_THREAD)); rows=c.fetchall()
    finally:_put_connection(conn)
    now=datetime.now(timezone.utc)
    for aid,name,amount,end,reminded in rows:
        if end.tzinfo is None: end=end.replace(tzinfo=timezone.utc)
        left=(end-now).total_seconds()
        if left<=0:
            result=_settle_one(aid)
            if not result: continue
            status,nm,total,bidder,seller,kiu=result
            if status=='ok': text=f"🔨 ¡VENDIDO!\n\n👤 {nm}\n💰 Puja final: {total:,} PiPesos\n🏆 Ganador de la subasta: {_display_name(bidder)}\n\n💵 80% → {seller:,} PiPesos para {nm}\n👑 20% → {kiu:,} PiPesos para Kiu\n\nPiBot da por terminadas las malas decisiones financieras de esta hora. 😂"
            elif status=='empty': text=f"🔨 Terminó la subasta de {nm} sin pujas. El mercado ha hablado… cruelmente. 😂"
            else: continue
            await context.bot.send_message(MAIN_CHAT,text,message_thread_id=EVENT_THREAD)
        elif left<=300 and not reminded:
            conn=_get_connection()
            try:
                c=conn.cursor(); c.execute("UPDATE user_auctions_tb SET recordatorio_5m=TRUE WHERE auction_id=%s AND recordatorio_5m=FALSE RETURNING auction_id",(aid,)); changed=c.fetchone(); conn.commit()
            except Exception: conn.rollback(); changed=None
            finally:_put_connection(conn)
            if changed:
                await context.bot.send_message(MAIN_CHAT,f"⏰ ¡ÚLTIMOS 5 MINUTOS!\n🔨 {name} sigue en subasta.\n💰 Puja actual: {(amount or 0):,} PiPesos\n\nUna… dos… todavía NO vendido. 👀",message_thread_id=EVENT_THREAD)
