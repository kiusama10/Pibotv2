"""Non-explicit BDSM glossary capsule every 75 minutes."""
from __future__ import annotations
import random
from telegram.ext import ContextTypes
from src.utils.seasonal import seasonalize

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
_last=None
async def dictionary_tick(context:ContextTypes.DEFAULT_TYPE):
    global _last
    choices=[x for x in TERMS if x[0]!=_last] or TERMS
    term,definition=random.choice(choices); _last=term
    await context.bot.send_message(chat_id=CHAT_ID,message_thread_id=THREAD_ID,text=seasonalize(f"📖 DICCIONARIO BDSM · {term}\n\n{definition}\n\n💬 Una misma palabra puede tener matices distintos entre personas; cuando importe, conviene aclarar qué significa para cada quien.",compact=True))
