from telegram import Update
from telegram.ext import ContextTypes
from src.utils.seasonal import current_season, seasonalize
from src.database.database import get_id_user, _get_connection, _put_connection

MAIN_CHAT_ID = -1003290179217
TARGET_THREADS = (435, 335263, 528)  # General, Eventos, Juegos

def _display(user):
    return ("@" + user.username) if getattr(user, "username", None) else getattr(user, "full_name", str(user))

def _known_display(uid:int, fallback:str):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT username,nombre FROM perfiles_tb WHERE id_user=%s",(uid,)); r=c.fetchone()
        if r:
            return ("@"+r[0]) if r[0] else (r[1] or fallback)
    except Exception:
        pass
    finally:_put_connection(conn)
    return fallback

async def caza(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Publish a bounty announcement. Never reserves/transfers the announced reward."""
    if update.effective_chat.id != MAIN_CHAT_ID:
        return await update.effective_message.reply_text("Este anuncio de caza solo está disponible en la comunidad principal.")
    msg=update.effective_message; args=list(context.args or []); target_name=None; amount_raw=None

    if msg.reply_to_message and msg.reply_to_message.from_user:
        target_name=_display(msg.reply_to_message.from_user)
        amount_raw=args[0] if args else None
    else:
        # Supported syntax: /caza @usuario cantidad. Keep quantity mandatory.
        if len(args)>=2 and args[0].startswith('@'):
            username=args[0][1:]
            uid=get_id_user(username)
            if uid is None:
                return await msg.reply_text(seasonalize(f"🎯 No encontré a @{username} entre los usuarios registrados por PiBot.",compact=True))
            target_name=_known_display(int(uid), '@'+username)
            amount_raw=args[1]
        else:
            # text_mention remains supported when Telegram provides the User entity.
            if msg.entities:
                for ent in msg.entities:
                    if ent.type=='text_mention' and ent.user:
                        target_name=_display(ent.user); break
            if target_name and args:
                amount_raw=args[-1]

    try:
        amount=int(str(amount_raw).replace(',','').replace('_',''))
        if amount<=0: raise ValueError
    except Exception:
        return await msg.reply_text(seasonalize("🎯 Uso: /caza @usuario cantidad\nTambién puedes responder al mensaje de alguien con /caza cantidad.\n\nEsto solo publica la recompensa; PiBot no aparta ni entrega ese dinero.",compact=True))
    if not target_name:
        return await msg.reply_text(seasonalize("🎯 No pude identificar a la persona. Usa /caza @usuario cantidad o responde su mensaje con /caza cantidad.",compact=True))

    hunter=_display(update.effective_user); season=current_season()
    headers={"halloween":"🎃🦇 CAZA DE HALLOWEEN 🦇🎃","dia_muertos":"💀🌼 CARTEL DE CAZA DEL MICTLÁN 🌼💀","navidad":"🎄🔔 RECOMPENSA NAVIDEÑA 🔔🎄","san_valentin":"💘🌹 CAZA DE CORAZONES 🌹💘","normal":"🎯 CARTEL DE CAZA 🎯"}
    text=(f"{headers[season]}\n\n👤 Objetivo: {target_name}\n💰 Recompensa anunciada: {amount:,} PiPesos\n📜 {hunter} promete entregar esa cantidad a quien consiga un /robar exitoso contra el objetivo.\n\n⚠️ PiBot solo publica el anuncio: no cobra, reserva ni entrega la recompensa. El pago queda bajo responsabilidad de quien abrió la caza.")
    sent=0
    for thread in TARGET_THREADS:
        try:
            await context.bot.send_message(chat_id=MAIN_CHAT_ID,message_thread_id=thread,text=text); sent+=1
        except Exception as exc: print(f"[CAZA] No pude publicar en thread {thread}: {exc}")
    await msg.reply_text(seasonalize(f"🎯 Caza publicada en {sent}/3 secciones: General, Eventos y Juegos.",compact=True))
