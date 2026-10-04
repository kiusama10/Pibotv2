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

DANTE_VERSION = "1.0.0"

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
        kb=InlineKeyboardMarkup([[InlineKeyboardButton("Estado",callback_data="dante:estado"),InlineKeyboardButton("Casos",callback_data="dante:casos")],[InlineKeyboardButton("Ayuda",callback_data="dante:ayuda")]])
        await msg.reply_text("🕵️ DANTE 1.0.0\nPanel privado. DANTE observa y conserva; nunca modera.",reply_markup=kb); return
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
    action=(q.data or '').split(':',1)[-1]
    if action=='estado':
        counts=_db("SELECT (SELECT COUNT(*) FROM dante_identity_tb),(SELECT COUNT(*) FROM dante_events_tb),(SELECT COUNT(*) FROM dante_cases_tb)",fetch=True)[0]
        text=f"🕵️ DANTE {DANTE_VERSION} · ACTIVO\nIdentidades: {counts[0]} · Eventos: {counts[1]} · Casos: {counts[2]}\nModeración automática: NINGUNA"
    elif action=='casos':
        rows=_db("SELECT case_code,title,status FROM dante_cases_tb ORDER BY id DESC LIMIT 10",fetch=True); text="🗃️ Casos\n"+("\n".join(f"• {c} · {t} · {st}" for c,t,st in rows) if rows else "Sin casos.")
    else:
        text="DANTE: /dante buscar, /dante comparar, /dante caso, /dante nota, /dante exportar, /dante estado. En grupo, por respuesta: /dante vigilar, /dante caso CASO-001, /dante evidencia CASO-001."
    try: await q.edit_message_text(text,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Estado",callback_data="dante:estado"),InlineKeyboardButton("Casos",callback_data="dante:casos")],[InlineKeyboardButton("Ayuda",callback_data="dante:ayuda")]]))
    except Exception: pass
