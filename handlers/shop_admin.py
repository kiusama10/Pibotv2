"""Administración ROOT del catálogo GIF sin redeploy."""
from telegram import Update
from telegram.ext import ContextTypes
from src.database.database import get_id_item, get_campo_item, insert_item, update_item, add_item_gif, set_item_category
from src.utils.root_owner import ensure_root_identity

KEY='shop_gif_wizard'

def _gif_file_id(message):
    if not message: return None
    if message.animation: return message.animation.file_id
    d=message.document
    if d and (d.mime_type or '').lower()=='image/gif': return d.file_id
    return None

async def agregargif(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if not ensure_root_identity(update.effective_user):
        return await update.effective_message.reply_text('⛔ Este comando es exclusivo de Kiu.')
    src=update.effective_message.reply_to_message
    fid=_gif_file_id(src)
    if not fid:
        return await update.effective_message.reply_text('🎞️ Responde al GIF que quieras añadir y escribe /agregargif.')
    context.user_data[KEY]={'step':'name','file_id':fid}
    await update.effective_message.reply_text('🎞️ GIF capturado.\n\n1/5 ¿A qué artículo pertenece?\nEscribe el nombre, por ejemplo: Collar. Si ya existe, lo añadiré a ese mismo artículo para que salga al azar.')

async def cancelaragregargif(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if KEY in context.user_data:
        context.user_data.pop(KEY,None); return await update.effective_message.reply_text('❌ Alta de GIF cancelada.')

async def gif_admin_text_input(update:Update, context:ContextTypes.DEFAULT_TYPE):
    st=context.user_data.get(KEY)
    if not st or not update.effective_message or not update.effective_message.text or update.effective_message.text.startswith('/'): return
    if not ensure_root_identity(update.effective_user): context.user_data.pop(KEY,None); return
    text=update.effective_message.text.strip()
    step=st['step']
    if step=='name':
        if not text: return
        st['name']=text; iid=get_id_item(text)
        if iid:
            st['item_id']=iid; st['existing']=True; st['step']='message'
            current=get_campo_item(iid,'mensaje') or ''
            return await update.effective_message.reply_text(f'✅ {get_campo_item(iid,"nombre")} ya existe. Este GIF se sumará a sus GIFs actuales y todos saldrán aleatoriamente.\n\nMensaje actual:\n{current}\n\nEscribe = para conservarlo, o escribe un mensaje nuevo. Puedes usar {{sender_username}} y {{receptor_username}}.')
        st['existing']=False; st['step']='price'
        return await update.effective_message.reply_text('2/5 💰 ¿Cuánto costará en PiPesos?')
    if step=='price':
        try: price=int(text.replace(',','').replace('.',''))
        except: return await update.effective_message.reply_text('Escribe solo el precio, por ejemplo: 2000')
        if price<0: return await update.effective_message.reply_text('El precio no puede ser negativo.')
        st['price']=price; st['step']='category'; return await update.effective_message.reply_text('3/5 🗂️ ¿Categoría? Ejemplo: BDSM, Cariño, Bromas o Especiales.')
    if step=='category':
        st['category']=text[:40] or 'General'; st['step']='description'; return await update.effective_message.reply_text('4/5 📝 ¿Qué descripción aparecerá en la tienda?')
    if step=='description':
        st['description']=text[:300]; st['step']='message'; return await update.effective_message.reply_text('5/5 💬 ¿Qué mensaje saldrá cuando lo usen?\nUsa {sender_username} para quien lo usa y {receptor_username} para quien lo recibe.')
    if step=='message':
        if st.get('existing'):
            iid=st['item_id']
            if text!='=': update_item(iid,mensaje=text[:700])
        else:
            ok=insert_item(st['name'],st['price'],'img_items/catalogo.png',st['description'],text[:700])
            if not ok:
                context.user_data.pop(KEY,None); return await update.effective_message.reply_text('⚠️ No pude crear el artículo. No se añadió el GIF.')
            iid=get_id_item(st['name']); set_item_category(iid,st['category'])
        ok=add_item_gif(iid,st['file_id'],update.effective_user.id)
        name=get_campo_item(iid,'nombre'); price=get_campo_item(iid,'precio')
        context.user_data.pop(KEY,None)
        if not ok: return await update.effective_message.reply_text('⚠️ El artículo existe, pero no pude registrar el GIF.')
        return await update.effective_message.reply_text(f'✅ Publicado.\n\n🛍️ {name}\n💰 {price:,} PiPesos\n🎲 Este GIF entra en la selección aleatoria del artículo.\n\nPuedes responder a otro GIF con /agregargif y poner el mismo nombre para seguir ampliándolo.')
