"""Non-explicit BDSM glossary capsule every 75 minutes."""
from __future__ import annotations
import random
from telegram.ext import ContextTypes
from src.utils.seasonal import seasonalize
from src.database.database import _get_connection,_put_connection
from handlers.community_activities import auto_can_post

CHAT_ID=-1003290179217
THREAD_ID=435
INTERVAL_SECONDS=75*60
TERMS=[
("Aftercare","Cuidados y atención posteriores a una dinámica, según lo que las personas involucradas hayan acordado y necesiten."),
("Bottom","Persona que recibe una acción o experiencia en una práctica; no implica necesariamente ser sumisa."),
("Dominante","Persona a quien se cede una autoridad acordada dentro de una dinámica o relación consensuada."),
("D/s","Abreviatura de Dominación/sumisión: intercambio consensuado de poder con alcance y límites acordados."),
("Hard limit","Límite que una persona no desea cruzar. No es una invitación a insistir o negociar en el momento."),
("Kink","Término amplio para intereses, dinámicas o prácticas no convencionales; no es sinónimo exacto de BDSM."),
("Munch","Reunión social informal de personas interesadas en BDSM/kink, normalmente en un entorno cotidiano."),
("Negociación","Conversación previa para acordar intereses, límites, riesgos, comunicación, privacidad y cuidados."),
("RACK","Risk-Aware Consensual Kink: marco que enfatiza consentimiento y conciencia de los riesgos."),
("Safeword","Palabra o señal acordada para comunicar pausa, ajuste o detención; debe respetarse inmediatamente según el acuerdo."),
("SSC","Safe, Sane and Consensual: marco histórico de seguridad, sensatez y consentimiento."),
("Soft limit","Actividad o situación sobre la que una persona tiene reservas y que requiere conversación específica; nunca equivale a consentimiento automático."),
("Sumisión","Cesión consensuada de cierto control o autoridad dentro de límites y acuerdos definidos."),
("Switch","Persona que puede disfrutar más de una posición o rol según la dinámica, la persona o el contexto."),
("Top","Persona que realiza una acción en una práctica; no necesariamente ocupa un rol dominante."),
("Consentimiento reversible","Principio por el que una persona puede cambiar de opinión y retirar su consentimiento, incluso si antes había aceptado."),
("Protocolo","Conjunto de formas, reglas o rituales acordados para una dinámica; no existe un protocolo universal obligatorio."),
("Límite","Frontera personal sobre lo que alguien acepta o no acepta. Puede cambiar y debe comunicarse y respetarse."),
("Check-in","Momento de comprobación para saber cómo se encuentra la otra persona y si desea continuar, ajustar o detener."),
("Subspace","Término comunitario usado para describir un estado subjetivo de concentración o alteración de la percepción que algunas personas reportan durante dinámicas intensas."),
]
TERMS += [
("24/7","Dinámica cuyos acuerdos pueden extenderse a la vida cotidiana. No significa consentimiento ilimitado ni elimina el derecho a detener o renegociar."),
("Agencia","Capacidad de una persona para decidir y actuar por sí misma; asumir un rol sumiso no elimina la agencia."),
("Bondage","Restricción consensuada del movimiento mediante técnicas o materiales diversos; cada método tiene riesgos específicos."),
("Brat","Etiqueta para un estilo de sumisión que puede incluir desafío juguetón dentro de acuerdos previamente aceptados."),
("Brat tamer","Etiqueta para quien disfruta responder al desafío de un brat dentro de una dinámica consensuada."),
("CNC","Consensual Non-Consent: fantasía o dinámica negociada que simula ausencia de consentimiento, pero depende de consentimiento real, límites y mecanismos de seguridad."),
("Collar","Objeto que puede tener un significado simbólico en una dinámica o relación. Su significado no es universal y debe acordarse."),
("Consentimiento continuo","Principio de que el consentimiento importa durante toda la interacción y puede revisarse o retirarse."),
("Consentimiento específico","Aceptar una actividad no implica aceptar automáticamente otras actividades."),
("Consentimiento informado","Decisión tomada con información suficiente sobre lo propuesto, sus condiciones y riesgos relevantes."),
("Debrief","Conversación posterior para revisar una experiencia, expresar sensaciones y acordar posibles cambios."),
("Domdrop","Término comunitario para un bajón físico o emocional que algunas personas dominantes reportan después de una dinámica intensa."),
("Drop","Término general para cambios físicos o emocionales posteriores a una experiencia intensa."),
("Escena","Periodo o contexto acordado en el que se desarrolla una práctica o dinámica."),
("Fantasía","Idea que puede resultar atractiva sin que exista necesariamente deseo o consentimiento para realizarla."),
("Impact play","Categoría de prácticas que emplean impactos consensuados; requiere atención a intensidad, zonas corporales, herramientas y riesgos."),
("Metaconsentimiento","Acuerdo sobre cómo se comunicará o gestionará el consentimiento dentro de una dinámica; nunca elimina la posibilidad de detenerse."),
("NRE","New Relationship Energy: entusiasmo intenso frecuente al inicio de una relación, que puede influir en expectativas y decisiones."),
("Pet play","Juego de rol consensuado inspirado en identidades o comportamientos de mascota."),
("Plan de emergencia","Acuerdo previo sobre cómo detener una actividad y qué hacer ante un incidente o problema inesperado."),
("PRICK","Personal Responsibility, Informed Consensual Kink: marco que pone énfasis en responsabilidad personal, información y consentimiento."),
("Primal play","Estilo de juego de rol que puede centrarse en instinto, persecución o energía física, siempre sujeto a negociación y límites."),
("Protocolo alto","Forma más estructurada o formal de aplicar reglas y rituales acordados dentro de una dinámica."),
("Protocolo bajo","Forma más flexible o informal de aplicar acuerdos y rituales dentro de una dinámica."),
("Reducción de riesgos","Medidas destinadas a disminuir la probabilidad o gravedad de un daño; no significa que el riesgo desaparezca."),
("Renegociación","Proceso de revisar y modificar acuerdos cuando cambian deseos, límites, circunstancias o experiencia."),
("Ritual","Acción simbólica o repetida que las personas acuerdan incorporar a su dinámica."),
("Safesign","Señal no verbal acordada para comunicar pausa, ajuste o detención cuando hablar no es posible o práctico."),
("Scene negotiation","Negociación específica previa a una escena sobre prácticas, intensidad, límites, señales, riesgos y cuidados."),
("Service submission","Estilo de sumisión orientado a prestar servicios o realizar tareas dentro de acuerdos definidos."),
("Shibari","Término asociado a formas japonesas de atadura con cuerda. Su práctica técnica requiere aprendizaje y atención a riesgos."),
("Subdrop","Bajón físico o emocional que algunas personas sumisas o bottoms pueden experimentar después de una dinámica intensa."),
("Suspensión","Forma de bondage donde parte o todo el peso corporal depende del sistema de cuerda; implica riesgos mayores y requiere formación específica."),
("TPE","Total Power Exchange: término para intercambios amplios de poder consensuado; no significa que el consentimiento deje de ser reversible."),
("Vetting","Proceso prudente de conocer, comprobar referencias y evaluar compatibilidad antes de confiar en alguien para una dinámica."),
("Aftercare diferido","Cuidado o seguimiento realizado horas o días después cuando las necesidades posteriores no terminan al finalizar la escena."),
("Autocuidado","Acciones personales de descanso, hidratación, alimentación o regulación emocional según las necesidades de cada persona."),
("Check-in no verbal","Señal o gesto acordado para comprobar bienestar y consentimiento sin depender del habla."),
("Compatibilidad","Coincidencia suficiente entre deseos, límites, comunicación y expectativas para una dinámica concreta."),
("Coerción","Presión, amenaza o manipulación que compromete la libertad necesaria para consentir."),
("Green flag","Conducta que inspira confianza, como respetar un no, hablar de riesgos y aceptar límites sin insistencia."),
("Red flag","Conducta que justifica cautela, por ejemplo presionar límites, despreciar safewords o negar riesgos."),
("Responsabilidad compartida","Idea de que todas las personas involucradas tienen responsabilidades de comunicación y cuidado acordes a su papel y capacidad."),
("Topdrop","Término usado por algunas personas para describir un bajón posterior en quien realizó una práctica, independientemente de si es dominante."),
("Vanilla","Término informal usado en algunas comunidades para actividades o relaciones fuera del kink/BDSM; no es una categoría clínica."),
("Power exchange","Intercambio consensuado de autoridad o control cuyo alcance depende de los acuerdos concretos de las personas involucradas."),
("Consentimiento granular","Forma de negociar componentes concretos por separado en lugar de tratar una actividad amplia como un único sí o no."),
("Capacidad para consentir","Capacidad de comprender y decidir libremente; ciertos estados de intoxicación o conciencia pueden comprometerla."),
("Acuerdo de privacidad","Pacto sobre qué información, imágenes o detalles de una experiencia pueden compartirse, con quién y en qué contexto."),
("Gradualidad","Enfoque de empezar con menor intensidad o complejidad y ajustar según experiencia, comunicación y acuerdos."),
]

_last=None
def ensure_dictionary_tables():
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("CREATE TABLE IF NOT EXISTS bdsm_dictionary_history_tb(term TEXT PRIMARY KEY,last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),uses INT NOT NULL DEFAULT 1)"); conn.commit()
    except Exception: conn.rollback()
    finally:_put_connection(conn)

def _pick_term():
    ensure_dictionary_tables(); conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT term FROM bdsm_dictionary_history_tb ORDER BY last_used_at DESC LIMIT %s",(max(1,len(TERMS)-3),)); recent={r[0] for r in c.fetchall()}
        pool=[x for x in TERMS if x[0] not in recent] or TERMS; term,definition=random.choice(pool)
        c.execute("INSERT INTO bdsm_dictionary_history_tb(term) VALUES(%s) ON CONFLICT(term) DO UPDATE SET last_used_at=NOW(),uses=bdsm_dictionary_history_tb.uses+1",(term,)); conn.commit(); return term,definition
    finally:_put_connection(conn)

async def dictionary_tick(context:ContextTypes.DEFAULT_TYPE):
    global _last
    if not auto_can_post('dictionary'): return
    term,definition=_pick_term(); _last=term
    await context.bot.send_message(chat_id=CHAT_ID,message_thread_id=THREAD_ID,text=seasonalize(f"📖 DICCIONARIO BDSM · {term}\n\n{definition}\n\n💬 Una misma palabra puede tener matices distintos entre personas; cuando importe, conviene aclarar qué significa para cada quien.\n\n#DiccionarioPiBot",compact=True))
