"""Human-friendly Telegram identity formatting.

Internal logic should keep using numeric Telegram IDs. User-facing messages should
prefer @username and fall back to the stored/display name.
"""
from html import escape
from src.database.database import get_usuario_resumen


def visible_user(user=None, user_id=None, fallback="Usuario") -> str:
    if user is not None:
        username = getattr(user, "username", None)
        if username:
            return f"@{username}"
        name = " ".join(x for x in [getattr(user, "first_name", None), getattr(user, "last_name", None)] if x).strip()
        if name:
            return name
        user_id = getattr(user, "id", user_id)
    if user_id is not None:
        try:
            row = get_usuario_resumen(int(user_id))
            if row:
                if row.get("username"):
                    return f"@{row['username']}"
                if row.get("nombre"):
                    return str(row["nombre"])
        except Exception:
            pass
    return fallback


def visible_user_html(user=None, user_id=None, fallback="Usuario") -> str:
    return escape(visible_user(user=user, user_id=user_id, fallback=fallback))
