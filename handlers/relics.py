"""PiPeso sink: collectible relic vault. Additive tables; never deletes legacy gifts."""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection,_put_connection
from src.utils.seasonal import seasonalize

CATALOG=[
("fragmento_lunar","🌙 Fragmento Lunar","raro",8_000),
("ojo_abismo","👁️ Ojo del Abismo","épico",25_000),
("pluma_serafin","🪽 Pluma de Serafín","épico",35_000),
("corona_obsidiana","👑 Corona de Obsidiana","legendario",90_000),
("nucleo_dragon","🐉 Núcleo de Dragón","legendario",120_000),
("reloj_vacio","⌛ Reloj del Vacío","mítico",250_000),
("reliquia_kiu","🦅 Sello de Kiu","mítico",500_000),
]

def ensure_relic_tables():
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""CREATE TABLE IF NOT EXISTS user_relics_tb(
          relic_id BIGSERIAL PRIMARY KEY,user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
          code TEXT NOT NULL,nombre TEXT NOT NULL,rareza TEXT NOT NULL,precio INTEGER NOT NULL,
          serial BIGINT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_user_relics_owner ON user_relics_tb(user_id,created_at DESC)")
        conn.commit()
    except Exception: conn.rollback(); raise
    finally:_put_connection(conn)

def _kb():
    rows=[]
    for code,name,rarity,price in CATALOG: rows.append([InlineKeyboardButton(f"{name} · {price:,} PP",callback_data=f"rel:buy:{code}")])
    rows.append([InlineKeyboardButton("🏛️ Mi colección",callback_data="rel:mine")])
    return InlineKeyboardMarkup(rows)

async def boveda(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(seasonalize("🏛️ BÓVEDA DE RELIQUIAS\n\nColeccionables con serial real. No son regalos: son piezas de colección para presumir en tu perfil y sacar PiPesos de circulación. Cada compra genera el siguiente serial global de esa reliquia.",compact=True),reply_markup=_kb())

async def misreliquias(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await _send_mine(update.effective_message,update.effective_user.id)

async def _send_mine(msg,uid):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT nombre,rareza,serial,precio FROM user_relics_tb WHERE user_id=%s ORDER BY created_at DESC LIMIT 30",(uid,)); rows=c.fetchall()
    finally:_put_connection(conn)
    if not rows: return await msg.reply_text(seasonalize("🏛️ Tu bóveda todavía está vacía. Usa /boveda para conseguir tu primera reliquia.",compact=True))
    text="🏛️ MIS RELIQUIAS\n\n"+"\n".join(f"• {n} · {r.title()} · #{s} · {p:,} PP" for n,r,s,p in rows)
    await msg.reply_text(seasonalize(text,compact=True))

async def relic_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; parts=(q.data or '').split(':'); uid=q.from_user.id
    if len(parts)>=2 and parts[1]=='mine':
        await q.answer(); return await _send_mine(q.message,uid)
    if len(parts)!=3 or parts[1]!='buy': return await q.answer()
    item=next((x for x in CATALOG if x[0]==parts[2]),None)
    if not item:return await q.answer("Reliquia desconocida.",show_alert=True)
    code,name,rarity,price=item; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo>=%s",(price,uid,price))
        if c.rowcount!=1: conn.rollback(); return await q.answer("No tienes PiPesos suficientes.",show_alert=True)
        c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))",(code,)); c.execute("SELECT COALESCE(MAX(serial),0)+1 FROM user_relics_tb WHERE code=%s",(code,)); serial=int(c.fetchone()[0])
        c.execute("INSERT INTO user_relics_tb(user_id,code,nombre,rareza,precio,serial) VALUES(%s,%s,%s,%s,%s,%s)",(uid,code,name,rarity,price,serial)); conn.commit()
        await q.answer("Reliquia adquirida ✨"); await q.message.reply_text(seasonalize(f"🏛️ {name} entró a tu bóveda.\n{rarity.title()} · Serial #{serial} · {price:,} PiPesos",compact=True))
    except Exception as e:
        conn.rollback(); print('[RELIC]',e); await q.answer("No se confirmó la compra.",show_alert=True)
    finally:_put_connection(conn)
