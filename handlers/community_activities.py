"""Actividades comunitarias PiBot: separación de automáticos, Pregunta del Día y ranking semanal."""
from __future__ import annotations
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection

CHAT_ID=-1003290179217
THREAD_ID=435
MEX=ZoneInfo('America/Mexico_City')
DAILY_REWARD=2000
WEEKLY_PRIZES=(10000,6000,3000)
AUTO_GAP_MINUTES=20
DAILY_PROTECT_MINUTES=45

CATS={
'roles':['tu rol actual','una dinámica que disfrutas','la forma en que vives tu rol','lo que esperas de una dinámica','algo que aprendiste sobre tu rol'],
'consentimiento':['poner un límite','recibir un no','renegociar un acuerdo','usar una palabra de seguridad','detener una dinámica'],
'confianza':['ganarte la confianza de alguien','sentirte seguro con alguien','ser vulnerable','delegar control','recuperar confianza después de un error'],
'comunicacion':['hablar de deseos','explicar un límite','dar feedback','pedir aftercare','decir que algo cambió'],
'aftercare':['recibir cuidados después','dar aftercare','pedir espacio después','hacer un check-in al día siguiente','descubrir qué cuidados necesitas'],
'comunidad':['conocer a alguien nuevo en BDSM','detectar una mala práctica','aprender de otras personas','corregir un mito','dar consejo a alguien que empieza'],
'preferencias':['una dinámica nueva','algo que te llamó la atención al empezar','una práctica que antes no entendías','un protocolo que te guste','una fantasía que prefieres dejar como fantasía'],
'experiencia':['tu primer acercamiento al BDSM','algo que harías diferente hoy','un error del que aprendiste','un momento que cambió tu perspectiva','algo que te sorprendió al aprender'],
'limites':['un límite que cambió con el tiempo','un límite que nunca negociarías','distinguir curiosidad de consentimiento','decidir que algo no es para ti','respetar una incompatibilidad'],
'relaciones':['separar rol y relación','mantener autonomía','manejar celos o inseguridad','crear acuerdos de pareja','hablar de expectativas'],
'seguridad':['prepararte antes de una dinámica','reaccionar ante algo inesperado','hacer un plan de emergencia','comprobar bienestar','decidir cuándo parar'],
'reflexion':['qué significa para ti la entrega','qué significa para ti dominar','qué hace valiosa una dinámica','qué diferencia poder de responsabilidad','qué hace que vuelvas a elegir una dinámica'],
}
PROMPTS=[
'¿Qué fue lo primero que aprendiste sobre {x} y qué piensas ahora?',
'¿Qué consejo le darías a alguien que está aprendiendo sobre {x}?',
'¿Qué detalle crees que la gente suele olvidar cuando se trata de {x}?',
'¿Qué tendría que pasar para que te sintieras cómodo/a con {x}?',
'¿Qué diferencia hay entre una buena y una mala experiencia con {x}?',
'¿Qué te gustaría que más personas entendieran sobre {x}?',
'¿Qué pregunta harías antes de involucrarte en {x}?',
'¿Qué señal te haría detenerte y hablar cuando se trata de {x}?',
'¿Qué pesa más para ti: la confianza, la experiencia o la comunicación cuando hablamos de {x}, y por qué?',
'¿Cómo ha cambiado tu manera de ver {x} con el tiempo?',
'¿Qué parte de {x} te parece más importante y por qué?',
'¿Qué mito sobre {x} te gustaría borrar?',
'¿Qué acuerdo considerarías indispensable antes de {x}?',
'¿Qué aprendiste viendo experiencias ajenas sobre {x}?',
'¿Qué haría que dijeras “esto sí es para mí” al hablar de {x}?',
'¿Qué haría que dijeras “hasta aquí” al hablar de {x}?',
'¿Cómo explicarías {x} a alguien que apenas empieza?',
'¿Qué valoras más de una persona cuando compartes {x}?',
'¿Qué crees que cambia cuando existe mucha confianza al hablar de {x}?',
'¿Qué error crees que es más fácil cometer con {x}?',
]
# 12 * 5 * 20 = 1,200 combinaciones distintas.
DAILY_BANK=[{'id':f'{cat}-{i}-{j}','category':cat,'q':tpl.format(x=x)} for cat,xs in CATS.items() for i,x in enumerate(xs) for j,tpl in enumerate(PROMPTS)]

def _week_start(now=None):
    now=(now or datetime.now(MEX)).date(); return now-timedelta(days=now.weekday())

def ensure_community_tables():
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS pibot_auto_state_tb(key TEXT PRIMARY KEY,last_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        c.execute("""CREATE TABLE IF NOT EXISTS daily_question_tb(id BIGSERIAL PRIMARY KEY,question_key TEXT NOT NULL,question_text TEXT NOT NULL,chat_id BIGINT NOT NULL,thread_id BIGINT,message_id BIGINT,status TEXT NOT NULL DEFAULT 'open',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
        c.execute("""CREATE TABLE IF NOT EXISTS daily_question_answers_tb(question_id BIGINT REFERENCES daily_question_tb(id) ON DELETE CASCADE,user_id BIGINT NOT NULL,reward BIGINT NOT NULL DEFAULT 2000,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(question_id,user_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS community_weekly_points_tb(week_start DATE NOT NULL,user_id BIGINT NOT NULL,quiz_points INT NOT NULL DEFAULT 0,daily_points INT NOT NULL DEFAULT 0,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(week_start,user_id))""")
        c.execute("""CREATE TABLE IF NOT EXISTS community_badges_tb(user_id BIGINT NOT NULL,badge TEXT NOT NULL,earned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),expires_at TIMESTAMPTZ,source TEXT,PRIMARY KEY(user_id,badge,earned_at))""")
        c.execute("""CREATE TABLE IF NOT EXISTS community_weekly_awards_tb(week_start DATE NOT NULL,place INT NOT NULL,user_id BIGINT NOT NULL,prize BIGINT NOT NULL,paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(week_start,place),UNIQUE(week_start,user_id))""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_daily_question_message ON daily_question_tb(chat_id,message_id)")
        conn.commit()
    except Exception: conn.rollback(); raise
    finally:_put_connection(conn)

def auto_can_post(kind:str, protect_daily=True):
    now=datetime.now(MEX)
    if protect_daily and now.hour==10 and now.minute < DAILY_PROTECT_MINUTES: return False
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT last_at FROM pibot_auto_state_tb WHERE key='last_auto'"); r=c.fetchone()
        if r and (datetime.now(timezone.utc)-r[0]).total_seconds()<AUTO_GAP_MINUTES*60: return False
        c.execute("INSERT INTO pibot_auto_state_tb(key,last_at) VALUES('last_auto',NOW()) ON CONFLICT(key) DO UPDATE SET last_at=NOW()")
        c.execute("INSERT INTO pibot_auto_state_tb(key,last_at) VALUES(%s,NOW()) ON CONFLICT(key) DO UPDATE SET last_at=NOW()",(kind,)); conn.commit(); return True
    except Exception: conn.rollback(); return True
    finally:_put_connection(conn)

def add_weekly_points(uid:int, quiz=0, daily=0):
    ws=_week_start(); conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""INSERT INTO community_weekly_points_tb(week_start,user_id,quiz_points,daily_points) VALUES(%s,%s,%s,%s)
        ON CONFLICT(week_start,user_id) DO UPDATE SET quiz_points=community_weekly_points_tb.quiz_points+EXCLUDED.quiz_points,daily_points=community_weekly_points_tb.daily_points+EXCLUDED.daily_points,updated_at=NOW()""",(ws,uid,quiz,daily)); conn.commit()
    except Exception: conn.rollback()
    finally:_put_connection(conn)

def ranking_rows(ws=None,limit=20):
    ws=ws or _week_start(); conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""SELECT p.user_id,p.quiz_points,p.daily_points,(p.quiz_points+p.daily_points) total,COALESCE(NULLIF(u.username,''),NULLIF(u.nombre,''),p.user_id::text)
        FROM community_weekly_points_tb p LEFT JOIN usuarios_tb u ON u.id_user=p.user_id WHERE p.week_start=%s ORDER BY total DESC,p.quiz_points DESC,p.updated_at ASC LIMIT %s""",(ws,limit)); return c.fetchall()
    finally:_put_connection(conn)

def ranking_text():
    rows=ranking_rows(); lines=['🏆 RANKING SEMANAL · CONOCIMIENTO','',f'Semana del {_week_start().strftime("%d/%m/%Y")}', '']
    if not rows: lines.append('Todavía no hay puntos esta semana.')
    for i,(uid,q,d,total,name) in enumerate(rows,1): lines.append(f'{i}. {name} — {total} pts · Quiz {q} · Pregunta del Día {d}')
    lines += ['', '🥇 10,000 · 🥈 6,000 · 🥉 3,000 PiPesos', '#RankingQuiz']
    return '\n'.join(lines)

async def ranking_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer(); await update.callback_query.message.reply_text(ranking_text())

async def daily_question_job(context:ContextTypes.DEFAULT_TYPE):
    # 10:00 Mexico. Daily post gets priority and resets shared spacing timestamp.
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT question_key FROM daily_question_tb ORDER BY created_at DESC LIMIT 1000"); recent={r[0] for r in c.fetchall()}
        pool=[x for x in DAILY_BANK if x['id'] not in recent] or DAILY_BANK; item=random.choice(pool)
        c.execute("UPDATE daily_question_tb SET status='closed' WHERE status='open'")
        c.execute("INSERT INTO daily_question_tb(question_key,question_text,chat_id,thread_id) VALUES(%s,%s,%s,%s) RETURNING id",(item['id'],item['q'],CHAT_ID,THREAD_ID)); qid=c.fetchone()[0]
        c.execute("INSERT INTO pibot_auto_state_tb(key,last_at) VALUES('last_auto',NOW()) ON CONFLICT(key) DO UPDATE SET last_at=NOW()")
        conn.commit()
    except Exception as e: conn.rollback(); print('[DAILY QUESTION]',e); return
    finally:_put_connection(conn)
    text=("⛓️ PREGUNTA DEL DÍA\n\nHoy toca conocernos un poquito más. No hace falta escribir una biblia; cualquier opinión cuenta.\n\n"
          f"{item['q']}\n\n💬 Responde DIRECTAMENTE a este mensaje para participar.\n💰 Recompensa: 2,000 PiPesos por persona.\n🏆 Tu primera respuesta suma 2 puntos al ranking semanal.\n\n#PreguntaDelDia")
    msg=await context.bot.send_message(CHAT_ID,text,message_thread_id=THREAD_ID,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🏆 Ver ranking semanal',callback_data='cr:rank')]]))
    conn=_get_connection()
    try: c=conn.cursor(); c.execute("UPDATE daily_question_tb SET message_id=%s WHERE id=%s",(msg.message_id,qid)); conn.commit()
    finally:_put_connection(conn)

async def daily_answer_handler(update:Update,context:ContextTypes.DEFAULT_TYPE):
    m=update.effective_message; u=update.effective_user
    if not m or not u or u.is_bot or not m.reply_to_message or update.effective_chat.id!=CHAT_ID: return
    replied=m.reply_to_message.message_id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT id FROM daily_question_tb WHERE chat_id=%s AND message_id=%s AND status='open' AND created_at>NOW()-INTERVAL '24 hours' FOR UPDATE",(CHAT_ID,replied)); r=c.fetchone()
        if not r: conn.rollback(); return
        qid=r[0]; c.execute("INSERT INTO daily_question_answers_tb(question_id,user_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",(qid,u.id))
        if c.rowcount!=1: conn.rollback(); return
        c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(DAILY_REWARD,u.id)); conn.commit()
    except Exception: conn.rollback(); return
    finally:_put_connection(conn)
    add_weekly_points(u.id,daily=2)
    await m.reply_text('✅ Respuesta registrada · +2,000 PiPesos · +2 puntos para #RankingQuiz')

async def weekly_awards_job(context:ContextTypes.DEFAULT_TYPE):
    # Pay the previous week idempotently.
    prev=_week_start()-timedelta(days=7); rows=ranking_rows(prev,3)
    if not rows: return
    conn=_get_connection(); paid=[]
    try:
        c=conn.cursor()
        for place,row in enumerate(rows,1):
            uid=row[0]; prize=WEEKLY_PRIZES[place-1]
            c.execute("INSERT INTO community_weekly_awards_tb(week_start,place,user_id,prize) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",(prev,place,uid,prize))
            if c.rowcount==1:
                c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(prize,uid)); badge=('🧠 Cerebro de la semana' if place==1 else ('📚 Sabio de la semana' if place==2 else '✨ Mente destacada')); c.execute("INSERT INTO community_badges_tb(user_id,badge,expires_at,source) VALUES(%s,%s,NOW()+INTERVAL '7 days','ranking_semanal')",(uid,badge)); paid.append((place,row[4],prize))
        conn.commit()
    except Exception: conn.rollback(); return
    finally:_put_connection(conn)
    if paid:
        txt='🏆 RESULTADO SEMANAL\n\n'+'\n'.join(f'{"🥇🥈🥉"[p-1]} {name} · +{prize:,} PiPesos' for p,name,prize in paid)+'\n\n#RankingQuiz'
        await context.bot.send_message(CHAT_ID,txt,message_thread_id=THREAD_ID)

async def ranking_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(ranking_text())

async def pregunta_dia_info(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(f'⛓️ Pregunta del Día: todos los días a las 10:00 AM (hora de México).\n💰 +{DAILY_REWARD:,} PiPesos y +2 puntos por responder directamente al mensaje.\n📚 Banco actual: {len(DAILY_BANK):,} preguntas.\n\n#PreguntaDelDia')
