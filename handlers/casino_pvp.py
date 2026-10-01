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
        c.execute("""CREATE TABLE IF NOT EXISTS blackjack_players_tb(
          game_id text REFERENCES blackjack_games_tb(game_id) ON DELETE CASCADE,
          user_id bigint NOT NULL, display_name text NOT NULL, hand text[] NOT NULL DEFAULT '{}',
          stood bool NOT NULL DEFAULT false, busted bool NOT NULL DEFAULT false,
          join_order int NOT NULL, joined_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY(game_id,user_id))""")
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

def _bj_buttons(gid, creator=False):
    rows=[[InlineKeyboardButton("🃏 Pedir",callback_data=f"bj:hit:{gid}"),InlineKeyboardButton("✋ Plantarme",callback_data=f"bj:stand:{gid}")]]
    return InlineKeyboardMarkup(rows)

def _bj_lobby_buttons(gid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Unirme",callback_data=f"bj:join:{gid}"),InlineKeyboardButton("▶️ Empezar",callback_data=f"bj:start:{gid}")],
        [InlineKeyboardButton("❌ Cancelar",callback_data=f"bj:cancel:{gid}")]
    ])

async def blackjack(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not _in_games(update): await update.effective_message.reply_text("🃏 Blackjack multijugador solo está en Juegos."); return
    if not context.args:
        await update.effective_message.reply_text("🃏 BLACKJACK MULTIJUGADOR\n\nUsa /blackjack cantidad\nEjemplo: /blackjack 3477\n\n💰 Puedes poner la apuesta que quieras entre 100 y 1,000,000 PiPesos."); return
    try: stake=int(str(context.args[0]).replace(',',''))
    except: stake=0
    if stake<100 or stake>1_000_000: await update.effective_message.reply_text("La apuesta debe estar entre 100 y 1,000,000 PiPesos."); return
    chat,thread=_loc(update); uid=update.effective_user.id; gid=uuid.uuid4().hex; name=update.effective_user.username or update.effective_user.first_name or str(uid)
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT 1 FROM blackjack_games_tb WHERE chat_id=%s AND thread_id=%s AND status IN ('waiting','active')",(chat,thread))
        if c.fetchone(): conn.rollback(); await update.effective_message.reply_text("🃏 Ya hay una mesa abierta en este tema."); return
        if not _reserve(uid,stake,c): conn.rollback(); await update.effective_message.reply_text("💸 No tienes saldo suficiente."); return
        c.execute("INSERT INTO blackjack_games_tb(game_id,chat_id,thread_id,creator_id,stake) VALUES(%s,%s,%s,%s,%s)",(gid,chat,thread,uid,stake))
        c.execute("INSERT INTO blackjack_players_tb(game_id,user_id,display_name,join_order) VALUES(%s,%s,%s,0)",(gid,uid,name)); conn.commit()
    except Exception as exc:
        conn.rollback(); print('[BLACKJACK create]',exc); await update.effective_message.reply_text("⚠️ No pude abrir la mesa; no se confirmó ningún cobro."); return
    finally:_put_connection(conn)
    await update.effective_message.reply_text(f"🃏 BLACKJACK MULTIJUGADOR\n💰 Entrada: {stake:,} PiPesos por persona\n👤 {name} creó la mesa.\n\nPueden entrar hasta 6 jugadores. Cuando haya 2 o más, el creador pulsa ▶️ Empezar.",reply_markup=_bj_lobby_buttons(gid))

def _bj_players(c,gid):
    c.execute("SELECT user_id,display_name,hand,stood,busted,join_order FROM blackjack_players_tb WHERE game_id=%s ORDER BY join_order",(gid,)); return c.fetchall()

def _next_live(players, current_uid):
    ids=[p[0] for p in players if not p[3] and not p[4]]
    if not ids: return None
    if current_uid not in [p[0] for p in players]: return ids[0]
    allids=[p[0] for p in players]; i=allids.index(current_uid)
    for step in range(1,len(allids)+1):
        p=players[(i+step)%len(players)]
        if not p[3] and not p[4]: return p[0]
    return None

def _finish_multi(c,gid,stake,players):
    valid=[(p[0],p[1],_score(p[2])) for p in players if _score(p[2])<=21]
    pot=stake*len(players)
    if not valid:
        for p in players: _pay(p[0],stake,c)
        result="🤝 Todos se pasaron de 21. Se devolvieron las entradas."
    else:
        best=max(x[2] for x in valid); winners=[x for x in valid if x[2]==best]
        share=pot//len(winners); rem=pot-share*len(winners)
        for i,(uid,name,score) in enumerate(winners): _pay(uid,share+(rem if i==0 else 0),c)
        names=', '.join(x[1] for x in winners)
        result=(f"🏆 Ganador: {names} · {best} puntos · {pot:,} PiPesos" if len(winners)==1 else f"🤝 Empate entre {names} · {best} puntos. Pozo {pot:,} PiPesos repartido.")
    c.execute("UPDATE blackjack_games_tb SET status='finished',updated_at=now() WHERE game_id=%s",(gid,))
    lines=["🃏 FINAL"]+[f"👤 {p[1]}: {' '.join(p[2])} = {_score(p[2])}" for p in players]
    return '\n'.join(lines)+"\n\n"+result

async def _bj_cb(q,parts):
    action,gid=parts[1],parts[2]; uid=q.from_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,creator_id,stake,status,turn_user_id,deck,action_started FROM blackjack_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
        if not g: conn.rollback(); await q.answer("Mesa inexistente.",show_alert=True); return
        chat,thread,creator,stake,status,turn,deck,started=g
        if q.message.chat_id!=chat or q.message.message_thread_id!=thread: conn.rollback(); await q.answer("Esta mesa es de otro tema.",show_alert=True); return
        players=_bj_players(c,gid); ids=[p[0] for p in players]
        if action=='join':
            if status!='waiting' or uid in ids: conn.rollback(); await q.answer("No puedes unirte a esta mesa.",show_alert=True); return
            if len(players)>=6: conn.rollback(); await q.answer("La mesa ya tiene 6 jugadores.",show_alert=True); return
            if not _reserve(uid,stake,c): conn.rollback(); await q.answer("No tienes saldo suficiente.",show_alert=True); return
            name=q.from_user.username or q.from_user.first_name or str(uid)
            c.execute("INSERT INTO blackjack_players_tb(game_id,user_id,display_name,join_order) VALUES(%s,%s,%s,%s)",(gid,uid,name,len(players))); conn.commit(); await q.answer("Entraste a la mesa 🃏")
            await q.message.reply_text(f"➕ {name} entró al Blackjack. Ya son {len(players)+1} jugadores.",reply_markup=_bj_lobby_buttons(gid)); return
        if action=='cancel':
            if uid!=creator or status!='waiting': conn.rollback(); await q.answer("Solo el creador puede cancelar antes de empezar.",show_alert=True); return
            for p in players: _pay(p[0],stake,c)
            c.execute("UPDATE blackjack_games_tb SET status='cancelled',updated_at=now() WHERE game_id=%s",(gid,)); conn.commit(); await q.answer(); await q.message.reply_text("❌ Mesa cancelada. Se devolvieron todas las entradas."); return
        if action=='start':
            if uid!=creator or status!='waiting': conn.rollback(); await q.answer("Solo quien creó la mesa puede iniciarla.",show_alert=True); return
            if len(players)<2: conn.rollback(); await q.answer("Se necesitan al menos 2 jugadores.",show_alert=True); return
            deck=_deck()
            for p in players:
                hand=[deck.pop(),deck.pop()]; c.execute("UPDATE blackjack_players_tb SET hand=%s,stood=false,busted=false WHERE game_id=%s AND user_id=%s",(hand,gid,p[0]))
            c.execute("UPDATE blackjack_games_tb SET status='active',turn_user_id=%s,deck=%s,action_started=false,updated_at=now() WHERE game_id=%s",(players[0][0],deck,gid)); conn.commit(); players=_bj_players(c,gid); await q.answer(); await q.edit_message_reply_markup(None)
            lines=["🃏 ¡EMPIEZA EL BLACKJACK!"]+[f"👤 {p[1]}: {' '.join(p[2])} = {_score(p[2])}" for p in players]
            await q.message.reply_text('\n'.join(lines)+f"\n\n➡️ Turno de {players[0][1]}",reply_markup=_bj_buttons(gid)); return
        if status!='active' or uid not in ids: conn.rollback(); await q.answer("No estás jugando esta mesa.",show_alert=True); return
        if uid!=turn: conn.rollback(); await q.answer("No es tu turno.",show_alert=True); return
        me=next(p for p in players if p[0]==uid); hand=list(me[2])
        if action=='hit':
            if not deck: deck=_deck()
            hand.append(deck.pop()); score=_score(hand); busted=score>21
            c.execute("UPDATE blackjack_players_tb SET hand=%s,busted=%s WHERE game_id=%s AND user_id=%s",(hand,busted,gid,uid)); players=_bj_players(c,gid)
            nxt=_next_live(players,uid)
            if nxt is None:
                result=_finish_multi(c,gid,stake,players); conn.commit(); await q.answer(); await q.edit_message_reply_markup(None); await q.message.reply_text(result); return
            c.execute("UPDATE blackjack_games_tb SET deck=%s,turn_user_id=%s,action_started=true,updated_at=now() WHERE game_id=%s",(deck,nxt,gid)); conn.commit(); await q.answer()
            nname=next(p[1] for p in players if p[0]==nxt); prefix=f"💥 {me[1]} se pasó con {score}." if busted else f"🃏 {me[1]} pidió {hand[-1]} · Total {score}."
            await q.message.reply_text(prefix+f"\n➡️ Turno de {nname}",reply_markup=_bj_buttons(gid)); return
        if action=='stand':
            c.execute("UPDATE blackjack_players_tb SET stood=true WHERE game_id=%s AND user_id=%s",(gid,uid)); players=_bj_players(c,gid); nxt=_next_live(players,uid)
            if nxt is None:
                result=_finish_multi(c,gid,stake,players); conn.commit(); await q.answer(); await q.edit_message_reply_markup(None); await q.message.reply_text(result); return
            c.execute("UPDATE blackjack_games_tb SET turn_user_id=%s,action_started=true,updated_at=now() WHERE game_id=%s",(nxt,gid)); conn.commit(); await q.answer(); nname=next(p[1] for p in players if p[0]==nxt)
            await q.message.reply_text(f"✋ {me[1]} se planta con {_score(hand)}.\n➡️ Turno de {nname}",reply_markup=_bj_buttons(gid)); return
    except Exception as exc:
        conn.rollback(); print('[BLACKJACK]',exc); await q.answer("Error de base de datos; no se liquidó dos veces.",show_alert=True)
    finally:_put_connection(conn)

async def cancelar_blackjack(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not _in_games(update): return await update.effective_message.reply_text("🃏 Este comando solo funciona en Juegos.")
    chat,thread=_loc(update); uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT game_id,creator_id,stake,status FROM blackjack_games_tb WHERE chat_id=%s AND thread_id=%s AND status IN ('waiting','active') ORDER BY created_at DESC LIMIT 1 FOR UPDATE",(chat,thread)); g=c.fetchone()
        if not g: conn.rollback(); return await update.effective_message.reply_text("🃏 No hay una mesa activa para cancelar.")
        gid,creator,stake,status=g
        if uid!=creator: conn.rollback(); return await update.effective_message.reply_text("❌ Solo quien creó la mesa puede cancelarla.")
        if status!='waiting': conn.rollback(); return await update.effective_message.reply_text("🃏 La partida ya comenzó. Ya no puede cancelarse.")
        players=_bj_players(c,gid)
        for p in players: _pay(p[0],stake,c)
        c.execute("UPDATE blackjack_games_tb SET status='cancelled',updated_at=now() WHERE game_id=%s",(gid,)); conn.commit()
        await update.effective_message.reply_text("❌ Blackjack cancelado. Se devolvieron todas las entradas.")
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
