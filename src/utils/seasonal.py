"""Central seasonal presentation helpers for PiBot.

Presentation only: this module must never change balances, odds, rewards or game rules.
Dates use the community's Mexico City calendar so Render/UTC does not shift the theme.
"""
from __future__ import annotations

from datetime import datetime
from random import choice
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Mexico_City")


def current_season(now: datetime | None = None) -> str:
    now = now.astimezone(TZ) if now and now.tzinfo else (now.replace(tzinfo=TZ) if now else datetime.now(TZ))
    m, d = now.month, now.day
    # Halloween collection begins one day before October starts.
    if (m == 9 and d >= 30) or m == 10:
        return "halloween"
    # Día de Muertos starts on November 1.
    if m == 11 and d <= 2:
        return "dia_muertos"
    # Christmas collection starts December 1.
    if m == 12:
        return "navidad"
    if m == 2 and 13 <= d <= 14:
        return "san_valentin"
    return "normal"


THEMES = {
    "normal": {"icon": "✨", "name": "PiBot"},
    "halloween": {"icon": "🎃", "name": "PiBot: Noche de Brujas"},
    "dia_muertos": {"icon": "💀🌼", "name": "PiBot: Día de Muertos"},
    "navidad": {"icon": "🎄", "name": "PiBot: Navidad"},
    "san_valentin": {"icon": "💘", "name": "PiBot: San Valentín"},
}

WELCOME_LINES = {
    "normal": [
        "Juegos, PiPesos y suficientes formas de tomar malas decisiones financieras.",
        "Pasa, mira los comandos y procura no perder todos tus PiPesos el primer día.",
        "Aquí hay juegos, tienda y caos cuidadosamente administrado.",
    ],
    "halloween": [
        "Entra bajo tu propio riesgo. Los fantasmas no cobran intereses; BANKIU sí.",
        "Esta temporada hay sustos, juegos y decisiones financieras aterradoras.",
        "Las puertas están abiertas. Si escuchas cadenas, probablemente sea la tienda.",
        "Octubre llegó a PiBot: disfraces opcionales, malas apuestas inevitables.",
        "No temas a la oscuridad. Teme quedarte sin PiPesos.",
    ],
    "dia_muertos": [
        "Entre flores y recuerdos, PiBot sigue despierto... sospechosamente despierto.",
        "Hoy honramos recuerdos, historias y a quienes dejaron sus PiPesos en el casino.",
        "Las flores están listas y el grupo también. Bienvenido a Día de Muertos en PiBot.",
    ],
    "navidad": [
        "Llegó diciembre: regalos, juegos y BANKIU deseándote felices intereses.",
        "PiBot puso el árbol. Los PiPesos debajo siguen siendo responsabilidad tuya.",
        "Felices fiestas. Compra regalos, presume títulos y no apuestes el aguinaldo virtual.",
        "Hay espíritu navideño, luces y una cantidad preocupante de botones para gastar PiPesos.",
    ],
    "san_valentin": [
        "Hoy abundan los corazones, los regalos y las decisiones románticamente costosas.",
        "El amor está en el aire. La tienda de regalos también.",
    ],
}

COMMAND_INTROS = {
    "normal": ["¿Qué quieres hacer hoy?", "Elige tu siguiente desastre cuidadosamente."],
    "halloween": ["Elige tu siguiente travesura... si te atreves.", "El menú despertó. No preguntes qué lo invocó."],
    "dia_muertos": ["Entre flores y velas, elige qué quieres hacer.", "Hasta los comandos regresaron para la ocasión."],
    "navidad": ["Elige un regalo... digo, un comando.", "El menú navideño ya está servido."],
    "san_valentin": ["Elige con el corazón. O con los PiPesos.", "Hoy hasta los comandos vienen con corazones."],
}


def themed_header(section: str = "") -> str:
    season = current_season()
    theme = THEMES[season]
    return f"{theme['icon']} {section or theme['name']}"


def welcome_text() -> str:
    season = current_season()
    theme = THEMES[season]
    return f"{theme['icon']} *{theme['name']}*\n\n{choice(WELCOME_LINES[season])}"


def commands_intro() -> str:
    season = current_season()
    theme = THEMES[season]
    return f"{theme['icon']} *CENTRO DE COMANDOS*\n\n{choice(COMMAND_INTROS[season])}"

PROFILE_STYLES = {
    "normal": ("✨", "━━━━━━━━━━━━━━━━━━"),
    "halloween": ("🎃", "🕸️━━━━━━━━━━━━━━🕸️"),
    "dia_muertos": ("💀🌼", "🌼━━━━━━━━━━━━━━🌼"),
    "navidad": ("🎄", "❄️━━━━━━━━━━━━━━❄️"),
    "san_valentin": ("💘", "💗━━━━━━━━━━━━━━💗"),
}

def profile_style() -> tuple[str, str]:
    """Seasonal profile presentation only; never changes economy or odds."""
    return PROFILE_STYLES[current_season()]


SEASONAL_PREFIXES = {
    "normal": ["✨"],
    "halloween": ["🎃", "🕸️", "👻", "🦇"],
    "dia_muertos": ["💀🌼", "🕯️", "🌼"],
    "navidad": ["🎄", "❄️", "🎁", "🔔"],
    "san_valentin": ["💘", "🌹", "💗"],
}
SEASONAL_SUFFIXES = {
    "normal": [""],
    "halloween": ["La noche está mirando. 👁️", "Que empiece la travesura. 🦇", "Octubre reclama otro mensaje. 🎃"],
    "dia_muertos": ["Entre flores y velas. 🌼", "Que no falten las historias. 🕯️"],
    "navidad": ["Que no se pierdan los PiPesos entre los regalos. 🎁", "PiBot anda con espíritu navideño. ❄️"],
    "san_valentin": ["Hasta PiBot anda romántico hoy. 💘", "Con cariño... y quizá algunos PiPesos. 🌹"],
}

def seasonalize(text: str, *, compact: bool = False) -> str:
    """Presentation-only seasonal wrapper. Never changes game/economy semantics."""
    season=current_season()
    if season=="normal" or not text:
        return text
    prefix=choice(SEASONAL_PREFIXES[season])
    if compact:
        return f"{prefix} {text}"
    suffix=choice(SEASONAL_SUFFIXES[season])
    return f"{prefix} {text}" + (f"\n\n{suffix}" if suffix else "")
