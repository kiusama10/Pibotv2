from datetime import datetime
from zoneinfo import ZoneInfo
from src.database.database import _get_connection, _put_connection

MX=ZoneInfo('America/Mexico_City')

def grant_christmas_once(now=None):
    local=(now or datetime.now(MX)).astimezone(MX)
    if not (local.month==12 and local.day==25): return None
    key=f"navidad_{local.year}_25000"
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (key,)); c.execute("SELECT 1 FROM global_events_tb WHERE event_key=%s",(key,))
        if c.fetchone():conn.rollback();return None
        # One SQL update: existing registered users receive exactly one grant for this event.
        c.execute("UPDATE usuarios_tb SET saldo=saldo+25000")
        affected=c.rowcount; total=affected*25000
        c.execute("INSERT INTO global_events_tb(event_key,afectados,total_pipesos) VALUES(%s,%s,%s)",(key,affected,total));conn.commit();return affected
    except Exception as e:
        conn.rollback();print('[GLOBAL EVENT]',e);return None
    finally:_put_connection(conn)

async def seasonal_event_tick(context):
    affected=grant_christmas_once()
    if affected:
        print(f'[NAVIDAD] 25,000 PiPesos acreditados una sola vez a {affected} usuarios registrados.')
