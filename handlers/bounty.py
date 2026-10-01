from telegram import Update
from telegram.ext import ContextTypes
from src.config.settings import COMUNIDADES
from src.utils.seasonal import current_season, seasonalize

MAIN_CHAT_ID = -1003290179217
TARGET_THREADS = (435, 335263, 528)  # General, Eventos, Juegos

def _display(user):
    return ("@" + user.username) if user.username else user.full_name

async def caza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Publish a bounty announcement. This command NEVER reserves, transfers or awards money."""
    if update.effective_chat.id != MAIN_CHAT_ID:
        return await update.effective_message.reply_text("Este anuncio de caza solo está disponible en la comunidad principal.")
    msg=update.effective_message
    target=None
    amount=None
    if msg.reply_to_message and msg.reply_to_message.from_user:
        target=msg.reply_to_message.from_user
        raw=context.args[0] if context.args else ""
    else:
        raw=context.args[-1] if context.args else ""
        # Telegram mention entity gives a real User only for text_mention; @username cannot be resolved safely by Bot API.
        if msg.entities:
            for ent in msg.entities:
                if ent.type=="text_mention" and ent.user:
                    target=ent.user; break
        # Fallback: preserve typed @username purely as announcement text.
        if not target and context.args and context.args[0].startswith("@"):
            target=context.args[0]
    try:
        amount=int(str(raw).replace(",","").replace("_",""))
        if amount <= 0: raise ValueError
    except Exception:
        return await msg.reply_text(seasonalize("🎯 Uso: /caza @usuario cantidad\nTambién puedes responder al mensaje de alguien con /caza cantidad.\n\nEsto solo publica la recompensa; PiBot no aparta ni entrega ese dinero.",compact=True))
    hunter=_display(update.effective_user)
    target_name=target if isinstance(target,str) else _display(target)
    if not target_name:
        return await msg.reply_text(seasonalize("🎯 No pude identificar a la persona. Usa @usuario o responde directamente a uno de sus mensajes.",compact=True))
    season=current_season()
    headers={
      "halloween":"🎃🦇 CAZA DE HALLOWEEN 🦇🎃",
      "dia_muertos":"💀🌼 CARTEL DE CAZA DEL MICTLÁN 🌼💀",
      "navidad":"🎄🔔 RECOMPENSA NAVIDEÑA 🔔🎄",
      "san_valentin":"💘🌹 CAZA DE CORAZONES 🌹💘",
      "normal":"🎯 CARTEL DE CAZA 🎯",
    }
    text=(f"{headers[season]}\n\n"
          f"👤 Objetivo: {target_name}\n"
          f"💰 Recompensa anunciada: {amount:,} PiPesos\n"
          f"📜 {hunter} promete entregar esa cantidad a quien consiga un /robar exitoso contra el objetivo.\n\n"
          "⚠️ PiBot solo publica el anuncio: no cobra, reserva ni entrega la recompensa. "
          "El pago queda bajo responsabilidad de quien abrió la caza.")
    # publish independently in all three configured destinations
    sent=0
    for thread in TARGET_THREADS:
        try:
            await context.bot.send_message(chat_id=MAIN_CHAT_ID,message_thread_id=thread,text=text)
            sent+=1
        except Exception as exc:
            print(f"[CAZA] No pude publicar en thread {thread}: {exc}")
    await msg.reply_text(seasonalize(f"🎯 Caza publicada en {sent}/3 secciones: General, Eventos y Juegos.",compact=True))
