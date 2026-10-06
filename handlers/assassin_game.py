"""Asesino 2.0: partida social rápida, roles y acciones privadas, sin pistas automáticas."""
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection
from src.utils.root_owner import ensure_root_identity

REWARD = 3000
ROUND_SECONDS = 180
MAX_ROUNDS = 5
_seen_members = set()


def ensure_assassin_tables():
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS assassin_fast_games_tb(
          game_id BIGSERIAL PRIMARY KEY, chat_id BIGINT NOT NULL, thread_id BIGINT,
          owner_id BIGINT NOT NULL, status TEXT NOT NULL DEFAULT 'lobby', round_no INT NOT NULL DEFAULT 0,
          public_message_id BIGINT, sabotage_round INT, action_used BOOLEAN NOT NULL DEFAULT FALSE,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), started_at TIMESTAMPTZ, ended_at TIMESTAMPTZ)""")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_assassin_fast_open ON assassin_fast_games_tb(chat_id,COALESCE(thread_id,0)) WHERE status IN ('lobby','active')")
        c.execute("""CREATE TABLE IF NOT EXISTS assassin_fast_players_tb(
          game_id BIGINT NOT NULL REFERENCES assassin_fast_games_tb(game_id) ON DELETE CASCADE,
          user_id BIGINT NOT NULL, nombre TEXT NOT NULL, role TEXT, alive BOOLEAN NOT NULL DEFAULT TRUE,
          accused BOOLEAN NOT NULL DEFAULT FALSE, secret_used_round INT NOT NULL DEFAULT 0,
          joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(game_id,user_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS assassin_fast_actions_tb(
          game_id BIGINT NOT NULL REFERENCES assassin_fast_games_tb(game_id) ON DELETE CASCADE,
          round_no INT NOT NULL, actor_id BIGINT NOT NULL, action TEXT NOT NULL, target_id BIGINT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), PRIMARY KEY(game_id,round_no,actor_id,action))""")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        _put_connection(conn)


def assassin_track_member(update):
    # Se conserva el hook para no tocar el resto de main.py; Asesino 2.0 solo usa quienes pulsan Unirme.
    return


def _thread(update):
    m = update.effective_message
    return getattr(m, 'message_thread_id', None)


def _name(u):
    return ('@' + u.username) if getattr(u, 'username', None) else (u.full_name or 'Jugador')


def _lobby_kb(gid, count):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f'🙋 Unirme ({count})', callback_data=f'as:join:{gid}'), InlineKeyboardButton('🚪 Salirme', callback_data=f'as:leave:{gid}')],
        [InlineKeyboardButton('🔪 Iniciar', callback_data=f'as:start:{gid}'), InlineKeyboardButton('❌ Cancelar', callback_data=f'as:cancel:{gid}')],
    ])


def _game_kb(gid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('💬 Interrogar', callback_data=f'as:interrogate:{gid}'), InlineKeyboardButton('🔪 Acusar', callback_data=f'as:accuse:{gid}')],
        [InlineKeyboardButton('🎭 Mi rol / acciones', callback_data=f'as:role:{gid}')],
    ])


def _target_kb(prefix, gid, players, exclude=None):
    rows=[]
    for uid,name in players:
        if uid == exclude: continue
        rows.append([InlineKeyboardButton(name[:32], callback_data=f'as:{prefix}:{gid}:{uid}')])
    rows.append([InlineKeyboardButton('↩️ Volver', callback_data=f'as:role:{gid}')])
    return InlineKeyboardMarkup(rows[:40])


def _job_name(gid): return f'assassin_fast_{gid}'


async def asesino(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private':
        return await update.effective_message.reply_text('🔪 Abre la partida desde el grupo.')
    chat=update.effective_chat.id; thread=_thread(update); owner=update.effective_user.id
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("SELECT game_id,status FROM assassin_fast_games_tb WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) AND status IN ('lobby','active') ORDER BY game_id DESC LIMIT 1",(chat,thread))
        row=c.fetchone()
        if row and row[1]=='active':
            conn.rollback(); return await update.effective_message.reply_text('🔪 Ya hay una partida en curso. Usa el panel actual o /terminarasesino si eres admin.')
        if row: gid=row[0]
        else:
            c.execute("INSERT INTO assassin_fast_games_tb(chat_id,thread_id,owner_id) VALUES(%s,%s,%s) RETURNING game_id",(chat,thread,owner)); gid=c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM assassin_fast_players_tb WHERE game_id=%s",(gid,)); count=int(c.fetchone()[0]); conn.commit()
    except Exception:
        conn.rollback(); return await update.effective_message.reply_text('⚠️ No pude abrir Asesino.')
    finally: _put_connection(conn)
    msg=await update.effective_message.reply_text(
        f'🔪 *ASESINO*\n\n👥 Jugadores: {count}\n⚡ Partida rápida · sin pistas automáticas\n\n4–6 jugadores: 1 asesino\n7 o más: 2 asesinos\n\nPulsen 🙋 Unirme y después inicia la partida.',
        parse_mode='Markdown', reply_markup=_lobby_kb(gid,count))
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE assassin_fast_games_tb SET public_message_id=%s WHERE game_id=%s",(msg.message_id,gid)); conn.commit()
    finally:_put_connection(conn)


async def cancelarasesino(update:Update, context:ContextTypes.DEFAULT_TYPE):
    return await _finish_command(update, context, lobby_only=True)


async def terminarasesino(update:Update, context:ContextTypes.DEFAULT_TYPE):
    return await _finish_command(update, context, lobby_only=False)


async def reiniciarasesino(update:Update, context:ContextTypes.DEFAULT_TYPE):
    # Compatibilidad con el comando viejo: ahora simplemente termina la partida actual.
    return await terminarasesino(update, context)


async def _finish_command(update, context, lobby_only=False):
    if update.effective_chat.type=='private': return await update.effective_message.reply_text('Hazlo desde el grupo.')
    if not ensure_root_identity(update.effective_user): return await update.effective_message.reply_text('🔒 Solo Kiu/admin puede hacer eso.')
    chat=update.effective_chat.id; thread=_thread(update); conn=_get_connection(); gid=None
    try:
        c=conn.cursor(); c.execute("SELECT game_id,status FROM assassin_fast_games_tb WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) AND status IN ('lobby','active') ORDER BY game_id DESC LIMIT 1 FOR UPDATE",(chat,thread)); row=c.fetchone()
        if not row: conn.rollback(); return await update.effective_message.reply_text('🔪 No hay una partida activa.')
        gid,status=row
        if lobby_only and status!='lobby': conn.rollback(); return await update.effective_message.reply_text('🔪 La partida ya empezó. Usa /terminarasesino.')
        c.execute("UPDATE assassin_fast_games_tb SET status='cancelled',ended_at=NOW() WHERE game_id=%s",(gid,)); conn.commit()
    except Exception:
        conn.rollback(); return await update.effective_message.reply_text('⚠️ No pude terminar la partida.')
    finally:_put_connection(conn)
    for j in context.job_queue.get_jobs_by_name(_job_name(gid)): j.schedule_removal()
    await update.effective_message.reply_text('🛑 Partida del Asesino terminada. Todo quedó limpio y ya pueden abrir otra.')


async def _send_roles(context,gid):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT user_id,nombre,role FROM assassin_fast_players_tb WHERE game_id=%s ORDER BY joined_at",(gid,)); players=c.fetchall()
    finally:_put_connection(conn)
    for uid,name,role in players:
        if role=='killer': text='🔪 *ERES ASESINO*\nEngaña al grupo. Cada ronda puedes atacar o sabotear desde aquí.'
        elif role=='detective': text='🕵️ *ERES DETECTIVE*\nInvestiga en privado. Tus resultados son parciales: tendrás que pensar y cruzar información.'
        elif role=='watcher': text='👁 *ERES VIGILANTE*\nVigila a alguien y sabrás si realizó una acción secreta durante la ronda.'
        else: text='😇 *ERES INOCENTE*\nObserva, interroga y acusa con cuidado. Solo tienes una acusación.'
        try: await context.bot.send_message(uid,text,parse_mode='Markdown',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🎭 Ver mis acciones',callback_data=f'as:role:{gid}')]]))
        except Exception: pass


async def _round_tick(context:ContextTypes.DEFAULT_TYPE):
    gid=context.job.data['gid']; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,status,round_no FROM assassin_fast_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); row=c.fetchone()
        if not row or row[2]!='active': conn.rollback(); return
        chat,thread,_,rnd=row
        if rnd>=MAX_ROUNDS:
            c.execute("SELECT user_id,nombre FROM assassin_fast_players_tb WHERE game_id=%s AND role='killer' AND alive=TRUE",(gid,)); killers=c.fetchall()
            c.execute("UPDATE assassin_fast_games_tb SET status='ended',ended_at=NOW() WHERE game_id=%s",(gid,))
            for uid,_ in killers: c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(REWARD,uid))
            conn.commit()
            names=', '.join(n for _,n in killers) or 'el asesino'
            await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f'🔪 *EL ASESINO ESCAPÓ*\n\nSobrevivió hasta el final: {names}\n💰 +{REWARD:,} PiPesos para cada asesino superviviente.',parse_mode='Markdown')
            return
        nr=rnd+1; c.execute("UPDATE assassin_fast_games_tb SET round_no=%s,action_used=FALSE WHERE game_id=%s",(nr,gid)); conn.commit()
    except Exception:
        conn.rollback(); return
    finally:_put_connection(conn)
    await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f'🌙 *RONDA {nr}/{MAX_ROUNDS}*\n\nLos roles con poderes ya pueden actuar otra vez por privado.\nHablen, sospechen y decidan bien antes de acusar. 👀',parse_mode='Markdown',reply_markup=_game_kb(gid))


async def assassin_cycle_job(context:ContextTypes.DEFAULT_TYPE):
    # Compatibilidad con el job antiguo de main.py. Asesino 2.0 programa sus propias rondas.
    return


async def assassin_callback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; p=q.data.split(':'); action=p[1] if len(p)>1 else ''; uid=q.from_user.id
    if action in ('join','leave'):
        gid=int(p[2]); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT status FROM assassin_fast_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); row=c.fetchone()
            if not row or row[0]!='lobby': conn.rollback(); return await q.answer('La sala ya cerró.',show_alert=True)
            if action=='join':
                c.execute("INSERT INTO assassin_fast_players_tb(game_id,user_id,nombre) VALUES(%s,%s,%s) ON CONFLICT(game_id,user_id) DO UPDATE SET nombre=EXCLUDED.nombre",(gid,uid,_name(q.from_user))); ans='🙋 Ya estás dentro.'
            else:
                c.execute("DELETE FROM assassin_fast_players_tb WHERE game_id=%s AND user_id=%s",(gid,uid)); ans='🚪 Saliste de la sala.'
            c.execute("SELECT COUNT(*) FROM assassin_fast_players_tb WHERE game_id=%s",(gid,)); count=int(c.fetchone()[0]); conn.commit()
        except Exception:
            conn.rollback(); return await q.answer('No pude actualizar la sala.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer(ans,show_alert=True)
        try: await q.edit_message_text(f'🔪 *ASESINO*\n\n👥 Jugadores: {count}\n⚡ Partida rápida · sin pistas automáticas\n\n4–6 jugadores: 1 asesino\n7 o más: 2 asesinos\n\nPulsen 🙋 Unirme y después inicia la partida.',parse_mode='Markdown',reply_markup=_lobby_kb(gid,count))
        except Exception: pass
        return

    if action in ('start','cancel'):
        gid=int(p[2])
        if not ensure_root_identity(q.from_user): return await q.answer('Solo Kiu/admin puede controlar la partida.',show_alert=True)
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT chat_id,thread_id,status FROM assassin_fast_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); g=c.fetchone()
            if not g or g[2]!='lobby': conn.rollback(); return await q.answer('La sala ya no está disponible.',show_alert=True)
            if action=='cancel':
                c.execute("UPDATE assassin_fast_games_tb SET status='cancelled',ended_at=NOW() WHERE game_id=%s",(gid,)); conn.commit(); await q.answer('Sala cancelada.'); return await q.edit_message_text('🛑 Sala del Asesino cancelada.')
            c.execute("SELECT user_id,nombre FROM assassin_fast_players_tb WHERE game_id=%s ORDER BY joined_at",(gid,)); players=c.fetchall()
            if len(players)<4: conn.rollback(); return await q.answer('Necesitas mínimo 4 jugadores.',show_alert=True)
            killer_n=1 if len(players)<=6 else 2
            ids=[x[0] for x in players]; killers=set(random.sample(ids,killer_n)); remaining=[x for x in ids if x not in killers]
            detective=random.choice(remaining); remaining.remove(detective)
            watcher=random.choice(remaining) if len(remaining)>=2 else None
            for pid,_ in players:
                role='killer' if pid in killers else ('detective' if pid==detective else ('watcher' if pid==watcher else 'innocent'))
                c.execute("UPDATE assassin_fast_players_tb SET role=%s,alive=TRUE,accused=FALSE,secret_used_round=0 WHERE game_id=%s AND user_id=%s",(role,gid,pid))
            c.execute("UPDATE assassin_fast_games_tb SET status='active',round_no=1,started_at=NOW(),action_used=FALSE WHERE game_id=%s",(gid,)); conn.commit(); chat,thread=g[0],g[1]
        except Exception:
            conn.rollback(); return await q.answer('No pude iniciar la partida.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('🔪 Partida iniciada.')
        try: await q.edit_message_text(f'🔪 *ASESINO — RONDA 1/{MAX_ROUNDS}*\n\n👥 {len(players)} jugadores\n😈 Asesinos ocultos: {killer_n}\n\nLos roles y poderes fueron enviados por privado.\n💬 Hablen en el grupo, interroguen y acusen cuando estén seguros.',parse_mode='Markdown',reply_markup=_game_kb(gid))
        except Exception: pass
        await _send_roles(context,gid)
        context.job_queue.run_repeating(_round_tick,interval=ROUND_SECONDS,first=ROUND_SECONDS,name=_job_name(gid),data={'gid':gid})
        return

    gid=int(p[2]) if len(p)>2 and p[2].isdigit() else None
    if not gid: return await q.answer('Acción inválida.',show_alert=True)
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,status,round_no,sabotage_round FROM assassin_fast_games_tb WHERE game_id=%s",(gid,)); game=c.fetchone()
        if not game or game[2]!='active': conn.rollback(); return await q.answer('La partida ya terminó.',show_alert=True)
        chat,thread,_,rnd,sabotage_round=game
        c.execute("SELECT nombre,role,alive,accused,secret_used_round FROM assassin_fast_players_tb WHERE game_id=%s AND user_id=%s",(gid,uid)); me=c.fetchone()
        if not me: conn.rollback(); return await q.answer('No estás en esta partida.',show_alert=True)
        if not me[2]: conn.rollback(); return await q.answer('☠️ Estás fuera de la partida.',show_alert=True)
        c.execute("SELECT user_id,nombre FROM assassin_fast_players_tb WHERE game_id=%s AND alive=TRUE ORDER BY joined_at",(gid,)); alive=c.fetchall(); conn.rollback()
    except Exception:
        conn.rollback(); return await q.answer('No pude abrir esa acción.',show_alert=True)
    finally:_put_connection(conn)

    role=me[1]
    if action=='role':
        if role=='killer': buttons=[[InlineKeyboardButton('🔪 Atacar',callback_data=f'as:attack:{gid}'),InlineKeyboardButton('🎭 Sabotear',callback_data=f'as:sabotage:{gid}')]]; desc='Eres 🔪 ASESINO. Una acción secreta por ronda entre los asesinos.'
        elif role=='detective': buttons=[[InlineKeyboardButton('🔍 Investigar',callback_data=f'as:investigate:{gid}')]]; desc='Eres 🕵️ DETECTIVE. Una investigación por ronda; el resultado nunca es una respuesta directa.'
        elif role=='watcher': buttons=[[InlineKeyboardButton('👁 Vigilar',callback_data=f'as:watch:{gid}')]]; desc='Eres 👁 VIGILANTE. Puedes comprobar si alguien realizó una acción secreta esta ronda.'
        else: buttons=[]; desc='Eres 😇 INOCENTE. Habla, interroga y usa tu única acusación con cuidado.'
        buttons.append([InlineKeyboardButton('💬 Interrogar',callback_data=f'as:interrogate:{gid}'),InlineKeyboardButton('🔪 Acusar',callback_data=f'as:accuse:{gid}')])
        try: await context.bot.send_message(uid,desc,reply_markup=InlineKeyboardMarkup(buttons))
        except Exception: return await q.answer('Abre primero el privado con PiGod.',show_alert=True)
        return await q.answer('Te mandé tus acciones por privado.',show_alert=True)

    if action in ('interrogate','accuse','investigate','watch','attack'):
        if action=='accuse' and me[3]: return await q.answer('Ya usaste tu única acusación.',show_alert=True)
        if action=='investigate' and role!='detective': return await q.answer('Esa acción no pertenece a tu rol.',show_alert=True)
        if action=='watch' and role!='watcher': return await q.answer('Esa acción no pertenece a tu rol.',show_alert=True)
        if action=='attack' and role!='killer': return await q.answer('Esa acción no pertenece a tu rol.',show_alert=True)
        if action in ('investigate','watch','attack') and me[4]==rnd: return await q.answer('Ya usaste tu poder esta ronda.',show_alert=True)
        prefix={'interrogate':'interrogate_pick','accuse':'accuse_pick','investigate':'investigate_pick','watch':'watch_pick','attack':'attack_pick'}[action]
        text={'interrogate':'💬 ¿A quién quieres interrogar?','accuse':'🔪 ¿A quién acusas? Recuerda: solo tienes una oportunidad.','investigate':'🔍 ¿A quién quieres investigar?','watch':'👁 ¿A quién quieres vigilar?','attack':'🔪 ¿A quién quieres atacar?'}[action]
        try: await context.bot.send_message(uid,text,reply_markup=_target_kb(prefix,gid,alive,uid))
        except Exception: return await q.answer('Abre primero el privado con PiGod.',show_alert=True)
        return await q.answer('Revisa tu privado. 👀',show_alert=True)

    if action=='sabotage':
        if role!='killer': return await q.answer('Esa acción no pertenece a tu rol.',show_alert=True)
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT action_used,round_no FROM assassin_fast_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); st=c.fetchone()
            if not st or st[0]: conn.rollback(); return await q.answer('Los asesinos ya usaron su acción de esta ronda.',show_alert=True)
            c.execute("UPDATE assassin_fast_games_tb SET action_used=TRUE,sabotage_round=%s WHERE game_id=%s",(rnd,gid)); c.execute("UPDATE assassin_fast_players_tb SET secret_used_round=%s WHERE game_id=%s AND user_id=%s",(rnd,gid,uid)); conn.commit()
        finally:_put_connection(conn)
        await q.answer('🎭 Sabotaje preparado.',show_alert=True); return

    if action.endswith('_pick') and len(p)>=4:
        target=int(p[3]); target_name=next((n for i,n in alive if i==target),None)
        if not target_name: return await q.answer('Ese jugador ya no está disponible.',show_alert=True)
        if action=='interrogate_pick':
            await q.answer('Interrogatorio abierto.',show_alert=True)
            await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f'💬 *INTERROGATORIO*\n\n{me[0]} quiere una respuesta de {target_name}. 👀\n\nPuede preguntarle en el chat. ¿Dirá la verdad?',parse_mode='Markdown')
            return
        if action=='accuse_pick':
            kb=InlineKeyboardMarkup([[InlineKeyboardButton('⚠️ Sí, acusar',callback_data=f'as:accuse_confirm:{gid}:{target}'),InlineKeyboardButton('↩️ No',callback_data=f'as:role:{gid}')]])
            return await q.edit_message_text(f'🔪 ¿Seguro que acusas a {target_name}?\n\nSolo tienes una acusación en toda la partida.',reply_markup=kb)
        if action in ('investigate_pick','watch_pick','attack_pick'):
            conn=_get_connection()
            try:
                c=conn.cursor(); c.execute("SELECT round_no,action_used,sabotage_round FROM assassin_fast_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); st=c.fetchone(); current=st[0]
                c.execute("SELECT role,secret_used_round FROM assassin_fast_players_tb WHERE game_id=%s AND user_id=%s",(gid,uid)); actor=c.fetchone()
                if not actor or actor[1]==current: conn.rollback(); return await q.answer('Ya usaste tu poder esta ronda.',show_alert=True)
                if action=='attack_pick':
                    if st[1]: conn.rollback(); return await q.answer('Los asesinos ya usaron su acción de esta ronda.',show_alert=True)
                    c.execute("UPDATE assassin_fast_games_tb SET action_used=TRUE WHERE game_id=%s",(gid,)); c.execute("UPDATE assassin_fast_players_tb SET alive=FALSE WHERE game_id=%s AND user_id=%s",(gid,target))
                c.execute("UPDATE assassin_fast_players_tb SET secret_used_round=%s WHERE game_id=%s AND user_id=%s",(current,gid,uid))
                if action=='watch_pick':
                    c.execute("SELECT secret_used_round FROM assassin_fast_players_tb WHERE game_id=%s AND user_id=%s",(gid,target)); tr=c.fetchone(); did=bool(tr and tr[0]==current)
                if action=='investigate_pick':
                    c.execute("SELECT role FROM assassin_fast_players_tb WHERE game_id=%s AND user_id=%s",(gid,target)); tr=c.fetchone(); target_role=tr[0] if tr else 'innocent'; sabotaged=(st[2]==current)
                conn.commit()
            except Exception:
                conn.rollback(); return await q.answer('No pude completar la acción.',show_alert=True)
            finally:_put_connection(conn)
            if action=='attack_pick':
                await q.answer('🔪 Ataque realizado.',show_alert=True); await q.edit_message_text(f'🔪 Elegiste a {target_name}.')
                await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f'☠️ *{target_name} ha caído.*\n\nEl asesino sigue entre ustedes. No habrá pistas automáticas: hablen, investiguen y piensen. 👀',parse_mode='Markdown',reply_markup=_game_kb(gid))
                await _check_end(context,gid,chat,thread); return
            if action=='watch_pick':
                result='realizó una acción secreta esta ronda' if did else 'no registró ninguna acción secreta esta ronda'
                return await q.edit_message_text(f'👁 Vigilaste a {target_name}.\n\nResultado: {result}.\n\nEsto no confirma su rol.')
            suspicious = (target_role=='killer')
            if sabotaged: suspicious = random.choice([True,False])
            elif random.random()<0.25: suspicious = not suspicious
            text=('encontraste señales que podrían relacionarlo con movimientos sospechosos' if suspicious else 'no encontraste nada concluyente que lo conecte con los movimientos sospechosos')
            return await q.edit_message_text(f'🔍 Investigaste a {target_name}.\n\n{text.capitalize()}.\n\n⚠️ Una investigación nunca es prueba definitiva.')

    if action=='accuse_confirm' and len(p)>=4:
        target=int(p[3]); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT accused FROM assassin_fast_players_tb WHERE game_id=%s AND user_id=%s FOR UPDATE",(gid,uid)); ar=c.fetchone()
            if not ar or ar[0]: conn.rollback(); return await q.answer('Ya usaste tu acusación.',show_alert=True)
            c.execute("SELECT nombre,role,alive FROM assassin_fast_players_tb WHERE game_id=%s AND user_id=%s",(gid,target)); tr=c.fetchone()
            if not tr or not tr[2]: conn.rollback(); return await q.answer('Ese jugador ya no está disponible.',show_alert=True)
            c.execute("UPDATE assassin_fast_players_tb SET accused=TRUE WHERE game_id=%s AND user_id=%s",(gid,uid)); correct=(tr[1]=='killer')
            if correct: c.execute("UPDATE assassin_fast_players_tb SET alive=FALSE WHERE game_id=%s AND user_id=%s",(gid,target))
            conn.commit(); target_name=tr[0]
        except Exception:
            conn.rollback(); return await q.answer('No pude registrar la acusación.',show_alert=True)
        finally:_put_connection(conn)
        if correct:
            await q.answer('🚨 ¡Era asesino!',show_alert=True); await q.edit_message_text(f'🚨 ¡Acertaste! {target_name} era asesino.')
            await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f'🚨 *¡ASESINO DESCUBIERTO!*\n\n{me[0]} acusó a {target_name}… y tenía razón. 🔪',parse_mode='Markdown')
            ended=await _check_end(context,gid,chat,thread,winner_id=uid,winner_name=me[0])
            return
        await q.answer('❌ Acusación fallida.',show_alert=True); await q.edit_message_text(f'❌ {target_name} no era asesino.\nTu única acusación ya fue utilizada.')
        await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f'⚖️ {me[0]} acusó a {target_name}… y se equivocó. 👀')
        return

    await q.answer('Acción no disponible.',show_alert=True)


async def _check_end(context,gid,chat,thread,winner_id=None,winner_name=None):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT COUNT(*) FROM assassin_fast_players_tb WHERE game_id=%s AND role='killer' AND alive=TRUE",(gid,)); killers=int(c.fetchone()[0])
        c.execute("SELECT COUNT(*) FROM assassin_fast_players_tb WHERE game_id=%s AND role<>'killer' AND alive=TRUE",(gid,)); innocents=int(c.fetchone()[0])
        if killers==0:
            c.execute("UPDATE assassin_fast_games_tb SET status='ended',ended_at=NOW() WHERE game_id=%s",(gid,))
            if winner_id: c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(REWARD,winner_id))
            conn.commit()
            for j in context.job_queue.get_jobs_by_name(_job_name(gid)): j.schedule_removal()
            prize=f'\n💰 +{REWARD:,} PiPesos para {winner_name}.' if winner_id else ''
            await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f'🏆 *CASO RESUELTO*\n\nTodos los asesinos fueron descubiertos.{prize}',parse_mode='Markdown'); return True
        if killers>=innocents and innocents>0:
            c.execute("SELECT user_id,nombre FROM assassin_fast_players_tb WHERE game_id=%s AND role='killer' AND alive=TRUE",(gid,)); ks=c.fetchall()
            c.execute("UPDATE assassin_fast_games_tb SET status='ended',ended_at=NOW() WHERE game_id=%s",(gid,))
            for kid,_ in ks: c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(REWARD,kid))
            conn.commit()
            for j in context.job_queue.get_jobs_by_name(_job_name(gid)): j.schedule_removal()
            await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f'🔪 *LOS ASESINOS TOMARON EL CONTROL*\n\nSobrevivieron: {", ".join(n for _,n in ks)}\n💰 +{REWARD:,} PiPesos para cada uno.',parse_mode='Markdown'); return True
        conn.rollback(); return False
    except Exception:
        conn.rollback(); return False
    finally:_put_connection(conn)
