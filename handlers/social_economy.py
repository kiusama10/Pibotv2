import hashlib
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from telegram import Update
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
GIFTS = {
    "rosa":("🌹 Rosa","comun",2000,["Un clásico que todavía funciona.","PiBot certifica que hubo intención bonita."]),
    "chocolates":("🍫 Chocolates","comun",3000,["Dulces, caros y sin necesidad de compartir.","El soborno emocional ha sido entregado."]),
    "peluche":("🧸 Peluche","comun",5000,["Para abrazarlo cuando el chat se pone raro.","Nivel de ternura peligrosamente alto."]),
    "patada":("🦵 Patada","comun",500,["La diplomacia abandonó el chat.","El cariño se demuestra de formas cuestionables."]),
    "chanclazo":("🩴 Chanclazo","comun",700,["Precisión legendaria. Las abuelas estarían orgullosas.","PiBot escuchó el impacto desde el servidor."]),
    "mordida":("🦷 Mordida","comun",1000,["No preguntaremos por qué. 👀","Una demostración de afecto con dientes."]),
    "collar":("⛓️ Collar","raro",15000,["Hay regalos que vienen con ciertas implicaciones. 👀","El grupo seguramente tendrá preguntas."]),
    "cuerda":("🪢 Cuerda","raro",12000,["Decorativa, coleccionable y sospechosamente temática.","PiBot recomienda negociar hasta los regalos."]),
    "antifaz":("🎭 Antifaz","raro",10000,["Misterio desbloqueado.","No mejora el sigilo, pero se ve genial."]),
    "campanita_pet":("🔔 Campanita de Pet","epico",30000,["Ahora será difícil perderle la pista.","*tin tin* El caos tiene sonido propio."]),
    "corona_dom":("👑 Corona Dom/Domme","epico",50000,["Autoridad cosmética: +100. Autoridad real: requiere consentimiento.","La corona llegó; el ego probablemente también."]),
    "anillo_obsidiana":("💍 Anillo de Obsidiana","legendario",100000,["Un regalo oscuro para alguien difícil de ignorar.","BANKIU ya lo está mirando con interés."]),
}
RARE_EMOJI={"comun":"⚪","raro":"🔵","epico":"🟣","legendario":"🟡","mitico":"🔴"}

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

def buy_gift(sender,target,code,anonymous=False,private=False):
    item=GIFTS.get(code)
    if not item:return "missing",None
    name,rarity,price,lines=item; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo>=%s",(price,sender,price))
        if c.rowcount!=1:conn.rollback();return "money",None
        c.execute("INSERT INTO social_assets_tb(asset_type,code,nombre,rareza,valor_base,propietario_id,origen,regalo_anonimo,regalo_privado,regalado_por) VALUES('regalo',%s,%s,%s,%s,%s,'regalo',%s,%s,%s) RETURNING asset_id",(code,name,rarity,price,target,anonymous,private,sender)); aid=c.fetchone()[0]
        c.execute("INSERT INTO social_asset_history_tb(asset_id,de_user,a_user,accion,precio) VALUES(%s,%s,%s,'regalo',%s)",(aid,sender,target,price))
        conn.commit();return "ok",(aid,name,rarity,price,random.choice(lines))
    except Exception as e:conn.rollback();print('[SOCIAL] gift',e);return "error",None
    finally:_put_connection(conn)

def list_assets(uid,atype=None):
    conn=_get_connection()
    try:
        c=conn.cursor(); q="SELECT asset_id,nombre,rareza,serial_no,serial_total,valor_base,estado FROM social_assets_tb WHERE propietario_id=%s"; args=[uid]
        if atype:q+=" AND asset_type=%s";args.append(atype)
        q+=" ORDER BY creado_en DESC LIMIT 30";c.execute(q,args);return c.fetchall()
    finally:_put_connection(conn)

def list_market():
    conn=_get_connection()
    try:
        c=conn.cursor();c.execute("SELECT m.listing_id,a.nombre,a.rareza,a.serial_no,a.serial_total,m.precio,m.vendedor_id FROM social_market_tb m JOIN social_assets_tb a ON a.asset_id=m.asset_id WHERE m.estado='activo' ORDER BY m.creado_en DESC LIMIT 20");return c.fetchall()
    finally:_put_connection(conn)

def sell_asset(uid,aid,price):
    conn=_get_connection()
    try:
        c=conn.cursor();c.execute("SELECT estado,transferible FROM social_assets_tb WHERE asset_id=%s AND propietario_id=%s FOR UPDATE",(aid,uid));r=c.fetchone()
        if not r or r[0]!='disponible' or not r[1]:conn.rollback();return False
        c.execute("INSERT INTO social_market_tb(asset_id,vendedor_id,precio) VALUES(%s,%s,%s)",(aid,uid,price));c.execute("UPDATE social_assets_tb SET estado='mercado' WHERE asset_id=%s",(aid,));conn.commit();return True
    except Exception as e:conn.rollback();print('[SOCIAL] sell',e);return False
    finally:_put_connection(conn)

def buy_market(uid,lid):
    conn=_get_connection()
    try:
        c=conn.cursor();c.execute("SELECT m.asset_id,m.vendedor_id,m.precio,a.nombre FROM social_market_tb m JOIN social_assets_tb a ON a.asset_id=m.asset_id WHERE m.listing_id=%s AND m.estado='activo' FOR UPDATE",(lid,));r=c.fetchone()
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
        c=conn.cursor();c.execute("SELECT valor_base,nombre,rareza,estado FROM social_assets_tb WHERE asset_id=%s AND propietario_id=%s FOR UPDATE",(aid,uid));r=c.fetchone()
        if not r or r[3]!='disponible':conn.rollback();return 'missing',None
        value,name,rarity,_=r
        ratios={'comun':.25,'raro':.35,'epico':.40,'legendario':.45,'mitico':.50};principal=max(100,int(value*ratios.get(rarity,.25)));payoff=(principal*110+99)//100
        c.execute("UPDATE social_assets_tb SET estado='empenado' WHERE asset_id=%s",(aid,));c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(principal,uid));c.execute("INSERT INTO bankiu_pawns_tb(asset_id,user_id,principal,payoff,vence_en) VALUES(%s,%s,%s,%s,NOW()+INTERVAL '7 days')",(aid,uid,principal,payoff));c.execute("INSERT INTO social_asset_history_tb(asset_id,de_user,a_user,accion,precio) VALUES(%s,%s,%s,'empeno',%s)",(aid,uid,uid,principal));conn.commit();return 'ok',(name,principal,payoff)
    except Exception as e:conn.rollback();print('[BANKIU] pawn',e);return 'error',None
    finally:_put_connection(conn)

def redeem_asset(uid,aid):
    conn=_get_connection()
    try:
        c=conn.cursor();c.execute("SELECT p.payoff,a.nombre FROM bankiu_pawns_tb p JOIN social_assets_tb a ON a.asset_id=p.asset_id WHERE p.asset_id=%s AND p.user_id=%s AND p.estado='activo' FOR UPDATE",(aid,uid));r=c.fetchone()
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

async def titulos(update:Update,context:ContextTypes.DEFAULT_TYPE):
    key,end=ensure_title_rotation();conn=_get_connection()
    try:
        c=conn.cursor();c.execute("SELECT code,nombre,rareza,precio,stock_total,stock_vendido FROM title_rotation_stock_tb WHERE rotation_key=%s ORDER BY CASE rareza WHEN 'mitico' THEN 1 WHEN 'legendario' THEN 2 WHEN 'epico' THEN 3 WHEN 'raro' THEN 4 ELSE 5 END,precio",(key,));rows=c.fetchall()
    finally:_put_connection(conn)
    left=max(timedelta(),end-datetime.now(timezone.utc));h=int(left.total_seconds()//3600);m=int(left.total_seconds()%3600//60)
    lines=[f"🏷️ TIENDA DE TÍTULOS · cambia en {h:02d}h {m:02d}m"]
    for code,name,r,p,total,sold in rows:
        stock='∞' if total is None else f'{max(0,total-sold)}/{total}'
        lines.append(f"{RARE_EMOJI.get(r,'⚪')} {name} — {p:,} PP · stock {stock}\n  /comprartitulo {code}")
    await update.message.reply_text('\n'.join(lines))

async def comprartitulo(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not context.args:return await update.message.reply_text('Uso: /comprartitulo codigo')
    st,data=buy_title(update.effective_user.id,context.args[0].lower())
    if st=='ok':
        aid,name,r,serial,total,price=data;ser=f' #{serial}/{total}' if total else ''
        await update.message.reply_text(f"✨ Título adquirido: {name}{ser}\n{RARE_EMOJI.get(r,'')} {r.title()} · {price:,} PiPesos\nID de colección: {aid}")
    elif st=='money':await update.message.reply_text('💸 No tienes suficientes PiPesos.')
    elif st=='soldout':await update.message.reply_text('😈 Llegaste tarde: esa edición se agotó.')
    else:await update.message.reply_text('Ese título no está en la rotación actual.')

async def regalos(update:Update,context:ContextTypes.DEFAULT_TYPE):
    lines=['🎁 CATÁLOGO DE REGALOS']
    for code,(name,r,p,_) in GIFTS.items():lines.append(f"{RARE_EMOJI.get(r,'')} {name} — {p:,} PP · `{code}`")
    lines.append('\n/regalo @usuario codigo · agrega `anonimo` y/o `privado` si quieres.\nTambién funciona respondiendo al mensaje de alguien.')
    await update.message.reply_text('\n'.join(lines),parse_mode='Markdown')

async def regalo(update:Update,context:ContextTypes.DEFAULT_TYPE):
    raw=list(context.args); anonymous=False; private=(update.effective_chat.type=='private')
    clean=[]
    for x in raw:
        low=x.lower()
        if low in ('anonimo','anónimo'): anonymous=True
        elif low in ('privado','pv'): private=True
        else: clean.append(x)
    uid,name,args=_target(update,clean)
    if not uid or not args:return await update.message.reply_text('Uso: /regalo @usuario rosa [anonimo] [privado]\nO responde: /regalo rosa anonimo')
    if uid==update.effective_user.id:return await update.message.reply_text('😂 Regalarte cosas tú mismo no cuenta.')
    st,data=buy_gift(update.effective_user.id,uid,args[0].lower(),anonymous,private)
    if st=='ok':
        aid,gift,r,price,line=data
        sender='Alguien' if anonymous else update.effective_user.first_name
        text=f"🎁 {sender} te regaló {gift}.\n{line}\n💎 {r.title()} · Coleccionable #{aid}"
        delivered=False
        if private:
            try:
                await context.bot.send_message(uid,text); delivered=True
                await context.bot.send_message(update.effective_user.id,f"✅ Regalo privado enviado a {name}. 💸 {price:,} PiPesos.")
            except Exception:
                # The asset remains valid; Telegram may refuse a DM if the recipient never opened the bot.
                await update.message.reply_text(f"🎁 Regalo comprado por {price:,} PiPesos, pero Telegram no me dejó avisarle por PV. El objeto sí quedó en su colección #{aid}.")
        else:
            await update.message.reply_text(f"🎁 {sender} le regaló {gift} a {name}.\n{line}\n💸 {price:,} PiPesos · Coleccionable #{aid}")
    elif st=='money':await update.message.reply_text('💸 Te faltan PiPesos para ese regalo.')
    else:await update.message.reply_text('No encuentro ese regalo. Mira /regalos.')

async def misregalos(update:Update,context:ContextTypes.DEFAULT_TYPE):
    rows=list_assets(update.effective_user.id,'regalo')
    if not rows:return await update.message.reply_text('🎁 Aún no tienes regalos coleccionables.')
    await update.message.reply_text('🎁 TUS REGALOS\n'+'\n'.join(f"#{a} · {n} · {RARE_EMOJI.get(r,'')} {r} · {v:,} PP · {e}" for a,n,r,_,_,v,e in rows))

async def mistitulos(update:Update,context:ContextTypes.DEFAULT_TYPE):
    rows=list_assets(update.effective_user.id,'titulo')
    if not rows:return await update.message.reply_text('🏷️ Aún no tienes títulos.')
    await update.message.reply_text('🏷️ TUS TÍTULOS\n'+'\n'.join(f"#{a} · {n}"+(f" #{sn}/{st}" if sn else '')+f" · {RARE_EMOJI.get(r,'')} {r} · {e}" for a,n,r,sn,st,_,e in rows))

async def mercado(update:Update,context:ContextTypes.DEFAULT_TYPE):
    rows=list_market()
    if not rows:return await update.message.reply_text('🏪 El mercado está vacío.')
    await update.message.reply_text('🏪 MERCADO ENTRE USUARIOS\n'+'\n'.join(f"Venta #{lid} · {n}"+(f" #{sn}/{st}" if sn else '')+f" · {RARE_EMOJI.get(r,'')} · {p:,} PP\n/comprarmercado {lid}" for lid,n,r,sn,st,p,_ in rows))

async def vender(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if len(context.args)<2:return await update.message.reply_text('Uso: /vender ID_OBJETO PRECIO')
    try:aid=int(context.args[0]);price=int(context.args[1])
    except:return await update.message.reply_text('ID y precio deben ser números.')
    if price<=0:return await update.message.reply_text('El precio debe ser mayor a cero.')
    await update.message.reply_text('🏪 Publicado en el mercado.' if sell_asset(update.effective_user.id,aid,price) else 'No pude publicarlo: revisa propiedad/estado del objeto.')

async def comprarmercado(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not context.args:return await update.message.reply_text('Uso: /comprarmercado ID_VENTA')
    try:lid=int(context.args[0])
    except:return await update.message.reply_text('ID inválido.')
    st,data=buy_market(update.effective_user.id,lid)
    if st=='ok':await update.message.reply_text(f"🤝 Compra cerrada: {data[0]} por {data[1]:,} PiPesos. El objeto cambió de propietario sin duplicarse.")
    elif st=='money':await update.message.reply_text('💸 No tienes saldo suficiente.')
    else:await update.message.reply_text('Esa venta ya no está disponible.')

async def empenar(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not context.args:return await update.message.reply_text('Uso: /empenar ID_OBJETO')
    try:aid=int(context.args[0])
    except:return await update.message.reply_text('ID inválido.')
    st,data=pawn_asset(update.effective_user.id,aid)
    if st=='ok':await update.message.reply_text(f"🏦 BANKIU aceptó {data[0]}.\n💰 Recibes {data[1]:,} PiPesos\n🧾 Para recuperarlo: {data[2]:,} PiPesos antes de 7 días.\nEl objeto queda bloqueado mientras esté empeñado.")
    else:await update.message.reply_text('BANKIU no puede aceptar ese objeto en su estado actual.')

async def desempenar(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not context.args:return await update.message.reply_text('Uso: /desempenar ID_OBJETO')
    try:aid=int(context.args[0])
    except:return await update.message.reply_text('ID inválido.')
    st,data=redeem_asset(update.effective_user.id,aid)
    if st=='ok':await update.message.reply_text(f"🏦 Recuperaste {data[0]} pagando {data[1]:,} PiPesos.")
    elif st=='money':await update.message.reply_text('💸 No tienes suficiente saldo para recuperarlo.')
    else:await update.message.reply_text('No hay un empeño activo de ese objeto a tu nombre.')
