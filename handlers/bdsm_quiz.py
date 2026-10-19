import random
import json
from datetime import datetime, timezone
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from src.database.database import vinculo_reward_amount, _get_connection, _put_connection
from handlers.community_activities import auto_can_post, add_weekly_points

QUIZ_CHAT_ID=-1003290179217
QUIZ_THREAD_ID=435
QUIZ_REWARD=1000
BASE=[
('consentimiento','Acuerdo libre, informado, específico y reversible.'),('safeword','Palabra o señal acordada para pausar o detener.'),('aftercare','Cuidados acordados después de una dinámica.'),('negociación','Conversación previa sobre deseos, límites, riesgos y señales.'),('límite duro','Algo que una persona no acepta realizar.'),('límite blando','Algo explorable solo bajo condiciones específicas.'),('SSC','Seguro, Sensato y Consensuado.'),('RACK','Marco centrado en consentimiento informado y conciencia del riesgo.'),('dominante','Rol que asume control consensuado dentro de límites.'),('sumiso','Rol que cede control consensuadamente dentro de límites.'),('switch','Persona que puede disfrutar roles dominantes y sumisos.'),('brat','Estilo de sumisión con desafío juguetón consensuado.'),('pet play','Rol consensuado con rasgos o comportamiento de mascota.'),('power exchange','Intercambio consensuado de poder.'),('D/s','Dinámica de Dominación y sumisión consensuada.'),('check-in','Comprobación del bienestar durante o después de una dinámica.'),('subdrop','Bajón físico o emocional posible después de una dinámica intensa.'),('domdrop','Bajón físico o emocional posible en la parte dominante.'),('debrief','Conversación posterior para revisar qué funcionó y qué ajustar.'),('consentimiento reversible','El consentimiento puede retirarse en cualquier momento.'),('consentimiento específico','Aceptar una práctica no implica aceptar otras.'),('señal no verbal','Gesto u objeto acordado para comunicar pausa o detención.'),('semáforo','Verde continuar, amarillo comprobar/reducir y rojo detener.'),('privacidad','Derecho a decidir qué información personal se comparte.'),('autonomía','Capacidad de decidir sobre el propio cuerpo y participación.'),('coerción','Presión o amenaza que impide una decisión verdaderamente libre.'),('tijeras de seguridad','Herramienta de rescate útil para liberar cuerda rápidamente.'),('escucha activa','Escuchar, comprobar comprensión y no asumir.'),('top','Quien realiza una acción; no siempre equivale a dominante.'),('bottom','Quien recibe una acción; no siempre equivale a sumiso.'),('TPE','Intercambio amplio de poder consensuado; el consentimiento sigue siendo reversible.'),('vetting','Proceso de conocer y verificar a alguien antes de una dinámica de mayor riesgo.'),('green flag','Conducta positiva como respetar un no y hablar de riesgos.'),('red flag','Conducta que justifica cautela o alejarse.'),('renegociación','Modificar acuerdos consensuadamente cuando cambian circunstancias.'),('gradualidad','Empezar moderadamente y ajustar según respuesta y acuerdos.'),('feedback','Comentarios posteriores para ajustar futuras dinámicas.'),('rojo','En el sistema semáforo significa detener inmediatamente.'),('amarillo','Suele indicar bajar intensidad, pausar o comprobar.'),('verde','Suele indicar que se puede continuar según lo acordado.'),('plan de emergencia','Acuerdo previo sobre qué hacer si ocurre un incidente.'),('consentimiento granular','Aceptar o rechazar componentes concretos por separado.'),('fantasía','Una idea atractiva no implica querer realizarla.'),('contrato simbólico','Puede expresar acuerdos, pero no reemplaza consentimiento continuo ni ley.'),('aftercare individual','Los cuidados deben adaptarse a cada persona.'),('consentimiento de terceros','No se debe involucrar a personas ajenas sin permiso.'),('entumecimiento','Señal que puede indicar compresión y requiere detener/revisar.'),('dolor inesperado','Señal para pausar y revisar, no para asumir que es normal.'),('acuerdo explícito','Acuerdo comunicado claramente, no basado en suposiciones.'),('incompatibilidad','Deseos o límites no encajan; no obliga a nadie a ceder.'),
]
BASE += [
('PRICK','Personal Responsibility, Informed Consensual Kink: marco que enfatiza responsabilidad personal, información y consentimiento.'),
('CNC','Consensual Non-Consent: fantasía o dinámica previamente negociada que sigue dependiendo de consentimiento real y límites.'),
('24/7','Acuerdo de dinámica que puede extenderse a la vida cotidiana; no significa consentimiento ilimitado.'),
('service submission','Sumisión orientada al servicio acordado, cuyas tareas y alcance dependen de cada dinámica.'),
('collar','Objeto que puede tener significado simbólico dentro de una relación o dinámica; su significado debe acordarse.'),
('munch','Reunión social informal de personas interesadas en kink/BDSM, normalmente sin prácticas.'),
('scene','Periodo o contexto acordado en el que se desarrolla una dinámica o práctica.'),
('drop','Bajón físico o emocional que algunas personas pueden experimentar después de una experiencia intensa.'),
('vetting comunitario','Búsqueda prudente de referencias e información antes de confiar en alguien, sin sustituir la negociación propia.'),
('riesgo informado','Comprender riesgos relevantes antes de decidir si se acepta una práctica.'),
('reducción de riesgos','Medidas destinadas a disminuir probabilidad o gravedad de daños sin afirmar que el riesgo desaparece.'),
('consentimiento entusiasta','Forma de describir una participación clara y voluntaria; el silencio o la presión no equivalen a entusiasmo.'),
('consentimiento continuo','El consentimiento se comprueba y respeta durante toda la interacción, no solo al principio.'),
('consentimiento informado','Decisión tomada con información suficiente sobre lo que se propone y sus riesgos relevantes.'),
('capacidad para consentir','Capacidad de comprender y decidir libremente; puede verse afectada por intoxicación o estados de conciencia alterados.'),
('acuerdo de privacidad','Pacto sobre qué información, imágenes o detalles pueden compartirse y con quién.'),
('señal de seguridad','Señal verbal o no verbal acordada para comunicar pausa, ajuste o detención.'),
('palabra verde','En algunos sistemas semáforo comunica que la intensidad actual está bien; su significado se acuerda antes.'),
('palabra amarilla','En algunos sistemas semáforo pide bajar intensidad, pausar o comprobar el estado.'),
('palabra roja','En algunos sistemas semáforo indica detener la actividad de inmediato.'),
('negociación previa','Conversación anterior a la dinámica para aclarar prácticas, límites, señales, riesgos y cuidados.'),
('renegociación en frío','Revisión de acuerdos fuera del momento intenso, cuando las personas pueden valorar cambios con calma.'),
('aftercare diferido','Seguimiento o cuidado que se realiza horas o días después si las personas lo necesitan.'),
('autocuidado posterior','Medidas personales de descanso, hidratación, alimentación o regulación acordes a las necesidades propias.'),
('debriefing','Conversación posterior para revisar la experiencia, aclarar sensaciones y decidir ajustes futuros.'),
('trigger','Estímulo que puede provocar una reacción emocional intensa; conocerlo puede ayudar a negociar cuidados.'),
('check-in verbal','Pregunta o frase acordada para comprobar bienestar y consentimiento durante una dinámica.'),
('check-in no verbal','Comprobación mediante gestos o señales cuando hablar no es práctico.'),
('responsabilidad dominante','Deber de respetar acuerdos, observar el estado de la otra persona y detenerse cuando corresponde; el rol no elimina responsabilidad.'),
('agencia sumisa','Capacidad de la persona sumisa para decidir, negociar, retirar consentimiento y conservar autonomía.'),
('protocolo alto','Conjunto más formal de reglas o rituales acordados; no es obligatorio ni universal.'),
('protocolo bajo','Forma más flexible o informal de aplicar acuerdos y rituales dentro de una dinámica.'),
('ritual','Acción simbólica repetida por acuerdo dentro de una dinámica o relación.'),
('brat tamer','Etiqueta comunitaria para quien disfruta responder al desafío juguetón de un brat dentro de acuerdos consensuados.'),
('caregiver/little','Dinámica de roles consensuada basada en cuidado y una presentación de rol; entre adultos no implica incapacidad real para consentir.'),
('pet play','Juego de rol consensuado inspirado en comportamientos o identidades de mascota.'),
('primal play','Estilo de juego de rol centrado en instinto, persecución o energía física, sujeto a límites y negociación.'),
('impact play','Categoría de prácticas basadas en impactos; requiere conocer zonas, intensidad, herramientas y riesgos.'),
('bondage','Restricción consensuada del movimiento; el método y los riesgos dependen de la técnica utilizada.'),
('shibari','Término asociado a formas japonesas de atadura con cuerda; la práctica requiere aprendizaje técnico y atención a riesgos.'),
('suspensión','Bondage en el que parte o todo el peso corporal depende del sistema de cuerda; implica riesgos mayores y requiere formación específica.'),
('punto de presión','Zona donde una compresión puede afectar nervios o circulación y requiere especial cuidado.'),
('circulación','Flujo sanguíneo que debe vigilarse en prácticas de restricción; cambios preocupantes requieren detener y revisar.'),
('daño nervioso','Lesión posible por presión, postura o compresión; entumecimiento u otros síntomas requieren atención y no deben ignorarse.'),
('tijeras de trauma','Herramienta de corte de seguridad que puede ayudar a retirar material rápidamente en una emergencia.'),
('plan de salida','Acuerdo práctico sobre cómo detener una dinámica y qué hacer ante una situación inesperada.'),
('compatibilidad','Coincidencia suficiente entre deseos, límites, comunicación y expectativas; no toda persona compatible socialmente lo es en una dinámica.'),
('incompatibilidad de límites','Situación donde lo que una persona necesita cruza un límite de otra; no obliga a nadie a ceder.'),
('NRE','New Relationship Energy: entusiasmo intenso de una relación nueva que puede influir en expectativas y decisiones.'),
('metaconsentimiento','Conversación sobre cómo se comunicará y gestionará el consentimiento; no elimina el derecho a detenerse.'),
]

# Conceptos extra para ampliar el banco REAL, no solo repetir la misma pregunta con otro número.
BASE += [
('consentimiento afirmativo','Consentimiento expresado de forma clara y voluntaria en vez de inferirse por silencio o falta de oposición.'),
('consentimiento contextual','Un sí depende del contexto acordado; aceptar algo en una situación no implica aceptarlo en todas.'),
('límite contextual','Límite que puede depender de persona, lugar, intensidad, momento u otras condiciones previamente habladas.'),
('acuerdo revisable','Acuerdo que puede revisarse cuando cambian necesidades, información o circunstancias.'),
('checklist de negociación','Lista de temas que ayuda a recordar deseos, límites, señales, riesgos, privacidad y cuidados; no sustituye conversar.'),
('plan de aftercare','Acuerdo previo sobre qué cuidados o espacio puede necesitar cada persona después de una dinámica.'),
('aftercare mutuo','Cuidado posterior que reconoce que cualquier persona involucrada puede necesitar apoyo, descanso o seguimiento.'),
('seguimiento','Contacto posterior para comprobar bienestar y hablar de efectos o ajustes después de una experiencia.'),
('privacidad digital','Acuerdos sobre capturas, mensajes, fotos, audios, almacenamiento y difusión de información en medios digitales.'),
('outing','Revelar sin permiso la participación o identidad kink/BDSM de otra persona, afectando su privacidad.'),
('consentimiento para grabar','Permiso específico para tomar fotos, audio o video; no se presume por consentir la actividad.'),
('consentimiento para publicar','Permiso específico para compartir contenido con terceros o en redes; es distinto de permitir grabarlo.'),
('compatibilidad de aftercare','Coincidencia o capacidad de acordar cuidados posteriores que funcionen para las personas involucradas.'),
('expectativa explícita','Expectativa comunicada y acordada en lugar de darse por hecha.'),
('expectativa implícita','Suposición no hablada sobre lo que otra persona debería hacer o aceptar.'),
('responsabilidad compartida','Idea de que todas las personas mantienen responsabilidad sobre comunicación, límites y seguridad dentro de sus posibilidades.'),
('autoridad consensuada','Autoridad que existe porque fue acordada dentro de un alcance concreto y puede revisarse.'),
('autonomía dentro del rol','Capacidad de conservar decisiones, límites y voz propia aunque exista intercambio consensuado de poder.'),
('pausa','Interrupción temporal para revisar estado, comunicación o condiciones antes de decidir si continuar.'),
('revisión de límites','Conversación para confirmar si límites y condiciones siguen siendo los mismos con el paso del tiempo.'),
('compatibilidad de expectativas','Coincidencia suficiente entre lo que cada persona espera de una relación o dinámica.'),
('presión social','Influencia del grupo o de una persona que puede dificultar una decisión realmente libre.'),
('presión por experiencia','Idea equivocada de que alguien debe aceptar algo para demostrar que es experimentado o “de verdad”.'),
('presión por rol','Idea equivocada de que una etiqueta como Dom, sub o Switch obliga a aceptar determinadas conductas.'),
('señal de incomodidad','Cambio verbal o conductual que merece atención y puede justificar una pausa o comprobación.'),
('comunicación previa','Conversación antes de una dinámica para alinear expectativas, límites, señales y cuidados.'),
('comunicación durante','Check-ins, señales y observación usadas para mantener claridad durante una dinámica.'),
('comunicación posterior','Conversación después de una experiencia para compartir sensaciones y ajustar futuros acuerdos.'),
('aprendizaje gradual','Adquirir experiencia paso a paso, sin asumir que conocer la teoría equivale a dominar una práctica.'),
('competencia técnica','Conocimientos y habilidades necesarios para realizar una práctica concreta de forma responsable dentro de sus riesgos.'),
('competencia relacional','Habilidades de escuchar, negociar, respetar límites, recibir feedback y manejar desacuerdos.'),
('mitigación de riesgo','Medidas para reducir probabilidad o gravedad de daños cuando una actividad conserva algún riesgo.'),
('consentimiento no transferible','El permiso dado a una persona o situación no se transfiere automáticamente a otra.'),
('acuerdo de alcance','Definición de dónde, cuándo y sobre qué temas aplica una autoridad o dinámica.'),
('derecho a renegociar','Posibilidad de proponer cambios a acuerdos sin que hacerlo sea tratado como desobediencia o traición.'),
('derecho a detener','Posibilidad de parar una interacción cuando sea necesario, incluso si antes se había acordado continuar.'),
]

BASE += [
    ('safecall', 'Plan de seguridad en el que una persona externa sabe dónde estás o espera una confirmación en un momento acordado.'),
    ('persona de confianza', 'Contacto externo elegido para apoyar un plan de seguridad o saber dónde acudir si algo sale mal.'),
    ('revisión previa', 'Comprobación breve antes de empezar para confirmar estado, límites, señales y cualquier cambio reciente.'),
    ('revisión posterior', 'Comprobación después de una dinámica para identificar molestias, emociones o ajustes que no aparecieron de inmediato.'),
    ('acuerdo de intensidad', 'Definición compartida de qué nivel de intensidad se busca y cómo se reducirá o aumentará.'),
    ('acuerdo de duración', 'Definición aproximada o máxima del tiempo que durará una actividad o dinámica.'),
    ('acuerdo de espacio', 'Definición de los lugares donde una dinámica aplica y de los espacios donde queda fuera.'),
    ('acuerdo de lenguaje', 'Pacto sobre palabras, títulos o expresiones que se pueden usar y cuáles no.'),
    ('límite temporal', 'Límite que aplica durante cierto periodo o mientras exista una condición concreta.'),
    ('límite de privacidad', 'Límite sobre qué información, imágenes o detalles no pueden compartirse.'),
    ('límite relacional', 'Límite sobre conductas o decisiones que afectan la relación fuera de una escena o rol.'),
    ('límite de contexto', 'Límite que cambia según lugar, momento, compañía o circunstancias acordadas.'),
    ('acuerdo de señales', 'Pacto sobre las palabras, gestos o acciones que comunicarán continuar, bajar intensidad o detener.'),
    ('consentimiento condicionado', 'Consentimiento válido solo mientras se mantengan ciertas condiciones previamente acordadas.'),
    ('consentimiento actualizado', 'Confirmación de que un acuerdo anterior sigue vigente cuando ha pasado tiempo o cambió el contexto.'),
    ('retirada de consentimiento', 'Decisión de dejar de participar, que debe respetarse aunque antes hubiera existido un sí.'),
    ('rechazo informado', 'Decisión de no participar después de conocer la propuesta y sus condiciones; no necesita ser negociado hasta convertirse en sí.'),
    ('pausa de seguridad', 'Interrupción para comprobar bienestar, equipo, entorno o comunicación antes de decidir si continuar.'),
    ('escalado gradual', 'Aumento progresivo de intensidad o complejidad según respuesta, experiencia y acuerdos.'),
    ('desescalado', 'Reducción de intensidad o complejidad cuando una señal, estado o acuerdo lo requiere.'),
    ('riesgo físico', 'Posibilidad de daño corporal asociada a una práctica o situación.'),
    ('riesgo emocional', 'Posibilidad de una reacción emocional difícil que debe considerarse en negociación y cuidados.'),
    ('riesgo social', 'Posibles consecuencias de privacidad, reputación o relaciones derivadas de que información íntima se conozca.'),
    ('riesgo digital', 'Posibles consecuencias de guardar, reenviar, perder o exponer contenido privado en dispositivos o plataformas.'),
    ('mapa de riesgos', 'Revisión de riesgos relevantes, señales de alerta y medidas para reducirlos antes de una actividad.'),
    ('equipo de seguridad', 'Herramientas preparadas para responder a problemas previsibles dentro de una práctica concreta.'),
    ('salida rápida', 'Forma acordada de liberar o detener una situación con rapidez si aparece una señal de riesgo.'),
    ('observación activa', 'Prestar atención a comunicación, postura, coloración, movilidad y conducta en lugar de depender solo de una palabra.'),
    ('estado basal', 'Cómo se encuentra una persona antes de empezar; sirve como referencia para notar cambios durante la actividad.'),
    ('fatiga', 'Cansancio que puede afectar atención, coordinación y capacidad de tomar decisiones con claridad.'),
    ('sobrecarga emocional', 'Estado de saturación en el que conviene bajar intensidad, pausar o terminar y priorizar regulación.'),
    ('descompresión', 'Periodo de calma y transición después de una experiencia intensa antes de volver a actividades cotidianas.'),
    ('cierre de escena', 'Momento acordado que marca que una escena o dinámica concreta terminó y comienza la transición posterior.'),
    ('reconexión', 'Acciones acordadas para recuperar sensación de cercanía, calma o normalidad después de una dinámica.'),
    ('aftercare práctico', 'Cuidados posteriores centrados en necesidades concretas como agua, descanso, temperatura o comida.'),
    ('aftercare emocional', 'Cuidados posteriores centrados en escucha, tranquilidad, validación o cercanía según lo acordado.'),
    ('aftercare con espacio', 'Cuidado que respeta que una persona prefiera silencio, distancia o tiempo a solas después.'),
    ('check-in diferido', 'Comprobación realizada horas o días después para saber cómo evolucionó el bienestar de las personas.'),
    ('feedback específico', 'Comentario centrado en una conducta o momento concreto para que sea más fácil entender qué repetir o cambiar.'),
    ('feedback bidireccional', 'Intercambio donde todas las personas pueden expresar qué funcionó, qué no y qué necesitan ajustar.'),
    ('reparación', 'Proceso de reconocer un daño o error, asumir responsabilidad y acordar cambios concretos cuando es posible.'),
    ('responsabilidad', 'Capacidad de responder por las propias decisiones y corregir conductas sin esconderse detrás de un rol.'),
    ('rendición de cuentas', 'Aceptar revisión y consecuencias razonables cuando se incumplen acuerdos o normas de una comunidad.'),
    ('confidencialidad', 'Compromiso de no divulgar información privada compartida dentro de una relación, dinámica o conversación.'),
    ('anonimización', 'Eliminar datos identificables antes de compartir una experiencia o ejemplo con terceros.'),
    ('permiso de terceros', 'Consentimiento de cualquier persona externa que pueda verse involucrada, identificada o afectada por una actividad.'),
    ('discreción', 'Cuidado consciente de no exponer información íntima o de rol fuera de los espacios acordados.'),
    ('reputación comunitaria', 'Información sobre experiencias previas de una persona; puede orientar, pero no sustituye la propia evaluación.'),
    ('referencia', 'Información aportada por otra persona sobre experiencias previas; debe interpretarse con contexto y criterio.'),
    ('evento social kink', 'Encuentro comunitario cuyo propósito puede ser convivencia, aprendizaje o socialización, con reglas propias del espacio.'),
    ('regla de espacio', 'Norma de un evento o grupo que aplica dentro de ese lugar y no crea autoridad automática fuera de él.'),
    ('etiqueta comunitaria', 'Nombre usado para describir un rol, práctica o estilo; puede variar entre personas y comunidades.'),
    ('compatibilidad de ritmo', 'Coincidencia razonable en la velocidad con la que dos personas quieren construir confianza o explorar una dinámica.'),
    ('compatibilidad de comunicación', 'Capacidad de entenderse y resolver dudas, límites y feedback de una forma que funcione para ambas partes.'),
    ('compatibilidad de riesgo', 'Coincidencia suficiente en el nivel de riesgo que cada persona está dispuesta a aceptar.'),
    ('compatibilidad de estructura', 'Coincidencia sobre cuánto protocolo, formalidad o reglas desean dentro de la dinámica.'),
    ('espacio fuera de rol', 'Momentos o contextos donde la autoridad o protocolo de una dinámica se deja expresamente en pausa.'),
    ('transición de rol', 'Forma acordada de entrar o salir de un rol para evitar confundir una escena con la vida cotidiana.'),
    ('señal de entrada', 'Palabra, gesto o ritual que marca de forma acordada el comienzo de una escena o modo de rol.'),
    ('señal de salida', 'Palabra, gesto o ritual que marca de forma acordada el final de una escena o modo de rol.'),
    ('autoevaluación', 'Revisión personal de capacidades, límites, estado emocional y preparación antes de asumir una actividad.'),
    ('aprendizaje supervisado', 'Práctica acompañada por alguien competente cuando una habilidad requiere más que teoría o videos.'),
    ('práctica en seco', 'Ensayo de pasos, señales o procedimientos sin intensidad real para aprender una técnica o respuesta de seguridad.'),
    ('plan de contingencia', 'Alternativa preparada para responder si el plan principal deja de ser seguro o posible.'),
]

# Quiz de emojis: solo texto y botones de Telegram. No descarga imágenes ni archivos.
EMOJI_QUIZ=[
('🚦🟢🟡🔴','Sistema semáforo',['Sistema semáforo','Aftercare','Munch','Vetting'],'Verde, amarillo y rojo suelen representar un sistema de comunicación por niveles.'),
('🛑🗣️🔐','Palabra de seguridad',['Palabra de seguridad','Título BDSM','Protocolo alto','Pet play'],'Una palabra de seguridad ayuda a comunicar pausa o detención con claridad.'),
('🤝✅🔄','Consentimiento reversible',['Consentimiento reversible','Contrato permanente','Jerarquía fija','Protocolo universal'],'El consentimiento puede cambiar o retirarse; no queda bloqueado para siempre.'),
('🗣️📋🤝','Negociación',['Negociación','Aftercare','Subdrop','Munch'],'Hablar y acordar antes de una dinámica representa la negociación.'),
('🫂🧃🛋️','Aftercare',['Aftercare','Vetting','Impact play','Protocolo'],'Cuidado, descanso y atención posterior son ejemplos de aftercare.'),
('👑↔️🖤','Switch',['Switch','Dominante','Sumiso','Top'],'La flecha entre dos posiciones representa poder disfrutar ambos roles.'),
('👑➡️🤝','Dominante',['Dominante','Bottom','Munch','Aftercare'],'El rol dominante asume control consensuado dentro de acuerdos.'),
('🤝➡️🖤','Sumiso',['Sumiso','Top','Vetting','RACK'],'El rol sumiso cede control de forma consensuada dentro de límites.'),
('🔒🚫','Límite duro',['Límite duro','Límite blando','Check-in','Feedback'],'Candado y prohibición representan algo que no se acepta realizar.'),
('⚠️🤔✅','Límite blando',['Límite blando','Límite duro','Rojo','Outing'],'Puede explorarse solo bajo condiciones concretas y habladas.'),
('🟢➡️','Verde',['Verde','Amarillo','Rojo','Aftercare'],'En el semáforo, verde suele significar que se puede continuar según lo acordado.'),
('🟡⏸️','Amarillo',['Amarillo','Verde','Rojo','Munch'],'Amarillo suele pedir bajar intensidad, pausar o comprobar.'),
('🔴🛑','Rojo',['Rojo','Verde','Amarillo','Feedback'],'Rojo suele significar detener inmediatamente.'),
('👂💬✅','Escucha activa',['Escucha activa','Coerción','Outing','24/7'],'Escuchar, comprobar comprensión y responder a lo dicho representa escucha activa.'),
('📸🔐🤝','Consentimiento para grabar',['Consentimiento para grabar','Pet play','TPE','Subdrop'],'Grabar requiere permiso específico, separado de consentir la actividad.'),
('📲🌍🔐','Consentimiento para publicar',['Consentimiento para publicar','Aftercare','Brat','Top'],'Publicar o compartir con terceros requiere un permiso propio.'),
('🕵️‍♂️🔎🤝','Vetting',['Vetting','Munch','Drop','Ritual'],'Investigar prudentemente referencias e información antes de confiar es vetting.'),
('☕👥💬','Munch',['Munch','Scene','TPE','Bondage'],'Una reunión social informal de la comunidad suele llamarse munch.'),
('🎭⏱️🤝','Scene',['Scene','Outing','Aftercare','Feedback'],'Un periodo o contexto acordado para una dinámica puede llamarse scene.'),
('⚖️⚠️🤝','RACK',['RACK','SSC','TPE','D/s'],'RACK enfatiza consentimiento y conciencia informada del riesgo.'),
('🛡️🧠🤝','SSC',['SSC','RACK','CNC','NRE'],'SSC se resume históricamente como Seguro, Sensato y Consensuado.'),
('🧩✅❌','Consentimiento granular',['Consentimiento granular','24/7','Subdrop','Protocolo alto'],'Aceptar o rechazar componentes por separado representa consentimiento granular.'),
('🧠💭≠✅','Fantasía',['Fantasía','Consentimiento informado','Vetting','Ritual'],'Imaginar algo no equivale a querer realizarlo.'),
('📜🤝🔄','Contrato simbólico',['Contrato simbólico','Consentimiento irrevocable','Munch','Check-in'],'Un contrato puede expresar acuerdos, pero no elimina la revisión continua del consentimiento.'),
('💬➡️🔄','Renegociación',['Renegociación','Coerción','Outing','Drop'],'Hablar para modificar acuerdos representa renegociación.'),
('⏸️👀💬','Check-in',['Check-in','Collar','Munch','Ritual'],'Pausar o preguntar para comprobar bienestar es un check-in.'),
('⬇️😔⏳','Drop',['Drop','Vetting','Top','Munch'],'Un bajón físico o emocional después de una experiencia intensa puede llamarse drop.'),
('👑⬇️😔','Domdrop',['Domdrop','Subdrop','Aftercare','Brat'],'El bajón posterior en quien ocupó el rol dominante puede llamarse domdrop.'),
('🖤⬇️😔','Subdrop',['Subdrop','Domdrop','Munch','Vetting'],'El bajón posterior en quien ocupó el rol sumiso puede llamarse subdrop.'),
('💬🔍📝','Debrief',['Debrief','Outing','Scene','Collar'],'Revisar después qué funcionó y qué ajustar es un debrief.'),
('🔐👤📱','Privacidad digital',['Privacidad digital','Impact play','Brat','RACK'],'Mensajes, capturas y archivos requieren acuerdos de privacidad también en lo digital.'),
('🚪➡️🛑','Plan de salida',['Plan de salida','Aftercare','TPE','Munch'],'Acordar cómo detener y salir de una situación inesperada es un plan de salida.'),
('✂️🧵🆘','Tijeras de seguridad',['Tijeras de seguridad','Collar','Ritual','Munch'],'Una herramienta de corte de emergencia puede formar parte de la preparación de seguridad.'),
('🧍✅🧠','Autonomía',['Autonomía','Coerción','Outing','Protocolo alto'],'Poder decidir sobre el propio cuerpo y participación representa autonomía.'),
('😣➡️✅❓','Coerción',['Coerción','Consentimiento entusiasta','Aftercare','Feedback'],'Presión o amenaza puede impedir una decisión realmente libre.'),
('🗣️👍✨','Consentimiento entusiasta',['Consentimiento entusiasta','Outing','Drop','Munch'],'Una participación clara y voluntaria se asocia con consentimiento entusiasta.'),
('🧠ℹ️✅','Consentimiento informado',['Consentimiento informado','Consentimiento implícito','TPE','Brat'],'Decidir con información suficiente sobre lo propuesto representa consentimiento informado.'),
('🍺❓🧠','Capacidad para consentir',['Capacidad para consentir','Aftercare','Vetting','Protocolo'],'La intoxicación puede afectar la capacidad de comprender y decidir libremente.'),
('🔁📅🤝','Revisión de límites',['Revisión de límites','Outing','Munch','Ritual'],'Volver a hablar de límites con el tiempo representa revisarlos.'),
('👥❤️❌🧩','Incompatibilidad',['Incompatibilidad','Coerción','Aftercare','Feedback'],'Dos personas pueden apreciarse y aun así no encajar en deseos o límites.'),
('✅🧩✅','Compatibilidad',['Compatibilidad','Outing','Subdrop','CNC'],'Coincidencia suficiente entre deseos, límites y expectativas representa compatibilidad.'),
('🏷️≠📜','Etiqueta no universal',['Etiqueta no universal','Contrato legal','Rojo','Aftercare'],'Una etiqueta orienta, pero no define por sí sola todos los acuerdos de una persona.'),
('👑⚖️🤝','Autoridad consensuada',['Autoridad consensuada','Superioridad personal','Coerción','Outing'],'La autoridad dentro de una dinámica existe por acuerdo, no por superioridad humana.'),
('🧍🗣️👑','Autonomía dentro del rol',['Autonomía dentro del rol','Obediencia automática','Outing','Munch'],'Tener rol no elimina la capacidad de decidir, negociar o detenerse.'),
('📦🧠➡️📈','Aprendizaje gradual',['Aprendizaje gradual','Experiencia instantánea','Outing','Drop'],'Aprender paso a paso evita confundir teoría con competencia práctica.'),
('🧰🧠✅','Competencia técnica',['Competencia técnica','Reputación','NRE','Munch'],'Conocer una técnica y sus riesgos forma parte de la competencia técnica.'),
('👂🤝💬','Competencia relacional',['Competencia relacional','Impact play','Collar','Drop'],'Escuchar, negociar y manejar feedback son habilidades relacionales.'),
('⚠️⬇️🛡️','Mitigación de riesgo',['Mitigación de riesgo','Riesgo cero','Outing','Brat'],'Reducir probabilidad o gravedad de daño es mitigación, no eliminación total del riesgo.'),
('👤✅➡️👤❌','Consentimiento no transferible',['Consentimiento no transferible','TPE','Munch','Aftercare'],'El permiso dado a una persona no se transfiere automáticamente a otra.'),
('🗺️📍🤝','Acuerdo de alcance',['Acuerdo de alcance','Outing','Drop','Brat'],'Definir dónde, cuándo y sobre qué aplica una dinámica es acordar su alcance.'),
('🔄🗣️✅','Derecho a renegociar',['Derecho a renegociar','Obediencia absoluta','Outing','Munch'],'Poder proponer cambios sin perder el derecho a ser escuchado representa renegociación.'),
]

EMOJI_QUIZ += [
    ('📞🕒✅', 'Safecall', ['Safecall', 'Aftercare', 'Ritual', 'Collar'], 'Una llamada o confirmación acordada con alguien externo representa un safecall.'),
    ('👤🤝🛡️', 'Persona de confianza', ['Persona de confianza', 'Brat tamer', 'Bottom', 'Outing'], 'Una persona externa elegida para apoyar un plan de seguridad puede ser una persona de confianza.'),
    ('🔍✅➡️🎬', 'Revisión previa', ['Revisión previa', 'Subdrop', 'Munch', 'Drop'], 'Comprobar estado y acuerdos antes de empezar es una revisión previa.'),
    ('🎬➡️🔍✅', 'Revisión posterior', ['Revisión posterior', 'Vetting', 'TPE', 'Protocolo alto'], 'Comprobar cómo quedó todo después de terminar representa una revisión posterior.'),
    ('📈🎚️🤝', 'Acuerdo de intensidad', ['Acuerdo de intensidad', 'Privacidad', 'Munch', 'Outing'], 'Acordar cuánto subir o bajar la intensidad es un acuerdo de intensidad.'),
    ('⏱️🤝📋', 'Acuerdo de duración', ['Acuerdo de duración', 'Consentimiento implícito', 'Collar', 'Brat'], 'Definir cuánto tiempo puede durar algo representa un acuerdo de duración.'),
    ('📍✅🚫', 'Acuerdo de espacio', ['Acuerdo de espacio', 'Aftercare', 'Drop', 'Top'], 'Definir dónde aplica y dónde no una dinámica es un acuerdo de espacio.'),
    ('🗣️✅🚫', 'Acuerdo de lenguaje', ['Acuerdo de lenguaje', 'RACK', 'Munch', 'Vetting'], 'Acordar palabras permitidas o no permitidas representa un acuerdo de lenguaje.'),
    ('📅⏳🚧', 'Límite temporal', ['Límite temporal', 'Título', 'Safeword', 'Scene'], 'Un límite que existe durante cierto periodo es un límite temporal.'),
    ('🔐📸🚧', 'Límite de privacidad', ['Límite de privacidad', 'Impact play', 'Switch', 'Drop'], 'Poner una frontera sobre fotos o información privada representa un límite de privacidad.'),
    ('❤️🏠🚧', 'Límite relacional', ['Límite relacional', 'Munch', 'Ritual', 'Safecall'], 'Un límite sobre lo que afecta la relación fuera del rol es un límite relacional.'),
    ('📍🕒👥🚧', 'Límite de contexto', ['Límite de contexto', 'SSC', 'Top', 'Aftercare'], 'Un límite que depende del lugar, momento o personas presentes es contextual.'),
    ('🗣️✋🟡🔴', 'Acuerdo de señales', ['Acuerdo de señales', 'Outing', 'Munch', 'Pet play'], 'Pactar señales para ajustar o detener es un acuerdo de señales.'),
    ('✅➕📋', 'Consentimiento condicionado', ['Consentimiento condicionado', 'Consentimiento ilimitado', 'TPE', 'Drop'], 'Un sí válido solo bajo condiciones concretas representa consentimiento condicionado.'),
    ('📅🔄✅', 'Consentimiento actualizado', ['Consentimiento actualizado', 'Consentimiento automático', 'Collar', 'Munch'], 'Volver a confirmar un acuerdo tras tiempo o cambios es consentimiento actualizado.'),
    ('✅➡️❌', 'Retirada de consentimiento', ['Retirada de consentimiento', 'Aftercare', 'Ritual', 'Top'], 'Pasar de aceptar a dejar de aceptar representa retirada de consentimiento.'),
    ('ℹ️🤔❌', 'Rechazo informado', ['Rechazo informado', 'Coerción', 'TPE', 'Subdrop'], 'Decir no después de entender la propuesta es un rechazo informado.'),
    ('⏸️🛡️🔍', 'Pausa de seguridad', ['Pausa de seguridad', 'Munch', 'Collar', 'Outing'], 'Pausar para revisar bienestar o equipo es una pausa de seguridad.'),
    ('1️⃣➡️2️⃣➡️3️⃣', 'Escalado gradual', ['Escalado gradual', 'Riesgo cero', 'Outing', 'Drop'], 'Subir por etapas según respuesta y acuerdos es escalado gradual.'),
    ('3️⃣➡️2️⃣➡️1️⃣', 'Desescalado', ['Desescalado', 'TPE', 'Vetting', 'Munch'], 'Reducir intensidad cuando hace falta representa desescalado.'),
    ('🩹⚠️🧍', 'Riesgo físico', ['Riesgo físico', 'Privacidad digital', 'Aftercare', 'Munch'], 'La posibilidad de daño corporal corresponde a riesgo físico.'),
    ('🧠⚠️💭', 'Riesgo emocional', ['Riesgo emocional', 'Impact play', 'Collar', 'Top'], 'La posibilidad de una reacción emocional difícil corresponde a riesgo emocional.'),
    ('👥⚠️🗣️', 'Riesgo social', ['Riesgo social', 'Bondage', 'Aftercare', 'Switch'], 'Consecuencias de reputación o relaciones por exposición de información son riesgo social.'),
    ('📱🔓⚠️', 'Riesgo digital', ['Riesgo digital', 'Subdrop', 'Ritual', 'Munch'], 'La exposición o pérdida de contenido privado en dispositivos es riesgo digital.'),
    ('🗺️⚠️🛡️', 'Mapa de riesgos', ['Mapa de riesgos', 'Contrato legal', 'Pet play', 'Drop'], 'Revisar riesgos y medidas antes de actuar es un mapa de riesgos.'),
    ('🧰🛡️✅', 'Equipo de seguridad', ['Equipo de seguridad', 'Título', 'Munch', 'Top'], 'Herramientas preparadas para responder a problemas forman equipo de seguridad.'),
    ('🚪⚡✅', 'Salida rápida', ['Salida rápida', 'Outing', 'NRE', 'Ritual'], 'Una forma preparada de detener y liberar rápidamente es una salida rápida.'),
    ('👀🧠✅', 'Observación activa', ['Observación activa', 'Consentimiento implícito', 'Munch', 'Drop'], 'Prestar atención a cambios y señales además de escuchar palabras es observación activa.'),
    ('🙂📍➡️🔍', 'Estado basal', ['Estado basal', 'TPE', 'Collar', 'Aftercare'], 'Saber cómo está alguien antes sirve como referencia: estado basal.'),
    ('😴⚠️🧠', 'Fatiga', ['Fatiga', 'Vetting', 'Munch', 'Ritual'], 'El cansancio que afecta atención y coordinación es fatiga.'),
    ('🧠🌊⏸️', 'Sobrecarga emocional', ['Sobrecarga emocional', 'Impact play', 'Top', 'Collar'], 'Sentirse saturado emocionalmente puede requerir pausa o cierre.'),
    ('🎬➡️😌🕒', 'Descompresión', ['Descompresión', 'Outing', 'Munch', 'TPE'], 'El periodo de calma tras algo intenso representa descompresión.'),
    ('🎬✅🏁', 'Cierre de escena', ['Cierre de escena', 'Consentimiento implícito', 'Vetting', 'Drop'], 'Marcar que una escena terminó es un cierre de escena.'),
    ('🤝❤️🔄', 'Reconexión', ['Reconexión', 'RACK', 'Outing', 'Top'], 'Volver a cercanía o calma después de una dinámica puede ser reconexión.'),
    ('💧🍎🛏️', 'Aftercare práctico', ['Aftercare práctico', 'Vetting', 'Munch', 'Collar'], 'Agua, comida y descanso son ejemplos de aftercare práctico.'),
    ('👂💬🤍', 'Aftercare emocional', ['Aftercare emocional', 'Impact play', 'TPE', 'Outing'], 'Escucha y tranquilidad pueden formar parte del aftercare emocional.'),
    ('🤍↔️🧍', 'Aftercare con espacio', ['Aftercare con espacio', 'Coerción', 'Munch', 'Collar'], 'Respetar distancia o tiempo a solas puede ser aftercare con espacio.'),
    ('🕒📅📞', 'Check-in diferido', ['Check-in diferido', 'Top', 'Outing', 'Brat'], 'Comprobar bienestar horas o días después es un check-in diferido.'),
    ('🎯💬📝', 'Feedback específico', ['Feedback específico', 'Munch', 'TPE', 'Collar'], 'Hablar de una conducta concreta hace el feedback más específico.'),
    ('↔️💬✅', 'Feedback bidireccional', ['Feedback bidireccional', 'Outing', 'Drop', 'Vetting'], 'Cuando todas las partes pueden dar feedback, es bidireccional.'),
    ('⚠️🙋🛠️', 'Reparación', ['Reparación', 'RACK', 'Munch', 'Top'], 'Reconocer un error y acordar cambios concretos forma parte de reparar.'),
    ('🙋⚖️✅', 'Responsabilidad', ['Responsabilidad', 'Consentimiento automático', 'Outing', 'Drop'], 'Responder por las propias decisiones representa responsabilidad.'),
    ('📋⚖️🙋', 'Rendición de cuentas', ['Rendición de cuentas', 'Pet play', 'Aftercare', 'Munch'], 'Aceptar revisión y consecuencias razonables es rendición de cuentas.'),
    ('🤫🔐🤝', 'Confidencialidad', ['Confidencialidad', 'Impact play', 'TPE', 'Brat'], 'No divulgar información privada acordada representa confidencialidad.'),
    ('📝👤❌', 'Anonimización', ['Anonimización', 'Outing', 'Subdrop', 'Collar'], 'Quitar datos identificables antes de compartir un ejemplo es anonimización.'),
    ('👥✅📋', 'Permiso de terceros', ['Permiso de terceros', 'Coerción', 'Munch', 'Drop'], 'Las personas externas afectadas necesitan su propio permiso.'),
    ('🤫👀🔐', 'Discreción', ['Discreción', 'Impact play', 'Top', 'Ritual'], 'Evitar exponer información íntima fuera de lo acordado es discreción.'),
    ('👥⭐🗣️', 'Reputación comunitaria', ['Reputación comunitaria', 'Consentimiento específico', 'Drop', 'Collar'], 'Lo que otras personas cuentan puede orientar, pero no sustituye tu evaluación.'),
    ('👤➡️🗣️ℹ️', 'Referencia', ['Referencia', 'TPE', 'Aftercare', 'Munch'], 'Información de otra persona sobre experiencias previas es una referencia.'),
    ('☕👥💬', 'Evento social kink', ['Evento social kink', 'Suspensión', 'Impact play', 'Safeword'], 'Un encuentro de convivencia o aprendizaje puede ser un evento social kink.'),
    ('🏠📜📍', 'Regla de espacio', ['Regla de espacio', 'Autoridad universal', 'Drop', 'Collar'], 'Una norma puede aplicar solo dentro del lugar o evento que la establece.'),
    ('🏷️👥↔️', 'Etiqueta comunitaria', ['Etiqueta comunitaria', 'Contrato legal', 'Safecall', 'Drop'], 'Una etiqueta puede variar entre comunidades y personas.'),
    ('🐢🤝🐇', 'Compatibilidad de ritmo', ['Compatibilidad de ritmo', 'Outing', 'TPE', 'Munch'], 'Querer avanzar a ritmos parecidos representa compatibilidad de ritmo.'),
    ('💬🤝✅', 'Compatibilidad de comunicación', ['Compatibilidad de comunicación', 'Impact play', 'Collar', 'Drop'], 'Poder entenderse y resolver dudas representa compatibilidad de comunicación.'),
    ('⚠️🤝⚖️', 'Compatibilidad de riesgo', ['Compatibilidad de riesgo', 'Outing', 'Munch', 'Brat'], 'Aceptar niveles de riesgo similares representa compatibilidad de riesgo.'),
    ('📋🤝🏛️', 'Compatibilidad de estructura', ['Compatibilidad de estructura', 'Subdrop', 'Top', 'Munch'], 'Coincidir en cuánto protocolo o reglas desean es compatibilidad de estructura.'),
    ('👑⏸️🏠', 'Espacio fuera de rol', ['Espacio fuera de rol', 'TPE absoluto', 'Outing', 'Drop'], 'Un momento donde el rol queda en pausa es un espacio fuera de rol.'),
    ('👤➡️🎭➡️👤', 'Transición de rol', ['Transición de rol', 'Consentimiento implícito', 'Munch', 'Vetting'], 'Entrar o salir de un rol de forma clara es una transición de rol.'),
    ('🔔▶️🎭', 'Señal de entrada', ['Señal de entrada', 'Outing', 'Drop', 'Aftercare'], 'Una señal que marca el inicio de una escena o modo de rol es señal de entrada.'),
    ('🔔⏹️🎭', 'Señal de salida', ['Señal de salida', 'TPE', 'Munch', 'Collar'], 'Una señal que marca el final de una escena o modo de rol es señal de salida.'),
    ('🪞🧠📋', 'Autoevaluación', ['Autoevaluación', 'Outing', 'Drop', 'Munch'], 'Revisar tus capacidades, límites y estado antes de actuar es autoevaluación.'),
    ('👩\u200d🏫🧠🛡️', 'Aprendizaje supervisado', ['Aprendizaje supervisado', 'Experiencia instantánea', 'Outing', 'Collar'], 'Aprender con supervisión cuando la técnica lo requiere es aprendizaje supervisado.'),
    ('🧪📝0️⃣', 'Práctica en seco', ['Práctica en seco', 'TPE', 'Munch', 'Subdrop'], 'Ensayar procedimientos sin intensidad real es práctica en seco.'),
    ('🅱️🛡️📋', 'Plan de contingencia', ['Plan de contingencia', 'Contrato irreversible', 'Outing', 'Top'], 'Tener una alternativa preparada si el plan principal falla es un plan de contingencia.'),
    ('📸✅≠🌐✅', 'Grabar no es publicar', ['Grabar no es publicar', 'Consentimiento universal', 'Munch', 'Drop'], 'Autorizar una grabación no autoriza automáticamente publicarla.'),
    ('👑✅📍', 'Autoridad con alcance', ['Autoridad con alcance', 'Superioridad personal', 'Outing', 'Munch'], 'La autoridad acordada aplica dentro de un alcance, no a toda decisión.'),
    ('🧍\u200d♀️🧍\u200d♂️🚫👑', 'Sin autoridad automática', ['Sin autoridad automática', 'TPE', 'Collar', 'Aftercare'], 'Un rol no da autoridad sobre personas con quienes no existe acuerdo.'),
    ('🧠❓➡️🗣️', 'Pedir aclaración', ['Pedir aclaración', 'Coerción', 'Drop', 'Munch'], 'Preguntar cuando algo no se entiende evita asumir.'),
    ('🗣️👂🔁', 'Confirmar comprensión', ['Confirmar comprensión', 'Outing', 'TPE', 'Brat'], 'Repetir con tus palabras lo entendido ayuda a confirmar comprensión.'),
    ('❌🧾🚫', 'Un no no necesita contrato', ['Un no no necesita contrato', 'Consentimiento implícito', 'Munch', 'Collar'], 'Un no debe respetarse aunque no venga acompañado de una explicación extensa.'),
    ('🤔💭≠✅', 'Curiosidad no es consentimiento', ['Curiosidad no es consentimiento', 'Consentimiento automático', 'TPE', 'Aftercare'], 'Tener curiosidad por algo no equivale a haber aceptado hacerlo.'),
    ('💭🔥≠🎬', 'Fantasía no es acuerdo', ['Fantasía no es acuerdo', 'Contrato simbólico', 'Munch', 'Drop'], 'Una fantasía puede disfrutarse sin convertirla en una práctica acordada.'),
    ('🏷️≠🧠', 'Rol no define personalidad', ['Rol no define personalidad', 'TPE', 'Outing', 'Collar'], 'Una etiqueta de rol no determina toda la personalidad de una persona.'),
    ('⏳🤝🏗️', 'Confianza gradual', ['Confianza gradual', 'Confianza instantánea', 'Munch', 'Drop'], 'La confianza se construye con tiempo y conductas consistentes.'),
    ('🚩🗣️❌', 'No respetar un no', ['No respetar un no', 'Green flag', 'Aftercare', 'Munch'], 'Insistir después de un no es una señal de alerta.'),
    ('🟢🗣️✅', 'Respetar un no', ['Respetar un no', 'Red flag', 'Outing', 'Drop'], 'Aceptar un no sin castigo ni presión es una buena señal.'),
    ('⭐👤≠🛡️', 'Reputación no garantiza seguridad', ['Reputación no garantiza seguridad', 'Vetting innecesario', 'TPE', 'Collar'], 'Una reputación positiva no sustituye límites ni evaluación propia.'),
    ('📚≠🛠️', 'Teoría no es práctica', ['Teoría no es práctica', 'Experiencia completa', 'Outing', 'Munch'], 'Leer o ver videos no equivale a dominar una habilidad práctica.'),
    ('🛠️➕💬', 'Técnica y comunicación', ['Técnica y comunicación', 'Solo técnica', 'Drop', 'Collar'], 'La competencia responsable combina habilidad técnica con comunicación.'),
    ('⚠️0️⃣❌', 'Riesgo cero no existe', ['Riesgo cero no existe', 'SSC garantiza cero riesgo', 'Munch', 'Outing'], 'Reducir riesgos no significa prometer riesgo cero.'),
    ('📍🧰✅', 'Herramienta accesible', ['Herramienta accesible', 'Objeto decorativo', 'Drop', 'TPE'], 'Una herramienta de emergencia debe estar accesible y ser conocida.'),
    ('🧍🔄🧍', 'Cambio de rol', ['Cambio de rol', 'Incoherencia', 'Munch', 'Outing'], 'Moverse entre roles puede ser parte de ser Switch o de acuerdos concretos.'),
    ('50/50❌🔀', 'Switch no es 50/50', ['Switch no es 50/50', 'Switch obligatorio', 'Drop', 'Collar'], 'Ser Switch no exige repartir ambos roles por igual.'),
    ('👑❤️🛡️', 'Firmeza con cuidado', ['Firmeza con cuidado', 'Dominación por miedo', 'Outing', 'Munch'], 'Ser firme puede coexistir con empatía, cuidado y límites.'),
    ('🙇🧠✅', 'Sumisión con criterio', ['Sumisión con criterio', 'Obediencia sin límites', 'TPE absoluto', 'Drop'], 'La sumisión no elimina criterio, límites ni autonomía.'),
    ('🔄📜✅', 'Acuerdo revisable', ['Acuerdo revisable', 'Contrato eterno', 'Munch', 'Collar'], 'Los acuerdos pueden revisarse cuando cambian las circunstancias.'),
    ('📋✅❓', 'Checklist de negociación', ['Checklist de negociación', 'Consentimiento automático', 'Outing', 'Drop'], 'Una lista puede ayudar a recordar temas, pero no sustituye conversar.'),
    ('🤍📋🎬', 'Plan de aftercare', ['Plan de aftercare', 'Munch', 'Vetting', 'Top'], 'Hablar antes sobre cuidados posteriores es un plan de aftercare.'),
    ('🤝🤍↔️', 'Aftercare mutuo', ['Aftercare mutuo', 'Outing', 'Drop', 'Collar'], 'Cualquiera de las partes puede necesitar cuidado posterior.'),
    ('📅💬🔍', 'Seguimiento', ['Seguimiento', 'TPE', 'Munch', 'Brat'], 'Volver a hablar después para revisar bienestar es seguimiento.'),
    ('📱📸🔐', 'Privacidad digital', ['Privacidad digital', 'Impact play', 'Subdrop', 'Munch'], 'Acuerdos sobre mensajes, fotos y almacenamiento forman privacidad digital.'),
    ('📢👤❌', 'Outing', ['Outing', 'Aftercare', 'RACK', 'Collar'], 'Revelar sin permiso la participación BDSM de alguien es outing.'),
    ('📹✅', 'Consentimiento para grabar', ['Consentimiento para grabar', 'Consentimiento para publicar', 'Munch', 'Drop'], 'Permitir una grabación requiere consentimiento específico.'),
    ('🌐✅', 'Consentimiento para publicar', ['Consentimiento para publicar', 'Consentimiento para grabar', 'TPE', 'Aftercare'], 'Compartir contenido con terceros requiere permiso específico.'),
    ('🤍🤝🧩', 'Compatibilidad de aftercare', ['Compatibilidad de aftercare', 'Outing', 'Munch', 'Top'], 'Poder acordar cuidados posteriores compatibles importa en una dinámica.'),
    ('🗣️💡✅', 'Expectativa explícita', ['Expectativa explícita', 'Expectativa implícita', 'Drop', 'Collar'], 'Una expectativa hablada y acordada es explícita.'),
    ('🤐💭❓', 'Expectativa implícita', ['Expectativa implícita', 'Expectativa explícita', 'Munch', 'TPE'], 'Una expectativa no hablada que se da por hecha es implícita.'),
    ('🤝⚖️🛡️', 'Responsabilidad compartida', ['Responsabilidad compartida', 'Responsabilidad unilateral', 'Outing', 'Drop'], 'Todas las personas conservan responsabilidad sobre comunicación y límites.'),
    ('👑🤝📋', 'Autoridad consensuada', ['Autoridad consensuada', 'Autoridad automática', 'Munch', 'Collar'], 'La autoridad en una dinámica existe porque fue acordada.'),
    ('👤🗣️👑', 'Autonomía dentro del rol', ['Autonomía dentro del rol', 'Obediencia total obligatoria', 'Outing', 'Drop'], 'Mantener voz y límites dentro del rol representa autonomía.'),
    ('⏸️💬🔄', 'Pausa', ['Pausa', 'Fracaso', 'Munch', 'TPE'], 'Una pausa puede servir para comprobar y decidir si continuar.'),
    ('🚧🔄📅', 'Revisión de límites', ['Revisión de límites', 'Límites eternos', 'Outing', 'Collar'], 'Volver a hablar de límites con el tiempo representa revisarlos.'),
    ('🎯🤝💭', 'Compatibilidad de expectativas', ['Compatibilidad de expectativas', 'Coerción', 'Drop', 'Munch'], 'Coincidir razonablemente en lo que cada persona espera ayuda a la compatibilidad.'),
    ('👥➡️😬✅?', 'Presión social', ['Presión social', 'Consentimiento libre', 'Aftercare', 'Top'], 'Sentir que hay que aceptar por lo que piensa el grupo puede ser presión social.'),
    ('🎖️➡️😬', 'Presión por experiencia', ['Presión por experiencia', 'Vetting', 'Munch', 'Collar'], 'Aceptar algo para demostrar experiencia es presión por experiencia.'),
    ('🏷️➡️😬', 'Presión por rol', ['Presión por rol', 'Consentimiento entusiasta', 'Drop', 'Outing'], 'Creer que el rol obliga a aceptar algo es presión por rol.'),
    ('😶➡️😟👀', 'Señal de incomodidad', ['Señal de incomodidad', 'Green flag', 'Munch', 'TPE'], 'Un cambio de conducta puede justificar una comprobación.'),
]

OPEN=[]  # Los temas abiertos/debate automáticos se retiraron; el Quiz sigue siendo de conocimiento.

STEMS=['¿Qué término corresponde a esta definición?','🧠 Adivina el concepto:','🔎 Identifica el término:','🎭 ¿De qué estamos hablando?','📚 Ronda de conocimiento:']

def build_bank():
    out=[]; n=len(BASE)
    for i,(term,definition) in enumerate(BASE):
        wrong=[BASE[(i+7)%n][0],BASE[(i+17)%n][0],BASE[(i+29)%n][0]]
        family=f'concept-{i}'
        for v in range(5):
            out.append({'id':f'def-{i}-{v}','family':family,'type':'choice','q':f'{STEMS[v]}\n\n{definition}','answer':term,'explanation':f'{term}: {definition}','options':[term]+wrong})
        out.append({'id':f'tf-ok-{i}','family':family,'type':'choice','q':f'Verdadero o falso:\n\n«{term}» puede describirse como: {definition}','answer':'Verdadero','explanation':f'Es verdadero porque {term} se refiere a: {definition}','options':['Verdadero','Falso']})
        out.append({'id':f'tf-no-{i}','family':family,'type':'choice','q':f'Verdadero o falso:\n\n«{term}» significa: {BASE[(i+13)%n][1]}','answer':'Falso','explanation':f'Es falso. {term} significa: {definition}','options':['Verdadero','Falso']})

    scenarios=[
      ('Alguien dice rojo durante una dinámica.','Detenerse inmediatamente'),
      ('Una persona retira hoy algo que aceptó ayer.','Respetar la decisión actual'),
      ('Aparece entumecimiento bajo una restricción.','Detener y revisar'),
      ('Alguien está demasiado intoxicado para decidir con claridad.','Posponer'),
      ('Surge dolor inesperado.','Pausar y comprobar'),
      ('Quieren compartir una foto privada.','Pedir permiso específico'),
      ('Los límites de dos personas no encajan.','Aceptar la incompatibilidad sin presionar'),
      ('Alguien pide espacio como aftercare.','Respetar y adaptar el cuidado'),
      ('Una persona no puede hablar durante la práctica.','Usar la señal no verbal acordada'),
      ('Una persona experimentada dice que no necesita negociar.','Negociar igualmente'),
      ('Una persona aceptó una foto privada, pero nunca autorizó publicarla.','No publicarla sin permiso específico'),
      ('Durante una conversación alguien cambia un límite que llevaba meses igual.','Aceptar el cambio y renegociar'),
      ('Una persona dice “amarillo” y la otra no entiende si debe seguir igual.','Bajar intensidad o pausar y comprobar'),
      ('Dos personas usan la misma etiqueta de rol pero la entienden distinto.','Preguntar qué significa para cada una'),
      ('Una persona nueva siente presión por demostrar que “aguanta”.','Quitar la presión y respetar su ritmo'),
      ('Después de una dinámica alguien prefiere estar solo un rato.','Respetar el espacio acordado'),
      ('Alguien se ríe nerviosamente y deja de responder con claridad.','Pausar y comprobar su estado'),
      ('Una práctica parece sencilla, pero ninguno conoce bien sus riesgos.','Informarse antes de intentarla'),
      ('Una persona dice que no quiere explicar por qué algo es un límite.','Respetar el límite sin exigir explicación'),
      ('Un acuerdo funcionaba antes, pero ahora genera incomodidad.','Revisarlo y renegociarlo'),
      ('Un amigo del grupo asegura que alguien es “100% seguro”.','Usar esa referencia solo como un dato y negociar por cuenta propia'),
      ('Una persona quiere grabar una dinámica para verla después.','Pedir consentimiento específico para grabar'),
      ('Ya existe permiso para grabar, pero ahora quieren enviarlo a otra persona.','Pedir un permiso nuevo para compartirlo'),
      ('Alguien usa su rol para exigir obediencia a una persona con quien no tiene dinámica.','No asumir autoridad sin acuerdo'),
      ('Una persona se equivoca y cruza accidentalmente un acuerdo menor.','Detener, reconocerlo y hablar de cómo repararlo'),
      ('Dos personas quieren intensidades muy diferentes.','Buscar un punto compatible o aceptar la incompatibilidad'),
      ('Alguien cambia de idea justo antes de empezar.','Aceptar el cambio sin presionarlo'),
      ('La palabra de seguridad no puede usarse porque la persona no puede hablar.','Usar la señal no verbal previamente acordada'),
      ('Una persona tiene experiencia técnica pero ignora el feedback.','Priorizar comunicación y límites, no solo técnica'),
      ('Una persona siente que debe decir sí para no decepcionar a su pareja.','Hablar de la presión y devolver espacio real para decidir'),
      ('Después de una experiencia intensa alguien parece bien, pero al día siguiente se siente mal.','Hacer seguimiento y adaptar cuidados si lo necesita'),
      ('Una persona recibe un “no” y empieza a negociar para cambiarlo.','Aceptar el no y dejar de presionar'),
      ('Un acuerdo 24/7 no especifica qué pasa durante el trabajo o con familia.','Definir el alcance y las excepciones'),
      ('Una persona ve una dinámica ajena y quiere copiarla exactamente.','Negociar la propia en lugar de asumir acuerdos ajenos'),
      ('Alguien cree que pedir una pausa demuestra poca experiencia.','Normalizar la pausa como herramienta de comunicación'),
      ('Dos personas necesitan aftercare opuesto: una cercanía y otra espacio.','Acordar una forma que respete ambas necesidades'),
      ('Una persona nueva pregunta algo básico y otros se burlan.','Responder con respeto o dejar que alguien informado ayude'),
      ('Una etiqueta no coincide con lo que alguien espera de esa persona.','Preguntar por sus acuerdos en vez de imponer la etiqueta'),
      ('Alguien quiere probar algo solo porque el grupo lo considera avanzado.','Decidir por interés propio, no por presión social'),
      ('Una persona no sabe responder si realmente quiere continuar.','Pausar y darle espacio para decidir sin presión'),
    ]
    bad=['Continuar porque ya había aceptado','Ignorarlo','Decidir por la otra persona']
    for i,(scenario,answer) in enumerate(scenarios):
        # Las 10 situaciones antiguas conservan sus IDs históricos; las nuevas amplían el banco.
        repeats=3 if i<10 else 1
        for v in range(repeats):
            out.append({'id':f'sc-{i}-{v}','family':f'scenario-{i}','type':'choice','q':f'🛡️ Caso práctico\n\n{scenario}\n\n¿Qué opción respeta mejor seguridad y consentimiento?','answer':answer,'explanation':f"La opción correcta es «{answer}» porque prioriza consentimiento, seguridad y comunicación ante esa situación.",'options':[answer]+bad})

    for i,(emojis,answer,options,explanation) in enumerate(EMOJI_QUIZ):
        out.append({
            'id':f'emoji-{i}', 'family':f'emoji-{i}', 'format':'emoji', 'type':'choice',
            'q':f'🧩 QUIZ EMOJI BDSM\n\n{emojis}\n\n¿Qué concepto representan estos emojis?',
            'answer':answer, 'explanation':explanation, 'options':options,
        })

    # Se conservan las rondas mixtas que ya existían para compatibilidad, pero comparten
    # "family" con su pregunta original y el selector evita repetir esa familia pronto.
    k=0; source=[x for x in out if x['type']=='choice' and not x.get('format')=='emoji']
    while len(out)<1250:
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
        c.execute("ALTER TABLE bdsm_quiz_rounds_tb ADD COLUMN IF NOT EXISTS explanation_text TEXT")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_bdsm_quiz_one_open ON bdsm_quiz_rounds_tb(chat_id,thread_id) WHERE status='open'")
        c.execute("CREATE TABLE IF NOT EXISTS bdsm_quiz_attempts_tb (round_id BIGINT NOT NULL REFERENCES bdsm_quiz_rounds_tb(round_id) ON DELETE CASCADE,user_id BIGINT NOT NULL,answer_text TEXT NOT NULL,correct BOOLEAN NOT NULL DEFAULT FALSE,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(round_id,user_id))")
        c.execute("CREATE TABLE IF NOT EXISTS bdsm_quiz_history_tb (question_key TEXT PRIMARY KEY,last_used_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),uses INTEGER NOT NULL DEFAULT 1)")
        conn.commit()
    except Exception: conn.rollback(); raise
    finally: _put_connection(conn)

_QUIZ_BY_ID={q['id']:q for q in QUIZ_BANK}

def _pick():
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute('SELECT question_key FROM bdsm_quiz_history_tb ORDER BY last_used_at DESC LIMIT 180'); recent_ids=[r[0] for r in c.fetchall()]
    finally: _put_connection(conn)
    recent=set(recent_ids)
    recent_families={_QUIZ_BY_ID[k].get('family',k) for k in recent_ids if k in _QUIZ_BY_ID}
    pool=[q for q in QUIZ_BANK if q['id'] not in recent and q.get('family',q['id']) not in recent_families]
    if not pool:
        pool=[q for q in QUIZ_BANK if q['id'] not in recent] or QUIZ_BANK
    emoji=[q for q in pool if q.get('format')=='emoji']
    if emoji and random.random()<0.25:
        return random.choice(emoji)
    original=[q for q in pool if q['type']=='choice' and not q['id'].startswith('mix-')]
    candidates=original or [q for q in pool if q['type']=='choice']
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
        c.execute('INSERT INTO bdsm_quiz_rounds_tb(question_key,question_text,answer_text,explanation_text,status,chat_id,thread_id) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING round_id',(q['id'],q['q'],q.get('answer'),q.get('explanation'),status,QUIZ_CHAT_ID,QUIZ_THREAD_ID)); rid=c.fetchone()[0]
        c.execute('INSERT INTO bdsm_quiz_history_tb(question_key) VALUES(%s) ON CONFLICT(question_key) DO UPDATE SET last_used_at=NOW(),uses=bdsm_quiz_history_tb.uses+1',(q['id'],)); conn.commit(); return rid
    except Exception: conn.rollback(); raise
    finally: _put_connection(conn)

async def quiz_tick(context: ContextTypes.DEFAULT_TYPE):
    try:
        if not auto_can_post('quiz'): return
        q=_pick(); rid=_create(q)
        if q['type']=='open':
            await context.bot.send_message(QUIZ_CHAT_ID,f"🖤 QUIZ BDSM · Ronda abierta\n\n{q['q']}\n\n💬 Sin respuesta única ni premio.\n\n#QuizPiBot",message_thread_id=QUIZ_THREAD_ID); return
        opts=list(dict.fromkeys(q['options'])); random.shuffle(opts); context.application.bot_data.setdefault('bq_options',{})[rid]=opts
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute('UPDATE bdsm_quiz_rounds_tb SET options_json=%s::jsonb WHERE round_id=%s',(json.dumps(opts,ensure_ascii=False),rid)); conn.commit()
        finally:_put_connection(conn)
        kb=_quiz_keyboard(rid,opts)
        heading="🧩 QUIZ EMOJI BDSM" if q.get('format')=='emoji' else "🖤 QUIZ BDSM"
        await context.bot.send_message(QUIZ_CHAT_ID,f"{heading} · 1 intento por persona\n\n{q['q']}\n\n🏆 Primera correcta: {QUIZ_REWARD:,} PiPesos\n⭐ La victoria también suma XP de temporada.\n⏳ Tienes hasta 30 minutos.\n\n#QuizPiBot",message_thread_id=QUIZ_THREAD_ID,reply_markup=kb)
    except Exception as e: print('[QUIZ]',e)

async def quiz_callback(update: Update,context: ContextTypes.DEFAULT_TYPE):
    cq=update.callback_query
    try: _,rs,is_=cq.data.split(':'); rid=int(rs); idx=int(is_)
    except Exception: await cq.answer('Ronda inválida.',show_alert=True); return
    if cq.message.chat_id!=QUIZ_CHAT_ID or cq.message.message_thread_id!=QUIZ_THREAD_ID: await cq.answer('Esta ronda pertenece a General.',show_alert=True); return
    opts=context.application.bot_data.get('bq_options',{}).get(rid)
    uid=cq.from_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT status,answer_text,options_json,created_at,eliminated_json,explanation_text FROM bdsm_quiz_rounds_tb WHERE round_id=%s FOR UPDATE",(rid,)); row=c.fetchone()
        if not row or row[0]!='open': conn.rollback(); await cq.answer('La ronda ya terminó.',show_alert=True); return
        if (datetime.now(timezone.utc)-row[3]).total_seconds()>1800:
            c.execute("UPDATE bdsm_quiz_rounds_tb SET status='expired',closed_at=NOW() WHERE round_id=%s AND status='open'",(rid,)); conn.commit(); await cq.answer('Esta ronda cerró después de 30 minutos.',show_alert=True); return
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
        c.execute("UPDATE bdsm_quiz_rounds_tb SET status='won',winner_id=%s,closed_at=NOW() WHERE round_id=%s AND status='open'",(uid,rid)); reward=vinculo_reward_amount(uid,QUIZ_REWARD,c); c.execute('UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s',(reward,uid))
        if c.rowcount!=1: conn.rollback(); await cq.answer('No pude acreditar el premio.',show_alert=True); return
        conn.commit()
    except Exception as e: conn.rollback(); print('[QUIZ callback]',e); await cq.answer('Error de base de datos.',show_alert=True); return
    finally: _put_connection(conn)
    context.application.bot_data.get('bq_options',{}).pop(rid,None); add_weekly_points(uid,quiz=1)
    try:
        from handlers.season_pass import grant_season_xp
        sx=grant_season_xp(uid,25,'quiz')
    except Exception:
        sx=None
    await cq.answer('🏆 ¡Correcto!',show_alert=True)
    xp_line=f"\n⭐ +{sx['granted']} XP de temporada" if sx and sx.get('granted',0) else ("\n⭐ XP de quiz: límite diario alcanzado" if sx else "")
    level_line=f"\n🎉 Nivel {sx['new_level']} del pase" if sx and sx.get('new_level',1)>sx.get('old_level',1) else ""
    try: await cq.edit_message_text(f"🏆 <b>¡CORRECTO!</b>\n\n{cq.from_user.mention_html()} ganó <b>{QUIZ_REWARD:,} PiPesos</b> y suma <b>1 punto</b>.{xp_line}{level_line}\nRespuesta: <b>{chosen}</b>\n\n💡 <b>¿Por qué?</b>\n{row[5] or ('La respuesta correcta es '+str(chosen)+'.')}\n\n#QuizPiBot",parse_mode='HTML',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🏆 Ver ranking semanal',callback_data='cr:rank')]]))
    except Exception: pass

async def quiz_manual(update: Update,context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(f'🧠 Quiz automático: General, tema {QUIZ_THREAD_ID}. Banco: {len(QUIZ_BANK):,} rondas. Sale de forma coordinada para no chocar con Diccionario, Información ni la Pregunta del Día.')

async def quiz_now(update: Update,context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text('🧠 Enviando ronda de prueba a General…'); await quiz_tick(context)
