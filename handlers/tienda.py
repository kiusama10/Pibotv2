import os
from telegram import InputMediaPhoto, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import get_campo_usuario, get_campo_item, comprar_item_atomico, get_catalog_items, get_item_gifs
from src.config import BOT_USERNAME
from telegram.error import TelegramError

# ==============================
#   TIENDA (Pantalla inicial)
# ==============================
async def tienda(update: Update, context: ContextTypes.DEFAULT_TYPE, from_menu=False):
    user_id = update.effective_user.id
    chat = update.effective_chat
    # --- SI NO ES PRIVADO ---
    if chat.type != "private":
        bot_user = BOT_USERNAME or context.bot.username
        deep_link = f"https://t.me/{bot_user}?start=menu"
        keyboard = [[InlineKeyboardButton("✨ Abrir menú principal", url=deep_link)]]

        await update.message.reply_text(
            "🛍️ La tienda solo está disponible en el chat privado.\n"
            "Haz clic en el botón para abrir el menú principal:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # --- REGISTRO ---
    if get_campo_usuario(user_id, "id_user") is None:
        await update.message.reply_text(
            "⚠️ No estás registrado.\nUsa /ver en el chat general de la comunidad para registrarte primero."
        )
        return

    # --- CARGAR IMAGEN DE CATÁLOGO ---
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RUTA_CATALOGO = os.path.join(BASE_DIR, "img_items", "catalogo.png")

    # --- SI VIENE DESDE UN BOTÓN ---
    if from_menu:
        sent = await update.callback_query.message.edit_media(
            media=InputMediaPhoto(open(RUTA_CATALOGO, "rb"))
        )
        await update.callback_query.message.edit_caption(
            caption="🛍️ **Catálogo de productos**",
            parse_mode="Markdown",
            reply_markup=botonera_catalogo()
        )
        return

    # --- SI VIENE DESDE /TIENDA ---
    await update.message.reply_photo(
        photo=open(RUTA_CATALOGO, "rb"),
        caption="🛍️ **Catálogo de productos**",
        parse_mode="Markdown",
        reply_markup=botonera_catalogo()
    )
# ==============================
#   CALLBACKS
# ==============================
def main_menu_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📜 Ver comandos", callback_data="ver_comandos")],
        [InlineKeyboardButton("🛍️ Abrir tienda", callback_data="abrir_tienda")],
        [InlineKeyboardButton("📦 Ver inventario", callback_data="ver_inventario")],
        [InlineKeyboardButton("👤 Perfil", callback_data="perfil")]
    ])

async def tienda_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()  # importante responder el callback
    data = query.data
    if data == "shop_noop":
        return
    # ------- VOLVER AL MENÚ PRINCIPAL (robusto) -------
    if data == "volver_menu":
        print("User ha regresado al menu principal")
        # Intentar editar el mensaje actual a texto del menú
        try:
            await query.edit_message_text(
                "✨ *Menú principal*\nSelecciona una opción:",
                parse_mode="Markdown",
                reply_markup=main_menu_markup()
            )
            return
        except TelegramError:
            # Si no es posible (por ejemplo, convertir mensaje-media a texto),
            # enviamos el menú como un nuevo mensaje y borramos el antiguo.
            try:
                # enviar nuevo mensaje con el menú
                await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text="✨ *Menú principal*\nSelecciona una opción:",
                    parse_mode="Markdown",
                    reply_markup=main_menu_markup()
                )
            except Exception as e:
                # opcionalmente loggear el error
                print("Error enviando menu fallback:", e)

            # intentar borrar el mensaje viejo (silencioso si falla)
            try:
                await query.message.delete()
            except Exception:
                pass
            return

    # ------- PAGINAR CATÁLOGO DINÁMICO -------
    if data.startswith("shop_page_"):
        try: page=max(1,int(data.rsplit("_",1)[1]))
        except Exception: page=1
        await query.edit_message_caption(caption="🛍️ **Catálogo de productos**",parse_mode="Markdown",reply_markup=botonera_catalogo(page))
        return

    # ------- PREVISUALIZAR UN GIF DEL ITEM -------
    if data.startswith("gif_preview_"):
        import random
        try: id_item=int(data.rsplit("_",1)[1])
        except Exception: return
        gifs=get_item_gifs(id_item)
        if not gifs:
            await context.bot.send_message(chat_id=query.from_user.id,text="🎞️ Este artículo usa por ahora los GIFs clásicos del bot. Puedes añadirle más con /agregargif."); return
        await context.bot.send_animation(chat_id=query.from_user.id,animation=random.choice(gifs),caption=f"🎞️ Vista previa · {get_campo_item(id_item,'nombre')}")
        return

    # ------- MOSTRAR ITEM -------
    if data.startswith("producto_"):
        id_item = int(data.replace("producto_", ""))
        descripcion = get_campo_item(id_item, "descripcion")
        await mostrar_item(id_item, descripcion, update, context)
        return

    # ------- VOLVER AL CATÁLOGO -------
    if data == "volver_catalogo":
        await volver_catalogo(update, context)
        return

    # ------- COMPRAR ITEM -------
    if data.startswith("comprar_"):
        id_item = int(data.replace("comprar_", ""))
        await comprar_item(id_item, update, context)
        return

# ==============================
#       VOLVER AL CATÁLOGO
# ==============================
async def volver_catalogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RUTA_CATALOGO = os.path.join(BASE_DIR, "img_items", "catalogo.png")

    # Cambiar imagen
    with open(RUTA_CATALOGO, "rb") as img:
        await query.edit_message_media(
            media=InputMediaPhoto(img)
        )

    # Cambiar caption
    await query.edit_message_caption(
        caption="🛍️ **Catálogo de productos**",
        parse_mode="Markdown",
        reply_markup=botonera_catalogo()
    )

# ==============================
#     COMPRAR ITEM
# ==============================
async def comprar_item(id_item, update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    item_nombre = get_campo_item(id_item, "nombre")
    item_precio = int(get_campo_item(id_item, "precio"))

    try:
        saldo_usuario = int(get_campo_usuario(user_id, "saldo"))
    except:
        saldo_usuario = 0

    # --- SIN SALDO ---
    if saldo_usuario < item_precio:
        await query.edit_message_caption(
            caption=(
                f"❌ *No tienes suficientes PiPesos*\n\n"
                f"Item: *{item_nombre}*\n"
                f"Precio: `{item_precio}`\n"
                f"Tu saldo actual: `{saldo_usuario}`"
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Volver al catálogo", callback_data="volver_catalogo")]
            ])
        )
        return

    # Cobro + entrega son una sola transacción. Si algo falla, no se cobra nada.
    if not comprar_item_atomico(user_id, id_item, item_precio):
        saldo_actual = get_campo_usuario(user_id, "saldo") or 0
        await query.edit_message_caption(
            caption=(
                f"❌ *No se pudo completar la compra*\n\n"
                f"Item: *{item_nombre}*\n"
                f"Precio: `{item_precio}`\n"
                f"Tu saldo actual: `{saldo_actual}`\n\n"
                "No se descontaron PiPesos si la operación falló."
            ),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ Volver al catálogo", callback_data="volver_catalogo")
            ]])
        )
        return

    await query.edit_message_caption(
        caption=(
            f"🎉 *¡Compra exitosa!*\n\n"
            f"Has comprado: *{item_nombre}*\n"
            f"Precio: `{item_precio}`\n\n"
            f"💼 El item ha sido añadido a tu inventario."
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("⬅️ Volver al catálogo", callback_data="volver_catalogo")
        ]])
    )
# ==============================
#    MOSTRAR ITEM ESPECÍFICO
# ==============================
async def mostrar_item(id_item, descripcion, update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    item_nombre = get_campo_item(id_item, "nombre")
    item_precio = get_campo_item(id_item, "precio")
    item_imagen = get_campo_item(id_item, "imagen")

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ruta_absoluta_imagen = os.path.join(BASE_DIR, item_imagen)


    texto_item = (
        f"📦 *{item_nombre}*\n"
        f"💬 {descripcion}\n"
        f"💲 Precio: {item_precio} COP"
    )

    botonera = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Volver al catálogo", callback_data="volver_catalogo")],
        [InlineKeyboardButton("🎞️ Ver GIF", callback_data=f"gif_preview_{id_item}"), InlineKeyboardButton("🛒 Comprar", callback_data=f"comprar_{id_item}")]
    ])

    # Imagen
    with open(ruta_absoluta_imagen, "rb") as img:
        await query.edit_message_media(
            media=InputMediaPhoto(img)
        )

    # Texto + Botones
    await query.edit_message_caption(
        caption=texto_item,
        parse_mode="Markdown",
        reply_markup=botonera
    )


# ==============================
#   BOTONERA CATÁLOGO
# ==============================
def botonera_catalogo(page=1):
    """Catálogo desde PostgreSQL: admite items nuevos sin tocar código."""
    items=get_catalog_items()
    per_page=8
    pages=max(1,(len(items)+per_page-1)//per_page)
    page=max(1,min(int(page or 1),pages))
    chunk=items[(page-1)*per_page:page*per_page]
    rows=[]
    for i in range(0,len(chunk),2):
        row=[]
        for iid,nombre,precio,categoria in chunk[i:i+2]:
            row.append(InlineKeyboardButton(f"{nombre} · {int(precio):,}",callback_data=f"producto_{iid}"))
        rows.append(row)
    if pages>1:
        nav=[]
        if page>1: nav.append(InlineKeyboardButton("⬅️",callback_data=f"shop_page_{page-1}"))
        nav.append(InlineKeyboardButton(f"{page}/{pages}",callback_data="shop_noop"))
        if page<pages: nav.append(InlineKeyboardButton("➡️",callback_data=f"shop_page_{page+1}"))
        rows.append(nav)
    rows.append([InlineKeyboardButton("⬅️ Volver al menú",callback_data="volver_menu")])
    return InlineKeyboardMarkup(rows)
