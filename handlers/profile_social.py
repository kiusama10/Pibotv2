from __future__ import annotations
from src.utils.seasonal import seasonalize

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from io import BytesIO
import time
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from telegram.ext import ContextTypes

from src.database.database import _get_connection, _put_connection
from src.utils.seasonal import current_season, profile_style

EDITABLE = {
    "rol": "Rol BDSM",
    "experiencia": "Experiencia",
    "gustos": "Gustos",
    "bio": "Sobre mí",
    "frase": "Mi frase",
    "limites": "Límites",
}

CUSTOM_FRAME_BORDERS = {
    "marco_clasico": "✨╔══════════════╗✨",
    "marco_cadenas": "⛓️╠══════════════╣⛓️",
    "marco_obsidiana": "🖤◆━━━━━━━━━━━━◆🖤",
    "marco_vampiro": "🩸♛━━━━━━━━━━━━♛🩸",
    "marco_anime_neon": "🌸✦════════════✦🌸",
    "marco_dragon": "🐉╬════════════╬🐉",
    "marco_infernal": "🔥⛧━━━━━━━━━━━━⛧🔥",
    "marco_celestial": "🪽✧════════════✧🪽",
    "marco_realeza": "👑♜════════════♜👑",
    "marco_kitsune": "🦊⛩️━━━━━━━━━━⛩️🦊",
    "marco_halloween": "🎃🕸️━━━━━━━━━━🕸️🎃",
    "marco_mictlan": "💀🌼━━━━━━━━━━🌼💀",
    "marco_navidad": "🎄❄️━━━━━━━━━━❄️🎄",
    "marco_valentin": "💘🌹━━━━━━━━━━🌹💘",
    "marco_eclipse": "🌘✦━━━━ ECLIPSE ━━━━✦🌒",
    "marco_aurora": "🌌✧━━━━ AURORA ━━━━✧🌌",
    "marco_void": "🕳️◆━━━━ VOID ━━━━◆🕳️",
    "marco_fenix": "🔥🪽━━━━ FÉNIX ━━━━🪽🔥",
    "marco_sakura": "🌸⛩️━━━━ SAKURA ━━━━⛩️🌸",
    "marco_cyberpunk": "💠⚡━━━━ 2099 ━━━━⚡💠",
    "marco_angel_caido": "🖤🪽━━━━ FALLEN ━━━━🪽🖤",
    "marco_rey_tortugas": "👑🐢━━━━ REY ━━━━🐢👑",
    "marco_saiyajin": "⚡✦━━━━ AURA ━━━━✦⚡",
    "marco_ninja_rojo": "🌙🔴━━━━ NINJA ━━━━🔴🌙",
    "marco_grand_line": "☠️🌊━━━━ GRAND LINE ━━━━🌊☠️",
    "marco_cazador_demonios": "🌊🔥━━━━ RESPIRACIÓN ━━━━🔥🌊",
    "marco_infinito": "🔵♾️━━━━ INFINITO ━━━━♾️🔵",
    "marco_luna_magica": "🌙✨━━━━ GUARDIANA ━━━━✨🌙",
    "marco_mecha_neon": "🟣⚡━━━━ MECHA ━━━━⚡🟢",
    "marco_titan": "🪽🧱━━━━ MURALLA ━━━━🧱🪽",
}



def _ensure_profile_phrase():
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("ALTER TABLE perfiles_tb ADD COLUMN IF NOT EXISTS frase TEXT")
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        _put_connection(conn)


def _editor_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎭 Rol", callback_data="profile_role"), InlineKeyboardButton("⭐ Experiencia", callback_data="profile_experience")],
        [InlineKeyboardButton("💜 Gustos", callback_data="profile_text_gustos"), InlineKeyboardButton("💞 Vínculo", callback_data="profile_help_vinculo")],
        [InlineKeyboardButton("🪪 Sobre mí", callback_data="profile_text_bio"), InlineKeyboardButton("💬 Mi frase", callback_data="profile_text_frase")],
        [InlineKeyboardButton("🛡️ Límites", callback_data="profile_text_limites"), InlineKeyboardButton("🔐 Privacidad", callback_data="profile_privacy")],
        [InlineKeyboardButton("🏷️ Títulos", callback_data="profile_help_titles"), InlineKeyboardButton("✨ Vestidor", callback_data="profile_help_cosmetics")],
        [InlineKeyboardButton("📸 Foto de mi tarjeta", callback_data="profile_photo"), InlineKeyboardButton("👁️ Ver mi perfil", callback_data="profile_preview")],
    ])


def _back_editor():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver al editor", callback_data="profile_editor")]])


def _set_pending_text(context, field):
    context.user_data["profile_edit_field"] = field


async def _editor_screen(q):
    await q.edit_message_text(
        "✨ MI PERFIL · EDITOR\n\n"
        "Hazlo tuyo. Toca una sección para cambiarla; solo escribes cuando quieras poner algo personal.\n\n"
        "🎭 Rol · ⭐ experiencia · 💜 gustos\n"
        "🔗 vínculo · 🪪 sobre mí · 💬 frase\n"
        "🛡️ límites · 🔐 privacidad\n"
        "🏷️ títulos · ✨ marcos e insignias",
        reply_markup=_editor_markup(),
    )


def _profile(uid: int):
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT p.nombre,p.username,p.rol,p.experiencia,p.gustos,p.relacion,p.bio,p.frase,p.limites,
                   p.perfil_publico,u.saldo,p.titulo_equipado_id,a.nombre,a.rareza,a.serial_no,a.serial_total,
                   f.cosmetic_id,f.nombre,f.code,b.cosmetic_id,b.nombre,b.code,p.profile_photo_file_id
            FROM usuarios_tb u
            JOIN perfiles_tb p ON p.id_user=u.id_user
            LEFT JOIN social_assets_tb a ON a.asset_id=p.titulo_equipado_id AND a.propietario_id=p.id_user
            LEFT JOIN profile_cosmetics_tb f ON f.cosmetic_id=p.marco_equipado_id AND f.owner_id=p.id_user AND f.cosmetic_type='marco'
            LEFT JOIN profile_cosmetics_tb b ON b.cosmetic_id=p.insignia_equipada_id AND b.owner_id=p.id_user AND b.cosmetic_type='insignia'
            WHERE p.id_user=%s
            """,
            (uid,),
        )
        return c.fetchone()
    finally:
        _put_connection(conn)


def _counts(uid: int):
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT asset_type,COUNT(*) FROM social_assets_tb WHERE propietario_id=%s GROUP BY asset_type",
            (uid,),
        )
        counts = dict(c.fetchall())
        c.execute(
            "SELECT cosmetic_type,COUNT(*) FROM profile_cosmetics_tb WHERE owner_id=%s GROUP BY cosmetic_type",
            (uid,),
        )
        counts.update({f"cos_{k}": v for k, v in c.fetchall()})
        return counts
    finally:
        _put_connection(conn)


def _set_field(uid: int, field: str, value: str):
    if field not in EDITABLE:
        return False
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute(f"UPDATE perfiles_tb SET {field}=%s WHERE id_user=%s", (value[:500], uid))
        conn.commit()
        return c.rowcount == 1
    except Exception:
        conn.rollback()
        return False
    finally:
        _put_connection(conn)


def _set_public(uid: int, value: bool):
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE perfiles_tb SET perfil_publico=%s WHERE id_user=%s", (value, uid))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        _put_connection(conn)


def _equip(uid: int, aid: int):
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT nombre FROM social_assets_tb WHERE asset_id=%s AND propietario_id=%s AND asset_type='titulo' AND estado='disponible' FOR UPDATE",
            (aid, uid),
        )
        r = c.fetchone()
        if not r:
            conn.rollback()
            return None
        c.execute("UPDATE perfiles_tb SET titulo_equipado_id=%s WHERE id_user=%s", (aid, uid))
        conn.commit()
        return r[0]
    except Exception:
        conn.rollback()
        return None
    finally:
        _put_connection(conn)


def _gift_summary(uid: int, viewer: int):
    conn = _get_connection()
    try:
        c = conn.cursor()
        # Los regalos marcados como privados solo aparecen al propietario.
        if viewer == uid:
            c.execute(
                """SELECT nombre, COUNT(*) FROM social_assets_tb
                   WHERE propietario_id=%s AND asset_type='regalo'
                   GROUP BY nombre ORDER BY COUNT(*) DESC, nombre LIMIT 20""", (uid,)
            )
        else:
            c.execute(
                """SELECT nombre, COUNT(*) FROM social_assets_tb
                   WHERE propietario_id=%s AND asset_type='regalo'
                     AND COALESCE(regalo_privado,FALSE)=FALSE
                   GROUP BY nombre ORDER BY COUNT(*) DESC, nombre LIMIT 20""", (uid,)
            )
        return c.fetchall()
    finally:
        _put_connection(conn)


def _save_profile_photo(uid: int, file_id: str | None):
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE perfiles_tb SET profile_photo_file_id=%s WHERE id_user=%s", (file_id, uid))
        conn.commit()
        return c.rowcount == 1
    except Exception:
        conn.rollback()
        return False
    finally:
        _put_connection(conn)


def _render(uid: int, viewer: int):
    r = _profile(uid)
    if not r:
        return "No encontré ese perfil."
    (
        nombre, username, rol, exp, gustos, rel, bio, frase, limites, publico, saldo,
        tid, tname, trare, sn, st, frame_id, frame_name, frame_code,
        badge_id, badge_name, badge_code, custom_photo_file_id,
    ) = r
    if viewer != uid and not publico:
        return "🔒 Este perfil es privado."

    counts = _counts(uid)
    formal_link=None
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT CASE WHEN v.user_a=%s THEN v.user_b ELSE v.user_a END FROM vinculos_tb v WHERE v.status='active' AND (v.user_a=%s OR v.user_b=%s) ORDER BY v.vinculo_id DESC LIMIT 1",(uid,uid,uid)); vr=c.fetchone()
        if vr:
            c.execute("SELECT COALESCE(NULLIF(username,''),nombre,%s) FROM perfiles_tb WHERE id_user=%s",(f"Usuario {vr[0]}",vr[0])); nr=c.fetchone(); formal_link=nr[0] if nr else f"Usuario {vr[0]}"
    except Exception:
        formal_link=None
    finally: _put_connection(conn)
    title = (tname + (f" #{sn}/{st}" if sn else "")) if tname else "Sin equipar"
    season_icon, seasonal_border = profile_style()
    border = CUSTOM_FRAME_BORDERS.get(frame_code, seasonal_border)

    lines = [
        border,
        f"{season_icon} PERFIL DE {nombre}",
        border,
        f"🏷️ {title}",
        f"🎖️ {badge_name or 'Sin insignia equipada'}",
        f"🖼️ {frame_name or 'Marco de temporada'}",
        f"💰 {saldo:,} PiPesos",
        f"📚 {counts.get('titulo',0)} títulos · 🎁 {counts.get('regalo',0)} regalos",
        f"✨ {counts.get('cos_marco',0)} marcos · 🎖️ {counts.get('cos_insignia',0)} insignias",
    ]
    gifts = _gift_summary(uid, viewer)
    if gifts:
        gift_text = " · ".join(f"{n} ×{qty}" if qty > 1 else n for n, qty in gifts)
        lines.append(f"🎁 Regalos: {gift_text}")
    else:
        lines.append("🎁 Regalos: ninguno visible")
    for label, val in [
        ("Rol", rol), ("Experiencia", exp), ("Gustos", gustos),
        ("Vínculo", formal_link or rel), ("Sobre mí", bio), ("Frase", frase), ("Límites", limites),
    ]:
        if val:
            lines.append(f"• {label}: {val}")
    lines.extend([border, f"🎉 Tema actual: {current_season().replace('_',' ').title()}"])
    return "\n".join(lines)


async def _edit_profile_url(context: ContextTypes.DEFAULT_TYPE) -> str:
    username = context.application.bot_data.get("bot_username")
    if not username:
        me = await context.bot.get_me()
        username = me.username
        context.application.bot_data["bot_username"] = username
    return f"https://t.me/{username}?start=editar_perfil"


async def send_profile_editor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Modern private editor: buttons first, typing only for personal text."""
    if update.effective_chat.type != "private":
        return
    _ensure_profile_phrase()
    await update.effective_message.reply_text(
        "✨ MI PERFIL · EDITOR\n\n"
        "Hazlo tuyo. Toca una sección para cambiarla; solo escribes cuando quieras poner algo personal.\n\n"
        "🎭 Rol · ⭐ experiencia · 💜 gustos\n"
        "🔗 vínculo · 🪪 sobre mí · 💬 frase\n"
        "🛡️ límites · 🔐 privacidad\n"
        "🏷️ títulos · ✨ marcos e insignias",
        reply_markup=_editor_markup(),
    )


async def profile_editor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.message.chat.type != "private":
        return
    _ensure_profile_phrase()
    data = q.data

    if data == "profile_editor":
        return await _editor_screen(q)
    if data == "profile_role":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 Dom", callback_data="profile_set_rol_Dom"),
             InlineKeyboardButton("⚖️ Switch", callback_data="profile_set_rol_Switch"),
             InlineKeyboardButton("🖤 Sub", callback_data="profile_set_rol_Sub")],
            [InlineKeyboardButton("🙈 Prefiero no decirlo", callback_data="profile_set_rol_")],
            [InlineKeyboardButton("⬅️ Volver", callback_data="profile_editor")],
        ])
        return await q.edit_message_text("🎭 ¿Cómo te identificas dentro del BDSM?\n\nElige la opción que mejor te represente. Puedes cambiarla cuando quieras.", reply_markup=kb)
    if data.startswith("profile_set_rol_"):
        value=data[len("profile_set_rol_"):]
        _set_field(q.from_user.id,"rol",value)
        await q.answer("🎭 Rol actualizado",show_alert=False)
        return await _editor_screen(q)
    if data == "profile_experience":
        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌱 Explorando",callback_data="profile_set_experiencia_Explorando"),
             InlineKeyboardButton("✨ Principiante",callback_data="profile_set_experiencia_Principiante")],
            [InlineKeyboardButton("🔥 Intermedio",callback_data="profile_set_experiencia_Intermedio"),
             InlineKeyboardButton("🏆 Experimentado",callback_data="profile_set_experiencia_Experimentado")],
            [InlineKeyboardButton("🙈 No mostrar",callback_data="profile_set_experiencia_")],
            [InlineKeyboardButton("⬅️ Volver",callback_data="profile_editor")],
        ])
        return await q.edit_message_text("⭐ EXPERIENCIA\n\nNo es una competencia; elige cómo quieres describir tu recorrido.",reply_markup=kb)
    if data.startswith("profile_set_experiencia_"):
        value=data[len("profile_set_experiencia_"):]
        _set_field(q.from_user.id,"experiencia",value)
        return await _editor_screen(q)
    if data == "profile_privacy":
        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌍 Perfil público",callback_data="profile_public"),
             InlineKeyboardButton("🔒 Perfil privado",callback_data="profile_private")],
            [InlineKeyboardButton("⬅️ Volver",callback_data="profile_editor")],
        ])
        return await q.edit_message_text("🔐 PRIVACIDAD\n\nTú decides quién puede ver tu tarjeta de perfil.",reply_markup=kb)
    if data == "profile_public":
        _set_public(q.from_user.id, True)
        return await _editor_screen(q)
    if data == "profile_private":
        _set_public(q.from_user.id, False)
        return await _editor_screen(q)
    if data == "profile_photo":
        context.user_data["profile_waiting_photo"] = True
        return await q.edit_message_text(
            "📸 FOTO DE TU TARJETA\n\nMándame la imagen que quieras usar. Puede ser tu foto de Telegram o cualquier imagen tuya que prefieras para tu perfil.\n\nSi después quieres volver a usar tu foto pública de Telegram, usa /fotoperfil telegram.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar",callback_data="profile_editor")]])
        )
    if data == "profile_preview":
        return await q.edit_message_text(_render(q.from_user.id,q.from_user.id),reply_markup=_back_editor())
    if data == "profile_help_vinculo":
        return await q.edit_message_text("💞 VÍNCULOS\n\nLos vínculos ahora son consensuados y aparecen automáticamente en ambos perfiles. Usa /vinculo respondiendo a la persona o /vinculo @usuario. Formarlo cuesta 20,000 PiPesos solo si acepta. Para terminarlo usa /separarse; también cuesta 20,000 PiPesos y requiere confirmación.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Volver",callback_data="profile_editor")]]))
    if data == "profile_help_titles":
        return await q.edit_message_text("🏷️ TUS TÍTULOS\n\nAbre tu colección, toca el que quieras y equípalo.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏷️ Abrir mis títulos", callback_data="soc:title_owned")],[InlineKeyboardButton("⬅️ Volver",callback_data="profile_editor")]]))
    if data == "profile_help_cosmetics":
        from handlers.profile_cosmetics import _home_text, _home_markup
        return await q.edit_message_text(_home_text(), reply_markup=_home_markup())
    if data.startswith("profile_text_"):
        field=data[len("profile_text_"):]
        if field not in EDITABLE:
            return
        _set_pending_text(context,field)
        label=EDITABLE[field]
        examples={
            "gustos":"Cuéntanos lo que disfrutas o te llama la atención.",
            "relacion":"Escribe cómo quieres describir tu vínculo o dinámica.",
            "bio":"Escribe lo que quieras que sepan de ti.",
            "frase":"Pon una frase que te represente. Puede ser seria, divertida o completamente tuya.",
            "limites":"Escribe únicamente lo que tú quieras hacer público sobre tus límites.",
        }
        return await q.edit_message_text(
            f"✍️ {label.upper()}\n\n{examples.get(field,'Escribe lo que quieras.')}"
            "\n\nEnvíame tu texto en el siguiente mensaje. No necesitas usar comandos.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancelar",callback_data="profile_editor")]])
        )


async def profile_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Capture one free-form editor reply in PV without requiring /editarperfil."""
    if update.effective_chat.type != "private" or not update.message or not update.message.text:
        return
    field=context.user_data.pop("profile_edit_field",None)
    if not field or field not in EDITABLE:
        return
    value=update.message.text.strip()
    if not value:
        return
    ok=_set_field(update.effective_user.id,field,value)
    await update.message.reply_text(
        ("✅ Guardado. Así sí se siente como tu perfil. 😌" if ok else "⚠️ No pude guardarlo."),
        reply_markup=_editor_markup() if ok else None
    )


_PHOTO_CACHE = {}

async def _profile_photo_bytes(uid: int, context: ContextTypes.DEFAULT_TYPE, custom_file_id: str | None):
    # Cache corto: evita pedir la misma foto a Telegram en cada /perfil.
    key=(int(uid), custom_file_id or "telegram")
    cached=_PHOTO_CACHE.get(key)
    if cached and time.monotonic()-cached[0] < 600:
        return cached[1]
    file_id = custom_file_id
    if not file_id:
        try:
            photos = await context.bot.get_user_profile_photos(uid, limit=1)
            if photos.total_count and photos.photos:
                file_id = photos.photos[0][-1].file_id
        except Exception:
            file_id = None
    if not file_id:
        _PHOTO_CACHE[key]=(time.monotonic(),None); return None
    try:
        tg_file = await context.bot.get_file(file_id)
        data=bytes(await tg_file.download_as_bytearray())
        _PHOTO_CACHE[key]=(time.monotonic(),data)
        return data
    except Exception:
        return None


def _font(size: int, bold: bool = False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


FRAME_THEMES = {
    "marco_halloween": ((255, 77, 0), (180, 0, 255), "HALLOWEEN"),
    "marco_vampiro": ((210, 0, 40), (110, 0, 20), "VAMPIRE"),
    "marco_anime_neon": ((255, 45, 220), (45, 220, 255), "NEON"),
    "marco_celestial": ((90, 190, 255), (235, 245, 255), "CELESTIAL"),
    "marco_infernal": ((255, 70, 0), (255, 180, 0), "INFERNAL"),
    "marco_dragon": ((30, 220, 130), (220, 180, 40), "DRAGON"),
    "marco_obsidiana": ((150, 80, 255), (35, 35, 55), "OBSIDIAN"),
    "marco_kitsune": ((255, 100, 180), (255, 190, 80), "KITSUNE"),
    "marco_realeza": ((245, 200, 50), (130, 70, 255), "ROYAL"),
    "marco_mictlan": ((255, 150, 30), (120, 230, 120), "MICTLAN"),
    "marco_navidad": ((40, 210, 100), (245, 245, 245), "WINTER"),
    "marco_valentin": ((255, 70, 130), (255, 180, 210), "VALENTINE"),
    "marco_eclipse": ((100, 70, 255), (255, 100, 20), "ECLIPSE"),
    "marco_aurora": ((60, 255, 210), (180, 80, 255), "AURORA"),
    "marco_void": ((100, 20, 180), (15, 15, 30), "VOID"),
    "marco_fenix": ((255, 80, 20), (255, 220, 60), "PHOENIX"),
    "marco_sakura": ((255, 120, 190), (255, 220, 240), "SAKURA"),
    "marco_cyberpunk": ((0, 245, 255), (255, 20, 200), "CYBERPUNK"),
    "marco_angel_caido": ((190, 190, 230), (80, 20, 130), "FALLEN ANGEL"),
    "marco_rey_tortugas": ((255, 215, 50), (50, 210, 120), "TURTLE KING"),
    "marco_saiyajin": ((255, 220, 35), (40, 150, 255), "SAIYAJIN AURA"),
    "marco_ninja_rojo": ((220, 25, 55), (35, 35, 45), "CRIMSON NINJA"),
    "marco_grand_line": ((35, 170, 255), (245, 205, 60), "GRAND LINE"),
    "marco_cazador_demonios": ((35, 175, 235), (255, 75, 45), "NIGHT BREATH"),
    "marco_infinito": ((50, 130, 255), (170, 70, 255), "INFINITY"),
    "marco_luna_magica": ((255, 120, 220), (255, 225, 80), "MOON GUARDIAN"),
    "marco_mecha_neon": ((145, 255, 40), (180, 45, 255), "MECHA UNIT"),
    "marco_titan": ((185, 85, 55), (220, 205, 175), "WALL TITAN"),
}



def _draw_frame_details(d, code, c1, c2, W, H):
    """Distinct motifs: higher-rank frames get visibly richer ornamentation."""
    code=code or "season"
    # corner ornaments
    for x,y,sx,sy in ((78,78,1,1),(W-78,78,-1,1),(78,H-78,1,-1),(W-78,H-78,-1,-1)):
        d.line((x,y,x+sx*105,y),fill=c1,width=5); d.line((x,y,x,y+sy*105),fill=c2,width=5)
        d.ellipse((x-8,y-8,x+8,y+8),fill=c2)
    if code=="marco_halloween":
        # moon, bats, webs, pumpkins - deliberately graphic rather than emoji fonts.
        d.ellipse((820,105,940,225),fill=(245,220,130)); d.ellipse((855,90,955,205),fill=(7,7,20))
        for bx,by in ((145,110),(210,145),(760,170)):
            d.arc((bx-28,by-10,bx,by+20),180,350,fill=c2,width=4); d.arc((bx,by-10,bx+28,by+20),190,360,fill=c2,width=4)
        for cx,cy in ((95,H-150),(885,H-150)):
            d.ellipse((cx,cy,cx+95,cy+72),fill=(235,92,20),outline=(255,165,30),width=4); d.rectangle((cx+42,cy-14,cx+53,cy+3),fill=(90,150,60))
            d.polygon([(cx+23,cy+32),(cx+37,cy+22),(cx+42,cy+38)],fill=(20,15,20)); d.polygon([(cx+58,cy+38),(cx+64,cy+22),(cx+78,cy+32)],fill=(20,15,20))
        for base in (105,975):
            for r in range(24,110,22): d.arc((base-r,70-r,base+r,70+r),0,90,fill=(150,150,180),width=2)
    elif code in {"marco_vampiro","marco_angel_caido","marco_void"}:
        for yy in range(150,H-140,105): d.polygon([(65,yy),(95,yy-24),(125,yy),(95,yy+24)],outline=c1)
        d.polygon([(540,85),(575,130),(540,118),(505,130)],fill=c2)
    elif code in {"marco_celestial","marco_aurora"}:
        for x in range(120,980,110): d.ellipse((x,105,x+8,113),fill=(245,245,255))
        d.arc((120,H-350,450,H-10),190,330,fill=c1,width=9); d.arc((630,H-350,960,H-10),210,350,fill=c2,width=9)
    elif code in {"marco_infernal","marco_fenix"}:
        for x in range(90,1000,75):
            d.polygon([(x,H-50),(x+28,H-130),(x+50,H-50)],fill=c1 if (x//75)%2 else c2)
    elif code in {"marco_kitsune","marco_sakura"}:
        for x,y in ((130,130),(870,160),(160,H-150),(850,H-180),(700,115)):
            d.ellipse((x,y,x+18,y+11),fill=c2); d.ellipse((x+14,y+5,x+30,y+16),fill=c1)
    elif code in {"marco_cyberpunk","marco_anime_neon"}:
        for yy in range(160,H-140,90): d.line((65,yy,115,yy),fill=c1,width=3); d.line((965,yy+25,1015,yy+25),fill=c2,width=3)
        d.text((760,92),"// ONLINE",font=_font(22,True),fill=c1)
    elif code in {"marco_dragon","marco_rey_tortugas","marco_realeza"}:
        d.polygon([(470,105),(505,70),(540,110),(575,70),(610,105),(600,135),(480,135)],fill=c1,outline=c2)
        for yy in (260,560,860): d.polygon([(62,yy),(95,yy-35),(128,yy),(95,yy+35)],outline=c2)
    elif code in {"marco_saiyajin","marco_infinito","marco_mecha_neon"}:
        # Anime-energy orbit: luminous circular arcs, stars and sparks around the portrait area.
        for rr,w in ((155,7),(170,4),(184,2)):
            d.arc((62-rr+155,122-rr+155,62+rr+155,122+rr+155),195,520,fill=c1 if rr!=170 else c2,width=w)
        for px,py in ((75,185),(340,135),(360,345),(105,390),(300,95)):
            d.polygon([(px,py-9),(px+4,py-3),(px+11,py),(px+4,py+3),(px,py+10),(px-4,py+3),(px-11,py),(px-4,py-3)],fill=c2)
        if code=="marco_mecha_neon":
            for yy in (150,205,330,385): d.line((70,yy,125,yy-22),fill=c1,width=4)
    elif code in {"marco_ninja_rojo","marco_luna_magica"}:
        d.ellipse((95,135,335,375),outline=c1,width=7); d.arc((78,118,352,392),205,500,fill=c2,width=4)
        d.ellipse((278,120,338,180),fill=c2); d.ellipse((296,110,350,170),fill=(7,7,20))
        for px,py in ((95,155),(345,230),(115,365),(320,390)): d.ellipse((px,py,px+10,py+10),fill=c1)
    elif code in {"marco_grand_line","marco_cazador_demonios"}:
        for rr in (158,174): d.arc((60,120,370,430),15,170,fill=c1,width=5); d.arc((60,120,370,430),195,350,fill=c2,width=5)
        for px,py in ((90,300),(125,355),(330,160),(355,210)): d.arc((px-25,py-12,px+25,py+18),180,355,fill=c1,width=3)
    elif code=="marco_titan":
        for xx in range(70,370,42): d.rectangle((xx,125,xx+28,150),outline=c2,width=3)
        d.arc((75,125,360,420),190,350,fill=c1,width=8)
    elif code=="marco_mictlan":
        for x in (110,880):
            d.ellipse((x,H-170,x+90,H-80),outline=c1,width=5); d.ellipse((x+20,H-145,x+35,H-130),fill=c2); d.ellipse((x+55,H-145,x+70,H-130),fill=c2)

def _gift_icon(d, x, y, name, c1, c2):
    n=str(name).lower(); box=(x,y,x+64,y+64)
    d.rounded_rectangle(box,radius=14,fill=(18,18,38),outline=c1,width=2)
    if "rosa" in n:
        d.ellipse((x+18,y+12,x+46,y+40),fill=(220,45,80)); d.line((x+32,y+38,x+32,y+56),fill=(70,190,90),width=4)
    elif "chocolate" in n:
        d.rectangle((x+14,y+16,x+50,y+50),fill=(110,62,38)); d.line((x+32,y+16,x+32,y+50),fill=(180,120,80),width=2); d.line((x+14,y+33,x+50,y+33),fill=(180,120,80),width=2)
    elif "peluche" in n:
        d.ellipse((x+18,y+18,x+46,y+50),fill=(190,135,85)); d.ellipse((x+12,y+12,x+27,y+27),fill=(190,135,85)); d.ellipse((x+37,y+12,x+52,y+27),fill=(190,135,85))
    elif "collar" in n or "cuerda" in n:
        d.arc((x+10,y+10,x+54,y+54),20,330,fill=c2,width=6); d.ellipse((x+27,y+42,x+37,y+52),fill=c1)
    elif "corona" in n:
        d.polygon([(x+10,y+45),(x+16,y+18),(x+30,y+35),(x+40,y+14),(x+53,y+45)],fill=(235,195,55))
    elif "anillo" in n:
        d.ellipse((x+15,y+18,x+49,y+52),outline=(210,210,230),width=7); d.polygon([(x+25,y+16),(x+32,y+7),(x+40,y+16),(x+32,y+24)],fill=c2)
    else:
        d.polygon([(x+32,y+10),(x+52,y+28),(x+32,y+54),(x+12,y+28)],fill=c2,outline=c1)

def _wrap(draw, text, font, max_width):
    words = str(text).split(); lines=[]; current=""
    for word in words:
        trial=(current+" "+word).strip()
        if draw.textbbox((0,0),trial,font=font)[2] <= max_width:
            current=trial
        else:
            if current: lines.append(current)
            current=word
    if current: lines.append(current)
    return lines or [""]


async def _build_profile_card(uid: int, viewer: int, context: ContextTypes.DEFAULT_TYPE):
    r=_profile(uid)
    if not r: return None, "No encontré ese perfil."
    (nombre, username, rol, exp, gustos, rel, bio, frase, limites, publico, saldo,
     tid, tname, trare, sn, st, frame_id, frame_name, frame_code,
     badge_id, badge_name, badge_code, custom_photo_file_id)=r
    if viewer != uid and not publico:
        return None, "🔒 Este perfil es privado."
    gifts=_gift_summary(uid,viewer); counts=_counts(uid)
    theme=FRAME_THEMES.get(frame_code, ((180,80,255),(255,50,190), current_season().replace('_',' ').upper()))
    c1,c2,theme_name=theme
    # Tarjeta más compacta: menos espacio muerto y más presencia visual del marco.
    W,H=1080,1120
    im=Image.new('RGB',(W,H),(7,7,20)); d=ImageDraw.Draw(im)
    # Fondo temático sutil para que el marco no parezca solo líneas sobre negro.
    for yy in range(H):
        t=yy/max(1,H-1)
        base=(int(7+(c1[0]*0.055)*(1-t)), int(7+(c1[1]*0.045)*(1-t)), int(20+(c2[2]*0.05)*t))
        d.line((0,yy,W,yy),fill=base)
    # Glow + layered geometric frame inspired by the equipped cosmetic.
    glow=Image.new('RGBA',(W,H),(0,0,0,0)); gd=ImageDraw.Draw(glow)
    for i in range(7):
        inset=34+i*7
        color=(*c1, max(35,150-i*15)) if i%2==0 else (*c2,max(35,150-i*15))
        gd.rounded_rectangle((inset, inset, W-inset, H-inset), radius=38, outline=color, width=4)
    glow=glow.filter(ImageFilter.GaussianBlur(8)); im=Image.alpha_composite(im.convert('RGBA'),glow).convert('RGB'); d=ImageDraw.Draw(im)
    for i in range(5):
        inset=48+i*8; col=c1 if i%2==0 else c2
        d.rounded_rectangle((inset,inset,W-inset,H-inset),radius=34,outline=col,width=3)
    _draw_frame_details(d,frame_code,c1,c2,W,H)
    # Marca de agua temática de bajo contraste.
    if frame_code == "marco_halloween":
        d.ellipse((720,560,1010,850),outline=(70,35,95),width=4)
        for bx,by in ((760,650),(835,590),(930,700)):
            d.arc((bx-35,by-15,bx,by+20),180,355,fill=(70,35,95),width=3); d.arc((bx,by-15,bx+35,by+20),185,360,fill=(70,35,95),width=3)
    elif frame_code in {"marco_vampiro","marco_angel_caido"}:
        d.polygon([(810,560),(900,690),(850,660),(910,810),(760,675),(815,700)],outline=(65,25,65))
    elif frame_code in {"marco_celestial","marco_aurora"}:
        for rr in (70,115,160): d.arc((760-rr,690-rr,760+rr,690+rr),200,340,fill=(45,70,100),width=3)
    title_font=_font(46,True); small=_font(26); body=_font(30); body_b=_font(31,True)
    d.text((90,82),"P I B O T   //   "+theme_name,font=small,fill=c2)
    photo=await _profile_photo_bytes(uid,context,custom_photo_file_id)
    if photo:
        try:
            av=Image.open(BytesIO(photo)).convert('RGB'); av.thumbnail((260,260))
            side=min(av.size); left=(av.width-side)//2; top=(av.height-side)//2; av=av.crop((left,top,left+side,top+side)).resize((250,250))
            mask=Image.new('L',(250,250),0); ImageDraw.Draw(mask).ellipse((0,0,249,249),fill=255)
            im.paste(av,(95,155),mask); d.ellipse((89,149,351,411),outline=c1,width=7); d.ellipse((82,142,358,418),outline=c2,width=2)
        except Exception: pass
    x=390; y=175
    d.text((x,y),str(nombre)[:28],font=title_font,fill=(245,245,255)); y+=65
    if username: d.text((x,y),"@"+str(username).lstrip('@')[:30],font=small,fill=(180,185,210)); y+=45
    title=(tname+(f" #{sn}/{st}" if sn else "")) if tname else "Sin título equipado"
    for line in _wrap(d,title,body_b,560)[:2]: d.text((x,y),line,font=body_b,fill=c1); y+=40
    d.text((x,y),f"{saldo:,} PiPesos",font=body_b,fill=(245,210,80)); y+=48
    d.line((90,450,990,450),fill=c2,width=2)
    y=485
    info=[("ROL",rol), ("EXPERIENCIA",exp), ("INSIGNIA",badge_name), ("MARCO",frame_name)]
    for label,val in info:
        if val:
            d.text((100,y),label,font=small,fill=c2); d.text((330,y),str(val)[:38],font=body,fill=(238,238,248)); y+=48
    if frase:
        y+=8; d.text((100,y),"F R A S E",font=small,fill=c2); y+=38
        for line in _wrap(d,'“'+str(frase)+'”',body,850)[:3]: d.text((115,y),line,font=body,fill=(245,245,255)); y+=39
    y+=12; d.line((90,y,990,y),fill=c1,width=2); y+=25
    d.text((100,y),f"COLECCIÓN  •  {counts.get('titulo',0)} títulos  •  {counts.get('cos_marco',0)} marcos  •  {counts.get('cos_insignia',0)} insignias",font=small,fill=(200,205,225)); y+=48
    d.text((100,y),"R E G A L O S",font=small,fill=c2); y+=38
    if gifts:
        # Colección visual: mini ficha por tipo de regalo, no una línea de nombres.
        for idx,(n,q) in enumerate(gifts[:8]):
            col=idx%4; row=idx//4; gx=105+col*225; gy=y+row*92
            _gift_icon(d,gx,gy,n,c1,c2)
            clean=str(n)
            # quita el primer símbolo no ASCII de los nombres del catálogo para evitar cuadros vacíos
            clean=' '.join(part for part in clean.split() if any(ch.isalnum() for ch in part))
            d.text((gx+74,gy+7),clean[:15],font=_font(21,True),fill=(242,242,250))
            d.text((gx+74,gy+38),f"×{q}",font=_font(22,True),fill=c1)
        y += 92*((min(len(gifts),8)+3)//4)
    else:
        d.text((115,y),"Sin regalos visibles todavía.",font=small,fill=(165,170,190)); y+=34
    # Optional bio/gustos, clipped so the card remains clean.
    extras=[]
    if bio: extras.append(("SOBRE MÍ",bio))
    if gustos: extras.append(("GUSTOS",gustos))
    for label,val in extras:
        if y>H-175: break
        y+=18; d.text((100,y),label,font=small,fill=c1); y+=34
        for line in _wrap(d,val,small,850)[:2]: d.text((115,y),line,font=small,fill=(225,225,238)); y+=32
    # Remate inferior integrado al marco.
    d.line((90,H-74,990,H-74),fill=c2,width=2)
    d.text((100,H-58),"PiBot • Social Profile",font=_font(20,True),fill=(150,155,180))
    tw=d.textbbox((0,0),theme_name,font=_font(20,True))[2]
    d.text((970-tw,H-58),theme_name,font=_font(20,True),fill=c1)
    out=BytesIO(); im.save(out,format='JPEG',quality=80,optimize=False,subsampling=2); out.seek(0); out.name='perfil.jpg'
    return out, _render(uid,viewer)


async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /perfil SIEMPRE pertenece a quien ejecuta el comando. Responder a otra persona ya no cambia el objetivo.
    target = update.effective_user.id
    card, text = await _build_profile_card(target, target, context)
    url = await _edit_profile_url(context)
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🏷️ Mis títulos", callback_data="soc:title_owned"), InlineKeyboardButton("🎁 Mis regalos", callback_data="soc:gift_owned")],
        [InlineKeyboardButton("✨ Mi vestidor / Tienda", url=url.replace("start=editar_perfil", "start=vestidor")), InlineKeyboardButton("📸 Mi foto", url=url)],
        [InlineKeyboardButton("✏️ Editar mi perfil", url=url)],
    ])
    if card:
        caption = f"✨ Perfil de {update.effective_user.full_name}\n🎨 Marco: {_profile(target)[18] or 'Temporada'}\n🎁 Mira su colección completa en la tarjeta."
        return await update.effective_message.reply_photo(photo=card, caption=caption, reply_markup=markup)
    await update.effective_message.reply_text(text, reply_markup=markup)


async def fotoperfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        url = await _edit_profile_url(context)
        return await update.effective_message.reply_text("📸 La foto de tu tarjeta se cambia por privado.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📸 Abrir editor",url=url)]]))
    if context.args and context.args[0].lower() == "telegram":
        _save_profile_photo(update.effective_user.id,None)
        return await update.effective_message.reply_text("✅ Volví a usar tu foto pública de Telegram para la tarjeta.")
    context.user_data["profile_waiting_photo"] = True
    await update.effective_message.reply_text("📸 Mándame ahora la imagen que quieras usar en tu tarjeta. No tiene que ser tu foto de Telegram.")


async def profile_photo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private" or not context.user_data.get("profile_waiting_photo"):
        return
    if not update.message or not update.message.photo:
        return
    context.user_data.pop("profile_waiting_photo",None)
    file_id=update.message.photo[-1].file_id
    ok=_save_profile_photo(update.effective_user.id,file_id)
    await update.message.reply_text("✅ Foto guardada. Usa /perfil para ver tu nueva tarjeta." if ok else "⚠️ No pude guardar la foto.")


async def editarperfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        url = await _edit_profile_url(context)
        return await update.message.reply_text(
            "🔐 Tu perfil solo se modifica por privado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Abrir editor privado", url=url)]]),
        )
    if not context.args:
        return await send_profile_editor(update, context)
    field = context.args[0].lower()
    value = " ".join(context.args[1:]).strip()
    if field not in EDITABLE or not value:
        return await update.message.reply_text("Uso: /editarperfil CAMPO TEXTO\nCampos: " + ", ".join(EDITABLE))
    await update.message.reply_text(
        "✅ Perfil actualizado." if _set_field(update.effective_user.id, field, value) else "No pude actualizarlo."
    )


async def privacidadperfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return await update.message.reply_text("🔐 La privacidad del perfil se cambia únicamente en PV.")
    if not context.args or context.args[0].lower() not in ("publico", "privado"):
        return await update.message.reply_text("Uso: /privacidadperfil publico | privado")
    public = context.args[0].lower() == "publico"
    _set_public(update.effective_user.id, public)
    await update.message.reply_text("🌍 Perfil público." if public else "🔒 Perfil privado. Solo tú podrás verlo.")


async def equipartitulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return await update.message.reply_text("🏷️ Equipa tus títulos desde el PV de PiBot.")
    if not context.args:
        return await update.message.reply_text("Uso: /equipartitulo ID_OBJETO")
    try:
        aid = int(context.args[0])
    except ValueError:
        return await update.message.reply_text("ID inválido.")
    name = _equip(update.effective_user.id, aid)
    await update.message.reply_text(f"✨ Título equipado: {name}" if name else "Ese título no es tuyo, está bloqueado o no existe.")
