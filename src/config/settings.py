"""
Configuration module for PiBot.

This module handles all configuration settings including:
- Bot token and API credentials
- Community IDs and topics
- Admin and DOM (dominant) user lists
- Database connection URL
- Environment-based configuration

All sensitive data should be loaded from environment variables.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

if not BOT_TOKEN:
    raise ValueError(
        "ERROR: BOT_TOKEN environment variable is not set. "
        "Please create a .env file with your bot token."
    )

# Database Configuration (PostgreSQL on Railway)
DATABASE_URL = os.getenv("DATABASE_URL", "")

if not DATABASE_URL:
    raise ValueError(
        "ERROR: DATABASE_URL environment variable is not set. "
        "Railway provides this automatically when you add a PostgreSQL plugin."
    )

# Bot username for deep links (without @)
BOT_USERNAME = os.getenv("BOT_USERNAME", "")

# BotMaster IDs (comma-separated) — these users get role=3 at startup
_botmaster_raw = os.getenv("BOTMASTER_IDS", "")
BOTMASTER_IDS = [int(x.strip()) for x in _botmaster_raw.split(",") if x.strip()]

# Community configurations with their topic IDs
COMUNIDADES = [
    {
        "id_comunidad": -1003290179217,  # Kiusama (main community)
        "nombre": "Kiusama",
        "temas": {
            "theme_anuncios": 526,
            "theme_questions": 902,
            "theme_escuela": 438,
            "theme_juegosYcasino": 528,
            "theme_general": 435,
            "theme_eventos": 335263,
            "theme_presentaciones": None,
            "theme_relatos": 683,
            "theme_NSFW": 2,
            "theme_Exhibicionismo": 324185,
            "theme_busquedas": 695,
            "theme_libreria": 462,
            "theme_multimedia": 688,
            "theme_rincon": 77167,  # Punishment corner (confinement)
        }
    },
    {
        "id_comunidad": -1002983018006,  # Rub (secondary community)
        "nombre": "Rub",
        "temas": {
            "theme_Anuncios": 207,
            "theme_questions": 7,
            "theme_escuela": 438,
            "theme_juegosYcasino": 16785,
            "theme_NSFW": 5,
            "theme_Exhibicionismo": 4,
            "theme_libreria": 3,
            "theme_multimedia": 15,
            "theme_platica": 28175,
            "theme_test": 43,
            "theme_reglas": 8,
            "theme_escuela": 6,
            "theme_presentaciones": 2,
            "theme_rincon": 36205,
        }
    }
]

# Dominant (DOM) users and their submissives
# DOM_ID: [submissive_IDs]
DOMS = {
    1370162159: [5661536115],
    1174798556: [7064982957, 7819911906, 1128700552, 1754172595],
    777745711: [7252166050],
    8019495591: [6843544299],
    1128700552: [1750172112]
}

# Application settings
PUNISHMENT_FILE = "castigados.json"


def obtener_temas_por_comunidad(community_id: int) -> dict:
    """
    Get topic IDs for a specific community.
    
    Args:
        community_id: The community chat ID
    
    Returns:
        Dictionary with topic names and their IDs, or None if community not found
    """
    for comunidad in COMUNIDADES:
        if comunidad["id_comunidad"] == community_id:
            return comunidad["temas"]
    return None

# Optional paid music topic. Keep unset/empty until the real Telegram topic ID is known.
_raw_music_thread = os.getenv("MUSIC_THREAD_ID", "").strip()
MUSIC_THREAD_ID = int(_raw_music_thread) if _raw_music_thread.lstrip("-").isdigit() else None
MUSIC_POST_PRICE = int(os.getenv("MUSIC_POST_PRICE", "500"))
