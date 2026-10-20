from __future__ import annotations

import asyncio
import json
import math
import random
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database.database import _get_connection, _put_connection, is_botmaster
from src.config import COMUNIDADES, obtener_temas_por_comunidad
from handlers.pokemon_gen1_data import (
    NAMES, TYPES, MOVES, ITEMS, TM_ITEMS, LEVEL_EVOLUTIONS, STONE_EVOLUTIONS,
    TRADE_EVOLUTIONS, LEGENDARY_IDS, EPIC_IDS, RARE_IDS, PHYSICAL_TYPES,
    available_moves, battle_base_stats, effectiveness, rarity_for, can_learn_tm,
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

# Capturas salvajes: aparecen solo en el tema Juegos y Casino.
WILD_SHINY_DENOMINATOR = 200  # 0.5% por aparición salvaje
WILD_MAX_ATTEMPTS = 2
WILD_DICE_ANIMATION_SECONDS = 4.2  # espera a que termine la animacion del dado en Telegram
WILD_LIFETIME_SECONDS = 600  # 10 minutos visible antes de irse
WILD_CATCH_THRESHOLD = {"comun": 3, "raro": 4, "epico": 5, "legendario": 6}
CANDIES_PER_LEVEL = 10


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
        # DVs/IVs estilo Gen 1: 0-15. HP se deriva de los otros cuatro.
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS iv_atk SMALLINT")
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS iv_def SMALLINT")
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS iv_spd SMALLINT")
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS iv_spc SMALLINT")
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS iv_hp SMALLINT")
        c.execute("""
            UPDATE pokemon_instances_tb SET
              iv_atk=COALESCE(iv_atk,FLOOR(random()*16)::int),
              iv_def=COALESCE(iv_def,FLOOR(random()*16)::int),
              iv_spd=COALESCE(iv_spd,FLOOR(random()*16)::int),
              iv_spc=COALESCE(iv_spc,FLOOR(random()*16)::int)
            WHERE iv_atk IS NULL OR iv_def IS NULL OR iv_spd IS NULL OR iv_spc IS NULL
        """)
        c.execute("""
            UPDATE pokemon_instances_tb SET iv_hp=
              ((iv_atk & 1)*8)+((iv_def & 1)*4)+((iv_spd & 1)*2)+(iv_spc & 1)
            WHERE iv_hp IS NULL
        """)
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
        c.execute("ALTER TABLE pokemon_team_tb ADD COLUMN IF NOT EXISTS principal_pokemon_id BIGINT")
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
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_trainer_tb(
              user_id BIGINT PRIMARY KEY,
              wild_catches INT NOT NULL DEFAULT 0,
              released INT NOT NULL DEFAULT 0,
              candies_earned INT NOT NULL DEFAULT 0,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_candies_tb(
              owner_id BIGINT NOT NULL,
              family_species_id SMALLINT NOT NULL CHECK(family_species_id BETWEEN 1 AND 151),
              qty INT NOT NULL DEFAULT 0,
              PRIMARY KEY(owner_id,family_species_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_wild_spawns_tb(
              spawn_id BIGSERIAL PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT,
              species_id SMALLINT NOT NULL CHECK(species_id BETWEEN 1 AND 151),
              level SMALLINT NOT NULL CHECK(level BETWEEN 1 AND 100),
              shiny BOOLEAN NOT NULL DEFAULT FALSE,
              status TEXT NOT NULL DEFAULT 'active',
              message_id BIGINT,
              caught_by BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_wild_active ON pokemon_wild_spawns_tb(chat_id,thread_id,status)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_wild_attempts_tb(
              spawn_id BIGINT NOT NULL,
              user_id BIGINT NOT NULL,
              attempts SMALLINT NOT NULL DEFAULT 0,
              PRIMARY KEY(spawn_id,user_id)
            )
        """)
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


def _games_topic(chat_id:int):
    topics = obtener_temas_por_comunidad(chat_id) or {}
    return topics.get("theme_juegosYcasino")


def _is_games_topic(update:Update)->bool:
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg or chat.type == 'private':
        return False
    return getattr(msg, 'message_thread_id', None) == _games_topic(chat.id)


def _family_root(species_id:int)->int:
    # Raíz de familia evolutiva Gen 1. Eevee y evoluciones por piedra/intercambio
    # quedan en la misma familia para que los repetidos siempre tengan utilidad.
    reverse = {}
    for src, (_, dst) in LEVEL_EVOLUTIONS.items():
        reverse[int(dst)] = int(src)
    for src, mapping in STONE_EVOLUTIONS.items():
        for dst in mapping.values():
            reverse[int(dst)] = int(src)
    for src, dst in TRADE_EVOLUTIONS.items():
        reverse[int(dst)] = int(src)
    cur = int(species_id)
    seen = set()
    while cur in reverse and cur not in seen:
        seen.add(cur)
        cur = reverse[cur]
    return cur


def _release_candies(level:int, iv_percent:int, shiny:bool)->int:
    base = min(6, 1 + max(0, int(level)-1)//10)
    iv_bonus = 2 if int(iv_percent) >= 100 else (1 if int(iv_percent) >= 90 else 0)
    shiny_bonus = 2 if shiny else 0
    return base + iv_bonus + shiny_bonus


def _ensure_trainer_row_cursor(c, uid:int):
    c.execute("INSERT INTO pokemon_trainer_tb(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (uid,))


def _wild_species()->int:
    legendary = list(LEGENDARY_IDS)
    epic = list(EPIC_IDS)
    rare = list(RARE_IDS)
    used = set(legendary) | set(epic) | set(rare)
    common = [i for i in range(1,152) if i not in used]
    rarity = random.choices(['comun','raro','epico','legendario'], [70,24,5.5,0.5], k=1)[0]
    return random.choice({'comun':common,'raro':rare,'epico':epic,'legendario':legendary}[rarity])


def _display_name_cursor(c, uid:int)->str:
    c.execute("SELECT COALESCE(NULLIF(nombre,''),NULLIF(username,''),%s) FROM perfiles_tb WHERE id_user=%s", (f'Jugador {uid}', uid))
    r = c.fetchone()
    return str(r[0]) if r and r[0] else f'Jugador {uid}'


def _dex_name(species:int)->str:
    species=int(species)
    return f"#{species:03d} {NAMES.get(species, 'Pokémon')}"


def _pokemon_label(row)->str:
    # row: id, species, nickname, level, ...
    # El número visible es SIEMPRE el de la Pokédex. El pokemon_id interno solo
    # identifica el ejemplar en PostgreSQL y no debe confundirse con la Pokédex.
    pid, species, nickname, level = int(row[0]), int(row[1]), row[2], int(row[3])
    base = NAMES.get(species, 'Pokémon')
    shown = f'{nickname} ({base})' if nickname else base
    shiny = bool(row[10]) if len(row) > 10 else False
    return f"#{species:03d} · {'✨ ' if shiny else ''}{shown} · Nv.{level}"


def _types_text(species_id:int)->str:
    return ' / '.join(f'{type_emoji(t)} {t}' for t in TYPES.get(species_id, ('Normal',)))


def _ensure_team_row_cursor(c, uid:int):
    c.execute("INSERT INTO pokemon_team_tb(owner_id) VALUES(%s) ON CONFLICT DO NOTHING", (uid,))


def _principal_pid(uid:int)->int|None:
    conn=_get_connection()
    try:
        c=conn.cursor(); _ensure_team_row_cursor(c,uid)
        c.execute("SELECT principal_pokemon_id FROM pokemon_team_tb WHERE owner_id=%s",(uid,))
        r=c.fetchone(); pid=int(r[0]) if r and r[0] else None
        if pid:
            c.execute("SELECT 1 FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid))
            if not c.fetchone():
                c.execute("UPDATE pokemon_team_tb SET principal_pokemon_id=NULL,updated_at=NOW() WHERE owner_id=%s",(uid,)); conn.commit(); pid=None
        return pid
    finally:_put_connection(conn)


def _is_principal(uid:int,pid:int)->bool:
    return _principal_pid(uid)==int(pid)


def _roll_ivs(force_perfect:bool=False)->dict:
    if force_perfect:
        atk=defn=spd=spc=15
    else:
        atk,defn,spd,spc=(random.randint(0,15) for _ in range(4))
    hp=((atk & 1)*8)+((defn & 1)*4)+((spd & 1)*2)+(spc & 1)
    return {'atk':atk,'def':defn,'spd':spd,'spc':spc,'hp':hp}


def _iv_values(row)->dict:
    # SELECT base mantiene shiny en 10 e IVs en 11..15.
    if row and len(row)>=16:
        vals=row[11:16]
        if all(v is not None for v in vals):
            return {'atk':int(vals[0]),'def':int(vals[1]),'spd':int(vals[2]),'spc':int(vals[3]),'hp':int(vals[4])}
    return {'atk':0,'def':0,'spd':0,'spc':0,'hp':0}


def _iv_percent(ivs:dict)->int:
    return round(sum(int(ivs.get(k,0)) for k in ('hp','atk','def','spc','spd'))/75*100)


def _iv_grade(pct:int)->str:
    if pct>=100:return 'PERFECTO'
    if pct>=95:return 'Casi perfecto'
    if pct>=85:return 'Excelente'
    if pct>=70:return 'Muy bueno'
    if pct>=55:return 'Bueno'
    if pct>=40:return 'Normal'
    return 'Bajo'


def grant_pokemon_with_cursor(c, uid:int, species_id:int, source:str='caja', force_shiny:bool=False, force_perfect:bool=False, level_override:int|None=None, shiny_override:bool|None=None)->dict:
    species_id = max(1, min(151, int(species_id)))
    level = max(1, min(MAX_LEVEL, int(level_override))) if level_override is not None else _starting_level(species_id)
    moves = available_moves(species_id, level)
    # Shiny es puramente cosmético y MUY raro: 1 entre 4096.
    shiny = bool(shiny_override) if shiny_override is not None else bool(force_shiny or random.randrange(4096) == 0)
    ivs = _roll_ivs(force_perfect)
    c.execute("""
        INSERT INTO pokemon_instances_tb(owner_id,species_id,level,xp,moves_json,obtained_from,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING pokemon_id
    """, (uid, species_id, level, _xp_floor(level), json.dumps(moves, ensure_ascii=False), source, shiny,
              ivs['atk'],ivs['def'],ivs['spd'],ivs['spc'],ivs['hp']))
    pid = int(c.fetchone()[0])
    c.execute("""
        INSERT INTO pokemon_pokedex_tb(owner_id,species_id,obtained_count)
        VALUES(%s,%s,1)
        ON CONFLICT(owner_id,species_id) DO UPDATE SET
          obtained_count=pokemon_pokedex_tb.obtained_count+1,last_obtained_at=NOW()
    """, (uid, species_id))
    _ensure_team_row_cursor(c, uid)
    # El primer Pokémon obtenido queda como principal hasta que el dueño elija otro.
    c.execute("UPDATE pokemon_team_tb SET principal_pokemon_id=COALESCE(principal_pokemon_id,%s),updated_at=NOW() WHERE owner_id=%s",(pid,uid))
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
        'iv_percent': _iv_percent(ivs), 'iv_grade': _iv_grade(_iv_percent(ivs)),
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
    # Las MT de Gen 1 pueden salir como objeto de caja; la Legendaria tiene
    # mejor probabilidad. Siguen siendo consumibles de un solo uso.
    tm_codes=list(TM_ITEMS)
    if tm_codes and random.random() < (0.50 if box_code=='legendary' else 0.35):
        return random.choice(tm_codes)
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
        c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp
                     FROM pokemon_instances_tb WHERE owner_id=%s ORDER BY pokemon_id LIMIT %s""", (uid,limit))
        return c.fetchall()
    finally:
        _put_connection(conn)


def _get_instance(uid:int, pid:int):
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp
                     FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s""", (uid,pid))
        return c.fetchone()
    finally:
        _put_connection(conn)


def _collection_markup(uid:int, page:int=0, prefix:str='detail'):
    mons = _get_owned(uid)
    principal=_principal_pid(uid)
    pages = max(1, math.ceil(len(mons)/PAGE_SIZE))
    page = max(0,min(page,pages-1))
    chunk = mons[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
    rows=[]
    for r in chunk:
        species=int(r[1])
        name = (r[2] or NAMES[species])[:20]
        star='⭐ ' if principal==int(r[0]) else ''
        rows.append([InlineKeyboardButton(f"{star}{rarity_emoji(rarity_for(species))} #{species:03d} {name} · Nv.{r[3]}", callback_data=f'pk:{prefix}:{r[0]}:{page}')])
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
    principal=_principal_pid(uid)
    text=(f"🎮 TUS POKÉMON · {len(mons)} ejemplares\n\n"
          "Tu colección y tu equipo son privados. Toca uno para verlo, ponerle apodo, foto/GIF/video, hacerlo principal o meterlo al equipo."
          + ("\n⭐ El Pokémon con estrella es tu principal." if principal else ""))
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
            c.execute("SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); out.append(c.fetchone())
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
    lines += ['', 'Las piedras, Cable Link, Caramelo Raro y MT se usan fuera de combate. Las MT enseñan un movimiento compatible y se consumen al usarlas. Las pociones/Revivir aparecen durante una batalla.']
    return '\n'.join(lines)


def _items_markup(uid:int):
    conn=_get_connection(); rows=[]
    try:
        c=conn.cursor(); c.execute("SELECT item_code,qty FROM pokemon_items_tb WHERE owner_id=%s AND qty>0",(uid,)); inv=c.fetchall()
    finally:_put_connection(conn)
    for code,qty in inv:
        if code in ITEMS and ITEMS[code][3] in ('evolution','trade_evolution','level','tm'):
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
        return await update.effective_message.reply_text('🎞️ La foto/GIF/video de tus Pokémon se configura por privado con /fotopokemon.')
    await update.effective_message.reply_text('Elige el Pokémon al que quieres poner foto, GIF o video:',reply_markup=_collection_markup(update.effective_user.id,0,'mediaselect'))


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
    target={'chat_id':uid,'thread_id':None} if update.effective_chat.type=='private' else {'chat_id':update.effective_chat.id,'thread_id':getattr(update.effective_message,'message_thread_id',None)}
    principal=_principal_pid(uid)
    if principal:
        ok=await _send_brag(context,uid,principal,target)
        if not ok:
            return await update.effective_message.reply_text('No pude presumir tu Pokémon principal.')
        return
    context.user_data['pk_brag_target']=target
    try:
        await context.bot.send_message(uid,'😎 Aún no tienes Pokémon principal. Elige uno para presumir; desde su ficha puedes marcarlo como ⭐ Principal.',reply_markup=_collection_markup(uid,0,'brag'))
    except Exception:
        return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private': await update.effective_message.reply_text('📩 No tienes principal todavía; te mandé tu colección por privado.')


async def _send_brag(context, uid:int, pid:int, target:dict):
    row=_get_instance(uid,pid)
    if not row:return False
    species=int(row[1]); nickname=row[2]; level=int(row[3]); media_type=row[6]; file_id=row[7]; wins=int(row[8]); losses=int(row[9]); shiny=bool(row[10]) if len(row)>10 else False
    conn=_get_connection()
    try:
        c=conn.cursor(); owner=_display_name_cursor(c,uid)
    finally:_put_connection(conn)
    title=nickname or NAMES[species]
    ivs=_iv_values(row); ivpct=_iv_percent(ivs); principal=_is_principal(uid,pid)
    principal_line='⭐ PRINCIPAL\n' if principal else ''
    caption=(f"✨ POKÉMON DE {owner}\n"
             f"{principal_line}"
             f"{rarity_emoji(rarity_for(species))} #{species:03d} {'✨ SHINY · ' if shiny else ''}{title}\n"
             f"{NAMES[species]} · Nv.{level}\n"
             f"{_types_text(species)}\n"
             f"🧬 IV: {ivpct}% · {_iv_grade(ivpct)}\n"
             f"⚔️ {wins}V / {losses}D\n\n"
             "Su equipo y sus movimientos siguen siendo privados.")
    kwargs={'chat_id':target['chat_id'],'message_thread_id':target.get('thread_id')}
    try:
        if media_type=='photo' and file_id: await context.bot.send_photo(photo=file_id,caption=caption,**kwargs)
        elif media_type=='animation' and file_id: await context.bot.send_animation(animation=file_id,caption=caption,**kwargs)
        elif media_type=='video' and file_id: await context.bot.send_video(video=file_id,caption=caption,**kwargs)
        else: await context.bot.send_message(text=caption,**kwargs)
        return True
    except Exception:return False


# ------------------------------ BATALLAS ------------------------------
def _stat_value(species:int,level:int,key:str,iv:int=0)->int:
    b=battle_base_stats(species)[key]
    # Fórmula estilo Gen 1 sin Stat Exp: el DV/IV 0-15 sí modifica la estadística real.
    if key=='hp': return int((2*(b+int(iv))*level)/100)+level+10
    return int((2*(b+int(iv))*level)/100)+5


def _battle_mon(row)->dict:
    pid,species,nick,level,xp,moves_json,_,_,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp=row
    species=int(species); level=int(level)
    try:moves=json.loads(moves_json or '[]')
    except Exception:moves=[]
    if not moves:moves=available_moves(species,level)
    ivs={'atk':int(iv_atk or 0),'def':int(iv_def or 0),'spd':int(iv_spd or 0),'spc':int(iv_spc or 0),'hp':int(iv_hp or 0)}
    hp=_stat_value(species,level,'hp',ivs['hp'])
    return {'pid':int(pid),'species':species,'nickname':nick,'level':level,'hp':hp,'max_hp':hp,'moves':moves,'pp':{m:MOVES[m][4] for m in moves if m in MOVES},'status':None,'sleep':0,'stages':{'atk':0,'def':0,'spd':0},'shiny':bool(shiny),'ivs':ivs}


def _team_for_battle_cursor(c,uid:int,mode:int):
    _ensure_team_row_cursor(c,uid)
    c.execute("SELECT slot1,slot2,slot3 FROM pokemon_team_tb WHERE owner_id=%s",(uid,)); slots=list(c.fetchone() or (None,None,None))[:mode]
    if len(slots)<mode or any(x is None for x in slots):return None
    mons=[]
    for pid in slots:
        c.execute("SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); r=c.fetchone()
        if not r:return None
        mons.append(_battle_mon(r))
    return mons


def _battle_title_mon(mon:dict)->str:
    species=int(mon['species']); base=NAMES[species]; name=mon.get('nickname') or base
    shown=f"{name} ({base})" if mon.get('nickname') else base
    shiny=f"✨ {shown}" if mon.get('shiny') else shown
    return f"#{species:03d} {shiny}"


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
    val=_stat_value(mon['species'],mon['level'],'spd',mon.get('ivs',{}).get('spd',0))*_stage_mult(mon['stages'].get('spd',0))
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
        A=_stat_value(att['species'],att['level'],atk_key,att.get('ivs',{}).get(atk_key,0))*_stage_mult(att['stages'].get('atk',0) if atk_key=='atk' else 0)
        D=_stat_value(defn['species'],defn['level'],def_key,defn.get('ivs',{}).get(def_key,0))*_stage_mult(defn['stages'].get('def',0) if def_key=='def' else 0)
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
    if update.effective_chat.type=='private':return await update.effective_message.reply_text('⚔️ Las batallas Pokémon se retan en el tema Juegos y Casino.')
    if not _is_games_topic(update):return await update.effective_message.reply_text('⚠️ Las batallas Pokémon solo se pueden iniciar en el tema Juegos y Casino.')
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
    c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp
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
        c=conn.cursor(); c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp
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
    force_perfect=any(str(x).lower() in ('perfect','perfecto','100','iv100') for x in context.args[1:]) if context.args else False
    sid=max(1,min(151,sid)); conn=_get_connection()
    try:
        c=conn.cursor(); data=grant_pokemon_with_cursor(c,update.effective_user.id,sid,'prueba_admin',force_shiny=force_shiny,force_perfect=force_perfect); conn.commit()
    except Exception as e:conn.rollback(); return await update.effective_message.reply_text(f'Error de prueba: {e}')
    finally:_put_connection(conn)
    await update.effective_message.reply_text(f"🧪 Te di #{sid:03d} {'✨ SHINY ' if data.get('shiny') else ''}{NAMES[sid]} Nv.{data['level']} · IV {data.get('iv_percent',0)}% {data.get('iv_grade','')} para probar. No costó PiPesos.")


def _candy_qty(uid:int, family_root:int)->int:
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT qty FROM pokemon_candies_tb WHERE owner_id=%s AND family_species_id=%s",(uid,family_root)); r=c.fetchone()
        return int(r[0]) if r else 0
    finally:_put_connection(conn)


def _release_markup(uid:int, page:int=0):
    mons=_get_owned(uid); pages=max(1,math.ceil(len(mons)/PAGE_SIZE)); page=max(0,min(page,pages-1))
    chunk=mons[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
    rows=[[InlineKeyboardButton(_pokemon_label(r)[:52],callback_data=f'pk:releasepick:{r[0]}:{page}')] for r in chunk]
    nav=[]
    if page>0:nav.append(InlineKeyboardButton('⬅️',callback_data=f'pk:releasepage:{page-1}'))
    nav.append(InlineKeyboardButton(f'{page+1}/{pages}',callback_data='pk:noop'))
    if page<pages-1:nav.append(InlineKeyboardButton('➡️',callback_data=f'pk:releasepage:{page+1}'))
    if nav:rows.append(nav)
    rows.append([InlineKeyboardButton('🎮 Volver a colección',callback_data='pk:list:0')])
    return InlineKeyboardMarkup(rows)


async def liberarpokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    try:
        await context.bot.send_message(uid,
            '🌿 LIBERAR POKÉMON\n\nElige uno. Liberarlo es permanente y te dará caramelos de su familia según nivel, IV y si es Shiny.\n\n⭐ El principal y los Pokémon de tu equipo no se pueden liberar.',
            reply_markup=_release_markup(uid,0))
    except Exception:
        return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private':
        await update.effective_message.reply_text('📩 Te mandé la liberación Pokémon por privado.')


async def caramelospokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT family_species_id,qty FROM pokemon_candies_tb WHERE owner_id=%s AND qty>0 ORDER BY qty DESC,family_species_id",(uid,)); rows=c.fetchall()
    finally:_put_connection(conn)
    lines=['🍬 CARAMELOS POKÉMON','']
    if not rows:lines.append('Todavía no tienes caramelos. Puedes conseguirlos liberando Pokémon repetidos.')
    for root,qty in rows[:60]:lines.append(f'🍬 Familia #{int(root):03d} {NAMES.get(int(root),"Pokémon")}: {int(qty)}')
    lines += ['', f'Cada {CANDIES_PER_LEVEL} caramelos de una familia pueden subir +1 nivel a un Pokémon de esa misma familia.']
    try:await context.bot.send_message(uid,'\n'.join(lines))
    except Exception:return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private':await update.effective_message.reply_text('📩 Te mandé tus caramelos Pokémon por privado.')


async def entrenador_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); _ensure_trainer_row_cursor(c,uid); _ensure_team_row_cursor(c,uid)
        name=_display_name_cursor(c,uid)
        c.execute("SELECT COUNT(*),COUNT(*) FILTER(WHERE shiny=TRUE) FROM pokemon_instances_tb WHERE owner_id=%s",(uid,)); total,shinys=c.fetchone()
        c.execute("SELECT COUNT(*) FROM pokemon_pokedex_tb WHERE owner_id=%s",(uid,)); dex=int(c.fetchone()[0])
        c.execute("SELECT rating,wins,losses,best_streak FROM pokemon_rank_tb WHERE user_id=%s",(uid,)); rank=c.fetchone() or (1000,0,0,0)
        c.execute("SELECT wild_catches,released,candies_earned FROM pokemon_trainer_tb WHERE user_id=%s",(uid,)); tr=c.fetchone() or (0,0,0)
        c.execute("SELECT COALESCE(SUM(qty),0) FROM pokemon_candies_tb WHERE owner_id=%s",(uid,)); candies=int(c.fetchone()[0] or 0)
        c.execute("SELECT principal_pokemon_id FROM pokemon_team_tb WHERE owner_id=%s",(uid,)); pr=c.fetchone(); principal=int(pr[0]) if pr and pr[0] else None
        prow=None
        if principal:
            c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp
                         FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s""",(uid,principal)); prow=c.fetchone()
        conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK trainer]',type(e).__name__,e); return await update.effective_message.reply_text('No pude abrir tu perfil de entrenador.')
    finally:_put_connection(conn)
    lines=[f'🎒 ENTRENADOR POKÉMON · {name}','',f'📖 Pokédex: {dex}/151',f'🎮 Pokémon: {int(total)}',f'✨ Shinys: {int(shinys)}',f'🎯 Capturas salvajes: {int(tr[0])}',f'🌿 Liberados: {int(tr[1])}',f'🍬 Caramelos disponibles: {candies}',f'🏆 Ranking: {int(rank[0])} pts · {int(rank[1])}V/{int(rank[2])}D',f'🔥 Mejor racha: {int(rank[3])}']
    if prow:
        ivpct=_iv_percent(_iv_values(prow)); lines += ['',f'⭐ Principal: {_pokemon_label(prow)}',f'🧬 IV {ivpct}% · {_iv_grade(ivpct)}']
    else:lines += ['','⭐ Principal: todavía no elegido']
    lines += ['','Tu equipo y tus movimientos siguen siendo privados.']
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('🎮 Mi colección',callback_data='pk:trainercollection'),InlineKeyboardButton('😎 Presumir principal',callback_data='pk:trainerbrag')]])
    await update.effective_message.reply_text('\n'.join(lines),reply_markup=kb)


def _wild_text(species:int, level:int, shiny:bool)->str:
    rarity=rarity_for(species); threshold=WILD_CATCH_THRESHOLD[rarity]
    shiny_line='✨ SHINY ✨\n' if shiny else ''
    return (f"🌿 ¡APARECIÓ UN POKÉMON SALVAJE!\n\n"
            f"{shiny_line}"
            f"{rarity_emoji(rarity)} #{species:03d} {NAMES[species]} · Nv.{level}\n"
            f"{_types_text(species)}\n"
            f"⭐ Rareza: {rarity.upper()}\n\n"
            f"🎯 El primer entrenador que pulse Atrapar se queda con el intento.\n"
            f"🎲 Tiene {WILD_MAX_ATTEMPTS} tiros; si falla los dos, el Pokémon se va.\n"
            f"⏳ La aparición dura 10 minutos.\n"
            f"Necesitas {threshold} o más para capturarlo.\n"
            f"1️⃣ pésimo · 2️⃣ flojo · 3️⃣ bien · 4️⃣ muy bien · 5️⃣ excelente · 6️⃣ perfecto")


async def _expire_wild_spawn(context: ContextTypes.DEFAULT_TYPE):
    data = getattr(context.job, 'data', None) or {}
    spawn_id = int(data.get('spawn_id') or 0)
    if not spawn_id:
        return
    conn = _get_connection(); row = None
    try:
        c = conn.cursor()
        c.execute(
            "SELECT species_id,level,shiny,chat_id,thread_id,message_id,status "
            "FROM pokemon_wild_spawns_tb WHERE spawn_id=%s FOR UPDATE",
            (spawn_id,),
        )
        row = c.fetchone()
        # Si ya alguien lanzó el dado antes de cumplirse los 10 min, dejamos terminar ese tiro.
        if not row or row[6] != 'active':
            conn.rollback(); return
        c.execute(
            "UPDATE pokemon_wild_spawns_tb SET status='expired',finished_at=NOW() "
            "WHERE spawn_id=%s",
            (spawn_id,),
        )
        conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK wild expire]', type(e).__name__, e); return
    finally:
        _put_connection(conn)
    try:
        species, level, shiny, chat_id, thread_id, message_id, _ = row
        await context.bot.edit_message_text(
            chat_id=int(chat_id),
            message_id=int(message_id),
            text=_wild_text(int(species), int(level), bool(shiny)) +
                 '\n\n⌛ Pasaron 10 minutos y el Pokémon se fue.',
            reply_markup=None,
        )
    except Exception:
        pass


async def _spawn_wild(context:ContextTypes.DEFAULT_TYPE, chat_id:int, thread_id:int|None)->bool:
    species=_wild_species(); level=min(MAX_LEVEL,_starting_level(species)+random.randint(0,5)); shiny=(random.randrange(WILD_SHINY_DENOMINATOR)==0)
    conn=_get_connection(); spawn_id=None
    try:
        c=conn.cursor()
        c.execute("UPDATE pokemon_wild_spawns_tb SET status='expired',finished_at=NOW() WHERE chat_id=%s AND thread_id IS NOT DISTINCT FROM %s AND status='active'",(chat_id,thread_id))
        c.execute("INSERT INTO pokemon_wild_spawns_tb(chat_id,thread_id,species_id,level,shiny) VALUES(%s,%s,%s,%s,%s) RETURNING spawn_id",(chat_id,thread_id,species,level,shiny)); spawn_id=int(c.fetchone()[0]); conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK wild spawn db]',type(e).__name__,e); return False
    finally:_put_connection(conn)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('🎯 Atrapar',callback_data=f'pk:wild:{spawn_id}')]])
    try:
        msg=await context.bot.send_message(chat_id=chat_id,message_thread_id=thread_id,text=_wild_text(species,level,shiny),reply_markup=kb)
    except Exception as e:
        print('[PK wild spawn send]',type(e).__name__,e); return False
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE pokemon_wild_spawns_tb SET message_id=%s WHERE spawn_id=%s",(msg.message_id,spawn_id)); conn.commit()
    except Exception:conn.rollback()
    finally:_put_connection(conn)
    try:
        if context.job_queue:
            context.job_queue.run_once(
                _expire_wild_spawn,
                WILD_LIFETIME_SECONDS,
                data={'spawn_id': spawn_id},
                name=f'pokemon_wild_expire:{spawn_id}',
            )
    except Exception as e:
        print('[PK wild expire schedule]', type(e).__name__, e)
    return True


async def pokemon_wild_spawn_job(context:ContextTypes.DEFAULT_TYPE):
    # Solo se ejecuta cada 2 horas; no observa mensajes ni hace polling continuo.
    for community in COMUNIDADES:
        try:
            chat_id=int(community.get('id_comunidad')); thread_id=_games_topic(chat_id)
            if thread_id is not None:await _spawn_wild(context,chat_id,thread_id)
        except Exception as e:print('[PK wild job]',type(e).__name__,e)


async def pokemonsalvaje_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    try:
        if not is_botmaster(update.effective_user.id):return await update.effective_message.reply_text('Solo BotMaster puede forzar una aparición Pokémon.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede forzar una aparición Pokémon.')
    if not _is_games_topic(update):return await update.effective_message.reply_text('🌿 Usa /pokemonsalvaje dentro del tema Juegos y Casino.')
    ok=await _spawn_wild(context,update.effective_chat.id,update.effective_message.message_thread_id)
    if not ok:await update.effective_message.reply_text('No pude crear la aparición Pokémon.')



async def pokemon_callback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; p=q.data.split(':'); uid=q.from_user.id
    action=p[1]
    if action=='noop':return await q.answer()
    if action=='trainercollection':
        try:
            await context.bot.send_message(uid,'🎮 TUS POKÉMON\n\nColección privada. Toca uno para administrarlo.',reply_markup=_collection_markup(uid,0))
            return await q.answer('Te mandé tu colección por privado.')
        except Exception:return await q.answer('Abre primero el privado de PiBot con /start.',show_alert=True)
    if action=='trainerbrag':
        pid=_principal_pid(uid)
        if not pid:return await q.answer('Todavía no tienes Pokémon principal.',show_alert=True)
        ok=await _send_brag(context,uid,pid,{'chat_id':q.message.chat_id,'thread_id':getattr(q.message,'message_thread_id',None)})
        return await q.answer('Presumido 😎' if ok else 'No pude publicarlo.',show_alert=True)
    if action=='wild':
        spawn_id=int(p[2]); conn=_get_connection(); spawn=None; attempts=0
        try:
            c=conn.cursor()
            c.execute(
                "SELECT chat_id,thread_id,species_id,level,shiny,status,message_id,caught_by, "
                "(created_at <= NOW() - INTERVAL '10 minutes') AS expired "
                "FROM pokemon_wild_spawns_tb WHERE spawn_id=%s FOR UPDATE",
                (spawn_id,),
            )
            spawn=c.fetchone()
            if not spawn:
                conn.rollback(); return await q.answer('Ese Pokémon ya no está disponible.',show_alert=True)
            if bool(spawn[8]) and spawn[5]=='active':
                c.execute("UPDATE pokemon_wild_spawns_tb SET status='expired',finished_at=NOW() WHERE spawn_id=%s",(spawn_id,)); conn.commit()
                try:
                    await q.edit_message_text(_wild_text(int(spawn[2]),int(spawn[3]),bool(spawn[4]))+'\n\n⌛ Pasaron 10 minutos y el Pokémon se fue.',reply_markup=None)
                except Exception:pass
                return await q.answer('Llegaste tarde: ya pasaron los 10 minutos.',show_alert=True)
            if spawn[5]=='throwing':
                conn.rollback()
                if spawn[7] is not None and int(spawn[7])==uid:
                    return await q.answer('🎲 Espera a que termine tu lanzamiento.',show_alert=True)
                return await q.answer('🎯 Otro entrenador ya está intentando atraparlo.',show_alert=True)
            if spawn[5]!='active':
                conn.rollback(); return await q.answer('Ese Pokémon ya se fue o ya fue atrapado.',show_alert=True)
            if int(spawn[0])!=int(q.message.chat_id) or spawn[1] != getattr(q.message,'message_thread_id',None):
                conn.rollback(); return await q.answer('Esta aparición ya no corresponde a este lugar.',show_alert=True)
            claimed_by=spawn[7]
            if claimed_by is not None and int(claimed_by)!=uid:
                conn.rollback(); return await q.answer('🎯 Otro entrenador llegó primero. Este Pokémon ya es su intento.',show_alert=True)
            if claimed_by is None:
                c.execute("UPDATE pokemon_wild_spawns_tb SET caught_by=%s WHERE spawn_id=%s",(uid,spawn_id))
            c.execute("INSERT INTO pokemon_wild_attempts_tb(spawn_id,user_id,attempts) VALUES(%s,%s,0) ON CONFLICT DO NOTHING",(spawn_id,uid))
            c.execute("SELECT attempts FROM pokemon_wild_attempts_tb WHERE spawn_id=%s AND user_id=%s FOR UPDATE",(spawn_id,uid)); attempts=int(c.fetchone()[0])
            if attempts>=WILD_MAX_ATTEMPTS:
                c.execute("UPDATE pokemon_wild_spawns_tb SET status='escaped',finished_at=NOW() WHERE spawn_id=%s",(spawn_id,)); conn.commit()
                return await q.answer('❌ Ya gastaste tus 2 tiros y el Pokémon se fue.',show_alert=True)
            attempts+=1
            c.execute("UPDATE pokemon_wild_attempts_tb SET attempts=%s WHERE spawn_id=%s AND user_id=%s",(attempts,spawn_id,uid))
            c.execute("UPDATE pokemon_wild_spawns_tb SET status='throwing' WHERE spawn_id=%s",(spawn_id,))
            conn.commit()
        except Exception as e:
            conn.rollback(); print('[PK wild attempt]',type(e).__name__,e); return await q.answer('No pude preparar tu Poké Ball.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer(f'🎯 Tiro {attempts}/{WILD_MAX_ATTEMPTS}...')
        try:
            dice_msg=await context.bot.send_dice(chat_id=q.message.chat_id,message_thread_id=getattr(q.message,'message_thread_id',None),emoji='🎲')
            value=int(dice_msg.dice.value)
        except Exception as e:
            # Si Telegram falla al lanzar el dado, no gastamos el tiro.
            conn=_get_connection()
            try:
                c=conn.cursor()
                c.execute("UPDATE pokemon_wild_attempts_tb SET attempts=GREATEST(attempts-1,0) WHERE spawn_id=%s AND user_id=%s",(spawn_id,uid))
                c.execute("UPDATE pokemon_wild_spawns_tb SET status='active' WHERE spawn_id=%s AND status='throwing' AND caught_by=%s",(spawn_id,uid))
                conn.commit()
            except Exception:conn.rollback()
            finally:_put_connection(conn)
            print('[PK wild dice]',type(e).__name__,e); return
        await asyncio.sleep(WILD_DICE_ANIMATION_SECONDS)
        effect={1:'PÉSIMO',2:'FLOJO',3:'BIEN',4:'MUY BIEN',5:'EXCELENTE',6:'PERFECTO'}[value]
        species=int(spawn[2]); level=int(spawn[3]); shiny=bool(spawn[4]); threshold=WILD_CATCH_THRESHOLD[rarity_for(species)]
        if value>=threshold:
            conn=_get_connection(); caught=None; trainer_name=q.from_user.first_name
            try:
                c=conn.cursor(); c.execute("SELECT status,species_id,level,shiny,chat_id,thread_id,message_id,caught_by FROM pokemon_wild_spawns_tb WHERE spawn_id=%s FOR UPDATE",(spawn_id,)); fresh=c.fetchone()
                if not fresh or fresh[0]!='throwing' or fresh[7] is None or int(fresh[7])!=uid:
                    conn.rollback(); fresh=None
                else:
                    species=int(fresh[1]); level=int(fresh[2]); shiny=bool(fresh[3]); trainer_name=_display_name_cursor(c,uid)
                    caught=grant_pokemon_with_cursor(c,uid,species,f'wild:{spawn_id}',level_override=level,shiny_override=shiny)
                    _ensure_trainer_row_cursor(c,uid); c.execute("UPDATE pokemon_trainer_tb SET wild_catches=wild_catches+1,updated_at=NOW() WHERE user_id=%s",(uid,))
                    c.execute("UPDATE pokemon_wild_spawns_tb SET status='caught',finished_at=NOW() WHERE spawn_id=%s",(spawn_id,)); conn.commit()
            except Exception as e:
                conn.rollback(); print('[PK wild catch]',type(e).__name__,e); caught=None
            finally:_put_connection(conn)
            if not caught:
                return await context.bot.send_message(q.message.chat_id,'💨 Ese Pokémon ya no está disponible.',message_thread_id=getattr(q.message,'message_thread_id',None))
            result=(f"🎲 {value}/6 · {effect}\n🎉 ¡{trainer_name} atrapó a #{species:03d} {'✨ SHINY ' if shiny else ''}{NAMES[species]} Nv.{level}!\n"
                    f"🧬 IV: {caught.get('iv_percent',0)}% · {caught.get('iv_grade','')}\n🎮 Ejemplar #{caught.get('pokemon_id')}")
            try:
                await context.bot.edit_message_text(chat_id=q.message.chat_id,message_id=q.message.message_id,text=_wild_text(species,level,shiny)+f'\n\n🏆 CAPTURADO POR {trainer_name}',reply_markup=None)
            except Exception:pass
            return await context.bot.send_message(q.message.chat_id,result,message_thread_id=getattr(q.message,'message_thread_id',None))
        remaining=WILD_MAX_ATTEMPTS-attempts
        trainer_name=q.from_user.first_name
        conn=_get_connection()
        try:
            c=conn.cursor()
            if remaining<=0:
                c.execute("UPDATE pokemon_wild_spawns_tb SET status='escaped',finished_at=NOW() WHERE spawn_id=%s AND status='throwing' AND caught_by=%s",(spawn_id,uid))
            else:
                c.execute("UPDATE pokemon_wild_spawns_tb SET status='active' WHERE spawn_id=%s AND status='throwing' AND caught_by=%s",(spawn_id,uid))
            conn.commit()
        except Exception as e:
            conn.rollback(); print('[PK wild miss]',type(e).__name__,e)
        finally:_put_connection(conn)
        text=f"🎲 {value}/6 · {effect}\n💨 #{species:03d} {NAMES[species]} escapó de la Poké Ball."
        if remaining>0:
            text += f"\n🎯 {trainer_name} tiene 1 último tiro. Nadie más puede intentarlo."
        else:
            text += "\n❌ Falló los 2 tiros. El Pokémon se fue para todos."
            try:
                await context.bot.edit_message_text(chat_id=q.message.chat_id,message_id=q.message.message_id,text=_wild_text(species,level,shiny)+f'\n\n💨 #{species:03d} {NAMES[species]} escapó después de los 2 intentos de {trainer_name}.',reply_markup=None)
            except Exception:pass
        return await context.bot.send_message(q.message.chat_id,text,message_thread_id=getattr(q.message,'message_thread_id',None))
    if action=='releasepage':
        page=int(p[2]); await q.answer(); return await q.edit_message_text('🌿 Elige el Pokémon que quieres liberar:',reply_markup=_release_markup(uid,page))
    if action=='releasepick':
        pid=int(p[2]); page=int(p[3]) if len(p)>3 else 0; row=_get_instance(uid,pid)
        if not row:return await q.answer('Ese Pokémon ya no está en tu colección.',show_alert=True)
        conn=_get_connection(); blocked=False
        try:
            c=conn.cursor(); _ensure_team_row_cursor(c,uid); c.execute("SELECT slot1,slot2,slot3,principal_pokemon_id FROM pokemon_team_tb WHERE owner_id=%s",(uid,)); team=c.fetchone() or (None,None,None,None); blocked=pid in [int(x) for x in team if x is not None]
        finally:_put_connection(conn)
        if blocked:return await q.answer('Primero quítalo del equipo o cambia tu Pokémon principal.',show_alert=True)
        ivpct=_iv_percent(_iv_values(row)); amount=_release_candies(int(row[3]),ivpct,bool(row[10])); root=_family_root(int(row[1]))
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(f'✅ Liberar · +{amount} 🍬',callback_data=f'pk:releaseconfirm:{pid}'),InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:detail:{pid}:{page}')]])
        await q.answer(); return await q.message.reply_text(f"🌿 ¿Liberar a {_pokemon_label(row)}?\n🧬 IV {ivpct}% · {_iv_grade(ivpct)}\n🍬 Recibirás {amount} caramelos de la familia #{root:03d} {NAMES[root]}.\n\nEsto es permanente.",reply_markup=kb)
    if action=='releaseconfirm':
        pid=int(p[2]); conn=_get_connection(); result=None
        try:
            c=conn.cursor(); c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s FOR UPDATE""",(uid,pid)); row=c.fetchone()
            if not row:conn.rollback(); return await q.answer('Ese Pokémon ya no está en tu colección.',show_alert=True)
            if _battle_busy_cursor(c,uid) or _trade_busy_cursor(c,uid):conn.rollback(); return await q.answer('Termina tu batalla/intercambio antes de liberar Pokémon.',show_alert=True)
            _ensure_team_row_cursor(c,uid); c.execute("SELECT slot1,slot2,slot3,principal_pokemon_id FROM pokemon_team_tb WHERE owner_id=%s FOR UPDATE",(uid,)); team=c.fetchone() or (None,None,None,None)
            if pid in [int(x) for x in team if x is not None]:conn.rollback(); return await q.answer('Primero quítalo del equipo o cambia tu principal.',show_alert=True)
            ivpct=_iv_percent(_iv_values(row)); amount=_release_candies(int(row[3]),ivpct,bool(row[10])); root=_family_root(int(row[1])); shown=row[2] or NAMES[int(row[1])]
            c.execute("DELETE FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid))
            c.execute("INSERT INTO pokemon_candies_tb(owner_id,family_species_id,qty) VALUES(%s,%s,%s) ON CONFLICT(owner_id,family_species_id) DO UPDATE SET qty=pokemon_candies_tb.qty+EXCLUDED.qty",(uid,root,amount))
            _ensure_trainer_row_cursor(c,uid); c.execute("UPDATE pokemon_trainer_tb SET released=released+1,candies_earned=candies_earned+%s,updated_at=NOW() WHERE user_id=%s",(amount,uid)); conn.commit(); result=(shown,amount,root)
        except Exception as e:
            conn.rollback(); print('[PK release]',type(e).__name__,e)
        finally:_put_connection(conn)
        if not result:return await q.answer('No pude liberarlo.',show_alert=True)
        await q.answer('Pokémon liberado.',show_alert=True)
        try:return await q.edit_message_text(f'🌿 Liberaste a {result[0]}.\n🍬 +{result[1]} caramelos de la familia {NAMES[result[2]]}.')
        except Exception:return
    if action=='candyup':
        pid=int(p[2]); conn=_get_connection(); notes=[]
        try:
            c=conn.cursor(); c.execute("SELECT species_id,level,xp,nickname FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s FOR UPDATE",(uid,pid)); r=c.fetchone()
            if not r:conn.rollback(); return await q.answer('Pokémon no encontrado.',show_alert=True)
            species,level,xp,nick=int(r[0]),int(r[1]),int(r[2]),r[3]
            if level>=MAX_LEVEL:conn.rollback(); return await q.answer('Ya está en nivel 100.',show_alert=True)
            root=_family_root(species); c.execute("UPDATE pokemon_candies_tb SET qty=qty-%s WHERE owner_id=%s AND family_species_id=%s AND qty>=%s RETURNING qty",(CANDIES_PER_LEVEL,uid,root,CANDIES_PER_LEVEL))
            if not c.fetchone():conn.rollback(); return await q.answer(f'Necesitas {CANDIES_PER_LEVEL} caramelos de esa familia.',show_alert=True)
            needed=max(1,_xp_floor(level+1)-xp); notes=_grant_pokemon_xp_cursor(c,pid,needed); conn.commit()
        except Exception as e:
            conn.rollback(); print('[PK candy level]',type(e).__name__,e)
        finally:_put_connection(conn)
        return await q.answer('🍬 '+(' · '.join(notes) if notes else 'Subió un nivel.'),show_alert=True)
    if action=='list':
        page=int(p[2]); await q.answer()
        text=f'🎮 TUS POKÉMON\n\nColección privada. Toca uno para administrarlo.'
        if q.message.photo or q.message.animation or q.message.video:
            try:
                await context.bot.send_message(chat_id=q.message.chat.id,text=text,reply_markup=_collection_markup(uid,page))
                await q.message.delete()
                return
            except Exception:
                pass
        return await q.edit_message_text(text,reply_markup=_collection_markup(uid,page))
    if action in ('detail','nickselect','mediaselect','brag'):
        pid=int(p[2]); page=int(p[3]) if len(p)>3 else 0; row=_get_instance(uid,pid)
        if not row:return await q.answer('Ese Pokémon ya no está en tu colección.',show_alert=True)
        if action=='brag':
            target=context.user_data.get('pk_brag_target') or {'chat_id':uid,'thread_id':None}; ok=await _send_brag(context,uid,pid,target); await q.answer('Presumido 😎' if ok else 'No pude publicarlo.',show_alert=True); return
        if action=='nickselect':context.user_data['pk_wait_nick']=pid; await q.answer(); return await q.message.reply_text(f"🏷️ Escribe el nuevo apodo para #{int(row[1]):03d} {NAMES[int(row[1])]} (máx. 24 caracteres). Escribe - para quitarlo.")
        if action=='mediaselect':context.user_data['pk_wait_media']=pid; await q.answer(); return await q.message.reply_text(f"🎞️ Envíame una FOTO, GIF o VIDEO para #{int(row[1]):03d} {row[2] or NAMES[int(row[1])]}. Telegram guardará el archivo; PiBot solo conservará su file_id.")
        species=int(row[1]); level=int(row[3]); moves=json.loads(row[5] or '[]'); move_names=', '.join(MOVES[m][0] for m in moves if m in MOVES)
        shiny_line = "✨ Variante SHINY\n" if len(row)>10 and row[10] else ""
        xp_line = (
            f"⭐ XP Pokémon: {row[4]:,} / {_xp_floor(level+1):,}\n"
            if level < MAX_LEVEL
            else f"⭐ XP Pokémon: {row[4]:,} · NIVEL MÁXIMO\n"
        )
        ivs=_iv_values(row); ivpct=_iv_percent(ivs)
        stats={
            'hp':_stat_value(species,level,'hp',ivs['hp']),
            'atk':_stat_value(species,level,'atk',ivs['atk']),
            'def':_stat_value(species,level,'def',ivs['def']),
            'spc':_stat_value(species,level,'spc',ivs['spc']),
            'spd':_stat_value(species,level,'spd',ivs['spd']),
        }
        principal=_is_principal(uid,pid)
        family_root=_family_root(species); family_candies=_candy_qty(uid,family_root)
        principal_line='⭐ Pokémon PRINCIPAL\n' if principal else ''
        txt=(f"{rarity_emoji(rarity_for(species))} {_pokemon_label(row)}\n"
             f"📖 Pokédex: #{species:03d} · 🎮 Ejemplar: #{int(row[0])}\n"
             f"{principal_line}"
             f"{shiny_line}"
             f"{_types_text(species)}\n"
             f"{xp_line}"
             f"🧬 IV: {ivpct}% · {_iv_grade(ivpct)}\n"
             f"📊 PS {stats['hp']} · ATQ {stats['atk']} · DEF {stats['def']} · ESP {stats['spc']} · VEL {stats['spd']}\n"
             f"🔬 DVs: PS {ivs['hp']}/15 · ATQ {ivs['atk']}/15 · DEF {ivs['def']}/15 · ESP {ivs['spc']}/15 · VEL {ivs['spd']}/15\n"
             f"🍬 Caramelos familia #{family_root:03d} {NAMES.get(family_root, 'Pokémon')}: {family_candies}\n"
             f"⚔️ {row[8]}V / {row[9]}D\n"
             f"🎯 Movimientos: {move_names or '—'}\n"
             f"🎞️ Multimedia: {'GIF' if row[6]=='animation' else 'Video' if row[6]=='video' else 'Foto' if row[6]=='photo' else 'Sin asignar'}")
        principal_btn=InlineKeyboardButton('⭐ Principal ✓' if principal else '⭐ Hacer principal',callback_data='pk:noop' if principal else f'pk:setprincipal:{pid}')
        extra_row=[]
        if family_candies>=CANDIES_PER_LEVEL and level<MAX_LEVEL:
            extra_row.append(InlineKeyboardButton(f'🍬 Subir nivel ({CANDIES_PER_LEVEL})',callback_data=f'pk:candyup:{pid}'))
        extra_row.append(InlineKeyboardButton('🌿 Liberar',callback_data=f'pk:releasepick:{pid}:{page}'))
        kb_rows=[[InlineKeyboardButton('🏷️ Apodo',callback_data=f'pk:nickselect:{pid}:{page}'),InlineKeyboardButton('🎞️ Foto/GIF/Video',callback_data=f'pk:mediaselect:{pid}:{page}')],[InlineKeyboardButton('👥 Meter al equipo',callback_data=f'pk:addteam:{pid}'),principal_btn],[InlineKeyboardButton('😎 Presumir aquí',callback_data=f'pk:braghere:{pid}'),InlineKeyboardButton('🗑 Quitar multimedia',callback_data=f'pk:removemedia:{pid}')],extra_row,[InlineKeyboardButton('⬅️ Volver',callback_data=f'pk:list:{page}')]]
        kb=InlineKeyboardMarkup(kb_rows)
        await q.answer()
        # Si ya tiene multimedia, al seleccionarlo se muestra inmediatamente con su ficha.
        if row[7] and row[6] in ('photo','animation','video'):
            try:
                if row[6]=='photo': await context.bot.send_photo(chat_id=q.message.chat.id,photo=row[7],caption=txt,reply_markup=kb)
                elif row[6]=='animation': await context.bot.send_animation(chat_id=q.message.chat.id,animation=row[7],caption=txt,reply_markup=kb)
                else: await context.bot.send_video(chat_id=q.message.chat.id,video=row[7],caption=txt,reply_markup=kb)
                try: await q.message.delete()
                except Exception: pass
                return
            except Exception:
                pass
        return await q.edit_message_text(txt,reply_markup=kb)
    if action=='setprincipal':
        pid=int(p[2]); conn=_get_connection(); name=None
        try:
            c=conn.cursor(); _ensure_team_row_cursor(c,uid)
            c.execute("SELECT species_id,nickname FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); r=c.fetchone()
            if not r:conn.rollback(); return await q.answer('Ese Pokémon ya no está en tu colección.',show_alert=True)
            c.execute("UPDATE pokemon_team_tb SET principal_pokemon_id=%s,updated_at=NOW() WHERE owner_id=%s",(pid,uid)); conn.commit()
            name=r[1] or NAMES[int(r[0])]
        except Exception as e:
            conn.rollback(); print('[PK principal]',type(e).__name__,e); return await q.answer('No pude cambiar tu Pokémon principal.',show_alert=True)
        finally:_put_connection(conn)
        return await q.answer(f'⭐ {name} ahora es tu Pokémon principal.',show_alert=True)
    if action=='removemedia':
        pid=int(p[2]); conn=_get_connection()
        try:c=conn.cursor(); c.execute("UPDATE pokemon_instances_tb SET media_type=NULL,media_file_id=NULL,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); conn.commit()
        except Exception:conn.rollback()
        finally:_put_connection(conn)
        return await q.answer('Multimedia quitada.',show_alert=True)
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
            tm_move=TM_ITEMS.get(code,(None,None,None))[2] if code in TM_ITEMS else None
            ok=(code in STONE_EVOLUTIONS.get(sid,{})) or (code=='link_cable' and sid in TRADE_EVOLUTIONS) or (code=='rare_candy' and level<MAX_LEVEL) or (tm_move is not None and can_learn_tm(sid,tm_move))
            if ok:eligible.append(r)
        if not eligible:return await q.answer('No tienes ningún Pokémon compatible con ese objeto/MT.',show_alert=True)
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
            if code in TM_ITEMS:
                move_code=TM_ITEMS[code][2]
                if not can_learn_tm(sid,move_code):
                    conn.rollback(); return await q.answer('Ese Pokémon no es compatible con esa MT.',show_alert=True)
                c.execute("SELECT moves_json FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); mr=c.fetchone()
                try: current_moves=json.loads((mr[0] if mr else '[]') or '[]')
                except Exception: current_moves=[]
                if move_code in current_moves:
                    conn.rollback(); return await q.answer('Ese Pokémon ya conoce ese movimiento.',show_alert=True)
                if len(current_moves)>=4:
                    conn.rollback()
                    rows=[]
                    for idx,mcode in enumerate(current_moves[:4]):
                        mname=MOVES.get(mcode,(mcode,))[0]
                        rows.append([InlineKeyboardButton(f'↪️ Olvidar {mname}',callback_data=f'pk:teachreplace:{code}:{pid}:{idx}')])
                    rows.append([InlineKeyboardButton('❌ Cancelar',callback_data='pk:items')])
                    await q.answer()
                    return await q.message.reply_text(f"📀 {ITEMS[code][0]} enseñará {MOVES[move_code][0]}.\n\n{r[1] or NAMES[sid]} ya conoce 4 movimientos. ¿Cuál quieres olvidar?",reply_markup=InlineKeyboardMarkup(rows))
                c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code=%s AND qty>0 RETURNING qty",(uid,code))
                if not c.fetchone():conn.rollback(); return await q.answer('Ya no tienes esa MT.',show_alert=True)
                current_moves.append(move_code)
                c.execute("UPDATE pokemon_instances_tb SET moves_json=%s,updated_at=NOW() WHERE pokemon_id=%s",(json.dumps(current_moves,ensure_ascii=False),pid))
                conn.commit(); note=f"📀 {r[1] or NAMES[sid]} aprendió {MOVES[move_code][0]}."
            elif code=='rare_candy':
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

    if action=='teachreplace':
        code=p[2]; pid=int(p[3]); idx=int(p[4]);
        if code not in TM_ITEMS:return await q.answer('MT inválida.',show_alert=True)
        conn=_get_connection(); note=None
        try:
            c=conn.cursor(); c.execute("SELECT species_id,nickname,moves_json FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s FOR UPDATE",(uid,pid)); r=c.fetchone()
            if not r:conn.rollback(); return await q.answer('Pokémon no encontrado.',show_alert=True)
            sid=int(r[0]); move_code=TM_ITEMS[code][2]
            if not can_learn_tm(sid,move_code):conn.rollback(); return await q.answer('Ese Pokémon no es compatible con esa MT.',show_alert=True)
            try:moves=json.loads(r[2] or '[]')
            except Exception:moves=[]
            if move_code in moves:conn.rollback(); return await q.answer('Ese Pokémon ya conoce ese movimiento.',show_alert=True)
            if not (0<=idx<len(moves)):conn.rollback(); return await q.answer('Movimiento inválido.',show_alert=True)
            old=moves[idx]; c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code=%s AND qty>0 RETURNING qty",(uid,code))
            if not c.fetchone():conn.rollback(); return await q.answer('Ya no tienes esa MT.',show_alert=True)
            moves[idx]=move_code
            c.execute("UPDATE pokemon_instances_tb SET moves_json=%s,updated_at=NOW() WHERE pokemon_id=%s",(json.dumps(moves,ensure_ascii=False),pid)); conn.commit()
            note=f"📀 {r[1] or NAMES[sid]} olvidó {MOVES.get(old,(old,))[0]} y aprendió {MOVES[move_code][0]}."
        except Exception as e:
            conn.rollback(); print('[PK TM]',type(e).__name__,e)
        finally:_put_connection(conn)
        return await q.answer(note or 'No pude usar esa MT.',show_alert=True)

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
            text=summary+'\n\nAmbos deben confirmar. El intercambio conserva nivel, XP, apodo, foto/GIF/video y condición Shiny.'
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
                    c.execute("UPDATE pokemon_team_tb SET principal_pokemon_id=NULL,updated_at=NOW() WHERE owner_id=%s AND principal_pokemon_id=%s",(owner,pid))
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
                result_text='🔄 ¡INTERCAMBIO COMPLETADO!\n\nLos Pokémon conservaron nivel, XP, apodo, foto/GIF/video y Shiny.'+('\n\n'+'\n'.join(evo_notes) if evo_notes else '')
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
    elif m.video:media_type='video'; file_id=m.video.file_id
    elif m.photo:media_type='photo'; file_id=m.photo[-1].file_id
    else:return await m.reply_text('Envíame una foto, GIF/animación o video de Telegram.')
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE pokemon_instances_tb SET media_type=%s,media_file_id=%s,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s RETURNING species_id",(media_type,file_id,update.effective_user.id,pid)); ok=c.fetchone(); conn.commit()
    except Exception:conn.rollback(); ok=None
    finally:_put_connection(conn)
    context.user_data.pop('pk_wait_media',None)
    await m.reply_text('🎞️ GIF guardado.' if ok and media_type=='animation' else '🎥 Video guardado.' if ok and media_type=='video' else '🖼️ Foto guardada.' if ok else 'No encontré ese Pokémon.')
