"""Juegos PvP persistentes del tema Juegos (528): Tortugas y Blackjack."""
import random
import uuid
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection

MAIN_CHAT_ID = -1003290179217
JUEGOS_THREAD_ID = 528
RACE_GOAL = 20

TURTLE_LINES = {
    1:["avanzó con la urgencia de un lunes 😭","dio un pasito... eventualmente llegará.","se distrajo viendo una hoja. +1."],
    2:["avanza sin prisa pero sin pausa.","se acordó de que esto era una carrera."],
    3:["agarra ritmo. Ya parece atleta.","cruza media pista con dignidad."],
    4:["mete velocidad y deja polvo detrás.","¡esa tortuga desayunó turbo!"],
    5:["sale disparada. ¿Eso sigue siendo una tortuga?","casi despega del caparazón."],
    6:["🚀 ¡TURBO! Alguien revise ese caparazón.","🔥 velocidad ilegal para una tortuga. +6."],
}
TURTLE_NAMES=["Donatello Fiscal","Caparazón del Caos","TurboLenta","Tortugón","Shelly","La Imparable"]


def ensure_casino_pvp_tables():
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS turtle_games_tb(
          game_id text PRIMARY KEY, chat_id bigint NOT NULL, thread_id bigint NOT NULL,
          creator_id bigint NOT NULL, stake bigint NOT NULL CHECK(stake>0), goal int NOT NULL DEFAULT 20,
          status text NOT NULL DEFAULT 'waiting', turn_index int NOT NULL DEFAULT 0,
          created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""")
        c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_turtle_active_location ON turtle_games_tb(chat_id,thread_id)
          WHERE status IN ('waiting','active')""")
        c.execute("""CREATE TABLE IF NOT EXISTS turtle_players_tb(
          game_id text REFERENCES turtle_games_tb(game_id) ON DELETE CASCADE, user_id bigint NOT NULL,
          display_name text NOT NULL, turtle_name text NOT NULL, position int NOT NULL DEFAULT 0,
          joined_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(game_id,user_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS blackjack_games_tb(
          game_id text PRIMARY KEY, chat_id bigint NOT NULL, thread_id bigint NOT NULL,
          creator_id bigint NOT NULL, rival_id bigint, stake bigint NOT NULL CHECK(stake>0),
          status text NOT NULL DEFAULT 'waiting', turn_user_id bigint, deck text[] NOT NULL DEFAULT '{}',
          hand_a text[] NOT NULL DEFAULT '{}', hand_b text[] NOT NULL DEFAULT '{}', stood_a bool NOT NULL DEFAULT false,
          stood_b bool NOT NULL DEFAULT false, action_started bool NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""")
        c.execute("ALTER TABLE blackjack_games_tb ADD COLUMN IF NOT EXISTS action_started bool NOT NULL DEFAULT false")
        # Tortuga personal + temporadas mensuales. Aditivo: no modifica saldos ni carreras históricas.
        c.execute("""CREATE TABLE IF NOT EXISTS turtle_profiles_tb(
          user_id bigint PRIMARY KEY REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
          turtle_name text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now())""")
        c.execute("""CREATE TABLE IF NOT EXISTS turtle_monthly_stats_tb(
          season text NOT NULL, user_id bigint NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
          races int NOT NULL DEFAULT 0, wins int NOT NULL DEFAULT 0,
          PRIMARY KEY(season,user_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS turtle_season_results_tb(
          season text NOT NULL, place int NOT NULL CHECK(place BETWEEN 1 AND 3),
          user_id bigint NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
          turtle_name text NOT NULL, wins int NOT NULL, races int NOT NULL, prize bigint NOT NULL,
          paid_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(season,place), UNIQUE(season,user_id))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_turtle_month_rank ON turtle_monthly_stats_tb(season,wins DESC,races ASC)")
        c.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_blackjack_active_location ON blackjack_games_tb(chat_id,thread_id)
          WHERE status IN ('waiting','active')""")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:_put_connection(conn)


def _reserve(user_id, amount, cur):
    cur.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo >= %s",(amount,user_id,amount))
    return cur.rowcount==1

def _pay(user_id, amount, cur):
    cur.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(amount,user_id))
    return cur.rowcount==1

def _loc(update):
    m=update.effective_message
    return update.effective_chat.id, (m.message_thread_id if m else None)

def _display_name(cur, uid):
    cur.execute("SELECT COALESCE(NULLIF(username,''),nombre,%s) FROM perfiles_tb WHERE id_user=%s",(f"Usuario {uid}",uid))
    row=cur.fetchone(); return row[0] if row else f"Usuario {uid}"

def _in_games(update):
    chat,thread=_loc(update)
    return chat == MAIN_CHAT_ID and update.effective_chat.type not in ('private',) and thread==JUEGOS_THREAD_ID

def _season_key(dt=None):
    dt = dt or datetime.now(ZoneInfo("America/Mexico_City"))
    return f"{dt.year:04d}-{dt.month:02d}"

def _previous_season_key():
    now=datetime.now(ZoneInfo("America/Mexico_City"))
    if now.month==1: return f"{now.year-1:04d}-12"
    return f"{now.year:04d}-{now.month-1:02d}"

def _clean_turtle_name(raw):
    name=re.sub(r"\s+"," ",(raw or "").strip())
    if not (2 <= len(name) <= 28): return None
    if any(ord(ch)<32 for ch in name): return None
    return name

def _get_or_create_turtle(cur, uid, suggested=None):
    cur.execute("SELECT turtle_name FROM turtle_profiles_tb WHERE user_id=%s",(uid,))
    row=cur.fetchone()
    if row: return row[0]
    base=_clean_turtle_name(suggested) or f"Tortuga {str(uid)[-4:]}"
    cur.execute("INSERT INTO turtle_profiles_tb(user_id,turtle_name) VALUES(%s,%s) ON CONFLICT(user_id) DO NOTHING RETURNING turtle_name",(uid,base))
    made=cur.fetchone()
    if made: return made[0]
    cur.execute("SELECT turtle_name FROM turtle_profiles_tb WHERE user_id=%s",(uid,)); return cur.fetchone()[0]

def _turtle_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Cambiar nombre",callback_data="turtle:rename"), InlineKeyboardButton("🏁 Crear carrera",callback_data="turtle:create")],
        [InlineKeyboardButton("🏆 Ranking mensual",callback_data="turtle:rank"), InlineKeyboardButton("📍 Mi posición",callback_data="turtle:myrank")],
        [InlineKeyboardButton("📊 Mis estadísticas",callback_data="turtle:stats"), InlineKeyboardButton("👑 Salón de Reyes",callback_data="turtle:history")],
        [InlineKeyboardButton("❓ Cómo jugar",callback_data="turtle:help")],
    ])

def _turtle_stake_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("100",callback_data="turtle:stake:100"),InlineKeyboardButton("500",callback_data="turtle:stake:500"),InlineKeyboardButton("1,000",callback_data="turtle:stake:1000")],
        [InlineKeyboardButton("2,500",callback_data="turtle:stake:2500"),InlineKeyboardButton("5,000",callback_data="turtle:stake:5000")],
        [InlineKeyboardButton("✏️ Otra cantidad",callback_data="turtle:customstake"),InlineKeyboardButton("⬅️ Mi tortuga",callback_data="turtle:home")],
    ])

async def tortuga(update:Update, context:ContextTypes.DEFAULT_TYPE):
    """Ver o nombrar la tortuga personal. /tortuga Mi Nombre"""
    uid=update.effective_user.id; msg=update.effective_message
    conn=_get_connection()
    try:
        c=conn.cursor()
        if context.args:
            new=_clean_turtle_name(" ".join(context.args))
            if not new:
                conn.rollback(); return await msg.reply_text("🐢 El nombre debe tener entre 2 y 28 caracteres.")
            _get_or_create_turtle(c,uid,update.effective_user.first_name)
            c.execute("UPDATE turtle_profiles_tb SET turtle_name=%s,updated_at=now() WHERE user_id=%s",(new,uid)); conn.commit()
            return await msg.reply_text(f"🐢✨ Tu tortuga ahora se llama {new}.\n\nSus estadísticas e historia siguen siendo las mismas.",reply_markup=_turtle_menu())
        name=_get_or_create_turtle(c,uid,update.effective_user.first_name)
        season=_season_key(); c.execute("SELECT races,wins FROM turtle_monthly_stats_tb WHERE season=%s AND user_id=%s",(season,uid)); row=c.fetchone() or (0,0)
        c.execute("SELECT count(*) FROM turtle_season_results_tb WHERE user_id=%s AND place=1",(uid,)); crowns=c.fetchone()[0]
        conn.commit()
        await msg.reply_text(f"🐢 MI TORTUGA\n\n🏷️ {name}\n🏁 Carreras este mes: {row[0]}\n🏆 Victorias este mes: {row[1]}\n👑 Coronas históricas: {crowns}\n\nElige qué quieres hacer con los botones de abajo.",reply_markup=_turtle_menu())
    except Exception as exc:
        conn.rollback(); print('[TURTLE profile]',exc); await msg.reply_text("⚠️ No pude abrir el perfil de tu tortuga.")
    finally:_put_connection(conn)

async def _send_turtle_home(message, uid):
    conn=_get_connection()
    try:
        c=conn.cursor(); name=_get_or_create_turtle(c,uid)
        season=_season_key(); c.execute("SELECT races,wins FROM turtle_monthly_stats_tb WHERE season=%s AND user_id=%s",(season,uid)); row=c.fetchone() or (0,0)
        c.execute("SELECT count(*) FROM turtle_season_results_tb WHERE user_id=%s AND place=1",(uid,)); crowns=c.fetchone()[0]; conn.commit()
        await message.reply_text(f"🐢 MI TORTUGA\n\n🏷️ {name}\n🏁 Carreras este mes: {row[0]}\n🏆 Victorias este mes: {row[1]}\n👑 Coronas históricas: {crowns}\n\nElige una opción:",reply_markup=_turtle_menu())
    finally:_put_connection(conn)

async def process_turtle_input(update:Update, context:ContextTypes.DEFAULT_TYPE):
    msg=update.effective_message; user=update.effective_user
    if not msg or not user or not msg.text or msg.text.startswith('/'):
        return
    mode=context.user_data.get('turtle_input')
    if not mode: return
    context.user_data.pop('turtle_input',None)
    if mode=='rename':
        new=_clean_turtle_name(msg.text)
        if not new:
            context.user_data['turtle_input']='rename'
            await msg.reply_text("🐢 Ese nombre no sirve. Escribe uno de 2 a 28 caracteres, o usa /cancelar para salir."); return
        conn=_get_connection()
        try:
            c=conn.cursor(); _get_or_create_turtle(c,user.id,user.first_name); c.execute("UPDATE turtle_profiles_tb SET turtle_name=%s,updated_at=now() WHERE user_id=%s",(new,user.id)); conn.commit()
        except Exception:
            conn.rollback(); await msg.reply_text("⚠️ No pude guardar el nombre. Inténtalo otra vez."); return
        finally:_put_connection(conn)
        await msg.reply_text(f"🐢✨ Listo. Tu tortuga ahora se llama {new}.",reply_markup=_turtle_menu()); return
    if mode=='stake':
        try: stake=int(msg.text.replace(',','').replace('.',''))
        except: stake=0
        if not 100 <= stake <= 1_000_000:
            context.user_data['turtle_input']='stake'; await msg.reply_text("💰 Escribe una apuesta entre 100 y 1,000,000 PiPesos."); return
        context.args=[str(stake)]; await tortugas(update,context)

async def ranking_tortugas(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await _send_turtle_ranking(update.effective_message)

async def _send_turtle_ranking(message, viewer_id=None):
    season=_season_key(); uid=viewer_id if viewer_id is not None else (message.from_user.id if message and message.from_user else None)
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""SELECT s.user_id,COALESCE(p.turtle_name,'Tortuga'),s.wins,s.races,
          COALESCE(NULLIF(pf.username,''),pf.nombre,'Usuario')
          FROM turtle_monthly_stats_tb s LEFT JOIN turtle_profiles_tb p ON p.user_id=s.user_id
          LEFT JOIN perfiles_tb pf ON pf.id_user=s.user_id WHERE s.season=%s AND s.races>0
          ORDER BY s.wins DESC,s.races ASC,s.user_id ASC LIMIT 10""",(season,)); rows=c.fetchall()
        lines=[f"🐢🏆 RANKING DE TORTUGAS · {season}",""]
        medals={1:'👑',2:'🥈',3:'🥉'}
        for i,r in enumerate(rows,1): lines.append(f"{medals.get(i,'▫️')} #{i} {r[1]} — {r[4]} · {r[2]} victorias / {r[3]} carreras")
        if not rows: lines.append("Todavía no hay carreras terminadas esta temporada.")
        if uid:
            c.execute("""SELECT pos,wins,races FROM (SELECT user_id,wins,races,ROW_NUMBER() OVER(ORDER BY wins DESC,races ASC,user_id ASC) pos FROM turtle_monthly_stats_tb WHERE season=%s AND races>0) x WHERE user_id=%s""",(season,uid)); me=c.fetchone()
            if me: lines += ["",f"📍 Tu posición: #{me[0]} · {me[1]} victorias / {me[2]} carreras"]
        conn.rollback(); await message.reply_text("\n".join(lines))
    finally:_put_connection(conn)

async def _send_turtle_history(message):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""SELECT season,turtle_name,COALESCE(NULLIF(p.username,''),p.nombre,'Usuario'),wins,races
          FROM turtle_season_results_tb r LEFT JOIN perfiles_tb p ON p.id_user=r.user_id WHERE place=1 ORDER BY season DESC LIMIT 12"""); rows=c.fetchall(); conn.rollback()
        text="👑🐢 SALÓN DE REYES\n\n" + ("\n".join(f"{r[0]} · {r[1]} — {r[2]} · {r[3]} victorias" for r in rows) if rows else "Aún no hay campeones mensuales registrados.")
        await message.reply_text(text)
    finally:_put_connection(conn)

async def turtle_season_maintenance_job(context):
    """Paga una sola vez el Top 3 del mes anterior. Idempotencia por PK(season,place)."""
    season=_previous_season_key(); prizes=[10000,6000,3000]; conn=_get_connection(); winners=[]
    try:
        c=conn.cursor(); c.execute("SELECT 1 FROM turtle_season_results_tb WHERE season=%s LIMIT 1 FOR UPDATE",(season,))
        if c.fetchone(): conn.rollback(); return
        c.execute("""SELECT s.user_id,COALESCE(p.turtle_name,'Tortuga'),s.wins,s.races
          FROM turtle_monthly_stats_tb s LEFT JOIN turtle_profiles_tb p ON p.user_id=s.user_id
          WHERE s.season=%s AND s.races>0 ORDER BY s.wins DESC,s.races ASC,s.user_id ASC LIMIT 3 FOR UPDATE OF s""",(season,)); rows=c.fetchall()
        if not rows: conn.rollback(); return
        for place,row in enumerate(rows,1):
            uid,name,wins,races=row; prize=prizes[place-1]
            if not _pay(uid,prize,c): raise RuntimeError(f"No se pudo pagar temporada a {uid}")
            c.execute("INSERT INTO turtle_season_results_tb(season,place,user_id,turtle_name,wins,races,prize) VALUES(%s,%s,%s,%s,%s,%s,%s)",(season,place,uid,name,wins,races,prize)); winners.append((place,uid,name,wins,races,prize))
        conn.commit()
    except Exception as exc:
        conn.rollback(); print('[TURTLE season]',exc); return
    finally:_put_connection(conn)
    if winners:
        medals={1:'👑',2:'🥈',3:'🥉'}; lines=[f"🐢🏆 FINAL DE TEMPORADA · {season}",""]
        for place,uid,name,wins,races,prize in winners: lines.append(f"{medals[place]} #{place} {name} · {wins} victorias / {races} carreras · +{prize:,} PiPesos")
        lines += ["","👑 El primer lugar entra al Salón de Reyes como REY DE LAS TORTUGAS.","🔄 Nueva temporada: el ranking mensual vuelve a cero; nombres e historia permanecen."]
        try: await context.bot.send_message(chat_id=MAIN_CHAT_ID,message_thread_id=JUEGOS_THREAD_ID,text="\n".join(lines))
        except Exception as exc: print('[TURTLE announce]',exc)

async def tortugas(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not _in_games(update):
        await update.effective_message.reply_text("🐢 Las carreras viven en el tema Juegos."); return
    try: stake=int(context.args[0]) if context.args else 1000
    except: stake=0
    if stake<100 or stake>1_000_000:
        await update.effective_message.reply_text("Usa /tortugas <apuesta>. Mínimo 100 y máximo 1,000,000 PiPesos."); return
    chat,thread=_loc(update); uid=update.effective_user.id; gid=uuid.uuid4().hex
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT 1 FROM turtle_games_tb WHERE chat_id=%s AND thread_id=%s AND status IN ('waiting','active')",(chat,thread))
        if c.fetchone(): conn.rollback(); await update.effective_message.reply_text("🐢 Ya hay una carrera abierta aquí."); return
        if not _reserve(uid,stake,c): conn.rollback(); await update.effective_message.reply_text("💸 No tienes suficientes PiPesos."); return
        c.execute("INSERT INTO turtle_games_tb(game_id,chat_id,thread_id,creator_id,stake,goal) VALUES(%s,%s,%s,%s,%s,%s)",(gid,chat,thread,uid,stake,RACE_GOAL))
        name=update.effective_user.username or update.effective_user.first_name
        tname=_get_or_create_turtle(c,uid,update.effective_user.first_name)
        c.execute("INSERT INTO turtle_players_tb VALUES(%s,%s,%s,%s,0,now())",(gid,uid,name,tname))
        conn.commit()
    except Exception:
        conn.rollback(); await update.effective_message.reply_text("⚠️ No pude abrir la carrera; no se confirmó ningún cobro."); return
    finally:_put_connection(conn)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("🐢 Unirme",callback_data=f"turtle:join:{gid}"),InlineKeyboardButton("🏁 Iniciar",callback_data=f"turtle:start:{gid}")],[InlineKeyboardButton("❌ Cancelar",callback_data=f"turtle:cancel:{gid}")]])
    await update.effective_message.reply_text(f"🐢 CARRERA ABIERTA\n💰 Entrada: {stake:,} PiPesos\n👥 1/6 jugadores\n🏁 Meta: {RACE_GOAL} casillas\n\nÚnete y prepara tu dado real de Telegram.",reply_markup=kb)

async def _turtle_cb(q,parts):
    action,gid=parts[1],parts[2]; uid=q.from_user.id
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,creator_id,stake,status FROM turtle_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
        if not g: conn.rollback(); await q.answer("La carrera ya no existe.",show_alert=True); return
        chat,thread,creator,stake,status=g
        if q.message.chat_id!=chat or q.message.message_thread_id!=thread: conn.rollback(); await q.answer("Esa carrera pertenece a otro tema.",show_alert=True); return
        if action=='join':
            if status!='waiting': conn.rollback(); await q.answer("La carrera ya empezó.",show_alert=True); return
            c.execute("SELECT count(*) FROM turtle_players_tb WHERE game_id=%s",(gid,)); n=c.fetchone()[0]
            c.execute("SELECT 1 FROM turtle_players_tb WHERE game_id=%s AND user_id=%s",(gid,uid))
            if c.fetchone(): conn.rollback(); await q.answer("Ya estás dentro 😹"); return
            if n>=6: conn.rollback(); await q.answer("Ya somos 6.",show_alert=True); return
            if not _reserve(uid,stake,c): conn.rollback(); await q.answer("No tienes saldo suficiente.",show_alert=True); return
            name=q.from_user.username or q.from_user.first_name
            tname=_get_or_create_turtle(c,uid,q.from_user.first_name)
            c.execute("INSERT INTO turtle_players_tb VALUES(%s,%s,%s,%s,0,now())",(gid,uid,name,tname)); conn.commit(); await q.answer("¡Dentro! 🐢")
            await q.message.reply_text(f"🐢 {name} entró a la carrera. Entrada reservada: {stake:,} PiPesos."); return
        if action=='start':
            if uid!=creator: conn.rollback(); await q.answer("Solo quien creó la carrera puede iniciarla.",show_alert=True); return
            c.execute("SELECT user_id,display_name,turtle_name FROM turtle_players_tb WHERE game_id=%s ORDER BY joined_at",(gid,)); ps=c.fetchall()
            if len(ps)<2: conn.rollback(); await q.answer("Falta al menos otro jugador.",show_alert=True); return
            c.execute("UPDATE turtle_games_tb SET status='active',turn_index=0,updated_at=now() WHERE game_id=%s",(gid,)); conn.commit(); await q.answer()
            await q.edit_message_reply_markup(reply_markup=None); await q.message.reply_text(f"🏁 ¡ARRANCA LA CARRERA!\nTurno de {ps[0][1]} — manda 🎲 usando el dado real de Telegram."); return
        if action=='cancel':
            if uid!=creator or status!='waiting': conn.rollback(); await q.answer("No puedes cancelarla ahora.",show_alert=True); return
            c.execute("SELECT user_id FROM turtle_players_tb WHERE game_id=%s",(gid,)); ids=[r[0] for r in c.fetchall()]
            for x in ids:_pay(x,stake,c)
            c.execute("UPDATE turtle_games_tb SET status='cancelled',updated_at=now() WHERE game_id=%s",(gid,)); conn.commit(); await q.answer(); await q.edit_message_reply_markup(reply_markup=None); await q.message.reply_text("❌ Carrera cancelada. Todas las entradas fueron devueltas."); return
    except Exception:
        conn.rollback(); await q.answer("Error de base de datos; inténtalo otra vez.",show_alert=True)
    finally:_put_connection(conn)


def _deck():
    cards=[]
    for s in "♠♥♦♣":
        for r in ["A","2","3","4","5","6","7","8","9","10","J","Q","K"]:cards.append(r+s)
    random.SystemRandom().shuffle(cards); return cards

def _score(hand):
    total=0; aces=0
    for card in hand:
        r=card[:-1]
        if r=='A': total+=11; aces+=1
        elif r in ('J','Q','K'): total+=10
        else: total+=int(r)
    while total>21 and aces: total-=10; aces-=1
    return total

def _bj_buttons(gid):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🃏 Pedir",callback_data=f"bj:hit:{gid}"),InlineKeyboardButton("✋ Plantarme",callback_data=f"bj:stand:{gid}")]])

async def blackjack(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _in_games(update): await update.effective_message.reply_text("🃏 Blackjack PvP solo está en Juegos."); return
    try: stake=int(context.args[0]) if context.args else 1000
    except: stake=0
    if stake<100 or stake>1_000_000: await update.effective_message.reply_text("Usa /blackjack <apuesta>. Mínimo 100 y máximo 1,000,000 PiPesos."); return
    chat,thread=_loc(update); uid=update.effective_user.id; gid=uuid.uuid4().hex
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT 1 FROM blackjack_games_tb WHERE chat_id=%s AND thread_id=%s AND status IN ('waiting','active')",(chat,thread))
        if c.fetchone(): conn.rollback(); await update.effective_message.reply_text("🃏 Ya hay una mesa abierta en este tema."); return
        if not _reserve(uid,stake,c): conn.rollback(); await update.effective_message.reply_text("💸 No tienes saldo suficiente."); return
        c.execute("INSERT INTO blackjack_games_tb(game_id,chat_id,thread_id,creator_id,stake) VALUES(%s,%s,%s,%s,%s)",(gid,chat,thread,uid,stake)); conn.commit()
    except Exception: conn.rollback(); await update.effective_message.reply_text("⚠️ No pude abrir la mesa; no se confirmó ningún cobro."); return
    finally:_put_connection(conn)
    await update.effective_message.reply_text(f"🃏 BLACKJACK PvP\n💰 Apuesta por jugador: {stake:,} PiPesos\nEl creador ya reservó su entrada. ¿Quién acepta?",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🤝 Aceptar mesa",callback_data=f"bj:join:{gid}"),InlineKeyboardButton("❌ Cancelar",callback_data=f"bj:cancel:{gid}")]]))

async def _bj_finish(c,gid,creator,rival,stake,ha,hb):
    sa,sb=_score(ha),_score(hb)
    if sa>21 and sb>21 or sa==sb:
        _pay(creator,stake,c); _pay(rival,stake,c); result="🤝 Empate. Se devolvieron ambas apuestas."
    elif sa<=21 and (sb>21 or sa>sb):
        _pay(creator,stake*2,c); result=f"🏆 Jugador 1 gana {stake*2:,} PiPesos."
    else:
        _pay(rival,stake*2,c); result=f"🏆 Jugador 2 gana {stake*2:,} PiPesos."
    c.execute("UPDATE blackjack_games_tb SET status='finished',updated_at=now() WHERE game_id=%s",(gid,))
    return f"🃏 FINAL\nJugador 1: {' '.join(ha)} = {sa}\nJugador 2: {' '.join(hb)} = {sb}\n\n{result}"

async def _bj_cb(q,parts):
    action,gid=parts[1],parts[2]; uid=q.from_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,creator_id,rival_id,stake,status,turn_user_id,deck,hand_a,hand_b,stood_a,stood_b,action_started FROM blackjack_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
        if not g: conn.rollback(); await q.answer("Mesa inexistente.",show_alert=True); return
        chat,thread,creator,rival,stake,status,turn,deck,ha,hb,sta,stb,action_started=g
        if q.message.chat_id!=chat or q.message.message_thread_id!=thread: conn.rollback(); await q.answer("Esta mesa es de otro tema.",show_alert=True); return
        if action=='cancel':
            if uid!=creator or status not in ('waiting','active') or action_started:
                conn.rollback(); await q.answer("La mesa ya tuvo una jugada y no puede cancelarse.",show_alert=True); return
            _pay(creator,stake,c)
            if status=='active' and rival: _pay(rival,stake,c)
            c.execute("UPDATE blackjack_games_tb SET status='cancelled',updated_at=now() WHERE game_id=%s AND status IN ('waiting','active')",(gid,))
            conn.commit(); await q.answer(); await q.edit_message_reply_markup(reply_markup=None); await q.message.reply_text("❌ Mesa cancelada. Todas las apuestas reservadas fueron devueltas."); return
        if action=='join':
            if status!='waiting' or uid==creator: conn.rollback(); await q.answer("No puedes aceptar esta mesa.",show_alert=True); return
            if not _reserve(uid,stake,c): conn.rollback(); await q.answer("No tienes saldo suficiente.",show_alert=True); return
            deck=_deck(); ha=[deck.pop(),deck.pop()]; hb=[deck.pop(),deck.pop()]
            c.execute("UPDATE blackjack_games_tb SET rival_id=%s,status='active',turn_user_id=%s,deck=%s,hand_a=%s,hand_b=%s,updated_at=now() WHERE game_id=%s",(uid,creator,deck,ha,hb,gid)); conn.commit(); await q.answer(); await q.edit_message_reply_markup(reply_markup=None)
            creator_name=_display_name(c,creator); rival_name=_display_name(c,uid)
            await q.message.reply_text(f"🃏 ¡Mesa completa!\n👤 {creator_name}: {' '.join(ha)} = {_score(ha)}\n👤 {rival_name}: {' '.join(hb)} = {_score(hb)}\n\n➡️ Turno de {creator_name}.",reply_markup=_bj_buttons(gid)); return
        if status!='active' or uid not in (creator,rival): conn.rollback(); await q.answer("No estás jugando esta mesa.",show_alert=True); return
        if uid!=turn: conn.rollback(); await q.answer("No es tu turno.",show_alert=True); return
        is_a=uid==creator; hand=list(ha if is_a else hb)
        if action=='hit':
            hand.append(deck.pop()); score=_score(hand)
            if is_a: ha=hand
            else: hb=hand
            if score>21:
                # bust ends immediately; other player receives pot
                winner=rival if is_a else creator; _pay(winner,stake*2,c)
                c.execute("UPDATE blackjack_games_tb SET status='finished',deck=%s,hand_a=%s,hand_b=%s,action_started=true,updated_at=now() WHERE game_id=%s",(deck,ha,hb,gid)); conn.commit(); await q.answer(); await q.edit_message_reply_markup(reply_markup=None); await q.message.reply_text(f"💥 ¡BUST! {score}.\n{'Jugador 2' if is_a else 'Jugador 1'} gana {stake*2:,} PiPesos."); return
            other_stood=stb if is_a else sta
            nextu=uid if other_stood else (rival if is_a else creator)
            c.execute("UPDATE blackjack_games_tb SET deck=%s,hand_a=%s,hand_b=%s,turn_user_id=%s,action_started=true,updated_at=now() WHERE game_id=%s",(deck,ha,hb,nextu,gid)); conn.commit(); await q.answer()
            suffix="Sigue tu turno porque el otro jugador ya se plantó." if other_stood else "Turno del otro jugador."
            await q.message.reply_text(f"🃏 Carta: {hand[-1]} · Total: {score}\n{suffix}",reply_markup=_bj_buttons(gid)); return
        if action=='stand':
            if is_a: sta=True
            else: stb=True
            other_stood=stb if is_a else sta
            if other_stood:
                result=await _bj_finish(c,gid,creator,rival,stake,ha,hb); conn.commit(); await q.answer(); await q.edit_message_reply_markup(reply_markup=None); await q.message.reply_text(result); return
            nextu=rival if is_a else creator
            c.execute("UPDATE blackjack_games_tb SET stood_a=%s,stood_b=%s,turn_user_id=%s,action_started=true,updated_at=now() WHERE game_id=%s",(sta,stb,nextu,gid)); conn.commit(); await q.answer(); await q.message.reply_text("✋ Te plantas. Turno del otro jugador.",reply_markup=_bj_buttons(gid)); return
    except Exception:
        conn.rollback(); await q.answer("Error de base de datos; no se liquidó dos veces.",show_alert=True)
    finally:_put_connection(conn)

async def cancelar_blackjack(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not _in_games(update): return await update.effective_message.reply_text("🃏 Este comando solo funciona en Juegos.")
    chat,thread=_loc(update); uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT game_id,creator_id,rival_id,stake,status,action_started FROM blackjack_games_tb WHERE chat_id=%s AND thread_id=%s AND status IN ('waiting','active') ORDER BY created_at DESC LIMIT 1 FOR UPDATE",(chat,thread)); g=c.fetchone()
        if not g: conn.rollback(); return await update.effective_message.reply_text("🃏 No hay una mesa activa para cancelar.")
        gid,creator,rival,stake,status,started=g
        if uid!=creator: conn.rollback(); return await update.effective_message.reply_text("❌ Solo quien creó la mesa puede cancelarla antes de la primera jugada.")
        if started: conn.rollback(); return await update.effective_message.reply_text("🃏 La partida ya tuvo una jugada. Ya no puede cancelarse.")
        _pay(creator,stake,c)
        if status=='active' and rival: _pay(rival,stake,c)
        c.execute("UPDATE blackjack_games_tb SET status='cancelled',updated_at=now() WHERE game_id=%s AND status IN ('waiting','active')",(gid,)); conn.commit()
        await update.effective_message.reply_text("❌ Blackjack cancelado. Se devolvieron todas las apuestas reservadas.")
    except Exception as exc:
        conn.rollback(); print('[BLACKJACK cancel]',exc); await update.effective_message.reply_text("⚠️ No pude cancelar la mesa; no se confirmó ninguna devolución.")
    finally: _put_connection(conn)

async def casino_pvp_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    parts=q.data.split(':')
    # answer above is harmless; subhandlers may answer again on some clients, so ignore BadRequest via wrapper not needed normally.
    if parts[0]=='turtle':
        if len(parts)==2 and parts[1]=='rank':
            await q.answer(); await _send_turtle_ranking(q.message, q.from_user.id)
        elif len(parts)==2 and parts[1]=='myrank':
            await q.answer(); await _send_turtle_ranking(q.message, q.from_user.id)
        elif len(parts)==2 and parts[1]=='history':
            await q.answer(); await _send_turtle_history(q.message)
        elif len(parts)==2 and parts[1]=='home':
            await q.answer(); await _send_turtle_home(q.message,q.from_user.id)
        elif len(parts)==2 and parts[1]=='rename':
            context.user_data['turtle_input']='rename'; await q.answer(); await q.message.reply_text("✏️🐢 Escribe ahora el nuevo nombre de tu tortuga.\n\nDebe tener entre 2 y 28 caracteres. No necesitas usar ningún comando.")
        elif len(parts)==2 and parts[1]=='create':
            await q.answer()
            if q.message.chat_id!=MAIN_CHAT_ID or q.message.message_thread_id!=JUEGOS_THREAD_ID:
                await q.message.reply_text("🏁 Las carreras se crean en el tema Juegos. Abre /tortuga allí y toca Crear carrera.")
            else: await q.message.reply_text("🐢 ¿Cuánto costará entrar a la carrera?",reply_markup=_turtle_stake_menu())
        elif len(parts)==2 and parts[1]=='customstake':
            context.user_data['turtle_input']='stake'; await q.answer(); await q.message.reply_text("💰 Escribe la cantidad de la entrada (100 a 1,000,000 PiPesos).")
        elif len(parts)==3 and parts[1]=='stake':
            await q.answer(); context.args=[parts[2]]
            # Reuse the same safe creator path using the callback message as effective context is not possible; create via helper update facade.
            class _U:
                effective_user=q.from_user; effective_chat=q.message.chat; effective_message=q.message
            await tortugas(_U(),context)
        elif len(parts)==2 and parts[1]=='stats':
            await q.answer(); await _send_turtle_home(q.message,q.from_user.id)
        elif len(parts)==2 and parts[1]=='help':
            await q.answer(); await q.message.reply_text("🐢 CÓMO JUGAR\n\n1. Ponle nombre a tu tortuga.\n2. En Juegos toca 🏁 Crear carrera y elige la entrada.\n3. De 2 a 6 personas pueden unirse.\n4. Cuando sea tu turno manda el dado 🎲 real de Telegram.\n5. La primera tortuga que alcance la meta gana el pozo.\n\n🏆 Cada victoria cuenta para el ranking mensual. Al cerrar el mes: 10,000 al #1, 6,000 al #2 y 3,000 al #3.",reply_markup=_turtle_menu())
        else: await _turtle_cb(q,parts)
    elif parts[0]=='bj': await _bj_cb(q,parts)

async def process_turtle_dice(update:Update,context:ContextTypes.DEFAULT_TYPE):
    msg=update.effective_message
    if not msg or not msg.dice or update.effective_chat.id != MAIN_CHAT_ID or msg.message_thread_id!=JUEGOS_THREAD_ID: return False
    chat=update.effective_chat.id; uid=update.effective_user.id
    # Si este usuario está en un combate, su dado pertenece al combate y no a la carrera.
    from handlers.battles import get_combate_activo
    if get_combate_activo(uid):
        return False
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT game_id,stake,goal,turn_index FROM turtle_games_tb WHERE chat_id=%s AND thread_id=%s AND status='active' FOR UPDATE",(chat,JUEGOS_THREAD_ID)); g=c.fetchone()
        if not g: conn.rollback(); return False
        gid,stake,goal,idx=g; c.execute("SELECT user_id,display_name,turtle_name,position FROM turtle_players_tb WHERE game_id=%s ORDER BY joined_at",(gid,)); ps=c.fetchall()
        if not ps: conn.rollback(); return False
        current=ps[idx%len(ps)]
        if uid!=current[0]: conn.rollback(); await msg.reply_text(f"⏳ No es tu turno. Le toca a {current[1]}."); return True
        value=msg.dice.value; newpos=current[3]+value
        c.execute("UPDATE turtle_players_tb SET position=%s WHERE game_id=%s AND user_id=%s",(newpos,gid,uid))
        if newpos>=goal:
            pot=stake*len(ps)
            if not _pay(uid,pot,c): raise RuntimeError("No se pudo pagar el pozo")
            season=_season_key()
            for p in ps:
                c.execute("""INSERT INTO turtle_monthly_stats_tb(season,user_id,races,wins) VALUES(%s,%s,1,%s)
                  ON CONFLICT(season,user_id) DO UPDATE SET races=turtle_monthly_stats_tb.races+1,wins=turtle_monthly_stats_tb.wins+EXCLUDED.wins""",(season,p[0],1 if p[0]==uid else 0))
            c.execute("UPDATE turtle_games_tb SET status='finished',updated_at=now() WHERE game_id=%s",(gid,)); conn.commit()
            await msg.reply_text(f"🎲 {value} — {random.choice(TURTLE_LINES[value])}\n🏆 ¡{current[2]} de {current[1]} cruzó la meta!\n💰 Pozo: {pot:,} PiPesos.\n👑 Victoria registrada en el ranking mensual."); return True
        nxt=(idx+1)%len(ps); c.execute("UPDATE turtle_games_tb SET turn_index=%s,updated_at=now() WHERE game_id=%s",(nxt,gid)); conn.commit()
        bars=[]
        for p in ps:
            pos=newpos if p[0]==uid else p[3]; bars.append(f"🐢 {p[2]}: {min(pos,goal)}/{goal}")
        await msg.reply_text(f"🎲 {value} — {random.choice(TURTLE_LINES[value])}\n"+'\n'.join(bars)+f"\n\n➡️ Turno de {ps[nxt][1]}")
        return True
    except Exception:
        conn.rollback(); await msg.reply_text("⚠️ No pude guardar el turno. El avance no se confirmó; vuelve a lanzar."); return True
    finally:_put_connection(conn)
