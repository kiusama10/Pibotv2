"""DANTE 1.0.0 - isolated, owner-only observation/evidence layer for PiBot.

DANTE never moderates users. It records Telegram-visible facts, keeps identity
history, watchlists/cases/notes, and sends owner-only alerts for watched users.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib, json, os, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection
from src.config import KIU_ROOT_ID, KIU_ROOT_USERNAME
from src.utils.display_name import visible_user

DANTE_VERSION = "1.0.1"



def _main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Personas", callback_data="dante:people:0"), InlineKeyboardButton("👁 Vigilados", callback_data="dante:watched:0")],
        [InlineKeyboardButton("📁 Casos", callback_data="dante:cases"), InlineKeyboardButton("🔗 Comparar", callback_data="dante:compare:0")],
        [InlineKeyboardButton("📊 Estado", callback_data="dante:estado"), InlineKeyboardButton("❓ Ayuda", callback_data="dante:ayuda")],
    ])

def _person_label(username, name):
    return (f"@{username}" if username else (name or "Usuario"))[:38]

def _people_rows(page=0, watched=False):
    page=max(0,int(page)); off=page*8
    if watched:
        sql="""SELECT i.chat_id,i.user_id,i.username,i.display_name,i.last_seen FROM dante_identity_tb i JOIN dante_watch_tb w ON w.chat_id=i.chat_id AND w.user_id=i.user_id AND w.enabled=TRUE ORDER BY i.last_seen DESC LIMIT 9 OFFSET %s"""
    else:
        sql="""SELECT chat_id,user_id,username,display_name,last_seen FROM dante_identity_tb ORDER BY last_seen DESC LIMIT 9 OFFSET %s"""
    return _db(sql,(off,),True)

def _people_keyboard(page=0, watched=False, prefix="people"):
    rows=_people_rows(page, watched); shown=rows[:8]; kb=[]
    for cid,uid,un,name,last in shown:
        kb.append([InlineKeyboardButton(_person_label(un,name),callback_data=f"dante:person:{cid}:{uid}")])
    nav=[]
    if page>0: nav.append(InlineKeyboardButton("◀️",callback_data=f"dante:{prefix}:{page-1}"))
    if len(rows)>8: nav.append(InlineKeyboardButton("▶️",callback_data=f"dante:{prefix}:{page+1}"))
    if nav: kb.append(nav)
    kb.append([InlineKeyboardButton("🏠 Menú",callback_data="dante:menu")])
    return InlineKeyboardMarkup(kb), len(shown)

def _person_data(chat_id,user_id):
    r=_db("SELECT username,display_name,first_seen,last_seen FROM dante_identity_tb WHERE chat_id=%s AND user_id=%s",(chat_id,user_id),True)
    return r[0] if r else None

def _person_keyboard(chat_id,user_id):
    watched=_is_watched(chat_id,user_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Historial",callback_data=f"dante:history:{chat_id}:{user_id}"), InlineKeyboardButton("👁 Dejar de vigilar" if watched else "👁 Vigilar",callback_data=f"dante:watch:{chat_id}:{user_id}")],
        [InlineKeyboardButton("📁 Añadir a caso",callback_data=f"dante:addcase:{chat_id}:{user_id}"), InlineKeyboardButton("🔗 Comparar",callback_data=f"dante:cmpfirst:{chat_id}:{user_id}:0")],
        [InlineKeyboardButton("◀️ Personas",callback_data="dante:people:0"), InlineKeyboardButton("🏠 Menú",callback_data="dante:menu")],
    ])

def _is_dante_owner(user):
    if not user: return False
    if KIU_ROOT_ID: return user.id == KIU_ROOT_ID
    return bool(KIU_ROOT_USERNAME and (user.username or '').lower() == KIU_ROOT_USERNAME)
DANTE_ENABLED = os.getenv("DANTE_ENABLED", "true").strip().lower() not in {"0","false","off","no"}
_started = time.monotonic()
_last_event = None
_errors = 0
_identity_cache = {}  # (chat,user) -> ((username,name), monotonic); avoids DB work per ordinary message


def _db(sql, params=(), fetch=False):
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() if fetch else None
        conn.commit(); return rows
    except Exception:
        conn.rollback(); raise
    finally:
        _put_connection(conn)


def ensure_dante_tables():
    statements = [
    """CREATE TABLE IF NOT EXISTS dante_settings_tb(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
    """CREATE TABLE IF NOT EXISTS dante_identity_tb(chat_id BIGINT NOT NULL,user_id BIGINT NOT NULL,username TEXT,display_name TEXT,first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(chat_id,user_id))""",
    """CREATE TABLE IF NOT EXISTS dante_alias_tb(id BIGSERIAL PRIMARY KEY,chat_id BIGINT NOT NULL,user_id BIGINT NOT NULL,username TEXT,display_name TEXT,seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(chat_id,user_id,username,display_name))""",
    """CREATE TABLE IF NOT EXISTS dante_events_tb(id BIGSERIAL PRIMARY KEY,event_key TEXT UNIQUE,chat_id BIGINT,user_id BIGINT,event_type TEXT NOT NULL,event_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),message_id BIGINT,source TEXT NOT NULL DEFAULT 'pibot',data JSONB NOT NULL DEFAULT '{}'::jsonb)""",
    """CREATE TABLE IF NOT EXISTS dante_watch_tb(chat_id BIGINT NOT NULL,user_id BIGINT NOT NULL,enabled BOOLEAN NOT NULL DEFAULT TRUE,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(chat_id,user_id))""",
    """CREATE TABLE IF NOT EXISTS dante_cases_tb(id BIGSERIAL PRIMARY KEY,case_code TEXT UNIQUE,status TEXT NOT NULL DEFAULT 'open',title TEXT,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),closed_at TIMESTAMPTZ)""",
    """CREATE TABLE IF NOT EXISTS dante_case_members_tb(case_id BIGINT REFERENCES dante_cases_tb(id),chat_id BIGINT,user_id BIGINT,added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(case_id,chat_id,user_id))""",
    """CREATE TABLE IF NOT EXISTS dante_notes_tb(id BIGSERIAL PRIMARY KEY,case_id BIGINT REFERENCES dante_cases_tb(id),chat_id BIGINT,user_id BIGINT,note TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
    """CREATE TABLE IF NOT EXISTS dante_evidence_tb(id BIGSERIAL PRIMARY KEY,case_id BIGINT REFERENCES dante_cases_tb(id),chat_id BIGINT,user_id BIGINT,message_id BIGINT,evidence_type TEXT NOT NULL,sha256 TEXT,file_id TEXT,file_unique_id TEXT,caption TEXT,source TEXT NOT NULL DEFAULT 'observed_by_pibot',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
    """CREATE TABLE IF NOT EXISTS dante_audit_tb(id BIGSERIAL PRIMARY KEY,actor_id BIGINT,action TEXT NOT NULL,data JSONB NOT NULL DEFAULT '{}'::jsonb,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""",
    "CREATE INDEX IF NOT EXISTS idx_dante_evidence_case ON dante_evidence_tb(case_id,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_dante_identity_username ON dante_identity_tb(LOWER(username))",
    "CREATE INDEX IF NOT EXISTS idx_dante_alias_user ON dante_alias_tb(chat_id,user_id,seen_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_dante_events_user ON dante_events_tb(chat_id,user_id,event_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_dante_events_type_time ON dante_events_tb(event_type,event_at DESC)",
    ]
    for s in statements: _db(s)


def _event_key(update, kind):
    chat = update.effective_chat; msg = update.effective_message; user = update.effective_user
    return f"{kind}:{getattr(chat,'id',0)}:{getattr(msg,'message_id',0)}:{getattr(user,'id',0)}:{update.update_id}"


def _record_event(update, kind, data=None):
    global _last_event, _errors
    if not DANTE_ENABLED: return
    try:
        chat=update.effective_chat; user=update.effective_user; msg=update.effective_message
        _db("""INSERT INTO dante_events_tb(event_key,chat_id,user_id,event_type,message_id,data) VALUES(%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(event_key) DO NOTHING""",
            (_event_key(update,kind), getattr(chat,'id',None), getattr(user,'id',None), kind, getattr(msg,'message_id',None), json.dumps(data or {},ensure_ascii=False)))
        _last_event=datetime.now(timezone.utc)
    except Exception as exc:
        _errors += 1; print(f"[DANTE EVENT] {type(exc).__name__}: {exc}")


def _observe(chat_id, user):
    global _last_event, _errors
    if not DANTE_ENABLED or not user or user.is_bot: return False
    name=" ".join(x for x in [user.first_name,user.last_name] if x).strip() or None
    sig=(user.username,name); key=(chat_id,user.id); now=time.monotonic(); cached=_identity_cache.get(key)
    # Normal messages with unchanged identity cause zero DB round-trips for five minutes.
    if cached and cached[0] == sig and now-cached[1] < 300:
        return False
    try:
        old=_db("SELECT username,display_name FROM dante_identity_tb WHERE chat_id=%s AND user_id=%s",(chat_id,user.id),True)
        changed=bool(old and (old[0][0] != user.username or old[0][1] != name))
        _db("""INSERT INTO dante_identity_tb(chat_id,user_id,username,display_name) VALUES(%s,%s,%s,%s)
               ON CONFLICT(chat_id,user_id) DO UPDATE SET username=EXCLUDED.username,display_name=EXCLUDED.display_name,last_seen=NOW()""",(chat_id,user.id,user.username,name))
        if not old or changed:
            _db("""INSERT INTO dante_alias_tb(chat_id,user_id,username,display_name) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING""",(chat_id,user.id,user.username,name))
        _identity_cache[key]=(sig,now); _last_event=datetime.now(timezone.utc); return changed
    except Exception as exc:
        _errors += 1; print(f"[DANTE OBSERVE] {type(exc).__name__}: {exc}"); return False


def _is_watched(chat_id,user_id):
    try: return bool(_db("SELECT 1 FROM dante_watch_tb WHERE chat_id=%s AND user_id=%s AND enabled=TRUE",(chat_id,user_id),True))
    except Exception: return False


async def dante_observer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DANTE_ENABLED: return
    chat=update.effective_chat; user=update.effective_user; msg=update.effective_message
    if not chat or not user or user.is_bot: return
    changed=_observe(chat.id,user)
    kind="message"
    if msg and msg.new_chat_members:
        kind="join"
        for joined in msg.new_chat_members:
            if not joined.is_bot:
                _observe(chat.id, joined)
                try:
                    key=f"join:{chat.id}:{joined.id}:{update.update_id}"
                    _db("INSERT INTO dante_events_tb(event_key,chat_id,user_id,event_type,message_id,data) VALUES(%s,%s,%s,'join',%s,'{}'::jsonb) ON CONFLICT(event_key) DO NOTHING",(key,chat.id,joined.id,msg.message_id))
                except Exception as exc: print(f"[DANTE JOIN] {exc}")
                if _is_watched(chat.id, joined.id) and KIU_ROOT_ID:
                    try: await context.bot.send_message(KIU_ROOT_ID, f"🕵️ DANTE · Reaparición observada\n{visible_user(user=joined)} entró al grupo.\nAcción de DANTE: ninguna.")
                    except Exception as exc: print(f"[DANTE ALERT] {exc}")
    elif msg and msg.left_chat_member:
        kind="leave"
    # Keep ordinary traffic lightweight: identity last_seen only. Events are kept for lifecycle/identity changes.
    if kind != "message" or changed: _record_event(update, "identity_change" if changed else kind)
    if changed and _is_watched(chat.id,user.id):
        try:
            if KIU_ROOT_ID:
                await context.bot.send_message(KIU_ROOT_ID, f"🕵️ DANTE · Cambio observado\n{visible_user(user=user)} cambió datos visibles de su cuenta.\nAcción de DANTE: ninguna.")
        except Exception as exc: print(f"[DANTE ALERT] {exc}")


def record_system_event(chat_id,user_id,kind,data=None):
    if not DANTE_ENABLED: return
    try:
        key=f"system:{kind}:{chat_id}:{user_id}:{int(time.time()*1000)}"
        _db("INSERT INTO dante_events_tb(event_key,chat_id,user_id,event_type,source,data) VALUES(%s,%s,%s,%s,'pibot',%s::jsonb) ON CONFLICT DO NOTHING",(key,chat_id,user_id,kind,json.dumps(data or {},ensure_ascii=False)))
    except Exception as exc: print(f"[DANTE SYSTEM] {exc}")


async def dante_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user=update.effective_user; msg=update.effective_message; chat=update.effective_chat
    if not _is_dante_owner(user): return
    if not DANTE_ENABLED:
        await msg.reply_text("🕵️ DANTE está desactivado por configuración."); return
    args=context.args or []; sub=(args[0].lower() if args else "")
    target=msg.reply_to_message.from_user if msg.reply_to_message else None
    # The only group-side DANTE action is selecting a replied user for watch/case notes.
    # Sensitive output is sent to the owner's private chat and the command is removed when possible.
    if chat.type != 'private':
        if sub == 'vigilar' and target:
            _observe(chat.id,target)
            _db("INSERT INTO dante_watch_tb(chat_id,user_id,enabled) VALUES(%s,%s,TRUE) ON CONFLICT(chat_id,user_id) DO UPDATE SET enabled=NOT dante_watch_tb.enabled",(chat.id,target.id))
            state=_db("SELECT enabled FROM dante_watch_tb WHERE chat_id=%s AND user_id=%s",(chat.id,target.id),True)[0][0]
            await context.bot.send_message(user.id,f"🕵️ Vigilancia {'activada' if state else 'desactivada'} para {visible_user(user=target)}.")
            try: await msg.delete()
            except Exception: pass
        elif sub == 'caso' and target and len(args) > 1:
            code=args[1].upper(); rows=_db("SELECT id FROM dante_cases_tb WHERE case_code=%s AND status='open'",(code,),True)
            if rows:
                _observe(chat.id,target); _db("INSERT INTO dante_case_members_tb(case_id,chat_id,user_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",(rows[0][0],chat.id,target.id))
                await context.bot.send_message(user.id,f"🗃️ {visible_user(user=target)} agregado a {code}. Relación registrada; no implica identidad ni culpabilidad.")
            else: await context.bot.send_message(user.id,f"No encontré un caso abierto llamado {code}.")
            try: await msg.delete()
            except Exception: pass
        elif sub == 'evidencia' and msg.reply_to_message and len(args) > 1:
            code=args[1].upper(); rows=_db("SELECT id FROM dante_cases_tb WHERE case_code=%s AND status='open'",(code,),True)
            if not rows:
                await context.bot.send_message(user.id,f"No encontré un caso abierto llamado {code}.")
            else:
                src=msg.reply_to_message; media=None; etype='message'
                if src.document: media=src.document; etype='document'
                elif src.video: media=src.video; etype='video'
                elif src.voice: media=src.voice; etype='voice'
                elif src.audio: media=src.audio; etype='audio'
                elif src.photo: media=src.photo[-1]; etype='photo'
                sha=None; fid=getattr(media,'file_id',None); funiq=getattr(media,'file_unique_id',None)
                if media and (getattr(media,'file_size',0) or 0) <= 20*1024*1024:
                    try:
                        tf=await context.bot.get_file(media.file_id); data=bytes(await tf.download_as_bytearray()); sha=hashlib.sha256(data).hexdigest()
                    except Exception as exc: print(f"[DANTE EVIDENCE HASH] {exc}")
                _db("INSERT INTO dante_evidence_tb(case_id,chat_id,user_id,message_id,evidence_type,sha256,file_id,file_unique_id,caption) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",(rows[0][0],chat.id,getattr(src.from_user,'id',None),src.message_id,etype,sha,fid,funiq,src.caption or src.text))
                await context.bot.send_message(user.id,f"📁 Evidencia registrada en {code}."+(f"\nSHA-256: {sha}" if sha else "\nMetadatos preservados; archivo sin hash local."))
            try: await msg.delete()
            except Exception: pass
        else:
            try: await context.bot.send_message(user.id,"🕵️ El panel y los resultados de DANTE solo se muestran por privado. Para vigilar a alguien, responde a su mensaje en el grupo con /dante vigilar.")
            except Exception: pass
        return
    if not sub:
        await msg.reply_text(f"🕷️ DANTE {DANTE_VERSION}\nElige una opción. No necesitas saber @usuarios ni IDs.",reply_markup=_main_keyboard()); return
    if sub=="estado":
        age=int(time.monotonic()-_started); last=_last_event.isoformat() if _last_event else "sin eventos desde este arranque"
        counts=_db("SELECT (SELECT COUNT(*) FROM dante_identity_tb),(SELECT COUNT(*) FROM dante_events_tb),(SELECT COUNT(*) FROM dante_cases_tb)",fetch=True)[0]
        await msg.reply_text(f"🕵️ DANTE {DANTE_VERSION}\nMotor: ACTIVO\nBD: conectada\nIdentidades: {counts[0]}\nEventos: {counts[1]}\nCasos: {counts[2]}\nÚltimo evento: {last}\nErrores de sesión: {_errors}\nUptime DANTE: {age}s\nModeración automática: NINGUNA"); return
    if sub=="buscar":
        q=" ".join(args[1:]).strip().lstrip("@")
        if not q: await msg.reply_text("Uso: /dante buscar @usuario o nombre"); return
        rows=_db("""SELECT DISTINCT i.chat_id,i.user_id,i.username,i.display_name,i.last_seen FROM dante_identity_tb i LEFT JOIN dante_alias_tb a ON a.chat_id=i.chat_id AND a.user_id=i.user_id WHERE LOWER(COALESCE(i.username,''))=LOWER(%s) OR LOWER(COALESCE(a.username,''))=LOWER(%s) OR LOWER(COALESCE(i.display_name,'')) LIKE LOWER(%s) OR LOWER(COALESCE(a.display_name,'')) LIKE LOWER(%s) ORDER BY i.last_seen DESC LIMIT 20""",(q,q,f"%{q}%",f"%{q}%"),True)
        if not rows: await msg.reply_text("DANTE no tiene coincidencias observadas."); return
        lines=[]
        for cid,uid,un,name,last in rows:
            label=f"@{un}" if un else (name or "Usuario sin nombre disponible")
            aliases=_db("SELECT username,display_name,seen_at FROM dante_alias_tb WHERE chat_id=%s AND user_id=%s ORDER BY seen_at DESC LIMIT 8",(cid,uid),True)
            ah=[]
            for aun,an,_ in aliases:
                x=f"@{aun}" if aun else an
                if x and x not in ah: ah.append(x)
            lines.append(f"• {label} · visto {last:%Y-%m-%d %H:%M}\n  Historial: {', '.join(ah) if ah else 'sin cambios registrados'}")
        await msg.reply_text("🕵️ Coincidencias observadas\n"+"\n".join(lines)); return
    if sub=="comparar":
        if len(args)<3: await msg.reply_text("Uso: /dante comparar @usuario1 @usuario2"); return
        def resolve(q):
            q=q.lstrip('@'); r=_db("SELECT chat_id,user_id,username,display_name FROM dante_identity_tb WHERE LOWER(COALESCE(username,''))=LOWER(%s) OR LOWER(COALESCE(display_name,''))=LOWER(%s) ORDER BY last_seen DESC LIMIT 1",(q,q),True); return r[0] if r else None
        a,b=resolve(args[1]),resolve(args[2])
        if not a or not b: await msg.reply_text("No tengo historial suficiente de una de esas cuentas."); return
        aa=_db("SELECT COALESCE(username,''),COALESCE(display_name,'') FROM dante_alias_tb WHERE chat_id=%s AND user_id=%s",(a[0],a[1]),True); bb=_db("SELECT COALESCE(username,''),COALESCE(display_name,'') FROM dante_alias_tb WHERE chat_id=%s AND user_id=%s",(b[0],b[1]),True)
        shared=sorted(set(aa)&set(bb)); la=f"@{a[2]}" if a[2] else a[3]; lb=f"@{b[2]}" if b[2] else b[3]
        await msg.reply_text(f"🧩 Comparación\n{la} ↔ {lb}\nCoincidencias exactas de alias observados: {len(shared)}\n"+("\n".join(f"• @{u}" if u else f"• {n}" for u,n in shared) if shared else "Sin coincidencias exactas de alias.")+"\n\nIdentidad común no demostrada."); return
    if sub=="caso":
        if len(args)>2 and args[1].lower() in ('cerrar','congelar'):
            code=args[2].upper(); rows=_db("UPDATE dante_cases_tb SET status='closed',closed_at=NOW() WHERE case_code=%s AND status='open' RETURNING case_code",(code,),True)
            await msg.reply_text(f"🔒 {code} cerrado y congelado." if rows else "Ese caso no existe o ya estaba cerrado."); return
        if len(args)>1 and args[1].lower()=='listar':
            rows=_db("SELECT case_code,title,status FROM dante_cases_tb ORDER BY id DESC LIMIT 20",fetch=True)
            await msg.reply_text("🗃️ Casos\n"+("\n".join(f"• {c} · {t} · {st}" for c,t,st in rows) if rows else "Sin casos.")); return
        title=" ".join(args[1:]).strip() or "Caso sin título"
        row=_db("INSERT INTO dante_cases_tb(title) VALUES(%s) RETURNING id",(title,),True)[0][0]; code=f"CASO-{row:03d}"; _db("UPDATE dante_cases_tb SET case_code=%s WHERE id=%s",(code,row))
        await msg.reply_text(f"🗃️ {code} creado: {title}"); return
    if sub=="nota":
        if len(args) < 3 or not args[1].upper().startswith("CASO-"):
            await msg.reply_text("Uso: /dante nota CASO-001 texto"); return
        code=args[1].upper(); text=" ".join(args[2:]).strip(); rows=_db("SELECT id FROM dante_cases_tb WHERE case_code=%s AND status='open'",(code,),True)
        if not rows: await msg.reply_text("Ese caso no existe o está cerrado."); return
        _db("INSERT INTO dante_notes_tb(case_id,note) VALUES(%s,%s)",(rows[0][0],text)); await msg.reply_text(f"📝 Nota guardada en {code}."); return
    if sub=="exportar":
        if len(args)<2: await msg.reply_text("Uso: /dante exportar CASO-001"); return
        code=args[1].upper(); cases=_db("SELECT id,case_code,title,status,created_at,closed_at FROM dante_cases_tb WHERE case_code=%s",(code,),True)
        if not cases: await msg.reply_text("Ese caso no existe."); return
        c=cases[0]; notes=_db("SELECT note,created_at FROM dante_notes_tb WHERE case_id=%s OR (case_id IS NULL AND %s IS NULL) ORDER BY created_at",(c[0],c[0]),True)
        members=_db("SELECT chat_id,user_id,added_at FROM dante_case_members_tb WHERE case_id=%s",(c[0],),True)
        evidence=_db("SELECT chat_id,user_id,message_id,evidence_type,sha256,file_unique_id,caption,source,created_at FROM dante_evidence_tb WHERE case_id=%s ORDER BY created_at",(c[0],),True)
        payload={'dante_version':DANTE_VERSION,'case':{'code':c[1],'title':c[2],'status':c[3],'created_at':c[4].isoformat(),'closed_at':c[5].isoformat() if c[5] else None},'members':members,'notes':[(n,t.isoformat()) for n,t in notes],'evidence':evidence}
        raw=json.dumps(payload,ensure_ascii=False,indent=2,default=str).encode(); sha=hashlib.sha256(raw).hexdigest(); path=f"/tmp/{code}.json"; open(path,'wb').write(raw)
        with open(path,'rb') as fh: await msg.reply_document(fh,filename=f"{code}.json",caption=f"🗃️ Exportación DANTE · SHA-256: {sha}")
        try: os.remove(path)
        except OSError: pass
        return
    await msg.reply_text("Subcomando DANTE no reconocido.")


async def dante_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; user=update.effective_user
    if not q or not _is_dante_owner(user): return
    await q.answer()
    parts=(q.data or '').split(':')
    action=parts[1] if len(parts)>1 else 'menu'
    try:
        if action=='menu':
            await q.edit_message_text(f"🕷️ DANTE {DANTE_VERSION}\nElige una opción. No necesitas saber @usuarios ni IDs.",reply_markup=_main_keyboard()); return
        if action in ('people','watched'):
            page=int(parts[2]) if len(parts)>2 else 0; watched=action=='watched'
            kb,n=_people_keyboard(page,watched,action)
            title="👁 Vigilados" if watched else "🔎 Personas conocidas por DANTE"
            text=title+"\nToca una persona para abrir su ficha."+("\n\nNo hay usuarios en esta sección." if n==0 else "")
            await q.edit_message_text(text,reply_markup=kb); return
        if action=='person':
            cid,uid=int(parts[2]),int(parts[3]); d=_person_data(cid,uid)
            if not d: await q.answer("Ya no encuentro ese registro.",show_alert=True); return
            un,name,first,last=d; label=_person_label(un,name)
            await q.edit_message_text(f"👤 {label}\nPrimera vez observada: {first:%Y-%m-%d %H:%M}\nÚltima vez observada: {last:%Y-%m-%d %H:%M}\n\n¿Qué quieres revisar?",reply_markup=_person_keyboard(cid,uid)); return
        if action=='history':
            cid,uid=int(parts[2]),int(parts[3]); d=_person_data(cid,uid)
            aliases=_db("SELECT username,display_name,seen_at FROM dante_alias_tb WHERE chat_id=%s AND user_id=%s ORDER BY seen_at DESC LIMIT 12",(cid,uid),True)
            label=_person_label(d[0],d[1]) if d else 'Usuario'; lines=[]
            for un,name,seen in aliases:
                x=_person_label(un,name)
                if x not in [a for a,_ in lines]: lines.append((x,seen))
            text=f"📋 Historial · {label}\n"+("\n".join(f"• {x} · {t:%Y-%m-%d %H:%M}" for x,t in lines) if lines else "Sin cambios de identidad registrados.")
            await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver",callback_data=f"dante:person:{cid}:{uid}")]])); return
        if action=='watch':
            cid,uid=int(parts[2]),int(parts[3]); _db("INSERT INTO dante_watch_tb(chat_id,user_id,enabled) VALUES(%s,%s,TRUE) ON CONFLICT(chat_id,user_id) DO UPDATE SET enabled=NOT dante_watch_tb.enabled",(cid,uid))
            state=_is_watched(cid,uid); await q.answer("Vigilancia activada" if state else "Vigilancia desactivada",show_alert=True)
            d=_person_data(cid,uid); label=_person_label(d[0],d[1]) if d else 'Usuario'
            await q.edit_message_text(f"👤 {label}\nVigilancia: {'ACTIVA' if state else 'desactivada'}\nDANTE solo observa; no modera.",reply_markup=_person_keyboard(cid,uid)); return
        if action=='addcase':
            cid,uid=int(parts[2]),int(parts[3]); rows=_db("SELECT case_code,title FROM dante_cases_tb WHERE status='open' ORDER BY id DESC LIMIT 12",fetch=True)
            kb=[[InlineKeyboardButton(f"{c} · {(t or 'Sin título')[:24]}",callback_data=f"dante:caseadd:{cid}:{uid}:{c}")] for c,t in rows]
            kb.append([InlineKeyboardButton("◀️ Volver",callback_data=f"dante:person:{cid}:{uid}")])
            await q.edit_message_text("📁 Elige el caso al que quieres añadir esta persona." if rows else "📁 No tienes casos abiertos. Crea uno con /dante caso nombre y después aparecerá aquí.",reply_markup=InlineKeyboardMarkup(kb)); return
        if action=='caseadd':
            cid,uid,code=int(parts[2]),int(parts[3]),parts[4]; r=_db("SELECT id FROM dante_cases_tb WHERE case_code=%s AND status='open'",(code,),True)
            if r: _db("INSERT INTO dante_case_members_tb(case_id,chat_id,user_id) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",(r[0][0],cid,uid)); await q.answer(f"Añadido a {code}",show_alert=True)
            await q.edit_message_text(f"📁 Persona añadida a {code}.\nEsto registra una relación para investigar; no implica identidad ni culpabilidad.",reply_markup=_person_keyboard(cid,uid)); return
        if action in ('compare','cmpfirst'):
            if action=='cmpfirst': first_cid,first_uid,page=int(parts[2]),int(parts[3]),int(parts[4])
            else:
                first_cid=first_uid=None; page=int(parts[2]) if len(parts)>2 else 0
            rows=_people_rows(page,False); shown=rows[:8]; kb=[]
            for cid,uid,un,name,last in shown:
                if first_uid==uid and first_cid==cid: continue
                cb=f"dante:cmpdo:{first_cid}:{first_uid}:{cid}:{uid}" if first_uid is not None else f"dante:cmpfirst:{cid}:{uid}:0"
                kb.append([InlineKeyboardButton(_person_label(un,name),callback_data=cb)])
            nav=[]
            if page>0:
                cb=f"dante:cmpfirst:{first_cid}:{first_uid}:{page-1}" if first_uid is not None else f"dante:compare:{page-1}"; nav.append(InlineKeyboardButton("◀️",callback_data=cb))
            if len(rows)>8:
                cb=f"dante:cmpfirst:{first_cid}:{first_uid}:{page+1}" if first_uid is not None else f"dante:compare:{page+1}"; nav.append(InlineKeyboardButton("▶️",callback_data=cb))
            if nav: kb.append(nav)
            kb.append([InlineKeyboardButton("🏠 Menú",callback_data="dante:menu")])
            await q.edit_message_text("🔗 Elige la segunda persona." if first_uid is not None else "🔗 Elige la primera persona.",reply_markup=InlineKeyboardMarkup(kb)); return
        if action=='cmpdo':
            ac,au,bc,bu=map(int,parts[2:6]); a=_person_data(ac,au); b=_person_data(bc,bu)
            aa=_db("SELECT COALESCE(username,''),COALESCE(display_name,'') FROM dante_alias_tb WHERE chat_id=%s AND user_id=%s",(ac,au),True); bb=_db("SELECT COALESCE(username,''),COALESCE(display_name,'') FROM dante_alias_tb WHERE chat_id=%s AND user_id=%s",(bc,bu),True)
            shared=sorted(set(aa)&set(bb)); la=_person_label(a[0],a[1]) if a else 'Persona 1'; lb=_person_label(b[0],b[1]) if b else 'Persona 2'
            detail="\n".join(f"• @{u}" if u else f"• {n}" for u,n in shared) if shared else "Sin coincidencias exactas de alias."
            await q.edit_message_text(f"🧩 Comparación\n{la} ↔ {lb}\nCoincidencias exactas: {len(shared)}\n{detail}\n\nIdentidad común no demostrada.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Otra comparación",callback_data="dante:compare:0"),InlineKeyboardButton("🏠 Menú",callback_data="dante:menu")]])); return
        if action in ('cases','casos'):
            rows=_db("SELECT case_code,title,status FROM dante_cases_tb ORDER BY id DESC LIMIT 12",fetch=True)
            kb=[[InlineKeyboardButton(f"{c} · {(t or 'Sin título')[:25]}",callback_data=f"dante:case:{c}")] for c,t,st in rows]
            kb.append([InlineKeyboardButton("🏠 Menú",callback_data="dante:menu")])
            await q.edit_message_text("📁 Casos\nToca uno para abrirlo." if rows else "📁 Todavía no hay casos.\nPara crear uno nuevo usa /dante caso nombre.",reply_markup=InlineKeyboardMarkup(kb)); return
        if action=='case':
            code=parts[2]; r=_db("SELECT id,title,status,created_at FROM dante_cases_tb WHERE case_code=%s",(code,),True)
            if not r: await q.answer("Caso no encontrado",show_alert=True); return
            cid,title,status,created=r[0]; nm=_db("SELECT COUNT(*) FROM dante_case_members_tb WHERE case_id=%s",(cid,),True)[0][0]; ne=_db("SELECT COUNT(*) FROM dante_evidence_tb WHERE case_id=%s",(cid,),True)[0][0]; nn=_db("SELECT COUNT(*) FROM dante_notes_tb WHERE case_id=%s",(cid,),True)[0][0]
            kb=InlineKeyboardMarkup([[InlineKeyboardButton("👥 Personas",callback_data=f"dante:casemembers:{code}"),InlineKeyboardButton("🧾 Evidencias",callback_data=f"dante:caseevidence:{code}")],[InlineKeyboardButton("📝 Notas",callback_data=f"dante:casenotes:{code}"),InlineKeyboardButton("📤 Exportar",callback_data=f"dante:caseexport:{code}")],[InlineKeyboardButton("◀️ Casos",callback_data="dante:cases"),InlineKeyboardButton("🏠 Menú",callback_data="dante:menu")]])
            await q.edit_message_text(f"📁 {code} · {title}\nEstado: {status}\nPersonas: {nm} · Evidencias: {ne} · Notas: {nn}",reply_markup=kb); return
        if action in ('casemembers','caseevidence','casenotes'):
            code=parts[2]; r=_db("SELECT id FROM dante_cases_tb WHERE case_code=%s",(code,),True); case_id=r[0][0] if r else None
            if not case_id: return
            if action=='casemembers':
                rows=_db("SELECT m.chat_id,m.user_id,i.username,i.display_name,m.added_at FROM dante_case_members_tb m LEFT JOIN dante_identity_tb i ON i.chat_id=m.chat_id AND i.user_id=m.user_id WHERE m.case_id=%s ORDER BY m.added_at DESC LIMIT 20",(case_id,),True); text="👥 Personas · "+code+"\n"+("\n".join(f"• {_person_label(un,name)}" for _,_,un,name,_ in rows) if rows else "Sin personas asociadas.")
            elif action=='caseevidence':
                rows=_db("SELECT evidence_type,created_at,sha256 FROM dante_evidence_tb WHERE case_id=%s ORDER BY created_at DESC LIMIT 20",(case_id,),True); text="🧾 Evidencias · "+code+"\n"+("\n".join(f"• {typ} · {dt:%Y-%m-%d %H:%M}"+(f" · SHA {sha[:10]}…" if sha else "") for typ,dt,sha in rows) if rows else "Sin evidencias.")
            else:
                rows=_db("SELECT note,created_at FROM dante_notes_tb WHERE case_id=%s ORDER BY created_at DESC LIMIT 20",(case_id,),True); text="📝 Notas · "+code+"\n"+("\n".join(f"• {dt:%Y-%m-%d}: {note[:120]}" for note,dt in rows) if rows else "Sin notas.")+f"\n\nPara añadir una nota nueva: /dante nota {code} texto"
            await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Volver",callback_data=f"dante:case:{code}")]])); return
        if action=='caseexport':
            code=parts[2]; cases=_db("SELECT id,case_code,title,status,created_at,closed_at FROM dante_cases_tb WHERE case_code=%s",(code,),True)
            if not cases: return
            c=cases[0]; notes=_db("SELECT note,created_at FROM dante_notes_tb WHERE case_id=%s ORDER BY created_at",(c[0],),True); members=_db("SELECT chat_id,user_id,added_at FROM dante_case_members_tb WHERE case_id=%s",(c[0],),True); evidence=_db("SELECT chat_id,user_id,message_id,evidence_type,sha256,file_unique_id,caption,source,created_at FROM dante_evidence_tb WHERE case_id=%s ORDER BY created_at",(c[0],),True)
            payload={'dante_version':DANTE_VERSION,'case':{'code':c[1],'title':c[2],'status':c[3],'created_at':c[4].isoformat(),'closed_at':c[5].isoformat() if c[5] else None},'members':members,'notes':[(n,t.isoformat()) for n,t in notes],'evidence':evidence}; raw=json.dumps(payload,ensure_ascii=False,indent=2,default=str).encode(); sha=hashlib.sha256(raw).hexdigest(); path=f"/tmp/{code}.json"; open(path,'wb').write(raw)
            with open(path,'rb') as fh: await context.bot.send_document(user.id,fh,filename=f"{code}.json",caption=f"📤 {code} · SHA-256: {sha}")
            try: os.remove(path)
            except OSError: pass
            await q.answer("Exportación enviada",show_alert=True); return
        if action=='estado':
            counts=_db("SELECT (SELECT COUNT(*) FROM dante_identity_tb),(SELECT COUNT(*) FROM dante_events_tb),(SELECT COUNT(*) FROM dante_cases_tb)",fetch=True)[0]
            await q.edit_message_text(f"📊 DANTE {DANTE_VERSION} · ACTIVO\nIdentidades: {counts[0]}\nEventos: {counts[1]}\nCasos: {counts[2]}\nModeración automática: NINGUNA",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menú",callback_data="dante:menu")]])); return
        if action=='ayuda':
            await q.edit_message_text("❓ DANTE\nUsa los botones para elegir personas, vigilarlas, compararlas y trabajar con casos. Ya no necesitas memorizar @usuarios ni IDs.\n\nLos comandos escritos siguen disponibles como atajos. Para registrar evidencia desde el grupo todavía debes responder al mensaje que quieres conservar.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menú",callback_data="dante:menu")]])); return
    except Exception as exc:
        print(f"[DANTE CALLBACK] {type(exc).__name__}: {exc}")
        try: await q.answer("DANTE no pudo completar esa acción.",show_alert=True)
        except Exception: pass
