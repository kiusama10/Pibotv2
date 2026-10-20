from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database.database import _get_connection, _put_connection, is_botmaster
from handlers.pokemon_gen1_data import (
    NAMES, TYPES, MOVES, ITEMS, LEVEL_EVOLUTIONS, STONE_EVOLUTIONS,
    TRADE_EVOLUTIONS, LEGENDARY_IDS, EPIC_IDS, RARE_IDS, PHYSICAL_TYPES,
    available_moves, battle_base_stats, effectiveness, rarity_for,
    rarity_emoji, type_emoji,
)

PAGE_SIZE = 8
MAX_LEVEL = 100
WIN_PIPESOS = 1000
LOSS_PIPESOS = 300
WIN_SEASON_XP = 25
LOSS_SEASON_XP = 10
WIN_POKEMON_XP = 60
LOSS_POKEMON_XP = 30


def ensure_pokemon_tables():
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_instances_tb(
              pokemon_id BIGSERIAL PRIMARY KEY,
              owner_id BIGINT NOT NULL,
              species_id SMALLINT NOT NULL CHECK(species_id BETWEEN 1 AND 151),
              nickname TEXT,
              level SMALLINT NOT NULL DEFAULT 5 CHECK(level BETWEEN 1 AND 100),
              xp BIGINT NOT NULL DEFAULT 0,
              moves_json TEXT NOT NULL DEFAULT '[]',
              media_type TEXT,
              media_file_id TEXT,
              wins INT NOT NULL DEFAULT 0,
              losses INT NOT NULL DEFAULT 0,
              obtained_from TEXT NOT NULL DEFAULT 'caja',
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_owner ON pokemon_instances_tb(owner_id,pokemon_id)")
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS shiny BOOLEAN NOT NULL DEFAULT FALSE")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_species ON pokemon_instances_tb(owner_id,species_id)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_team_tb(
              owner_id BIGINT PRIMARY KEY,
              slot1 BIGINT,
              slot2 BIGINT,
              slot3 BIGINT,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_pokedex_tb(
              owner_id BIGINT NOT NULL,
              species_id SMALLINT NOT NULL,
              obtained_count INT NOT NULL DEFAULT 1,
              first_obtained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              last_obtained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY(owner_id,species_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_items_tb(
              owner_id BIGINT NOT NULL,
              item_code TEXT NOT NULL,
              qty INT NOT NULL DEFAULT 0,
              PRIMARY KEY(owner_id,item_code)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_rank_tb(
              user_id BIGINT PRIMARY KEY,
              rating INT NOT NULL DEFAULT 1000,
              wins INT NOT NULL DEFAULT 0,
              losses INT NOT NULL DEFAULT 0,
              current_streak INT NOT NULL DEFAULT 0,
              best_streak INT NOT NULL DEFAULT 0,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_battles_tb(
              battle_id BIGSERIAL PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT,
              challenger_id BIGINT NOT NULL,
              opponent_id BIGINT,
              mode SMALLINT,
              status TEXT NOT NULL DEFAULT 'open',
              state_json TEXT,
              message_id BIGINT,
              winner_id BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_battle_status ON pokemon_battles_tb(status,challenger_id,opponent_id)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_trades_tb(
              trade_id BIGSERIAL PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT,
              user_a BIGINT NOT NULL,
              user_b BIGINT NOT NULL,
              pokemon_a BIGINT,
              pokemon_b BIGINT,
              confirm_a BOOLEAN NOT NULL DEFAULT FALSE,
              confirm_b BOOLEAN NOT NULL DEFAULT FALSE,
              status TEXT NOT NULL DEFAULT 'selecting',
              message_id BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_trade_users ON pokemon_trades_tb(status,user_a,user_b)")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print('[POKEMON tables]', type(e).__name__, e)
        raise
    finally:
        _put_connection(conn)


def _xp_floor(level:int)->int:
    # Curva compacta para Telegram; mantiene el progreso entre combates.
    return 25 * max(0, level - 1) ** 2


def _starting_level(species_id:int)->int:
    r = rarity_for(species_id)
    return {"comun":5, "raro":10, "epico":18, "legendario":25}[r]


def _display_name_cursor(c, uid:int)->str:
    c.execute("SELECT COALESCE(NULLIF(nombre,''),NULLIF(username,''),%s) FROM perfiles_tb WHERE id_user=%s", (f'Jugador {uid}', uid))
    r = c.fetchone()
    return str(r[0]) if r and r[0] else f'Jugador {uid}'


def _pokemon_label(row)->str:
    # row: id, species, nickname, level, ...
    pid, species, nickname, level = int(row[0]), int(row[1]), row[2], int(row[3])
    base = NAMES.get(species, f'#{species}')
    shown = f'{nickname} ({base})' if nickname else base
    shiny = bool(row[10]) if len(row) > 10 else False
    return f"#{pid} · {'✨ ' if shiny else ''}{shown} · Nv.{level}"


def _types_text(species_id:int)->str:
    return ' / '.join(f'{type_emoji(t)} {t}' for t in TYPES.get(species_id, ('Normal',)))


def _ensure_team_row_cursor(c, uid:int):
    c.execute("INSERT INTO pokemon_team_tb(owner_id) VALUES(%s) ON CONFLICT DO NOTHING", (uid,))


def grant_pokemon_with_cursor(c, uid:int, species_id:int, source:str='caja', force_shiny:bool=False)->dict:
    species_id = max(1, min(151, int(species_id)))
    level = _starting_level(species_id)
    moves = available_moves(species_id, level)
    # Shiny es puramente cosmético y MUY raro: 1 entre 4096.
    shiny = bool(force_shiny or random.randrange(4096) == 0)
    c.execute("""
        INSERT INTO pokemon_instances_tb(owner_id,species_id,level,xp,moves_json,obtained_from,shiny)
        VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING pokemon_id
    """, (uid, species_id, level, _xp_floor(level), json.dumps(moves, ensure_ascii=False), source, shiny))
    pid = int(c.fetchone()[0])
    c.execute("""
        INSERT INTO pokemon_pokedex_tb(owner_id,species_id,obtained_count)
        VALUES(%s,%s,1)
        ON CONFLICT(owner_id,species_id) DO UPDATE SET
          obtained_count=pokemon_pokedex_tb.obtained_count+1,last_obtained_at=NOW()
    """, (uid, species_id))
    _ensure_team_row_cursor(c, uid)
    # Los primeros tres Pokémon se acomodan solos; después el equipo se gestiona por privado.
    c.execute("SELECT slot1,slot2,slot3 FROM pokemon_team_tb WHERE owner_id=%s FOR UPDATE", (uid,))
    team = list(c.fetchone() or (None,None,None))
    if pid not in team:
        for i in range(3):
            if team[i] is None:
                team[i] = pid
                c.execute(f"UPDATE pokemon_team_tb SET slot{i+1}=%s,updated_at=NOW() WHERE owner_id=%s", (pid,uid))
                break
    return {
        'pokemon_id': pid, 'species_id': species_id, 'name': NAMES[species_id],
        'level': level, 'rarity': rarity_for(species_id), 'moves': moves, 'shiny': shiny,
    }


def grant_item_with_cursor(c, uid:int, item_code:str, qty:int=1):
    if item_code not in ITEMS:
        return False
    c.execute("""
        INSERT INTO pokemon_items_tb(owner_id,item_code,qty) VALUES(%s,%s,%s)
        ON CONFLICT(owner_id,item_code) DO UPDATE SET qty=pokemon_items_tb.qty+EXCLUDED.qty
    """, (uid,item_code,max(1,int(qty))))
    return True


def roll_box_pokemon(box_code:str)->int:
    # La Legendaria tiene mejor acceso a épicos/legendarios, pero los legendarios
    # siguen siendo realmente raros incluso dentro de una tirada Pokémon.
    all_ids = list(range(1,152))
    pools = {
        'comun':[i for i in all_ids if rarity_for(i)=='comun'],
        'raro':[i for i in all_ids if rarity_for(i)=='raro'],
        'epico':[i for i in all_ids if rarity_for(i)=='epico'],
        'legendario':[i for i in all_ids if rarity_for(i)=='legendario'],
    }
    if box_code == 'legendary':
        r = random.choices(['comun','raro','epico','legendario'], [38,35,24,3], k=1)[0]
    else:
        r = random.choices(['comun','raro','epico','legendario'], [58,32,9.5,0.5], k=1)[0]
    return random.choice(pools[r])


def roll_box_item(box_code:str)->str:
    if box_code == 'legendary':
        return random.choices(
            ['super_potion','hyper_potion','full_restore','revive','fire_stone','water_stone','thunder_stone','leaf_stone','moon_stone','link_cable','rare_candy'],
            [17,15,6,15,8,8,8,8,8,4,3], k=1
        )[0]
    return random.choices(
        ['potion','super_potion','revive','fire_stone','water_stone','thunder_stone','leaf_stone','moon_stone','link_cable','rare_candy'],
        [34,21,14,6,6,6,5,5,1,2], k=1
    )[0]


def _get_owned(uid:int, limit:int=200):
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny
                     FROM pokemon_instances_tb WHERE owner_id=%s ORDER BY pokemon_id LIMIT %s""", (uid,limit))
        return c.fetchall()
    finally:
        _put_connection(conn)


def _get_instance(uid:int, pid:int):
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny
                     FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s""", (uid,pid))
        return c.fetchone()
    finally:
        _put_connection(conn)


def _collection_markup(uid:int, page:int=0, prefix:str='detail'):
    mons = _get_owned(uid)
    pages = max(1, math.ceil(len(mons)/PAGE_SIZE))
    page = max(0,min(page,pages-1))
    chunk = mons[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
    rows=[]
    for r in chunk:
        name = (r[2] or NAMES[int(r[1])])[:22]
        rows.append([InlineKeyboardButton(f"{rarity_emoji(rarity_for(int(r[1])))} {name} · Nv.{r[3]}", callback_data=f'pk:{prefix}:{r[0]}:{page}')])
    nav=[]
    if page>0: nav.append(InlineKeyboardButton('⬅️',callback_data=f'pk:list:{page-1}'))
    nav.append(InlineKeyboardButton(f'{page+1}/{pages}',callback_data='pk:noop'))
    if page<pages-1: nav.append(InlineKeyboardButton('➡️',callback_data=f'pk:list:{page+1}'))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton('👥 Mi equipo',callback_data='pk:team'),InlineKeyboardButton('🎒 Objetos',callback_data='pk:items')])
    return InlineKeyboardMarkup(rows)


async def _send_collection_private(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    mons=_get_owned(uid)
    text=(f"🎮 TUS POKÉMON · {len(mons)} ejemplares\n\n"
          "Tu colección y tu equipo son privados. Toca uno para verlo, ponerle apodo, foto/GIF o meterlo al equipo.")
    try:
        await context.bot.send_message(uid,text,reply_markup=_collection_markup(uid,0))
    except Exception:
        return False
    return True


async def pokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    ok=await _send_collection_private(update,context)
    if update.effective_chat.type!='private':
        await update.effective_message.reply_text('📩 Te mandé tu colección Pokémon por privado.' if ok else '📩 Abre primero el privado de PiBot con /start.')


async def pokedex_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT species_id,obtained_count FROM pokemon_pokedex_tb WHERE owner_id=%s ORDER BY species_id",(uid,)); rows=c.fetchall()
    finally:_put_connection(conn)
    got={int(a):int(b) for a,b in rows}
    lines=[f"📖 POKÉDEX DE KANTO · {len(got)}/151",""]
    for start in range(1,152,25):
        end=min(151,start+24); count=sum(1 for i in range(start,end+1) if i in got)
        lines.append(f"#{start:03d}-#{end:03d}: {count}/{end-start+1}")
    lines += ["", "Usa /pokemon para ver tus ejemplares. Puedes tener más de uno de la misma especie."]
    try: await context.bot.send_message(uid,'\n'.join(lines))
    except Exception:
        return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private': await update.effective_message.reply_text('📩 Te mandé tu Pokédex por privado.')


def _team_rows(uid:int):
    conn=_get_connection()
    try:
        c=conn.cursor(); _ensure_team_row_cursor(c,uid)
        c.execute("SELECT slot1,slot2,slot3 FROM pokemon_team_tb WHERE owner_id=%s",(uid,)); team=c.fetchone() or (None,None,None)
        out=[]
        for pid in team:
            if pid is None: out.append(None); continue
            c.execute("SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); out.append(c.fetchone())
        conn.commit(); return out
    except Exception:
        conn.rollback(); return [None,None,None]
    finally:_put_connection(conn)


def _team_text(uid:int)->str:
    rows=_team_rows(uid); lines=['👥 EQUIPO POKÉMON · PRIVADO','']
    for i,r in enumerate(rows,1):
        lines.append(f'{i}. {_pokemon_label(r) if r else "— Vacío —"}')
    lines += ['', 'Máximo 3. En batalla 1v1 usa el primero; 2v2 los dos primeros; 3v3 los tres.']
    return '\n'.join(lines)


def _team_markup(uid:int):
    rows=[]
    for i in range(1,4): rows.append([InlineKeyboardButton(f'🔄 Cambiar espacio {i}',callback_data=f'pk:teamslot:{i}:0')])
    rows.append([InlineKeyboardButton('🎮 Volver a colección',callback_data='pk:list:0')])
    return InlineKeyboardMarkup(rows)


async def equipo_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    try: await context.bot.send_message(uid,_team_text(uid),reply_markup=_team_markup(uid))
    except Exception: return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private': await update.effective_message.reply_text('📩 Tu equipo es privado; te lo mandé por PV.')


def _items_text(uid:int)->str:
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT item_code,qty FROM pokemon_items_tb WHERE owner_id=%s AND qty>0 ORDER BY item_code",(uid,)); rows=c.fetchall()
    finally:_put_connection(conn)
    lines=['🎒 OBJETOS POKÉMON · PRIVADO','']
    if not rows: lines.append('Todavía no tienes objetos Pokémon.')
    for code,qty in rows:
        if code in ITEMS:
            name,em,_,kind=ITEMS[code]; lines.append(f'{em} {name} ×{qty}')
    lines += ['', 'Las piedras, Cable Link y Caramelo Raro se usan fuera de combate. Las pociones/Revivir aparecen como opción durante una batalla.']
    return '\n'.join(lines)


def _items_markup(uid:int):
    conn=_get_connection(); rows=[]
    try:
        c=conn.cursor(); c.execute("SELECT item_code,qty FROM pokemon_items_tb WHERE owner_id=%s AND qty>0",(uid,)); inv=c.fetchall()
    finally:_put_connection(conn)
    for code,qty in inv:
        if code in ITEMS and ITEMS[code][3] in ('evolution','trade_evolution','level'):
            name,em,_,_=ITEMS[code]; rows.append([InlineKeyboardButton(f'{em} Usar {name} ×{qty}',callback_data=f'pk:useitem:{code}:0')])
    rows.append([InlineKeyboardButton('🎮 Colección',callback_data='pk:list:0')])
    return InlineKeyboardMarkup(rows)


async def pokeobjetos_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    try: await context.bot.send_message(uid,_items_text(uid),reply_markup=_items_markup(uid))
    except Exception: return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private': await update.effective_message.reply_text('📩 Te mandé tus objetos Pokémon por privado.')


async def nombrarpokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type!='private':
        return await update.effective_message.reply_text('🏷️ Los apodos se configuran por privado. Usa /pokemon con PiBot.')
    if len(context.args)>=2:
        try: pid=int(context.args[0])
        except Exception: return await update.effective_message.reply_text('Usa /nombrarpokemon ID apodo. Ejemplo: /nombrarpokemon 12 Sombra')
        name=' '.join(context.args[1:]).strip()[:24]
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("UPDATE pokemon_instances_tb SET nickname=%s,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s RETURNING species_id",(name or None,update.effective_user.id,pid)); r=c.fetchone(); conn.commit()
        except Exception: conn.rollback(); r=None
        finally:_put_connection(conn)
        return await update.effective_message.reply_text(f'🏷️ Apodo guardado: {name}' if r else 'No encontré ese Pokémon en tu colección.')
    await update.effective_message.reply_text('Toca el Pokémon que quieres nombrar:',reply_markup=_collection_markup(update.effective_user.id,0,'nickselect'))


async def fotopokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type!='private':
        return await update.effective_message.reply_text('🎞️ La foto/GIF de tus Pokémon se configura por privado con /fotopokemon.')
    await update.effective_message.reply_text('Elige el Pokémon al que quieres poner foto o GIF:',reply_markup=_collection_markup(update.effective_user.id,0,'mediaselect'))


def _resolve_target(update,context):
    m=update.effective_message
    if m.reply_to_message and m.reply_to_message.from_user and not m.reply_to_message.from_user.is_bot:
        return m.reply_to_message.from_user.id
    if context.args and context.args[0].startswith('@'):
        uname=context.args[0][1:].lower(); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT id_user FROM perfiles_tb WHERE lower(username)=%s LIMIT 1",(uname,)); r=c.fetchone(); return int(r[0]) if r else None
        finally:_put_connection(conn)
    return None


async def presumirpokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if update.effective_chat.type=='private':
        context.user_data['pk_brag_target']={'chat_id':uid,'thread_id':None}
    else:
        context.user_data['pk_brag_target']={'chat_id':update.effective_chat.id,'thread_id':getattr(update.effective_message,'message_thread_id',None)}
    try:
        await context.bot.send_message(uid,'😎 ¿Cuál quieres presumir?',reply_markup=_collection_markup(uid,0,'brag'))
    except Exception:
        return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private': await update.effective_message.reply_text('📩 Elige por privado cuál quieres presumir.')


async def _send_brag(context, uid:int, pid:int, target:dict):
    row=_get_instance(uid,pid)
    if not row:return False
    species=int(row[1]); nickname=row[2]; level=int(row[3]); media_type=row[6]; file_id=row[7]; wins=int(row[8]); losses=int(row[9]); shiny=bool(row[10]) if len(row)>10 else False
    conn=_get_connection()
    try:
        c=conn.cursor(); owner=_display_name_cursor(c,uid)
    finally:_put_connection(conn)
    title=nickname or NAMES[species]
    caption=(f"✨ POKÉMON DE {owner}\n"
             f"{rarity_emoji(rarity_for(species))} {'✨ SHINY · ' if shiny else ''}{title}\n"
             f"{NAMES[species]} · Nv.{level}\n"
             f"{_types_text(species)}\n"
             f"⚔️ {wins}V / {losses}D\n\n"
             "Su equipo y sus movimientos siguen siendo privados.")
    kwargs={'chat_id':target['chat_id'],'message_thread_id':target.get('thread_id')}
    try:
        if media_type=='photo' and file_id: await context.bot.send_photo(photo=file_id,caption=caption,**kwargs)
        elif media_type=='animation' and file_id: await context.bot.send_animation(animation=file_id,caption=caption,**kwargs)
        else: await context.bot.send_message(text=caption,**kwargs)
        return True
    except Exception:return False


# ------------------------------ BATALLAS ------------------------------
def _stat_value(species:int,level:int,key:str)->int:
    b=battle_base_stats(species)[key]
    if key=='hp': return int((2*b*level)/100)+level+10
    return int((2*b*level)/100)+5


def _battle_mon(row)->dict:
    pid,species,nick,level,xp,moves_json,_,_,wins,losses,*extra=row
    shiny=bool(extra[0]) if extra else False
    species=int(species); level=int(level)
    try:moves=json.loads(moves_json or '[]')
    except Exception:moves=[]
    if not moves:moves=available_moves(species,level)
    hp=_stat_value(species,level,'hp')
    return {'pid':int(pid),'species':species,'nickname':nick,'level':level,'hp':hp,'max_hp':hp,'moves':moves,'pp':{m:MOVES[m][4] for m in moves if m in MOVES},'status':None,'sleep':0,'stages':{'atk':0,'def':0,'spd':0},'shiny':shiny}


def _team_for_battle_cursor(c,uid:int,mode:int):
    _ensure_team_row_cursor(c,uid)
    c.execute("SELECT slot1,slot2,slot3 FROM pokemon_team_tb WHERE owner_id=%s",(uid,)); slots=list(c.fetchone() or (None,None,None))[:mode]
    if len(slots)<mode or any(x is None for x in slots):return None
    mons=[]
    for pid in slots:
        c.execute("SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); r=c.fetchone()
        if not r:return None
        mons.append(_battle_mon(r))
    return mons


def _battle_title_mon(mon:dict)->str:
    base=NAMES[mon['species']]; name=mon.get('nickname') or base
    shown=f"{name} ({base})" if mon.get('nickname') else base
    return f"✨ {shown}" if mon.get('shiny') else shown


def _battle_text(state:dict, note:str|None=None)->str:
    ids=list(state['players'].keys()); a=state['players'][ids[0]]; b=state['players'][ids[1]]
    am=a['mons'][a['active']]; bm=b['mons'][b['active']]
    def bar(m):
        pct=max(0,min(1,m['hp']/max(1,m['max_hp']))); full=round(pct*10)
        return '█'*full+'░'*(10-full)
    lines=[f"⚔️ BATALLA POKÉMON {state['mode']}v{state['mode']}","",
           f"{a['name']} · {_battle_title_mon(am)} Nv.{am['level']}",f"❤️ {am['hp']}/{am['max_hp']}  {bar(am)}",
           "VS",
           f"{b['name']} · {_battle_title_mon(bm)} Nv.{bm['level']}",f"❤️ {bm['hp']}/{bm['max_hp']}  {bar(bm)}",
           "",f"🔁 Ronda {state.get('round',1)}"]
    if note: lines += ['',note]
    if state.get('status')=='active':
        chosen=state.get('choices',{})
        lines += ['',f"Elecciones: {('✅' if ids[0] in chosen else '⌛')} {a['name']} · {('✅' if ids[1] in chosen else '⌛')} {b['name']}"]
    return '\n'.join(lines)


def _battle_markup(bid:int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⚔️ Elegir acción',callback_data=f'pk:action:{bid}')],
        [InlineKeyboardButton('🏳 Rendirse',callback_data=f'pk:surrender:{bid}')],
    ])


def _move_menu(bid:int,mon:dict):
    rows=[]
    for i,code in enumerate(mon['moves']):
        if code not in MOVES:continue
        name,tp,power,acc,pp,kind=MOVES[code]; left=int(mon.get('pp',{}).get(code,pp))
        rows.append([InlineKeyboardButton(f"{type_emoji(tp)} {name} · PP {left}/{pp}",callback_data=f'pk:move:{bid}:{i}')])
    rows.append([InlineKeyboardButton('🔄 Cambiar Pokémon',callback_data=f'pk:bswitchmenu:{bid}'),InlineKeyboardButton('🎒 Objeto',callback_data=f'pk:bitemmenu:{bid}')])
    return InlineKeyboardMarkup(rows)


def _get_battle(bid:int, lock=False):
    conn=_get_connection()
    try:
        c=conn.cursor(); sql="SELECT battle_id,chat_id,thread_id,challenger_id,opponent_id,mode,status,state_json,message_id,winner_id FROM pokemon_battles_tb WHERE battle_id=%s"+(' FOR UPDATE' if lock else '')
        c.execute(sql,(bid,)); return c.fetchone()
    finally:_put_connection(conn)


def _stage_mult(stage:int)->float:
    stage=max(-2,min(2,int(stage)))
    return {-2:0.6,-1:0.8,0:1.0,1:1.25,2:1.5}[stage]


def _effective_speed(mon):
    val=_stat_value(mon['species'],mon['level'],'spd')*_stage_mult(mon['stages'].get('spd',0))
    if mon.get('status')=='paralyze':val*=0.5
    return val


def _do_move(att:dict,defn:dict,move_code:str)->list[str]:
    if move_code not in MOVES:return ['El movimiento falló.']
    name,tp,power,acc,maxpp,kind=MOVES[move_code]
    logs=[]
    if att.get('sleep',0)>0:
        att['sleep']-=1
        if att['sleep']>0:return [f"💤 {_battle_title_mon(att)} está dormido."]
        logs.append(f"✨ {_battle_title_mon(att)} despertó.")
    if att.get('status')=='paralyze' and random.random()<0.25:
        return logs+[f"⚡ {_battle_title_mon(att)} está paralizado y no puede moverse."]
    if acc<100 and random.randint(1,100)>acc:
        return logs+[f"💨 {name} falló."]
    if kind=='nothing': return logs+[f"… {_battle_title_mon(att)} usó {name}. No pasó nada."]
    if kind=='heal':
        heal=max(1,att['max_hp']//2); before=att['hp']; att['hp']=min(att['max_hp'],att['hp']+heal)
        return logs+[f"💚 {name}: recuperó {att['hp']-before} HP."]
    if kind=='buff_def':
        att['stages']['def']=min(2,att['stages']['def']+1); return logs+[f"🛡️ {name}: subió la Defensa."]
    if kind=='buff_speed':
        att['stages']['spd']=min(2,att['stages']['spd']+1); return logs+[f"💨 {name}: subió la Velocidad."]
    if kind=='debuff_atk':
        defn['stages']['atk']=max(-2,defn['stages']['atk']-1); return logs+[f"📉 {name}: bajó el Ataque rival."]
    if kind=='sleep':
        if defn.get('sleep',0)>0:return logs+[f"💤 {name}: el rival ya dormía."]
        defn['sleep']=random.randint(2,4); return logs+[f"💤 {name}: {_battle_title_mon(defn)} se durmió."]
    if kind=='poison':
        if defn.get('status') is None:defn['status']='poison'; return logs+[f"☠️ {name}: rival envenenado."]
        return logs+[f"☠️ {name}: no cambió el estado del rival."]
    if kind=='paralyze':
        if defn.get('status') is None:defn['status']='paralyze'; return logs+[f"⚡ {name}: rival paralizado."]
        return logs+[f"⚡ {name}: no cambió el estado del rival."]
    if kind=='transform':
        att['species']=defn['species']; att['moves']=list(defn['moves']); att['pp']={m:MOVES[m][4] for m in att['moves'] if m in MOVES}
        return logs+[f"✨ Transformación: copió a {_battle_title_mon(defn)}."]
    if kind=='metronome':
        pool=[m for m,v in MOVES.items() if v[5] in ('damage','drain','fixed','fixed40') and m!='metronome']
        picked=random.choice(pool); logs.append(f"🎲 Metrónomo eligió {MOVES[picked][0]}.")
        return logs+_do_move(att,defn,picked)

    if kind=='fixed': dmg=max(1,int(att['level']))
    elif kind=='fixed40': dmg=40
    else:
        atk_key='atk' if tp in PHYSICAL_TYPES else 'spc'; def_key='def' if tp in PHYSICAL_TYPES else 'spc'
        A=_stat_value(att['species'],att['level'],atk_key)*_stage_mult(att['stages'].get('atk',0) if atk_key=='atk' else 0)
        D=_stat_value(defn['species'],defn['level'],def_key)*_stage_mult(defn['stages'].get('def',0) if def_key=='def' else 0)
        base=((((2*att['level']/5)+2)*max(1,power)*max(1,A)/max(1,D))/50)+2
        stab=1.5 if tp in TYPES.get(att['species'],()) else 1.0
        eff=effectiveness(tp,TYPES.get(defn['species'],('Normal',)))
        crit_chance=0.25 if move_code=='slash' else 0.0625
        crit=random.random()<crit_chance
        dmg=max(1,int(base*stab*eff*random.uniform(0.85,1.0)*(1.5 if crit else 1.0))) if eff>0 else 0
        if crit:logs.append('💥 ¡Golpe crítico!')
        if eff==0:logs.append('🚫 No afecta al rival.')
        elif eff>=2:logs.append('🔥 ¡Es súper eficaz!')
        elif eff<1:logs.append('🛡️ No es muy eficaz.')
    before=defn['hp']; defn['hp']=max(0,defn['hp']-dmg); dealt=before-defn['hp']
    logs.insert(0,f"⚔️ {_battle_title_mon(att)} usó {name}: -{dealt} HP.")
    if kind=='drain' and dealt>0:
        heal=max(1,dealt//2); old=att['hp']; att['hp']=min(att['max_hp'],att['hp']+heal); logs.append(f"💚 Recuperó {att['hp']-old} HP.")
    return logs


def _next_alive(player:dict):
    for i,m in enumerate(player['mons']):
        if m['hp']>0:return i
    return None


def _choice_speed(player,choice):
    if choice['type'] in ('switch','item'):return 9999
    mon=player['mons'][player['active']]
    code=choice.get('move')
    priority=1 if code=='quick_attack' else 0
    return _effective_speed(mon)+priority*1000


def _apply_item_action(player:dict,choice:dict,c,uid:int)->str:
    code=choice['item']; idx=player['active']; mon=player['mons'][idx]
    if code not in ITEMS:return '🎒 Objeto inválido.'
    name,em,val,kind=ITEMS[code]
    c.execute("SELECT qty FROM pokemon_items_tb WHERE owner_id=%s AND item_code=%s FOR UPDATE",(uid,code)); r=c.fetchone()
    if not r or int(r[0])<=0:return f'🎒 No quedaba {name}.'
    if kind=='heal':
        if mon['hp']<=0:return f'🎒 {name} no puede usarse sobre un Pokémon debilitado.'
        before=mon['hp']; mon['hp']=min(mon['max_hp'],mon['hp']+val); used=mon['hp']>before
        if not used:return f'🎒 {name}: ya tenía todos sus HP.'
    elif kind=='revive':
        target=next((m for m in player['mons'] if m['hp']<=0),None)
        if not target:return '🎒 Revivir: no hay Pokémon debilitados.'
        target['hp']=max(1,target['max_hp']//2)
    else:return f'🎒 {name} no se usa dentro de batalla.'
    c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code=%s",(uid,code))
    return f'{em} Usó {name}.'


def _grant_pokemon_xp_cursor(c,pid:int,amount:int)->list[str]:
    c.execute("SELECT owner_id,species_id,nickname,level,xp FROM pokemon_instances_tb WHERE pokemon_id=%s FOR UPDATE",(pid,)); r=c.fetchone()
    if not r:return []
    owner,species,nick,level,xp=int(r[0]),int(r[1]),r[2],int(r[3]),int(r[4]); oldlevel=level; xp+=int(amount); notes=[]
    while level<MAX_LEVEL and xp>=_xp_floor(level+1):level+=1
    evolved=False
    while species in LEVEL_EVOLUTIONS and level>=LEVEL_EVOLUTIONS[species][0]:
        old=NAMES[species]; species=LEVEL_EVOLUTIONS[species][1]; evolved=True
        c.execute("""INSERT INTO pokemon_pokedex_tb(owner_id,species_id,obtained_count) VALUES(%s,%s,1)
                     ON CONFLICT(owner_id,species_id) DO UPDATE SET last_obtained_at=NOW()""",(owner,species))
        notes.append(f'✨ {nick or old} evolucionó a {NAMES[species]}.')
    moves=available_moves(species,level)
    c.execute("UPDATE pokemon_instances_tb SET species_id=%s,level=%s,xp=%s,moves_json=%s,updated_at=NOW() WHERE pokemon_id=%s",(species,level,xp,json.dumps(moves,ensure_ascii=False),pid))
    if level>oldlevel:notes.append(f'⭐ {nick or NAMES[species]} subió a Nv.{level}.')
    return notes


def _update_rank_cursor(c,winner:int,loser:int):
    for uid in (winner,loser):c.execute("INSERT INTO pokemon_rank_tb(user_id) VALUES(%s) ON CONFLICT DO NOTHING",(uid,))
    c.execute("SELECT user_id,rating,wins,losses,current_streak,best_streak FROM pokemon_rank_tb WHERE user_id IN (%s,%s) FOR UPDATE",(winner,loser)); rows={int(r[0]):r for r in c.fetchall()}
    rw=int(rows[winner][1]); rl=int(rows[loser][1]); ew=1/(1+10**((rl-rw)/400)); delta=max(8,round(24*(1-ew)))
    ws=int(rows[winner][4])+1; best=max(int(rows[winner][5]),ws)
    c.execute("UPDATE pokemon_rank_tb SET rating=rating+%s,wins=wins+1,current_streak=%s,best_streak=%s,updated_at=NOW() WHERE user_id=%s",(delta,ws,best,winner))
    c.execute("UPDATE pokemon_rank_tb SET rating=GREATEST(0,rating-%s),losses=losses+1,current_streak=0,updated_at=NOW() WHERE user_id=%s",(delta,loser))
    return delta


def _resolve_round_cursor(c,bid:int,state:dict)->tuple[str|None,list[str],dict]:
    ids=list(state['players'].keys()); choices=state.get('choices',{})
    if any(uid not in choices for uid in ids):return None,[],state
    logs=[]
    order=sorted(ids,key=lambda u:_choice_speed(state['players'][u],choices[u]),reverse=True)
    for uid in order:
        if state.get('status')!='active':break
        p=state['players'][uid]; oppid=ids[1] if uid==ids[0] else ids[0]; o=state['players'][oppid]; choice=choices[uid]
        mon=p['mons'][p['active']]
        if mon['hp']<=0:continue
        if choice['type']=='switch':
            idx=int(choice['index'])
            if 0<=idx<len(p['mons']) and p['mons'][idx]['hp']>0 and idx!=p['active']:
                p['active']=idx; logs.append(f"🔄 {p['name']} cambió a {_battle_title_mon(p['mons'][idx])}.")
            continue
        if choice['type']=='item':
            logs.append(f"{p['name']}: {_apply_item_action(p,choice,c,int(uid))}")
            continue
        # El rival puede haberse cambiado/curado antes de este ataque.
        mon=p['mons'][p['active']]; target=o['mons'][o['active']]
        code=choice.get('move'); pp=int(mon.get('pp',{}).get(code,0))
        if pp<=0:
            logs.append(f"⚠️ {p['name']} no tenía PP para ese movimiento.")
            continue
        mon['pp'][code]=pp-1
        logs += _do_move(mon,target,code)
        if target['hp']<=0:
            logs.append(f"💫 {_battle_title_mon(target)} quedó debilitado.")
            nxt=_next_alive(o)
            if nxt is None:
                state['status']='finished'; state['winner']=uid; state['loser']=oppid; break
            o['active']=nxt; logs.append(f"➡️ {o['name']} envía a {_battle_title_mon(o['mons'][nxt])}.")
    # daño de veneno al final de ronda
    if state.get('status')=='active':
        for uid in ids:
            p=state['players'][uid]; mon=p['mons'][p['active']]
            if mon.get('status')=='poison' and mon['hp']>0:
                dmg=max(1,mon['max_hp']//8); mon['hp']=max(0,mon['hp']-dmg); logs.append(f"☠️ {_battle_title_mon(mon)} perdió {dmg} HP por veneno.")
                if mon['hp']<=0:
                    nxt=_next_alive(p)
                    if nxt is None:
                        other=ids[1] if uid==ids[0] else ids[0]; state['status']='finished'; state['winner']=other; state['loser']=uid; break
                    p['active']=nxt; logs.append(f"➡️ {p['name']} envía a {_battle_title_mon(p['mons'][nxt])}.")
    state['choices']={}; state['round']=int(state.get('round',1))+1
    return state.get('winner'),logs,state


def _finish_battle_cursor(c,bid:int,state:dict)->dict:
    winner=int(state['winner']); loser=int(state['loser'])
    c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(WIN_PIPESOS,winner))
    c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(LOSS_PIPESOS,loser))
    delta=_update_rank_cursor(c,winner,loser)
    level_notes=[]
    for uid,p in state['players'].items():
        won=int(uid)==winner; amount=WIN_POKEMON_XP if won else LOSS_POKEMON_XP
        for mon in p['mons']:
            level_notes += _grant_pokemon_xp_cursor(c,int(mon['pid']),amount)
        c.execute("UPDATE pokemon_instances_tb SET wins=wins+1 WHERE owner_id=%s AND pokemon_id=ANY(%s)",(int(uid),[int(m['pid']) for m in p['mons']])) if won else c.execute("UPDATE pokemon_instances_tb SET losses=losses+1 WHERE owner_id=%s AND pokemon_id=ANY(%s)",(int(uid),[int(m['pid']) for m in p['mons']]))
    c.execute("UPDATE pokemon_battles_tb SET status='finished',winner_id=%s,state_json=%s,finished_at=NOW(),updated_at=NOW() WHERE battle_id=%s",(winner,json.dumps(state,ensure_ascii=False),bid))
    return {'winner':winner,'loser':loser,'elo':delta,'notes':level_notes}


async def batallapokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private':return await update.effective_message.reply_text('⚔️ Las batallas Pokémon se retan en el grupo.')
    uid=update.effective_user.id; target=_resolve_target(update,context)
    if target==uid:return await update.effective_message.reply_text('😂 No puedes retarte a ti mismo.')
    if context.args and context.args[0].startswith('@') and target is None:return await update.effective_message.reply_text('No encontré a ese usuario registrado. También puedes responderle con /batallapokemon.')
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT 1 FROM pokemon_battles_tb WHERE status IN ('open','active') AND (challenger_id=%s OR opponent_id=%s) LIMIT 1",(uid,uid))
        if c.fetchone():return await update.effective_message.reply_text('⚔️ Ya tienes un reto Pokémon pendiente o activo.')
        if _trade_busy_cursor(c,uid):return await update.effective_message.reply_text('🔄 Termina o cancela tu intercambio Pokémon antes de iniciar una batalla.')
        c.execute("INSERT INTO pokemon_battles_tb(chat_id,thread_id,challenger_id,opponent_id) VALUES(%s,%s,%s,%s) RETURNING battle_id",(update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),uid,target)); bid=int(c.fetchone()[0]); conn.commit()
    except Exception:conn.rollback(); raise
    finally:_put_connection(conn)
    who=f' para <b>{update.effective_message.reply_to_message.from_user.first_name}</b>' if target and update.effective_message.reply_to_message else (' dirigido a ese usuario' if target else ' abierto para quien quiera aceptar')
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('1️⃣ 1v1',callback_data=f'pk:accept:{bid}:1'),InlineKeyboardButton('2️⃣ 2v2',callback_data=f'pk:accept:{bid}:2'),InlineKeyboardButton('3️⃣ 3v3',callback_data=f'pk:accept:{bid}:3')],[InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:cancelchallenge:{bid}')]])
    await update.effective_message.reply_text(f'⚔️ <b>RETO POKÉMON</b>{who}\n\nEl rival elige formato. El equipo permanece privado y solo se revelan los Pokémon que salen a pelear.',reply_markup=kb,parse_mode='HTML')


def _trade_busy_cursor(c, uid:int)->bool:
    c.execute("""SELECT 1 FROM pokemon_trades_tb
                 WHERE status IN ('selecting','confirming') AND (user_a=%s OR user_b=%s)
                 LIMIT 1""", (uid,uid))
    return c.fetchone() is not None


def _battle_busy_cursor(c, uid:int)->bool:
    c.execute("""SELECT 1 FROM pokemon_battles_tb
                 WHERE status IN ('open','active') AND (challenger_id=%s OR opponent_id=%s)
                 LIMIT 1""", (uid,uid))
    return c.fetchone() is not None


def _trade_pick_markup(uid:int, trade_id:int, page:int=0):
    mons=_get_owned(uid)
    pages=max(1,math.ceil(len(mons)/PAGE_SIZE)); page=max(0,min(page,pages-1))
    chunk=mons[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
    rows=[[InlineKeyboardButton(_pokemon_label(r)[:54],callback_data=f'pk:tradeoffer:{trade_id}:{r[0]}')] for r in chunk]
    nav=[]
    if page>0:nav.append(InlineKeyboardButton('⬅️',callback_data=f'pk:tradepick:{trade_id}:{page-1}'))
    nav.append(InlineKeyboardButton(f'{page+1}/{pages}',callback_data='pk:noop'))
    if page<pages-1:nav.append(InlineKeyboardButton('➡️',callback_data=f'pk:tradepick:{trade_id}:{page+1}'))
    if nav:rows.append(nav)
    rows.append([InlineKeyboardButton('❌ Cancelar intercambio',callback_data=f'pk:tradecancel:{trade_id}')])
    return InlineKeyboardMarkup(rows)


def _trade_mon_text_cursor(c, owner:int, pid:int|None)->str:
    if not pid:return '— pendiente —'
    c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny
                 FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s""",(owner,pid))
    r=c.fetchone()
    return _pokemon_label(r) if r else '— ya no disponible —'


async def intercambiopokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private':
        return await update.effective_message.reply_text('🔄 Inicia el intercambio en el grupo respondiendo al mensaje de la otra persona con /intercambiopokemon.')
    if not update.effective_message.reply_to_message:
        return await update.effective_message.reply_text('🔄 Responde al mensaje de la persona con /intercambiopokemon.')
    target_user=update.effective_message.reply_to_message.from_user
    uid=update.effective_user.id; target=target_user.id
    if target==uid or target_user.is_bot:return await update.effective_message.reply_text('😂 Necesitas otra persona real para intercambiar.')
    conn=_get_connection(); trade_id=None
    try:
        c=conn.cursor()
        if _battle_busy_cursor(c,uid) or _battle_busy_cursor(c,target):
            return await update.effective_message.reply_text('⚔️ Uno de los dos tiene una batalla Pokémon pendiente o activa.')
        if _trade_busy_cursor(c,uid) or _trade_busy_cursor(c,target):
            return await update.effective_message.reply_text('🔄 Uno de los dos ya tiene un intercambio pendiente.')
        c.execute("""INSERT INTO pokemon_trades_tb(chat_id,thread_id,user_a,user_b)
                     VALUES(%s,%s,%s,%s) RETURNING trade_id""",
                  (update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),uid,target))
        trade_id=int(c.fetchone()[0]); conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK trade create]',type(e).__name__,e)
        return await update.effective_message.reply_text('No pude crear el intercambio.')
    finally:_put_connection(conn)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('🔄 Elegir mi Pokémon',callback_data=f'pk:tradepick:{trade_id}:0')],[InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:tradecancel:{trade_id}')]])
    msg=await update.effective_message.reply_text(f'🔄 INTERCAMBIO POKÉMON\n\n{update.effective_user.first_name} ↔ {target_user.first_name}\n\nCada uno elige su Pokémon por privado. Cuando ambos elijan, los dos deberán confirmar.\n✨ Kadabra, Machoke, Graveler y Haunter evolucionan al intercambiarse.',reply_markup=kb)
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute('UPDATE pokemon_trades_tb SET message_id=%s WHERE trade_id=%s',(msg.message_id,trade_id)); conn.commit()
    except Exception:conn.rollback()
    finally:_put_connection(conn)


async def cancelarintercambiopokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""UPDATE pokemon_trades_tb SET status='cancelled',finished_at=NOW(),updated_at=NOW()
                                     WHERE status IN ('selecting','confirming') AND (user_a=%s OR user_b=%s)""",(uid,uid)); n=c.rowcount; conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK trade cancel command]',type(e).__name__,e); n=0
    finally:_put_connection(conn)
    await update.effective_message.reply_text('❌ Intercambio Pokémon cancelado.' if n else 'No tienes ningún intercambio Pokémon pendiente.')


async def shinys_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny
                                     FROM pokemon_instances_tb WHERE owner_id=%s AND shiny=TRUE ORDER BY pokemon_id""",(uid,)); rows=c.fetchall()
    finally:_put_connection(conn)
    lines=[f'✨ TUS SHINYS · {len(rows)}','']
    lines += [_pokemon_label(r) for r in rows[:40]] if rows else ['Todavía no tienes ninguno. La probabilidad base es 1 entre 4096 cuando obtienes un Pokémon.']
    if len(rows)>40:lines.append(f'… y {len(rows)-40} más.')
    try:await context.bot.send_message(uid,'\n'.join(lines))
    except Exception:return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private':await update.effective_message.reply_text('📩 Te mandé tus Shinys por privado.')


async def rankingpokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""SELECT r.user_id,r.rating,r.wins,r.losses,r.best_streak,COALESCE(NULLIF(p.nombre,''),p.username,'Jugador')
                                   FROM pokemon_rank_tb r LEFT JOIN perfiles_tb p ON p.id_user=r.user_id
                                   ORDER BY r.rating DESC,r.wins DESC,r.updated_at ASC LIMIT 10"""); rows=c.fetchall()
    finally:_put_connection(conn)
    lines=['🏆 RANKING POKÉMON','']
    if not rows:lines.append('Todavía no hay batallas clasificatorias.')
    medals=['🥇','🥈','🥉']
    for i,r in enumerate(rows,1):lines.append(f"{medals[i-1] if i<=3 else str(i)+'.'} {r[5]} · {r[1]} pts · {r[2]}V/{r[3]}D · 🔥{r[4]}")
    await update.effective_message.reply_text('\n'.join(lines))


async def poketest_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    # Solo para que Kiu/admins puedan probar el sistema sin abrir 100 cajas.
    try:
        if not is_botmaster(update.effective_user.id):return await update.effective_message.reply_text('Solo BotMaster puede usar /poketest.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede usar /poketest.')
    try:sid=int(context.args[0]) if context.args else random.randint(1,151)
    except Exception:sid=random.randint(1,151)
    force_shiny=any(str(x).lower() in ('shiny','variocolor','✨') for x in context.args[1:]) if context.args else False
    sid=max(1,min(151,sid)); conn=_get_connection()
    try:
        c=conn.cursor(); data=grant_pokemon_with_cursor(c,update.effective_user.id,sid,'prueba_admin',force_shiny=force_shiny); conn.commit()
    except Exception as e:conn.rollback(); return await update.effective_message.reply_text(f'Error de prueba: {e}')
    finally:_put_connection(conn)
    await update.effective_message.reply_text(f"🧪 Te di #{sid:03d} {'✨ SHINY ' if data.get('shiny') else ''}{NAMES[sid]} Nv.{data['level']} para probar. No costó PiPesos.")


async def pokemon_callback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; p=q.data.split(':'); uid=q.from_user.id
    action=p[1]
    if action=='noop':return await q.answer()
    if action=='list':
        page=int(p[2]); await q.answer(); return await q.edit_message_text(f'🎮 TUS POKÉMON\n\nColección privada. Toca uno para administrarlo.',reply_markup=_collection_markup(uid,page))
    if action in ('detail','nickselect','mediaselect','brag'):
        pid=int(p[2]); page=int(p[3]) if len(p)>3 else 0; row=_get_instance(uid,pid)
        if not row:return await q.answer('Ese Pokémon ya no está en tu colección.',show_alert=True)
        if action=='brag':
            target=context.user_data.get('pk_brag_target') or {'chat_id':uid,'thread_id':None}; ok=await _send_brag(context,uid,pid,target); await q.answer('Presumido 😎' if ok else 'No pude publicarlo.',show_alert=True); return
        if action=='nickselect':context.user_data['pk_wait_nick']=pid; await q.answer(); return await q.message.reply_text(f"🏷️ Escribe el nuevo apodo para {NAMES[int(row[1])]} (máx. 24 caracteres). Escribe - para quitarlo.")
        if action=='mediaselect':context.user_data['pk_wait_media']=pid; await q.answer(); return await q.message.reply_text(f"🎞️ Envíame una FOTO o GIF para {row[2] or NAMES[int(row[1])]}. Telegram guardará el archivo; PiBot solo conservará su file_id.")
        species=int(row[1]); moves=json.loads(row[5] or '[]'); move_names=', '.join(MOVES[m][0] for m in moves if m in MOVES)
        shiny_line = "✨ Variante SHINY\n" if len(row)>10 and row[10] else ""
        xp_line = (
            f"⭐ XP Pokémon: {row[4]:,} / {_xp_floor(int(row[3])+1):,}\n"
            if int(row[3]) < MAX_LEVEL
            else f"⭐ XP Pokémon: {row[4]:,} · NIVEL MÁXIMO\n"
        )
        txt=(f"{rarity_emoji(rarity_for(species))} {_pokemon_label(row)}\n"
             f"{shiny_line}"
             f"{_types_text(species)}\n"
             f"{xp_line}"
             f"⚔️ {row[8]}V / {row[9]}D\n"
             f"🎯 Movimientos: {move_names or '—'}\n"
             f"🎞️ Multimedia: {'GIF' if row[6]=='animation' else 'Foto' if row[6]=='photo' else 'Sin asignar'}")
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('🏷️ Apodo',callback_data=f'pk:nickselect:{pid}:{page}'),InlineKeyboardButton('🎞️ Foto/GIF',callback_data=f'pk:mediaselect:{pid}:{page}')],[InlineKeyboardButton('👥 Meter al equipo',callback_data=f'pk:addteam:{pid}'),InlineKeyboardButton('😎 Presumir aquí',callback_data=f'pk:braghere:{pid}')],[InlineKeyboardButton('🗑 Quitar foto/GIF',callback_data=f'pk:removemedia:{pid}'),InlineKeyboardButton('⬅️ Volver',callback_data=f'pk:list:{page}')]])
        await q.answer(); return await q.edit_message_text(txt,reply_markup=kb)
    if action=='removemedia':
        pid=int(p[2]); conn=_get_connection()
        try:c=conn.cursor(); c.execute("UPDATE pokemon_instances_tb SET media_type=NULL,media_file_id=NULL,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); conn.commit()
        except Exception:conn.rollback()
        finally:_put_connection(conn)
        return await q.answer('Foto/GIF quitado.',show_alert=True)
    if action=='braghere':
        pid=int(p[2]); ok=await _send_brag(context,uid,pid,{'chat_id':q.message.chat_id,'thread_id':q.message.message_thread_id}); return await q.answer('Listo 😎' if ok else 'No pude enviarlo.',show_alert=True)
    if action=='team':
        await q.answer(); return await q.edit_message_text(_team_text(uid),reply_markup=_team_markup(uid))
    if action=='teamslot':
        slot=int(p[2]); page=int(p[3]); mons=_get_owned(uid); pages=max(1,math.ceil(len(mons)/PAGE_SIZE)); page=max(0,min(page,pages-1)); chunk=mons[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
        rows=[[InlineKeyboardButton(_pokemon_label(r)[:50],callback_data=f'pk:setslot:{slot}:{r[0]}')] for r in chunk]
        nav=[]
        if page>0:nav.append(InlineKeyboardButton('⬅️',callback_data=f'pk:teamslot:{slot}:{page-1}'))
        if page<pages-1:nav.append(InlineKeyboardButton('➡️',callback_data=f'pk:teamslot:{slot}:{page+1}'))
        if nav:rows.append(nav)
        rows.append([InlineKeyboardButton('🗑 Vaciar espacio',callback_data=f'pk:setslot:{slot}:0'),InlineKeyboardButton('⬅️ Equipo',callback_data='pk:team')])
        await q.answer(); return await q.edit_message_text(f'👥 Elige Pokémon para el espacio {slot}:',reply_markup=InlineKeyboardMarkup(rows))
    if action=='setslot':
        slot=int(p[2]); pid=int(p[3]); conn=_get_connection()
        try:
            c=conn.cursor(); _ensure_team_row_cursor(c,uid)
            if pid:
                c.execute("SELECT 1 FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid))
                if not c.fetchone():conn.rollback(); return await q.answer('Ese Pokémon no es tuyo.',show_alert=True)
                c.execute("SELECT slot1,slot2,slot3 FROM pokemon_team_tb WHERE owner_id=%s FOR UPDATE",(uid,)); current=list(c.fetchone())
                # Si ya estaba en otro hueco, lo quitamos para no duplicarlo.
                for i,x in enumerate(current,1):
                    if x==pid:c.execute(f"UPDATE pokemon_team_tb SET slot{i}=NULL WHERE owner_id=%s",(uid,))
            c.execute(f"UPDATE pokemon_team_tb SET slot{slot}=%s,updated_at=NOW() WHERE owner_id=%s",(pid or None,uid)); conn.commit()
        except Exception:conn.rollback(); return await q.answer('No pude cambiar el equipo.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Equipo actualizado.',show_alert=True); return await q.edit_message_text(_team_text(uid),reply_markup=_team_markup(uid))
    if action=='addteam':
        pid=int(p[2]); rows=[[InlineKeyboardButton(f'Espacio {i}',callback_data=f'pk:setslot:{i}:{pid}') for i in range(1,4)],[InlineKeyboardButton('⬅️ Volver',callback_data='pk:list:0')]]
        await q.answer(); return await q.message.reply_text('¿En qué espacio lo quieres?',reply_markup=InlineKeyboardMarkup(rows))
    if action=='items':
        await q.answer(); return await q.edit_message_text(_items_text(uid),reply_markup=_items_markup(uid))
    if action=='useitem':
        code=p[2]; page=int(p[3]); mons=_get_owned(uid); eligible=[]
        for r in mons:
            sid=int(r[1]); level=int(r[3])
            ok=(code in STONE_EVOLUTIONS.get(sid,{})) or (code=='link_cable' and sid in TRADE_EVOLUTIONS) or (code=='rare_candy' and level<MAX_LEVEL)
            if ok:eligible.append(r)
        if not eligible:return await q.answer('No tienes ningún Pokémon que pueda evolucionar con ese objeto.',show_alert=True)
        pages=max(1,math.ceil(len(eligible)/PAGE_SIZE)); page=max(0,min(page,pages-1)); chunk=eligible[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
        rows=[[InlineKeyboardButton(_pokemon_label(r)[:50],callback_data=f'pk:evolveitem:{code}:{r[0]}')] for r in chunk]
        nav=[]
        if page>0:nav.append(InlineKeyboardButton('⬅️',callback_data=f'pk:useitem:{code}:{page-1}'))
        if page<pages-1:nav.append(InlineKeyboardButton('➡️',callback_data=f'pk:useitem:{code}:{page+1}'))
        if nav:rows.append(nav)
        rows.append([InlineKeyboardButton('⬅️ Objetos',callback_data='pk:items')])
        await q.answer(); return await q.edit_message_text(f'Elige quién usará {ITEMS[code][1]} {ITEMS[code][0]}:',reply_markup=InlineKeyboardMarkup(rows))
    if action=='evolveitem':
        code=p[2]; pid=int(p[3]); conn=_get_connection(); note=None
        try:
            c=conn.cursor(); c.execute("SELECT species_id,nickname,level FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s FOR UPDATE",(uid,pid)); r=c.fetchone()
            if not r:conn.rollback(); return await q.answer('Pokémon no encontrado.',show_alert=True)
            sid=int(r[0]); current_level=int(r[2])
            if code=='rare_candy':
                if current_level>=MAX_LEVEL:conn.rollback(); return await q.answer('Ese Pokémon ya está en nivel 100.',show_alert=True)
                c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code=%s AND qty>0 RETURNING qty",(uid,code))
                if not c.fetchone():conn.rollback(); return await q.answer('Ya no tienes ese objeto.',show_alert=True)
                new_level=current_level+1; target=sid
                while target in LEVEL_EVOLUTIONS and new_level>=LEVEL_EVOLUTIONS[target][0]:
                    target=LEVEL_EVOLUTIONS[target][1]
                moves=available_moves(target,new_level)
                c.execute("UPDATE pokemon_instances_tb SET species_id=%s,level=%s,xp=GREATEST(xp,%s),moves_json=%s,updated_at=NOW() WHERE pokemon_id=%s",(target,new_level,_xp_floor(new_level),json.dumps(moves,ensure_ascii=False),pid))
                c.execute("INSERT INTO pokemon_pokedex_tb(owner_id,species_id,obtained_count) VALUES(%s,%s,1) ON CONFLICT(owner_id,species_id) DO UPDATE SET last_obtained_at=NOW()",(uid,target))
                conn.commit(); note=f"🍬 {r[1] or NAMES[sid]} subió a Nv.{new_level}." + (f" ✨ Evolucionó a {NAMES[target]}." if target!=sid else '')
            else:
                target=STONE_EVOLUTIONS.get(sid,{}).get(code) if code!='link_cable' else TRADE_EVOLUTIONS.get(sid)
                if not target:conn.rollback(); return await q.answer('Ese objeto no sirve para este Pokémon.',show_alert=True)
                c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code=%s AND qty>0 RETURNING qty",(uid,code))
                if not c.fetchone():conn.rollback(); return await q.answer('Ya no tienes ese objeto.',show_alert=True)
                moves=available_moves(target,current_level)
                c.execute("UPDATE pokemon_instances_tb SET species_id=%s,moves_json=%s,updated_at=NOW() WHERE pokemon_id=%s",(target,json.dumps(moves,ensure_ascii=False),pid))
                c.execute("INSERT INTO pokemon_pokedex_tb(owner_id,species_id,obtained_count) VALUES(%s,%s,1) ON CONFLICT(owner_id,species_id) DO UPDATE SET last_obtained_at=NOW()",(uid,target))
                conn.commit(); note=f'✨ {r[1] or NAMES[sid]} evolucionó a {NAMES[target]}.'
        except Exception as e:conn.rollback(); print('[PK evolve]',e)
        finally:_put_connection(conn)
        return await q.answer(note or 'No pude evolucionarlo.',show_alert=True)

    # ---- callbacks de intercambio ----
    if action=='tradepick':
        tid=int(p[2]); page=int(p[3]); conn=_get_connection(); allowed=False
        try:
            c=conn.cursor(); c.execute("SELECT user_a,user_b,status FROM pokemon_trades_tb WHERE trade_id=%s",(tid,)); tr=c.fetchone()
            allowed=bool(tr and tr[2] in ('selecting','confirming') and uid in (int(tr[0]),int(tr[1])))
        finally:_put_connection(conn)
        if not allowed:return await q.answer('Ese intercambio no es tuyo o ya terminó.',show_alert=True)
        try:
            await context.bot.send_message(uid,'🔄 Elige el Pokémon que vas a ofrecer. Tu colección sigue siendo privada:',reply_markup=_trade_pick_markup(uid,tid,page))
            return await q.answer('Te mandé tu colección por privado.')
        except Exception:return await q.answer('Abre primero el privado de PiBot con /start.',show_alert=True)
    if action=='tradeoffer':
        tid=int(p[2]); pid=int(p[3]); conn=_get_connection(); summary=None; ready=False; chat_id=None; thread_id=None; msgid=None
        try:
            c=conn.cursor(); c.execute("SELECT user_a,user_b,status,chat_id,thread_id,message_id FROM pokemon_trades_tb WHERE trade_id=%s FOR UPDATE",(tid,)); tr=c.fetchone()
            if not tr or tr[2] not in ('selecting','confirming') or uid not in (int(tr[0]),int(tr[1])):conn.rollback(); return await q.answer('Intercambio no disponible.',show_alert=True)
            c.execute("SELECT 1 FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid))
            if not c.fetchone():conn.rollback(); return await q.answer('Ese Pokémon ya no es tuyo.',show_alert=True)
            col='pokemon_a' if uid==int(tr[0]) else 'pokemon_b'
            c.execute(f"UPDATE pokemon_trades_tb SET {col}=%s,confirm_a=FALSE,confirm_b=FALSE,status='selecting',updated_at=NOW() WHERE trade_id=%s",(pid,tid))
            c.execute("SELECT pokemon_a,pokemon_b FROM pokemon_trades_tb WHERE trade_id=%s",(tid,)); pa,pb=c.fetchone(); ready=bool(pa and pb)
            if ready:c.execute("UPDATE pokemon_trades_tb SET status='confirming',updated_at=NOW() WHERE trade_id=%s",(tid,))
            atext=_trade_mon_text_cursor(c,int(tr[0]),pa); btext=_trade_mon_text_cursor(c,int(tr[1]),pb)
            summary=f'🔄 INTERCAMBIO POKÉMON\n\nJugador A ofrece:\n{atext}\n\nJugador B ofrece:\n{btext}'
            chat_id=int(tr[3]); thread_id=tr[4]; msgid=tr[5]; conn.commit()
        except Exception as e:conn.rollback(); print('[PK trade offer]',type(e).__name__,e); return await q.answer('No pude guardar tu oferta.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Oferta guardada ✅',show_alert=True)
        if ready:
            kb=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Confirmar intercambio',callback_data=f'pk:tradeconfirm:{tid}')],[InlineKeyboardButton('🔄 Cambiar mi Pokémon',callback_data=f'pk:tradepick:{tid}:0'),InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:tradecancel:{tid}')]])
            text=summary+'\n\nAmbos deben confirmar. El intercambio conserva nivel, XP, apodo, foto/GIF y condición Shiny.'
        else:
            kb=InlineKeyboardMarkup([[InlineKeyboardButton('🔄 Elegir mi Pokémon',callback_data=f'pk:tradepick:{tid}:0')],[InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:tradecancel:{tid}')]])
            text=summary+'\n\nFalta que la otra persona elija.'
        try:await context.bot.edit_message_text(chat_id=chat_id,message_id=msgid,text=text,reply_markup=kb)
        except Exception:
            try:await context.bot.send_message(chat_id,text,message_thread_id=thread_id,reply_markup=kb)
            except Exception:pass
        return
    if action=='tradecancel':
        tid=int(p[2]); conn=_get_connection(); ok=False
        try:
            c=conn.cursor(); c.execute("UPDATE pokemon_trades_tb SET status='cancelled',finished_at=NOW(),updated_at=NOW() WHERE trade_id=%s AND status IN ('selecting','confirming') AND (user_a=%s OR user_b=%s) RETURNING trade_id",(tid,uid,uid)); ok=bool(c.fetchone()); conn.commit()
        except Exception:conn.rollback()
        finally:_put_connection(conn)
        if not ok:return await q.answer('Ese intercambio ya terminó.',show_alert=True)
        await q.answer('Intercambio cancelado.');
        try:return await q.edit_message_text('❌ Intercambio Pokémon cancelado.')
        except Exception:return
    if action=='tradeconfirm':
        tid=int(p[2]); conn=_get_connection(); finished=False; result_text=None; chat_id=None; thread_id=None; msgid=None
        try:
            c=conn.cursor(); c.execute("SELECT user_a,user_b,pokemon_a,pokemon_b,confirm_a,confirm_b,status,chat_id,thread_id,message_id FROM pokemon_trades_tb WHERE trade_id=%s FOR UPDATE",(tid,)); tr=c.fetchone()
            if not tr or tr[6]!='confirming' or uid not in (int(tr[0]),int(tr[1])):conn.rollback(); return await q.answer('Intercambio no disponible.',show_alert=True)
            ua,ub,pa,pb=int(tr[0]),int(tr[1]),int(tr[2]),int(tr[3])
            if _battle_busy_cursor(c,ua) or _battle_busy_cursor(c,ub):conn.rollback(); return await q.answer('No se puede cerrar un intercambio mientras alguno está en batalla.',show_alert=True)
            if uid==ua:c.execute("UPDATE pokemon_trades_tb SET confirm_a=TRUE,updated_at=NOW() WHERE trade_id=%s",(tid,))
            else:c.execute("UPDATE pokemon_trades_tb SET confirm_b=TRUE,updated_at=NOW() WHERE trade_id=%s",(tid,))
            c.execute("SELECT confirm_a,confirm_b FROM pokemon_trades_tb WHERE trade_id=%s",(tid,)); ca,cb=c.fetchone()
            chat_id=int(tr[7]); thread_id=tr[8]; msgid=tr[9]
            if not (ca and cb):conn.commit(); result_text='✅ Confirmaste. Falta la otra persona.'
            else:
                c.execute("SELECT pokemon_id,owner_id,species_id,nickname,level,shiny FROM pokemon_instances_tb WHERE pokemon_id IN (%s,%s) FOR UPDATE",(pa,pb)); rr={int(x[0]):x for x in c.fetchall()}
                if pa not in rr or pb not in rr or int(rr[pa][1])!=ua or int(rr[pb][1])!=ub:conn.rollback(); return await q.answer('Una de las ofertas ya no está disponible.',show_alert=True)
                # Los sacamos de sus equipos viejos para no dejar referencias cruzadas.
                for owner,pid in ((ua,pa),(ub,pb)):
                    for slot in (1,2,3):c.execute(f"UPDATE pokemon_team_tb SET slot{slot}=NULL,updated_at=NOW() WHERE owner_id=%s AND slot{slot}=%s",(owner,pid))
                c.execute("UPDATE pokemon_instances_tb SET owner_id=%s,updated_at=NOW() WHERE pokemon_id=%s",(ub,pa))
                c.execute("UPDATE pokemon_instances_tb SET owner_id=%s,updated_at=NOW() WHERE pokemon_id=%s",(ua,pb))
                evo_notes=[]
                for new_owner,pid,row in ((ub,pa,rr[pa]),(ua,pb,rr[pb])):
                    oldsid=int(row[2]); target=TRADE_EVOLUTIONS.get(oldsid)
                    finalsid=oldsid
                    if target:
                        finalsid=target; moves=available_moves(target,int(row[4])); c.execute("UPDATE pokemon_instances_tb SET species_id=%s,moves_json=%s,updated_at=NOW() WHERE pokemon_id=%s",(target,json.dumps(moves,ensure_ascii=False),pid)); evo_notes.append(f"✨ {row[3] or NAMES[oldsid]} evolucionó a {NAMES[target]} por intercambio.")
                    c.execute("""INSERT INTO pokemon_pokedex_tb(owner_id,species_id,obtained_count) VALUES(%s,%s,1)
                                 ON CONFLICT(owner_id,species_id) DO UPDATE SET obtained_count=pokemon_pokedex_tb.obtained_count+1,last_obtained_at=NOW()""",(new_owner,finalsid))
                c.execute("UPDATE pokemon_trades_tb SET status='done',finished_at=NOW(),updated_at=NOW() WHERE trade_id=%s",(tid,)); conn.commit(); finished=True
                result_text='🔄 ¡INTERCAMBIO COMPLETADO!\n\nLos Pokémon conservaron nivel, XP, apodo, foto/GIF y Shiny.'+('\n\n'+'\n'.join(evo_notes) if evo_notes else '')
        except Exception as e:conn.rollback(); print('[PK trade confirm]',type(e).__name__,e); return await q.answer('No pude completar el intercambio.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Confirmado ✅',show_alert=True)
        if finished:
            try:await context.bot.edit_message_text(chat_id=chat_id,message_id=msgid,text=result_text)
            except Exception:
                try:await context.bot.send_message(chat_id,result_text,message_thread_id=thread_id)
                except Exception:pass
        return

    # ---- callbacks de batalla ----
    if action=='cancelchallenge':
        bid=int(p[2]); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("UPDATE pokemon_battles_tb SET status='cancelled',updated_at=NOW() WHERE battle_id=%s AND challenger_id=%s AND status='open' RETURNING battle_id",(bid,uid)); ok=c.fetchone(); conn.commit()
        except Exception:conn.rollback(); ok=None
        finally:_put_connection(conn)
        if not ok:return await q.answer('Ya no puedes cancelar ese reto.',show_alert=True)
        await q.answer('Reto cancelado.'); return await q.edit_message_text('❌ Reto Pokémon cancelado.')
    if action=='accept':
        bid=int(p[2]); mode=int(p[3]); conn=_get_connection(); state=None
        try:
            c=conn.cursor(); c.execute("SELECT challenger_id,opponent_id,status,chat_id,thread_id FROM pokemon_battles_tb WHERE battle_id=%s FOR UPDATE",(bid,)); br=c.fetchone()
            if not br or br[2]!='open':conn.rollback(); return await q.answer('Ese reto ya no está disponible.',show_alert=True)
            challenger=int(br[0]); invited=int(br[1]) if br[1] is not None else None
            if uid==challenger:conn.rollback(); return await q.answer('El rival debe aceptar.',show_alert=True)
            if invited is not None and uid!=invited:conn.rollback(); return await q.answer('Este reto era para otra persona.',show_alert=True)
            a=_team_for_battle_cursor(c,challenger,mode); b=_team_for_battle_cursor(c,uid,mode)
            if not a or not b:conn.rollback(); return await q.answer(f'Los dos necesitan {mode} Pokémon colocados en los primeros {mode} espacios del equipo.',show_alert=True)
            state={'status':'active','mode':mode,'round':1,'choices':{},'players':{str(challenger):{'name':_display_name_cursor(c,challenger),'mons':a,'active':0},str(uid):{'name':_display_name_cursor(c,uid),'mons':b,'active':0}}}
            c.execute("UPDATE pokemon_battles_tb SET opponent_id=%s,mode=%s,status='active',state_json=%s,message_id=%s,updated_at=NOW() WHERE battle_id=%s",(uid,mode,json.dumps(state,ensure_ascii=False),q.message.message_id,bid)); conn.commit()
        except Exception as e:conn.rollback(); print('[PK accept]',e); return await q.answer('No pude iniciar la batalla.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('¡Batalla aceptada!'); await q.edit_message_text(_battle_text(state,'Toca “Elegir acción”. PiBot te mostrará tus movimientos por privado.'),reply_markup=_battle_markup(bid)); return
    if action=='action':
        bid=int(p[2]); br=_get_battle(bid)
        if not br or br[6]!='active':return await q.answer('La batalla ya terminó.',show_alert=True)
        state=json.loads(br[7]); key=str(uid)
        if key not in state['players']:return await q.answer('No participas en esta batalla.',show_alert=True)
        mon=state['players'][key]['mons'][state['players'][key]['active']]
        try:await context.bot.send_message(uid,f"⚔️ {_battle_title_mon(mon)} · Nv.{mon['level']}\nElige tu acción de la ronda {state['round']}:",reply_markup=_move_menu(bid,mon)); await q.answer('Te mandé tus opciones por privado.')
        except Exception:return await q.answer('Abre primero el privado de PiBot con /start.',show_alert=True)
        return
    if action in ('move','bswitch','bitem'):
        bid=int(p[2]); conn=_get_connection(); final=None; state=None; logs=[]
        try:
            c=conn.cursor(); c.execute("SELECT state_json,status,chat_id,thread_id,message_id FROM pokemon_battles_tb WHERE battle_id=%s FOR UPDATE",(bid,)); br=c.fetchone()
            if not br or br[1]!='active':conn.rollback(); return await q.answer('La batalla ya terminó.',show_alert=True)
            state=json.loads(br[0]); key=str(uid)
            if key not in state['players']:conn.rollback(); return await q.answer('No participas en esta batalla.',show_alert=True)
            if key in state.get('choices',{}):conn.rollback(); return await q.answer('Ya elegiste en esta ronda.',show_alert=True)
            player=state['players'][key]
            if action=='move':
                idx=int(p[3]); mon=player['mons'][player['active']]
                if idx<0 or idx>=len(mon['moves']):conn.rollback(); return await q.answer('Movimiento inválido.',show_alert=True)
                code=mon['moves'][idx]
                if int(mon.get('pp',{}).get(code,0))<=0:conn.rollback(); return await q.answer('Ese movimiento ya no tiene PP.',show_alert=True)
                state.setdefault('choices',{})[key]={'type':'move','move':code}
            elif action=='bswitch':
                idx=int(p[3]);
                if idx<0 or idx>=len(player['mons']) or idx==player['active'] or player['mons'][idx]['hp']<=0:conn.rollback(); return await q.answer('No puedes cambiar a ese Pokémon.',show_alert=True)
                state.setdefault('choices',{})[key]={'type':'switch','index':idx}
            else:
                code=p[3]
                if code not in ITEMS or ITEMS[code][3] not in ('heal','revive'):conn.rollback(); return await q.answer('Ese objeto no se usa en batalla.',show_alert=True)
                state.setdefault('choices',{})[key]={'type':'item','item':code}
            winner,logs,state=_resolve_round_cursor(c,bid,state)
            if winner is not None:
                final=_finish_battle_cursor(c,bid,state)
            else:
                c.execute("UPDATE pokemon_battles_tb SET state_json=%s,updated_at=NOW() WHERE battle_id=%s",(json.dumps(state,ensure_ascii=False),bid))
            conn.commit(); chat_id=int(br[2]); thread_id=br[3]; msgid=br[4]
        except Exception as e:conn.rollback(); print('[PK action]',type(e).__name__,e); return await q.answer('No pude registrar la acción.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Acción elegida ✅')
        # Actualiza mensaje de grupo. Si todavía falta el rival, solo marca la elección.
        note='\n'.join(logs[-8:]) if logs else 'Esperando la elección del rival…'
        try:
            await context.bot.edit_message_text(chat_id=chat_id,message_id=q.message.message_id if q.message and q.message.chat_id==chat_id else msgid,text=_battle_text(state,note),reply_markup=None if final else _battle_markup(bid))
        except Exception:
            try:await context.bot.send_message(chat_id, _battle_text(state,note),message_thread_id=thread_id,reply_markup=None if final else _battle_markup(bid))
            except Exception:pass
        if final:
            try:
                from handlers.season_pass import grant_season_xp
                wx=grant_season_xp(final['winner'],WIN_SEASON_XP,'pokemon_battle'); lx=grant_season_xp(final['loser'],LOSS_SEASON_XP,'pokemon_battle')
            except Exception:wx=lx=None
            wname=state['players'][str(final['winner'])]['name']; lname=state['players'][str(final['loser'])]['name']
            lines=[f"🏆 {wname} ganó la batalla Pokémon.",f"💰 {wname}: +{WIN_PIPESOS:,} PiPesos · ⭐ +{WIN_SEASON_XP} XP de temporada",f"💰 {lname}: +{LOSS_PIPESOS:,} PiPesos · ⭐ +{LOSS_SEASON_XP} XP de temporada",f"🎮 Pokémon: ganador +{WIN_POKEMON_XP} XP c/u · rival +{LOSS_POKEMON_XP} XP c/u",f"📈 Ranking: ±{final['elo']} puntos"]+final['notes'][:6]
            try:await context.bot.send_message(chat_id,'\n'.join(lines),message_thread_id=thread_id)
            except Exception:pass
        return
    if action=='bswitchmenu':
        bid=int(p[2]); br=_get_battle(bid)
        if not br or br[6]!='active':return await q.answer('Batalla terminada.',show_alert=True)
        state=json.loads(br[7]); key=str(uid)
        if key not in state['players']:return await q.answer('No participas.',show_alert=True)
        pl=state['players'][key]; rows=[]
        for i,m in enumerate(pl['mons']):
            if i!=pl['active'] and m['hp']>0:rows.append([InlineKeyboardButton(f"🔄 {_battle_title_mon(m)} · {m['hp']}/{m['max_hp']} HP",callback_data=f'pk:bswitch:{bid}:{i}')])
        if not rows:return await q.answer('No tienes otro Pokémon disponible.',show_alert=True)
        await q.answer(); return await q.message.reply_text('Elige cambio para esta ronda:',reply_markup=InlineKeyboardMarkup(rows))
    if action=='bitemmenu':
        bid=int(p[2]); conn=_get_connection()
        try:c=conn.cursor(); c.execute("SELECT item_code,qty FROM pokemon_items_tb WHERE owner_id=%s AND qty>0",(uid,)); inv=c.fetchall()
        finally:_put_connection(conn)
        rows=[]
        for code,qty in inv:
            if code in ITEMS and ITEMS[code][3] in ('heal','revive'):
                name,em,_,_=ITEMS[code]; rows.append([InlineKeyboardButton(f'{em} {name} ×{qty}',callback_data=f'pk:bitem:{bid}:{code}')])
        if not rows:return await q.answer('No tienes objetos utilizables en batalla.',show_alert=True)
        await q.answer(); return await q.message.reply_text('🎒 Elige objeto para esta ronda:',reply_markup=InlineKeyboardMarkup(rows))
    if action=='surrender':
        bid=int(p[2]); conn=_get_connection(); final=None; state=None; chat_id=None; thread_id=None
        try:
            c=conn.cursor(); c.execute("SELECT state_json,status,chat_id,thread_id FROM pokemon_battles_tb WHERE battle_id=%s FOR UPDATE",(bid,)); br=c.fetchone()
            if not br or br[1]!='active':conn.rollback(); return await q.answer('Ya terminó.',show_alert=True)
            state=json.loads(br[0]); key=str(uid)
            if key not in state['players']:conn.rollback(); return await q.answer('No participas.',show_alert=True)
            ids=list(state['players'].keys()); other=int(ids[1] if key==ids[0] else ids[0]); state['status']='finished'; state['winner']=other; state['loser']=uid; final=_finish_battle_cursor(c,bid,state); conn.commit(); chat_id=int(br[2]); thread_id=br[3]
        except Exception:conn.rollback(); return await q.answer('No pude rendirte.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Te rendiste.',show_alert=True)
        try:await context.bot.send_message(chat_id,f"🏳 {state['players'][str(uid)]['name']} se rindió.\n🏆 Gana {state['players'][str(final['winner'])]['name']}.",message_thread_id=thread_id)
        except Exception:pass
        return

    return await q.answer()


async def pokemon_text_input(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type!='private':return
    pid=context.user_data.get('pk_wait_nick')
    if not pid:return
    txt=(update.effective_message.text or '').strip()
    if not txt:return
    name=None if txt=='-' else txt[:24]
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE pokemon_instances_tb SET nickname=%s,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s RETURNING species_id",(name,update.effective_user.id,pid)); ok=c.fetchone(); conn.commit()
    except Exception:conn.rollback(); ok=None
    finally:_put_connection(conn)
    context.user_data.pop('pk_wait_nick',None)
    await update.effective_message.reply_text(f"🏷️ Apodo {'quitado' if name is None else 'guardado: '+name}." if ok else 'No encontré ese Pokémon.')


async def pokemon_media_input(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type!='private':return
    pid=context.user_data.get('pk_wait_media')
    if not pid:return
    m=update.effective_message; media_type=None; file_id=None
    if m.animation:media_type='animation'; file_id=m.animation.file_id
    elif m.photo:media_type='photo'; file_id=m.photo[-1].file_id
    else:return await m.reply_text('Envíame una foto o un GIF/animación de Telegram.')
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE pokemon_instances_tb SET media_type=%s,media_file_id=%s,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s RETURNING species_id",(media_type,file_id,update.effective_user.id,pid)); ok=c.fetchone(); conn.commit()
    except Exception:conn.rollback(); ok=None
    finally:_put_connection(conn)
    context.user_data.pop('pk_wait_media',None)
    await m.reply_text('🎞️ GIF guardado.' if ok and media_type=='animation' else '🖼️ Foto guardada.' if ok else 'No encontré ese Pokémon.')
