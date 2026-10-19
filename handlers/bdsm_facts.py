"""Educational BDSM facts for PiBot.

This module is intentionally informational and non-explicit. Facts rotate in the
General topic every 2 hours. Presentation is seasonal; content and economy are
independent. The bank uses verified/established core facts plus many presentation
variants so the bot does not repeat the same wording constantly.
"""
from __future__ import annotations

import random
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection
from handlers.community_activities import auto_can_post
from src.utils.seasonal import current_season

FACT_CHAT_ID = -1003290179217
FACT_THREAD_ID = 435
FACT_INTERVAL_SECONDS = 7200  # 2 hours

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
("consentimiento", "El consentimiento puede incluir condiciones concretas: persona, lugar, duración, intensidad o forma de comunicación. Cambiar una condición puede requerir volver a preguntar."),
("consentimiento", "Consentir por entusiasmo propio no es lo mismo que aceptar para evitar una discusión, una culpa o una consecuencia social."),
("consentimiento", "Pedir confirmación cuando algo cambia no 'rompe el ambiente'; ayuda a que el acuerdo siga correspondiendo a lo que las personas quieren en ese momento."),
("consentimiento", "El consentimiento para una dinámica no se transfiere automáticamente a una tercera persona, incluso si existe confianza entre todas."),
("consentimiento", "Poder decir que no sin tener que justificarlo es una parte importante de que una decisión siga siendo libre."),
("limites", "Un límite puede ser permanente, temporal o depender del contexto. Hablar de condiciones concretas evita convertirlos en etiquetas rígidas."),
("limites", "Descubrir un límite durante una experiencia no convierte a nadie en 'inconsistente'; a veces solo se conoce una reacción cuando la situación ocurre."),
("limites", "Respetar un límite también significa no convertirlo en tema de bromas, presión o negociación insistente después de que fue expresado."),
("negociacion", "Una negociación útil no se limita a 'sí o no': también puede incluir intensidad, duración, señales, privacidad, después de la dinámica y cómo detenerse."),
("negociacion", "Cuando dos personas usan la misma palabra de forma distinta, definirla con ejemplos concretos suele ser más útil que discutir quién tiene la definición correcta."),
("negociacion", "Renegociar fuera de un momento intenso puede facilitar decisiones más claras, especialmente cuando se está pensando en ampliar límites o responsabilidades."),
("negociacion", "Los acuerdos pueden incluir lo que NO forma parte de la dinámica. Definir esos espacios protege la vida cotidiana y reduce suposiciones."),
("roles", "Ser Dominante no obliga a disfrutar todas las formas de control, igual que ser sumiso no obliga a disfrutar todas las formas de entrega."),
("roles", "Un Switch no necesita repartir sus preferencias 50/50. Puede inclinarse mucho hacia un rol y seguir disfrutando el otro en determinadas condiciones."),
("roles", "Top y Dominante pueden coincidir, pero no son sinónimos: una persona puede realizar una acción sin asumir autoridad relacional."),
("roles", "Bottom y sumiso pueden coincidir, pero una persona puede recibir una práctica sin ceder poder fuera de ese momento acordado."),
("roles", "Las etiquetas pueden cambiar con la experiencia. Ajustar cómo una persona se describe no invalida cómo se identificaba antes."),
("dynamics", "La intensidad de una dinámica no determina su calidad. Una estructura sencilla y bien comunicada puede ser más satisfactoria que una muy compleja."),
("dynamics", "Una relación puede tener intercambio de poder solo en ciertos momentos, tareas o espacios; no tiene que abarcar toda la vida para ser válida."),
("dynamics", "Una dinámica puede ser seria y aun incluir humor. Reírse no elimina necesariamente el rol si todas las personas entienden el contexto."),
("dynamics", "La autoridad consensuada tiene alcance. Fuera de lo acordado, una etiqueta de rol no crea derechos sobre decisiones personales de otra persona."),
("aftercare", "Preguntar qué NO ayuda también puede ser parte del aftercare. Algunas formas de cercanía, conversación o contacto pueden no ser útiles para todo el mundo."),
("aftercare", "El autocuidado posterior puede complementar el aftercare compartido, especialmente cuando las personas no pueden permanecer juntas después de una dinámica."),
("aftercare", "El aftercare no tiene que parecer romántico. Puede ser práctico, breve, silencioso o centrado en necesidades físicas y emocionales concretas."),
("aftercare", "Un seguimiento al día siguiente puede revelar necesidades que no aparecieron inmediatamente después de una experiencia."),
("seguridad", "Tener una herramienta de emergencia sirve poco si nadie sabe dónde está o cómo usarla. La preparación también incluye accesibilidad y práctica razonable."),
("seguridad", "Una técnica aprendida en video no equivale automáticamente a competencia práctica. Algunas habilidades requieren supervisión, práctica gradual o formación específica."),
("seguridad", "La ausencia de dolor no garantiza por sí sola que todo esté bien. Cambios de color, sensibilidad, movilidad o estado mental también pueden requerir atención."),
("seguridad", "Cuando una persona no puede usar una palabra de seguridad, una señal no verbal acordada puede ofrecer una alternativa clara para comunicar pausa o detención."),
("seguridad", "Un plan de emergencia debería ser suficientemente simple para recordarse bajo estrés; demasiadas reglas difíciles de ejecutar pueden dejar de ser útiles."),
("privacidad", "Guardar una foto privada y compartirla son decisiones distintas. El permiso para una no implica permiso para la otra."),
("privacidad", "Las capturas de pantalla también pueden revelar información privada. Los acuerdos digitales son parte de la privacidad, no una excepción."),
("privacidad", "Revelar el rol o participación BDSM de otra persona sin permiso puede tener consecuencias sociales, familiares o laborales; la discreción debe hablarse."),
("privacidad", "Borrar contenido cuando termina una relación o dinámica puede formar parte de acuerdos de privacidad previamente negociados."),
("comunicacion", "Decir 'no entendí' puede ser una buena práctica de comunicación. Fingir claridad para evitar incomodidad suele aumentar los malentendidos."),
("comunicacion", "El feedback útil puede incluir lo que sí funcionó, no solo lo que salió mal. Eso ayuda a repetir conductas positivas y ajustar las demás."),
("comunicacion", "Preguntar '¿quieres que te escuche o quieres una solución?' puede evitar asumir qué tipo de apoyo necesita la otra persona."),
("comunicacion", "Un desacuerdo sobre una práctica no tiene que convertirse en un juicio sobre el rol o la identidad de la otra persona."),
("comunidad", "Una buena reputación puede ser información útil, pero no reemplaza comprobar compatibilidad, negociar y observar cómo una persona responde a límites concretos."),
("comunidad", "Una comunidad sana permite hacer preguntas básicas sin convertir la falta de experiencia en motivo de vergüenza."),
("comunidad", "Corregir información equivocada es más útil cuando se distingue entre hechos de seguridad, costumbres comunitarias y preferencias personales."),
("comunidad", "El hecho de que una práctica sea popular en un grupo no crea obligación de probarla. La presión social también puede afectar decisiones."),
("comunidad", "Las normas de un grupo sirven para ese espacio; no sustituyen los acuerdos privados entre personas ni crean autoridad fuera de él."),
("mitos", "Más experiencia no significa necesitar menos comunicación. Conocer muchas prácticas puede incluso aumentar la cantidad de detalles que vale la pena negociar."),
("mitos", "Una persona puede ser firme y seguir cuidando. Dominación y empatía no son conceptos opuestos."),
("mitos", "Una persona puede ser sumisa y tener límites muy estrictos. Ceder poder dentro de acuerdos no elimina criterio ni autonomía."),
("mitos", "Cambiar una safeword, una señal o un acuerdo no significa que la dinámica haya fallado; puede significar que las personas aprendieron algo nuevo."),
("mitos", "No toda relación BDSM necesita títulos, contratos, collares o protocolos. Son herramientas o símbolos opcionales, no requisitos universales."),
("aprendizaje", "Aprender a recibir un 'no' con calma es una habilidad tan importante como aprender a pedir un 'sí'."),
("aprendizaje", "Reconocer 'esto no lo sé hacer' puede ser una señal de responsabilidad, no de poca experiencia."),
("aprendizaje", "La práctica gradual permite evaluar cómo responde cada persona y ajustar acuerdos antes de aumentar complejidad o intensidad."),
("aprendizaje", "Separar preferencia personal de regla universal ayuda a enseñar BDSM sin convertir el estilo propio en obligación para los demás."),
("lenguaje", "Cuando una palabra tiene varias definiciones comunitarias, describir la conducta concreta suele ser más claro que depender solo de la etiqueta."),
("lenguaje", "'Protocolo alto' y 'protocolo bajo' suelen describir grados de formalidad acordada; ninguno es automáticamente mejor que el otro."),
("lenguaje", "'Scene' puede referirse a una sesión o contexto acordado, mientras 'the scene' también puede usarse informalmente para hablar de la comunidad BDSM."),
("lenguaje", "'Collar' puede ser un objeto, un símbolo o parte de un acuerdo; su significado depende de quienes lo usan y no existe una interpretación obligatoria."),
]

CORE_FACTS += [
    ('consentimiento', 'Un sí puede depender de condiciones concretas. Si cambia la persona, el lugar, la intensidad o el propósito, puede ser necesario volver a preguntar.'),
    ('consentimiento', 'Retirar consentimiento no requiere demostrar que la actividad era peligrosa; basta con que la persona ya no quiera continuar.'),
    ('consentimiento', 'Tener curiosidad por una práctica no equivale a consentirla. La curiosidad puede quedarse en conversación, investigación o fantasía.'),
    ('consentimiento', 'Un acuerdo anterior puede necesitar confirmación después de una pausa larga o de cambios importantes en la relación o contexto.'),
    ('consentimiento', 'El silencio puede tener muchas causas; cuando la claridad importa, una respuesta afirmativa o una señal previamente acordada es más útil que asumir.'),
    ('consentimiento', 'Un “sí, pero solo si…” sigue siendo un consentimiento condicionado. Ignorar la condición cambia el acuerdo.'),
    ('limites', 'Los límites también pueden referirse a lenguaje, privacidad, lugares, duración o exposición pública, no solo a prácticas físicas.'),
    ('limites', 'Un límite contextual puede ser distinto con otra persona o en otro momento sin que eso vuelva incoherente a quien lo establece.'),
    ('limites', 'Pedir detalles para comprender un límite puede ser válido, pero respetarlo no debería depender de que la otra persona entregue una explicación íntima.'),
    ('limites', 'Un límite que cambia merece una conversación nueva; no debe usarse una versión antigua del acuerdo para invalidar la decisión actual.'),
    ('negociacion', 'Acordar cómo terminar una dinámica puede ser tan importante como acordar cómo empezarla.'),
    ('negociacion', 'Hablar de duración aproximada ayuda a evitar que una actividad se extienda más de lo que alguien esperaba.'),
    ('negociacion', 'Definir qué espacios quedan fuera del rol puede reducir conflictos cuando una dinámica también existe en la vida cotidiana.'),
    ('negociacion', 'La negociación puede incluir qué hacer si alguien necesita tiempo para decidir; una respuesta inmediata no siempre es necesaria.'),
    ('negociacion', 'Una checklist puede ayudar a recordar temas, pero marcar casillas no reemplaza una conversación real sobre significados y condiciones.'),
    ('comunicacion', 'Confirmar lo entendido con tus propias palabras puede detectar malentendidos antes de que se conviertan en problemas.'),
    ('comunicacion', 'Un feedback concreto suele ser más útil que “todo estuvo mal” o “todo estuvo bien”, porque permite saber qué repetir o cambiar.'),
    ('comunicacion', 'Recibir feedback sin castigar emocionalmente a quien lo da facilita que los problemas se hablen antes de crecer.'),
    ('comunicacion', 'No saber responder todavía también es información válida. Pedir tiempo para pensar puede ser una forma responsable de decidir.'),
    ('comunicacion', 'Una conversación seria puede requerir salir temporalmente del rol para que todas las personas hablen desde un plano claro y cotidiano.'),
    ('aftercare', 'El aftercare puede planearse antes y aun necesitar cambios después, porque las necesidades reales no siempre se predicen con precisión.'),
    ('aftercare', 'Una persona puede necesitar aftercare práctico, otra emocional y otra simplemente espacio; ninguna forma es universal.'),
    ('aftercare', 'La descompresión es el periodo de transición después de algo intenso y puede ser útil incluso cuando nadie experimenta drop.'),
    ('aftercare', 'El seguimiento diferido permite detectar cansancio, molestias o emociones que aparecieron horas después de la actividad.'),
    ('aftercare', 'El cuidado posterior puede ser mutuo: asumir un rol dominante no impide necesitar descanso, conversación o regulación emocional.'),
    ('seguridad', 'La fatiga puede reducir coordinación y atención. Cambiar o cancelar un plan por cansancio puede ser una decisión de seguridad.'),
    ('seguridad', 'Una herramienta de seguridad debería estar al alcance y no enterrada en una mochila o habitación diferente cuando podría necesitarse rápido.'),
    ('seguridad', 'Practicar una salida de emergencia en condiciones tranquilas puede hacer más fácil recordarla cuando existe estrés real.'),
    ('seguridad', 'Observar cambios de comportamiento o movilidad complementa las señales verbales; ninguna observación sustituye preguntar cuando hay duda.'),
    ('seguridad', 'Conocer el estado normal de una persona antes de empezar ayuda a detectar cambios inesperados durante una actividad.'),
    ('seguridad', 'Reducir intensidad es una opción de seguridad distinta de detener por completo; el sistema acordado debería dejar claro cuándo usar cada una.'),
    ('seguridad', 'Un plan de contingencia responde a la pregunta “¿qué hacemos si el plan principal deja de ser seguro o posible?”.'),
    ('seguridad', 'Aprender una técnica también incluye aprender sus errores comunes, señales de alarma y formas de detenerla.'),
    ('seguridad', 'Una práctica de mayor riesgo no se vuelve segura solo porque ambas personas la desean; el deseo y la gestión del riesgo son asuntos diferentes.'),
    ('riesgo', 'Los riesgos pueden ser físicos, emocionales, sociales y digitales. Una negociación completa puede necesitar considerar más de una categoría.'),
    ('riesgo', 'Dos personas pueden ser compatibles en gustos y no serlo en tolerancia al riesgo; reconocerlo evita presionar acuerdos.'),
    ('riesgo', 'Una reputación positiva reduce incertidumbre, pero nunca convierte una actividad en riesgo cero.'),
    ('riesgo', 'Un “mapa de riesgos” informal puede ser simplemente hablar de qué puede salir mal, cómo detectarlo y qué harían en ese caso.'),
    ('riesgo', 'La experiencia disminuye algunos errores, pero también puede crear exceso de confianza; revisar procedimientos sigue siendo útil.'),
    ('privacidad', 'Autorizar una foto no autoriza automáticamente guardarla indefinidamente, reenviarla o publicarla.'),
    ('privacidad', 'Anonimizar un relato implica retirar detalles que permitan identificar a las personas, no solo quitar sus nombres.'),
    ('privacidad', 'Los acuerdos de privacidad pueden incluir qué ocurre con archivos si la relación o dinámica termina.'),
    ('privacidad', 'La discreción también incluye evitar mencionar roles o relaciones kink frente a personas que no tienen permiso para conocerlos.'),
    ('privacidad', 'Compartir una captura puede revelar nombres, fotos, horarios o datos indirectos; conviene revisar más que el texto principal.'),
    ('roles', 'La autoridad consensuada tiene límites de alcance; un título no otorga autoridad sobre trabajo, dinero, amistades u otras áreas si no fueron acordadas.'),
    ('roles', 'Una persona dominante puede pedir una pausa, cambiar de opinión o admitir que no sabe algo sin dejar de ser dominante.'),
    ('roles', 'Una persona sumisa puede negociar con firmeza y seguir siendo sumisa; la capacidad de poner límites no contradice el rol.'),
    ('roles', 'Un Switch puede expresar un rol distinto según la persona, el contexto o el momento sin que eso implique indecisión.'),
    ('roles', 'Entrar y salir del rol de manera explícita puede ayudar a separar una dinámica de conflictos o decisiones cotidianas.'),
    ('roles', 'Los rituales tienen significado porque las personas se lo dan; repetirlos sin deseo o acuerdo puede vaciarlos de sentido.'),
    ('dynamics', 'Una dinámica 24/7 necesita hablar de excepciones y espacios fuera de rol precisamente porque la vida cotidiana tiene contextos muy distintos.'),
    ('dynamics', 'Más protocolo no significa automáticamente más compromiso; la estructura útil es la que las personas realmente desean y pueden sostener.'),
    ('dynamics', 'La compatibilidad también incluye ritmo: dos personas pueden querer lo mismo pero no querer avanzar a la misma velocidad.'),
    ('dynamics', 'Una dinámica puede crecer en confianza, comunicación o significado sin aumentar intensidad física.'),
    ('dynamics', 'Cambiar una regla que dejó de funcionar puede fortalecer una dinámica; conservarla solo por tradición no garantiza estabilidad.'),
    ('comunidad', 'Una referencia es una pieza de información, no una certificación absoluta. Conviene considerar contexto y hablar directamente con la persona.'),
    ('comunidad', 'Las reglas de un evento protegen ese espacio; incumplirlas no puede justificarse diciendo que una dinámica privada permite otra cosa.'),
    ('comunidad', 'Una comunidad útil diferencia entre corregir información peligrosa y convertir preferencias personales en normas universales.'),
    ('comunidad', 'La antigüedad en una comunidad no vuelve a alguien inmune a preguntas, límites o rendición de cuentas.'),
    ('comunidad', 'La forma en que alguien recibe un no o una crítica puede ser tan informativa como la forma en que se presenta al inicio.'),
    ('comunidad', 'Permitir decir “no sé” reduce la presión por aparentar experiencia y puede favorecer decisiones más seguras.'),
    ('aprendizaje', 'Practicar un procedimiento sin intensidad real puede ayudar a aprender pasos, comunicación y salida antes de añadir dificultad.'),
    ('aprendizaje', 'La competencia técnica y la competencia relacional son diferentes: saber hacer algo no garantiza saber negociar o recibir feedback.'),
    ('aprendizaje', 'Supervisión y práctica gradual son especialmente valiosas cuando un error puede tener consecuencias rápidas o difíciles de revertir.'),
    ('aprendizaje', 'La autoevaluación incluye reconocer cuándo el propio cansancio, emoción o experiencia no son adecuados para una actividad planeada.'),
    ('aprendizaje', 'Aprender de un error exige algo más que disculparse: también implica identificar qué cambiar para reducir la probabilidad de repetirlo.'),
    ('mitos', '“Si confías en mí no necesitas safeword” es una falsa oposición: la confianza y las herramientas de comunicación pueden coexistir.'),
    ('mitos', '“Un Dominante siempre sabe qué hacer” es un mito. Reconocer límites de conocimiento puede ser una conducta responsable.'),
    ('mitos', '“Una persona sumisa debe aceptar correcciones en cualquier momento” confunde el rol con autoridad ilimitada; el alcance se acuerda.'),
    ('mitos', '“Un contrato hace irrevocable el consentimiento” es falso. Ningún documento convierte un sí pasado en obligación permanente.'),
    ('mitos', '“Si alguien ya hizo una práctica antes, volverá a quererla” es falso; cada ocasión requiere consentimiento actual.'),
    ('lenguaje', '“Safecall” suele referirse a una comprobación acordada con una persona externa para aumentar seguridad durante un encuentro.'),
    ('lenguaje', '“Aftercare mutuo” recuerda que las necesidades posteriores no pertenecen exclusivamente a un rol.'),
    ('lenguaje', '“Espacio fuera de rol” describe momentos donde la dinámica de autoridad queda expresamente en pausa.'),
    ('lenguaje', '“Cierre de escena” puede ser una señal, frase o ritual que marque claramente que la escena terminó.'),
    ('lenguaje', '“Consentimiento condicionado” significa que el sí depende de condiciones específicas y deja de aplicar si esas condiciones cambian.'),
    ('confianza', 'La confianza no debería medirse por cuánto riesgo acepta una persona, sino también por qué tan libre se siente de decir no.'),
    ('confianza', 'La consistencia entre lo que alguien promete y lo que hace construye confianza más lentamente, pero de forma más verificable.'),
    ('confianza', 'Acelerar la intimidad no acelera automáticamente la confianza; compartir mucho muy rápido puede crear una sensación de cercanía distinta de la seguridad real.'),
    ('confianza', 'Una persona confiable puede aceptar que otra necesite verificar información o pedir referencias sin tomarlo como insulto.'),
    ('confianza', 'La reparación después de un error depende de conducta futura, no solo de palabras dichas en el momento.'),
    ('comunicacion', 'Preguntar si la otra persona quiere ser escuchada, recibir una solución o simplemente tener espacio puede evitar respuestas que no necesita.'),
]

INTRO = [
    "¿Sabías que…", "Dato BDSM del día:", "Un minuto de cultura BDSM:", "Dato para guardar:",
    "Pequeña cápsula BDSM:", "Entre tanta charla, un dato útil:", "PiBot encontró algo que vale la pena saber:",
    "Dato rápido, pero importante:", "Hoy aprendemos algo:", "Cultura BDSM en pocas palabras:",
    "Una cosa que a veces se confunde:", "Para nuevos y veteranos:", "Dato de comunidad:",
    "PiBot educativo apareció otra vez:", "Antes de seguir con el caos del grupo:", "Dato para conversar:",
    "Algo interesante del BDSM:", "Cápsula de historia y cultura:", "Recordatorio útil:", "¿Lo conocías?",
    "Archivo PiBot:", "Dato para el debate:", "Dos minutos de cultura:", "Concepto útil:",
    "Apunte de comunidad:", "Para aprender algo nuevo:", "Una idea para conversar:", "Dato sin mitos:",
    "Biblioteca BDSM:", "PiBot comparte:", "Punto importante:", "Cultura y consentimiento:",
    "Nota de seguridad:", "Dato de roles y dinámicas:", "Aprendizaje del día:", "Pequeño recordatorio de comunidad:",
    "Entre roles y acuerdos:", "Dato para tener presente:", "Un concepto que conviene conocer:", "Cápsula educativa PiBot:"
]

OUTRO = [
    "💭 Puede servir para abrir conversación en el grupo.",
    "🧠 Aprender también es revisar lo que creíamos saber.",
    "🤝 Los acuerdos concretos siempre se hablan entre las personas involucradas.",
    "📖 Una etiqueta orienta; la comunicación define la dinámica real.",
    "🖤 Información primero, consentimiento siempre.",
    "🔎 Si una definición importa en una dinámica, conviene aclarar qué significa para cada persona.",
    "💬 Preguntar con respeto suele ser mejor que asumir.",
    "🧩 No todas las dinámicas funcionan igual para todas las personas.",
    "🛡️ Seguridad y consentimiento forman parte de la práctica, no son un añadido.",
    "✨ Conocer términos ayuda; conocer los límites de la otra persona ayuda todavía más.",
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
        c.execute("SELECT fact_key FROM bdsm_fact_history_tb ORDER BY last_used_at DESC LIMIT %s", (min(120, max(1, len(CORE_FACTS)-12)),))
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
    return len(CORE_FACTS) * len(INTRO) * len(OUTRO)


def render_fact(fact) -> str:
    category, body = fact
    season = current_season()
    icon = random.choice(SEASON_OPEN.get(season, SEASON_OPEN["normal"]))
    intro = random.choice(INTRO)
    outro = random.choice(OUTRO)
    return f"{icon} <b>{intro}</b>\n\n{body}\n\n{outro}\n\n📚 <i>Tema: {category.title()} · Información educativa.</i>\n\n#InfoPiBot"


async def bdsm_fact_tick(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if not auto_can_post('fact'): return
        _, fact = _pick_fact()
        await context.bot.send_message(
            chat_id=FACT_CHAT_ID,
            message_thread_id=FACT_THREAD_ID,
            text=render_fact(fact),
            parse_mode="HTML",
        )
    except Exception as e:
        print(f"[BDSM FACT] {type(e).__name__}: {e}")
