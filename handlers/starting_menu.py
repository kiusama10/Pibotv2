from src.utils.seasonal import seasonalize
# starting_menu.py
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import get_campo_usuario
from handlers.tienda import tienda
from handlers.inventario import inventario
from src.utils.seasonal import welcome_text, commands_intro
from handlers.profile_social import send_profile_editor, _render
from handlers.profile_cosmetics import send_cosmetics_home

# =========  COMANDO /START  ========= #
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    if get_campo_usuario(user.id,"id_user") is None:
        await context.bot.send_message(
            chat_id=user.id,
            text=(
                "🎉 Veo que eres nuevo, no te tengo en mi sistema.\n\n"
                "Si deseas ingresar a la tienda o ver tu perfil,\n"
                "primero usa el comando /ver en la comunidad. 😄"
            )
        )
        return

    # Deep-link del botón "Editar mi perfil". Siempre abre el editor del usuario que hizo clic.
    if update.message.chat.type == "private" and context.args and context.args[0] in {"editar_perfil", "editarperfil"}:
        await send_profile_editor(update, context)
        return
    if update.message.chat.type == "private" and context.args and context.args[0] == "vestidor":
        await send_cosmetics_home(update, context)
        return

    # Solo mostrar menú si está en privado
    if update.message.chat.type != "private":
        await update.message.reply_text("Envíame /start por privado para ver el menú.")
        return

    keyboard = [
        [InlineKeyboardButton("📜 Ver comandos", callback_data="ver_comandos"), InlineKeyboardButton("❓ Instrucciones", callback_data="instrucciones")],
        [InlineKeyboardButton("🛍️ Abrir tienda", callback_data="abrir_tienda")],
        [InlineKeyboardButton("📦 Ver inventario", callback_data="ver_inventario")],
        [InlineKeyboardButton("👤 Perfil", callback_data="perfil")]
    ]

    await update.message.reply_text(
        welcome_text() + "\n\nSelecciona una opción:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


def _commands_text():
    return (
        commands_intro() +
        "\n\n🎮 *Juegos y casino*\n/jugar · /robar · /caza · /apostar · /aceptar · /cancelar · /tortugas · /blackjack · /asesino · /dibujar\n"
        "\n⚔️ *Combates*\n/lucha · /aceptarlucha · /ataque\n"
        "\n💰 *Economía*\n/pipesos · /tienda · /inventario · /usar · /dar · /ver · /bankiu · /pagarbanco\n"
        "\n👤 *Perfil y personalización*\n/perfil · /editarperfil · /privacidadperfil · /titulos · /mistitulos · /equipartitulo · /cosmeticos · /miscosmeticos\n"
        "\n🎁 *Social y mercado*\n/regalos · /regalo · /misregalos · /mercado · /vender · /comprarmercado · /empenar · /desempenar\n"
        "\n🏆 *Rankings y actividades*\n/ranking · /ricospipesos · /quiz · /subasta · /puja · /cancelarsubasta\n"
        "\n📺 *Servicios*\n/canales · /instrucciones · /comandos\n"
        "\n🧩 *Otros*\n/MiRol · /Suerte · /userid\n"
    )


async def comandos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(_commands_text(), parse_mode="Markdown")


# =========  CALLBACK DEL MENÚ  ========= #
async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data

    if data == "ver_comandos":
        await query.edit_message_text(_commands_text(), parse_mode="Markdown")

    elif data == "instrucciones":
        from handlers.help_center import instrucciones
        await instrucciones(update, context)
        return

    elif data == "abrir_tienda":
        await tienda(update, context,from_menu=True)
        return

    elif data == "ver_inventario":
        await inventario(update,context)
        return

    elif data == "perfil":
        text = _render(user.id, user.id)
        me = await context.bot.get_me()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Editar mi perfil", url=f"https://t.me/{me.username}?start=editar_perfil")]])
        await query.edit_message_text(text, reply_markup=kb)
        return
