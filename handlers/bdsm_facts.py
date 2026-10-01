"""Educational BDSM facts for PiBot.

This module is intentionally informational and non-explicit. Facts rotate in the
General topic every 2.5 hours. Presentation is seasonal; content and economy are
independent. The bank uses verified/established core facts plus many presentation
variants so the bot does not repeat the same wording constantly.
"""
from __future__ import annotations

import random
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection
from src.utils.seasonal import current_season

FACT_CHAT_ID = -1003290179217
FACT_THREAD_ID = 435
FACT_INTERVAL_SECONDS = 9000  # 2.5 hours

# Core educational facts. Keep these concise, non-graphic and useful for newcomers.
CORE_FACTS = [
("consentimiento", "El consentimiento en BDSM debe ser voluntario, informado y reversible: haber aceptado algo antes no obliga a aceptarlo hoy."),
("consentimiento", "Una palabra de seguridad es una herramienta, no un sustituto de la negociación, la atención y la comunicación durante una dinámica."),
("consentimiento", "El silencio no equivale automáticamente a consentimiento. Los acuerdos claros reducen malentendidos y ayudan a cuidar a todas las personas involucradas."),
("consentimiento", "Una persona puede retirar su consentimiento en cualquier momento, incluso si la actividad ya había comenzado."),
("consentimiento", "Aceptar una práctica no significa aceptar todas las demás. El consentimiento puede ser específico para una actividad, momento o contexto."),
("limites", "Los límites pueden cambiar con el tiempo. Conocer a alguien desde hace años no elimina la necesidad de seguir hablando sobre ellos."),
("limites", "Un límite no necesita una explicación extensa para ser válido. Un 'no' o un 'hasta aquí' es suficiente."),
("negociacion", "Negociar no significa redactar un contrato enorme: puede ser una conversación clara sobre deseos, límites, señales, riesgos y cuidados."),
("negociacion", "La experiencia no reemplaza la negociación. Dos personas experimentadas también pueden tener límites, expectativas y formas de comunicarse completamente diferentes."),
("negociacion", "Hablar después de una dinámica puede ayudar a descubrir qué funcionó, qué no y qué conviene ajustar la próxima vez."),
("roles", "Dominante y sumiso describen posiciones dentro de un intercambio de poder; no significan que una persona valga más que la otra."),
("roles", "Ser Switch suele describir a alguien que puede disfrutar posiciones dominantes y sumisas, según la persona, el contexto o la dinámica."),
("roles", "Una persona puede identificarse con un rol BDSM sin practicarlo de la misma manera que otra. Las etiquetas orientan; no son manuales universales."),
("roles", "Brat suele usarse para un estilo o subrol sumiso basado en desafío juguetón, provocación o resistencia negociada; no significa ignorar límites reales."),
("roles", "Brat tamer suele describir a quien disfruta interactuar con la resistencia juguetona de una brat dentro de una dinámica acordada."),
("roles", "Service submissive suele describir una forma de sumisión centrada en actos de servicio acordados con la otra persona."),
("roles", "Pet play puede involucrar roles o comportamientos simbólicos inspirados en animales; su significado depende de los acuerdos de quienes participan."),
("roles", "El rol que alguien usa en una comunidad no autoriza a otras personas a tratarle de determinada manera sin consentimiento."),
("dynamics", "D/s significa Dominación y sumisión y se refiere a un intercambio de poder consensuado; puede existir con intensidades y estructuras muy distintas."),
("dynamics", "Una dinámica 24/7 describe acuerdos que pueden extenderse a la vida cotidiana, pero 24/7 no significa consentimiento ilimitado ni ausencia de límites."),
("dynamics", "Tener protocolo dentro de una dinámica significa acordar determinadas formas de comportamiento o interacción; no existe un protocolo universal del BDSM."),
("dynamics", "Las relaciones BDSM pueden ser románticas o no románticas. El intercambio de poder y el enamoramiento no son la misma cosa."),
("dynamics", "Una dinámica puede terminar aunque haya existido consentimiento y cariño. Consentir también incluye poder dejar de participar."),
("aftercare", "Aftercare es el cuidado posterior que algunas personas acuerdan después de una experiencia intensa. No existe una única forma correcta de hacerlo."),
("aftercare", "Para algunas personas el aftercare significa cercanía; para otras, espacio, comida, agua, conversación o simplemente descansar. Lo importante es hablarlo."),
("aftercare", "El cuidado posterior también puede ser útil para quien ocupó el rol dominante; las reacciones emocionales no pertenecen a un solo rol."),
("aftercare", "El aftercare puede necesitar seguimiento horas o días después. Una conversación posterior puede ser tan importante como el momento inmediato."),
("seguridad", "Conocer el material y sus riesgos forma parte de la reducción de riesgos. Tener consentimiento no convierte automáticamente una práctica en segura."),
("seguridad", "Las señales no verbales pueden ser útiles cuando hablar no es posible; deben acordarse antes y ser fáciles de reconocer."),
("seguridad", "Una safeword suele ser una palabra acordada para comunicar pausa o detención con claridad, especialmente cuando palabras habituales podrían formar parte del juego de roles."),
("seguridad", "El sistema semáforo usa normalmente verde, amarillo y rojo para comunicar continuar, bajar intensidad/revisar y detenerse; su significado exacto debe acordarse."),
("seguridad", "Reducir riesgos incluye saber detener una actividad y tener una forma razonable de resolver imprevistos, no solamente saber cómo iniciarla."),
("historia", "SSC —Safe, Sane and Consensual— fue formulado en 1983 en el entorno de Gay Male S/M Activists de Nueva York y se volvió una referencia histórica de consentimiento en la comunidad."),
("historia", "RACK significa Risk-Aware Consensual Kink. Gary Switch propuso el término a finales de los años noventa como alternativa a SSC, poniendo énfasis en reconocer los riesgos."),
("historia", "SSC y RACK no son leyes universales del BDSM: son marcos creados dentro de la comunidad para pensar y comunicar consentimiento y riesgo."),
("historia", "Las comunidades leather y S/M tuvieron un papel importante en el desarrollo de lenguaje, organizaciones y modelos de consentimiento que luego circularon ampliamente en el BDSM moderno."),
("historia", "El vocabulario BDSM actual se formó durante décadas y mezcla términos provenientes de distintas comunidades; por eso algunas palabras cambian de significado según el lugar o el grupo."),
("comunidad", "Un munch suele ser una reunión social informal de personas interesadas en BDSM o kink, normalmente en un entorno cotidiano y sin necesidad de realizar prácticas."),
("comunidad", "Una comunidad responsable puede enseñar y compartir experiencias, pero pertenecer a un grupo no convierte automáticamente a alguien en experto."),
("comunidad", "La reputación dentro de un grupo no sustituye la responsabilidad individual. Una persona conocida también debe respetar límites y consentimiento."),
("comunidad", "No existe una autoridad universal que asigne roles BDSM. La identidad y los acuerdos de cada persona no dependen de que otra persona los 'certifique'."),
("comunidad", "Preguntar con respeto es una herramienta importante para aprender BDSM; asumir que todas las personas usan las mismas definiciones puede generar confusión."),
("mitos", "Ser sumiso no significa carecer de carácter, autonomía o capacidad de decisión. La sumisión consensuada es una elección dentro de acuerdos determinados."),
("mitos", "Ser dominante no significa controlar a cualquier persona. La autoridad de una dinámica existe dentro de los límites que las personas involucradas acordaron."),
("mitos", "BDSM no es sinónimo de dolor. Algunas dinámicas se centran en estructura, servicio, restricción, roles, sensaciones, protocolo u otras formas de intercambio."),
("mitos", "No todas las personas BDSM buscan una relación 24/7. Algunas prefieren dinámicas ocasionales, otras relaciones continuas y otras solo ciertos elementos."),
("mitos", "Tener una safeword no vuelve aceptable ignorar otras señales de malestar. La comunicación incluye palabras, comportamiento y atención al contexto."),
("mitos", "Decir 'soy Dom' o 'soy sub' no crea automáticamente una relación de poder con nadie. Esa relación necesita acuerdo entre las personas involucradas."),
("privacidad", "Contar una experiencia compartida puede revelar información de otra persona. La privacidad también puede negociarse: qué puede contarse, a quién y con cuánto detalle."),
("privacidad", "El consentimiento para participar en una actividad no implica consentimiento para fotografías, grabaciones o publicaciones. Son decisiones separadas."),
("comunicacion", "Una buena pregunta antes de una dinámica no es solo '¿qué te gusta?', sino también '¿qué no quieres?', '¿qué debo saber?' y '¿cómo prefieres comunicar una pausa?'."),
("comunicacion", "Los acuerdos pueden revisarse. Cambiar de opinión después de adquirir experiencia no invalida lo que una persona decidió anteriormente."),
("comunicacion", "Las expectativas implícitas son una fuente común de conflictos. Decir claramente qué espera cada persona puede evitar asumir compromisos que nunca fueron acordados."),
("comunicacion", "Una respuesta responsable a un límite es respetarlo, no intentar convencer a la persona de que debería tener otro."),
("aprendizaje", "Aprender una técnica y aprender consentimiento son cosas diferentes; una persona responsable necesita ambas."),
("aprendizaje", "Los títulos y años de experiencia pueden aportar contexto, pero no garantizan automáticamente buenas prácticas. La conducta concreta importa más que la etiqueta."),
("aprendizaje", "Observar, preguntar y empezar con acuerdos claros suele enseñar más que intentar imitar dinámicas ajenas sin conocer su negociación previa."),
("aprendizaje", "No todas las prácticas o dinámicas son compatibles con todas las personas. Reconocer incompatibilidad también es una habilidad sana."),
("lenguaje", "Top y Bottom suelen describir lo que alguien hace en una actividad, mientras Dominante y sumiso suelen referirse al intercambio de poder; no siempre son equivalentes."),
("lenguaje", "Kink es un término amplio para intereses o prácticas no convencionales; BDSM es un conjunto más específico de conceptos y dinámicas dentro de ese universo."),
("lenguaje", "La palabra 'vainilla' suele usarse informalmente para referirse a relaciones o prácticas fuera del kink/BDSM; no es una categoría clínica."),
("lenguaje", "Una etiqueta puede tener matices distintos entre comunidades. Cuando importa, preguntar '¿qué significa para ti?' suele ser mejor que asumir una definición."),
]

INTRO = [
    "¿Sabías que…", "Dato BDSM del día:", "Un minuto de cultura BDSM:", "Dato para guardar:",
    "Pequeña cápsula BDSM:", "Entre tanta charla, un dato útil:", "PiBot encontró algo que vale la pena saber:",
    "Dato rápido, pero importante:", "Hoy aprendemos algo:", "Cultura BDSM en pocas palabras:",
    "Una cosa que a veces se confunde:", "Para nuevos y veteranos:", "Dato de comunidad:",
    "PiBot educativo apareció otra vez:", "Antes de seguir con el caos del grupo:", "Dato para conversar:",
    "Algo interesante del BDSM:", "Cápsula de historia y cultura:", "Recordatorio útil:", "¿Lo conocías?"
]

SEASON_OPEN = {
    "normal": ["🖤", "⛓️", "📚"],
    "halloween": ["🎃🖤", "🕸️⛓️", "👻📚", "🦇🖤"],
    "dia_muertos": ["💀🌼", "🕯️🖤", "🌼📚"],
    "navidad": ["🎄🖤", "❄️⛓️", "🎁📚"],
    "san_valentin": ["💘🖤", "🌹⛓️", "💗📚"],
    "anio_nuevo": ["🎆🖤", "🥂📚", "✨⛓️"],
    "independencia_mx": ["🇲🇽🖤", "🎉⛓️", "🇲🇽📚"],
}


def ensure_fact_tables() -> None:
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS bdsm_fact_history_tb (
            fact_key TEXT PRIMARY KEY,
            last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            uses INTEGER NOT NULL DEFAULT 1
        )""")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:
        _put_connection(conn)


def _pick_fact():
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT fact_key FROM bdsm_fact_history_tb ORDER BY last_used_at DESC LIMIT %s", (min(45, max(1, len(CORE_FACTS)-5)),))
        recent = {r[0] for r in c.fetchall()}
        candidates = [(i, x) for i, x in enumerate(CORE_FACTS) if f"fact-{i}" not in recent]
        if not candidates:
            candidates = list(enumerate(CORE_FACTS))
        i, fact = random.choice(candidates)
        key = f"fact-{i}"
        c.execute("INSERT INTO bdsm_fact_history_tb(fact_key) VALUES(%s) ON CONFLICT(fact_key) DO UPDATE SET last_used_at=NOW(), uses=bdsm_fact_history_tb.uses+1", (key,))
        conn.commit()
        return key, fact
    except Exception:
        conn.rollback(); raise
    finally:
        _put_connection(conn)


def fact_bank_size() -> int:
    # Each core fact has 20 intentionally different intros. This is presentation
    # variety, not a claim that they are 20 different historical facts.
    return len(CORE_FACTS) * len(INTRO)


def render_fact(fact) -> str:
    category, body = fact
    season = current_season()
    icon = random.choice(SEASON_OPEN.get(season, SEASON_OPEN["normal"]))
    intro = random.choice(INTRO)
    return f"{icon} <b>{intro}</b>\n\n{body}\n\n📚 <i>Tema: {category.title()} · Información educativa; los acuerdos concretos siempre dependen de las personas involucradas.</i>"


async def bdsm_fact_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        _, fact = _pick_fact()
        await context.bot.send_message(
            chat_id=FACT_CHAT_ID,
            message_thread_id=FACT_THREAD_ID,
            text=render_fact(fact),
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"[BDSM FACT] {type(e).__name__}: {e}")
