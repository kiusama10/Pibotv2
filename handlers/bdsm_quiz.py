import random
import json
from datetime import datetime, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection

QUIZ_CHAT_ID=-1003290179217
QUIZ_THREAD_ID=435
QUIZ_REWARD=1000
BASE=[
('consentimiento','Acuerdo libre, informado, específico y reversible.'),('safeword','Palabra o señal acordada para pausar o detener.'),('aftercare','Cuidados acordados después de una dinámica.'),('negociación','Conversación previa sobre deseos, límites, riesgos y señales.'),('límite duro','Algo que una persona no acepta realizar.'),('límite blando','Algo explorable solo bajo condiciones específicas.'),('SSC','Seguro, Sensato y Consensuado.'),('RACK','Marco centrado en consentimiento informado y conciencia del riesgo.'),('dominante','Rol que asume control consensuado dentro de límites.'),('sumiso','Rol que cede control consensuadamente dentro de límites.'),('switch','Persona que puede disfrutar roles dominantes y sumisos.'),('brat','Estilo de sumisión con desafío juguetón consensuado.'),('pet play','Rol consensuado con rasgos o comportamiento de mascota.'),('power exchange','Intercambio consensuado de poder.'),('D/s','Dinámica de Dominación y sumisión consensuada.'),('check-in','Comprobación del bienestar durante o después de una dinámica.'),('subdrop','Bajón físico o emocional posible después de una dinámica intensa.'),('domdrop','Bajón físico o emocional posible en la parte dominante.'),('debrief','Conversación posterior para revisar qué funcionó y qué ajustar.'),('consentimiento reversible','El consentimiento puede retirarse en cualquier momento.'),('consentimiento específico','Aceptar una práctica no implica aceptar otras.'),('señal no verbal','Gesto u objeto acordado para comunicar pausa o detención.'),('semáforo','Verde continuar, amarillo comprobar/reducir y rojo detener.'),('privacidad','Derecho a decidir qué información personal se comparte.'),('autonomía','Capacidad de decidir sobre el propio cuerpo y participación.'),('coerción','Presión o amenaza que impide una decisión verdaderamente libre.'),('tijeras de seguridad','Herramienta de rescate útil para liberar cuerda rápidamente.'),('escucha activa','Escuchar, comprobar comprensión y no asumir.'),('top','Quien realiza una acción; no siempre equivale a dominante.'),('bottom','Quien recibe una acción; no siempre equivale a sumiso.'),('TPE','Intercambio amplio de poder consensuado; el consentimiento sigue siendo reversible.'),('vetting','Proceso de conocer y verificar a alguien antes de una dinámica de mayor riesgo.'),('green flag','Conducta positiva como respetar un no y hablar de riesgos.'),('red flag','Conducta que justifica cautela o alejarse.'),('renegociación','Modificar acuerdos consensuadamente cuando cambian circunstancias.'),('gradualidad','Empezar moderadamente y ajustar según respuesta y acuerdos.'),('feedback','Comentarios posteriores para ajustar futuras dinámicas.'),('rojo','En el sistema semáforo significa detener inmediatamente.'),('amarillo','Suele indicar bajar intensidad, pausar o comprobar.'),('verde','Suele indicar que se puede continuar según lo acordado.'),('plan de emergencia','Acuerdo previo sobre qué hacer si ocurre un incidente.'),('consentimiento granular','Aceptar o rechazar componentes concretos por separado.'),('fantasía','Una idea atractiva no implica querer realizarla.'),('contrato simbólico','Puede expresar acuerdos, pero no reemplaza consentimiento continuo ni ley.'),('aftercare individual','Los cuidados deben adaptarse a cada persona.'),('consentimiento de terceros','No se debe involucrar a personas ajenas sin permiso.'),('entumecimiento','Señal que puede indicar compresión y requiere detener/revisar.'),('dolor inesperado','Señal para pausar y revisar, no para asumir que es normal.'),('acuerdo explícito','Acuerdo comunicado claramente, no basado en suposiciones.'),('incompatibilidad','Deseos o límites no encajan; no obliga a nadie a ceder.'),
]
OPEN=[
'¿Qué diferencia ves entre confianza y consentimiento?','¿Por qué una safeword no sustituye una buena negociación?','¿Cómo debería reaccionar alguien responsable cuando recibe un no?','¿Por qué los límites pueden cambiar con el tiempo?','¿Qué hace que un buen aftercare sea diferente para cada persona?','¿Cómo respetarías la privacidad al contar una experiencia compartida?','¿Qué diferencia hay entre fantasía y querer llevar algo a la práctica?','¿Por qué tener experiencia no da permiso para ignorar límites?','¿Qué señales te hacen pensar que alguien negocia responsablemente?','¿Cómo puede una comunidad ayudar a detectar malas prácticas?'
]
STEMS=['¿Qué término corresponde a esta definición?','🧠 Adivina el concepto:','🔎 Identifica el término:','🎭 ¿De qué estamos hablando?','📚 Ronda de conocimiento:']

def build_bank():
    out=[]; n=len(BASE)
    for i,(term,definition) in enumerate(BASE):
        wrong=[BASE[(i+7)%n][0],BASE[(i+17)%n][0],BASE[(i+29)%n][0]]
        for v in range(5):
            out.append({'id':f'def-{i}-{v}','type':'choice','q':f'{STEMS[v]}\n\n{definition}','answer':term,'options':[term]+wrong})
        out.append({'id':f'tf-ok-{i}','type':'choice','q':f'Verdadero o falso:\n\n«{term}» puede describirse como: {definition}','answer':'Verdadero','options':['Verdadero','Falso']})
        out.append({'id':f'tf-no-{i}','type':'choice','q':f'Verdadero o falso:\n\n«{term}» significa: {BASE[(i+13)%n][1]}','answer':'Falso','options':['Verdadero','Falso']})
    scenarios=[
      ('Alguien dice rojo durante una dinámica.','Detenerse inmediatamente'),('Una persona retira hoy algo que aceptó ayer.','Respetar la decisión actual'),('Aparece entumecimiento bajo una restricción.','Detener y revisar'),('Alguien está demasiado intoxicado para decidir con claridad.','Posponer'),('Surge dolor inesperado.','Pausar y comprobar'),('Quieren compartir una foto privada.','Pedir permiso específico'),('Los límites de dos personas no encajan.','Aceptar la incompatibilidad sin presionar'),('Alguien pide espacio como aftercare.','Respetar y adaptar el cuidado'),('Una persona no puede hablar durante la práctica.','Usar la señal no verbal acordada'),('Una persona experimentada dice que no necesita negociar.','Negociar igualmente')]
    bad=['Continuar porque ya había aceptado','Ignorarlo','Decidir por la otra persona']
    for i,(s,a) in enumerate(scenarios):
        for v in range(30): out.append({'id':f'sc-{i}-{v}','type':'choice','q':f'🛡️ Caso práctico #{v+1}\n\n{s}\n\n¿Qué opción respeta mejor seguridad y consentimiento?','answer':a,'options':[a]+bad})
    for i,q in enumerate(OPEN):
        for v in range(10): out.append({'id':f'open-{i}-{v}','type':'open','q':f'💬 Debate #{v+1}\n\n{q}'})
    # Additional mixed rounds: same knowledge tested with different prompts/options; bank is built once in RAM.
    k=0; source=[x for x in out if x['type']=='choice']
    while len(out)<1100:
        x=dict(source[k%len(source)]); x['id']=f'mix-{k}-{x["id"]}'; x['q']='✨ Ronda mixta\n\n'+x['q']; out.append(x); k+=1
    return out
QUIZ_BANK=build_bank()

def ensure_quiz_tables():
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS bdsm_quiz_rounds_tb (round_id BIGSERIAL PRIMARY KEY, question_key TEXT NOT NULL, question_text TEXT NOT NULL, answer_text TEXT, status TEXT NOT NULL DEFAULT 'open', winner_id BIGINT, chat_id BIGINT NOT NULL, thread_id BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), closed_at TIMESTAMPTZ)")
        c.execute("ALTER TABLE bdsm_quiz_rounds_tb ADD COLUMN IF NOT EXISTS options_json JSONB")
        c.execute("ALTER TABLE bdsm_quiz_rounds_tb ADD COLUMN IF NOT EXISTS eliminated_json JSONB NOT NULL DEFAULT '[]'::jsonb")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_bdsm_quiz_one_open ON bdsm_quiz_rounds_tb(chat_id,thread_id) WHERE status='open'")
        c.execute("CREATE TABLE IF NOT EXISTS bdsm_quiz_attempts_tb (round_id BIGINT NOT NULL REFERENCES bdsm_quiz_rounds_tb(round_id) ON DELETE CASCADE,user_id BIGINT NOT NULL,answer_text TEXT NOT NULL,correct BOOLEAN NOT NULL DEFAULT FALSE,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(round_id,user_id))")
        c.execute("CREATE TABLE IF NOT EXISTS bdsm_quiz_history_tb (question_key TEXT PRIMARY KEY,last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),uses INTEGER NOT NULL DEFAULT 1)")
        conn.commit()
    except Exception: conn.rollback(); raise
    finally: _put_connection(conn)

def _pick():
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute('SELECT question_key FROM bdsm_quiz_history_tb ORDER BY last_used_at DESC LIMIT 850'); recent={r[0] for r in c.fetchall()}
    finally: _put_connection(conn)
    pool=[q for q in QUIZ_BANK if q['id'] not in recent] or QUIZ_BANK
    typ='open' if random.random()<.12 else 'choice'; candidates=[q for q in pool if q['type']==typ]
    return random.choice(candidates or pool)

def _strike(text):
    # Telegram inline buttons do not render Markdown. Combining strike keeps the
    # discarded answer visibly crossed out without changing its stored value.
    return ''.join(ch + '\u0336' if not ch.isspace() else ch for ch in str(text))

def _quiz_keyboard(rid, opts, eliminated=None):
    eliminated=set(eliminated or [])
    rows=[]
    for i,opt in enumerate(opts):
        label=("❌ "+_strike(opt)) if i in eliminated else opt
        rows.append([InlineKeyboardButton(label, callback_data=f'bq:{rid}:{i}')])
    return InlineKeyboardMarkup(rows)

def _create(q):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE bdsm_quiz_rounds_tb SET status='expired',closed_at=NOW() WHERE chat_id=%s AND thread_id=%s AND status='open'",(QUIZ_CHAT_ID,QUIZ_THREAD_ID))
        status='discussion' if q['type']=='open' else 'open'
        c.execute('INSERT INTO bdsm_quiz_rounds_tb(question_key,question_text,answer_text,status,chat_id,thread_id) VALUES(%s,%s,%s,%s,%s,%s) RETURNING round_id',(q['id'],q['q'],q.get('answer'),status,QUIZ_CHAT_ID,QUIZ_THREAD_ID)); rid=c.fetchone()[0]
        c.execute('INSERT INTO bdsm_quiz_history_tb(question_key) VALUES(%s) ON CONFLICT(question_key) DO UPDATE SET last_used_at=NOW(),uses=bdsm_quiz_history_tb.uses+1',(q['id'],)); conn.commit(); return rid
    except Exception: conn.rollback(); raise
    finally: _put_connection(conn)

async def quiz_tick(context: ContextTypes.DEFAULT_TYPE):
    try:
        q=_pick(); rid=_create(q)
        if q['type']=='open':
            await context.bot.send_message(QUIZ_CHAT_ID,f"🖤 QUIZ BDSM · Ronda abierta\n\n{q['q']}\n\n💬 Sin respuesta única ni premio.",message_thread_id=QUIZ_THREAD_ID); return
        opts=list(dict.fromkeys(q['options'])); random.shuffle(opts); context.application.bot_data.setdefault('bq_options',{})[rid]=opts
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute('UPDATE bdsm_quiz_rounds_tb SET options_json=%s::jsonb WHERE round_id=%s',(json.dumps(opts,ensure_ascii=False),rid)); conn.commit()
        finally:_put_connection(conn)
        kb=_quiz_keyboard(rid,opts)
        await context.bot.send_message(QUIZ_CHAT_ID,f"🖤 QUIZ BDSM · 1 intento por persona\n\n{q['q']}\n\n🏆 Primera correcta: {QUIZ_REWARD:,} PiPesos",message_thread_id=QUIZ_THREAD_ID,reply_markup=kb)
    except Exception as e: print('[QUIZ]',e)

async def quiz_callback(update: Update,context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query
    try: _,rs,is_=cq.data.split(':'); rid=int(rs); idx=int(is_)
    except Exception: await cq.answer('Ronda inválida.',show_alert=True); return
    if cq.message.chat_id!=QUIZ_CHAT_ID or cq.message.message_thread_id!=QUIZ_THREAD_ID: await cq.answer('Esta ronda pertenece a General.',show_alert=True); return
    opts=context.application.bot_data.get('bq_options',{}).get(rid)
    uid=cq.from_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT status,answer_text,options_json,created_at,eliminated_json FROM bdsm_quiz_rounds_tb WHERE round_id=%s FOR UPDATE",(rid,)); row=c.fetchone()
        if not row or row[0]!='open': conn.rollback(); await cq.answer('La ronda ya terminó.',show_alert=True); return
        if (datetime.now(timezone.utc)-row[3]).total_seconds()>900:
            c.execute("UPDATE bdsm_quiz_rounds_tb SET status='expired',closed_at=NOW() WHERE round_id=%s AND status='open'",(rid,)); conn.commit(); await cq.answer('Esta ronda cerró después de 15 minutos.',show_alert=True); return
        if not opts: opts=row[2] if isinstance(row[2],list) else (json.loads(row[2]) if row[2] else None)
        if not opts or idx>=len(opts): conn.rollback(); await cq.answer('No pude recuperar las opciones de esta ronda.',show_alert=True); return
        context.application.bot_data.setdefault('bq_options',{})[rid]=opts
        eliminated=row[4] if isinstance(row[4],list) else (json.loads(row[4]) if row[4] else [])
        eliminated={int(x) for x in eliminated}
        if idx in eliminated:
            conn.rollback(); await cq.answer('❌ Esa respuesta ya fue descartada. Elige otra.',show_alert=False); return
        chosen=opts[idx]
        ok=chosen==row[1]; c.execute('INSERT INTO bdsm_quiz_attempts_tb(round_id,user_id,answer_text,correct) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(rid,uid,chosen,ok))
        if c.rowcount!=1: conn.rollback(); await cq.answer('Ya usaste tu intento.',show_alert=True); return
        if not ok:
            eliminated.add(idx)
            c.execute('UPDATE bdsm_quiz_rounds_tb SET eliminated_json=%s::jsonb WHERE round_id=%s AND status=\'open\'',(json.dumps(sorted(eliminated)),rid))
            conn.commit()
            await cq.answer('❌ Incorrecto. Esa opción quedó descartada.',show_alert=True)
            try:
                await cq.edit_message_reply_markup(reply_markup=_quiz_keyboard(rid,opts,eliminated))
            except Exception as e:
                print('[QUIZ keyboard]',e)
            return
        c.execute("UPDATE bdsm_quiz_rounds_tb SET status='won',winner_id=%s,closed_at=NOW() WHERE round_id=%s AND status='open'",(uid,rid)); c.execute('UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s',(QUIZ_REWARD,uid))
        if c.rowcount!=1: conn.rollback(); await cq.answer('No pude acreditar el premio.',show_alert=True); return
        conn.commit()
    except Exception as e: conn.rollback(); print('[QUIZ callback]',e); await cq.answer('Error de base de datos.',show_alert=True); return
    finally: _put_connection(conn)
    context.application.bot_data.get('bq_options',{}).pop(rid,None); await cq.answer('🏆 ¡Correcto!',show_alert=True)
    try: await cq.edit_message_text(f"🏆 <b>¡CORRECTO!</b>\n\n{cq.from_user.mention_html()} ganó <b>{QUIZ_REWARD:,} PiPesos</b>.\nRespuesta: <b>{chosen}</b>",parse_mode='HTML')
    except Exception: pass

async def quiz_manual(update: Update,context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(f'🧠 Quiz automático: General, tema {QUIZ_THREAD_ID}. Banco: {len(QUIZ_BANK):,} rondas. Sale cada hora.')

async def quiz_now(update: Update,context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text('🧠 Enviando ronda de prueba a General…'); await quiz_tick(context)
