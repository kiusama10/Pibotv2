"""Administración ROOT del catálogo GIF sin redeploy."""
from telegram import Update
from telegram.ext import ContextTypes
from src.database.database import (
    get_campo_item,
    insert_item,
    update_item,
    add_item_gif,
    set_item_category,
    unhide_item,
    _get_connection,
    _put_connection,
)
from src.utils.root_owner import ensure_root_identity

KEY = 'shop_gif_wizard'
DEFAULT_NEW_ITEM_PRICE = 1000


def _gif_file_id(message):
    if not message:
        return None
    if message.animation:
        return message.animation.file_id
    d = message.document
    if d and (d.mime_type or '').lower() == 'image/gif':
        return d.file_id
    return None


def _find_item_id(name: str):
    """Busca sin depender de mayúsculas/minúsculas.

    Corrige artículos antiguos guardados como `flores` que antes no eran
    encontrados por get_id_item(), que buscaba `Flores`.
    """
    clean = ' '.join((name or '').strip().split())
    if not clean:
        return None
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT id_item FROM items_tb WHERE LOWER(TRIM(nombre)) = LOWER(TRIM(%s)) ORDER BY id_item LIMIT 1",
            (clean,),
        )
        row = c.fetchone()
        return row[0] if row else None
    except Exception as e:
        print('[SHOP GIF LOOKUP]', e)
        return None
    finally:
        _put_connection(conn)


def _ensure_gif_table():
    """Autorrepara la tabla opcional de GIFs si el deploy viejo no la creó."""
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS item_gifs_tb (
                gif_id BIGSERIAL PRIMARY KEY,
                id_item INTEGER NOT NULL REFERENCES items_tb(id_item) ON DELETE CASCADE,
                telegram_file_id TEXT NOT NULL,
                added_by BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(id_item, telegram_file_id)
            )
            """
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_item_gifs_item ON item_gifs_tb(id_item)")
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print('[SHOP GIF TABLE]', e)
        return False
    finally:
        _put_connection(conn)


async def agregargif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not ensure_root_identity(update.effective_user):
        return await update.effective_message.reply_text('⛔ Este comando es exclusivo de Kiu.')

    src = update.effective_message.reply_to_message
    fid = _gif_file_id(src)
    if not fid:
        return await update.effective_message.reply_text(
            '🎞️ Responde al GIF que quieras añadir y escribe /agregargif.'
        )

    context.user_data[KEY] = {'step': 'name', 'file_id': fid}
    await update.effective_message.reply_text(
        '🎞️ GIF capturado.\n\n'
        '1/2 🏷️ ¿Cómo se llama el regalo?\n'
        'Si ya existe, añadiré este GIF al mismo regalo.'
    )


async def cancelaragregargif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if KEY in context.user_data:
        context.user_data.pop(KEY, None)
        return await update.effective_message.reply_text('❌ Alta de GIF cancelada.')


async def gif_admin_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st = context.user_data.get(KEY)
    if (
        not st
        or not update.effective_message
        or not update.effective_message.text
        or update.effective_message.text.startswith('/')
    ):
        return
    if not ensure_root_identity(update.effective_user):
        context.user_data.pop(KEY, None)
        return

    text = update.effective_message.text.strip()
    step = st['step']

    if step == 'name':
        name = ' '.join(text.split())[:80]
        if not name:
            return
        st['name'] = name
        iid = _find_item_id(name)
        st['item_id'] = iid
        st['existing'] = bool(iid)
        st['step'] = 'message'

        if iid:
            current = get_campo_item(iid, 'mensaje') or ''
            return await update.effective_message.reply_text(
                f'✅ {get_campo_item(iid, "nombre")} ya existe. Añadiré este GIF al mismo regalo.\n\n'
                f'2/2 💬 ¿Qué texto saldrá cuando lo usen?\n'
                f'Actual: {current or "(sin texto)"}\n\n'
                'Puedes usar {sender_username} y {receptor_username}.\n'
                'Escribe = si quieres conservar el texto actual.'
            )

        return await update.effective_message.reply_text(
            '2/2 💬 ¿Qué texto saldrá cuando lo usen?\n'
            'Puedes usar {sender_username} para quien lo usa y '
            '{receptor_username} para quien lo recibe.\n\n'
            f'Los regalos nuevos creados desde aquí cuestan {DEFAULT_NEW_ITEM_PRICE:,} PiPesos.'
        )

    if step == 'message':
        if not _ensure_gif_table():
            context.user_data.pop(KEY, None)
            return await update.effective_message.reply_text(
                '⚠️ No pude preparar el registro de GIFs. Revisa el log de Render.'
            )

        iid = st.get('item_id') or _find_item_id(st['name'])

        if iid:
            # Artículo existente: solo cambia el texto si Kiu escribió uno nuevo.
            if text != '=':
                update_item(iid, mensaje=text[:700])
        else:
            # Flujo simplificado: nombre + texto. El resto usa valores seguros.
            ok = insert_item(
                st['name'],
                DEFAULT_NEW_ITEM_PRICE,
                'img_items/catalogo.png',
                st['name'],
                text[:700],
            )
            if not ok:
                # Puede existir con otra capitalización por el bug viejo; reintenta lookup flexible.
                iid = _find_item_id(st['name'])
                if not iid:
                    context.user_data.pop(KEY, None)
                    return await update.effective_message.reply_text(
                        '⚠️ No pude crear el regalo. No se añadió el GIF.'
                    )
            else:
                iid = _find_item_id(st['name'])
                if iid:
                    set_item_category(iid, 'General')

        if not iid:
            context.user_data.pop(KEY, None)
            return await update.effective_message.reply_text(
                '⚠️ Encontré un problema al localizar el regalo. No se añadió el GIF.'
            )

        # Si el artículo había sido retirado del catálogo, volver a publicarlo al agregar GIF.
        try:
            unhide_item(iid)
        except Exception as e:
            print('[SHOP GIF UNHIDE]', e)

        ok = add_item_gif(iid, st['file_id'], update.effective_user.id)
        name = get_campo_item(iid, 'nombre') or st['name']
        price = get_campo_item(iid, 'precio') or DEFAULT_NEW_ITEM_PRICE
        context.user_data.pop(KEY, None)

        if not ok:
            return await update.effective_message.reply_text(
                '⚠️ El regalo existe, pero no pude registrar el GIF. Revisa el log de Render.'
            )

        return await update.effective_message.reply_text(
            f'✅ GIF agregado.\n\n'
            f'🎁 {name}\n'
            f'💰 {price:,} PiPesos\n'
            '🎲 Si tiene varios GIFs, PiBot elegirá uno al azar cuando lo usen.'
        )
