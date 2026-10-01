# handlers/rewards.py
import asyncio
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from src.config import obtener_temas_por_comunidad
from src.database.database import normalizar_nombre,get_campo_usuario,insert_user,dar_puntos
from handlers.presentation_watchdog import mark_presented

contador_imagenes_multimedia = {}
contador_imagenes_nsfw = {}
contador_imagenes_exhibicion = {}
contador_imagenes_presentacion = []
reset_tasks_multimedia = {}
reset_tasks_nsfw = {}
reset_tasks_exhibicion = {}

async def manejar_imagenes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message == None:
        return
    group_id = update.effective_chat.id
    CHAT_IDS = obtener_temas_por_comunidad(group_id)
    if not CHAT_IDS:
        return
    thread_id = update.message.message_thread_id

    if thread_id == CHAT_IDS.get("theme_multimedia"):
        await detectar_imagenes_multimedia(update, context)
        return
    if group_id != -1003290179217: 
        if thread_id == CHAT_IDS.get("theme_presentaciones"):
            await detectar_imagen_presentacion(update, context)
            return
    else:
        if thread_id == None:
            await detectar_imagen_presentacion(update, context)
            return
    if thread_id == CHAT_IDS.get("theme_NSFW"):
        await detectar_imagenes_nsfw(update,context)
        return
    if thread_id == CHAT_IDS.get("theme_Exhibicionismo"):
        await detectar_exhibicion(update,context)
        return
    
async def detectar_imagen_presentacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return

    # DEBUG: mostrar atributos del mensaje
    thread_id = getattr(msg, "message_thread_id", None)

    # 2) Detectar si el mensaje contiene imagen (photo) o archivo de imagen (document)
    tiene_photo = bool(msg.photo)
    tiene_document_image = False
    if msg.document and getattr(msg.document, "mime_type", ""):
        if msg.document.mime_type.startswith("image/"):
            tiene_document_image = True

    if not (tiene_photo or tiene_document_image):
        return

    # 4) Cargar usuarios con la función del general
    user = msg.from_user
    user_id = user.id
    username = user.username

    # Existing presentation flow doubles as the persistent 30-minute watchdog proof.
    mark_presented(update.effective_chat.id, user_id)
    nombre = normalizar_nombre(user.first_name,user.last_name)

    # comprobar campo personalizado 'primera_imagen_presentacion'
    if user_id in contador_imagenes_presentacion:
        return

    if get_campo_usuario(user_id,"id_user") is None:
        insert_user(user_id,0,username,nombre)
    
    if not dar_puntos(user_id, 5):
        print(f"[REWARDS] No se pudo acreditar presentación a {user_id}; podrá volver a intentarse.")
        return
    contador_imagenes_presentacion.append(user_id)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"📸 {username or nombre}, gracias por presentarte con imagen 😁 como recompensa, te hemos otorgado tus primeros 5 pipesos 🌟 \n Puedes ganar más participando activamente en la comunidad, recuerda leer las reglas y pasarla bien con el resto de gente 🥰",
        message_thread_id=thread_id
    )

async def detectar_imagenes_multimedia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detecta imágenes en el tema multimedia y recompensa al usuario cada 3 enviadas."""
    mensaje = update.message

    if not mensaje:
        return

    tiene_foto = bool(mensaje.photo)
    tiene_video = bool(mensaje.video)
    tiene_gif = bool(mensaje.animation)

    if not (tiene_foto or tiene_video or tiene_gif):
        return

    thread_id = mensaje.message_thread_id
    user = mensaje.from_user

    user_id = user.id
    username = user.username
    nombre = normalizar_nombre(user.first_name,user.last_name)

    # Inicializar contador
    if user_id not in contador_imagenes_multimedia:
        contador_imagenes_multimedia[user_id] = 0

    # Incrementar contador de imágenes consecutivas
    contador_imagenes_multimedia[user_id] += 1

    # Recompensa cada 3 imágenes
    if contador_imagenes_multimedia[user_id] >= 3:
        if get_campo_usuario(user_id,"id_user") is None:
            insert_user(user_id,0,username,nombre)
        # Solo consumir el bloque y anunciar si el abono realmente se confirmó.
        if dar_puntos(user_id,10):
            contador_imagenes_multimedia[user_id] = 0
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"🎉 @{username or nombre} ha sido recompensado con 10 PiPesos por su actividad en multimedia 📸",
                message_thread_id=thread_id
            )

    # Reiniciar 2 minutos después de la ÚLTIMA publicación, no de la primera.
    old_task = reset_tasks_multimedia.get(user_id)
    if old_task and not old_task.done():
        old_task.cancel()
    async def resetear_contador(uid):
        try:
            await asyncio.sleep(120)
            contador_imagenes_multimedia[uid] = 0
        except asyncio.CancelledError:
            pass
    reset_tasks_multimedia[user_id] = asyncio.create_task(resetear_contador(user_id))

async def detectar_imagenes_nsfw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detecta archivos multimedia en NSFW y recompensa 1,000 PiPesos por cada bloque de 5."""
    mensaje = update.message

    if not mensaje:
        return

    tiene_foto = bool(mensaje.photo)
    tiene_video = bool(mensaje.video)
    tiene_gif = bool(mensaje.animation)

    if not(tiene_foto or tiene_video or tiene_gif):
        return
    
    thread_id = mensaje.message_thread_id
    user = mensaje.from_user

    # ✅ Solo se ejecuta en el tema NSFW

    user_id = user.id
    username = user.username
    nombre = normalizar_nombre(user.first_name,user.last_name)

    # Inicializar contador si no existe
    if user_id not in contador_imagenes_nsfw:
        contador_imagenes_nsfw[user_id] = 0

    # Incrementar contador de imágenes consecutivas
    contador_imagenes_nsfw[user_id] += 1

    # Recompensa acumulable: 1,000 PiPesos por CADA bloque completo de 5 archivos.
    # Se conserva cualquier sobrante para el siguiente bloque (ej.: 12 = 2,000 + 2 pendientes).
    bloques, sobrante = divmod(contador_imagenes_nsfw[user_id], 5)
    if bloques:
        recompensa = bloques * 1000
        if get_campo_usuario(user_id,"id_user") is None:
            insert_user(user_id,0,username,nombre)
        if dar_puntos(user_id, recompensa):
            contador_imagenes_nsfw[user_id] = sobrante
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"🔥 @{username or nombre} ha sido recompensado con {recompensa:,} PiPesos por su actividad en NSFW 😏",
                message_thread_id=thread_id
            )
    # Reiniciar 2 minutos después de la ÚLTIMA publicación.
    old_task = reset_tasks_nsfw.get(user_id)
    if old_task and not old_task.done():
        old_task.cancel()
    async def resetear_contador(uid):
        try:
            await asyncio.sleep(120)
            contador_imagenes_nsfw[uid] = 0
        except asyncio.CancelledError:
            pass
    reset_tasks_nsfw[user_id] = asyncio.create_task(resetear_contador(user_id))

async def detectar_exhibicion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recompensa Exhibición por publicación: foto=1,000, video=2,000; GIF/animación no cuenta."""
    mensaje = update.message
    if not mensaje:
        return

    # Los GIF de Telegram llegan normalmente como animation. Se ignoran por completo
    # para evitar recompensar respuestas/reacciones con GIF.
    if mensaje.animation:
        return

    tiene_foto = bool(mensaje.photo)
    tiene_video = bool(mensaje.video)
    if not (tiene_foto or tiene_video):
        return

    recompensa = 2000 if tiene_video else 1000
    thread_id = mensaje.message_thread_id
    user = mensaje.from_user
    user_id = user.id
    username = user.username
    nombre = normalizar_nombre(user.first_name, user.last_name)

    if get_campo_usuario(user_id, "id_user") is None:
        insert_user(user_id, 0, username, nombre)

    if dar_puntos(user_id, recompensa):
        tipo = "video" if tiene_video else "foto"
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✨ @{username or nombre} recibió {recompensa:,} PiPesos por su {tipo} en Exhibicionismo 💫",
            message_thread_id=thread_id
        )
    else:
        print(f"[REWARDS] No se pudo acreditar Exhibición a {user_id}; no se registró recompensa.")
