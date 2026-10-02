from handlers.pipeso_extras import send_victory
from src.utils.seasonal import seasonalize
import asyncio,random,uuid
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.general import get_receptor
from src.database.database import normalizar_nombre,get_campo_usuario,insert_user,dar_puntos, dar_recompensa,quitar_puntos,update_perfil,get_suerte,reservar_apuesta_doble,reembolsar_apuesta_doble,consumir_uso_diario,transferir_robo_atomico,get_usuario_resumen,reservar_apuesta_persistente,liquidar_apuesta_persistente,registrar_dado_apuesta,obtener_apuestas_reservadas
from src.config import obtener_temas_por_comunidad

# === BASE DE DATOS EN MEMORIA ===
active_bets = {}
robar_usuarios = {}
juego = {}

def _bet_key(chat_id, thread_id):
    """Keep bets isolated between communities that reuse the same topic id."""
    return (chat_id, thread_id)

# === CREAR APUESTA ===
async def apostar(update: Update, context: ContextTypes.DEFAULT_TYPE):

    CHAT_IDS = obtener_temas_por_comunidad(update.effective_chat.id)

    thread_id = update.message.message_thread_id
    bet_key = _bet_key(update.effective_chat.id, thread_id)
    user = update.effective_user
    
    if thread_id != CHAT_IDS["theme_juegosYcasino"]:
        await update.message.reply_text("⚠️ Este comando solo está permitido en el tema Juegos y Casino.")
        return

    # 📌 Validar parámetros
    if len(context.args) < 1:
        await update.message.reply_text("Uso: /apostar <cantidad>")
        return

    try:
        cantidad = int(context.args[0])
        if cantidad <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ La cantidad debe ser un número mayor que 0.")
        return

    #Verificar si ya hay una apuesta activa
    if bet_key in active_bets:
        await update.message.reply_text("⚠️ Ya hay una apuesta activa en este tema.")
        return

    # 📌 Verificar si el usuario existe y tiene saldo suficiente
    user_id = user.id
    user_username = user.username
    user_nombre = normalizar_nombre(user.first_name,user.last_name)

    resumen = get_usuario_resumen(user_id)
    if resumen is not None:
        user_saldo = resumen["saldo"]
    else:
        insert_user(user_id,0,user_username,user_nombre)
        user_saldo = 0
    
    if user_saldo < cantidad:
        await update.message.reply_text(f"💸 Saldo insuficiente. Tu saldo es de {user_saldo} PiPesos.")
        return

    # 📌 Guardar apuesta inicial en memoria
    active_bets[bet_key] = {
        "apostador_id": user_id,
        "apostador_username": user_username or user_nombre,
        "rival_id": None,
        "rival_username": None,
        "cantidad": cantidad,
        "dados": {"apostador": None, "rival": None},
        "activa": True,
        "apuesta_id": uuid.uuid4().hex
    }

    await update.message.reply_text(
        f"🎲 {user_username or user_nombre} ha creado una apuesta de {cantidad} PiPesos.\n"
        "Cualquier jugador puede escribir /aceptar para unirse en los próximos 60 segundos."
    )

    # 📌 Auto-cancelación en 60 segundos
    async def auto_cancel():
        await asyncio.sleep(60)
        bet = active_bets.get(bet_key)
        if bet and bet["activa"] and bet["rival_id"] is None:
            del active_bets[bet_key]
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⏳ Tiempo agotado. La apuesta fue cancelada automáticamente.",
                message_thread_id=thread_id
            )

    asyncio.create_task(auto_cancel())

# === ACEPTAR APUESTA ===
async def aceptar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    CHAT_IDS = obtener_temas_por_comunidad(update.effective_chat.id)
    
    thread_id = update.message.message_thread_id
    bet_key = _bet_key(update.effective_chat.id, thread_id)
    user = update.effective_user
    
    bet = active_bets.get(bet_key)
    if not bet:
        await update.message.reply_text("⚠️ No hay apuestas activas para aceptar en este tema.")
        return

    if bet["rival_id"] is not None:
        await update.message.reply_text("⚠️ Esta apuesta ya fue aceptada por otro jugador.")
        return

    if user.id == bet["apostador_id"]:
        await update.message.reply_text("⚠️ No puedes aceptar tu propia apuesta.")
        return

    # 📌 Verificar si el usuario existe en el sistema
    user_id = user.id
    user_username = user.username
    user_nombre = normalizar_nombre(user.first_name,user.last_name)
    
    resumen = get_usuario_resumen(user_id)
    if resumen is not None:
        user_saldo = resumen["saldo"]
    else:
        user_saldo = 0
        insert_user(user_id, user_saldo, user_username, user_nombre)

    if user_saldo < bet["cantidad"]:
        await update.message.reply_text(f"💸 Saldo insuficiente. Tu saldo es {user_saldo} PiPesos.")
        return

    # Reserve both wagers at acceptance. This prevents spending the stake mid-game.
    if not reservar_apuesta_persistente(
        bet["apuesta_id"], update.effective_chat.id, thread_id,
        bet["apostador_id"], user_id, bet["cantidad"]
    ):
        await update.message.reply_text(
            "💸 La apuesta no pudo reservarse porque uno de los dos ya no tiene saldo suficiente."
        )
        return

    bet["rival_id"] = user_id
    bet["rival_username"] = user_username or user_nombre
    bet["fondos_reservados"] = True

    await update.message.reply_text(
        f"✅ {user_username or user_nombre} ha aceptado la apuesta de "
        f"{bet['apostador_username']}.\n\n🎲 ¡Ambos deben lanzar el dado para continuar!",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Reiniciar apuesta", callback_data="reiniciar_apuesta")
        ]])
    )

    # Si uno de los jugadores desaparece, no puede bloquear la apuesta indefinidamente.
    # Tras 2 minutos desde la aceptación:
    # - si solo uno lanzó, ese jugador gana el pozo completo;
    # - si ninguno lanzó, se devuelve el dinero a ambos (no hay forma justa de culpar a uno).
    accepted_bet = bet
    async def timeout_apuesta_aceptada():
        await asyncio.sleep(120)
        current = active_bets.get(bet_key)
        if current is not accepted_bet or not current.get("activa"):
            return

        dado_ap = current["dados"]["apostador"]
        dado_rv = current["dados"]["rival"]

        # Si ambos ya lanzaron, detectar_dado ya resolvió (o está resolviendo) la apuesta.
        if dado_ap is not None and dado_rv is not None:
            return

        cantidad = current["cantidad"]
        apostador_id = current["apostador_id"]
        rival_id = current["rival_id"]

        if dado_ap is not None and dado_rv is None:
            liquidacion = liquidar_apuesta_persistente(current["apuesta_id"], "ganador", apostador_id)
            if liquidacion == "error":
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    message_thread_id=thread_id,
                    text="⚠️ No pude cerrar la apuesta por un error de base de datos. Los fondos siguen reservados; no se perdió el estado."
                )
                return
            current["fondos_reservados"] = False
            active_bets.pop(bet_key, None)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                message_thread_id=thread_id,
                text=(f"⏰ Pasaron 2 minutos y @{current['rival_username']} no lanzó el dado.\n"
                      f"🏆 @{current['apostador_username']} gana el pozo de {cantidad * 2} PiPesos por abandono.")
            )
            return

        if dado_rv is not None and dado_ap is None:
            liquidacion = liquidar_apuesta_persistente(current["apuesta_id"], "ganador", rival_id)
            if liquidacion == "error":
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    message_thread_id=thread_id,
                    text="⚠️ No pude cerrar la apuesta por un error de base de datos. Los fondos siguen reservados; no se perdió el estado."
                )
                return
            current["fondos_reservados"] = False
            active_bets.pop(bet_key, None)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                message_thread_id=thread_id,
                text=(f"⏰ Pasaron 2 minutos y @{current['apostador_username']} no lanzó el dado.\n"
                      f"🏆 @{current['rival_username']} gana el pozo de {cantidad * 2} PiPesos por abandono.")
            )
            return

        # Ninguno apareció: no adjudicar culpa arbitrariamente.
        if current.get("fondos_reservados"):
            liquidacion = liquidar_apuesta_persistente(current["apuesta_id"], "cancelada")
            if liquidacion == "error":
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    message_thread_id=thread_id,
                    text="⚠️ No pude cancelar la apuesta por un error de base de datos. Los fondos siguen reservados; no se perdió el estado."
                )
                return
            current["fondos_reservados"] = False
        active_bets.pop(bet_key, None)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            message_thread_id=thread_id,
            text="⏰ Pasaron 2 minutos y ninguno lanzó el dado. La apuesta se canceló y los PiPesos fueron devueltos a ambos."
        )

    asyncio.create_task(timeout_apuesta_aceptada())

# === CANCELAR APUESTA ===
async def cancelar_apuesta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    thread_id = update.message.message_thread_id
    bet_key = _bet_key(update.effective_chat.id, thread_id)
    user = update.effective_user
    
    bet = active_bets.get(bet_key)
    if not bet:
        await update.message.reply_text("⚠️ No hay apuesta activa para cancelar en este tema.")
        return

    if bet["rival_id"] is not None:
        await update.message.reply_text(
            "⚠️ La apuesta ya fue aceptada. Usa el botón 🔄 Reiniciar apuesta antes de lanzar los dados."
        )
        return

    # 📌 Solo el creador puede cancelar
    if user.id != bet["apostador_id"]:
        await update.message.reply_text("⚠️ Solo quien creó la apuesta puede cancelarla.")
        return

    # ✅ Cancelar apuesta
    del active_bets[bet_key]
    await update.message.reply_text(
        f"❌ {user.username or user.first_name} canceló la apuesta."
    )

# === DETECTAR DADOS ===
async def detectar_dado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Procesa dados de combate en su chat/tema de origen y, si no aplica, casino."""
    msg = update.message
    if not msg or not msg.dice:
        return

    user = msg.from_user

    # Carreras de tortugas tienen prioridad en el tema Juegos.
    from handlers.casino_pvp import process_turtle_dice
    if await process_turtle_dice(update, context):
        return

    # ===== CHECK FOR ACTIVE COMBAT FIRST =====
    from handlers.battles import get_combate_activo, actualizar_combate, terminar_combate

    combate = get_combate_activo(user.id)
    if combate:
        combat_chat_id = combate.get("chat_id")
        combat_thread_id = combate.get("message_thread_id")

        # Un dado enviado en PV u otro tema no debe alterar el combate.
        if combat_chat_id is not None and (
            update.effective_chat.id != combat_chat_id
            or msg.message_thread_id != combat_thread_id
        ):
            return

        es_turno = (
            (combate['es_turno_atacante'] == 1 and combate['id_atacante'] == user.id) or
            (combate['es_turno_atacante'] == 0 and combate['id_defensor'] == user.id)
        )
        if not es_turno:
            turno_de = combate['username_atacante'] if combate['es_turno_atacante'] else combate['username_defensor']
            await context.bot.send_message(
                chat_id=combat_chat_id or update.effective_chat.id,
                message_thread_id=combat_thread_id,
                text=f"⏳ No es tu turno\nAguarda a que @{turno_de} ataque"
            )
            return

        daño = msg.dice.value
        turno_atacante_original = combate['es_turno_atacante'] == 1

        if turno_atacante_original:
            hp_atacante = combate['hp_atacante']
            hp_defensor = max(0, combate['hp_defensor'] - daño)
            atacante_nombre = combate['username_atacante']
        else:
            hp_atacante = max(0, combate['hp_atacante'] - daño)
            hp_defensor = combate['hp_defensor']
            atacante_nombre = combate['username_defensor']

        # Primero resolvemos muerte; no cambiamos turno de un combate ya terminado.
        if hp_atacante <= 0 or hp_defensor <= 0:
            if hp_atacante <= 0:
                id_ganador = combate['id_defensor']
                ganador_name = combate['username_defensor']
                perdedor_name = combate['username_atacante']
                hp_ganador = hp_defensor
            else:
                id_ganador = combate['id_atacante']
                ganador_name = combate['username_atacante']
                perdedor_name = combate['username_defensor']
                hp_ganador = hp_atacante

            # Persistir HP final y pagar exactamente una vez.
            if not actualizar_combate(
                combate['id_combate'], hp_atacante=hp_atacante, hp_defensor=hp_defensor,
                turno=combate['turno'] + 1
            ):
                await context.bot.send_message(
                    chat_id=combat_chat_id or update.effective_chat.id,
                    message_thread_id=combat_thread_id,
                    text="⚠️ No pude guardar el último turno. No se entregó el premio; intenta nuevamente."
                )
                return

            if not terminar_combate(combate['id_combate'], id_ganador):
                await context.bot.send_message(
                    chat_id=combat_chat_id or update.effective_chat.id,
                    message_thread_id=combat_thread_id,
                    text="⚠️ No pude finalizar/pagar el combate. El premio no se duplicó; revisa el registro antes de continuar."
                )
                return


            fin_msg = (
                f"🎉 **¡COMBATE FINALIZADO!**\n\n"
                f"🏆 Ganador: {ganador_name}\n"
                f"💀 Perdedor: {perdedor_name}\n\n"
                f"🎲 Último turno: {atacante_nombre} lanzó {daño} de daño\n"
                f"❤️ {ganador_name}: {hp_ganador} HP\n"
                f"💀 {perdedor_name}: 0 HP\n\n"
                f"💰 Ganador recibió {combate['apuesta'] * 2} PiPesos"
            )
            await context.bot.send_message(
                chat_id=combat_chat_id or update.effective_chat.id,
                message_thread_id=combat_thread_id,
                text=fin_msg,
                parse_mode='Markdown'
            )
            await send_victory(context,id_ganador,'lucha',combat_chat_id or update.effective_chat.id,combat_thread_id,ganador_name)
            return

        siguiente_turno_atacante = 0 if turno_atacante_original else 1
        if not actualizar_combate(
            combate['id_combate'],
            hp_atacante=hp_atacante, hp_defensor=hp_defensor,
            es_turno_atacante=siguiente_turno_atacante,
            turno=combate['turno'] + 1
        ):
            await context.bot.send_message(
                chat_id=combat_chat_id or update.effective_chat.id,
                message_thread_id=combat_thread_id,
                text="⚠️ No pude guardar este turno. Vuelve a lanzar el dado."
            )
            return

        siguiente_atacante = combate['username_defensor'] if turno_atacante_original else combate['username_atacante']
        combate_msg = (
            f"⚔️ **COMBATE EN CURSO**\n\n"
            f"{combate['username_atacante']}: ❤️ {hp_atacante}\n"
            f"{combate['username_defensor']}: ❤️ {hp_defensor}\n\n"
            f"🎲 {atacante_nombre} lanzó {daño} de daño\n\n"
            f"📊 Turno de: @{siguiente_atacante}\n"
            f"Lanza el dado 🎲 para atacar"
        )
        await context.bot.send_message(
            chat_id=combat_chat_id or update.effective_chat.id,
            message_thread_id=combat_thread_id,
            text=combate_msg,
            parse_mode='Markdown'
        )
        return

    # ===== NO ACTIVE COMBAT - CHECK FOR BETTING =====

    thread_id = msg.message_thread_id
    bet_key = _bet_key(update.effective_chat.id, thread_id)
    bet = active_bets.get(bet_key)
    if not bet:
        return  # no hay apuesta activa

    if user.id == bet["apostador_id"]:
        jugador = "apostador"
    elif user.id == bet["rival_id"]:
        jugador = "rival"
    else:
        return  # no es parte de la apuesta
    
    if bet["dados"][jugador] is not None:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Ya haz lanzado el dado, no puedes volver a lanzar",
            message_thread_id=thread_id
        )
        return
    
    valor = msg.dice.value
    guardado = registrar_dado_apuesta(bet["apuesta_id"], user.id, valor)
    if guardado == "already":
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Ya haz lanzado el dado, no puedes volver a lanzar", message_thread_id=thread_id)
        return
    if guardado == "error":
        await context.bot.send_message(chat_id=update.effective_chat.id, text="⚠️ No pude registrar el dado en la base de datos. Intenta de nuevo.", message_thread_id=thread_id)
        return
    bet["dados"][jugador] = valor

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"🎲 @{user.username or user.first_name} ha lanzado el dado y sacó {valor}",
        message_thread_id=thread_id
    )

    # Si ambos ya lanzaron, resolver una sola vez. Marcamos el estado ANTES del
    # siguiente await para que dos updates simultáneos no puedan pagar dos veces.
    if bet["dados"]["apostador"] is not None and bet["dados"]["rival"] is not None:
        if bet.get("resolviendo"):
            return
        bet["resolviendo"] = True
        bet["activa"] = False

        ap = bet["dados"]["apostador"]
        rv = bet["dados"]["rival"]
        apostador_id = bet["apostador_id"]
        rival_id = bet["rival_id"]
        cantidad = bet["cantidad"]

        if ap > rv:
            ganador = bet["apostador_username"]
            ok = liquidar_apuesta_persistente(bet["apuesta_id"], "ganador", apostador_id) != "error"
            resultado = f"🏆 *{ganador}* gana la apuesta de {cantidad} PiPesos!"
        elif rv > ap:
            ganador = bet["rival_username"]
            ok = liquidar_apuesta_persistente(bet["apuesta_id"], "ganador", rival_id) != "error"
            resultado = f"🏆 *{ganador}* gana la apuesta de {cantidad} PiPesos!"
        else:
            ok = liquidar_apuesta_persistente(bet["apuesta_id"], "empate") != "error"
            resultado = "🤝 ¡Empate! Nadie gana ni pierde. Se devolvieron ambas apuestas."

        if not ok:
            bet["resolviendo"] = False
            bet["activa"] = True
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="⚠️ No pude liquidar la apuesta por un error de base de datos. El estado se conservó para evitar perder PiPesos.",
                message_thread_id=thread_id
            )
            return

        bet["fondos_reservados"] = False
        active_bets.pop(bet_key, None)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=resultado,
            message_thread_id=thread_id
        )

async def reiniciar_apuesta_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Safely reset an accepted wager before either player has rolled."""
    query = update.callback_query
    thread_id = query.message.message_thread_id
    bet_key = _bet_key(query.message.chat_id, thread_id)
    bet = active_bets.get(bet_key)
    if not bet:
        await query.answer("La apuesta ya no está activa.", show_alert=True)
        return
    if query.from_user.id not in (bet["apostador_id"], bet.get("rival_id")):
        await query.answer("Solo los jugadores pueden reiniciar esta apuesta.", show_alert=True)
        return
    if bet.get("rival_id") is None:
        await query.answer("La apuesta todavía no ha sido aceptada.", show_alert=True)
        return
    if any(v is not None for v in bet["dados"].values()):
        await query.answer("Ya se lanzó un dado; la apuesta no puede reiniciarse.", show_alert=True)
        return
    if bet.get("fondos_reservados"):
        if liquidar_apuesta_persistente(bet["apuesta_id"], "cancelada") == "error":
            await query.answer("No se pudo devolver la apuesta. Intenta de nuevo.", show_alert=True)
            return
        bet["fondos_reservados"] = False
    del active_bets[bet_key]
    await query.answer("Apuesta reiniciada y PiPesos devueltos.")
    await query.edit_message_reply_markup(reply_markup=None)
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        message_thread_id=thread_id,
        text=(f"🔄 {query.from_user.username or query.from_user.first_name} reinició la apuesta. "
              "Los PiPesos reservados fueron devueltos a ambos jugadores.")
    )


async def _resolver_timeout_recuperado(bot, bet_key, bet, espera):
    """Resume the original 2-minute abandonment rule after a process restart."""
    if espera > 0:
        await asyncio.sleep(espera)
    current = active_bets.get(bet_key)
    if current is not bet or not current.get("activa"):
        return
    da, dr = current["dados"]["apostador"], current["dados"]["rival"]
    if da is not None and dr is not None:
        return
    if da is not None:
        result = liquidar_apuesta_persistente(current["apuesta_id"], "ganador", current["apostador_id"]); winner="apostador"
    elif dr is not None:
        result = liquidar_apuesta_persistente(current["apuesta_id"], "ganador", current["rival_id"]); winner="rival"
    else:
        result = liquidar_apuesta_persistente(current["apuesta_id"], "cancelada"); winner=None
    if result == "error":
        return
    active_bets.pop(bet_key, None)
    if winner:
        loser = "rival" if winner == "apostador" else "apostador"
        await bot.send_message(chat_id=bet_key[0], message_thread_id=bet_key[1],
            text=f"⏰ La apuesta recuperada venció: @{current[loser + '_username']} no lanzó el dado.\n🏆 @{current[winner + '_username']} gana el pozo de {current['cantidad'] * 2} PiPesos por abandono.")
    else:
        await bot.send_message(chat_id=bet_key[0], message_thread_id=bet_key[1],
            text="⏰ La apuesta recuperada venció sin dados. Los PiPesos fueron devueltos a ambos.")


async def recuperar_apuestas_al_iniciar(application):
    """Rebuild accepted wagers from PostgreSQL without touching balances."""
    rows = obtener_apuestas_reservadas()
    now = datetime.now()
    for row in rows:
        key = _bet_key(row["chat_id"], row["thread_id"] )
        if key in active_bets:
            continue
        bet = {
            "apostador_id": row["apostador_id"], "apostador_username": row["apostador_username"],
            "rival_id": row["rival_id"], "rival_username": row["rival_username"],
            "cantidad": row["cantidad"],
            "dados": {"apostador": row["dado_apostador"], "rival": row["dado_rival"]},
            "activa": True, "apuesta_id": row["apuesta_id"], "fondos_reservados": True,
        }
        active_bets[key] = bet
        da, dr = bet["dados"]["apostador"], bet["dados"]["rival"]
        if da is not None and dr is not None:
            if da > dr:
                settlement = liquidar_apuesta_persistente(bet["apuesta_id"], "ganador", bet["apostador_id"]); result=f"🏆 *{bet['apostador_username']}* gana la apuesta de {bet['cantidad']} PiPesos!"
            elif dr > da:
                settlement = liquidar_apuesta_persistente(bet["apuesta_id"], "ganador", bet["rival_id"]); result=f"🏆 *{bet['rival_username']}* gana la apuesta de {bet['cantidad']} PiPesos!"
            else:
                settlement = liquidar_apuesta_persistente(bet["apuesta_id"], "empate"); result="🤝 ¡Empate! Se devolvieron ambas apuestas."
            if settlement == "error":
                print(f"[CASINO RECOVERY] No se pudo liquidar {bet['apuesta_id']}; queda reservada para reintento seguro.")
                continue
            active_bets.pop(key, None)
            try:
                await application.bot.send_message(chat_id=key[0], message_thread_id=key[1], text="🔄 PiBot recuperó una apuesta pendiente tras reiniciarse.\n" + result, parse_mode="Markdown")
            except Exception as e:
                print(f"[CASINO RECOVERY] Settlement notification failed: {e}")
            continue
        created = row["fecha_creacion"]
        # PostgreSQL devuelve timestamptz aware; usa el mismo tz para evitar estados fantasma.
        current_now = datetime.now(created.tzinfo) if created is not None and getattr(created, "tzinfo", None) else datetime.now()
        elapsed = max(0.0, (current_now - created).total_seconds()) if created else 120.0
        remaining = max(0.0, 120.0 - elapsed)
        if remaining <= 0.0:
            # Una reserva vencida se resuelve durante el arranque, antes de aceptar comandos.
            await _resolver_timeout_recuperado(application.bot, key, bet, 0)
        else:
            asyncio.create_task(_resolver_timeout_recuperado(application.bot, key, bet, remaining))
    if rows:
        print(f"[CASINO RECOVERY] {len(rows)} apuesta(s) reservada(s) revisadas al iniciar.")

async def jugar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    CHAT_IDS = obtener_temas_por_comunidad(update.effective_chat.id)
    if not CHAT_IDS:
        await update.message.reply_text("⚠️ Este comando no está habilitado en este grupo.")
        return

    thread_id = update.message.message_thread_id
    user = update.effective_user
    user_id = user.id
    
    tmp_user_username = user.username
    tmp_user_nombre = normalizar_nombre(user.first_name,user.last_name)
    resumen = get_usuario_resumen(user_id)
    sql_user_username = resumen["username"] if resumen else None
    sql_user_nombre = resumen["nombre"] if resumen else None

    if resumen is None:
        insert_user(user_id,0,tmp_user_username,tmp_user_nombre)

    if tmp_user_nombre != sql_user_nombre or tmp_user_username != sql_user_username:
        update_perfil(user_id,username=tmp_user_username,nombre=tmp_user_nombre)

    sql_user_username = tmp_user_username
    sql_user_nombre = tmp_user_nombre

    if thread_id != CHAT_IDS["theme_juegosYcasino"]:
        await update.message.reply_text("⚠️ Este comando solo está permitido en el tema Juegos y Casino.")
        return

    hoy = datetime.now().strftime("%Y-%m-%d")
    uso_numero = consumir_uso_diario(user_id, "jugar", hoy, 5)
    if uso_numero is None:
        await update.message.reply_text(
            "⚠️ Ya has jugado 5 veces hoy. Inténtalo de nuevo mañana.",
            message_thread_id=thread_id
        )
        return

    dice_message = await context.bot.send_dice(
        chat_id=update.effective_chat.id,
        emoji="🎲",
        message_thread_id=thread_id
    )
    valor = dice_message.dice.value
    if valor == 6 or valor == 1:
        if dar_recompensa(user_id, 1000):
            resultado = f"🎉 ¡Ganaste! sacaste {valor} 🎲\n💰 Se te acreditaron 1,000 PiPesos."
        else:
            resultado = f"🎲 Sacaste {valor}, pero la base de datos no confirmó el premio. No se anunciará un abono inexistente."
    else:
        resultado = f"😔 Sacaste {valor}, perdiste."

    nuevo_saldo = get_campo_usuario(user_id,"saldo")

    await update.message.reply_text(
        f"{resultado}\nSaldo actual: {nuevo_saldo} PiPesos\n"
        f"🔄 Veces jugadas hoy: {uso_numero}/5",
        message_thread_id=thread_id
    )

async def robar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /robar @Usuario - Solo válido con @Usuario, no con reply."""
    CHAT_IDS = obtener_temas_por_comunidad(update.effective_chat.id)
    
    try:
        thread_id = update.message.message_thread_id
    except ArithmeticError or TypeError as e:
        hora = datetime.now().time()
        print(f"No ha sido posible identificar el tema, {e}\nError a las: {hora.hour}:{hora.minute}")
        del hora
        return
    
    robber_user = update.effective_user
    robbed_user = None
    resumen_robber = get_usuario_resumen(robber_user.id)
    sql_robber_username = resumen_robber["username"] if resumen_robber else None
    tmp_robber_username = robber_user.username
    sql_robber_nombre = resumen_robber["nombre"] if resumen_robber else None
    tmp_robber_nombre = normalizar_nombre(robber_user.first_name,robber_user.last_name)
    
    if resumen_robber is None:
        insert_user(robber_user.id,0,tmp_robber_username,tmp_robber_nombre)
        sql_robber_nombre = tmp_robber_nombre
        sql_robber_username = tmp_robber_username

    if tmp_robber_username != sql_robber_username or tmp_robber_nombre != sql_robber_nombre:
        update_perfil(robber_user.id,username=tmp_robber_username,nombre=tmp_robber_nombre)
        sql_robber_nombre = tmp_robber_nombre
        sql_robber_username = tmp_robber_username
    
    # 1) Solo en el tema Juegos y Casino
    if thread_id != CHAT_IDS["theme_juegosYcasino"]:
        await update.message.reply_text("⚠️ Este comando solo se puede usar en el tema Juegos y Casino.")
        return
    
    robbed_user = await get_receptor(update,context,1)
    
    if robbed_user is None or robbed_user is False:
        await update.message.reply_text("⚠️ No ha sido posible encontrar al usuario.")
        return    
    
    robber_id = robber_user.id
    robbed_id = robbed_user.id
    robbed_username = robbed_user.username
    
    # 4) Control de uso diario persistente y atómico
    hoy_robo = datetime.now().strftime("%Y-%m-%d")
    uso_robo = consumir_uso_diario(robber_id, "robar", hoy_robo, 3)
    if uso_robo is None:
        await update.message.reply_text("⚠️ Solo puedes usar /robar 3 veces al día.")
        return

    # Luck-based probability: suerte 3 → 2/3, suerte 2 → 1/3, suerte 1 → 0/3
    nivel_suerte = get_suerte(robber_id)
    if nivel_suerte == 3:
        opciones = [True, True, False]
    elif nivel_suerte == 1:
        opciones = [False, False, False]
    else:
        opciones = [True, False, False]
    exito = random.choice(opciones)

    if exito:
        intento_robo = random.randint(1,10000)
        cantidad_robada = transferir_robo_atomico(robber_id, robbed_id, intento_robo)
        if cantidad_robada is None:
            await update.message.reply_text("⚠️ No se pudo completar el robo por un problema temporal. No se movieron PiPesos.")
            return
        await update.message.reply_text(f"🎉 {sql_robber_username} logró robar a {robbed_username} exitosamente {cantidad_robada} PiPesos")
    else:
        await update.message.reply_text(f"💨 {sql_robber_username} intentó robar a {robbed_username}, pero falló.")
