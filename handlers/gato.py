import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection, reservar_apuesta_doble, reembolsar_apuesta_doble
from src.utils.display_name import visible_user
from handlers.pipeso_extras import send_victory

MIN_BET = 100


def ensure_gato_tables():
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS gato_games_tb(
          game_id bigserial PRIMARY KEY, chat_id bigint NOT NULL, thread_id bigint,
          creator_id bigint NOT NULL, invited_id bigint, opponent_id bigint,
          bet bigint NOT NULL, status text NOT NULL DEFAULT 'open',
          board text NOT NULL DEFAULT '         ', turn_id bigint,
          x_id bigint, o_id bigint, winner_id bigint,
          created_at timestamptz NOT NULL DEFAULT now(), accepted_at timestamptz,
          finished_at timestamptz, CHECK (bet >= 100)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_gato_active ON gato_games_tb(chat_id,status)")
        c.execute("""CREATE TABLE IF NOT EXISTS gato_stats_tb(
          user_id bigint PRIMARY KEY, wins int NOT NULL DEFAULT 0, losses int NOT NULL DEFAULT 0,
          draws int NOT NULL DEFAULT 0, games int NOT NULL DEFAULT 0
        )""")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:_put_connection(conn)


def _get(gid):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT game_id,chat_id,thread_id,creator_id,invited_id,opponent_id,bet,status,board,turn_id,x_id,o_id,winner_id FROM gato_games_tb WHERE game_id=%s",(gid,)); r=c.fetchone()
        if not r:return None
        return dict(zip(['game_id','chat_id','thread_id','creator_id','invited_id','opponent_id','bet','status','board','turn_id','x_id','o_id','winner_id'],r))
    finally:_put_connection(conn)


def _open_kb(gid):
    return InlineKeyboardMarkup([[InlineKeyboardButton('🐱 Jugar',callback_data=f'gt:a:{gid}')],[InlineKeyboardButton('❌ Cancelar',callback_data=f'gt:c:{gid}')]])


def _board_kb(g):
    b=g['board']
    rows=[]
    for r in range(3):
        row=[]
        for c in range(3):
            i=r*3+c; mark=b[i]
            row.append(InlineKeyboardButton(mark if mark!=' ' else '·',callback_data=f'gt:p:{g["game_id"]}:{i}'))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _text(g, note=None):
    x=visible_user(user_id=g['x_id']); o=visible_user(user_id=g['o_id'])
    parts=['🐱 GATO','',f'❌ {x}  vs  ⭕ {o}',f'💰 Pozo: {g["bet"]*2:,} PiPesos']
    if note: parts += ['',note]
    if g['status']=='active': parts += ['',f'🎯 Turno de {visible_user(user_id=g["turn_id"])}']
    return '\n'.join(parts)


def _winner(board):
    wins=((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6))
    for a,b,c in wins:
        if board[a]!=' ' and board[a]==board[b]==board[c]: return board[a]
    return None


def _target_from_update(update, context):
    msg=update.effective_message
    if msg.reply_to_message and msg.reply_to_message.from_user and not msg.reply_to_message.from_user.is_bot:
        return msg.reply_to_message.from_user.id
    if len(context.args)>=2 and context.args[0].startswith('@'):
        username=context.args[0][1:].lower(); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT id_user FROM perfiles_tb WHERE lower(username)=%s LIMIT 1",(username,)); r=c.fetchone(); return r[0] if r else None
        finally:_put_connection(conn)
    return None


async def gato(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private': return await update.effective_message.reply_text('🐱 El Gato se juega en el grupo.')
    target=_target_from_update(update,context)
    args=context.args
    raw=None
    if args:
        raw=args[1] if args[0].startswith('@') and len(args)>1 else args[0]
    if raw is None:return await update.effective_message.reply_text('🐱 Usa /gato 100 para abrir partida o /gato @usuario 100 para retar a alguien.')
    try: bet=int(str(raw).replace(',',''))
    except Exception:return await update.effective_message.reply_text('⚠️ La apuesta debe ser un número.')
    if bet<MIN_BET:return await update.effective_message.reply_text(f'🐱 La apuesta mínima es {MIN_BET:,} PiPesos.')
    uid=update.effective_user.id
    if target==uid:return await update.effective_message.reply_text('🐱 No puedes retarte a ti mismo jajaja.')
    if args and args[0].startswith('@') and target is None:return await update.effective_message.reply_text('🐱 No encontré a ese usuario registrado. También puedes responder a uno de sus mensajes con /gato 100.')
    chat=update.effective_chat.id; thread=getattr(update.effective_message,'message_thread_id',None)
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT 1 FROM gato_games_tb WHERE status IN ('open','active') AND (creator_id=%s OR opponent_id=%s) LIMIT 1",(uid,uid))
        if c.fetchone():return await update.effective_message.reply_text('🐱 Ya tienes una partida de Gato pendiente o activa.')
        c.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s",(uid,)); r=c.fetchone()
        if not r or r[0]<bet:return await update.effective_message.reply_text(f'💸 No tienes {bet:,} PiPesos para respaldar esa apuesta.')
        c.execute("INSERT INTO gato_games_tb(chat_id,thread_id,creator_id,invited_id,bet) VALUES(%s,%s,%s,%s,%s) RETURNING game_id",(chat,thread,uid,target,bet)); gid=c.fetchone()[0]; conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:_put_connection(conn)
    who=f' reta a {visible_user(user_id=target)}' if target else ' abrió una partida para cualquiera'
    await update.effective_message.reply_text(f'🐱 GATO\n\n{visible_user(user=update.effective_user)}{who}.\n💰 Apuesta: {bet:,} PiPesos por jugador\n🏆 Pozo: {bet*2:,} PiPesos',reply_markup=_open_kb(gid))


async def gato_callback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); p=q.data.split(':'); action=p[1]; gid=int(p[2]); uid=q.from_user.id; g=_get(gid)
    if not g:return await q.answer('Esta partida ya no existe.',show_alert=True)
    if action=='c':
        if g['status']!='open' or uid!=g['creator_id']:return await q.answer('Solo quien abrió una partida pendiente puede cancelarla.',show_alert=True)
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("UPDATE gato_games_tb SET status='cancelled',finished_at=now() WHERE game_id=%s AND status='open'",(gid,)); conn.commit()
        finally:_put_connection(conn)
        return await q.edit_message_text('🐱 Partida de Gato cancelada.')
    if action=='a':
        if g['status']!='open':return await q.answer('Esta partida ya fue tomada.',show_alert=True)
        if uid==g['creator_id']:return await q.answer('Necesitas otro jugador 😹',show_alert=True)
        if g['invited_id'] and uid!=g['invited_id']:return await q.answer('Este reto es para otra persona.',show_alert=True)
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT 1 FROM gato_games_tb WHERE game_id<>%s AND status='active' AND (creator_id=%s OR opponent_id=%s) LIMIT 1",(gid,uid,uid)); busy=c.fetchone()
        finally:_put_connection(conn)
        if busy:return await q.answer('Ya tienes otra partida activa.',show_alert=True)
        if not reservar_apuesta_doble(g['creator_id'],uid,g['bet']):return await q.answer('Ambos necesitan saldo suficiente.',show_alert=True)
        x_id,o_id=(g['creator_id'],uid) if random.choice((True,False)) else (uid,g['creator_id']); first=random.choice((x_id,o_id))
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("UPDATE gato_games_tb SET opponent_id=%s,status='active',x_id=%s,o_id=%s,turn_id=%s,accepted_at=now() WHERE game_id=%s AND status='open'",(uid,x_id,o_id,first,gid))
            if c.rowcount!=1:
                conn.rollback(); reembolsar_apuesta_doble(g['creator_id'],uid,g['bet']); return await q.answer('Alguien se adelantó.',show_alert=True)
            conn.commit()
        finally:_put_connection(conn)
        ng=_get(gid); return await q.edit_message_text(_text(ng),reply_markup=_board_kb(ng))
    if action=='p' and len(p)>=4:
        if g['status']!='active':return await q.answer('La partida ya terminó.',show_alert=True)
        if uid!=g['turn_id']:return await q.answer('No es tu turno.',show_alert=True)
        i=int(p[3]); board=list(g['board'])
        if i<0 or i>8 or board[i]!=' ':return await q.answer('Esa casilla ya está ocupada.',show_alert=True)
        mark='X' if uid==g['x_id'] else 'O'; board[i]=mark; board=''.join(board); win=_winner(board); draw=not win and ' ' not in board
        other=g['o_id'] if uid==g['x_id'] else g['x_id']; conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT status,turn_id FROM gato_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); st=c.fetchone()
            if not st or st[0]!='active' or st[1]!=uid:conn.rollback(); return await q.answer('El turno acaba de cambiar.',show_alert=True)
            if win:
                c.execute("UPDATE gato_games_tb SET board=%s,status='finished',winner_id=%s,finished_at=now() WHERE game_id=%s",(board,uid,gid)); c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(g['bet']*2,uid))
                c.execute("INSERT INTO gato_stats_tb(user_id,wins,games) VALUES(%s,1,1) ON CONFLICT(user_id) DO UPDATE SET wins=gato_stats_tb.wins+1,games=gato_stats_tb.games+1",(uid,)); c.execute("INSERT INTO gato_stats_tb(user_id,losses,games) VALUES(%s,1,1) ON CONFLICT(user_id) DO UPDATE SET losses=gato_stats_tb.losses+1,games=gato_stats_tb.games+1",(other,))
            elif draw:
                c.execute("UPDATE gato_games_tb SET board=%s,status='draw',finished_at=now() WHERE game_id=%s",(board,gid)); c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user IN (%s,%s)",(g['bet'],g['creator_id'],g['opponent_id'])); c.execute("INSERT INTO gato_stats_tb(user_id,draws,games) VALUES(%s,1,1) ON CONFLICT(user_id) DO UPDATE SET draws=gato_stats_tb.draws+1,games=gato_stats_tb.games+1",(g['creator_id'],)); c.execute("INSERT INTO gato_stats_tb(user_id,draws,games) VALUES(%s,1,1) ON CONFLICT(user_id) DO UPDATE SET draws=gato_stats_tb.draws+1,games=gato_stats_tb.games+1",(g['opponent_id'],))
            else:c.execute("UPDATE gato_games_tb SET board=%s,turn_id=%s WHERE game_id=%s",(board,other,gid))
            conn.commit()
        except Exception:
            conn.rollback(); raise
        finally:_put_connection(conn)
        ng=_get(gid)
        if win:
            await q.edit_message_text(_text(ng,f'🏆 {visible_user(user_id=uid)} hizo tres en línea y gana {g["bet"]*2:,} PiPesos.'))
            await send_victory(context,uid,'gato',g['chat_id'],g['thread_id'],visible_user(user_id=uid)); return
        if draw:return await q.edit_message_text(_text(ng,'🤝 Empate. Se devolvió la apuesta a ambos.'))
        return await q.edit_message_text(_text(ng),reply_markup=_board_kb(ng))


async def cancelar_gato(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; chat=update.effective_chat.id; thread=getattr(update.effective_message,'message_thread_id',None)
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT game_id,status FROM gato_games_tb WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) AND creator_id=%s AND status='open' ORDER BY game_id DESC LIMIT 1 FOR UPDATE",(chat,thread,uid)); r=c.fetchone()
        if not r:conn.rollback(); return await update.effective_message.reply_text('🐱 No tienes una partida abierta que puedas cancelar.')
        c.execute("UPDATE gato_games_tb SET status='cancelled',finished_at=now() WHERE game_id=%s AND status='open'",(r[0],)); conn.commit()
    finally:_put_connection(conn)
    await update.effective_message.reply_text('🐱 Partida de Gato cancelada.')


async def ranking_gato(update:Update, context:ContextTypes.DEFAULT_TYPE):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT user_id,wins,losses,draws FROM gato_stats_tb ORDER BY wins DESC,games DESC LIMIT 10"); rows=c.fetchall()
    finally:_put_connection(conn)
    if not rows:return await update.effective_message.reply_text('🐱 Todavía no hay partidas terminadas.')
    lines=['🏆 RANKING GATO','']+[f'{i}. {visible_user(user_id=u)} · {w}V/{l}D · {d}E' for i,(u,w,l,d) in enumerate(rows,1)]
    await update.effective_message.reply_text('\n'.join(lines))
