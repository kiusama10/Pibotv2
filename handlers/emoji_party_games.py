"""Juegos sociales con emojis animados de Telegram.
Aislado del resto de PiBot: Dardos, Boliche y Aliados Traicioneros.
"""
import asyncio, uuid
from collections import Counter
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import quitar_puntos, dar_puntos, normalizar_nombre, _get_connection, _put_connection
from handlers.pipeso_extras import send_victory


def _ensure_stats():
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""CREATE TABLE IF NOT EXISTS emoji_game_stats_tb(user_id BIGINT NOT NULL,game_type TEXT NOT NULL,plays INT NOT NULL DEFAULT 0,wins INT NOT NULL DEFAULT 0,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(user_id,game_type))"""); conn.commit()
    except Exception: conn.rollback()
    finally:_put_connection(conn)

def _record_finished(g,winner):
    _ensure_stats(); conn=_get_connection()
    try:
        c=conn.cursor()
        for uid in g['players']:
            c.execute("""INSERT INTO emoji_game_stats_tb(user_id,game_type,plays,wins) VALUES(%s,%s,1,%s) ON CONFLICT(user_id,game_type) DO UPDATE SET plays=emoji_game_stats_tb.plays+1,wins=emoji_game_stats_tb.wins+EXCLUDED.wins,updated_at=NOW()""",(uid,g['type'],1 if uid==winner else 0))
        conn.commit()
    except Exception: conn.rollback()
    finally:_put_connection(conn)

_GAMES = {}  # (chat_id, thread_id) -> state
_LOCKS = {}

def _key(update):
    m=update.effective_message
    return (update.effective_chat.id, getattr(m,'message_thread_id',None))
def _lock(key): return _LOCKS.setdefault(key, asyncio.Lock())
def _name(u): return u.username or normalizar_nombre(u.first_name,u.last_name) or str(u.id)
def _money(n): return f"{int(n):,}"

def _lobby_kb(g):
    gid=g['id']
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('➕ Unirme',callback_data=f'eg:join:{gid}'), InlineKeyboardButton('▶️ Empezar',callback_data=f'eg:start:{gid}')],
        [InlineKeyboardButton('❌ Cancelar juego',callback_data=f'eg:cancel:{gid}')]
    ])

def _lobby_text(g):
    names='\n'.join(f"• {p['name']}" for p in g['players'].values())
    title={'dardos':'🎯 DARDOS','boliche':'🎳 BOLICHE','aliados':'🤝💀 ALIADOS TRAICIONEROS'}[g['type']]
    return f"{title}\n\n💰 Apuesta: {_money(g['stake'])} PiPesos por jugador\n🏦 Pozo actual: {_money(g['stake']*len(g['players']))}\n\n👥 Jugadores:\n{names}\n\n🔓 Partida abierta: cualquiera puede entrar hasta que el creador pulse Empezar."

async def _create(update,context,kind):
    if update.effective_chat.type=='private': return await update.effective_message.reply_text('🎮 Este juego se juega en el grupo.')
    try: stake=int(str(context.args[0]).replace(',',''))
    except Exception: return await update.effective_message.reply_text(f"Uso: /{kind} <apuesta>\nEjemplo: /{kind} 2000")
    if stake<=0: return await update.effective_message.reply_text('💰 La apuesta debe ser mayor que 0.')
    key=_key(update); u=update.effective_user
    async with _lock(key):
        if key in _GAMES: return await update.effective_message.reply_text('⚠️ Ya hay uno de estos juegos abierto en este tema. Termínalo o cancélalo primero.')
        if not quitar_puntos(u.id,stake): return await update.effective_message.reply_text('💸 No tienes suficientes PiPesos para abrir esa apuesta.')
        g={'id':uuid.uuid4().hex[:10],'type':kind,'chat':key[0],'thread':key[1],'owner':u.id,'stake':stake,'status':'lobby','players':{u.id:{'name':_name(u),'score':0,'throws':0,'lives':3}},'turn_order':[],'turn':0,'round':1,'eligible':None,'shooter':None,'votes':{},'message_id':None,'busy':set()}
        _GAMES[key]=g
    msg=await update.effective_message.reply_text(_lobby_text(g),reply_markup=_lobby_kb(g)); g['message_id']=msg.message_id

async def dardos(update,context): await _create(update,context,'dardos')
async def boliche(update,context): await _create(update,context,'boliche')
async def aliados(update,context): await _create(update,context,'aliados')

async def cancelar_emoji_juego(update,context):
    key=_key(update); g=_GAMES.get(key)
    if not g: return await update.effective_message.reply_text('⚠️ No hay un juego de Dardos, Boliche o Aliados activo aquí.')
    if update.effective_user.id!=g['owner']: return await update.effective_message.reply_text('⚠️ Solo quien abrió el juego puede cancelarlo.')
    await _cancel(context,key,g,'❌ Juego cancelado por su creador. Todos los PiPesos reservados fueron devueltos.')

async def _cancel(context,key,g,text):
    if g.get('status')=='finished': return
    g['status']='finished'
    for uid in g['players']: dar_puntos(uid,g['stake'])
    _GAMES.pop(key,None)
    await context.bot.send_message(chat_id=g['chat'],message_thread_id=g['thread'],text=text)

async def _finish(context,key,g,winner):
    _record_finished(g,winner)
    g['status']='finished'; pot=g['stake']*len(g['players']); dar_puntos(winner,pot)
    name=g['players'][winner]['name']; _GAMES.pop(key,None)
    await context.bot.send_message(chat_id=g['chat'],message_thread_id=g['thread'],text=f"👑 {name} gana la partida.\n💰 Premio: {_money(pot)} PiPesos")
    try: await send_victory(context,winner,g['type'],g['chat'],g['thread'],name)
    except Exception: pass

async def emoji_game_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; parts=q.data.split(':'); action=parts[1]; gid=parts[2]
    key=(q.message.chat.id,getattr(q.message,'message_thread_id',None)); g=_GAMES.get(key)
    if not g or g['id']!=gid: return await q.answer('Esta partida ya terminó.',show_alert=True)
    uid=q.from_user.id
    if action=='join':
        async with _lock(key):
            if g['status']!='lobby': return await q.answer('La partida ya comenzó.',show_alert=True)
            if uid in g['players']: return await q.answer('Ya estás dentro. 😈',show_alert=True)
            if not quitar_puntos(uid,g['stake']): return await q.answer('No tienes suficientes PiPesos.',show_alert=True)
            g['players'][uid]={'name':_name(q.from_user),'score':0,'throws':0,'lives':3}
        await q.answer('Entraste a la partida.'); return await q.edit_message_text(_lobby_text(g),reply_markup=_lobby_kb(g))
    if action=='cancel':
        if uid!=g['owner']: return await q.answer('Solo quien abrió el juego puede cancelarlo.',show_alert=True)
        await q.answer(); return await _cancel(context,key,g,'❌ Juego cancelado. Todos recuperaron su apuesta.')
    if action=='start':
        if uid!=g['owner']: return await q.answer('Solo quien abrió el juego puede iniciarlo.',show_alert=True)
        if len(g['players'])<2: return await q.answer('Necesitas al menos 2 jugadores.',show_alert=True)
        g['status']='playing'; g['turn_order']=list(g['players']); g['turn']=0
        await q.answer();
        if g['type'] in ('dardos','boliche'): return await _show_skill_turn(context,g)
        return await _show_allies_round(context,g)
    if action=='throw': return await _skill_throw(q,context,key,g)
    if action=='roll': return await _allies_roll(q,context,key,g)
    if action=='shoot': return await _shoot(q,context,key,g,int(parts[3]))
    if action=='vote': return await _vote(q,context,key,g,int(parts[3]))

async def _show_skill_turn(context,g):
    uid=g['turn_order'][g['turn']]; p=g['players'][uid]; emoji='🎯' if g['type']=='dardos' else '🎳'; label='Lanzar dardo' if g['type']=='dardos' else 'Lanzar bola'
    await context.bot.send_message(chat_id=g['chat'],message_thread_id=g['thread'],text=f"{emoji} Turno de {p['name']} · tiro {p['throws']+1}/3",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f'{emoji} {label}',callback_data=f"eg:throw:{g['id']}")],[InlineKeyboardButton('❌ Cancelar juego',callback_data=f"eg:cancel:{g['id']}")]]))

async def _skill_throw(q,context,key,g):
    uid=q.from_user.id; expected=g['turn_order'][g['turn']]
    if uid!=expected: return await q.answer('Todavía no es tu turno.',show_alert=True)
    if uid in g['busy']: return await q.answer('Tu lanzamiento ya está en curso.',show_alert=True)
    g['busy'].add(uid)
    await q.answer(); emoji='🎯' if g['type']=='dardos' else '🎳'
    dice=await context.bot.send_dice(chat_id=g['chat'],message_thread_id=g['thread'],emoji=emoji)
    value=dice.dice.value; g['players'][uid]['score']+=value; g['players'][uid]['throws']+=1
    await asyncio.sleep(4); g['busy'].discard(uid)
    extra=' 🎯 ¡DIANA!' if emoji=='🎯' and value==6 else (' 🎳 ¡STRIKE!' if emoji=='🎳' and value==6 else '')
    await context.bot.send_message(chat_id=g['chat'],message_thread_id=g['thread'],text=f"{g['players'][uid]['name']}: +{value} puntos{extra}\n📊 Total: {g['players'][uid]['score']}")
    if g['players'][uid]['throws']>=3: g['turn']+=1
    if g['turn']<len(g['turn_order']): return await _show_skill_turn(context,g)
    contenders=list(g['turn_order']); top=max(g['players'][u]['score'] for u in contenders); tied=[u for u in contenders if g['players'][u]['score']==top]
    if len(tied)==1: return await _finish(context,key,g,tied[0])
    # desempate súbito: un lanzamiento por empatado
    for u in tied: g['players'][u]['throws']=2; g['players'][u]['score']=0
    g['turn_order']=tied; g['turn']=0
    await context.bot.send_message(chat_id=g['chat'],message_thread_id=g['thread'],text='🔥 ¡EMPATE! Solo los empatados tiran una vez en muerte súbita.')
    await _show_skill_turn(context,g)

async def _show_allies_round(context,g):
    alive=[u for u,p in g['players'].items() if p['lives']>0]
    g['eligible']=set(alive); g['rolls']={}; g['shooter']=None
    lives='\n'.join(f"❤️ x{g['players'][u]['lives']} · {g['players'][u]['name']}" for u in alive)
    await context.bot.send_message(chat_id=g['chat'],message_thread_id=g['thread'],text=f"🤝💀 ALIADOS TRAICIONEROS · RONDA {g['round']}\n\n{lives}\n\n🎲 Todos los supervivientes deben tirar. El número más alto será el Tirador Supremo.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🎲 Tirar dado',callback_data=f"eg:roll:{g['id']}")],[InlineKeyboardButton('❌ Cancelar juego',callback_data=f"eg:cancel:{g['id']}")]]))

async def _allies_roll(q,context,key,g):
    uid=q.from_user.id
    if g['status']!='playing' or uid not in (g.get('eligible') or set()): return await q.answer('No te toca tirar en esta ronda.',show_alert=True)
    if uid in g.get('rolls',{}) or uid in g['busy']: return await q.answer('Ya tiraste o tu dado sigue en curso.',show_alert=True)
    g['busy'].add(uid)
    await q.answer(); d=await context.bot.send_dice(chat_id=g['chat'],message_thread_id=g['thread'],emoji='🎲'); g['rolls'][uid]=d.dice.value
    await asyncio.sleep(4); g['busy'].discard(uid); await context.bot.send_message(chat_id=g['chat'],message_thread_id=g['thread'],text=f"🎲 {g['players'][uid]['name']} sacó {d.dice.value}.")
    if set(g['rolls']) != set(g['eligible']): return
    high=max(g['rolls'].values()); tied={u for u,v in g['rolls'].items() if v==high}
    if len(tied)>1:
        g['eligible']=tied; g['rolls']={}
        names=', '.join(g['players'][u]['name'] for u in tied)
        return await context.bot.send_message(chat_id=g['chat'],message_thread_id=g['thread'],text=f"🎲🔁 Empate entre {names}. SOLO ellos vuelven a tirar.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🎲 Desempatar',callback_data=f"eg:roll:{g['id']}")],[InlineKeyboardButton('❌ Cancelar juego',callback_data=f"eg:cancel:{g['id']}")]]))
    shooter=next(iter(tied)); g['shooter']=shooter
    rows=[]
    for target,p in g['players'].items():
        if p['lives']>0: rows.append([InlineKeyboardButton(f"🔫 {p['name']} · ❤️{p['lives']}",callback_data=f"eg:shoot:{g['id']}:{target}")])
    rows.append([InlineKeyboardButton('❌ Cancelar juego',callback_data=f"eg:cancel:{g['id']}")])
    await context.bot.send_message(chat_id=g['chat'],message_thread_id=g['thread'],text=f"🔫😈 {g['players'][shooter]['name']} es EL TIRADOR SUPREMO.\nTiene 1 minuto para elegir a quién quitarle una vida. Puede dispararse incluso a sí mismo.",reply_markup=InlineKeyboardMarkup(rows))
    token=(g['round'],shooter)
    asyncio.create_task(_shoot_timeout(context,key,g,token))

async def _shoot(q,context,key,g,target):
    if q.from_user.id!=g.get('shooter'): return await q.answer('Solo el Tirador Supremo decide ahora.',show_alert=True)
    if target not in g['players'] or g['players'][target]['lives']<=0: return await q.answer('Ese jugador ya no está disponible.',show_alert=True)
    await q.answer('💥 Disparo realizado.'); await _apply_hit(context,key,g,target)

async def _apply_hit(context,key,g,target):
    g['players'][target]['lives']-=1; victim=g['players'][target]
    dead=victim['lives']<=0
    status = "💀 ELIMINADO. El grupo puede ponerle su mini castigo. 😈" if dead else f"❤️ Le quedan {victim['lives']} vidas."
    await context.bot.send_message(chat_id=g['chat'],message_thread_id=g['thread'],text=f"💥🔫 {victim['name']} pierde 1 vida.\n{status}")
    alive=[u for u,p in g['players'].items() if p['lives']>0]
    if len(alive)==1:
        await context.bot.send_message(chat_id=g['chat'],message_thread_id=g['thread'],text=f"👑🔥 {g['players'][alive[0]]['name']} se convierte en EL EMPERADOR DE LA TRAICIÓN.\nPuede imponer un mini castigo consensuado a cualquier jugador. 😈")
        return await _finish(context,key,g,alive[0])
    g['round']+=1; await _show_allies_round(context,g)

async def _shoot_timeout(context,key,g,token):
    await asyncio.sleep(60)
    if _GAMES.get(key) is not g or g['status']!='playing' or token!=(g['round'],g.get('shooter')): return
    alive=[u for u,p in g['players'].items() if p['lives']>0]; g['votes']={}; g['vote_round']=g['round']
    rows=[[InlineKeyboardButton(f"💀 {g['players'][u]['name']}",callback_data=f"eg:vote:{g['id']}:{u}")] for u in alive]
    rows.append([InlineKeyboardButton('❌ Cancelar juego',callback_data=f"eg:cancel:{g['id']}")])
    await context.bot.send_message(chat_id=g['chat'],message_thread_id=g['thread'],text='⏳ El Tirador no decidió en 1 minuto.\n💀 Ahora EL GRUPO elige la víctima. Tienen 30 segundos; el Tirador también puede terminar siendo elegido.',reply_markup=InlineKeyboardMarkup(rows))
    asyncio.create_task(_vote_timeout(context,key,g,g['round']))

async def _vote(q,context,key,g,target):
    uid=q.from_user.id
    if g.get('vote_round')!=g['round']: return await q.answer('La votación ya terminó.',show_alert=True)
    if uid not in g['players'] or g['players'][uid]['lives']<=0: return await q.answer('Solo los jugadores vivos pueden votar.',show_alert=True)
    g['votes'][uid]=target; await q.answer('Voto registrado. 💀')

async def _vote_timeout(context,key,g,round_no):
    await asyncio.sleep(30)
    if _GAMES.get(key) is not g or g.get('vote_round')!=round_no: return
    g['vote_round']=None
    alive=[u for u,p in g['players'].items() if p['lives']>0]
    if g['votes']:
        counts=Counter(g['votes'].values()); mx=max(counts.values()); candidates=[u for u,n in counts.items() if n==mx and u in alive]
    else: candidates=[]
    if len(candidates)!=1:
        # Sin mayoría única: el tirador paga su indecisión, tal como permite la regla "puede ser él".
        target=g.get('shooter') if g.get('shooter') in alive else alive[0]
        await context.bot.send_message(chat_id=g['chat'],message_thread_id=g['thread'],text='💀 No hubo una mayoría única. La indecisión se vuelve contra el Tirador Supremo.')
    else: target=candidates[0]
    await _apply_hit(context,key,g,target)
