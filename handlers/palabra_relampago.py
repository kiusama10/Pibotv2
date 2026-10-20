"""Palabra Relámpago BDSM: reto visual horario en el tema Juegos.

Aislado del resto de PiBot. Genera las imágenes localmente con Pillow, sin IA ni APIs.
"""
from __future__ import annotations

import io
import random
import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg2
from PIL import Image, ImageDraw, ImageFont
from telegram import Update
from telegram.ext import ContextTypes

from src.config import DATABASE_URL, COMUNIDADES, obtener_temas_por_comunidad
from src.database.database import dar_recompensa, is_botmaster
from src.utils.display_name import visible_user

REWARD = 1500
TZ = ZoneInfo("America/Mexico_City")
_active: dict[tuple[int, int | None], dict] = {}

# Banco BDSM/seguridad. La imagen nunca incluye la respuesta en el caption.
WORDS = [
    "aftercare","consentimiento","safeword","negociación","límites","confianza","comunicación","respeto",
    "dominación","sumisión","switch","dominante","sumiso","sumisa","protocolo","dinámica","sesión","escena",
    "subspace","domspace","drop","subdrop","domdrop","RACK","SSC","PRICK","CNC","TPE","D/s","M/s","BDSM",
    "bondage","shibari","kinbaku","cuerda","arnés","nudo","suspensión","restricción","esposas","collar",
    "impacto","spanking","azote","pala","fusta","flogger","caning","disciplina","sensación","privación",
    "sensorial","vendas","temperatura","cera","hielo","plumas","pinzas","mordaza","postura","órdenes",
    "servicio","entrega","control","poder","responsabilidad","cuidado","empatía","acuerdo","reversible",
    "informado","entusiasta","continuo","capacidad","riesgo","seguridad","emergencia","señales","semáforo",
    "verde","amarillo","rojo","pausa","detener","revisar","hidratar","descanso","primeros auxilios","tijeras",
    "mosquetón","anclaje","circulación","nervios","entumecimiento","presión","respiración","monitoreo","check-in",
    "debriefing","límites duros","límites blandos","preferencias","desencadenante","accesibilidad","privacidad",
    "discreción","confidencialidad","vetting","compatibilidad","expectativas","fantasía","realidad","intensidad",
    "ritual","entrenamiento","recompensa","castigo","corrección","obediencia","adoración","petplay","brat",
    "brat tamer","service sub","primal","handler","owner","master","mistress","sir","ma'am","little","caregiver",
    "mommy","daddy","slave","bottom","top","rope bunny","rigger","sadismo","masoquismo","sadomasoquismo",
    "fetiche","kink","vainilla","edgeplay","breathplay","wax play","needle play","knife play","electroplay",
    "roleplay","humillación","degradación","alabanza","praise kink","orgasm control","edging","tease and denial",
    "chastity","exhibicionismo","voyeurismo","latex","cuero","uniforme","mascota","jaula","correa","bozal",
    "contrato","símbolo","pertenencia","collaring","protección","mentor","comunidad","educación","experiencia",
    "autocuidado","recuperación","emociones","vulnerabilidad","intimidad","conexión","presencia","atención",
    "escucha","preguntar","confirmar","renegociar","retirar consentimiento","planificar","evaluar riesgo","reducción de daño",
    "higiene","desinfección","materiales","equipo","inspección","mantenimiento","posición segura","liberación rápida",
    "comunicación no verbal","gesto seguro","objeto seguro","doble toque","palabra de seguridad","consentimiento activo",
    "consentimiento explícito","consentimiento condicionado","consentimiento previo","aftercare físico","aftercare emocional",
    "negociación previa","límites temporales","intensidad gradual","registro emocional","revisión posterior","responsabilidad compartida",
    # Ampliación del banco: más conceptos sin tocar la lógica del minijuego.
    'safecall','lista sí no quizá','lista sí no tal vez','negociación continua','renegociación','consentimiento específico',
    'consentimiento contextual','consentimiento afirmativo','consentimiento sobrio','consentimiento presente','consentimiento renovable','consentimiento informado de riesgo',
    'acuerdo previo','acuerdo posterior','acuerdo de escena','acuerdo de privacidad','acuerdo de señales','acuerdo de intensidad',
    'acuerdo de tiempo','acuerdo de salida','acuerdo de contacto','check-in emocional','check-in físico','check-out',
    'señal no verbal','señal de pausa','señal de alto','gesto de seguridad','doble apretón','objeto de seguridad',
    'palabra neutra','palabra alternativa','comunicación clara','comunicación directa','comunicación honesta','escucha activa',
    'validación','pregunta abierta','confirmación verbal','confirmación no verbal','revisión de límites','mapa de límites',
    'preferencia fuerte','preferencia suave','límite situacional','límite negociable','límite no negociable','expectativa realista',
    'expectativa compartida','compatibilidad de límites','compatibilidad de dinámica','compatibilidad de riesgo','autonomía','agencia',
    'decisión voluntaria','derecho a parar','derecho a cambiar de opinión','retirada de consentimiento','pausa segura','salida segura',
    'plan de salida','plan de contingencia','contacto de emergencia','persona de confianza','ubicación compartida','hora de regreso',
    'verificación posterior','conciencia de riesgo','evaluación de riesgos','gestión de riesgos','riesgo aceptado','riesgo residual',
    'reducción de riesgos','reducción de daños','plan de emergencia','botiquín','guantes','barrera',
    'limpieza de equipo','limpieza de juguetes','desinfección de superficie','contaminación cruzada','material poroso','material no poroso',
    'revisión de equipo','desgaste de equipo','punto de anclaje','anclaje redundante','carga dinámica','carga estática',
    'carga lateral','liberación de emergencia','corte de emergencia','tijeras de seguridad','circulación sanguínea','compresión nerviosa',
    'presión nerviosa','hormigueo','adormecimiento','cambio de color','temperatura de la piel','dolor agudo',
    'dolor sordo','mareo','náusea','desorientación','fatiga','agotamiento',
    'hidratación','electrolitos','comida ligera','sobriedad','capacidad de decisión','medicación',
    'alergia','sensibilidad de piel','lesión previa','movilidad reducida','rango de movimiento','postura neutral',
    'mecánica corporal','apoyo cervical','respiración libre','vía aérea','circulación distal','pulso distal',
    'prueba de sensibilidad','control de temperatura','sobrecalentamiento','hipotermia','tiempo de exposición','intensidad progresiva',
    'rope top','rope bottom','rope switch','tying partner','bondage decorativo','bondage funcional',
    'bondage de suelo','bondage parcial','predicament bondage','floorwork','suspensión parcial','suspensión completa',
    'transición de cuerda','arnés de pecho','arnés de cadera','arnés corporal','single column tie','double column tie',
    'single column','double column','fricción de cuerda','tensión de cuerda','dirección de carga','línea de carga',
    'punto de suspensión','línea de suspensión','línea principal','línea de seguridad','mosquetón con seguro','mosquetón ovalado',
    'anilla','sling','cinta de anclaje','bambú','barra separadora','spread bar',
    'cuffs','muñequeras','tobilleras','restricción de muñecas','restricción de tobillos','liberación de manos',
    'espacio de dos dedos','revisión de circulación','posición de hombros','nudo de liberación rápida','nudo de columna','nudo plano',
    "lark's head",'somerville bowline','cinch','hitch','friction','impact play',
    'sensation play','sensory play','temperature play','ice play','spanking a mano','paddle',
    'cane','crop','flogging','slapper','strap','tawse',
    'punto de impacto','zona segura','zona de riesgo','calentamiento corporal','warm-up','ramp-up',
    'ritmo de impacto','cadencia','intensidad de impacto','feedback corporal','lectura corporal','sensación punzante',
    'sensación sorda','stingy','thuddy','presión sostenida','textura','cosquillas',
    'cepillo','rueda wartenberg','pluma','hielo envuelto','cera de baja temperatura','prueba de temperatura',
    'distancia de vertido','prueba de piel','pausa de recuperación','power exchange','intercambio de poder','authority transfer',
    'transferencia de autoridad','D slash s','M slash s','24/7','protocolo bajo','protocolo medio',
    'protocolo alto','protocolo de servicio','protocolo de saludo','protocolo de escena','regla negociada','regla temporal',
    'regla revisable','consecuencia acordada','disciplina consensuada','estructura','rutina','ritual de inicio',
    'ritual de cierre','service top','service bottom','service dominant','service submissive','sensual domination',
    'gentle domination','female domination','male domination','financial domination','primal play','pet play',
    'puppy play','kitten play','pony play','age play','caregiver little','bratting',
    'brat taming','handler pet','owner pet','master slave','mistress slave','top bottom',
    'dominant submissive','mentor mentee','protector','guardian','trainer','collar de consideración',
    'collar de entrenamiento','collar de protección','collar formal','collar virtual','collar simbólico','ceremonia de collar',
    'retiro de collar','protocolo de collar','aftercare inmediato','aftercare tardío','aftercare personal','self aftercare',
    'autocuidado posterior','decompresión','regulación emocional','regulación corporal','reconexión','reaseguro',
    'reassurance','contacto tranquilo','espacio personal','silencio','manta','agua',
    'snack','descanso posterior','mensaje posterior','llamada posterior','revisión al día siguiente','seguimiento emocional',
    'seguimiento físico','drop tardío','drop emocional','drop físico','subdrop tardío','domdrop tardío',
    'recuperación gradual','procesamiento emocional','diario de escena','reflexión posterior','munch','play party',
    'dungeon','dungeon monitor','DM de seguridad','monitor de mazmorra','código de conducta','reglas del evento',
    'reglas de casa','etiqueta BDSM','etiqueta de mazmorra','consentimiento en eventos','observador','demostración',
    'taller','práctica supervisada','educación entre pares','mentor responsable','fuente confiable','verificación de información',
    'mito BDSM','educación sexual','comunidad kink','espacio seguro','espacio inclusivo','privacidad comunitaria',
    'discreción comunitaria','foto consensuada','publicación consensuada','permiso de grabación','permiso de fotografía','consentimiento para compartir',
    'anonimato','seudónimo','nombre de escena','outing','doxxing','scene plan',
    'plan de escena','objetivo de escena','duración acordada','temporizador','punto de revisión','secuencia de escena',
    'progresión','transición','desescalada','cierre de escena','interrupción de escena','reanudación',
    'práctica en seco','dry run','ensayo','señal de inicio','señal de cierre','nivel de intensidad',
    'escala de dolor','escala de comodidad','escala del uno al diez','zona verde','zona amarilla','zona roja',
    'semáforo verbal','semáforo no verbal','checklist de escena','checklist de seguridad','equipo de respaldo','herramienta de corte',
    'teléfono cargado','dirección conocida','ruta de salida','acceso a agua','ventilación','kink informed',
    'kink aware','KAP','consensual non-consent','consensual power exchange','edge play','risk profile',
    'risk tolerance','risk awareness','personal responsibility','informed consent','affirmative consent','ongoing consent',
    'enthusiastic consent','revocable consent','mutual consent','informed decision','trust building','earned trust',
    'boundary setting','boundary check','limit check','negotiation checklist','aftercare plan','safety plan',
    'emergency plan','privacy plan','scene agreement','relationship agreement','dynamic agreement','power dynamic',
    'role transition','role fluidity','switching','role negotiation','consent culture','accountability',
    'responsabilidad personal','responsabilidad mutua','cuidado mutuo',
]


def _db():
    return psycopg2.connect(DATABASE_URL)


def ensure_palabra_tables() -> None:
    conn = _db()
    try:
        with conn:
            with conn.cursor() as c:
                c.execute("""CREATE TABLE IF NOT EXISTS palabra_relampago_settings_tb(
                    chat_id BIGINT PRIMARY KEY,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )""")
                c.execute("""CREATE TABLE IF NOT EXISTS palabra_relampago_stats_tb(
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    wins INTEGER NOT NULL DEFAULT 0,
                    pipesos INTEGER NOT NULL DEFAULT 0,
                    best_ms INTEGER,
                    last_win TIMESTAMPTZ,
                    PRIMARY KEY(chat_id,user_id)
                )""")
                c.execute("""CREATE TABLE IF NOT EXISTS palabra_relampago_active_tb(
                    chat_id BIGINT NOT NULL,
                    thread_id BIGINT NOT NULL DEFAULT 0,
                    answer TEXT NOT NULL,
                    shown TEXT NOT NULL,
                    started_at TIMESTAMPTZ NOT NULL,
                    message_id BIGINT NOT NULL,
                    PRIMARY KEY(chat_id,thread_id)
                )""")
    finally:
        conn.close()


def _enabled(chat_id: int) -> bool:
    conn = _db()
    try:
        with conn.cursor() as c:
            c.execute("SELECT enabled FROM palabra_relampago_settings_tb WHERE chat_id=%s", (chat_id,))
            row = c.fetchone()
            return True if row is None else bool(row[0])
    finally:
        conn.close()


def _set_enabled(chat_id: int, enabled: bool) -> None:
    conn = _db()
    try:
        with conn:
            with conn.cursor() as c:
                c.execute("""INSERT INTO palabra_relampago_settings_tb(chat_id,enabled,updated_at)
                    VALUES(%s,%s,NOW()) ON CONFLICT(chat_id) DO UPDATE
                    SET enabled=EXCLUDED.enabled,updated_at=NOW()""", (chat_id, enabled))
    finally:
        conn.close()


def _norm(s: str) -> str:
    s = ''.join(ch for ch in unicodedata.normalize('NFD', s.casefold()) if unicodedata.category(ch) != 'Mn')
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _font(size: int):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _wrap_for_width(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    """Parte por palabras sin cortar conceptos; una palabra larga se conserva completa."""
    words = text.split()
    if not words:
        return [text]
    lines: list[str] = []
    current = words[0]
    for token in words[1:]:
        candidate = f"{current} {token}"
        box = draw.textbbox((0, 0), candidate, font=font, stroke_width=1)
        if box[2] - box[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = token
    lines.append(current)
    return lines


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_height: int):
    """Busca automáticamente tamaño y saltos de línea para que TODO el texto quepa."""
    # Empieza grande para palabras cortas y va bajando solo cuando hace falta.
    for size in range(80, 27, -2):
        font = _font(size)
        lines = _wrap_for_width(draw, text, font, max_width)
        # Preferimos hasta 3 líneas. Con tamaños pequeños permitimos 4 como último recurso.
        if len(lines) > (3 if size >= 34 else 4):
            continue
        rendered = "\n".join(lines)
        spacing = max(6, size // 5)
        box = draw.multiline_textbbox(
            (0, 0), rendered, font=font, spacing=spacing, align="center", stroke_width=1
        )
        width, height = box[2] - box[0], box[3] - box[1]
        if width <= max_width and height <= max_height:
            return font, rendered, width, height, spacing

    # Salvavidas para un término anormalmente largo: nunca permitimos que se salga de la tarjeta.
    font = _font(26)
    lines = _wrap_for_width(draw, text, font, max_width)
    rendered = "\n".join(lines)
    spacing = 6
    box = draw.multiline_textbbox(
        (0, 0), rendered, font=font, spacing=spacing, align="center", stroke_width=1
    )
    return font, rendered, box[2] - box[0], box[3] - box[1], spacing


def _render(word: str) -> io.BytesIO:
    # El texto se autoajusta; los conceptos largos se parten en varias líneas en vez de cortarse.
    palettes = [
        ((18,18,24),(240,240,245)),((31,24,39),(245,235,250)),((18,34,36),(236,247,244)),
        ((38,25,20),(250,239,229)),((24,27,45),(235,239,255)),((42,20,31),(255,236,244)),
        ((20,35,25),(238,249,239)),((36,36,20),(250,249,230)),((25,25,25),(245,245,245)),
        ((45,30,18),(252,242,226)),((17,30,45),(234,244,255)),((40,18,18),(255,235,235)),
        ((22,20,38),(242,238,255)),((20,40,40),(233,252,252)),((43,24,39),(255,238,251)),
        ((30,38,20),(244,252,233)),((38,31,18),(255,248,230)),((19,32,42),(235,247,253)),
    ]
    bg, fg = random.choice(palettes)
    im = Image.new("RGB", (900, 500), bg)
    d = ImageDraw.Draw(im)

    # Decoración procedural: no revela la palabra y produce miles de imágenes distintas.
    for _ in range(22):
        x1, y1 = random.randint(0, 899), random.randint(0, 499)
        x2, y2 = x1 + random.randint(20, 180), y1 + random.randint(10, 120)
        tone = tuple(min(255, max(0, c + random.randint(-12, 22))) for c in bg)
        d.rounded_rectangle((x1,y1,x2,y2), radius=random.randint(5,28), outline=tone, width=random.randint(1,4))

    shown = word.upper().strip()
    # 70 px de margen a cada lado y espacio vertical suficiente para la línea ornamental.
    max_width = 760
    max_height = 285
    f, rendered, tw, th, spacing = _fit_text(d, shown, max_width, max_height)

    # Centrado real: así incluso 2-4 líneas quedan completas y equilibradas.
    x = (900 - tw) // 2
    y = max(60, (500 - th) // 2 - 10)
    d.multiline_text(
        (450, y), rendered, font=f, fill=fg, anchor="ma", align="center",
        spacing=spacing, stroke_width=1, stroke_fill=fg
    )

    # Línea ornamental siempre dentro de la tarjeta y proporcional al texto.
    ly = min(455, y + th + 22)
    line_width = min(760, max(180, tw))
    d.line(((900-line_width)//2, ly, (900+line_width)//2, ly), fill=fg, width=3)

    out = io.BytesIO(); im.save(out, format="PNG", optimize=True); out.seek(0); out.name="palabra_relampago.png"
    return out


def _topic(chat_id: int):
    topics = obtener_temas_por_comunidad(chat_id) or {}
    return topics.get("theme_juegosYcasino")


async def _launch(context: ContextTypes.DEFAULT_TYPE, chat_id: int, *, force: bool=False) -> bool:
    thread = _topic(chat_id)
    if thread is None or (not force and not _enabled(chat_id)):
        return False
    key = (chat_id, thread)
    if key in _active:
        return False
    word = random.choice(WORDS)
    started = datetime.now(TZ)
    photo = _render(word)
    msg = await context.bot.send_photo(
        chat_id=chat_id, message_thread_id=thread, photo=photo,
        caption="⚡ PALABRA RELÁMPAGO BDSM\n\nToca la imagen para revelarla y sé el primero en escribir la palabra o concepto. No necesitas responder ni mencionar la imagen.\n\n💰 Premio: 1,500 PiPesos\n⏱️ Tienes 10 minutos.",
        has_spoiler=True,
    )
    _active[key] = {"answer": _norm(word), "shown": word, "started": started, "message_id": msg.message_id}
    conn = _db()
    try:
        with conn:
            with conn.cursor() as c:
                c.execute("""INSERT INTO palabra_relampago_active_tb(chat_id,thread_id,answer,shown,started_at,message_id)
                    VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(chat_id,thread_id) DO UPDATE SET
                    answer=EXCLUDED.answer,shown=EXCLUDED.shown,started_at=EXCLUDED.started_at,message_id=EXCLUDED.message_id""",
                    (chat_id, int(thread or 0), _norm(word), word, started, msg.message_id))
    finally:
        conn.close()
    context.job_queue.run_once(_expire, 600, data={"chat_id":chat_id,"thread":thread,"message_id":msg.message_id}, name=f"palabra:{chat_id}:{msg.message_id}")
    return True


async def _expire(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    key = (data["chat_id"], data["thread"])
    game = _active.get(key)
    if not game or game["message_id"] != data["message_id"]:
        return
    _active.pop(key, None)
    conn = _db()
    try:
        with conn:
            with conn.cursor() as c:
                c.execute("DELETE FROM palabra_relampago_active_tb WHERE chat_id=%s AND thread_id=%s AND message_id=%s",
                          (key[0], int(key[1] or 0), game["message_id"]))
    finally:
        conn.close()
    await context.bot.send_message(chat_id=key[0], message_thread_id=key[1], text=f"⌛ Se acabó el tiempo. La palabra era: {game['shown']}.")


async def palabra_hourly_job(context: ContextTypes.DEFAULT_TYPE):
    for community in COMUNIDADES:
        chat_id = int(community["id_comunidad"])
        try:
            await _launch(context, chat_id)
        except Exception as exc:
            print(f"[PALABRA RELAMPAGO] {chat_id}: {type(exc).__name__}: {exc}")


async def palabra_guess(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text or not update.effective_chat or update.effective_chat.type == "private":
        return
    # Telegram puede entregar mensajes normales/replies del mismo tema con pequeñas
    # diferencias en message_thread_id. Primero intentamos el tema exacto y, si no
    # coincide, buscamos la única ronda activa de este chat. Así NO hace falta
    # responder ni mencionar la imagen para acertar.
    chat_id = update.effective_chat.id
    thread_id = int(msg.message_thread_id or 0)
    guess = _norm(msg.text)

    # Reclamo atómico desde PostgreSQL: sobrevive reinicios y garantiza un solo ganador.
    conn = _db()
    claimed = None
    claimed_thread = thread_id
    try:
        with conn:
            with conn.cursor() as c:
                c.execute("""SELECT thread_id,answer,shown,started_at,message_id
                    FROM palabra_relampago_active_tb WHERE chat_id=%s ORDER BY started_at DESC""", (chat_id,))
                rows = c.fetchall()
                row = next((r for r in rows if int(r[0]) == thread_id), None)
                if row is None and len(rows) == 1:
                    row = rows[0]
                if row and guess == row[1]:
                    claimed_thread = int(row[0])
                    c.execute("""DELETE FROM palabra_relampago_active_tb
                        WHERE chat_id=%s AND thread_id=%s AND answer=%s AND message_id=%s
                        RETURNING shown,started_at,message_id""",
                        (chat_id, claimed_thread, guess, int(row[4])))
                    claimed = c.fetchone()
    finally:
        conn.close()
    if not claimed:
        return
    key = (chat_id, None if claimed_thread == 0 else claimed_thread)
    game = {"answer": guess, "shown": claimed[0], "started": claimed[1], "message_id": int(claimed[2])}
    _active.pop(key, None)
    elapsed_ms = max(0, int((datetime.now(TZ)-game["started"]).total_seconds()*1000))
    paid = dar_recompensa(update.effective_user.id, REWARD)
    conn = _db()
    try:
        with conn:
            with conn.cursor() as c:
                c.execute("""INSERT INTO palabra_relampago_stats_tb(chat_id,user_id,wins,pipesos,best_ms,last_win)
                    VALUES(%s,%s,1,%s,%s,NOW()) ON CONFLICT(chat_id,user_id) DO UPDATE SET
                    wins=palabra_relampago_stats_tb.wins+1,
                    pipesos=palabra_relampago_stats_tb.pipesos+EXCLUDED.pipesos,
                    best_ms=CASE WHEN palabra_relampago_stats_tb.best_ms IS NULL THEN EXCLUDED.best_ms ELSE LEAST(palabra_relampago_stats_tb.best_ms,EXCLUDED.best_ms) END,
                    last_win=NOW()""", (key[0], update.effective_user.id, paid, elapsed_ms))
    finally:
        conn.close()
    seconds = elapsed_ms / 1000
    await msg.reply_text(f"⚡ ¡{visible_user(update.effective_user)} fue el primero!\n🔎 {game['shown']}\n⏱️ {seconds:.1f} segundos\n💰 +{paid:,} PiPesos")


async def palabra_prueba(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_botmaster(update.effective_user.id):
        return
    chat = update.effective_chat
    if not chat or chat.type == "private":
        await update.effective_message.reply_text("⚠️ Usa /palabraprueba dentro del grupo.")
        return
    if update.effective_message.message_thread_id != _topic(chat.id):
        await update.effective_message.reply_text("⚠️ La prueba se usa en el tema Juegos y Casino.")
        return
    ok = await _launch(context, chat.id, force=True)
    if not ok:
        await update.effective_message.reply_text("⚠️ Ya hay una Palabra Relámpago activa.")


async def palabra_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_botmaster(update.effective_user.id):
        return
    if not update.effective_chat or update.effective_chat.type == "private":
        await update.effective_message.reply_text("⚠️ Usa este comando en el grupo que quieres configurar.")
        return
    _set_enabled(update.effective_chat.id, True)
    await update.effective_message.reply_text("⚡ Palabra Relámpago activada. Saldrá una ronda automática cada hora en Juegos.")


async def palabra_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_botmaster(update.effective_user.id):
        return
    if not update.effective_chat or update.effective_chat.type == "private":
        await update.effective_message.reply_text("⚠️ Usa este comando en el grupo que quieres configurar.")
        return
    _set_enabled(update.effective_chat.id, False)
    await update.effective_message.reply_text("🌙 Palabra Relámpago desactivada. Las rondas automáticas quedan apagadas.")
