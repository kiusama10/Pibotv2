from src.utils.seasonal import seasonalize
import json, os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection


def _kb(rows): return InlineKeyboardMarkup(rows)

def _catalog():
    """Admin-configurable channel catalog. No invented channel IDs or prices."""
    raw=os.getenv('PIBOT_CHANNEL_CATALOG','').strip()
    if not raw: return []
    try:
        data=json.loads(raw)
        out=[]
        for x in data if isinstance(data,list) else []:
            if all(k in x for k in ('code','name','price')) and int(x['price'])>0:
                out.append({'code':str(x['code'])[:32], 'name':str(x['name'])[:80], 'price':int(x['price']), 'description':str(x.get('description',''))[:200]})
        return out[:20]
    except Exception:
        return []

async def pipesos(update:Update, context:ContextTypes.DEFAULT_TYPE):
    text=("🪙 *CENTRO DE PiPesos*\n\nLa moneda de la comunidad. Puedes conseguirla participando y ganando actividades/juegos, y usarla en tiendas, regalos, títulos, cosméticos, mercado, BANKIU, juegos y otros servicios configurados.\n\nElige una sección; consultar información nunca mueve tu dinero.")
    kb=_kb([[InlineKeyboardButton('💰 Mi saldo',callback_data='ph:saldo'),InlineKeyboardButton('📈 Cómo conseguirlos',callback_data='ph:ganar')],
            [InlineKeyboardButton('🛍️ En qué gastarlos',callback_data='ph:gastar'),InlineKeyboardButton('💸 Enviar',callback_data='ph:enviar')],
            [InlineKeyboardButton('🏦 BANKIU',callback_data='ph:bank'),InlineKeyboardButton('🏷️ Mercado',callback_data='ph:mercado')],
            [InlineKeyboardButton('📺 Canales',callback_data='ph:canales'),InlineKeyboardButton('❓ Instrucciones',callback_data='ph:help')]])
    await update.effective_message.reply_text(text,parse_mode='Markdown',reply_markup=kb)

async def instrucciones(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text('❓ *INSTRUCCIONES DE PIBOT*\n\nNo necesitas memorizar todo. Elige qué quieres hacer:',parse_mode='Markdown',reply_markup=_kb([
        [InlineKeyboardButton('🪙 PiPesos',callback_data='ph:home'),InlineKeyboardButton('👤 Perfil',callback_data='ph:perfil')],
        [InlineKeyboardButton('🎮 Juegos',callback_data='ph:juegos'),InlineKeyboardButton('🎁 Regalos',callback_data='ph:regalos')],
        [InlineKeyboardButton('🏦 BANKIU',callback_data='ph:bank'),InlineKeyboardButton('🎨 Vestidor',callback_data='ph:vestidor')],
        [InlineKeyboardButton('🏷️ Mercado',callback_data='ph:mercado'),InlineKeyboardButton('📺 Canales',callback_data='ph:canales')]
    ]))

async def canales(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await _show_channels(update,context,edit=False)

async def _show_channels(update,context,edit=True):
    cat=_catalog()
    if not cat:
        text='📺 *CANALES*\n\nEl sistema de compra ya está preparado, pero Kiu todavía no ha configurado canales y precios. No se cobrará nada hasta que exista un catálogo real.'
        kb=_kb([[InlineKeyboardButton('⬅️ PiPesos',callback_data='ph:home')]])
    else:
        text='📺 *CANALES DISPONIBLES*\n\nToca uno para revisar el precio. Comprar requiere confirmación.'
        rows=[[InlineKeyboardButton(f"{x['name']} · {x['price']:,}",callback_data=f"ch:view:{x['code']}")] for x in cat]
        rows.append([InlineKeyboardButton('⬅️ PiPesos',callback_data='ph:home')]); kb=_kb(rows)
    q=getattr(update,'callback_query',None)
    if edit and q: await q.edit_message_text(text,parse_mode='Markdown',reply_markup=kb)
    else: await update.effective_message.reply_text(text,parse_mode='Markdown',reply_markup=kb)

async def help_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); d=q.data
    if d=='ph:home':
        text='🪙 *CENTRO DE PiPesos*\n\nElige una sección:'; kb=_kb([[InlineKeyboardButton('💰 Mi saldo',callback_data='ph:saldo'),InlineKeyboardButton('📈 Cómo conseguirlos',callback_data='ph:ganar')],[InlineKeyboardButton('🛍️ En qué gastarlos',callback_data='ph:gastar'),InlineKeyboardButton('💸 Enviar',callback_data='ph:enviar')],[InlineKeyboardButton('🏦 BANKIU',callback_data='ph:bank'),InlineKeyboardButton('🏷️ Mercado',callback_data='ph:mercado')],[InlineKeyboardButton('📺 Canales',callback_data='ph:canales'),InlineKeyboardButton('❓ Instrucciones',callback_data='ph:help')]])
    elif d=='ph:saldo':
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute('SELECT saldo FROM usuarios_tb WHERE id_user=%s',(q.from_user.id,)); r=c.fetchone(); saldo=(r[0] if r else 0)
        finally:_put_connection(conn)
        text=f'💰 *Tu saldo:* {saldo:,} PiPesos'; kb=_kb([[InlineKeyboardButton('⬅️ Volver',callback_data='ph:home')]])
    elif d=='ph:ganar': text='📈 *Cómo conseguir PiPesos*\n\nParticipación, Quiz BDSM, juegos y eventos con recompensa. Cada sistema aplica sus propias reglas y límites.'; kb=_kb([[InlineKeyboardButton('⬅️ Volver',callback_data='ph:home')]])
    elif d=='ph:gastar': text='🛍️ *Dónde gastarlos*\n\n/regalos · /titulos · /cosmeticos · /mercado · /bankiu · juegos/apuestas y canales configurados.'; kb=_kb([[InlineKeyboardButton('⬅️ Volver',callback_data='ph:home')]])
    elif d=='ph:enviar': text='💸 *Enviar PiPesos*\n\nUsa `/dar cantidad @usuario` o responde a su mensaje con `/dar cantidad`. La transferencia es distinta del sistema social `/regalo`.'; kb=_kb([[InlineKeyboardButton('⬅️ Volver',callback_data='ph:home')]])
    elif d=='ph:bank': text='🏦 *BANKIU*\n\nPréstamos, pagos y empeños. Abre /bankiu para usar su interfaz.'; kb=_kb([[InlineKeyboardButton('⬅️ Volver',callback_data='ph:home')]])
    elif d=='ph:mercado': text='🏷️ *Mercado*\n\nCompra y venta de coleccionables transferibles. Abre /mercado.'; kb=_kb([[InlineKeyboardButton('⬅️ Volver',callback_data='ph:home')]])
    elif d=='ph:perfil': text='👤 *Perfil*\n\n/perfil para verlo. La edición de datos personales y cosméticos se realiza por PV.'; kb=_kb([[InlineKeyboardButton('⬅️ Volver',callback_data='ph:help')]])
    elif d=='ph:juegos': text='🎮 *Juegos*\n\n/jugar · /apostar · /caza · /lucha · /tortugas · /tortuga · /rankingtortugas · /blackjack · /cancelarblackjack · /asesino'; kb=_kb([[InlineKeyboardButton('⬅️ Volver',callback_data='ph:help')]])
    elif d=='ph:regalos': text='🎁 *Regalos*\n\n/regalos abre el catálogo y /regalo permite enviar regalos normales, privados o anónimos.'; kb=_kb([[InlineKeyboardButton('⬅️ Volver',callback_data='ph:help')]])
    elif d=='ph:vestidor': text='🎨 *Vestidor*\n\n/cosmeticos abre el acceso al vestidor privado con marcos e insignias.'; kb=_kb([[InlineKeyboardButton('⬅️ Volver',callback_data='ph:help')]])
    elif d=='ph:canales': return await _show_channels(update,context,edit=True)
    elif d=='ph:help': text='❓ *INSTRUCCIONES*\n\nElige una categoría. Las pantallas informativas nunca cobran PiPesos.'; kb=_kb([[InlineKeyboardButton('👤 Perfil',callback_data='ph:perfil'),InlineKeyboardButton('🎮 Juegos',callback_data='ph:juegos')],[InlineKeyboardButton('🎁 Regalos',callback_data='ph:regalos'),InlineKeyboardButton('🎨 Vestidor',callback_data='ph:vestidor')],[InlineKeyboardButton('⬅️ PiPesos',callback_data='ph:home')]])
    else: return
    await q.edit_message_text(text,parse_mode='Markdown',reply_markup=kb)

async def channel_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; parts=q.data.split(':',2); cat={x['code']:x for x in _catalog()}
    if len(parts)<3 or parts[2] not in cat: return await q.answer('Ese canal ya no está disponible.',show_alert=True)
    x=cat[parts[2]]
    if parts[1]=='view':
        await q.answer()
        return await q.edit_message_text(f"📺 *{x['name']}*\n💰 {x['price']:,} PiPesos\n{x['description']}\n\nLa compra queda registrada; el acceso se entrega según la configuración del canal.",parse_mode='Markdown',reply_markup=_kb([[InlineKeyboardButton('✅ Comprar',callback_data=f"ch:buy:{x['code']}")],[InlineKeyboardButton('⬅️ Canales',callback_data='ph:canales')]]))
    if parts[1]=='buy':
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute('SELECT purchase_id FROM channel_purchases_tb WHERE user_id=%s AND channel_code=%s AND estado IN (\'pagado\',\'entregado\')',(q.from_user.id,x['code']))
            if c.fetchone(): conn.rollback(); return await q.answer('Ya compraste este canal.',show_alert=True)
            c.execute('UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo>=%s',(x['price'],q.from_user.id,x['price']))
            if c.rowcount!=1: conn.rollback(); return await q.answer('No tienes PiPesos suficientes.',show_alert=True)
            c.execute('INSERT INTO channel_purchases_tb(user_id,channel_code,channel_name,precio,estado) VALUES(%s,%s,%s,%s,\'pagado\') RETURNING purchase_id',(q.from_user.id,x['code'],x['name'],x['price'])); pid=c.fetchone()[0]; conn.commit()
        except Exception:
            conn.rollback(); return await q.answer('No pude completar la compra.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Compra registrada.')
        await q.edit_message_text(f"✅ *Compra registrada*\n\n📺 {x['name']}\n💰 {x['price']:,} PiPesos\n🧾 Compra #{pid}\n\nEl acceso queda pendiente del método configurado para ese canal.",parse_mode='Markdown')
