"""Vínculos sociales/BDSM consensuados. Economía atómica: 20k al aceptar y 20k al separarse."""
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection, get_id_user

LINK_COST=20_000
SEPARATION_COST=20_000

OPENINGS=[
"Hay personas que llegan sin hacer ruido y, con el tiempo, terminan ocupando un lugar que nadie más podría llenar.",
"A veces una conexión empieza con una conversación cualquiera y termina convirtiéndose en un espacio de confianza, complicidad y cuidado.",
"No todos los encuentros están destinados a convertirse en un vínculo; algunos, sin embargo, empiezan a sentirse demasiado especiales para dejarlos sin nombre.",
"Entre tantas personas que cruzan nuestro camino, de vez en cuando aparece alguien con quien quedarse un poco más deja de sentirse casual.",
"Un vínculo no se construye por obligación: nace cuando dos personas deciden elegirse, respetarse y cuidar lo que comparten.",
"Hay conexiones que se explican con palabras y otras que simplemente se sienten; esta parece pedir una historia propia.",
"La confianza se construye despacio, con pequeños actos, conversaciones honestas y la libertad de poder decir sí o no sin miedo.",
"Compartir un vínculo significa elegir caminar juntos sin dejar de ser dos personas completas, libres y capaces de decidir.",
"Algunas historias comienzan con una coincidencia y continúan porque dos personas deciden que vale la pena cuidarlas.",
"Lo bonito de elegir a alguien no está en necesitarlo, sino en poder seguir siendo uno mismo y aun así querer compartir el camino.",
]
MIDDLES=[
"Hoy {a} quiere preguntarle a {b} si desea convertir esa conexión en un vínculo elegido por ambos.",
"Por eso {a} ha decidido dar un pequeño paso y preguntarle a {b} si quiere construir un vínculo juntos.",
"Hoy {a} pone esta pregunta frente a {b}, no como una exigencia, sino como una invitación que puede aceptar o rechazar con total libertad.",
"Con esa intención, {a} quiere saber si {b} desea darle un nombre especial a lo que han ido construyendo.",
"Así que {a} deja la decisión en manos de {b}: compartir un vínculo y comenzar una nueva parte de su historia.",
]
ENDINGS=[
"Que la respuesta nazca de lo que ambos quieren, porque un vínculo bonito empieza precisamente ahí: en poder elegirlo.",
"No promete perfección; promete la oportunidad de construir algo desde la comunicación, el respeto y el consentimiento.",
"Si la respuesta es sí, que sea porque ambos desean estar ahí. Y si es no, que la confianza para decirlo también sea respetada.",
"Lo importante no es la etiqueta, sino lo que decidan cuidar detrás de ella: confianza, límites, comunicación y cariño.",
"Porque elegir un vínculo también significa recordar que cada día ambas personas siguen teniendo voz propia dentro de él.",
]
ACCEPT=[
"Y así comienza un nuevo capítulo. {b} aceptó el vínculo de {a}. No significa pertenecer por obligación ni prometer que nada cambiará; significa que hoy ambos decidieron elegirse y darle un lugar especial a lo que comparten. Que nunca falten la comunicación, el consentimiento y esas pequeñas cosas que hacen que quedarse siga siendo una elección bonita.",
"La respuesta fue sí. {a} y {b} han decidido formar un vínculo. Desde ahora aparecerá en sus perfiles como recuerdo de esta decisión compartida. Que sea un espacio donde puedan hablar, poner límites, reír, aprender y seguir eligiéndose sin perder aquello que hace único a cada uno.",
"Dos caminos acaban de decidir caminar un tramo juntos. {a} y {b} ahora comparten un vínculo. Que lo que construyan no se mida solamente por cuánto dure, sino por la confianza, el respeto y los buenos recuerdos que sean capaces de dejar en el camino.",
]
SEPARATE=[
"No todos los vínculos que terminan fueron un error. Algunas personas llegan para acompañarnos durante una parte del camino, enseñarnos algo, dejarnos recuerdos y después continuar por rutas diferentes. Hoy el vínculo entre {a} y {b} llega a su final. Lo vivido no desaparece; simplemente deja de definir el siguiente capítulo de sus historias.",
"A veces cuidar una historia también significa saber cuándo dejarla descansar. {a} y {b} ya no comparten un vínculo. Lo que alguna vez eligieron fue real en su momento, y terminarlo no obliga a convertir los recuerdos buenos en algo malo. Cada uno vuelve a caminar por su lado, con espacio para escribir lo que venga después.",
"Soltar no siempre significa olvidar. Hay despedidas que simplemente reconocen que dos personas ya no desean caminar de la misma manera. El vínculo de {a} y {b} termina aquí, con la posibilidad de conservar lo aprendido y seguir adelante sin convertir el final en una negación de todo lo anterior.",
"El vínculo entre {a} y {b} ha llegado a su última página. Algunas historias están hechas para durar muchos capítulos y otras para enseñarnos algo antes de terminar. Ninguna necesita ser eterna para haber significado algo. Desde hoy, cada uno vuelve a tener su perfil libre para una nueva historia.",
]

def ensure_vinculo_tables():
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS vinculo_proposals_tb(
          proposal_id BIGSERIAL PRIMARY KEY, proposer_id BIGINT NOT NULL, target_id BIGINT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), resolved_at TIMESTAMPTZ)""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_vinculo_prop_pending ON vinculo_proposals_tb(target_id,status,created_at DESC)")
        c.execute("""CREATE TABLE IF NOT EXISTS vinculos_tb(
          vinculo_id BIGSERIAL PRIMARY KEY, user_a BIGINT NOT NULL, user_b BIGINT NOT NULL,
          status TEXT NOT NULL DEFAULT 'active', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), ended_at TIMESTAMPTZ, ended_by BIGINT,
          CHECK(user_a<>user_b))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_vinculos_a ON vinculos_tb(user_a,status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_vinculos_b ON vinculos_tb(user_b,status)")
        conn.commit()
    except Exception: conn.rollback(); raise
    finally:_put_connection(conn)

def _name(c,uid):
    c.execute("SELECT COALESCE(NULLIF(username,''),nombre,%s) FROM perfiles_tb WHERE id_user=%s",(f"Usuario {uid}",uid)); r=c.fetchone(); return r[0] if r else f"Usuario {uid}"

def _active(c,uid,lock=False):
    c.execute("SELECT vinculo_id,user_a,user_b FROM vinculos_tb WHERE status='active' AND (user_a=%s OR user_b=%s) ORDER BY vinculo_id DESC LIMIT 1"+(" FOR UPDATE" if lock else ""),(uid,uid)); return c.fetchone()

def _proposal_text(a,b): return f"💞 PROPUESTA DE VÍNCULO\n\n{random.choice(OPENINGS)}\n\n{random.choice(MIDDLES).format(a=a,b=b)}\n\n{random.choice(ENDINGS)}\n\n💰 Formar el vínculo cuesta {LINK_COST:,} PiPesos. Solo se cobrará a quien hizo la propuesta si tú aceptas."

async def vinculo(update:Update,context:ContextTypes.DEFAULT_TYPE):
    msg=update.effective_message; uid=update.effective_user.id; target=None
    if msg.reply_to_message and msg.reply_to_message.from_user: target=msg.reply_to_message.from_user.id
    elif context.args and context.args[0].startswith('@'): target=get_id_user(context.args[0][1:])
    if not target: return await msg.reply_text("💞 Responde al mensaje de la persona con /vinculo o usa /vinculo @usuario.")
    if target==uid: return await msg.reply_text("💞 Un vínculo necesita dos personas distintas, poeta. 😂")
    conn=_get_connection()
    try:
        c=conn.cursor()
        if _active(c,uid) or _active(c,target): conn.rollback(); return await msg.reply_text("💞 Una de las dos personas ya tiene un vínculo activo.")
        c.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s",(uid,)); r=c.fetchone()
        if not r or r[0]<LINK_COST: conn.rollback(); return await msg.reply_text(f"💸 Necesitas {LINK_COST:,} PiPesos para hacer la propuesta. No se cobrará nada hasta que sea aceptada.")
        c.execute("UPDATE vinculo_proposals_tb SET status='expired',resolved_at=NOW() WHERE status='pending' AND (proposer_id IN (%s,%s) OR target_id IN (%s,%s))",(uid,target,uid,target))
        c.execute("INSERT INTO vinculo_proposals_tb(proposer_id,target_id) VALUES(%s,%s) RETURNING proposal_id",(uid,target)); pid=c.fetchone()[0]
        a,b=_name(c,uid),_name(c,target); conn.commit()
    except Exception as e: conn.rollback(); print('[VINCULO create]',e); return await msg.reply_text("⚠️ No pude crear la propuesta.")
    finally:_put_connection(conn)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("💞 Aceptar",callback_data=f"vin:accept:{pid}"),InlineKeyboardButton("🌙 Rechazar",callback_data=f"vin:reject:{pid}")]])
    await msg.reply_text(_proposal_text(a,b),reply_markup=kb)


async def cancelarvinculo(update:Update,context:ContextTypes.DEFAULT_TYPE):
    """Cancela únicamente una propuesta pendiente creada por quien ejecuta el comando."""
    uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""SELECT proposal_id,target_id FROM vinculo_proposals_tb
          WHERE proposer_id=%s AND status='pending' ORDER BY created_at DESC LIMIT 1 FOR UPDATE""",(uid,)); row=c.fetchone()
        if not row:
            conn.rollback(); return await update.effective_message.reply_text("💞 No tienes una propuesta de vínculo pendiente para cancelar.")
        pid,target=row; target_name=_name(c,target)
        c.execute("UPDATE vinculo_proposals_tb SET status='cancelled',resolved_at=NOW() WHERE proposal_id=%s AND status='pending'",(pid,))
        conn.commit()
        await update.effective_message.reply_text(f"🌙 Propuesta de vínculo con {target_name} cancelada. No se cobró ningún PiPeso.")
    except Exception as e:
        conn.rollback(); print('[VINCULO cancel proposal]',e); await update.effective_message.reply_text("⚠️ No pude cancelar la propuesta.")
    finally:_put_connection(conn)

async def separarse(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); v=_active(c,uid)
        if not v: return await update.effective_message.reply_text("🌙 No tienes un vínculo activo que terminar.")
        vid,a,b=v; other=b if a==uid else a; on=_name(c,other)
    finally:_put_connection(conn)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton(f"💔 Confirmar · {SEPARATION_COST:,} PP",callback_data=f"vin:separate:{vid}"),InlineKeyboardButton("🌙 Mejor no",callback_data="vin:stay:0")]])
    await update.effective_message.reply_text(f"💔 TERMINAR VÍNCULO\n\nEstás a punto de cerrar tu vínculo con {on}. No es una decisión que PiBot vaya a ejecutar por un toque accidental.\n\nSepararse cuesta {SEPARATION_COST:,} PiPesos. El cobro y la separación ocurren juntos únicamente cuando confirmes. Si no tienes saldo suficiente, el vínculo seguirá intacto.",reply_markup=kb)

async def vinculo_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; parts=(q.data or '').split(':'); action=parts[1]; uid=q.from_user.id
    if action=='stay': await q.answer(); return await q.edit_message_text("💞 El vínculo sigue intacto. A veces un botón de ‘mejor no’ salva 20,000 PiPesos y una conversación incómoda. 😂")
    ident=int(parts[2]); conn=_get_connection()
    try:
        c=conn.cursor()
        if action in ('accept','reject'):
            c.execute("SELECT proposer_id,target_id,status FROM vinculo_proposals_tb WHERE proposal_id=%s FOR UPDATE",(ident,)); p=c.fetchone()
            if not p or p[2]!='pending': conn.rollback(); return await q.answer("Esta propuesta ya no está disponible.",show_alert=True)
            proposer,target,_=p
            if uid!=target: conn.rollback(); return await q.answer("Solo la persona invitada puede responder.",show_alert=True)
            if action=='reject':
                c.execute("UPDATE vinculo_proposals_tb SET status='rejected',resolved_at=NOW() WHERE proposal_id=%s",(ident,)); a,b=_name(c,proposer),_name(c,target); conn.commit(); await q.answer(); return await q.edit_message_text(f"🌙 {b} decidió no formar el vínculo con {a}.\n\nY está bien. Una propuesta solo tiene sentido cuando la respuesta puede ser un sí o un no con la misma libertad. No hubo ningún cobro y ambos perfiles permanecen como estaban.")
            if _active(c,proposer,True) or _active(c,target,True): conn.rollback(); return await q.answer("Una de las personas ya tiene otro vínculo activo.",show_alert=True)
            c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo>=%s",(LINK_COST,proposer,LINK_COST))
            if c.rowcount!=1: conn.rollback(); return await q.answer("Quien propuso ya no tiene los 20,000 PiPesos necesarios.",show_alert=True)
            c.execute("INSERT INTO vinculos_tb(user_a,user_b) VALUES(%s,%s)",(proposer,target)); c.execute("UPDATE vinculo_proposals_tb SET status='accepted',resolved_at=NOW() WHERE proposal_id=%s",(ident,)); a,b=_name(c,proposer),_name(c,target); conn.commit(); await q.answer(); return await q.edit_message_text(random.choice(ACCEPT).format(a=a,b=b)+f"\n\n💰 {LINK_COST:,} PiPesos fueron cobrados a {a}. El vínculo ya aparece en ambos perfiles.")
        if action=='separate':
            c.execute("SELECT user_a,user_b,status FROM vinculos_tb WHERE vinculo_id=%s FOR UPDATE",(ident,)); v=c.fetchone()
            if not v or v[2]!='active' or uid not in v[:2]: conn.rollback(); return await q.answer("Ese vínculo ya no está activo.",show_alert=True)
            a,b,_=v; c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo>=%s",(SEPARATION_COST,uid,SEPARATION_COST))
            if c.rowcount!=1: conn.rollback(); return await q.answer("Necesitas 20,000 PiPesos para confirmar la separación.",show_alert=True)
            c.execute("UPDATE vinculos_tb SET status='ended',ended_at=NOW(),ended_by=%s WHERE vinculo_id=%s AND status='active'",(uid,ident)); an,bn=_name(c,a),_name(c,b); conn.commit(); await q.answer(); return await q.edit_message_text(random.choice(SEPARATE).format(a=an,b=bn)+f"\n\n💸 PiBot cobró {SEPARATION_COST:,} PiPesos por cerrar el vínculo. BANKIU observa desde lejos y finge no estar feliz. 😂")
    except Exception as e:
        conn.rollback(); print('[VINCULO callback]',e); await q.answer("No pude completar la operación; no se confirmó ningún cobro.",show_alert=True)
    finally:_put_connection(conn)
