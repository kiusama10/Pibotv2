import os, secrets, time, json, sqlite3
from saocb_persistence import restore_once, connect as durable_sqlite_connect
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Request, HTTPException, Header
from pydantic import BaseModel, Field
import httpx

BOT_TOKEN=os.getenv('TELEGRAM_BOT_TOKEN','')
API_SECRET=os.getenv('SAOCB_API_SECRET','')
WEBHOOK_SECRET=os.getenv('TELEGRAM_WEBHOOK_SECRET','')
DB_PATH=os.getenv('SAOCB_DB_PATH','/tmp/saocb.db')
PIBOT_API_URL=os.getenv('PIBOT_API_URL','').rstrip('/')
PIBOT_API_SECRET=os.getenv('PIBOT_API_SECRET','')
DATABASE_URL=os.getenv('DATABASE_URL','').strip()
TG=f"https://api.telegram.org/bot{BOT_TOKEN}" if BOT_TOKEN else ''
restore_once()
app=FastAPI(title='SAO-CB Bridge',version='1.0-protected')

# IMPORTANT: real character IDs are configured from the game data; no fake Halloween IDs.
def ints_env(name):
    raw=os.getenv(name,'').strip()
    if not raw:return []
    try:return [int(x.strip()) for x in raw.split(',') if x.strip()]
    except:return []

BANNERS={
 'halloween-2026':{
  'id':'halloween-2026','name':'Halloween 2026','cost_single':10000,'cost_multi':50000,'multi_count':10,'currency':'PiPesos',
  'active_from':'2026-10-01T00:00:00Z','active_until':'2026-11-05T23:59:59Z',
  'pool':ints_env('HALLOWEEN_POOL'),'featured':ints_env('HALLOWEEN_FEATURED'),
  'rates_source':'original-banner-required'
 }
}

def db():
 c=durable_sqlite_connect(DB_PATH); c.row_factory=sqlite3.Row
 c.executescript('''
 CREATE TABLE IF NOT EXISTS profiles(game_user TEXT PRIMARY KEY, rank INTEGER DEFAULT 1, tutorial_step INTEGER DEFAULT 0, releases TEXT DEFAULT '[]');
 CREATE TABLE IF NOT EXISTS links(code TEXT PRIMARY KEY, game_user TEXT NOT NULL, expires INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS telegram_links(telegram_id TEXT PRIMARY KEY, game_user TEXT UNIQUE NOT NULL);
 CREATE TABLE IF NOT EXISTS inventory(game_user TEXT NOT NULL, character_id INTEGER NOT NULL, copies INTEGER DEFAULT 1, PRIMARY KEY(game_user,character_id));
 CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY AUTOINCREMENT, game_user TEXT NOT NULL, delta INTEGER NOT NULL, reason TEXT, source TEXT, created_at INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS local_balance(game_user TEXT PRIMARY KEY, pipesos INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS gacha_log(id INTEGER PRIMARY KEY AUTOINCREMENT, game_user TEXT,banner_id TEXT,character_id INTEGER,cost INTEGER,created_at INTEGER);
 CREATE TABLE IF NOT EXISTS reward_claims(claim_id TEXT PRIMARY KEY,game_user TEXT,delta INTEGER,reason TEXT,created_at INTEGER);
 CREATE TABLE IF NOT EXISTS materials(game_user TEXT NOT NULL, material_id TEXT NOT NULL, amount INTEGER DEFAULT 0, PRIMARY KEY(game_user,material_id));
 CREATE TABLE IF NOT EXISTS upgrades(game_user TEXT NOT NULL, target_type TEXT NOT NULL, target_id TEXT NOT NULL, level INTEGER DEFAULT 1, skill_level INTEGER DEFAULT 1, PRIMARY KEY(game_user,target_type,target_id));
 CREATE TABLE IF NOT EXISTS pvp_rating(game_user TEXT PRIMARY KEY, rating INTEGER DEFAULT 1000, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, streak INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS event_progress(game_user TEXT NOT NULL,event_id TEXT NOT NULL,points INTEGER DEFAULT 0,clears INTEGER DEFAULT 0,PRIMARY KEY(game_user,event_id));
 CREATE TABLE IF NOT EXISTS friends(game_user TEXT NOT NULL,friend_user TEXT NOT NULL,status TEXT DEFAULT 'pending',PRIMARY KEY(game_user,friend_user));
 CREATE TABLE IF NOT EXISTS support_character(game_user TEXT PRIMARY KEY,character_id INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS guilds(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT UNIQUE NOT NULL,owner_user TEXT NOT NULL,points INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS guild_members(guild_id INTEGER NOT NULL,game_user TEXT UNIQUE NOT NULL,role TEXT DEFAULT 'member',contribution INTEGER DEFAULT 0,PRIMARY KEY(guild_id,game_user));
 CREATE TABLE IF NOT EXISTS global_bosses(id TEXT PRIMARY KEY,name TEXT NOT NULL,max_hp INTEGER NOT NULL,current_hp INTEGER NOT NULL,phase INTEGER DEFAULT 1,status TEXT DEFAULT 'active',starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,version INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS boss_damage(boss_id TEXT NOT NULL,game_user TEXT NOT NULL,damage INTEGER DEFAULT 0,hits INTEGER DEFAULT 0,last_hit_at INTEGER DEFAULT 0,PRIMARY KEY(boss_id,game_user));
 CREATE TABLE IF NOT EXISTS boss_battles(battle_id TEXT PRIMARY KEY,boss_id TEXT NOT NULL,game_user TEXT NOT NULL,damage INTEGER NOT NULL,created_at INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS boss_rewards(boss_id TEXT NOT NULL,game_user TEXT NOT NULL,reward_type TEXT NOT NULL,claimed INTEGER DEFAULT 0,PRIMARY KEY(boss_id,game_user,reward_type));
 CREATE TABLE IF NOT EXISTS world_goals(id TEXT PRIMARY KEY,name TEXT NOT NULL,target INTEGER NOT NULL,current INTEGER DEFAULT 0,status TEXT DEFAULT 'active',starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS world_goal_contrib(goal_id TEXT NOT NULL,game_user TEXT NOT NULL,amount INTEGER DEFAULT 0,PRIMARY KEY(goal_id,game_user));
 CREATE TABLE IF NOT EXISTS achievements(game_user TEXT NOT NULL,achievement_id TEXT NOT NULL,unlocked_at INTEGER NOT NULL,PRIMARY KEY(game_user,achievement_id));
 CREATE TABLE IF NOT EXISTS state_snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT,game_user TEXT NOT NULL,reason TEXT NOT NULL,state_json TEXT NOT NULL,created_at INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS legacy_sessions(session_id TEXT PRIMARY KEY,game_user TEXT NOT NULL,quest_id INTEGER DEFAULT 0,state TEXT DEFAULT 'started',started_at INTEGER NOT NULL,finished_at INTEGER DEFAULT 0,result_json TEXT DEFAULT '{}');
 CREATE TABLE IF NOT EXISTS legacy_idempotency(request_id TEXT PRIMARY KEY,path TEXT NOT NULL,response_json TEXT NOT NULL,created_at INTEGER NOT NULL);
 CREATE TABLE IF NOT EXISTS legacy_user_state(game_user TEXT PRIMARY KEY, player_name TEXT DEFAULT 'Kirito', exp INTEGER DEFAULT 0, col INTEGER DEFAULT 0, memory_diamonds INTEGER DEFAULT 0, area_id INTEGER DEFAULT 0, world_id INTEGER DEFAULT 0, current_party_id INTEGER DEFAULT 1, last_quest_id INTEGER DEFAULT 0, updated_at INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS legacy_user_characters(game_user TEXT NOT NULL, character_id INTEGER NOT NULL, level INTEGER DEFAULT 1, exp INTEGER DEFAULT 0, main INTEGER DEFAULT 0, PRIMARY KEY(game_user,character_id));
 CREATE TABLE IF NOT EXISTS legacy_user_equipment(game_user TEXT NOT NULL, equipment_id INTEGER NOT NULL, level INTEGER DEFAULT 1, exp INTEGER DEFAULT 0, equipped_character_id INTEGER DEFAULT 0, PRIMARY KEY(game_user,equipment_id));
 CREATE TABLE IF NOT EXISTS legacy_user_parties(game_user TEXT NOT NULL, party_id INTEGER NOT NULL, slot INTEGER NOT NULL, character_id INTEGER DEFAULT 0, PRIMARY KEY(game_user,party_id,slot));
 CREATE TABLE IF NOT EXISTS legacy_quest_progress(game_user TEXT NOT NULL, quest_id INTEGER NOT NULL, clear_count INTEGER DEFAULT 0, best_rank INTEGER DEFAULT 0, last_clear_at INTEGER DEFAULT 0, PRIMARY KEY(game_user,quest_id));
 CREATE TABLE IF NOT EXISTS legacy_user_titles(game_user TEXT NOT NULL,title_id TEXT NOT NULL,title_name TEXT NOT NULL,equipped INTEGER DEFAULT 0,granted_at INTEGER NOT NULL,PRIMARY KEY(game_user,title_id));
 CREATE TABLE IF NOT EXISTS starter_grants(game_user TEXT PRIMARY KEY,package_id TEXT NOT NULL,granted_at INTEGER NOT NULL);
 '''); return c

def ensure_user(c,gu):
 c.execute('INSERT OR IGNORE INTO profiles(game_user) VALUES(?)',(gu,)); c.execute('INSERT OR IGNORE INTO local_balance(game_user) VALUES(?)',(gu,)); c.execute('INSERT OR IGNORE INTO pvp_rating(game_user) VALUES(?)',(gu,))
 c.execute('INSERT OR IGNORE INTO legacy_user_state(game_user,updated_at) VALUES(?,?)',(gu,int(time.time())))

STARTER_PACKAGE_ID='saocb-launch-v1'
STARTER_CHARACTER_ID=11001  # verified present in user-provided character.bin catalog
STARTER_PIPESOS=10000
STARTER_TITLE_ID='saocb_pioneer'
STARTER_TITLE_NAME='Pionero de Aincrad'

def grant_starter(c,gu):
 # Atomic/idempotent SAO-CB welcome pack. Never grants twice.
 if c.execute('SELECT 1 FROM starter_grants WHERE game_user=?',(gu,)).fetchone():
  return False
 now=int(time.time())
 c.execute('INSERT INTO legacy_user_characters(game_user,character_id,level,exp,main) VALUES(?,?,1,0,1) ON CONFLICT(game_user,character_id) DO UPDATE SET main=1',(gu,STARTER_CHARACTER_ID))
 c.execute('INSERT INTO legacy_user_parties(game_user,party_id,slot,character_id) VALUES(?,1,1,?) ON CONFLICT(game_user,party_id,slot) DO UPDATE SET character_id=excluded.character_id',(gu,STARTER_CHARACTER_ID))
 c.execute('INSERT INTO inventory(game_user,character_id,copies) VALUES(?,?,1) ON CONFLICT(game_user,character_id) DO NOTHING',(gu,STARTER_CHARACTER_ID))
 c.execute('UPDATE local_balance SET pipesos=pipesos+? WHERE game_user=?',(STARTER_PIPESOS,gu))
 c.execute('INSERT INTO ledger(game_user,delta,reason,source,created_at) VALUES(?,?,?,?,?)',(gu,STARTER_PIPESOS,'Paquete de inicio SAO-CB','starter',now))
 c.execute('INSERT INTO legacy_user_titles(game_user,title_id,title_name,equipped,granted_at) VALUES(?,?,?,?,?)',(gu,STARTER_TITLE_ID,STARTER_TITLE_NAME,1,now))
 c.execute('INSERT INTO starter_grants(game_user,package_id,granted_at) VALUES(?,?,?)',(gu,STARTER_PACKAGE_ID,now))
 return True

def auth(secret):
 if API_SECRET and secret!=API_SECRET: raise HTTPException(401,'bad secret')

def active(b):
 now=datetime.now(timezone.utc); a=datetime.fromisoformat(b['active_from'].replace('Z','+00:00')); z=datetime.fromisoformat(b['active_until'].replace('Z','+00:00'))
 return a<=now<=z

async def tg(method,payload):
 if not TG:return None
 async with httpx.AsyncClient(timeout=15) as h:
  r=await h.post(f'{TG}/{method}',json=payload); return r.json()

async def pibot(method,telegram_id,amount=0,reason=''):
 """Single source of truth: PiBot when PIBOT_API_URL is configured. Expected API:
 GET  /saocb/economy/{telegram_id} -> {pipesos:int}
 POST /saocb/economy/change -> {telegram_id,delta,reason} -> {pipesos:int}
 """
 if not PIBOT_API_URL:return None
 headers={'X-PiBot-Secret':PIBOT_API_SECRET} if PIBOT_API_SECRET else {}
 async with httpx.AsyncClient(timeout=15) as h:
  if method=='get':r=await h.get(f'{PIBOT_API_URL}/saocb/economy/{telegram_id}',headers=headers)
  else:r=await h.post(f'{PIBOT_API_URL}/saocb/economy/change',headers=headers,json={'telegram_id':telegram_id,'delta':amount,'reason':reason})
  if r.status_code>=400:raise HTTPException(502,f'PiBot economy error {r.status_code}')
  data=r.json(); return int(data['pipesos'])

def _pibot_pg_change(telegram_id:str, delta:int, op_id:str):
    """Atomic/idempotent PiPesos mutation in PiBot PostgreSQL."""
    if not DATABASE_URL: return None
    import psycopg2
    pg=psycopg2.connect(DATABASE_URL,sslmode='require',connect_timeout=10)
    try:
        with pg.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS saocb_economy_ops(op_id TEXT PRIMARY KEY,telegram_id BIGINT NOT NULL,delta BIGINT NOT NULL,created_at BIGINT NOT NULL)")
            cur.execute("SELECT delta FROM saocb_economy_ops WHERE op_id=%s",(op_id,))
            old=cur.fetchone()
            if old is None:
                if delta>=0:
                    cur.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(delta,int(telegram_id)))
                else:
                    cur.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s AND saldo >= %s",(delta,int(telegram_id),-delta))
                if cur.rowcount!=1: pg.rollback(); raise HTTPException(402,'PiBot user missing or insufficient PiPesos')
                cur.execute("INSERT INTO saocb_economy_ops(op_id,telegram_id,delta,created_at) VALUES(%s,%s,%s,%s)",(op_id,int(telegram_id),delta,int(time.time())))
            cur.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s",(int(telegram_id),)); row=cur.fetchone()
            if not row: pg.rollback(); raise HTTPException(404,'PiBot user not found')
            pg.commit(); return int(row[0])
    finally:
        pg.close()

def _pibot_pg_balance(telegram_id:str):
    if not DATABASE_URL:return None
    import psycopg2
    pg=psycopg2.connect(DATABASE_URL,sslmode='require',connect_timeout=10)
    try:
        with pg.cursor() as cur:
            cur.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s",(int(telegram_id),)); row=cur.fetchone(); return int(row[0]) if row else None
    finally: pg.close()

def _migrate_starter_to_pibot(game_user:str,telegram_id:str):
    """Move the one-time local starter credit into PiBot exactly once."""
    with db() as c:
        ensure_user(c,game_user); row=c.execute('SELECT pipesos FROM local_balance WHERE game_user=?',(game_user,)).fetchone(); amount=int(row[0]) if row else 0
    if amount<=0:return _pibot_pg_balance(telegram_id)
    bal=_pibot_pg_change(telegram_id,amount,f'starter-migrate:{game_user}')
    # Safe after PG commit: if this local zeroing fails, retry uses same PG op_id and cannot double-credit.
    with db() as c:c.execute('UPDATE local_balance SET pipesos=0 WHERE game_user=?',(game_user,))
    return bal

async def linked_tid(game_user):
 with db() as c:r=c.execute('SELECT telegram_id FROM telegram_links WHERE game_user=?',(game_user,)).fetchone()
 return r['telegram_id'] if r else None

async def balance(game_user):
 tid=await linked_tid(game_user)
 if tid:
  direct=_pibot_pg_balance(tid)
  if direct is not None:return direct
  if PIBOT_API_URL:return await pibot('get',tid)
 with db() as c:
  ensure_user(c,game_user); return int(c.execute('SELECT pipesos FROM local_balance WHERE game_user=?',(game_user,)).fetchone()[0])

async def change_balance(game_user,delta,reason,source='SAO-CB'):
 tid=await linked_tid(game_user)
 if tid and DATABASE_URL:newbal=_pibot_pg_change(tid,delta,f'{source}:{game_user}:{int(time.time()*1000)}:{secrets.token_hex(4)}')
 elif tid and PIBOT_API_URL:newbal=await pibot('change',tid,delta,reason)
 else:
  with db() as c:
   ensure_user(c,game_user); old=int(c.execute('SELECT pipesos FROM local_balance WHERE game_user=?',(game_user,)).fetchone()[0])
   if old+delta<0:raise HTTPException(402,f'not enough PiPesos: {old}/{abs(delta)}')
   c.execute('UPDATE local_balance SET pipesos=pipesos+? WHERE game_user=?',(delta,game_user)); newbal=old+delta
 with db() as c:c.execute('INSERT INTO ledger(game_user,delta,reason,source,created_at) VALUES(?,?,?,?,?)',(game_user,delta,reason,source,int(time.time())))
 return newbal

class LinkRequest(BaseModel):game_user:str
class SyncRequest(BaseModel):game_user:str; rank:int|None=None; tutorial_step:int|None=None; releases:list[int]=Field(default_factory=list)
class RewardRequest(BaseModel):game_user:str; pipesos:int=0; reason:str=''; claim_id:str|None=None
class GachaRequest(BaseModel):game_user:str; banner_id:str='halloween-2026'; count:int=1


# Seasonal calendar. Events rotate automatically by date; content IDs stay configurable
# until mapped to real event.bin/event_quest_2.bin records.
SEASONAL_EVENTS=[
 {'id':'halloween-opening','name':'Halloween: Apertura','month':10,'day':1,'duration_days':7,'reward_pipesos':3000},
 {'id':'halloween-hunt','name':'Halloween: Cacería','month':10,'day':8,'duration_days':7,'reward_pipesos':5000},
 {'id':'halloween-boss','name':'Halloween: Boss','month':10,'day':15,'duration_days':10,'reward_pipesos':8000},
 {'id':'day-of-the-dead','name':'Día de Muertos','month':10,'day':25,'duration_days':12,'reward_pipesos':10000},
]

def seasonal_window(e, year=None):
 now=datetime.now(timezone.utc); year=year or now.year
 start=datetime(year,e['month'],e['day'],tzinfo=timezone.utc); end=start+timedelta(days=e['duration_days'])
 return start,end

def current_events():
 now=datetime.now(timezone.utc); out=[]
 for e in SEASONAL_EVENTS:
  a,z=seasonal_window(e)
  if a<=now<z: out.append(e|{'active_from':a.isoformat(),'active_until':z.isoformat()})
 return out

class UpgradeRequest(BaseModel):
 game_user:str; target_type:str; target_id:str; levels:int=1
class SkillRequest(BaseModel):
 game_user:str; target_type:str='character'; target_id:str; levels:int=1
class PvPResult(BaseModel):
 game_user:str; won:bool; opponent_rating:int=1000
class EventClear(BaseModel):
 game_user:str; event_id:str; points:int=1; claim_id:str|None=None

@app.get('/game/events/current')
def events_current(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); return {'ok':True,'events':current_events()}

@app.post('/game/event/clear')
async def event_clear(body:EventClear,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); ev=next((x for x in current_events() if x['id']==body.event_id),None)
 if not ev: raise HTTPException(409,'event inactive')
 with db() as c:
  ensure_user(c,body.game_user)
  c.execute('INSERT INTO event_progress(game_user,event_id,points,clears) VALUES(?,?,?,1) ON CONFLICT(game_user,event_id) DO UPDATE SET points=points+excluded.points,clears=clears+1',(body.game_user,body.event_id,max(0,body.points)))
 # modest repeat reward; final quest tables can override this once mapped.
 gain=min(2000,250+max(0,body.points)*50)
 bal=await change_balance(body.game_user,gain,f'Evento {ev["name"]}','event')
 return {'ok':True,'event':ev['id'],'earned_pipesos':gain,'pipesos':bal}

@app.post('/game/forge/upgrade')
def forge_upgrade(body:UpgradeRequest,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 if body.levels<1 or body.levels>10: raise HTTPException(400,'levels 1..10')
 with db() as c:
  ensure_user(c,body.game_user)
  r=c.execute('SELECT level FROM upgrades WHERE game_user=? AND target_type=? AND target_id=?',(body.game_user,body.target_type,body.target_id)).fetchone(); old=int(r[0]) if r else 1
  new=min(100,old+body.levels)
  # Col/material costs will be switched to the original tables after their exact fields are mapped.
  c.execute('INSERT INTO upgrades(game_user,target_type,target_id,level,skill_level) VALUES(?,?,?,?,1) ON CONFLICT(game_user,target_type,target_id) DO UPDATE SET level=excluded.level',(body.game_user,body.target_type,body.target_id,new))
 return {'ok':True,'target_id':body.target_id,'level_before':old,'level':new}

@app.post('/game/skills/upgrade')
def skill_upgrade(body:SkillRequest,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 if body.levels<1 or body.levels>10: raise HTTPException(400,'levels 1..10')
 with db() as c:
  ensure_user(c,body.game_user)
  r=c.execute('SELECT level,skill_level FROM upgrades WHERE game_user=? AND target_type=? AND target_id=?',(body.game_user,body.target_type,body.target_id)).fetchone(); level=int(r[0]) if r else 1; old=int(r[1]) if r else 1; new=min(10,old+body.levels)
  c.execute('INSERT INTO upgrades(game_user,target_type,target_id,level,skill_level) VALUES(?,?,?,?,?) ON CONFLICT(game_user,target_type,target_id) DO UPDATE SET skill_level=excluded.skill_level',(body.game_user,body.target_type,body.target_id,level,new))
 return {'ok':True,'target_id':body.target_id,'skill_before':old,'skill_level':new}

@app.get('/game/pvp/opponent/{game_user}')
def pvp_opponent(game_user:str,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:
  ensure_user(c,game_user); me=int(c.execute('SELECT rating FROM pvp_rating WHERE game_user=?',(game_user,)).fetchone()[0])
  rows=c.execute('SELECT game_user,rating,wins,losses FROM pvp_rating WHERE game_user<>? ORDER BY ABS(rating-?) LIMIT 12',(game_user,me)).fetchall()
 if rows:
  # Prefer a close human snapshot. Randomized choice prevents a permanently predictable opponent.
  r=secrets.choice(rows[:min(5,len(rows))]); return {'ok':True,'type':'player_snapshot','opponent':dict(r),'ai_difficulty':'adaptive'}
 # No human yet: AI scales around the player's rating and is intentionally not a pushover.
 jitter=secrets.randbelow(161)-60
 return {'ok':True,'type':'ai','opponent':{'game_user':'SAO-CB_AI','rating':max(800,me+jitter)},'ai_difficulty':'adaptive'}

@app.post('/game/pvp/result')
async def pvp_result(body:PvPResult,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:
  ensure_user(c,body.game_user); r=c.execute('SELECT rating,wins,losses,streak FROM pvp_rating WHERE game_user=?',(body.game_user,)).fetchone(); rating,w,l,st=map(int,r)
  expected=1/(1+10**((body.opponent_rating-rating)/400)); score=1 if body.won else 0; new=max(100,int(round(rating+24*(score-expected))))
  if body.won: w+=1; st+=1
  else: l+=1; st=0
  c.execute('UPDATE pvp_rating SET rating=?,wins=?,losses=?,streak=? WHERE game_user=?',(new,w,l,st,body.game_user))
 gain=750 if body.won else 150
 bal=await change_balance(body.game_user,gain,'PvP victoria' if body.won else 'PvP participación','pvp')
 return {'ok':True,'rating_before':rating,'rating':new,'wins':w,'losses':l,'streak':st,'earned_pipesos':gain,'pipesos':bal}


CATALOG_PATH=os.path.join(os.path.dirname(__file__),'data','catalog_raw.json')
def load_catalog():
 try:
  with open(CATALOG_PATH,'r',encoding='utf-8') as f:return json.load(f)
 except Exception:return {'sources':{}}

@app.get('/game/catalog/summary')
def catalog_summary(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); c=load_catalog()
 return {'ok':True,'sources':{k:{'record_count':v.get('record_count',0),'size':v.get('size',0)} for k,v in c.get('sources',{}).items()}}

@app.get('/game/catalog/{kind}/{record_id}')
def catalog_record(kind:str,record_id:int,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); c=load_catalog(); src=c.get('sources',{}).get(kind+'.bin')
 if not src: raise HTTPException(404,'catalog type not found')
 for r in src.get('records',[]):
  if r.get('id')==record_id:return {'ok':True,'record':r}
 raise HTTPException(404,'record not found')

class FriendRequest(BaseModel): game_user:str; friend_user:str
class SupportRequest(BaseModel): game_user:str; character_id:int
class GuildCreate(BaseModel): game_user:str; name:str
class GuildJoin(BaseModel): game_user:str; guild_id:int

@app.post('/game/friends/request')
def friend_request(body:FriendRequest,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 if body.game_user==body.friend_user: raise HTTPException(400,'cannot friend yourself')
 with db() as c:
  ensure_user(c,body.game_user);ensure_user(c,body.friend_user)
  c.execute("INSERT INTO friends(game_user,friend_user,status) VALUES(?,?,'pending') ON CONFLICT(game_user,friend_user) DO NOTHING",(body.game_user,body.friend_user))
 return {'ok':True}

@app.post('/game/friends/accept')
def friend_accept(body:FriendRequest,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:
  r=c.execute("UPDATE friends SET status='accepted' WHERE game_user=? AND friend_user=?",(body.friend_user,body.game_user))
  if not r.rowcount: raise HTTPException(404,'request not found')
  c.execute("INSERT INTO friends(game_user,friend_user,status) VALUES(?,?,'accepted') ON CONFLICT(game_user,friend_user) DO UPDATE SET status='accepted'",(body.game_user,body.friend_user))
 return {'ok':True}

@app.get('/game/friends/{game_user}')
def friends_list(game_user:str,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c: rows=c.execute("SELECT friend_user,status FROM friends WHERE game_user=? ORDER BY status,friend_user",(game_user,)).fetchall()
 return {'ok':True,'friends':[dict(x) for x in rows]}

@app.post('/game/support/set')
def support_set(body:SupportRequest,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:
  own=c.execute('SELECT 1 FROM inventory WHERE game_user=? AND character_id=?',(body.game_user,body.character_id)).fetchone()
  if not own: raise HTTPException(409,'character not owned')
  c.execute('INSERT INTO support_character(game_user,character_id) VALUES(?,?) ON CONFLICT(game_user) DO UPDATE SET character_id=excluded.character_id',(body.game_user,body.character_id))
 return {'ok':True}

@app.get('/game/support/options/{game_user}')
def support_options(game_user:str,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:
  rows=c.execute("SELECT f.friend_user,s.character_id FROM friends f JOIN support_character s ON s.game_user=f.friend_user WHERE f.game_user=? AND f.status='accepted'",(game_user,)).fetchall()
 return {'ok':True,'supports':[dict(x) for x in rows]}

@app.post('/game/guild/create')
def guild_create(body:GuildCreate,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); name=body.name.strip()
 if not (3<=len(name)<=24): raise HTTPException(400,'guild name length 3..24')
 with db() as c:
  if c.execute('SELECT 1 FROM guild_members WHERE game_user=?',(body.game_user,)).fetchone(): raise HTTPException(409,'already in guild')
  try:r=c.execute('INSERT INTO guilds(name,owner_user) VALUES(?,?)',(name,body.game_user))
  except sqlite3.IntegrityError: raise HTTPException(409,'guild name exists')
  gid=r.lastrowid;c.execute("INSERT INTO guild_members(guild_id,game_user,role) VALUES(?,?,'owner')",(gid,body.game_user))
 return {'ok':True,'guild_id':gid,'name':name}

@app.post('/game/guild/join')
def guild_join(body:GuildJoin,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:
  if not c.execute('SELECT 1 FROM guilds WHERE id=?',(body.guild_id,)).fetchone(): raise HTTPException(404,'guild not found')
  if c.execute('SELECT 1 FROM guild_members WHERE game_user=?',(body.game_user,)).fetchone(): raise HTTPException(409,'already in guild')
  c.execute("INSERT INTO guild_members(guild_id,game_user,role) VALUES(?,?,'member')",(body.guild_id,body.game_user))
 return {'ok':True}

@app.get('/game/guild/{guild_id}')
def guild_info(guild_id:int,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:
  g=c.execute('SELECT * FROM guilds WHERE id=?',(guild_id,)).fetchone()
  if not g: raise HTTPException(404,'guild not found')
  m=c.execute('SELECT game_user,role,contribution FROM guild_members WHERE guild_id=? ORDER BY contribution DESC',(guild_id,)).fetchall()
 return {'ok':True,'guild':dict(g),'members':[dict(x) for x in m]}

@app.get('/health')
def health():return {'ok':True,'service':'SAO-CB Bridge','version':'1.0-protected','economy':'PiBot-PostgreSQL' if DATABASE_URL else ('PiBot-API' if PIBOT_API_URL else 'local-dev')}

@app.post('/game/link/start')
def link_start(body:LinkRequest,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); code=f'{secrets.randbelow(1000000):06d}'; exp=int(time.time())+600
 with db() as c:ensure_user(c,body.game_user); c.execute('DELETE FROM links WHERE game_user=?',(body.game_user,)); c.execute('INSERT INTO links VALUES(?,?,?)',(code,body.game_user,exp))
 return {'ok':True,'code':code,'expires_in':600}

@app.get('/game/link/status/{game_user}')
def link_status(game_user:str,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:r=c.execute('SELECT telegram_id FROM telegram_links WHERE game_user=?',(game_user,)).fetchone()
 return {'ok':True,'linked':bool(r)}

@app.post('/game/sync')
async def sync(body:SyncRequest,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:
  ensure_user(c,body.game_user); old=c.execute('SELECT * FROM profiles WHERE game_user=?',(body.game_user,)).fetchone(); rank=body.rank if body.rank is not None else old['rank']; step=body.tutorial_step if body.tutorial_step is not None else old['tutorial_step']; rel=body.releases if body.releases else json.loads(old['releases']); c.execute('UPDATE profiles SET rank=?,tutorial_step=?,releases=? WHERE game_user=?',(rank,step,json.dumps(rel),body.game_user))
 return {'ok':True,'rank':rank,'tutorial_step':step,'releases':rel,'pipesos':await balance(body.game_user)}

@app.get('/game/state/{game_user}')
async def state(game_user:str,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:
  ensure_user(c,game_user); p=c.execute('SELECT * FROM profiles WHERE game_user=?',(game_user,)).fetchone(); inv=[dict(x) for x in c.execute('SELECT character_id,copies FROM inventory WHERE game_user=?',(game_user,))]
 return {'ok':True,'profile':dict(p)|{'releases':json.loads(p['releases']),'pipesos':await balance(game_user)},'inventory':inv}

@app.post('/admin/reward')
async def reward(body:RewardRequest,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 if body.claim_id:
  with db() as c:
   if c.execute('SELECT 1 FROM reward_claims WHERE claim_id=?',(body.claim_id,)).fetchone():return {'ok':True,'duplicate':True,'pipesos':await balance(body.game_user)}
   c.execute('INSERT INTO reward_claims VALUES(?,?,?,?,?)',(body.claim_id,body.game_user,body.pipesos,body.reason,int(time.time())))
 bal=await change_balance(body.game_user,body.pipesos,body.reason or 'Recompensa','reward')
 tid=await linked_tid(body.game_user)
 if tid:await tg('sendMessage',{'chat_id':tid,'text':f'⚔️ SAO-CB: {body.pipesos:+,} PiPesos'+(f' — {body.reason}' if body.reason else '')+f'\nSaldo: {bal:,}'})
 return {'ok':True,'pipesos':bal}

@app.get('/game/gacha/banners')
def banners(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); out=[]
 for b in BANNERS.values():out.append({k:v for k,v in b.items() if k not in ('pool','featured')}|{'active':active(b),'ready':bool(b['pool'])})
 return {'ok':True,'banners':out}

def draw_character(b):
 if not b['pool']:raise HTTPException(503,'Halloween pool not configured with real character IDs')
 feat=[x for x in b['featured'] if x in b['pool']]; reg=[x for x in b['pool'] if x not in feat] or b['pool']; isf=bool(feat) and secrets.randbelow(100)<b['rates']['featured']; return secrets.choice(feat if isf else reg),isf

@app.post('/game/gacha/draw')
async def gacha(body:GachaRequest,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); b=BANNERS.get(body.banner_id)
 if not b or not active(b): raise HTTPException(404,'banner unavailable')
 if not b['pool']: raise HTTPException(503,'banner pool not mapped to verified game IDs')
 if body.count not in (1,10): raise HTTPException(400,'count must be 1 or 10')
 cost=b['cost_single'] if body.count==1 else b['cost_multi']
 bal=await balance(body.game_user)
 if bal<cost: raise HTTPException(402,f'not enough PiPesos: {bal}/{cost}')
 # IMPORTANT: exact original banner rates must be mapped before production. No invented rates.
 if not b.get('original_rate_table'):
  raise HTTPException(503,'original banner probabilities not mapped yet')
 results=[draw_character(b) for _ in range(body.count)]
 newbal=await change_balance(body.game_user,-cost,f'Gacha {b["name"]} x{body.count}','gacha')
 try:
  with db() as c:
   ensure_user(c,body.game_user)
   for cid,featured in results:
    c.execute('INSERT INTO inventory(game_user,character_id,copies) VALUES(?,?,1) ON CONFLICT(game_user,character_id) DO UPDATE SET copies=copies+1',(body.game_user,cid))
    c.execute('INSERT INTO gacha_log(game_user,banner_id,character_id,cost,created_at) VALUES(?,?,?,?,?)',(body.game_user,b['id'],cid,0,int(time.time())))
 except Exception:
  await change_balance(body.game_user,cost,f'Reembolso gacha {b["name"]}','gacha-refund')
  raise
 return {'ok':True,'banner_id':b['id'],'results':[{'character_id':x[0],'featured':x[1]} for x in results],'count':body.count,'cost':cost,'pipesos':newbal}

@app.post('/telegram/webhook')
async def webhook(req:Request,x_telegram_bot_api_secret_token:str|None=Header(default=None)):
 if WEBHOOK_SECRET and x_telegram_bot_api_secret_token!=WEBHOOK_SECRET:raise HTTPException(401,'bad telegram secret')
 u=await req.json(); m=u.get('message') or {}; text=(m.get('text') or '').strip(); tid=str((m.get('chat') or {}).get('id',''))
 if not tid:return {'ok':True}
 if text.startswith('/start'):await tg('sendMessage',{'chat_id':tid,'text':'⚔️ SAO-CB conectado. /vincular CODIGO · /estado · /gacha'})
 elif text.startswith('/vincular'):
  code=(text.split(maxsplit=1)+[''])[1].strip()
  with db() as c:
   r=c.execute('SELECT game_user,expires FROM links WHERE code=?',(code,)).fetchone()
   if r and r['expires']>=int(time.time()):
    gu_link=str(r['game_user']); c.execute('DELETE FROM telegram_links WHERE telegram_id=? OR game_user=?',(tid,gu_link)); c.execute('INSERT INTO telegram_links VALUES(?,?)',(tid,gu_link)); c.execute('DELETE FROM links WHERE code=?',(code,)); msg=f'✅ Partida SAO-CB vinculada: {gu_link}'
   else: gu_link=None; msg='Código inválido o vencido.'
  if gu_link and DATABASE_URL:
   try:
    migrated_balance=_migrate_starter_to_pibot(gu_link,tid); msg+=f'\n💰 PiPesos compartidos: {migrated_balance:,}'
   except Exception as exc: msg+=f'\n⚠️ Vinculado; saldo inicial pendiente de sincronización ({type(exc).__name__}).'
  await tg('sendMessage',{'chat_id':tid,'text':msg})
 elif text=='/estado':await tg('sendMessage',{'chat_id':tid,'text':await status_text(tid)})
 elif text=='/gacha':
  with db() as c:l=c.execute('SELECT game_user FROM telegram_links WHERE telegram_id=?',(tid,)).fetchone()
  if not l:msg='Primero vincula tu partida con /vincular CODIGO.'
  else:
   try:
    msg='🎃 Scout SAO-CB: 10,000 individual / 50,000 multi. Las probabilidades originales deben estar mapeadas antes de habilitar tiradas.'
   except HTTPException as e:msg=f'🎃 Gacha: {e.detail}'
  await tg('sendMessage',{'chat_id':tid,'text':msg})
 return {'ok':True}

# --- SAO-MD Legacy Adapter / compatibility probe layer ---
# The client-facing wire envelope is still being reconstructed. These handlers now
# implement persistent semantics instead of fake stateless placeholders; every call
# is also captured so the exact original wire schema can be matched from a real run.
ORIGINAL_TUTORIAL_RELEASES=[4702,4703,4707,4711,604,4706,4704,4711,1007,4705,4710,4711,4712,4713,4711]

def legacy_user_from_request(request:Request, body):
    if isinstance(body,dict):
        for k in ('game_user','user_id','userId','id'):
            if body.get(k) not in (None,''): return str(body[k])
    for k in ('x-saocb-user','x-user-id'):
        if request.headers.get(k): return request.headers[k]
    return '1'

def legacy_envelope(result=None,status=200):
    return {'status':status,'result':result if result is not None else {}}

@app.api_route('/api', methods=['GET','POST','HEAD'])
@app.api_route('/api/', methods=['GET','POST','HEAD'])
async def legacy_api_root():
    # Stable public base probe. Keeping this alive also makes Render/base-URL
    # checks distinguishable from an application 404.
    return {'status':200,'result':{'ok':True,'service':'SAO-CB','adapter':'legacy'}}

@app.api_route('/api/{path:path}', methods=['GET','POST','PUT','PATCH','DELETE'])
async def original_api_probe(path:str, request:Request):
    raw=await request.body()
    try: body=json.loads(raw.decode('utf-8')) if raw else {}
    except Exception: body={'raw_hex':raw[:2048].hex(),'size':len(raw)}
    headers={k:v for k,v in request.headers.items() if k.lower() in ('content-type','accept','accept-language','user-agent','authorization','x-requested-with','x-saocb-user','x-user-id','x-request-id')}
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS client_probe(id INTEGER PRIMARY KEY AUTOINCREMENT,method TEXT,path TEXT,body TEXT,headers TEXT,created_at INTEGER)')
        c.execute('INSERT INTO client_probe(method,path,body,headers,created_at) VALUES(?,?,?,?,?)',(request.method,path,json.dumps(body,ensure_ascii=False),json.dumps(headers,ensure_ascii=False),int(time.time())))
    gu=legacy_user_from_request(request,body)
    rid=request.headers.get('x-request-id') or (body.get('request_id') if isinstance(body,dict) else None)
    if rid:
        with db() as c:
            old=c.execute('SELECT response_json FROM legacy_idempotency WHERE request_id=?',(str(rid),)).fetchone()
            if old:return json.loads(old['response_json'])

    response=None
    # Persistent user-state surfaces used by RealDriver. Wire field names are kept
    # deliberately simple until the exact original parser schema is proven.
    # RealDriver::fetchUserAll is slot 44. Binary analysis confirms request flags
    # x_uid/sub_character/is_search/is_dungeon/is_sortie. The exact retail envelope
    # is still under reconstruction, but user/{uid} is an original route and is
    # therefore exposed as one aggregate state surface instead of fabricated data.
    import re as _re
    _user_aggregate = _re.fullmatch(r'user/([^/]+)', path)
    # Retail boot route recovered from the client: master/start.
    # Keep the old 'start' alias for backward compatibility with earlier SAO-CB builds.
    # RealDriver's success callback consumes post, ptoken and prealtime; server_time is also present.
    if path in ('master/start','start'):
        response=legacy_envelope({'post':False,'ptoken':'','prealtime':False,'server_time':int(time.time())},200)
    elif _user_aggregate and _user_aggregate.group(1) not in ('register','comment','characters','equipment','current-party','cleared-quests','last-quest','world','area','quest'):
        route_user=str(_user_aggregate.group(1))
        if route_user not in ('{0}',): gu=route_user
        with db() as c:
            ensure_user(c,gu)
            st=dict(c.execute('SELECT * FROM legacy_user_state WHERE game_user=?',(gu,)).fetchone())
            chars=[dict(x) for x in c.execute('SELECT * FROM legacy_user_characters WHERE game_user=? ORDER BY main DESC,character_id',(gu,))]
            equips=[dict(x) for x in c.execute('SELECT * FROM legacy_user_equipment WHERE game_user=? ORDER BY equipment_id',(gu,))]
            parties=[dict(x) for x in c.execute('SELECT * FROM legacy_user_parties WHERE game_user=? ORDER BY party_id,slot',(gu,))]
            progress=[dict(x) for x in c.execute('SELECT * FROM legacy_quest_progress WHERE game_user=? ORDER BY quest_id',(gu,))]
            titles=[dict(x) for x in c.execute('SELECT title_id,title_name,equipped FROM legacy_user_titles WHERE game_user=? ORDER BY granted_at',(gu,))]
        # RealDriver::fetchUserAll success callback ($_33 @ 0x1359184) reads
        # these exact cocos2d::ValueMap keys.  Keep the older plural aliases for
        # our own diagnostics, but expose the retail singular names too.
        party_ids=sorted({int(x['party_id']) for x in parties})
        current_party=[x for x in parties if int(x['party_id'])==int(st.get('current_party_id') or 1)]
        user_wire=dict(st)
        user_wire.update({
            'info': {
                'id': str(gu),
                'user_id': str(gu),
                'rank': int(st.get('rank') or 1),
            },
            'data': {
                'world_id': int(st.get('world_id') or 0),
                'area_id': int(st.get('area_id') or 0),
                'last_quest_id': int(st.get('last_quest_id') or 0),
            },
            # Some User fields are read from the parent map as well as info/data.
            'id': str(gu),
            'user_id': str(gu),
            'rank': int(st.get('rank') or 1),
        })
        retail={
            'user': user_wire,
            'title': titles,
            'party_ids': party_ids,
            'extra_party': [],
            'party': current_party,
            'equipment': equips,
            'character': chars,
            'item': [],
            'function_lock': [],
            # Diagnostic/forward-compatible state retained for SAO-CB services.
            'characters': chars,
            'parties': parties,
            'quest_progress': progress,
        }
        response=legacy_envelope(retail,200)
    elif path in ('user/characters','user/equipment','user/current-party','user/cleared-quests','user/last-quest','user/world','user/area','user/quest') or (path.startswith('user/') and path.endswith('/profile')):
        with db() as c:
            ensure_user(c,gu)
            st=dict(c.execute('SELECT * FROM legacy_user_state WHERE game_user=?',(gu,)).fetchone())
            prof=dict(c.execute('SELECT * FROM profiles WHERE game_user=?',(gu,)).fetchone())
            if path=='user/characters': result={'characters':[dict(x) for x in c.execute('SELECT * FROM legacy_user_characters WHERE game_user=? ORDER BY main DESC,character_id',(gu,))]}
            elif path=='user/equipment': result={'equipment':[dict(x) for x in c.execute('SELECT * FROM legacy_user_equipment WHERE game_user=? ORDER BY equipment_id',(gu,))]}
            elif path=='user/current-party': result={'party_id':st['current_party_id'],'members':[dict(x) for x in c.execute('SELECT slot,character_id FROM legacy_user_parties WHERE game_user=? AND party_id=? ORDER BY slot',(gu,st['current_party_id']))]}
            elif path=='user/cleared-quests': result={'quests':[dict(x) for x in c.execute('SELECT quest_id,clear_count,best_rank,last_clear_at FROM legacy_quest_progress WHERE game_user=? AND clear_count>0 ORDER BY quest_id',(gu,))]}
            elif path=='user/last-quest': result={'quest_id':st['last_quest_id']}
            elif path=='user/world': result={'world_id':st['world_id']}
            elif path=='user/area': result={'area_id':st['area_id']}
            elif path=='user/quest': result={'last_quest_id':st['last_quest_id'],'progress':[dict(x) for x in c.execute('SELECT * FROM legacy_quest_progress WHERE game_user=? ORDER BY quest_id',(gu,))]}
            else: result={'user':st,'profile':prof}
        response=legacy_envelope(result,200)
    elif path=='user/register':
        # DummyDriver virtual slot 16 returns success=true and status 200.
        with db() as c:
            ensure_user(c,gu)
            fresh=grant_starter(c,gu)
        response=legacy_envelope({'ok':True,'user_id':gu,'starter_granted':fresh,'starter_package':STARTER_PACKAGE_ID},200)
    elif path=='tutorial/start':
        with db() as c:
            ensure_user(c,gu); c.execute('UPDATE profiles SET tutorial_step=0 WHERE game_user=?',(gu,))
        response=legacy_envelope({'ok':True,'tutorial_step':0},200)
    elif path=='tutorial/step':
        step=int(body.get('tutorial_step',body.get('step',0))) if isinstance(body,dict) else 0
        with db() as c:
            ensure_user(c,gu); old=c.execute('SELECT tutorial_step FROM profiles WHERE game_user=?',(gu,)).fetchone()[0]; step=max(int(old),step); c.execute('UPDATE profiles SET tutorial_step=? WHERE game_user=?',(step,gu))
        response=legacy_envelope({'ok':True,'tutorial_step':step},200)
    elif path=='tutorial/clear':
        step=int(body.get('tutorial_step',body.get('step',1))) if isinstance(body,dict) else 1
        with db() as c:
            ensure_user(c,gu); old=c.execute('SELECT tutorial_step FROM profiles WHERE game_user=?',(gu,)).fetchone()[0]; step=max(int(old),step); c.execute('UPDATE profiles SET tutorial_step=?,releases=? WHERE game_user=?',(step,json.dumps(ORIGINAL_TUTORIAL_RELEASES),gu))
        response=legacy_envelope({'ok':True,'tutorial_step':step},200)
    elif path=='tutorial/clear-evaluation':
        response=legacy_envelope({'ok':True},200)
    elif path=='tutorial/release':
        with db() as c:
            ensure_user(c,gu); row=c.execute('SELECT releases FROM profiles WHERE game_user=?',(gu,)).fetchone(); rel=json.loads(row['releases']) if row and row['releases'] else []
        response=legacy_envelope({'released_function':rel},200)
    elif path=='quest/start' or path=='quest/start-tutorial':
        qid=int(body.get('quest_id',body.get('questId',0))) if isinstance(body,dict) else 0
        sid=str(body.get('session_id') or body.get('battle_id') or secrets.token_hex(12)) if isinstance(body,dict) else secrets.token_hex(12)
        with db() as c:
            ensure_user(c,gu); c.execute('INSERT OR IGNORE INTO legacy_sessions(session_id,game_user,quest_id,state,started_at) VALUES(?,?,?,?,?)',(sid,gu,qid,'started',int(time.time())))
        response=legacy_envelope({'ok':True,'session_id':sid,'quest_id':qid},200)
    elif path in ('quest/result','quest/result-party','quest/save'):
        sid=str(body.get('session_id') or body.get('battle_id') or '') if isinstance(body,dict) else ''
        qid=int(body.get('quest_id',body.get('questId',0))) if isinstance(body,dict) else 0
        if not sid: sid=f'{gu}:{qid}:legacy'
        now=int(time.time())
        with db() as c:
            ensure_user(c,gu)
            row=c.execute('SELECT state,result_json FROM legacy_sessions WHERE session_id=?',(sid,)).fetchone()
            if row and row['state']=='finished': result=json.loads(row['result_json'])
            else:
                result={'ok':True,'session_id':sid,'quest_id':qid,'cleared':True}
                c.execute('INSERT OR REPLACE INTO legacy_sessions(session_id,game_user,quest_id,state,started_at,finished_at,result_json) VALUES(?,?,?,?,?,?,?)',(sid,gu,qid,'finished',now,now,json.dumps(result)))
                c.execute('INSERT INTO legacy_quest_progress(game_user,quest_id,clear_count,best_rank,last_clear_at) VALUES(?,?,1,0,?) ON CONFLICT(game_user,quest_id) DO UPDATE SET clear_count=clear_count+1,last_clear_at=excluded.last_clear_at',(gu,qid,now))
                c.execute('UPDATE legacy_user_state SET last_quest_id=?,updated_at=? WHERE game_user=?',(qid,now,gu))
                c.execute('INSERT INTO state_snapshots(game_user,reason,state_json,created_at) VALUES(?,?,?,?)',(gu,f'quest:{qid}:clear',json.dumps({'quest_id':qid,'session_id':sid}),now))
            response=legacy_envelope(result,200)
    elif path=='lottery/active-list':
        response=legacy_envelope({'lotteries':[]},200)
    # Boot-safe compatibility surfaces.  These are all retail route names recovered
    # from the client.  Returning typed empty collections lets the old client reach
    # its parser without turning an unimplemented optional feed into HTTP failure.
    elif path=='tutorial/all':
        response=legacy_envelope({'tutorials':[],'released_function':[]},200)
    elif path=='tutorial/evaluation-enabled':
        response=legacy_envelope({'enabled':False},200)
    elif path=='user/all-quests':
        response=legacy_envelope({'quests':[]},200)
    elif path=='user/played-direction':
        response=legacy_envelope({'played_directions':[]},200)
    elif path=='user/diamond-shop/filter':
        response=legacy_envelope({'items':[],'diamonds':[]},200)
    elif path in ('quest/playable/filter','quest/playable/friend/filter'):
        response=legacy_envelope({'quests':[]},200)
    elif path=='quest/supporter':
        response=legacy_envelope({'supporters':[]},200)
    elif path=='quest/detail':
        response=legacy_envelope({'quest':{}},200)
    elif path=='event/all':
        response=legacy_envelope({'events':[]},200)
    elif path in ('mission/daily','mission/daily/all','mission/normal','mission/normal/all'):
        response=legacy_envelope({'missions':[]},200)
    if response is None: response={'status':501,'error':'SAO-CB route captured','path':path}
    if rid:
        with db() as c:c.execute('INSERT OR IGNORE INTO legacy_idempotency(request_id,path,response_json,created_at) VALUES(?,?,?,?)',(str(rid),path,json.dumps(response),int(time.time())))
    return response

@app.get('/admin/probe/recent')
def probe_recent(limit:int=100,x_saocb_secret:str|None=Header(default=None)):
    auth(x_saocb_secret); limit=max(1,min(500,limit))
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS client_probe(id INTEGER PRIMARY KEY AUTOINCREMENT,method TEXT,path TEXT,body TEXT,headers TEXT,created_at INTEGER)')
        rows=c.execute('SELECT * FROM client_probe ORDER BY id DESC LIMIT ?',(limit,)).fetchall()
    return {'ok':True,'calls':[dict(r) for r in rows]}

# --- SAO-CB Global Boss / World systems ---
class BossCreate(BaseModel):
 id:str; name:str; max_hp:int=Field(gt=0); duration_hours:int=Field(default=72,ge=1,le=720)
class BossHit(BaseModel):
 game_user:str; battle_id:str; damage:int=Field(gt=0)
class GoalCreate(BaseModel):
 id:str; name:str; target:int=Field(gt=0); duration_hours:int=Field(default=168,ge=1,le=2160)
class GoalContrib(BaseModel):
 game_user:str; amount:int=Field(gt=0)

def boss_phase(hp,max_hp):
 pct=(hp*100/max_hp) if max_hp else 0
 return 1 if pct>70 else (2 if pct>30 else 3)

def snapshot_user(c,game_user,reason):
 ensure_user(c,game_user)
 p=dict(c.execute('SELECT * FROM profiles WHERE game_user=?',(game_user,)).fetchone())
 inv=[dict(x) for x in c.execute('SELECT character_id,copies FROM inventory WHERE game_user=?',(game_user,))]
 state={'profile':p,'inventory':inv}
 c.execute('INSERT INTO state_snapshots(game_user,reason,state_json,created_at) VALUES(?,?,?,?)',(game_user,reason,json.dumps(state,ensure_ascii=False),int(time.time())))
 return state

@app.post('/admin/boss/create')
def boss_create(body:BossCreate,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); now=int(time.time()); end=now+body.duration_hours*3600
 with db() as c:
  c.execute('INSERT OR REPLACE INTO global_bosses(id,name,max_hp,current_hp,phase,status,starts_at,ends_at,version) VALUES(?,?,?,?,1,\'active\',?,?,0)',(body.id,body.name,body.max_hp,body.max_hp,now,end))
 return {'ok':True,'boss_id':body.id,'hp':body.max_hp,'phase':1}

@app.get('/game/boss/current')
def boss_current(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); now=int(time.time())
 with db() as c:
  r=c.execute("SELECT * FROM global_bosses WHERE status='active' AND starts_at<=? AND ends_at>=? ORDER BY starts_at DESC LIMIT 1",(now,now)).fetchone()
  if not r:return {'ok':True,'boss':None}
  b=dict(r); b['hp_percent']=round(100*b['current_hp']/b['max_hp'],4)
  top=[dict(x) for x in c.execute('SELECT game_user,damage,hits FROM boss_damage WHERE boss_id=? ORDER BY damage DESC LIMIT 10',(b['id'],))]
 return {'ok':True,'boss':b,'top':top}

@app.post('/game/boss/hit')
async def boss_hit(body:BossHit,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); now=int(time.time())
 touch_player(body.game_user)
 with db() as c:
  ensure_user(c,body.game_user)
  prior=c.execute('SELECT damage FROM boss_battles WHERE battle_id=?',(body.battle_id,)).fetchone()
  if prior:return {'ok':True,'duplicate':True,'accepted_damage':int(prior['damage'])}
  b=c.execute("SELECT * FROM global_bosses WHERE status='active' AND starts_at<=? AND ends_at>=? ORDER BY starts_at DESC LIMIT 1",(now,now)).fetchone()
  if not b:raise HTTPException(404,'no active global boss')
  # Hard anti-overflow ceiling. Later this is replaced by validation against battle/action logs.
  cap=max(1,int(b['max_hp'])//20); accepted=min(body.damage,cap,int(b['current_hp']))
  if accepted<=0:raise HTTPException(409,'boss already defeated')
  newhp=int(b['current_hp'])-accepted; phase=boss_phase(newhp,int(b['max_hp'])); status='defeated' if newhp==0 else 'active'
  c.execute('INSERT INTO boss_battles VALUES(?,?,?,?,?)',(body.battle_id,b['id'],body.game_user,accepted,now))
  c.execute('INSERT INTO boss_damage(boss_id,game_user,damage,hits,last_hit_at) VALUES(?,?,?,1,?) ON CONFLICT(boss_id,game_user) DO UPDATE SET damage=damage+excluded.damage,hits=hits+1,last_hit_at=excluded.last_hit_at',(b['id'],body.game_user,accepted,now))
  c.execute('UPDATE global_bosses SET current_hp=?,phase=?,status=?,version=version+1 WHERE id=?',(newhp,phase,status,b['id']))
  if status=='defeated':
   c.execute('INSERT OR IGNORE INTO achievements VALUES(?,?,?)',(body.game_user,'GLOBAL_BOSS_FINAL_HIT',now))
   c.execute('INSERT OR IGNORE INTO hall_of_fame(category,event_id,game_user,value,metadata_json,created_at) VALUES(?,?,?,?,?,?)',('final_hit',b['id'],body.game_user,accepted,json.dumps({'boss_name':b['name']},ensure_ascii=False),now))
  leader=c.execute('SELECT game_user,damage FROM boss_damage WHERE boss_id=? ORDER BY damage DESC LIMIT 1',(b['id'],)).fetchone()
 return {'ok':True,'boss_id':b['id'],'accepted_damage':accepted,'remaining_hp':newhp,'phase':phase,'defeated':newhp==0,'final_hit':newhp==0,'leader':dict(leader) if leader else None}

@app.get('/game/boss/{boss_id}/ranking')
def boss_ranking(boss_id:str,limit:int=50,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); limit=max(1,min(100,limit))
 with db() as c: rows=c.execute('SELECT game_user,damage,hits,last_hit_at FROM boss_damage WHERE boss_id=? ORDER BY damage DESC LIMIT ?',(boss_id,limit)).fetchall()
 return {'ok':True,'boss_id':boss_id,'ranking':[dict(x) for x in rows]}

@app.post('/admin/world-goal/create')
def world_goal_create(body:GoalCreate,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); now=int(time.time())
 with db() as c:c.execute("INSERT OR REPLACE INTO world_goals(id,name,target,current,status,starts_at,ends_at) VALUES(?,?,?,0,'active',?,?)",(body.id,body.name,body.target,now,now+body.duration_hours*3600))
 return {'ok':True,'goal_id':body.id,'target':body.target}

@app.post('/game/world-goal/{goal_id}/contribute')
def world_goal_contribute(goal_id:str,body:GoalContrib,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); now=int(time.time())
 with db() as c:
  g=c.execute("SELECT * FROM world_goals WHERE id=? AND status='active' AND starts_at<=? AND ends_at>=?",(goal_id,now,now)).fetchone()
  if not g:raise HTTPException(404,'world goal inactive')
  add=min(body.amount,max(0,int(g['target'])-int(g['current']))); cur=int(g['current'])+add; status='complete' if cur>=int(g['target']) else 'active'
  c.execute('UPDATE world_goals SET current=?,status=? WHERE id=?',(cur,status,goal_id))
  c.execute('INSERT INTO world_goal_contrib(goal_id,game_user,amount) VALUES(?,?,?) ON CONFLICT(goal_id,game_user) DO UPDATE SET amount=amount+excluded.amount',(goal_id,body.game_user,add))
 return {'ok':True,'goal_id':goal_id,'accepted':add,'current':cur,'target':int(g['target']),'complete':status=='complete'}

@app.post('/admin/snapshot/{game_user}')
def create_snapshot(game_user:str,reason:str='manual',x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c: state=snapshot_user(c,game_user,reason)
 return {'ok':True,'game_user':game_user,'reason':reason,'state':state}

# --- SAO-CB Operations / Event Director / Aincrad ---
ADMIN_TELEGRAM_IDS={x.strip() for x in os.getenv('SAOCB_ADMIN_TELEGRAM_IDS','').split(',') if x.strip()}

def ops_schema():
 with db() as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS player_activity(game_user TEXT PRIMARY KEY,last_seen INTEGER NOT NULL,actions INTEGER DEFAULT 0);
  CREATE TABLE IF NOT EXISTS live_events(id TEXT PRIMARY KEY,name TEXT NOT NULL,event_type TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'scheduled',starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,difficulty TEXT DEFAULT 'auto',reward_mode TEXT DEFAULT 'original',config_json TEXT DEFAULT '{}',created_by TEXT DEFAULT 'system');
  CREATE TABLE IF NOT EXISTS hall_of_fame(id INTEGER PRIMARY KEY AUTOINCREMENT,category TEXT NOT NULL,event_id TEXT NOT NULL,game_user TEXT NOT NULL,value INTEGER DEFAULT 0,metadata_json TEXT DEFAULT '{}',created_at INTEGER NOT NULL,UNIQUE(category,event_id,game_user));
  CREATE TABLE IF NOT EXISTS aincrad_state(key TEXT PRIMARY KEY,value TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY AUTOINCREMENT,message TEXT NOT NULL,starts_at INTEGER NOT NULL,ends_at INTEGER NOT NULL,created_by TEXT DEFAULT 'system');
  ''')
  c.execute("INSERT OR IGNORE INTO aincrad_state(key,value) VALUES('floor','1')")
ops_schema()

def touch_player(game_user,actions=1):
 now=int(time.time())
 with db() as c:
  c.execute('INSERT INTO player_activity(game_user,last_seen,actions) VALUES(?,?,?) ON CONFLICT(game_user) DO UPDATE SET last_seen=excluded.last_seen,actions=actions+excluded.actions',(game_user,now,max(0,actions)))

def active_players(days=7):
 cutoff=int(time.time())-max(1,days)*86400
 with db() as c:return int(c.execute('SELECT COUNT(*) FROM player_activity WHERE last_seen>=?',(cutoff,)).fetchone()[0])

def recommended_quest_goal(players=None):
 p=active_players() if players is None else max(0,int(players))
 # Designed for a small community: eight clears per active player, bounded.
 return max(40,min(1200,p*8 if p else 40))

def event_tick(now=None):
 now=int(time.time()) if now is None else int(now)
 with db() as c:
  c.execute("UPDATE live_events SET status='active' WHERE status='scheduled' AND starts_at<=? AND ends_at>?",(now,now))
  c.execute("UPDATE live_events SET status='ended' WHERE status IN ('scheduled','active') AND ends_at<=?",(now,))
  return {r['status']:r['n'] for r in c.execute('SELECT status,COUNT(*) n FROM live_events GROUP BY status')}

class LiveEventCreate(BaseModel):
 id:str; name:str; event_type:str; starts_at:int|None=None; duration_hours:int=Field(default=24,ge=1,le=2160); difficulty:str='auto'; reward_mode:str='original'; config:dict=Field(default_factory=dict); created_by:str='admin'

@app.post('/admin/event/create')
def live_event_create(body:LiveEventCreate,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); now=int(time.time()); start=body.starts_at if body.starts_at is not None else now; end=start+body.duration_hours*3600; status='active' if start<=now<end else ('ended' if end<=now else 'scheduled')
 with db() as c:c.execute('INSERT OR REPLACE INTO live_events(id,name,event_type,status,starts_at,ends_at,difficulty,reward_mode,config_json,created_by) VALUES(?,?,?,?,?,?,?,?,?,?)',(body.id,body.name,body.event_type,status,start,end,body.difficulty,body.reward_mode,json.dumps(body.config,ensure_ascii=False),body.created_by))
 return {'ok':True,'event_id':body.id,'status':status,'starts_at':start,'ends_at':end}

@app.get('/game/live-events')
def live_events(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); event_tick(); now=int(time.time())
 with db() as c:rows=c.execute("SELECT * FROM live_events WHERE status='active' AND starts_at<=? AND ends_at>? ORDER BY starts_at",(now,now)).fetchall()
 out=[]
 for r in rows:
  d=dict(r); d['config']=json.loads(d.pop('config_json') or '{}'); out.append(d)
 return {'ok':True,'events':out}

@app.post('/admin/event/{event_id}/stop')
def live_event_stop(event_id:str,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:c.execute("UPDATE live_events SET status='ended',ends_at=? WHERE id=?",(int(time.time()),event_id))
 return {'ok':True,'event_id':event_id,'status':'ended'}

@app.get('/admin/activity')
def activity_report(days:int=7,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); p=active_players(days)
 return {'ok':True,'days':days,'active_players':p,'recommended_quest_goal':recommended_quest_goal(p)}

@app.get('/game/aincrad')
def aincrad_get(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:floor=int(c.execute("SELECT value FROM aincrad_state WHERE key='floor'").fetchone()[0])
 return {'ok':True,'floor':floor}

@app.post('/admin/aincrad/advance')
def aincrad_advance(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:
  floor=int(c.execute("SELECT value FROM aincrad_state WHERE key='floor'").fetchone()[0]); new=min(100,floor+1); c.execute("UPDATE aincrad_state SET value=? WHERE key='floor'",(str(new),))
 return {'ok':True,'old_floor':floor,'floor':new,'complete':new>=100}

@app.get('/game/hall-of-fame')
def hall_of_fame(limit:int=100,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); limit=max(1,min(500,limit))
 with db() as c:rows=c.execute('SELECT category,event_id,game_user,value,metadata_json,created_at FROM hall_of_fame ORDER BY id DESC LIMIT ?',(limit,)).fetchall()
 out=[]
 for r in rows:
  d=dict(r); d['metadata']=json.loads(d.pop('metadata_json') or '{}'); out.append(d)
 return {'ok':True,'records':out}

@app.get('/game/announcements')
def announcements(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); now=int(time.time())
 with db() as c:rows=c.execute('SELECT id,message,starts_at,ends_at FROM announcements WHERE starts_at<=? AND ends_at>? ORDER BY id DESC',(now,now)).fetchall()
 return {'ok':True,'announcements':[dict(x) for x in rows]}

# Stable operations endpoint for the future Telegram button UI.
@app.get('/admin/status')
def admin_status(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); counts=event_tick(); p=active_players()
 with db() as c:
  boss=c.execute("SELECT id,name,current_hp,max_hp,phase,status FROM global_bosses WHERE status='active' ORDER BY starts_at DESC LIMIT 1").fetchone(); floor=int(c.execute("SELECT value FROM aincrad_state WHERE key='floor'").fetchone()[0])
 return {'ok':True,'active_players_7d':p,'recommended_quest_goal':recommended_quest_goal(p),'events':counts,'aincrad_floor':floor,'boss':dict(boss) if boss else None}

# --- SAO-CB Auto Director ---
def auto_schema():
 with db() as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS automation_settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
  CREATE TABLE IF NOT EXISTS server_history(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,ref_id TEXT NOT NULL,message TEXT NOT NULL,metadata_json TEXT DEFAULT '{}',created_at INTEGER NOT NULL);
  ''')
  defaults={'enabled':'1','events_enabled':'1','aincrad_enabled':'1','boss_enabled':'1','emergency_enabled':'1','target_event_hours':'48','cooldown_hours':'24'}
  for k,v in defaults.items(): c.execute('INSERT OR IGNORE INTO automation_settings(key,value) VALUES(?,?)',(k,v))
auto_schema()

def auto_settings():
 with db() as c:return {r['key']:r['value'] for r in c.execute('SELECT key,value FROM automation_settings')}

def set_auto_setting(key,value):
 with db() as c:c.execute('INSERT INTO automation_settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,str(value)))

def history(kind,ref_id,message,metadata=None):
 with db() as c:c.execute('INSERT INTO server_history(kind,ref_id,message,metadata_json,created_at) VALUES(?,?,?,?,?)',(kind,ref_id,message,json.dumps(metadata or {},ensure_ascii=False),int(time.time())))

def adaptive_boss_hp(players=None):
 p=active_players() if players is None else max(1,int(players))
 # Conservative placeholder until real battle damage telemetry exists: scales between 250k and 25m.
 return max(250_000,min(25_000_000,p*350_000))

def auto_director_tick(now=None):
 now=int(time.time()) if now is None else int(now); cfg=auto_settings(); event_tick(now)
 if cfg.get('enabled','1')!='1': return {'enabled':False,'actions':[]}
 actions=[]
 with db() as c:
  # Expire bosses whose window ended.
  c.execute("UPDATE global_bosses SET status='expired' WHERE status='active' AND ends_at<?",(now,))
  active_event=c.execute("SELECT id FROM live_events WHERE status='active' AND starts_at<=? AND ends_at>? LIMIT 1",(now,now)).fetchone()
  future_event=c.execute("SELECT id FROM live_events WHERE status='scheduled' AND starts_at>? LIMIT 1",(now,)).fetchone()
  boss=c.execute("SELECT id FROM global_bosses WHERE status='active' AND starts_at<=? AND ends_at>=? LIMIT 1",(now,now)).fetchone()
 # Never spam automatic content when an admin already has current/future programming.
 if cfg.get('events_enabled','1')=='1' and not active_event and not future_event:
  p=active_players(); goal=recommended_quest_goal(p); eid=f'auto-goal-{now}'
  duration=max(6,min(168,int(cfg.get('target_event_hours','48'))))
  with db() as c:
   c.execute("INSERT INTO live_events(id,name,event_type,status,starts_at,ends_at,difficulty,reward_mode,config_json,created_by) VALUES(?,?,?,'active',?,?,?,?,?,?)",(eid,'Misión comunitaria','world_goal',now,now+duration*3600,'auto','original',json.dumps({'target':goal,'metric':'quest_clear','active_players':p}), 'auto-director'))
   c.execute("INSERT INTO world_goals(id,name,target,current,status,starts_at,ends_at) VALUES(?,?,?,0,'active',?,?)",(eid,'Misión comunitaria',goal,now,now+duration*3600))
  history('auto_event',eid,'Auto Director inició una misión comunitaria',{'target':goal,'players':p}); actions.append({'type':'world_goal','id':eid,'target':goal})
 if cfg.get('boss_enabled','1')=='1' and not boss:
  # Boss creation is intentionally tied to a floor/event trigger, not spawned every tick.
  pass
 return {'enabled':True,'actions':actions,'active_players':active_players(),'recommended_quest_goal':recommended_quest_goal()}

@app.post('/admin/auto/state/{state}')
def auto_toggle(state:str,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); state=state.lower()
 if state not in ('on','off'): raise HTTPException(400,'state must be on or off')
 set_auto_setting('enabled','1' if state=='on' else '0'); return {'ok':True,'automatic':state=='on'}

@app.post('/admin/auto/tick')
def auto_tick_endpoint(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); return {'ok':True,**auto_director_tick()}

@app.get('/admin/auto/status')
def auto_status(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); return {'ok':True,'settings':auto_settings(),'active_players':active_players(),'recommended_quest_goal':recommended_quest_goal(),'recommended_boss_hp':adaptive_boss_hp()}

@app.get('/game/server-history')
def server_history(limit:int=100,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); limit=max(1,min(500,limit))
 with db() as c:rows=c.execute('SELECT kind,ref_id,message,metadata_json,created_at FROM server_history ORDER BY id DESC LIMIT ?',(limit,)).fetchall()
 out=[]
 for r in rows:
  d=dict(r); d['metadata']=json.loads(d.pop('metadata_json') or '{}'); out.append(d)
 return {'ok':True,'history':out}

# --- SAO-CB Release Center / automatic announcements / Telegram control bridge ---
def release_center_schema():
 with db() as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS releases(id TEXT PRIMARY KEY,version TEXT NOT NULL,title TEXT NOT NULL,notes TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'draft',publish_at INTEGER NOT NULL,created_at INTEGER NOT NULL,created_by TEXT DEFAULT 'system',announcement_id INTEGER);
  CREATE TABLE IF NOT EXISTS notification_log(id INTEGER PRIMARY KEY AUTOINCREMENT,kind TEXT NOT NULL,ref_id TEXT NOT NULL,channel TEXT NOT NULL,payload_json TEXT NOT NULL DEFAULT '{}',created_at INTEGER NOT NULL,UNIQUE(kind,ref_id,channel));
  ''')
  defaults={'announcements_enabled':'1','release_announcements_enabled':'1','event_announcements_enabled':'1','boss_announcements_enabled':'1','telegram_control_enabled':'1','announcement_hours':'72'}
  for k,v in defaults.items(): c.execute('INSERT OR IGNORE INTO automation_settings(key,value) VALUES(?,?)',(k,v))
release_center_schema()

def telegram_admin_guard(x_telegram_user_id):
 if not ADMIN_TELEGRAM_IDS: return True  # local/dev: API secret remains required by endpoints
 if not x_telegram_user_id or str(x_telegram_user_id) not in ADMIN_TELEGRAM_IDS: raise HTTPException(403,'telegram admin not allowed')
 return True

def create_announcement(message,starts_at=None,duration_hours=72,created_by='system',kind='manual',ref_id=''):
 now=int(time.time()); start=now if starts_at is None else int(starts_at); end=start+max(1,min(2160,int(duration_hours)))*3600
 with db() as c:
  cur=c.execute('INSERT INTO announcements(message,starts_at,ends_at,created_by) VALUES(?,?,?,?)',(message,start,end,created_by)); aid=cur.lastrowid
  if ref_id:
   c.execute('INSERT OR IGNORE INTO notification_log(kind,ref_id,channel,payload_json,created_at) VALUES(?,?,?,?,?)',(kind,ref_id,'in_game',json.dumps({'announcement_id':aid,'message':message},ensure_ascii=False),now))
 return {'id':aid,'message':message,'starts_at':start,'ends_at':end}

def notification_exists(kind,ref_id,channel='in_game'):
 with db() as c:return c.execute('SELECT 1 FROM notification_log WHERE kind=? AND ref_id=? AND channel=?',(kind,ref_id,channel)).fetchone() is not None

def release_tick(now=None):
 now=int(time.time()) if now is None else int(now); cfg=auto_settings(); actions=[]
 if cfg.get('announcements_enabled','1')!='1' or cfg.get('release_announcements_enabled','1')!='1': return actions
 hours=int(cfg.get('announcement_hours','72'))
 with db() as c: rows=c.execute("SELECT * FROM releases WHERE status='scheduled' AND publish_at<=? ORDER BY publish_at",(now,)).fetchall()
 for r in rows:
  rid=r['id']
  if not notification_exists('release',rid):
   msg=f"Actualización {r['version']}: {r['title']}"
   if r['notes']: msg += f"\n{r['notes']}"
   a=create_announcement(msg,now,hours,'auto-director','release',rid)
   with db() as c:c.execute("UPDATE releases SET status='published',announcement_id=? WHERE id=?",(a['id'],rid))
   history('release_published',rid,msg,{'version':r['version'],'announcement_id':a['id']}); actions.append({'type':'release_announcement','release_id':rid,'announcement_id':a['id']})
 return actions

def event_announcement_tick(now=None):
 now=int(time.time()) if now is None else int(now); cfg=auto_settings(); actions=[]
 if cfg.get('announcements_enabled','1')!='1' or cfg.get('event_announcements_enabled','1')!='1': return actions
 hours=int(cfg.get('announcement_hours','72'))
 with db() as c: rows=c.execute("SELECT id,name,event_type,ends_at FROM live_events WHERE status='active' AND starts_at<=? AND ends_at>?",(now,now)).fetchall()
 for r in rows:
  if not notification_exists('event_started',r['id']):
   a=create_announcement(f"Evento activo: {r['name']}",now,min(hours,max(1,(r['ends_at']-now+3599)//3600)),'auto-director','event_started',r['id'])
   history('event_announcement',r['id'],f"Evento activo: {r['name']}",{'announcement_id':a['id'],'event_type':r['event_type']}); actions.append({'type':'event_announcement','event_id':r['id'],'announcement_id':a['id']})
 return actions

class ReleaseCreate(BaseModel):
 id:str; version:str; title:str; notes:str=''; publish_at:int|None=None; created_by:str='admin'
class AnnouncementCreate(BaseModel):
 message:str=Field(min_length=1,max_length=2000); starts_at:int|None=None; duration_hours:int=Field(default=72,ge=1,le=2160); created_by:str='admin'

@app.post('/admin/release/create')
def release_create(body:ReleaseCreate,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); now=int(time.time()); pub=now if body.publish_at is None else int(body.publish_at); status='scheduled'
 with db() as c:c.execute('INSERT OR REPLACE INTO releases(id,version,title,notes,status,publish_at,created_at,created_by,announcement_id) VALUES(?,?,?,?,?,?,?,?,NULL)',(body.id,body.version,body.title,body.notes,status,pub,now,body.created_by))
 return {'ok':True,'release_id':body.id,'status':status,'publish_at':pub}

@app.post('/admin/announcement/create')
def announcement_create(body:AnnouncementCreate,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); return {'ok':True,'announcement':create_announcement(body.message,body.starts_at,body.duration_hours,body.created_by)}

@app.post('/admin/announcement/{announcement_id}/stop')
def announcement_stop(announcement_id:int,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); now=int(time.time())
 with db() as c:c.execute('UPDATE announcements SET ends_at=? WHERE id=?',(now,announcement_id))
 return {'ok':True,'announcement_id':announcement_id,'status':'ended'}

@app.post('/admin/notifications/tick')
def notifications_tick(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); return {'ok':True,'actions':release_tick()+event_announcement_tick()}

# Telegram-facing control API. PiBot can call these without changing existing /dar behavior.
@app.get('/telegram/admin/dashboard')
def telegram_dashboard(x_saocb_secret:str|None=Header(default=None),x_telegram_user_id:str|None=Header(default=None)):
 auth(x_saocb_secret); telegram_admin_guard(x_telegram_user_id); base=admin_status(x_saocb_secret)
 with db() as c:
  releases_n=c.execute("SELECT COUNT(*) FROM releases WHERE status='scheduled'").fetchone()[0]
  announcements_n=c.execute('SELECT COUNT(*) FROM announcements WHERE starts_at<=? AND ends_at>?',(int(time.time()),int(time.time()))).fetchone()[0]
 return {**base,'scheduled_releases':releases_n,'active_announcements':announcements_n,'auto':auto_settings()}

@app.post('/telegram/admin/auto/{state}')
def telegram_auto_toggle(state:str,x_saocb_secret:str|None=Header(default=None),x_telegram_user_id:str|None=Header(default=None)):
 auth(x_saocb_secret); telegram_admin_guard(x_telegram_user_id); return auto_toggle(state,x_saocb_secret)

@app.post('/telegram/admin/announcement')
def telegram_announcement(body:AnnouncementCreate,x_saocb_secret:str|None=Header(default=None),x_telegram_user_id:str|None=Header(default=None)):
 auth(x_saocb_secret); telegram_admin_guard(x_telegram_user_id); body.created_by=f'telegram:{x_telegram_user_id or "dev"}'; return announcement_create(body,x_saocb_secret)

@app.post('/telegram/admin/release')
def telegram_release(body:ReleaseCreate,x_saocb_secret:str|None=Header(default=None),x_telegram_user_id:str|None=Header(default=None)):
 auth(x_saocb_secret); telegram_admin_guard(x_telegram_user_id); body.created_by=f'telegram:{x_telegram_user_id or "dev"}'; return release_create(body,x_saocb_secret)

# Extend automatic director without changing its existing behavior.
_old_auto_director_tick=auto_director_tick
def auto_director_tick(now=None):
 result=_old_auto_director_tick(now); now2=int(time.time()) if now is None else int(now)
 extra=release_tick(now2)+event_announcement_tick(now2)
 result['notifications']=extra
 return result

# --- autonomous notification loop + Telegram operator commands ---
import asyncio
ANNOUNCE_CHAT_ID=os.getenv('SAOCB_TELEGRAM_ANNOUNCE_CHAT_ID','').strip()
AUTO_LOOP_SECONDS=max(60,int(os.getenv('SAOCB_AUTO_LOOP_SECONDS','300') or 300))
_auto_loop_task=None

async def deliver_telegram_notifications():
 if not BOT_TOKEN or not ANNOUNCE_CHAT_ID: return []
 delivered=[]
 # Mirror new in-game notifications to Telegram exactly once.
 with db() as c:
  rows=c.execute("SELECT kind,ref_id,payload_json FROM notification_log WHERE channel='in_game' ORDER BY id DESC LIMIT 100").fetchall()
 for r in reversed(rows):
  kind,ref_id=r['kind'],r['ref_id']
  if notification_exists(kind,ref_id,'telegram'): continue
  payload=json.loads(r['payload_json'] or '{}'); msg=payload.get('message')
  if not msg: continue
  await tg('sendMessage',{'chat_id':ANNOUNCE_CHAT_ID,'text':f'⚔️ SAO-CB\n{msg}'})
  with db() as c:c.execute('INSERT OR IGNORE INTO notification_log(kind,ref_id,channel,payload_json,created_at) VALUES(?,?,?,?,?)',(kind,ref_id,'telegram',json.dumps({'message':msg},ensure_ascii=False),int(time.time())))
  delivered.append({'kind':kind,'ref_id':ref_id})
 return delivered

async def autonomous_tick_once():
 data=auto_director_tick()
 data['telegram_delivered']=await deliver_telegram_notifications()
 return data

async def _autonomous_loop():
 while True:
  try: await autonomous_tick_once()
  except Exception as e:
   try: history('auto_error','loop','Auto loop error',{'error':str(e)[:500]})
   except Exception: pass
  await asyncio.sleep(AUTO_LOOP_SECONDS)

@app.on_event('startup')
async def start_saocb_autonomous_loop():
 global _auto_loop_task
 if _auto_loop_task is None or _auto_loop_task.done(): _auto_loop_task=asyncio.create_task(_autonomous_loop())

@app.on_event('shutdown')
async def stop_saocb_autonomous_loop():
 global _auto_loop_task
 if _auto_loop_task and not _auto_loop_task.done():
  _auto_loop_task.cancel()
  try: await _auto_loop_task
  except BaseException: pass

@app.post('/admin/auto/run-now')
async def auto_run_now(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); return {'ok':True,**(await autonomous_tick_once())}

# Additional commands handled directly by SAO-CB's Telegram webhook.
# PiBot's existing /dar remains untouched and is intentionally not reimplemented here.
_old_webhook=webhook
@app.post('/telegram/control-webhook')
async def control_webhook(req:Request,x_telegram_bot_api_secret_token:str|None=Header(default=None)):
 if WEBHOOK_SECRET and x_telegram_bot_api_secret_token!=WEBHOOK_SECRET: raise HTTPException(401,'bad telegram secret')
 u=await req.json(); m=u.get('message') or {}; text=(m.get('text') or '').strip(); tid=str((m.get('from') or {}).get('id') or (m.get('chat') or {}).get('id','')); chat_id=str((m.get('chat') or {}).get('id',''))
 if not text or not tid:return {'ok':True}
 if tid not in ADMIN_TELEGRAM_IDS:
  if text.startswith('/saocb') or text.startswith('/anuncio') or text.startswith('/actualizacion'): await tg('sendMessage',{'chat_id':chat_id,'text':'⛔ Comando exclusivo de administración SAO-CB.'})
  return {'ok':True}
 if text=='/saocb':
  d=admin_status(None); cfg=auto_settings(); msg=f"⚔️ SAO-CB\nAuto: {'ON' if cfg.get('enabled')=='1' else 'OFF'}\nActivos 7d: {d['active_players_7d']}\nAincrad: Piso {d['aincrad_floor']}\nMeta sugerida: {d['recommended_quest_goal']} quests"
  await tg('sendMessage',{'chat_id':chat_id,'text':msg})
 elif text in ('/saocb auto on','/saocb auto off'):
  state=text.rsplit(' ',1)[1]; set_auto_setting('enabled','1' if state=='on' else '0'); await tg('sendMessage',{'chat_id':chat_id,'text':f"🤖 Auto Director: {state.upper()}"})
 elif text.startswith('/anuncio '):
  msg=text.split(' ',1)[1].strip(); a=create_announcement(msg,None,72,f'telegram:{tid}','manual_tg',f'{tid}-{int(time.time())}'); await tg('sendMessage',{'chat_id':chat_id,'text':f"📢 Anuncio publicado. #{a['id']}"})
 elif text.startswith('/actualizacion '):
  raw=text.split(' ',1)[1].strip(); parts=raw.split('|',2)
  if len(parts)<2: await tg('sendMessage',{'chat_id':chat_id,'text':'Uso: /actualizacion VERSION | TÍTULO | NOTAS'})
  else:
   version,title=parts[0].strip(),parts[1].strip(); notes=parts[2].strip() if len(parts)>2 else ''; rid=f'rel-{version}-{int(time.time())}'
   now=int(time.time())
   with db() as c:c.execute('INSERT INTO releases(id,version,title,notes,status,publish_at,created_at,created_by) VALUES(?,?,?,?,?,?,?,?)',(rid,version,title,notes,'scheduled',now,now,f'telegram:{tid}'))
   release_tick(now); await deliver_telegram_notifications(); await tg('sendMessage',{'chat_id':chat_id,'text':f'✅ Actualización {version} publicada y anunciada.'})
 else: await tg('sendMessage',{'chat_id':chat_id,'text':'SAO-CB Admin: /saocb · /saocb auto on|off · /anuncio TEXTO · /actualizacion VERSION | TÍTULO | NOTAS'})
 return {'ok':True}

# --- SAO-CB Guardian: auto-maintenance, safe self-repair and update orchestration ---
def guardian_schema():
 with db() as c:
  c.executescript('''
  CREATE TABLE IF NOT EXISTS maintenance_state(id INTEGER PRIMARY KEY CHECK(id=1),enabled INTEGER NOT NULL DEFAULT 0,reason TEXT DEFAULT '',mode TEXT DEFAULT 'auto',started_at INTEGER DEFAULT 0,updated_at INTEGER DEFAULT 0);
  INSERT OR IGNORE INTO maintenance_state(id,enabled,reason,mode,started_at,updated_at) VALUES(1,0,'','auto',0,0);
  CREATE TABLE IF NOT EXISTS guardian_runs(id INTEGER PRIMARY KEY AUTOINCREMENT,status TEXT NOT NULL,checks_json TEXT NOT NULL,repairs_json TEXT NOT NULL,created_at INTEGER NOT NULL);
  CREATE TABLE IF NOT EXISTS update_state(id INTEGER PRIMARY KEY CHECK(id=1),current_version TEXT DEFAULT 'work100',target_version TEXT DEFAULT '',state TEXT DEFAULT 'idle',required INTEGER DEFAULT 0,notes TEXT DEFAULT '',updated_at INTEGER DEFAULT 0);
  INSERT OR IGNORE INTO update_state(id,current_version,target_version,state,required,notes,updated_at) VALUES(1,'work100','','idle',0,'',0);
  ''')
  for k,v in {'guardian_enabled':'1','auto_maintenance_enabled':'1','auto_repair_enabled':'1','auto_update_orchestration_enabled':'1'}.items():
   c.execute('INSERT OR IGNORE INTO automation_settings(key,value) VALUES(?,?)',(k,v))
guardian_schema()

def maintenance_status():
 with db() as c:r=c.execute('SELECT enabled,reason,mode,started_at,updated_at FROM maintenance_state WHERE id=1').fetchone()
 return dict(r)

def set_maintenance(enabled,reason='',mode='manual'):
 now=int(time.time())
 with db() as c:
  old=c.execute('SELECT enabled FROM maintenance_state WHERE id=1').fetchone(); old_enabled=int(old[0]) if old else 0
  c.execute('UPDATE maintenance_state SET enabled=?,reason=?,mode=?,started_at=CASE WHEN ?=1 AND enabled=0 THEN ? ELSE started_at END,updated_at=? WHERE id=1',(1 if enabled else 0,reason,mode,1 if enabled else 0,now,now))
 if old_enabled!=(1 if enabled else 0): history('maintenance','server','Mantenimiento activado' if enabled else 'Mantenimiento finalizado',{'reason':reason,'mode':mode})
 return maintenance_status()

def guardian_check_and_repair():
 now=int(time.time()); cfg=auto_settings(); checks={}; repairs=[]
 # SQLite integrity is authoritative for the current dev backend.
 try:
  with db() as c:
   checks['database']=c.execute('PRAGMA quick_check').fetchone()[0]
   # Safe consistency repairs only: never invent inventory/currency/content.
   bad=c.execute('SELECT COUNT(*) FROM global_bosses WHERE current_hp<0 OR current_hp>max_hp OR max_hp<=0').fetchone()[0]
   checks['boss_invalid_rows']=int(bad)
   if bad and cfg.get('auto_repair_enabled','1')=='1':
    c.execute('UPDATE global_bosses SET current_hp=MAX(0,MIN(current_hp,max_hp)) WHERE max_hp>0 AND (current_hp<0 OR current_hp>max_hp)'); repairs.append('boss_hp_clamped')
   neg=c.execute('SELECT COUNT(*) FROM world_goals WHERE current<0 OR current>target OR target<=0').fetchone()[0]
   checks['world_goal_invalid_rows']=int(neg)
   if neg and cfg.get('auto_repair_enabled','1')=='1':
    c.execute('UPDATE world_goals SET current=MAX(0,MIN(current,target)) WHERE target>0 AND (current<0 OR current>target)'); repairs.append('world_goal_progress_clamped')
   orphan=c.execute("SELECT COUNT(*) FROM legacy_sessions WHERE state='started' AND started_at<?",(now-86400,)).fetchone()[0]
   checks['stale_quest_sessions']=int(orphan)
   if orphan and cfg.get('auto_repair_enabled','1')=='1':
    c.execute("UPDATE legacy_sessions SET state='abandoned',finished_at=? WHERE state='started' AND started_at<?",(now,now-86400)); repairs.append('stale_quests_abandoned')
 except Exception as e:
  checks['database']='error'; checks['error']=str(e)[:300]
 critical=checks.get('database')!='ok'
 if critical and cfg.get('auto_maintenance_enabled','1')=='1': set_maintenance(True,'Guardian detectó un fallo crítico','auto')
 status='critical' if critical else ('repaired' if repairs else 'healthy')
 with db() as c:c.execute('INSERT INTO guardian_runs(status,checks_json,repairs_json,created_at) VALUES(?,?,?,?)',(status,json.dumps(checks,ensure_ascii=False),json.dumps(repairs,ensure_ascii=False),now))
 return {'status':status,'checks':checks,'repairs':repairs,'maintenance':maintenance_status()}

@app.get('/game/service-status')
def game_service_status():
 m=maintenance_status()
 with db() as c:u=c.execute('SELECT current_version,target_version,state,required,notes FROM update_state WHERE id=1').fetchone()
 return {'ok':True,'maintenance':bool(m['enabled']),'reason':m['reason'],'update':dict(u)}

@app.post('/admin/guardian/run')
def guardian_run(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); return {'ok':True,**guardian_check_and_repair()}

@app.post('/admin/maintenance/{state}')
def maintenance_admin(state:str,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); state=state.lower()
 if state not in ('on','off'): raise HTTPException(400,'state must be on or off')
 return {'ok':True,'maintenance':set_maintenance(state=='on','Activado manualmente' if state=='on' else '','manual')}

class UpdatePlan(BaseModel):
 version:str; notes:str=''; required:bool=False

@app.post('/admin/update/plan')
def update_plan(body:UpdatePlan,x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); now=int(time.time())
 with db() as c:c.execute("UPDATE update_state SET target_version=?,state='ready',required=?,notes=?,updated_at=? WHERE id=1",(body.version,1 if body.required else 0,body.notes,now))
 create_announcement(f'Actualización {body.version} preparada. {body.notes}'.strip(),now,72,'guardian','update_ready',body.version)
 return {'ok':True,'version':body.version,'state':'ready','required':body.required}

@app.post('/admin/update/commit')
def update_commit(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret); now=int(time.time())
 # Orchestrates state safely. Deployment itself remains the platform's job; we never self-overwrite a running binary.
 with db() as c:
  r=c.execute('SELECT target_version,notes FROM update_state WHERE id=1').fetchone()
  if not r or not r['target_version']: raise HTTPException(409,'no prepared update')
  target=r['target_version']; c.execute("UPDATE update_state SET current_version=?,target_version='',state='idle',required=0,updated_at=? WHERE id=1",(target,now))
 set_maintenance(False,'','auto-update'); create_announcement(f'SAO-CB actualizado a {target}.',now,72,'guardian','update_done',target); history('update_committed',target,'Actualización marcada como aplicada',{})
 return {'ok':True,'current_version':target}

@app.get('/admin/guardian/status')
def guardian_status(x_saocb_secret:str|None=Header(default=None)):
 auth(x_saocb_secret)
 with db() as c:r=c.execute('SELECT status,checks_json,repairs_json,created_at FROM guardian_runs ORDER BY id DESC LIMIT 1').fetchone()
 return {'ok':True,'maintenance':maintenance_status(),'last_run':dict(r) if r else None,'settings':auto_settings()}

# Guardian joins the existing autonomous loop without changing Auto Director semantics.
_old_autonomous_tick_once=autonomous_tick_once
async def autonomous_tick_once():
 data=await _old_autonomous_tick_once(); cfg=auto_settings()
 if cfg.get('guardian_enabled','1')=='1': data['guardian']=guardian_check_and_repair()
 return data

# Telegram operator controls for Guardian. Existing PiBot /dar remains untouched.
@app.post('/telegram/admin/maintenance/{state}')
def telegram_maintenance(state:str,x_saocb_secret:str|None=Header(default=None),x_telegram_user_id:str|None=Header(default=None)):
 auth(x_saocb_secret); telegram_admin_guard(x_telegram_user_id); return maintenance_admin(state,x_saocb_secret)

@app.post('/telegram/admin/repair')
def telegram_repair(x_saocb_secret:str|None=Header(default=None),x_telegram_user_id:str|None=Header(default=None)):
 auth(x_saocb_secret); telegram_admin_guard(x_telegram_user_id); return {'ok':True,**guardian_check_and_repair()}
