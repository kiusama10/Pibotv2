from __future__ import annotations

import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.database.database import _get_connection, _put_connection
from src.utils.seasonal import current_season

MX = ZoneInfo("America/Mexico_City")
RARE_EMOJI = {"comun":"⚪","raro":"🔵","epico":"🟣","legendario":"🟡","mitico":"🔴"}

# code: (name, type, rarity, price, season-or-None)
COSMETICS = {
    "marco_clasico": ("Marco Clásico", "marco", "comun", 3000, None),
    "marco_cadenas": ("Marco de Cadenas", "marco", "raro", 18000, None),
    "marco_obsidiana": ("Marco de Obsidiana", "marco", "epico", 45000, None),
    "marco_vampiro": ("Marco Vampírico", "marco", "legendario", 95000, None),
    "marco_anime_neon": ("Marco Anime Neón", "marco", "epico", 55000, None),
    "insignia_brattamer": ("Brat Tamer", "insignia", "raro", 22000, None),
    "insignia_pet": ("Pet de Élite", "insignia", "raro", 22000, None),
    "insignia_dom": ("Dominio Carmesí", "insignia", "epico", 50000, None),
    "insignia_kitsune": ("Kitsune Imperial", "insignia", "legendario", 110000, None),
    "insignia_otaku": ("Otaku Supremo", "insignia", "comun", 8000, None),
    "marco_halloween": ("Marco Noche de Brujas", "marco", "epico", 60000, "halloween"),
    "insignia_calabaza": ("Calabaza Eterna", "insignia", "raro", 30000, "halloween"),
    "marco_mictlan": ("Marco del Mictlán", "marco", "legendario", 120000, "dia_muertos"),
    "insignia_catrina": ("Catrina Nocturna", "insignia", "epico", 65000, "dia_muertos"),
    "marco_navidad": ("Marco Invernal", "marco", "epico", 60000, "navidad"),
    "insignia_estrella": ("Estrella de Invierno", "insignia", "raro", 30000, "navidad"),
    "marco_valentin": ("Marco Corazón Carmesí", "marco", "epico", 60000, "san_valentin"),
    "insignia_corazon": ("Corazón Encadenado", "insignia", "raro", 30000, "san_valentin"),
}


def _rotation(now=None):
    now = now or datetime.now(MX)
    slot = 0 if now.hour < 12 else 1
    slot_start = now.replace(hour=slot * 12, minute=0, second=0, microsecond=0)
    if slot == 0:
        slot_end = now.replace(hour=12, minute=0, second=0, microsecond=0)
    else:
        from datetime import timedelta
        slot_end = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return f"{slot_start.date().isoformat()}-{slot}", slot_end


def _countdown():
    _, end = _rotation()
    secs = max(0, int((end - datetime.now(MX)).total_seconds()))
    h, rem = divmod(secs, 3600); m = rem // 60
    return f"{h:02d}h {m:02d}m"


def _available_catalog():
    """Stable 12-hour rotation. Commons stay; seasonal items join only in their season."""
    season = current_season()
    eligible = {c:d for c,d in COSMETICS.items() if d[4] is None or d[4] == season}
    permanent = {c:d for c,d in eligible.items() if d[2] == "comun"}
    rotating = [(c,d) for c,d in eligible.items() if d[2] != "comun"]
    key, _ = _rotation()
    rotating.sort(key=lambda x: hashlib.sha256(f"{key}:{x[0]}".encode()).hexdigest())
    # Six changing pieces plus all cheap commons. Seasonal pieces are forced into the window.
    seasonal = [(c,d) for c,d in rotating if d[4] == season and season != "normal"]
    chosen = seasonal[:]
    for item in rotating:
        if item not in chosen and len(chosen) < 6:
            chosen.append(item)
    return {**permanent, **dict(chosen)}


def _buy(uid:int, code:str):
    item = _available_catalog().get(code)
    if not item: return "missing", None
    name, ctype, rarity, price, season = item
    conn = _get_connection()
    try:
        cur=conn.cursor(); cur.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s FOR UPDATE",(uid,)); row=cur.fetchone()
        if not row or row[0] < price: conn.rollback(); return "money", None
        cur.execute("SELECT cosmetic_id FROM profile_cosmetics_tb WHERE owner_id=%s AND code=%s",(uid,code))
        if cur.fetchone(): conn.rollback(); return "owned", None
        cur.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo>=%s",(price,uid,price))
        if cur.rowcount != 1: conn.rollback(); return "money", None
        cur.execute("""INSERT INTO profile_cosmetics_tb(code,nombre,cosmetic_type,rareza,precio_compra,owner_id,season_key)
                       VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING cosmetic_id""",(code,name,ctype,rarity,price,uid,season))
        cid=cur.fetchone()[0]; conn.commit(); return "ok",(cid,name,ctype,rarity,price)
    except Exception as exc:
        conn.rollback(); print("[COSMETICS] buy",exc); return "error",None
    finally: _put_connection(conn)


def _owned(uid:int, ctype=None):
    conn=_get_connection()
    try:
        cur=conn.cursor(); sql="SELECT cosmetic_id,nombre,cosmetic_type,rareza,precio_compra,code FROM profile_cosmetics_tb WHERE owner_id=%s"; args=[uid]
        if ctype: sql += " AND cosmetic_type=%s"; args.append(ctype)
        sql += " ORDER BY cosmetic_type,rareza,nombre"; cur.execute(sql,tuple(args)); return cur.fetchall()
    finally: _put_connection(conn)


def _equip(uid:int,cid:int,ctype:str):
    col="marco_equipado_id" if ctype=="marco" else "insignia_equipada_id"; conn=_get_connection()
    try:
        cur=conn.cursor(); cur.execute("SELECT nombre FROM profile_cosmetics_tb WHERE cosmetic_id=%s AND owner_id=%s AND cosmetic_type=%s FOR UPDATE",(cid,uid,ctype)); row=cur.fetchone()
        if not row: conn.rollback(); return None
        cur.execute(f"UPDATE perfiles_tb SET {col}=%s WHERE id_user=%s",(cid,uid)); conn.commit(); return row[0]
    except Exception as exc:
        conn.rollback(); print("[COSMETICS] equip",exc); return None
    finally: _put_connection(conn)


def _home_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍️ Tienda",callback_data="cos_shop"), InlineKeyboardButton("🎒 Mi colección",callback_data="cos_collection")],
        [InlineKeyboardButton("🖼️ Mis marcos",callback_data="cos_owned_marco"), InlineKeyboardButton("🎖️ Mis insignias",callback_data="cos_owned_insignia")],
        [InlineKeyboardButton("👤 Volver a mi perfil",callback_data="cos_profile")],
    ])


def _home_text():
    season=current_season(); extra="\n🎉 Hay piezas especiales de temporada disponibles." if season!="normal" else ""
    return ("✨ VESTIDOR DE PIBOT\n\nAquí puedes comprar y equipar tu perfil sin escribir IDs ni códigos."
            f"\n\n🔄 La colección cambia en {_countdown()}.{extra}")


async def send_cosmetics_home(update:Update, context:ContextTypes.DEFAULT_TYPE, edit=False):
    target=update.callback_query if update.callback_query else update.message
    if edit and update.callback_query:
        await target.edit_message_text(_home_text(),reply_markup=_home_markup())
    else:
        await target.reply_text(_home_text(),reply_markup=_home_markup())


async def cosmeticos(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        me=await context.bot.get_me(); url=f"https://t.me/{me.username}?start=vestidor"
        return await update.message.reply_text("✨ Tu vestidor está en privado.\nTe mando directo para que cambies tu perfil sin llenar el grupo de botones. 😌",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✨ Abrir mi vestidor",url=url)]]))
    await send_cosmetics_home(update,context)


async def cosmetics_callback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); uid=q.from_user.id
    if q.message.chat.type != "private": return await q.answer("El vestidor solo funciona por privado.",show_alert=True)
    data=q.data
    if data=="cos_home": return await send_cosmetics_home(update,context,edit=True)
    if data=="cos_shop":
        rows=[]
        for code,(name,ctype,rarity,price,season) in _available_catalog().items():
            icon="🖼️" if ctype=="marco" else "🎖️"; rows.append([InlineKeyboardButton(f"{icon} {RARE_EMOJI.get(rarity,'')} {name} · {price:,}",callback_data=f"cos_view_{code}")])
        rows.append([InlineKeyboardButton("⬅️ Vestidor",callback_data="cos_home")])
        return await q.edit_message_text(f"🛍️ TIENDA COSMÉTICA\n\n🔄 Cambia en {_countdown()}\nToca una pieza para verla y comprarla.",reply_markup=InlineKeyboardMarkup(rows))
    if data.startswith("cos_view_"):
        code=data[9:]; item=_available_catalog().get(code)
        if not item: return await q.edit_message_text("⏳ Esa pieza ya no está en la rotación actual.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ Volver",callback_data="cos_shop")]]))
        name,ctype,rarity,price,season=item; icon="🖼️ Marco" if ctype=="marco" else "🎖️ Insignia"; seasonal="\n🎃/🎄 Edición de temporada" if season else ""
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(f"💰 Comprar por {price:,} PP",callback_data=f"cos_buy_{code}")],[InlineKeyboardButton("⬅️ Tienda",callback_data="cos_shop")]])
        return await q.edit_message_text(f"{icon}: {name}\n{RARE_EMOJI.get(rarity,'')} {rarity.title()}\n💰 {price:,} PiPesos{seasonal}",reply_markup=kb)
    if data.startswith("cos_buy_"):
        code=data[8:]; status,res=_buy(uid,code)
        if status=="ok":
            cid,name,ctype,rarity,price=res; typ="m" if ctype=="marco" else "i"
            kb=InlineKeyboardMarkup([[InlineKeyboardButton("✨ Equipar ahora",callback_data=f"cos_eq_{typ}_{cid}")],[InlineKeyboardButton("🛍️ Seguir viendo",callback_data="cos_shop"),InlineKeyboardButton("🏠 Vestidor",callback_data="cos_home")]])
            return await q.edit_message_text(f"✅ ¡Ya es tuyo!\n\n{name}\n{RARE_EMOJI.get(rarity,'')} {rarity.title()} · {price:,} PiPesos",reply_markup=kb)
        msg={"money":"💸 No tienes suficientes PiPesos.","owned":"😌 Ese cosmético ya está en tu colección.","missing":"⏳ Esa pieza ya salió de la rotación."}.get(status,"⚠️ No pude completar la compra.")
        return await q.answer(msg,show_alert=True)
    if data in {"cos_collection","cos_owned_marco","cos_owned_insignia"}:
        ctype=None if data=="cos_collection" else ("marco" if data.endswith("marco") else "insignia"); owned=_owned(uid,ctype)
        if not owned: return await q.edit_message_text("✨ Todavía no tienes piezas en esta sección.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ Ir a la tienda",callback_data="cos_shop"),InlineKeyboardButton("⬅️ Vestidor",callback_data="cos_home")]]))
        rows=[]
        for cid,name,kind,rarity,price,code in owned[:30]:
            typ="m" if kind=="marco" else "i"; icon="🖼️" if kind=="marco" else "🎖️"
            rows.append([InlineKeyboardButton(f"{icon} {RARE_EMOJI.get(rarity,'')} {name}",callback_data=f"cos_eq_{typ}_{cid}")])
        rows.append([InlineKeyboardButton("⬅️ Vestidor",callback_data="cos_home")])
        return await q.edit_message_text("🎒 TU COLECCIÓN\n\nToca una pieza para equiparla. No necesitas copiar ningún ID.",reply_markup=InlineKeyboardMarkup(rows))
    if data.startswith("cos_eq_"):
        try: _,_,typ,cid=data.split("_",3); cid=int(cid)
        except Exception: return await q.answer("Selección inválida.",show_alert=True)
        ctype="marco" if typ=="m" else "insignia"; name=_equip(uid,cid,ctype)
        if not name: return await q.answer("Esa pieza no pertenece a tu colección.",show_alert=True)
        await q.answer(f"Equipado: {name} ✨",show_alert=True)
        return await send_cosmetics_home(update,context,edit=True)
    if data=="cos_profile":
        from handlers.profile_social import _render
        text=_render(uid,uid); me=await context.bot.get_me()
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Editar mi perfil",url=f"https://t.me/{me.username}?start=editar_perfil")],[InlineKeyboardButton("✨ Vestidor",callback_data="cos_home")]])
        return await q.edit_message_text(text,reply_markup=kb)


# Legacy commands kept only for compatibility; users no longer need IDs/codes.
async def comprarcosmetico(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await cosmeticos(update,context)
async def miscosmeticos(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await cosmeticos(update,context)
async def equiparmarco(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await cosmeticos(update,context)
async def equiparinsignia(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await cosmeticos(update,context)
