from __future__ import annotations
from src.utils.seasonal import seasonalize

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
        [InlineKeyboardButton("👁️ Ver mi perfil", callback_data="profile_preview")],
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
                   f.cosmetic_id,f.nombre,f.code,b.cosmetic_id,b.nombre,b.code
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


def _render(uid: int, viewer: int):
    r = _profile(uid)
    if not r:
        return "No encontré ese perfil."
    (
        nombre, username, rol, exp, gustos, rel, bio, frase, limites, publico, saldo,
        tid, tname, trare, sn, st, frame_id, frame_name, frame_code,
        badge_id, badge_name, badge_code,
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


async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.effective_user.id
    if update.message and update.message.reply_to_message:
        target = update.message.reply_to_message.from_user.id
    text = _render(target, update.effective_user.id)
    markup = None
    if target == update.effective_user.id:
        url = await _edit_profile_url(context)
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🏷️ Mis títulos", callback_data="soc:title_owned"), InlineKeyboardButton("🎁 Mis regalos", callback_data="soc:gift_owned")],
            [InlineKeyboardButton("✨ Mi vestidor", callback_data="cos_home")],
            [InlineKeyboardButton("✏️ Editar mi perfil", url=url)],
        ])
    await update.message.reply_text(text, reply_markup=markup)


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
