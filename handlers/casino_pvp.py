"""Juegos PvP persistentes del tema Juegos (528): Tortugas y Blackjack."""
import random
import uuid
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
          stood_b bool NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""")
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

def _in_games(update):
    chat,thread=_loc(update)
    return chat == MAIN_CHAT_ID and update.effective_chat.type not in ('private',) and thread==JUEGOS_THREAD_ID

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
        c.execute("INSERT INTO turtle_players_tb VALUES(%s,%s,%s,%s,0,now())",(gid,uid,name,random.choice(TURTLE_NAMES)))
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
            c.execute("INSERT INTO turtle_players_tb VALUES(%s,%s,%s,%s,0,now())",(gid,uid,name,TURTLE_NAMES[n%len(TURTLE_NAMES)])); conn.commit(); await q.answer("¡Dentro! 🐢")
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
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,creator_id,rival_id,stake,status,turn_user_id,deck,hand_a,hand_b,stood_a,stood_b FROM blackjack_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
        if not g: conn.rollback(); await q.answer("Mesa inexistente.",show_alert=True); return
        chat,thread,creator,rival,stake,status,turn,deck,ha,hb,sta,stb=g
        if q.message.chat_id!=chat or q.message.message_thread_id!=thread: conn.rollback(); await q.answer("Esta mesa es de otro tema.",show_alert=True); return
        if action=='cancel':
            if uid!=creator or status!='waiting': conn.rollback(); await q.answer("No puedes cancelarla.",show_alert=True); return
            _pay(creator,stake,c); c.execute("UPDATE blackjack_games_tb SET status='cancelled' WHERE game_id=%s",(gid,)); conn.commit(); await q.answer(); await q.edit_message_reply_markup(reply_markup=None); await q.message.reply_text("❌ Mesa cancelada. Apuesta devuelta."); return
        if action=='join':
            if status!='waiting' or uid==creator: conn.rollback(); await q.answer("No puedes aceptar esta mesa.",show_alert=True); return
            if not _reserve(uid,stake,c): conn.rollback(); await q.answer("No tienes saldo suficiente.",show_alert=True); return
            deck=_deck(); ha=[deck.pop(),deck.pop()]; hb=[deck.pop(),deck.pop()]
            c.execute("UPDATE blackjack_games_tb SET rival_id=%s,status='active',turn_user_id=%s,deck=%s,hand_a=%s,hand_b=%s,updated_at=now() WHERE game_id=%s",(uid,creator,deck,ha,hb,gid)); conn.commit(); await q.answer(); await q.edit_message_reply_markup(reply_markup=None)
            await q.message.reply_text(f"🃏 ¡Mesa completa!\nJugador 1: {' '.join(ha)} = {_score(ha)}\nJugador 2: {' '.join(hb)} = {_score(hb)}\n\nTurno del creador.",reply_markup=_bj_buttons(gid)); return
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
                c.execute("UPDATE blackjack_games_tb SET status='finished',deck=%s,hand_a=%s,hand_b=%s,updated_at=now() WHERE game_id=%s",(deck,ha,hb,gid)); conn.commit(); await q.answer(); await q.edit_message_reply_markup(reply_markup=None); await q.message.reply_text(f"💥 ¡BUST! {score}.\n{'Jugador 2' if is_a else 'Jugador 1'} gana {stake*2:,} PiPesos."); return
            other_stood=stb if is_a else sta
            nextu=uid if other_stood else (rival if is_a else creator)
            c.execute("UPDATE blackjack_games_tb SET deck=%s,hand_a=%s,hand_b=%s,turn_user_id=%s,updated_at=now() WHERE game_id=%s",(deck,ha,hb,nextu,gid)); conn.commit(); await q.answer()
            suffix="Sigue tu turno porque el otro jugador ya se plantó." if other_stood else "Turno del otro jugador."
            await q.message.reply_text(f"🃏 Carta: {hand[-1]} · Total: {score}\n{suffix}",reply_markup=_bj_buttons(gid)); return
        if action=='stand':
            if is_a: sta=True
            else: stb=True
            other_stood=stb if is_a else sta
            if other_stood:
                result=await _bj_finish(c,gid,creator,rival,stake,ha,hb); conn.commit(); await q.answer(); await q.edit_message_reply_markup(reply_markup=None); await q.message.reply_text(result); return
            nextu=rival if is_a else creator
            c.execute("UPDATE blackjack_games_tb SET stood_a=%s,stood_b=%s,turn_user_id=%s,updated_at=now() WHERE game_id=%s",(sta,stb,nextu,gid)); conn.commit(); await q.answer(); await q.message.reply_text("✋ Te plantas. Turno del otro jugador.",reply_markup=_bj_buttons(gid)); return
    except Exception:
        conn.rollback(); await q.answer("Error de base de datos; no se liquidó dos veces.",show_alert=True)
    finally:_put_connection(conn)

async def casino_pvp_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    parts=q.data.split(':')
    # answer above is harmless; subhandlers may answer again on some clients, so ignore BadRequest via wrapper not needed normally.
    if parts[0]=='turtle': await _turtle_cb(q,parts)
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
            pot=stake*len(ps); _pay(uid,pot,c); c.execute("UPDATE turtle_games_tb SET status='finished',updated_at=now() WHERE game_id=%s",(gid,)); conn.commit()
            await msg.reply_text(f"🎲 {value} — {random.choice(TURTLE_LINES[value])}\n🏆 ¡{current[1]} y {current[2]} cruzan la meta!\n💰 Pozo: {pot:,} PiPesos."); return True
        nxt=(idx+1)%len(ps); c.execute("UPDATE turtle_games_tb SET turn_index=%s,updated_at=now() WHERE game_id=%s",(nxt,gid)); conn.commit()
        bars=[]
        for p in ps:
            pos=newpos if p[0]==uid else p[3]; bars.append(f"🐢 {p[2]}: {min(pos,goal)}/{goal}")
        await msg.reply_text(f"🎲 {value} — {random.choice(TURTLE_LINES[value])}\n"+'\n'.join(bars)+f"\n\n➡️ Turno de {ps[nxt][1]}")
        return True
    except Exception:
        conn.rollback(); await msg.reply_text("⚠️ No pude guardar el turno. El avance no se confirmó; vuelve a lanzar."); return True
    finally:_put_connection(conn)
