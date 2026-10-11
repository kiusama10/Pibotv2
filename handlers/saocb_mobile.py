"""SAO-CB mobile/web client bridge.

Securely links the SAO-CB Android/PWA client to the same Telegram account and
PostgreSQL state used by handlers.saocb_telegram. No second economy or save.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from telegram import Update
from telegram.ext import ContextTypes

from src.database.database import _get_connection, _put_connection
from src.utils.display_name import visible_user
from handlers.saocb_telegram import (
    MAX_STAMINA,
    SINGLE_COST,
    MULTI_COST,
    _ensure_player,
    _player,
    _aincrad_name,
    _set_aincrad_name,
    _user_units,
    _party_stats,
    _party,
    _set_party_slot,
    _gacha,
    _quest,
    _start_battle,
    _battle_get,
    _battle_action,
    _upgrade_unit,
    _claim_daily,
    _max_level,
)

LINK_TTL_MINUTES = 10
TOKEN_TTL_DAYS = 180
_CODE_RE = re.compile(r"^[A-Z2-9]{6}$")
_ALLOWED_ACTIONS = {"attack", "guard", "skill", "retreat"}


def ensure_saocb_mobile_tables() -> None:
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS saocb_app_links_tb(
                code TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                user_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL,
                approved_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_saocb_app_link_device ON saocb_app_links_tb(device_id, expires_at DESC)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS saocb_app_tokens_tb(
                token_hash TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES usuarios_tb(id_user) ON DELETE CASCADE,
                device_id TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL,
                revoked BOOLEAN NOT NULL DEFAULT FALSE
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_saocb_app_token_user ON saocb_app_tokens_tb(user_id, revoked, expires_at)")
        # Cleanup is cheap and keeps abandoned codes/tokens from growing forever.
        c.execute("DELETE FROM saocb_app_links_tb WHERE expires_at < NOW() - INTERVAL '1 day'")
        c.execute("DELETE FROM saocb_app_tokens_tb WHERE expires_at < NOW() - INTERVAL '30 days'")
        conn.commit()
        print("[SAO-APP] Tablas listas: mobile bridge V1")
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_connection(conn)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _clean_device_id(value: Any) -> str:
    v = str(value or "").strip()
    if not (8 <= len(v) <= 128):
        raise ValueError("device_id inválido")
    # UUIDs and generated browser IDs are enough; reject control chars.
    if any(ord(ch) < 32 for ch in v):
        raise ValueError("device_id inválido")
    return v


def _new_code(c) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(50):
        code = "".join(secrets.choice(alphabet) for _ in range(6))
        c.execute("SELECT 1 FROM saocb_app_links_tb WHERE code=%s", (code,))
        if not c.fetchone():
            return code
    raise RuntimeError("No fue posible generar código")


def begin_link(device_id: str) -> Dict[str, Any]:
    device_id = _clean_device_id(device_id)
    conn = _get_connection()
    try:
        c = conn.cursor()
        # One active code per device. Creating a new one invalidates the old one.
        c.execute("DELETE FROM saocb_app_links_tb WHERE device_id=%s", (device_id,))
        code = _new_code(c)
        expires = datetime.now(timezone.utc) + timedelta(minutes=LINK_TTL_MINUTES)
        c.execute(
            "INSERT INTO saocb_app_links_tb(code,device_id,expires_at) VALUES(%s,%s,%s)",
            (code, device_id, expires),
        )
        conn.commit()
        return {
            "code": code,
            "expires_seconds": LINK_TTL_MINUTES * 60,
            "telegram_command": f"/saoapp {code}",
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_connection(conn)


def approve_link_code(user_id: int, code: str) -> Tuple[bool, str]:
    code = (code or "").strip().upper()
    if not _CODE_RE.match(code):
        return False, "Ese código no tiene el formato correcto."
    _ensure_player(int(user_id))
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT device_id,expires_at,user_id FROM saocb_app_links_tb WHERE code=%s FOR UPDATE", (code,))
        row = c.fetchone()
        if not row:
            conn.rollback()
            return False, "Ese código no existe o ya fue usado."
        if row[1] <= datetime.now(timezone.utc):
            c.execute("DELETE FROM saocb_app_links_tb WHERE code=%s", (code,))
            conn.commit()
            return False, "Ese código ya venció. Genera uno nuevo en la app."
        if row[2] and int(row[2]) != int(user_id):
            conn.rollback()
            return False, "Ese código ya fue aprobado por otra cuenta."
        c.execute(
            "UPDATE saocb_app_links_tb SET user_id=%s,approved_at=NOW() WHERE code=%s",
            (int(user_id), code),
        )
        conn.commit()
        return True, "✅ App SAO-CB vinculada. Regresa a la app; entrará sola en unos segundos."
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_connection(conn)


async def sao_app_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_message:
        return
    if not context.args:
        return await update.effective_message.reply_text(
            "📱 Para vincular SAO-CB App, abre la app y escribe aquí el código que te muestre.\n\nEjemplo: /saoapp ABC123"
        )
    ok, msg = approve_link_code(update.effective_user.id, context.args[0])
    await update.effective_message.reply_text(msg)


def claim_link(device_id: str, code: str) -> Dict[str, Any]:
    device_id = _clean_device_id(device_id)
    code = (code or "").strip().upper()
    if not _CODE_RE.match(code):
        return {"status": "invalid"}
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("SELECT device_id,user_id,expires_at,approved_at FROM saocb_app_links_tb WHERE code=%s FOR UPDATE", (code,))
        row = c.fetchone()
        if not row or row[0] != device_id:
            conn.rollback()
            return {"status": "invalid"}
        if row[2] <= datetime.now(timezone.utc):
            c.execute("DELETE FROM saocb_app_links_tb WHERE code=%s", (code,))
            conn.commit()
            return {"status": "expired"}
        if not row[1] or not row[3]:
            conn.rollback()
            return {"status": "waiting"}
        uid = int(row[1])
        token = secrets.token_urlsafe(40)
        token_hash = _hash_token(token)
        expires = datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)
        c.execute(
            "INSERT INTO saocb_app_tokens_tb(token_hash,user_id,device_id,expires_at) VALUES(%s,%s,%s,%s)",
            (token_hash, uid, device_id, expires),
        )
        c.execute("DELETE FROM saocb_app_links_tb WHERE code=%s", (code,))
        conn.commit()
        return {
            "status": "linked",
            "token": token,
            "expires_at": expires.isoformat(),
            "user": _brief_player(uid),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        _put_connection(conn)


def authenticate(headers: Dict[str, str]) -> Optional[int]:
    auth = headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    if len(token) < 20:
        return None
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute(
            """SELECT user_id FROM saocb_app_tokens_tb
               WHERE token_hash=%s AND revoked=FALSE AND expires_at>NOW()""",
            (_hash_token(token),),
        )
        row = c.fetchone()
        if not row:
            return None
        uid = int(row[0])
        c.execute("UPDATE saocb_app_tokens_tb SET last_seen_at=NOW() WHERE token_hash=%s", (_hash_token(token),))
        conn.commit()
        return uid
    except Exception:
        conn.rollback()
        return None
    finally:
        _put_connection(conn)


def revoke_token(headers: Dict[str, str]) -> None:
    auth = headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return
    token = auth.split(" ", 1)[1].strip()
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("UPDATE saocb_app_tokens_tb SET revoked=TRUE WHERE token_hash=%s", (_hash_token(token),))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        _put_connection(conn)


def _brief_player(uid: int) -> Dict[str, Any]:
    p = _player(uid)
    hp, atk, de, power, party = _party_stats(uid)
    return {
        "user_id": uid,
        "name": _aincrad_name(uid, p),
        "rank": p["rank"],
        "floor": p["floor"],
        "pipesos": p["md"],
        "col": p["col"],
        "fragments": p["fragments"],
        "stamina": p["stamina"],
        "stamina_max": MAX_STAMINA,
        "power": power,
        "party_hp": hp,
        "party_atk": atk,
        "party_def": de,
        "main_unit": party[0]["name"] if party else None,
    }


def _home(uid: int) -> Dict[str, Any]:
    return {
        "player": _brief_player(uid),
        "party": _party(uid),
        "has_battle": _battle_get(uid) is not None,
        "scout": {"single_cost": SINGLE_COST, "multi_cost": MULTI_COST},
    }


def _units_payload(uid: int) -> Dict[str, Any]:
    units = _user_units(uid)
    for u in units:
        u["max_level"] = _max_level(int(u["stars"]), int(u["awaken"]))
        u["upgrade_cost"] = 500 + int(u["level"]) * 120
    return {"units": units, "player": _brief_player(uid)}


def _quests_payload(uid: int) -> Dict[str, Any]:
    p = _player(uid)
    _, _, _, power, _ = _party_stats(uid)
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT q.quest_id,q.floor,q.name,q.enemy,q.recommended_power,q.enemy_hp,q.enemy_atk,
                   q.reward_col,q.reward_md,q.stamina_cost,COALESCE(p.clear_count,0)
            FROM saocb_quests_tb q
            LEFT JOIN saocb_quest_progress_tb p ON p.quest_id=q.quest_id AND p.user_id=%s
            WHERE q.active=TRUE ORDER BY q.quest_id
        """, (uid,))
        out = []
        for r in c.fetchall():
            out.append({
                "quest_id": int(r[0]), "floor": int(r[1]), "name": r[2], "enemy": r[3],
                "recommended_power": int(r[4]), "enemy_hp": int(r[5]), "enemy_atk": int(r[6]),
                "reward_col": int(r[7]), "reward_md": int(r[8]), "stamina_cost": int(r[9]),
                "clear_count": int(r[10]), "locked": int(r[1]) > int(p["floor"]) + 10,
            })
        return {"quests": out, "player_power": power, "stamina": p["stamina"]}
    finally:
        _put_connection(conn)


def _battle_payload(uid: int, note: str = "") -> Dict[str, Any]:
    b = _battle_get(uid)
    if not b:
        return {"active": False, "note": note}
    q = _quest(int(b["quest_id"]))
    maxhp, _, _, power, party = _party_stats(uid)
    main = party[0] if party else None
    return {
        "active": True,
        "note": note,
        "turn": int(b["turn"]),
        "player_hp": max(0, int(b["player_hp"])),
        "player_hp_max": maxhp,
        "enemy_hp": max(0, int(b["enemy_hp"])),
        "enemy_hp_max": int(q["enemy_hp"]),
        "enemy": q["enemy"],
        "quest_name": q["name"],
        "floor": int(q["floor"]),
        "power": power,
        "main_unit": main["name"] if main else None,
        "skill_name": main["skill_name"] if main else "Skill",
        "skill_cd": int(b["skill_cd"]),
    }


def _ranking(uid: int) -> Dict[str, Any]:
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""SELECT p.user_id,p.rank,p.floor,p.col,
            COALESCE(SUM((uc.base_atk*(1+(u.level-1)*0.035))*2 + uc.base_def*(1+(u.level-1)*0.035) + (uc.base_hp*(1+(u.level-1)*0.035))/8),0) AS power,
            p.player_name
            FROM saocb_players_tb p
            LEFT JOIN saocb_parties_tb pt ON pt.user_id=p.user_id
            LEFT JOIN saocb_user_units_tb u ON u.user_id=pt.user_id AND u.unit_id=pt.unit_id
            LEFT JOIN saocb_units_catalog_tb uc ON uc.unit_id=u.unit_id
            GROUP BY p.user_id,p.rank,p.floor,p.col,p.player_name
            ORDER BY p.floor DESC,power DESC LIMIT 50""")
        rows = []
        for i, r in enumerate(c.fetchall(), 1):
            rid = int(r[0])
            rows.append({
                "position": i,
                "user_id": rid,
                "name": (r[5] or "").strip() or visible_user(user_id=rid),
                "rank": int(r[1]),
                "floor": int(r[2]),
                "col": int(r[3]),
                "power": int(float(r[4])),
                "me": rid == uid,
            })
        return {"ranking": rows}
    finally:
        _put_connection(conn)


def _json_body(raw: bytes) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def mobile_api(method: str, path: str, headers: Dict[str, str], raw_body: bytes) -> Tuple[int, Dict[str, Any]]:
    """Return (HTTP status, JSON-serializable payload)."""
    body = _json_body(raw_body)
    method = method.upper()
    # Public link endpoints.
    if path == "/saocb-app/api/v1/health" and method == "GET":
        return 200, {"ok": True, "version": "1.0", "economy": "pipesos=memory_diamonds"}
    if path == "/saocb-app/api/v1/link/start" and method == "POST":
        try:
            return 200, begin_link(body.get("device_id", ""))
        except ValueError as e:
            return 400, {"error": str(e)}
    if path == "/saocb-app/api/v1/link/claim" and method == "POST":
        try:
            return 200, claim_link(body.get("device_id", ""), body.get("code", ""))
        except ValueError as e:
            return 400, {"error": str(e)}

    uid = authenticate(headers)
    if uid is None:
        return 401, {"error": "unauthorized"}
    _ensure_player(uid)

    if path == "/saocb-app/api/v1/logout" and method == "POST":
        revoke_token(headers)
        return 200, {"ok": True}
    if path == "/saocb-app/api/v1/home" and method == "GET":
        return 200, _home(uid)
    if path == "/saocb-app/api/v1/profile" and method == "GET":
        return 200, {"player": _brief_player(uid), "unit_count": len(_user_units(uid)), "party": _party(uid)}
    if path == "/saocb-app/api/v1/profile/name" and method == "POST":
        msg = _set_aincrad_name(uid, str(body.get("name", "")))
        ok = msg.startswith("✅")
        return (200 if ok else 400), {"ok": ok, "message": msg, "player": _brief_player(uid)}
    if path == "/saocb-app/api/v1/units" and method == "GET":
        return 200, _units_payload(uid)
    if path == "/saocb-app/api/v1/party" and method == "GET":
        hp, atk, de, power, party = _party_stats(uid)
        return 200, {"party": party, "hp": hp, "atk": atk, "def": de, "power": power}
    if path == "/saocb-app/api/v1/party/set" and method == "POST":
        try:
            slot, unit_id = int(body.get("slot", 0)), int(body.get("unit_id", 0))
        except Exception:
            return 400, {"error": "bad_request"}
        if slot not in (1, 2, 3):
            return 400, {"error": "slot_invalid"}
        msg = _set_party_slot(uid, slot, unit_id)
        hp, atk, de, power, party = _party_stats(uid)
        return 200, {"message": msg, "party": party, "hp": hp, "atk": atk, "def": de, "power": power}
    if path == "/saocb-app/api/v1/scout" and method == "GET":
        p = _player(uid)
        return 200, {
            "banner": "Aincrad Standard",
            "rates": {"2": 55, "3": 30, "4": 12, "5": 3},
            "single_cost": SINGLE_COST,
            "multi_cost": MULTI_COST,
            "guaranteed_multi": "4★+",
            "pipesos": p["md"],
            "fragments": p["fragments"],
        }
    if path == "/saocb-app/api/v1/scout/draw" and method == "POST":
        try:
            count = int(body.get("count", 1))
        except Exception:
            count = 1
        if count not in (1, 11):
            return 400, {"error": "count_invalid"}
        ok, msg, results = _gacha(uid, count)
        if not ok:
            return 409, {"error": "insufficient_funds", "message": msg, "player": _brief_player(uid)}
        out = []
        for unit, dup in results:
            out.append({**unit, "duplicate": bool(dup)})
        p = _player(uid)
        return 200, {"results": out, "pipesos": p["md"], "fragments": p["fragments"], "player": _brief_player(uid)}
    if path == "/saocb-app/api/v1/quests" and method == "GET":
        return 200, _quests_payload(uid)
    if path == "/saocb-app/api/v1/quest/start" and method == "POST":
        try:
            qid = int(body.get("quest_id", 0))
        except Exception:
            return 400, {"error": "bad_request"}
        q = _quest(qid)
        p = _player(uid)
        if not q or int(q["floor"]) > int(p["floor"]) + 10:
            return 403, {"error": "quest_locked"}
        ok, msg = _start_battle(uid, qid)
        if not ok:
            return 409, {"error": "battle_start_failed", "message": msg}
        return 200, _battle_payload(uid, "⚔️ Entraste al combate.")
    if path == "/saocb-app/api/v1/battle" and method == "GET":
        return 200, _battle_payload(uid)
    if path == "/saocb-app/api/v1/battle/action" and method == "POST":
        action = str(body.get("action", "")).lower()
        if action not in _ALLOWED_ACTIONS:
            return 400, {"error": "action_invalid"}
        note, _ = _battle_action(uid, action)
        return 200, _battle_payload(uid, note)
    if path == "/saocb-app/api/v1/upgrade" and method == "POST":
        try:
            unit_id = int(body.get("unit_id", 0))
        except Exception:
            return 400, {"error": "bad_request"}
        msg = _upgrade_unit(uid, unit_id)
        return 200, {"message": msg, **_units_payload(uid)}
    if path == "/saocb-app/api/v1/daily" and method == "POST":
        ok, msg = _claim_daily(uid)
        return 200, {"claimed": ok, "message": msg, "player": _brief_player(uid)}
    if path == "/saocb-app/api/v1/ranking" and method == "GET":
        return 200, _ranking(uid)

    return 404, {"error": "not_found"}
