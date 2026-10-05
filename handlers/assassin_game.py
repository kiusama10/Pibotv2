"""Asesino automático: Kiu inicia/cancela; cada 6 h PiBot elige dos asesinos del grupo."""
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection,_put_connection
from src.utils.root_owner import ensure_root_identity

CYCLE_SECONDS=6*60*60
HINT_SECONDS=15*60
DETECTIVE_REWARD=3000
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
        # Estado adicional del mismo juego: muertos y acusaciones secretas.
        c.execute("""CREATE TABLE IF NOT EXISTS assassin_deaths_tb(
          cycle_id BIGINT NOT NULL REFERENCES assassin_cycles_tb(cycle_id) ON DELETE CASCADE,
          target_id BIGINT NOT NULL,killer_id BIGINT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY(cycle_id,target_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS assassin_guesses_tb(
          cycle_id BIGINT NOT NULL REFERENCES assassin_cycles_tb(cycle_id) ON DELETE CASCADE,
          target_id BIGINT NOT NULL,guesser_id BIGINT NOT NULL,suspect_id BIGINT NOT NULL,
          correct BOOLEAN NOT NULL DEFAULT FALSE,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY(cycle_id,target_id,guesser_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS assassin_players_tb(config_id BIGINT NOT NULL REFERENCES assassin_auto_tb(config_id) ON DELETE CASCADE,user_id BIGINT NOT NULL,nombre TEXT NOT NULL,joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(config_id,user_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS assassin_hint_state_tb(cycle_id BIGINT NOT NULL REFERENCES assassin_cycles_tb(cycle_id) ON DELETE CASCADE,target_id BIGINT NOT NULL,killer_id BIGINT NOT NULL,hint_no INT NOT NULL DEFAULT 1,next_hint_at TIMESTAMPTZ NOT NULL DEFAULT NOW()+INTERVAL '15 minutes',active BOOLEAN NOT NULL DEFAULT TRUE,PRIMARY KEY(cycle_id,target_id))""")
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


def _hint_for(name:str, number:int):
    clean=''.join(ch for ch in str(name) if ch.isalnum())
    low=clean.lower(); n=len(clean); vowels=sum(ch in 'aeiouáéíóú' for ch in low)
    clues=[
        'El asesino está entre las personas registradas en esta partida.',
        ('Su alias es corto (hasta 5 caracteres).' if n<=5 else ('Su alias es mediano (6 a 9 caracteres).' if n<=9 else 'Su alias es largo (10 o más caracteres).')),
        ('Su alias tiene una cantidad par de caracteres.' if n%2==0 else 'Su alias tiene una cantidad impar de caracteres.'),
        ('En su alias predominan las consonantes.' if vowels < max(1,n/2) else 'En su alias aparecen bastantes vocales.'),
    ]
    if clean: clues.append(f'La primera letra de su alias es «{clean[0].upper()}».')
    if len(clean)>2: clues.append(f'La última letra de su alias es «{clean[-1].upper()}».')
    return clues[min(max(1,number)-1,len(clues)-1)]

def _cryptic_hint(name:str):
    return _hint_for(name, random.randint(1,4))


def _thread(update):
    m=update.effective_message; return getattr(m,'message_thread_id',None)


def _alive_pool(c, config_id, chat_id):
    # Only people who explicitly joined THIS Assassin game can be selected,
    # receive missions, appear as targets or appear as suspects.
    c.execute("""SELECT p.user_id,p.nombre FROM assassin_players_tb p
      WHERE p.config_id=%s AND NOT EXISTS(
        SELECT 1 FROM assassin_deaths_tb d JOIN assassin_cycles_tb cy ON cy.cycle_id=d.cycle_id
        WHERE cy.config_id=%s AND d.target_id=p.user_id)
      ORDER BY p.joined_at ASC""",(config_id,config_id))
    return c.fetchall()


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
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('🙋 Unirme',callback_data=f'as:join:{cid}'),InlineKeyboardButton('🚪 Salirme',callback_data=f'as:leave:{cid}')],[InlineKeyboardButton('▶️ Empezar juego',callback_data=f'as:auto_start:{cid}'),InlineKeyboardButton('🛑 Cancelar',callback_data=f'as:auto_cancel:{cid}')]])
    state='🟢 Activo' if active else '⚪ Detenido'
    await update.effective_message.reply_text(f'🔪 *JUEGO DEL ASESINO*\n\n{state}\nPrimero regístrense con 🙋 Unirme. Solo quienes se registren participan, reciben mensajes privados y aparecen como objetivos/sospechosos.\n\n🕵️ Después de cada crimen habrá una pista nueva cada 15 minutos.',parse_mode='Markdown',reply_markup=kb)


async def reiniciarasesino(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private': return await update.effective_message.reply_text('🔪 Reinicia el juego desde el grupo.')
    if not ensure_root_identity(update.effective_user): return await update.effective_message.reply_text('🔒 Solo Kiu puede reiniciar este evento.')
    chat=update.effective_chat.id; thread=_thread(update); conn=_get_connection(); cid=None
    try:
        c=conn.cursor(); c.execute("SELECT config_id FROM assassin_auto_tb WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0) LIMIT 1",(chat,thread)); row=c.fetchone()
        if not row:
            conn.rollback(); return await update.effective_message.reply_text('🔪 No hay una partida del Asesino configurada aquí.')
        cid=row[0]
        # Al borrar ciclos, las elecciones, muertes y acusaciones se limpian por CASCADE.
        c.execute("DELETE FROM assassin_cycles_tb WHERE config_id=%s",(cid,))
        c.execute("UPDATE assassin_auto_tb SET active=TRUE,next_cycle_at=NOW() WHERE config_id=%s",(cid,))
        conn.commit()
    except Exception:
        conn.rollback(); return await update.effective_message.reply_text('⚠️ No pude reiniciar el Asesino.')
    finally:_put_connection(conn)
    await update.effective_message.reply_text('🔄 *JUEGO DEL ASESINO REINICIADO*\n\nTodos vuelven a estar vivos. PiBot hará un nuevo sorteo. 😈',parse_mode='Markdown')
    await _run_cycle(context,cid,True)


async def _run_cycle(context,cid,manual=False):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,active FROM assassin_auto_tb WHERE config_id=%s FOR UPDATE",(cid,)); cfg=c.fetchone()
        if not cfg or not cfg[2]: conn.rollback(); return False
        chat,thread,_=cfg
        pool=_alive_pool(c,cid,chat)
        if len(pool)<4:
            c.execute("UPDATE assassin_auto_tb SET next_cycle_at=NOW()+INTERVAL '6 hours' WHERE config_id=%s",(cid,)); conn.commit()
            await context.bot.send_message(chat_id=chat,message_thread_id=thread,text='🔪 Necesito al menos 4 jugadores registrados y vivos. Pulsen 🙋 Unirme en el panel de /asesino.')
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
        c.execute("""SELECT h.cycle_id,h.target_id,h.killer_id,h.hint_no,a.chat_id,a.thread_id,p.nombre
          FROM assassin_hint_state_tb h JOIN assassin_cycles_tb cy ON cy.cycle_id=h.cycle_id
          JOIN assassin_auto_tb a ON a.config_id=cy.config_id
          JOIN assassin_players_tb p ON p.config_id=cy.config_id AND p.user_id=h.killer_id
          WHERE h.active=TRUE AND h.next_hint_at<=NOW()"""); due=c.fetchall()
    finally:_put_connection(conn)
    for cid in ids: await _run_cycle(context,cid)
    for cycle,target,killer,hno,chat,thread,kname in due:
        try:
            await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f'🕵️ PISTA #{hno+1} DEL ASESINO\n\n{_hint_for(kname,hno+1)}\n\n#PistasAsesino')
            conn2=_get_connection()
            try:
                cc=conn2.cursor(); cc.execute("UPDATE assassin_hint_state_tb SET hint_no=hint_no+1,next_hint_at=NOW()+INTERVAL '15 minutes' WHERE cycle_id=%s AND target_id=%s AND active=TRUE",(cycle,target)); conn2.commit()
            finally:_put_connection(conn2)
        except Exception as e: print('[ASESINO PISTA]',e)


async def assassin_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; p=q.data.split(':'); action=p[1] if len(p)>1 else ''
    if action in ('join','leave'):
        cid=int(p[2]); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT chat_id FROM assassin_auto_tb WHERE config_id=%s",(cid,)); cfg=c.fetchone()
            if not cfg: conn.rollback(); return await q.answer('Ese juego ya no existe.',show_alert=True)
            if action=='join':
                name=('@'+q.from_user.username) if q.from_user.username else q.from_user.full_name
                c.execute("INSERT INTO assassin_players_tb(config_id,user_id,nombre) VALUES(%s,%s,%s) ON CONFLICT(config_id,user_id) DO UPDATE SET nombre=EXCLUDED.nombre",(cid,q.from_user.id,name)); conn.commit(); return await q.answer('🔪 Ya estás dentro del juego.',show_alert=True)
            c.execute("DELETE FROM assassin_players_tb WHERE config_id=%s AND user_id=%s",(cid,q.from_user.id)); conn.commit(); return await q.answer('🚪 Saliste del juego del Asesino.',show_alert=True)
        except Exception:
            conn.rollback(); return await q.answer('No pude cambiar tu registro.',show_alert=True)
        finally:_put_connection(conn)

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
            c=conn.cursor(); c.execute("SELECT ac.killer1,ac.killer2,a.chat_id,a.thread_id,ac.config_id FROM assassin_cycles_tb ac JOIN assassin_auto_tb a ON a.config_id=ac.config_id WHERE ac.cycle_id=%s",(cycle,)); row=c.fetchone()
            if not row or killer not in row[:2]: conn.rollback(); return await q.answer('Esta misión no es tuya.',show_alert=True)
            # Un muerto ya no puede matar y una persona muerta no puede volver a ser víctima.
            c.execute("SELECT 1 FROM assassin_deaths_tb d JOIN assassin_cycles_tb cy ON cy.cycle_id=d.cycle_id WHERE cy.config_id=%s AND d.target_id=%s LIMIT 1",(row[4],killer))
            if c.fetchone(): conn.rollback(); return await q.answer('Estás fuera de la partida.',show_alert=True)
            c.execute("SELECT 1 FROM assassin_deaths_tb d JOIN assassin_cycles_tb cy ON cy.cycle_id=d.cycle_id WHERE cy.config_id=%s AND d.target_id=%s LIMIT 1",(row[4],target))
            if c.fetchone(): conn.rollback(); return await q.answer('Esa persona ya está fuera de la partida.',show_alert=True)
            c.execute("INSERT INTO assassin_choices_tb(cycle_id,killer_id,target_id) VALUES(%s,%s,%s) ON CONFLICT(cycle_id,killer_id) DO NOTHING",(cycle,killer,target))
            if c.rowcount!=1: conn.rollback(); return await q.answer('Ya elegiste una víctima en este ciclo.',show_alert=True)
            c.execute("INSERT INTO assassin_deaths_tb(cycle_id,target_id,killer_id) VALUES(%s,%s,%s)",(cycle,target,killer))
            c.execute("INSERT INTO assassin_hint_state_tb(cycle_id,target_id,killer_id,hint_no,next_hint_at) VALUES(%s,%s,%s,1,NOW()+INTERVAL '15 minutes') ON CONFLICT(cycle_id,target_id) DO NOTHING",(cycle,target,killer))
            c.execute("SELECT nombre FROM assassin_players_tb WHERE config_id=%s AND user_id=%s",(row[4],target)); rr=c.fetchone(); name=rr[0] if rr else str(target); conn.commit(); chat,thread=row[2],row[3]
        except Exception: conn.rollback(); return await q.answer('No pude registrar la víctima.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Víctima elegida. 😈',show_alert=True); await q.edit_message_text(f'🔪 Misión completada. Elegiste a {name}.')
        guess_kb=InlineKeyboardMarkup([[InlineKeyboardButton('🕵️ Ya sé quién es el asesino',callback_data=f'as:guess_start:{cycle}:{target}')]])
        await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f'☠️ *{name} ha sido víctima del Asesino.*\n¿Quién habrá sido? 👀',parse_mode='Markdown',reply_markup=guess_kb)
        conn2=_get_connection()
        try:
            cc=conn2.cursor(); cc.execute("SELECT nombre FROM assassin_players_tb WHERE config_id=%s AND user_id=%s",(row[4],killer)); kr=cc.fetchone(); kname=kr[0] if kr else str(killer)
        finally:_put_connection(conn2)
        await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=f'🕵️ PISTA #1 DEL ASESINO\n\n{_hint_for(kname,1)}\n\n⏳ Nueva pista en 15 minutos.\n\n#PistasAsesino')
        return

    if action=='guess_start':
        cycle=int(p[2]); victim=int(p[3]); guesser=q.from_user.id; conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("""SELECT a.chat_id,a.thread_id,cy.config_id,d.killer_id
              FROM assassin_deaths_tb d JOIN assassin_cycles_tb cy ON cy.cycle_id=d.cycle_id
              JOIN assassin_auto_tb a ON a.config_id=cy.config_id
              WHERE d.cycle_id=%s AND d.target_id=%s""",(cycle,victim)); row=c.fetchone()
            if not row: conn.rollback(); return await q.answer('Esta acusación ya no está disponible.',show_alert=True)
            chat,thread,cid,_=row
            c.execute("SELECT 1 FROM assassin_players_tb WHERE config_id=%s AND user_id=%s",(cid,guesser))
            if not c.fetchone(): conn.rollback(); return await q.answer('🔪 Solo los jugadores registrados pueden acusar.',show_alert=True)
            c.execute("SELECT 1 FROM assassin_deaths_tb d JOIN assassin_cycles_tb cy ON cy.cycle_id=d.cycle_id WHERE cy.config_id=%s AND d.target_id=%s LIMIT 1",(cid,guesser))
            if c.fetchone(): conn.rollback(); return await q.answer('☠️ Los muertos ya no pueden participar.',show_alert=True)
            c.execute("SELECT 1 FROM assassin_guesses_tb WHERE cycle_id=%s AND target_id=%s AND guesser_id=%s",(cycle,victim,guesser))
            if c.fetchone(): conn.rollback(); return await q.answer('Ya hiciste tu acusación para esta víctima.',show_alert=True)
            c.execute("SELECT user_id,nombre FROM assassin_players_tb WHERE config_id=%s AND user_id<>%s ORDER BY joined_at ASC",(cid,victim)); suspects=c.fetchall()
            conn.rollback()
        except Exception: conn.rollback(); return await q.answer('No pude abrir las sospechas.',show_alert=True)
        finally:_put_connection(conn)
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(f'🔎 {name[:32]}',callback_data=f'as:guess_pick:{cycle}:{victim}:{uid}')] for uid,name in suspects[:40]])
        try:
            await context.bot.send_message(chat_id=guesser,text='🕵️ *ACUSACIÓN SECRETA*\n\n¿Quién crees que cometió este asesinato?\nTienes una sola acusación para esta víctima.',parse_mode='Markdown',reply_markup=kb)
        except Exception:
            return await q.answer('Abre primero el privado con PiBot y vuelve a pulsar el botón.',show_alert=True)
        await q.answer('Te mandé los sospechosos por privado. 👀',show_alert=True)
        return

    if action=='guess_pick':
        cycle=int(p[2]); victim=int(p[3]); suspect=int(p[4]); guesser=q.from_user.id; conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("""SELECT a.chat_id,a.thread_id,cy.config_id,d.killer_id
              FROM assassin_deaths_tb d JOIN assassin_cycles_tb cy ON cy.cycle_id=d.cycle_id
              JOIN assassin_auto_tb a ON a.config_id=cy.config_id
              WHERE d.cycle_id=%s AND d.target_id=%s""",(cycle,victim)); row=c.fetchone()
            if not row: conn.rollback(); return await q.answer('Esta acusación ya no está disponible.',show_alert=True)
            chat,thread,cid,killer=row
            c.execute("SELECT 1 FROM assassin_deaths_tb d JOIN assassin_cycles_tb cy ON cy.cycle_id=d.cycle_id WHERE cy.config_id=%s AND d.target_id=%s LIMIT 1",(cid,guesser))
            if c.fetchone(): conn.rollback(); return await q.answer('☠️ Los muertos ya no pueden participar.',show_alert=True)
            correct=(suspect==killer)
            c.execute("INSERT INTO assassin_guesses_tb(cycle_id,target_id,guesser_id,suspect_id,correct) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(cycle_id,target_id,guesser_id) DO NOTHING",(cycle,victim,guesser,suspect,correct))
            if c.rowcount!=1: conn.rollback(); return await q.answer('Ya usaste tu acusación para esta víctima.',show_alert=True)
            c.execute("SELECT nombre FROM assassin_players_tb WHERE config_id=%s AND user_id=%s",(cid,guesser)); gr=c.fetchone(); gname=gr[0] if gr else q.from_user.full_name
            c.execute("SELECT nombre FROM assassin_players_tb WHERE config_id=%s AND user_id=%s",(cid,killer)); kr=c.fetchone(); kname=kr[0] if kr else str(killer)
            if correct:
                c.execute("UPDATE assassin_hint_state_tb SET active=FALSE WHERE cycle_id=%s AND target_id=%s",(cycle,victim))
                c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(DETECTIVE_REWARD,guesser))
            conn.commit()
        except Exception: conn.rollback(); return await q.answer('No pude registrar tu acusación.',show_alert=True)
        finally:_put_connection(conn)
        if not correct:
            await q.answer('❌ No era esa persona. Tu acusación ya fue usada.',show_alert=True)
            await q.edit_message_text('❌ Acusación fallida. Esa persona no fue quien cometió este asesinato. 👀')
            return
        await q.answer('🏆 ¡Lo descubriste!',show_alert=True)
        await q.edit_message_text(f'🏆 ¡Acertaste! El asesino era {kname}.\n🪙 +{DETECTIVE_REWARD:,} PiPesos.')
        victory=random.choice([
            f'🕵️‍♂️ *¡ASESINO DESCUBIERTO!*\n\n{gname} siguió las pistas, sospechó de medio grupo y finalmente desenmascaró a *{kname}*. 😂🔪\n\n🏆 Caso resuelto.',
            f'🚨 *¡LO ATRAPARON!*\n\n{gname} señaló a *{kname}*… ¡y tenía razón! 🔪😂\n\n🕵️ La investigación dio resultado.',
            f'🏆 *DETECTIVE DEL GRUPO*\n\n{gname} acaba de descubrir que *{kname}* era el asesino. 👀🔪\n\nNi las pistas pudieron salvarlo esta vez. 😂'
        ])
        await context.bot.send_message(chat_id=chat,message_thread_id=thread,text=victory,parse_mode='Markdown')
        return
