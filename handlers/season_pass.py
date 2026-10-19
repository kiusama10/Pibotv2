"""Pase mensual de PiBot, XP de temporada y licencia temporal de GIF de perfil.

Diseño ligero para Render:
- No hay loops nuevos ni escaneo de mensajes.
- La temporada se resuelve por clave YYYY-MM; no hace falta un reset mensual.
- Solo toca PostgreSQL cuando una acción ya ocurrió (quiz, caja, aporte, etc.).
"""
from __future__ import annotations

import math
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from src.database.database import _get_connection, _put_connection

MEX = ZoneInfo("America/Mexico_City")
MAX_LEVEL = 100
SEASON_RANK_PRIZES = {1: 30000, 2: 20000, 3: 10000}

# XP equilibrada para que el 100 sea posible, pero no regalado.
SOURCE_CAPS = {
    "box": 180,      # máximo diario procedente de cajas
    "quiz": 150,     # 6 victorias de 25 XP
    "daily": 40,     # Pregunta del Día
    "content": 70,   # 2 aportes aprobados de 35 XP
}


def current_season_id() -> str:
    return datetime.now(MEX).strftime("%Y-%m")


def season_label(season_id: str | None = None) -> str:
    sid = season_id or current_season_id()
    year, month = sid.split("-", 1)
    names = {
        "01": "Enero", "02": "Febrero", "03": "Marzo", "04": "Abril",
        "05": "Mayo", "06": "Junio", "07": "Julio", "08": "Agosto",
        "09": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre",
    }
    return f"{names.get(month, month)} {year}"


def xp_for_level(level: int) -> int:
    """XP total necesaria para ESTAR en `level` (nivel 1 = 0 XP)."""
    level = max(1, min(MAX_LEVEL, int(level)))
    n = level - 1
    return int(round(45 * n + 0.55 * n * n))


def level_for_xp(xp: int) -> int:
    xp = max(0, int(xp))
    lo, hi = 1, MAX_LEVEL
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if xp_for_level(mid) <= xp:
            lo = mid
        else:
            hi = mid - 1
    return lo


def _season_rank_title(place: int, sid: str) -> str:
    label = season_label(sid)
    return {
        1: f"Campeón de Temporada · {label}",
        2: f"Subcampeón de Temporada · {label}",
        3: f"Top 3 de Temporada · {label}",
    }[place]


def _finalize_previous_seasons_cursor(c) -> list[tuple[str, int, int, int, str, int]]:
    """Premia Top 3 de temporadas cerradas una sola vez, sin cron ni loop permanente."""
    current = current_season_id()
    c.execute(
        """SELECT DISTINCT s.season_id
           FROM season_progression_tb s
           WHERE s.season_id < %s
             AND NOT EXISTS (SELECT 1 FROM season_ranking_awards_tb a WHERE a.season_id=s.season_id)
           ORDER BY s.season_id""",
        (current,),
    )
    pending = [r[0] for r in c.fetchall()]
    paid = []
    for sid in pending:
        c.execute(
            """SELECT user_id,level,xp
               FROM season_progression_tb
               WHERE season_id=%s
               ORDER BY level DESC,level_reached_at ASC,xp DESC,user_id ASC
               LIMIT 3""",
            (sid,),
        )
        rows = c.fetchall()
        for place, (uid, _level, _xp) in enumerate(rows, 1):
            prize = SEASON_RANK_PRIZES[place]
            title = _season_rank_title(place, sid)
            gif_days = 10 if place == 1 else 0
            c.execute(
                """INSERT INTO season_ranking_awards_tb(season_id,place,user_id,prize,title_name,gif_days)
                   VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (sid, place, uid, prize, title, gif_days),
            )
            if c.rowcount != 1:
                continue
            c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s", (prize, uid))
            code = f"season_rank_{sid.replace('-', '_')}_{place}"
            c.execute(
                """INSERT INTO social_assets_tb(asset_type,code,nombre,rareza,valor_base,propietario_id,origen,transferible)
                   VALUES('titulo',%s,%s,'temporada',0,%s,'ranking_temporada',FALSE)""",
                (code, title, uid),
            )
            if gif_days:
                _grant_gif_days_cursor(c, int(uid), gif_days)
            paid.append((sid, place, int(uid), prize, title, gif_days))
    return paid


def ensure_season_tables() -> None:
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS season_progression_tb(
            season_id TEXT NOT NULL,
            user_id BIGINT NOT NULL,
            xp BIGINT NOT NULL DEFAULT 0,
            level INT NOT NULL DEFAULT 1,
            level_reached_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(season_id,user_id)
        )""")
        # Migración aditiva para instalaciones que ya tenían el pase.
        # Para datos viejos usamos updated_at como la mejor marca disponible de llegada.
        c.execute("ALTER TABLE season_progression_tb ADD COLUMN IF NOT EXISTS level_reached_at TIMESTAMPTZ")
        c.execute("UPDATE season_progression_tb SET level_reached_at=updated_at WHERE level_reached_at IS NULL")
        c.execute("ALTER TABLE season_progression_tb ALTER COLUMN level_reached_at SET DEFAULT NOW()")
        c.execute("""CREATE INDEX IF NOT EXISTS idx_season_progression_rank_v2
                     ON season_progression_tb(season_id,level DESC,level_reached_at ASC,xp DESC,user_id ASC)""")
        c.execute("""CREATE TABLE IF NOT EXISTS season_xp_daily_tb(
            season_id TEXT NOT NULL,
            day DATE NOT NULL,
            user_id BIGINT NOT NULL,
            source TEXT NOT NULL,
            xp INT NOT NULL DEFAULT 0,
            PRIMARY KEY(season_id,day,user_id,source)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS season_level_rewards_tb(
            season_id TEXT NOT NULL,
            user_id BIGINT NOT NULL,
            level INT NOT NULL,
            reward_text TEXT NOT NULL,
            claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(season_id,user_id,level)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS season_ranking_awards_tb(
            season_id TEXT NOT NULL,
            place INT NOT NULL CHECK(place BETWEEN 1 AND 3),
            user_id BIGINT NOT NULL,
            prize BIGINT NOT NULL,
            title_name TEXT,
            gif_days INT NOT NULL DEFAULT 0,
            awarded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(season_id,place),
            UNIQUE(season_id,user_id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS season_content_approvals_tb(
            chat_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            season_id TEXT NOT NULL,
            user_id BIGINT NOT NULL,
            approved_by BIGINT NOT NULL,
            xp INT NOT NULL DEFAULT 0,
            approved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(chat_id,message_id)
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS profile_gif_license_tb(
            user_id BIGINT PRIMARY KEY,
            gif_file_id TEXT,
            expires_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""")
        _finalize_previous_seasons_cursor(c)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_connection(conn)


def _grant_gif_days_cursor(c, uid: int, days: int = 10) -> None:
    days = max(1, int(days))
    c.execute(
        """INSERT INTO profile_gif_license_tb(user_id,expires_at)
           VALUES(%s,NOW()+(%s||' days')::interval)
           ON CONFLICT(user_id) DO UPDATE SET
             expires_at=CASE
               WHEN profile_gif_license_tb.expires_at IS NOT NULL AND profile_gif_license_tb.expires_at>NOW()
                 THEN profile_gif_license_tb.expires_at+(%s||' days')::interval
               ELSE NOW()+(%s||' days')::interval
             END,
             updated_at=NOW()""",
        (uid, days, days, days),
    )


def grant_profile_gif_days(uid: int, days: int = 10) -> bool:
    conn = _get_connection()
    try:
        c = conn.cursor()
        _grant_gif_days_cursor(c, uid, days)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        _put_connection(conn)


def _grant_unowned_font_cursor(c, uid: int) -> str:
    from handlers.pipeso_extras import FONTS, FONT_LABELS
    c.execute("SELECT asset_code FROM user_box_assets_tb WHERE user_id=%s AND asset_type='font'", (uid,))
    owned = {r[0] for r in c.fetchall()}
    available = [x for x in FONTS if x not in owned]
    code = random.choice(available or FONTS)
    label = FONT_LABELS.get(code, code)
    c.execute(
        """INSERT INTO user_box_assets_tb(user_id,asset_type,asset_code,asset_name)
           VALUES(%s,'font',%s,%s) ON CONFLICT DO NOTHING""",
        (uid, code, f"Tipografía {label} · PASE"),
    )
    if c.rowcount == 0:
        c.execute("UPDATE usuarios_tb SET saldo=saldo+3000 WHERE id_user=%s", (uid,))
        return "🔤 Tipografía repetida → +3,000 PiPesos"
    return f"🔤 Tipografía desbloqueada: {label}"


def _grant_unowned_title_cursor(c, uid: int) -> str:
    from handlers.pipeso_extras import title_pool
    titles = title_pool()
    c.execute("SELECT nombre FROM social_assets_tb WHERE propietario_id=%s AND asset_type='titulo'", (uid,))
    owned = {r[0] for r in c.fetchall()}
    available = [x for x in titles if x not in owned]
    title = random.choice(available or titles)
    code = "season_" + "".join(ch.lower() if ch.isalnum() else "_" for ch in title).strip("_")
    c.execute(
        """INSERT INTO social_assets_tb(asset_type,code,nombre,rareza,valor_base,propietario_id,origen)
           VALUES('titulo',%s,%s,'temporada',0,%s,'pase_temporada')""",
        (code, title, uid),
    )
    return f"🏷️ Título desbloqueado: {title}"


def _level_reward_cursor(c, sid: str, uid: int, level: int) -> list[str]:
    """Otorga una sola vez la recompensa de un nivel dentro de la transacción actual."""
    if level <= 1:
        return []
    # Marcador idempotente primero. Si ya existe, no se vuelve a pagar.
    c.execute(
        """INSERT INTO season_level_rewards_tb(season_id,user_id,level,reward_text)
           VALUES(%s,%s,%s,'pendiente') ON CONFLICT DO NOTHING""",
        (sid, uid, level),
    )
    if c.rowcount != 1:
        return []

    rewards: list[str] = []
    small = 250 + 25 * ((level - 1) // 10)
    c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s", (small, uid))
    rewards.append(f"🪙 +{small:,} PiPesos")

    milestones = {10: 2500, 20: 3500, 40: 5500, 60: 8000, 80: 12000, 100: 20000}
    if level in milestones:
        extra = milestones[level]
        c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s", (extra, uid))
        rewards.append(f"🎁 +{extra:,} PiPesos de hito")
    if level in (30, 70):
        rewards.append(_grant_unowned_font_cursor(c, uid))
    if level in (50, 90):
        rewards.append(_grant_unowned_title_cursor(c, uid))
    if level == 100:
        _grant_gif_days_cursor(c, uid, 10)
        rewards.append("🎞️ GIF de perfil por 10 días")
        title = f"Leyenda de Temporada · {season_label(sid)}"
        code = f"season_legend_{sid.replace('-', '_')}"
        c.execute(
            """INSERT INTO social_assets_tb(asset_type,code,nombre,rareza,valor_base,propietario_id,origen)
               VALUES('titulo',%s,%s,'legendario',0,%s,'pase_temporada')
               ON CONFLICT DO NOTHING""",
            (code, title, uid),
        )
        rewards.append(f"🏆 Título: {title}")

    reward_text = " · ".join(rewards)
    c.execute(
        "UPDATE season_level_rewards_tb SET reward_text=%s WHERE season_id=%s AND user_id=%s AND level=%s",
        (reward_text, sid, uid, level),
    )
    return rewards


def _grant_xp_cursor(c, uid: int, amount: int, source: str, daily_cap: int | None = None) -> dict:
    _finalize_previous_seasons_cursor(c)
    sid = current_season_id()
    amount = max(0, int(amount))
    if amount <= 0:
        return {"granted": 0, "old_level": 1, "new_level": 1, "xp": 0, "rewards": []}

    if daily_cap is None:
        daily_cap = SOURCE_CAPS.get(source)
    granted = amount
    if daily_cap is not None:
        today = datetime.now(MEX).date()
        c.execute(
            """INSERT INTO season_xp_daily_tb(season_id,day,user_id,source,xp)
               VALUES(%s,%s,%s,%s,0) ON CONFLICT DO NOTHING""",
            (sid, today, uid, source),
        )
        c.execute(
            "SELECT xp FROM season_xp_daily_tb WHERE season_id=%s AND day=%s AND user_id=%s AND source=%s FOR UPDATE",
            (sid, today, uid, source),
        )
        used = int((c.fetchone() or (0,))[0])
        granted = min(amount, max(0, int(daily_cap) - used))
        if granted:
            c.execute(
                """UPDATE season_xp_daily_tb SET xp=xp+%s
                   WHERE season_id=%s AND day=%s AND user_id=%s AND source=%s""",
                (granted, sid, today, uid, source),
            )

    c.execute(
        """INSERT INTO season_progression_tb(season_id,user_id,xp,level)
           VALUES(%s,%s,0,1) ON CONFLICT DO NOTHING""",
        (sid, uid),
    )
    c.execute(
        "SELECT xp,level FROM season_progression_tb WHERE season_id=%s AND user_id=%s FOR UPDATE",
        (sid, uid),
    )
    old_xp, old_level = c.fetchone()
    new_xp = int(old_xp) + granted
    new_level = level_for_xp(new_xp)
    rewards: list[tuple[int, list[str]]] = []
    if new_level > int(old_level):
        for lv in range(int(old_level) + 1, new_level + 1):
            rr = _level_reward_cursor(c, sid, uid, lv)
            if rr:
                rewards.append((lv, rr))
    if new_level > int(old_level):
        c.execute(
            """UPDATE season_progression_tb
               SET xp=%s,level=%s,level_reached_at=NOW(),updated_at=NOW()
               WHERE season_id=%s AND user_id=%s""",
            (new_xp, new_level, sid, uid),
        )
    else:
        c.execute(
            """UPDATE season_progression_tb SET xp=%s,level=%s,updated_at=NOW()
               WHERE season_id=%s AND user_id=%s""",
            (new_xp, new_level, sid, uid),
        )
    return {
        "season_id": sid,
        "granted": granted,
        "old_level": int(old_level),
        "new_level": new_level,
        "xp": new_xp,
        "rewards": rewards,
        "cap": daily_cap,
    }


def grant_season_xp(uid: int, amount: int, source: str, daily_cap: int | None = None) -> dict | None:
    conn = _get_connection()
    try:
        c = conn.cursor()
        result = _grant_xp_cursor(c, uid, amount, source, daily_cap)
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        print(f"[SEASON XP] {type(e).__name__}: {e}")
        return None
    finally:
        _put_connection(conn)


def season_status(uid: int) -> dict:
    sid = current_season_id()
    conn = _get_connection()
    try:
        c = conn.cursor()
        _finalize_previous_seasons_cursor(c)
        conn.commit()
        c.execute("SELECT xp,level FROM season_progression_tb WHERE season_id=%s AND user_id=%s", (sid, uid))
        row = c.fetchone() or (0, 1)
        xp, level = int(row[0]), int(row[1])
        c.execute(
            """SELECT pos FROM (
                 SELECT user_id,ROW_NUMBER() OVER(
                   ORDER BY level DESC,level_reached_at ASC,xp DESC,user_id ASC
                 ) AS pos
                 FROM season_progression_tb WHERE season_id=%s
               ) ranked WHERE user_id=%s""",
            (sid, uid),
        )
        rr = c.fetchone()
        rank = int(rr[0]) if rr else 1
        return {"season_id": sid, "xp": xp, "level": level, "rank": rank}
    finally:
        _put_connection(conn)


def gif_license_status(uid: int) -> dict:
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """SELECT gif_file_id,expires_at,
                      GREATEST(0,CEIL(EXTRACT(EPOCH FROM (expires_at-NOW()))/86400.0))::int
               FROM profile_gif_license_tb WHERE user_id=%s""",
            (uid,),
        )
        row = c.fetchone()
        if not row or row[1] is None or row[2] <= 0:
            return {"active": False, "file_id": row[0] if row else None, "days": 0}
        return {"active": True, "file_id": row[0], "days": int(row[2]), "expires_at": row[1]}
    finally:
        _put_connection(conn)


def set_profile_gif(uid: int, file_id: str) -> bool:
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """UPDATE profile_gif_license_tb SET gif_file_id=%s,updated_at=NOW()
               WHERE user_id=%s AND expires_at>NOW() RETURNING user_id""",
            (file_id, uid),
        )
        ok = bool(c.fetchone())
        conn.commit()
        return ok
    except Exception:
        conn.rollback()
        return False
    finally:
        _put_connection(conn)


def _progress_bar(xp: int, level: int) -> tuple[str, str]:
    if level >= MAX_LEVEL:
        return "██████████", "Nivel máximo"
    start = xp_for_level(level)
    end = xp_for_level(level + 1)
    span = max(1, end - start)
    frac = max(0.0, min(1.0, (xp - start) / span))
    filled = min(10, max(0, int(math.floor(frac * 10))))
    return "█" * filled + "░" * (10 - filled), f"{xp - start:,} / {span:,} XP"


async def nivel_temporada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st = season_status(update.effective_user.id)
    bar, local = _progress_bar(st["xp"], st["level"])
    next_big = min(MAX_LEVEL, ((st["level"] // 10) + 1) * 10)
    extra = "🏁 Ya completaste el pase." if st["level"] >= MAX_LEVEL else f"🎁 Próximo hito grande: nivel {next_big}"
    await update.effective_message.reply_text(
        f"⭐ PASE DE TEMPORADA · {season_label(st['season_id'])}\n\n"
        f"Nivel {st['level']} / {MAX_LEVEL}\n{bar} {local}\n"
        f"🏆 Ranking: #{st['rank']}\n\n{extra}\n\n"
        "En empate de nivel, queda arriba quien llegó primero a ese nivel.\n"
        "La temporada cambia automáticamente cada mes."
    )


async def pase_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st = season_status(update.effective_user.id)
    gif = gif_license_status(update.effective_user.id)
    gif_line = f"🎞️ GIF de perfil activo: {gif['days']} día(s)" if gif["active"] else "🎞️ GIF de perfil: sin licencia activa"
    await update.effective_message.reply_text(
        f"🎟️ PASE PIBOT · {season_label(st['season_id'])}\n\n"
        f"⭐ Nivel actual: {st['level']}\n🏆 Ranking: #{st['rank']}\n{gif_line}\n\n"
        "Cada nivel da una recompensa pequeña.\n"
        "10 · 20 · 40 · 60 · 80 → PiPesos extra\n"
        "30 · 70 → tipografía\n"
        "50 · 90 → título\n"
        "100 → premio final + título de temporada + GIF de perfil por 10 días\n\n"
        "🏆 PREMIOS DEL RANKING AL CERRAR EL MES\n"
        "🥇 30,000 PiPesos + título Campeón + 10 días de GIF\n"
        "🥈 20,000 PiPesos + título Subcampeón\n"
        "🥉 10,000 PiPesos + título Top 3\n\n"
        "En empate de nivel, gana posición quien llegó primero a ese nivel.\n"
        "La XP se reinicia por temporada sin borrar tu historial anterior."
    )


async def ranking_niveles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sid = current_season_id()
    uid = update.effective_user.id
    conn = _get_connection()
    try:
        c = conn.cursor()
        _finalize_previous_seasons_cursor(c)
        conn.commit()
        c.execute(
            """SELECT s.user_id,s.level,s.xp,COALESCE(NULLIF(p.username,''),NULLIF(p.nombre,''),s.user_id::text)
               FROM season_progression_tb s
               LEFT JOIN perfiles_tb p ON p.id_user=s.user_id
               WHERE s.season_id=%s
               ORDER BY s.level DESC,s.level_reached_at ASC,s.xp DESC,s.user_id ASC LIMIT 10""",
            (sid,),
        )
        rows = c.fetchall()
        c.execute(
            """SELECT pos FROM (
                 SELECT user_id,ROW_NUMBER() OVER(
                   ORDER BY level DESC,level_reached_at ASC,xp DESC,user_id ASC
                 ) AS pos
                 FROM season_progression_tb WHERE season_id=%s
               ) ranked WHERE user_id=%s""",
            (sid, uid),
        )
        me = c.fetchone()
        my_rank = int(me[0]) if me else None
    finally:
        _put_connection(conn)
    lines = [f"🏆 RANKING DE NIVELES · {season_label(sid)}", ""]
    medals = ["🥇", "🥈", "🥉"]
    if not rows:
        lines.append("Todavía nadie ha ganado XP esta temporada.")
    for i, (_ruid, level, xp, name) in enumerate(rows, 1):
        prefix = medals[i-1] if i <= 3 else f"{i}."
        lines.append(f"{prefix} {name} — Nivel {level} · {xp:,} XP")
    if my_rank is not None and my_rank > 10:
        lines += ["", f"Tu posición: #{my_rank}"]
    lines += [
        "",
        "🎁 PREMIOS AL CERRAR EL MES",
        "🥇 30,000 PiPesos + título Campeón + 10 días de GIF",
        "🥈 20,000 PiPesos + título Subcampeón",
        "🥉 10,000 PiPesos + título Top 3",
        "",
        "🤝 Empate de nivel: queda arriba quien llegó primero a ese nivel.",
    ]
    await update.effective_message.reply_text("\n".join(lines))


async def aprobar_aporte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m = update.effective_message
    if not m or update.effective_chat.type == "private":
        return await m.reply_text("Este comando se usa en el grupo respondiendo al contenido que quieres aprobar.")
    if not m.reply_to_message or not m.reply_to_message.from_user:
        return await m.reply_text("Responde al contenido con /aporte para aprobarlo.")
    try:
        member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
        if member.status not in ("administrator", "creator"):
            return await m.reply_text("⛔ Solo un admin puede aprobar aportes para XP.")
    except Exception:
        return await m.reply_text("⚠️ No pude verificar permisos de admin.")
    target = m.reply_to_message.from_user
    if target.is_bot:
        return await m.reply_text("Los bots no ganan XP de temporada.")

    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """INSERT INTO season_content_approvals_tb(chat_id,message_id,season_id,user_id,approved_by,xp)
               VALUES(%s,%s,%s,%s,%s,0) ON CONFLICT DO NOTHING""",
            (update.effective_chat.id, m.reply_to_message.message_id, current_season_id(), target.id, update.effective_user.id),
        )
        if c.rowcount != 1:
            conn.rollback()
            return await m.reply_text("Ese aporte ya fue aprobado anteriormente.")
        result = _grant_xp_cursor(c, target.id, 35, "content", SOURCE_CAPS["content"])
        c.execute(
            "UPDATE season_content_approvals_tb SET xp=%s WHERE chat_id=%s AND message_id=%s",
            (result["granted"], update.effective_chat.id, m.reply_to_message.message_id),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"[APORTE XP] {type(e).__name__}: {e}")
        return await m.reply_text("⚠️ No pude registrar el aporte.")
    finally:
        _put_connection(conn)

    if result["granted"] <= 0:
        return await m.reply_text("✅ Aporte aprobado. Ya alcanzó el máximo diario de XP por contenido.")
    level_line = ""
    if result["new_level"] > result["old_level"]:
        level_line = f"\n🎉 Subió a nivel {result['new_level']}."
    await m.reply_text(f"✅ Aporte aprobado para {target.mention_html()} · +{result['granted']} XP.{level_line}", parse_mode="HTML")


async def gifperfil_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return await update.effective_message.reply_text("🎞️ El GIF del perfil se configura por privado con PiBot.")
    st = gif_license_status(update.effective_user.id)
    if not st["active"]:
        return await update.effective_message.reply_text("🔒 No tienes una licencia de GIF de perfil activa. Puede salir en cajas y el nivel 100 la da por 10 días.")
    context.user_data["profile_waiting_gif"] = True
    await update.effective_message.reply_text(
        f"🎞️ Tienes {st['days']} día(s) de GIF de perfil.\n\nEnvíame ahora el GIF que quieres usar. Telegram lo guardará por file_id y PiBot lo reutilizará sin volver a subirlo cada vez."
    )


async def profile_gif_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private" or not context.user_data.get("profile_waiting_gif"):
        return
    if not update.message or not update.message.animation:
        return
    st = gif_license_status(update.effective_user.id)
    if not st["active"]:
        context.user_data.pop("profile_waiting_gif", None)
        return await update.message.reply_text("Tu licencia ya venció.")
    ok = set_profile_gif(update.effective_user.id, update.message.animation.file_id)
    context.user_data.pop("profile_waiting_gif", None)
    await update.message.reply_text("✅ GIF de perfil guardado. Usa /perfil para verlo." if ok else "⚠️ No pude guardar el GIF.")
