from __future__ import annotations
import math, random, time, asyncio
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection,_put_connection, get_id_user
from src.utils.seasonal import current_season
from src.utils.root_owner import ensure_root_identity

SEASON_BOX_NAMES={
    "normal": {"epic":"💜 Caja Épica","legendary":"🌟 Caja Legendaria"},
    "halloween": {"epic":"🎃 Cofre Épico de Halloween","legendary":"🦇 Cofre Legendario de Halloween"},
    "dia_muertos": {"epic":"🌼 Cofre Épico del Mictlán","legendary":"💀 Cofre Legendario de las Ánimas"},
    "navidad": {"epic":"❄️ Cofre Épico Invernal","legendary":"🎄 Cofre Legendario de Navidad"},
    "san_valentin": {"epic":"💘 Cofre Épico del Corazón","legendary":"👑 Cofre Legendario del Vínculo"},
}
# Se conservan los precios de las dos cajas superiores del sistema anterior.
BOX_PRICES={"epic":15000,"legendary":40000}
def current_boxes():
    names=SEASON_BOX_NAMES.get(current_season(),SEASON_BOX_NAMES["normal"])
    return {k:(BOX_PRICES[k],names[k]) for k in ("epic","legendary")}

POTIONS={"money1":(5000,60,1.25,"🪙 Elixir de Fortuna x1.25"),"money3":(12000,180,1.25,"🪙 Elixir de Fortuna x1.25"),"xp1":(5000,60,1.50,"✨ Elixir de Experiencia x1.50"),"xp3":(12000,180,1.50,"✨ Elixir de Experiencia x1.50")}
_GENERAL_TITLES=[
    "Leyenda del Clan","Rey del Caos","Reina del Caos","Señor de la Noche","Dama de la Noche",
    "Dueño del After","Mente Maestra","Corazón de Acero","Alma Rebelde","Último en Pie",
    "Emperador de la Traición","Emperatriz de la Traición","Tirano del Dado","Diosa de la Suerte",
    "Señor de los PiPesos","Magnate del Clan","Coleccionista Supremo","Fantasma del Chat","Insomne Oficial",
    "Rey del Meme","Reina del Meme","Drama Premium","Caos Certificado","Problema Favorito","Mala Influencia",
    "Santo del Desmadre","Villano con Encanto","Héroe por Accidente","NPC Legendario","Jefe Secreto",
    "Boss Final","Plot Twist Viviente","Main Character","Antiheroína","Antihéroe","Rompecorazones",
    "Corazón Blindado","Amor de Medianoche","Tentación Oficial","Mirada Peligrosa","Sonrisa Criminal",
    "Ángel Caído","Demonio Elegante","Vampiro de Medianoche","Bruja del Eclipse","Hechicero del Caos",
    "Guardián del Eclipse","Heredero de Obsidiana","Corona Carmesí","Luna Negra","Sol de Medianoche",
    "Fénix Eterno","Dragón Dorado","Lobo de Plata","Cuervo Real","Serpiente de Jade","Kitsune Celestial",
    "Samurái del Chat","Ronin Digital","Pirata del Clan","Capitán del Caos","Comandante Supremo",
    "Maestro del Juego","Reina del Casino","Rey del Casino","Amo del Blackjack","Señora de la Ruleta",
    "Francotirador de Dardos","Rey del Boliche","Domador de Tortugas","Asesino Fantasma","Detective del Clan",
    "Sabio del Quiz","Enciclopedia Humana","Respuesta Final","Cerebro Galáctico","Dato Inútil Supremo",
    "DJ de Medianoche","Rockstar del Clan","Alma Ochentera","Metal de Corazón","Pop Star Secreta",
    "Dueño del Playlist","Himno Viviente","Nota Prohibida","Ritmo Salvaje","Leyenda del Karaoke",
    "Guardián del Consentimiento","Maestro del Protocolo","Reina del Aftercare","Switch del Eclipse",
    "Collar de Medianoche","Cuerda Carmesí","Dominio Nocturno","Entrega de Obsidiana","Límite Sagrado",
    "Rey del Silencio","Reina del Protocolo","Guardián de la Confianza","Señor del Shibari","Dama del Collar",
    "One Winged Angel","Cowboy del Caos","Aerial Legend","Best Bout Machine","Rainmaker del Clan",
    "Campeón Sin Corona","Icono del Main Event","Fenómeno del Ring","Rebel Heart","Final Boss del Ring",
]
_SEASON_TITLES={
    "halloween":["Rey Calabaza","Reina Calabaza","Conde de Halloween","Condesa de Halloween","Señor del Cementerio","Dama del Cementerio","Fantasma VIP","Bruja Escarlata","Hechicero de Medianoche","Dueño de la Cripta","Reina de las Sombras","Pesadilla del Clan","Cazador de Fantasmas","Alma en Pena Premium","Monstruo Favorito","Vampiro Carmesí","Hijo de la Noche","Hija de la Noche","Guardián de la Cripta","Corona Maldita"],
    "dia_muertos":["Guardián del Mictlán","Reina Cempasúchil","Rey Cempasúchil","Alma Eterna","Calavera de Oro","Catrina Imperial","Catrín de Medianoche","Señor de las Ánimas","Dama de las Ánimas","Memoria Eterna"],
    "navidad":["Rey del Invierno","Reina del Invierno","Krampus VIP","Estrella Invernal","Guardián de la Nieve","Milagro de Medianoche","Espíritu Navideño","Corona de Hielo","Duende Legendario","Noche Eterna"],
    "san_valentin":["Cupido Rebelde","Corazón Legendario","Amor Caótico","Flechazo Mortal","Dueño de Corazones","Reina de Corazones","Romance de Medianoche","Tentación de Febrero","Corazón de Obsidiana","Vínculo Eterno"],
}
def title_pool():
    return list(dict.fromkeys(_GENERAL_TITLES + _SEASON_TITLES.get(current_season(),[])))
BDSM_TITLES=_GENERAL_TITLES  # compatibilidad con cualquier import anterior

FONT_BASES=["normal","bold","italic","script","double","mono","smallcaps","circled"]
FONT_DECORATORS=[
    ("plain","{t}"),("stars","✦ {t} ✦"),("spark","✨ {t} ✨"),("moon","☾ {t} ☽"),("heart","♡ {t} ♡"),
    ("diamond","◇ {t} ◇"),("crown","♛ {t} ♛"),("chain","⛓ {t} ⛓"),("dot","• {t} •"),("wave","〜 {t} 〜"),
    ("cross","† {t} †"),("flower","❀ {t} ❀"),("arrow","➤ {t} ◀"),("bracket","【{t}】"),("angle","《{t}》"),
]
FONTS=[f"{base}__{deco}" for base in FONT_BASES for deco,_ in FONT_DECORATORS]  # 120 opciones
_BASE_LABELS={"normal":"Normal","bold":"𝐍𝐞𝐠𝐫𝐢𝐭𝐚","italic":"𝐼𝑡𝑎𝑙𝑖𝑐","script":"𝒮𝒸𝓇𝒾𝓅𝓉","double":"𝔻𝕠𝕓𝕝𝕖","mono":"𝙼𝚘𝚗𝚘","smallcaps":"ꜱᴍᴀʟʟᴄᴀᴘꜱ","circled":"Ⓒⓘⓡⓒⓛⓔⓓ"}
_DECO=dict(FONT_DECORATORS)
FONT_LABELS={code:_DECO[code.split('__',1)[1]].format(t=_BASE_LABELS[code.split('__',1)[0]]) for code in FONTS}
FONT_PAGE_SIZE=12

def style_text(text,code):
    base,deco=(code.split('__',1)+['plain'])[:2] if '__' in code else (code,'plain')
    maps={
      "bold":("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789","𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟡"),
      "mono":("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789","𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"),
      "circled":("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789","ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ⓪①②③④⑤⑥⑦⑧⑨"),
      "italic":("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz","𝐴𝐵𝐶𝐷𝐸𝐹𝐺𝐻𝐼𝐽𝐾𝐿𝑀𝑁𝑂𝑃𝑄𝑅𝑆𝑇𝑈𝑉𝑊𝑋𝑌𝑍𝑎𝑏𝑐𝑑𝑒𝑓𝑔ℎ𝑖𝑗𝑘𝑙𝑚𝑛𝑜𝑝𝑞𝑟𝑠𝑡𝑢𝑣𝑤𝑥𝑦𝑧"),
      "script":("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz","𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥𝒦ℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏"),
      "double":("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789","𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡")}
    out=str(text)
    if base in maps:
        a,b=maps[base]; out=out.translate(str.maketrans(a,b))
    elif base=='smallcaps': out=out.translate(str.maketrans("abcdefghijklmnopqrstuvwxyz","ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘqʀꜱᴛᴜᴠᴡxʏᴢ"))
    return _DECO.get(deco,"{t}").format(t=out)

def owned_fonts(uid):
    """Tipografías desbloqueadas por cajas. Normal y la actualmente equipada se conservan siempre."""
    owned={"normal__plain"}
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("SELECT asset_code FROM user_box_assets_tb WHERE user_id=%s AND asset_type='font'",(uid,))
        
        for r in c.fetchall():
            if not r: continue
            code=r[0]
            if code in FONTS: owned.add(code)
            elif f"{code}__plain" in FONTS: owned.add(f"{code}__plain")
        c.execute("SELECT font_code FROM user_profile_style_tb WHERE user_id=%s",(uid,))
        r=c.fetchone()
        if r:
            current=r[0]
            if current in FONTS: owned.add(current)
            elif f"{current}__plain" in FONTS: owned.add(f"{current}__plain")
    except Exception:
        pass
    finally:
        _put_connection(conn)
    return [f for f in FONTS if f in owned]

def font_markup(page=0,back_callback=None,uid=None):
    available=owned_fonts(uid) if uid is not None else FONTS
    pages=max(1,(len(available)+FONT_PAGE_SIZE-1)//FONT_PAGE_SIZE); page=max(0,min(page,pages-1)); subset=available[page*FONT_PAGE_SIZE:(page+1)*FONT_PAGE_SIZE]
    kb=[[InlineKeyboardButton(FONT_LABELS[c],callback_data=f'ex:font:{c}')] for c in subset]
    nav=[]
    if page>0: nav.append(InlineKeyboardButton('⬅️',callback_data=f'ex:fontpage:{page-1}'))
    nav.append(InlineKeyboardButton(f'{page+1}/{pages}',callback_data='ex:fontnoop'))
    if page<pages-1: nav.append(InlineKeyboardButton('➡️',callback_data=f'ex:fontpage:{page+1}'))
    kb.append(nav)
    if back_callback: kb.append([InlineKeyboardButton('⬅️ Volver',callback_data=back_callback)])
    return InlineKeyboardMarkup(kb)
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
        c.execute("""CREATE TABLE IF NOT EXISTS daily_luck_tb(user_id BIGINT NOT NULL,play_date DATE NOT NULL,choice SMALLINT,results_json TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(user_id,play_date))""")
        c.execute("""CREATE TABLE IF NOT EXISTS daily_basketball_tb(user_id BIGINT NOT NULL,play_date DATE NOT NULL,plays INT NOT NULL DEFAULT 0,made INT NOT NULL DEFAULT 0,net BIGINT NOT NULL DEFAULT 0,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(user_id,play_date))""")
        c.execute("""CREATE TABLE IF NOT EXISTS challenge_weekly_points_tb(week_start DATE NOT NULL,user_id BIGINT NOT NULL,points INT NOT NULL DEFAULT 0,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(week_start,user_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS challenge_weekly_audit_tb(audit_id BIGSERIAL PRIMARY KEY,week_start DATE NOT NULL,target_id BIGINT NOT NULL,actor_id BIGINT NOT NULL,delta INT NOT NULL,before_points INT NOT NULL,after_points INT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        c.execute("""CREATE TABLE IF NOT EXISTS challenge_weekly_payouts_tb(week_start DATE PRIMARY KEY,paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),first_id BIGINT,second_id BIGINT,third_id BIGINT)""")
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
    """Open the boxes menu in private. Group use only redirects to PV."""
    uid=update.effective_user.id
    if update.effective_chat.type!='private':
        try:
            await context.bot.send_message(chat_id=uid,text='🎁 Me pediste tus cajas. Elige cuál quieres abrir:',reply_markup=_boxes_markup())
        except Exception:
            return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start y después vuelve a usar /cajas.')
        return await update.effective_message.reply_text('📩 Te mandé tus cajas por privado.')
    await update.effective_message.reply_text(_boxes_text(),reply_markup=_boxes_markup())

def _boxes_markup():
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"{name} · {price:,} PiPesos",callback_data=f'ex:box:{code}')] for code,(price,name) in current_boxes().items()])

def _boxes_text():
    season=current_season().replace('_',' ').upper()
    return (f"🎁 CAJAS · {season}\n\n💜 Épica: premios comunes, raros y hasta ÉPICOS.\n🌟 Legendaria: puede soltar todo lo anterior y premios LEGENDARIOS.\n\nDentro pueden salir PiPesos, títulos y tipografías coleccionables. Si repites un coleccionable, recibes 2,000 PiPesos.")

def _roll_box(code):
    # Dos cajas únicamente: la Épica llega hasta épico; la Legendaria añade legendario.
    x=random.random()
    if code=='epic':
        rarity=random.choices(['comun','raro','epico'],weights=[52,33,15],k=1)[0]
        money_by_rarity={'comun':[2000,3000,4000],'raro':[5000,7000,9000],'epico':[12000,15000,18000]}
    else:
        rarity=random.choices(['comun','raro','epico','legendario'],weights=[36,31,23,10],k=1)[0]
        money_by_rarity={'comun':[4000,6000,8000],'raro':[9000,12000,15000],'epico':[18000,22000,28000],'legendario':[35000,45000,60000]}
    kind=random.choices(['title','font','money'],weights=[38,34,28],k=1)[0]
    if kind=='title':
        val=random.choice(title_pool()); return 'title',val,f'{val} · {rarity.upper()}'
    if kind=='font':
        f=random.choice(FONTS); return 'font',f,f'Tipografía {FONT_LABELS.get(f,f)} · {rarity.upper()}'
    money=random.choice(money_by_rarity[rarity]); return 'money',str(money),f'{money:,} PiPesos · {rarity.upper()}'

async def extras_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; p=q.data.split(':'); uid=q.from_user.id
    if p[1]=='luck':
        import json
        idx=int(p[2]); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute(f"SELECT choice,results_json FROM daily_luck_tb WHERE user_id=%s AND play_date={_mx_day_sql()} FOR UPDATE",(uid,)); row=c.fetchone()
            if not row: conn.rollback(); return await q.answer('Tu tirada de hoy ya no está disponible.',show_alert=True)
            if row[0] is not None: conn.rollback(); return await q.answer('Ya elegiste hoy.',show_alert=True)
            results=json.loads(row[1]); delta=int(results[idx])
            if delta<0:
                c.execute('SELECT saldo FROM usuarios_tb WHERE id_user=%s FOR UPDATE',(uid,)); rr=c.fetchone(); delta=-min(-delta,max(0,int(rr[0] if rr else 0)))
            c.execute('UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s',(delta,uid)); c.execute(f"UPDATE daily_luck_tb SET choice=%s WHERE user_id=%s AND play_date={_mx_day_sql()}",(idx,uid)); conn.commit()
        except Exception:
            conn.rollback(); return await q.answer('No pude registrar tu elección.',show_alert=True)
        finally:_put_connection(conn)
        emojis=['🍀','🎲','🎁','💀']; reveal=' · '.join(f'{emojis[i]} {v:+,}' for i,v in enumerate(results))
        await q.answer('¡Suerte decidida!',show_alert=True)
        return await q.edit_message_text(f'🍀 Elegiste {emojis[idx]}…\n\n{delta:+,} PiPesos\n\nLos cuatro escondían:\n{reveal}\n\nVuelve mañana a tentar a la suerte. 😈')
    if p[1]=='fontnoop': return await q.answer()
    if p[1]=='fontpage':
        page=int(p[2]); return await q.edit_message_reply_markup(reply_markup=font_markup(page,'profile_editor',q.from_user.id))
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
        code=p[2]; price,name=current_boxes()[code]; conn=_get_connection(); kind,val,label=_roll_box(code)
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
    await update.effective_message.reply_text('🔤 TIPOGRAFÍAS DE PERFIL\n\nAquí aparecen las tipografías que has conseguido en cajas. Equipar o cambiar entre las que ya tienes es gratis.',reply_markup=font_markup(0,uid=update.effective_user.id))

async def font_callback(q,code):
    uid=q.from_user.id
    if code not in FONTS: return await q.answer('Tipografía inválida.',show_alert=True)
    if code not in owned_fonts(uid): return await q.answer('🔒 Esa tipografía todavía no te ha salido en una caja.',show_alert=True)
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT font_code FROM user_profile_style_tb WHERE user_id=%s FOR UPDATE",(uid,)); old=c.fetchone(); old_code=old[0] if old else 'normal'
        if old_code==code or (old_code=='normal' and code=='normal__plain'): conn.rollback(); return await q.answer('Ya estás usando esa tipografía.',show_alert=True)
        c.execute("INSERT INTO user_profile_style_tb(user_id,font_code) VALUES(%s,%s) ON CONFLICT(user_id) DO UPDATE SET font_code=EXCLUDED.font_code,updated_at=now()",(uid,code)); conn.commit()
    except Exception:
        conn.rollback(); return await q.answer('No pude cambiar la tipografía.',show_alert=True)
    finally:_put_connection(conn)
    await q.answer(f'Tipografía equipada: {FONT_LABELS.get(code,code)}.',show_alert=True)


async def quitargif(update:Update,context:ContextTypes.DEFAULT_TYPE):
    # /quitargif <artículo>: ROOT quita únicamente los GIF dinámicos del artículo.
    # /quitargif sin argumento conserva el comportamiento existente del GIF de victoria.
    if context.args:
        if not ensure_root_identity(update.effective_user):
            return await update.effective_message.reply_text('⛔ Este comando es exclusivo de Kiu.')
        item_name=' '.join(context.args).strip(); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT id_item,nombre FROM items_tb WHERE LOWER(nombre)=LOWER(%s) LIMIT 1",(item_name,)); item=c.fetchone()
            if not item:
                return await update.effective_message.reply_text(f'⚠️ No encontré el artículo “{item_name}”.')
            c.execute("DELETE FROM item_gifs_tb WHERE id_item=%s",(item[0],)); removed=c.rowcount; conn.commit()
        except Exception:
            conn.rollback(); return await update.effective_message.reply_text('⚠️ No pude quitar el GIF del artículo. No se modificó nada más.')
        finally:_put_connection(conn)
        if removed:
            return await update.effective_message.reply_text(f'🗑️ Quité {removed} GIF(s) personalizados de {item[1]}.\nEl artículo, precio, inventario y efecto siguen intactos.')
        return await update.effective_message.reply_text(f'ℹ️ {item[1]} no tenía GIFs personalizados registrados.')

    uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("DELETE FROM victory_gif_tb WHERE user_id=%s",(uid,)); removed=c.rowcount; conn.commit()
    except Exception:
        conn.rollback(); return await update.effective_message.reply_text('⚠️ No pude quitar tu celebración.')
    finally:_put_connection(conn)
    await update.effective_message.reply_text('🗑️ Tu GIF de victoria fue eliminado.' if removed else '🏆 No tenías un GIF de victoria configurado.')

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


# ==================== DAILY LUCK / BASKETBALL / WEEKLY CHALLENGES ====================
def _mx_day_sql():
    return "(NOW() AT TIME ZONE 'America/Mexico_City')::date"

def _luck_results():
    # Exactly one normal, one bad, one very bad and one very good result.
    values=[random.randint(1000,5000), -random.randint(1000,4500), -random.randint(5000,12000), random.randint(10000,25000)]
    random.shuffle(values)
    return values

async def suerte_diaria(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute(f"SELECT choice,results_json FROM daily_luck_tb WHERE user_id=%s AND play_date={_mx_day_sql()}",(uid,)); old=c.fetchone()
        if old:
            return await update.effective_message.reply_text('🍀 Ya tentaste a la suerte hoy. Vuelve mañana para elegir otra vez.')
        import json
        results=_luck_results(); c.execute(f"INSERT INTO daily_luck_tb(user_id,play_date,results_json) VALUES(%s,{_mx_day_sql()},%s)",(uid,json.dumps(results))); conn.commit()
    except Exception:
        conn.rollback(); return await update.effective_message.reply_text('⚠️ No pude preparar tu suerte de hoy. Inténtalo de nuevo.')
    finally:_put_connection(conn)
    emojis=['🍀','🎲','🎁','💀']; kb=InlineKeyboardMarkup([[InlineKeyboardButton(emojis[i],callback_data=f'ex:luck:{i}') for i in range(4)]])
    await update.effective_message.reply_text('🍀 SUERTE DEL DÍA\n\nHay cuatro opciones. Una es normal, una mala, una MUY mala y una MUY buena. 😈\nElige una; hoy solo tienes una oportunidad.',reply_markup=kb)

async def baloncesto(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute(f"SELECT plays,made,net FROM daily_basketball_tb WHERE user_id=%s AND play_date={_mx_day_sql()} FOR UPDATE",(uid,)); row=c.fetchone()
        plays,made,net=(row or (0,0,0))
        if plays>=3:
            conn.rollback(); return await update.effective_message.reply_text(f'🏀 Ya usaste tus 3 tiros de hoy.\nEncestados: {made}/3 · Balance: {net:+,} PiPesos')
        # Reserve the attempt before awaiting Telegram, preventing double taps/commands.
        if row: c.execute(f"UPDATE daily_basketball_tb SET plays=plays+1,updated_at=NOW() WHERE user_id=%s AND play_date={_mx_day_sql()}",(uid,))
        else: c.execute(f"INSERT INTO daily_basketball_tb(user_id,play_date,plays) VALUES(%s,{_mx_day_sql()},1)",(uid,))
        conn.commit()
    except Exception:
        conn.rollback(); return await update.effective_message.reply_text('⚠️ No pude preparar el tiro.')
    finally:_put_connection(conn)
    try:
        dice=await context.bot.send_dice(chat_id=update.effective_chat.id,emoji='🏀',message_thread_id=getattr(update.effective_message,'message_thread_id',None)); value=dice.dice.value
    except Exception:
        # Give the reserved attempt back if Telegram itself could not send the dice.
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute(f"UPDATE daily_basketball_tb SET plays=GREATEST(0,plays-1) WHERE user_id=%s AND play_date={_mx_day_sql()}",(uid,)); conn.commit()
        finally:_put_connection(conn)
        return await update.effective_message.reply_text('⚠️ Telegram no pudo lanzar el balón. Tu intento no fue consumido.')
    # Esperar a que termine la animación del balón antes de revelar el resultado.
    await asyncio.sleep(4.2)
    rewards={1:-1000,2:-500,3:500,4:1500,5:3000}; delta=rewards.get(value,0); made_now=value>=4
    conn=_get_connection()
    try:
        c=conn.cursor();
        if delta<0:
            c.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s FOR UPDATE",(uid,)); rr=c.fetchone(); actual=min(-delta,max(0,int(rr[0] if rr else 0))); delta=-actual
        c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(delta,uid))
        c.execute(f"UPDATE daily_basketball_tb SET made=made+%s,net=net+%s,updated_at=NOW() WHERE user_id=%s AND play_date={_mx_day_sql()} RETURNING plays,made,net",(1 if made_now else 0,delta,uid)); stats=c.fetchone(); conn.commit()
    except Exception:
        conn.rollback(); return await update.effective_message.reply_text('⚠️ El tiro salió, pero no pude registrar el resultado. No se modificó tu saldo.')
    finally:_put_connection(conn)
    label='🔥 ¡Tiro limpio!' if value==5 else ('🏀 ¡Encestaste!' if made_now else '💥 Fallaste el tiro.')
    await update.effective_message.reply_text(f'{label}\nResultado: {delta:+,} PiPesos\nIntentos de hoy: {stats[0]}/3 · Encestados: {stats[1]} · Balance: {stats[2]:+,}')

def _challenge_target(update,context):
    m=update.effective_message
    if m.reply_to_message and m.reply_to_message.from_user:
        return m.reply_to_message.from_user.id
    # This is handled by a Regex MessageHandler, so context.args is not
    # guaranteed to be populated like it is for CommandHandler.
    for token in (m.text or '').split()[1:]:
        if token.startswith('@'):
            return get_id_user(token[1:])
    return None

async def challenge_points_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    """Handle /+N and /-N. Root-only; target by reply or @username."""
    if not ensure_root_identity(update.effective_user): return
    text=(update.effective_message.text or '').strip(); import re
    m=re.match(r'^/([+-])(\d+)(?:@\w+)?(?:\s|$)',text)
    if not m: return
    amount=int(m.group(2));
    if amount<=0 or amount>1000: return await update.effective_message.reply_text('🏆 Usa una cantidad entre 1 y 1000 puntos.')
    delta=amount if m.group(1)=='+' else -amount; target=_challenge_target(update,context)
    if not target: return await update.effective_message.reply_text('🏆 Responde al mensaje de alguien o añade @usuario. Ejemplo: /+3 @usuario')
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT id_user FROM usuarios_tb WHERE id_user=%s",(target,))
        if not c.fetchone(): conn.rollback(); return await update.effective_message.reply_text('🏆 Esa persona todavía no está registrada en PiBot.')
        c.execute("SELECT date_trunc('week',NOW() AT TIME ZONE 'America/Mexico_City')::date"); ws=c.fetchone()[0]
        c.execute("SELECT points FROM challenge_weekly_points_tb WHERE week_start=%s AND user_id=%s FOR UPDATE",(ws,target)); r=c.fetchone(); before=int(r[0]) if r else 0; after=max(0,before+delta); real=after-before
        c.execute("INSERT INTO challenge_weekly_points_tb(week_start,user_id,points) VALUES(%s,%s,%s) ON CONFLICT(week_start,user_id) DO UPDATE SET points=EXCLUDED.points,updated_at=NOW()",(ws,target,after))
        c.execute("INSERT INTO challenge_weekly_audit_tb(week_start,target_id,actor_id,delta,before_points,after_points) VALUES(%s,%s,%s,%s,%s,%s)",(ws,target,update.effective_user.id,real,before,after)); conn.commit()
        c.execute("SELECT username,nombre FROM perfiles_tb WHERE id_user=%s",(target,)); rr=c.fetchone(); name=(('@'+rr[0]) if rr and rr[0] else (rr[1] if rr else str(target)))
    except Exception:
        conn.rollback(); return await update.effective_message.reply_text('⚠️ No pude actualizar el ranking de retos.')
    finally:_put_connection(conn)
    await update.effective_message.reply_text(f"🏆 {name} {real:+d} punto{'s' if abs(real)!=1 else ''} · Total semanal: {after}")

async def ranking_retos(update:Update,context:ContextTypes.DEFAULT_TYPE):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT date_trunc('week',NOW() AT TIME ZONE 'America/Mexico_City')::date"); ws=c.fetchone()[0]
        c.execute("""SELECT p.user_id,p.points,pr.username,pr.nombre FROM challenge_weekly_points_tb p LEFT JOIN perfiles_tb pr ON pr.id_user=p.user_id WHERE p.week_start=%s ORDER BY p.points DESC,p.updated_at ASC LIMIT 30""",(ws,)); rows=c.fetchall()
    finally:_put_connection(conn)
    if not rows:return await update.effective_message.reply_text('🏆 El ranking semanal de retos todavía está vacío.')
    medals=['🥇','🥈','🥉']; lines=['🏆 RANKING SEMANAL DE RETOS','']
    for i,(uid,pts,user,name) in enumerate(rows): lines.append(f"{medals[i] if i<3 else str(i+1)+'.'} {('@'+user) if user else (name or 'Usuario')} — {pts} puntos")
    lines += ['','🎁 Premios: 20,000 · 12,000 · 8,000 PiPesos']
    await update.effective_message.reply_text('\n'.join(lines))

async def challenge_weekly_awards_job(context:ContextTypes.DEFAULT_TYPE):
    """Idempotent payout for the previous Mexico-City week."""
    conn=_get_connection(); winners=[]; ws=None
    try:
        c=conn.cursor(); c.execute("SELECT (date_trunc('week',NOW() AT TIME ZONE 'America/Mexico_City')::date - 7)"); ws=c.fetchone()[0]
        c.execute("SELECT 1 FROM challenge_weekly_payouts_tb WHERE week_start=%s",(ws,))
        if c.fetchone(): conn.rollback(); return
        c.execute("SELECT user_id,points FROM challenge_weekly_points_tb WHERE week_start=%s AND points>0 ORDER BY points DESC,updated_at ASC LIMIT 3 FOR UPDATE",(ws,)); rows=c.fetchall(); prizes=[20000,12000,8000]
        for i,row in enumerate(rows):
            uid,pts=row; prize=prizes[i]; c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(prize,uid)); winners.append((uid,pts,prize))
        ids=[w[0] for w in winners]+[None]*3; c.execute("INSERT INTO challenge_weekly_payouts_tb(week_start,first_id,second_id,third_id) VALUES(%s,%s,%s,%s)",(ws,ids[0],ids[1],ids[2])); conn.commit()
    except Exception as e:
        conn.rollback(); print('[RETOS WEEKLY]',e); return
    finally:_put_connection(conn)
    if not winners:return
    lines=['🏆 RANKING SEMANAL DE RETOS · RESULTADOS','']; medals=['🥇','🥈','🥉']
    conn=_get_connection()
    try:
        c=conn.cursor()
        for i,(uid,pts,prize) in enumerate(winners):
            c.execute("SELECT username,nombre FROM perfiles_tb WHERE id_user=%s",(uid,)); r=c.fetchone(); name=(('@'+r[0]) if r and r[0] else (r[1] if r else 'Usuario')); lines.append(f'{medals[i]} {name} — {pts} puntos · +{prize:,} PiPesos')
    finally:_put_connection(conn)
    try: await context.bot.send_message(chat_id=-1003290179217,message_thread_id=435,text='\n'.join(lines))
    except Exception as e: print('[RETOS ANNOUNCE]',e)
