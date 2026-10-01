from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.database.database import _get_connection, _put_connection
from src.utils.seasonal import current_season, profile_style

EDITABLE = {
    "rol": "Rol BDSM",
    "experiencia": "Experiencia",
    "gustos": "Gustos",
    "relacion": "Vínculo / relación",
    "bio": "Bio",
    "limites": "Límites",
}

CUSTOM_FRAME_BORDERS = {
    "marco_clasico": "✨━━━━━━━━━━━━━━✨",
    "marco_cadenas": "⛓️━━━━━━━━━━━━━━⛓️",
    "marco_obsidiana": "🖤━━━━━━━━━━━━━━🖤",
    "marco_vampiro": "🩸━━━━━━━━━━━━━━🩸",
    "marco_anime_neon": "🌸━━━━━━━━━━━━━━🌸",
    "marco_halloween": "🎃🕸️━━━━━━━━━━🕸️🎃",
    "marco_mictlan": "💀🌼━━━━━━━━━━🌼💀",
    "marco_navidad": "🎄❄️━━━━━━━━━━❄️🎄",
    "marco_valentin": "💘🌹━━━━━━━━━━🌹💘",
}


def _profile(uid: int):
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            SELECT p.nombre,p.username,p.rol,p.experiencia,p.gustos,p.relacion,p.bio,p.limites,
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
        nombre, username, rol, exp, gustos, rel, bio, limites, publico, saldo,
        tid, tname, trare, sn, st, frame_id, frame_name, frame_code,
        badge_id, badge_name, badge_code,
    ) = r
    if viewer != uid and not publico:
        return "🔒 Este perfil es privado."

    counts = _counts(uid)
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
        ("Vínculo", rel), ("Bio", bio), ("Límites", limites),
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
    """Private profile editor landing page. It always edits the clicker's own profile."""
    if update.effective_chat.type != "private":
        return
    keyboard = [
        [InlineKeyboardButton("🎭 Rol", callback_data="profile_help_rol"), InlineKeyboardButton("🧠 Experiencia", callback_data="profile_help_experiencia")],
        [InlineKeyboardButton("💜 Gustos", callback_data="profile_help_gustos"), InlineKeyboardButton("🔗 Vínculo", callback_data="profile_help_relacion")],
        [InlineKeyboardButton("📝 Bio", callback_data="profile_help_bio"), InlineKeyboardButton("🛡️ Límites", callback_data="profile_help_limites")],
        [InlineKeyboardButton("🌍 Público", callback_data="profile_public"), InlineKeyboardButton("🔒 Privado", callback_data="profile_private")],
        [InlineKeyboardButton("🏷️ Mis títulos", callback_data="profile_help_titles")],
        [InlineKeyboardButton("🖼️ Marcos e insignias", callback_data="profile_help_cosmetics")],
    ]
    text = _render(update.effective_user.id, update.effective_user.id)
    await update.effective_message.reply_text(
        text + "\n\n✏️ EDITAR MI PERFIL\nElige qué quieres cambiar. Nadie puede editar tu perfil desde este menú.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def profile_editor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.message.chat.type != "private":
        return await q.answer("Tu perfil solo se edita por privado.", show_alert=True)
    data = q.data
    if data == "profile_public":
        _set_public(q.from_user.id, True)
        return await q.edit_message_text("🌍 Tu perfil ahora es público.\n\nUsa /perfil para verlo.")
    if data == "profile_private":
        _set_public(q.from_user.id, False)
        return await q.edit_message_text("🔒 Tu perfil ahora es privado.\n\nSolo tú podrás verlo.")
    if data == "profile_help_titles":
        return await q.edit_message_text("🏷️ Usa /mistitulos para ver tu colección y /equipartitulo ID para equipar uno.")
    if data == "profile_help_cosmetics":
        from handlers.profile_cosmetics import _home_text, _home_markup
        return await q.edit_message_text(_home_text(), reply_markup=_home_markup())
    field = data.removeprefix("profile_help_")
    if field in EDITABLE:
        return await q.edit_message_text(
            f"✏️ {EDITABLE[field]}\n\nEnvía:\n/editarperfil {field} TU TEXTO\n\nEjemplo:\n/editarperfil {field} ..."
        )


async def perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.effective_user.id
    if update.message and update.message.reply_to_message:
        target = update.message.reply_to_message.from_user.id
    text = _render(target, update.effective_user.id)
    markup = None
    if target == update.effective_user.id:
        url = await _edit_profile_url(context)
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Editar mi perfil", url=url)]])
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
