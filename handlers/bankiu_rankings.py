from __future__ import annotations

import os
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.database.database import _get_connection, _put_connection

# Centralized knobs: can be changed from Render without touching balances/schema.
BANKIU_INTEREST_PERCENT = max(0, int(os.getenv("BANKIU_INTEREST_PERCENT", "10")))
BANKIU_TERM_DAYS = max(1, int(os.getenv("BANKIU_TERM_DAYS", "7")))
CREDIT_TIERS = (10_000, 25_000, 50_000, 75_000, 100_000)
RANKING_DAYS = 14

_activity_lock = threading.Lock()
_activity_pending: dict[int, int] = defaultdict(int)
_activity_last: dict[int, datetime] = {}


def _money(n: int) -> str:
    return f"{int(n):,}".replace(",", ",")


def _loan_limit(completed: int) -> int:
    return CREDIT_TIERS[min(max(0, completed), len(CREDIT_TIERS) - 1)]


def _active_loan(uid: int, for_update: bool = False):
    conn = _get_connection()
    try:
        c = conn.cursor()
        suffix = " FOR UPDATE" if for_update else ""
        c.execute(
            """SELECT loan_id, principal, saldo_pendiente, interes_pct, creado_en, vence_en, estado
               FROM bankiu_loans_tb
               WHERE user_id=%s AND estado IN ('activo','vencido')
               ORDER BY loan_id DESC LIMIT 1""" + suffix,
            (uid,),
        )
        return c.fetchone()
    finally:
        _put_connection(conn)


def _credit_summary(uid: int):
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM bankiu_loans_tb WHERE user_id=%s AND estado='pagado'", (uid,))
        completed = int(c.fetchone()[0])
        c.execute("SELECT COUNT(*) FROM bankiu_loans_tb WHERE user_id=%s AND estado='vencido'", (uid,))
        overdue = int(c.fetchone()[0])
        return completed, overdue, _loan_limit(completed)
    finally:
        _put_connection(conn)


def create_loan(uid: int, amount: int):
    conn = _get_connection()
    try:
        c = conn.cursor()
        # Serialize credit decisions per user on the user row.
        c.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s FOR UPDATE", (uid,))
        if not c.fetchone():
            conn.rollback(); return "missing", None
        c.execute("SELECT COUNT(*) FROM bankiu_loans_tb WHERE user_id=%s AND estado='pagado'", (uid,))
        completed = int(c.fetchone()[0])
        limit = _loan_limit(completed)
        c.execute("SELECT 1 FROM bankiu_loans_tb WHERE user_id=%s AND estado IN ('activo','vencido') LIMIT 1", (uid,))
        if c.fetchone():
            conn.rollback(); return "active", None
        if amount <= 0 or amount > limit:
            conn.rollback(); return "limit", limit
        interest = (amount * BANKIU_INTEREST_PERCENT + 99) // 100
        total = amount + interest
        c.execute(
            """INSERT INTO bankiu_loans_tb(user_id,principal,interes_pct,saldo_pendiente,vence_en,estado)
               VALUES(%s,%s,%s,%s,NOW()+(%s || ' days')::interval,'activo') RETURNING loan_id,vence_en""",
            (uid, amount, BANKIU_INTEREST_PERCENT, total, BANKIU_TERM_DAYS),
        )
        loan_id, due = c.fetchone()
        c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s", (amount, uid))
        c.execute("INSERT INTO bankiu_payments_tb(loan_id,user_id,monto,tipo) VALUES(%s,%s,%s,'desembolso')", (loan_id, uid, amount))
        conn.commit()
        return "ok", (loan_id, amount, total, due)
    except Exception as exc:
        conn.rollback(); print("[BANKIU] create loan", exc); return "error", None
    finally:
        _put_connection(conn)


def pay_loan(uid: int, requested: int | None = None):
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s FOR UPDATE", (uid,))
        row = c.fetchone()
        if not row: conn.rollback(); return "missing", None
        balance = int(row[0])
        c.execute(
            """SELECT loan_id,saldo_pendiente FROM bankiu_loans_tb
               WHERE user_id=%s AND estado IN ('activo','vencido') ORDER BY loan_id DESC LIMIT 1 FOR UPDATE""",
            (uid,),
        )
        loan = c.fetchone()
        if not loan: conn.rollback(); return "none", None
        loan_id, pending = int(loan[0]), int(loan[1])
        amount = min(pending, balance, requested if requested and requested > 0 else pending)
        if amount <= 0: conn.rollback(); return "money", pending
        c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s", (amount, uid))
        remaining = pending - amount
        state = "pagado" if remaining == 0 else "activo"
        c.execute("UPDATE bankiu_loans_tb SET saldo_pendiente=%s,estado=%s,pagado_en=CASE WHEN %s=0 THEN NOW() ELSE pagado_en END WHERE loan_id=%s", (remaining, state, remaining, loan_id))
        c.execute("INSERT INTO bankiu_payments_tb(loan_id,user_id,monto,tipo) VALUES(%s,%s,%s,'pago')", (loan_id, uid, amount))
        conn.commit(); return "ok", (amount, remaining)
    except Exception as exc:
        conn.rollback(); print("[BANKIU] pay", exc); return "error", None
    finally:
        _put_connection(conn)


def _bank_keyboard(limit: int, has_loan: bool):
    rows = []
    if not has_loan:
        amounts = [x for x in CREDIT_TIERS if x <= limit]
        rows.extend([[InlineKeyboardButton(f"💰 Pedir {_money(x)}", callback_data=f"bank_loan_{x}")] for x in amounts])
    else:
        rows.append([InlineKeyboardButton("💸 Pagar deuda", callback_data="bank_pay_all")])
    rows.append([InlineKeyboardButton("📜 Mi historial", callback_data="bank_history")])
    return InlineKeyboardMarkup(rows)


async def bankiu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    completed, _, limit = _credit_summary(uid)
    loan = _active_loan(uid)
    if loan:
        _, principal, pending, pct, _, due, state = loan
        text = (f"🏦 BANKIU\n\n💳 Préstamo original: {_money(principal)} PiPesos\n"
                f"💸 Pendiente: {_money(pending)} PiPesos\n📈 Interés: {pct}%\n"
                f"📅 Vence: {due:%d/%m/%Y %H:%M} UTC\nEstado: {state}\n\n"
                "Puedes pagar antes o hacer pagos parciales.")
    else:
        text = (f"🏦 BANKIU\n\nTu límite actual es de {_money(limit)} PiPesos.\n"
                f"Préstamos pagados: {completed}\nInterés actual: {BANKIU_INTEREST_PERCENT}% · plazo: {BANKIU_TERM_DAYS} días.\n\n"
                "Pagar préstamos aumenta gradualmente tu límite hasta 100,000 PiPesos.")
    kb = _bank_keyboard(limit, bool(loan))
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)


async def bankiu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; uid = q.from_user.id; data = q.data or ""
    if data.startswith("bank_loan_"):
        try: amount = int(data.rsplit("_", 1)[1])
        except ValueError: return
        st, info = create_loan(uid, amount)
        if st == "ok":
            _, principal, total, _ = info
            await q.answer(f"BANKIU depositó {_money(principal)} PiPesos", show_alert=True)
        elif st == "active": await q.answer("Ya tienes un préstamo pendiente.", show_alert=True)
        elif st == "limit": await q.answer(f"Tu límite actual es {_money(info)}.", show_alert=True)
        else: await q.answer("No pude crear el préstamo.", show_alert=True)
        return await bankiu(update, context)
    if data == "bank_pay_all":
        st, info = pay_loan(uid)
        if st == "ok":
            paid, remaining = info; await q.answer(f"Pagaste {_money(paid)}. Pendiente: {_money(remaining)}", show_alert=True)
        elif st == "money": await q.answer("No tienes saldo disponible para pagar ahora.", show_alert=True)
        else: await q.answer("No encontré una deuda activa.", show_alert=True)
        return await bankiu(update, context)
    if data == "bank_history":
        await q.answer()
        conn = _get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT principal,saldo_pendiente,estado,creado_en,vence_en FROM bankiu_loans_tb WHERE user_id=%s ORDER BY loan_id DESC LIMIT 8",(uid,)); rows=c.fetchall()
        finally: _put_connection(conn)
        lines=["📜 BANKIU · Historial"]
        for p,rem,state,created,due in rows: lines.append(f"• {_money(p)} PP · {state} · pendiente {_money(rem)} · {created:%d/%m/%Y}")
        if not rows: lines.append("Todavía no tienes préstamos.")
        return await q.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ BANKIU",callback_data="bank_home")]]))
    if data == "bank_home":
        await q.answer()
        return await bankiu(update, context)


async def pagarbanco(update: Update, context: ContextTypes.DEFAULT_TYPE):
    requested = None
    if context.args:
        try: requested = int(context.args[0].replace(",", ""))
        except ValueError: return await update.message.reply_text("Usa /pagarbanco 5000 o abre /bankiu.")
        if requested <= 0:
            return await update.message.reply_text("El pago debe ser mayor que 0 PiPesos.")
    st, info = pay_loan(update.effective_user.id, requested)
    if st == "ok":
        paid, rem = info; return await update.message.reply_text(f"🏦 Pago recibido: {_money(paid)} PiPesos.\nPendiente: {_money(rem)} PiPesos.")
    if st == "none": return await update.message.reply_text("🏦 No tienes préstamos pendientes.")
    if st == "money": return await update.message.reply_text("💸 No tienes saldo disponible para ese pago.")
    await update.message.reply_text("BANKIU no pudo procesar el pago.")


# -------- Participation ranking: one point per user per minute, batched DB writes. --------
async def track_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u or u.is_bot or update.effective_chat.type == "private": return
    now = datetime.now(timezone.utc)
    with _activity_lock:
        last = _activity_last.get(u.id)
        if last and (now-last).total_seconds() < 60: return
        _activity_last[u.id] = now
        _activity_pending[u.id] += 1


def _ensure_cycle(c):
    c.execute("SELECT cycle_id,starts_at,ends_at,estado FROM participation_cycles_tb WHERE estado='activo' ORDER BY cycle_id DESC LIMIT 1 FOR UPDATE")
    row=c.fetchone()
    now=datetime.now(timezone.utc)
    if row and row[2] > now: return row
    if row:
        c.execute("UPDATE participation_cycles_tb SET estado='cerrado' WHERE cycle_id=%s",(row[0],))
    c.execute("INSERT INTO participation_cycles_tb(starts_at,ends_at,estado) VALUES(NOW(),NOW()+INTERVAL '14 days','activo') RETURNING cycle_id,starts_at,ends_at,estado")
    return c.fetchone()


def flush_activity_sync():
    with _activity_lock:
        batch=dict(_activity_pending); _activity_pending.clear()
    if not batch: return 0
    conn=_get_connection()
    try:
        c=conn.cursor(); cycle=_ensure_cycle(c); cid=cycle[0]
        for uid,points in batch.items():
            c.execute("INSERT INTO participation_scores_tb(cycle_id,user_id,puntos) VALUES(%s,%s,%s) ON CONFLICT(cycle_id,user_id) DO UPDATE SET puntos=participation_scores_tb.puntos+EXCLUDED.puntos",(cid,uid,points))
        conn.commit(); return sum(batch.values())
    except Exception:
        conn.rollback()
        with _activity_lock:
            for uid,points in batch.items(): _activity_pending[uid]+=points
        raise
    finally:_put_connection(conn)


async def activity_flush_job(context: ContextTypes.DEFAULT_TYPE):
    try: flush_activity_sync()
    except Exception as exc: print("[RANKING] flush",exc)


def _award_cycle(c, cycle_id:int):
    c.execute("SELECT 1 FROM participation_awards_tb WHERE cycle_id=%s LIMIT 1",(cycle_id,))
    if c.fetchone(): return
    c.execute("SELECT user_id,puntos FROM participation_scores_tb WHERE cycle_id=%s ORDER BY puntos DESC,user_id ASC LIMIT 3",(cycle_id,)); top=c.fetchall()
    names=("👑 Soberano del Caos","⚔️ Guardián del Podio","🔥 Leyenda de la Quincena")
    codes=("rank_soberano","rank_guardian","rank_leyenda")
    for pos,(uid,points) in enumerate(top,1):
        code=f"{codes[pos-1]}_{cycle_id}"
        c.execute("""INSERT INTO social_assets_tb(asset_type,code,nombre,rareza,serial_no,serial_total,valor_base,propietario_id,origen,transferible)
                     VALUES('titulo',%s,%s,'mitico',1,1,0,%s,%s,TRUE) RETURNING asset_id""",(code,names[pos-1],uid,f"ranking:{cycle_id}:puesto:{pos}"))
        aid=c.fetchone()[0]
        c.execute("INSERT INTO social_asset_history_tb(asset_id,a_user,accion,precio) VALUES(%s,%s,'premio_ranking',0)",(aid,uid))
        c.execute("INSERT INTO participation_awards_tb(cycle_id,position,user_id,asset_id,puntos) VALUES(%s,%s,%s,%s,%s)",(cycle_id,pos,uid,aid,points))


def ranking_maintenance_sync():
    flush_activity_sync()
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT cycle_id,ends_at FROM participation_cycles_tb WHERE estado='activo' ORDER BY cycle_id DESC LIMIT 1 FOR UPDATE"); row=c.fetchone()
        if row and row[1] <= datetime.now(timezone.utc):
            _award_cycle(c,row[0]); c.execute("UPDATE participation_cycles_tb SET estado='cerrado' WHERE cycle_id=%s",(row[0],))
        _ensure_cycle(c); conn.commit()
    except Exception: conn.rollback(); raise
    finally:_put_connection(conn)


async def ranking_maintenance_job(context: ContextTypes.DEFAULT_TYPE):
    try: ranking_maintenance_sync()
    except Exception as exc: print("[RANKING] maintenance",exc)


async def ranking(update:Update, context:ContextTypes.DEFAULT_TYPE):
    try: flush_activity_sync()
    except Exception: pass
    conn=_get_connection()
    try:
        c=conn.cursor(); cycle=_ensure_cycle(c); conn.commit(); cid,_,end,_=cycle
        c.execute("""SELECT s.user_id,s.puntos,COALESCE(u.username,'Usuario '||s.user_id::text)
                     FROM participation_scores_tb s LEFT JOIN usuarios_tb u ON u.id_user=s.user_id
                     WHERE s.cycle_id=%s ORDER BY s.puntos DESC,s.user_id ASC LIMIT 10""",(cid,)); rows=c.fetchall()
    finally:_put_connection(conn)
    left=max(timedelta(),end-datetime.now(timezone.utc)); d=left.days; h=left.seconds//3600; m=(left.seconds%3600)//60
    lines=[f"🏆 RANKING QUINCENAL\n⏳ Cierra en {d}d {h:02d}h {m:02d}m\n"]
    medals=("🥇","🥈","🥉")
    for i,(uid,pts,name) in enumerate(rows,1): lines.append(f"{medals[i-1] if i<=3 else str(i)+'.'} {name} — {pts} pts")
    if not rows: lines.append("Todavía no hay actividad registrada en esta quincena.")
    lines.append("\n🎁 Top 3 recibe un título exclusivo y transferible de esta edición.")
    await update.message.reply_text("\n".join(lines))


async def ranking_pipesos(update:Update, context:ContextTypes.DEFAULT_TYPE):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT id_user,COALESCE(username,'Usuario '||id_user::text),saldo FROM usuarios_tb ORDER BY saldo DESC,id_user ASC LIMIT 10"); rows=c.fetchall()
    finally:_put_connection(conn)
    lines=["💰 RANKING DE PIPESOS"]
    for i,(_,name,saldo) in enumerate(rows,1): lines.append(f"{i}. {name} — {_money(saldo)} PP")
    await update.message.reply_text("\n".join(lines))


async def bankiu_collect_overdue_job(context: ContextTypes.DEFAULT_TYPE):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE bankiu_loans_tb SET estado='vencido' WHERE estado='activo' AND vence_en<=NOW()")
        c.execute("SELECT loan_id,user_id,saldo_pendiente FROM bankiu_loans_tb WHERE estado='vencido' AND saldo_pendiente>0 ORDER BY loan_id FOR UPDATE")
        for loan_id,uid,pending in c.fetchall():
            c.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s FOR UPDATE",(uid,)); r=c.fetchone(); available=max(0,int(r[0])) if r else 0
            take=min(available,int(pending))
            if take<=0: continue
            remaining=int(pending)-take
            c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s",(take,uid))
            c.execute("UPDATE bankiu_loans_tb SET saldo_pendiente=%s,estado=%s,pagado_en=CASE WHEN %s=0 THEN NOW() ELSE pagado_en END WHERE loan_id=%s",(remaining,'pagado' if remaining==0 else 'vencido',remaining,loan_id))
            c.execute("INSERT INTO bankiu_payments_tb(loan_id,user_id,monto,tipo) VALUES(%s,%s,%s,'cobro_vencido')",(loan_id,uid,take))
        conn.commit()
    except Exception as exc: conn.rollback(); print("[BANKIU] overdue collection",exc)
    finally:_put_connection(conn)
