from src.utils.seasonal import seasonalize
import hashlib
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection, get_id_user
from src.utils.seasonal import current_season

TITLE_POOL = [
    ("pet_travieso","Pet Travieso","comun",5000,None),("brat","Brat","comun",5000,None),
    ("rope_lover","Rope Lover","comun",7000,None),("dom_nocturno","Dom Nocturno","comun",8000,None),
    ("kitsune_rebelde","Kitsune Rebelde","raro",35000,10),("vampiro_medianoche","Vampiro de Medianoche","raro",40000,10),
    ("oni_dominante","Oni Dominante","raro",45000,10),("angel_caido","Ángel Caído","raro",45000,10),
    ("reina_cadenas","Reina de las Cadenas","epico",90000,5),("shinigami_carmesi","Shinigami Carmesí","epico",95000,5),
    ("emperador_sombras","Emperador de las Sombras","epico",100000,5),("one_winged_angel","One Winged Angel","legendario",250000,3),
    ("hangman","Hangman","legendario",225000,3),("aerial_assassin","Aerial Assassin","legendario",250000,3),
    ("the_cleaner","The Cleaner","legendario",225000,3),("demon_king","Demon King","mitico",600000,1),
    ("vampire_overlord","Vampire Overlord","mitico",650000,1),("crimson_shogun","Crimson Shogun","mitico",700000,1),
]

# Catálogo ampliado: conserva todos los títulos originales y añade más de 100 opciones temáticas.
_EXTRA_TITLE_A=["Guardián","Reina","Rey","Dama","Señor","Príncipe","Princesa","Soberano","Soberana","Maestro","Maestra","Heredero"]
_EXTRA_TITLE_B=["del Eclipse","de Medianoche","de Obsidiana","Carmesí","del Aftercare","del Protocolo","de las Cadenas","del Consenso","de la Luna","del Caos"]
for _i,(_a,_b) in enumerate(((_a,_b) for _a in _EXTRA_TITLE_A for _b in _EXTRA_TITLE_B),1):
    _code=f"extra_{_i:03d}"
    _name=f"{_a} {_b}"
    if not any(x[0]==_code or x[1]==_name for x in TITLE_POOL):
        TITLE_POOL.append((_code,_name,"comun",8000,None))
RARE_EMOJI={"comun":"⚪","raro":"🔵","epico":"🟣","legendario":"🟡","mitico":"🔴"}
TITLE_RESALE_PRICE=1000

SEASONAL_TITLES = {
    "halloween": [("little_nightmare","Little Nightmare","raro",45000,10),("amo_carmesi","Amo Carmesí","epico",95000,5),("vampire_lord_halloween","Vampire Lord","legendario",275000,3),("nightmare_king","Nightmare King","mitico",750000,1)],
    "dia_muertos": [("alma_eterna","Alma Eterna","raro",45000,10),("catrina","Catrina","epico",90000,5),("guardian_mictlan","Guardián del Mictlán","legendario",260000,3),("rey_mictlan","Rey del Mictlán","mitico",750000,1)],
    "navidad": [("christmas_little","Christmas Little","raro",40000,10),("daddy_claus","Daddy Claus","epico",85000,5),("mommy_claus","Mommy Claus","epico",85000,5),("winter_dom","Dom de Invierno","legendario",250000,3),("krampus_supreme","Krampus Supreme","mitico",700000,1)],
    "san_valentin": [("daddys_little","Daddy's Little","raro",45000,10),("mommys_favorite","Mommy's Favorite","epico",90000,5),("corazon_con_dueno","Corazón con Dueño","legendario",250000,3),("eternal_bond","Eternal Bond","mitico",700000,1)],
}

def _rotation_bounds(now=None):
    # Rotate at 00:00 and 12:00 Mexico City time, independent of Render's UTC clock.
    mx=ZoneInfo('America/Mexico_City')
    local=(now or datetime.now(timezone.utc)).astimezone(mx)
    hour=0 if local.hour < 12 else 12
    start_local=local.replace(hour=hour,minute=0,second=0,microsecond=0)
    end_local=start_local+timedelta(hours=12)
    return start_local.astimezone(timezone.utc),end_local.astimezone(timezone.utc)

def ensure_title_rotation():
    start,end=_rotation_bounds(); key=start.strftime('%Y%m%d%H')
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT 1 FROM title_rotations_tb WHERE rotation_key=%s",(key,))
        if not c.fetchone():
            c.execute("INSERT INTO title_rotations_tb(rotation_key,starts_at,ends_at) VALUES(%s,%s,%s)",(key,start,end))
            pool=TITLE_POOL+SEASONAL_TITLES.get(current_season(),[]); commons=[x for x in pool if x[2]=='comun']; limited=[x for x in pool if x[2]!='comun']
            seed=int(hashlib.sha256(key.encode()).hexdigest()[:16],16); rng=random.Random(seed)
            picks=commons+rng.sample(limited,min(8,len(limited)))
            for code,name,rarity,price,stock in picks:
                c.execute("INSERT INTO title_rotation_stock_tb(rotation_key,code,nombre,rareza,precio,stock_total) VALUES(%s,%s,%s,%s,%s,%s)",
                          (key,code,name,rarity,price,stock))
        conn.commit(); return key,end
    except Exception:
        conn.rollback(); raise
    finally:_put_connection(conn)

def buy_title(uid,code):
    key,_=ensure_title_rotation(); conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT nombre,rareza,precio,stock_total,stock_vendido FROM title_rotation_stock_tb WHERE rotation_key=%s AND code=%s FOR UPDATE",(key,code))
        row=c.fetchone()
        if not row: conn.rollback(); return "missing",None
        name,rarity,price,total,sold=row
        if total is not None and sold>=total: conn.rollback(); return "soldout",None
        c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo>=%s",(price,uid,price))
        if c.rowcount!=1: conn.rollback(); return "money",None
        serial=(sold+1) if total is not None else None
        origin=f"tienda:{key}"
        c.execute("INSERT INTO social_assets_tb(asset_type,code,nombre,rareza,serial_no,serial_total,valor_base,propietario_id,origen) VALUES('titulo',%s,%s,%s,%s,%s,%s,%s,%s) RETURNING asset_id",
                  (code,name,rarity,serial,total,price,uid,origin)); aid=c.fetchone()[0]
        c.execute("UPDATE title_rotation_stock_tb SET stock_vendido=stock_vendido+1 WHERE rotation_key=%s AND code=%s",(key,code))
        c.execute("INSERT INTO social_asset_history_tb(asset_id,a_user,accion,precio) VALUES(%s,%s,'compra_tienda',%s)",(aid,uid,price))
        conn.commit(); return "ok",(aid,name,rarity,serial,total,price)
    except Exception as e: conn.rollback(); print('[SOCIAL] buy title',e); return "error",None
    finally:_put_connection(conn)

def sell_title_to_pibot(uid,aid):
    """Retira un título disponible de la colección y paga 1,000 PiPesos. Conserva su historial."""
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("SELECT nombre,estado FROM social_assets_tb WHERE asset_id=%s AND propietario_id=%s AND asset_type='titulo' FOR UPDATE",(aid,uid)); row=c.fetchone()
        if not row or row[1] != 'disponible':
            conn.rollback(); return None
        name=row[0]
        # Si estaba equipado, se quita antes de devolverlo a PiBot.
        c.execute("UPDATE perfiles_tb SET titulo_equipado_id=NULL WHERE id_user=%s AND titulo_equipado_id=%s",(uid,aid))
        c.execute("UPDATE social_assets_tb SET propietario_id=NULL,estado='vendido_pibot' WHERE asset_id=%s AND propietario_id=%s AND estado='disponible'",(aid,uid))
        if c.rowcount != 1:
            conn.rollback(); return None
        c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s RETURNING saldo",(TITLE_RESALE_PRICE,uid)); bal=c.fetchone()
        c.execute("INSERT INTO social_asset_history_tb(asset_id,de_user,a_user,accion,precio) VALUES(%s,%s,NULL,'venta_pibot',%s)",(aid,uid,TITLE_RESALE_PRICE))
        conn.commit(); return name,int(bal[0]) if bal else None
    except Exception as e:
        conn.rollback(); print('[SOCIAL] sell title to pibot',e); return None
    finally:
        _put_connection(conn)


def list_assets(uid,atype=None):
    conn=_get_connection()
    try:
        c=conn.cursor(); q="SELECT asset_id,nombre,rareza,serial_no,serial_total,valor_base,estado FROM social_assets_tb WHERE propietario_id=%s"; args=[uid]
        if atype:q+=" AND asset_type=%s";args.append(atype)
        else:q+=" AND asset_type<>'regalo'"
        q+=" ORDER BY creado_en DESC LIMIT 30";c.execute(q,args);return c.fetchall()
    finally:_put_connection(conn)

def list_market():
    conn=_get_connection()
    try:
        c=conn.cursor();c.execute("SELECT m.listing_id,a.nombre,a.rareza,a.serial_no,a.serial_total,m.precio,m.vendedor_id FROM social_market_tb m JOIN social_assets_tb a ON a.asset_id=m.asset_id WHERE m.estado='activo' AND a.asset_type<>'regalo' ORDER BY m.creado_en DESC LIMIT 20");return c.fetchall()
    finally:_put_connection(conn)

def sell_asset(uid,aid,price):
    conn=_get_connection()
    try:
        c=conn.cursor();c.execute("SELECT estado,transferible FROM social_assets_tb WHERE asset_id=%s AND propietario_id=%s AND asset_type<>'regalo' FOR UPDATE",(aid,uid));r=c.fetchone()
        if not r or r[0]!='disponible' or not r[1]:conn.rollback();return False
        c.execute("INSERT INTO social_market_tb(asset_id,vendedor_id,precio) VALUES(%s,%s,%s)",(aid,uid,price));c.execute("UPDATE social_assets_tb SET estado='mercado' WHERE asset_id=%s",(aid,));conn.commit();return True
    except Exception as e:conn.rollback();print('[SOCIAL] sell',e);return False
    finally:_put_connection(conn)

def buy_market(uid,lid):
    conn=_get_connection()
    try:
        c=conn.cursor();c.execute("SELECT m.asset_id,m.vendedor_id,m.precio,a.nombre FROM social_market_tb m JOIN social_assets_tb a ON a.asset_id=m.asset_id WHERE m.listing_id=%s AND m.estado='activo' AND a.asset_type<>'regalo' FOR UPDATE",(lid,));r=c.fetchone()
        if not r:conn.rollback();return 'missing',None
        aid,seller,price,name=r
        if seller==uid:conn.rollback();return 'self',None
        ids=sorted((uid,seller));c.execute("SELECT id_user,saldo FROM usuarios_tb WHERE id_user IN (%s,%s) ORDER BY id_user FOR UPDATE",ids);balances=dict(c.fetchall())
        if balances.get(uid,0)<price:conn.rollback();return 'money',None
        c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s",(price,uid));c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(price,seller))
        c.execute("UPDATE social_assets_tb SET propietario_id=%s,estado='disponible' WHERE asset_id=%s AND propietario_id=%s",(uid,aid,seller))
        if c.rowcount!=1:conn.rollback();return 'error',None
        c.execute("UPDATE social_market_tb SET estado='vendido',vendido_en=NOW() WHERE listing_id=%s",(lid,));c.execute("INSERT INTO social_asset_history_tb(asset_id,de_user,a_user,accion,precio) VALUES(%s,%s,%s,'venta',%s)",(aid,seller,uid,price));conn.commit();return 'ok',(name,price,seller)
    except Exception as e:conn.rollback();print('[SOCIAL] market buy',e);return 'error',None
    finally:_put_connection(conn)

def pawn_asset(uid,aid):
    conn=_get_connection()
    try:
        c=conn.cursor();c.execute("SELECT valor_base,nombre,rareza,estado FROM social_assets_tb WHERE asset_id=%s AND propietario_id=%s AND asset_type<>'regalo' FOR UPDATE",(aid,uid));r=c.fetchone()
        if not r or r[3]!='disponible':conn.rollback();return 'missing',None
        value,name,rarity,_=r
        ratios={'comun':.25,'raro':.35,'epico':.40,'legendario':.45,'mitico':.50};principal=max(100,int(value*ratios.get(rarity,.25)));payoff=(principal*110+99)//100
        c.execute("UPDATE social_assets_tb SET estado='empenado' WHERE asset_id=%s",(aid,));c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(principal,uid));c.execute("INSERT INTO bankiu_pawns_tb(asset_id,user_id,principal,payoff,vence_en) VALUES(%s,%s,%s,%s,NOW()+INTERVAL '7 days')",(aid,uid,principal,payoff));c.execute("INSERT INTO social_asset_history_tb(asset_id,de_user,a_user,accion,precio) VALUES(%s,%s,%s,'empeno',%s)",(aid,uid,uid,principal));conn.commit();return 'ok',(name,principal,payoff)
    except Exception as e:conn.rollback();print('[BANKIU] pawn',e);return 'error',None
    finally:_put_connection(conn)

def redeem_asset(uid,aid):
    conn=_get_connection()
    try:
        c=conn.cursor();c.execute("SELECT p.payoff,a.nombre FROM bankiu_pawns_tb p JOIN social_assets_tb a ON a.asset_id=p.asset_id WHERE p.asset_id=%s AND p.user_id=%s AND p.estado='activo' AND a.asset_type<>'regalo' FOR UPDATE",(aid,uid));r=c.fetchone()
        if not r:conn.rollback();return 'missing',None
        payoff,name=r;c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo>=%s",(payoff,uid,payoff))
        if c.rowcount!=1:conn.rollback();return 'money',None
        c.execute("UPDATE bankiu_pawns_tb SET estado='pagado' WHERE asset_id=%s",(aid,));c.execute("UPDATE social_assets_tb SET estado='disponible' WHERE asset_id=%s",(aid,));c.execute("INSERT INTO social_asset_history_tb(asset_id,de_user,a_user,accion,precio) VALUES(%s,%s,%s,'desempeno',%s)",(aid,uid,uid,payoff));conn.commit();return 'ok',(name,payoff)
    except Exception as e:conn.rollback();print('[BANKIU] redeem',e);return 'error',None
    finally:_put_connection(conn)

def _target(update,args):
    if update.message.reply_to_message:return update.message.reply_to_message.from_user.id, update.message.reply_to_message.from_user.first_name, args
    if args and args[0].startswith('@'):
        username=args[0][1:];uid=get_id_user(username)
        return uid,('@'+username),args[1:]
    return None,None,args

def _title_shop_rows():
    key,end=ensure_title_rotation(); conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT code,nombre,rareza,precio,stock_total,stock_vendido FROM title_rotation_stock_tb WHERE rotation_key=%s ORDER BY CASE rareza WHEN 'mitico' THEN 1 WHEN 'legendario' THEN 2 WHEN 'epico' THEN 3 WHEN 'raro' THEN 4 ELSE 5 END,precio",(key,)); rows=c.fetchall()
    finally:_put_connection(conn)
    return rows,end

def _titles_home_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍️ Tienda de títulos",callback_data="soc:title_shop"),InlineKeyboardButton("🎒 Mis títulos",callback_data="soc:title_owned")],
        [InlineKeyboardButton("✨ Vestidor",callback_data="cos_home")],
    ])

def _title_shop_markup(rows):
    kb=[]
    for code,name,r,p,total,sold in rows:
        stock='∞' if total is None else f'{max(0,total-sold)}/{total}'
        kb.append([InlineKeyboardButton(f"{RARE_EMOJI.get(r,'⚪')} {name} · {p:,} PP · {stock}",callback_data=f"soc:title_view:{code}")])
    kb.append([InlineKeyboardButton("🎒 Mi colección",callback_data="soc:title_owned"),InlineKeyboardButton("⬅️ Inicio",callback_data="soc:title_home")])
    return InlineKeyboardMarkup(kb)

async def titulos(update:Update,context:ContextTypes.DEFAULT_TYPE):
    rows,end=_title_shop_rows(); left=max(timedelta(),end-datetime.now(timezone.utc));h=int(left.total_seconds()//3600);m=int(left.total_seconds()%3600//60)
    text=("🏷️✨ TIENDA DE TÍTULOS ✨🏷️\n\n"
          "Colecciona títulos, presume sus seriales y equipa tu favorito desde botones.\n"
          f"🔄 Nueva rotación en {h:02d}h {m:02d}m\n\nToca uno para ver sus detalles.")
    await update.message.reply_text(text,reply_markup=_title_shop_markup(rows))

async def comprartitulo(update:Update,context:ContextTypes.DEFAULT_TYPE):
    # Compatibilidad: el comando antiguo sigue funcionando, pero la interfaz principal usa botones.
    if not context.args:return await titulos(update,context)
    st,data=buy_title(update.effective_user.id,context.args[0].lower())
    if st=='ok':
        aid,name,r,serial,total,price=data;ser=f' #{serial}/{total}' if total else ''
        await update.message.reply_text(f"✨ ¡Título adquirido!\n🏷️ {name}{ser}\n{RARE_EMOJI.get(r,'')} {r.title()} · {price:,} PiPesos",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✨ Equipar ahora",callback_data=f"soc:title_equip:{aid}")],[InlineKeyboardButton("🎒 Mis títulos",callback_data="soc:title_owned")]]))
    elif st=='money':await update.message.reply_text('💸 No tienes suficientes PiPesos.')
    elif st=='soldout':await update.message.reply_text('😈 Llegaste tarde: esa edición se agotó.')
    else:await update.message.reply_text('Ese título no está en la rotación actual.')






async def mistitulos(update:Update,context:ContextTypes.DEFAULT_TYPE):
    rows=list_assets(update.effective_user.id,'titulo')
    if not rows:return await update.message.reply_text('🏷️ Aún no tienes títulos.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ Ir a la tienda",callback_data="soc:title_shop")]]))
    kb=[]
    for a,n,r,sn,st,_,e in rows:
        serial=f" #{sn}/{st}" if sn else ""; lock=" 🔒" if e!='disponible' else ""
        kb.append([InlineKeyboardButton(f"{RARE_EMOJI.get(r,'⚪')} {n}{serial}{lock}",callback_data=f"soc:title_info:{a}")])
    kb.append([InlineKeyboardButton("🛍️ Tienda",callback_data="soc:title_shop")])
    await update.message.reply_text(f"🏷️✨ TUS TÍTULOS ✨🏷️\n\nTienes {len(rows)}. Toca uno para equiparlo o venderlo por {TITLE_RESALE_PRICE:,} PiPesos.",reply_markup=InlineKeyboardMarkup(kb))


async def _safe_q_text(q, text, reply_markup=None):
    if getattr(q.message, "photo", None):
        return await q.message.reply_text(text, reply_markup=reply_markup)
    return await q.edit_message_text(text, reply_markup=reply_markup)

async def social_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); uid=q.from_user.id; data=q.data
    if data=='soc:title_home': return await _safe_q_text(q, "🏷️ COLECCIÓN DE TÍTULOS\n\nCompra, colecciona y equipa tu favorito.",reply_markup=_titles_home_markup())
    if data=='soc:title_shop':
        rows,end=_title_shop_rows(); left=max(timedelta(),end-datetime.now(timezone.utc));h=int(left.total_seconds()//3600);m=int(left.total_seconds()%3600//60)
        return await _safe_q_text(q, f"🏷️✨ TIENDA DE TÍTULOS ✨🏷️\n\n🔄 Cambia en {h:02d}h {m:02d}m\nToca uno para comprarlo.",reply_markup=_title_shop_markup(rows))
    if data.startswith('soc:title_view:'):
        code=data.split(':',2)[2]; rows,_=_title_shop_rows(); item=next((x for x in rows if x[0]==code),None)
        if not item:return await q.answer('Ese título ya no está disponible.',show_alert=True)
        _,name,r,p,total,sold=item; stock='∞' if total is None else f'{max(0,total-sold)}/{total}'
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(f"💰 Comprar · {p:,} PP",callback_data=f"soc:title_buy:{code}")],[InlineKeyboardButton("⬅️ Tienda",callback_data="soc:title_shop")]])
        return await _safe_q_text(q, f"{RARE_EMOJI.get(r,'⚪')} {name}\n✨ Rareza: {r.title()}\n📦 Stock: {stock}\n💰 Precio: {p:,} PiPesos",reply_markup=kb)
    if data.startswith('soc:title_buy:'):
        code=data.split(':',2)[2]; st,res=buy_title(uid,code)
        if st=='ok':
            aid,name,r,serial,total,price=res; ser=f' #{serial}/{total}' if total else ''
            return await _safe_q_text(q, f"🎉 ¡YA ES TUYO!\n\n{RARE_EMOJI.get(r,'⚪')} {name}{ser}\n💰 {price:,} PiPesos",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✨ Equipar ahora",callback_data=f"soc:title_equip:{aid}")],[InlineKeyboardButton("🎒 Mis títulos",callback_data="soc:title_owned"),InlineKeyboardButton("🛍️ Tienda",callback_data="soc:title_shop")]]))
        return await q.answer({'money':'No tienes suficientes PiPesos.','soldout':'Se agotó justo antes de tu compra.','missing':'Ya salió de la rotación.'}.get(st,'No pude completar la compra.'),show_alert=True)
    if data=='soc:title_owned':
        rows=list_assets(uid,'titulo')
        if not rows:return await _safe_q_text(q, '🏷️ Aún no tienes títulos.',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛍️ Tienda",callback_data="soc:title_shop")]]))
        kb=[[InlineKeyboardButton(f"{RARE_EMOJI.get(r,'⚪')} {n}"+(f" #{sn}/{st}" if sn else ''),callback_data=f"soc:title_info:{a}")] for a,n,r,sn,st,_,e in rows]
        kb.append([InlineKeyboardButton("🛍️ Tienda",callback_data="soc:title_shop"),InlineKeyboardButton("⬅️ Inicio",callback_data="soc:title_home")])
        return await _safe_q_text(q, f'🏷️✨ TUS TÍTULOS ✨🏷️\n\nToca uno para equiparlo o venderlo por {TITLE_RESALE_PRICE:,} PiPesos.',reply_markup=InlineKeyboardMarkup(kb))
    if data.startswith('soc:title_info:'):
        aid=int(data.rsplit(':',1)[1]); row=next((x for x in list_assets(uid,'titulo') if x[0]==aid),None)
        if not row:return await q.answer('Ese título no está disponible.',show_alert=True)
        a,n,r,sn,st,v,e=row; ser=f' #{sn}/{st}' if sn else ''
        kb=[]
        if e=='disponible':
            kb.append([InlineKeyboardButton("✨ Equipar",callback_data=f"soc:title_equip:{aid}"),InlineKeyboardButton(f"💰 Vender · {TITLE_RESALE_PRICE:,}",callback_data=f"soc:title_sell:{aid}")])
        kb.append([InlineKeyboardButton("⬅️ Mis títulos",callback_data="soc:title_owned")])
        return await _safe_q_text(q, f"{RARE_EMOJI.get(r,'⚪')} {n}{ser}\n✨ {r.title()}\n💎 Valor base: {v:,} PP\n📦 Estado: {e}\n💰 Reventa a PiBot: {TITLE_RESALE_PRICE:,} PP",reply_markup=InlineKeyboardMarkup(kb))
    if data.startswith('soc:title_sell:'):
        aid=int(data.rsplit(':',1)[1]); row=next((x for x in list_assets(uid,'titulo') if x[0]==aid and x[6]=='disponible'),None)
        if not row:return await q.answer('Ese título ya no está disponible para vender.',show_alert=True)
        n=row[1]
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ Sí, vender por {TITLE_RESALE_PRICE:,}",callback_data=f"soc:title_sellconfirm:{aid}")],[InlineKeyboardButton("❌ Conservar",callback_data=f"soc:title_info:{aid}")]])
        return await _safe_q_text(q,f"💰 ¿VENDER {n.upper()}?\n\nRecibirás {TITLE_RESALE_PRICE:,} PiPesos. Si está equipado, se quitará automáticamente de tu perfil.",reply_markup=kb)
    if data.startswith('soc:title_sellconfirm:'):
        aid=int(data.rsplit(':',1)[1]); sold=sell_title_to_pibot(uid,aid)
        if not sold:return await q.answer('Ese título ya no se puede vender.',show_alert=True)
        name,balance=sold
        return await _safe_q_text(q,f"✅ Vendiste {name} por {TITLE_RESALE_PRICE:,} PiPesos.\n💰 Saldo: {balance:,} PiPesos",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏷️ Volver a mis títulos",callback_data="soc:title_owned")]]))
    if data.startswith('soc:title_equip:'):
        from handlers.profile_social import _equip
        aid=int(data.rsplit(':',1)[1]); name=_equip(uid,aid)
        if not name:return await q.answer('No se puede equipar ese título.',show_alert=True)
        return await _safe_q_text(q, f"✨🏷️ TÍTULO EQUIPADO\n\n{name}\n\nYa aparece en tu perfil.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎒 Mis títulos",callback_data="soc:title_owned"),InlineKeyboardButton("👤 Ver perfil",callback_data="soc:profile")]]))
    if data.startswith('soc:market_buy:'):
        lid=int(data.rsplit(':',1)[1]); st,res=buy_market(uid,lid)
        if st=='ok': return await _safe_q_text(q, f"🤝 Compra cerrada: {res[0]} por {res[1]:,} PiPesos. El objeto ya está en tu colección.")
        return await q.answer('No tienes saldo suficiente.' if st=='money' else 'Esa venta ya no está disponible.',show_alert=True)
    if data.startswith('soc:sell_pick:'):
        aid=int(data.rsplit(':',1)[1]); row=next((x for x in list_assets(uid) if x[0]==aid and x[6]=='disponible'),None)
        if not row:return await q.answer('Ese objeto ya no está disponible.',show_alert=True)
        context.user_data['social_sell_asset']=aid
        context.user_data['social_input']='sell_price'
        return await _safe_q_text(q, f"🏪 Vas a vender: {row[1]}\n\nEscribe ahora el precio en PiPesos. Para cancelar escribe cancelar.")
    if data.startswith('soc:pawn_pick:'):
        aid=int(data.rsplit(':',1)[1]); st,res=pawn_asset(uid,aid)
        if st=='ok':return await _safe_q_text(q, f"🏦 BANKIU aceptó {res[0]}.\n💰 Recibes {res[1]:,} PiPesos\n🧾 Recuperarlo cuesta {res[2]:,} PiPesos antes de 7 días.")
        return await q.answer('BANKIU no puede aceptar ese objeto.',show_alert=True)
    if data=='soc:profile':
        from handlers.profile_social import _render
        return await _safe_q_text(q, _render(uid,uid),reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏷️ Mis títulos",callback_data="soc:title_owned")],[InlineKeyboardButton("✨ Mi vestidor",callback_data="cos_home")]]))

async def mercado(update:Update,context:ContextTypes.DEFAULT_TYPE):
    rows=list_market()
    if not rows:return await update.message.reply_text('🏪 El mercado está vacío.')
    kb=[]
    for lid,n,r,sn,st,p,seller in rows[:30]:
        label=f"{RARE_EMOJI.get(r,'')} {n}"+(f" #{sn}/{st}" if sn else '')+f" · {p:,} PP"
        kb.append([InlineKeyboardButton(label,callback_data=f"soc:market_buy:{lid}")])
    await update.message.reply_text('🏪 MERCADO ENTRE USUARIOS\n\nToca una publicación para comprarla. No necesitas copiar IDs.',reply_markup=InlineKeyboardMarkup(kb))

async def vender(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    # Compatibilidad: el formato antiguo sigue disponible, pero la ruta normal es por botones.
    if len(context.args)>=2:
        try: aid=int(context.args[0]); price=int(context.args[1])
        except: return await update.message.reply_text('ID y precio deben ser números.')
        if price<=0:return await update.message.reply_text('El precio debe ser mayor a cero.')
        return await update.message.reply_text('🏪 Publicado en el mercado.' if sell_asset(uid,aid,price) else 'No pude publicarlo: revisa propiedad/estado del objeto.')
    rows=[x for x in list_assets(uid) if x[6]=='disponible']
    if not rows:return await update.message.reply_text('🎒 No tienes objetos disponibles para vender.')
    kb=[[InlineKeyboardButton(f"{RARE_EMOJI.get(r,'⚪')} {n}"+(f" #{sn}/{st}" if sn else ''),callback_data=f"soc:sell_pick:{a}")] for a,n,r,sn,st,v,e in rows[:30]]
    await update.message.reply_text('🏪 ¿Qué quieres vender?\n\nElige el objeto; después solo escribe el precio.',reply_markup=InlineKeyboardMarkup(kb))

async def comprarmercado(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not context.args:return await mercado(update,context)
    try:lid=int(context.args[0])
    except:return await update.message.reply_text('Venta inválida.')
    st,data=buy_market(update.effective_user.id,lid)
    if st=='ok':await update.message.reply_text(f"🤝 Compra cerrada: {data[0]} por {data[1]:,} PiPesos.")
    elif st=='money':await update.message.reply_text('💸 No tienes saldo suficiente.')
    else:await update.message.reply_text('Esa venta ya no está disponible.')

async def empenar(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if context.args:
        try:aid=int(context.args[0])
        except:return await update.message.reply_text('Objeto inválido.')
        st,data=pawn_asset(uid,aid)
        if st=='ok':return await update.message.reply_text(f"🏦 BANKIU aceptó {data[0]}.\n💰 Recibes {data[1]:,} PiPesos\n🧾 Para recuperarlo: {data[2]:,} PiPesos antes de 7 días.")
        return await update.message.reply_text('BANKIU no puede aceptar ese objeto en su estado actual.')
    rows=[x for x in list_assets(uid) if x[6]=='disponible']
    if not rows:return await update.message.reply_text('🎒 No tienes objetos disponibles para empeñar.')
    kb=[[InlineKeyboardButton(f"{RARE_EMOJI.get(r,'⚪')} {n}"+(f" #{sn}/{st}" if sn else ''),callback_data=f"soc:pawn_pick:{a}")] for a,n,r,sn,st,v,e in rows[:30]]
    await update.message.reply_text('🏦 BANKIU · EMPEÑO\n\nElige el objeto que quieres empeñar. PiBot te mostrará el resultado sin pedirte IDs.',reply_markup=InlineKeyboardMarkup(kb))

async def desempenar(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not context.args:return await update.message.reply_text('Uso: /desempenar ID_OBJETO')
    try:aid=int(context.args[0])
    except:return await update.message.reply_text('ID inválido.')
    st,data=redeem_asset(update.effective_user.id,aid)
    if st=='ok':await update.message.reply_text(f"🏦 Recuperaste {data[0]} pagando {data[1]:,} PiPesos.")
    elif st=='money':await update.message.reply_text('💸 No tienes suficiente saldo para recuperarlo.')
    else:await update.message.reply_text('No hay un empeño activo de ese objeto a tu nombre.')


async def process_social_input(update:Update, context:ContextTypes.DEFAULT_TYPE):
    mode=context.user_data.get('social_input')
    if mode!='sell_price' or not update.effective_message or not update.effective_message.text:return
    raw=update.effective_message.text.strip()
    if raw.lower()=='cancelar':
        context.user_data.pop('social_input',None);context.user_data.pop('social_sell_asset',None)
        await update.effective_message.reply_text('❌ Venta cancelada.');return
    try:price=int(raw.replace(',','').replace('_',''))
    except ValueError:return
    if price<=0:return await update.effective_message.reply_text('El precio debe ser mayor a cero.')
    aid=context.user_data.pop('social_sell_asset',None);context.user_data.pop('social_input',None)
    if not aid:return
    ok=sell_asset(update.effective_user.id,aid,price)
    await update.effective_message.reply_text(f'🏪 Publicado por {price:,} PiPesos.' if ok else '⚠️ Ese objeto ya no puede ponerse a la venta.')
