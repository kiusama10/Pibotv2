"""Dibuja y Adivina: partida por chat+tema, canvas privado del dibujante y respuestas en Telegram."""
import os, random, secrets, threading, time, unicodedata, io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection
from PIL import Image, ImageDraw

ROUND_SECONDS=120
CHANGE_COST=100
WIN_PRIZE=1500
WEBAPP_BASE_URL=(os.getenv("WEBAPP_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip('/')
WORDS_NORMAL=["dragón","castillo","pizza","guitarra","tortuga","avión","volcán","fantasma","corona","reloj","café","paraguas","robot","cohete","sirena","espada","gato","pingüino","mariposa","laberinto","pirata","tesoro","luna","estrella","helado","bicicleta","barco","cactus","dinosaurio","martillo","candado","llave","máscara","libro","vela","ancla","globo","zapato","sombrero"]
WORDS_BDSM=["collar","cuerda","antifaz","fusta","látigo","aftercare","consentimiento","brat","switch","pet","dominante","sumisión","límites","palabra segura","negociación","confianza","campanita","esposas"]
WORDS=WORDS_NORMAL+WORDS_BDSM
# Estado de trazos es efímero: si Render reinicia, la ronda persistente expira/reinicia sin tocar dinero.
_strokes={}; _stroke_lock=threading.Lock()
_chat_feed={}; _feed_lock=threading.Lock()
_canvas_versions={}; _version_lock=threading.Lock()

def ensure_drawing_tables():
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS drawing_games_tb(
          game_id text PRIMARY KEY, chat_id bigint NOT NULL, thread_id bigint,
          creator_id bigint NOT NULL, status text NOT NULL DEFAULT 'waiting',
          drawer_id bigint, word text, drawer_token text, viewer_token text, round_no int NOT NULL DEFAULT 0,
          round_ends_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""")
        c.execute("ALTER TABLE drawing_games_tb ADD COLUMN IF NOT EXISTS viewer_token text")
        c.execute("ALTER TABLE drawing_games_tb ADD COLUMN IF NOT EXISTS live_message_id bigint")
        c.execute("DROP INDEX IF EXISTS uq_drawing_active_location")
        c.execute("""CREATE UNIQUE INDEX uq_drawing_active_location ON drawing_games_tb(chat_id,COALESCE(thread_id,0)) WHERE status='active'""")
        c.execute("""CREATE TABLE IF NOT EXISTS drawing_players_tb(game_id text REFERENCES drawing_games_tb(game_id) ON DELETE CASCADE,user_id bigint NOT NULL,display_name text NOT NULL,turn_order int NOT NULL,joined_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(game_id,user_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS drawing_round_wins_tb(game_id text NOT NULL,round_no int NOT NULL,winner_id bigint NOT NULL,prize bigint NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(game_id,round_no))""")
        conn.commit()
    except Exception: conn.rollback(); raise
    finally:_put_connection(conn)

def _loc(update):
    m=update.effective_message
    return update.effective_chat.id, (m.message_thread_id if m else None)

def _norm(s):
    s=unicodedata.normalize('NFD',(s or '').strip().lower())
    return ''.join(ch for ch in s if unicodedata.category(ch)!='Mn')

def _name(u): return u.username or u.first_name or str(u.id)

def _new_word(old=None):
    choices=[w for w in WORDS if w!=old]
    return random.choice(choices)

def _reserve(uid, amount, c):
    c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo >= %s",(amount,uid,amount)); return c.rowcount==1

def _pay(uid, amount, c):
    c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(amount,uid)); return c.rowcount==1

async def dibujar(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private':
        await update.effective_message.reply_text("🎨 Dibuja y Adivina se crea dentro del grupo/tema donde quieran jugar."); return
    chat,thread=_loc(update); uid=update.effective_user.id; gid=secrets.token_hex(8)
    conn=_get_connection()
    try:
        c=conn.cursor()
        # Cada /dibujar es una ronda independiente; limpia estados legado que no deben bloquear.
        c.execute("UPDATE drawing_games_tb SET status='cancelled',word=NULL,drawer_token=NULL,viewer_token=NULL,round_ends_at=NULL,updated_at=now() WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) AND (status IN ('waiting','between') OR (status='active' AND (round_ends_at IS NULL OR round_ends_at<=now())))",(chat,thread))
        c.execute("SELECT 1 FROM drawing_games_tb WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) AND status='active' AND round_ends_at>now()",(chat,thread))
        if c.fetchone(): conn.rollback(); await update.effective_message.reply_text("🎨 Hay un dibujo activo en este tema. Espera a que termine o usa /matardibujo."); return
        c.execute("INSERT INTO drawing_games_tb(game_id,chat_id,thread_id,creator_id) VALUES(%s,%s,%s,%s)",(gid,chat,thread,uid))
        c.execute("INSERT INTO drawing_players_tb(game_id,user_id,display_name,turn_order) VALUES(%s,%s,%s,0)",(gid,uid,_name(update.effective_user))); conn.commit()
    except Exception:
        conn.rollback(); await update.effective_message.reply_text("⚠️ No pude crear la partida."); return
    finally:_put_connection(conn)
    await _start_round(context,gid)

async def _send_drawer(context, gid, uid, word, token):
    # Sin PV: el acceso al lienzo vive en el mensaje de la ronda.
    return True

def _render_canvas_bytes(gid):
    """Renderiza los trazos actuales como JPEG para mostrarlos dentro de Telegram."""
    with _stroke_lock:
        strokes=list(_strokes.get(gid,[]))
    im=Image.new('RGB',(1200,900),'white'); d=ImageDraw.Draw(im)
    for x in strokes:
        if not isinstance(x,dict): continue
        if x.get('t')=='clear':
            d.rectangle((0,0,1200,900),fill='white'); continue
        if x.get('t')!='s': continue
        try:
            a=x.get('a') or [0,0]; b=x.get('b') or [0,0]
            col=x.get('c') or '#111111'; w=max(1,min(60,int(float(x.get('w',7)))))
            d.line((float(a[0]),float(a[1]),float(b[0]),float(b[1])),fill=col,width=w)
        except Exception: pass
    out=io.BytesIO(); im.save(out,'JPEG',quality=88,optimize=True); out.seek(0); out.name='pibot_dibujo.jpg'; return out

def _round_caption(nr,drawer_name):
    return f"🎨 RONDA {nr} · {drawer_name} está dibujando\n⏱️ Tienes 2 minutos\n\n💬 Adivina escribiendo en este chat.\n🏆 Primer acierto: 1,500 PiPesos"

async def _start_round(context,gid):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,round_no,status FROM drawing_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
        if not g or g[3] not in ('waiting','active'): conn.rollback(); return False
        chat,thread,rno,_=g
        c.execute("SELECT user_id,display_name FROM drawing_players_tb WHERE game_id=%s ORDER BY turn_order",(gid,)); ps=c.fetchall()
        if len(ps)<1: conn.rollback(); return False
        nr=rno+1; drawer=ps[(nr-1)%len(ps)]; word=_new_word(); token=secrets.token_urlsafe(24); viewer_token=secrets.token_urlsafe(24)
        c.execute("UPDATE drawing_games_tb SET status='active',drawer_id=%s,word=%s,drawer_token=%s,viewer_token=%s,round_no=%s,round_ends_at=now()+(%s||' seconds')::interval,live_message_id=NULL,updated_at=now() WHERE game_id=%s",(drawer[0],word,token,viewer_token,nr,ROUND_SECONDS,gid)); conn.commit()
    except Exception: conn.rollback(); return False
    finally:_put_connection(conn)
    with _stroke_lock:_strokes[gid]=[]
    with _feed_lock:_chat_feed[gid]=[]
    with _version_lock:_canvas_versions[gid]=1
    rows=[]
    if WEBAPP_BASE_URL:
        rows.append([InlineKeyboardButton('🖌️ ABRIR LIENZO · SOLO DIBUJANTE',url=f"{WEBAPP_BASE_URL}/pibot-canvas-v4?game={gid}&token={token}&mode=draw")])
    kb=InlineKeyboardMarkup(rows) if rows else None
    try:
        msg=await context.bot.send_photo(chat,photo=_render_canvas_bytes(gid),caption=_round_caption(nr,drawer[1]),message_thread_id=thread,reply_markup=kb)
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("UPDATE drawing_games_tb SET live_message_id=%s WHERE game_id=%s AND round_no=%s",(msg.message_id,gid,nr)); conn.commit()
        except Exception: conn.rollback()
        finally:_put_connection(conn)
    except Exception:
        return False
    context.job_queue.run_repeating(_live_canvas_job,interval=3,first=2,data={"gid":gid,"round":nr,"last":-1},name=f"drawlive:{gid}:{nr}")
    context.job_queue.run_once(_round_timeout,ROUND_SECONDS+1,data={"gid":gid,"round":nr},name=f"draw:{gid}:{nr}")
    return True

async def _live_canvas_job(context:ContextTypes.DEFAULT_TYPE):
    data=context.job.data; gid=data['gid']; rno=data['round']
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT d.chat_id,d.live_message_id,d.status,d.round_no,COALESCE(p.display_name,'Alguien'),d.drawer_token FROM drawing_games_tb d LEFT JOIN drawing_players_tb p ON p.game_id=d.game_id AND p.user_id=d.drawer_id WHERE d.game_id=%s",(gid,)); g=c.fetchone()
    finally:_put_connection(conn)
    if not g or g[2]!='active' or g[3]!=rno or not g[1]: context.job.schedule_removal(); return
    with _version_lock: ver=_canvas_versions.get(gid,0)
    if ver==data.get('last'): return
    try:
        
        live_kb=None
        if WEBAPP_BASE_URL and g[5]:
            live_kb=InlineKeyboardMarkup([[InlineKeyboardButton('🖌️ ABRIR LIENZO · SOLO DIBUJANTE',url=f"{WEBAPP_BASE_URL}/pibot-canvas-v4?game={gid}&token={g[5]}&mode=draw")]])
        await context.bot.edit_message_media(chat_id=g[0],message_id=g[1],media=InputMediaPhoto(media=_render_canvas_bytes(gid),caption=_round_caption(rno,g[4])),reply_markup=live_kb)
        data['last']=ver
    except Exception:
        # Un fallo temporal de Telegram no mata la ronda; se reintenta en el siguiente tick.
        pass

async def matar_dibujo(update:Update, context:ContextTypes.DEFAULT_TYPE):
    """Cierra a la fuerza la ronda del tema. Creador o admin; no mueve PiPesos."""
    if update.effective_chat.type=='private': return await update.effective_message.reply_text("Úsalo en el grupo/tema del dibujo.")
    chat,thread=_loc(update); uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT game_id,creator_id,status FROM drawing_games_tb WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) AND status IN ('waiting','active','between') ORDER BY created_at DESC LIMIT 1 FOR UPDATE",(chat,thread)); row=c.fetchone()
        if not row:
            conn.rollback(); return await update.effective_message.reply_text("🎨 No había dibujo activo. El tema ya está limpio y listo para /dibujar.")
        gid,creator,_status=row
        allowed=(uid==creator)
        if not allowed:
            try:
                member=await context.bot.get_chat_member(chat,uid); allowed=member.status in ('administrator','creator')
            except Exception: allowed=False
        if not allowed: conn.rollback(); return await update.effective_message.reply_text("❌ Solo quien inició el dibujo o un administrador puede cerrarlo.")
        c.execute("UPDATE drawing_games_tb SET status='cancelled',word=NULL,drawer_token=NULL,viewer_token=NULL,round_ends_at=NULL,updated_at=now() WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) AND status IN ('waiting','active','between')",(chat,thread)); conn.commit()
        try:
            for job in context.job_queue.jobs():
                if job.name and (job.name.startswith(f"draw:{gid}:") or job.name.startswith(f"drawlive:{gid}:")):
                    job.schedule_removal()
        except Exception:
            pass
        with _stroke_lock: _strokes.pop(gid,None)
        await update.effective_message.reply_text("☠️ Dibujo cerrado. Ya no existe una ronda activa aquí. Usa /dibujar o 🎨 Tomar turno para iniciar otra.")
    except Exception:
        conn.rollback(); await update.effective_message.reply_text("⚠️ No pude cerrar el dibujo.")
    finally: _put_connection(conn)

async def drawing_callback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; p=q.data.split(':'); action,gid=p[1],p[2]; uid=q.from_user.id
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,creator_id,status,drawer_id,word,round_no FROM drawing_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
        if not g: conn.rollback(); await q.answer("Partida terminada.",show_alert=True); return
        chat,thread,creator,status,drawer,word,rno=g
        if action in ('take','start','cancel') and (q.message.chat_id!=chat or q.message.message_thread_id!=thread): conn.rollback(); await q.answer("Esta partida pertenece a otro tema.",show_alert=True); return
        if action=='take':
            if status=='active': conn.rollback(); await q.answer("⏳ Espera a que termine el dibujo actual.",show_alert=True); return
            conn.rollback(); await q.answer("🎨 Tomando turno…")
            class _U:
                effective_user=q.from_user; effective_chat=q.message.chat; effective_message=q.message
            return await dibujar(_U(),context)
        if action=='cancel':
            if uid!=creator or status!='waiting': conn.rollback(); await q.answer("No puedes cancelarla ahora.",show_alert=True); return
            c.execute("UPDATE drawing_games_tb SET status='cancelled',updated_at=now() WHERE game_id=%s",(gid,)); conn.commit(); await q.answer('Partida cancelada.'); await q.edit_message_reply_markup(None); await q.message.reply_text("❌ Partida cancelada."); return
        if action=='start':
            if uid!=creator or status!='waiting': conn.rollback(); await q.answer("Solo quien creó la partida puede iniciarla.",show_alert=True); return
            c.execute("SELECT count(*) FROM drawing_players_tb WHERE game_id=%s",(gid,)); n=c.fetchone()[0]
            if n<2: conn.rollback(); await q.answer("Se necesitan al menos 2 jugadores.",show_alert=True); return
            conn.commit(); await q.answer('¡Empieza la partida!'); await q.edit_message_reply_markup(None)
        elif action=='change':
            if status!='active' or uid!=drawer: conn.rollback(); await q.answer("No eres el dibujante actual.",show_alert=True); return
            if not _reserve(uid,CHANGE_COST,c): conn.rollback(); await q.answer("No tienes 100 PiPesos.",show_alert=True); return
            nw=_new_word(word); token=secrets.token_urlsafe(24); c.execute("UPDATE drawing_games_tb SET word=%s,drawer_token=%s,updated_at=now() WHERE game_id=%s",(nw,token,gid)); conn.commit()
            with _stroke_lock:_strokes[gid]=[]
            await q.answer("Palabra cambiada. -100 PiPesos",show_alert=True); return
    except Exception:
        conn.rollback(); await q.answer("Error de base de datos.",show_alert=True); return
    finally:_put_connection(conn)
    if action=='start': await _start_round(context,gid)

def _stop_live_jobs(context,gid):
    try:
        for job in context.job_queue.jobs():
            if job.name and (job.name.startswith(f"drawlive:{gid}:") or job.name.startswith(f"draw:{gid}:")):
                job.schedule_removal()
    except Exception: pass


async def drawing_guess(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.text or update.effective_message.text.startswith('/') or update.effective_chat.type=='private': return
    chat,thread=_loc(update); uid=update.effective_user.id; guess=_norm(update.effective_message.text)
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT game_id,drawer_id,word,round_no FROM drawing_games_tb WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) AND status='active' AND round_ends_at>now() FOR UPDATE",(chat,thread)); g=c.fetchone()
        if not g: conn.rollback(); return
        gid,drawer,word,rno=g
        # Todo comentario de espectadores se refleja en el lienzo del artista en tiempo casi real.
        if uid!=drawer:
            txt=(update.effective_message.text or '').strip()[:180]
            if txt:
                with _feed_lock:
                    feed=_chat_feed.setdefault(gid,[]); feed.append({'name':_name(update.effective_user)[:40],'text':txt,'ts':int(time.time())}); del feed[:-40]
        if uid==drawer or guess!=_norm(word): conn.rollback(); return
        c.execute("INSERT INTO drawing_round_wins_tb(game_id,round_no,winner_id,prize) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",(gid,rno,uid,WIN_PRIZE))
        if c.rowcount!=1: conn.rollback(); return
        if not _pay(uid,WIN_PRIZE,c): conn.rollback(); return
        c.execute("UPDATE drawing_games_tb SET status='finished',word=NULL,drawer_token=NULL,viewer_token=NULL,round_ends_at=NULL,updated_at=now() WHERE game_id=%s AND round_no=%s",(gid,rno)); conn.commit()
    except Exception: conn.rollback(); return
    finally:_put_connection(conn)
    _stop_live_jobs(context,gid)
    winner=_name(update.effective_user)
    text=f"🏆 ¡{winner} acertó!\n🎨 La palabra era {word.upper()}.\n💰 +1,500 PiPesos\n\n✅ La ronda terminó."
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('🎨 Tomar turno',callback_data=f'draw:take:{gid}')]])
    # Aviso independiente en el mismo tema: no depende de que Telegram conserve el reply.
    await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=text,reply_markup=kb)
    # El mensaje del dibujo también queda marcado como finalizado para que el artista lo vea al instante.
    try:
        conn=_get_connection(); c=conn.cursor(); c.execute("SELECT live_message_id FROM drawing_games_tb WHERE game_id=%s",(gid,)); rr=c.fetchone(); conn.rollback(); _put_connection(conn)
        if rr and rr[0]:
            await context.bot.edit_message_caption(chat_id=chat,message_id=rr[0],caption=f"🎉 {winner} ADIVINÓ · {word.upper()}\n💰 Premio: 1,500 PiPesos\n✅ Ronda terminada",reply_markup=kb)
    except Exception: pass

async def _round_timeout(context:ContextTypes.DEFAULT_TYPE):
    gid=context.job.data['gid']; rno=context.job.data['round']; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,word,status,round_no FROM drawing_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
        if not g or g[3]!='active' or g[4]!=rno: conn.rollback(); return
        chat,thread,word,_,_=g; c.execute("UPDATE drawing_games_tb SET status='finished',word=NULL,drawer_token=NULL,viewer_token=NULL,round_ends_at=NULL,updated_at=now() WHERE game_id=%s",(gid,)); conn.commit()
    except Exception: conn.rollback(); return
    finally:_put_connection(conn)
    _stop_live_jobs(context,gid)
    await context.bot.send_message(chat,f"⏰ Tiempo. La palabra era {word.upper()}. Nadie cobró esta ronda.\n\nLa ronda terminó. Quien quiera dibujar puede tomar el siguiente turno.",message_thread_id=thread,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🎨 Tomar turno',callback_data=f'draw:take:{gid}')]]))

async def _next_round_job(context): await _start_round(context,context.job.data['gid'])

async def drawing_maintenance_job(context:ContextTypes.DEFAULT_TYPE):
    """Recover expired drawing rounds after Render restarts; never touches balances."""
    conn=_get_connection(); expired=[]
    try:
        c=conn.cursor(); c.execute("SELECT game_id,chat_id,thread_id,word,round_no FROM drawing_games_tb WHERE status='active' AND round_ends_at<=now() FOR UPDATE SKIP LOCKED LIMIT 20")
        expired=c.fetchall()
        for gid,chat,thread,word,rno in expired:
            c.execute("UPDATE drawing_games_tb SET status='finished',word=NULL,drawer_token=NULL,viewer_token=NULL,round_ends_at=NULL,updated_at=now() WHERE game_id=%s AND status='active' AND round_no=%s",(gid,rno))
        conn.commit()
    except Exception:
        conn.rollback(); expired=[]
    finally:_put_connection(conn)
    for gid,chat,thread,word,rno in expired:
        try: await context.bot.send_message(chat,f"⏰ Tiempo. La palabra era {word.upper()}. Nadie cobró esta ronda.\n\nLa ronda terminó. Quien quiera dibujar puede tomar el siguiente turno.",message_thread_id=thread,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🎨 Tomar turno',callback_data=f'draw:take:{gid}')]]))
        except Exception: pass
    
# HTTP API usado por el lienzo. Token secreto del dibujante valida escritura.
def canvas_get(gid,token):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT 1 FROM drawing_games_tb WHERE game_id=%s AND (drawer_token=%s OR viewer_token=%s) AND status='active' AND round_ends_at>now()",(gid,token,token)); ok=bool(c.fetchone())
    finally:_put_connection(conn)
    if not ok:return None
    with _stroke_lock:return list(_strokes.get(gid,[]))

def canvas_meta(gid,token):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT word FROM drawing_games_tb WHERE game_id=%s AND drawer_token=%s AND status='active' AND round_ends_at>now()",(gid,token)); r=c.fetchone()
    finally:_put_connection(conn)
    return {"word":r[0]} if r else None

def canvas_change_word(gid,token):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT drawer_id,word FROM drawing_games_tb WHERE game_id=%s AND drawer_token=%s AND status='active' AND round_ends_at>now() FOR UPDATE",(gid,token)); r=c.fetchone()
        if not r: conn.rollback(); return None
        uid,old=r
        if not _reserve(uid,CHANGE_COST,c): conn.rollback(); return {"error":"money"}
        nw=_new_word(old); c.execute("UPDATE drawing_games_tb SET word=%s,updated_at=now() WHERE game_id=%s",(nw,gid)); conn.commit()
        with _stroke_lock:_strokes[gid]=[]
        with _version_lock:_canvas_versions[gid]=_canvas_versions.get(gid,0)+1
        return {"word":nw}
    except Exception:
        conn.rollback(); return None
    finally:_put_connection(conn)

def canvas_chat(gid,token):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT 1 FROM drawing_games_tb WHERE game_id=%s AND drawer_token=%s AND status='active' AND round_ends_at>now()",(gid,token)); ok=bool(c.fetchone())
    finally:_put_connection(conn)
    if not ok:return None
    with _feed_lock:return list(_chat_feed.get(gid,[]))

def canvas_append(gid,token,items):
    if not isinstance(items,list) or len(items)>200:return False
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT 1 FROM drawing_games_tb WHERE game_id=%s AND drawer_token=%s AND status='active' AND round_ends_at>now()",(gid,token)); ok=bool(c.fetchone())
    finally:_put_connection(conn)
    if not ok:return False
    clean=[]
    for x in items:
        if isinstance(x,dict) and x.get('t') in ('s','clear'):
            clean.append(x)
    with _stroke_lock:
        arr=_strokes.setdefault(gid,[]); arr.extend(clean); del arr[:-8000]
    if clean:
        with _version_lock:_canvas_versions[gid]=_canvas_versions.get(gid,0)+1
    return True
