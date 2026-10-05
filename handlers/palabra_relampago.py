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
from src.utils.display_name import display_name_from_user

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


def _render(word: str) -> io.BytesIO:
    # 18 fondos x 9 posiciones x 8 tamaños = 1,296 composiciones base, antes de variaciones de líneas/ruido.
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
    sizes = [52,56,60,64,68,72,76,80]
    f = _font(random.choice(sizes))
    shown = word.upper()
    box = d.textbbox((0,0), shown, font=f, stroke_width=1)
    tw, th = box[2]-box[0], box[3]-box[1]
    xs = [70, max(70,(900-tw)//2), max(70,830-tw)]
    ys = [85, max(85,(500-th)//2), max(85,405-th)]
    x, y = random.choice(xs), random.choice(ys)
    d.text((x,y), shown, font=f, fill=fg, stroke_width=1, stroke_fill=fg)
    # Línea ornamental que cambia de posición, como tarjeta de minijuego.
    ly = min(470, y + th + random.randint(12,35))
    d.line((x,ly,min(860,x+max(120,tw)),ly), fill=fg, width=3)
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
        caption="⚡ PALABRA RELÁMPAGO BDSM\n\nSé el primero en escribir exactamente la palabra o concepto que aparece en la imagen.\n\n💰 Premio: 1,500 PiPesos\n⏱️ Tienes 10 minutos."
    )
    _active[key] = {"answer": _norm(word), "shown": word, "started": started, "message_id": msg.message_id}
    context.job_queue.run_once(_expire, 600, data={"chat_id":chat_id,"thread":thread,"message_id":msg.message_id}, name=f"palabra:{chat_id}:{msg.message_id}")
    return True


async def _expire(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    key = (data["chat_id"], data["thread"])
    game = _active.get(key)
    if not game or game["message_id"] != data["message_id"]:
        return
    _active.pop(key, None)
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
    key = (update.effective_chat.id, msg.message_thread_id)
    game = _active.get(key)
    if not game or _norm(msg.text) != game["answer"]:
        return
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
    await msg.reply_text(f"⚡ ¡{display_name_from_user(update.effective_user)} fue el primero!\n🔎 {game['shown']}\n⏱️ {seconds:.1f} segundos\n💰 +{paid:,} PiPesos")


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
