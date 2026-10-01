"""
Role management handler for PiBot.

Internal role system:
  1 = Usuario (User)
  2 = Admin
  3 = BotMaster

Hierarchical permissions for /AsignarRol:
  Admin (2)     → can assign roles 1-2, cannot modify BotMasters
  BotMaster (3) → can assign any role (1, 2, 3) to anyone

Commands:
  /AsignarRol @usuario [1|2|3]  — Admin+ can use this (with restrictions)
"""

from telegram import Update
from telegram.ext import ContextTypes
from src.database.database import get_id_user, get_user_role, set_user_role, check_permission, set_suerte, is_botmaster
from src.config import BOTMASTER_IDS

ROLE_NAMES = {1: "Usuario", 2: "Admin", 3: "BotMaster"}


async def asignar_rol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Command: /AsignarRol @usuario [1|2|3]
    Admin (2): can assign roles 1-2, cannot touch BotMasters.
    BotMaster (3): unrestricted.
    """
    sender = update.effective_user
    sender_role = get_user_role(sender.id)

    # Permission check: Admin (2) or higher
    if sender_role < 2:
        await update.message.reply_text("❌ No tienes permisos para asignar roles.")
        return

    if not context.args or len(context.args) < 2:
        if sender_role >= 3:
            roles_text = "  1 = Usuario\n  2 = Admin\n  3 = BotMaster"
        else:
            roles_text = "  1 = Usuario\n  2 = Admin"
        await update.message.reply_text(
            f"📋 Uso: /AsignarRol @usuario [rol]\n\nRoles:\n{roles_text}"
        )
        return

    # Parse target user
    mention = context.args[0].lstrip("@")
    if not mention:
        await update.message.reply_text("⚠️ Debes mencionar un usuario con @.")
        return

    target_id = get_id_user(mention)
    if target_id is None:
        await update.message.reply_text(
            f"❌ No encontré a @{mention} en el sistema.\n"
            "El usuario debe haberse registrado primero con /ver."
        )
        return

    # Parse role
    try:
        role = int(context.args[1])
        if role not in (1, 2, 3):
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ El rol debe ser 1, 2 o 3.")
        return

    # BotMaster role 3 has broad admin powers, but only the protected root
    # configured in BOTMASTER_IDS may create/remove BotMasters.
    target_role = get_user_role(target_id)
    is_root = sender.id in BOTMASTER_IDS
    if target_id in BOTMASTER_IDS and target_id != sender.id:
        await update.message.reply_text("🛡️ Ese BotMaster principal está protegido.")
        return
    if target_role >= 3 and not is_root:
        await update.message.reply_text("❌ Solo el BotMaster principal puede modificar a otro BotMaster.")
        return
    if role >= 3 and not is_root:
        await update.message.reply_text("❌ Solo el BotMaster principal puede nombrar BotMasters.")
        return
    if sender_role == 2 and role >= 3:
        await update.message.reply_text("❌ No puedes asignar el rol de BotMaster.")
        return

    # Set role
    if set_user_role(target_id, role):
        role_name = ROLE_NAMES.get(role, "Desconocido")
        await update.message.reply_text(
            f"✅ @{mention} ahora tiene el rol: **{role_name}** ({role})",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("❌ Error al asignar el rol.")


async def ver_rol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Command: /MiRol
    Show the user's current internal role.
    """
    user = update.effective_user
    role = get_user_role(user.id)

    if role == 0:
        await update.message.reply_text(
            "⚠️ No estás registrado en el sistema. Usa /ver para registrarte."
        )
        return

    role_name = ROLE_NAMES.get(role, "Desconocido")
    await update.message.reply_text(
        f"⚡👑 **MODO SÚPER DIOS** 👑⚡\n**BotMaster Principal · ROOT**\n🔥 Acceso absoluto a PiBot\n🛡️ Por encima de Admin y BotMaster secundarios\n⚙️ Control total de administración interna" if user.id in BOTMASTER_IDS else (f"👑 **BotMaster**\nPermisos administrativos concedidos por Kiu." if role >= 3 else f"👤 Tu rol actual: **{role_name}**"),
        parse_mode="Markdown",
    )


SUERTE_PROB = {1: "0/3", 2: "1/3", 3: "2/3"}


async def suerte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Command: /Suerte @usuario [1|2|3]
    Only BotMaster (role=3) can set a user's luck value.
    """
    sender = update.effective_user

    if not check_permission(sender.id, 3):
        await update.message.reply_text("❌ Solo el BotMaster puede usar este comando.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "📋 Uso: /Suerte @usuario [1|2|3]\n\n"
            "Valores:\n"
            "  1 = Sin suerte (0/3)\n"
            "  2 = Normal (1/3)\n"
            "  3 = Mucha suerte (2/3)"
        )
        return

    mention = context.args[0].lstrip("@")
    if not mention:
        await update.message.reply_text("⚠️ Debes mencionar un usuario con @.")
        return

    target_id = get_id_user(mention)
    if target_id is None:
        await update.message.reply_text(
            f"❌ No encontré a @{mention} en el sistema.\n"
            "El usuario debe haberse registrado primero con /ver."
        )
        return

    try:
        valor = int(context.args[1])
        if valor not in (1, 2, 3):
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ El valor de suerte debe ser 1, 2 o 3.")
        return

    if set_suerte(target_id, valor):
        prob = SUERTE_PROB.get(valor, "?")
        await update.message.reply_text(
            f"🍀 Se ha actualizado la suerte de @{mention} a {valor} "
            f"(Probabilidad de robo: {prob})"
        )
    else:
        await update.message.reply_text("❌ Error al actualizar la suerte.")


def _botmaster_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.reply_to_message:
        u=update.message.reply_to_message.from_user
        return u.id, (u.username or u.full_name)
    if context.args and context.args[0].startswith("@"):
        name=context.args[0][1:]
        return get_id_user(name), name
    return None, None


async def hacer_botmaster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in BOTMASTER_IDS:
        return await update.message.reply_text("❌ Solo el BotMaster principal puede otorgar este permiso.")
    uid,name=_botmaster_target(update,context)
    if not uid:
        return await update.message.reply_text("Uso: /hacerbotmaster @usuario\nTambién puedes responder a su mensaje con /hacerbotmaster.")
    if uid == update.effective_user.id:
        return await update.message.reply_text("👑 Ya eres BotMaster principal.")
    if set_user_role(uid,3):
        await update.message.reply_text(f"👑 {name} ahora es BotMaster.")
    else:
        await update.message.reply_text("⚠️ No pude cambiar el permiso.")


async def quitar_botmaster(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in BOTMASTER_IDS:
        return await update.message.reply_text("❌ Solo el BotMaster principal puede retirar este permiso.")
    uid,name=_botmaster_target(update,context)
    if not uid:
        return await update.message.reply_text("Uso: /quitarbotmaster @usuario\nTambién puedes responder a su mensaje con /quitarbotmaster.")
    if uid in BOTMASTER_IDS:
        return await update.message.reply_text("🛡️ Ese BotMaster está protegido por BOTMASTER_IDS de Render.")
    if get_user_role(uid) != 3:
        return await update.message.reply_text(f"ℹ️ {name} no es BotMaster.")
    if set_user_role(uid,1):
        await update.message.reply_text(f"🔒 {name} dejó de ser BotMaster y volvió a Usuario.")
    else:
        await update.message.reply_text("⚠️ No pude retirar el permiso.")
