"""SAO-CB Telegram Reborn.

Telegram-native RPG inspired by the user's SAO-CB / Memory Defrag revival work.
It does not depend on the retired Android client or WrightFlyer services.
All persistent game state lives in the same PostgreSQL used by PiBot.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.database.database import _get_connection, _put_connection
from src.utils.display_name import visible_user


MAX_STAMINA = 30
STAMINA_REGEN_SECONDS = 300  # 1 point / 5 min
STARTER_PIPESOS = 250
STARTER_COL = 10000
SINGLE_COST = 25
MULTI_COST = 250


# Telegram-native seed catalog. IDs are SAO-CB Telegram IDs, deliberately
# independent from old client master IDs so the new game can evolve freely.
UNIT_SEEDS = [
    # id, name, title, stars, weapon, element, hp, atk, defense, skill, skill_power
    (1001, "Kirito", "Black Swordsman", 4, "Sword", "Dark", 1500, 420, 230, "Starburst Stream", 2.15),
    (1002, "Asuna", "Lightning Flash", 4, "Rapier", "Light", 1380, 405, 245, "Mother's Rosario", 2.10),
    (1003, "Sinon", "Phantom Bullet", 4, "Gun", "Wind", 1250, 435, 205, "Dead Line Shot", 2.20),
    (1004, "Leafa", "Sylph Swordswoman", 4, "Sword", "Wind", 1420, 385, 255, "Sylph Tempest", 2.00),
    (1005, "Yuuki", "Absolute Sword", 5, "Sword", "Light", 1650, 490, 265, "Eleven Hit Rosario", 2.50),
    (1006, "Alice", "Osmanthus Knight", 5, "Sword", "Holy", 1780, 470, 310, "Release Recollection", 2.45),
    (1007, "Eugeo", "Blue Rose Swordsman", 5, "Sword", "Water", 1720, 455, 320, "Blue Rose Release", 2.40),
    (1008, "Silica", "Beast Tamer", 3, "Dagger", "Earth", 1180, 320, 210, "Pina's Blessing", 1.75),
    (1009, "Lisbeth", "Mace Smith", 3, "Mace", "Fire", 1320, 305, 255, "Forge Breaker", 1.70),
    (1010, "Klein", "Fuurinkazan", 3, "Katana", "Fire", 1360, 330, 240, "Samurai Rush", 1.78),
    (1011, "Agil", "Axe Warrior", 3, "Axe", "Earth", 1580, 310, 300, "Grand Impact", 1.72),
    (1012, "Rain", "Dual Wielder", 4, "Dual Blades", "Water", 1400, 415, 220, "Thousand Rain", 2.12),
    (1013, "Strea", "Giant Sword", 4, "Greatsword", "Dark", 1680, 410, 285, "Heart Break", 2.08),
    (1014, "Philia", "Treasure Hunter", 4, "Dagger", "Earth", 1320, 398, 225, "Treasure Raid", 2.05),
    (1015, "Sachi", "Moonlit Black Cat", 3, "Spear", "Water", 1210, 300, 235, "Moonlit Pierce", 1.68),
    (1016, "Kirito", "Aincrad Rookie", 2, "Sword", "Neutral", 980, 250, 160, "Horizontal", 1.40),
    (1017, "Asuna", "Aincrad Fencer", 2, "Rapier", "Neutral", 900, 245, 170, "Linear", 1.40),
    (1018, "Silica", "Aincrad Tamer", 2, "Dagger", "Neutral", 880, 230, 165, "Rapid Bite", 1.35),
]

QUEST_SEEDS = [
    # id, floor, name, enemy, rec_power, hp, atk, col, first-clear MD, stamina
    (1, 1, "Starting City Outskirts", "Frenzy Boar", 900, 2300, 180, 900, 10, 3),
    (2, 1, "Forest of Beginnings", "Little Nepent", 1200, 3200, 220, 1200, 10, 4),
    (3, 2, "Ruins Below", "Ruin Kobold", 1650, 4600, 270, 1600, 12, 5),
    (4, 3, "Lake Crossing", "Water Lizard", 2200, 6200, 340, 2100, 12, 5),
    (5, 5, "Labyrinth Gate", "Kobold Sentinel", 2900, 8200, 420, 2800, 15, 6),
    (6, 10, "Floor Boss: Illfang", "Illfang the Kobold Lord", 3800, 11500, 520, 4200, 25, 8),
    (7, 20, "Desert Ambush", "Sand Reaper", 5000, 15500, 650, 5800, 20, 8),
    (8, 35, "Frozen Passage", "Ice Golem", 6500, 22000, 780, 7600, 25, 9),
    (9, 50, "Mid-Aincrad Trial", "Guardian Knight", 8300, 30000, 930, 9800, 30, 10),
    (10, 75, "Skull Reaper Chamber", "The Skull Reaper", 10500, 42000, 1150, 15000, 50, 12),
]


RARITY_WEIGHTS = {2: 55, 3: 30, 4: 12, 5: 3}


def ensure_saocb_telegram_tables():
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS saocb_players_tb(
                user_id BIGINT PRIMARY KEY REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                player_name TEXT,
                rank INTEGER NOT NULL DEFAULT 1,
                exp BIGINT NOT NULL DEFAULT 0,
                col BIGINT NOT NULL DEFAULT 0,
                memory_diamonds INTEGER NOT NULL DEFAULT 0,
                memory_fragments INTEGER NOT NULL DEFAULT 0,
                floor INTEGER NOT NULL DEFAULT 1,
                stamina INTEGER NOT NULL DEFAULT 30,
                stamina_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                daily_claim DATE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("ALTER TABLE saocb_players_tb ADD COLUMN IF NOT EXISTS player_name TEXT")
        c.execute("""
            CREATE TABLE IF NOT EXISTS saocb_units_catalog_tb(
                unit_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                title TEXT NOT NULL,
                stars INTEGER NOT NULL CHECK(stars BETWEEN 1 AND 6),
                weapon TEXT NOT NULL,
                element TEXT NOT NULL,
                base_hp INTEGER NOT NULL,
                base_atk INTEGER NOT NULL,
                base_def INTEGER NOT NULL,
                skill_name TEXT NOT NULL,
                skill_power NUMERIC(8,3) NOT NULL DEFAULT 1.5,
                asset_key TEXT,
                source TEXT NOT NULL DEFAULT 'telegram_v1_seed'
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS saocb_user_units_tb(
                user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                unit_id INTEGER NOT NULL REFERENCES saocb_units_catalog_tb(unit_id),
                level INTEGER NOT NULL DEFAULT 1,
                exp BIGINT NOT NULL DEFAULT 0,
                copies INTEGER NOT NULL DEFAULT 1,
                awaken INTEGER NOT NULL DEFAULT 0,
                acquired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY(user_id,unit_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS saocb_parties_tb(
                user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 3),
                unit_id INTEGER NOT NULL REFERENCES saocb_units_catalog_tb(unit_id),
                PRIMARY KEY(user_id,slot),
                UNIQUE(user_id,unit_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS saocb_quests_tb(
                quest_id INTEGER PRIMARY KEY,
                floor INTEGER NOT NULL,
                name TEXT NOT NULL,
                enemy TEXT NOT NULL,
                recommended_power INTEGER NOT NULL,
                enemy_hp INTEGER NOT NULL,
                enemy_atk INTEGER NOT NULL,
                reward_col INTEGER NOT NULL,
                reward_md INTEGER NOT NULL,
                stamina_cost INTEGER NOT NULL,
                active BOOLEAN NOT NULL DEFAULT TRUE
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS saocb_quest_progress_tb(
                user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                quest_id INTEGER NOT NULL REFERENCES saocb_quests_tb(quest_id),
                clear_count INTEGER NOT NULL DEFAULT 0,
                best_rank INTEGER NOT NULL DEFAULT 0,
                last_clear_at TIMESTAMPTZ,
                PRIMARY KEY(user_id,quest_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS saocb_battles_tb(
                user_id BIGINT PRIMARY KEY REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                quest_id INTEGER NOT NULL REFERENCES saocb_quests_tb(quest_id),
                enemy_hp INTEGER NOT NULL,
                player_hp INTEGER NOT NULL,
                turn INTEGER NOT NULL DEFAULT 1,
                guarding BOOLEAN NOT NULL DEFAULT FALSE,
                skill_cd INTEGER NOT NULL DEFAULT 0,
                started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS saocb_gacha_log_tb(
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                unit_id INTEGER NOT NULL REFERENCES saocb_units_catalog_tb(unit_id),
                stars INTEGER NOT NULL,
                duplicate BOOLEAN NOT NULL DEFAULT FALSE,
                cost INTEGER NOT NULL DEFAULT 0,
                banner TEXT NOT NULL DEFAULT 'aincrad_standard',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_saocb_units_user ON saocb_user_units_tb(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_saocb_gacha_user ON saocb_gacha_log_tb(user_id,created_at DESC)")

        c.executemany("""
            INSERT INTO saocb_units_catalog_tb(
              unit_id,name,title,stars,weapon,element,base_hp,base_atk,base_def,skill_name,skill_power
            ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(unit_id) DO NOTHING
        """, UNIT_SEEDS)
        c.executemany("""
            INSERT INTO saocb_quests_tb(
              quest_id,floor,name,enemy,recommended_power,enemy_hp,enemy_atk,reward_col,reward_md,stamina_cost
            ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(quest_id) DO NOTHING
        """, QUEST_SEEDS)
        conn.commit()
        print("[SAO-TG] Tablas listas: Telegram Reborn V1")
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_connection(conn)


def _ensure_player(user_id: int) -> bool:
    """Create SAO profile and starter once. Returns True when newly created."""
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM saocb_players_tb WHERE user_id=%s", (user_id,))
        if c.fetchone():
            return False
        c.execute(
            "INSERT INTO saocb_players_tb(user_id,col,stamina) VALUES(%s,%s,%s)",
            (user_id, STARTER_COL, MAX_STAMINA),
        )
        # Memory Diamonds are the user's real PiPeso balance (1:1).
        c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s", (STARTER_PIPESOS, user_id))
        c.execute(
            "INSERT INTO saocb_user_units_tb(user_id,unit_id,level,copies) VALUES(%s,1001,1,1)",
            (user_id,),
        )
        c.execute(
            "INSERT INTO saocb_parties_tb(user_id,slot,unit_id) VALUES(%s,1,1001)",
            (user_id,),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_connection(conn)


def _regen_stamina_locked(c, user_id: int) -> Tuple[int, datetime]:
    c.execute("SELECT stamina,stamina_updated_at FROM saocb_players_tb WHERE user_id=%s FOR UPDATE", (user_id,))
    row = c.fetchone()
    if not row:
        return 0, datetime.now(timezone.utc)
    stamina, updated = int(row[0]), row[1]
    now = datetime.now(timezone.utc)
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    if stamina >= MAX_STAMINA:
        if stamina != MAX_STAMINA or (now - updated).total_seconds() > STAMINA_REGEN_SECONDS:
            c.execute("UPDATE saocb_players_tb SET stamina=%s,stamina_updated_at=%s WHERE user_id=%s", (MAX_STAMINA, now, user_id))
        return MAX_STAMINA, now
    elapsed = max(0, int((now - updated).total_seconds()))
    gained = elapsed // STAMINA_REGEN_SECONDS
    if gained > 0:
        new_stamina = min(MAX_STAMINA, stamina + gained)
        used_seconds = gained * STAMINA_REGEN_SECONDS
        if new_stamina >= MAX_STAMINA:
            new_updated = now
        else:
            from datetime import timedelta
            new_updated = updated + timedelta(seconds=used_seconds)
        c.execute("UPDATE saocb_players_tb SET stamina=%s,stamina_updated_at=%s WHERE user_id=%s", (new_stamina, new_updated, user_id))
        stamina, updated = new_stamina, new_updated
    return stamina, updated


def _player(user_id: int) -> Dict:
    _ensure_player(user_id)
    conn = _get_connection()
    try:
        c = conn.cursor()
        stamina, _ = _regen_stamina_locked(c, user_id)
        c.execute("""SELECT p.rank,p.exp,p.col,COALESCE(u.saldo,0),p.memory_fragments,p.floor,p.daily_claim,p.player_name
                   FROM saocb_players_tb p JOIN usuarios_tb u ON u.id_user=p.user_id WHERE p.user_id=%s""", (user_id,))
        r = c.fetchone()
        conn.commit()
        return {
            "rank": int(r[0]), "exp": int(r[1]), "col": int(r[2]), "md": int(r[3]),
            "fragments": int(r[4]), "floor": int(r[5]), "daily_claim": r[6], "player_name": r[7], "stamina": stamina,
        }
    finally:
        _put_connection(conn)


def _unit_row(unit_id: int) -> Optional[Dict]:
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT unit_id,name,title,stars,weapon,element,base_hp,base_atk,base_def,skill_name,skill_power FROM saocb_units_catalog_tb WHERE unit_id=%s", (unit_id,))
        r = c.fetchone()
        if not r:
            return None
        keys = ["unit_id","name","title","stars","weapon","element","base_hp","base_atk","base_def","skill_name","skill_power"]
        d = dict(zip(keys, r)); d["skill_power"] = float(d["skill_power"])
        return d
    finally:
        _put_connection(conn)


def _max_level(stars: int, awaken: int = 0) -> int:
    base = {1: 30, 2: 40, 3: 60, 4: 80, 5: 100, 6: 120}.get(stars, 80)
    return base + awaken * 5


def _scaled_stats(cat: Dict, level: int, awaken: int = 0) -> Tuple[int, int, int]:
    mult = 1.0 + max(0, level - 1) * 0.035 + awaken * 0.10
    return (
        int(cat["base_hp"] * mult),
        int(cat["base_atk"] * mult),
        int(cat["base_def"] * mult),
    )


def _user_units(user_id: int) -> List[Dict]:
    _ensure_player(user_id)
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT u.unit_id,u.level,u.exp,u.copies,u.awaken,
                   c.name,c.title,c.stars,c.weapon,c.element,c.base_hp,c.base_atk,c.base_def,c.skill_name,c.skill_power
            FROM saocb_user_units_tb u
            JOIN saocb_units_catalog_tb c ON c.unit_id=u.unit_id
            WHERE u.user_id=%s
            ORDER BY c.stars DESC,u.level DESC,u.unit_id
        """, (user_id,))
        out = []
        for r in c.fetchall():
            keys = ["unit_id","level","exp","copies","awaken","name","title","stars","weapon","element","base_hp","base_atk","base_def","skill_name","skill_power"]
            d = dict(zip(keys, r)); d["skill_power"] = float(d["skill_power"])
            hp, atk, de = _scaled_stats(d, d["level"], d["awaken"])
            d.update(hp=hp, atk=atk, defense=de, power=atk * 2 + de + hp // 8)
            out.append(d)
        return out
    finally:
        _put_connection(conn)


def _party(user_id: int) -> List[Dict]:
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT p.slot,u.unit_id,u.level,u.awaken,c.name,c.title,c.stars,c.weapon,c.element,
                   c.base_hp,c.base_atk,c.base_def,c.skill_name,c.skill_power
            FROM saocb_parties_tb p
            JOIN saocb_user_units_tb u ON u.user_id=p.user_id AND u.unit_id=p.unit_id
            JOIN saocb_units_catalog_tb c ON c.unit_id=u.unit_id
            WHERE p.user_id=%s ORDER BY p.slot
        """, (user_id,))
        out = []
        for r in c.fetchall():
            keys = ["slot","unit_id","level","awaken","name","title","stars","weapon","element","base_hp","base_atk","base_def","skill_name","skill_power"]
            d = dict(zip(keys, r)); d["skill_power"] = float(d["skill_power"])
            hp, atk, de = _scaled_stats(d, d["level"], d["awaken"])
            d.update(hp=hp, atk=atk, defense=de, power=atk * 2 + de + hp // 8)
            out.append(d)
        return out
    finally:
        _put_connection(conn)


def _party_stats(user_id: int) -> Tuple[int, int, int, int, List[Dict]]:
    party = _party(user_id)
    if not party:
        return 0, 0, 0, 0, []
    hp = sum(x["hp"] for x in party)
    atk = sum(x["atk"] for x in party)
    defense = sum(x["defense"] for x in party)
    power = sum(x["power"] for x in party)
    return hp, atk, defense, power, party


def _stars(n: int) -> str:
    return "★" * n


def _aincrad_name(user_id: int, player: Optional[Dict] = None) -> str:
    p = player or _player(user_id)
    custom = (p.get("player_name") or "").strip()
    return custom if custom else visible_user(user_id=user_id)


def _set_aincrad_name(user_id: int, name: str) -> str:
    clean = " ".join((name or "").strip().split())
    if not (2 <= len(clean) <= 24):
        return "El nombre debe tener entre 2 y 24 caracteres."
    if any(ch in clean for ch in "\n\r\t"):
        return "Ese nombre no es válido."
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE saocb_players_tb SET player_name=%s,updated_at=NOW() WHERE user_id=%s", (clean, user_id))
        conn.commit()
        return f"✅ En Aincrad ahora te llamas {clean}."
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_connection(conn)


async def sao_name_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    _ensure_player(uid)
    if not context.args:
        return await update.effective_message.reply_text("Usa: /saonombre TuNombre")
    msg = _set_aincrad_name(uid, " ".join(context.args))
    await update.effective_message.reply_text(msg)


def _home_keyboard(active_battle: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("👤 Perfil", callback_data="sao:profile"), InlineKeyboardButton("⚔️ Party", callback_data="sao:party")],
        [InlineKeyboardButton("✨ SCOUT", callback_data="sao:scout"), InlineKeyboardButton("🗺️ Quests", callback_data="sao:quests")],
        [InlineKeyboardButton("🧰 Unidades", callback_data="sao:units:0"), InlineKeyboardButton("⬆️ Mejorar", callback_data="sao:upgrade:0")],
        [InlineKeyboardButton("🎁 Diario", callback_data="sao:daily"), InlineKeyboardButton("🏆 Ranking", callback_data="sao:ranking")],
    ]
    if active_battle:
        rows.insert(0, [InlineKeyboardButton("🔥 Continuar batalla", callback_data="sao:battle:resume")])
    return InlineKeyboardMarkup(rows)


def _back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Aincrad", callback_data="sao:home")]])


def _has_battle(user_id: int) -> bool:
    conn = _get_connection()
    try:
        c = conn.cursor(); c.execute("SELECT 1 FROM saocb_battles_tb WHERE user_id=%s", (user_id,))
        return c.fetchone() is not None
    finally:
        _put_connection(conn)


def _home_text(user_id: int, first: bool = False) -> str:
    p = _player(user_id)
    _, _, _, power, party = _party_stats(user_id)
    main = party[0]["name"] if party else "Sin unidad"
    welcome = "\n🎁 Cuenta nueva: recibiste Kirito, +250 PiPesos y 10,000 Col.\n" if first else ""
    return (
        "⚔️ SAO-CB · TELEGRAM REBORN\n"
        "Aincrad vive aquí. Ya no depende del APK viejo.\n"
        f"{welcome}\n"
        f"🧑‍🚀 {_aincrad_name(user_id, p)} · Rank {p['rank']} · Piso {p['floor']}\n"
        f"⭐ Principal: {main}\n"
        f"💥 Poder: {power:,}\n"
        f"💎 PiPesos / Memory Diamonds: {p['md']:,}\n"
        f"🪙 Col: {p['col']:,}\n"
        f"⚡ Stamina: {p['stamina']}/{MAX_STAMINA}\n\n"
        "Elige qué hacer."
    )


async def sao_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    first = _ensure_player(uid)
    await update.effective_message.reply_text(
        _home_text(uid, first),
        reply_markup=_home_keyboard(_has_battle(uid)),
    )


async def _show_home(q, uid: int):
    await q.edit_message_text(_home_text(uid), reply_markup=_home_keyboard(_has_battle(uid)))


async def _show_profile(q, uid: int):
    p = _player(uid)
    hp, atk, defense, power, party = _party_stats(uid)
    units = _user_units(uid)
    text = (
        "👤 PERFIL DE AINCRAD\n\n"
        f"Nombre: {_aincrad_name(uid, p)}\n"
        f"Rank: {p['rank']}\n"
        f"EXP: {p['exp']:,}\n"
        f"Piso alcanzado: {p['floor']}\n"
        f"Unidades: {len(units)}\n"
        f"Poder de party: {power:,}\n"
        f"HP total: {hp:,} · ATK: {atk:,} · DEF: {defense:,}\n\n"
        f"💎 {p['md']:,} PiPesos / Memory Diamonds\n"
        f"🪙 {p['col']:,} Col\n"
        f"🧩 {p['fragments']:,} Memory Fragments\n"
        f"⚡ {p['stamina']}/{MAX_STAMINA} Stamina"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Cambiar nombre", callback_data="sao:name")],
        [InlineKeyboardButton("⬅️ Aincrad", callback_data="sao:home")],
    ])
    await q.edit_message_text(text, reply_markup=kb)


async def _show_units(q, uid: int, page: int = 0):
    units = _user_units(uid)
    per = 6
    pages = max(1, math.ceil(len(units) / per))
    page = max(0, min(page, pages - 1))
    chunk = units[page * per:(page + 1) * per]
    lines = [f"🧰 UNIDADES · {page+1}/{pages}", ""]
    rows = []
    for u in chunk:
        lines.append(f"{_stars(u['stars'])} {u['name']} · Lv.{u['level']} · {u['power']:,} POW")
        rows.append([InlineKeyboardButton(f"{u['name']} Lv.{u['level']}", callback_data=f"sao:unit:{u['unit_id']}")])
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("◀️", callback_data=f"sao:units:{page-1}"))
    nav.append(InlineKeyboardButton("🏠", callback_data="sao:home"))
    if page + 1 < pages: nav.append(InlineKeyboardButton("▶️", callback_data=f"sao:units:{page+1}"))
    rows.append(nav)
    await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))


async def _show_unit(q, uid: int, unit_id: int):
    owned = next((x for x in _user_units(uid) if x["unit_id"] == unit_id), None)
    if not owned:
        return await q.answer("No tienes esa unidad.", show_alert=True)
    text = (
        f"{_stars(owned['stars'])} {owned['name']}\n"
        f"{owned['title']}\n\n"
        f"Lv. {owned['level']}/{_max_level(owned['stars'], owned['awaken'])}\n"
        f"⚔️ {owned['weapon']} · {owned['element']}\n"
        f"❤️ HP {owned['hp']:,}\n"
        f"💥 ATK {owned['atk']:,}\n"
        f"🛡 DEF {owned['defense']:,}\n"
        f"✨ Skill: {owned['skill_name']}\n"
        f"📦 Copias: {owned['copies']}\n"
        f"🔥 Awakening: +{owned['awaken']}"
    )
    rows = [
        [InlineKeyboardButton("1️⃣ Slot 1", callback_data=f"sao:partyset:1:{unit_id}"), InlineKeyboardButton("2️⃣ Slot 2", callback_data=f"sao:partyset:2:{unit_id}"), InlineKeyboardButton("3️⃣ Slot 3", callback_data=f"sao:partyset:3:{unit_id}")],
        [InlineKeyboardButton("⬆️ Mejorar", callback_data=f"sao:upgradeunit:{unit_id}")],
        [InlineKeyboardButton("⬅️ Unidades", callback_data="sao:units:0")],
    ]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))


async def _show_party(q, uid: int):
    hp, atk, defense, power, party = _party_stats(uid)
    lines = ["⚔️ PARTY", ""]
    slots = {x["slot"]: x for x in party}
    for slot in (1, 2, 3):
        u = slots.get(slot)
        if u:
            lines.append(f"{slot}. {_stars(u['stars'])} {u['name']} · Lv.{u['level']} · {u['power']:,}")
        else:
            lines.append(f"{slot}. — vacío —")
    lines += ["", f"💥 Poder total: {power:,}", f"❤️ HP {hp:,} · ATK {atk:,} · DEF {defense:,}", "", "Abre Unidades y toca un personaje para asignarlo a un slot."]
    rows = [[InlineKeyboardButton("🧰 Elegir unidades", callback_data="sao:units:0")], [InlineKeyboardButton("⬅️ Aincrad", callback_data="sao:home")]]
    await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))


def _set_party_slot(user_id: int, slot: int, unit_id: int) -> str:
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT 1 FROM saocb_user_units_tb WHERE user_id=%s AND unit_id=%s", (user_id, unit_id))
        if not c.fetchone(): return "No tienes esa unidad."
        # A unit cannot occupy two slots; moving it clears its previous slot.
        c.execute("DELETE FROM saocb_parties_tb WHERE user_id=%s AND unit_id=%s", (user_id, unit_id))
        c.execute("""
            INSERT INTO saocb_parties_tb(user_id,slot,unit_id) VALUES(%s,%s,%s)
            ON CONFLICT(user_id,slot) DO UPDATE SET unit_id=EXCLUDED.unit_id
        """, (user_id, slot, unit_id))
        conn.commit(); return f"Unidad colocada en slot {slot}."
    except Exception:
        conn.rollback(); raise
    finally:
        _put_connection(conn)


def _catalog_pool(min_stars: int = 2) -> List[Dict]:
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT unit_id,name,title,stars,weapon,element FROM saocb_units_catalog_tb WHERE stars>=%s ORDER BY unit_id", (min_stars,))
        return [dict(zip(["unit_id","name","title","stars","weapon","element"], r)) for r in c.fetchall()]
    finally:
        _put_connection(conn)


def _roll_unit(pool: List[Dict], guaranteed_four: bool = False) -> Dict:
    eligible = [u for u in pool if u["stars"] >= 4] if guaranteed_four else pool
    if guaranteed_four:
        weights = [80 if u["stars"] == 4 else 20 for u in eligible]
        return random.choices(eligible, weights=weights, k=1)[0]
    weights = [RARITY_WEIGHTS.get(u["stars"], 1) / max(1, sum(1 for x in pool if x["stars"] == u["stars"])) for u in pool]
    return random.choices(pool, weights=weights, k=1)[0]


def _gacha(user_id: int, count: int) -> Tuple[bool, str, List[Tuple[Dict, bool]]]:
    cost = SINGLE_COST if count == 1 else MULTI_COST
    pool = _catalog_pool()
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s FOR UPDATE", (user_id,))
        row = c.fetchone()
        if not row or int(row[0]) < cost:
            conn.rollback(); return False, f"Necesitas {cost} PiPesos (💎).", []
        c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo>=%s", (cost, user_id, cost))
        results = []
        for i in range(count):
            u = _roll_unit(pool, guaranteed_four=(count > 1 and i == count - 1))
            c.execute("SELECT copies FROM saocb_user_units_tb WHERE user_id=%s AND unit_id=%s FOR UPDATE", (user_id, u["unit_id"]))
            old = c.fetchone(); duplicate = old is not None
            if duplicate:
                c.execute("UPDATE saocb_user_units_tb SET copies=copies+1 WHERE user_id=%s AND unit_id=%s", (user_id, u["unit_id"]))
                fragments = {2: 2, 3: 5, 4: 15, 5: 40}.get(u["stars"], 2)
                c.execute("UPDATE saocb_players_tb SET memory_fragments=memory_fragments+%s WHERE user_id=%s", (fragments, user_id))
            else:
                c.execute("INSERT INTO saocb_user_units_tb(user_id,unit_id,level,copies) VALUES(%s,%s,1,1)", (user_id, u["unit_id"]))
            c.execute("INSERT INTO saocb_gacha_log_tb(user_id,unit_id,stars,duplicate,cost) VALUES(%s,%s,%s,%s,%s)", (user_id, u["unit_id"], u["stars"], duplicate, cost if i == 0 else 0))
            results.append((u, duplicate))
        conn.commit(); return True, "", results
    except Exception:
        conn.rollback(); raise
    finally:
        _put_connection(conn)


async def _show_scout(q, uid: int):
    p = _player(uid)
    text = (
        "✨ SCOUT · AINCRAD STANDARD\n\n"
        "5★ 3% · 4★ 12% · 3★ 30% · 2★ 55%\n"
        "El x11 garantiza al menos una unidad 4★ o 5★.\n"
        "Los duplicados dan Memory Fragments.\n\n"
        f"💎 Tienes {p['md']:,} PiPesos / Memory Diamonds"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"1x · {SINGLE_COST} 💎", callback_data="sao:draw:1"), InlineKeyboardButton(f"11x · {MULTI_COST} 💎", callback_data="sao:draw:11")],
        [InlineKeyboardButton("⬅️ Aincrad", callback_data="sao:home")],
    ])
    await q.edit_message_text(text, reply_markup=kb)


async def _draw(q, uid: int, count: int):
    ok, msg, results = _gacha(uid, count)
    if not ok:
        return await q.answer(msg, show_alert=True)
    lines = ["✨ SCOUT RESULT", ""]
    for u, dup in results:
        suffix = " · DUPLICADO 🧩" if dup else " · NUEVA 🔥"
        lines.append(f"{_stars(u['stars'])} {u['name']} — {u['title']}{suffix}")
    p = _player(uid)
    lines += ["", f"💎 Restantes: {p['md']:,} · 🧩 Fragmentos: {p['fragments']:,}"]
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("✨ Otra tirada", callback_data="sao:scout"), InlineKeyboardButton("🧰 Ver unidades", callback_data="sao:units:0")], [InlineKeyboardButton("🏠 Aincrad", callback_data="sao:home")]])
    await q.edit_message_text("\n".join(lines), reply_markup=kb)


async def _show_quests(q, uid: int):
    p = _player(uid)
    _, _, _, power, _ = _party_stats(uid)
    conn = _get_connection()
    try:
        c = conn.cursor(); c.execute("SELECT quest_id,floor,name,enemy,recommended_power,stamina_cost FROM saocb_quests_tb WHERE active=TRUE ORDER BY quest_id")
        quests = c.fetchall()
    finally:
        _put_connection(conn)
    lines = ["🗺️ QUESTS DE AINCRAD", f"💥 Tu poder: {power:,} · ⚡ {p['stamina']}/{MAX_STAMINA}", ""]
    rows = []
    for qid, floor, name, enemy, rec, sta in quests:
        lock = "🔒" if floor > p["floor"] + 10 else "⚔️"
        lines.append(f"{lock} Piso {floor} · {name} · Rec {rec:,}")
        if lock != "🔒": rows.append([InlineKeyboardButton(f"P{floor} · {name}", callback_data=f"sao:quest:{qid}")])
    rows.append([InlineKeyboardButton("⬅️ Aincrad", callback_data="sao:home")])
    await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))


def _quest(qid: int) -> Optional[Dict]:
    conn = _get_connection()
    try:
        c = conn.cursor(); c.execute("SELECT quest_id,floor,name,enemy,recommended_power,enemy_hp,enemy_atk,reward_col,reward_md,stamina_cost FROM saocb_quests_tb WHERE quest_id=%s AND active=TRUE", (qid,))
        r = c.fetchone()
        if not r: return None
        keys = ["quest_id","floor","name","enemy","recommended_power","enemy_hp","enemy_atk","reward_col","reward_md","stamina_cost"]
        return dict(zip(keys, r))
    finally:_put_connection(conn)


async def _show_quest(q, uid: int, qid: int):
    quest = _quest(qid)
    if not quest: return await q.answer("Quest no disponible.", show_alert=True)
    p = _player(uid); _, _, _, power, _ = _party_stats(uid)
    text = (
        f"🗺️ Piso {quest['floor']} · {quest['name']}\n\n"
        f"👹 {quest['enemy']}\n"
        f"❤️ HP enemigo: {quest['enemy_hp']:,}\n"
        f"⚔️ ATK enemigo: {quest['enemy_atk']:,}\n"
        f"💥 Recomendado: {quest['recommended_power']:,}\n"
        f"💥 Tu party: {power:,}\n\n"
        f"🎁 {quest['reward_col']:,} Col · primera victoria +{quest['reward_md']} PiPesos/💎\n"
        f"⚡ Coste: {quest['stamina_cost']} · tienes {p['stamina']}"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("⚔️ Entrar", callback_data=f"sao:battlestart:{qid}")], [InlineKeyboardButton("⬅️ Quests", callback_data="sao:quests")]])
    await q.edit_message_text(text, reply_markup=kb)


def _battle_get(user_id: int) -> Optional[Dict]:
    conn = _get_connection()
    try:
        c = conn.cursor(); c.execute("SELECT user_id,quest_id,enemy_hp,player_hp,turn,guarding,skill_cd FROM saocb_battles_tb WHERE user_id=%s", (user_id,)); r=c.fetchone()
        if not r:return None
        return dict(zip(["user_id","quest_id","enemy_hp","player_hp","turn","guarding","skill_cd"], r))
    finally:_put_connection(conn)


def _start_battle(user_id: int, qid: int) -> Tuple[bool, str]:
    quest = _quest(qid)
    if not quest:return False,"Quest no disponible."
    hp, _, _, power, party = _party_stats(user_id)
    if not party:return False,"Necesitas al menos una unidad en tu party."
    conn = _get_connection()
    try:
        c=conn.cursor(); stamina,_=_regen_stamina_locked(c,user_id)
        c.execute("SELECT 1 FROM saocb_battles_tb WHERE user_id=%s",(user_id,))
        if c.fetchone(): conn.rollback(); return False,"Ya tienes una batalla activa."
        if stamina<quest["stamina_cost"]: conn.rollback(); return False,"No tienes suficiente stamina."
        c.execute("UPDATE saocb_players_tb SET stamina=stamina-%s,stamina_updated_at=CASE WHEN stamina=%s THEN NOW() ELSE stamina_updated_at END WHERE user_id=%s",(quest["stamina_cost"],MAX_STAMINA,user_id))
        c.execute("INSERT INTO saocb_battles_tb(user_id,quest_id,enemy_hp,player_hp) VALUES(%s,%s,%s,%s)",(user_id,qid,quest["enemy_hp"],hp))
        conn.commit(); return True,""
    except Exception:
        conn.rollback(); raise
    finally:_put_connection(conn)


def _battle_text(user_id:int, note:str="") -> Tuple[str,InlineKeyboardMarkup]:
    b=_battle_get(user_id)
    if not b:return "No hay batalla activa.",_back_home()
    quest=_quest(b["quest_id"]); maxhp,_,_,power,party=_party_stats(user_id)
    main=party[0] if party else None
    emax=quest["enemy_hp"]
    text=(
      f"🔥 BATALLA · TURNO {b['turn']}\n\n"
      f"🧑 {main['name'] if main else 'Party'} · ❤️ {max(0,b['player_hp']):,}/{maxhp:,}\n"
      f"👹 {quest['enemy']} · ❤️ {max(0,b['enemy_hp']):,}/{emax:,}\n"
      f"💥 Poder {power:,}\n"
    )
    if note:text += f"\n{note}\n"
    skill_label=f"✨ {main['skill_name']}" if main and b["skill_cd"]<=0 else f"✨ Skill ({b['skill_cd']})"
    kb=InlineKeyboardMarkup([
      [InlineKeyboardButton("⚔️ Atacar",callback_data="sao:battleact:attack"),InlineKeyboardButton("🛡 Guardar",callback_data="sao:battleact:guard")],
      [InlineKeyboardButton(skill_label,callback_data="sao:battleact:skill")],
      [InlineKeyboardButton("🏃 Retirarse",callback_data="sao:battleact:retreat")]
    ])
    return text,kb


def _finish_victory(c,user_id:int,quest:Dict,party:List[Dict]) -> str:
    c.execute("SELECT clear_count FROM saocb_quest_progress_tb WHERE user_id=%s AND quest_id=%s FOR UPDATE",(user_id,quest["quest_id"])); row=c.fetchone(); first=not row or int(row[0])==0
    md=quest["reward_md"] if first else 0
    exp_gain=max(100,quest["recommended_power"]//8)
    c.execute("UPDATE saocb_players_tb SET col=col+%s,exp=exp+%s,floor=GREATEST(floor,%s),updated_at=NOW() WHERE user_id=%s",(quest["reward_col"],exp_gain,quest["floor"],user_id))
    if md:
        c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s", (md, user_id))
    c.execute("SELECT exp,rank FROM saocb_players_tb WHERE user_id=%s",(user_id,))
    exp_now,rank_now=c.fetchone(); expected_rank=1+int(exp_now)//1000
    if expected_rank>int(rank_now):
        c.execute("UPDATE saocb_players_tb SET rank=%s WHERE user_id=%s",(expected_rank,user_id))
    c.execute("""INSERT INTO saocb_quest_progress_tb(user_id,quest_id,clear_count,best_rank,last_clear_at) VALUES(%s,%s,1,3,NOW())
               ON CONFLICT(user_id,quest_id) DO UPDATE SET clear_count=saocb_quest_progress_tb.clear_count+1,best_rank=GREATEST(saocb_quest_progress_tb.best_rank,3),last_clear_at=NOW()""",(user_id,quest["quest_id"]))
    for u in party:
        # Level-up directly from quest EXP; compact and deterministic.
        gain=max(30,quest["recommended_power"]//30)
        new_level=min(_max_level(u["stars"],u["awaken"]),u["level"]+max(1,gain//300))
        c.execute("UPDATE saocb_user_units_tb SET exp=exp+%s,level=GREATEST(level,%s) WHERE user_id=%s AND unit_id=%s",(gain,new_level,user_id,u["unit_id"]))
    return f"🏆 Victoria. +{quest['reward_col']:,} Col"+(f" · +{md} PiPesos/💎 (primera victoria)" if md else "")+f" · +{exp_gain} EXP"


def _battle_action(user_id:int,action:str) -> Tuple[str,bool]:
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT quest_id,enemy_hp,player_hp,turn,guarding,skill_cd FROM saocb_battles_tb WHERE user_id=%s FOR UPDATE",(user_id,)); r=c.fetchone()
        if not r:return "No hay batalla activa.",True
        b=dict(zip(["quest_id","enemy_hp","player_hp","turn","guarding","skill_cd"],r)); quest=_quest(b["quest_id"]); maxhp,atk,defense,power,party=_party_stats(user_id); main=party[0]
        if action=="retreat":
            c.execute("DELETE FROM saocb_battles_tb WHERE user_id=%s",(user_id,)); conn.commit(); return "🏃 Te retiraste. La stamina usada no se devuelve.",True
        if action=="skill" and b["skill_cd"]>0:
            conn.rollback(); return f"La skill estará lista en {b['skill_cd']} turno(s).",False
        if action=="guard":
            damage=max(1,int(quest["enemy_atk"]*random.uniform(.80,1.10)-defense*.20)); damage=max(1,damage//2)
            player_hp=b["player_hp"]-damage; enemy_hp=b["enemy_hp"]; note=f"🛡 Bloqueaste parte del golpe. Recibiste {damage:,}."; skill_cd=max(0,b["skill_cd"]-1)
        else:
            if action=="skill":
                dealt=max(1,int(atk*main["skill_power"]*random.uniform(.92,1.08))); skill_cd=2; label=f"✨ {main['skill_name']}"
            else:
                dealt=max(1,int(atk*random.uniform(.82,1.12))); skill_cd=max(0,b["skill_cd"]-1); label="⚔️ Ataque"
            enemy_hp=b["enemy_hp"]-dealt
            if enemy_hp<=0:
                reward=_finish_victory(c,user_id,quest,party); c.execute("DELETE FROM saocb_battles_tb WHERE user_id=%s",(user_id,)); conn.commit(); return f"{label}: {dealt:,} daño.\n{reward}",True
            incoming=max(1,int(quest["enemy_atk"]*random.uniform(.85,1.15)-defense*.18)); player_hp=b["player_hp"]-incoming; note=f"{label}: {dealt:,} daño.\n👹 Contraataque: {incoming:,} daño."
        if player_hp<=0:
            c.execute("DELETE FROM saocb_battles_tb WHERE user_id=%s",(user_id,)); conn.commit(); return note+"\n💀 Tu party cayó. Mejora unidades o cambia la formación y vuelve a intentarlo.",True
        c.execute("UPDATE saocb_battles_tb SET enemy_hp=%s,player_hp=%s,turn=turn+1,guarding=FALSE,skill_cd=%s,updated_at=NOW() WHERE user_id=%s",(enemy_hp,player_hp,skill_cd,user_id)); conn.commit(); return note,False
    except Exception:
        conn.rollback(); raise
    finally:_put_connection(conn)


async def _show_upgrade(q,uid:int,page:int=0):
    units=_user_units(uid); per=6; pages=max(1,math.ceil(len(units)/per)); page=max(0,min(page,pages-1)); chunk=units[page*per:(page+1)*per]
    p=_player(uid); lines=["⬆️ MEJORAR UNIDADES",f"🪙 Col: {p['col']:,} · 🧩 Fragmentos: {p['fragments']:,}",""] ; rows=[]
    for u in chunk:
        maxlv=_max_level(u['stars'],u['awaken']); cost=500+u['level']*120
        lines.append(f"{_stars(u['stars'])} {u['name']} · Lv.{u['level']}/{maxlv} · coste {cost:,} Col")
        rows.append([InlineKeyboardButton(f"⬆️ {u['name']}",callback_data=f"sao:upgradeunit:{u['unit_id']}")])
    nav=[]
    if page>0:nav.append(InlineKeyboardButton("◀️",callback_data=f"sao:upgrade:{page-1}"))
    nav.append(InlineKeyboardButton("🏠",callback_data="sao:home"))
    if page+1<pages:nav.append(InlineKeyboardButton("▶️",callback_data=f"sao:upgrade:{page+1}"))
    rows.append(nav); await q.edit_message_text("\n".join(lines),reply_markup=InlineKeyboardMarkup(rows))


def _upgrade_unit(user_id:int,unit_id:int)->str:
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""SELECT u.level,u.awaken,c.stars,c.name FROM saocb_user_units_tb u JOIN saocb_units_catalog_tb c ON c.unit_id=u.unit_id WHERE u.user_id=%s AND u.unit_id=%s FOR UPDATE""",(user_id,unit_id)); r=c.fetchone()
        if not r:return "No tienes esa unidad."
        level,awaken,stars,name=int(r[0]),int(r[1]),int(r[2]),r[3]; maxlv=_max_level(stars,awaken)
        if level>=maxlv:return f"{name} ya está en su nivel máximo ({maxlv})."
        cost=500+level*120
        c.execute("SELECT col FROM saocb_players_tb WHERE user_id=%s FOR UPDATE",(user_id,)); col=int(c.fetchone()[0])
        if col<cost:conn.rollback();return f"Necesitas {cost:,} Col."
        c.execute("UPDATE saocb_players_tb SET col=col-%s WHERE user_id=%s",(cost,user_id)); c.execute("UPDATE saocb_user_units_tb SET level=level+1 WHERE user_id=%s AND unit_id=%s",(user_id,unit_id)); conn.commit();return f"⬆️ {name} subió a Lv.{level+1}. Coste: {cost:,} Col."
    except Exception:
        conn.rollback();raise
    finally:_put_connection(conn)


def _claim_daily(user_id:int)->Tuple[bool,str]:
    today=datetime.now(ZoneInfo("America/Mexico_City")).date(); conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT daily_claim FROM saocb_players_tb WHERE user_id=%s FOR UPDATE",(user_id,)); row=c.fetchone()
        if row and row[0]==today:conn.rollback();return False,"Ya reclamaste el regalo de hoy."
        c.execute("UPDATE saocb_players_tb SET daily_claim=%s,col=col+1500 WHERE user_id=%s",(today,user_id)); c.execute("UPDATE usuarios_tb SET saldo=saldo+25 WHERE id_user=%s",(user_id,)); conn.commit();return True,"🎁 Diario: +25 PiPesos (💎) y +1,500 Col."
    except Exception:
        conn.rollback();raise
    finally:_put_connection(conn)


async def _show_ranking(q,uid:int):
    conn=_get_connection()
    try:
        c=conn.cursor();c.execute("""SELECT p.user_id,p.rank,p.floor,p.col,COALESCE(SUM((uc.base_atk*(1+(u.level-1)*0.035))*2 + uc.base_def*(1+(u.level-1)*0.035) + (uc.base_hp*(1+(u.level-1)*0.035))/8),0) AS power,p.player_name
            FROM saocb_players_tb p
            LEFT JOIN saocb_parties_tb pt ON pt.user_id=p.user_id
            LEFT JOIN saocb_user_units_tb u ON u.user_id=pt.user_id AND u.unit_id=pt.unit_id
            LEFT JOIN saocb_units_catalog_tb uc ON uc.unit_id=u.unit_id
            GROUP BY p.user_id,p.rank,p.floor,p.col,p.player_name ORDER BY p.floor DESC,power DESC LIMIT 10""");rows=c.fetchall()
    finally:_put_connection(conn)
    lines=["🏆 RANKING AINCRAD",""]
    for i,r in enumerate(rows,1):
        mark=" 👑" if int(r[0])==uid else ""
        name=(r[5] or "").strip() or visible_user(user_id=int(r[0]))
        lines.append(f"{i}. {name} · Piso {r[2]} · {int(r[4]):,} POW{mark}")
    await q.edit_message_text("\n".join(lines),reply_markup=_back_home())


async def sao_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; _ensure_player(uid)
    p=q.data.split(":"); action=p[1] if len(p)>1 else "home"
    try:
        if action=="home":return await _show_home(q,uid)
        if action=="profile":return await _show_profile(q,uid)
        if action=="name":
            return await q.edit_message_text("✏️ NOMBRE DE AINCRAD\n\nEscribe /saonombre TuNombre\n\nEjemplo: /saonombre Kiu", reply_markup=_back_home())
        if action=="units":return await _show_units(q,uid,int(p[2]) if len(p)>2 else 0)
        if action=="unit":return await _show_unit(q,uid,int(p[2]))
        if action=="party":return await _show_party(q,uid)
        if action=="partyset":
            msg=_set_party_slot(uid,int(p[2]),int(p[3])); await q.answer(msg,show_alert=False); return await _show_party(q,uid)
        if action=="scout":return await _show_scout(q,uid)
        if action=="draw":return await _draw(q,uid,int(p[2]))
        if action=="quests":return await _show_quests(q,uid)
        if action=="quest":return await _show_quest(q,uid,int(p[2]))
        if action=="battlestart":
            ok,msg=_start_battle(uid,int(p[2]));
            if not ok:return await q.answer(msg,show_alert=True)
            text,kb=_battle_text(uid,"⚔️ Entraste al combate.");return await q.edit_message_text(text,reply_markup=kb)
        if action=="battle":
            text,kb=_battle_text(uid);return await q.edit_message_text(text,reply_markup=kb)
        if action=="battleact":
            note,done=_battle_action(uid,p[2])
            if done:
                return await q.edit_message_text(note,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Aincrad",callback_data="sao:home"),InlineKeyboardButton("🗺️ Quests",callback_data="sao:quests")]]))
            text,kb=_battle_text(uid,note);return await q.edit_message_text(text,reply_markup=kb)
        if action=="upgrade":return await _show_upgrade(q,uid,int(p[2]) if len(p)>2 else 0)
        if action=="upgradeunit":
            msg=_upgrade_unit(uid,int(p[2]));await q.answer(msg,show_alert=True);return await _show_unit(q,uid,int(p[2]))
        if action=="daily":
            _,msg=_claim_daily(uid);await q.answer(msg,show_alert=True);return await _show_home(q,uid)
        if action=="ranking":return await _show_ranking(q,uid)
        return await q.answer("Opción no disponible.",show_alert=True)
    except Exception as exc:
        print(f"[SAO-TG ERROR] {type(exc).__name__}: {exc}")
        try: await q.answer("SAO-CB tuvo un error. No se perdió tu progreso.",show_alert=True)
        except Exception: pass
