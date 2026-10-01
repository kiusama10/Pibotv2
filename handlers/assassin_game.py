import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection,_put_connection

MIN_PLAYERS=4
MAX_PLAYERS=12

def _loc(update):
    m=update.effective_message
    return update.effective_chat.id, getattr(m,'message_thread_id',None)

def _game(chat,thread,lock=False):
    conn=_get_connection()
    try:
        c=conn.cursor(); sql="SELECT game_id,host_id,estado,asesino_id,ronda FROM assassin_games_tb WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) AND estado IN ('lobby','jugando','votacion') ORDER BY game_id DESC LIMIT 1" + (' FOR UPDATE' if lock else '')
        c.execute(sql,(chat,thread)); return c.fetchone()
    finally:_put_connection(conn)

def _players(gid,alive_only=False):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute('SELECT user_id,nombre,vivo FROM assassin_players_tb WHERE game_id=%s'+(" AND vivo=TRUE" if alive_only else '')+' ORDER BY joined_at',(gid,)); return c.fetchall()
    finally:_put_connection(conn)

async def asesino(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private': return await update.effective_message.reply_text('🔪 Las partidas se crean en el grupo. Los secretos sí llegan por aquí.')
    chat,thread=_loc(update)
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT game_id FROM assassin_games_tb WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) AND estado IN ('lobby','jugando','votacion')",(chat,thread))
        if c.fetchone(): conn.rollback(); return await update.effective_message.reply_text('🔪 Ya hay una partida de Asesino activa en este tema.')
        c.execute("INSERT INTO assassin_games_tb(chat_id,thread_id,host_id,estado) VALUES(%s,%s,%s,'lobby') RETURNING game_id",(chat,thread,update.effective_user.id)); gid=c.fetchone()[0]
        c.execute('INSERT INTO assassin_players_tb(game_id,user_id,nombre) VALUES(%s,%s,%s)',(gid,update.effective_user.id,update.effective_user.full_name)); conn.commit()
    except Exception: conn.rollback(); return await update.effective_message.reply_text('No pude crear la partida.')
    finally:_put_connection(conn)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('🔪 Unirme',callback_data=f'as:join:{gid}')],[InlineKeyboardButton('▶️ Iniciar',callback_data=f'as:start:{gid}'),InlineKeyboardButton('🛑 Cancelar',callback_data=f'as:cancel:{gid}')]])
    await update.effective_message.reply_text(f'🔪 *ASESINO*\n\nLobby abierto. Necesitamos entre {MIN_PLAYERS} y {MAX_PLAYERS} personas.\nEl asesino recibirá su identidad y sus acciones por PV.\n\n👥 1 jugador',parse_mode='Markdown',reply_markup=kb)

async def _start(q,context,gid):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT host_id,chat_id,thread_id,estado FROM assassin_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
        if not g or g[3]!='lobby': conn.rollback(); return await q.answer('La partida ya cambió.',show_alert=True)
        if q.from_user.id!=g[0]: conn.rollback(); return await q.answer('Solo quien creó la partida puede iniciarla.',show_alert=True)
        c.execute('SELECT user_id,nombre FROM assassin_players_tb WHERE game_id=%s',(gid,)); ps=c.fetchall()
        if len(ps)<MIN_PLAYERS: conn.rollback(); return await q.answer(f'Faltan jugadores. Mínimo {MIN_PLAYERS}.',show_alert=True)
        assassin=random.choice(ps)[0]; c.execute("UPDATE assassin_games_tb SET estado='jugando',asesino_id=%s,iniciado_en=now() WHERE game_id=%s",(assassin,gid)); conn.commit()
    except Exception: conn.rollback(); return await q.answer('No pude iniciar.',show_alert=True)
    finally:_put_connection(conn)
    targets=[p for p in ps if p[0]!=assassin]
    kb=InlineKeyboardMarkup([[InlineKeyboardButton(f'🎯 {name[:35]}',callback_data=f'as:kill:{gid}:{uid}')] for uid,name in targets])
    try: await context.bot.send_message(assassin,'🔪 *HOY TE TOCA SER EL ASESINO*\n\nNadie más conoce tu identidad. Elige tu primera víctima:',parse_mode='Markdown',reply_markup=kb)
    except Exception:
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("UPDATE assassin_games_tb SET estado='cancelado',cerrado_en=now() WHERE game_id=%s",(gid,)); conn.commit()
        finally:_put_connection(conn)
        return await q.edit_message_text('🛑 No pude enviar el rol secreto por PV. El asesino debe haber iniciado PiBot por privado. Partida cancelada.')
    await q.edit_message_text('🔪 *LA PARTIDA COMENZÓ*\n\nEl asesino ya recibió su identidad en privado. Ahora solo falta que elija a su víctima… 👀',parse_mode='Markdown')

async def assassin_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; p=q.data.split(':'); action=p[1]; gid=int(p[2])
    if action=='join':
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT estado FROM assassin_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
            if not g or g[0]!='lobby': conn.rollback(); return await q.answer('El lobby ya cerró.',show_alert=True)
            c.execute('SELECT count(*) FROM assassin_players_tb WHERE game_id=%s',(gid,)); n=c.fetchone()[0]
            if n>=MAX_PLAYERS: conn.rollback(); return await q.answer('La partida está llena.',show_alert=True)
            c.execute('INSERT INTO assassin_players_tb(game_id,user_id,nombre) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING',(gid,q.from_user.id,q.from_user.full_name)); joined=c.rowcount; conn.commit()
        except Exception: conn.rollback(); return
        finally:_put_connection(conn)
        return await q.answer('Entraste 🔪' if joined else 'Ya estabas dentro.',show_alert=True)
    if action=='start': return await _start(q,context,gid)
    if action=='cancel':
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("UPDATE assassin_games_tb SET estado='cancelado',cerrado_en=now() WHERE game_id=%s AND host_id=%s AND estado='lobby' RETURNING game_id",(gid,q.from_user.id)); ok=c.fetchone(); conn.commit()
        finally:_put_connection(conn)
        if ok: await q.answer('Partida cancelada.'); await q.edit_message_text('🛑 Partida de Asesino cancelada.')
        else: await q.answer('No puedes cancelarla.',show_alert=True)
        return
    if action=='kill':
        victim=int(p[3]); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT asesino_id,chat_id,thread_id,estado,ronda FROM assassin_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
            if not g or g[3]!='jugando' or q.from_user.id!=g[0]: conn.rollback(); return await q.answer('No puedes hacer eso.',show_alert=True)
            c.execute('UPDATE assassin_players_tb SET vivo=FALSE WHERE game_id=%s AND user_id=%s AND vivo=TRUE RETURNING nombre',(gid,victim)); r=c.fetchone()
            if not r: conn.rollback(); return await q.answer('Esa víctima ya no está disponible.',show_alert=True)
            c.execute("UPDATE assassin_games_tb SET estado='votacion' WHERE game_id=%s",(gid,)); conn.commit(); name=r[0]
        except Exception: conn.rollback(); return
        finally:_put_connection(conn)
        await q.answer('Víctima elegida. 🤫')
        alive=_players(gid,True); buttons=[[InlineKeyboardButton(n[:30],callback_data=f'as:vote:{gid}:{u}')] for u,n,_ in alive]
        assassin_name=next((n for u,n,_ in alive if u==g[0]),'')
        clean=''.join(ch for ch in assassin_name if ch.isalnum())
        if g[4]<=1: clue=('su nombre visible tiene 8 letras o más' if len(clean)>=8 else 'su nombre visible tiene menos de 8 letras')
        elif g[4]==2: clue=(f"su nombre visible empieza con '{clean[:1].upper()}'" if clean else 'su nombre visible no empieza con una letra')
        else: clue=(f"su nombre visible termina con '{clean[-1:].upper()}'" if clean else 'su nombre visible no termina con una letra')
        await context.bot.send_message(g[1],f'💀 {name} ha sido eliminado.\n\n🔎 Pista {g[4]}: {clue}.\n🗳️ Voten de forma anónima: los nombres de quién votó a quién no se publicarán.',message_thread_id=g[2],reply_markup=InlineKeyboardMarkup(buttons))
        return
    if action=='vote':
        target=int(p[3]); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT estado,asesino_id,chat_id,thread_id,ronda FROM assassin_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
            if not g or g[0]!='votacion': conn.rollback(); return await q.answer('La votación ya terminó.',show_alert=True)
            c.execute('SELECT vivo FROM assassin_players_tb WHERE game_id=%s AND user_id=%s',(gid,q.from_user.id)); me=c.fetchone()
            if not me or not me[0]: conn.rollback(); return await q.answer('Solo supervivientes pueden votar.',show_alert=True)
            c.execute('INSERT INTO assassin_votes_tb(game_id,ronda,voter_id,target_id) VALUES(%s,%s,%s,%s) ON CONFLICT(game_id,ronda,voter_id) DO NOTHING',(gid,g[4],q.from_user.id,target)); added=c.rowcount
            c.execute('SELECT count(*) FROM assassin_players_tb WHERE game_id=%s AND vivo=TRUE',(gid,)); alive_n=c.fetchone()[0]
            c.execute('SELECT count(*) FROM assassin_votes_tb WHERE game_id=%s AND ronda=%s',(gid,g[4])); votes=c.fetchone()[0]; conn.commit()
        except Exception: conn.rollback(); return
        finally:_put_connection(conn)
        if not added: return await q.answer('Ya votaste en esta ronda.',show_alert=True)
        if votes<alive_n: return await q.answer('Voto registrado en secreto. 🤫',show_alert=True)
        await _resolve_vote(context,gid)

async def _resolve_vote(context,gid):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT asesino_id,chat_id,thread_id,ronda FROM assassin_games_tb WHERE game_id=%s AND estado='votacion' FOR UPDATE",(gid,)); g=c.fetchone()
        if not g: conn.rollback(); return
        c.execute('SELECT target_id,count(*) n FROM assassin_votes_tb WHERE game_id=%s AND ronda=%s GROUP BY target_id ORDER BY n DESC,target_id',(gid,g[3])); rows=c.fetchall(); top=rows[0][1]; tied=[x[0] for x in rows if x[1]==top]
        if len(tied)>1:
            c.execute("UPDATE assassin_games_tb SET estado='jugando',ronda=ronda+1 WHERE game_id=%s",(gid,)); conn.commit(); text='⚖️ Empate en la votación. Nadie es expulsado. El asesino vuelve a moverse…'
        else:
            out=tied[0]; c.execute('UPDATE assassin_players_tb SET vivo=FALSE WHERE game_id=%s AND user_id=%s RETURNING nombre',(gid,out)); name=c.fetchone()[0]
            if out==g[0]:
                c.execute("UPDATE assassin_games_tb SET estado='supervivientes',cerrado_en=now() WHERE game_id=%s",(gid,)); conn.commit(); text=f'🎉 ¡ATRAPARON AL ASESINO!\n\n{name} era el asesino. Los supervivientes ganan la partida.'
            else:
                c.execute('SELECT count(*) FROM assassin_players_tb WHERE game_id=%s AND vivo=TRUE AND user_id<>%s',(gid,g[0])); survivors=c.fetchone()[0]
                if survivors<=1:
                    c.execute("UPDATE assassin_games_tb SET estado='asesino',cerrado_en=now() WHERE game_id=%s",(gid,)); conn.commit(); text=f'☠️ Expulsaron a {name}, pero era inocente.\n\n🔪 El asesino ya controla la partida y gana.'
                else:
                    c.execute("UPDATE assassin_games_tb SET estado='jugando',ronda=ronda+1 WHERE game_id=%s",(gid,)); conn.commit(); text=f'😬 Expulsaron a {name}… y era inocente.\n\nEl asesino sigue suelto. Nueva ronda.'
    except Exception: conn.rollback(); return
    finally:_put_connection(conn)
    await context.bot.send_message(g[1],text,message_thread_id=g[2])
    # If the game continues, privately offer the assassin the next living targets.
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT estado,asesino_id FROM assassin_games_tb WHERE game_id=%s",(gid,)); state=c.fetchone()
    finally:_put_connection(conn)
    if state and state[0]=='jugando':
        alive=[x for x in _players(gid,True) if x[0]!=state[1]]
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(f'🎯 {n[:35]}',callback_data=f'as:kill:{gid}:{u}')] for u,n,_ in alive])
        try: await context.bot.send_message(state[1],'🔪 Nueva ronda. Elige otra víctima:',reply_markup=kb)
        except Exception: pass
