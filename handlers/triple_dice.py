"""Mini juego Triple para el tema Juegos y Casino.

Flujo actual (ligero y pensado para Telegram):
1) /triple <apuesta>
2) PiBot muestra botones 1-6.
3) El jugador toca un número.
4) PiBot lanza automáticamente el dado nativo 🎲 de Telegram.
5) Si coincide, paga x3; si no, la apuesta se pierde.

No usa jobs, timers ni escaneo constante de mensajes. PostgreSQL solo se toca
cuando alguien abre/juega/cancela una ronda. Se conserva compatibilidad con
apuestas pendientes creadas por la versión anterior, donde el usuario lanzaba
el dado manualmente.
"""
from __future__ import annotations

import secrets

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.config import obtener_temas_por_comunidad
from src.database.database import _get_connection, _put_connection

MIN_STAKE = 100
SESSION_MINUTES = 10


def ensure_triple_dice_tables() -> None:
    conn = _get_connection()
    try:
        c = conn.cursor()
        # Tabla antigua: se conserva para no romper apuestas que pudieran haber
        # quedado pendientes antes de actualizar PiBot.
        c.execute(
            """CREATE TABLE IF NOT EXISTS triple_dice_bets_tb(
                user_id BIGINT PRIMARY KEY REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                chat_id BIGINT NOT NULL,
                thread_id BIGINT,
                chosen_number SMALLINT NOT NULL CHECK(chosen_number BETWEEN 1 AND 6),
                stake BIGINT NOT NULL CHECK(stake > 0),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""
        )
        # Sesión de la nueva interfaz. No aparta saldo hasta que el usuario toca
        # un número. El token impide que un botón viejo pueda jugar otra ronda.
        c.execute(
            """CREATE TABLE IF NOT EXISTS triple_dice_ui_tb(
                token TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                chat_id BIGINT NOT NULL,
                thread_id BIGINT,
                stake BIGINT NOT NULL CHECK(stake > 0),
                chosen_number SMALLINT CHECK(chosen_number BETWEEN 1 AND 6),
                status TEXT NOT NULL DEFAULT 'open',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                resolved_at TIMESTAMPTZ
            )"""
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_triple_ui_user ON triple_dice_ui_tb(user_id, created_at DESC)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_connection(conn)


def _location(update: Update) -> tuple[int | None, int | None]:
    msg = update.effective_message
    return (
        update.effective_chat.id if update.effective_chat else None,
        msg.message_thread_id if msg else None,
    )


def _in_games_topic(update: Update) -> bool:
    if not update.effective_chat or update.effective_chat.type == "private":
        return False
    msg = update.effective_message
    if not msg:
        return False
    try:
        themes = obtener_temas_por_comunidad(update.effective_chat.id)
        return msg.message_thread_id == themes.get("theme_juegosYcasino")
    except Exception:
        return False


def _number_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("1️⃣", callback_data=f"tri:n:{token}:1"),
                InlineKeyboardButton("2️⃣", callback_data=f"tri:n:{token}:2"),
                InlineKeyboardButton("3️⃣", callback_data=f"tri:n:{token}:3"),
            ],
            [
                InlineKeyboardButton("4️⃣", callback_data=f"tri:n:{token}:4"),
                InlineKeyboardButton("5️⃣", callback_data=f"tri:n:{token}:5"),
                InlineKeyboardButton("6️⃣", callback_data=f"tri:n:{token}:6"),
            ],
            [InlineKeyboardButton("❌ Cancelar", callback_data=f"tri:c:{token}")],
        ]
    )


def _again_keyboard(user_id: int, stake: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"🎲 Jugar otra vez · {stake:,}", callback_data=f"tri:a:{user_id}:{stake}")]]
    )


def _can_start_other_games(update: Update, user_id: int) -> str | None:
    """Devuelve un mensaje de bloqueo si otro dado/combate tiene prioridad."""
    chat_id, thread_id = _location(update)
    try:
        from handlers.theme_juegosYcasino import active_bets, _bet_key
        if active_bets.get(_bet_key(chat_id, thread_id)):
            return "⚠️ Hay una apuesta de dados PvP activa en este tema. Termínala antes de jugar Triple."
    except Exception:
        pass

    try:
        from handlers.battles import get_combate_activo
        if get_combate_activo(user_id):
            return "⚔️ Primero termina tu combate activo; ese dado tiene prioridad en la lucha."
    except Exception:
        pass
    return None


def _create_ui_session(user_id: int, chat_id: int, thread_id: int | None, stake: int) -> str:
    token = secrets.token_urlsafe(6)
    conn = _get_connection()
    try:
        c = conn.cursor()
        # Una sola selección abierta por usuario. Las rondas cerradas se limpian
        # de forma oportunista; no hace falta ningún job en segundo plano.
        c.execute("DELETE FROM triple_dice_ui_tb WHERE user_id=%s AND status='open'", (user_id,))
        c.execute("DELETE FROM triple_dice_ui_tb WHERE created_at < NOW() - INTERVAL '2 days'")
        c.execute(
            """INSERT INTO triple_dice_ui_tb(token,user_id,chat_id,thread_id,stake,status)
               VALUES(%s,%s,%s,%s,%s,'open')""",
            (token, user_id, chat_id, thread_id, stake),
        )
        conn.commit()
        return token
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_connection(conn)


async def _show_number_picker(update: Update, context: ContextTypes.DEFAULT_TYPE, stake: int, *, edit: bool = False) -> None:
    user = update.effective_user
    chat_id, thread_id = _location(update)
    if not user or chat_id is None:
        return

    block = _can_start_other_games(update, user.id)
    if block:
        if update.callback_query:
            await update.callback_query.answer(block, show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text(block)
        return

    try:
        token = _create_ui_session(user.id, chat_id, thread_id, stake)
    except Exception as exc:
        print(f"[TRIPLE UI CREATE] {type(exc).__name__}: {exc}")
        if update.callback_query:
            await update.callback_query.answer("⚠️ No pude abrir la ronda.", show_alert=True)
        elif update.effective_message:
            await update.effective_message.reply_text("⚠️ No pude abrir la ronda Triple.")
        return

    text = (
        "🎲 TRIPLE · ELIGE TU NÚMERO\n\n"
        f"💰 Apuesta: {stake:,} PiPesos\n"
        "🎯 Toca el número que crees que saldrá.\n\n"
        "PiBot lanzará el dado automáticamente.\n"
        f"✅ Si aciertas: recibes {stake * 3:,} PiPesos.\n"
        "❌ Si fallas: pierdes tu apuesta."
    )
    keyboard = _number_keyboard(token)
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=keyboard)


async def triple(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/triple <apuesta> — luego el usuario elige 1-6 con botones."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    if not _in_games_topic(update):
        return await msg.reply_text("🎲 /triple solo se juega en el tema Juegos y Casino.")

    # Compatibilidad amable con el formato viejo /triple <numero> <apuesta>:
    # ya no obliga a usar ese número; muestra la nueva interfaz.
    if len(context.args) == 2:
        raw_stake = context.args[1]
    elif len(context.args) == 1:
        raw_stake = context.args[0]
    else:
        return await msg.reply_text(
            "🎲 TRIPLE\n\n"
            "Solo escribe cuánto quieres apostar:\n"
            "`/triple 3000`\n\n"
            "Después PiBot te mostrará los botones 1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣ 6️⃣ y lanzará el dado por ti.",
            parse_mode="Markdown",
        )

    try:
        stake = int(str(raw_stake).replace(",", "").replace(".", ""))
    except ValueError:
        return await msg.reply_text("⚠️ Escribe solo la apuesta. Ejemplo: /triple 3000")

    if stake < MIN_STAKE:
        return await msg.reply_text(f"💰 La apuesta mínima es de {MIN_STAKE:,} PiPesos.")

    await _show_number_picker(update, context, stake)


async def triple_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    user = update.effective_user
    if not q or not user or not q.data:
        return

    parts = q.data.split(":")
    if len(parts) < 3 or parts[0] != "tri":
        return

    action = parts[1]

    # Volver a jugar con la misma apuesta desde el resultado anterior.
    if action == "a" and len(parts) == 4:
        try:
            owner_id = int(parts[2])
            stake = int(parts[3])
        except ValueError:
            return await q.answer("Ronda inválida.", show_alert=True)
        if user.id != owner_id:
            return await q.answer("Ese botón pertenece a otro jugador 😏", show_alert=True)
        if not _in_games_topic(update):
            return await q.answer("Triple solo se juega en Juegos y Casino.", show_alert=True)
        await q.answer()
        return await _show_number_picker(update, context, stake, edit=True)

    if action not in {"n", "c"}:
        return

    token = parts[2]

    # Cancelar una selección abierta: todavía no había saldo apartado.
    if action == "c":
        conn = _get_connection()
        try:
            c = conn.cursor()
            c.execute(
                """UPDATE triple_dice_ui_tb
                   SET status='cancelled', resolved_at=NOW()
                   WHERE token=%s AND user_id=%s AND status='open'
                   RETURNING stake""",
                (token, user.id),
            )
            row = c.fetchone()
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"[TRIPLE UI CANCEL] {type(exc).__name__}: {exc}")
            return await q.answer("⚠️ No pude cancelar la ronda.", show_alert=True)
        finally:
            _put_connection(conn)

        if not row:
            return await q.answer("Esta ronda ya terminó o no es tuya.", show_alert=True)
        await q.answer("Ronda cancelada")
        return await q.edit_message_text("❌ Triple cancelado. No se descontaron PiPesos.")

    if len(parts) != 4:
        return await q.answer("Ronda inválida.", show_alert=True)
    try:
        chosen = int(parts[3])
    except ValueError:
        return await q.answer("Número inválido.", show_alert=True)
    if chosen < 1 or chosen > 6:
        return await q.answer("Número inválido.", show_alert=True)

    if not _in_games_topic(update):
        return await q.answer("Triple solo se juega en Juegos y Casino.", show_alert=True)

    block = _can_start_other_games(update, user.id)
    if block:
        return await q.answer(block, show_alert=True)

    chat_id, thread_id = _location(update)

    # Reclama la sesión y aparta el saldo en una sola transacción. Esto evita
    # dobles clics y que dos callbacks cobren la misma ronda.
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """SELECT user_id,chat_id,thread_id,stake,status,created_at
               FROM triple_dice_ui_tb WHERE token=%s FOR UPDATE""",
            (token,),
        )
        row = c.fetchone()
        if not row:
            conn.rollback()
            return await q.answer("Esta ronda ya no existe.", show_alert=True)

        owner_id, bet_chat, bet_thread, stake, status, _created_at = row
        owner_id, bet_chat, stake = int(owner_id), int(bet_chat), int(stake)
        if owner_id != user.id:
            conn.rollback()
            return await q.answer("Ese botón pertenece a otro jugador 😏", show_alert=True)
        if bet_chat != chat_id or bet_thread != thread_id:
            conn.rollback()
            return await q.answer("Esa ronda pertenece a otro tema.", show_alert=True)
        if status != "open":
            conn.rollback()
            return await q.answer("Ese dado ya fue jugado.", show_alert=True)

        c.execute(
            """UPDATE triple_dice_ui_tb
               SET status='rolling', chosen_number=%s
               WHERE token=%s AND status='open'""",
            (chosen, token),
        )
        if c.rowcount != 1:
            conn.rollback()
            return await q.answer("Ese dado ya fue jugado.", show_alert=True)

        c.execute(
            "UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo >= %s RETURNING saldo",
            (stake, user.id, stake),
        )
        balance_row = c.fetchone()
        if not balance_row:
            conn.rollback()
            return await q.answer("💸 Ya no tienes suficientes PiPesos para esa apuesta.", show_alert=True)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"[TRIPLE UI CLAIM] {type(exc).__name__}: {exc}")
        return await q.answer("⚠️ No pude iniciar el lanzamiento.", show_alert=True)
    finally:
        _put_connection(conn)

    await q.answer(f"Elegiste {chosen} 🎲")
    try:
        await q.edit_message_text(
            f"🎲 TRIPLE\n\n🎯 Elegiste: {chosen}\n💰 Apuesta: {stake:,} PiPesos\n\nPiBot está lanzando el dado..."
        )
    except Exception:
        pass

    # El dado es el nativo de Telegram; Telegram genera el resultado.
    try:
        dice_msg = await context.bot.send_dice(
            chat_id=chat_id,
            emoji="🎲",
            message_thread_id=thread_id,
        )
        rolled = int(dice_msg.dice.value)
    except Exception as exc:
        print(f"[TRIPLE AUTO DICE] {type(exc).__name__}: {exc}")
        # Si Telegram no pudo lanzar el dado, devolvemos la apuesta.
        conn = _get_connection()
        try:
            c = conn.cursor()
            c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s", (stake, user.id))
            c.execute(
                "UPDATE triple_dice_ui_tb SET status='cancelled', resolved_at=NOW() WHERE token=%s",
                (token,),
            )
            conn.commit()
        except Exception:
            conn.rollback()
        finally:
            _put_connection(conn)
        return await context.bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id,
            text="⚠️ Telegram no pudo lanzar el dado. Te devolví la apuesta.",
        )

    conn = _get_connection()
    try:
        c = conn.cursor()
        if rolled == chosen:
            payout = stake * 3
            c.execute(
                "UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s RETURNING saldo",
                (payout, user.id),
            )
            balance = int((c.fetchone() or (0,))[0])
        else:
            payout = 0
            c.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s", (user.id,))
            balance = int((c.fetchone() or (0,))[0])
        c.execute(
            "UPDATE triple_dice_ui_tb SET status='done', resolved_at=NOW() WHERE token=%s",
            (token,),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"[TRIPLE UI RESOLVE] {type(exc).__name__}: {exc}")
        # La apuesta ya quedó apartada y el dado ya salió. No volvemos a tirar.
        return await context.bot.send_message(
            chat_id=chat_id,
            message_thread_id=thread_id,
            text="⚠️ El dado salió, pero no pude cerrar la jugada. Avísale a un admin antes de volver a jugar.",
        )
    finally:
        _put_connection(conn)

    if rolled == chosen:
        text = (
            f"🎲 Cayó {rolled}. ¡LE DISTE!\n\n"
            f"🎯 Elegiste: {chosen}\n"
            f"💰 Premio: {payout:,} PiPesos (x3)\n"
            f"📈 Ganancia real: +{stake * 2:,}\n"
            f"💳 Saldo: {balance:,} PiPesos"
        )
    else:
        text = (
            f"🎲 Cayó {rolled}. Tú elegiste {chosen}.\n\n"
            f"💸 Perdiste {stake:,} PiPesos.\n"
            f"💳 Saldo: {balance:,} PiPesos"
        )

    await context.bot.send_message(
        chat_id=chat_id,
        message_thread_id=thread_id,
        text=text,
        reply_markup=_again_keyboard(user.id, stake),
    )


async def cancelar_triple(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Compatibilidad: cancela apuestas pendientes de la versión manual anterior."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user:
        return

    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT stake FROM triple_dice_bets_tb WHERE user_id=%s FOR UPDATE", (user.id,))
        row = c.fetchone()
        if not row:
            conn.rollback()
            return await msg.reply_text(
                "🎲 No tienes una apuesta Triple antigua pendiente.\n"
                "En la interfaz nueva usa el botón ❌ Cancelar antes de elegir número."
            )
        stake = int(row[0])
        c.execute("DELETE FROM triple_dice_bets_tb WHERE user_id=%s", (user.id,))
        c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s", (stake, user.id))
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"[TRIPLE CANCEL] {type(exc).__name__}: {exc}")
        return await msg.reply_text("⚠️ No pude cancelar la apuesta; quedó intacta para no perder tus PiPesos.")
    finally:
        _put_connection(conn)

    await msg.reply_text(f"↩️ Triple cancelado. Te devolví {stake:,} PiPesos.")


async def process_triple_dice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Compatibilidad con apuestas manuales creadas por la versión anterior."""
    msg = update.effective_message
    user = update.effective_user
    if not msg or not user or not msg.dice or msg.dice.emoji != "🎲":
        return False

    chat_id, thread_id = _location(update)
    conn = _get_connection()
    consumed = False
    try:
        c = conn.cursor()
        c.execute(
            """SELECT chat_id,thread_id,chosen_number,stake
               FROM triple_dice_bets_tb WHERE user_id=%s FOR UPDATE""",
            (user.id,),
        )
        row = c.fetchone()
        if not row:
            conn.rollback()
            return False

        bet_chat, bet_thread, chosen, stake = int(row[0]), row[1], int(row[2]), int(row[3])
        if bet_chat != chat_id or bet_thread != thread_id:
            conn.rollback()
            return False

        consumed = True
        rolled = int(msg.dice.value)
        c.execute("DELETE FROM triple_dice_bets_tb WHERE user_id=%s", (user.id,))

        if rolled == chosen:
            payout = stake * 3
            c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s RETURNING saldo", (payout, user.id))
            balance = int((c.fetchone() or (0,))[0])
            conn.commit()
            await msg.reply_text(
                f"🎲 Cayó {rolled}. ¡LE DISTE!\n\n"
                f"💰 Premio: {payout:,} PiPesos (x3)\n"
                f"💳 Saldo: {balance:,} PiPesos"
            )
        else:
            c.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s", (user.id,))
            balance = int((c.fetchone() or (0,))[0])
            conn.commit()
            await msg.reply_text(
                f"🎲 Cayó {rolled}. Tú habías elegido {chosen}.\n\n"
                f"💸 Perdiste {stake:,} PiPesos.\n"
                f"💳 Saldo: {balance:,} PiPesos"
            )
        return True
    except Exception as exc:
        conn.rollback()
        print(f"[TRIPLE DICE LEGACY] {type(exc).__name__}: {exc}")
        if consumed:
            await msg.reply_text("⚠️ No pude resolver el Triple antiguo. La apuesta sigue guardada.")
            return True
        return False
    finally:
        _put_connection(conn)
