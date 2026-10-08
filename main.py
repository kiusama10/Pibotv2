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
from src.database.database import create_database, create_tables, restart_all_combats, seed_items, init_botmaster_roles, get_campo_usuario, get_usuario_resumen, insert_user, normalizar_nombre, update_perfil, is_botmaster

# Handler imports - General commands
from handlers.general import dar, ver, regalar, numero_azar, quitar, userid
from handlers.starting_menu import start, comandos, menu_callback
from handlers.tienda import tienda, tienda_callback
from handlers.inventario import inventario, inventario_callback, usar
from handlers.battles import lucha, ataque, aceptar_lucha, cancelar_lucha
from handlers.roles import asignar_rol, ver_rol, suerte as suerte_admin_legacy, hacer_botmaster, quitar_botmaster

# Handler imports - Games and rewards
from handlers.theme_juegosYcasino import (
    apostar, aceptar, detectar_dado, cancelar_apuesta, jugar, robar, reiniciar_apuesta_callback, aceptar_apuesta_callback, recuperar_apuestas_al_iniciar
)
from handlers.rewards import manejar_imagenes
from handlers.social_economy import titulos, comprartitulo, regalos, regalo, misregalos, mistitulos, rankingregalos, mercado, vender, comprarmercado, empenar, desempenar, social_callback, process_social_input
from handlers.profile_social import perfil, editarperfil, privacidadperfil, equipartitulo, fotoperfil, profile_editor_callback, profile_text_input, profile_photo_input
from handlers.profile_cosmetics import cosmeticos, comprarcosmetico, miscosmeticos, equiparmarco, equiparinsignia, cosmetics_callback
from handlers.global_events import seasonal_event_tick
from handlers.bankiu_rankings import bankiu, pagarbanco, ranking, ranking_pipesos, bankiu_callback, track_activity, activity_flush_job, ranking_maintenance_job, bankiu_collect_overdue_job
from handlers.bdsm_quiz import quiz_tick, quiz_callback, quiz_manual, quiz_now, ensure_quiz_tables
from handlers.bdsm_facts import bdsm_fact_tick, ensure_fact_tables, FACT_INTERVAL_SECONDS
from handlers.bdsm_dictionary import dictionary_tick, INTERVAL_SECONDS as DICTIONARY_INTERVAL_SECONDS
from handlers.knowledge import wiki, buscar
from src.utils.instance_guard import acquire_single_poller_lock
from src.utils.seasonal_bot import SeasonalExtBot
from src.utils.root_owner import ensure_root_identity
from handlers.casino_pvp import tortugas, tortuga, ranking_tortugas, blackjack, cancelar_blackjack, casino_pvp_callback, ensure_casino_pvp_tables, turtle_season_maintenance_job, process_turtle_input
from handlers.auctions import subasta, puja, versubasta, cancelarsubasta, auction_maintenance_job
from handlers.assassin_game import asesino, reiniciarasesino, cancelarasesino, terminarasesino, assassin_callback, assassin_cycle_job, assassin_track_member, ensure_assassin_tables
from handlers.help_center import pipesos, instrucciones, canales, help_callback, channel_callback
from handlers.bounty import caza
from handlers.vinculos import vinculo, cancelarvinculo, separarse, vinculo_callback, ensure_vinculo_tables
from handlers.drawing_game import dibujar, matar_dibujo, drawing_callback, drawing_guess, ensure_drawing_tables, drawing_maintenance_job
from handlers.presentation_watchdog import silent_new_member_watch, detect_presentation_message, presentation_watchdog_job, ensure_presentation_tables, presentaciones_command
from handlers.music_fee import paid_music_post, ensure_music_tables, activarmusica, desactivarmusica
from handlers.shop_admin import agregargif, cancelaragregargif, gif_admin_text_input
from handlers.pipeso_extras import cajas, pociones, nivel, tipografias, gifvictoria, quitargif, extras_callback, victory_callback, victory_toggle_callback, victory_input, xp_activity, ensure_extras_tables, suerte_diaria, baloncesto, challenge_points_command, ranking_retos, challenge_weekly_awards_job

# Handler imports - User onboarding
from handlers.welcoming import nuevo_usuario, mensaje_de_presentaciones
from handlers.emoji_party_games import dardos, boliche, aliados, cancelar_emoji_juego, emoji_game_callback
from handlers.dante import ensure_dante_tables, dante_observer, dante_command, dante_callback
from handlers.everyone import todos
from handlers.activity_admin import actividad, actividad_callback, ensure_member_activity_table, member_activity_observer
from handlers.community_activities import ensure_community_tables, daily_question_job, daily_answer_handler, weekly_awards_job, ranking_callback, ranking_command, pregunta_dia_info
from handlers.palabra_relampago import ensure_palabra_tables, palabra_hourly_job, palabra_guess, palabra_prueba, palabra_on, palabra_off
from handlers.batalla_naval import batalla_naval, cancelar_naval, naval_callback, ranking_naval, ensure_naval_tables
from handlers.gato import gato, cancelar_gato, ranking_gato, gato_callback, ensure_gato_tables

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

    # Registra silenciosamente miembros vistos para el sorteo automático del Asesino.
    try: assassin_track_member(update)
    except Exception: pass

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
    """Comando /bienvenida: presentación educativa y estacional de la comunidad."""
    if not update.effective_message:
        return
    from src.utils.seasonal import current_season, TZ
    from datetime import datetime
    import random

    now_local = datetime.now(TZ)
    season = current_season(now_local)
    fecha = now_local.strftime("%d/%m/%Y")
    seasonal = {
        "halloween": ("🎃🕸️", "Esta temporada las sombras, las cadenas decorativas y el ambiente de Halloween se apoderaron de PiBot. Aquí el único susto que no queremos es descubrir que alguien olvidó hablar de límites y consentimiento."),
        "dia_muertos": ("💀🌼", "Entre flores, recuerdos y velas, celebramos también las historias que construyen una comunidad. Aprender de quienes estuvieron antes es parte de cuidar lo que hacemos hoy."),
        "navidad": ("🎄⛓️", "Diciembre llegó con regalos, luces y caos navideño. Entre todo eso, hay algo que no cambia con la temporada: respeto, comunicación y consentimiento."),
        "san_valentin": ("💘🌹", "San Valentín puede hablar de vínculos, pero aquí recordamos que ningún vínculo se sostiene solo con una etiqueta: se construye con comunicación, acuerdos y respeto."),
        "anio_nuevo": ("🎆🖤", "Comienza otro año para aprender, conocer gente y descubrir nuevas partes de nosotros mismos. Los acuerdos también pueden revisarse: cambiar y aprender forma parte del camino."),
        "independencia_mx": ("🇲🇽🖤", "Septiembre también llegó a PiBot. Celebramos la comunidad sin olvidar que libertad y autonomía son palabras importantes aquí: nadie tiene autoridad sobre otra persona sin un acuerdo real."),
        "normal": ("🖤⛓️", "No hace falta una fecha especial para recordar qué queremos construir: una comunidad donde podamos aprender, conversar y ser nosotros mismos con respeto."),
    }
    icon, fest = seasonal.get(season, seasonal["normal"])
    closings = [
        "Aquí nadie necesita saberlo todo para participar. Preguntar, escuchar y aprender también forman parte de la experiencia.",
        "Puedes tener años de experiencia o estar descubriendo todo esto hoy. Lo importante es mantener curiosidad, respeto y responsabilidad.",
        "Las etiquetas ayudan a describirnos, pero nunca sustituyen una conversación. Cada persona y cada dinámica pueden vivirlas de manera diferente.",
    ]
    mensaje_final = (
        f"{icon} <b>BIENVENIDOS A LA COMUNIDAD</b> {icon}\n<i>{fecha} · La bienvenida cambia con el calendario de PiBot.</i>\n\n"
        "Este es un espacio para conversar, aprender, convivir y descubrir el BDSM sin convertirlo en una competencia por quién sabe más o quién tiene el título más impresionante. "
        "BDSM reúne conceptos relacionados con Bondage y Disciplina, Dominación y Sumisión, y Sadismo y Masoquismo, pero detrás de las siglas existe algo todavía más importante: personas reales, acuerdos reales y responsabilidad.\n\n"
        "⛓️ <b>¿Nuevo por aquí?</b>\n"
        "No necesitas elegir un rol inmediatamente. Dom, sub, Switch, brat y muchas otras etiquetas pueden servir para explicar preferencias o formas de vivir una dinámica, pero ninguna etiqueta concede derechos sobre otra persona. "
        "Una brat, por ejemplo, suele expresar una forma de sumisión mediante desafío o provocación juguetona dentro de límites negociados; no es simplemente ignorar acuerdos.\n\n"
        "🛡️ <b>Lo que sí queremos cuidar</b>\n"
        "Consentimiento, negociación, límites, comunicación, privacidad y aftercare son temas que vas a escuchar bastante. Un sí puede cambiar, un límite puede aparecer después y tener experiencia nunca convierte a alguien en dueño de las decisiones de otra persona.\n\n"
        f"{fest}\n\n"
        "📚 Además, PiBot irá dejando periódicamente cápsulas de <b>¿Sabías que...?</b> con historia, conceptos, roles, mitos y cultura BDSM para que siempre haya algo interesante que aprender o debatir.\n\n"
        f"💬 {random.choice(closings)}\n\n"
        "📜 Lee las reglas, participa a tu ritmo y recuerda que una buena comunidad no se construye porque todos pensemos igual, sino porque sabemos convivir y respetar los límites de los demás.\n\n"
        "🦅 <b>Bienvenido. — Kiu y PiBot</b>"
    )
    await update.effective_message.reply_text(mensaje_final, parse_mode="HTML")

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
    if not is_botmaster(actor_id) and actor_id not in DOMS:
        
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
    if not is_botmaster(actor_id) and target_id not in DOMS.get(actor_id, []):
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
    if not is_botmaster(actor_id) and actor_id not in DOMS:
        
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
    if not is_botmaster(actor_id) and target_id not in DOMS.get(actor_id, []):
        
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


async def root_identity_bootstrap(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Keep Kiu's protected ROOT role self-healing without touching other users."""
    if update.effective_user:
        ensure_root_identity(update.effective_user)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Central unexpected-error logger."""
    import logging
    log=logging.getLogger(__name__)
    if isinstance(update, Update):
        cq=update.callback_query
        log.error("Unhandled PiBot error | user=%s chat=%s update_id=%s callback=%r message=%r",
                  getattr(update.effective_user,"id",None),getattr(update.effective_chat,"id",None),update.update_id,
                  (cq.data if cq else None),(update.effective_message.text if update.effective_message else None),exc_info=context.error)
        if cq:
            try: await cq.answer("⚠️ Esa acción falló. El error quedó registrado para revisión.",show_alert=True)
            except Exception: pass
            return
    else:
        log.exception("Unhandled PiBot error",exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try: await update.effective_message.reply_text("⚠️ PiBot encontró un error al procesar eso. El detalle quedó registrado.")
        except Exception: pass


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
    ensure_fact_tables()
    ensure_casino_pvp_tables()
    ensure_drawing_tables()
    ensure_presentation_tables()
    try:
        ensure_dante_tables()
    except Exception as exc:
        print(f"[DANTE INIT] DANTE no pudo iniciar y queda aislado; PiBot continúa: {type(exc).__name__}: {exc}")
    ensure_music_tables()
    ensure_vinculo_tables()
    ensure_extras_tables()
    ensure_assassin_tables()
    ensure_community_tables()
    ensure_member_activity_table()
    ensure_palabra_tables()
    ensure_naval_tables()
    ensure_gato_tables()
    
    print("[INIT] Restarting active combats...")
    restart_all_combats()
    
    app = Application.builder().bot(SeasonalExtBot(token=BOT_TOKEN)).post_init(recuperar_apuestas_al_iniciar).build()
    app.add_error_handler(error_handler)
    app.add_handler(MessageHandler(filters.ALL, root_identity_bootstrap), group=-10)
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
        # Educational BDSM capsule every 2.5 hours. No economy side effects.
        app.job_queue.run_repeating(bdsm_fact_tick, interval=FACT_INTERVAL_SECONDS, first=300, name="bdsm_fact_2h")
        app.job_queue.run_repeating(dictionary_tick, interval=DICTIONARY_INTERVAL_SECONDS, first=1200, name="bdsm_dictionary_75m")
        app.job_queue.run_repeating(turtle_season_maintenance_job, interval=3600, first=45, name="turtle_monthly_awards")
        app.job_queue.run_repeating(assassin_cycle_job, interval=300, first=20, name="assassin_6h_cycle")
        # Palabra Relámpago: una ronda al inicio de cada hora en el tema Juegos, si está activada.
        _pnow=datetime.now(ZoneInfo("America/Mexico_City")); _pnext=(_pnow+timedelta(hours=1)).replace(minute=0,second=0,microsecond=0)
        app.job_queue.run_repeating(palabra_hourly_job, interval=3600, first=max(1,(_pnext-_pnow).total_seconds()), name="palabra_relampago_hourly")
        # Pregunta del Día: 10:00 AM hora de México. El coordinador reserva su ventana para evitar choques.
        from datetime import time as dt_time
        from zoneinfo import ZoneInfo as _ZoneInfo
        app.job_queue.run_daily(daily_question_job, time=dt_time(hour=10, minute=0, tzinfo=_ZoneInfo('America/Mexico_City')), name='pregunta_del_dia_10mx')
        # Cierre/pago semanal idempotente: lunes 10:50, fuera de la ventana protegida de la Pregunta del Día.
        app.job_queue.run_daily(weekly_awards_job, time=dt_time(hour=10, minute=50, tzinfo=_ZoneInfo('America/Mexico_City')), days=(1,), name='ranking_quiz_weekly')
        app.job_queue.run_daily(challenge_weekly_awards_job, time=dt_time(hour=0, minute=5, tzinfo=_ZoneInfo('America/Mexico_City')), days=(1,), name='ranking_retos_weekly')

    # DANTE observes independently of presentation controls.
    app.add_handler(MessageHandler(filters.ALL, dante_observer), group=-5)

    # Group -4: capture genuinely new members BEFORE auto-registration. Sends nothing.
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, silent_new_member_watch), group=-4)
    # Any genuine text/media in Presentaciones cancels the 30-minute removal timer.
    app.add_handler(MessageHandler((filters.TEXT | filters.PHOTO | filters.VIDEO | filters.ANIMATION | filters.Document.ALL | filters.VOICE | filters.AUDIO) & ~filters.COMMAND, detect_presentation_message), group=-4)

    # Group -2: Auto-register users on any message (silent, never blocks)
    app.add_handler(MessageHandler(filters.ALL, auto_registrar), group=-2)
    # Permanent written-message activity registry. Keep it in its own PTB group:
    # only one matching handler runs per group, so sharing -3 with track_activity
    # prevented this observer from ever receiving messages.
    app.add_handler(MessageHandler(filters.ALL, member_activity_observer), group=-6)
    # Existing participation/ranking tracker remains unchanged.
    app.add_handler(MessageHandler(filters.ALL, track_activity), group=-3)

    # Group -1: Community blocking filter (runs first, can stop others)
    app.add_handler(MessageHandler(filters.ALL, bloquear_comunidad), group=-1)

    # Group 0: Core commands (start, admin commands)
    app.add_handler(CommandHandler("start", start), group=0)
    app.add_handler(CommandHandler("dante", dante_command), group=0)
    app.add_handler(CommandHandler("presentaciones", presentaciones_command), group=0)
    app.add_handler(CommandHandler("todos", todos), group=0)
    app.add_handler(CommandHandler("actividad", actividad), group=0)
    app.add_handler(CommandHandler("comandos", comandos), group=0)
    app.add_handler(CommandHandler(["bienvenida", "saludar"], saludar), group=0)
    app.add_handler(CommandHandler("castigar", castigar), group=0)
    app.add_handler(CommandHandler("perdonar", perdonar), group=0)
    
    # Group 1: Games and betting commands
    app.add_handler(CommandHandler("apostar", apostar), group=1)
    app.add_handler(CommandHandler("aceptar", aceptar), group=1)
    app.add_handler(CommandHandler("cancelar", cancelar_apuesta), group=1)
    app.add_handler(CommandHandler("dardos", dardos), group=1)
    app.add_handler(CommandHandler("boliche", boliche), group=1)
    app.add_handler(CommandHandler("aliados", aliados), group=1)
    app.add_handler(CommandHandler(["cancelardardos","cancelarboliche","cancelaraliados"], cancelar_emoji_juego), group=1)
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
    app.add_handler(CommandHandler("AsignarRol", asignar_rol), group=2)
    app.add_handler(CommandHandler("MiRol", ver_rol), group=2)
    app.add_handler(CommandHandler("suerte", suerte_diaria), group=2)
    # Conserva el antiguo ajuste administrativo de roles bajo un nombre no conflictivo.
    app.add_handler(CommandHandler("ajustarsuerte", suerte_admin_legacy), group=2)
    app.add_handler(CommandHandler("baloncesto", baloncesto), group=2)
    app.add_handler(CommandHandler("batallanaval", batalla_naval), group=2)
    app.add_handler(CommandHandler("rankingnaval", ranking_naval), group=2)
    app.add_handler(CommandHandler("cancelarnaval", cancelar_naval), group=2)
    app.add_handler(CommandHandler("gato", gato), group=2)
    app.add_handler(CommandHandler("cancelargato", cancelar_gato), group=2)
    app.add_handler(CommandHandler("rankinggato", ranking_gato), group=2)
    app.add_handler(CommandHandler("rankingretos", ranking_retos), group=2)
    app.add_handler(CommandHandler("palabraprueba", palabra_prueba), group=2)
    app.add_handler(CommandHandler("palabraon", palabra_on), group=2)
    app.add_handler(CommandHandler("palabraoff", palabra_off), group=2)
    app.add_handler(MessageHandler(filters.Regex(r"^/[+-]\d+(?:@\w+)?(?:\s|$)"), challenge_points_command), group=2)
    app.add_handler(CommandHandler("hacerbotmaster", hacer_botmaster), group=2)
    app.add_handler(CommandHandler("quitarbotmaster", quitar_botmaster), group=2)
    app.add_handler(CommandHandler("userid", userid), group=2)
    app.add_handler(CommandHandler("bankiu", bankiu), group=2)
    app.add_handler(CommandHandler("pagarbanco", pagarbanco), group=2)
    app.add_handler(CommandHandler("ranking", ranking), group=2)
    app.add_handler(CommandHandler("ricospipesos", ranking_pipesos), group=2)
    app.add_handler(CommandHandler("quiz", quiz_manual), group=2)
    app.add_handler(CommandHandler("quizahora", quiz_now), group=2)
    app.add_handler(CommandHandler("rankingquiz", ranking_command), group=2)
    app.add_handler(CommandHandler("preguntadia", pregunta_dia_info), group=2)
    app.add_handler(CommandHandler("tortugas", tortugas), group=2)
    app.add_handler(CommandHandler("tortuga", tortuga), group=2)
    app.add_handler(CommandHandler("rankingtortugas", ranking_tortugas), group=2)
    app.add_handler(CommandHandler("blackjack", blackjack), group=2)
    app.add_handler(CommandHandler("cancelarblackjack", cancelar_blackjack), group=2)
    app.add_handler(CommandHandler("subasta", subasta), group=2)
    app.add_handler(CommandHandler("puja", puja), group=2)
    app.add_handler(CommandHandler("versubasta", versubasta), group=2)
    app.add_handler(CommandHandler("cancelarsubasta", cancelarsubasta), group=2)
    app.add_handler(CommandHandler("asesino", asesino), group=2)
    app.add_handler(CommandHandler("reiniciarasesino", reiniciarasesino), group=2)
    app.add_handler(CommandHandler("cancelarasesino", cancelarasesino), group=2)
    app.add_handler(CommandHandler("terminarasesino", terminarasesino), group=2)
    app.add_handler(CommandHandler("agregargif", agregargif), group=2)
    app.add_handler(CommandHandler("cancelaragregargif", cancelaragregargif), group=2)
    app.add_handler(CommandHandler("pipesos", pipesos), group=2)
    app.add_handler(CommandHandler("instrucciones", instrucciones), group=2)
    app.add_handler(CommandHandler("canales", canales), group=2)
    app.add_handler(CommandHandler("wiki", wiki), group=2)
    app.add_handler(CommandHandler("buscar", buscar), group=2)
    app.add_handler(CommandHandler("cajas", cajas), group=2)
    app.add_handler(CommandHandler("tipografias", tipografias), group=2)
    app.add_handler(CommandHandler("gifvictoria", gifvictoria), group=2)
    app.add_handler(CommandHandler("quitargif", quitargif), group=2)
    app.add_handler(CommandHandler("caza", caza), group=2)
    app.add_handler(CommandHandler("vinculo", vinculo), group=2)
    app.add_handler(CommandHandler("cancelarvinculo", cancelarvinculo), group=2)
    app.add_handler(CommandHandler("separarse", separarse), group=2)
    app.add_handler(CommandHandler("activarmusica", activarmusica), group=2)
    app.add_handler(CommandHandler("desactivarmusica", desactivarmusica), group=2)
    app.add_handler(CommandHandler("dibujar", dibujar), group=2)
    app.add_handler(CommandHandler("matardibujo", matar_dibujo), group=2)
    app.add_handler(CommandHandler("titulos", titulos), group=2)
    app.add_handler(CommandHandler("comprartitulo", comprartitulo), group=2)
    app.add_handler(CommandHandler("mistitulos", mistitulos), group=2)
    app.add_handler(CommandHandler("perfil", perfil), group=2)
    app.add_handler(CommandHandler("fotoperfil", fotoperfil), group=2)
    app.add_handler(CommandHandler("editarperfil", editarperfil), group=2)
    app.add_handler(CommandHandler("privacidadperfil", privacidadperfil), group=2)
    app.add_handler(CommandHandler("equipartitulo", equipartitulo), group=2)

    # Group 2.5: Battle/Combat system (refactored)
    app.add_handler(CommandHandler("lucha", lucha), group=2)
    app.add_handler(CommandHandler("aceptarlucha", aceptar_lucha), group=2)
    app.add_handler(CommandHandler("cancelarlucha", cancelar_lucha), group=2)
    # Dice handler for combat is in group=1 with detectar_dado
    app.add_handler(CommandHandler("ataque", ataque), group=2)  # Backward compatibility

    # Guess detector: only reacts when an active drawing round exists in this exact chat/topic.
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND, profile_text_input), group=2)
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.PHOTO, profile_photo_input), group=2)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, drawing_guess), group=3)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, daily_answer_handler), group=4)
    # Grupo separado para que no compita con Dibuja ni Pregunta del Día.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, palabra_guess), group=7)

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

    # Legacy welcome handlers remain intentionally disabled: Rose handles welcome.
    # The silent 30-minute presentation watchdog is active in group -4 above.
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
            pattern="^(ver_comandos|ver_inventario|perfil|instrucciones|abrir_tienda)$"
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
            pattern="^(producto_|volver_menu|volver_catalogo|comprar_|shop_page_|shop_noop$|gif_preview_)"
        ),
        group=5
    )

    app.add_handler(
        CallbackQueryHandler(profile_editor_callback, pattern="^profile_(editor$|role$|experience$|privacy$|preview$|photo$|text_|set_|help_|public$|private$)"),
        group=5
    )
    app.add_handler(
        CallbackQueryHandler(cosmetics_callback, pattern="^cos_"),
        group=5
    )
    app.add_handler(CallbackQueryHandler(dante_callback, pattern="^dante:"), group=5)
    app.add_handler(CallbackQueryHandler(actividad_callback, pattern="^act:"), group=5)
    app.add_handler(CallbackQueryHandler(social_callback, pattern="^soc:"), group=5)
    app.add_handler(CallbackQueryHandler(vinculo_callback, pattern="^vin:"), group=5)
    app.add_handler(
        CallbackQueryHandler(bankiu_callback, pattern="^bank_"),
        group=5
    )
    app.add_handler(CallbackQueryHandler(quiz_callback, pattern="^bq:"), group=5)
    app.add_handler(CallbackQueryHandler(extras_callback, pattern="^ex:(box|font|fontpage|luck):|^ex:fontnoop$"), group=5)
    app.add_handler(CallbackQueryHandler(victory_toggle_callback, pattern="^vg:toggle:"), group=5)
    app.add_handler(CallbackQueryHandler(victory_callback, pattern="^vg:(gif|text|games|preview|remove)$"), group=5)
    app.add_handler(CallbackQueryHandler(casino_pvp_callback, pattern="^(turtle|bj):"), group=5)
    app.add_handler(CallbackQueryHandler(assassin_callback, pattern="^as:"), group=5)
    app.add_handler(CallbackQueryHandler(naval_callback, pattern="^nv:"), group=5)
    app.add_handler(CallbackQueryHandler(gato_callback, pattern="^gt:"), group=5)
    app.add_handler(CallbackQueryHandler(emoji_game_callback, pattern="^eg:"), group=5)
    app.add_handler(CallbackQueryHandler(ranking_callback, pattern="^cr:rank$"), group=5)
    app.add_handler(CallbackQueryHandler(drawing_callback, pattern="^draw:"), group=5)
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^ph:"), group=5)
    app.add_handler(CallbackQueryHandler(channel_callback, pattern="^ch:"), group=5)
    app.add_handler(
        CallbackQueryHandler(reiniciar_apuesta_callback, pattern="^reiniciar_apuesta$"),
        group=5
    )
    app.add_handler(
        CallbackQueryHandler(aceptar_apuesta_callback, pattern="^aceptar_apuesta$"),
        group=5
    )

    # Turtle UI text input (rename/custom stake). It ignores users without a pending turtle action.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_turtle_input), group=8)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process_social_input), group=9)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, gif_admin_text_input), group=10)

    # Group 6: Punishment filter (prevents messages outside punishment corner)
    app.add_handler(MessageHandler(filters.ALL, filtro_castigo), group=6)

    # Start the bot
    print("🤖 PiBot listo. Iniciando SAO-CB, servidor web y guardia de instancia...")
    import threading, time
    def _run_saocb_internal():
        import uvicorn
        uvicorn.run("saocb_app:app", host="127.0.0.1", port=8091, log_level="warning")
    threading.Thread(target=_run_saocb_internal, daemon=True, name="saocb-api").start()
    time.sleep(0.5)
    threading.Thread(target=run_server, daemon=True, name="pibot-web").start()
    while not acquire_single_poller_lock():
        print("[INSTANCE] Otra instancia de PiBot ya posee el polling. Esta copia queda en espera segura.")
        time.sleep(15)
    print("[INSTANCE] Lock adquirido: esta es la única instancia autorizada para getUpdates.")
    app.add_handler(MessageHandler((filters.TEXT | filters.ANIMATION) & ~filters.COMMAND, victory_input), group=11)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
