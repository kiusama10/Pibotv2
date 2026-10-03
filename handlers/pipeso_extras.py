from __future__ import annotations
import math, random, time
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection,_put_connection

BOXES={"mini":(5000,"📦 Caja Sumisa"),"pro":(15000,"🖤 Caja Dominante"),"elite":(40000,"👑 Caja Switch Élite")}
POTIONS={"money1":(5000,60,1.25,"🪙 Elixir de Fortuna x1.25"),"money3":(12000,180,1.25,"🪙 Elixir de Fortuna x1.25"),"xp1":(5000,60,1.50,"✨ Elixir de Experiencia x1.50"),"xp3":(12000,180,1.50,"✨ Elixir de Experiencia x1.50")}
BDSM_TITLES=["Collar de Medianoche","Dominante de Acero","Sumisión de Seda","Switch del Eclipse","Guardián del Aftercare","Dueño del Silencio","Reina del Protocolo","Consentimiento Sagrado","Cuerda Carmesí","Mirada Dominante","Entrega Absoluta","Señor del Shibari","Dama del Collar","Príncipe del Aftercare","Musa Sumisa","Dominio Nocturno"]
FONTS=["normal","bold","italic","script","double","mono","smallcaps","circled"]
FONT_LABELS={"normal":"Normal","bold":"𝐍𝐞𝐠𝐫𝐢𝐭𝐚","italic":"𝐼𝑡𝑎𝑙𝑖𝑐","script":"𝒮𝒸𝓇𝒾𝓅𝓉","double":"𝔻𝕠𝕓𝕝𝕖","mono":"𝙼𝚘𝚗𝚘","smallcaps":"ꜱᴍᴀʟʟᴄᴀᴘꜱ","circled":"Ⓒⓘⓡⓒⓛⓔⓓ"}
_last_activity={}

def ensure_extras_tables():
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS user_progression_tb(user_id bigint PRIMARY KEY,xp bigint NOT NULL DEFAULT 0,level int NOT NULL DEFAULT 1,updated_at timestamptz NOT NULL DEFAULT now())""")
        c.execute("""CREATE TABLE IF NOT EXISTS user_boosters_tb(user_id bigint NOT NULL,kind text NOT NULL,multiplier numeric NOT NULL,expires_at timestamptz NOT NULL,PRIMARY KEY(user_id,kind))""")
        c.execute("""CREATE TABLE IF NOT EXISTS user_box_assets_tb(asset_id bigserial PRIMARY KEY,user_id bigint NOT NULL,asset_type text NOT NULL,asset_code text NOT NULL,asset_name text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(user_id,asset_type,asset_code))""")
        c.execute("""CREATE TABLE IF NOT EXISTS user_profile_style_tb(user_id bigint PRIMARY KEY,font_code text NOT NULL DEFAULT 'normal',updated_at timestamptz NOT NULL DEFAULT now())""")
        c.execute("""CREATE TABLE IF NOT EXISTS victory_gif_tb(user_id bigint PRIMARY KEY,file_id text NOT NULL,message text NOT NULL DEFAULT '🏆 {nombre} celebra su victoria.',enabled_games text[] NOT NULL DEFAULT ARRAY['all']::text[],created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now())""")
        conn.commit()
    except Exception as e: conn.rollback(); print('[EXTRAS tables]',e)
    finally:_put_connection(conn)

def _charge(c,uid,amount):
    c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo>=%s RETURNING saldo",(amount,uid,amount)); return c.fetchone()

def active_multiplier(uid,kind):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT multiplier FROM user_boosters_tb WHERE user_id=%s AND kind=%s AND expires_at>NOW()",(uid,kind)); r=c.fetchone(); return float(r[0]) if r else 1.0
    finally:_put_connection(conn)

def generated_reward_amount(uid,base):
    return max(0,int(round(int(base)*active_multiplier(uid,'money'))))

def _level_for_xp(xp): return max(1,int(math.sqrt(max(0,xp)/100))+1)
def _level_reward(level): return ((max(1,level)-1)//5+1)*1000

def add_xp(uid,amount):
    amount=max(0,int(round(amount*active_multiplier(uid,'xp'))));
    if not amount:return None
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("INSERT INTO user_progression_tb(user_id,xp,level) VALUES(%s,0,1) ON CONFLICT DO NOTHING",(uid,)); c.execute("SELECT xp,level FROM user_progression_tb WHERE user_id=%s FOR UPDATE",(uid,)); xp,old=c.fetchone(); newxp=int(xp)+amount; new=_level_for_xp(newxp); bonus=0
        if new>old:
            for lv in range(old+1,new+1): bonus+=_level_reward(lv)
            c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(bonus,uid))
        c.execute("UPDATE user_progression_tb SET xp=%s,level=%s,updated_at=now() WHERE user_id=%s",(newxp,new,uid)); conn.commit(); return amount,old,new,bonus,newxp
    except Exception as e: conn.rollback(); print('[XP]',e); return None
    finally:_put_connection(conn)

async def xp_activity(update:Update,context:ContextTypes.DEFAULT_TYPE):
    u=update.effective_user; m=update.effective_message
    if not u or u.is_bot or not m or update.effective_chat.type=='private': return
    now=time.monotonic(); last=_last_activity.get(u.id,0)
    if now-last<20:return
    _last_activity[u.id]=now
    pts=2
    if m.video or m.animation: pts=8
    elif m.audio or m.voice: pts=7
    elif m.photo: pts=5
    elif m.document: pts=4
    res=add_xp(u.id,pts)
    if res and res[2]>res[1]:
        await m.reply_text(f"🎉 ¡Subiste a nivel {res[2]}!\n🪙 Bono de nivel: +{res[3]:,} PiPesos")

async def nivel(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT xp,level FROM user_progression_tb WHERE user_id=%s",(uid,)); r=c.fetchone() or (0,1)
    finally:_put_connection(conn)
    nxt=(int(r[1]))**2*100
    await update.effective_message.reply_text(f"✨ NIVEL {r[1]}\nXP: {r[0]:,} / {nxt:,}\n\nTexto +2 · foto +5 · audio/voz +7 · video/GIF +8 XP.\nLa actividad tiene anti-spam y las pociones de XP pueden multiplicarla.")

async def pociones(update:Update,context:ContextTypes.DEFAULT_TYPE):
    kb=[]
    for code,(price,mins,mult,name) in POTIONS.items(): kb.append([InlineKeyboardButton(f"{name} · {mins//60}h · {price:,}",callback_data=f'ex:pot:{code}')])
    await update.effective_message.reply_text("🧪 POCIONES\n\nLos potenciadores de PiPesos solo afectan recompensas NUEVAS creadas por PiBot; nunca transferencias, mercado, préstamos o apuestas entre usuarios.",reply_markup=InlineKeyboardMarkup(kb))

async def cajas(update:Update,context:ContextTypes.DEFAULT_TYPE):
    kb=[[InlineKeyboardButton(f"{name} · {price:,} PiPesos",callback_data=f'ex:box:{code}')] for code,(price,name) in BOXES.items()]
    await update.effective_message.reply_text("🎁 CAJAS MISTERIOSAS\n\nPueden contener títulos BDSM, tipografías de perfil y premios de PiPesos. Si sale un coleccionable que ya tienes, PiBot lo convierte en 2,000 PiPesos.",reply_markup=InlineKeyboardMarkup(kb))

def _roll_box(code):
    tier={'mini':0,'pro':1,'elite':2}[code]; x=random.random()
    if x < .34: return 'title',random.choice(BDSM_TITLES),random.choice(BDSM_TITLES)
    if x < .60: 
        f=random.choice(FONTS); return 'font',f,f'Tipografía {f}'
    money=random.choice(([1000,2000,3000],[3000,5000,8000],[8000,12000,20000])[tier]); return 'money',str(money),f'{money:,} PiPesos'

async def extras_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; p=q.data.split(':'); uid=q.from_user.id
    if p[1]=='font': return await font_callback(q,p[2])
    if p[1]=='pot':
        code=p[2]; price,mins,mult,name=POTIONS[code]; kind='xp' if code.startswith('xp') else 'money'; conn=_get_connection()
        try:
            c=conn.cursor();
            if not _charge(c,uid,price): conn.rollback(); return await q.answer('No tienes suficientes PiPesos.',show_alert=True)
            c.execute("""INSERT INTO user_boosters_tb(user_id,kind,multiplier,expires_at) VALUES(%s,%s,%s,NOW()+(%s||' minutes')::interval) ON CONFLICT(user_id,kind) DO UPDATE SET multiplier=EXCLUDED.multiplier,expires_at=GREATEST(user_boosters_tb.expires_at,NOW())+(%s||' minutes')::interval""",(uid,kind,mult,mins,mins)); conn.commit()
        finally:_put_connection(conn)
        return await q.answer(f'{name} activado por {mins//60}h.',show_alert=True)
    if p[1]=='box':
        code=p[2]; price,name=BOXES[code]; conn=_get_connection(); kind,val,label=_roll_box(code)
        try:
            c=conn.cursor();
            if not _charge(c,uid,price): conn.rollback(); return await q.answer('No tienes suficientes PiPesos.',show_alert=True)
            if kind=='money': c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(int(val),uid))
            elif kind=='potion':
                _,mins,mult,pname=POTIONS[val]; k='xp' if val.startswith('xp') else 'money'; c.execute("""INSERT INTO user_boosters_tb(user_id,kind,multiplier,expires_at) VALUES(%s,%s,%s,NOW()+(%s||' minutes')::interval) ON CONFLICT(user_id,kind) DO UPDATE SET multiplier=EXCLUDED.multiplier,expires_at=GREATEST(user_boosters_tb.expires_at,NOW())+(%s||' minutes')::interval""",(uid,k,mult,mins,mins))
            elif kind=='title':
                code='box_'+''.join(ch.lower() if ch.isalnum() else '_' for ch in val).strip('_')
                c.execute("SELECT 1 FROM social_assets_tb WHERE propietario_id=%s AND asset_type='titulo' AND code=%s LIMIT 1",(uid,code))
                if c.fetchone():
                    c.execute("UPDATE usuarios_tb SET saldo=saldo+2000 WHERE id_user=%s",(uid,)); label+=' · repetido → +2,000 PiPesos'
                else:
                    c.execute("INSERT INTO social_assets_tb(asset_type,code,nombre,rareza,valor_base,propietario_id,origen) VALUES('titulo',%s,%s,'caja',0,%s,'caja_misteriosa')",(code,val,uid))
            else:
                c.execute("INSERT INTO user_box_assets_tb(user_id,asset_type,asset_code,asset_name) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",(uid,kind,val,label))
                if c.rowcount==0: c.execute("UPDATE usuarios_tb SET saldo=saldo+2000 WHERE id_user=%s",(uid,)); label+=' · repetido → +2,000 PiPesos'
            conn.commit()
        finally:_put_connection(conn)
        await q.answer('Caja abierta 🎁',show_alert=True); return await q.message.reply_text(f"🎁 Abriste {name}\n✨ Te salió: {label}")

async def tipografias(update:Update,context:ContextTypes.DEFAULT_TYPE):
    kb=[[InlineKeyboardButton(f'🔤 {FONT_LABELS.get(f,f)}',callback_data=f'ex:font:{f}')] for f in FONTS]
    await update.effective_message.reply_text('🔤 TIPOGRAFÍAS DE PERFIL\n\nElige el estilo que quieras. Cada cambio cuesta 5,000 PiPesos y se cobra únicamente al tocar la opción.',reply_markup=InlineKeyboardMarkup(kb))

async def font_callback(q,code):
    uid=q.from_user.id
    if code not in FONTS: return await q.answer('Tipografía inválida.',show_alert=True)
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT font_code FROM user_profile_style_tb WHERE user_id=%s FOR UPDATE",(uid,)); old=c.fetchone(); old_code=old[0] if old else 'normal'
        if old_code==code: conn.rollback(); return await q.answer('Ya estás usando esa tipografía.',show_alert=True)
        c.execute("UPDATE usuarios_tb SET saldo=saldo-5000 WHERE id_user=%s AND saldo>=5000",(uid,))
        if c.rowcount!=1: conn.rollback(); return await q.answer('Necesitas 5,000 PiPesos para cambiar la tipografía.',show_alert=True)
        c.execute("INSERT INTO user_profile_style_tb(user_id,font_code) VALUES(%s,%s) ON CONFLICT(user_id) DO UPDATE SET font_code=EXCLUDED.font_code,updated_at=now()",(uid,code)); conn.commit()
    except Exception:
        conn.rollback(); return await q.answer('No pude cambiar la tipografía.',show_alert=True)
    finally:_put_connection(conn)
    await q.answer(f'Tipografía {code} equipada · -5,000 PiPesos.',show_alert=True)

async def gifvictoria(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type!='private': return await update.effective_message.reply_text('🏆 Configura tu celebración por privado con PiBot.')
    uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT file_id,message,enabled_games FROM victory_gif_tb WHERE user_id=%s",(uid,)); r=c.fetchone()
    finally:_put_connection(conn)
    price=30000 if r else 80000; games=(r[2] if r else ['all'])
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('🎞️ Subir/cambiar GIF',callback_data='vg:gif'),InlineKeyboardButton('💬 Cambiar texto',callback_data='vg:text')],[InlineKeyboardButton('🎮 Elegir juegos',callback_data='vg:games'),InlineKeyboardButton('👁 Vista previa',callback_data='vg:preview')],[InlineKeyboardButton('🗑️ Quitar celebración',callback_data='vg:remove')]])
    await update.effective_message.reply_text(f"🏆 TU CELEBRACIÓN DE VICTORIA\n\nEstado: {'✅ configurada' if r else '❌ sin configurar'}\nJuegos: {', '.join(games)}\nPrecio de {'cambio' if r else 'primera configuración'}: {price:,} PiPesos\n\nTodo se configura aquí con botones.",reply_markup=kb)

GAMES=[('all','🌐 Todos'),('lucha','⚔️ Lucha'),('dibujo','🎨 Dibujo'),('tortugas','🐢 Tortugas'),('blackjack','🃏 Blackjack'),('dardos','🎯 Dardos'),('boliche','🎳 Boliche'),('aliados','🤝 Aliados')]
async def victory_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; uid=q.from_user.id; action=q.data.split(':')[1]
    if q.message.chat.type!='private': return await q.answer('Ábrelo por privado.',show_alert=True)
    if action in ('gif','text'):
        context.user_data['vg_wait']=action; return await q.answer('Ahora envíame el GIF.' if action=='gif' else 'Ahora envíame el texto. Puedes usar {nombre}.',show_alert=True)
    if action=='games':
        kb=[[InlineKeyboardButton(label,callback_data=f'vg:toggle:{code}')] for code,label in GAMES]; return await q.message.reply_text('🎮 ¿Dónde debe aparecer?',reply_markup=InlineKeyboardMarkup(kb))
    if action=='toggle': return
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT file_id,message,enabled_games FROM victory_gif_tb WHERE user_id=%s",(uid,)); r=c.fetchone()
    finally:_put_connection(conn)
    if action=='preview':
        if not r:return await q.answer('Primero configura un GIF.',show_alert=True)
        return await q.message.reply_animation(r[0],caption=r[1].replace('{nombre}',q.from_user.first_name or 'Jugador'))
    if action=='remove':
        conn=_get_connection(); c=conn.cursor(); c.execute('DELETE FROM victory_gif_tb WHERE user_id=%s',(uid,)); conn.commit(); _put_connection(conn); return await q.answer('Celebración quitada.',show_alert=True)

async def victory_toggle_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; uid=q.from_user.id; code=q.data.split(':')[2]; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute('SELECT enabled_games FROM victory_gif_tb WHERE user_id=%s FOR UPDATE',(uid,)); r=c.fetchone()
        if not r: conn.rollback(); return await q.answer('Primero configura tu GIF.',show_alert=True)
        games=list(r[0] or [])
        if code=='all': games=['all']
        else:
            games=[x for x in games if x!='all']; games.remove(code) if code in games else games.append(code)
            if not games: games=['all']
        c.execute('UPDATE victory_gif_tb SET enabled_games=%s,updated_at=now() WHERE user_id=%s',(games,uid)); conn.commit()
    finally:_put_connection(conn)
    await q.answer('Juegos actualizados: '+', '.join(games),show_alert=True)

async def victory_input(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type!='private':return
    mode=context.user_data.get('vg_wait');
    if not mode:return
    uid=update.effective_user.id; m=update.effective_message
    if mode=='gif':
        if not m.animation:return await m.reply_text('Envíame un GIF/animación de Telegram.')
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute('SELECT 1 FROM victory_gif_tb WHERE user_id=%s',(uid,)); exists=c.fetchone(); price=30000 if exists else 80000
            if not _charge(c,uid,price): conn.rollback(); return await m.reply_text(f'Necesitas {price:,} PiPesos.')
            c.execute("""INSERT INTO victory_gif_tb(user_id,file_id) VALUES(%s,%s) ON CONFLICT(user_id) DO UPDATE SET file_id=EXCLUDED.file_id,updated_at=now()""",(uid,m.animation.file_id)); conn.commit(); context.user_data.pop('vg_wait',None)
        finally:_put_connection(conn)
        return await m.reply_text(f'🏆 GIF guardado. Se cobraron {price:,} PiPesos. El texto lo puedes cambiar gratis desde /gifvictoria.')
    txt=(m.text or '').strip()
    if not txt:return await m.reply_text('Envíame el texto que quieres mostrar.')
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute('UPDATE victory_gif_tb SET message=%s,updated_at=now() WHERE user_id=%s RETURNING user_id',(txt[:500],uid)); ok=c.fetchone(); conn.commit()
    finally:_put_connection(conn)
    if not ok:return await m.reply_text('Primero configura tu GIF desde /gifvictoria.')
    context.user_data.pop('vg_wait',None); await m.reply_text('💬 Texto de victoria actualizado.')

async def send_victory(context,uid,game,chat_id,thread_id=None,name=None):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute('SELECT file_id,message,enabled_games FROM victory_gif_tb WHERE user_id=%s',(uid,)); r=c.fetchone()
    finally:_put_connection(conn)
    if not r or ('all' not in r[2] and game not in r[2]):return
    try: await context.bot.send_animation(chat_id,r[0],caption=r[1].replace('{nombre}',name or 'Jugador'),message_thread_id=thread_id)
    except Exception: pass
