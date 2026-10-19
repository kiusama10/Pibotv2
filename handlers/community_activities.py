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
# Preguntas escritas una por una para que el feed no se sienta como la misma plantilla
# cambiando dos palabras. Se mezclan con el banco combinatorio existente.
CURATED_DAILY_TEXT=[
'¿Qué diferencia notas entre obedecer porque quieres y obedecer porque sientes presión?',
'¿Qué te hace confiar de verdad en alguien dentro de una dinámica?',
'¿Cuál es una señal pequeña que para ti demuestra que alguien sí sabe escuchar?',
'¿Qué prefieres aclarar desde el principio aunque parezca obvio?',
'¿Qué cosa antes te parecía indispensable en una dinámica y hoy ya no?',
'¿Qué aprendiste de una vez en la que dijiste “no” y te respetaron sin discutir?',
'¿Qué te hace sentir que puedes cambiar de opinión sin que la otra persona se moleste?',
'¿Qué diferencia hay para ti entre tener autoridad y querer controlarlo todo?',
'¿Qué debería saber alguien antes de llamarse Dominante?',
'¿Qué debería saber alguien antes de asumir un rol sumiso?',
'¿Qué hace que un Switch se sienta libre de moverse entre ambos roles?',
'¿Hay alguna etiqueta BDSM que te guste, pero que no explique por completo quién eres?',
'¿Qué etiqueta crees que se malinterpreta más dentro del BDSM?',
'¿Qué te importa más al conocer a alguien: lo que dice de su rol o cómo trata a los demás?',
'¿Qué comportamiento te hace desconfiar aunque la persona tenga mucha experiencia?',
'¿Qué comportamiento te inspira confianza incluso antes de hablar de una dinámica?',
'¿Qué significa para ti que una persona sea responsable con el poder que recibe?',
'¿Qué parte de una negociación te parece más fácil olvidar?',
'¿Qué pregunta nunca debería faltar antes de probar algo nuevo?',
'¿Qué prefieres: acuerdos muy detallados o pocos acuerdos pero muy claros?',
'¿Cuándo crees que vale la pena renegociar algo que ya estaba acordado?',
'¿Qué haces cuando descubres que algo que te gustaba en teoría no te gusta en la práctica?',
'¿Qué diferencia hay entre curiosidad y ganas reales de probar algo?',
'¿Cómo sabes que estás aceptando algo por deseo y no por complacer a otra persona?',
'¿Qué te parece una buena forma de decir “hasta aquí” sin sentir que arruinaste el momento?',
'¿Qué tan importante es para ti poder reírte dentro de una dinámica?',
'¿Qué hace que una dinámica se sienta natural y no actuada?',
'¿Qué valoras más: intensidad, conexión, estructura o confianza?',
'¿Qué puede volver especial una dinámica sencilla aunque no tenga nada espectacular?',
'¿Qué detalle pequeño puede cambiar por completo cómo recuerdas una experiencia?',
'¿Qué significa para ti cuidar a alguien sin quitarle autonomía?',
'¿Cómo distingues cuidado de sobreprotección?',
'¿Qué tipo de aftercare te parece más fácil pedir y cuál más difícil?',
'¿Crees que el aftercare debe hablarse antes o descubrirse con el tiempo?',
'¿Qué tan importante es preguntar al día siguiente cómo se sintió la otra persona?',
'¿Qué harías si el aftercare que tú necesitas es muy distinto al de la otra persona?',
'¿Qué crees que necesita más atención: el momento de la dinámica o lo que pasa después?',
'¿Qué aprendiste sobre tus propias emociones después de una dinámica intensa?',
'¿Qué diferencia hay entre corregir un error y justificarlo?',
'¿Qué debería hacer alguien cuando cruza un límite por accidente?',
'¿Qué te hace pensar “con esta persona sí puedo hablar de algo incómodo”?',
'¿Qué tema te cuesta más hablar antes de una dinámica?',
'¿Qué conversación incómoda terminó siendo útil para ti?',
'¿Qué prefieres recibir cuando das feedback: una explicación, una disculpa o un cambio de conducta?',
'¿Qué te parece más importante al dar feedback: el momento, el tono o la claridad?',
'¿Qué señal te dice que alguien escucha para entender y no solo para responder?',
'¿Qué tan fácil te resulta decir que algo ya no te funciona aunque antes sí?',
'¿Qué diferencia hay entre paciencia y aguantar algo que no quieres?',
'¿Qué significa para ti sentirse seguro sin perder la emoción?',
'¿Qué riesgo crees que la gente subestima más cuando empieza en BDSM?',
'¿Qué prefieres aprender primero de una práctica: la técnica o cómo detenerla con seguridad?',
'¿Qué te hace decidir que todavía no estás listo para intentar algo?',
'¿Qué opinas de empezar suave incluso cuando ambas personas quieren algo intenso?',
'¿Qué papel debería tener la experiencia previa cuando dos personas hacen algo juntas por primera vez?',
'¿Qué harías si notas que la otra persona dice que está bien, pero su comportamiento dice otra cosa?',
'¿Qué tan importante es tener un plan B cuando algo no sale como esperaban?',
'¿Qué significa para ti “reducir riesgos” sin prometer que algo es completamente seguro?',
'¿Qué aprendizaje de seguridad te habría gustado conocer cuando empezaste?',
'¿Qué mito de seguridad te gustaría que desapareciera del BDSM?',
'¿Qué debería pesar más: la reputación de alguien o lo que demuestra contigo?',
'¿Qué opinas de pedir referencias antes de confiar en alguien para una dinámica?',
'¿Qué red flag crees que mucha gente normaliza por tener poca experiencia?',
'¿Qué green flag te parece poco mencionada pero muy importante?',
'¿Qué tan rápido crees que debería construirse la confianza?',
'¿Qué haría que dejaras de confiar en alguien aunque nunca haya cruzado un límite físico?',
'¿Puede recuperarse la confianza después de un error? ¿Qué tendría que pasar?',
'¿Qué diferencia ves entre equivocarse y repetir una conducta después de que ya se habló?',
'¿Qué te parece más difícil: confiar o permitir que alguien confíe en ti?',
'¿Qué te ayuda a ser vulnerable sin sentir que pierdes control sobre ti mismo?',
'¿Qué responsabilidad aparece cuando alguien te cuenta un límite muy personal?',
'¿Qué no debería confundirse nunca con “ser de vieja escuela”?',
'¿Qué tradición o idea antigua del BDSM sí te parece útil conservar?',
'¿Qué práctica de comunidad crees que debería cambiar con los años?',
'¿Qué crees que hace sana a una comunidad BDSM además de tener reglas?',
'¿Cómo debería reaccionar un grupo cuando alguien nuevo hace una pregunta básica?',
'¿Qué es peor para una comunidad: la desinformación o el miedo a preguntar?',
'¿Qué tan importante es que una comunidad permita cuestionar a personas con experiencia?',
'¿Qué hace que un consejo sea útil sin convertirse en una orden?',
'¿Qué opinas de aprender BDSM solo por contenido de redes sociales?',
'¿Qué diferencia hay entre enseñar desde la experiencia y presentarla como verdad universal?',
'¿Qué tema BDSM crees que necesita explicarse mejor a quienes apenas comienzan?',
'¿Qué término aprendiste tarde y te habría ahorrado muchas confusiones?',
'¿Qué término crees que la gente usa de forma demasiado distinta?',
'¿Qué diferencia hay para ti entre rol, personalidad y forma de relacionarte?',
'¿Qué tan importante es separar una fantasía de un acuerdo real?',
'¿Hay algo que disfrutas imaginar pero no necesitas llevar a la práctica?',
'¿Qué hace que una fantasía sea buena para conversar aunque nunca se realice?',
'¿Qué te parece más íntimo: contar un deseo o contar un límite?',
'¿Qué descubriste sobre ti hablando de algo que antes te daba pena mencionar?',
'¿Qué tan importante es poder decir “no sé” dentro del BDSM?',
'¿Qué prefieres en alguien con experiencia: seguridad al hablar o capacidad de reconocer lo que no sabe?',
'¿Qué cambia cuando dejas de intentar encajar en una etiqueta y empiezas a construir tu propia dinámica?',
'¿Qué acuerdo de pareja crees que más se da por hecho y menos se habla?',
'¿Qué debería mantenerse fuera del rol para proteger la relación cotidiana?',
'¿Cómo evitas que una discusión de pareja se convierta en una herramienta de poder dentro del rol?',
'¿Qué tan importante es tener momentos donde el rol no esté presente?',
'¿Qué crees que pasa cuando una dinámica funciona muy bien pero la relación fuera del rol no?',
'¿Qué debe pasar cuando dos personas quieren cosas distintas de la misma dinámica?',
'¿Qué diferencia hay entre adaptarse a alguien y dejar de lado lo que tú necesitas?',
'¿Qué significa para ti compatibilidad dentro del BDSM?',
'¿Qué incompatibilidad aceptarías sin intentar “arreglarla”?',
'¿Qué te parece más difícil de aceptar: que alguien no quiera lo mismo o que sí lo quiera pero de otra forma?',
'¿Qué hace que vuelvas a elegir a una persona para compartir una dinámica?',
'¿Qué cosa puede hacer crecer una dinámica sin volverla más intensa?',
'¿Qué debería cambiar primero cuando una dinámica empieza a sentirse rutinaria?',
'¿Qué tan importante es conservar curiosidad incluso cuando ya tienes experiencia?',
'¿Qué aprendiste de una persona con menos experiencia que tú?',
'¿Qué aprendiste de alguien cuyo rol era muy distinto al tuyo?',
'¿Qué idea sobre dominar cambió más con tu experiencia?',
'¿Qué idea sobre entregarte cambió más con tu experiencia?',
'¿Qué significa para ti que el consentimiento sea continuo y no solo algo que se pregunta al inicio?',
'¿Qué tan importante es que una persona pueda detener una dinámica sin tener que justificarse?',
'¿Qué harías si un acuerdo que funcionaba hace meses ya no se siente igual?',
'¿Qué te parece más valioso: conocer muchas prácticas o conocerte bien a ti mismo?',
'¿Cuál es una cosa que jamás medirías por “años de experiencia”?',
'¿Qué hace que una persona experimentada siga siendo segura para alguien principiante?',
'¿Qué diferencia hay entre liderazgo y superioridad dentro de una dinámica?',
'¿Qué significa para ti ceder control sin ceder tu voz?',
'¿Qué significa para ti recibir control sin apropiarte de la otra persona?',
'¿Qué tan importante es poder bromear o relajarse después de una conversación seria sobre límites?',
'¿Qué conversación crees que debería repetirse incluso si ya se tuvo muchas veces?',
'¿Qué detalle te hace sentir que tus límites son recordados y no solo tolerados?',
'¿Qué prefieres que alguien haga cuando no entiende uno de tus límites: preguntar o evitar asumir?',
'¿Qué te hace pensar que una persona sabe manejar un “no” de forma madura?',
'¿Qué crees que enseña más sobre alguien: cómo consigue un sí o cómo recibe un no?',
]

CURATED_DAILY_TEXT += [
    '¿Qué diferencia hay entre una regla que cuida la dinámica y una regla que solo existe para controlar?',
    '¿Qué debería pasar cuando una persona cumple un acuerdo pero descubre que emocionalmente no le funcionó?',
    '¿Qué hace que una disculpa dentro de una dinámica se sienta real y no solo como una forma de cerrar el tema?',
    '¿Qué tan importante es hablar de expectativas antes de poner un título a una relación o dinámica?',
    '¿Qué prefieres saber primero de alguien: sus gustos, sus límites o cómo maneja los desacuerdos?',
    '¿Qué te parece más difícil de negociar: lo que quieres o lo que definitivamente no quieres?',
    '¿Qué comportamiento te demuestra que alguien puede manejar responsabilidad sin abusar de ella?',
    '¿Cuándo crees que una regla deja de ser útil y necesita revisarse?',
    '¿Qué diferencia notas entre alguien que pregunta por tus límites y alguien que realmente los recuerda?',
    '¿Qué tan importante es poder decir “hoy no” aunque normalmente algo sí te guste?',
    '¿Qué debería hacerse si una persona se queda en silencio justo cuando hay que tomar una decisión?',
    '¿Qué significa para ti que el consentimiento dependa también del contexto?',
    '¿Qué condición podría cambiar completamente un “sí” que habías dado antes?',
    '¿Qué tan seguido crees que deberían revisarse los acuerdos en una dinámica estable?',
    '¿Qué hace que una renegociación se sienta como crecimiento y no como fracaso?',
    '¿Qué prefieres después de un error: hablarlo de inmediato o esperar a estar más tranquilo?',
    '¿Qué diferencia hay entre dar espacio y desaparecer cuando la otra persona necesita claridad?',
    '¿Qué tipo de seguimiento al día siguiente te parece realmente útil?',
    '¿Qué harías si descubres que tú y la otra persona necesitan formas opuestas de aftercare?',
    '¿Qué detalle de cuidado posterior suele parecer pequeño pero puede importar mucho?',
    '¿Qué significa para ti cerrar bien una dinámica antes de volver a hablar como siempre?',
    '¿Te parece útil tener una señal clara para entrar y salir del rol? ¿Por qué?',
    '¿Qué problema puede aparecer cuando nunca se habla de cuándo termina el rol?',
    '¿Qué parte de tu vida preferirías mantener completamente fuera de una dinámica?',
    '¿Qué tan importante es que una persona dominante también pueda admitir que se equivocó?',
    '¿Qué tan importante es que una persona sumisa pueda decir “esto no me gustó” sin miedo?',
    '¿Qué crees que demuestra más madurez: aguantar más o saber detenerse a tiempo?',
    '¿Qué hace que una persona sea buena recibiendo feedback?',
    '¿Qué hace que un feedback sea útil en vez de sentirse como ataque?',
    '¿Qué tan específico debería ser un límite para evitar malentendidos?',
    '¿Qué diferencia hay entre “no quiero” y “no quiero en estas condiciones”?',
    '¿Qué tan importante es hablar de privacidad antes de compartir fotos o mensajes íntimos?',
    '¿Qué opinas de guardar capturas de conversaciones privadas sin hablarlo antes?',
    '¿Qué debería pasar con fotos o videos cuando una dinámica termina?',
    '¿Qué diferencia hay entre permitir grabar algo y permitir compartirlo?',
    '¿Qué responsabilidad tiene alguien cuando conoce información muy privada de otra persona?',
    '¿Qué harías si alguien del grupo te cuenta un rumor sobre una persona con la que quieres hablar?',
    '¿Qué valor le das a las referencias de otras personas y qué cosas preferirías comprobar tú mismo?',
    '¿Qué señal te haría dejar de confiar en la reputación de alguien?',
    '¿Qué tan importante es ver cómo una persona trata a quienes no le interesan romántica o sexualmente?',
    '¿Qué te dice más de alguien: cómo habla de sus exparejas o cómo habla de sus propios errores?',
    '¿Qué green flag te parece más importante cuando alguien recibe una crítica?',
    '¿Qué red flag aparece cuando alguien presume demasiado sus años de experiencia?',
    '¿Qué opinas de quien usa “así se hace en BDSM” para cerrar una conversación?',
    '¿Qué diferencia hay entre enseñar una costumbre y presentarla como una regla universal?',
    '¿Qué tan importante es distinguir tradición de seguridad real?',
    '¿Qué parte del BDSM crees que se aprende mejor practicando poco a poco que leyendo?',
    '¿Qué práctica crees que jamás debería aprenderse únicamente mirando videos?',
    '¿Qué hace responsable a alguien cuando todavía está aprendiendo una técnica?',
    '¿Qué tan importante es practicar cómo detener algo antes de practicar cómo hacerlo?',
    '¿Qué opinas de ensayar señales o procedimientos de seguridad antes de necesitarlos?',
    '¿Qué plan B te parece útil tener antes de una dinámica?',
    '¿Qué podría hacerte cancelar una dinámica aunque todo estuviera planeado?',
    '¿Qué tan importante es el cansancio al decidir si hacer algo intenso?',
    '¿Qué cambia si una persona llega emocionalmente saturada a una dinámica?',
    '¿Qué señal física te haría detenerte aunque la otra persona todavía no haya dicho rojo?',
    '¿Qué tan importante es conocer cómo se ve normalmente la otra persona antes de notar cambios?',
    '¿Qué diferencia hay entre observar y asumir lo que la otra persona siente?',
    '¿Qué debería hacerse si las señales verbales y el lenguaje corporal parecen contradecirse?',
    '¿Qué tan importante es que una safeword sea fácil de recordar bajo estrés?',
    '¿Qué alternativa usarías cuando hablar no es práctico durante una dinámica?',
    '¿Qué opinas de tener demasiadas señales o reglas difíciles de recordar?',
    '¿Qué significa para ti una buena salida de emergencia?',
    '¿Qué tan accesibles deberían estar las herramientas de seguridad?',
    '¿Qué diferencia hay entre tener herramientas y saber realmente utilizarlas?',
    '¿Qué crees que pasa cuando alguien confía demasiado en que “nunca pasa nada”?',
    '¿Qué nivel de riesgo aceptarías explorar y cuál simplemente no te interesa?',
    '¿Qué tan importante es que dos personas tengan tolerancias de riesgo parecidas?',
    '¿Qué haces cuando alguien quiere avanzar mucho más rápido que tú?',
    '¿Qué hace compatible el ritmo de dos personas al construir una dinámica?',
    '¿Qué señal te indica que alguien está tratando de acelerar la confianza?',
    '¿Qué diferencia hay entre química inmediata y confianza real?',
    '¿Qué crees que necesita tiempo aunque la conexión sea muy fuerte desde el inicio?',
    '¿Qué tan importante es poder hablar sin rol cuando aparece un problema serio?',
    '¿Qué conversación jamás debería resolverse desde una posición de autoridad de rol?',
    '¿Qué significa para ti separar un conflicto de pareja de una corrección dentro de la dinámica?',
    '¿Qué pasa cuando una persona usa el rol para ganar discusiones cotidianas?',
    '¿Qué debería quedar claro antes de una dinámica 24/7?',
    '¿Qué espacios crees que conviene dejar fuera incluso en una dinámica muy estructurada?',
    '¿Qué diferencia hay entre protocolo y vigilancia?',
    '¿Qué ritual te parece bonito precisamente porque es voluntario?',
    '¿Qué hace que un ritual tenga significado en vez de sentirse como obligación?',
    '¿Qué opinas de cambiar un ritual que antes era importante pero ya no se siente igual?',
    '¿Qué tan importante es poder redefinir una etiqueta con el tiempo?',
    '¿Qué rol o término crees que la gente intenta encerrar demasiado en una sola definición?',
    '¿Qué diferencia hay entre decir “soy así” y usar una etiqueta como excusa para una conducta?',
    '¿Qué hace que alguien sea responsable al explorar un rol nuevo?',
    '¿Qué aprenderías primero si quisieras probar el lado contrario de tu rol habitual?',
    '¿Qué cambia cuando un Switch encuentra personas distintas con quienes expresa lados diferentes?',
    '¿Qué tan útil te parece hablar de lo que NO buscas, además de lo que sí?',
    '¿Qué expectativa no hablada puede causar más problemas en una dinámica?',
    '¿Qué pregunta te gustaría que te hicieran más seguido cuando conoces a alguien?',
    '¿Qué respuesta a una pregunta sobre límites te haría sentir más tranquilo?',
    '¿Qué tan importante es poder decir “no tengo respuesta todavía”?',
    '¿Qué haces cuando necesitas tiempo para decidir algo y la otra persona quiere respuesta inmediata?',
    '¿Qué diferencia hay entre paciencia y presión disfrazada de insistencia cariñosa?',
    '¿Qué significa para ti que una persona respete tu tiempo para decidir?',
    '¿Qué hace que una comunidad sea segura para decir “no sé”?',
    '¿Qué debería hacer un admin cuando ve información de seguridad claramente equivocada?',
    '¿Cómo corregirías a alguien sin humillarlo frente a todo el grupo?',
]
CURATED_DAILY=[{'id':f'curated-{i:03d}','category':'curada','q':q} for i,q in enumerate(CURATED_DAILY_TEXT)]
_GENERATED_DAILY=[{'id':f'{cat}-{i}-{j}','category':cat,'q':tpl.format(x=x)} for cat,xs in CATS.items() for i,x in enumerate(xs) for j,tpl in enumerate(PROMPTS)]
DAILY_BANK=CURATED_DAILY+_GENERATED_DAILY

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
        c=conn.cursor(); c.execute("""SELECT p.user_id,p.quiz_points,p.daily_points,(p.quiz_points+p.daily_points) total,COALESCE(NULLIF(pr.username,''),NULLIF(pr.nombre,''),p.user_id::text)
        FROM community_weekly_points_tb p LEFT JOIN perfiles_tb pr ON pr.id_user=p.user_id WHERE p.week_start=%s ORDER BY total DESC,p.quiz_points DESC,p.updated_at ASC LIMIT %s""",(ws,limit)); return c.fetchall()
    finally:_put_connection(conn)

def ranking_text():
    rows=ranking_rows(); lines=['🏆 RANKING SEMANAL · CONOCIMIENTO','',f'Semana del {_week_start().strftime("%d/%m/%Y")}', '']
    if not rows: lines.append('Todavía no hay puntos esta semana.')
    for i,(uid,q,d,total,name) in enumerate(rows,1): lines.append(f'{i}. {name} — {total} pts · {q} aciertos de Quiz · {d//2} Preguntas del Día')
    lines += ['', '🥇 10,000 · 🥈 6,000 · 🥉 3,000 PiPesos', '#RankingQuiz']
    return '\n'.join(lines)

async def ranking_callback(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer(); await update.callback_query.message.reply_text(ranking_text())

async def daily_question_job(context:ContextTypes.DEFAULT_TYPE):
    # 10:00 Mexico. Daily post gets priority and resets shared spacing timestamp.
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT question_key FROM daily_question_tb ORDER BY created_at DESC LIMIT 1200"); recent={r[0] for r in c.fetchall()}
        curated_pool=[x for x in CURATED_DAILY if x['id'] not in recent]
        generated_pool=[x for x in _GENERATED_DAILY if x['id'] not in recent]
        if curated_pool and (random.random()<0.78 or not generated_pool):
            item=random.choice(curated_pool)
        else:
            pool=generated_pool or curated_pool or DAILY_BANK; item=random.choice(pool)
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
    try:
        from handlers.season_pass import grant_season_xp
        sx=grant_season_xp(u.id,40,'daily')
    except Exception:
        sx=None
    xp_line=f" · +{sx['granted']} XP de temporada" if sx and sx.get('granted',0) else ''
    level_line=f"\n🎉 ¡Subiste a nivel {sx['new_level']} del pase!" if sx and sx.get('new_level',1)>sx.get('old_level',1) else ''
    await m.reply_text(f'✅ Respuesta registrada · +2,000 PiPesos · +2 puntos para #RankingQuiz{xp_line}{level_line}')

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
