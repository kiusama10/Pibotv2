"""Dibuja y Adivina: partida por chat+tema, canvas privado del dibujante y respuestas en Telegram."""
import os, random, secrets, threading, time, unicodedata
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection

ROUND_SECONDS=120
CHANGE_COST=100
WIN_PRIZE=1500
WEBAPP_BASE_URL=(os.getenv("WEBAPP_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").rstrip('/')
WORDS_NORMAL=["dragón","castillo","pizza","guitarra","tortuga","avión","volcán","fantasma","corona","reloj","café","paraguas","robot","cohete","sirena","espada","gato","pingüino","mariposa","laberinto","pirata","tesoro","luna","estrella","helado","bicicleta","barco","cactus","dinosaurio","martillo","candado","llave","máscara","libro","vela","ancla","globo","zapato","sombrero"]
WORDS_BDSM=["collar","cuerda","antifaz","fusta","látigo","aftercare","consentimiento","brat","switch","pet","dominante","sumisión","límites","palabra segura","negociación","confianza","campanita","esposas"]
WORDS=WORDS_NORMAL+WORDS_BDSM
# Estado de trazos es efímero: si Render reinicia, la ronda persistente expira/reinicia sin tocar dinero.
_strokes={}; _stroke_lock=threading.Lock()

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
        c.execute("DROP INDEX IF EXISTS uq_drawing_active_location")
        c.execute("""CREATE UNIQUE INDEX uq_drawing_active_location ON drawing_games_tb(chat_id,COALESCE(thread_id,0)) WHERE status IN ('waiting','active','between')""")
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
        c=conn.cursor(); c.execute("SELECT 1 FROM drawing_games_tb WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) AND status IN ('waiting','active','between')",(chat,thread))
        if c.fetchone(): conn.rollback(); await update.effective_message.reply_text("🎨 Ya hay una partida de Dibuja y Adivina aquí."); return
        c.execute("INSERT INTO drawing_games_tb(game_id,chat_id,thread_id,creator_id) VALUES(%s,%s,%s,%s)",(gid,chat,thread,uid))
        c.execute("INSERT INTO drawing_players_tb(game_id,user_id,display_name,turn_order) VALUES(%s,%s,%s,0)",(gid,uid,_name(update.effective_user))); conn.commit()
    except Exception:
        conn.rollback(); await update.effective_message.reply_text("⚠️ No pude crear la partida."); return
    finally:_put_connection(conn)
    await update.effective_message.reply_text("🎨 DIBUJA Y ADIVINA\n\nLa ronda empieza aquí mismo. Todo el grupo puede adivinar escribiendo en Telegram; no hay salas ni hace falta unirse para jugar.\n\n⏱️ 2 minutos por dibujo\n🏆 Primer acierto: 1,500 PiPesos\n🔄 Cambiar palabra: 100 PiPesos")
    await _start_round(context,gid)

async def _send_drawer(context, gid, uid, word, token):
    text=f"🎨 Te toca dibujar.\n\n🤫 Tu palabra es: {word.upper()}\n⏱️ Tienes 2 minutos."
    rows=[]
    if WEBAPP_BASE_URL:
        rows.append([InlineKeyboardButton("🖌️ Abrir lienzo",web_app=WebAppInfo(url=f"{WEBAPP_BASE_URL}/draw?game={gid}&token={token}"))])
    rows.append([InlineKeyboardButton("🔄 Cambiar palabra · 100",callback_data=f"draw:change:{gid}")])
    try: await context.bot.send_message(uid,text,reply_markup=InlineKeyboardMarkup(rows))
    except Exception: return False
    return True

async def _start_round(context,gid):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,round_no,status FROM drawing_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
        if not g or g[3] not in ('waiting','active'): conn.rollback(); return False
        chat,thread,rno,_=g
        c.execute("SELECT user_id,display_name FROM drawing_players_tb WHERE game_id=%s ORDER BY turn_order",(gid,)); ps=c.fetchall()
        if len(ps)<1: conn.rollback(); return False
        nr=rno+1; drawer=ps[(nr-1)%len(ps)]; word=_new_word(); token=secrets.token_urlsafe(24); viewer_token=secrets.token_urlsafe(24)
        c.execute("UPDATE drawing_games_tb SET status='active',drawer_id=%s,word=%s,drawer_token=%s,viewer_token=%s,round_no=%s,round_ends_at=now()+(%s||' seconds')::interval,updated_at=now() WHERE game_id=%s",(drawer[0],word,token,viewer_token,nr,ROUND_SECONDS,gid)); conn.commit()
    except Exception: conn.rollback(); return False
    finally:_put_connection(conn)
    with _stroke_lock:_strokes[gid]=[]
    ok=await _send_drawer(context,gid,drawer[0],word,token)
    if not ok:
        await context.bot.send_message(chat,"⚠️ El dibujante debe abrir PiBot por privado primero. La ronda no puede mostrarle la palabra.",message_thread_id=thread)
        return False
    rows=[[InlineKeyboardButton('🎨 Pedir turno',callback_data=f'draw:join:{gid}')]]
    if WEBAPP_BASE_URL:
        rows.insert(0,[InlineKeyboardButton('👀 Ver lienzo en vivo',url=f"{WEBAPP_BASE_URL}/draw?game={gid}&token={viewer_token}&view=1")])
    viewer_kb=InlineKeyboardMarkup(rows)
    await context.bot.send_message(chat,f"🎨 RONDA {nr}\n🖌️ Dibuja: {drawer[1]}\n⏱️ 2:00\n\nEscriban sus respuestas aquí. ¡Primer acierto gana 1,500 PiPesos!",message_thread_id=thread,reply_markup=viewer_kb)
    context.job_queue.run_once(_round_timeout,ROUND_SECONDS+1,data={"gid":gid,"round":nr},name=f"draw:{gid}:{nr}")
    return True

async def drawing_callback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; p=q.data.split(':'); action,gid=p[1],p[2]; uid=q.from_user.id
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,creator_id,status,drawer_id,word,round_no FROM drawing_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
        if not g: conn.rollback(); await q.answer("Partida terminada.",show_alert=True); return
        chat,thread,creator,status,drawer,word,rno=g
        if action in ('join','start','cancel') and (q.message.chat_id!=chat or q.message.message_thread_id!=thread): conn.rollback(); await q.answer("Esta partida pertenece a otro tema.",show_alert=True); return
        if action=='join':
            if status not in ('waiting','active','between'): conn.rollback(); await q.answer("Esta partida ya terminó.",show_alert=True); return
            c.execute("SELECT 1 FROM drawing_players_tb WHERE game_id=%s AND user_id=%s",(gid,uid))
            if c.fetchone(): conn.rollback(); await q.answer("Ya estás dentro 😹"); return
            c.execute("SELECT COALESCE(max(turn_order),-1)+1 FROM drawing_players_tb WHERE game_id=%s",(gid,)); order=c.fetchone()[0]
            c.execute("INSERT INTO drawing_players_tb(game_id,user_id,display_name,turn_order) VALUES(%s,%s,%s,%s)",(gid,uid,_name(q.from_user),order)); conn.commit(); await q.answer('Turno solicitado 🎨'); await q.message.reply_text(f"🎨 {_name(q.from_user)} pidió turno para dibujar. Todo el grupo sigue participando con sus respuestas."); return
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
            await _send_drawer(context,gid,uid,nw,token); await q.answer("Palabra cambiada. -100 PiPesos",show_alert=True); return
    except Exception:
        conn.rollback(); await q.answer("Error de base de datos.",show_alert=True); return
    finally:_put_connection(conn)
    if action=='start': await _start_round(context,gid)

async def drawing_guess(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not update.effective_message or not update.effective_message.text or update.effective_message.text.startswith('/') or update.effective_chat.type=='private': return
    chat,thread=_loc(update); uid=update.effective_user.id; guess=_norm(update.effective_message.text)
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT game_id,drawer_id,word,round_no FROM drawing_games_tb WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) AND status='active' AND round_ends_at>now() FOR UPDATE",(chat,thread)); g=c.fetchone()
        if not g: conn.rollback(); return
        gid,drawer,word,rno=g
        if uid==drawer or guess!=_norm(word): conn.rollback(); return
        c.execute("INSERT INTO drawing_round_wins_tb(game_id,round_no,winner_id,prize) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",(gid,rno,uid,WIN_PRIZE))
        if c.rowcount!=1: conn.rollback(); return
        if not _pay(uid,WIN_PRIZE,c): conn.rollback(); return
        c.execute("UPDATE drawing_games_tb SET status='between',word=NULL,drawer_token=NULL,viewer_token=NULL,round_ends_at=NULL,updated_at=now() WHERE game_id=%s AND round_no=%s",(gid,rno)); conn.commit()
    except Exception: conn.rollback(); return
    finally:_put_connection(conn)
    await update.effective_message.reply_text(f"🏆 ¡{_name(update.effective_user)} acertó!\nLa palabra era {word.upper()}.\n💰 +1,500 PiPesos")
    context.job_queue.run_once(_next_round_job,4,data={"gid":gid})

async def _round_timeout(context:ContextTypes.DEFAULT_TYPE):
    gid=context.job.data['gid']; rno=context.job.data['round']; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,word,status,round_no FROM drawing_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
        if not g or g[3]!='active' or g[4]!=rno: conn.rollback(); return
        chat,thread,word,_,_=g; c.execute("UPDATE drawing_games_tb SET status='between',word=NULL,drawer_token=NULL,viewer_token=NULL,round_ends_at=NULL,updated_at=now() WHERE game_id=%s",(gid,)); conn.commit()
    except Exception: conn.rollback(); return
    finally:_put_connection(conn)
    await context.bot.send_message(chat,f"⏰ Tiempo. La palabra era {word.upper()}. Nadie cobró esta ronda.",message_thread_id=thread)
    context.job_queue.run_once(_next_round_job,4,data={"gid":gid})

async def _next_round_job(context): await _start_round(context,context.job.data['gid'])

async def drawing_maintenance_job(context:ContextTypes.DEFAULT_TYPE):
    """Recover expired drawing rounds after Render restarts; never touches balances."""
    conn=_get_connection(); expired=[]
    try:
        c=conn.cursor(); c.execute("SELECT game_id,chat_id,thread_id,word,round_no FROM drawing_games_tb WHERE status='active' AND round_ends_at<=now() FOR UPDATE SKIP LOCKED LIMIT 20")
        expired=c.fetchall()
        for gid,chat,thread,word,rno in expired:
            c.execute("UPDATE drawing_games_tb SET status='between',word=NULL,drawer_token=NULL,viewer_token=NULL,round_ends_at=NULL,updated_at=now() WHERE game_id=%s AND status='active' AND round_no=%s",(gid,rno))
        conn.commit()
    except Exception:
        conn.rollback(); expired=[]
    finally:_put_connection(conn)
    for gid,chat,thread,word,rno in expired:
        try: await context.bot.send_message(chat,f"⏰ Tiempo. La palabra era {word.upper()}. Nadie cobró esta ronda.",message_thread_id=thread)
        except Exception: pass
        context.job_queue.run_once(_next_round_job,4,data={"gid":gid})

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
        return {"word":nw}
    except Exception:
        conn.rollback(); return None
    finally:_put_connection(conn)

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
    return True
