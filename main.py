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

orig_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4(*args, **kwargs):
    return [x for x in orig_getaddrinfo(*args, **kwargs) if x[0] == socket.AF_INET]
socket.getaddrinfo = getaddrinfo_ipv4

from drawing_web import run_server

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
from src.database.database import create_database, create_tables, restart_all_combats, seed_items, init_botmaster_roles, get_campo_usuario, get_usuario_resumen, insert_user, normalizar_nombre, update_perfil

# Handler imports - General commands
from handlers.general import dar, ver, regalar, numero_azar, quitar, userid
from handlers.starting_menu import start, comandos, menu_callback
from handlers.tienda import tienda, tienda_callback
from handlers.inventario import inventario, inventario_callback, usar
from handlers.battles import lucha, ataque, aceptar_lucha
from handlers.roles import asignar_rol, ver_rol, suerte, hacer_botmaster, quitar_botmaster

# Handler imports - Games and rewards
from handlers.theme_juegosYcasino import (
    apostar, aceptar, detectar_dado, cancelar_apuesta, jugar, robar, reiniciar_apuesta_callback, recuperar_apuestas_al_iniciar
)
from handlers.rewards import manejar_imagenes
from handlers.social_economy import titulos, comprartitulo, regalos, regalo, misregalos, mistitulos, mercado, vender, comprarmercado, empenar, desempenar, social_callback
from handlers.profile_social import perfil, editarperfil, privacidadperfil, equipartitulo, profile_editor_callback, profile_text_input
from handlers.profile_cosmetics import cosmeticos, comprarcosmetico, miscosmeticos, equiparmarco, equiparinsignia, cosmetics_callback
from handlers.global_events import seasonal_event_tick
from handlers.bankiu_rankings import bankiu, pagarbanco, ranking, ranking_pipesos, bankiu_callback, track_activity, activity_flush_job, ranking_maintenance_job, bankiu_collect_overdue_job
from handlers.bdsm_quiz import quiz_tick, quiz_callback, quiz_manual, quiz_now, ensure_quiz_tables
from handlers.casino_pvp import tortugas, blackjack, casino_pvp_callback, ensure_casino_pvp_tables
from handlers.auctions import subasta, puja, cancelarsubasta, auction_maintenance_job
from handlers.assassin_game import asesino, assassin_callback
from handlers.help_center import pipesos, instrucciones, canales, help_callback, channel_callback
from handlers.bounty import caza
from handlers.drawing_game import dibujar, drawing_callback, drawing_guess, ensure_drawing_tables, drawing_maintenance_job
from handlers.presentation_watchdog import silent_new_member_watch, presentation_watchdog_job, ensure_presentation_tables
from handlers.music_fee import paid_music_post, ensure_music_tables, activarmusica, desactivarmusica

# Handler imports - User onboarding
from handlers.welcoming import nuevo_usuario, mensaje_de_presentaciones

# Constants
RUTA_CASTIGADOS = PUNISHMENT_FILE


# ==================== AUTO-REGISTRATION ====================

# Cache only registration/profile metadata. Never caches balances or inventory.
_auto_registered_cache = {}

async def auto_registrar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Silently register any user who sends a message, if not already in the DB.
    Runs in group -2 (before everything else) and never blocks other handlers.
    """
    user = update.effective_user
    if not user or user.is_bot:
        return

    try:
        nombre = normalizar_nombre(user.first_name or "", user.last_name or "")
        if not nombre.strip():
            nombre = user.username or f"user{user.id}"
        signature = (user.username, nombre)

        # Most messages now require zero DB round-trips here. The cache contains
        # no economy data, so balances/inventory can never become stale through it.
        if _auto_registered_cache.get(user.id) == signature:
            return

        resumen = get_usuario_resumen(user.id)
        if resumen is None:
            if insert_user(user.id, 0, user.username, nombre):
                _auto_registered_cache[user.id] = signature
        else:
            cambios = {}
            if resumen.get("username") != user.username:
                cambios["username"] = user.username
            if resumen.get("nombre") != nombre:
                cambios["nombre"] = nombre
            if not cambios or update_perfil(user.id, **cambios):
                _auto_registered_cache[user.id] = signature
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
    """Envia un mensaje de bienvenida con el alma de la comunidad."""
    mensaje_final = (
        "🦅 **Bienvenidos a nuestra Comunidad BDSM** 🦅\n\n"
        "El BDSM es mucho más que una práctica; es la valentía de entregar la voluntad y el honor de saber cuidarla. "
        "Es una danza de **Bondage, Dominación, Sumisión, Sadismo y Masoquismo** donde la piel habla lo que el corazón siente, "
        "siempre bajo el refugio del respeto y la confianza absoluta.\n\n"
        "Queremos detenernos un momento para mirarlos a los ojos y darles las gracias. "
        "A los que están desde el primer día, aguantando tormentas y celebrando victorias; a los que acaban de llegar con el alma abierta "
        "buscando un lugar donde encajar, y también a los que ya se fueron... porque cada uno de ellos dejó un trozo de su historia "
        "que nos ayudó a ser los que somos hoy.\n\n"
        "**Ustedes no son solo usuarios, son la razón por la que este grupo respira.** Sin su lealtad, sin su tiempo y sin su esencia, "
        "esto sería solo un rincón frío y vacío. Ustedes son quienes transforman este chat en un hogar, en una familia y en un refugio "
        "donde podemos ser nosotros mismos sin miedo. Son fundamentales, son valiosos y son el motor de cada paso que damos.\n\n"
        "📩 **Tu voz nos importa:** Este lugar se construye con tus manos, por eso tus sugerencias siempre serán nuestro norte. \n\n"
        "📜 *No olvides leer las reglas; son el pacto que protege nuestra paz.* \n\n"
        "**Todos somos mejores si trabajamos juntos.**\n\n"
        "Con mucho cariño, **Kiu y PiBot**. 🦅💙"
    )
    await update.message.reply_text(mensaje_final, parse_mode="Markdown")

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
    
     # Check if user is a DOM or the BotMaster
    if actor_id not in BOTMASTER_IDS and actor_id not in DOMS:
        
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
    if actor_id not in BOTMASTER_IDS and target_id not in DOMS.get(actor_id, []):
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

    # Check permission for BotMaster or DOM
    if actor_id not in BOTMASTER_IDS and actor_id not in DOMS:
        
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
    # El BotMaster puede perdonar a cualquiera
    if actor_id not in BOTMASTER_IDS and target_id not in DOMS.get(actor_id, []):
        
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


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Central unexpected-error logger."""
    import logging
    logging.getLogger(__name__).exception("Unhandled PiBot error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("⚠️ PiBot encontró un error al procesar eso. Intenta nuevamente.")
        except Exception:
            pass


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
    ensure_quiz_tables()
    ensure_casino_pvp_tables()
    ensure_drawing_tables()
    ensure_presentation_tables()
    ensure_music_tables()
    
    print("[INIT] Restarting active combats...")
    restart_all_combats()
    
    app = Application.builder().token(BOT_TOKEN).post_init(recuperar_apuestas_al_iniciar).build()
    app.add_error_handler(error_handler)
    # Lightweight seasonal event check. DB idempotency prevents duplicate Christmas grants.
    if app.job_queue:
        app.job_queue.run_repeating(seasonal_event_tick, interval=3600, first=5, name="seasonal_events")
        app.job_queue.run_repeating(activity_flush_job, interval=60, first=60, name="participation_flush")
        app.job_queue.run_repeating(ranking_maintenance_job, interval=900, first=20, name="ranking_maintenance")
        app.job_queue.run_repeating(bankiu_collect_overdue_job, interval=3600, first=30, name="bankiu_overdue")
        app.job_queue.run_repeating(auction_maintenance_job, interval=60, first=15, name="auction_maintenance")
        app.job_queue.run_repeating(presentation_watchdog_job, interval=60, first=10, name="presentation_watchdog")
        app.job_queue.run_repeating(drawing_maintenance_job, interval=30, first=12, name="drawing_maintenance")
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        _qnow=datetime.now(ZoneInfo("America/Mexico_City")); _qnext=(_qnow+timedelta(hours=1)).replace(minute=0,second=0,microsecond=0)
        app.job_queue.run_repeating(quiz_tick, interval=3600, first=max(1,(_qnext-_qnow).total_seconds()), name="bdsm_quiz_hourly")

    # Group -4: capture genuinely new members BEFORE auto-registration. Sends nothing.
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, silent_new_member_watch), group=-4)

    # Group -2: Auto-register users on any message (silent, never blocks)
    app.add_handler(MessageHandler(filters.ALL, auto_registrar), group=-2)
    # Participation is throttled to one point/minute/user and flushed in batches.
    app.add_handler(MessageHandler(filters.ALL, track_activity), group=-3)

    # Group -1: Community blocking filter (runs first, can stop others)
    app.add_handler(MessageHandler(filters.ALL, bloquear_comunidad), group=-1)

    # Group 0: Core commands (start, admin commands)
    app.add_handler(CommandHandler("start", start), group=0)
    app.add_handler(CommandHandler("comandos", comandos), group=0)
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
    app.add_handler(CommandHandler("hacerbotmaster", hacer_botmaster), group=2)
    app.add_handler(CommandHandler("quitarbotmaster", quitar_botmaster), group=2)
    app.add_handler(CommandHandler("userid", userid), group=2)
    app.add_handler(CommandHandler("bankiu", bankiu), group=2)
    app.add_handler(CommandHandler("pagarbanco", pagarbanco), group=2)
    app.add_handler(CommandHandler("ranking", ranking), group=2)
    app.add_handler(CommandHandler("ricospipesos", ranking_pipesos), group=2)
    app.add_handler(CommandHandler("quiz", quiz_manual), group=2)
    app.add_handler(CommandHandler("quizahora", quiz_now), group=2)
    app.add_handler(CommandHandler("tortugas", tortugas), group=2)
    app.add_handler(CommandHandler("blackjack", blackjack), group=2)
    app.add_handler(CommandHandler("subasta", subasta), group=2)
    app.add_handler(CommandHandler("puja", puja), group=2)
    app.add_handler(CommandHandler("cancelarsubasta", cancelarsubasta), group=2)
    app.add_handler(CommandHandler("asesino", asesino), group=2)
    app.add_handler(CommandHandler("pipesos", pipesos), group=2)
    app.add_handler(CommandHandler("instrucciones", instrucciones), group=2)
    app.add_handler(CommandHandler("canales", canales), group=2)
    app.add_handler(CommandHandler("caza", caza), group=2)
    app.add_handler(CommandHandler("activarmusica", activarmusica), group=2)
    app.add_handler(CommandHandler("desactivarmusica", desactivarmusica), group=2)
    app.add_handler(CommandHandler("dibujar", dibujar), group=2)
    app.add_handler(CommandHandler("titulos", titulos), group=2)
    app.add_handler(CommandHandler("comprartitulo", comprartitulo), group=2)
    app.add_handler(CommandHandler("regalos", regalos), group=2)
    app.add_handler(CommandHandler("regalo", regalo), group=2)
    app.add_handler(CommandHandler("misregalos", misregalos), group=2)
    app.add_handler(CommandHandler("mistitulos", mistitulos), group=2)
    app.add_handler(CommandHandler("mercado", mercado), group=2)
    app.add_handler(CommandHandler("vender", vender), group=2)
    app.add_handler(CommandHandler("comprarmercado", comprarmercado), group=2)
    app.add_handler(CommandHandler("empenar", empenar), group=2)
    app.add_handler(CommandHandler("desempenar", desempenar), group=2)
    app.add_handler(CommandHandler("perfil", perfil), group=2)
    app.add_handler(CommandHandler("editarperfil", editarperfil), group=2)
    app.add_handler(CommandHandler("privacidadperfil", privacidadperfil), group=2)
    app.add_handler(CommandHandler("equipartitulo", equipartitulo), group=2)
    app.add_handler(CommandHandler("cosmeticos", cosmeticos), group=2)
    app.add_handler(CommandHandler("comprarcosmetico", comprarcosmetico), group=2)
    app.add_handler(CommandHandler("miscosmeticos", miscosmeticos), group=2)
    app.add_handler(CommandHandler("equiparmarco", equiparmarco), group=2)
    app.add_handler(CommandHandler("equiparinsignia", equiparinsignia), group=2)

    # Group 2.5: Battle/Combat system (refactored)
    app.add_handler(CommandHandler("lucha", lucha), group=2)
    app.add_handler(CommandHandler("aceptarlucha", aceptar_lucha), group=2)
    # Dice handler for combat is in group=1 with detectar_dado
    app.add_handler(CommandHandler("ataque", ataque), group=2)  # Backward compatibility

    # Guess detector: only reacts when an active drawing round exists in this exact chat/topic.
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, profile_text_input), group=2)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, drawing_guess), group=3)

    # Paid music posts. Disabled safely until MUSIC_THREAD_ID is configured.
    app.add_handler(MessageHandler((filters.AUDIO | filters.VIDEO | filters.TEXT) & ~filters.COMMAND, paid_music_post), group=2)

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
            pattern="^(ver_comandos|abrir_tienda|ver_inventario|perfil|instrucciones)$"
        ),
        group=5
    )
    app.add_handler(
        CallbackQueryHandler(
            inventario_callback,
            pattern="^(inv_prev_|inv_next_|ver_item_|inv_noop$)"
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

    app.add_handler(
        CallbackQueryHandler(profile_editor_callback, pattern="^profile_(editor$|role$|experience$|privacy$|preview$|text_|set_|help_|public$|private$)"),
        group=5
    )
    app.add_handler(
        CallbackQueryHandler(cosmetics_callback, pattern="^cos_"),
        group=5
    )
    app.add_handler(CallbackQueryHandler(social_callback, pattern="^soc:"), group=5)
    app.add_handler(
        CallbackQueryHandler(bankiu_callback, pattern="^bank_"),
        group=5
    )
    app.add_handler(CallbackQueryHandler(quiz_callback, pattern="^bq:"), group=5)
    app.add_handler(CallbackQueryHandler(casino_pvp_callback, pattern="^(turtle|bj):"), group=5)
    app.add_handler(CallbackQueryHandler(assassin_callback, pattern="^as:"), group=5)
    app.add_handler(CallbackQueryHandler(drawing_callback, pattern="^draw:"), group=5)
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^ph:"), group=5)
    app.add_handler(CallbackQueryHandler(channel_callback, pattern="^ch:"), group=5)
    app.add_handler(
        CallbackQueryHandler(reiniciar_apuesta_callback, pattern="^reiniciar_apuesta$"),
        group=5
    )

    # Group 6: Punishment filter (prevents messages outside punishment corner)
    app.add_handler(MessageHandler(filters.ALL, filtro_castigo), group=6)

    # Start the bot
    print("🤖 PiBot iniciado e listo para recibir mensajes...")
    import threading
    threading.Thread(target=run_server, daemon=True).start()
    
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
