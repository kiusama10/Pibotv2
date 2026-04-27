"""
PiBot Main Module

Entry point for the PiBot Telegram bot. Initializes the bot, registers all
handler groups, and starts the polling loop.

This module handles:
- Bot initialization through aiogram
- Handler registration and priority grouping
- Punishment system (castigados.json management)
- Community blocking/filtering
"""
import socket
import threading
import http.server
import socketserver

orig_getaddrinfo = socket.getaddrinfo

def getaddrinfo_ipv4(*args, **kwargs):
    return [x for x in orig_getaddrinfo(*args, **kwargs) if x[0] == socket.AF_INET]
def run_server():
    PORT = 8080
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()
        


socket.getaddrinfo = getaddrinfo_ipv4

import json
import os
from telegram import ChatPermissions, Update
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    MessageHandler,
    filters,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

# Local imports
from src.config import BOT_TOKEN, DOMS, obtener_temas_por_comunidad, PUNISHMENT_FILE, BOTMASTER_IDS
from src.database.database import create_database, create_tables, restart_all_combats, seed_items, init_botmaster_roles, get_campo_usuario, insert_user, normalizar_nombre, update_perfil

# Handler imports - General commands
from handlers.general import dar, ver, regalar, numero_azar, quitar, userid
from handlers.starting_menu import start, menu_callback
from handlers.tienda import tienda, tienda_callback
from handlers.inventario import inventario, inventario_callback, usar
from handlers.battles import lucha, ataque, aceptar_lucha
from handlers.roles import asignar_rol, ver_rol, suerte

# Handler imports - Games and rewards
from handlers.theme_juegosYcasino import (
    apostar, aceptar, detectar_dado, cancelar_apuesta, jugar, robar
)
from handlers.rewards import manejar_imagenes
from blackjack import cmd_blackjack
# Handler imports - User onboarding
from handlers.welcoming import nuevo_usuario, mensaje_de_presentaciones

# Constants
RUTA_CASTIGADOS = PUNISHMENT_FILE


# ==================== AUTO-REGISTRATION ====================

async def auto_registrar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Silently register any user who sends a message, if not already in the DB.
    Runs in group -2 (before everything else) and never blocks other handlers.
    """
    user = update.effective_user
    if not user or user.is_bot:
        return

    try:
        existing = get_campo_usuario(user.id, "id_user")
        if existing is None:
            nombre = normalizar_nombre(user.first_name or "", user.last_name or "")
            if not nombre.strip():
                nombre = user.username or f"user{user.id}"
            insert_user(user.id, 0, user.username, nombre)
        elif user.username and get_campo_usuario(user.id, "username") != user.username:
            update_perfil(user.id, username=user.username)
    except Exception as e:
        print(f"[AUTO-REG] Error: {e}")

# ==================== PUNISHMENT SYSTEM FUNCTIONS ====================

def cargar_castigados() -> dict:
    """
    Load punished users from JSON file.
    
    Returns:
        Dictionary mapping community IDs to sets of punished user IDs.
        Returns empty dict if file doesn't exist.
    """
    if not os.path.exists(RUTA_CASTIGADOS):
        return {}
    try:
        with open(RUTA_CASTIGADOS, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Convert lists to sets for O(1) lookup
            return {int(k): set(v) for k, v in data.items()}
    except Exception as e:
        print(f"[ERROR] Failed to load punished users: {e}")
        return {}


def guardar_castigados(data: dict) -> None:
    """
    Save punished users to JSON file.
    
    Args:
        data: Dictionary with community IDs mapping to sets of user IDs
    """
    try:
        # Convert sets to lists for JSON serialization
        serializable = {str(k): list(v) for k, v in data.items()}
        with open(RUTA_CASTIGADOS, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[ERROR] Failed to save punished users: {e}")


# ==================== COMMAND HANDLERS ====================

async def get_theme_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Display chat ID and theme (message_thread_id) information.
    
    Useful for configuring new communities and debugging.
    """
    if not update.message:
        return
    
    thread_id = update.message.message_thread_id
    chat_id = update.effective_chat.id
    
    await update.message.reply_text(
        f"📌 Chat ID: `{chat_id}`\n"
        f"📌 Theme (message_thread_id): `{thread_id}`",
        parse_mode="Markdown"
    )


async def saludar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a festive welcome message to the chat."""
    mensaje_bienvenida = (
        "🎄✨ *¡Ho, ho, ho! Llegó PiBot al chat* ✨🎄\n"
        "¡Hola a todos! 🤖🎅\n"
        "Estoy aquí para traer *alegría, buena vibra y espíritu navideño* a este lugar.\n"
        "Prepárense para luces, diversión y un montón de sorpresas festivas. 🎁❄️\n\n"
        "¡Que comience la magia navideña! 🎅🤖✨"
    )
    await update.message.reply_text(mensaje_bienvenida, parse_mode="Markdown")


async def castigar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command: /castigar @user
    
    Confine a user to the punishment corner (topic).
    Only available to DOM (Dominant) users in the main community.
    """
    chat_id = update.effective_chat.id
    actor_id = update.effective_user.id

    # Only available in Kiusama community
    if chat_id != -1003290179217:
        await update.message.reply_text(
            "❌ Este comando no está habilitado en este grupo."
        )
        return
    
    # Check if user is a DOM
    if actor_id not in DOMS:
        await update.message.reply_text(
            "❌ No tienes permisos para usar este comando."
        )
        return
    
    # Extract target user from reply or mention
    # Note: get_receptor needs to be imported or reimplemented
    from handlers.general import get_receptor
    usuario_objetivo = await get_receptor(update, context, 1)
    
    if usuario_objetivo in (False, None):
        await update.message.reply_text(
            "❌ No pude identificar al usuario objetivo."
        )
        return
    
    target_id = usuario_objetivo.id
    target_username = usuario_objetivo.username or usuario_objetivo.first_name

    # Verify ownership relationship (DOM can only punish their submissives)
    if target_id not in DOMS.get(actor_id, []):
        await update.message.reply_text(
            f"❌ No puedes castigar a {target_username}. "
            "No tienes control sobre él/ella."
        )
        return

    # Load and update punishment list
    castigados = cargar_castigados()
    
    if chat_id not in castigados:
        castigados[chat_id] = set()
    
    castigados[chat_id].add(target_id)
    guardar_castigados(castigados)

    await update.message.reply_text(
        f"🔇 @{target_username} te has portado mal. "
        "Ahora tendrás que quedarte en el rincón hasta que te perdonen."
    )


async def filtro_castigo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Filter that prevents punished users from posting outside the punishment corner.
    
    If a punished user tries to post in other topics, their message is deleted
    and a reminder is sent.
    """
    if not update.message:
        return
    
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name

    # Get the punishment topic ID for Kiusama
    temas = obtener_temas_por_comunidad(-1003290179217)
    if not temas:
        return
    
    rincon_id = temas.get("theme_rincon")
    
    # Load punishment list
    castigados = cargar_castigados()
    
    if chat_id not in castigados:
        return
    
    if user_id not in castigados[chat_id]:
        return

    # If user is punished and posting outside punishment corner, delete message
    topic = update.message.message_thread_id
    
    if topic != rincon_id:
        try:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=chat_id,
                message_thread_id=topic,
                text=f"Oh oh... @{username} fue atrapado fuera del rincón :)"
            )
        except Exception as e:
            print(f"[WARNING] Could not delete message: {e}")
    

async def perdonar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Command: /perdonar @user
    
    Release a punished user from the punishment corner.
    Only available to the DOM user who punished them.
    """
    chat_id = update.effective_chat.id
    actor_id = update.effective_user.id

    # Only in Kiusama
    if chat_id != -1003290179217:
        await update.message.reply_text(
            "❌ Este comando no está habilitado en este grupo."
        )
        return

    # Check permission
    if actor_id not in DOMS:
        await update.message.reply_text(
            "❌ No tienes permiso para usar este comando."
        )
        return

    # Get target user
    from handlers.general import get_receptor
    usuario_objetivo = await get_receptor(update, context, args_length=1)

    if usuario_objetivo in (False, None):
        await update.message.reply_text(
            "❌ No pude identificar al usuario que deseas perdonar."
        )
        return

    target_id = usuario_objetivo.id
    target_username = usuario_objetivo.username or usuario_objetivo.first_name

    # Verify ownership
    if target_id not in DOMS.get(actor_id, []):
        await update.message.reply_text(
            f"❌ No puedes perdonar a @{target_username}."
        )
        return

    # Load and update
    castigados = cargar_castigados()

    if chat_id not in castigados or target_id not in castigados[chat_id]:
        await update.message.reply_text(
            f"ℹ️ @{target_username} no está castigado."
        )
        return

    # Remove from punishment
    castigados[chat_id].remove(target_id)
    
    if not castigados[chat_id]:
        del castigados[chat_id]
    
    guardar_castigados(castigados)

    await update.message.reply_text(
        f"✅ @{target_username} ha sido perdonado. "
        "Ya puede hablar en todos los temas."
    )


async def bloquear_comunidad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Filter to block certain communities from using the bot.
    
    Prevents the bot from responding in blacklisted communities.
    """
    if not update.effective_chat:
        return

    # Block specific community
    BLOCKED_COMMUNITY = -1003397946543
    
    if update.effective_chat.id == BLOCKED_COMMUNITY:
        if update.message:
            await update.message.reply_text(
                "❌ Este bot no está habilitado para esta comunidad."
            )
        
        # Stop all further handlers
        raise ApplicationHandlerStop()


# ==================== BOT SETUP AND EXECUTION ====================

def main() -> None:
    """
    Initialize and run the PiBot telegram bot.
    
    Sets up:
    - Handlers grouped by priority
    - Command handlers for all commands
    - Callback handlers for inline keyboards
    - Message filters for images and special messages
    - Punishment filter to enforce confinement
    """
    # Initialize database
    print("[INIT] Creating database if it doesn't exist...")
    create_database()
    
    print("[INIT] Creating tables...")
    create_tables()
    
    print("[INIT] Seeding items catalog...")
    seed_items()
    
    print("[INIT] Initializing BotMaster roles...")
    init_botmaster_roles(BOTMASTER_IDS)
    
    print("[INIT] Restarting active combats...")
    restart_all_combats()
    
    app = Application.builder().token(BOT_TOKEN).build()

    # Group -2: Auto-register users on any message (silent, never blocks)
    app.add_handler(MessageHandler(filters.ALL, auto_registrar), group=-2)

    # Group -1: Community blocking filter (runs first, can stop others)
    app.add_handler(MessageHandler(filters.ALL, bloquear_comunidad), group=-1)

    # Group 0: Core commands (start, admin commands)
    app.add_handler(CommandHandler("start", start), group=0)
    app.add_handler(CommandHandler("castigar", castigar), group=0)
    app.add_handler(CommandHandler("perdonar", perdonar), group=0)
    
    # Group 1: Games and betting commands
    app.add_handler(CommandHandler("apostar", apostar), group=1)
    app.add_handler(CommandHandler("aceptar", aceptar), group=1)
    app.add_handler(CommandHandler("cancelar", cancelar_apuesta), group=1)
    app.add_handler(CommandHandler("robar", robar), group=1)
    app.add_handler(CommandHandler("jugar", jugar), group=1)
    app.add_handler(CommandHandler("usar", usar), group=1)
    # MessageHandler for dice - handles both betting and combat
    app.add_handler(MessageHandler(filters.Dice.DICE, detectar_dado), group=1)

    # Group 2: Economy and general commands
    app.add_handler(CommandHandler("tienda", tienda), group=2)
    app.add_handler(CommandHandler("inventario", inventario), group=2)
    app.add_handler(CommandHandler("ver", ver), group=2)
    app.add_handler(CommandHandler("regalar", regalar), group=2)
    app.add_handler(CommandHandler("dar", dar), group=2)
    app.add_handler(CommandHandler("quitar", quitar), group=2)
    app.add_handler(CommandHandler("NumAzar", numero_azar), group=2)
    app.add_handler(CommandHandler("id", get_theme_id), group=2)
    app.add_handler(CommandHandler("saludar", saludar), group=2)
    app.add_handler(CommandHandler("AsignarRol", asignar_rol), group=2)
    app.add_handler(CommandHandler("MiRol", ver_rol), group=2)
    app.add_handler(CommandHandler("Suerte", suerte), group=2)
    app.add_handler(CommandHandler("userid", userid), group=2)

    # Group 2.5: Battle/Combat system (refactored)
    app.add_handler(CommandHandler("lucha", lucha), group=2)
    app.add_handler(CommandHandler("aceptarlucha", aceptar_lucha), group=2)
    # Dice handler for combat is in group=1 with detectar_dado
    app.add_handler(CommandHandler("ataque", ataque), group=2)  # Backward compatibility

    # Group 3: Reward handler (automatic rewards for images)
    app.add_handler(
        MessageHandler(
            filters.PHOTO | filters.VIDEO | filters.ANIMATION,
            manejar_imagenes
        ),
        group=3
    )

    # Group 4: Welcome and onboarding (currently disabled)
    # Uncomment to enable welcome messages for new members
    # app.add_handler(
    #     MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, nuevo_usuario),
    #     group=4
    # )
    # app.add_handler(
    #     MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje_de_presentaciones),
    #     group=4
    # )

    # Group 5: Callback handlers for inline keyboards
    app.add_handler(
        CallbackQueryHandler(
            menu_callback,
            pattern="^(ver_comandos|abrir_tienda|ver_inventario|perfil)$"
        ),
        group=5
    )
    app.add_handler(
        CallbackQueryHandler(
            inventario_callback,
            pattern="^(inv_prev_|inv_next_|ver_item_)"
        ),
        group=5
    )
    app.add_handler(
        CallbackQueryHandler(
            tienda_callback,
            pattern="^(producto_|volver_menu|abrir_tienda|volver_catalogo|comprar_)"
        ),
        group=5
    )

    # Group 6: Punishment filter (prevents messages outside punishment corner)
    app.add_handler(MessageHandler(filters.ALL, filtro_castigo), group=6)
app.add_handler(CommandHandler("blackjack", cmd_blackjack))

    # Start the bot
    print("🤖 PiBot iniciado e listo para recibir mensajes...")
    import threading
    threading.Thread(target=run_server, daemon=True).start()
    
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
