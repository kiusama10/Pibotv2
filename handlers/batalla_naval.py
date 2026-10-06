import json
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.database.database import _get_connection, _put_connection, reservar_apuesta_doble
from src.utils.display_name import visible_user
from handlers.pipeso_extras import send_victory

SIZE=4
SHIP_SIZES=(2,1,1)
LETTERS='ABCD'


def ensure_naval_tables():
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS naval_games_tb(
          game_id bigserial PRIMARY KEY, chat_id bigint NOT NULL, thread_id bigint,
          creator_id bigint NOT NULL, opponent_id bigint, bet bigint NOT NULL,
          status text NOT NULL DEFAULT 'open', board1 text, board2 text,
          ready1 boolean NOT NULL DEFAULT false, ready2 boolean NOT NULL DEFAULT false,
          turn_id bigint, shots1 text NOT NULL DEFAULT '{}', shots2 text NOT NULL DEFAULT '{}',
          winner_id bigint, created_at timestamptz NOT NULL DEFAULT now(),
          accepted_at timestamptz, finished_at timestamptz,
          CHECK (bet > 0)
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_naval_open_chat ON naval_games_tb(chat_id,status)")
        c.execute("""CREATE TABLE IF NOT EXISTS naval_stats_tb(
          user_id bigint PRIMARY KEY, wins int NOT NULL DEFAULT 0, losses int NOT NULL DEFAULT 0,
          ships_sunk int NOT NULL DEFAULT 0, shots int NOT NULL DEFAULT 0, hits int NOT NULL DEFAULT 0
        )""")
        conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:_put_connection(conn)


def _new_board():
    occupied=set(); ships=[]
    for length in SHIP_SIZES:
        for _ in range(500):
            horizontal=random.choice((True,False))
            r=random.randrange(SIZE); col=random.randrange(SIZE)
            cells=[]
            for i in range(length):
                rr=r+(0 if horizontal else i); cc=col+(i if horizontal else 0)
                if rr>=SIZE or cc>=SIZE: cells=[]; break
                cells.append(f'{LETTERS[cc]}{rr+1}')
            if cells and not occupied.intersection(cells):
                occupied.update(cells); ships.append(cells); break
    return ships


def _board_text(ships, shots_against=None, hide=False):
    shots_against=shots_against or {}
    occ={x for ship in ships for x in ship}
    lines=['    A  B  C  D']
    for r in range(1,SIZE+1):
        row=[]
        for col in LETTERS:
            cell=f'{col}{r}'
            if cell in shots_against:
                row.append('💥' if shots_against[cell] else '❌')
            elif not hide and cell in occ: row.append('🚢')
            else: row.append('🌊')
        lines.append(f'{r}  '+''.join(row))
    return '\n'.join(lines)


def _battle_text(g, last_line=None):
    # Public view: both players' ATTACK boards. Ship positions always stay private.
    name1=visible_user(user_id=g['creator_id'])
    name2=visible_user(user_id=g['opponent_id'])
    shots1=g.get('shots1') or {}
    shots2=g.get('shots2') or {}
    parts=['🚢 BATALLA NAVAL']
    if last_line:
        parts += ['', last_line]
    parts += [
        '', f'⚓ {name1} → {name2}', _board_text([],shots1,True),
        '', f'⚓ {name2} → {name1}', _board_text([],shots2,True),
        '', f'🎯 Turno de {visible_user(user_id=g["turn_id"])}',
        f'💰 Pozo: {g["bet"]*2:,} PiPesos',
        '', 'Elige una coordenada:'
    ]
    return '\n'.join(parts)


def _attack_keyboard(game_id, shots):
    rows=[]
    for r in range(1,SIZE+1):
        row=[]
        for col in LETTERS:
            cell=f'{col}{r}'
            label=('💥' if shots.get(cell) else '❌') if cell in shots else cell
            row.append(InlineKeyboardButton(label,callback_data=f'nv:f:{game_id}:{cell}'))
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _open_keyboard(game_id):
    return InlineKeyboardMarkup([[InlineKeyboardButton('⚔️ Aceptar batalla',callback_data=f'nv:a:{game_id}')],[InlineKeyboardButton('❌ Cancelar reto',callback_data=f'nv:c:{game_id}')]])


def _ready_keyboard(game_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🎲 Aleatorio',callback_data=f'nv:r:{game_id}'), InlineKeyboardButton('🛠 Acomodar',callback_data=f'nv:m:{game_id}')],
        [InlineKeyboardButton('✅ Listo para combatir',callback_data=f'nv:y:{game_id}')]
    ])


def _manual_keyboard(game_id, ships):
    occupied={x for ship in ships for x in ship}
    rows=[]
    for r in range(1,SIZE+1):
        row=[]
        for col in LETTERS:
            cell=f'{col}{r}'
            row.append(InlineKeyboardButton('🚢' if cell in occupied else cell,callback_data=f'nv:p:{game_id}:{cell}'))
        rows.append(row)
    rows.append([InlineKeyboardButton('🔄 Reiniciar',callback_data=f'nv:m:{game_id}'),InlineKeyboardButton('🎲 Aleatorio',callback_data=f'nv:r:{game_id}')])
    if sorted(len(x) for x in ships)==[1,1,2]: rows.append([InlineKeyboardButton('✅ Listo para combatir',callback_data=f'nv:y:{game_id}')])
    return InlineKeyboardMarkup(rows)


def _manual_help(ships):
    sizes=sorted(len(x) for x in ships)
    if not ships:return '🛠 Primero elige la primera casilla del barco de 2.'
    if sizes==[1]:return '🛠 Ahora toca una casilla pegada (arriba, abajo o a un lado) para completar el barco de 2.'
    if sizes==[2]:return '🛠 Coloca el primer barco de 1 casilla.'
    if sizes==[1,2]:return '🛠 Coloca el último barco de 1 casilla.'
    return '✅ Tu flota está completa. Puedes confirmar o volver a acomodarla.'


def _manual_add(ships, cell):
    occupied={x for ship in ships for x in ship}
    if cell in occupied:return None
    if not ships:return [[cell]]
    if len(ships)==1 and len(ships[0])==1:
        a=ships[0][0]; ac,ar=a[0],int(a[1:]); cc,cr=cell[0],int(cell[1:])
        if abs(ord(ac)-ord(cc))+abs(ar-cr)!=1:return None
        return [[a,cell]]
    if sorted(len(x) for x in ships) in ([2],[1,2]):
        if len(ships)>=3:return None
        return ships+[[cell]]
    return None


def _get_game(gid, lock=False):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT game_id,chat_id,thread_id,creator_id,opponent_id,bet,status,board1,board2,ready1,ready2,turn_id,shots1,shots2,winner_id FROM naval_games_tb WHERE game_id=%s"+(" FOR UPDATE" if lock else ""),(gid,)); r=c.fetchone()
        if not r:return None
        keys=['game_id','chat_id','thread_id','creator_id','opponent_id','bet','status','board1','board2','ready1','ready2','turn_id','shots1','shots2','winner_id']
        d=dict(zip(keys,r))
        for k in ('board1','board2','shots1','shots2'):
            if d[k]: d[k]=json.loads(d[k])
            elif k.startswith('shots'): d[k]={}
        return d
    finally:_put_connection(conn)


async def batalla_naval(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private':
        return await update.effective_message.reply_text('🚢 La Batalla Naval se abre en el grupo: /batallanaval cantidad')
    if not context.args:
        return await update.effective_message.reply_text('🚢 Usa /batallanaval 5000 para abrir un reto de apuestas.')
    try: bet=int(str(context.args[0]).replace(',',''))
    except Exception:return await update.effective_message.reply_text('⚠️ La apuesta debe ser un número. Ejemplo: /batallanaval 5000')
    if bet<=0:return await update.effective_message.reply_text('⚠️ La apuesta debe ser mayor a 0.')
    uid=update.effective_user.id; chat=update.effective_chat.id; thread=getattr(update.effective_message,'message_thread_id',None)
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT 1 FROM naval_games_tb WHERE status IN ('open','placing','active') AND (creator_id=%s OR opponent_id=%s) LIMIT 1",(uid,uid))
        if c.fetchone(): return await update.effective_message.reply_text('🚢 Ya tienes una Batalla Naval pendiente o activa.')
        c.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s",(uid,)); rr=c.fetchone()
        if not rr or rr[0]<bet:return await update.effective_message.reply_text(f'💸 No tienes {bet:,} PiPesos para respaldar ese reto.')
        c.execute("INSERT INTO naval_games_tb(chat_id,thread_id,creator_id,bet) VALUES(%s,%s,%s,%s) RETURNING game_id",(chat,thread,uid,bet)); gid=c.fetchone()[0]; conn.commit()
    except Exception:
        conn.rollback(); raise
    finally:_put_connection(conn)
    name=visible_user(user=update.effective_user)
    await update.effective_message.reply_text(f'🚢 BATALLA NAVAL · RETO ABIERTO\n\n⚓ {name} busca rival.\n💰 Apuesta: {bet:,} PiPesos por jugador\n🏆 Pozo: {bet*2:,} PiPesos\n🗺️ Tablero 4×4 · 3 barcos\n\nEl primero que acepte entra a la batalla.',reply_markup=_open_keyboard(gid))


async def _send_setup(context, gid, uid, ships):
    text='🚢 COLOCA TU FLOTA\n\n'+_board_text(ships)+'\n\nTienes 3 barcos: 3, 2 y 2 casillas.\n🎲 Puedes recolocarlos al azar hasta que te gusten.\nCuando estés listo, confirma. Tu rival NO verá este tablero.'
    await context.bot.send_message(uid,text,reply_markup=_ready_keyboard(gid))


async def _start_if_ready(context,gid):
    g=_get_game(gid)
    if not g or g['status']!='placing' or not (g['ready1'] and g['ready2']):return
    first=random.choice([g['creator_id'],g['opponent_id']])
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE naval_games_tb SET status='active',turn_id=%s WHERE game_id=%s AND status='placing' AND ready1=TRUE AND ready2=TRUE",(first,gid)); conn.commit()
    finally:_put_connection(conn)
    ng=_get_game(gid)
    first_slot=1 if first==ng['creator_id'] else 2
    await context.bot.send_message(chat_id=g['chat_id'],message_thread_id=g['thread_id'],text=_battle_text(ng),reply_markup=_attack_keyboard(gid,ng[f'shots{first_slot}'] or {}))


async def naval_callback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); p=q.data.split(':')
    if len(p)<3:return
    action=p[1]; gid=int(p[2]); uid=q.from_user.id
    g=_get_game(gid)
    if not g:return await q.answer('Esta batalla ya no existe.',show_alert=True)
    if action=='c':
        if uid!=g['creator_id']:return await q.answer('Solo quien abrió el reto puede cancelarlo.',show_alert=True)
        if g['status']!='open':return await q.answer('El reto ya fue aceptado.',show_alert=True)
        conn=_get_connection();
        try:
            c=conn.cursor(); c.execute("UPDATE naval_games_tb SET status='cancelled',finished_at=now() WHERE game_id=%s AND status='open'",(gid,)); conn.commit()
        finally:_put_connection(conn)
        return await q.edit_message_text('🚢 Reto de Batalla Naval cancelado.')
    if action=='a':
        if uid==g['creator_id']:return await q.answer('No puedes aceptar tu propio reto jajaja.',show_alert=True)
        if g['status']!='open':return await q.answer('Alguien ya tomó este reto.',show_alert=True)
        # Prevent accepting while already in another naval game.
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT 1 FROM naval_games_tb WHERE game_id<>%s AND status IN ('placing','active') AND (creator_id=%s OR opponent_id=%s) LIMIT 1",(gid,uid,uid)); busy=c.fetchone()
        finally:_put_connection(conn)
        if busy:return await q.answer('Ya tienes otra Batalla Naval activa.',show_alert=True)
        if not reservar_apuesta_doble(g['creator_id'],uid,g['bet']):return await q.answer('No se pudo reservar la apuesta. Ambos necesitan saldo suficiente.',show_alert=True)
        b1=_new_board(); b2=_new_board(); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("UPDATE naval_games_tb SET opponent_id=%s,status='placing',board1=%s,board2=%s,accepted_at=now() WHERE game_id=%s AND status='open'",(uid,json.dumps(b1),json.dumps(b2),gid))
            if c.rowcount!=1:
                conn.rollback()
                from src.database.database import reembolsar_apuesta_doble
                reembolsar_apuesta_doble(g['creator_id'],uid,g['bet'])
                return await q.answer('Ese reto acaba de ser tomado.',show_alert=True)
            conn.commit()
        finally:_put_connection(conn)
        try:
            await _send_setup(context,gid,g['creator_id'],b1); await _send_setup(context,gid,uid,b2)
        except Exception:
            conn=_get_connection()
            try:
                c=conn.cursor(); c.execute("UPDATE naval_games_tb SET status='cancelled',finished_at=now() WHERE game_id=%s AND status='placing'",(gid,)); conn.commit()
            finally:_put_connection(conn)
            from src.database.database import reembolsar_apuesta_doble
            reembolsar_apuesta_doble(g['creator_id'],uid,g['bet'])
            return await q.edit_message_text('⚠️ No pude enviar el tablero privado a ambos. Los PiPesos fueron devueltos. Ambos deben abrir el PV de PiBot con /start.')
        await q.edit_message_text(f'🚢 ¡RETO ACEPTADO!\n\n{visible_user(user_id=g["creator_id"])} vs {visible_user(user=q.from_user)}\n💰 {g["bet"]:,} PiPesos cada uno ya están reservados.\n📩 Les envié su flota por privado. Cuando ambos pulsen Listo, comienza la batalla.')
        return
    if action in ('r','m','p','y'):
        if g['status']!='placing' or uid not in (g['creator_id'],g['opponent_id']):return await q.answer('No puedes modificar esta flota.',show_alert=True)
        slot=1 if uid==g['creator_id'] else 2
        if (g['ready1'] if slot==1 else g['ready2']):return await q.answer('Ya confirmaste tu flota.',show_alert=True)
        if action=='r':
            ships=_new_board(); conn=_get_connection()
            try:
                c=conn.cursor(); c.execute(f"UPDATE naval_games_tb SET board{slot}=%s WHERE game_id=%s AND status='placing'",(json.dumps(ships),gid)); conn.commit()
            finally:_put_connection(conn)
            return await q.edit_message_text('🚢 COLOCA TU FLOTA\n\n'+_board_text(ships)+'\n\n🎲 Nueva distribución. Puedes volver a cambiarla, acomodarla tú o confirmar.',reply_markup=_ready_keyboard(gid))
        if action=='m':
            ships=[]; conn=_get_connection()
            try:
                c=conn.cursor(); c.execute(f"UPDATE naval_games_tb SET board{slot}=%s WHERE game_id=%s AND status='placing'",(json.dumps(ships),gid)); conn.commit()
            finally:_put_connection(conn)
            return await q.edit_message_text('🚢 ACOMODA TU FLOTA\n\n'+_board_text(ships)+'\n\n'+_manual_help(ships),reply_markup=_manual_keyboard(gid,ships))
        if action=='p' and len(p)>=4:
            ships=g[f'board{slot}'] or []; newships=_manual_add(ships,p[3].upper())
            if newships is None:return await q.answer('Esa casilla no sirve ahí. El barco de 2 debe quedar unido y no puedes encimar barcos.',show_alert=True)
            conn=_get_connection()
            try:
                c=conn.cursor(); c.execute(f"UPDATE naval_games_tb SET board{slot}=%s WHERE game_id=%s AND status='placing'",(json.dumps(newships),gid)); conn.commit()
            finally:_put_connection(conn)
            return await q.edit_message_text('🚢 ACOMODA TU FLOTA\n\n'+_board_text(newships)+'\n\n'+_manual_help(newships),reply_markup=_manual_keyboard(gid,newships))
        ships=g[f'board{slot}'] or []
        if sorted(len(x) for x in ships)!=[1,1,2]:return await q.answer('Primero completa tus 3 barcos.',show_alert=True)
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute(f"UPDATE naval_games_tb SET ready{slot}=TRUE WHERE game_id=%s AND status='placing'",(gid,)); conn.commit()
        finally:_put_connection(conn)
        await q.edit_message_text('✅ Flota confirmada. Esperando a tu rival…')
        await _start_if_ready(context,gid); return
    if action=='f' and len(p)>=4:
        cell=p[3].upper(); g=_get_game(gid)
        if not g or g['status']!='active':return await q.answer('Esta batalla ya terminó.',show_alert=True)
        if uid!=g['turn_id']:return await q.answer('Todavía no es tu turno.',show_alert=True)
        if uid not in (g['creator_id'],g['opponent_id']):return await q.answer('No participas en esta batalla.',show_alert=True)
        attacker_slot=1 if uid==g['creator_id'] else 2; defender_slot=2 if attacker_slot==1 else 1
        shots=dict(g[f'shots{attacker_slot}'] or {})
        if cell in shots:return await q.answer('Ya disparaste ahí.',show_alert=True)
        enemy=g[f'board{defender_slot}']; occupied={x for ship in enemy for x in ship}; hit=cell in occupied; shots[cell]=hit
        sunk_now=None
        if hit:
            for ship in enemy:
                if cell in ship and all(shots.get(x) is True for x in ship): sunk_now=ship; break
        all_sunk=all(shots.get(x) is True for x in occupied)
        other=g['opponent_id'] if uid==g['creator_id'] else g['creator_id']
        conn=_get_connection()
        try:
            c=conn.cursor()
            if all_sunk:
                c.execute("SELECT status FROM naval_games_tb WHERE game_id=%s FOR UPDATE",(gid,)); st=c.fetchone()
                if not st or st[0]!='active': conn.rollback(); return await q.answer('La batalla ya terminó.',show_alert=True)
                c.execute(f"UPDATE naval_games_tb SET shots{attacker_slot}=%s,status='finished',winner_id=%s,finished_at=now() WHERE game_id=%s",(json.dumps(shots),uid,gid))
                c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(g['bet']*2,uid))
                c.execute("INSERT INTO naval_stats_tb(user_id,wins,shots,hits,ships_sunk) VALUES(%s,1,1,%s,%s) ON CONFLICT(user_id) DO UPDATE SET wins=naval_stats_tb.wins+1,shots=naval_stats_tb.shots+1,hits=naval_stats_tb.hits+EXCLUDED.hits,ships_sunk=naval_stats_tb.ships_sunk+EXCLUDED.ships_sunk",(uid,1 if hit else 0,1 if sunk_now else 0))
                c.execute("INSERT INTO naval_stats_tb(user_id,losses) VALUES(%s,1) ON CONFLICT(user_id) DO UPDATE SET losses=naval_stats_tb.losses+1",(other,)); conn.commit()
            else:
                c.execute(f"UPDATE naval_games_tb SET shots{attacker_slot}=%s,turn_id=%s WHERE game_id=%s AND status='active' AND turn_id=%s",(json.dumps(shots),other,gid,uid))
                c.execute("INSERT INTO naval_stats_tb(user_id,shots,hits,ships_sunk) VALUES(%s,1,%s,%s) ON CONFLICT(user_id) DO UPDATE SET shots=naval_stats_tb.shots+1,hits=naval_stats_tb.hits+EXCLUDED.hits,ships_sunk=naval_stats_tb.ships_sunk+EXCLUDED.ships_sunk",(uid,1 if hit else 0,1 if sunk_now else 0)); conn.commit()
        except Exception:
            conn.rollback(); raise
        finally:_put_connection(conn)
        result='💥 ¡IMPACTO!' if hit else '🌊 Agua.'
        if sunk_now: result+=' 🚢☠️ ¡BARCO HUNDIDO!'
        try: await context.bot.send_message(other,f'💣 {visible_user(user_id=uid)} disparó a {cell}: {result}')
        except Exception: pass
        if all_sunk:
            text=f'🏆 ¡FLOTA DESTRUIDA!\n\n{visible_user(user_id=uid)} hundió todos los barcos de {visible_user(user_id=other)}.\n💰 Gana el pozo de {g["bet"]*2:,} PiPesos.\n\nÚltimo disparo: {cell} · {result}'
            await q.edit_message_text(text)
            await send_victory(context,uid,'naval',g['chat_id'],g['thread_id'],visible_user(user_id=uid)); return
        # New turn: keep BOTH public attack boards visible; buttons belong to the next shooter's history.
        ng=_get_game(gid); next_slot=1 if other==ng['creator_id'] else 2; nextshots=ng[f'shots{next_slot}'] or {}
        await q.edit_message_text(_battle_text(ng,f'💣 {visible_user(user_id=uid)} disparó a {cell}: {result}'),reply_markup=_attack_keyboard(gid,nextshots))


async def cancelar_naval(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private':
        return await update.effective_message.reply_text('🚢 Cancela la Batalla Naval desde el grupo donde se está jugando.')
    uid=update.effective_user.id; chat=update.effective_chat.id; thread=getattr(update.effective_message,'message_thread_id',None)
    conn=_get_connection(); refund=None
    try:
        c=conn.cursor()
        c.execute("""SELECT game_id,creator_id,opponent_id,bet,status FROM naval_games_tb
          WHERE chat_id=%s AND COALESCE(thread_id,0)=COALESCE(%s,0)
            AND status IN ('open','placing','active') AND (creator_id=%s OR opponent_id=%s)
          ORDER BY game_id DESC LIMIT 1 FOR UPDATE""",(chat,thread,uid,uid))
        row=c.fetchone()
        if not row:
            conn.rollback(); return await update.effective_message.reply_text('🚢 No tienes una Batalla Naval pendiente o activa aquí.')
        gid,creator,opponent,bet,status=row
        # Claim cancellation first. This makes repeated /cancelarnaval calls idempotent.
        c.execute("UPDATE naval_games_tb SET status='cancelled',finished_at=now() WHERE game_id=%s AND status=%s",(gid,status))
        if c.rowcount!=1:
            conn.rollback(); return await update.effective_message.reply_text('🚢 Esa batalla ya cambió de estado.')
        conn.commit()
        if status in ('placing','active') and opponent:
            refund=(creator,opponent,bet)
    except Exception:
        conn.rollback(); raise
    finally:_put_connection(conn)
    if refund:
        from src.database.database import reembolsar_apuesta_doble
        if not reembolsar_apuesta_doble(*refund):
            # Restore active state so money is never silently stranded; user can retry cancellation.
            conn=_get_connection()
            try:
                c=conn.cursor(); c.execute("UPDATE naval_games_tb SET status=%s,finished_at=NULL WHERE game_id=%s AND status='cancelled'",(status,gid)); conn.commit()
            finally:_put_connection(conn)
            return await update.effective_message.reply_text('⚠️ No pude devolver la apuesta. La batalla sigue activa; intenta /cancelarnaval otra vez.')
        return await update.effective_message.reply_text(f'🚢 Batalla Naval cancelada. Se devolvieron {bet:,} PiPesos a cada jugador.')
    await update.effective_message.reply_text('🚢 Reto de Batalla Naval cancelado.')


async def ranking_naval(update:Update, context:ContextTypes.DEFAULT_TYPE):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT user_id,wins,losses,ships_sunk,shots,hits FROM naval_stats_tb ORDER BY wins DESC, ships_sunk DESC, hits DESC LIMIT 10"); rows=c.fetchall()
    finally:_put_connection(conn)
    if not rows:return await update.effective_message.reply_text('🚢 Todavía no hay batallas navales terminadas.')
    lines=['🏆 RANKING BATALLA NAVAL','']
    for i,(uid,w,l,s,shots,hits) in enumerate(rows,1):
        acc=(hits*100/shots) if shots else 0; lines.append(f'{i}. {visible_user(user_id=uid)} · {w}V/{l}D · 🚢 {s} · 🎯 {acc:.0f}%')
    await update.effective_message.reply_text('\n'.join(lines))
