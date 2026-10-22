from __future__ import annotations

import asyncio
import json
import math
import random
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.database.database import _get_connection, _put_connection, is_botmaster
from src.config import COMUNIDADES, obtener_temas_por_comunidad
from handlers.pokemon_gen1_data import (
    NAMES, TYPES, MOVES, ITEMS, TM_ITEMS, LEVEL_EVOLUTIONS, STONE_EVOLUTIONS,
    TRADE_EVOLUTIONS, LEGENDARY_IDS, EPIC_IDS, RARE_IDS, PHYSICAL_TYPES,
    available_moves, battle_base_stats, effectiveness, rarity_for, can_learn_tm,
    rarity_emoji, type_emoji, SPECIAL_LEARNSETS, TYPE_MOVESETS,
)

PAGE_SIZE = 8
MAX_LEVEL = 100
WIN_PIPESOS = 1000
LOSS_PIPESOS = 300
WIN_SEASON_XP = 25
LOSS_SEASON_XP = 10
WIN_POKEMON_XP = 60
LOSS_POKEMON_XP = 30

# Capturas salvajes: aparecen solo en el tema Juegos y Casino.
WILD_SHINY_DENOMINATOR = 200  # 0.5% por aparición salvaje
WILD_MAX_ATTEMPTS = 2
WILD_DICE_ANIMATION_SECONDS = 4.2  # espera a que termine la animacion del dado en Telegram
WILD_LIFETIME_SECONDS = 600  # 10 minutos visible antes de irse
WILD_CATCH_THRESHOLD = {"comun": 3, "raro": 4, "epico": 5, "legendario": 6}
CANDIES_PER_LEVEL = 1

POKEMON_TZ = ZoneInfo("America/Mexico_City")
POKEMON_SEASON_PRIZES = {1: 30000, 2: 20000, 3: 10000}
TOURNAMENT_MAX_PLAYERS = 16
TEAM_MAX_SIZE = 4
NPC_LIFETIME_SECONDS = 600
NPC_NORMAL_WIN_PIPESOS = {1:1500, 2:2000}
NPC_NORMAL_LOSS_PIPESOS = 300
NPC_NORMAL_XP = {1:100, 2:140}
NPC_NORMAL_LOSS_XP = 35
LEADER_WIN_PIPESOS = 5000
LEADER_LOSS_PIPESOS = 500
LEADER_XP = 250
LEADER_LOSS_XP = 60
LEADER_BONUS_XP = 150
LEGENDARY_SPECIAL_SHINY_DENOMINATOR = 64
LEGENDARY_SPECIAL_MAX_ATTEMPTS = 3
MASTER_BALL_BOX_CHANCE = 0.005

# Preferencias de aparición por franja. Todos los 151 siguen siendo posibles,
# pero estos tienen más peso en su horario. Además se excluyen especies recientes
# para que no se repita el mismo Pokémon una y otra vez.
DAY_PREFERRED = {
    10,11,12,13,14,15,16,17,18,19,20,21,22,25,26,29,30,31,32,33,34,
    37,38,43,44,45,46,47,48,49,52,53,54,55,58,59,69,70,71,77,78,
    83,84,85,102,103,111,112,113,114,115,123,127,128,133,134,135,136
}
NIGHT_PREFERRED = {
    19,20,23,24,27,28,35,36,39,40,41,42,48,49,50,51,52,53,63,64,65,
    66,67,68,74,75,76,79,80,88,89,90,91,92,93,94,95,96,97,104,105,
    109,110,116,117,120,121,124,129,130,137,138,139,140,141,142
}

# Evoluciones por piedra de TODOS los Pokémon de la Pokédex Gen 1 compatibles.
# Se mantiene aquí como garantía aunque pokemon_gen1_data.py ya tenga la tabla.
GEN1_STONE_EVOLUTIONS = {
    25:{"thunder_stone":26},
    30:{"moon_stone":31}, 33:{"moon_stone":34}, 35:{"moon_stone":36},
    37:{"fire_stone":38}, 39:{"moon_stone":40}, 44:{"leaf_stone":45},
    58:{"fire_stone":59}, 61:{"water_stone":62}, 70:{"leaf_stone":71},
    90:{"water_stone":91}, 102:{"leaf_stone":103}, 120:{"water_stone":121},
    133:{"water_stone":134,"thunder_stone":135,"fire_stone":136},
}
STONE_CODES = ("fire_stone","water_stone","thunder_stone","leaf_stone","moon_stone")

# Afinidades temáticas para drops de piedras. No garantizan el objeto: solo
# aumentan su peso cuando ya se decidió que la captura soltará una piedra.
STONE_DROP_AFFINITY = {
    # Fuego
    37:("fire_stone",),38:("fire_stone",),58:("fire_stone",),59:("fire_stone",),
    # Agua
    60:("water_stone",),61:("water_stone",),62:("water_stone",),
    90:("water_stone",),91:("water_stone",),120:("water_stone",),121:("water_stone",),
    # Trueno
    25:("thunder_stone",),26:("thunder_stone",),
    # Hoja
    43:("leaf_stone",),44:("leaf_stone",),45:("leaf_stone",),
    69:("leaf_stone",),70:("leaf_stone",),71:("leaf_stone",),
    102:("leaf_stone",),103:("leaf_stone",),
    # Lunar
    29:("moon_stone",),30:("moon_stone",),31:("moon_stone",),
    32:("moon_stone",),33:("moon_stone",),34:("moon_stone",),
    35:("moon_stone",),36:("moon_stone",),39:("moon_stone",),40:("moon_stone",),
    # Eevee puede relacionarse con cualquiera de sus tres piedras Gen 1.
    133:("water_stone","thunder_stone","fire_stone"),
    134:("water_stone",),135:("thunder_stone",),136:("fire_stone",),
}

WILD_DROP_CHANCE = {"comun":0.18,"raro":0.30,"epico":0.45,"legendario":0.60}
WILD_DROP_KIND_WEIGHTS = {
    "comun":      (("rare_candy","stone","tm"),(50,40,10)),
    "raro":       (("rare_candy","stone","tm"),(40,35,25)),
    "epico":      (("rare_candy","stone","tm"),(30,30,40)),
    "legendario": (("rare_candy","stone","tm"),(20,25,55)),
}
TM_LOW = ("tm12","tm30","tm39","tm45")
TM_MID = ("tm06","tm08","tm11","tm17","tm19","tm21","tm28","tm35","tm42","tm48")
TM_HIGH = ("tm13","tm14","tm15","tm22","tm24","tm25","tm26","tm29","tm38")

# Centro de Entrenamiento Pokémon: no usa cron ni proceso adicional.
TRAINING_DAILY_LIMIT = 3
TRAINING_BOT_ID = 0
TRAINING_WIN_PIPESOS = 1000
TRAINING_LOSS_PIPESOS = 300
TRAINING_HELD_DROP_CHANCE = 0.08


# Expansión Pokémon: Safari, Team Rocket, Incursiones, Liga y progresión.
SAFARI_PASS_COST = 10_000
SAFARI_DURATION_SECONDS = 1800
SAFARI_START_BALLS = 10
SAFARI_SHINY_DENOMINATOR = 128
SAFARI_IV_MIN = 10
SAFARI_LEGENDARY_APPEAR_CHANCE = 0.005  # 0.5% por exploración
# Probabilidad máxima con el Pokémon a 0 PS; a más PS, menor captura.
SAFARI_CAPTURE_CHANCE = {'comun':0.82,'raro':0.68,'epico':0.52,'legendario':0.10}
ROCKET_EVENT_SECONDS = 1800
RAID_EVENT_SECONDS = 2700
RAID_USER_ATTACKS = 5
RAID_ATTACK_COOLDOWN_SECONDS = 60
RAID_LEGENDARY_CHANCE = 0.10  # 10% de las incursiones pueden ser legendarias.
RAID_LEGENDARY_BOSSES = (144,145,146,150,151)
RAID_LEGENDARY_SHINY_DENOMINATOR = 256  # Se decide una sola vez por raid; nunca uno por participante.
RAID_NORMAL_SHINY_DENOMINATOR = 512  # Muy raro; también es un único ejemplar para toda la incursión.
RAID_LEGENDARY_CAPTURE_ATTEMPTS = 3
RAID_LEGENDARY_CAPTURE_SECONDS = 600  # 10 minutos para que el entrenador elegido haga sus 3 tiros.
RAID_LEGENDARY_DICE_SUCCESS = 6  # Solo un 6 captura al legendario.
WEATHER_KEYS = ('despejado','lluvia','tormenta','niebla','soleado','viento')
WEATHER_NAMES = {
    'despejado':'☀️ Despejado','lluvia':'🌧️ Lluvia','tormenta':'⛈️ Tormenta',
    'niebla':'🌫️ Niebla','soleado':'🔥 Sol intenso','viento':'💨 Viento fuerte'
}
WEATHER_TYPES = {
    'despejado':(), 'lluvia':('Water',), 'tormenta':('Electric','Water'),
    'niebla':('Ghost','Psychic','Poison'), 'soleado':('Fire','Grass'),
    'viento':('Flying','Dragon')
}
ROCKET_WAVES = ('rocket_grunt_event','rocket_exec_event','jessie_event','james_event')
LEAGUE_ORDER = ('lorelei_e4','bruno_e4','agatha_e4','lance_e4','champion_e4')
RAID_BOSSES = (94,131,143,142,149)

# Objetos equipables reales. El inventario sigue siendo pokemon_items_tb; cuando
# uno se equipa se descuenta del inventario y queda ligado al ejemplar mediante
# pokemon_instances_tb.held_item_code. Así un objeto equipado no puede entregarse.
HELD_ITEMS = {
    'light_ball':      {'name':'Bola Luminosa','emoji':'🔆','rarity':'epico','description':'Solo en Pikachu: duplica ATQ y ESP durante el combate.'},
    'leftovers':       {'name':'Restos','emoji':'🍎','rarity':'raro','description':'Recupera 1/16 de los PS máximos al final de cada ronda.'},
    'quick_claw':      {'name':'Garra Rápida','emoji':'⚡','rarity':'raro','description':'20% de probabilidad de actuar primero en la ronda.'},
    'focus_band':      {'name':'Banda Focus','emoji':'🎗️','rarity':'raro','description':'10% de probabilidad de sobrevivir con 1 PS a un golpe que debilitaría.'},
    'choice_band':     {'name':'Cinta Elegida','emoji':'🎀','rarity':'epico','description':'ATQ ×1.5; bloquea al primer movimiento elegido hasta cambiar de Pokémon.'},
    'choice_specs':    {'name':'Gafas Elegidas','emoji':'👓','rarity':'epico','description':'ESP ×1.5; bloquea al primer movimiento elegido hasta cambiar de Pokémon.'},
    'choice_scarf':    {'name':'Pañuelo Elegido','emoji':'🧣','rarity':'epico','description':'VEL ×1.5; bloquea al primer movimiento elegido hasta cambiar de Pokémon.'},
    'life_orb':        {'name':'Vidaesfera','emoji':'🔮','rarity':'epico','description':'Daño ×1.3; después de dañar pierde 1/10 de sus PS máximos.'},
    'expert_belt':     {'name':'Cinta Experto','emoji':'🥋','rarity':'raro','description':'Daño ×1.2 cuando el movimiento es súper eficaz.'},
    'shell_bell':      {'name':'Cascabel Concha','emoji':'🔔','rarity':'raro','description':'Recupera 1/8 del daño causado.'},
    'charcoal':        {'name':'Carbón','emoji':'🔥','rarity':'comun','description':'Potencia los movimientos de tipo Fuego ×1.2.'},
    'mystic_water':    {'name':'Agua Mística','emoji':'💧','rarity':'comun','description':'Potencia los movimientos de tipo Agua ×1.2.'},
    'magnet':          {'name':'Imán','emoji':'🧲','rarity':'comun','description':'Potencia los movimientos de tipo Eléctrico ×1.2.'},
    'miracle_seed':    {'name':'Semilla Milagro','emoji':'🌱','rarity':'comun','description':'Potencia los movimientos de tipo Planta ×1.2.'},
    'twisted_spoon':   {'name':'Cuchara Torcida','emoji':'🥄','rarity':'comun','description':'Potencia los movimientos de tipo Psíquico ×1.2.'},
    'sharp_beak':      {'name':'Pico Afilado','emoji':'🪶','rarity':'comun','description':'Potencia los movimientos de tipo Volador ×1.2.'},
    'hard_stone':      {'name':'Roca Dura','emoji':'🪨','rarity':'comun','description':'Potencia los movimientos de tipo Roca ×1.2.'},
    'poison_barb':     {'name':'Veneno Barbado','emoji':'☠️','rarity':'comun','description':'Potencia los movimientos de tipo Veneno ×1.2.'},
    'soft_sand':       {'name':'Arena Suave','emoji':'🏜️','rarity':'comun','description':'Potencia los movimientos de tipo Tierra ×1.2.'},
    'black_belt':      {'name':'Cinturón Negro','emoji':'🥋','rarity':'comun','description':'Potencia los movimientos de tipo Lucha ×1.2.'},
    'silver_powder':   {'name':'Polvo Plata','emoji':'✨','rarity':'comun','description':'Potencia los movimientos de tipo Bicho ×1.2.'},
    'thick_club':      {'name':'Hueso Grueso','emoji':'🦴','rarity':'epico','description':'Solo Cubone/Marowak: duplica el ATQ durante el combate.'},
    'never_melt_ice':  {'name':'Antiderretir','emoji':'🧊','rarity':'comun','description':'Potencia los movimientos de tipo Hielo ×1.2.'},
    'dragon_fang':     {'name':'Colmillo Dragón','emoji':'🐉','rarity':'raro','description':'Potencia los movimientos de tipo Dragón ×1.2.'},
    'spell_tag':       {'name':'Hechizo','emoji':'👻','rarity':'raro','description':'Potencia los movimientos de tipo Fantasma ×1.2.'},
    'silk_scarf':      {'name':'Pañuelo Seda','emoji':'🧵','rarity':'comun','description':'Potencia los movimientos de tipo Normal ×1.2.'},
    'muscle_band':     {'name':'Cinta Fuerte','emoji':'💪','rarity':'raro','description':'Potencia los movimientos físicos ×1.1.'},
    'wise_glasses':    {'name':'Gafas Especiales','emoji':'🤓','rarity':'raro','description':'Potencia los movimientos especiales ×1.1.'},
    'bright_powder':   {'name':'Polvo Brillo','emoji':'🌟','rarity':'raro','description':'Reduce aproximadamente 10% la precisión de los ataques rivales.'},
    'razor_claw':      {'name':'Garra Afilada','emoji':'🗡️','rarity':'epico','description':'Duplica la probabilidad base de golpe crítico.'},
}
HELD_RARITY_EMOJI = {'comun':'⚪','raro':'🔵','epico':'🟣'}
SPECIAL_POKEMON_ITEMS = {
    'object_box': {'name':'Caja de Objetos Pokémon','emoji':'🎁','description':'Contiene un objeto Pokémon aleatorio. Puede incluir una Master Ball extremadamente rara.'},
    'master_ball': {'name':'Master Ball','emoji':'🟣','description':'Captura garantizada en encuentros salvajes y legendarios especiales.'},
    'safari_ticket': {'name':'Pase Safari','emoji':'🎟️','description':'Permite entrar una vez a la Zona Safari sin pagar los 10,000 PiPesos.'},
}

HELD_TYPE_BOOSTS = {
    'charcoal':'Fire','mystic_water':'Water','magnet':'Electric','miracle_seed':'Grass',
    'twisted_spoon':'Psychic','sharp_beak':'Flying','hard_stone':'Rock','poison_barb':'Poison',
    'soft_sand':'Ground','black_belt':'Fighting','silver_powder':'Bug','never_melt_ice':'Ice',
    'dragon_fang':'Dragon','spell_tag':'Ghost','silk_scarf':'Normal',
}
WILD_HELD_DROP_CHANCE = {'comun':0.12,'raro':0.22,'epico':0.35,'legendario':0.50}
HELD_QUALITY_WEIGHTS = {
    'comun':      {'comun':82,'raro':17,'epico':1},
    'raro':       {'comun':55,'raro':40,'epico':5},
    'epico':      {'comun':28,'raro':55,'epico':17},
    'legendario': {'comun':12,'raro':53,'epico':35},
}
TYPE_HELD_AFFINITY = {
    'Fire':'charcoal','Water':'mystic_water','Electric':'magnet','Grass':'miracle_seed',
    'Psychic':'twisted_spoon','Flying':'sharp_beak','Rock':'hard_stone','Poison':'poison_barb',
    'Ground':'soft_sand','Fighting':'black_belt','Bug':'silver_powder','Ice':'never_melt_ice',
    'Dragon':'dragon_fang','Ghost':'spell_tag','Normal':'silk_scarf',
}


# ==================== CRIANZA / HUEVOS ====================
# gender_rate de PokéAPI: probabilidad de hembra en octavos. -1 = sin sexo.
# Se conserva fijo por ejemplar una vez asignado.
_GENDERLESS = {81,82,100,101,120,121,132,137,144,145,146,150,151}
_MALE_ONLY = {32,33,34,106,107,128}
_FEMALE_ONLY = {29,30,31,113,115,124}
_FEMALE_75 = {35,36,37,38,39,40}
_FEMALE_25 = {58,59,63,64,65,66,67,68,125,126}
_FEMALE_12_5 = {1,2,3,4,5,6,7,8,9,133,134,135,136,138,139,140,141,142,143}

EGG_PROGRESS_PER_MESSAGE = 150      # 1.50% en base 10000
EGG_PROGRESS_MAX = 10000
EGG_MAX_ACTIVE = 3
BREEDING_COST_PIPESOS = 3000
BREEDING_WAIT_SECONDS = 1800  # 30 minutos para que la pareja produzca el huevo
EGG_EVENT_LIFETIME_SECONDS = 3600   # 1 hora
EGG_EVENT_TIER_WEIGHTS = {'comun':70, 'raro':25, 'epico':5}
EGG_TIERS = {
    'comun': {'name':'Huevo Común','emoji':'🥚'},
    'raro': {'name':'Huevo Raro','emoji':'🔵🥚'},
    'epico': {'name':'Huevo Épico','emoji':'🟣🥚'},
}


# ==================== HALLOWEEN 2026 ====================
# Evento temporal autónomo. Después del cierre las recompensas conseguidas permanecen,
# pero se detienen drops, tienda, sorpresas y apariciones especiales.
HALLOWEEN_START = datetime(2026,10,20,0,0,0,tzinfo=POKEMON_TZ)
HALLOWEEN_END = datetime(2026,11,5,23,59,59,tzinfo=POKEMON_TZ)
HALLOWEEN_EVENT_LIFETIME_SECONDS = 1800
HALLOWEEN_BOX_SHINY_DENOMINATOR = 128
HALLOWEEN_EGG_SHINY_DENOMINATOR = 256
HALLOWEEN_PIKACHU_SHINY_CHANCE = 0.20  # 80% normal / 20% shiny
HALLOWEEN_YEAR = 2026
HALLOWEEN_SHOP = {
    'rare_candy': {'name':'Caramelo Raro','emoji':'🍬','price':20},
    'object_box': {'name':'Caja de Objetos Pokémon','emoji':'🎁','price':35},
    'pibot_epic': {'name':'Caja Épica normal de PiBot','emoji':'💜','price':55},
    'cursed_egg': {'name':'Huevo Maldito','emoji':'🎃🥚','price':75},
    'halloween_box': {'name':'Caja Pokémon Halloween','emoji':'🎃📦','price':90},
    'pibot_legendary': {'name':'Caja Legendaria normal de PiBot','emoji':'🌟','price':120},
    'halloween_pikachu': {'name':'Pikachu Halloween','emoji':'🎃⚡','price':180},
}
HALLOWEEN_THEME_BASES = (23,41,48,88,92,96,104,109)
HALLOWEEN_MEDIA_KEYS = {
    'cover':'🎃 Portada /evento',
    'surprise':'🌑 Aparición sorpresa',
    'npc':'👻 NPC Halloween',
    'boss':'💀 Jefe Halloween',
    'cursed_egg':'🎃🥚 Huevo Maldito',
    'cursed_hatch':'💥 Eclosión Maldita',
    'pikachu_normal':'🎃⚡ Pikachu Halloween',
    'pikachu_shiny':'✨🎃⚡ Pikachu Halloween Shiny',
    'halloween_box':'🎃📦 Caja Pokémon Halloween',
    'shop':'🛒 Tienda Halloween',
}


def _gender_rate(species_id:int)->int:
    sid=int(species_id)
    if sid in _GENDERLESS:return -1
    if sid in _MALE_ONLY:return 0
    if sid in _FEMALE_ONLY:return 8
    if sid in _FEMALE_75:return 6
    if sid in _FEMALE_25:return 2
    if sid in _FEMALE_12_5:return 1
    return 4


def _roll_sex(species_id:int)->str:
    rate=_gender_rate(species_id)
    if rate<0:return 'N'
    if rate==0:return 'M'
    if rate>=8:return 'F'
    return 'F' if random.randrange(8)<rate else 'M'


def _sex_symbol(sex:str|None)->str:
    return {'M':'♂','F':'♀','N':'⚪'}.get(str(sex or '').upper(),'⚪')


def _sex_text(sex:str|None)->str:
    return {'M':'♂ Macho','F':'♀ Hembra','N':'⚪ Sin sexo'}.get(str(sex or '').upper(),'⚪ Sin sexo')


# Grupos Huevo oficiales aplicados a las especies Gen 1.
# IDs: 1 Monster, 2 Water1, 3 Bug, 4 Flying, 5 Field/Ground, 6 Fairy,
# 7 Grass/Plant, 8 Human-Like, 9 Water3, 10 Mineral, 11 Amorphous,
# 12 Water2, 13 Ditto, 14 Dragon, 15 Undiscovered/No Eggs.
EGG_GROUPS:dict[int,frozenset[int]]={}
def _eg(ids, *groups):
    for _sid in ids: EGG_GROUPS[int(_sid)]=frozenset(int(g) for g in groups)
_eg(range(1,4),1,7); _eg(range(4,7),1,14); _eg(range(7,10),1,2)
_eg(range(10,16),3); _eg(range(16,19),4); _eg(range(19,21),5); _eg(range(21,23),4)
_eg(range(23,25),5,14); _eg(range(25,27),5,6); _eg(range(27,29),5); _eg([29],1,5); _eg([30,31],15)
_eg(range(32,35),1,5); _eg(range(35,37),6); _eg(range(37,39),5); _eg(range(39,41),6); _eg(range(41,43),4)
_eg(range(43,46),7); _eg(range(46,48),3,7); _eg(range(48,50),3); _eg(range(50,54),5); _eg(range(54,56),2,5)
_eg(range(56,60),5); _eg(range(60,63),2); _eg(range(63,69),8); _eg(range(69,72),7); _eg(range(72,74),9)
_eg(range(74,77),10); _eg(range(77,79),5); _eg(range(79,81),1,2); _eg(range(81,83),10); _eg([83],4,5)
_eg(range(84,86),4); _eg(range(86,88),2,5); _eg(range(88,90),11); _eg(range(90,92),9); _eg(range(92,95),11)
_eg([95],10); _eg(range(96,98),8); _eg(range(98,100),9); _eg(range(100,102),10); _eg(range(102,104),7)
_eg(range(104,106),1); _eg(range(106,108),8); _eg([108],1); _eg(range(109,111),11); _eg(range(111,113),1,5)
_eg([113],6); _eg([114],7); _eg([115],1); _eg(range(116,118),2,14); _eg(range(118,120),12); _eg(range(120,122),9)
_eg([122],8); _eg([123],3); _eg(range(124,127),8); _eg([127],3); _eg([128],5); _eg(range(129,131),12,14)
_eg([131],1,2); _eg([132],13); _eg(range(133,137),5); _eg([137],10); _eg(range(138,142),2,9); _eg([142],4)
_eg([143],1); _eg(range(144,147),15); _eg(range(147,150),2,14); _eg(range(150,152),15)

# Forma Gen 1 que nace del huevo. No se introducen bebés de Gen 2.
BREED_BASE={}
def _base(ids, base):
    for _sid in ids: BREED_BASE[int(_sid)]=int(base)
for _a,_b in [((1,2,3),1),((4,5,6),4),((7,8,9),7),((10,11,12),10),((13,14,15),13),((16,17,18),16),
              ((19,20),19),((21,22),21),((23,24),23),((25,26),25),((27,28),27),((29,30,31),29),((32,33,34),32),
              ((35,36),35),((37,38),37),((39,40),39),((41,42),41),((43,44,45),43),((46,47),46),((48,49),48),
              ((50,51),50),((52,53),52),((54,55),54),((56,57),56),((58,59),58),((60,61,62),60),((63,64,65),63),
              ((66,67,68),66),((69,70,71),69),((72,73),72),((74,75,76),74),((77,78),77),((79,80),79),((81,82),81),
              ((84,85),84),((86,87),86),((88,89),88),((90,91),90),((92,93,94),92),((96,97),96),((98,99),98),
              ((100,101),100),((102,103),102),((104,105),104),((109,110),109),((111,112),111),((116,117),116),
              ((118,119),118),((120,121),120),((129,130),129),((133,134,135,136),133),((138,139),138),((140,141),140),
              ((147,148,149),147)]: _base(_a,_b)
for _sid in range(1,152): BREED_BASE.setdefault(_sid,_sid)


def _egg_groups(species_id:int)->frozenset[int]:
    return EGG_GROUPS.get(int(species_id),frozenset({15}))


def _breedable_species(species_id:int)->bool:
    return 15 not in _egg_groups(species_id)


def _breeding_compatible(species_a:int, sex_a:str, species_b:int, sex_b:str)->bool:
    a,b=int(species_a),int(species_b)
    if a==b==132:return False
    if not _breedable_species(a) or not _breedable_species(b):return False
    if a==132 or b==132:
        other=b if a==132 else a
        return other!=132 and _breedable_species(other)
    if sex_a not in ('M','F') or sex_b not in ('M','F') or sex_a==sex_b:return False
    return bool((_egg_groups(a)-{13,15}) & (_egg_groups(b)-{13,15}))


def _offspring_species(species_a:int, sex_a:str, species_b:int, sex_b:str)->int:
    a,b=int(species_a),int(species_b)
    if a==132: parent=b
    elif b==132: parent=a
    else: parent=a if sex_a=='F' else b
    base=int(BREED_BASE.get(parent,parent))
    # Nidoran puede producir cualquiera de las dos ramas Gen 1.
    if base in (29,32):return random.choice([29,32])
    return base


def _gift_egg_pool(tier:str)->list[int]:
    bases=sorted({int(BREED_BASE.get(i,i)) for i in range(1,152) if i not in set(LEGENDARY_IDS)})
    pool=[i for i in bases if rarity_for(i)==tier and i not in set(LEGENDARY_IDS)]
    if not pool and tier=='epico':pool=[i for i in bases if rarity_for(i) in ('epico','raro') and i not in set(LEGENDARY_IDS)]
    return pool or [i for i in bases if i not in set(LEGENDARY_IDS)]


def _roll_gift_egg_species(tier:str)->int:
    return random.choice(_gift_egg_pool(tier))


def _egg_progress_text(progress:int)->str:
    p=max(0,min(EGG_PROGRESS_MAX,int(progress))); pct=p/100
    full=min(10,int(pct//10)); bar='█'*full+'░'*(10-full)
    return f'{pct:.1f}%\n{bar}'


def _species_level_learnset(species_id:int)->list[tuple[int,str]]:
    """Learnset compacto de PiBot, pero sin recortar a los 4 movimientos actuales."""
    sid=int(species_id)
    rows=SPECIAL_LEARNSETS.get(sid)
    if rows is None:
        rows=[(1,'tackle'),(12,'quick_attack'),(24,'body_slam')]
        for tp in TYPES.get(sid,('Normal',)):
            rows.extend(TYPE_MOVESETS.get(tp,[]))
    out=[]; seen=set()
    for req,code in sorted(rows,key=lambda x:(int(x[0]),str(x[1]))):
        req=int(req); code=str(code)
        if code not in MOVES or (req,code) in seen:continue
        seen.add((req,code)); out.append((req,code))
    return out


def _species_moves_at_level(species_id:int,level:int)->list[str]:
    return [code for req,code in _species_level_learnset(species_id) if int(req)==int(level)]


def _queue_level_move_cursor(c,owner_id:int,pokemon_id:int,species_id:int,nickname,current_moves:list[str],move_code:str,notes:list[str])->None:
    """Aprende automáticamente con hueco; con 4 movimientos deja una decisión pendiente."""
    code=str(move_code)
    if code not in MOVES or code in current_moves:return
    # Si esta enseñanza ya fue resuelta antes (aprendida u omitida), no vuelve a molestar.
    c.execute("SELECT status FROM pokemon_move_learning_tb WHERE pokemon_id=%s AND move_code=%s ORDER BY request_id DESC LIMIT 1",(int(pokemon_id),code))
    hist=c.fetchone()
    if hist and str(hist[0]) in ('learned','skipped'):return
    mon_name=nickname or NAMES.get(int(species_id),'Pokémon'); move_name=MOVES[code][0]
    if len(current_moves)<4:
        current_moves.append(code)
        # Guardamos historial para no volver a proponérselo tras reinicios/migraciones.
        c.execute("""INSERT INTO pokemon_move_learning_tb(owner_id,pokemon_id,move_code,status,resolved_at)
                     VALUES(%s,%s,%s,'learned',NOW())""",(int(owner_id),int(pokemon_id),code))
        notes.append(f'📚 {mon_name} aprendió {move_name}.')
        return
    c.execute("""INSERT INTO pokemon_move_learning_tb(owner_id,pokemon_id,move_code,status)
                 SELECT %s,%s,%s,'pending'
                 WHERE NOT EXISTS(SELECT 1 FROM pokemon_move_learning_tb WHERE pokemon_id=%s AND move_code=%s AND status='pending')""",
              (int(owner_id),int(pokemon_id),code,int(pokemon_id),code))
    if c.rowcount:
        notes.append(f'🧠 {mon_name} quiere aprender {move_name}. Te mandaré el selector por privado.')


def _level_path_and_moves_cursor(c,owner_id:int,pokemon_id:int,species_id:int,nickname,old_level:int,new_level:int,current_moves:list[str],notes:list[str])->int:
    """Procesa niveles uno por uno: aprende movimientos y conserva el set elegido/MT."""
    species=int(species_id)
    for lv in range(int(old_level)+1,int(new_level)+1):
        for code in _species_moves_at_level(species,lv):
            _queue_level_move_cursor(c,owner_id,pokemon_id,species,nickname,current_moves,code,notes)
        # Evolución por nivel después de aprender los movimientos de ese nivel.
        while species in LEVEL_EVOLUTIONS and lv>=int(LEVEL_EVOLUTIONS[species][0]):
            old_species=species; species=int(LEVEL_EVOLUTIONS[species][1])
            c.execute("""INSERT INTO pokemon_pokedex_tb(owner_id,species_id,obtained_count) VALUES(%s,%s,1)
                         ON CONFLICT(owner_id,species_id) DO UPDATE SET last_obtained_at=NOW()""",(int(owner_id),species))
            notes.append(f'✨ {nickname or NAMES[old_species]} evolucionó a {NAMES[species]}.')
            # Al evolucionar, rellena huecos con movimientos naturales de la nueva forma
            # que ya correspondan a su nivel. No reemplaza nada sin permiso.
            if len(current_moves)<4:
                for req,code in _species_level_learnset(species):
                    if int(req)>lv:break
                    if code in current_moves:continue
                    _queue_level_move_cursor(c,owner_id,pokemon_id,species,nickname,current_moves,code,notes)
                    if len(current_moves)>=4:break
            # Si la forma evolucionada aprende algo exactamente al mismo nivel y ya
            # estaba completa, se ofrece mediante el selector normal.
            for code in _species_moves_at_level(species,lv):
                _queue_level_move_cursor(c,owner_id,pokemon_id,species,nickname,current_moves,code,notes)
    return species


def _repair_incomplete_level_moves_cursor(c)->int:
    """Repara sets viejos y recupera aprendizajes de nivel que quedaron saltados.

    - Con menos de 4 movimientos, completa huecos en orden cronológico.
    - Con 4 movimientos, solo encola movimientos posteriores al último movimiento
      natural que conserva el Pokémon; así no ofrece ataques viejos/debiles ni pisa MT.
    - Las decisiones pendientes se resuelven por privado, una por una.
    """
    c.execute("SELECT pokemon_id,owner_id,species_id,nickname,level,moves_json FROM pokemon_instances_tb ORDER BY pokemon_id")
    rows=c.fetchall(); changed=0
    for pid,owner,species,nick,level,moves_json in rows:
        try:moves=[str(x) for x in json.loads(moves_json or '[]') if str(x) in MOVES]
        except Exception:moves=[]
        # Quita duplicados conservando el orden elegido por el jugador.
        moves=list(dict.fromkeys(moves))[:4]
        learnset=[(int(req),str(code)) for req,code in _species_level_learnset(int(species)) if int(req)<=int(level)]
        req_by_code={}
        for req,code in learnset:req_by_code[code]=max(req,req_by_code.get(code,0))
        before=list(moves)

        # Primero rellena huecos con movimientos que ya debería conocer.
        for req,code in learnset:
            if len(moves)>=4:break
            if code not in moves:moves.append(code)
        if moves!=before:
            c.execute("UPDATE pokemon_instances_tb SET moves_json=%s,updated_at=NOW() WHERE pokemon_id=%s",(json.dumps(moves,ensure_ascii=False),int(pid)))
            changed+=1

        # Si el set ya está completo, recupera solo aprendizajes posteriores.
        natural_reqs=[req_by_code[m] for m in moves if m in req_by_code]
        # Si el jugador reemplazó TODO por MT/elecciones ajenas al learnset, respetamos su set.
        if len(moves)>=4 and not natural_reqs:
            continue
        frontier=max(natural_reqs,default=0)
        for req,code in learnset:
            if code in moves or req<=frontier:continue
            c.execute("SELECT status FROM pokemon_move_learning_tb WHERE pokemon_id=%s AND move_code=%s ORDER BY request_id DESC LIMIT 1",(int(pid),code))
            hist=c.fetchone()
            if hist and str(hist[0]) in ('learned','skipped','pending'):continue
            c.execute("""INSERT INTO pokemon_move_learning_tb(owner_id,pokemon_id,move_code,status)
                         VALUES(%s,%s,%s,'pending') ON CONFLICT DO NOTHING""",(int(owner),int(pid),code))
    return changed


def _move_learning_markup(request_id:int,current_moves:list[str]):
    rows=[]
    for idx,code in enumerate(current_moves[:4]):
        name=MOVES.get(code,(code,))[0]
        rows.append([InlineKeyboardButton(f'↪️ Olvidar {name}',callback_data=f'pk:learnreplace:{int(request_id)}:{idx}')])
    rows.append([InlineKeyboardButton('❌ No aprenderlo',callback_data=f'pk:learnskip:{int(request_id)}')])
    return InlineKeyboardMarkup(rows)


async def _notify_pending_move_learning(context:ContextTypes.DEFAULT_TYPE,owner_id:int|None=None):
    conn=_get_connection(); pending=[]
    try:
        c=conn.cursor(); params=[]
        where="ml.status='pending' AND ml.notified_at IS NULL"
        if owner_id is not None:
            where += ' AND ml.owner_id=%s'; params.append(int(owner_id))
        c.execute(f"""SELECT ml.request_id,ml.owner_id,ml.pokemon_id,ml.move_code,p.species_id,p.nickname,p.moves_json
                      FROM pokemon_move_learning_tb ml
                      JOIN pokemon_instances_tb p ON p.pokemon_id=ml.pokemon_id AND p.owner_id=ml.owner_id
                      WHERE {where}
                        AND NOT EXISTS (
                          SELECT 1 FROM pokemon_move_learning_tb prev
                          WHERE prev.pokemon_id=ml.pokemon_id AND prev.status='pending'
                            AND prev.request_id<ml.request_id
                        )
                      ORDER BY ml.request_id ASC LIMIT 30""",tuple(params))
        pending=c.fetchall(); conn.rollback()
    except Exception as e:
        conn.rollback(); print('[PK move learn pending]',type(e).__name__,e)
    finally:_put_connection(conn)
    for req,owner,pid,code,species,nick,moves_json in pending:
        try:moves=[str(x) for x in json.loads(moves_json or '[]') if str(x) in MOVES]
        except Exception:moves=[]
        if code in moves:
            conn=_get_connection()
            try:
                c=conn.cursor(); c.execute("UPDATE pokemon_move_learning_tb SET status='learned',resolved_at=NOW() WHERE request_id=%s AND status='pending'",(int(req),)); conn.commit()
            except Exception:conn.rollback()
            finally:_put_connection(conn)
            continue
        if len(moves)<4:
            moves.append(str(code)); conn=_get_connection()
            try:
                c=conn.cursor(); c.execute("UPDATE pokemon_instances_tb SET moves_json=%s,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s",(json.dumps(moves,ensure_ascii=False),int(owner),int(pid)))
                c.execute("UPDATE pokemon_move_learning_tb SET status='learned',resolved_at=NOW() WHERE request_id=%s AND status='pending'",(int(req),)); conn.commit()
            except Exception:conn.rollback()
            finally:_put_connection(conn)
            continue
        mon_name=nick or NAMES.get(int(species),'Pokémon'); move_name=MOVES.get(str(code),(str(code),))[0]
        try:
            await context.bot.send_message(int(owner),f'🧠 {mon_name} quiere aprender {move_name}.\n\nYa conoce 4 movimientos. ¿Cuál quieres olvidar?',reply_markup=_move_learning_markup(int(req),moves))
        except Exception:
            continue
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("UPDATE pokemon_move_learning_tb SET notified_at=NOW() WHERE request_id=%s AND status='pending' AND notified_at IS NULL",(int(req),)); conn.commit()
        except Exception:conn.rollback()
        finally:_put_connection(conn)


def ensure_pokemon_tables():
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_instances_tb(
              pokemon_id BIGSERIAL PRIMARY KEY,
              owner_id BIGINT NOT NULL,
              species_id SMALLINT NOT NULL CHECK(species_id BETWEEN 1 AND 151),
              nickname TEXT,
              level SMALLINT NOT NULL DEFAULT 5 CHECK(level BETWEEN 1 AND 100),
              xp BIGINT NOT NULL DEFAULT 0,
              moves_json TEXT NOT NULL DEFAULT '[]',
              media_type TEXT,
              media_file_id TEXT,
              wins INT NOT NULL DEFAULT 0,
              losses INT NOT NULL DEFAULT 0,
              obtained_from TEXT NOT NULL DEFAULT 'caja',
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_owner ON pokemon_instances_tb(owner_id,pokemon_id)")
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS shiny BOOLEAN NOT NULL DEFAULT FALSE")
        # DVs/IVs estilo Gen 1: 0-15. HP se deriva de los otros cuatro.
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS iv_atk SMALLINT")
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS iv_def SMALLINT")
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS iv_spd SMALLINT")
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS iv_spc SMALLINT")
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS iv_hp SMALLINT")
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS held_item_code TEXT")
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS sex TEXT")
        # Repara Pokémon viejos cuya XP interna quedó por debajo de la base de su nivel.
        c.execute("UPDATE pokemon_instances_tb SET xp=GREATEST(xp,25*(level-1)*(level-1))")
        c.execute("""
            UPDATE pokemon_instances_tb SET
              iv_atk=COALESCE(iv_atk,FLOOR(random()*16)::int),
              iv_def=COALESCE(iv_def,FLOOR(random()*16)::int),
              iv_spd=COALESCE(iv_spd,FLOOR(random()*16)::int),
              iv_spc=COALESCE(iv_spc,FLOOR(random()*16)::int)
            WHERE iv_atk IS NULL OR iv_def IS NULL OR iv_spd IS NULL OR iv_spc IS NULL
        """)
        c.execute("""
            UPDATE pokemon_instances_tb SET iv_hp=
              ((iv_atk & 1)*8)+((iv_def & 1)*4)+((iv_spd & 1)*2)+(iv_spc & 1)
            WHERE iv_hp IS NULL
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_species ON pokemon_instances_tb(owner_id,species_id)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_team_tb(
              owner_id BIGINT PRIMARY KEY,
              slot1 BIGINT,
              slot2 BIGINT,
              slot3 BIGINT,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("ALTER TABLE pokemon_team_tb ADD COLUMN IF NOT EXISTS slot4 BIGINT")
        c.execute("ALTER TABLE pokemon_team_tb ADD COLUMN IF NOT EXISTS principal_pokemon_id BIGINT")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_pokedex_tb(
              owner_id BIGINT NOT NULL,
              species_id SMALLINT NOT NULL,
              obtained_count INT NOT NULL DEFAULT 1,
              first_obtained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              last_obtained_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY(owner_id,species_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_items_tb(
              owner_id BIGINT NOT NULL,
              item_code TEXT NOT NULL,
              qty INT NOT NULL DEFAULT 0,
              PRIMARY KEY(owner_id,item_code)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_move_learning_tb(
              request_id BIGSERIAL PRIMARY KEY,
              owner_id BIGINT NOT NULL,
              pokemon_id BIGINT NOT NULL,
              move_code TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              notified_at TIMESTAMPTZ,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              resolved_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_move_learning_owner ON pokemon_move_learning_tb(owner_id,status,request_id)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_pokemon_move_learning_pending ON pokemon_move_learning_tb(pokemon_id,move_code) WHERE status='pending'")
        # Corrige Pokémon viejos que tenían menos de 4 movimientos sin tocar sets completos/MT.
        _repair_incomplete_level_moves_cursor(c)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_rank_tb(
              user_id BIGINT PRIMARY KEY,
              rating INT NOT NULL DEFAULT 1000,
              wins INT NOT NULL DEFAULT 0,
              losses INT NOT NULL DEFAULT 0,
              current_streak INT NOT NULL DEFAULT 0,
              best_streak INT NOT NULL DEFAULT 0,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("ALTER TABLE pokemon_rank_tb ADD COLUMN IF NOT EXISTS season_best_streak INT NOT NULL DEFAULT 0")
        c.execute("ALTER TABLE pokemon_rank_tb ADD COLUMN IF NOT EXISTS peak_rating INT NOT NULL DEFAULT 1000")
        c.execute("ALTER TABLE pokemon_rank_tb ADD COLUMN IF NOT EXISTS rating_reached_at TIMESTAMPTZ NOT NULL DEFAULT NOW()")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_rank_season_state_tb(
              singleton SMALLINT PRIMARY KEY DEFAULT 1 CHECK(singleton=1),
              season_key TEXT NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_rank_history_tb(
              season_key TEXT NOT NULL,
              user_id BIGINT NOT NULL,
              position INT NOT NULL,
              rating INT NOT NULL,
              wins INT NOT NULL,
              losses INT NOT NULL,
              best_streak INT NOT NULL DEFAULT 0,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY(season_key,user_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_season_boxes_tb(
              box_id BIGSERIAL PRIMARY KEY,
              owner_id BIGINT NOT NULL,
              season_key TEXT NOT NULL,
              placement SMALLINT NOT NULL CHECK(placement BETWEEN 1 AND 3),
              opened BOOLEAN NOT NULL DEFAULT FALSE,
              pokemon_id BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              opened_at TIMESTAMPTZ,
              UNIQUE(owner_id,season_key)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_tournaments_tb(
              tournament_id BIGSERIAL PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT,
              created_by BIGINT NOT NULL,
              mode SMALLINT NOT NULL CHECK(mode BETWEEN 1 AND 3),
              status TEXT NOT NULL DEFAULT 'registration',
              round_no INT NOT NULL DEFAULT 0,
              message_id BIGINT,
              champion_id BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              started_at TIMESTAMPTZ,
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_tournament_active ON pokemon_tournaments_tb(chat_id,thread_id,status)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_tournament_players_tb(
              tournament_id BIGINT NOT NULL,
              user_id BIGINT NOT NULL,
              joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY(tournament_id,user_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_tournament_matches_tb(
              match_id BIGSERIAL PRIMARY KEY,
              tournament_id BIGINT NOT NULL,
              round_no INT NOT NULL,
              slot_no INT NOT NULL,
              user_a BIGINT NOT NULL,
              user_b BIGINT,
              winner_id BIGINT,
              battle_id BIGINT,
              status TEXT NOT NULL DEFAULT 'pending',
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_tournament_match ON pokemon_tournament_matches_tb(tournament_id,round_no,status)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_battles_tb(
              battle_id BIGSERIAL PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT,
              challenger_id BIGINT NOT NULL,
              opponent_id BIGINT,
              mode SMALLINT,
              status TEXT NOT NULL DEFAULT 'open',
              state_json TEXT,
              message_id BIGINT,
              winner_id BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_battle_status ON pokemon_battles_tb(status,challenger_id,opponent_id)")
        c.execute("ALTER TABLE pokemon_battles_tb ADD COLUMN IF NOT EXISTS tournament_match_id BIGINT")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_trades_tb(
              trade_id BIGSERIAL PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT,
              user_a BIGINT NOT NULL,
              user_b BIGINT NOT NULL,
              pokemon_a BIGINT,
              pokemon_b BIGINT,
              confirm_a BOOLEAN NOT NULL DEFAULT FALSE,
              confirm_b BOOLEAN NOT NULL DEFAULT FALSE,
              status TEXT NOT NULL DEFAULT 'selecting',
              message_id BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_trade_users ON pokemon_trades_tb(status,user_a,user_b)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_trainer_tb(
              user_id BIGINT PRIMARY KEY,
              wild_catches INT NOT NULL DEFAULT 0,
              released INT NOT NULL DEFAULT 0,
              candies_earned INT NOT NULL DEFAULT 0,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("ALTER TABLE pokemon_trainer_tb ADD COLUMN IF NOT EXISTS media_type TEXT")
        c.execute("ALTER TABLE pokemon_trainer_tb ADD COLUMN IF NOT EXISTS media_file_id TEXT")
        c.execute("ALTER TABLE pokemon_trainer_tb ADD COLUMN IF NOT EXISTS tournament_wins INT NOT NULL DEFAULT 0")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_candies_tb(
              owner_id BIGINT NOT NULL,
              family_species_id SMALLINT NOT NULL CHECK(family_species_id BETWEEN 1 AND 151),
              qty INT NOT NULL DEFAULT 0,
              PRIMARY KEY(owner_id,family_species_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_settings_tb(
              setting_key TEXT PRIMARY KEY,
              setting_value TEXT,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        # Compatibilidad: convierte una sola vez los viejos caramelos universales
        # en Caramelos Raros, 1:1, para no perder saldos existentes.
        c.execute("SELECT setting_value FROM pokemon_settings_tb WHERE setting_key='rare_candy_migration_v1'")
        if not c.fetchone():
            c.execute("""
                INSERT INTO pokemon_items_tb(owner_id,item_code,qty)
                SELECT owner_id,'rare_candy',SUM(qty)::int
                FROM pokemon_candies_tb WHERE qty>0 GROUP BY owner_id
                ON CONFLICT(owner_id,item_code) DO UPDATE
                SET qty=pokemon_items_tb.qty+EXCLUDED.qty
            """)
            c.execute("UPDATE pokemon_candies_tb SET qty=0 WHERE qty>0")
            c.execute("""INSERT INTO pokemon_settings_tb(setting_key,setting_value) VALUES('rare_candy_migration_v1','done')
                         ON CONFLICT(setting_key) DO UPDATE SET setting_value='done',updated_at=NOW()""")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_wild_spawns_tb(
              spawn_id BIGSERIAL PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT,
              species_id SMALLINT NOT NULL CHECK(species_id BETWEEN 1 AND 151),
              level SMALLINT NOT NULL CHECK(level BETWEEN 1 AND 100),
              shiny BOOLEAN NOT NULL DEFAULT FALSE,
              is_returning BOOLEAN NOT NULL DEFAULT FALSE,
              status TEXT NOT NULL DEFAULT 'active',
              message_id BIGINT,
              caught_by BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_wild_active ON pokemon_wild_spawns_tb(chat_id,thread_id,status)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_wild_attempts_tb(
              spawn_id BIGINT NOT NULL,
              user_id BIGINT NOT NULL,
              attempts SMALLINT NOT NULL DEFAULT 0,
              PRIMARY KEY(spawn_id,user_id)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_training_daily_tb(
              user_id BIGINT NOT NULL,
              training_date DATE NOT NULL,
              completed SMALLINT NOT NULL DEFAULT 0 CHECK(completed BETWEEN 0 AND 3),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY(user_id,training_date)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_training_sessions_tb(
              training_id BIGSERIAL PRIMARY KEY,
              battle_id BIGINT NOT NULL UNIQUE,
              user_id BIGINT NOT NULL,
              training_date DATE NOT NULL,
              rival_avg_level SMALLINT NOT NULL CHECK(rival_avg_level BETWEEN 1 AND 100),
              status TEXT NOT NULL DEFAULT 'active',
              result TEXT,
              xp_per_pokemon INT,
              pipesos_reward INT,
              held_item_drop TEXT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_training_user_date ON pokemon_training_sessions_tb(user_id,training_date,status)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_item_transfers_tb(
              transfer_id BIGSERIAL PRIMARY KEY,
              sender_id BIGINT NOT NULL,
              recipient_id BIGINT NOT NULL,
              item_code TEXT NOT NULL,
              qty INT NOT NULL CHECK(qty>0),
              category TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_transfer_pending ON pokemon_item_transfers_tb(sender_id,status,created_at)")
        # NPCs, líderes, medallas y encuentros legendarios especiales.
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_npc_media_tb(
              npc_key TEXT PRIMARY KEY,
              media_type TEXT NOT NULL,
              media_file_id TEXT NOT NULL,
              updated_by BIGINT NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_npc_encounters_tb(
              encounter_id BIGSERIAL PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT,
              npc_key TEXT NOT NULL,
              encounter_type TEXT NOT NULL CHECK(encounter_type IN ('normal','leader')),
              mode SMALLINT NOT NULL CHECK(mode BETWEEN 1 AND 3),
              status TEXT NOT NULL DEFAULT 'active',
              claimed_by BIGINT,
              selected_json TEXT NOT NULL DEFAULT '[]',
              message_id BIGINT,
              battle_id BIGINT,
              is_manual BOOLEAN NOT NULL DEFAULT FALSE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW()+INTERVAL '10 minutes'),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("ALTER TABLE pokemon_npc_encounters_tb ADD COLUMN IF NOT EXISTS is_manual BOOLEAN NOT NULL DEFAULT FALSE")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_npc_active ON pokemon_npc_encounters_tb(chat_id,thread_id,status,created_at)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_badges_tb(
              user_id BIGINT NOT NULL,
              leader_key TEXT NOT NULL,
              earned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY(user_id,leader_key)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_kanto_completion_tb(
              user_id BIGINT PRIMARY KEY,
              rewarded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_leader_bonus_tb(
              battle_id BIGINT PRIMARY KEY,
              user_id BIGINT NOT NULL,
              eligible_pokemon_json TEXT NOT NULL,
              claimed_pokemon_id BIGINT,
              claimed_at TIMESTAMPTZ
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_legendary_encounters_tb(
              encounter_id BIGSERIAL PRIMARY KEY,
              owner_id BIGINT NOT NULL,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT,
              species_id SMALLINT NOT NULL CHECK(species_id BETWEEN 1 AND 151),
              level SMALLINT NOT NULL CHECK(level BETWEEN 1 AND 100),
              shiny BOOLEAN NOT NULL DEFAULT FALSE,
              attempts SMALLINT NOT NULL DEFAULT 0,
              max_attempts SMALLINT NOT NULL DEFAULT 3,
              status TEXT NOT NULL DEFAULT 'active',
              message_id BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW()+INTERVAL '10 minutes'),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_legendary_owner ON pokemon_legendary_encounters_tb(owner_id,status,created_at)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_eggs_tb(
              egg_id BIGSERIAL PRIMARY KEY,
              owner_id BIGINT NOT NULL,
              source TEXT NOT NULL,
              egg_tier TEXT NOT NULL CHECK(egg_tier IN ('comun','raro','epico')),
              species_id SMALLINT NOT NULL CHECK(species_id BETWEEN 1 AND 151),
              progress INT NOT NULL DEFAULT 0 CHECK(progress BETWEEN 0 AND 10000),
              status TEXT NOT NULL DEFAULT 'active',
              parent_a BIGINT,
              parent_b BIGINT,
              parent_a_species SMALLINT,
              parent_b_species SMALLINT,
              shiny BOOLEAN NOT NULL DEFAULT FALSE,
              iv_atk SMALLINT NOT NULL,
              iv_def SMALLINT NOT NULL,
              iv_spd SMALLINT NOT NULL,
              iv_spc SMALLINT NOT NULL,
              pokemon_id BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              hatched_at TIMESTAMPTZ
            )
        """)
        # Antes solo se permitía 1 huevo vivo por usuario. Desde esta versión se permiten hasta 3.
        c.execute("DROP INDEX IF EXISTS idx_pokemon_one_live_egg")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_eggs_owner ON pokemon_eggs_tb(owner_id,status,created_at)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_breedings_tb(
              breeding_id BIGSERIAL PRIMARY KEY,
              owner_id BIGINT NOT NULL,
              parent_a BIGINT NOT NULL,
              parent_b BIGINT NOT NULL,
              parent_a_species SMALLINT NOT NULL,
              parent_b_species SMALLINT NOT NULL,
              species_id SMALLINT NOT NULL CHECK(species_id BETWEEN 1 AND 151),
              egg_tier TEXT NOT NULL CHECK(egg_tier IN ('comun','raro','epico')),
              shiny BOOLEAN NOT NULL DEFAULT FALSE,
              iv_atk SMALLINT NOT NULL,
              iv_def SMALLINT NOT NULL,
              iv_spd SMALLINT NOT NULL,
              iv_spc SMALLINT NOT NULL,
              status TEXT NOT NULL DEFAULT 'waiting',
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              ready_at TIMESTAMPTZ NOT NULL DEFAULT (NOW()+INTERVAL '30 minutes'),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pokemon_one_waiting_breeding ON pokemon_breedings_tb(owner_id) WHERE status='waiting'")
        c.execute("CREATE INDEX IF NOT EXISTS idx_pokemon_breedings_ready ON pokemon_breedings_tb(status,ready_at)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_halloween_wallet_tb(
              user_id BIGINT PRIMARY KEY,
              candies INT NOT NULL DEFAULT 0 CHECK(candies>=0),
              earned_total BIGINT NOT NULL DEFAULT 0,
              spent_total BIGINT NOT NULL DEFAULT 0,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_halloween_media_tb(
              media_key TEXT PRIMARY KEY,
              media_type TEXT NOT NULL,
              media_file_id TEXT NOT NULL,
              updated_by BIGINT NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_halloween_events_tb(
              event_id BIGSERIAL PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT NOT NULL DEFAULT 0,
              event_kind TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active',
              message_id BIGINT,
              claimed_by BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW()+INTERVAL '30 minutes'),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_halloween_events_active ON pokemon_halloween_events_tb(chat_id,thread_id,status,created_at)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_egg_media_tb(
              egg_key TEXT PRIMARY KEY,
              media_type TEXT NOT NULL,
              media_file_id TEXT NOT NULL,
              updated_by BIGINT NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_egg_events_tb(
              event_id BIGSERIAL PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT NOT NULL DEFAULT 0,
              event_date DATE NOT NULL,
              egg_tier TEXT NOT NULL,
              species_id SMALLINT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active',
              message_id BIGINT,
              claimed_by BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW()+INTERVAL '1 hour'),
              finished_at TIMESTAMPTZ,
              UNIQUE(chat_id,thread_id,event_date)
            )
        """)
        # Expansión: Safari diario.
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_safari_sessions_tb(
              session_id BIGSERIAL PRIMARY KEY,
              user_id BIGINT NOT NULL,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT,
              safari_date DATE NOT NULL,
              status TEXT NOT NULL DEFAULT 'active',
              balls INT NOT NULL DEFAULT 10,
              current_species SMALLINT,
              current_level SMALLINT,
              current_shiny BOOLEAN,
              current_ivs_json TEXT,
              current_defeated BOOLEAN NOT NULL DEFAULT FALSE,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW()+INTERVAL '30 minutes'),
              finished_at TIMESTAMPTZ,
              UNIQUE(user_id,safari_date)
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_safari_active ON pokemon_safari_sessions_tb(user_id,status,expires_at)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_safari_battles_tb(
              battle_id BIGINT PRIMARY KEY,
              session_id BIGINT NOT NULL,
              user_id BIGINT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        # Team Rocket grupal.
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_rocket_events_tb(
              event_id BIGSERIAL PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT NOT NULL DEFAULT 0,
              event_date DATE NOT NULL,
              status TEXT NOT NULL DEFAULT 'active',
              stage INT NOT NULL DEFAULT 0,
              message_id BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW()+INTERVAL '30 minutes'),
              finished_at TIMESTAMPTZ,
              UNIQUE(chat_id,thread_id,event_date)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_rocket_participants_tb(
              event_id BIGINT NOT NULL,
              user_id BIGINT NOT NULL,
              wins INT NOT NULL DEFAULT 0,
              PRIMARY KEY(event_id,user_id)
            )
        """)
        c.execute("ALTER TABLE pokemon_npc_encounters_tb ADD COLUMN IF NOT EXISTS event_ref BIGINT")
        # Incursiones grupales con PS compartidos.
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_raids_tb(
              raid_id BIGSERIAL PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT NOT NULL DEFAULT 0,
              species_id SMALLINT NOT NULL,
              level SMALLINT NOT NULL,
              max_hp INT NOT NULL,
              hp INT NOT NULL,
              status TEXT NOT NULL DEFAULT 'active',
              message_id BIGINT,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              expires_at TIMESTAMPTZ NOT NULL DEFAULT (NOW()+INTERVAL '45 minutes'),
              finished_at TIMESTAMPTZ
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_raid_participants_tb(
              raid_id BIGINT NOT NULL,
              user_id BIGINT NOT NULL,
              damage INT NOT NULL DEFAULT 0,
              attacks INT NOT NULL DEFAULT 0,
              last_attack_at TIMESTAMPTZ,
              PRIMARY KEY(raid_id,user_id)
            )
        """)
        # Captura especial de incursiones legendarias. Se añaden con ALTER para actualizar instalaciones existentes.
        c.execute("ALTER TABLE pokemon_raids_tb ADD COLUMN IF NOT EXISTS is_legendary BOOLEAN NOT NULL DEFAULT FALSE")
        c.execute("ALTER TABLE pokemon_raids_tb ADD COLUMN IF NOT EXISTS shiny BOOLEAN NOT NULL DEFAULT FALSE")
        c.execute("ALTER TABLE pokemon_raids_tb ADD COLUMN IF NOT EXISTS catcher_id BIGINT")
        c.execute("ALTER TABLE pokemon_raids_tb ADD COLUMN IF NOT EXISTS capture_attempts INT NOT NULL DEFAULT 0")
        c.execute("ALTER TABLE pokemon_raids_tb ADD COLUMN IF NOT EXISTS capture_status TEXT NOT NULL DEFAULT 'none'")
        # Misiones, logros, Liga, Pokédex y clima.
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_daily_missions_tb(
              user_id BIGINT NOT NULL,
              mission_date DATE NOT NULL,
              captures INT NOT NULL DEFAULT 0,
              wins INT NOT NULL DEFAULT 0,
              trainings INT NOT NULL DEFAULT 0,
              claimed BOOLEAN NOT NULL DEFAULT FALSE,
              PRIMARY KEY(user_id,mission_date)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_achievements_tb(
              user_id BIGINT NOT NULL,
              achievement_key TEXT NOT NULL,
              claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY(user_id,achievement_key)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_dex_milestones_tb(
              user_id BIGINT NOT NULL,
              milestone INT NOT NULL,
              claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY(user_id,milestone)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_dex_rewards_tb(
              user_id BIGINT PRIMARY KEY,
              claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              pokemon_id BIGINT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_league_progress_tb(
              user_id BIGINT PRIMARY KEY,
              stage INT NOT NULL DEFAULT 0,
              champion_done BOOLEAN NOT NULL DEFAULT FALSE,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_world_state_tb(
              state_key TEXT PRIMARY KEY,
              state_value TEXT,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_fugitives_tb(
              fugitive_id BIGSERIAL PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              thread_id BIGINT NOT NULL DEFAULT 0,
              species_id SMALLINT NOT NULL,
              level SMALLINT NOT NULL,
              shiny BOOLEAN NOT NULL DEFAULT FALSE,
              status TEXT NOT NULL DEFAULT 'waiting',
              last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("ALTER TABLE pokemon_wild_spawns_tb ADD COLUMN IF NOT EXISTS is_returning BOOLEAN NOT NULL DEFAULT FALSE")
        c.execute("ALTER TABLE pokemon_instances_tb ADD COLUMN IF NOT EXISTS friendship INT NOT NULL DEFAULT 0")
        c.execute("""
            CREATE TABLE IF NOT EXISTS pokemon_streak_rewards_tb(
              user_id BIGINT NOT NULL,
              threshold INT NOT NULL,
              season_key TEXT NOT NULL,
              claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY(user_id,threshold,season_key)
            )
        """)
        # Asigna sexo una sola vez a ejemplares anteriores. Después queda persistido.
        c.execute("SELECT pokemon_id,species_id FROM pokemon_instances_tb WHERE sex IS NULL")
        for _pid,_sid in c.fetchall():
            c.execute("UPDATE pokemon_instances_tb SET sex=%s WHERE pokemon_id=%s",(_roll_sex(int(_sid)),int(_pid)))
        _pokemon_season_rollover_cursor(c)
        conn.commit()
    except Exception as e:
        conn.rollback()
        print('[POKEMON tables]', type(e).__name__, e)
        raise
    finally:
        _put_connection(conn)



def _pokemon_month_key(now:datetime|None=None)->str:
    now = now or datetime.now(POKEMON_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=POKEMON_TZ)
    else:
        now = now.astimezone(POKEMON_TZ)
    return now.strftime('%Y-%m')


def _wild_period(now:datetime|None=None)->str:
    now = (now or datetime.now(POKEMON_TZ)).astimezone(POKEMON_TZ)
    return 'day' if 6 <= now.hour < 18 else 'night'


def _pokemon_season_rollover_cursor(c):
    """Cierra el ranking mensual una sola vez y deja las recompensas listas."""
    current = _pokemon_month_key()
    c.execute("SELECT season_key FROM pokemon_rank_season_state_tb WHERE singleton=1 FOR UPDATE")
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO pokemon_rank_season_state_tb(singleton,season_key) VALUES(1,%s)", (current,))
        return None
    previous = str(row[0])
    if previous == current:
        return None

    c.execute("""
        SELECT user_id,rating,wins,losses,season_best_streak,rating_reached_at
        FROM pokemon_rank_tb
        WHERE (wins+losses)>0
        ORDER BY rating DESC,wins DESC,rating_reached_at ASC,user_id ASC
    """)
    rows = c.fetchall()
    winners = []
    for pos,r in enumerate(rows,1):
        uid,rating,wins,losses,season_best,_ = r
        c.execute("""
            INSERT INTO pokemon_rank_history_tb(season_key,user_id,position,rating,wins,losses,best_streak)
            VALUES(%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(season_key,user_id) DO NOTHING
        """, (previous,int(uid),pos,int(rating),int(wins),int(losses),int(season_best or 0)))
        if pos <= 3:
            prize = int(POKEMON_SEASON_PRIZES[pos])
            c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s", (prize,int(uid)))
            c.execute("""
                INSERT INTO pokemon_season_boxes_tb(owner_id,season_key,placement)
                VALUES(%s,%s,%s) ON CONFLICT(owner_id,season_key) DO NOTHING
            """, (int(uid),previous,pos))
            winners.append((pos,int(uid),prize))

    c.execute("""
        UPDATE pokemon_rank_tb SET rating=1000,wins=0,losses=0,current_streak=0,
        season_best_streak=0,rating_reached_at=NOW(),updated_at=NOW()
    """)
    c.execute("UPDATE pokemon_rank_season_state_tb SET season_key=%s,updated_at=NOW() WHERE singleton=1", (current,))
    return {'closed':previous,'current':current,'winners':winners}


def _ensure_pokemon_season():
    conn=_get_connection()
    try:
        c=conn.cursor(); result=_pokemon_season_rollover_cursor(c); conn.commit(); return result
    except Exception as e:
        conn.rollback(); print('[PK season rollover]',type(e).__name__,e); return None
    finally:
        _put_connection(conn)


def _pending_season_boxes(uid:int)->list[tuple]:
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""
            SELECT box_id,season_key,placement FROM pokemon_season_boxes_tb
            WHERE owner_id=%s AND opened=FALSE ORDER BY created_at,box_id
        """,(uid,)); return c.fetchall()
    finally:_put_connection(conn)


def _recent_wild_species_cursor(c,chat_id:int,thread_id:int|None,limit:int=8)->set[int]:
    c.execute("""
        SELECT species_id FROM pokemon_wild_spawns_tb
        WHERE chat_id=%s AND thread_id IS NOT DISTINCT FROM %s
        ORDER BY created_at DESC LIMIT %s
    """,(chat_id,thread_id,int(limit)))
    return {int(r[0]) for r in c.fetchall()}


def _wild_species_cursor(c,chat_id:int,thread_id:int|None)->int:
    legendary=list(LEGENDARY_IDS); epic=list(EPIC_IDS); rare=list(RARE_IDS)
    used=set(legendary)|set(epic)|set(rare)
    common=[i for i in range(1,152) if i not in used]
    rarity=random.choices(['comun','raro','epico','legendario'],[70,24,5.5,0.5],k=1)[0]
    base={'comun':common,'raro':rare,'epico':epic,'legendario':legendary}[rarity]
    recent=_recent_wild_species_cursor(c,chat_id,thread_id,8)
    candidates=[i for i in base if i not in recent]
    if not candidates:
        candidates=list(base)
    preferred=DAY_PREFERRED if _wild_period()=='day' else NIGHT_PREFERRED
    weather=_current_weather_cursor(c) if 'pokemon_world_state_tb' else 'despejado'
    boosted=set(WEATHER_TYPES.get(weather,()))
    weights=[]
    for i in candidates:
        w=4 if i in preferred else 1
        if boosted and any(tp in boosted for tp in TYPES.get(i,())):w*=3
        weights.append(w)
    return random.choices(candidates,weights=weights,k=1)[0]


def _tournament_active_cursor(c,chat_id:int,thread_id:int|None,statuses=('registration','active')):
    # statuses se mantiene en la firma por compatibilidad; los estados vivos son estos dos.
    c.execute("""
        SELECT tournament_id,mode,status,round_no,created_by,message_id,champion_id
        FROM pokemon_tournaments_tb
        WHERE chat_id=%s AND thread_id IS NOT DISTINCT FROM %s AND status IN ('registration','active')
        ORDER BY tournament_id DESC LIMIT 1
    """,(chat_id,thread_id))
    return c.fetchone()


def _tournament_name_cursor(c,uid:int)->str:
    return _display_name_cursor(c,uid)


def _tournament_round_text_cursor(c,tid:int)->str:
    c.execute("SELECT mode,status,round_no,champion_id FROM pokemon_tournaments_tb WHERE tournament_id=%s",(tid,)); tr=c.fetchone()
    if not tr:return '🏆 Torneo no encontrado.'
    mode,status,round_no,champion=tr
    c.execute("SELECT COUNT(*) FROM pokemon_tournament_players_tb WHERE tournament_id=%s",(tid,)); count=int(c.fetchone()[0])
    lines=[f'🏆 TORNEO POKÉMON #{tid} · {mode}v{mode}',f'👥 Participantes: {count}',f'📌 Estado: {status.upper()}']
    if status=='registration':
        lines += ['','Inscripciones abiertas.']
    elif status=='active':
        lines += ['',f'⚔️ Ronda {round_no}']
        c.execute("""SELECT slot_no,user_a,user_b,winner_id,status FROM pokemon_tournament_matches_tb
                     WHERE tournament_id=%s AND round_no=%s ORDER BY slot_no""",(tid,round_no))
        for slot,a,b,winner,mstatus in c.fetchall():
            an=_tournament_name_cursor(c,int(a)); bn=_tournament_name_cursor(c,int(b)) if b else 'Pase libre'
            mark='✅' if mstatus=='finished' else '⚔️'
            if b is None: mark='➡️'
            lines.append(f'{mark} {slot}. {an} vs {bn}')
    elif status=='finished' and champion:
        lines += ['',f'👑 Campeón: {_tournament_name_cursor(c,int(champion))}']
    return '\n'.join(lines)


def _create_tournament_round_cursor(c,tid:int,round_no:int,players:list[int]):
    players=[int(x) for x in players]
    slot=1
    for i in range(0,len(players),2):
        a=players[i]; b=players[i+1] if i+1<len(players) else None
        if b is None:
            c.execute("""INSERT INTO pokemon_tournament_matches_tb(tournament_id,round_no,slot_no,user_a,user_b,winner_id,status,finished_at)
                         VALUES(%s,%s,%s,%s,NULL,%s,'finished',NOW())""",(tid,round_no,slot,a,a))
        else:
            c.execute("""INSERT INTO pokemon_tournament_matches_tb(tournament_id,round_no,slot_no,user_a,user_b,status)
                         VALUES(%s,%s,%s,%s,%s,'pending')""",(tid,round_no,slot,a,b))
        slot+=1


def _advance_tournament_cursor(c,tid:int):
    c.execute("SELECT status,round_no FROM pokemon_tournaments_tb WHERE tournament_id=%s FOR UPDATE",(tid,)); tr=c.fetchone()
    if not tr or tr[0]!='active':return None
    round_no=int(tr[1])
    c.execute("SELECT COUNT(*) FROM pokemon_tournament_matches_tb WHERE tournament_id=%s AND round_no=%s AND status!='finished'",(tid,round_no))
    if int(c.fetchone()[0])>0:return None
    c.execute("SELECT winner_id FROM pokemon_tournament_matches_tb WHERE tournament_id=%s AND round_no=%s ORDER BY slot_no",(tid,round_no))
    winners=[int(r[0]) for r in c.fetchall() if r[0] is not None]
    if len(winners)==1:
        champion=winners[0]
        c.execute("UPDATE pokemon_tournaments_tb SET status='finished',champion_id=%s,finished_at=NOW() WHERE tournament_id=%s",(champion,tid))
        _ensure_trainer_row_cursor(c,champion)
        c.execute("UPDATE pokemon_trainer_tb SET tournament_wins=tournament_wins+1,updated_at=NOW() WHERE user_id=%s",(champion,))
        return {'finished':True,'champion':champion,'round':round_no}
    next_round=round_no+1
    _create_tournament_round_cursor(c,tid,next_round,winners)
    c.execute("UPDATE pokemon_tournaments_tb SET round_no=%s WHERE tournament_id=%s",(next_round,tid))
    # Si la nueva ronda fue un único pase libre, finaliza de inmediato.
    c.execute("SELECT COUNT(*) FROM pokemon_tournament_matches_tb WHERE tournament_id=%s AND round_no=%s AND status!='finished'",(tid,next_round))
    if int(c.fetchone()[0])==0:
        return _advance_tournament_cursor(c,tid)
    return {'finished':False,'round':next_round}


def _tournament_match_for_pair_cursor(c,chat_id:int,thread_id:int|None,a:int,b:int):
    c.execute("""
        SELECT m.match_id,t.tournament_id,t.mode
        FROM pokemon_tournament_matches_tb m
        JOIN pokemon_tournaments_tb t ON t.tournament_id=m.tournament_id
        WHERE t.chat_id=%s AND t.thread_id IS NOT DISTINCT FROM %s AND t.status='active'
          AND m.status='pending' AND ((m.user_a=%s AND m.user_b=%s) OR (m.user_a=%s AND m.user_b=%s))
        ORDER BY m.match_id DESC LIMIT 1
    """,(chat_id,thread_id,a,b,b,a))
    return c.fetchone()


def _record_tournament_battle_cursor(c,bid:int,winner:int):
    c.execute("SELECT tournament_match_id FROM pokemon_battles_tb WHERE battle_id=%s",(bid,)); r=c.fetchone()
    if not r or not r[0]:return None
    mid=int(r[0])
    c.execute("SELECT tournament_id,status FROM pokemon_tournament_matches_tb WHERE match_id=%s FOR UPDATE",(mid,)); mr=c.fetchone()
    if not mr or mr[1] not in ('pending','active'):return None
    tid=int(mr[0])
    c.execute("UPDATE pokemon_tournament_matches_tb SET winner_id=%s,status='finished',finished_at=NOW() WHERE match_id=%s",(winner,mid))
    return {'tournament_id':tid,'advance':_advance_tournament_cursor(c,tid)}


def _xp_floor(level:int)->int:
    # Curva compacta para Telegram; mantiene el progreso entre combates.
    return 25 * max(0, level - 1) ** 2


def _xp_step(level:int)->int:
    level=max(1,min(MAX_LEVEL,int(level)))
    if level>=MAX_LEVEL:return 0
    return max(1,_xp_floor(level+1)-_xp_floor(level))


def _combat_xp_amount(rival_avg_level:int, won:bool, kind:str)->int:
    """XP escalada al nivel rival para que progresar no dependa de farm infinito.

    Ritmo aproximado: PvP 4 victorias por nivel, NPC 3, entrenamiento 4
    y líder 2-3. Las derrotas también dan progreso, pero bastante menos.
    """
    level=max(1,min(MAX_LEVEL,int(rival_avg_level or 1)))
    step=_xp_step(level) or _xp_step(MAX_LEVEL-1)
    fractions={
        'pvp':(0.25,0.10),
        'npc':(0.32,0.14),
        'training':(0.26,0.12),
        'leader':(0.45,0.18),
    }
    win_frac,loss_frac=fractions.get(str(kind),(0.25,0.10))
    frac=win_frac if won else loss_frac
    minimums={
        'pvp':(25,10),
        'npc':(30,12),
        'training':(25,10),
        'leader':(40,15),
    }
    minimum=minimums.get(str(kind),(120,50))[0 if won else 1]
    return max(int(minimum),int(round(step*frac)))


def _starting_level(species_id:int)->int:
    r = rarity_for(species_id)
    return {"comun":5, "raro":10, "epico":18, "legendario":25}[r]


def _games_topic(chat_id:int):
    topics = obtener_temas_por_comunidad(chat_id) or {}
    return topics.get("theme_juegosYcasino")


def _is_games_topic(update:Update)->bool:
    chat = update.effective_chat
    msg = update.effective_message
    if not chat or not msg or chat.type == 'private':
        return False
    return getattr(msg, 'message_thread_id', None) == _games_topic(chat.id)


def _stone_evolution_target(species_id:int, item_code:str)->int|None:
    # Combina la tabla de datos con la garantía local completa de Gen 1.
    mapping=dict(STONE_EVOLUTIONS.get(int(species_id),{}))
    mapping.update(GEN1_STONE_EVOLUTIONS.get(int(species_id),{}))
    target=mapping.get(str(item_code))
    return int(target) if target else None


def _family_root(species_id:int)->int:
    # Raíz de familia evolutiva Gen 1. Eevee y evoluciones por piedra/intercambio
    # quedan en la misma familia para que los repetidos siempre tengan utilidad.
    reverse = {}
    for src, (_, dst) in LEVEL_EVOLUTIONS.items():
        reverse[int(dst)] = int(src)
    stone_sources=set(STONE_EVOLUTIONS) | set(GEN1_STONE_EVOLUTIONS)
    for src in stone_sources:
        mapping=dict(STONE_EVOLUTIONS.get(src,{})); mapping.update(GEN1_STONE_EVOLUTIONS.get(src,{}))
        for dst in mapping.values():
            reverse[int(dst)] = int(src)
    for src, dst in TRADE_EVOLUTIONS.items():
        reverse[int(dst)] = int(src)
    cur = int(species_id)
    seen = set()
    while cur in reverse and cur not in seen:
        seen.add(cur)
        cur = reverse[cur]
    return cur


def _release_candies(species_id:int)->int:
    # Caramelos Raros: 1 por Pokémon Común/Raro; 2 si es Épico/Legendario.
    return 2 if rarity_for(int(species_id)) in ('epico', 'legendario') else 1


def _ensure_trainer_row_cursor(c, uid:int):
    c.execute("INSERT INTO pokemon_trainer_tb(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (uid,))


def _wild_species()->int:
    # Compatibilidad para llamadas internas antiguas; las apariciones reales usan
    # _wild_species_cursor para aplicar horario y anti-repetición.
    legendary=list(LEGENDARY_IDS); epic=list(EPIC_IDS); rare=list(RARE_IDS)
    used=set(legendary)|set(epic)|set(rare); common=[i for i in range(1,152) if i not in used]
    rarity=random.choices(['comun','raro','epico','legendario'],[70,24,5.5,0.5],k=1)[0]
    return random.choice({'comun':common,'raro':rare,'epico':epic,'legendario':legendary}[rarity])


def _display_name_cursor(c, uid:int)->str:
    c.execute("SELECT COALESCE(NULLIF(nombre,''),NULLIF(username,''),%s) FROM perfiles_tb WHERE id_user=%s", (f'Jugador {uid}', uid))
    r = c.fetchone()
    return str(r[0]) if r and r[0] else f'Jugador {uid}'


def _dex_name(species:int)->str:
    species=int(species)
    return f"#{species:03d} {NAMES.get(species, 'Pokémon')}"


def _pokemon_label(row)->str:
    # row: id, species, nickname, level, ...
    # El número visible es SIEMPRE el de la Pokédex. El pokemon_id interno solo
    # identifica el ejemplar en PostgreSQL y no debe confundirse con la Pokédex.
    pid, species, nickname, level = int(row[0]), int(row[1]), row[2], int(row[3])
    base = NAMES.get(species, 'Pokémon')
    shown = f'{nickname} ({base})' if nickname else base
    shiny = bool(row[10]) if len(row) > 10 else False
    sex = _sex_symbol(row[17]) if len(row) > 17 else ''
    return f"#{species:03d} · {'✨ ' if shiny else ''}{shown} {sex} · Nv.{level}"


def _types_text(species_id:int)->str:
    return ' / '.join(f'{type_emoji(t)} {t}' for t in TYPES.get(species_id, ('Normal',)))


def _ensure_team_row_cursor(c, uid:int):
    c.execute("INSERT INTO pokemon_team_tb(owner_id) VALUES(%s) ON CONFLICT DO NOTHING", (uid,))


def _principal_pid(uid:int)->int|None:
    conn=_get_connection()
    try:
        c=conn.cursor(); _ensure_team_row_cursor(c,uid)
        c.execute("SELECT principal_pokemon_id FROM pokemon_team_tb WHERE owner_id=%s",(uid,))
        r=c.fetchone(); pid=int(r[0]) if r and r[0] else None
        if pid:
            c.execute("SELECT 1 FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid))
            if not c.fetchone():
                c.execute("UPDATE pokemon_team_tb SET principal_pokemon_id=NULL,updated_at=NOW() WHERE owner_id=%s",(uid,)); conn.commit(); pid=None
        return pid
    finally:_put_connection(conn)


def _is_principal(uid:int,pid:int)->bool:
    return _principal_pid(uid)==int(pid)


def _roll_ivs(force_perfect:bool=False)->dict:
    if force_perfect:
        atk=defn=spd=spc=15
    else:
        atk,defn,spd,spc=(random.randint(0,15) for _ in range(4))
    hp=((atk & 1)*8)+((defn & 1)*4)+((spd & 1)*2)+(spc & 1)
    return {'atk':atk,'def':defn,'spd':spd,'spc':spc,'hp':hp}


def _iv_values(row)->dict:
    # SELECT base mantiene shiny en 10 e IVs en 11..15.
    if row and len(row)>=16:
        vals=row[11:16]
        if all(v is not None for v in vals):
            return {'atk':int(vals[0]),'def':int(vals[1]),'spd':int(vals[2]),'spc':int(vals[3]),'hp':int(vals[4])}
    return {'atk':0,'def':0,'spd':0,'spc':0,'hp':0}


def _iv_percent(ivs:dict)->int:
    return round(sum(int(ivs.get(k,0)) for k in ('hp','atk','def','spc','spd'))/75*100)


def _iv_grade(pct:int)->str:
    if pct>=100:return 'PERFECTO'
    if pct>=95:return 'Casi perfecto'
    if pct>=85:return 'Excelente'
    if pct>=70:return 'Muy bueno'
    if pct>=55:return 'Bueno'
    if pct>=40:return 'Normal'
    return 'Bajo'


def grant_pokemon_with_cursor(c, uid:int, species_id:int, source:str='caja', force_shiny:bool=False, force_perfect:bool=False, level_override:int|None=None, shiny_override:bool|None=None, ivs_override:dict|None=None, sex_override:str|None=None)->dict:
    species_id = max(1, min(151, int(species_id)))
    level = max(1, min(MAX_LEVEL, int(level_override))) if level_override is not None else _starting_level(species_id)
    moves = available_moves(species_id, level)
    # Shiny es puramente cosmético y MUY raro: 1 entre 4096.
    shiny = bool(shiny_override) if shiny_override is not None else bool(force_shiny or random.randrange(4096) == 0)
    ivs = dict(ivs_override) if ivs_override else _roll_ivs(force_perfect)
    if 'hp' not in ivs:ivs['hp']=((int(ivs['atk']) & 1)*8)+((int(ivs['def']) & 1)*4)+((int(ivs['spd']) & 1)*2)+(int(ivs['spc']) & 1)
    sex = str(sex_override or _roll_sex(species_id))
    c.execute("""
        INSERT INTO pokemon_instances_tb(owner_id,species_id,level,xp,moves_json,obtained_from,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp,sex)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING pokemon_id
    """, (uid, species_id, level, _xp_floor(level), json.dumps(moves, ensure_ascii=False), source, shiny,
              ivs['atk'],ivs['def'],ivs['spd'],ivs['spc'],ivs['hp'],sex))
    pid = int(c.fetchone()[0])
    c.execute("""
        INSERT INTO pokemon_pokedex_tb(owner_id,species_id,obtained_count)
        VALUES(%s,%s,1)
        ON CONFLICT(owner_id,species_id) DO UPDATE SET
          obtained_count=pokemon_pokedex_tb.obtained_count+1,last_obtained_at=NOW()
    """, (uid, species_id))
    _ensure_team_row_cursor(c, uid)
    # El primer Pokémon obtenido queda como principal hasta que el dueño elija otro.
    c.execute("UPDATE pokemon_team_tb SET principal_pokemon_id=COALESCE(principal_pokemon_id,%s),updated_at=NOW() WHERE owner_id=%s",(pid,uid))
    # El equipo NO se modifica al obtener/capturar un Pokémon.
    # Cada entrenador decide manualmente qué Pokémon ocupa cada espacio desde /equipo
    # o con el botón «Meter al equipo» de la ficha.
    return {
        'pokemon_id': pid, 'species_id': species_id, 'name': NAMES[species_id],
        'level': level, 'rarity': rarity_for(species_id), 'moves': moves, 'shiny': shiny,
        'iv_percent': _iv_percent(ivs), 'iv_grade': _iv_grade(_iv_percent(ivs)), 'sex': sex,
    }


def _item_info(item_code:str):
    if item_code in HELD_ITEMS:
        x=HELD_ITEMS[item_code]
        return x['name'],x['emoji'],0,'held'
    if item_code in ITEMS:
        return ITEMS[item_code]
    if item_code in SPECIAL_POKEMON_ITEMS:
        x=SPECIAL_POKEMON_ITEMS[item_code]; return x['name'],x['emoji'],0,'special'
    return None


def _item_name(item_code:str)->str:
    info=_item_info(item_code)
    return str(info[0]) if info else str(item_code)


def _held_item_text(item_code:str|None)->str:
    if not item_code or item_code not in HELD_ITEMS:return 'Ninguno'
    x=HELD_ITEMS[item_code]
    return f"{x['emoji']} {x['name']} · {HELD_RARITY_EMOJI.get(x['rarity'],'')} {x['rarity'].title()}\n   {x['description']}"


def grant_item_with_cursor(c, uid:int, item_code:str, qty:int=1):
    if item_code not in ITEMS and item_code not in HELD_ITEMS and item_code not in SPECIAL_POKEMON_ITEMS:
        return False
    c.execute("""
        INSERT INTO pokemon_items_tb(owner_id,item_code,qty) VALUES(%s,%s,%s)
        ON CONFLICT(owner_id,item_code) DO UPDATE SET qty=pokemon_items_tb.qty+EXCLUDED.qty
    """, (uid,item_code,max(1,int(qty))))
    return True


def _held_pool_for_quality(quality:str)->list[str]:
    return [code for code,data in HELD_ITEMS.items() if data['rarity']==quality and code!='light_ball']


def _choose_held_by_source_rarity(source_rarity:str)->str|None:
    weights=HELD_QUALITY_WEIGHTS.get(source_rarity,HELD_QUALITY_WEIGHTS['comun'])
    qualities=[q for q,w in weights.items() if w>0 and _held_pool_for_quality(q)]
    if not qualities:return None
    quality=random.choices(qualities,weights=[weights[q] for q in qualities],k=1)[0]
    pool=_held_pool_for_quality(quality)
    return random.choice(pool) if pool else None


def _species_held_affinities(species_id:int)->list[str]:
    species_id=int(species_id); out=[]
    # Hueso Grueso tiene afinidad directa con Cubone/Marowak.
    if species_id in (104,105):out.append('thick_club')
    # Bola Luminosa NO entra aquí: Pikachu la obtiene mediante su tirada especial rara.
    for tp in TYPES.get(species_id,()):
        code=TYPE_HELD_AFFINITY.get(tp)
        if code and code not in out:out.append(code)
    return out


def _roll_wild_held_item(species_id:int, shiny:bool=False)->str|None:
    species_id=int(species_id)
    # Tirada especial e independiente: aproximadamente 1% en Pikachu salvaje.
    if species_id==25 and random.random()<0.01:
        return 'light_ball'
    rarity=rarity_for(species_id)
    chance=float(WILD_HELD_DROP_CHANCE.get(rarity,0.12)) + (0.05 if shiny else 0.0)
    if random.random()>=min(0.75,chance):return None
    affinities=_species_held_affinities(species_id)
    if affinities and random.random()<0.35:
        # La afinidad ayuda, pero sigue respetando la calidad asociada a la rareza del encuentro.
        allowed=[]; affinity_weights=[]
        source_weights=HELD_QUALITY_WEIGHTS.get(rarity,HELD_QUALITY_WEIGHTS['comun'])
        for code in affinities:
            q=HELD_ITEMS.get(code,{}).get('rarity'); w=int(source_weights.get(q,0)) if q else 0
            if w>0:allowed.append(code); affinity_weights.append(w)
        if allowed:return random.choices(allowed,weights=affinity_weights,k=1)[0]
    return _choose_held_by_source_rarity(rarity)


def _roll_box_held_item(box_code:str)->str|None:
    legendary=(box_code=='legendary')
    if random.random()>=(0.55 if legendary else 0.22):return None
    return _choose_held_by_source_rarity('legendario' if legendary else 'raro')


def _roll_training_held_item()->str|None:
    if random.random()>=TRAINING_HELD_DROP_CHANCE:return None
    # Entrenar puede dar objeto, pero deliberadamente no es una granja de épicos.
    return random.choices(
        [_choose_held_by_source_rarity('comun'),_choose_held_by_source_rarity('raro')],
        weights=[80,20],k=1
    )[0]


def _setting_get_cursor(c,key:str)->str|None:
    c.execute("SELECT setting_value FROM pokemon_settings_tb WHERE setting_key=%s",(str(key),))
    r=c.fetchone(); return str(r[0]) if r and r[0] else None


def _setting_set_cursor(c,key:str,value:str|None):
    if value is None:
        c.execute("DELETE FROM pokemon_settings_tb WHERE setting_key=%s",(str(key),))
    else:
        c.execute("""INSERT INTO pokemon_settings_tb(setting_key,setting_value) VALUES(%s,%s)
                     ON CONFLICT(setting_key) DO UPDATE SET setting_value=EXCLUDED.setting_value,updated_at=NOW()""",(str(key),str(value)))


def _trade_gif_file_id()->str|None:
    conn=_get_connection()
    try:
        c=conn.cursor(); return _setting_get_cursor(c,'trade_gif_file_id')
    finally:_put_connection(conn)


def _choose_tm_drop(rarity:str)->str|None:
    pools={
        'comun':((TM_LOW,TM_MID),(75,25)),
        'raro':((TM_LOW,TM_MID,TM_HIGH),(30,55,15)),
        'epico':((TM_MID,TM_HIGH),(45,55)),
        'legendario':((TM_MID,TM_HIGH),(20,80)),
    }
    groups,weights=pools.get(rarity,pools['comun'])
    available_groups=[]; available_weights=[]
    for group,w in zip(groups,weights):
        valid=[code for code in group if code in TM_ITEMS]
        if valid:
            available_groups.append(valid); available_weights.append(w)
    if not available_groups:
        all_codes=list(TM_ITEMS)
        return random.choice(all_codes) if all_codes else None
    return random.choice(random.choices(available_groups,weights=available_weights,k=1)[0])


def _roll_wild_drop(species_id:int, shiny:bool=False)->tuple[str,int]|None:
    rarity=rarity_for(int(species_id))
    chance=float(WILD_DROP_CHANCE.get(rarity,0.18)) + (0.05 if shiny else 0.0)
    if random.random() >= min(0.80,chance):
        return None
    kinds,weights=WILD_DROP_KIND_WEIGHTS.get(rarity,WILD_DROP_KIND_WEIGHTS['comun'])
    kind=random.choices(kinds,weights=weights,k=1)[0]
    if kind=='rare_candy':
        return ('rare_candy',1)
    if kind=='stone':
        affinity=[x for x in STONE_DROP_AFFINITY.get(int(species_id),()) if x in ITEMS]
        if affinity and random.random()<0.70:
            return (random.choice(affinity),1)
        valid=[x for x in STONE_CODES if x in ITEMS]
        return (random.choice(valid),1) if valid else None
    code=_choose_tm_drop(rarity)
    return (code,1) if code else None


def _drop_label(drop:tuple[str,int]|None)->str:
    if not drop:return ''
    code,qty=drop
    if code in ITEMS:
        name,emoji,_,_=ITEMS[code]
        return f'{emoji} {name}' + (f' ×{qty}' if int(qty)>1 else '')
    return str(code)


def roll_box_pokemon(box_code:str)->int:
    # La Legendaria tiene mejor acceso a épicos/legendarios, pero los legendarios
    # siguen siendo realmente raros incluso dentro de una tirada Pokémon.
    all_ids = list(range(1,152))
    pools = {
        'comun':[i for i in all_ids if rarity_for(i)=='comun'],
        'raro':[i for i in all_ids if rarity_for(i)=='raro'],
        'epico':[i for i in all_ids if rarity_for(i)=='epico'],
        'legendario':[i for i in all_ids if rarity_for(i)=='legendario'],
    }
    if box_code == 'legendary':
        r = random.choices(['comun','raro','epico','legendario'], [38,35,24,3], k=1)[0]
    else:
        r = random.choices(['comun','raro','epico','legendario'], [58,32,9.5,0.5], k=1)[0]
    return random.choice(pools[r])


def roll_box_item(box_code:str)->str:
    # Las MT de Gen 1 pueden salir como objeto de caja; la Legendaria tiene
    # mejor probabilidad. Siguen siendo consumibles de un solo uso.
    tm_codes=list(TM_ITEMS)
    if tm_codes and random.random() < (0.50 if box_code=='legendary' else 0.35):
        return random.choice(tm_codes)
    if box_code == 'legendary':
        return random.choices(
            ['super_potion','hyper_potion','full_restore','revive','fire_stone','water_stone','thunder_stone','leaf_stone','moon_stone','link_cable','rare_candy'],
            [17,15,6,15,8,8,8,8,8,4,3], k=1
        )[0]
    return random.choices(
        ['potion','super_potion','revive','fire_stone','water_stone','thunder_stone','leaf_stone','moon_stone','link_cable','rare_candy'],
        [34,21,14,6,6,6,5,5,1,2], k=1
    )[0]


def _get_owned(uid:int, limit:int=200):
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp,held_item_code,sex
                     FROM pokemon_instances_tb WHERE owner_id=%s ORDER BY pokemon_id LIMIT %s""", (uid,limit))
        return c.fetchall()
    finally:
        _put_connection(conn)


def _get_instance(uid:int, pid:int):
    conn = _get_connection()
    try:
        c = conn.cursor()
        c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp,held_item_code,sex
                     FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s""", (uid,pid))
        return c.fetchone()
    finally:
        _put_connection(conn)


def _collection_markup(uid:int, page:int=0, prefix:str='detail'):
    mons = _get_owned(uid)
    principal=_principal_pid(uid)
    pages = max(1, math.ceil(len(mons)/PAGE_SIZE))
    page = max(0,min(page,pages-1))
    chunk = mons[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
    rows=[]
    for r in chunk:
        species=int(r[1])
        name = (r[2] or NAMES[species])[:20]
        star='⭐ ' if principal==int(r[0]) else ''
        rows.append([InlineKeyboardButton(f"{star}{rarity_emoji(rarity_for(species))} #{species:03d} {name} · Nv.{r[3]}", callback_data=f'pk:{prefix}:{r[0]}:{page}')])
    nav=[]
    if page>0: nav.append(InlineKeyboardButton('⬅️',callback_data=f'pk:list:{page-1}'))
    nav.append(InlineKeyboardButton(f'{page+1}/{pages}',callback_data='pk:noop'))
    if page<pages-1: nav.append(InlineKeyboardButton('➡️',callback_data=f'pk:list:{page+1}'))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton('👥 Mi equipo',callback_data='pk:team'),InlineKeyboardButton('🎒 Objetos',callback_data='pk:items')])
    return InlineKeyboardMarkup(rows)


async def _send_collection_private(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    mons=_get_owned(uid)
    principal=_principal_pid(uid)
    text=(f"🎮 TUS POKÉMON · {len(mons)} ejemplares\n\n"
          "Tu colección y tu equipo son privados. Toca uno para verlo, ponerle apodo, foto/GIF/video, hacerlo principal o meterlo al equipo."
          + ("\n⭐ El Pokémon con estrella es tu principal." if principal else ""))
    try:
        await context.bot.send_message(uid,text,reply_markup=_collection_markup(uid,0))
    except Exception:
        return False
    return True


async def pokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    ok=await _send_collection_private(update,context)
    if update.effective_chat.type!='private':
        await update.effective_message.reply_text('📩 Te mandé tu colección Pokémon por privado.' if ok else '📩 Abre primero el privado de PiBot con /start.')


async def pokedex_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT species_id,obtained_count FROM pokemon_pokedex_tb WHERE owner_id=%s ORDER BY species_id",(uid,)); rows=c.fetchall()
    finally:_put_connection(conn)
    got={int(a):int(b) for a,b in rows}
    # Premios automáticos por hitos; cada uno se entrega una sola vez.
    milestone_notes=[]; connm=_get_connection()
    try:
        cm=connm.cursor(); rewards={25:'🍬 +1 Caramelo Raro',50:'💰 +3,000 PiPesos',75:'🎁 +1 Caja de Objetos',100:'💰 +5,000 PiPesos',125:'🍬 +2 Caramelos Raros'}
        for m in (25,50,75,100,125):
            if len(got)>=m:
                cm.execute("INSERT INTO pokemon_dex_milestones_tb(user_id,milestone) VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING milestone",(uid,m)); fresh=cm.fetchone()
                if fresh:
                    if m==25:grant_item_with_cursor(cm,uid,'rare_candy',1)
                    elif m==50:cm.execute("UPDATE usuarios_tb SET saldo=saldo+3000 WHERE id_user=%s",(uid,))
                    elif m==75:grant_item_with_cursor(cm,uid,'object_box',1)
                    elif m==100:cm.execute("UPDATE usuarios_tb SET saldo=saldo+5000 WHERE id_user=%s",(uid,))
                    elif m==125:grant_item_with_cursor(cm,uid,'rare_candy',2)
                    milestone_notes.append(f'🎁 Hito {m}/151: {rewards[m]}')
        connm.commit()
    except Exception as e:connm.rollback(); print('[PK dex milestone]',type(e).__name__,e)
    finally:_put_connection(connm)
    lines=[f"📖 POKÉDEX DE KANTO · {len(got)}/151",""]
    for start in range(1,152,25):
        end=min(151,start+24); count=sum(1 for i in range(start,end+1) if i in got)
        lines.append(f"#{start:03d}-#{end:03d}: {count}/{end-start+1}")
    if milestone_notes:lines += ['', *milestone_notes]
    lines += ["", "Usa /pokemon para ver tus ejemplares. Puedes tener más de uno de la misma especie."]
    markup=None
    if len(got)>=151:
        conn2=_get_connection(); claimed=False
        try:
            c2=conn2.cursor(); c2.execute("SELECT 1 FROM pokemon_dex_rewards_tb WHERE user_id=%s",(uid,)); claimed=bool(c2.fetchone())
        finally:_put_connection(conn2)
        if claimed:lines += ['', '👑 151/151 · Caja Legendaria Shiny ya reclamada.']
        else:
            lines += ['', '🌟 ¡151/151 COMPLETADA!', '🎁 Recompensa: Caja Legendaria con un Pokémon LEGENDARIO SHINY garantizado.']
            markup=InlineKeyboardMarkup([[InlineKeyboardButton('🎁 Abrir Caja Legendaria Shiny',callback_data='pk:dexclaim')]])
    try: await context.bot.send_message(uid,'\n'.join(lines),reply_markup=markup)
    except Exception:
        return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private': await update.effective_message.reply_text('📩 Te mandé tu Pokédex por privado.')


def _team_rows(uid:int):
    conn=_get_connection()
    try:
        c=conn.cursor(); _ensure_team_row_cursor(c,uid)
        c.execute("SELECT slot1,slot2,slot3,slot4 FROM pokemon_team_tb WHERE owner_id=%s",(uid,)); team=c.fetchone() or (None,None,None,None)
        out=[]
        for pid in team:
            if pid is None: out.append(None); continue
            c.execute("SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp,held_item_code,sex FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); out.append(c.fetchone())
        conn.commit(); return out
    except Exception:
        conn.rollback(); return [None,None,None,None]
    finally:_put_connection(conn)


def _team_text(uid:int)->str:
    rows=_team_rows(uid); lines=['👥 EQUIPO POKÉMON · PRIVADO','']
    for i,r in enumerate(rows,1):
        lines.append(f'{i}. {_pokemon_label(r) if r else "— Vacío —"}')
    lines += ['', 'Máximo 4. Las batallas normales conservan 1v1/2v2/3v3; el modo doble usa los 4.']
    return '\n'.join(lines)


def _team_markup(uid:int):
    rows=[]
    for i in range(1,5): rows.append([InlineKeyboardButton(f'🔄 Cambiar espacio {i}',callback_data=f'pk:teamslot:{i}:0')])
    rows.append([InlineKeyboardButton('🎮 Volver a colección',callback_data='pk:list:0')])
    return InlineKeyboardMarkup(rows)


async def equipo_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    try: await context.bot.send_message(uid,_team_text(uid),reply_markup=_team_markup(uid))
    except Exception: return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private': await update.effective_message.reply_text('📩 Tu equipo es privado; te lo mandé por PV.')


def _public_team_text(uid:int, display_name:str)->str:
    rows=_team_rows(uid)
    principal=_principal_pid(uid)
    lines=[f'🎒 EQUIPO POKÉMON · {display_name}','']
    if not any(rows):
        lines.append('Todavía no tienes Pokémon en tu equipo.')
        return '\n'.join(lines)
    for i,r in enumerate(rows,1):
        if not r:
            lines.append(f'{i}. — Vacío —')
            continue
        pid,species,nickname,level=int(r[0]),int(r[1]),r[2],int(r[3])
        base=NAMES.get(species,'Pokémon')
        shown=f'{nickname} ({base})' if nickname else base
        shiny='✨ ' if bool(r[10]) else ''
        star='⭐ ' if principal==pid else ''
        sex=_sex_symbol(r[17]) if len(r)>17 else ''
        lines.append(f'{i}. {star}{shiny}#{species:03d} {shown} {sex} · Nv.{level}')
        lines.append(f'   {_types_text(species)}')
        held=r[16] if len(r)>16 else None
        if held in HELD_ITEMS:
            item=HELD_ITEMS[held]
            lines.append(f"   🎒 {item['emoji']} {item['name']}")
    return '\n'.join(lines)


async def mostrarequipo_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private':
        return await update.effective_message.reply_text('📢 Usa /mostrarequipo en el grupo donde quieras enseñar tu equipo.')
    user=update.effective_user
    display_name=(user.full_name or user.first_name or user.username or 'Entrenador').strip()
    await update.effective_message.reply_text(_public_team_text(user.id,display_name))


def _items_text(uid:int)->str:
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT item_code,qty FROM pokemon_items_tb WHERE owner_id=%s AND qty>0 ORDER BY item_code",(uid,)); rows=c.fetchall()
    finally:_put_connection(conn)
    lines=['🎒 OBJETOS POKÉMON · PRIVADO','']
    if not rows: lines.append('Todavía no tienes objetos Pokémon.')
    for code,qty in rows:
        if code in HELD_ITEMS:
            x=HELD_ITEMS[code]; lines.append(f"{x['emoji']} {x['name']} ×{qty} · {HELD_RARITY_EMOJI.get(x['rarity'],'')} {x['rarity'].title()}")
        elif code in ITEMS:
            name,em,_,kind=ITEMS[code]; lines.append(f'{em} {name} ×{qty}')
        elif code in SPECIAL_POKEMON_ITEMS:
            x=SPECIAL_POKEMON_ITEMS[code]; lines.append(f"{x['emoji']} {x['name']} ×{qty}")
        else:
            lines.append(f'🎒 {code} ×{qty}')
    lines += ['', 'Los objetos equipables se ponen desde la ficha de cada Pokémon. Las piedras, Cable Link, Caramelo Raro y MT se usan fuera de combate. Las MT enseñan un movimiento compatible y se consumen al usarlas.']
    return '\n'.join(lines)


def _items_markup(uid:int):
    conn=_get_connection(); rows=[]
    try:
        c=conn.cursor(); c.execute("SELECT item_code,qty FROM pokemon_items_tb WHERE owner_id=%s AND qty>0",(uid,)); inv=c.fetchall()
    finally:_put_connection(conn)
    for code,qty in inv:
        if code in ITEMS and ITEMS[code][3] in ('evolution','trade_evolution','level','tm'):
            name,em,_,_=ITEMS[code]; rows.append([InlineKeyboardButton(f'{em} Usar {name} ×{qty}',callback_data=f'pk:useitem:{code}:0')])
    if any(str(code)=='object_box' and int(qty)>0 for code,qty in inv):
        rows.append([InlineKeyboardButton('🎁 Abrir Caja de Objetos',callback_data='pk:openobjbox')])
    rows.append([InlineKeyboardButton('🎮 Colección',callback_data='pk:list:0')])
    return InlineKeyboardMarkup(rows)


async def pokeobjetos_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    try: await context.bot.send_message(uid,_items_text(uid),reply_markup=_items_markup(uid))
    except Exception: return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private': await update.effective_message.reply_text('📩 Te mandé tus objetos Pokémon por privado.')


async def nombrarpokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type!='private':
        return await update.effective_message.reply_text('🏷️ Los apodos se configuran por privado. Usa /pokemon con PiBot.')
    if len(context.args)>=2:
        try: pid=int(context.args[0])
        except Exception: return await update.effective_message.reply_text('Usa /nombrarpokemon ID apodo. Ejemplo: /nombrarpokemon 12 Sombra')
        name=' '.join(context.args[1:]).strip()[:24]
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("UPDATE pokemon_instances_tb SET nickname=%s,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s RETURNING species_id",(name or None,update.effective_user.id,pid)); r=c.fetchone(); conn.commit()
        except Exception: conn.rollback(); r=None
        finally:_put_connection(conn)
        return await update.effective_message.reply_text(f'🏷️ Apodo guardado: {name}' if r else 'No encontré ese Pokémon en tu colección.')
    await update.effective_message.reply_text('Toca el Pokémon que quieres nombrar:',reply_markup=_collection_markup(update.effective_user.id,0,'nickselect'))


async def fotopokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type!='private':
        return await update.effective_message.reply_text('🎞️ La foto/GIF/video de tus Pokémon se configura por privado con /fotopokemon.')
    await update.effective_message.reply_text('Elige el Pokémon al que quieres poner foto, GIF o video:',reply_markup=_collection_markup(update.effective_user.id,0,'mediaselect'))


def _resolve_target(update,context):
    m=update.effective_message
    if m.reply_to_message and m.reply_to_message.from_user and not m.reply_to_message.from_user.is_bot:
        return m.reply_to_message.from_user.id
    if context.args and context.args[0].startswith('@'):
        uname=context.args[0][1:].lower(); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT id_user FROM perfiles_tb WHERE lower(username)=%s LIMIT 1",(uname,)); r=c.fetchone(); return int(r[0]) if r else None
        finally:_put_connection(conn)
    return None


async def presumirpokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    target={'chat_id':uid,'thread_id':None} if update.effective_chat.type=='private' else {'chat_id':update.effective_chat.id,'thread_id':getattr(update.effective_message,'message_thread_id',None)}
    principal=_principal_pid(uid)
    if principal:
        ok=await _send_brag(context,uid,principal,target)
        if not ok:
            return await update.effective_message.reply_text('No pude presumir tu Pokémon principal.')
        return
    context.user_data['pk_brag_target']=target
    try:
        await context.bot.send_message(uid,'😎 Aún no tienes Pokémon principal. Elige uno para presumir; desde su ficha puedes marcarlo como ⭐ Principal.',reply_markup=_collection_markup(uid,0,'brag'))
    except Exception:
        return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private': await update.effective_message.reply_text('📩 No tienes principal todavía; te mandé tu colección por privado.')


async def _send_brag(context, uid:int, pid:int, target:dict):
    row=_get_instance(uid,pid)
    if not row:return False
    species=int(row[1]); nickname=row[2]; level=int(row[3]); media_type=row[6]; file_id=row[7]; wins=int(row[8]); losses=int(row[9]); shiny=bool(row[10]) if len(row)>10 else False
    conn=_get_connection()
    try:
        c=conn.cursor(); owner=_display_name_cursor(c,uid)
    finally:_put_connection(conn)
    title=nickname or NAMES[species]
    ivs=_iv_values(row); ivpct=_iv_percent(ivs); principal=_is_principal(uid,pid)
    principal_line='⭐ PRINCIPAL\n' if principal else ''
    caption=(f"✨ POKÉMON DE {owner}\n"
             f"{principal_line}"
             f"{rarity_emoji(rarity_for(species))} #{species:03d} {'✨ SHINY · ' if shiny else ''}{title} {_sex_symbol(row[17]) if len(row)>17 else ''}\n"
             f"{NAMES[species]} · Nv.{level}\n"
             f"{_types_text(species)}\n"
             f"🧬 IV: {ivpct}% · {_iv_grade(ivpct)}\n"
             f"⚔️ {wins}V / {losses}D\n\n"
             "Su equipo y sus movimientos siguen siendo privados.")
    kwargs={'chat_id':target['chat_id'],'message_thread_id':target.get('thread_id')}
    try:
        if media_type=='photo' and file_id: await context.bot.send_photo(photo=file_id,caption=caption,**kwargs)
        elif media_type=='animation' and file_id: await context.bot.send_animation(animation=file_id,caption=caption,**kwargs)
        elif media_type=='video' and file_id: await context.bot.send_video(video=file_id,caption=caption,**kwargs)
        else: await context.bot.send_message(text=caption,**kwargs)
        return True
    except Exception:return False


# ------------------------------ BATALLAS ------------------------------
def _stat_value(species:int,level:int,key:str,iv:int=0)->int:
    b=battle_base_stats(species)[key]
    # Fórmula estilo Gen 1 sin Stat Exp: el DV/IV 0-15 sí modifica la estadística real.
    if key=='hp': return int((2*(b+int(iv))*level)/100)+level+10
    return int((2*(b+int(iv))*level)/100)+5


def _battle_mon(row)->dict:
    pid,species,nick,level,xp,moves_json,_,_,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp=row[:16]
    held_item=row[16] if len(row)>16 else None
    species=int(species); level=int(level)
    try:moves=json.loads(moves_json or '[]')
    except Exception:moves=[]
    if not moves:moves=available_moves(species,level)
    ivs={'atk':int(iv_atk or 0),'def':int(iv_def or 0),'spd':int(iv_spd or 0),'spc':int(iv_spc or 0),'hp':int(iv_hp or 0)}
    hp=_stat_value(species,level,'hp',ivs['hp'])
    return {'pid':int(pid),'species':species,'nickname':nick,'level':level,'hp':hp,'max_hp':hp,'moves':moves,'pp':{m:MOVES[m][4] for m in moves if m in MOVES},'status':None,'sleep':0,'stages':{'atk':0,'def':0,'spd':0},'shiny':bool(shiny),'ivs':ivs,'held_item':held_item,'choice_lock':None}


def _team_for_battle_cursor(c,uid:int,mode:int):
    _ensure_team_row_cursor(c,uid)
    c.execute("SELECT slot1,slot2,slot3,slot4 FROM pokemon_team_tb WHERE owner_id=%s",(uid,)); slots=list(c.fetchone() or (None,None,None,None))[:mode]
    if len(slots)<mode or any(x is None for x in slots):return None
    mons=[]
    for pid in slots:
        c.execute("SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp,held_item_code,sex FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); r=c.fetchone()
        if not r:return None
        mons.append(_battle_mon(r))
    return mons


def _pvp_team_slot_ids_cursor(c,uid:int)->list[int]:
    """Los PvP normales eligen exclusivamente entre los 4 espacios de /equipo."""
    _ensure_team_row_cursor(c,uid)
    c.execute("SELECT slot1,slot2,slot3,slot4 FROM pokemon_team_tb WHERE owner_id=%s",(uid,))
    row=c.fetchone() or (None,None,None,None)
    return [int(x) for x in row if x is not None]


def _pvp_selection_markup_cursor(c,uid:int,bid:int,mode:int,selected:list[int],ready:bool=False):
    rows=[]; slots=_pvp_team_slot_ids_cursor(c,uid)
    order={int(pid):i+1 for i,pid in enumerate(selected)}
    for pid in slots:
        c.execute("SELECT species_id,nickname,level,shiny FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); r=c.fetchone()
        if not r:continue
        shown=r[1] or NAMES[int(r[0])]; shiny='✨ ' if r[3] else ''
        prefix=f'{order[pid]}️⃣' if pid in order and order[pid] <= 3 else ('✅' if pid in order else '⬜')
        rows.append([InlineKeyboardButton(f'{prefix} {shiny}{shown} · Nv.{int(r[2])}',callback_data=f'pk:pvppick:{bid}:{pid}')])
    if len(selected)==mode and not ready:
        rows.append([InlineKeyboardButton(f'✅ Confirmar equipo {mode}v{mode}',callback_data=f'pk:pvpready:{bid}')])
    return InlineKeyboardMarkup(rows) if rows else None


def _pvp_mons_from_ids_cursor(c,uid:int,pids:list[int])->list[dict]|None:
    mons=[]
    for pid in pids:
        c.execute("SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp,held_item_code,sex FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,int(pid))); r=c.fetchone()
        if not r:return None
        mons.append(_battle_mon(r))
    return mons


def _pvp_setup_public_text(state:dict)->str:
    ids=list(state.get('players',{})); ready=state.get('pvp_ready',{})
    mode=int(state.get('mode',1)); lines=[f'⚔️ PREPARANDO BATALLA POKÉMON {mode}v{mode}','',
        'Cada entrenador está eligiendo su equipo por privado.','Los Pokémon elegidos siguen ocultos hasta que salgan al combate.','']
    for key in ids:
        pl=state['players'][key]; lines.append(f"{'✅' if ready.get(key) else '⌛'} {pl['name']}")
    return '\n'.join(lines)


def _battle_title_mon(mon:dict)->str:
    species=int(mon['species']); base=NAMES[species]; name=mon.get('nickname') or base
    shown=f"{name} ({base})" if mon.get('nickname') else base
    shiny=f"✨ {shown}" if mon.get('shiny') else shown
    return f"#{species:03d} {shiny}"


_BATTLE_TYPE_LABELS_ES={
    'Normal':'Normal','Fire':'Fuego','Water':'Agua','Electric':'Eléctrico','Grass':'Planta','Ice':'Hielo',
    'Fighting':'Lucha','Poison':'Veneno','Ground':'Tierra','Flying':'Volador','Psychic':'Psíquico',
    'Bug':'Bicho','Rock':'Roca','Ghost':'Fantasma','Dragon':'Dragón',
}


def _battle_type_label(tp:str)->str:
    return _BATTLE_TYPE_LABELS_ES.get(str(tp),str(tp))


def _battle_text(state:dict, note:str|None=None)->str:
    ids=list(state['players'].keys()); a=state['players'][ids[0]]; b=state['players'][ids[1]]
    am=a['mons'][a['active']]; bm=b['mons'][b['active']]
    def bar(m):
        pct=max(0,min(1,m['hp']/max(1,m['max_hp']))); full=round(pct*10)
        return '█'*full+'░'*(10-full)
    lines=[f"⚔️ BATALLA POKÉMON {state['mode']}v{state['mode']}","",
           f"{a['name']} · {_battle_title_mon(am)} Nv.{am['level']}",f"❤️ {am['hp']}/{am['max_hp']}  {bar(am)}",
           "VS",
           f"{b['name']} · {_battle_title_mon(bm)} Nv.{bm['level']}",f"❤️ {bm['hp']}/{bm['max_hp']}  {bar(bm)}",
           "",f"🔁 Ronda {state.get('round',1)}"]
    if note: lines += ['',note]
    if state.get('status')=='active':
        chosen=state.get('choices',{})
        lines += ['',f"Elecciones: {('✅' if ids[0] in chosen else '⌛')} {a['name']} · {('✅' if ids[1] in chosen else '⌛')} {b['name']}"]
    return '\n'.join(lines)


def _battle_markup(bid:int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('⚔️ Elegir acción',callback_data=f'pk:action:{bid}')],
        [InlineKeyboardButton('🏳 Rendirse',callback_data=f'pk:surrender:{bid}')],
    ])


def _move_menu(bid:int,mon:dict):
    rows=[]
    locked=mon.get('choice_lock') if mon.get('held_item') in ('choice_band','choice_specs','choice_scarf') else None
    for i,code in enumerate(mon['moves']):
        if code not in MOVES or (locked and code!=locked):continue
        name,tp,power,acc,pp,kind=MOVES[code]; left=int(mon.get('pp',{}).get(code,pp))
        rows.append([InlineKeyboardButton(f"{type_emoji(tp)} {name} · {_battle_type_label(tp)} · PP {left}/{pp}",callback_data=f'pk:move:{bid}:{i}')])
    rows.append([InlineKeyboardButton('🔄 Cambiar Pokémon',callback_data=f'pk:bswitchmenu:{bid}'),InlineKeyboardButton('🎒 Objeto',callback_data=f'pk:bitemmenu:{bid}')])
    return InlineKeyboardMarkup(rows)


# Mensajes espejo de batalla por privado. Solo guardamos IDs de mensajes en memoria;
# el estado real de la batalla sigue viviendo exclusivamente en state_json/DB.
_BATTLE_PRIVATE_VIEW_MESSAGES={}
# Menús auxiliares temporales de batalla (movimiento/objetivo/cambio/objeto).
# Se eliminan al registrar la acción para que el privado no se llene de mensajes viejos.
_BATTLE_PRIVATE_TRANSIENT_MESSAGES={}


def _remember_battle_transient(bid:int,uid:int,message_id:int):
    key=(int(bid),int(uid))
    _BATTLE_PRIVATE_TRANSIENT_MESSAGES.setdefault(key,set()).add(int(message_id))


async def _delete_battle_transients(context,bid:int,uid:int):
    key=(int(bid),int(uid)); mids=list(_BATTLE_PRIVATE_TRANSIENT_MESSAGES.pop(key,set()))
    for mid in mids:
        try:await context.bot.delete_message(chat_id=int(uid),message_id=int(mid))
        except Exception:pass


async def _send_battle_transient(context,bid:int,uid:int,text:str,markup=None):
    # Al abrir un submenú nuevo, borra cualquier selector anterior de esa batalla.
    await _delete_battle_transients(context,bid,uid)
    try:
        msg=await context.bot.send_message(chat_id=int(uid),text=text,reply_markup=markup)
        _remember_battle_transient(bid,uid,int(msg.message_id))
        return msg
    except Exception:
        return None


async def _delete_all_battle_transients(context,bid:int,state:dict):
    for human in _human_battle_ids(state):
        await _delete_battle_transients(context,bid,human)


def _human_battle_ids(state:dict)->list[int]:
    out=[]
    for raw in state.get('players',{}):
        try:uid=int(raw)
        except Exception:continue
        if uid>0:out.append(uid)
    return out


def _single_private_text(state:dict,uid:int,note:str|None=None,final:bool=False)->str:
    text=_battle_text(state,note)
    if final:return text+"\n\n🏁 Batalla terminada."
    key=str(uid)
    if key in state.get('choices',{}):return text+"\n\n✅ Tu acción ya está registrada. Esperando que se resuelva la ronda…"
    return text+"\n\n🔒 Tus decisiones solo se eligen aquí.\n👇 Elige tu acción:"

def _single_private_markup(bid:int,state:dict,uid:int,final:bool=False):
    key=str(uid)
    if final or state.get('status')!='active' or key not in state.get('players',{}):return None
    if key in state.get('choices',{}):return None
    pl=state['players'][key]; mon=pl['mons'][pl['active']]
    if mon.get('hp',0)<=0:return None
    base=_move_menu(bid,mon)
    # En Safari la bola puede lanzarse en cualquier momento de la pelea.
    if state.get('battle_kind')=='safari' and int(uid)==int(state.get('safari_user_id',-1)):
        rows=[list(r) for r in base.inline_keyboard]
        rows.insert(0,[InlineKeyboardButton('🔴 Lanzar Safari Ball',callback_data=f'pk:safbattleball:{bid}')])
        return InlineKeyboardMarkup(rows)
    return base


async def _set_private_battle_view(context,bid:int,uid:int,text:str,markup=None,final:bool=False):
    cache_key=(int(bid),int(uid)); mid=_BATTLE_PRIVATE_VIEW_MESSAGES.get(cache_key)
    if mid:
        try:
            await context.bot.edit_message_text(chat_id=int(uid),message_id=int(mid),text=text,reply_markup=markup)
            if final:_BATTLE_PRIVATE_VIEW_MESSAGES.pop(cache_key,None)
            return mid
        except Exception as e:
            if 'not modified' in str(e).lower():
                if final:_BATTLE_PRIVATE_VIEW_MESSAGES.pop(cache_key,None)
                return mid
    try:
        msg=await context.bot.send_message(chat_id=int(uid),text=text,reply_markup=markup)
        if final:_BATTLE_PRIVATE_VIEW_MESSAGES.pop(cache_key,None)
        else:_BATTLE_PRIVATE_VIEW_MESSAGES[cache_key]=int(msg.message_id)
        return int(msg.message_id)
    except Exception:
        return None


async def _store_battle_public_message_id(bid:int,message_id:int):
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute('UPDATE pokemon_battles_tb SET message_id=%s,updated_at=NOW() WHERE battle_id=%s',(int(message_id),int(bid))); conn.commit()
    except Exception:conn.rollback()
    finally:_put_connection(conn)


async def _sync_single_battle_views(context,bid:int,state:dict,chat_id:int,thread_id,message_id:int|None,note:str|None=None,final:bool=False):
    humans=_human_battle_ids(state)
    private_in_same_chat=next((u for u in humans if int(u)==int(chat_id)),None)
    if private_in_same_chat is not None:
        public_text=_single_private_text(state,private_in_same_chat,note,final)
        public_markup=_single_private_markup(bid,state,private_in_same_chat,final)
    else:
        public_text=_battle_text(state,note)
        public_markup=None if final else _battle_markup(bid)
    public_mid=message_id
    edited=False
    if message_id:
        try:
            await context.bot.edit_message_text(chat_id=int(chat_id),message_id=int(message_id),text=public_text,reply_markup=public_markup)
            edited=True
        except Exception as e:
            if 'not modified' in str(e).lower():edited=True
    if not edited:
        try:
            msg=await context.bot.send_message(chat_id=int(chat_id),text=public_text,message_thread_id=thread_id,reply_markup=public_markup)
            public_mid=int(msg.message_id); await _store_battle_public_message_id(bid,public_mid)
        except Exception:pass
    for human in humans:
        if int(human)==int(chat_id):continue
        await _set_private_battle_view(context,bid,human,_single_private_text(state,human,note,final),_single_private_markup(bid,state,human,final),final)
    return public_mid


async def _update_single_public_final(context,bid:int,state:dict,chat_id:int,thread_id,message_id:int|None,note:str|None,result_text:str):
    """Garantiza que el cierre y sus recompensas queden visibles en el mensaje público."""
    text=_battle_text(state,note) + "\n\n🏁 Batalla terminada.\n\n" + str(result_text)
    edited=False
    if message_id:
        try:
            await context.bot.edit_message_text(chat_id=int(chat_id),message_id=int(message_id),text=text,reply_markup=None)
            edited=True
        except Exception as e:
            if 'not modified' in str(e).lower():edited=True
    if not edited:
        try:
            msg=await context.bot.send_message(chat_id=int(chat_id),text=text,message_thread_id=thread_id)
            await _store_battle_public_message_id(bid,int(msg.message_id))
            return int(msg.message_id)
        except Exception as e:
            print('[PK public final]',type(e).__name__,e)
            return None
    return int(message_id) if message_id else None


async def _send_private_battle_result(context,state:dict,text:str,skip_chat_id:int|None=None):
    for uid in _human_battle_ids(state):
        if skip_chat_id is not None and int(uid)==int(skip_chat_id):continue
        try:await context.bot.send_message(int(uid),text)
        except Exception:pass


def _get_battle(bid:int, lock=False):
    conn=_get_connection()
    try:
        c=conn.cursor(); sql="SELECT battle_id,chat_id,thread_id,challenger_id,opponent_id,mode,status,state_json,message_id,winner_id FROM pokemon_battles_tb WHERE battle_id=%s"+(' FOR UPDATE' if lock else '')
        c.execute(sql,(bid,)); return c.fetchone()
    finally:_put_connection(conn)


def _stage_mult(stage:int)->float:
    stage=max(-2,min(2,int(stage)))
    return {-2:0.6,-1:0.8,0:1.0,1:1.25,2:1.5}[stage]


def _held_stat_multiplier(mon:dict,key:str)->float:
    held=mon.get('held_item')
    species=int(mon.get('species',0))
    if held=='light_ball' and species==25 and key in ('atk','spc'):return 2.0
    if held=='thick_club' and species in (104,105) and key=='atk':return 2.0
    if held=='choice_band' and key=='atk':return 1.5
    if held=='choice_specs' and key=='spc':return 1.5
    return 1.0


def _effective_speed(mon):
    val=_stat_value(mon['species'],mon['level'],'spd',mon.get('ivs',{}).get('spd',0))*_stage_mult(mon['stages'].get('spd',0))
    if mon.get('held_item')=='choice_scarf':val*=1.5
    if mon.get('status')=='paralyze':val*=0.5
    return val


def _held_damage_multiplier(att:dict,tp:str,eff:float,physical:bool)->float:
    held=att.get('held_item'); mult=1.0
    if HELD_TYPE_BOOSTS.get(held)==tp:mult*=1.2
    if held=='muscle_band' and physical:mult*=1.1
    if held=='wise_glasses' and not physical:mult*=1.1
    if held=='life_orb':mult*=1.3
    if held=='expert_belt' and eff>1:mult*=1.2
    return mult


def _apply_held_end_round(state:dict,logs:list[str]):
    for player in state.get('players',{}).values():
        if not player.get('mons'):continue
        mon=player['mons'][player['active']]
        if mon.get('hp',0)>0 and mon.get('held_item')=='leftovers' and mon['hp']<mon['max_hp']:
            heal=max(1,mon['max_hp']//16); old=mon['hp']; mon['hp']=min(mon['max_hp'],mon['hp']+heal)
            logs.append(f"🍎 Restos: {_battle_title_mon(mon)} recuperó {mon['hp']-old} HP.")


def _mark_training_participant(state:dict,uid,mon:dict):
    if state.get('battle_kind')!='training':return
    if int(uid)!=int(state.get('training_user_id',-1)):return
    pid=int(mon.get('pid',0))
    if pid<=0:return
    ids=state.setdefault('training_participants',[])
    if pid not in ids:ids.append(pid)


def _do_move(att:dict,defn:dict,move_code:str,_called_move:bool=False)->list[str]:
    if move_code not in MOVES:return ['El movimiento falló.']
    name,tp,power,acc,maxpp,kind=MOVES[move_code]
    logs=[]
    held=att.get('held_item')
    if not _called_move and held in ('choice_band','choice_specs','choice_scarf'):
        locked=att.get('choice_lock')
        if locked and locked!=move_code:
            return [f"🔒 {_item_name(held)} mantiene a {_battle_title_mon(att)} usando {MOVES.get(locked,(locked,))[0]} hasta que cambie."]
        if not locked:att['choice_lock']=move_code
    if att.get('sleep',0)>0:
        att['sleep']-=1
        if att['sleep']>0:return [f"💤 {_battle_title_mon(att)} está dormido."]
        logs.append(f"✨ {_battle_title_mon(att)} despertó.")
    if att.get('status')=='paralyze' and random.random()<0.25:
        return logs+[f"⚡ {_battle_title_mon(att)} está paralizado y no puede moverse."]
    effective_acc=float(acc)*(0.90 if defn.get('held_item')=='bright_powder' else 1.0)
    if effective_acc<100 and random.uniform(0,100)>effective_acc:
        return logs+[f"💨 {name} falló."]
    if kind=='nothing': return logs+[f"… {_battle_title_mon(att)} usó {name}. No pasó nada."]
    if kind=='heal':
        heal=max(1,att['max_hp']//2); before=att['hp']; att['hp']=min(att['max_hp'],att['hp']+heal)
        return logs+[f"💚 {name}: recuperó {att['hp']-before} HP."]
    if kind=='buff_def':
        att['stages']['def']=min(2,att['stages']['def']+1); return logs+[f"🛡️ {name}: subió la Defensa."]
    if kind=='buff_speed':
        att['stages']['spd']=min(2,att['stages']['spd']+1); return logs+[f"💨 {name}: subió la Velocidad."]
    if kind=='debuff_atk':
        defn['stages']['atk']=max(-2,defn['stages']['atk']-1); return logs+[f"📉 {name}: bajó el Ataque rival."]
    if kind=='sleep':
        if defn.get('sleep',0)>0:return logs+[f"💤 {name}: el rival ya dormía."]
        defn['sleep']=random.randint(2,4); return logs+[f"💤 {name}: {_battle_title_mon(defn)} se durmió."]
    if kind=='poison':
        if defn.get('status') is None:defn['status']='poison'; return logs+[f"☠️ {name}: rival envenenado."]
        return logs+[f"☠️ {name}: no cambió el estado del rival."]
    if kind=='paralyze':
        if defn.get('status') is None:defn['status']='paralyze'; return logs+[f"⚡ {name}: rival paralizado."]
        return logs+[f"⚡ {name}: no cambió el estado del rival."]
    if kind=='transform':
        att['species']=defn['species']; att['moves']=list(defn['moves']); att['pp']={m:MOVES[m][4] for m in att['moves'] if m in MOVES}
        return logs+[f"✨ Transformación: copió a {_battle_title_mon(defn)}."]
    if kind=='metronome':
        pool=[m for m,v in MOVES.items() if v[5] in ('damage','drain','fixed','fixed40') and m!='metronome']
        picked=random.choice(pool); logs.append(f"🎲 Metrónomo eligió {MOVES[picked][0]}.")
        return logs+_do_move(att,defn,picked,True)

    eff=effectiveness(tp,TYPES.get(defn['species'],('Normal',)))
    if kind=='fixed': dmg=max(1,int(att['level']))
    elif kind=='fixed40': dmg=40
    else:
        physical=tp in PHYSICAL_TYPES
        atk_key='atk' if physical else 'spc'; def_key='def' if physical else 'spc'
        A=_stat_value(att['species'],att['level'],atk_key,att.get('ivs',{}).get(atk_key,0))*_stage_mult(att['stages'].get('atk',0) if atk_key=='atk' else 0)*_held_stat_multiplier(att,atk_key)
        D=_stat_value(defn['species'],defn['level'],def_key,defn.get('ivs',{}).get(def_key,0))*_stage_mult(defn['stages'].get('def',0) if def_key=='def' else 0)
        base=((((2*att['level']/5)+2)*max(1,power)*max(1,A)/max(1,D))/50)+2
        stab=1.5 if tp in TYPES.get(att['species'],()) else 1.0
        crit_chance=0.25 if move_code=='slash' else 0.0625
        if held=='razor_claw':crit_chance=min(1.0,crit_chance*2)
        crit=random.random()<crit_chance
        dmg=max(1,int(base*stab*eff*_held_damage_multiplier(att,tp,eff,physical)*random.uniform(0.85,1.0)*(1.5 if crit else 1.0))) if eff>0 else 0
        if crit:logs.append('💥 ¡Golpe crítico!')
        if eff==0:logs.append('🚫 No afecta al rival.')
        elif eff>=2:logs.append('🔥 ¡Es súper eficaz!')
        elif eff<1:logs.append('🛡️ No es muy eficaz.')
    before=defn['hp']
    if defn.get('held_item')=='focus_band' and before>1 and dmg>=before and random.random()<0.10:
        dmg=max(0,before-1); logs.append(f"🎗️ Banda Focus dejó a {_battle_title_mon(defn)} con 1 PS.")
    defn['hp']=max(0,defn['hp']-dmg); dealt=before-defn['hp']
    logs.insert(0,f"⚔️ {_battle_title_mon(att)} usó {name}: -{dealt} HP.")
    if kind=='drain' and dealt>0:
        heal=max(1,dealt//2); old=att['hp']; att['hp']=min(att['max_hp'],att['hp']+heal); logs.append(f"💚 Recuperó {att['hp']-old} HP.")
    if held=='shell_bell' and dealt>0 and att['hp']>0:
        heal=max(1,dealt//8); old=att['hp']; att['hp']=min(att['max_hp'],att['hp']+heal)
        if att['hp']>old:logs.append(f"🔔 Cascabel Concha: recuperó {att['hp']-old} HP.")
    if held=='life_orb' and dealt>0 and att['hp']>0:
        recoil=max(1,att['max_hp']//10); att['hp']=max(0,att['hp']-recoil); logs.append(f"🔮 Vidaesfera: perdió {recoil} HP.")
    return logs


def _next_alive(player:dict):
    for i,m in enumerate(player['mons']):
        if m['hp']>0:return i
    return None


def _choice_speed(player,choice):
    if choice['type'] in ('switch','item'):return 9999
    mon=player['mons'][player['active']]
    code=choice.get('move')
    priority=1 if code=='quick_attack' else 0
    quick=5000 if mon.get('held_item')=='quick_claw' and random.random()<0.20 else 0
    return _effective_speed(mon)+priority*1000+quick


def _apply_item_action(player:dict,choice:dict,c,uid:int)->str:
    code=choice['item']; idx=player['active']; mon=player['mons'][idx]
    if code not in ITEMS:return '🎒 Objeto inválido.'
    name,em,val,kind=ITEMS[code]
    c.execute("SELECT qty FROM pokemon_items_tb WHERE owner_id=%s AND item_code=%s FOR UPDATE",(uid,code)); r=c.fetchone()
    if not r or int(r[0])<=0:return f'🎒 No quedaba {name}.'
    if kind=='heal':
        if mon['hp']<=0:return f'🎒 {name} no puede usarse sobre un Pokémon debilitado.'
        before=mon['hp']; mon['hp']=min(mon['max_hp'],mon['hp']+val); used=mon['hp']>before
        if not used:return f'🎒 {name}: ya tenía todos sus HP.'
    elif kind=='revive':
        target=next((m for m in player['mons'] if m['hp']<=0),None)
        if not target:return '🎒 Revivir: no hay Pokémon debilitados.'
        target['hp']=max(1,target['max_hp']//2)
    else:return f'🎒 {name} no se usa dentro de batalla.'
    c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code=%s",(uid,code))
    return f'{em} Usó {name}.'


def _grant_pokemon_xp_cursor(c,pid:int,amount:int)->list[str]:
    c.execute("SELECT owner_id,species_id,nickname,level,xp,moves_json FROM pokemon_instances_tb WHERE pokemon_id=%s FOR UPDATE",(pid,)); r=c.fetchone()
    if not r:return []
    owner,species,nick,level,xp=int(r[0]),int(r[1]),r[2],int(r[3]),int(r[4]); oldlevel=level; xp=max(xp,_xp_floor(level))+int(amount); notes=[]
    try:current_moves=[str(x) for x in json.loads(r[5] or '[]') if str(x) in MOVES]
    except Exception:current_moves=[]
    if not current_moves:current_moves=list(available_moves(species,level))
    while level<MAX_LEVEL and xp>=_xp_floor(level+1):level+=1
    final_species=species
    if level>oldlevel:
        final_species=_level_path_and_moves_cursor(c,owner,pid,species,nick,oldlevel,level,current_moves,notes)
    c.execute("UPDATE pokemon_instances_tb SET species_id=%s,level=%s,xp=%s,moves_json=%s,friendship=LEAST(255,friendship+2),updated_at=NOW() WHERE pokemon_id=%s",
              (final_species,level,xp,json.dumps(current_moves[:4],ensure_ascii=False),pid))
    if level>oldlevel:notes.insert(0,f'⭐ {nick or NAMES[final_species]} subió a Nv.{level}.')
    return notes


def _update_rank_cursor(c,winner:int,loser:int):
    _pokemon_season_rollover_cursor(c)
    for uid in (winner,loser):c.execute("INSERT INTO pokemon_rank_tb(user_id) VALUES(%s) ON CONFLICT DO NOTHING",(uid,))
    c.execute("SELECT user_id,rating,wins,losses,current_streak,best_streak,season_best_streak,peak_rating FROM pokemon_rank_tb WHERE user_id IN (%s,%s) FOR UPDATE",(winner,loser)); rows={int(r[0]):r for r in c.fetchall()}
    rw=int(rows[winner][1]); rl=int(rows[loser][1]); ew=1/(1+10**((rl-rw)/400)); delta=max(8,round(24*(1-ew)))
    ws=int(rows[winner][4])+1; best=max(int(rows[winner][5]),ws); season_best=max(int(rows[winner][6]),ws); new_rating=rw+delta; peak=max(int(rows[winner][7]),new_rating)
    c.execute("UPDATE pokemon_rank_tb SET rating=%s,wins=wins+1,current_streak=%s,best_streak=%s,season_best_streak=%s,peak_rating=%s,rating_reached_at=NOW(),updated_at=NOW() WHERE user_id=%s",(new_rating,ws,best,season_best,peak,winner))
    c.execute("UPDATE pokemon_rank_tb SET rating=GREATEST(0,rating-%s),losses=losses+1,current_streak=0,rating_reached_at=NOW(),updated_at=NOW() WHERE user_id=%s",(delta,loser))
    return delta


def _resolve_round_cursor(c,bid:int,state:dict)->tuple[str|None,list[str],dict]:
    ids=list(state['players'].keys()); choices=state.get('choices',{})
    if any(uid not in choices for uid in ids):return None,[],state
    logs=[]
    # Cada acción pertenece al Pokémon que estaba activo cuando comenzó la resolución.
    # Si ese Pokémon cae antes de actuar y entra un reemplazo, la acción vieja NO se hereda.
    source_active={uid:int(state['players'][uid]['active']) for uid in ids}
    order=sorted(ids,key=lambda u:_choice_speed(state['players'][u],choices[u]),reverse=True)
    for uid in order:
        if state.get('status')!='active':break
        p=state['players'][uid]; oppid=ids[1] if uid==ids[0] else ids[0]; o=state['players'][oppid]; choice=choices[uid]
        original_active=source_active.get(uid)
        if original_active is None or int(p['active'])!=int(original_active):
            # El Pokémon que eligió la acción fue debilitado/cambiado antes de su turno.
            continue
        mon=p['mons'][int(original_active)]
        if mon['hp']<=0:continue
        if choice['type']=='switch':
            idx=int(choice['index'])
            if 0<=idx<len(p['mons']) and p['mons'][idx]['hp']>0 and idx!=p['active']:
                p['mons'][p['active']]['choice_lock']=None
                p['active']=idx; _mark_training_participant(state,uid,p['mons'][idx]); logs.append(f"🔄 {p['name']} cambió a {_battle_title_mon(p['mons'][idx])}.")
            continue
        if choice['type']=='item':
            logs.append(f"{p['name']}: {_apply_item_action(p,choice,c,int(uid))}")
            continue
        # El rival puede haberse cambiado/curado antes de este ataque.
        mon=p['mons'][p['active']]; target=o['mons'][o['active']]
        code=choice.get('move'); pp=int(mon.get('pp',{}).get(code,0))
        if pp<=0:
            logs.append(f"⚠️ {p['name']} no tenía PP para ese movimiento.")
            continue
        mon['pp'][code]=pp-1
        logs += _do_move(mon,target,code)
        if target['hp']<=0:
            logs.append(f"💫 {_battle_title_mon(target)} quedó debilitado.")
            target['choice_lock']=None
            nxt=_next_alive(o)
            if nxt is None:
                state['status']='finished'; state['winner']=uid; state['loser']=oppid; break
            o['active']=nxt; _mark_training_participant(state,oppid,o['mons'][nxt]); logs.append(f"➡️ {o['name']} envía a {_battle_title_mon(o['mons'][nxt])}.")
        # Efectos como Vidaesfera pueden debilitar al atacante después de golpear.
        if state.get('status')=='active' and mon['hp']<=0:
            logs.append(f"💫 {_battle_title_mon(mon)} quedó debilitado.")
            mon['choice_lock']=None
            nxt=_next_alive(p)
            if nxt is None:
                state['status']='finished'; state['winner']=oppid; state['loser']=uid; break
            p['active']=nxt; _mark_training_participant(state,uid,p['mons'][nxt]); logs.append(f"➡️ {p['name']} envía a {_battle_title_mon(p['mons'][nxt])}.")
    # daño de veneno al final de ronda
    if state.get('status')=='active':
        for uid in ids:
            p=state['players'][uid]; mon=p['mons'][p['active']]
            if mon.get('status')=='poison' and mon['hp']>0:
                dmg=max(1,mon['max_hp']//8); mon['hp']=max(0,mon['hp']-dmg); logs.append(f"☠️ {_battle_title_mon(mon)} perdió {dmg} HP por veneno.")
                if mon['hp']<=0:
                    mon['choice_lock']=None
                    nxt=_next_alive(p)
                    if nxt is None:
                        other=ids[1] if uid==ids[0] else ids[0]; state['status']='finished'; state['winner']=other; state['loser']=uid; break
                    p['active']=nxt; _mark_training_participant(state,uid,p['mons'][nxt]); logs.append(f"➡️ {p['name']} envía a {_battle_title_mon(p['mons'][nxt])}.")
    if state.get('status')=='active':_apply_held_end_round(state,logs)
    state['choices']={}; state['round']=int(state.get('round',1))+1
    return state.get('winner'),logs,state


def _finish_battle_cursor(c,bid:int,state:dict)->dict:
    winner=int(state['winner']); loser=int(state['loser'])
    c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(WIN_PIPESOS,winner))
    c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(LOSS_PIPESOS,loser))
    delta=_update_rank_cursor(c,winner,loser)
    _mission_progress_cursor(c,winner,'win',1)
    # Recompensas por racha PvP: una vez por umbral y temporada.
    c.execute("SELECT current_streak FROM pokemon_rank_tb WHERE user_id=%s",(winner,)); _sr=c.fetchone(); _streak=int(_sr[0]) if _sr else 0
    _season=_pokemon_month_key(); streak_notes=[]
    for _threshold in (3,5,10):
        if _streak>=_threshold:
            c.execute("INSERT INTO pokemon_streak_rewards_tb(user_id,threshold,season_key) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING RETURNING threshold",(winner,_threshold,_season)); _got=c.fetchone()
            if _got:
                if _threshold==3:grant_item_with_cursor(c,winner,'rare_candy',1); streak_notes.append('🔥 Racha 3: +1 Caramelo Raro')
                elif _threshold==5:grant_item_with_cursor(c,winner,'object_box',1); streak_notes.append('🔥 Racha 5: +1 Caja de Objetos Pokémon')
                else:
                    _sk=f'streak10:{_season}:{winner}'; c.execute("INSERT INTO pokemon_season_boxes_tb(owner_id,season_key,placement) VALUES(%s,%s,1) ON CONFLICT(owner_id,season_key) DO NOTHING",(winner,_sk)); streak_notes.append('🔥 Racha 10: +1 Caja Pokémon SHINY garantizado')
    level_notes=list(streak_notes); xp_rewards={}
    player_ids=list(state['players'].keys())
    for uid,p in state['players'].items():
        won=int(uid)==winner
        other=next((state['players'][oid] for oid in player_ids if oid!=str(uid)),None)
        rival_levels=[int(m.get('level',1)) for m in (other or {}).get('mons',[])]
        rival_avg=max(1,round(sum(rival_levels)/len(rival_levels))) if rival_levels else 1
        amount=_combat_xp_amount(rival_avg,won,'pvp'); xp_rewards[str(uid)]=amount
        for mon in p['mons']:
            level_notes += _grant_pokemon_xp_cursor(c,int(mon['pid']),amount)
        c.execute("UPDATE pokemon_instances_tb SET wins=wins+1 WHERE owner_id=%s AND pokemon_id=ANY(%s)",(int(uid),[int(m['pid']) for m in p['mons']])) if won else c.execute("UPDATE pokemon_instances_tb SET losses=losses+1 WHERE owner_id=%s AND pokemon_id=ANY(%s)",(int(uid),[int(m['pid']) for m in p['mons']]))
    c.execute("UPDATE pokemon_battles_tb SET status='finished',winner_id=%s,state_json=%s,finished_at=NOW(),updated_at=NOW() WHERE battle_id=%s",(winner,json.dumps(state,ensure_ascii=False),bid))
    tournament=_record_tournament_battle_cursor(c,bid,winner)
    return {'winner':winner,'loser':loser,'elo':delta,'notes':level_notes,'tournament':tournament,'xp_rewards':xp_rewards}


def _today_pokemon_date():
    return datetime.now(POKEMON_TZ).date()


def _training_used_cursor(c,uid:int,day=None,lock:bool=False)->int:
    day=day or _today_pokemon_date()
    c.execute("INSERT INTO pokemon_training_daily_tb(user_id,training_date,completed) VALUES(%s,%s,0) ON CONFLICT DO NOTHING",(uid,day))
    c.execute("SELECT completed FROM pokemon_training_daily_tb WHERE user_id=%s AND training_date=%s"+(' FOR UPDATE' if lock else ''),(uid,day))
    r=c.fetchone(); return int(r[0]) if r else 0


def _make_training_bot_mon(level:int)->dict:
    level=max(1,min(MAX_LEVEL,int(level)))
    # Evita llenar el entrenamiento de legendarios; el reto se balancea por nivel.
    pool=[i for i in range(1,152) if i not in LEGENDARY_IDS]
    species=random.choice(pool)
    ivs=_roll_ivs(False); moves=available_moves(species,level)
    hp=_stat_value(species,level,'hp',ivs['hp'])
    return {'pid':-random.randint(100000,999999999),'species':species,'nickname':None,'level':level,'hp':hp,'max_hp':hp,
            'moves':moves,'pp':{m:MOVES[m][4] for m in moves if m in MOVES},'status':None,'sleep':0,
            'stages':{'atk':0,'def':0,'spd':0},'shiny':False,'ivs':ivs,'held_item':None,'choice_lock':None}


def _training_bot_choice(state:dict)->dict:
    bot=state['players'][str(TRAINING_BOT_ID)]; mon=bot['mons'][bot['active']]
    usable=[m for m in mon.get('moves',[]) if m in MOVES and int(mon.get('pp',{}).get(m,0))>0]
    if not usable:
        usable=[m for m in mon.get('moves',[]) if m in MOVES]
        if usable:mon.setdefault('pp',{})[usable[0]]=1
    if not usable:return {'type':'move','move':next(iter(MOVES))}
    damaging=[m for m in usable if MOVES[m][5] in ('damage','drain','fixed','fixed40')]
    pick=random.choice(damaging if damaging and random.random()<0.80 else usable)
    return {'type':'move','move':pick}


def _finish_training_cursor(c,bid:int,state:dict)->dict:
    uid=int(state['training_user_id'])
    c.execute("SELECT training_id,training_date,rival_avg_level,status FROM pokemon_training_sessions_tb WHERE battle_id=%s FOR UPDATE",(bid,))
    sr=c.fetchone()
    if not sr or sr[3]!='active':
        return {'training':True,'duplicate':True,'winner':int(state.get('winner',-1)),'loser':int(state.get('loser',-1)),'xp_lines':[],'notes':[]}
    training_id=int(sr[0]); day=sr[1]; avg=int(sr[2]); won=int(state['winner'])==uid
    xp_amount=_combat_xp_amount(avg,won,'training')
    reward=TRAINING_WIN_PIPESOS if won else TRAINING_LOSS_PIPESOS
    participants=[]; seen=set()
    for raw in state.get('training_participants',[]):
        pid=int(raw)
        if pid>0 and pid not in seen:seen.add(pid); participants.append(pid)
    xp_lines=[]; notes=[]
    for pid in participants:
        c.execute("SELECT species_id,nickname,level FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); rr=c.fetchone()
        if not rr:continue
        before_name=rr[1] or NAMES[int(rr[0])]
        xp_lines.append(f"{before_name} +{xp_amount} XP")
        notes += _grant_pokemon_xp_cursor(c,pid,xp_amount)
    c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(reward,uid))
    held_drop=None
    if won:
        held_drop=_roll_training_held_item()
        if held_drop:grant_item_with_cursor(c,uid,held_drop,1)
    used=_training_used_cursor(c,uid,day,lock=True)
    if used<TRAINING_DAILY_LIMIT:
        c.execute("UPDATE pokemon_training_daily_tb SET completed=completed+1,updated_at=NOW() WHERE user_id=%s AND training_date=%s",(uid,day))
        used+=1
    # Halloween: solo PvE y solo por rivales realmente debilitados. PvP nunca genera dulces.
    enemy=state.get('players',{}).get(str(TRAINING_BOT_ID),{})
    defeated_species=[int(m.get('species',0)) for m in enemy.get('mons',[]) if int(m.get('hp',0))<=0]
    halloween_candies=_halloween_award_species_cursor(c,uid,defeated_species)
    _mission_progress_cursor(c,uid,'training',1)
    result='win' if won else 'loss'
    c.execute("""UPDATE pokemon_training_sessions_tb SET status='finished',result=%s,xp_per_pokemon=%s,pipesos_reward=%s,
                 held_item_drop=%s,finished_at=NOW() WHERE training_id=%s AND status='active'""",
              (result,xp_amount,reward,held_drop,training_id))
    c.execute("UPDATE pokemon_battles_tb SET status='finished',winner_id=%s,state_json=%s,finished_at=NOW(),updated_at=NOW() WHERE battle_id=%s AND status='active'",
              (int(state['winner']),json.dumps(state,ensure_ascii=False),bid))
    return {'training':True,'duplicate':False,'winner':int(state['winner']),'loser':int(state['loser']),'won':won,
            'xp':xp_amount,'xp_lines':xp_lines,'notes':notes,'pipesos':reward,'used':used,'held_drop':held_drop,'avg':avg,
            'halloween_candies':halloween_candies}


def _training_result_lines(final:dict)->list[str]:
    if final.get('duplicate'):return ['🏋️ Este entrenamiento ya había sido procesado.']
    lines=['🏋️ Entrenamiento terminado']
    lines += final.get('xp_lines',[])
    lines.append(f"💰 +{int(final.get('pipesos',0)):,} PiPesos")
    if final.get('held_drop'):
        code=final['held_drop']; x=HELD_ITEMS.get(code)
        if x:lines.append(f"🎁 Encontraste: {x['emoji']} {x['name']}")
    if int(final.get('halloween_candies',0))>0:
        lines.append(f"🎃🍬 +{int(final['halloween_candies'])} Dulces Halloween")
    lines += final.get('notes',[])[:6]
    lines.append(f"Entrenamientos de hoy: {int(final.get('used',0))}/{TRAINING_DAILY_LIMIT}")
    return lines


def _finish_safari_battle_cursor(c,bid:int,state:dict)->dict:
    uid=int(state['safari_user_id']); sid=int(state['safari_session_id']); won=int(state['winner'])==uid
    c.execute("SELECT current_species,current_level,current_shiny,status FROM pokemon_safari_sessions_tb WHERE session_id=%s AND user_id=%s FOR UPDATE",(sid,uid)); sr=c.fetchone()
    if not sr:return {'safari':True,'duplicate':True,'won':False,'uid':uid,'session_id':sid,'notes':[]}
    notes=[]; xp=0
    user=state['players'].get(str(uid),{})
    if user.get('mons'):
        rival_level=int(sr[1] or 1); xp=_combat_xp_amount(rival_level,won,'npc')
        for mon in user['mons']:notes += _grant_pokemon_xp_cursor(c,int(mon['pid']),xp)
    if won:
        c.execute("UPDATE pokemon_safari_sessions_tb SET current_defeated=TRUE WHERE session_id=%s",(sid,))
        _mission_progress_cursor(c,uid,'win',1)
    else:
        # Si pierdes, el Pokémon se escapa y puedes volver a explorar dentro del tiempo restante.
        c.execute("UPDATE pokemon_safari_sessions_tb SET current_species=NULL,current_level=NULL,current_shiny=NULL,current_ivs_json=NULL,current_defeated=FALSE WHERE session_id=%s",(sid,))
    c.execute("UPDATE pokemon_battles_tb SET status='finished',winner_id=%s,state_json=%s,finished_at=NOW(),updated_at=NOW() WHERE battle_id=%s",(int(state['winner']),json.dumps(state,ensure_ascii=False),bid))
    return {'safari':True,'duplicate':False,'won':won,'uid':uid,'session_id':sid,'xp':xp,'notes':notes,'species':int(sr[0]) if sr[0] else None}


def _safari_result_lines(final:dict)->list[str]:
    if final.get('duplicate'):return ['🌿 Esta batalla Safari ya había terminado.']
    if final.get('won'):
        lines=['🌿 ¡Victoria en la Zona Safari!',f"⭐ +{int(final.get('xp',0))} XP",'💫 El Pokémon quedó debilitado. Ahora puedes intentar capturarlo con una Safari Ball.']
    else:lines=['🌿 El Pokémon Safari ganó el combate y escapó.','🌾 Puedes volver a explorar mientras tu pase siga activo.']
    lines += list(final.get('notes',[]))[:5]
    return lines


async def entrenamientopokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type!='private' and not _is_games_topic(update):
        return await update.effective_message.reply_text('🏋️ El Centro de Entrenamiento Pokémon se usa por privado o en Juegos y Casino.')
    uid=update.effective_user.id; conn=_get_connection(); state=None; bid=None
    try:
        c=conn.cursor(); day=_today_pokemon_date(); used=_training_used_cursor(c,uid,day,lock=True)
        if used>=TRAINING_DAILY_LIMIT:
            conn.rollback(); return await update.effective_message.reply_text('Ya completaste tus 3 entrenamientos Pokémon de hoy. Vuelve mañana.')
        if _battle_busy_cursor(c,uid):
            conn.rollback(); return await update.effective_message.reply_text('⚔️ Ya tienes una batalla Pokémon pendiente o activa.')
        if _trade_busy_cursor(c,uid):
            conn.rollback(); return await update.effective_message.reply_text('🔄 Termina tu intercambio Pokémon antes de entrenar.')
        _ensure_team_row_cursor(c,uid); c.execute("SELECT slot1,slot2,slot3,slot4 FROM pokemon_team_tb WHERE owner_id=%s",(uid,)); slots=list(c.fetchone() or (None,None,None,None))
        mode=0
        for slot in slots[:3]:
            if slot is None:break
            mode+=1
        if mode<1:
            conn.rollback(); return await update.effective_message.reply_text('🏋️ Necesitas al menos un Pokémon en el primer espacio de /equipo.')
        user_mons=_team_for_battle_cursor(c,uid,mode)
        if not user_mons:
            conn.rollback(); return await update.effective_message.reply_text('🏋️ No pude preparar tu equipo. Revisa /equipo.')
        bot_mons=[]
        for mon in user_mons:
            rival_level=max(1,min(MAX_LEVEL,int(mon['level'])+random.choice([-2,-1,0,0,0,1,2])))
            bot_mons.append(_make_training_bot_mon(rival_level))
        avg=max(1,min(MAX_LEVEL,int(math.floor(sum(m['level'] for m in bot_mons)/len(bot_mons)+0.5))))
        state={'status':'active','battle_kind':'training','training_user_id':uid,'training_participants':[int(user_mons[0]['pid'])],
               'mode':mode,'round':1,'choices':{},'players':{
                   str(uid):{'name':_display_name_cursor(c,uid),'mons':user_mons,'active':0},
                   str(TRAINING_BOT_ID):{'name':'Entrenador Pi','mons':bot_mons,'active':0}}}
        c.execute("""INSERT INTO pokemon_battles_tb(chat_id,thread_id,challenger_id,opponent_id,mode,status,state_json)
                     VALUES(%s,%s,%s,%s,%s,'active',%s) RETURNING battle_id""",
                  (update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),uid,TRAINING_BOT_ID,mode,json.dumps(state,ensure_ascii=False)))
        bid=int(c.fetchone()[0])
        c.execute("INSERT INTO pokemon_training_sessions_tb(battle_id,user_id,training_date,rival_avg_level,status) VALUES(%s,%s,%s,%s,'active')",
                  (bid,uid,day,avg))
        conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK training start]',type(e).__name__,e)
        return await update.effective_message.reply_text('No pude iniciar el entrenamiento Pokémon. No se gastó ningún intento.')
    finally:_put_connection(conn)
    try:
        msg=await update.effective_message.reply_text(_battle_text(state,f'🏋️ Centro de Entrenamiento · rival promedio Nv.{avg}\nIntentos completados hoy: {used}/{TRAINING_DAILY_LIMIT}'),reply_markup=_battle_markup(bid))
    except Exception as e:
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("UPDATE pokemon_battles_tb SET status='cancelled',finished_at=NOW(),updated_at=NOW() WHERE battle_id=%s AND status='active'",(bid,))
            c.execute("UPDATE pokemon_training_sessions_tb SET status='technical_error',finished_at=NOW() WHERE battle_id=%s AND status='active'",(bid,)); conn.commit()
        except Exception:conn.rollback()
        finally:_put_connection(conn)
        print('[PK training telegram]',type(e).__name__,e); return
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE pokemon_battles_tb SET message_id=%s,updated_at=NOW() WHERE battle_id=%s",(msg.message_id,bid)); conn.commit()
    except Exception:conn.rollback()
    finally:_put_connection(conn)
    await _sync_single_battle_views(context,bid,state,update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),msg.message_id,
                                    f'🏋️ Centro de Entrenamiento · rival promedio Nv.{avg}\nIntentos completados hoy: {used}/{TRAINING_DAILY_LIMIT}')


async def batallapokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private':return await update.effective_message.reply_text('⚔️ Las batallas Pokémon se retan en el tema Juegos y Casino.')
    if not _is_games_topic(update):return await update.effective_message.reply_text('⚠️ Las batallas Pokémon solo se pueden iniciar en el tema Juegos y Casino.')
    uid=update.effective_user.id; target=_resolve_target(update,context)
    if target==uid:return await update.effective_message.reply_text('😂 No puedes retarte a ti mismo.')
    if context.args and context.args[0].startswith('@') and target is None:return await update.effective_message.reply_text('No encontré a ese usuario registrado. También puedes responderle con /batallapokemon.')
    conn=_get_connection(); tournament_match=None
    try:
        c=conn.cursor(); c.execute("SELECT 1 FROM pokemon_battles_tb WHERE status IN ('open','active') AND (challenger_id=%s OR opponent_id=%s) LIMIT 1",(uid,uid))
        if c.fetchone():return await update.effective_message.reply_text('⚔️ Ya tienes un reto Pokémon pendiente o activo.')
        if _trade_busy_cursor(c,uid):return await update.effective_message.reply_text('🔄 Termina o cancela tu intercambio Pokémon antes de iniciar una batalla.')
        if target is not None:
            tournament_match=_tournament_match_for_pair_cursor(c,update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),uid,target)
        if tournament_match:
            mid,tid,tmode=map(int,tournament_match)
            c.execute("INSERT INTO pokemon_battles_tb(chat_id,thread_id,challenger_id,opponent_id,mode,tournament_match_id) VALUES(%s,%s,%s,%s,%s,%s) RETURNING battle_id",(update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),uid,target,tmode,mid)); bid=int(c.fetchone()[0])
            c.execute("UPDATE pokemon_tournament_matches_tb SET battle_id=%s,status='active' WHERE match_id=%s",(bid,mid))
        else:
            c.execute("INSERT INTO pokemon_battles_tb(chat_id,thread_id,challenger_id,opponent_id) VALUES(%s,%s,%s,%s) RETURNING battle_id",(update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),uid,target)); bid=int(c.fetchone()[0])
        conn.commit()
    except Exception:conn.rollback(); raise
    finally:_put_connection(conn)
    who=f' para <b>{update.effective_message.reply_to_message.from_user.first_name}</b>' if target and update.effective_message.reply_to_message else (' dirigido a ese usuario' if target else ' abierto para quien quiera aceptar')
    if tournament_match:
        tmode=int(tournament_match[2]); kb=InlineKeyboardMarkup([[InlineKeyboardButton(f'🏆 Aceptar torneo · {tmode}v{tmode}',callback_data=f'pk:accept:{bid}:{tmode}')],[InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:cancelchallenge:{bid}')]])
        text=f'🏆 <b>BATALLA DE TORNEO</b>{who}\n\nFormato obligatorio: {tmode}v{tmode}. El ganador avanzará automáticamente en el cuadro.'
    else:
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('1️⃣ 1v1',callback_data=f'pk:accept:{bid}:1'),InlineKeyboardButton('2️⃣ 2v2',callback_data=f'pk:accept:{bid}:2'),InlineKeyboardButton('3️⃣ 3v3',callback_data=f'pk:accept:{bid}:3')],[InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:cancelchallenge:{bid}')]])
        text=f'⚔️ <b>RETO POKÉMON</b>{who}\n\nEl rival elige formato. Después ambos eligen por privado qué Pokémon de sus 4 usar y en qué orden. El equipo permanece oculto hasta salir a pelear.'
    await update.effective_message.reply_text(text,reply_markup=kb,parse_mode='HTML')


def _trade_busy_cursor(c, uid:int)->bool:
    c.execute("""SELECT 1 FROM pokemon_trades_tb
                 WHERE status IN ('selecting','confirming') AND (user_a=%s OR user_b=%s)
                 LIMIT 1""", (uid,uid))
    return c.fetchone() is not None


def _battle_busy_cursor(c, uid:int)->bool:
    c.execute("""SELECT 1 FROM pokemon_battles_tb
                 WHERE status IN ('open','active') AND (challenger_id=%s OR opponent_id=%s)
                 LIMIT 1""", (uid,uid))
    return c.fetchone() is not None


def _trade_pick_markup(uid:int, trade_id:int, page:int=0):
    mons=_get_owned(uid)
    pages=max(1,math.ceil(len(mons)/PAGE_SIZE)); page=max(0,min(page,pages-1))
    chunk=mons[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
    rows=[[InlineKeyboardButton(_pokemon_label(r)[:54],callback_data=f'pk:tradeoffer:{trade_id}:{r[0]}')] for r in chunk]
    nav=[]
    if page>0:nav.append(InlineKeyboardButton('⬅️',callback_data=f'pk:tradepick:{trade_id}:{page-1}'))
    nav.append(InlineKeyboardButton(f'{page+1}/{pages}',callback_data='pk:noop'))
    if page<pages-1:nav.append(InlineKeyboardButton('➡️',callback_data=f'pk:tradepick:{trade_id}:{page+1}'))
    if nav:rows.append(nav)
    rows.append([InlineKeyboardButton('❌ Cancelar intercambio',callback_data=f'pk:tradecancel:{trade_id}')])
    return InlineKeyboardMarkup(rows)


def _trade_mon_text_cursor(c, owner:int, pid:int|None)->str:
    if not pid:return '— pendiente —'
    c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp
                 FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s""",(owner,pid))
    r=c.fetchone()
    return _pokemon_label(r) if r else '— ya no disponible —'


async def gifintercambio_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    try:
        if not is_botmaster(update.effective_user.id):
            return await update.effective_message.reply_text('Solo BotMaster puede cambiar el GIF global de intercambio.')
    except Exception:
        return await update.effective_message.reply_text('Solo BotMaster puede cambiar el GIF global de intercambio.')
    msg=update.effective_message; replied=msg.reply_to_message if msg else None
    animation=getattr(replied,'animation',None) if replied else None
    if not animation:
        return await msg.reply_text('Responde a un GIF de Telegram con /gifintercambio.')
    file_id=str(animation.file_id); conn=_get_connection()
    try:
        c=conn.cursor(); _setting_set_cursor(c,'trade_gif_file_id',file_id); conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK trade gif set]',type(e).__name__,e); return await msg.reply_text('No pude guardar el GIF de intercambio.')
    finally:_put_connection(conn)
    await msg.reply_text('✅ GIF global de intercambio guardado por file_id.')


async def quitargifintercambio_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    try:
        if not is_botmaster(update.effective_user.id):
            return await update.effective_message.reply_text('Solo BotMaster puede quitar el GIF global de intercambio.')
    except Exception:
        return await update.effective_message.reply_text('Solo BotMaster puede quitar el GIF global de intercambio.')
    conn=_get_connection()
    try:
        c=conn.cursor(); _setting_set_cursor(c,'trade_gif_file_id',None); conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK trade gif remove]',type(e).__name__,e); return await update.effective_message.reply_text('No pude quitar el GIF de intercambio.')
    finally:_put_connection(conn)
    await update.effective_message.reply_text('🗑️ GIF global de intercambio eliminado.')


async def intercambiopokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private':
        return await update.effective_message.reply_text('🔄 Inicia el intercambio en el grupo respondiendo al mensaje de la otra persona con /intercambiopokemon.')
    if not update.effective_message.reply_to_message:
        return await update.effective_message.reply_text('🔄 Responde al mensaje de la persona con /intercambiopokemon.')
    target_user=update.effective_message.reply_to_message.from_user
    uid=update.effective_user.id; target=target_user.id
    if target==uid or target_user.is_bot:return await update.effective_message.reply_text('😂 Necesitas otra persona real para intercambiar.')
    conn=_get_connection(); trade_id=None
    try:
        c=conn.cursor()
        if _battle_busy_cursor(c,uid) or _battle_busy_cursor(c,target):
            return await update.effective_message.reply_text('⚔️ Uno de los dos tiene una batalla Pokémon pendiente o activa.')
        if _trade_busy_cursor(c,uid) or _trade_busy_cursor(c,target):
            return await update.effective_message.reply_text('🔄 Uno de los dos ya tiene un intercambio pendiente.')
        c.execute("""INSERT INTO pokemon_trades_tb(chat_id,thread_id,user_a,user_b)
                     VALUES(%s,%s,%s,%s) RETURNING trade_id""",
                  (update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),uid,target))
        trade_id=int(c.fetchone()[0]); conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK trade create]',type(e).__name__,e)
        return await update.effective_message.reply_text('No pude crear el intercambio.')
    finally:_put_connection(conn)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('🔄 Elegir mi Pokémon',callback_data=f'pk:tradepick:{trade_id}:0')],[InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:tradecancel:{trade_id}')]])
    msg=await update.effective_message.reply_text(f'🔄 INTERCAMBIO POKÉMON\n\n{update.effective_user.first_name} ↔ {target_user.first_name}\n\nCada uno elige su Pokémon por privado. Cuando ambos elijan, los dos deberán confirmar.\n✨ Kadabra, Machoke, Graveler y Haunter evolucionan al intercambiarse.',reply_markup=kb)
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute('UPDATE pokemon_trades_tb SET message_id=%s WHERE trade_id=%s',(msg.message_id,trade_id)); conn.commit()
    except Exception:conn.rollback()
    finally:_put_connection(conn)


async def cancelarintercambiopokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""UPDATE pokemon_trades_tb SET status='cancelled',finished_at=NOW(),updated_at=NOW()
                                     WHERE status IN ('selecting','confirming') AND (user_a=%s OR user_b=%s)""",(uid,uid)); n=c.rowcount; conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK trade cancel command]',type(e).__name__,e); n=0
    finally:_put_connection(conn)
    await update.effective_message.reply_text('❌ Intercambio Pokémon cancelado.' if n else 'No tienes ningún intercambio Pokémon pendiente.')


def _inventory_category(code:str)->str:
    if code in HELD_ITEMS:return 'held'
    if code in TM_ITEMS:return 'tm'
    if code in STONE_CODES:return 'stone'
    if code=='rare_candy':return 'candy'
    if code in SPECIAL_POKEMON_ITEMS:return 'other'
    return 'other'


def _transfer_category_label(cat:str)->str:
    return {'held':'🎒 Objetos equipables','tm':'💿 MT','stone':'🪨 Piedras evolutivas','candy':'🍬 Caramelos Raros','box':'📦 Cajas Pokémon','other':'📁 Otros objetos Pokémon'}.get(cat,cat)


def _transfer_available_cursor(c,uid:int,cat:str)->list[tuple[str,int]]:
    if cat=='box':
        c.execute("SELECT COUNT(*) FROM pokemon_season_boxes_tb WHERE owner_id=%s AND opened=FALSE",(uid,)); n=int(c.fetchone()[0]); return [('pokemon_box',n)] if n>0 else []
    c.execute("SELECT item_code,qty FROM pokemon_items_tb WHERE owner_id=%s AND qty>0 ORDER BY item_code",(uid,)); out=[]
    for code,qty in c.fetchall():
        code=str(code); qty=int(qty)
        if _inventory_category(code)==cat:out.append((code,qty))
    return out


def _transfer_item_label(code:str)->str:
    if code=='pokemon_box':return '📦 Caja Pokémon'
    if code in HELD_ITEMS:
        x=HELD_ITEMS[code]; return f"{x['emoji']} {x['name']}"
    if code in ITEMS:
        name,em,_,_=ITEMS[code]; return f'{em} {name}'
    if code in SPECIAL_POKEMON_ITEMS:
        x=SPECIAL_POKEMON_ITEMS[code]; return f"{x['emoji']} {x['name']}"
    return f'🎒 {code}'


async def entregar_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    msg=update.effective_message
    if not msg.reply_to_message or not msg.reply_to_message.from_user:
        return await msg.reply_text('🎁 Responde al mensaje de otra persona con /entregar.')
    target=msg.reply_to_message.from_user
    if target.is_bot or target.id==update.effective_user.id:return await msg.reply_text('🎁 Elige a otra persona real.')
    uid=update.effective_user.id; conn=_get_connection(); cats=[]
    try:
        c=conn.cursor()
        for cat in ('held','tm','stone','candy','box','other'):
            if _transfer_available_cursor(c,uid,cat):cats.append(cat)
    finally:_put_connection(conn)
    if not cats:return await msg.reply_text('🎒 No tienes objetos Pokémon disponibles para entregar.')
    rows=[[InlineKeyboardButton(_transfer_category_label(cat),callback_data=f'pk:gcat:{uid}:{target.id}:{cat}')] for cat in cats]
    await msg.reply_text(f'🎁 Entregar a {target.first_name}\n\nElige una categoría:',reply_markup=InlineKeyboardMarkup(rows))


async def shinys_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp
                                     FROM pokemon_instances_tb WHERE owner_id=%s AND shiny=TRUE ORDER BY pokemon_id""",(uid,)); rows=c.fetchall()
    finally:_put_connection(conn)
    lines=[f'✨ TUS SHINYS · {len(rows)}','']
    lines += [_pokemon_label(r) for r in rows[:40]] if rows else ['Todavía no tienes ninguno. La probabilidad base es 1 entre 4096 cuando obtienes un Pokémon.']
    if len(rows)>40:lines.append(f'… y {len(rows)-40} más.')
    try:await context.bot.send_message(uid,'\n'.join(lines))
    except Exception:return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private':await update.effective_message.reply_text('📩 Te mandé tus Shinys por privado.')


async def rankingpokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    rollover=_ensure_pokemon_season(); uid=update.effective_user.id; conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("""SELECT r.user_id,r.rating,r.wins,r.losses,r.season_best_streak,COALESCE(NULLIF(p.nombre,''),p.username,'Jugador')
                                   FROM pokemon_rank_tb r LEFT JOIN perfiles_tb p ON p.id_user=r.user_id
                                   WHERE (r.wins+r.losses)>0
                                   ORDER BY r.rating DESC,r.wins DESC,r.rating_reached_at ASC,r.user_id ASC LIMIT 10"""); rows=c.fetchall()
        c.execute("SELECT COUNT(*) FROM pokemon_season_boxes_tb WHERE owner_id=%s AND opened=FALSE",(uid,)); pending=int(c.fetchone()[0])
        c.execute("""SELECT season_key,position,rating,wins,losses FROM pokemon_rank_history_tb
                     WHERE position<=3 ORDER BY season_key DESC,position ASC LIMIT 3"""); last_top=c.fetchall()
    finally:_put_connection(conn)
    lines=[f'🏆 RANKING POKÉMON · {_pokemon_month_key()}','']
    if not rows:lines.append('Todavía no hay batallas clasificatorias este mes.')
    medals=['🥇','🥈','🥉']
    for i,r in enumerate(rows,1):lines.append(f"{medals[i-1] if i<=3 else str(i)+'.'} {r[5]} · {r[1]} pts · {r[2]}V/{r[3]}D · 🔥{r[4]}")
    lines += ['', '📅 El ranking se reinicia cada mes a 1,000 puntos.', '🥇 30,000 · 🥈 20,000 · 🥉 10,000 PiPesos', '🎁 Los 3 primeros reciben una Caja Pokémon de temporada con SHINY garantizado.']
    if pending: lines += ['',f'🎁 Tienes {pending} Caja(s) Pokémon de temporada pendientes. Usa /cajapokemon.']
    if rollover and rollover.get('closed'): lines += ['',f"✅ Se cerró la temporada {rollover['closed']}."]
    await update.effective_message.reply_text('\n'.join(lines))


async def cajapokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    _ensure_pokemon_season(); uid=update.effective_user.id; boxes=_pending_season_boxes(uid)
    if not boxes:
        return await update.effective_message.reply_text('🎁 No tienes Cajas Pokémon pendientes.')
    rows=[]
    for box_id,season,placement in boxes[:10]:
        if str(season).startswith('regalo:'):
            label='🎁 Caja de bienvenida · SHINY garantizado'
        elif str(season).startswith('kanto_complete:'):
            label='🏆 Caja Kanto 8/8 · SHINY garantizado'
        else:
            medal={1:'🥇',2:'🥈',3:'🥉'}.get(int(placement),'🏆')
            label=f'{medal} Caja {season} · SHINY garantizado'
        rows.append([InlineKeyboardButton(label,callback_data=f'pk:seasonbox:{box_id}')])
    await update.effective_message.reply_text('🎁 CAJAS POKÉMON\n\nCada una contiene 1 Pokémon SHINY garantizado.',reply_markup=InlineKeyboardMarkup(rows))


async def darcajapokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    """BotMaster: regala de 1 a 10 Cajas Pokémon respondiendo al usuario."""
    try:
        if not is_botmaster(update.effective_user.id):
            return await update.effective_message.reply_text('🎁 Solo BotMaster puede regalar Cajas Pokémon.')
    except Exception:
        return await update.effective_message.reply_text('🎁 Solo BotMaster puede regalar Cajas Pokémon.')

    msg=update.effective_message
    reply=getattr(msg,'reply_to_message',None)
    target=getattr(reply,'from_user',None) if reply else None
    if not target or getattr(target,'is_bot',False):
        return await msg.reply_text('🎁 Responde al mensaje de la persona con /darcajapokemon o /darcajapokemon 2.')

    qty=1
    if context.args:
        try:
            qty=int(context.args[0])
        except Exception:
            return await msg.reply_text('🎁 Usa una cantidad del 1 al 10. Ejemplo: /darcajapokemon 2')
    if qty < 1 or qty > 10:
        return await msg.reply_text('🎁 Puedes regalar entre 1 y 10 cajas por comando.')

    giver_id=update.effective_user.id
    now=datetime.now(timezone.utc)
    conn=_get_connection()
    try:
        c=conn.cursor()
        for i in range(qty):
            gift_key=(
                f"regalo:{now.strftime('%Y%m%d%H%M%S%f')}:"
                f"{giver_id}:{random.randrange(100000,999999)}:{i}"
            )
            c.execute(
                "INSERT INTO pokemon_season_boxes_tb(owner_id,season_key,placement) VALUES(%s,%s,3)",
                (target.id,gift_key),
            )
        conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK gift box]',type(e).__name__,e)
        return await msg.reply_text('⚠️ No pude entregar la Caja Pokémon.')
    finally:
        _put_connection(conn)

    cajas='Caja Pokémon' if qty==1 else 'Cajas Pokémon'
    await msg.reply_text(
        f'🎁 {target.first_name} recibió {qty} {cajas} de bienvenida.\n'
        f'✨ Cada caja tiene 1 Pokémon SHINY garantizado.\n'
        f'📦 Puede abrirla con /cajapokemon.'
    )


async def _is_pokemon_admin(update:Update, context:ContextTypes.DEFAULT_TYPE)->bool:
    try:
        if is_botmaster(update.effective_user.id):return True
    except Exception:pass
    try:
        member=await context.bot.get_chat_member(update.effective_chat.id,update.effective_user.id)
        return member.status in ('administrator','creator')
    except Exception:return False


async def torneopokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private' or not _is_games_topic(update):
        return await update.effective_message.reply_text('🏆 Los torneos Pokémon se organizan en Juegos y Casino.')
    chat_id=update.effective_chat.id; thread_id=getattr(update.effective_message,'message_thread_id',None); conn=_get_connection()
    try:
        c=conn.cursor(); tr=_tournament_active_cursor(c,chat_id,thread_id)
        if tr:
            text=_tournament_round_text_cursor(c,int(tr[0])); tid=int(tr[0]); status=tr[2]
            rows=[]
            if status=='registration':
                rows.append([InlineKeyboardButton('✅ Participar',callback_data=f'pk:tjoin:{tid}'),InlineKeyboardButton('🚪 Salirme',callback_data=f'pk:tleave:{tid}')])
                rows.append([InlineKeyboardButton('📋 Participantes',callback_data=f'pk:tlist:{tid}'),InlineKeyboardButton('🏁 Iniciar',callback_data=f'pk:tstart:{tid}')])
                rows.append([InlineKeyboardButton('❌ Cancelar torneo',callback_data=f'pk:tcancel:{tid}')])
            else:
                rows.append([InlineKeyboardButton('📋 Ver cuadro',callback_data=f'pk:tlist:{tid}'),InlineKeyboardButton('⚔️ Mi rival',callback_data=f'pk:tmatch:{tid}')])
            return await update.effective_message.reply_text(text,reply_markup=InlineKeyboardMarkup(rows))
    finally:_put_connection(conn)
    if not await _is_pokemon_admin(update,context):
        return await update.effective_message.reply_text('🏆 No hay torneo activo. Un admin puede crear uno con /torneopokemon.')
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('1️⃣ 1v1',callback_data='pk:tcreate:1'),InlineKeyboardButton('2️⃣ 2v2',callback_data='pk:tcreate:2'),InlineKeyboardButton('3️⃣ 3v3',callback_data='pk:tcreate:3')]])
    await update.effective_message.reply_text('🏆 CREAR TORNEO POKÉMON\n\nElige el formato. Después se abrirán las inscripciones con botón.',reply_markup=kb)


async def poketest_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    # Solo para que Kiu/admins puedan probar el sistema sin abrir 100 cajas.
    try:
        if not is_botmaster(update.effective_user.id):return await update.effective_message.reply_text('Solo BotMaster puede usar /poketest.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede usar /poketest.')
    try:sid=int(context.args[0]) if context.args else random.randint(1,151)
    except Exception:sid=random.randint(1,151)
    force_shiny=any(str(x).lower() in ('shiny','variocolor','✨') for x in context.args[1:]) if context.args else False
    force_perfect=any(str(x).lower() in ('perfect','perfecto','100','iv100') for x in context.args[1:]) if context.args else False
    sid=max(1,min(151,sid)); conn=_get_connection()
    try:
        c=conn.cursor(); data=grant_pokemon_with_cursor(c,update.effective_user.id,sid,'prueba_admin',force_shiny=force_shiny,force_perfect=force_perfect); conn.commit()
    except Exception as e:conn.rollback(); return await update.effective_message.reply_text(f'Error de prueba: {e}')
    finally:_put_connection(conn)
    await update.effective_message.reply_text(f"🧪 Te di #{sid:03d} {'✨ SHINY ' if data.get('shiny') else ''}{NAMES[sid]} {_sex_symbol(data.get('sex'))} Nv.{data['level']} · IV {data.get('iv_percent',0)}% {data.get('iv_grade','')} para probar. No costó PiPesos.")


def _candy_total(uid:int)->int:
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT qty FROM pokemon_items_tb WHERE owner_id=%s AND item_code='rare_candy'",(uid,)); r=c.fetchone()
        return int(r[0] or 0) if r else 0
    finally:_put_connection(conn)


def _spend_rare_candies_cursor(c, uid:int, amount:int)->bool:
    amount=max(0,int(amount))
    if amount<=0:return True
    c.execute("""UPDATE pokemon_items_tb SET qty=qty-%s
                 WHERE owner_id=%s AND item_code='rare_candy' AND qty>=%s RETURNING qty""",(amount,uid,amount))
    return bool(c.fetchone())


def _release_markup(uid:int, page:int=0):
    mons=_get_owned(uid); pages=max(1,math.ceil(len(mons)/PAGE_SIZE)); page=max(0,min(page,pages-1))
    chunk=mons[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
    rows=[[InlineKeyboardButton(_pokemon_label(r)[:52],callback_data=f'pk:releasepick:{r[0]}:{page}')] for r in chunk]
    nav=[]
    if page>0:nav.append(InlineKeyboardButton('⬅️',callback_data=f'pk:releasepage:{page-1}'))
    nav.append(InlineKeyboardButton(f'{page+1}/{pages}',callback_data='pk:noop'))
    if page<pages-1:nav.append(InlineKeyboardButton('➡️',callback_data=f'pk:releasepage:{page+1}'))
    if nav:rows.append(nav)
    rows.append([InlineKeyboardButton('🎮 Volver a colección',callback_data='pk:list:0')])
    return InlineKeyboardMarkup(rows)


async def liberarpokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    try:
        await context.bot.send_message(uid,
            '🌿 LIBERAR POKÉMON\n\nElige uno. Liberarlo es permanente y te dará Caramelos Raros.\n\n🍬 Común/Raro: 1 Caramelo Raro · Épico/Legendario: 2 Caramelos Raros.\n⭐ El principal y los Pokémon de tu equipo no se pueden liberar.',
            reply_markup=_release_markup(uid,0))
    except Exception:
        return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private':
        await update.effective_message.reply_text('📩 Te mandé la liberación Pokémon por privado.')


async def caramelospokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; total=_candy_total(uid)
    lines=['🍬 CARAMELOS POKÉMON','',f'🍬 Caramelos Raros: {total}','','1 Caramelo Raro = +1 nivel, hasta nivel 100.','Puedes conseguirlos liberando Pokémon o como drop de algunas capturas salvajes.']
    if total<=0:
        lines.insert(2,'Todavía no tienes Caramelos Raros.')
    try:await context.bot.send_message(uid,'\n'.join(lines))
    except Exception:return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private':await update.effective_message.reply_text('📩 Te mandé tus Caramelos Raros por privado.')


async def _trainer_profile_data(uid:int):
    _ensure_pokemon_season()
    conn=_get_connection()
    try:
        c=conn.cursor(); _ensure_trainer_row_cursor(c,uid); _ensure_team_row_cursor(c,uid)
        name=_display_name_cursor(c,uid)
        c.execute("SELECT COUNT(*),COUNT(*) FILTER(WHERE shiny=TRUE) FROM pokemon_instances_tb WHERE owner_id=%s",(uid,)); total,shinys=c.fetchone()
        c.execute("SELECT COUNT(*) FROM pokemon_pokedex_tb WHERE owner_id=%s",(uid,)); dex=int(c.fetchone()[0])
        c.execute("SELECT rating,wins,losses,best_streak,season_best_streak,peak_rating FROM pokemon_rank_tb WHERE user_id=%s",(uid,)); rank=c.fetchone() or (1000,0,0,0,0,1000)
        c.execute("SELECT wild_catches,released,candies_earned,media_type,media_file_id,tournament_wins FROM pokemon_trainer_tb WHERE user_id=%s",(uid,)); tr=c.fetchone() or (0,0,0,None,None,0)
        c.execute("SELECT COUNT(*) FILTER(WHERE position=1),COUNT(*) FILTER(WHERE position<=3) FROM pokemon_rank_history_tb WHERE user_id=%s",(uid,)); hist=c.fetchone() or (0,0)
        c.execute("SELECT COUNT(*) FROM pokemon_season_boxes_tb WHERE owner_id=%s AND opened=FALSE",(uid,)); pending_boxes=int(c.fetchone()[0])
        c.execute("SELECT COALESCE(qty,0) FROM pokemon_items_tb WHERE owner_id=%s AND item_code='rare_candy'",(uid,)); cr=c.fetchone(); candies=int(cr[0] or 0) if cr else 0
        c.execute("SELECT COUNT(*) FROM pokemon_badges_tb WHERE user_id=%s",(uid,)); badges=int(c.fetchone()[0])
        c.execute("SELECT principal_pokemon_id FROM pokemon_team_tb WHERE owner_id=%s",(uid,)); pr=c.fetchone(); principal=int(pr[0]) if pr and pr[0] else None
        prow=None
        if principal:
            c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp
                         FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s""",(uid,principal)); prow=c.fetchone()
        conn.commit()
        return {
            'name':name,'total':int(total),'shinys':int(shinys),'dex':dex,'rank':rank,'trainer':tr,
            'candies':candies,'principal':prow,'media_type':tr[3],'media_file_id':tr[4],
            'history':hist,'pending_boxes':pending_boxes,'badges':badges
        }
    except Exception:
        conn.rollback(); raise
    finally:_put_connection(conn)


def _trainer_profile_text(data:dict)->str:
    rank=data['rank']; tr=data['trainer']; prow=data['principal']
    hist=data.get('history') or (0,0)
    lines=[f"🎒 ENTRENADOR POKÉMON · {data['name']}",'',f"📖 Pokédex: {data['dex']}/151",f"🎮 Pokémon: {data['total']}",f"✨ Shinys: {data['shinys']}",f"🎯 Capturas salvajes: {int(tr[0])}",f"🌿 Liberados: {int(tr[1])}",f"🍬 Caramelos Raros: {data['candies']}",f"🏆 Ranking {_pokemon_month_key()}: {int(rank[0])} pts · {int(rank[1])}V/{int(rank[2])}D",f"🔥 Mejor racha histórica: {int(rank[3])}",f"📈 Mejor rating histórico: {int(rank[5])}",f"👑 Campeón mensual: ×{int(hist[0])} · Top 3: ×{int(hist[1])}",f"🏟️ Torneos ganados: {int(tr[5])}",f"🏅 Medallas de Kanto: {int(data.get('badges',0))}/8"]
    if int(data.get('pending_boxes',0))>0: lines.append(f"🎁 Cajas Pokémon pendientes: {int(data['pending_boxes'])}")
    if prow:
        ivpct=_iv_percent(_iv_values(prow)); lines += ['',f"⭐ Principal: {_pokemon_label(prow)}",f"🧬 IV {ivpct}% · {_iv_grade(ivpct)}"]
    else:lines += ['','⭐ Principal: todavía no elegido']
    lines += ['','🔒 Tu equipo y tus movimientos siguen siendo privados.']
    return '\n'.join(lines)


def _trainer_profile_markup(owner_id:int, has_media:bool=True)->InlineKeyboardMarkup:
    rows=[
        [InlineKeyboardButton('📸 Subir/Cambiar foto · GIF · video',callback_data=f'pk:trainermedia:{owner_id}')],
    ]
    if has_media:
        rows.append([InlineKeyboardButton('🗑 Quitar multimedia',callback_data=f'pk:trainerremovemedia:{owner_id}')])
    rows.append([InlineKeyboardButton('🎮 Mi colección',callback_data=f'pk:trainercollection:{owner_id}'),InlineKeyboardButton('😎 Presumir principal',callback_data=f'pk:trainerbrag:{owner_id}')])
    return InlineKeyboardMarkup(rows)


async def _send_trainer_profile(context:ContextTypes.DEFAULT_TYPE, owner_id:int, chat_id:int, thread_id=None, controls:bool=True):
    data=await _trainer_profile_data(owner_id)
    text=_trainer_profile_text(data)
    media_type=data.get('media_type'); file_id=data.get('media_file_id')
    kb=_trainer_profile_markup(owner_id,bool(file_id)) if controls else None
    kwargs={'chat_id':chat_id,'reply_markup':kb}
    if thread_id is not None:kwargs['message_thread_id']=thread_id
    if media_type=='photo' and file_id:
        return await context.bot.send_photo(photo=file_id,caption=text,**kwargs)
    if media_type=='animation' and file_id:
        return await context.bot.send_animation(animation=file_id,caption=text,**kwargs)
    if media_type=='video' and file_id:
        return await context.bot.send_video(video=file_id,caption=text,**kwargs)
    return await context.bot.send_message(text=text,**kwargs)


async def entrenador_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    # Siempre usa el ID de quien ejecuta el comando: cada entrenador ve SU perfil y SU multimedia.
    uid=update.effective_user.id
    try:
        await _send_trainer_profile(context,uid,update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),controls=True)
    except Exception as e:
        print('[PK trainer]',type(e).__name__,e)
        await update.effective_message.reply_text('No pude abrir tu perfil de entrenador.')


def _wild_text(species:int, level:int, shiny:bool)->str:
    # La identidad real permanece oculta mientras el encuentro siga activo.
    period=_wild_period(); period_line='☀️ Aparición diurna' if period=='day' else '🌙 Aparición nocturna'
    return (f"🌿 ¡APARECIÓ UN POKÉMON SALVAJE!\n{period_line}\n\n"
            f"❓ Un Pokémon desconocido apareció...\n\n"
            f"🎯 El primer entrenador que pulse Atrapar se queda con el intento.\n"
            f"🎲 Tiene {WILD_MAX_ATTEMPTS} tiros; si falla los dos, el Pokémon se va.\n"
            f"⏳ La aparición dura 10 minutos.\n\n"
            f"🎲 ¡Atrévete a descubrir cuál es!")


def _wild_reveal_text(species:int, level:int, shiny:bool)->str:
    rarity=rarity_for(species)
    shiny_line='✨ SHINY ✨\n' if shiny else ''
    return (f"👀 El Pokémon misterioso era:\n"
            f"{shiny_line}"
            f"{rarity_emoji(rarity)} #{species:03d} {NAMES[species]} · Nv.{level}\n"
            f"{_types_text(species)}\n"
            f"⭐ Rareza: {rarity.upper()}")


def _wild_ditto_disguise_species(spawn_id:int)->int:
    # Disfraz visual estable por encuentro. Usa un RNG local para no tocar el RNG normal del juego.
    pool=[i for i in range(1,152) if i!=132]
    return random.Random(int(spawn_id) ^ 0xD1770).choice(pool)


def _wild_attempt_reveal_text(spawn_id:int, species:int, level:int, shiny:bool)->str:
    # Al pulsar Atrapar se revela la identidad. Ditto es la única excepción: muestra un disfraz visual.
    shown_species=_wild_ditto_disguise_species(spawn_id) if int(species)==132 else int(species)
    rarity=rarity_for(shown_species)
    shiny_line='✨ SHINY ✨\n' if shiny else ''
    return (f"👀 ¡El Pokémon misterioso era!\n"
            f"{shiny_line}"
            f"{rarity_emoji(rarity)} #{shown_species:03d} {NAMES[shown_species]} · Nv.{level}\n"
            f"{_types_text(shown_species)}\n"
            f"⭐ Rareza: {rarity.upper()}")


async def _expire_wild_spawn(context: ContextTypes.DEFAULT_TYPE):
    data = getattr(context.job, 'data', None) or {}
    spawn_id = int(data.get('spawn_id') or 0)
    if not spawn_id:
        return
    conn = _get_connection(); row = None
    try:
        c = conn.cursor()
        c.execute(
            "SELECT species_id,level,shiny,chat_id,thread_id,message_id,status "
            "FROM pokemon_wild_spawns_tb WHERE spawn_id=%s FOR UPDATE",
            (spawn_id,),
        )
        row = c.fetchone()
        # Si ya alguien lanzó el dado antes de cumplirse los 10 min, dejamos terminar ese tiro.
        if not row or row[6] != 'active':
            conn.rollback(); return
        c.execute(
            "UPDATE pokemon_wild_spawns_tb SET status='expired',finished_at=NOW() "
            "WHERE spawn_id=%s",
            (spawn_id,),
        )
        # A veces un Pokémon que escapó se convierte en fugitivo y puede regresar más adelante.
        if random.random()<0.25:
            c.execute("INSERT INTO pokemon_fugitives_tb(chat_id,thread_id,species_id,level,shiny) VALUES(%s,%s,%s,%s,%s)",
                      (int(row[3]),int(row[4] or 0),int(row[0]),min(MAX_LEVEL,int(row[1])+random.randint(1,3)),bool(row[2])))
        conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK wild expire]', type(e).__name__, e); return
    finally:
        _put_connection(conn)
    try:
        species, level, shiny, chat_id, thread_id, message_id, _ = row
        await context.bot.edit_message_text(
            chat_id=int(chat_id),
            message_id=int(message_id),
            text='⌛ Pasaron 10 minutos y el Pokémon se fue.\n\n' +
                 _wild_reveal_text(int(species), int(level), bool(shiny)),
            reply_markup=None,
        )
    except Exception:
        pass


async def _spawn_wild(context:ContextTypes.DEFAULT_TYPE, chat_id:int, thread_id:int|None)->bool:
    conn=_get_connection(); spawn_id=None; species=None; level=None; shiny=None
    try:
        c=conn.cursor()
        c.execute("UPDATE pokemon_wild_spawns_tb SET status='expired',finished_at=NOW() WHERE chat_id=%s AND thread_id IS NOT DISTINCT FROM %s AND status='active'",(chat_id,thread_id))
        returning=False
        c.execute("SELECT fugitive_id,species_id,level,shiny FROM pokemon_fugitives_tb WHERE chat_id=%s AND thread_id=%s AND status='waiting' ORDER BY last_seen_at LIMIT 1",(chat_id,int(thread_id or 0))); fug=c.fetchone()
        if fug and random.random()<0.20:
            returning=True; species=int(fug[1]); level=int(fug[2]); shiny=bool(fug[3]); c.execute("UPDATE pokemon_fugitives_tb SET status='returned' WHERE fugitive_id=%s",(int(fug[0]),))
        else:
            species=_wild_species_cursor(c,chat_id,thread_id); level=min(MAX_LEVEL,_starting_level(species)+random.randint(0,5)); shiny=(random.randrange(WILD_SHINY_DENOMINATOR)==0)
        c.execute("INSERT INTO pokemon_wild_spawns_tb(chat_id,thread_id,species_id,level,shiny,is_returning) VALUES(%s,%s,%s,%s,%s,%s) RETURNING spawn_id",(chat_id,thread_id,species,level,shiny,returning)); spawn_id=int(c.fetchone()[0]); conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK wild spawn db]',type(e).__name__,e); return False
    finally:_put_connection(conn)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('🎯 Atrapar',callback_data=f'pk:wild:{spawn_id}')]])
    try:
        msg=await context.bot.send_message(chat_id=chat_id,message_thread_id=thread_id,text=_wild_text(species,level,shiny)+("\n\n👣 Hay huellas conocidas... parece que este Pokémon ya había escapado antes." if returning else ""),reply_markup=kb)
    except Exception as e:
        print('[PK wild spawn send]',type(e).__name__,e); return False
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE pokemon_wild_spawns_tb SET message_id=%s WHERE spawn_id=%s",(msg.message_id,spawn_id)); conn.commit()
    except Exception:conn.rollback()
    finally:_put_connection(conn)
    try:
        if context.job_queue:
            context.job_queue.run_once(
                _expire_wild_spawn,
                WILD_LIFETIME_SECONDS,
                data={'spawn_id': spawn_id},
                name=f'pokemon_wild_expire:{spawn_id}',
            )
    except Exception as e:
        print('[PK wild expire schedule]', type(e).__name__, e)
    return True


async def pokemon_wild_spawn_job(context:ContextTypes.DEFAULT_TYPE):
    # Solo se ejecuta cada 30 minutos; no observa mensajes ni hace polling continuo.
    for community in COMUNIDADES:
        try:
            chat_id=int(community.get('id_comunidad')); thread_id=_games_topic(chat_id)
            if thread_id is not None:await _spawn_wild(context,chat_id,thread_id)
        except Exception as e:print('[PK wild job]',type(e).__name__,e)


async def pokemonsalvaje_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    try:
        if not is_botmaster(update.effective_user.id):return await update.effective_message.reply_text('Solo BotMaster puede forzar una aparición Pokémon.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede forzar una aparición Pokémon.')
    if not _is_games_topic(update):return await update.effective_message.reply_text('🌿 Usa /pokemonsalvaje dentro del tema Juegos y Casino.')
    ok=await _spawn_wild(context,update.effective_chat.id,update.effective_message.message_thread_id)
    if not ok:await update.effective_message.reply_text('No pude crear la aparición Pokémon.')



# ==================== GUARDERÍA / HUEVOS ====================
def _live_eggs_cursor(c,uid:int,for_update:bool=False):
    sql=("SELECT egg_id,owner_id,source,egg_tier,species_id,progress,status,parent_a,parent_b,parent_a_species,parent_b_species,shiny,iv_atk,iv_def,iv_spd,iv_spc,pokemon_id,created_at "
         "FROM pokemon_eggs_tb WHERE owner_id=%s AND status IN ('active','hatching') ORDER BY egg_id ASC")
    if for_update:sql += ' FOR UPDATE'
    c.execute(sql,(int(uid),)); return c.fetchall()


def _active_egg_cursor(c,uid:int,for_update:bool=False):
    # Compatibilidad con rutas antiguas: devuelve el huevo vivo más reciente.
    rows=_live_eggs_cursor(c,uid,for_update); return rows[-1] if rows else None


def _egg_by_id_cursor(c,egg_id:int,for_update:bool=False):
    sql=("SELECT egg_id,owner_id,source,egg_tier,species_id,progress,status,parent_a,parent_b,parent_a_species,parent_b_species,shiny,iv_atk,iv_def,iv_spd,iv_spc,pokemon_id,created_at "
         "FROM pokemon_eggs_tb WHERE egg_id=%s AND status IN ('active','hatching')")
    if for_update:sql += ' FOR UPDATE'
    c.execute(sql,(int(egg_id),)); return c.fetchone()


def _live_egg_count_cursor(c,uid:int)->int:
    c.execute("SELECT COUNT(*) FROM pokemon_eggs_tb WHERE owner_id=%s AND status IN ('active','hatching')",(int(uid),))
    return int((c.fetchone() or (0,))[0])


def _active_breeding_cursor(c,uid:int,for_update:bool=False):
    sql=("SELECT breeding_id,owner_id,parent_a,parent_b,parent_a_species,parent_b_species,species_id,egg_tier,shiny,iv_atk,iv_def,iv_spd,iv_spc,status,created_at,ready_at "
         "FROM pokemon_breedings_tb WHERE owner_id=%s AND status='waiting' ORDER BY breeding_id DESC LIMIT 1")
    if for_update:sql += ' FOR UPDATE'
    c.execute(sql,(int(uid),)); return c.fetchone()


def _egg_slots_used_cursor(c,uid:int)->int:
    # Una crianza pendiente reserva un espacio para que al cumplir el tiempo siempre pueda entregar su huevo.
    used=_live_egg_count_cursor(c,uid)
    if _active_breeding_cursor(c,uid):used += 1
    return used


def _breeding_wait_text(row)->str:
    if not row:return ''
    ready=row[15]
    now=datetime.now(timezone.utc)
    if getattr(ready,'tzinfo',None) is None:ready=ready.replace(tzinfo=timezone.utc)
    secs=max(0,int((ready-now).total_seconds()))
    if secs<=0:return '🥚 El huevo está por ser entregado...'
    mins=(secs+59)//60
    return f'⏳ Tiempo restante: {mins} min'


def _egg_media_cursor(c,key:str):
    c.execute("SELECT media_type,media_file_id FROM pokemon_egg_media_tb WHERE egg_key=%s",(str(key),)); r=c.fetchone()
    return (str(r[0]),str(r[1])) if r else (None,None)


def _egg_tier_label(tier:str)->str:
    d=EGG_TIERS.get(str(tier),EGG_TIERS['comun']); return f"{d['emoji']} {d['name']}"


def _egg_display_label(row)->str:
    if not row:return '🥚 Huevo Pokémon'
    source=str(row[2]); tier=str(row[3])
    if source.startswith('halloween'):return '🎃🥚 Huevo Maldito'
    return _egg_tier_label(tier)


def _egg_media_key_for_row(row)->str:
    if row and str(row[2]).startswith('halloween'):return 'cursed_egg'
    return str(row[3]) if row else 'comun'


def _egg_ready_markup(row):
    if not row:return None
    if int(row[5])>=EGG_PROGRESS_MAX and str(row[6])=='hatching':
        return InlineKeyboardMarkup([[InlineKeyboardButton('🥚 Romper huevo',callback_data=f'pk:egghatch:{int(row[0])}')]])
    return None


def _eggs_ready_markup(rows):
    buttons=[]
    for row in rows or []:
        if int(row[5])>=EGG_PROGRESS_MAX and str(row[6])=='hatching':
            buttons.append([InlineKeyboardButton(f'🥚 Romper huevo #{int(row[0])}',callback_data=f'pk:egghatch:{int(row[0])}')])
    return InlineKeyboardMarkup(buttons) if buttons else None


def _eggs_compact_text(rows)->str:
    if not rows:return '🥚 No tienes huevos activos.'
    parts=[f'🥚 HUEVOS ACTIVOS · {len(rows)}/{EGG_MAX_ACTIVE}']
    for i,row in enumerate(rows,1):
        parts.append(f"\n{i}. {_egg_display_label(row)} · #{int(row[0])}\n   📈 {_egg_progress_text(int(row[5]))}" + (' · ✨ LISTO' if str(row[6])=='hatching' else ''))
    return '\n'.join(parts)


def _egg_row_text(row, reveal:bool=False)->str:
    if not row:return '🥚 No tienes un huevo activo.'
    egg_id,_,source,tier,species,progress,status,*_=row
    lines=[f"{_egg_display_label(row)} · #{int(egg_id)}",'',f"📈 Progreso: {_egg_progress_text(int(progress))}"]
    if int(progress)<EGG_PROGRESS_MAX:
        lines.append('💬 Cada mensaje tuyo en el grupo suma +1.5%.')
    else:
        lines += ['', '✨ ¡El huevo está listo!', '🥚 Pulsa «Romper huevo» para comenzar la eclosión.']
    if source=='crianza':lines.append('💕 Origen: Crianza Pokémon')
    elif source=='evento':lines.append('🎉 Origen: Huevo encontrado en el evento diario')
    elif source=='regalo':lines.append('🎁 Origen: Regalo')
    elif source=='admin':lines.append('🎁 Origen: Regalo especial')
    elif str(source).startswith('halloween'):lines.append('🎃 Origen: Evento Halloween 2026')
    if reveal:lines.append(f"🔎 Contenido: #{int(species):03d} {NAMES[int(species)]}")
    else:lines.append('❓ El Pokémon de dentro seguirá siendo un misterio hasta eclosionar.')
    return '\n'.join(lines)


def _inherit_ivs(row_a,row_b)->dict:
    # Índices del selector completo: atk/def/spd/spc = 11/12/13/14.
    parents=[row_a,row_b]; inherited=set(random.sample(['atk','def','spd','spc'],2)); out={}
    idx={'atk':11,'def':12,'spd':13,'spc':14}
    for k in ('atk','def','spd','spc'):
        if k in inherited:
            pr=random.choice(parents); out[k]=int(pr[idx[k]] if pr[idx[k]] is not None else random.randint(0,15))
        else:out[k]=random.randint(0,15)
    out['hp']=((out['atk']&1)*8)+((out['def']&1)*4)+((out['spd']&1)*2)+(out['spc']&1)
    return out


def _egg_shiny_roll(parent_a=None,parent_b=None)->bool:
    count=sum(1 for r in (parent_a,parent_b) if r is not None and len(r)>10 and bool(r[10]))
    denom=4096 if count==0 else 2048 if count==1 else 1024
    return random.randrange(denom)==0


def _create_egg_cursor(c,uid:int,species:int,tier:str,source:str,parent_a=None,parent_b=None,parent_a_species=None,parent_b_species=None,ivs:dict|None=None,shiny:bool|None=None)->int:
    if _live_egg_count_cursor(c,uid)>=EGG_MAX_ACTIVE:raise ValueError('egg_slots_full')
    ivs=ivs or _roll_ivs(False); shiny=bool(_egg_shiny_roll() if shiny is None else shiny)
    c.execute("""INSERT INTO pokemon_eggs_tb(owner_id,source,egg_tier,species_id,parent_a,parent_b,parent_a_species,parent_b_species,shiny,iv_atk,iv_def,iv_spd,iv_spc)
                 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING egg_id""",
              (uid,source,tier,int(species),parent_a,parent_b,parent_a_species,parent_b_species,shiny,ivs['atk'],ivs['def'],ivs['spd'],ivs['spc']))
    return int(c.fetchone()[0])


def _breed_first_markup(uid:int,page:int=0):
    mons=_get_owned(uid); valid=[r for r in mons if _breedable_species(int(r[1])) and (len(r)>17 and str(r[17]) in ('M','F','N'))]
    per=8; pages=max(1,math.ceil(len(valid)/per)); page=max(0,min(int(page),pages-1)); chunk=valid[page*per:(page+1)*per]
    rows=[]
    for r in chunk:
        rows.append([InlineKeyboardButton(f"{_sex_symbol(r[17])} {r[2] or NAMES[int(r[1])]} · Nv.{int(r[3])}",callback_data=f'pk:breed1:{int(uid)}:{int(r[0])}:{page}')])
    nav=[]
    if page>0:nav.append(InlineKeyboardButton('⬅️',callback_data=f'pk:breedpage:{int(uid)}:{page-1}'))
    nav.append(InlineKeyboardButton(f'{page+1}/{pages}',callback_data='pk:noop'))
    if page<pages-1:nav.append(InlineKeyboardButton('➡️',callback_data=f'pk:breedpage:{int(uid)}:{page+1}'))
    if nav:rows.append(nav)
    return InlineKeyboardMarkup(rows) if rows else None


def _breed_second_markup(uid:int,first_pid:int):
    first=_get_instance(uid,first_pid)
    if not first:return None
    rows=[]
    for r in _get_owned(uid):
        if int(r[0])==int(first_pid):continue
        if len(r)<=17:continue
        if _breeding_compatible(int(first[1]),str(first[17]),int(r[1]),str(r[17])):
            rows.append([InlineKeyboardButton(f"{_sex_symbol(r[17])} {r[2] or NAMES[int(r[1])]} · Nv.{int(r[3])}",callback_data=f'pk:breed2:{int(uid)}:{int(first_pid)}:{int(r[0])}')])
            if len(rows)>=20:break
    return InlineKeyboardMarkup(rows) if rows else None


async def crianzapokemon_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection(); eggs=[]; pending=None; used=0
    try:
        c=conn.cursor(); eggs=_live_eggs_cursor(c,uid); pending=_active_breeding_cursor(c,uid); used=_egg_slots_used_cursor(c,uid)
    finally:_put_connection(conn)
    if pending:
        text=(f"💕 CRIANZA POKÉMON · {update.effective_user.full_name}\n\n🏡 Ya tienes una pareja en la Guardería.\n"
              f"{_breeding_wait_text(pending)}\n\nCuando produzcan el huevo, PiBot te avisará por privado.\n\n{_eggs_compact_text(eggs)}")
        return await update.effective_message.reply_text(text,reply_markup=_eggs_ready_markup(eggs))
    if used>=EGG_MAX_ACTIVE:
        return await update.effective_message.reply_text(f'🥚 Ya tienes ocupados tus {EGG_MAX_ACTIVE} espacios de huevo. Eclosiona o regala uno antes de criar de nuevo.',reply_markup=_eggs_ready_markup(eggs))
    kb=_breed_first_markup(uid,0)
    text=(f"💕 CRIANZA POKÉMON · {update.effective_user.full_name}\n\nElige el primer Pokémon. PiBot respetará sexo y Grupos Huevo. Ditto tiene su compatibilidad especial.\n"
          f"💰 Crianza: {BREEDING_COST_PIPESOS:,} PiPesos.\n⏳ La pareja tarda 30 minutos en producir el huevo.\n🥚 Espacios: {len(eggs)}/{EGG_MAX_ACTIVE}.")
    if kb is None:text += '\n\n⚠️ No tienes Pokémon aptos para iniciar una crianza.'
    return await update.effective_message.reply_text(text,reply_markup=kb)


async def guarderiapokemon_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection(); eggs=[]; pending=None
    try:
        c=conn.cursor(); eggs=_live_eggs_cursor(c,uid); pending=_active_breeding_cursor(c,uid)
    finally:_put_connection(conn)
    lines=[f'🏡 GUARDERÍA POKÉMON · {update.effective_user.full_name}']
    if pending:
        lines += ['', '💕 Pareja criando actualmente', f'• #{int(pending[4]):03d} {NAMES[int(pending[4])]} + #{int(pending[5]):03d} {NAMES[int(pending[5])]}', _breeding_wait_text(pending), '📩 Te avisaré por privado cuando tengan el huevo.']
    else:
        lines += ['', '💕 No tienes una pareja criando ahora mismo.']
    lines += ['', _eggs_compact_text(eggs)]
    return await update.effective_message.reply_text('\n'.join(lines),reply_markup=_eggs_ready_markup(eggs))


async def huevos_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection(); rows=[]
    try:c=conn.cursor(); rows=_live_eggs_cursor(c,uid)
    finally:_put_connection(conn)
    try:
        if not rows:
            await context.bot.send_message(uid,f'🥚 TUS HUEVOS · 0/{EGG_MAX_ACTIVE}\n\nNo tienes huevos activos.')
        else:
            await context.bot.send_message(uid,f'🥚 TUS HUEVOS · {len(rows)}/{EGG_MAX_ACTIVE}')
            for row in rows:
                conn=_get_connection(); media=(None,None)
                try:
                    c=conn.cursor(); key=_egg_media_key_for_row(row); media=_halloween_media_cursor(c,key) if key=='cursed_egg' else _egg_media_cursor(c,key)
                finally:_put_connection(conn)
                text=_egg_row_text(row); markup=_egg_ready_markup(row)
                if media[0]=='animation' and media[1]:await context.bot.send_animation(uid,animation=media[1],caption=text,reply_markup=markup)
                elif media[0]=='photo' and media[1]:await context.bot.send_photo(uid,photo=media[1],caption=text,reply_markup=markup)
                else:await context.bot.send_message(uid,text,reply_markup=markup)
    except Exception:return await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')
    if update.effective_chat.type!='private':await update.effective_message.reply_text('📩 Te mandé tus huevos por privado.')


async def regalarhuevo_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; target=_resolve_target(update,context)
    if target is None:return await update.effective_message.reply_text('🎁 Responde al mensaje de la persona con /regalarhuevo.')
    if int(target)==int(uid):return await update.effective_message.reply_text('😂 No puedes regalarte tu propio huevo.')
    conn=_get_connection(); eggs=[]; name=None; target_used=0
    try:
        c=conn.cursor(); eggs=_live_eggs_cursor(c,uid); target_used=_egg_slots_used_cursor(c,target); name=_display_name_cursor(c,target)
    finally:_put_connection(conn)
    if not eggs:return await update.effective_message.reply_text('🥚 No tienes huevos activos para regalar.')
    if target_used>=EGG_MAX_ACTIVE:return await update.effective_message.reply_text(f'🥚 {name} ya tiene ocupados sus {EGG_MAX_ACTIVE} espacios de huevo.')
    rows=[]
    for egg in eggs:
        pct=int(egg[5])/100
        rows.append([InlineKeyboardButton(f'{_egg_display_label(egg)} #{int(egg[0])} · {pct:.1f}%',callback_data=f'pk:egggiftpick:{uid}:{int(target)}:{int(egg[0])}')])
    rows.append([InlineKeyboardButton('❌ Cancelar',callback_data='pk:egggiftcancel')])
    await update.effective_message.reply_text(f'🎁 ¿Cuál de tus huevos quieres regalar a {name}?',reply_markup=InlineKeyboardMarkup(rows))


async def darhuevo_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    try:
        if not is_botmaster(update.effective_user.id):return await update.effective_message.reply_text('Solo BotMaster puede dar huevos especiales.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede dar huevos especiales.')
    target=_resolve_target(update,context)
    if target is None:return await update.effective_message.reply_text('Responde al mensaje de alguien con /darhuevo [comun|raro|epico|halloween].')
    raw=(context.args[0].lower() if context.args else 'comun')
    cursed=raw in ('halloween','maldito','maldita')
    tier=raw if raw in EGG_TIERS else 'comun'
    conn=_get_connection(); eid=None; name=None
    try:
        c=conn.cursor(); name=_display_name_cursor(c,target)
        if _egg_slots_used_cursor(c,target)>=EGG_MAX_ACTIVE:conn.rollback(); return await update.effective_message.reply_text(f'🥚 {name} ya tiene ocupados sus {EGG_MAX_ACTIVE} espacios de huevo.')
        if cursed:
            eid=_create_cursed_egg_cursor(c,target,'halloween_admin')
        else:
            species=_roll_gift_egg_species(tier); eid=_create_egg_cursor(c,target,species,tier,'admin')
        conn.commit()
    except Exception as e:conn.rollback(); print('[PK give egg]',type(e).__name__,e); return await update.effective_message.reply_text('No pude entregar el huevo.')
    finally:_put_connection(conn)
    label='🎃🥚 Huevo Maldito' if cursed else _egg_tier_label(tier)
    await update.effective_message.reply_text(f'🎁 {name} recibió {label} #{eid}. El Pokémon interior es secreto hasta eclosionar.')


def _egg_media_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🥚 Huevo Común',callback_data='pk:eggmediapick:comun'),InlineKeyboardButton('🔵 Huevo Raro',callback_data='pk:eggmediapick:raro')],
        [InlineKeyboardButton('🟣 Huevo Épico',callback_data='pk:eggmediapick:epico')],
        [InlineKeyboardButton('💥 Animación eclosión',callback_data='pk:eggmediapick:hatching')],
    ])


async def imageneshuevo_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    try:
        if not is_botmaster(uid):return await update.effective_message.reply_text('Solo BotMaster puede configurar imágenes de huevos.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede configurar imágenes de huevos.')
    try:
        await context.bot.send_message(uid,'🥚 MULTIMEDIA DE HUEVOS\n\nElige qué imagen/GIF quieres configurar. “Animación eclosión” es el GIF que se muestra justo antes de revelar el Pokémon.',reply_markup=_egg_media_markup())
        if update.effective_chat.type!='private':await update.effective_message.reply_text('📩 Te mandé el panel de huevos por privado.')
    except Exception:await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')


async def _send_egg_event_message(context,event_id:int)->bool:
    conn=_get_connection(); row=None; media=(None,None)
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,egg_tier,status FROM pokemon_egg_events_tb WHERE event_id=%s",(event_id,)); row=c.fetchone()
        if row:media=_egg_media_cursor(c,str(row[2]))
    finally:_put_connection(conn)
    if not row or row[3]!='active':return False
    chat_id,thread0,tier=int(row[0]),int(row[1]),str(row[2]); thread_id=None if thread0==0 else thread0
    text=(f"🥚 ¡OH! ¡HAS ENCONTRADO UN HUEVO!\n\n{_egg_tier_label(tier)} apareció en el camino.\n"
          "❓ Nadie sabe qué Pokémon hay dentro.\n🚫 Los huevos diarios nunca contienen legendarios.\n"
          "💬 Cuando alguien lo recoja, sus propios mensajes harán subir el porcentaje hasta 100%.\n\n⏳ El primero que pueda recogerlo se lo queda. Dura 1 hora.")
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('🥚 Recoger huevo',callback_data=f'pk:eggclaim:{event_id}')]])
    try:
        mt,fid=media
        if mt=='animation' and fid:msg=await context.bot.send_animation(chat_id=chat_id,animation=fid,caption=text,message_thread_id=thread_id,reply_markup=kb)
        elif mt=='photo' and fid:msg=await context.bot.send_photo(chat_id=chat_id,photo=fid,caption=text,message_thread_id=thread_id,reply_markup=kb)
        else:msg=await context.bot.send_message(chat_id=chat_id,text=text,message_thread_id=thread_id,reply_markup=kb)
    except Exception as e:
        print('[PK egg event send]',type(e).__name__,e)
        conn=_get_connection()
        try:c=conn.cursor(); c.execute("DELETE FROM pokemon_egg_events_tb WHERE event_id=%s AND status='active'",(event_id,)); conn.commit()
        except Exception:conn.rollback()
        finally:_put_connection(conn)
        return False
    conn=_get_connection()
    try:c=conn.cursor(); c.execute("UPDATE pokemon_egg_events_tb SET message_id=%s WHERE event_id=%s",(msg.message_id,event_id)); conn.commit()
    except Exception:conn.rollback()
    finally:_put_connection(conn)
    try:
        if context.job_queue:context.job_queue.run_once(_expire_egg_event,EGG_EVENT_LIFETIME_SECONDS,data={'event_id':event_id},name=f'pk_egg_expire:{event_id}')
    except Exception:pass
    return True


async def _spawn_daily_egg_event(context:ContextTypes.DEFAULT_TYPE,chat_id:int,thread_id:int|None,manual:bool=False)->bool:
    conn=_get_connection(); eid=None
    try:
        c=conn.cursor(); today=datetime.now(POKEMON_TZ).date(); t0=int(thread_id or 0)
        if not manual:
            c.execute("SELECT event_id FROM pokemon_egg_events_tb WHERE chat_id=%s AND thread_id=%s AND event_date=%s",(chat_id,t0,today))
            if c.fetchone():conn.rollback(); return False
        else:
            # Los forzados usan una fecha virtual negativa mediante borrado del bloqueo diario activo del mismo día.
            c.execute("UPDATE pokemon_egg_events_tb SET status='expired',finished_at=NOW() WHERE chat_id=%s AND thread_id=%s AND status='active'",(chat_id,t0))
            c.execute("DELETE FROM pokemon_egg_events_tb WHERE chat_id=%s AND thread_id=%s AND event_date=%s",(chat_id,t0,today))
        tiers=list(EGG_EVENT_TIER_WEIGHTS); weights=list(EGG_EVENT_TIER_WEIGHTS.values()); tier=random.choices(tiers,weights=weights,k=1)[0]
        species=_roll_gift_egg_species(tier)
        c.execute("INSERT INTO pokemon_egg_events_tb(chat_id,thread_id,event_date,egg_tier,species_id) VALUES(%s,%s,%s,%s,%s) RETURNING event_id",(chat_id,t0,today,tier,species)); eid=int(c.fetchone()[0]); conn.commit()
    except Exception as e:conn.rollback(); print('[PK egg event db]',type(e).__name__,e); return False
    finally:_put_connection(conn)
    return await _send_egg_event_message(context,eid)


async def _expire_egg_event(context:ContextTypes.DEFAULT_TYPE):
    eid=int((getattr(context.job,'data',None) or {}).get('event_id') or 0); row=None; media=(None,None)
    if not eid:return
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,egg_tier,status,message_id FROM pokemon_egg_events_tb WHERE event_id=%s FOR UPDATE",(eid,)); row=c.fetchone()
        if not row or row[3]!='active':conn.rollback(); return
        media=_egg_media_cursor(c,str(row[2])); c.execute("UPDATE pokemon_egg_events_tb SET status='expired',finished_at=NOW() WHERE event_id=%s",(eid,)); conn.commit()
    except Exception:conn.rollback(); return
    finally:_put_connection(conn)
    text=f"⌛ Nadie recogió {_egg_tier_label(str(row[2]))}. El huevo desapareció."
    try:
        if media[0] in ('photo','animation'):await context.bot.edit_message_caption(chat_id=int(row[0]),message_id=int(row[4]),caption=text,reply_markup=None)
        else:await context.bot.edit_message_text(chat_id=int(row[0]),message_id=int(row[4]),text=text,reply_markup=None)
    except Exception:pass


async def pokemon_egg_event_job(context:ContextTypes.DEFAULT_TYPE):
    for community in COMUNIDADES:
        try:
            chat_id=int(community.get('id_comunidad')); thread_id=_games_topic(chat_id)
            if thread_id is not None:await _spawn_daily_egg_event(context,chat_id,thread_id,False)
        except Exception as e:print('[PK egg daily]',type(e).__name__,e)


async def huevoahora_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    try:
        if not is_botmaster(update.effective_user.id):return await update.effective_message.reply_text('Solo BotMaster puede forzar el evento de huevo.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede forzar el evento de huevo.')
    if not _is_games_topic(update):return await update.effective_message.reply_text('Usa /huevoahora en Juegos y Casino.')
    ok=await _spawn_daily_egg_event(context,update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),True)
    if not ok:await update.effective_message.reply_text('No pude crear el evento de huevo.')


async def _send_hatch_media(context:ContextTypes.DEFAULT_TYPE,chat_id:int,thread_id:int|None,source:str,caption:str):
    conn=_get_connection(); media=(None,None)
    try:
        c=conn.cursor()
        media=_halloween_media_cursor(c,'cursed_hatch') if str(source).startswith('halloween') else _egg_media_cursor(c,'hatching')
    finally:_put_connection(conn)
    if media[0]=='animation' and media[1]:
        return await context.bot.send_animation(chat_id=chat_id,animation=media[1],caption=caption,message_thread_id=thread_id)
    if media[0]=='photo' and media[1]:
        return await context.bot.send_photo(chat_id=chat_id,photo=media[1],caption=caption,message_thread_id=thread_id)
    return await context.bot.send_message(chat_id=chat_id,text=caption,message_thread_id=thread_id)


async def _hatch_egg(context:ContextTypes.DEFAULT_TYPE,egg_id:int,chat_id:int,thread_id:int|None,display_name:str):
    # La concesión se confirma en BD antes de la animación para que un doble toque nunca duplique la cría.
    conn=_get_connection(); result=None; source=''; uid=None
    try:
        c=conn.cursor(); c.execute("SELECT owner_id,source,egg_tier,species_id,status,progress,shiny,iv_atk,iv_def,iv_spd,iv_spc FROM pokemon_eggs_tb WHERE egg_id=%s FOR UPDATE",(egg_id,)); r=c.fetchone()
        if not r or str(r[4])!='hatching' or int(r[5])<EGG_PROGRESS_MAX:conn.rollback(); return None
        uid,source,species=int(r[0]),str(r[1]),int(r[3]); shiny=bool(r[6]); ivs={'atk':int(r[7]),'def':int(r[8]),'spd':int(r[9]),'spc':int(r[10])}; ivs['hp']=((ivs['atk']&1)*8)+((ivs['def']&1)*4)+((ivs['spd']&1)*2)+(ivs['spc']&1)
        result=grant_pokemon_with_cursor(c,uid,species,source='huevo_'+source,level_override=1,shiny_override=shiny,ivs_override=ivs)
        c.execute("UPDATE pokemon_eggs_tb SET status='hatched',pokemon_id=%s,progress=10000,hatched_at=NOW() WHERE egg_id=%s",(int(result['pokemon_id']),egg_id)); conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK egg hatch]',type(e).__name__,e); return None
    finally:_put_connection(conn)

    pre=(f"🥚 ¡EL HUEVO DE {display_name} ESTÁ REACCIONANDO!\n\n"
         "✨ El huevo empieza a moverse...\n💥 crack... crack...")
    try:await _send_hatch_media(context,chat_id,thread_id,source,pre)
    except Exception:pass
    await asyncio.sleep(2.8)
    sex=_sex_symbol(result.get('sex')); shiny_line='✨ ¡SHINY!\n' if result.get('shiny') else ''
    text=(f"🎉 ¡HA NACIDO UN POKÉMON!\n\n{shiny_line}{rarity_emoji(rarity_for(result['species_id']))} #{result['species_id']:03d} {result['name']} {sex} · Nv.1\n"
          f"{_types_text(result['species_id'])}\n🧬 IV: {result['iv_percent']}% · {result['iv_grade']}\n🎮 Ejemplar #{result['pokemon_id']}")
    try:await context.bot.send_message(chat_id=chat_id,text=text,message_thread_id=thread_id)
    except Exception:pass
    if uid is not None and int(chat_id)!=int(uid):
        try:await context.bot.send_message(int(uid),text)
        except Exception:pass
    return result


async def pokemon_egg_activity(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or update.effective_user.is_bot or not update.effective_message:return
    if update.effective_chat.type=='private':return
    if update.effective_message.text and update.effective_message.text.lstrip().startswith('/'):return
    uid=int(update.effective_user.id); reached_ids=[]; reached_rows=[]
    conn=_get_connection()
    try:
        c=conn.cursor(); rows=_live_eggs_cursor(c,uid,True)
        active=[r for r in rows if str(r[6])=='active']
        if not active:conn.rollback(); return
        for row in active:
            egg_id=int(row[0]); newp=min(EGG_PROGRESS_MAX,int(row[5])+EGG_PROGRESS_PER_MESSAGE)
            if newp>=EGG_PROGRESS_MAX:
                c.execute("UPDATE pokemon_eggs_tb SET progress=10000,status='hatching' WHERE egg_id=%s",(egg_id,)); reached_ids.append(egg_id)
            else:
                c.execute("UPDATE pokemon_eggs_tb SET progress=%s WHERE egg_id=%s",(newp,egg_id))
        conn.commit()
        if reached_ids:
            c=conn.cursor()
            for egg_id in reached_ids:
                row=_egg_by_id_cursor(c,egg_id)
                if row:reached_rows.append(row)
    except Exception as e:conn.rollback(); print('[PK egg progress]',type(e).__name__,e); return
    finally:_put_connection(conn)
    if reached_rows:
        name=(update.effective_user.full_name or update.effective_user.first_name or update.effective_user.username or f'Entrenador {uid}').strip()
        for row in reached_rows:
            text=(f"🥚 ¡UN HUEVO DE {name} ESTÁ LISTO!\n\n"
                  f"{_egg_display_label(row)} #{int(row[0])} llegó al 100%.\n✨ Ya puede comenzar la eclosión.")
            kb=_egg_ready_markup(row)
            try:await context.bot.send_message(update.effective_chat.id,text,message_thread_id=getattr(update.effective_message,'message_thread_id',None),reply_markup=kb)
            except Exception:pass
            try:await context.bot.send_message(uid,f'🥚 ¡Tu {_egg_display_label(row)} #{int(row[0])} llegó al 100%!\n\nPulsa el botón cuando quieras romperlo.',reply_markup=kb)
            except Exception:pass


async def pokemon_breeding_ready_job(context:ContextTypes.DEFAULT_TYPE):
    # Revisa parejas cada minuto. El estado vive en PostgreSQL, así que reiniciar Render no pierde el tiempo.
    conn=_get_connection(); notifications=[]
    try:
        c=conn.cursor()
        c.execute("""SELECT breeding_id,owner_id,parent_a,parent_b,parent_a_species,parent_b_species,species_id,egg_tier,shiny,iv_atk,iv_def,iv_spd,iv_spc,status,created_at,ready_at
                     FROM pokemon_breedings_tb WHERE status='waiting' AND ready_at<=NOW() ORDER BY ready_at ASC LIMIT 50 FOR UPDATE SKIP LOCKED""")
        rows=c.fetchall()
        for br in rows:
            bid,uid,a,b,sa,sb,species,tier,shiny,ia,idf,ispd,ispc,*_=br
            if _live_egg_count_cursor(c,int(uid))>=EGG_MAX_ACTIVE:
                # Debería ser raro porque la crianza reserva espacio; se conserva para reintentar sin perder el huevo.
                continue
            ivs={'atk':int(ia),'def':int(idf),'spd':int(ispd),'spc':int(ispc)}
            ivs['hp']=((ivs['atk']&1)*8)+((ivs['def']&1)*4)+((ivs['spd']&1)*2)+(ivs['spc']&1)
            eid=_create_egg_cursor(c,int(uid),int(species),str(tier),'crianza',int(a),int(b),int(sa),int(sb),ivs,bool(shiny))
            c.execute("UPDATE pokemon_breedings_tb SET status='completed',finished_at=NOW() WHERE breeding_id=%s",(int(bid),))
            notifications.append((int(uid),int(eid),str(tier)))
        conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK breeding ready]',type(e).__name__,e)
    finally:_put_connection(conn)
    for uid,eid,tier in notifications:
        try:
            await context.bot.send_message(uid,f"🏡 ¡TU PAREJA POKÉMON TUVO UN HUEVO! 🥚\n\n{_egg_tier_label(tier)} #{eid} ya está contigo.\n💬 Cada mensaje válido tuyo en el grupo hará subir +1.5% a todos tus huevos activos.\n🥚 Puedes tener hasta {EGG_MAX_ACTIVE} huevos.\n\nUsa /huevos para verlos.")
        except Exception:
            pass


# ==================== EVENTO HALLOWEEN 2026 ====================
def _halloween_now()->datetime:
    return datetime.now(POKEMON_TZ)


def _halloween_active(now:datetime|None=None)->bool:
    now=now or _halloween_now()
    return HALLOWEEN_START <= now <= HALLOWEEN_END


def _halloween_countdown_text(now:datetime|None=None)->str:
    now=now or _halloween_now()
    if now>HALLOWEEN_END:return 'Evento terminado'
    if now<HALLOWEEN_START:
        delta=HALLOWEEN_START-now; prefix='Comienza en'
    else:
        delta=HALLOWEEN_END-now; prefix='Termina en'
    total=max(0,int(delta.total_seconds())); days,h=divmod(total,86400); hours,m=divmod(h,3600); mins=m//60
    return f'{prefix}: {days} días · {hours} h · {mins} min'


def _halloween_media_cursor(c,key:str):
    c.execute("SELECT media_type,media_file_id FROM pokemon_halloween_media_tb WHERE media_key=%s",(str(key),)); r=c.fetchone()
    return (str(r[0]),str(r[1])) if r else (None,None)


def _halloween_wallet_cursor(c,uid:int,lock:bool=False)->int:
    c.execute("INSERT INTO pokemon_halloween_wallet_tb(user_id) VALUES(%s) ON CONFLICT DO NOTHING",(int(uid),))
    c.execute("SELECT candies FROM pokemon_halloween_wallet_tb WHERE user_id=%s"+(' FOR UPDATE' if lock else ''),(int(uid),)); r=c.fetchone()
    return int(r[0]) if r else 0


def _halloween_add_candies_cursor(c,uid:int,amount:int)->int:
    amount=max(0,int(amount)); _halloween_wallet_cursor(c,uid,True)
    if amount:
        c.execute("UPDATE pokemon_halloween_wallet_tb SET candies=candies+%s,earned_total=earned_total+%s,updated_at=NOW() WHERE user_id=%s",(amount,amount,int(uid)))
    c.execute("SELECT candies FROM pokemon_halloween_wallet_tb WHERE user_id=%s",(int(uid),)); return int(c.fetchone()[0])


def _halloween_spend_cursor(c,uid:int,amount:int)->bool:
    amount=max(0,int(amount)); bal=_halloween_wallet_cursor(c,uid,True)
    if bal<amount:return False
    c.execute("UPDATE pokemon_halloween_wallet_tb SET candies=candies-%s,spent_total=spent_total+%s,updated_at=NOW() WHERE user_id=%s",(amount,amount,int(uid)))
    return True


def _halloween_drop_amount(species:int)->int:
    if not _halloween_active():return 0
    r=rarity_for(int(species))
    lo,hi={'comun':(0,2),'raro':(1,3),'epico':(2,5),'legendario':(4,8)}.get(r,(0,2))
    amount=random.randint(lo,hi)
    if 'Ghost' in TYPES.get(int(species),()):
        amount += random.randint(2,4)  # los Fantasma siempre son la mejor fuente del evento
    return max(0,amount)


def _halloween_award_species_cursor(c,uid:int,species_ids)->int:
    if not _halloween_active():return 0
    total=sum(_halloween_drop_amount(int(s)) for s in species_ids if s)
    if total>0:_halloween_add_candies_cursor(c,uid,total)
    return total


def _halloween_themed_species()->int:
    # 70% temático; 30% cualquier familia Gen 1 no legendaria.
    if random.random()<0.70:return random.choice(HALLOWEEN_THEME_BASES)
    pool=sorted({int(BREED_BASE.get(i,i)) for i in range(1,152) if i not in set(LEGENDARY_IDS)})
    return random.choice(pool)


def _grant_halloween_box_cursor(c,uid:int)->dict:
    species=_halloween_themed_species(); shiny=(random.randrange(HALLOWEEN_BOX_SHINY_DENOMINATOR)==0)
    data=grant_pokemon_with_cursor(c,uid,species,'halloween_box_2026',shiny_override=shiny)
    return data


def _grant_halloween_pikachu_cursor(c,uid:int)->dict:
    shiny=(random.random()<HALLOWEEN_PIKACHU_SHINY_CHANCE)
    data=grant_pokemon_with_cursor(c,uid,25,'halloween_2026_pikachu',shiny_override=shiny)
    media=_halloween_media_cursor(c,'pikachu_shiny' if shiny else 'pikachu_normal')
    c.execute("UPDATE pokemon_instances_tb SET nickname=%s,media_type=COALESCE(%s,media_type),media_file_id=COALESCE(%s,media_file_id),updated_at=NOW() WHERE pokemon_id=%s AND owner_id=%s",
              ('Pikachu Halloween',media[0],media[1],int(data['pokemon_id']),int(uid)))
    data['special_name']='Pikachu Halloween'; return data


def _create_cursed_egg_cursor(c,uid:int,source:str='halloween_shop')->int:
    if _live_egg_count_cursor(c,uid)>=EGG_MAX_ACTIVE:raise ValueError('egg_slots_full')
    species=random.choice(HALLOWEEN_THEME_BASES)
    shiny=(random.randrange(HALLOWEEN_EGG_SHINY_DENOMINATOR)==0)
    return _create_egg_cursor(c,uid,species,'epico',source,shiny=shiny)


def _grant_normal_pibot_box_cursor(c,uid:int,code:str)->dict:
    # Reutiliza el mismo roll de las cajas normales; solo cambia la moneda de compra a Dulces Halloween.
    from handlers.pipeso_extras import _roll_box
    kind,val,label=_roll_box(code,uid); jackpot_win=0; jackpot_after=10000; gif_bonus=False
    c.execute("INSERT INTO box_jackpot_tb(jackpot_key,amount,purchases) VALUES('main',10000,0) ON CONFLICT DO NOTHING")
    c.execute("SELECT amount,purchases FROM box_jackpot_tb WHERE jackpot_key='main' FOR UPDATE"); jr=c.fetchone() or (10000,0)
    pot=int(jr[0])+10000; chance=0.0002 if code=='epic' else 0.0005
    if random.random()<chance:
        jackpot_win=pot; c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(jackpot_win,uid))
        c.execute("UPDATE box_jackpot_tb SET amount=10000,purchases=purchases+1,last_winner_id=%s,last_win_amount=%s,updated_at=NOW() WHERE jackpot_key='main'",(uid,jackpot_win)); jackpot_after=10000
    else:
        c.execute("UPDATE box_jackpot_tb SET amount=%s,purchases=purchases+1,updated_at=NOW() WHERE jackpot_key='main'",(pot,)); jackpot_after=pot
    if kind=='money':c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(int(val),uid))
    elif kind=='pokemon':
        pdata=grant_pokemon_with_cursor(c,uid,int(val),'caja_'+code); label += f" · ejemplar #{pdata['pokemon_id']} · Nv.{pdata['level']} · IV {pdata.get('iv_percent',0)}% {pdata.get('iv_grade','')}" + (' · ✨ SHINY' if pdata.get('shiny') else '')
    elif kind=='pokeitem':grant_item_with_cursor(c,uid,val,1)
    elif kind=='title':
        asset_code='box_'+''.join(ch.lower() if ch.isalnum() else '_' for ch in val).strip('_')
        c.execute("SELECT 1 FROM social_assets_tb WHERE propietario_id=%s AND asset_type='titulo' AND code=%s LIMIT 1",(uid,asset_code))
        if c.fetchone():c.execute("UPDATE usuarios_tb SET saldo=saldo+2000 WHERE id_user=%s",(uid,)); label+=' · repetido → +2,000 PiPesos'
        else:c.execute("INSERT INTO social_assets_tb(asset_type,code,nombre,rareza,valor_base,propietario_id,origen) VALUES('titulo',%s,%s,'caja',0,%s,'caja_misteriosa')",(asset_code,val,uid))
    elif kind=='cosmetic':
        from handlers.profile_cosmetics import COSMETICS
        item=COSMETICS.get(val)
        if not item:c.execute("UPDATE usuarios_tb SET saldo=saldo+2000 WHERE id_user=%s",(uid,)); label+=' · premio sustituido → +2,000 PiPesos'
        else:
            cname,ctype,crarity,cprice,cseason=item; c.execute("SELECT 1 FROM profile_cosmetics_tb WHERE owner_id=%s AND code=%s LIMIT 1",(uid,val))
            if c.fetchone():c.execute("UPDATE usuarios_tb SET saldo=saldo+2000 WHERE id_user=%s",(uid,)); label+=' · repetido → +2,000 PiPesos'
            else:c.execute("INSERT INTO profile_cosmetics_tb(code,nombre,cosmetic_type,rareza,precio_compra,owner_id,season_key) VALUES(%s,%s,%s,%s,0,%s,%s)",(val,cname,ctype,crarity,uid,cseason))
    else:
        c.execute("INSERT INTO user_box_assets_tb(user_id,asset_type,asset_code,asset_name) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",(uid,kind,val,label))
        if c.rowcount==0:c.execute("UPDATE usuarios_tb SET saldo=saldo+2000 WHERE id_user=%s",(uid,)); label+=' · repetido → +2,000 PiPesos'
    gif_chance=0.002 if code=='epic' else 0.008
    if random.random()<gif_chance:
        gif_bonus=True; c.execute("""INSERT INTO profile_gif_license_tb(user_id,expires_at) VALUES(%s,NOW()+INTERVAL '10 days')
            ON CONFLICT(user_id) DO UPDATE SET expires_at=CASE WHEN profile_gif_license_tb.expires_at IS NOT NULL AND profile_gif_license_tb.expires_at>NOW()
            THEN profile_gif_license_tb.expires_at+INTERVAL '10 days' ELSE NOW()+INTERVAL '10 days' END,updated_at=NOW()""",(uid,))
    return {'label':label,'jackpot_win':jackpot_win,'jackpot_after':jackpot_after,'gif_bonus':gif_bonus,'code':code}


def _halloween_home_markup(uid:int):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🛒 Tienda',callback_data=f'pk:eventshop:{int(uid)}'),InlineKeyboardButton('🎁 Recompensas',callback_data=f'pk:eventrewards:{int(uid)}')],
        [InlineKeyboardButton('🥚 Mi huevo',callback_data=f'pk:eventegg:{int(uid)}'),InlineKeyboardButton('ℹ️ Cómo funciona',callback_data=f'pk:eventinfo:{int(uid)}')],
    ])


def _halloween_shop_markup(uid:int):
    rows=[]
    for code,item in HALLOWEEN_SHOP.items():
        rows.append([InlineKeyboardButton(f"{item['emoji']} {item['name']} · {item['price']} 🍬",callback_data=f'pk:eventbuy:{int(uid)}:{code}')])
    rows.append([InlineKeyboardButton('⬅️ Evento',callback_data=f'pk:eventhome:{int(uid)}')]); return InlineKeyboardMarkup(rows)


def _halloween_media_markup():
    rows=[]; keys=list(HALLOWEEN_MEDIA_KEYS)
    for i in range(0,len(keys),2):rows.append([InlineKeyboardButton(HALLOWEEN_MEDIA_KEYS[k],callback_data=f'pk:eventmediapick:{k}') for k in keys[i:i+2]])
    return InlineKeyboardMarkup(rows)


async def _send_event_home(context:ContextTypes.DEFAULT_TYPE,uid:int,chat_id:int,thread_id:int|None=None):
    conn=_get_connection(); candies=0; media=(None,None); owner_name=f'Entrenador {uid}'
    try:
        c=conn.cursor(); candies=_halloween_wallet_cursor(c,uid); media=_halloween_media_cursor(c,'cover'); owner_name=_display_name_cursor(c,uid)
    finally:_put_connection(conn)
    active=_halloween_active(); status=_halloween_countdown_text()
    text=(f"🎃 EVENTO HALLOWEEN 2026 · {owner_name}\n\n🍬 Tus Dulces Halloween: {candies}\n👻 Los Pokémon Fantasma sueltan más dulces.\n"
          f"✨ Caja Pokémon Halloween: Shiny 1/{HALLOWEEN_BOX_SHINY_DENOMINATOR}.\n🎃⚡ Pikachu Halloween: exclusivo de la tienda · 80% normal · 20% Shiny.\n\n⏳ {status}")
    if not active:text += '\n\n🔒 La tienda y los drops del evento ya están cerrados. Lo que ganaste sigue siendo tuyo.'
    markup=_halloween_home_markup(uid)
    kwargs={'reply_markup':markup}
    if thread_id:kwargs['message_thread_id']=thread_id
    if media[0]=='animation' and media[1]:return await context.bot.send_animation(chat_id,animation=media[1],caption=text,**kwargs)
    if media[0]=='photo' and media[1]:return await context.bot.send_photo(chat_id,photo=media[1],caption=text,**kwargs)
    return await context.bot.send_message(chat_id,text,**kwargs)


async def evento_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; chat_id=update.effective_chat.id; thread_id=getattr(update.effective_message,'message_thread_id',None)
    return await _send_event_home(context,uid,chat_id,thread_id)


async def imagenesevento_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    try:
        if not is_botmaster(uid):return await update.effective_message.reply_text('Solo BotMaster puede configurar imágenes del evento.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede configurar imágenes del evento.')
    try:
        await context.bot.send_message(uid,'🎃 MULTIMEDIA HALLOWEEN 2026\n\nElige qué elemento quieres configurar y luego envíame una foto o GIF.',reply_markup=_halloween_media_markup())
        if update.effective_chat.type!='private':await update.effective_message.reply_text('📩 Te mandé el panel de Halloween por privado.')
    except Exception:await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')


async def _send_halloween_surprise(context:ContextTypes.DEFAULT_TYPE,event_id:int)->bool:
    conn=_get_connection(); row=None; media=(None,None)
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,event_kind,status FROM pokemon_halloween_events_tb WHERE event_id=%s",(event_id,)); row=c.fetchone(); media=_halloween_media_cursor(c,'surprise') if row else (None,None)
    finally:_put_connection(conn)
    if not row or str(row[3])!='active':return False
    chat_id,thread_id=int(row[0]),int(row[1] or 0)
    text=('🍬 ¡OH! ¡APARECIERON DULCES DE HALLOWEEN!\n\n'
          '🎃 Alguien los dejó tirados en Juegos y Casino...\n'
          '👀 El primero en recogerlos se los queda.\n\n⏳ Desaparecerán en 30 minutos.')
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('🍬 Recoger dulces',callback_data=f'pk:eventclaim:{event_id}')]])
    try:
        if media[0]=='animation' and media[1]:msg=await context.bot.send_animation(chat_id,animation=media[1],caption=text,message_thread_id=thread_id or None,reply_markup=kb)
        elif media[0]=='photo' and media[1]:msg=await context.bot.send_photo(chat_id,photo=media[1],caption=text,message_thread_id=thread_id or None,reply_markup=kb)
        else:msg=await context.bot.send_message(chat_id,text,message_thread_id=thread_id or None,reply_markup=kb)
    except Exception as e:print('[PK Halloween surprise send]',type(e).__name__,e); return False
    conn=_get_connection()
    try:c=conn.cursor(); c.execute("UPDATE pokemon_halloween_events_tb SET message_id=%s WHERE event_id=%s",(msg.message_id,event_id)); conn.commit()
    except Exception:conn.rollback()
    finally:_put_connection(conn)
    if context.job_queue:context.job_queue.run_once(_expire_halloween_surprise,HALLOWEEN_EVENT_LIFETIME_SECONDS,data={'event_id':event_id},name=f'pk_halloween_expire:{event_id}')
    return True


async def _spawn_halloween_surprise(context:ContextTypes.DEFAULT_TYPE,chat_id:int,thread_id:int|None,forced_kind:str|None=None,manual:bool=False)->bool:
    if not manual and not _halloween_active():return False
    # Las apariciones automáticas de Halloween son exclusivamente de Dulces Halloween.
    # Huevos, cajas, NPC/jefe y Pikachu conservan sus rutas separadas; Pikachu es exclusivo de tienda.
    kind='candy'
    conn=_get_connection(); eid=None
    try:
        c=conn.cursor(); t0=int(thread_id or 0)
        if not manual:
            c.execute("SELECT 1 FROM pokemon_halloween_events_tb WHERE chat_id=%s AND thread_id=%s AND created_at>NOW()-INTERVAL '90 minutes' AND status='active' LIMIT 1",(chat_id,t0))
            if c.fetchone():conn.rollback(); return False
        c.execute("INSERT INTO pokemon_halloween_events_tb(chat_id,thread_id,event_kind) VALUES(%s,%s,%s) RETURNING event_id",(chat_id,t0,kind)); eid=int(c.fetchone()[0]); conn.commit()
    except Exception as e:conn.rollback(); print('[PK Halloween surprise db]',type(e).__name__,e); return False
    finally:_put_connection(conn)
    return await _send_halloween_surprise(context,eid)


async def _expire_halloween_surprise(context:ContextTypes.DEFAULT_TYPE):
    eid=int((getattr(context.job,'data',None) or {}).get('event_id') or 0); row=None
    if not eid:return
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,status,message_id FROM pokemon_halloween_events_tb WHERE event_id=%s FOR UPDATE",(eid,)); row=c.fetchone()
        if not row or str(row[2])!='active':conn.rollback(); return
        c.execute("UPDATE pokemon_halloween_events_tb SET status='expired',finished_at=NOW() WHERE event_id=%s",(eid,)); conn.commit()
    except Exception:conn.rollback(); return
    finally:_put_connection(conn)
    try:
        await context.bot.edit_message_caption(chat_id=int(row[0]),message_id=int(row[3]),caption='🍬 Los Dulces Halloween desaparecieron antes de que alguien los recogiera.',reply_markup=None)
    except Exception:
        try:await context.bot.edit_message_text(chat_id=int(row[0]),message_id=int(row[3]),text='🍬 Los Dulces Halloween desaparecieron antes de que alguien los recogiera.',reply_markup=None)
        except Exception:pass


async def pokemon_halloween_event_job(context:ContextTypes.DEFAULT_TYPE):
    if not _halloween_active():return
    for community in COMUNIDADES:
        try:
            chat_id=int(community.get('id_comunidad')); thread_id=_games_topic(chat_id)
            if thread_id is not None:await _spawn_halloween_surprise(context,chat_id,thread_id)
        except Exception as e:print('[PK Halloween job]',type(e).__name__,e)


async def halloweenahora_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    try:
        if not is_botmaster(update.effective_user.id):return await update.effective_message.reply_text('Solo BotMaster puede forzar Halloween.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede forzar Halloween.')
    if not _is_games_topic(update):return await update.effective_message.reply_text('Usa /halloweenahora en Juegos y Casino.')
    ok=await _spawn_halloween_surprise(context,update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),'candy',True)
    if not ok:await update.effective_message.reply_text('No pude crear la aparición Halloween.')


async def npchalloweenahora_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    try:
        if not is_botmaster(update.effective_user.id):return await update.effective_message.reply_text('Solo BotMaster puede forzar el NPC Halloween.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede forzar el NPC Halloween.')
    if not _is_games_topic(update):return await update.effective_message.reply_text('Usa /npchalloweenahora en Juegos y Casino.')
    ok=await _spawn_halloween_special_npc(context,update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),'halloween_trainer',True)
    if not ok:await update.effective_message.reply_text('No pude crear el NPC Halloween.')


async def jefehalloween_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    try:
        if not is_botmaster(update.effective_user.id):return await update.effective_message.reply_text('Solo BotMaster puede forzar el jefe Halloween.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede forzar el jefe Halloween.')
    if not _is_games_topic(update):return await update.effective_message.reply_text('Usa /jefehalloween en Juegos y Casino.')
    ok=await _spawn_halloween_special_npc(context,update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),'halloween_boss',True)
    if not ok:await update.effective_message.reply_text('No pude crear el jefe Halloween.')



async def pokemon_halloween_npc_job(context:ContextTypes.DEFAULT_TYPE):
    if not _halloween_active():return
    for community in COMUNIDADES:
        try:
            chat_id=int(community.get('id_comunidad')); thread_id=_games_topic(chat_id)
            if thread_id is not None:await _spawn_halloween_special_npc(context,chat_id,thread_id,'halloween_trainer',False)
        except Exception as e:print('[PK Halloween NPC job]',type(e).__name__,e)


async def pokemon_halloween_boss_job(context:ContextTypes.DEFAULT_TYPE):
    if not _halloween_active() or _halloween_now().weekday() not in (4,5,6):return
    for community in COMUNIDADES:
        try:
            chat_id=int(community.get('id_comunidad')); thread_id=_games_topic(chat_id)
            if thread_id is not None:await _spawn_halloween_special_npc(context,chat_id,thread_id,'halloween_boss',False)
        except Exception as e:print('[PK Halloween boss job]',type(e).__name__,e)


# ==================== EXPANSIÓN POKÉMON · SAFARI / ROCKET / RAID / LIGA ====================

def _world_state_cursor(c,key:str,default:str|None=None)->str|None:
    c.execute("SELECT state_value FROM pokemon_world_state_tb WHERE state_key=%s",(str(key),))
    r=c.fetchone(); return str(r[0]) if r and r[0] is not None else default


def _set_world_state_cursor(c,key:str,value:str):
    c.execute("""INSERT INTO pokemon_world_state_tb(state_key,state_value) VALUES(%s,%s)
                 ON CONFLICT(state_key) DO UPDATE SET state_value=EXCLUDED.state_value,updated_at=NOW()""",(str(key),str(value)))


def _current_weather_cursor(c)->str:
    weather=_world_state_cursor(c,'weather','despejado') or 'despejado'
    return weather if weather in WEATHER_KEYS else 'despejado'


async def climapokemon_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    conn=_get_connection()
    try:c=conn.cursor(); weather=_current_weather_cursor(c)
    finally:_put_connection(conn)
    boosted=WEATHER_TYPES.get(weather,())
    bonus=(' · favorece '+', '.join(boosted)) if boosted else ''
    await update.effective_message.reply_text(f"🌦️ CLIMA POKÉMON\n\n{WEATHER_NAMES.get(weather,weather)}{bonus}\n\nEl clima cambia aproximadamente cada 6 horas y modifica qué tipos tienen más probabilidad de aparecer.")


async def pokemon_weather_job(context:ContextTypes.DEFAULT_TYPE):
    conn=_get_connection(); weather=None
    try:
        c=conn.cursor(); old=_current_weather_cursor(c); choices=[x for x in WEATHER_KEYS if x!=old]; weather=random.choice(choices or list(WEATHER_KEYS)); _set_world_state_cursor(c,'weather',weather); conn.commit()
    except Exception as e:conn.rollback(); print('[PK weather]',type(e).__name__,e); return
    finally:_put_connection(conn)
    for community in COMUNIDADES:
        try:
            chat_id=int(community.get('id_comunidad')); thread_id=_games_topic(chat_id)
            if thread_id is not None:await context.bot.send_message(chat_id,f"🌦️ El clima Pokémon cambió: {WEATHER_NAMES.get(weather,weather)}",message_thread_id=thread_id)
        except Exception:pass


def _mission_reset_text()->str:
    now=datetime.now(POKEMON_TZ)
    nxt=(now+timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)
    secs=max(0,int((nxt-now).total_seconds()))
    h,rem=divmod(secs,3600); m=rem//60
    return f"{h} h {m} min"


def _mission_progress_cursor(c,uid:int,key:str,amount:int=1)->bool:
    """Las misiones están activas todo el día y se reinician automáticamente por fecha México.
    Devuelve True si ESTA acción completó el set y entregó el premio automáticamente.
    """
    day=_today_pokemon_date()
    c.execute("INSERT INTO pokemon_daily_missions_tb(user_id,mission_date) VALUES(%s,%s) ON CONFLICT DO NOTHING",(int(uid),day))
    col={'capture':'captures','win':'wins','training':'trainings'}.get(str(key))
    if col:
        c.execute(f"UPDATE pokemon_daily_missions_tb SET {col}={col}+%s WHERE user_id=%s AND mission_date=%s",(max(1,int(amount)),int(uid),day))
    c.execute("SELECT captures,wins,trainings,claimed FROM pokemon_daily_missions_tb WHERE user_id=%s AND mission_date=%s FOR UPDATE",(int(uid),day))
    r=c.fetchone() or (0,0,0,False)
    cap,wins,tr,claimed=int(r[0]),int(r[1]),int(r[2]),bool(r[3])
    if cap>=1 and wins>=2 and tr>=1 and not claimed:
        c.execute("UPDATE pokemon_daily_missions_tb SET claimed=TRUE WHERE user_id=%s AND mission_date=%s",(int(uid),day))
        c.execute("UPDATE usuarios_tb SET saldo=saldo+3000 WHERE id_user=%s",(int(uid),))
        grant_item_with_cursor(c,int(uid),'rare_candy',1)
        return True
    return False


async def misionespokemon_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; day=_today_pokemon_date(); migrated_reward=False
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("INSERT INTO pokemon_daily_missions_tb(user_id,mission_date) VALUES(%s,%s) ON CONFLICT DO NOTHING",(uid,day))
        c.execute("SELECT captures,wins,trainings,claimed FROM pokemon_daily_missions_tb WHERE user_id=%s AND mission_date=%s FOR UPDATE",(uid,day)); r=c.fetchone() or (0,0,0,False)
        cap,wins,tr,claimed=int(r[0]),int(r[1]),int(r[2]),bool(r[3])
        # Compatibilidad con una misión ya completada antes de instalar este parche.
        if cap>=1 and wins>=2 and tr>=1 and not claimed:
            c.execute("UPDATE pokemon_daily_missions_tb SET claimed=TRUE WHERE user_id=%s AND mission_date=%s",(uid,day))
            c.execute("UPDATE usuarios_tb SET saldo=saldo+3000 WHERE id_user=%s",(uid,)); grant_item_with_cursor(c,uid,'rare_candy',1)
            claimed=True; migrated_reward=True
        conn.commit()
    except Exception as e:
        conn.rollback(); print('[PK missions]',type(e).__name__,e); return await update.effective_message.reply_text('No pude consultar tus misiones Pokémon.')
    finally:_put_connection(conn)
    lines=['📜 MISIONES POKÉMON · AUTOMÁTICAS','',
           f"{'✅' if cap>=1 else '⬜'} Captura 1 Pokémon · {min(cap,1)}/1",
           f"{'✅' if wins>=2 else '⬜'} Gana 2 combates Pokémon · {min(wins,2)}/2",
           f"{'✅' if tr>=1 else '⬜'} Completa 1 entrenamiento · {min(tr,1)}/1",'',
           '🎁 Completar las 3: 3,000 PiPesos + 1 Caramelo Raro.',
           '⚙️ No tienes que activarlas: PiBot registra el progreso automáticamente.',
           f'🔄 Se renuevan automáticamente en {_mission_reset_text()} (00:00 México).']
    if migrated_reward:lines += ['', '🎉 ¡Ya las habías completado! Premio entregado automáticamente.']
    elif claimed:lines += ['', '✅ Premio de hoy ya entregado automáticamente.']
    await update.effective_message.reply_text('\n'.join(lines))


async def pokemon_daily_missions_job(context:ContextTypes.DEFAULT_TYPE):
    """Anuncio diario; el progreso se crea/renueva solo por mission_date al primer avance de cada usuario."""
    for community in COMUNIDADES:
        try:
            chat_id=int(community.get('id_comunidad')); thread_id=_games_topic(chat_id)
            if thread_id is not None:
                await context.bot.send_message(chat_id,
                    '📜 NUEVAS MISIONES POKÉMON\n\n'
                    '🎯 Captura 1 Pokémon\n⚔️ Gana 2 combates Pokémon\n🏋️ Completa 1 entrenamiento\n\n'
                    '🎁 3,000 PiPesos + 1 Caramelo Raro al completar las 3.\n'
                    '⚙️ Son automáticas y estarán activas durante las próximas 24 horas.\nUsa /misionespokemon para ver tu progreso.',
                    message_thread_id=thread_id)
        except Exception as e:print('[PK daily missions job]',type(e).__name__,e)

def _achievement_stats_cursor(c,uid:int)->dict:
    c.execute("SELECT wild_catches FROM pokemon_trainer_tb WHERE user_id=%s",(uid,)); r=c.fetchone(); catches=int(r[0]) if r else 0
    c.execute("SELECT COUNT(*) FROM pokemon_instances_tb WHERE owner_id=%s AND shiny=TRUE",(uid,)); shinies=int(c.fetchone()[0])
    c.execute("SELECT COUNT(*) FROM pokemon_badges_tb WHERE user_id=%s",(uid,)); badges=int(c.fetchone()[0])
    c.execute("SELECT COUNT(*) FROM pokemon_pokedex_tb WHERE owner_id=%s",(uid,)); dex=int(c.fetchone()[0])
    c.execute("SELECT wins,best_streak FROM pokemon_rank_tb WHERE user_id=%s",(uid,)); rr=c.fetchone() or (0,0)
    c.execute("SELECT COALESCE(SUM(wins),0),COALESCE(MAX(best_streak),0) FROM pokemon_rank_history_tb WHERE user_id=%s",(uid,)); hist=c.fetchone() or (0,0)
    total_wins=int(rr[0])+int(hist[0]); best_streak=max(int(rr[1]),int(hist[1]))
    c.execute("SELECT COUNT(*) FROM pokemon_eggs_tb WHERE owner_id=%s AND status='hatched'",(uid,)); hatched=int(c.fetchone()[0])
    return {'catches':catches,'shinies':shinies,'badges':badges,'dex':dex,'wins':total_wins,'streak':best_streak,'hatched':hatched}


async def logrospokemon_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection(); newly=[]; stats={}
    achievements=[
        ('capturador10','🎯 Capturador',lambda s:s['catches']>=10,'10 capturas'),
        ('capturador50','🏹 Cazador experto',lambda s:s['catches']>=50,'50 capturas'),
        ('primer_shiny','✨ Cazador Shiny',lambda s:s['shinies']>=1,'1 Shiny'),
        ('ocho_medallas','🏅 Maestro de Kanto',lambda s:s['badges']>=8,'8 medallas'),
        ('pokedex151','📖 Pokédex completa',lambda s:s['dex']>=151,'151 especies'),
        ('pvp10','⚔️ Combatiente',lambda s:s['wins']>=10,'10 victorias PvP'),
        ('racha5','🔥 En racha',lambda s:s['streak']>=5,'racha de 5'),
        ('criador5','🥚 Criador',lambda s:s['hatched']>=5,'5 huevos eclosionados'),
    ]
    try:
        c=conn.cursor(); stats=_achievement_stats_cursor(c,uid); c.execute("SELECT achievement_key FROM pokemon_achievements_tb WHERE user_id=%s",(uid,)); owned={str(x[0]) for x in c.fetchall()}
        for key,name,cond,_ in achievements:
            if cond(stats) and key not in owned:
                c.execute("INSERT INTO pokemon_achievements_tb(user_id,achievement_key) VALUES(%s,%s) ON CONFLICT DO NOTHING",(uid,key)); newly.append(name); c.execute("UPDATE usuarios_tb SET saldo=saldo+2500 WHERE id_user=%s",(uid,)); grant_item_with_cursor(c,uid,'rare_candy',1); owned.add(key)
        conn.commit()
    except Exception as e:conn.rollback(); print('[PK achievements]',type(e).__name__,e); return await update.effective_message.reply_text('No pude revisar tus logros.')
    finally:_put_connection(conn)
    lines=['🏆 LOGROS POKÉMON','']
    for key,name,cond,req in achievements:lines.append(f"{'✅' if cond(stats) else '⬜'} {name} · {req}")
    lines += ['', '🎁 Cada logro nuevo entrega 2,500 PiPesos + 1 Caramelo Raro.']
    if newly:lines += ['', '🎉 Nuevos: '+', '.join(newly)]
    await update.effective_message.reply_text('\n'.join(lines))


def _friendship_name(value:int)->str:
    v=int(value)
    if v>=220:return '💖 Inseparables'
    if v>=150:return '❤️ Gran amistad'
    if v>=80:return '💛 Confianza'
    if v>=30:return '💚 Compañeros'
    return '🤍 Recién conocidos'


async def amistadpokemon_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection(); lines=['❤️ AMISTAD POKÉMON','']
    try:
        c=conn.cursor(); _ensure_team_row_cursor(c,uid); c.execute("SELECT slot1,slot2,slot3,slot4 FROM pokemon_team_tb WHERE owner_id=%s",(uid,)); slots=c.fetchone() or (None,None,None,None)
        for i,pid in enumerate(slots,1):
            if pid is None:lines.append(f'{i}. — Vacío —'); continue
            c.execute("SELECT species_id,nickname,friendship FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); r=c.fetchone()
            if r:lines.append(f"{i}. {r[1] or NAMES[int(r[0])]} · {int(r[2])}/255 · {_friendship_name(int(r[2]))}")
    finally:_put_connection(conn)
    lines += ['', 'La amistad aumenta al entrenar y combatir con ese ejemplar.']
    await update.effective_message.reply_text('\n'.join(lines))


# ---------- Zona Safari ----------
def _safari_session_cursor(c,uid:int,lock:bool=False):
    sql="SELECT session_id,user_id,chat_id,thread_id,safari_date,status,balls,current_species,current_level,current_shiny,current_ivs_json,current_defeated,created_at,expires_at FROM pokemon_safari_sessions_tb WHERE user_id=%s AND safari_date=%s ORDER BY session_id DESC LIMIT 1"
    if lock:sql+=' FOR UPDATE'
    c.execute(sql,(int(uid),_today_pokemon_date())); r=c.fetchone()
    if r and str(r[5])=='active' and r[13] is not None and r[13]<=datetime.now(timezone.utc):
        c.execute("UPDATE pokemon_safari_sessions_tb SET status='expired',finished_at=NOW() WHERE session_id=%s",(int(r[0]),)); return None
    return r


def _safari_pool_species()->int:
    legendary=[int(x) for x in LEGENDARY_IDS]
    # Muy rara vez el Safari puede esconder un legendario de Kanto.
    if legendary and random.random()<SAFARI_LEGENDARY_APPEAR_CHANCE:
        return random.choice(legendary)
    legendary_set=set(legendary); epic=[int(x) for x in EPIC_IDS if int(x) not in legendary_set]; rare=[int(x) for x in RARE_IDS if int(x) not in legendary_set]
    special=[1,4,7,25,37,58,63,92,113,115,123,127,128,131,133,137,138,140,142,143,147]
    tier=random.choices(('rare','epic','special'),weights=(45,35,20),k=1)[0]
    pool=rare if tier=='rare' else epic if tier=='epic' else special
    return random.choice(pool or special)


def _safari_capture_probability(species:int,hp_ratio:float=1.0)->float:
    """Safari Ball: se puede lanzar siempre; bajar PS mejora mucho la captura."""
    rarity=rarity_for(int(species)); maximum=float(SAFARI_CAPTURE_CHANCE.get(rarity,0.45))
    hp=max(0.0,min(1.0,float(hp_ratio)))
    # A PS completos se conserva 30% de la probabilidad máxima; a 0 PS se usa el máximo.
    factor=0.30 + (1.0-hp)*0.70
    return max(0.005,min(0.95,maximum*factor))


def _safari_text(row)->str:
    sid=int(row[0]); status=str(row[5]); balls=int(row[6]); sp=row[7]
    left=max(0,int((row[13]-datetime.now(timezone.utc)).total_seconds())) if row[13] else 0
    lines=[f'🌿 ZONA SAFARI · Sesión #{sid}',f'🎟️ Pase diario · ⏳ {(left+59)//60} min',f'🔴 Safari Balls: {balls}']
    if status!='active' or balls<=0:
        lines += ['', '🏁 Safari terminado.', '🔴 Te quedaste sin Safari Balls. Vuelve mañana para una nueva entrada.']
        return '\n'.join(lines)
    if sp is None:lines += ['', '🌾 No tienes un encuentro activo. Explora para buscar un Pokémon raro.']
    else:
        rarity=rarity_for(int(sp)); shiny='✨ SHINY · ' if bool(row[9]) else ''
        lines += ['',f"👀 {shiny}#{int(sp):03d} {NAMES[int(sp)]} · Nv.{int(row[8])}",f"⭐ Rareza: {rarity.upper()}", '💪 En Safari salen más fuertes y con mejores IV.']
        if int(sp) in set(int(x) for x in LEGENDARY_IDS):lines.append('🌟 ¡Es un encuentro legendario extremadamente raro!')
        if bool(row[11]):lines.append('💫 Está debilitado: ahora será mucho más fácil capturarlo.')
        else:lines.append('🔴 Puedes lanzar una Safari Ball ahora o pelear para bajar sus PS y mejorar la captura.')
    return '\n'.join(lines)


def _safari_markup(row):
    sid=int(row[0]); rows=[]
    if str(row[5])!='active' or int(row[6])<=0:return None
    if row[7] is None:rows.append([InlineKeyboardButton('🌾 Explorar',callback_data=f'pk:safexplore:{sid}')])
    elif bool(row[11]):rows.append([InlineKeyboardButton('🔴 Lanzar Safari Ball',callback_data=f'pk:safball:{sid}'),InlineKeyboardButton('💨 Dejarlo ir',callback_data=f'pk:safskip:{sid}')])
    else:
        rows.append([InlineKeyboardButton('🔴 Lanzar Safari Ball',callback_data=f'pk:safball:{sid}')])
        rows.append([InlineKeyboardButton('⚔️ Pelear',callback_data=f'pk:saffight:{sid}'),InlineKeyboardButton('💨 Huir',callback_data=f'pk:safskip:{sid}')])
    return InlineKeyboardMarkup(rows)


def _safari_team_markup_cursor(c,uid:int,sid:int):
    rows=[]
    for pid in _npc_team_slot_ids_cursor(c,uid):
        c.execute("SELECT species_id,nickname,level,shiny FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); r=c.fetchone()
        if not r:continue
        rows.append([InlineKeyboardButton(f"⚔️ {'✨ ' if r[3] else ''}{r[1] or NAMES[int(r[0])]} · Nv.{int(r[2])}",callback_data=f'pk:safpick:{sid}:{pid}')])
    rows.append([InlineKeyboardButton('⬅️ Volver',callback_data=f'pk:safback:{sid}')])
    return InlineKeyboardMarkup(rows)


async def safari_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private' or not _is_games_topic(update):return await update.effective_message.reply_text('🌿 La Zona Safari se usa en Juegos y Casino.')
    uid=update.effective_user.id; conn=_get_connection(); row=None; used=False
    try:
        c=conn.cursor(); row=_safari_session_cursor(c,uid)
        if row is None:
            c.execute("SELECT status FROM pokemon_safari_sessions_tb WHERE user_id=%s AND safari_date=%s",(uid,_today_pokemon_date())); old=c.fetchone(); used=bool(old)
        conn.commit()
    except Exception:conn.rollback()
    finally:_put_connection(conn)
    if row and str(row[5])=='active':return await update.effective_message.reply_text(_safari_text(row),reply_markup=_safari_markup(row))
    if row:used=True
    if used:return await update.effective_message.reply_text('🌿 Ya usaste tu entrada a la Zona Safari de hoy. Vuelve mañana.')
    kb=InlineKeyboardMarkup([[InlineKeyboardButton(f'🎟️ Entrar · {SAFARI_PASS_COST:,} PiPesos',callback_data='pk:safbuy')]])
    await update.effective_message.reply_text(f'🌿 ZONA SAFARI\n\n🎟️ Entrada diaria: {SAFARI_PASS_COST:,} PiPesos\n⏳ Duración: 30 minutos\n🔴 Recibes {SAFARI_START_BALLS} Safari Balls fijas; cuando se acaban, termina tu Safari.\n✨ Shiny: 1/{SAFARI_SHINY_DENOMINATOR}\n🧬 IV más altos que las apariciones normales\n🔴 Puedes lanzar una Safari Ball en cualquier momento. Bajar los PS mejora la captura.\n🌟 Existe una posibilidad extremadamente rara de encontrar un legendario de Kanto.\n\n🎟️ Si encuentras un Pase Safari como drop secreto, la entrada te sale gratis.',reply_markup=kb)


# ---------- Team Rocket ----------
def _rocket_active_cursor(c,chat_id:int,thread_id:int|None,lock:bool=False):
    sql="SELECT event_id,chat_id,thread_id,status,stage,message_id,created_at,expires_at FROM pokemon_rocket_events_tb WHERE chat_id=%s AND thread_id=%s AND status='active' ORDER BY event_id DESC LIMIT 1"
    if lock:sql+=' FOR UPDATE'
    c.execute(sql,(int(chat_id),int(thread_id or 0))); return c.fetchone()


def _rocket_stage_label(stage:int)->str:
    names=['🚀 Recluta Rocket','🧪 Ejecutivo Rocket','❤️ Jessie','💙 James']
    return names[min(max(0,int(stage)),3)]


def _rocket_event_text(row)->str:
    stage=int(row[4]); left=max(0,int((row[7]-datetime.now(timezone.utc)).total_seconds())) if row[7] else 0
    mins=(left+59)//60
    lines=['🚀 INVASIÓN TEAM ROCKET','',f'⏳ Tiempo restante: {mins} min',f'📍 Progreso: {stage}/4 enemigos derrotados','']
    for i in range(4):lines.append(f"{'✅' if i<stage else '➡️' if i==stage else '🔒'} {_rocket_stage_label(i)}")
    lines += ['', '🎁 Pueden soltar PiPesos, Caja de Objetos y premios de las cajas normales de PiBot.', '⚠️ Jessie y James son los combates más difíciles.']
    return '\n'.join(lines)


def _rocket_markup(row):
    if str(row[3])!='active' or int(row[4])>=4:return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(f'⚔️ Enfrentar a {_rocket_stage_label(int(row[4]))}',callback_data=f'pk:rocketfight:{int(row[0])}')]])


async def _refresh_rocket_event_message(context,event_id:int):
    conn=_get_connection(); row=None
    try:c=conn.cursor(); c.execute("SELECT event_id,chat_id,thread_id,status,stage,message_id,created_at,expires_at FROM pokemon_rocket_events_tb WHERE event_id=%s",(event_id,)); row=c.fetchone()
    finally:_put_connection(conn)
    if not row:return
    text=_rocket_event_text(row) if str(row[3])=='active' else ('🏆 ¡TEAM ROCKET FUE DERROTADO!\n\nJessie y James huyeron prometiendo volver...') if str(row[3])=='finished' else '⌛ Team Rocket escapó antes de que el grupo pudiera detenerlo.'
    try:await context.bot.edit_message_text(chat_id=int(row[1]),message_id=int(row[5]),text=text,reply_markup=_rocket_markup(row))
    except Exception:pass


async def _spawn_rocket_event(context,chat_id:int,thread_id:int|None,manual:bool=False)->bool:
    conn=_get_connection(); row=None
    try:
        c=conn.cursor(); day=_today_pokemon_date(); c.execute("SELECT event_id,status FROM pokemon_rocket_events_tb WHERE chat_id=%s AND thread_id=%s AND event_date=%s FOR UPDATE",(chat_id,int(thread_id or 0),day)); old=c.fetchone()
        if old:
            if not manual:conn.rollback(); return False
            c.execute("DELETE FROM pokemon_rocket_participants_tb WHERE event_id=%s",(int(old[0]),))
            c.execute("UPDATE pokemon_npc_encounters_tb SET status='expired',finished_at=NOW() WHERE event_ref=%s AND status IN ('active','selecting')",(int(old[0]),))
            c.execute("UPDATE pokemon_rocket_events_tb SET status='active',stage=0,message_id=NULL,created_at=NOW(),expires_at=NOW()+INTERVAL '30 minutes',finished_at=NULL WHERE event_id=%s RETURNING event_id,chat_id,thread_id,status,stage,message_id,created_at,expires_at",(int(old[0]),)); row=c.fetchone()
        else:
            c.execute("INSERT INTO pokemon_rocket_events_tb(chat_id,thread_id,event_date) VALUES(%s,%s,%s) RETURNING event_id,chat_id,thread_id,status,stage,message_id,created_at,expires_at",(chat_id,int(thread_id or 0),day)); row=c.fetchone()
        conn.commit()
    except Exception as e:conn.rollback(); print('[PK rocket spawn]',type(e).__name__,e); return False
    finally:_put_connection(conn)
    try:
        msg=await context.bot.send_message(chat_id,_rocket_event_text(row),message_thread_id=thread_id,reply_markup=_rocket_markup(row)); conn=_get_connection(); c=conn.cursor(); c.execute("UPDATE pokemon_rocket_events_tb SET message_id=%s WHERE event_id=%s",(msg.message_id,int(row[0]))); conn.commit(); _put_connection(conn); return True
    except Exception as e:print('[PK rocket send]',type(e).__name__,e); return False


async def pokemon_rocket_job(context:ContextTypes.DEFAULT_TYPE):
    for community in COMUNIDADES:
        try:
            chat_id=int(community.get('id_comunidad')); thread_id=_games_topic(chat_id)
            if thread_id is not None:await _spawn_rocket_event(context,chat_id,thread_id,False)
        except Exception as e:print('[PK rocket job]',type(e).__name__,e)


async def rocketpokemon_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private' or not _is_games_topic(update):return await update.effective_message.reply_text('🚀 Team Rocket aparece en Juegos y Casino.')
    conn=_get_connection(); row=None
    try:c=conn.cursor(); row=_rocket_active_cursor(c,update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None))
    finally:_put_connection(conn)
    await update.effective_message.reply_text(_rocket_event_text(row),reply_markup=_rocket_markup(row)) if row else await update.effective_message.reply_text('🚀 No hay una invasión Team Rocket activa ahora mismo.')


async def rocketahora_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    try:
        if not is_botmaster(update.effective_user.id):return await update.effective_message.reply_text('Solo BotMaster puede forzar Team Rocket.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede forzar Team Rocket.')
    if not _is_games_topic(update):return await update.effective_message.reply_text('Usa /rocketahora en Juegos y Casino.')
    ok=await _spawn_rocket_event(context,update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),True)
    if not ok:await update.effective_message.reply_text('No pude iniciar la invasión Rocket.')


# ---------- Incursiones ----------
RAID_SELECT = "raid_id,chat_id,thread_id,species_id,level,max_hp,hp,status,message_id,created_at,expires_at,is_legendary,shiny,catcher_id,capture_attempts,capture_status"


def _raid_active_cursor(c,chat_id:int,thread_id:int|None,lock:bool=False):
    # Una captura legendaria pendiente también bloquea otra incursión en el mismo tema.
    sql=f"SELECT {RAID_SELECT} FROM pokemon_raids_tb WHERE chat_id=%s AND thread_id=%s AND status IN ('active','capture') ORDER BY raid_id DESC LIMIT 1"
    if lock:sql+=' FOR UPDATE'
    c.execute(sql,(int(chat_id),int(thread_id or 0))); return c.fetchone()


def _raid_capture_markup(row):
    if not row or str(row[7])!='capture' or str(row[15]) not in ('pending','none'):return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(f"🎲 Lanzar Poké Ball · {int(row[14])}/{RAID_LEGENDARY_CAPTURE_ATTEMPTS}",callback_data=f'pk:raidcatch:{int(row[0])}')]])


def _raid_text(row,catcher_name:str|None=None)->str:
    hp,maxhp=int(row[6]),int(row[5]); pct=max(0,min(100,round(hp/max(1,maxhp)*100))); bars=max(0,min(10,round(pct/10))); bar='█'*bars+'░'*(10-bars)
    left=max(0,int((row[10]-datetime.now(timezone.utc)).total_seconds())) if row[10] else 0
    legendary=bool(row[11])
    if str(row[7])=='capture':
        who=catcher_name or 'el entrenador elegido'
        cap_title='🌟 LEGENDARIO DERROTADO' if legendary else '🏆 JEFE DE INCURSIÓN DERROTADO'
        return (f"{cap_title}\n\n#{int(row[3]):03d} {NAMES[int(row[3])]} · Nv.{int(row[4])}\n"
                f"🎯 {who} obtuvo la oportunidad de captura.\n🎲 Intentos usados: {int(row[14])}/{RAID_LEGENDARY_CAPTURE_ATTEMPTS}\n"
                f"⏳ {(left+59)//60} min para completar la captura.\n\nSolo un 6 en el dado consigue atraparlo.")
    title='🌟 INCURSIÓN LEGENDARIA' if legendary else '💥 INCURSIÓN POKÉMON'
    power='\n⚠️ Los legendarios tienen MUCHOS más PS y nivel.' if legendary else ''
    return (f"{title}\n\n👹 #{int(row[3]):03d} {NAMES[int(row[3])]} · Nv.{int(row[4])}\n"
            f"❤️ {hp:,}/{maxhp:,} · {bar} {pct}%\n⏳ {(left+59)//60} min restantes\n\n"
            f"⚔️ Cada entrenador puede atacar hasta {RAID_USER_ATTACKS} veces.\n🏆 Todos los participantes reciben premio si el grupo lo derrota.{power}")


def _raid_markup(row):
    if not row:return None
    if str(row[7])=='active':return InlineKeyboardMarkup([[InlineKeyboardButton('⚔️ Atacar incursión',callback_data=f'pk:raidattack:{int(row[0])}')]])
    if str(row[7])=='capture':return _raid_capture_markup(row)
    return None


def _raid_weighted_catcher(parts)->int|None:
    if not parts:return None
    users=[int(r[0]) for r in parts]; weights=[max(1,int(r[1])) for r in parts]
    return int(random.choices(users,weights=weights,k=1)[0])


async def _refresh_raid_message(context,raid_id:int):
    conn=_get_connection(); row=None; catcher_name=None
    try:
        c=conn.cursor(); c.execute(f"SELECT {RAID_SELECT} FROM pokemon_raids_tb WHERE raid_id=%s",(raid_id,)); row=c.fetchone()
        if row and row[13] is not None:catcher_name=_display_name_cursor(c,int(row[13]))
    finally:_put_connection(conn)
    if not row:return
    status=str(row[7]); capstatus=str(row[15] or 'none')
    if status=='capture':text=_raid_text(row,catcher_name)
    elif status=='finished' and capstatus=='caught':
        title='🏆 INCURSIÓN LEGENDARIA COMPLETADA' if bool(row[11]) else '🏆 INCURSIÓN COMPLETADA'
        text=(f"{title}\n\n#{int(row[3]):03d} {NAMES[int(row[3])]} fue derrotado.\n"
              f"🎉 {catcher_name or 'El entrenador elegido'} logró capturarlo en {int(row[14])}/{RAID_LEGENDARY_CAPTURE_ATTEMPTS} tiros."
              + ("\n✨ ¡Y resultó ser SHINY!" if bool(row[12]) else ''))
    elif status=='finished' and capstatus=='escaped':
        title='💨 EL LEGENDARIO ESCAPÓ' if bool(row[11]) else '💨 EL JEFE DE INCURSIÓN ESCAPÓ'
        text=(f"{title}\n\n#{int(row[3]):03d} {NAMES[int(row[3])]} fue derrotado en la incursión, "
              f"pero escapó durante la captura.\n🎲 Se usaron {int(row[14])}/{RAID_LEGENDARY_CAPTURE_ATTEMPTS} tiros.")
    elif status=='finished':text=f"🏆 INCURSIÓN COMPLETADA\n\n#{int(row[3]):03d} {NAMES[int(row[3])]} fue derrotado por el grupo.\n🎁 Premios entregados a los participantes."
    elif status=='expired':text=f"💨 INCURSIÓN FALLIDA\n\n#{int(row[3]):03d} {NAMES[int(row[3])]} escapó."
    else:text=_raid_text(row,catcher_name)
    try:await context.bot.edit_message_text(chat_id=int(row[1]),message_id=int(row[8]),text=text,reply_markup=_raid_markup(row))
    except Exception:pass


def _raid_reference_level_cursor(c)->int:
    """Nivel mediano de los Pokémon que los entrenadores tienen actualmente en /equipo.

    Evita que una cuenta muy alta desbalancee el raid para todo el grupo. Si aún no
    hay equipos configurados, usa un nivel base bajo y seguro.
    """
    c.execute("""
        SELECT p.level
        FROM pokemon_team_tb t
        JOIN pokemon_instances_tb p
          ON p.owner_id=t.owner_id
         AND p.pokemon_id IN (t.slot1,t.slot2,t.slot3,t.slot4)
        WHERE p.level IS NOT NULL
    """)
    levels=sorted(int(r[0]) for r in c.fetchall() if r and r[0] is not None)
    if not levels:return 10
    n=len(levels)
    if n%2:return max(1,min(MAX_LEVEL,int(levels[n//2])))
    return max(1,min(MAX_LEVEL,round((levels[n//2-1]+levels[n//2])/2)))


async def _spawn_raid(context,chat_id:int,thread_id:int|None,manual:bool=False,forced_legendary:bool|None=None)->bool:
    conn=_get_connection(); row=None
    try:
        c=conn.cursor(); c.execute("SELECT created_at FROM pokemon_raids_tb WHERE chat_id=%s AND thread_id=%s ORDER BY raid_id DESC LIMIT 1",(chat_id,int(thread_id or 0))); last=c.fetchone()
        if last and not manual and (datetime.now(timezone.utc)-last[0]).total_seconds()<47*3600:conn.rollback(); return False
        if _raid_active_cursor(c,chat_id,thread_id):conn.rollback(); return False
        legendary=(bool(forced_legendary) if forced_legendary is not None else random.random()<RAID_LEGENDARY_CHANCE)
        reference_level=_raid_reference_level_cursor(c)
        if legendary:
            # Los legendarios quedan claramente por encima del nivel habitual del grupo,
            # pero sin saltos absurdos (p. ej. equipos Nv.25 -> jefe aprox. Nv.31-35).
            sp=random.choice(RAID_LEGENDARY_BOSSES); level=max(5,min(MAX_LEVEL,reference_level+random.randint(6,10))); maxhp=22_000+level*180
            shiny=(random.randrange(RAID_LEGENDARY_SHINY_DENOMINATOR)==0)
        else:
            # Raid normal: solo 2-5 niveles por encima del nivel mediano de los equipos.
            # Ejemplo pedido: equipos alrededor de Nv.25 -> jefe Nv.27-30.
            sp=random.choice(RAID_BOSSES); level=max(3,min(MAX_LEVEL,reference_level+random.randint(2,5))); maxhp=9000+level*90; shiny=(random.randrange(RAID_NORMAL_SHINY_DENOMINATOR)==0)
        c.execute("""INSERT INTO pokemon_raids_tb(chat_id,thread_id,species_id,level,max_hp,hp,is_legendary,shiny)
                     VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                     RETURNING """+RAID_SELECT,(chat_id,int(thread_id or 0),sp,level,maxhp,maxhp,legendary,shiny)); row=c.fetchone(); conn.commit()
    except Exception as e:conn.rollback(); print('[PK raid spawn]',type(e).__name__,e); return False
    finally:_put_connection(conn)
    try:
        msg=await context.bot.send_message(chat_id,_raid_text(row),message_thread_id=thread_id,reply_markup=_raid_markup(row)); conn=_get_connection(); c=conn.cursor(); c.execute("UPDATE pokemon_raids_tb SET message_id=%s WHERE raid_id=%s",(msg.message_id,int(row[0]))); conn.commit(); _put_connection(conn); return True
    except Exception as e:print('[PK raid send]',type(e).__name__,e); return False


async def pokemon_raid_job(context:ContextTypes.DEFAULT_TYPE):
    for community in COMUNIDADES:
        try:
            chat_id=int(community.get('id_comunidad')); thread_id=_games_topic(chat_id)
            if thread_id is not None:await _spawn_raid(context,chat_id,thread_id,False)
        except Exception as e:print('[PK raid job]',type(e).__name__,e)


async def raidpokemon_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private' or not _is_games_topic(update):return await update.effective_message.reply_text('💥 Las incursiones aparecen en Juegos y Casino.')
    conn=_get_connection(); row=None; catcher_name=None
    try:
        c=conn.cursor(); row=_raid_active_cursor(c,update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None))
        if row and row[13] is not None:catcher_name=_display_name_cursor(c,int(row[13]))
    finally:_put_connection(conn)
    await update.effective_message.reply_text(_raid_text(row,catcher_name),reply_markup=_raid_markup(row)) if row else await update.effective_message.reply_text('💥 No hay una incursión activa. Aparece aproximadamente una cada 2 días.')


async def raidahora_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    try:
        if not is_botmaster(update.effective_user.id):return await update.effective_message.reply_text('Solo BotMaster puede forzar una incursión.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede forzar una incursión.')
    if not _is_games_topic(update):return await update.effective_message.reply_text('Usa /raidahora en Juegos y Casino.')
    forced=None
    if context.args:
        arg=str(context.args[0]).lower()
        if arg in ('legendario','legendaria','legend'):forced=True
        elif arg in ('normal','comun'):forced=False
    ok=await _spawn_raid(context,update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),True,forced)
    if not ok:await update.effective_message.reply_text('No pude iniciar la incursión.')


async def pokemon_adventure_maintenance_job(context:ContextTypes.DEFAULT_TYPE):
    rocket_ids=[]; raid_ids=[]
    conn=_get_connection()
    try:
        c=conn.cursor()
        c.execute("UPDATE pokemon_safari_sessions_tb SET status='expired',finished_at=NOW() WHERE status='active' AND expires_at<=NOW()")
        c.execute("SELECT event_id FROM pokemon_rocket_events_tb WHERE status='active' AND expires_at<=NOW() FOR UPDATE"); rocket_ids=[int(r[0]) for r in c.fetchall()]
        if rocket_ids:c.execute("UPDATE pokemon_rocket_events_tb SET status='expired',finished_at=NOW() WHERE event_id=ANY(%s)",(rocket_ids,))
        c.execute("SELECT raid_id FROM pokemon_raids_tb WHERE status='active' AND expires_at<=NOW() FOR UPDATE"); active_raid_ids=[int(r[0]) for r in c.fetchall()]
        if active_raid_ids:c.execute("UPDATE pokemon_raids_tb SET status='expired',finished_at=NOW() WHERE raid_id=ANY(%s)",(active_raid_ids,))
        c.execute("SELECT raid_id FROM pokemon_raids_tb WHERE status='capture' AND expires_at<=NOW() FOR UPDATE"); capture_raid_ids=[int(r[0]) for r in c.fetchall()]
        if capture_raid_ids:c.execute("UPDATE pokemon_raids_tb SET status='finished',capture_status='escaped',finished_at=NOW() WHERE raid_id=ANY(%s)",(capture_raid_ids,))
        raid_ids=active_raid_ids+capture_raid_ids
        c.execute("DELETE FROM pokemon_fugitives_tb WHERE last_seen_at<NOW()-INTERVAL '7 days'")
        conn.commit()
    except Exception as e:conn.rollback(); print('[PK adventure maintenance]',type(e).__name__,e)
    finally:_put_connection(conn)
    for eid in rocket_ids:
        try:await _refresh_rocket_event_message(context,eid)
        except Exception:pass
    for rid in raid_ids:
        try:await _refresh_raid_message(context,rid)
        except Exception:pass
    # Enseñanza de movimientos pendiente: el selector llega automáticamente por privado.
    await _notify_pending_move_learning(context)


# ---------- Liga Pokémon ----------
async def ligapokemon_command(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private' or not _is_games_topic(update):return await update.effective_message.reply_text('👑 La Liga Pokémon se desafía en Juegos y Casino.')
    uid=update.effective_user.id; conn=_get_connection(); stage=0; done=False; badges=0; eid=None
    try:
        c=conn.cursor(); c.execute("SELECT COUNT(*) FROM pokemon_badges_tb WHERE user_id=%s",(uid,)); badges=int(c.fetchone()[0])
        if badges<8:conn.rollback(); return await update.effective_message.reply_text(f'🏅 Necesitas las 8 medallas de Kanto. Llevas {badges}/8.')
        c.execute("INSERT INTO pokemon_league_progress_tb(user_id) VALUES(%s) ON CONFLICT DO NOTHING",(uid,)); c.execute("SELECT stage,champion_done FROM pokemon_league_progress_tb WHERE user_id=%s FOR UPDATE",(uid,)); r=c.fetchone(); stage=int(r[0]); done=bool(r[1])
        if done:conn.rollback(); return await update.effective_message.reply_text('👑 Ya derrotaste al Alto Mando y al Campeón de Kanto. Eres Campeón Pokémon.')
        if _battle_busy_cursor(c,uid):conn.rollback(); return await update.effective_message.reply_text('⚔️ Termina tu batalla actual antes de entrar a la Liga.')
        key=LEAGUE_ORDER[min(stage,len(LEAGUE_ORDER)-1)]
        c.execute("INSERT INTO pokemon_npc_encounters_tb(chat_id,thread_id,npc_key,encounter_type,mode,expires_at) VALUES(%s,%s,%s,'normal',3,NOW()+INTERVAL '30 minutes') RETURNING encounter_id",(update.effective_chat.id,int(getattr(update.effective_message,'message_thread_id',None) or 0),key)); eid=int(c.fetchone()[0]); conn.commit()
    except Exception as e:conn.rollback(); print('[PK league]',type(e).__name__,e); return await update.effective_message.reply_text('No pude abrir tu desafío de Liga.')
    finally:_put_connection(conn)
    await _send_npc_encounter(context,eid)




# ==================== NPC / LÍDERES / MEDALLAS / DOBLES ====================
# Subsistema aislado: usa las tablas Pokémon existentes y añade solo sus propias tablas/callbacks.

NPC_NORMALS = {
    'youngster': {'name':'Joven','emoji':'🧢','pool':[19,20,21,22,32,33,56,57]},
    'bug_catcher': {'name':'Cazabichos','emoji':'🐛','pool':[10,11,12,13,14,15,46,47,48,49,123,127]},
    'lass': {'name':'Chica','emoji':'🎀','pool':[16,17,19,25,35,39,43,52,69,133]},
    'sailor': {'name':'Marinero','emoji':'⚓','pool':[54,55,60,61,66,67,72,73,90,98]},
    'jr_trainer': {'name':'Entrenador Jr.','emoji':'🎒','pool':[21,22,29,32,41,43,56,58,60,69,84]},
    'pokemaniac': {'name':'Pokémaníaco','emoji':'🤓','pool':[104,105,108,111,112,115,128,131,143]},
    'super_nerd': {'name':'Super Nerd','emoji':'🧪','pool':[81,82,88,89,100,101,109,110,137]},
    'hiker': {'name':'Montañero','emoji':'🥾','pool':[66,67,74,75,95,111,112]},
    'biker': {'name':'Motociclista','emoji':'🏍️','pool':[23,24,88,89,109,110]},
    'burglar': {'name':'Ladrón','emoji':'🕶️','pool':[37,38,58,59,77,78,109,110]},
    'engineer': {'name':'Ingeniero','emoji':'🛠️','pool':[25,26,81,82,100,101]},
    'fisherman': {'name':'Pescador','emoji':'🎣','pool':[60,61,72,73,90,98,99,116,117,118,119,129]},
    'swimmer': {'name':'Nadador','emoji':'🏊','pool':[54,55,60,61,72,73,86,87,90,98,116,117,118]},
    'cue_ball': {'name':'Pandillero','emoji':'🕶️','pool':[56,57,66,67,88,89]},
    'gambler': {'name':'Jugador','emoji':'🎲','pool':[23,24,37,58,77,84,85,111]},
    'beauty': {'name':'Bella','emoji':'💄','pool':[35,36,39,40,43,44,45,69,70,71,120]},
    'psychic': {'name':'Psíquico','emoji':'🔮','pool':[63,64,65,79,80,96,97,102,103]},
    'rocker': {'name':'Rockero','emoji':'🎸','pool':[25,26,81,82,100,101,125]},
    'juggler': {'name':'Malabarista','emoji':'🎪','pool':[63,64,92,93,96,97,122]},
    'rocket': {'name':'Recluta Rocket','emoji':'🚀','pool':[19,20,23,24,41,42,52,53,88,89,109,110]},
}

KANTO_LEADERS = {
    'brock': {'name':'Brock','city':'Ciudad Plateada','badge':'Medalla Roca','badge_emoji':'🪨','emoji':'🪨','pool':[74,95,75]},
    'misty': {'name':'Misty','city':'Ciudad Celeste','badge':'Medalla Cascada','badge_emoji':'💧','emoji':'💧','pool':[120,121,54]},
    'lt_surge': {'name':'Lt. Surge','city':'Ciudad Carmín','badge':'Medalla Trueno','badge_emoji':'⚡','emoji':'⚡','pool':[100,25,26]},
    'erika': {'name':'Erika','city':'Ciudad Azulona','badge':'Medalla Arcoíris','badge_emoji':'🌿','emoji':'🌿','pool':[71,114,45]},
    'koga': {'name':'Koga','city':'Ciudad Fucsia','badge':'Medalla Alma','badge_emoji':'☠️','emoji':'☠️','pool':[109,110,89]},
    'sabrina': {'name':'Sabrina','city':'Ciudad Azafrán','badge':'Medalla Pantano','badge_emoji':'🔮','emoji':'🔮','pool':[64,122,65]},
    'blaine': {'name':'Blaine','city':'Isla Canela','badge':'Medalla Volcán','badge_emoji':'🔥','emoji':'🔥','pool':[58,77,59]},
    'giovanni': {'name':'Giovanni','city':'Ciudad Verde','badge':'Medalla Tierra','badge_emoji':'🌎','emoji':'🌎','pool':[51,112,150]},
}

HALLOWEEN_NPCS = {
    'halloween_trainer': {'name':'Entrenador de las Sombras','emoji':'👻','pool':[92,93,105,94],'event_mode':3},
    'halloween_boss': {'name':'Gengar · Señor de la Noche','emoji':'💀','pool':[92,93,105,94],'event_mode':3},
}

ROCKET_EVENT_NPCS = {
    'rocket_grunt_event': {'name':'Recluta Rocket','emoji':'🚀','pool':[20,24,42,89,110],'event_mode':2},
    'rocket_exec_event': {'name':'Ejecutivo Rocket','emoji':'🧪','pool':[53,89,110,112,101],'event_mode':2},
    'jessie_event': {'name':'Jessie','emoji':'❤️','pool':[24,89,110],'event_mode':3},
    'james_event': {'name':'James','emoji':'💙','pool':[71,110,89],'event_mode':3},
}

LEAGUE_NPCS = {
    'lorelei_e4': {'name':'Lorelei · Alto Mando','emoji':'❄️','pool':[87,91,80],'event_mode':3},
    'bruno_e4': {'name':'Bruno · Alto Mando','emoji':'🥊','pool':[95,107,68],'event_mode':3},
    'agatha_e4': {'name':'Agatha · Alto Mando','emoji':'👻','pool':[94,42,94],'event_mode':3},
    'lance_e4': {'name':'Lance · Alto Mando','emoji':'🐉','pool':[130,148,149],'event_mode':3},
    'champion_e4': {'name':'Campeón de Kanto','emoji':'👑','pool':[65,130,149],'event_mode':3},
}

NPC_ALL = {**NPC_NORMALS, **KANTO_LEADERS, **HALLOWEEN_NPCS, **ROCKET_EVENT_NPCS, **LEAGUE_NPCS}


def _npc_media_cursor(c,key:str):
    c.execute("SELECT media_type,media_file_id FROM pokemon_npc_media_tb WHERE npc_key=%s",(key,))
    r=c.fetchone(); return (str(r[0]),str(r[1])) if r else (None,None)


def _npc_media_for_key_cursor(c,key:str):
    if key=='halloween_trainer':return _halloween_media_cursor(c,'npc')
    if key=='halloween_boss':return _halloween_media_cursor(c,'boss')
    return _npc_media_cursor(c,key)


def _npc_label(key:str)->str:
    d=NPC_ALL.get(key,{})
    return f"{d.get('emoji','👤')} {d.get('name',key)}"


def _npc_media_home_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('👤 NPC normales',callback_data='pk:npcmediacat:normal:0')],
        [InlineKeyboardButton('🏟️ Líderes de gimnasio',callback_data='pk:npcmediacat:leader:0')],
        [InlineKeyboardButton('🚀 Team Rocket',callback_data='pk:npcmediacat:rocket:0')],
        [InlineKeyboardButton('👑 Liga Pokémon',callback_data='pk:npcmediacat:league:0')],
    ])


def _npc_media_category_markup(kind:str,page:int=0):
    if kind=='normal':keys=list(NPC_NORMALS)
    elif kind=='leader':keys=list(KANTO_LEADERS)
    elif kind=='rocket':keys=list(ROCKET_EVENT_NPCS)
    elif kind=='league':keys=list(LEAGUE_NPCS)
    else:keys=[]
    per=10; pages=max(1,math.ceil(len(keys)/per)); page=max(0,min(page,pages-1)); chunk=keys[page*per:(page+1)*per]
    rows=[]
    for i in range(0,len(chunk),2):
        rows.append([InlineKeyboardButton(_npc_label(k),callback_data=f'pk:npcmediapick:{kind}:{k}') for k in chunk[i:i+2]])
    nav=[]
    if page>0:nav.append(InlineKeyboardButton('⬅️',callback_data=f'pk:npcmediacat:{kind}:{page-1}'))
    nav.append(InlineKeyboardButton(f'{page+1}/{pages}',callback_data='pk:noop'))
    if page<pages-1:nav.append(InlineKeyboardButton('➡️',callback_data=f'pk:npcmediacat:{kind}:{page+1}'))
    if nav:rows.append(nav)
    rows.append([InlineKeyboardButton('⬅️ Categorías',callback_data='pk:npcmediahome')])
    return InlineKeyboardMarkup(rows)


async def imagenesnpc_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    try:
        if not is_botmaster(uid):return await update.effective_message.reply_text('Solo BotMaster puede configurar imágenes de NPC.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede configurar imágenes de NPC.')
    text='🎭 MULTIMEDIA POKÉMON\n\nElige NPC normales, líderes, Team Rocket o Liga. Después selecciona uno y envíame por privado una foto o GIF.'
    try:
        await context.bot.send_message(uid,text,reply_markup=_npc_media_home_markup())
        if update.effective_chat.type!='private':await update.effective_message.reply_text('📩 Te mandé el panel de NPC por privado.')
    except Exception:
        await update.effective_message.reply_text('📩 Abre primero el privado de PiBot con /start.')


async def npcpokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        '🎮 NPC POKÉMON\n\n'
        '👤 Cada hora puede aparecer un entrenador durante 10 minutos. Son combates 1v1 o 2v2 y eliges qué Pokémon de tu equipo usar.\n'
        '🏟️ Una vez al día aparece un líder de Kanto durante 10 minutos. Su combate es 3v3.\n'
        '📈 Los rivales escalan al nivel medio de tus elegidos: mismo nivel, +1 o +2.\n'
        '🎖️ La primera victoria contra cada líder entrega su medalla. Usa /medallas.\n'
        '🎁 Los líderes dan MT, Caramelos Raros, Caja de Objetos, PiPesos y mucha XP.\n'
        '🚀 Team Rocket puede invadir el grupo durante 30 minutos; Jessie y James cierran la invasión.\n'
        '👑 Con 8/8 medallas desbloqueas /ligapokemon para desafiar al Alto Mando.'
    )


def _badges_text_cursor(c,uid:int)->str:
    c.execute("SELECT leader_key FROM pokemon_badges_tb WHERE user_id=%s",(uid,)); owned={str(r[0]) for r in c.fetchall()}
    lines=['🏅 MEDALLAS DE KANTO','']
    for key,d in KANTO_LEADERS.items():
        mark=d['badge_emoji'] if key in owned else '⬜'
        lines.append(f"{mark} {d['badge']} · {d['name']}")
    lines += ['',f'Progreso: {len(owned)}/8']
    if len(owned)==8:lines += ['🏆 Kanto completado.', '👑 Liga Pokémon desbloqueada: usa /ligapokemon en Juegos y Casino.']
    else:lines.append('🎁 8/8: Caja Pokémon Shiny + 10,000 PiPesos + 10 Caramelos Raros + encuentro legendario.')
    return '\n'.join(lines)


async def medallas_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; conn=_get_connection()
    try:c=conn.cursor(); text=_badges_text_cursor(c,uid)
    finally:_put_connection(conn)
    await update.effective_message.reply_text(text)


def _npc_team_slot_ids_cursor(c,uid:int)->list[int]:
    _ensure_team_row_cursor(c,uid)
    c.execute("SELECT slot1,slot2,slot3,slot4 FROM pokemon_team_tb WHERE owner_id=%s",(uid,)); r=c.fetchone() or (None,None,None,None)
    return [int(x) for x in r if x is not None]


def _npc_selection_markup_cursor(c,uid:int,eid:int,mode:int,selected:list[int]):
    slots=_npc_team_slot_ids_cursor(c,uid); rows=[]
    for pid in slots:
        c.execute("SELECT species_id,nickname,level,shiny FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); r=c.fetchone()
        if not r:continue
        mark='✅' if pid in selected else '⬜'; shown=r[1] or NAMES[int(r[0])]; shiny='✨ ' if r[3] else ''
        rows.append([InlineKeyboardButton(f'{mark} {shiny}{shown} · Nv.{int(r[2])}',callback_data=f'pk:npcpick:{eid}:{pid}')])
    if len(selected)==mode:rows.append([InlineKeyboardButton('⚔️ Iniciar combate',callback_data=f'pk:npcstart:{eid}')])
    rows.append([InlineKeyboardButton('❌ Liberar encuentro',callback_data=f'pk:npcrelease:{eid}')])
    return InlineKeyboardMarkup(rows)


def _make_npc_mon(species:int,level:int)->dict:
    species=int(species); level=max(1,min(MAX_LEVEL,int(level))); ivs=_roll_ivs(False); moves=available_moves(species,level)
    hp=_stat_value(species,level,'hp',ivs['hp'])
    return {'pid':-random.randint(1_000_000_000,1_999_999_999),'species':species,'nickname':None,'level':level,'hp':hp,'max_hp':hp,
            'moves':moves,'pp':{m:MOVES[m][4] for m in moves if m in MOVES},'status':None,'sleep':0,
            'stages':{'atk':0,'def':0,'spd':0},'shiny':False,'ivs':ivs,'held_item':None,'choice_lock':None}


def _npc_bot_choice(state:dict)->dict:
    bot_id=str(state.get('bot_player_id'))
    bot=state['players'][bot_id]; mon=bot['mons'][bot['active']]
    usable=[m for m in mon.get('moves',[]) if m in MOVES and int(mon.get('pp',{}).get(m,0))>0]
    if not usable:
        usable=[m for m in mon.get('moves',[]) if m in MOVES]
        if usable:mon.setdefault('pp',{})[usable[0]]=1
    if not usable:return {'type':'move','move':next(iter(MOVES))}
    damaging=[m for m in usable if MOVES[m][5] in ('damage','drain','fixed','fixed40')]
    return {'type':'move','move':random.choice(damaging if damaging and random.random()<0.82 else usable)}


def _leader_completion_rewards_cursor(c,uid:int,chat_id:int,thread_id:int|None,selected_levels:list[int]):
    c.execute("SELECT COUNT(*) FROM pokemon_badges_tb WHERE user_id=%s",(uid,)); count=int(c.fetchone()[0])
    if count<8:return None
    c.execute("INSERT INTO pokemon_kanto_completion_tb(user_id) VALUES(%s) ON CONFLICT DO NOTHING RETURNING user_id",(uid,)); first=c.fetchone()
    if not first:return None
    c.execute("UPDATE usuarios_tb SET saldo=saldo+10000 WHERE id_user=%s",(uid,))
    grant_item_with_cursor(c,uid,'rare_candy',10)
    season_key=f'kanto_complete:{uid}'
    c.execute("INSERT INTO pokemon_season_boxes_tb(owner_id,season_key,placement) VALUES(%s,%s,1) ON CONFLICT(owner_id,season_key) DO NOTHING",(uid,season_key))
    # Gen 1 legendarios del sistema: Articuno, Zapdos, Moltres, Mewtwo y Mew.
    allowed=[x for x in (144,145,146,150,151) if x in set(int(v) for v in LEGENDARY_IDS)] or [144,145,146,150,151]
    species=random.choice(allowed)
    avg=max(1,min(MAX_LEVEL,round(sum(selected_levels)/max(1,len(selected_levels)))))
    level=max(1,min(MAX_LEVEL,avg+random.choice([0,1,2])))
    shiny=(random.randrange(LEGENDARY_SPECIAL_SHINY_DENOMINATOR)==0)
    c.execute("""INSERT INTO pokemon_legendary_encounters_tb(owner_id,chat_id,thread_id,species_id,level,shiny,max_attempts)
                 VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING encounter_id""",
              (uid,chat_id,thread_id,species,level,shiny,LEGENDARY_SPECIAL_MAX_ATTEMPTS))
    return {'encounter_id':int(c.fetchone()[0]),'species':species,'level':level,'shiny':shiny}


def _finish_npc_battle_cursor(c,bid:int,state:dict)->dict:
    uid=int(state['human_user_id']); won=int(state['winner'])==uid; mode=int(state['mode']); kind=state.get('battle_kind','npc'); eid=int(state['npc_encounter_id'])
    c.execute("SELECT chat_id,thread_id,npc_key,event_ref,encounter_type FROM pokemon_npc_encounters_tb WHERE encounter_id=%s FOR UPDATE",(eid,)); er=c.fetchone()
    chat_id=int(er[0]) if er else int(state.get('chat_id',0)); thread_id=er[1] if er else None; npc_key=str(er[2]) if er else str(state.get('npc_key','')); event_ref=int(er[3]) if er and er[3] is not None else None; encounter_type=str(er[4]) if er and er[4] is not None else ''
    bot_levels=[int(m.get('level',1)) for m in state.get('players',{}).get(str(state.get('bot_player_id')),{}).get('mons',[])]; rival_avg=max(1,round(sum(bot_levels)/len(bot_levels))) if bot_levels else 1; xp=_combat_xp_amount(rival_avg,won,'leader' if kind=='leader' else 'npc')
    pipes=(LEADER_WIN_PIPESOS if kind=='leader' else NPC_NORMAL_WIN_PIPESOS.get(mode,1500)) if won else (LEADER_LOSS_PIPESOS if kind=='leader' else NPC_NORMAL_LOSS_PIPESOS)
    notes=[]; selected=[]; selected_levels=[]
    human=state['players'][str(uid)]
    for mon in human['mons']:
        selected.append(int(mon['pid'])); selected_levels.append(int(mon['level'])); notes += _grant_pokemon_xp_cursor(c,int(mon['pid']),xp)
    c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(pipes,uid))
    # Halloween: NPC/líderes pueden soltar dulces por cada rival que realmente cayó.
    bot=state.get('players',{}).get(str(state.get('bot_player_id')),{})
    defeated_species=[int(m.get('species',0)) for m in bot.get('mons',[]) if int(m.get('hp',0))<=0]
    halloween_candies=_halloween_award_species_cursor(c,uid,defeated_species)
    halloween_bonus=0; halloween_object_box=False; halloween_box=None
    if won and npc_key=='halloween_trainer' and _halloween_active():
        halloween_bonus=random.randint(10,20); _halloween_add_candies_cursor(c,uid,halloween_bonus)
        if random.random()<0.25:
            grant_item_with_cursor(c,uid,'object_box',1); halloween_object_box=True
        if random.random()<0.12 and _egg_slots_used_cursor(c,uid)<EGG_MAX_ACTIVE:
            _create_cursed_egg_cursor(c,uid,'halloween_npc'); halloween_box='cursed_egg'
    elif won and npc_key=='halloween_boss' and _halloween_active():
        halloween_bonus=random.randint(25,40); _halloween_add_candies_cursor(c,uid,halloween_bonus)
        grant_item_with_cursor(c,uid,'object_box',1); halloween_object_box=True
        # Pikachu Halloween es exclusivo de la tienda; el jefe nunca lo regala.
        if random.random()<0.22:
            halloween_box=_grant_halloween_box_cursor(c,uid)
    rocket_event=None; rocket_drop=None; league_stage=None; league_champion=False
    if won and npc_key in ROCKET_EVENT_NPCS and event_ref is not None:
        c.execute("SELECT stage,status,expires_at FROM pokemon_rocket_events_tb WHERE event_id=%s FOR UPDATE",(event_ref,)); rr=c.fetchone()
        if rr and str(rr[1])=='active' and rr[2]>datetime.now(timezone.utc):
            expected=ROCKET_WAVES[min(int(rr[0]),len(ROCKET_WAVES)-1)]
            if expected==npc_key:
                newstage=int(rr[0])+1; finished=newstage>=len(ROCKET_WAVES)
                c.execute("UPDATE pokemon_rocket_events_tb SET stage=%s,status=%s,finished_at=CASE WHEN %s THEN NOW() ELSE finished_at END WHERE event_id=%s",(newstage,'finished' if finished else 'active',finished,event_ref))
                c.execute("INSERT INTO pokemon_rocket_participants_tb(event_id,user_id,wins) VALUES(%s,%s,1) ON CONFLICT(event_id,user_id) DO UPDATE SET wins=pokemon_rocket_participants_tb.wins+1",(event_ref,uid))
                # Drops Rocket: cajas/objetos y bonus de PiPesos. Jessie/James dan más.
                bonus=3500 if npc_key in ('jessie_event','james_event') else 2000
                c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(bonus,uid)); pipes += bonus
                roll=random.random()
                if roll<0.04:
                    rocket_drop=_grant_normal_pibot_box_cursor(c,uid,'legendary')
                elif roll<0.18:
                    rocket_drop=_grant_normal_pibot_box_cursor(c,uid,'epic')
                elif roll<0.45:
                    grant_item_with_cursor(c,uid,'object_box',1); rocket_drop={'label':'🎁 Caja de Objetos Pokémon'}
                if finished:
                    # Bonus final a todos los que ayudaron en la invasión.
                    c.execute("SELECT user_id FROM pokemon_rocket_participants_tb WHERE event_id=%s",(event_ref,))
                    for (part_uid,) in c.fetchall():
                        c.execute("UPDATE usuarios_tb SET saldo=saldo+5000 WHERE id_user=%s",(int(part_uid),)); grant_item_with_cursor(c,int(part_uid),'rare_candy',1)
                rocket_event={'event_id':event_ref,'stage':newstage,'finished':finished}
        _mission_progress_cursor(c,uid,'win',1)
    if won and npc_key in LEAGUE_NPCS:
        c.execute("INSERT INTO pokemon_league_progress_tb(user_id) VALUES(%s) ON CONFLICT DO NOTHING",(uid,)); c.execute("SELECT stage,champion_done FROM pokemon_league_progress_tb WHERE user_id=%s FOR UPDATE",(uid,)); lr=c.fetchone() or (0,False)
        current=int(lr[0]); expected=LEAGUE_ORDER[min(current,len(LEAGUE_ORDER)-1)]
        if not bool(lr[1]) and expected==npc_key:
            nxt=current+1; league_champion=nxt>=len(LEAGUE_ORDER)
            c.execute("UPDATE pokemon_league_progress_tb SET stage=%s,champion_done=%s,updated_at=NOW() WHERE user_id=%s",(nxt,league_champion,uid))
            bonus=30000 if league_champion else 7500; c.execute("UPDATE usuarios_tb SET saldo=saldo+%s WHERE id_user=%s",(bonus,uid)); pipes += bonus
            grant_item_with_cursor(c,uid,'rare_candy',5 if league_champion else 2)
            if league_champion:
                season_key=f'league_champion:{uid}'
                c.execute("INSERT INTO pokemon_season_boxes_tb(owner_id,season_key,placement) VALUES(%s,%s,1) ON CONFLICT(owner_id,season_key) DO NOTHING",(uid,season_key))
            league_stage=nxt
        _mission_progress_cursor(c,uid,'win',1)
    badge_new=False; tm=None; candies=0; completion=None
    if won and npc_key not in ROCKET_EVENT_NPCS and npc_key not in LEAGUE_NPCS:_mission_progress_cursor(c,uid,'win',1)
    if won and kind=='leader':
        tm=random.choice(list(TM_ITEMS.keys())) if TM_ITEMS else None
        if tm:grant_item_with_cursor(c,uid,tm,1)
        candies=random.randint(1,3); grant_item_with_cursor(c,uid,'rare_candy',candies); grant_item_with_cursor(c,uid,'object_box',1)
        c.execute("INSERT INTO pokemon_badges_tb(user_id,leader_key) VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING leader_key",(uid,npc_key)); badge_new=bool(c.fetchone())
        c.execute("INSERT INTO pokemon_leader_bonus_tb(battle_id,user_id,eligible_pokemon_json) VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",(bid,uid,json.dumps(selected)))
        completion=_leader_completion_rewards_cursor(c,uid,chat_id,thread_id,selected_levels) if badge_new else None
    c.execute("UPDATE pokemon_npc_encounters_tb SET status='finished',finished_at=NOW() WHERE encounter_id=%s",(eid,))
    c.execute("UPDATE pokemon_battles_tb SET status='finished',winner_id=%s,state_json=%s,finished_at=NOW(),updated_at=NOW() WHERE battle_id=%s",(int(state['winner']),json.dumps(state,ensure_ascii=False),bid))
    return {'npc':True,'leader':kind=='leader','won':won,'winner':int(state['winner']),'loser':int(state['loser']),'uid':uid,'xp':xp,'pipesos':pipes,
            'notes':notes,'npc_key':npc_key,'badge_new':badge_new,'tm':tm,'candies':candies,'object_box':bool(won and kind=='leader'),
            'bonus_pids':selected if won and kind=='leader' else [],'completion':completion,'chat_id':chat_id,'thread_id':thread_id,
            'halloween_candies':halloween_candies,'halloween_bonus':halloween_bonus,'halloween_object_box':halloween_object_box,
            'halloween_box':halloween_box,'rocket_event':rocket_event,'rocket_drop':rocket_drop,
            'league_stage':league_stage,'league_champion':league_champion}


def _npc_result_lines(final:dict)->list[str]:
    d=NPC_ALL.get(final.get('npc_key'),{}); name=d.get('name','Entrenador')
    lines=[f"{'🏆 Victoria' if final.get('won') else '💥 Derrota'} contra {name}.",f"💰 +{int(final.get('pipesos',0)):,} PiPesos",f"⭐ +{int(final.get('xp',0))} XP por Pokémon usado"]
    if int(final.get('halloween_candies',0))>0:
        lines.append(f"🎃🍬 Pokémon derrotados: +{int(final['halloween_candies'])} Dulces Halloween")
    if int(final.get('halloween_bonus',0))>0:
        lines.append(f"🎃 Bonus del evento: +{int(final['halloween_bonus'])} Dulces Halloween")
    if final.get('halloween_object_box'):
        lines.append('🎁 +1 Caja de Objetos Pokémon')
    if isinstance(final.get('halloween_box'),dict):
        hb=final['halloween_box']; lines.append(f"🎃📦 Premio del jefe: {'✨ SHINY ' if hb.get('shiny') else ''}{hb.get('name','Pokémon')}")
    elif final.get('halloween_box')=='cursed_egg':
        lines.append('🎃🥚 ¡Encontraste un Huevo Maldito!')
    if final.get('rocket_event'):
        re=final['rocket_event']; lines.append(f"🚀 Invasión Rocket: {int(re.get('stage',0))}/4 derrotados")
        if final.get('rocket_drop'):
            rd=final['rocket_drop']
            if isinstance(rd,dict) and rd.get('code') in ('epic','legendary'):
                boxname='💜 Caja Épica de PiBot' if rd.get('code')=='epic' else '🌟 Caja Legendaria de PiBot'
                lines.append(f"🎁 Drop Rocket: {boxname} → {rd.get('label','premio')}")
            else:lines.append(f"🎁 Drop Rocket: {rd.get('label','Premio especial') if isinstance(rd,dict) else rd}")
        if re.get('finished'):lines += ['🏆 ¡Team Rocket fue derrotado!', '🎁 Todos los participantes: +5,000 PiPesos + 1 Caramelo Raro']
    if final.get('league_stage') is not None:
        if final.get('league_champion'):lines += ['👑 ¡DERROTASTE AL CAMPEÓN DE KANTO!', '💰 Bonus Liga incluido: +30,000 PiPesos', '📦 +1 Caja Pokémon Shiny garantizada', '🍬 +5 Caramelos Raros']
        else:lines.append(f"👑 Liga Kanto: fase {int(final['league_stage'])}/5 superada · +7,500 PiPesos +2 Caramelos Raros")
    if final.get('leader') and final.get('won'):
        if final.get('tm') in ITEMS:
            n,e,_,_=ITEMS[final['tm']]; lines.append(f'💿 MT: {e} {n}')
        lines.append(f"🍬 +{int(final.get('candies',0))} Caramelos Raros")
        lines.append('🎁 +1 Caja de Objetos Pokémon')
        if final.get('badge_new'):
            lines.append(f"{d.get('badge_emoji','🏅')} Nueva medalla: {d.get('badge','Medalla')}")
        lines.append(f'⭐ Elige uno de tus Pokémon usados para +{LEADER_BONUS_XP} XP extra.')
    lines += list(final.get('notes',[]))[:6]
    if final.get('completion'):
        lines += ['', '🏆 ¡KANTO COMPLETADO!', '📦 +1 Caja Pokémon con SHINY garantizado', '💰 +10,000 PiPesos', '🍬 +10 Caramelos Raros', '🌟 Se abrió tu encuentro legendario especial.']
    return lines


def _leader_bonus_markup(bid:int,pids:list[int]):
    conn=_get_connection(); rows=[]
    try:
        c=conn.cursor(); c.execute("SELECT user_id FROM pokemon_leader_bonus_tb WHERE battle_id=%s",(bid,)); owner_row=c.fetchone(); owner=int(owner_row[0]) if owner_row else None
        for pid in pids:
            c.execute("SELECT species_id,nickname,level,shiny FROM pokemon_instances_tb WHERE pokemon_id=%s AND owner_id=%s",(pid,owner)); r=c.fetchone() if owner is not None else None
            if r:rows.append([InlineKeyboardButton(f"⭐ {r[1] or NAMES[int(r[0])]} · Nv.{int(r[2])}",callback_data=f'pk:npcbonus:{bid}:{pid}')])
    finally:_put_connection(conn)
    return InlineKeyboardMarkup(rows) if rows else None


async def _send_npc_encounter(context:ContextTypes.DEFAULT_TYPE,eid:int)->bool:
    conn=_get_connection(); row=None; media=(None,None)
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,npc_key,encounter_type,mode,status FROM pokemon_npc_encounters_tb WHERE encounter_id=%s",(eid,)); row=c.fetchone()
        if row:media=_npc_media_for_key_cursor(c,str(row[2]))
    finally:_put_connection(conn)
    if not row:return False
    chat_id,thread_id,key,kind,mode,status=int(row[0]),row[1],str(row[2]),str(row[3]),int(row[4]),str(row[5])
    if status!='active':return False
    d=NPC_ALL[key]
    if key=='halloween_trainer':
        text=(f"🎃 ¡UN ENTRENADOR DE HALLOWEEN HA APARECIDO!\n\n{d['emoji']} {d['name']}\n⚔️ Combate {mode}v{mode}\n"
              "👻 Equipo temático Fantasma/Sombras\n🍬 Victoria: bonus de Dulces Halloween y posibilidad de Caja de Objetos.\n⏳ Disponible durante 10 minutos.")
    elif key=='halloween_boss':
        text=(f"💀 JEFE DE HALLOWEEN\n\n{d['emoji']} {d['name']}\n⚔️ Combate {mode}v{mode}\n"
              "🎃 Un reto especial del evento.\n🍬 Victoria: gran bonus de Dulces + Caja de Objetos.\n⏳ Disponible durante 10 minutos.")
    elif kind=='leader':
        text=(f"🏟️ ¡UN LÍDER DE GIMNASIO HA APARECIDO!\n\n{d['emoji']} {d['name']} · {d['city']}\n"
              f"⚔️ Combate {mode}v{mode}\n⏳ Disponible durante 10 minutos\n\n🎁 Victoria: PiPesos, mucha XP, MT, Caramelos Raros y Caja de Objetos.")
    elif key in ROCKET_EVENT_NPCS:
        text=(f"🚀 INVASIÓN TEAM ROCKET\n\n{d['emoji']} {d['name']}\n⚔️ Combate {mode}v{mode}\n"
              "⏳ Forma parte del evento grupal de 30 minutos.\n🎁 Puede soltar Caja de Objetos o premios de las cajas normales de PiBot.")
    elif key in LEAGUE_NPCS:
        text=(f"👑 LIGA POKÉMON DE KANTO\n\n{d['emoji']} {d['name']}\n⚔️ Combate {mode}v{mode}\n"
              "🔥 Sus Pokémon salen por encima del nivel de tu equipo.\n🏆 Vence para avanzar al siguiente miembro de la Liga.")
    else:
        text=(f"👤 ¡UN ENTRENADOR HA APARECIDO!\n\n{d['emoji']} {d['name']}\n⚔️ Combate {mode}v{mode}\n"
              f"⏳ Disponible durante 10 minutos\n📈 Sus Pokémon estarán a tu nivel, +1 o +2.")
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('⚔️ Desafiar',callback_data=f'pk:npcclaim:{eid}')]])
    try:
        mt,fid=media
        if mt=='animation' and fid:msg=await context.bot.send_animation(chat_id=chat_id,animation=fid,caption=text,message_thread_id=thread_id,reply_markup=kb)
        elif mt=='photo' and fid:msg=await context.bot.send_photo(chat_id=chat_id,photo=fid,caption=text,message_thread_id=thread_id,reply_markup=kb)
        else:msg=await context.bot.send_message(chat_id=chat_id,text=text,message_thread_id=thread_id,reply_markup=kb)
    except Exception as e:
        print('[PK NPC send]',type(e).__name__,e); return False
    conn=_get_connection()
    try:c=conn.cursor(); c.execute("UPDATE pokemon_npc_encounters_tb SET message_id=%s WHERE encounter_id=%s",(msg.message_id,eid)); conn.commit()
    except Exception:conn.rollback()
    finally:_put_connection(conn)
    try:
        if context.job_queue:context.job_queue.run_once(_expire_npc_encounter,(ROCKET_EVENT_SECONDS if key in ROCKET_EVENT_NPCS or key in LEAGUE_NPCS else NPC_LIFETIME_SECONDS),data={'encounter_id':eid},name=f'pk_npc_expire:{eid}')
    except Exception as e:print('[PK NPC expiry schedule]',type(e).__name__,e)
    return True


async def _expire_npc_encounter(context:ContextTypes.DEFAULT_TYPE):
    eid=int((getattr(context.job,'data',None) or {}).get('encounter_id') or 0)
    if not eid:return
    conn=_get_connection(); row=None; media=(None,None)
    try:
        c=conn.cursor(); c.execute("SELECT chat_id,thread_id,npc_key,status,message_id FROM pokemon_npc_encounters_tb WHERE encounter_id=%s FOR UPDATE",(eid,)); row=c.fetchone()
        if not row or row[3] not in ('active','selecting'):conn.rollback(); return
        c.execute("UPDATE pokemon_npc_encounters_tb SET status='expired',finished_at=NOW() WHERE encounter_id=%s",(eid,)); media=_npc_media_for_key_cursor(c,str(row[2])); conn.commit()
    except Exception as e:conn.rollback(); print('[PK NPC expire]',type(e).__name__,e); return
    finally:_put_connection(conn)
    text=f"⌛ {_npc_label(str(row[2]))} se retiró. El encuentro terminó."
    try:
        if media[0] in ('photo','animation'):await context.bot.edit_message_caption(chat_id=int(row[0]),message_id=int(row[4]),caption=text,reply_markup=None)
        else:await context.bot.edit_message_text(chat_id=int(row[0]),message_id=int(row[4]),text=text,reply_markup=None)
    except Exception:pass


async def _spawn_npc_encounter(context:ContextTypes.DEFAULT_TYPE,chat_id:int,thread_id:int|None,kind:str='normal',forced_key:str|None=None)->bool:
    conn=_get_connection(); eid=None
    try:
        c=conn.cursor()
        if kind=='normal':
            if not forced_key:
                c.execute("SELECT 1 FROM pokemon_npc_encounters_tb WHERE chat_id=%s AND thread_id IS NOT DISTINCT FROM %s AND encounter_type='normal' AND is_manual=FALSE AND created_at>NOW()-INTERVAL '50 minutes' LIMIT 1",(chat_id,thread_id))
                if c.fetchone():conn.rollback(); return False
            key=forced_key if forced_key in NPC_NORMALS else random.choice(list(NPC_NORMALS)); mode=random.choice([1,2])
        else:
            today=_today_pokemon_date()
            c.execute("SELECT 1 FROM pokemon_npc_encounters_tb WHERE chat_id=%s AND thread_id IS NOT DISTINCT FROM %s AND encounter_type='leader' AND is_manual=FALSE AND (created_at AT TIME ZONE 'America/Mexico_City')::date=%s LIMIT 1",(chat_id,thread_id,today))
            if c.fetchone() and not forced_key:conn.rollback(); return False
            key=forced_key if forced_key in KANTO_LEADERS else random.choice(list(KANTO_LEADERS)); mode=3
        c.execute("INSERT INTO pokemon_npc_encounters_tb(chat_id,thread_id,npc_key,encounter_type,mode,is_manual) VALUES(%s,%s,%s,%s,%s,%s) RETURNING encounter_id",(chat_id,thread_id,key,kind,mode,bool(forced_key))); eid=int(c.fetchone()[0]); conn.commit()
    except Exception as e:conn.rollback(); print('[PK NPC spawn]',type(e).__name__,e); return False
    finally:_put_connection(conn)
    return await _send_npc_encounter(context,eid)


async def _spawn_halloween_special_npc(context:ContextTypes.DEFAULT_TYPE,chat_id:int,thread_id:int|None,key:str,manual:bool=False)->bool:
    if key not in HALLOWEEN_NPCS:return False
    if not manual and not _halloween_active():return False
    conn=_get_connection(); eid=None
    try:
        c=conn.cursor(); today=_today_pokemon_date()
        if not manual:
            c.execute("""SELECT 1 FROM pokemon_npc_encounters_tb
                         WHERE chat_id=%s AND thread_id IS NOT DISTINCT FROM %s AND npc_key=%s
                           AND is_manual=FALSE AND (created_at AT TIME ZONE 'America/Mexico_City')::date=%s LIMIT 1""",
                      (chat_id,thread_id,key,today))
            if c.fetchone():conn.rollback(); return False
        mode=int(HALLOWEEN_NPCS[key].get('event_mode',3))
        c.execute("INSERT INTO pokemon_npc_encounters_tb(chat_id,thread_id,npc_key,encounter_type,mode,is_manual) VALUES(%s,%s,%s,'normal',%s,%s) RETURNING encounter_id",
                  (chat_id,thread_id,key,mode,bool(manual))); eid=int(c.fetchone()[0]); conn.commit()
    except Exception as e:conn.rollback(); print('[PK Halloween NPC spawn]',type(e).__name__,e); return False
    finally:_put_connection(conn)
    return await _send_npc_encounter(context,eid)


async def pokemon_npc_spawn_job(context:ContextTypes.DEFAULT_TYPE):
    for community in COMUNIDADES:
        try:
            chat_id=int(community.get('id_comunidad')); thread_id=_games_topic(chat_id)
            if thread_id is not None:await _spawn_npc_encounter(context,chat_id,thread_id,'normal')
        except Exception as e:print('[PK NPC job]',type(e).__name__,e)


async def pokemon_leader_spawn_job(context:ContextTypes.DEFAULT_TYPE):
    for community in COMUNIDADES:
        try:
            chat_id=int(community.get('id_comunidad')); thread_id=_games_topic(chat_id)
            if thread_id is not None:await _spawn_npc_encounter(context,chat_id,thread_id,'leader')
        except Exception as e:print('[PK leader job]',type(e).__name__,e)


async def npcahora_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    try:
        if not is_botmaster(update.effective_user.id):return await update.effective_message.reply_text('Solo BotMaster puede forzar NPC.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede forzar NPC.')
    if not _is_games_topic(update):return await update.effective_message.reply_text('Usa /npcahora en Juegos y Casino.')
    key=(context.args[0].lower() if context.args else random.choice(list(NPC_NORMALS))); ok=await _spawn_npc_encounter(context,update.effective_chat.id,update.effective_message.message_thread_id,'normal',key)
    if not ok:await update.effective_message.reply_text('No pude crear el NPC o ya hubo uno recientemente.')


async def liderahora_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    try:
        if not is_botmaster(update.effective_user.id):return await update.effective_message.reply_text('Solo BotMaster puede forzar líderes.')
    except Exception:return await update.effective_message.reply_text('Solo BotMaster puede forzar líderes.')
    if not _is_games_topic(update):return await update.effective_message.reply_text('Usa /liderahora en Juegos y Casino.')
    raw=' '.join(context.args).strip().lower().replace('.','').replace(' ','_') if context.args else ''
    aliases={'surge':'lt_surge','lt_surge':'lt_surge','ltsurge':'lt_surge'}; key=aliases.get(raw,raw) if raw else random.choice(list(KANTO_LEADERS))
    ok=await _spawn_npc_encounter(context,update.effective_chat.id,update.effective_message.message_thread_id,'leader',key)
    if not ok:await update.effective_message.reply_text('No pude crear el líder.')


def _roll_object_box_reward_cursor(c,uid:int)->str:
    r=random.random()
    if r<MASTER_BALL_BOX_CHANCE:
        grant_item_with_cursor(c,uid,'master_ball',1); return '🟣 ¡MASTER BALL! ×1'
    r=(r-MASTER_BALL_BOX_CHANCE)/(1-MASTER_BALL_BOX_CHANCE)
    if r<0.38:
        code=_choose_held_by_source_rarity('raro') or random.choice(list(HELD_ITEMS)); grant_item_with_cursor(c,uid,code,1); x=HELD_ITEMS[code]; return f"{x['emoji']} {x['name']} ×1"
    if r<0.63 and TM_ITEMS:
        code=random.choice(list(TM_ITEMS)); grant_item_with_cursor(c,uid,code,1); info=ITEMS.get(code); return f"{info[1]} {info[0]} ×1" if info else f'💿 {code} ×1'
    if r<0.80:
        code=random.choice(list(STONE_CODES)); grant_item_with_cursor(c,uid,code,1); info=ITEMS.get(code); return f"{info[1]} {info[0]} ×1" if info else f'🪨 {code} ×1'
    qty=random.randint(1,3); grant_item_with_cursor(c,uid,'rare_candy',qty); return f'🍬 Caramelo Raro ×{qty}'


def _open_object_box(uid:int)->str|None:
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("SELECT qty FROM pokemon_items_tb WHERE owner_id=%s AND item_code='object_box' FOR UPDATE",(uid,)); r=c.fetchone()
        if not r or int(r[0])<=0:conn.rollback(); return None
        c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code='object_box'",(uid,)); reward=_roll_object_box_reward_cursor(c,uid); conn.commit(); return reward
    except Exception as e:conn.rollback(); print('[PK object box]',type(e).__name__,e); return None
    finally:_put_connection(conn)


async def cajaobjetospokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    reward=_open_object_box(update.effective_user.id)
    await update.effective_message.reply_text(f'🎁 CAJA DE OBJETOS POKÉMON\n\nTe salió: {reward}' if reward else '🎁 No tienes Cajas de Objetos Pokémon.')


def _legendary_public_text(row, revealed:bool=False)->str:
    eid,owner,chat,thread,species,level,shiny,attempts,max_attempts,status,msgid=row[:11]
    if not revealed:
        return f"🌟 ¡ENCUENTRO LEGENDARIO ESPECIAL!\n\n❓ Un Pokémon legendario desconocido apareció...\n🎲 Tienes {max_attempts} intentos.\n✨ Puede ser Shiny.\n⏳ Disponible durante 10 minutos."
    r=rarity_for(int(species)); shiny_line='✨ SHINY ✨\n' if shiny else ''
    return (f"🌟 ¡LEGENDARIO REVELADO!\n{shiny_line}{rarity_emoji(r)} #{int(species):03d} {NAMES[int(species)]} · Nv.{int(level)}\n{_types_text(int(species))}\n⭐ Rareza: {r.upper()}\n🎲 Intentos usados: {int(attempts)}/{int(max_attempts)}")


async def _announce_legendary_encounter(context:ContextTypes.DEFAULT_TYPE,eid:int):
    conn=_get_connection(); row=None
    try:
        c=conn.cursor(); c.execute("SELECT encounter_id,owner_id,chat_id,thread_id,species_id,level,shiny,attempts,max_attempts,status,message_id FROM pokemon_legendary_encounters_tb WHERE encounter_id=%s",(eid,)); row=c.fetchone()
    finally:_put_connection(conn)
    if not row:return
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('🎯 Atrapar',callback_data=f'pk:leg:{eid}')]])
    try:msg=await context.bot.send_message(chat_id=int(row[2]),message_thread_id=row[3],text=_legendary_public_text(row,False),reply_markup=kb)
    except Exception as e:print('[PK legendary announce]',type(e).__name__,e); return
    conn=_get_connection()
    try:c=conn.cursor(); c.execute("UPDATE pokemon_legendary_encounters_tb SET message_id=%s WHERE encounter_id=%s",(msg.message_id,eid)); conn.commit()
    except Exception:conn.rollback()
    finally:_put_connection(conn)
    try:
        if context.job_queue:context.job_queue.run_once(_expire_legendary_encounter,NPC_LIFETIME_SECONDS,data={'encounter_id':eid},name=f'pk_leg_expire:{eid}')
    except Exception:pass


async def _expire_legendary_encounter(context:ContextTypes.DEFAULT_TYPE):
    eid=int((getattr(context.job,'data',None) or {}).get('encounter_id') or 0); conn=_get_connection(); row=None
    try:
        c=conn.cursor(); c.execute("SELECT encounter_id,owner_id,chat_id,thread_id,species_id,level,shiny,attempts,max_attempts,status,message_id FROM pokemon_legendary_encounters_tb WHERE encounter_id=%s FOR UPDATE",(eid,)); row=c.fetchone()
        if not row or row[9] not in ('active','revealed'):conn.rollback(); return
        c.execute("UPDATE pokemon_legendary_encounters_tb SET status='expired',finished_at=NOW() WHERE encounter_id=%s",(eid,)); conn.commit()
    except Exception:conn.rollback(); return
    finally:_put_connection(conn)
    try:await context.bot.edit_message_text(chat_id=int(row[2]),message_id=int(row[10]),text='⌛ El encuentro legendario terminó.\n\n'+_legendary_public_text(row,True),reply_markup=None)
    except Exception:pass


# -------- Batallas dobles 4v4 --------

def _double_required_actions(state:dict,uid:str)->int:
    p=state['players'][uid]
    return sum(1 for idx in p.get('active',[]) if 0 <= int(idx) < len(p['mons']) and p['mons'][int(idx)]['hp']>0)


def _double_text(state:dict,note:str|None=None)->str:
    ids=list(state['players']); a=state['players'][ids[0]]; b=state['players'][ids[1]]
    def active_lines(p):
        out=[]
        for n,idx in enumerate(p.get('active',[]),1):
            m=p['mons'][idx]
            if m['hp']>0:
                pct=max(0,min(1,m['hp']/max(1,m['max_hp']))); full=round(pct*10); bar='█'*full+'░'*(10-full)
                out.append(f"{n}. {_battle_title_mon(m)} Nv.{m['level']} · ❤️ {m['hp']}/{m['max_hp']} {bar}")
            else:out.append(f"{n}. 💫 {_battle_title_mon(m)} · debilitado")
        return out
    lines=['⚔️ BATALLA DOBLE POKÉMON · 4v4','',f"{a['name']}:",*active_lines(a),'',f"{b['name']}:",*active_lines(b),'',f"🔁 Ronda {state.get('round',1)}"]
    if note:lines += ['',note]
    if state.get('status')=='active':
        ch=state.get('choices',{})
        a_ready=len(ch.get(ids[0],{}))>=_double_required_actions(state,ids[0])
        b_ready=len(ch.get(ids[1],{}))>=_double_required_actions(state,ids[1])
        lines += ['',f"Elecciones: {'✅' if a_ready else '⌛'} {a['name']} · {'✅' if b_ready else '⌛'} {b['name']}"]
    return '\n'.join(lines)


def _double_group_markup(bid:int):
    return InlineKeyboardMarkup([[InlineKeyboardButton('⚔️ Elegir acciones',callback_data=f'pk:daction:{bid}')],[InlineKeyboardButton('🏳 Rendirse',callback_data=f'pk:dsurrender:{bid}')]])


def _double_private_markup(bid:int,state:dict,uid:int,final:bool=False):
    key=str(uid)
    if final or state.get('status')!='active' or key not in state.get('players',{}):return None
    pl=state['players'][key]; need=list(state.get('replacement_needed',{}).get(key,[]))
    rows=[]
    if need:
        pos=int(need[0]); candidates=[i for i,m in enumerate(pl['mons']) if m['hp']>0 and i not in pl.get('active',[])]
        for i in candidates:
            rows.append([InlineKeyboardButton(f"➡️ Reemplazar por {_battle_title_mon(pl['mons'][i])}",callback_data=f'pk:dreplace:{bid}:{pos}:{i}')])
        return InlineKeyboardMarkup(rows) if rows else None
    chosen=state.get('choices',{}).get(key,{})
    for pos,idx in enumerate(pl.get('active',[])):
        mon=pl['mons'][idx]
        if mon.get('hp',0)<=0:continue
        if str(pos) in chosen:
            rows.append([InlineKeyboardButton(f"✅ {pos+1}. {_battle_title_mon(mon)} · acción lista",callback_data='pk:noop')])
        else:
            rows.append([InlineKeyboardButton(f"⚔️ {pos+1}. {_battle_title_mon(mon)}",callback_data=f'pk:dmon:{bid}:{pos}'),InlineKeyboardButton('🔄 Cambiar',callback_data=f'pk:dswitchmenu:{bid}:{pos}')])
    rows.append([InlineKeyboardButton('🏳 Rendirse',callback_data=f'pk:dsurrender:{bid}')])
    return InlineKeyboardMarkup(rows)


def _double_private_text(state:dict,uid:int,note:str|None=None,final:bool=False)->str:
    text=_double_text(state,note)
    if final:return text+"\n\n🏁 Batalla terminada."
    key=str(uid)
    if state.get('replacement_needed',{}).get(key):return text+"\n\n💫 Elige el reemplazo de tu Pokémon debilitado."
    needed=_double_required_actions(state,key) if key in state.get('players',{}) else 0
    chosen=len(state.get('choices',{}).get(key,{}))
    if chosen>=needed and needed>0:return text+"\n\n✅ Tus acciones están registradas. Esperando al rival…"
    return text+"\n\n🔒 Movimientos y objetivos se eligen únicamente aquí.\n👇 Elige las acciones pendientes:"

async def _sync_double_battle_views(context,bid:int,state:dict,chat_id:int,thread_id,message_id:int|None,note:str|None=None,final:bool=False):
    public_text=_double_text(state,note); public_markup=None if final else _double_group_markup(bid); public_mid=message_id; edited=False
    if message_id:
        try:
            await context.bot.edit_message_text(chat_id=int(chat_id),message_id=int(message_id),text=public_text,reply_markup=public_markup); edited=True
        except Exception as e:
            if 'not modified' in str(e).lower():edited=True
    if not edited:
        try:
            msg=await context.bot.send_message(chat_id=int(chat_id),text=public_text,message_thread_id=thread_id,reply_markup=public_markup)
            public_mid=int(msg.message_id); await _store_battle_public_message_id(bid,public_mid)
        except Exception:pass
    for human in _human_battle_ids(state):
        await _set_private_battle_view(context,bid,human,_double_private_text(state,human,note,final),_double_private_markup(bid,state,human,final),final)
    return public_mid


async def _update_double_public_final(context,bid:int,state:dict,chat_id:int,thread_id,message_id:int|None,note:str|None,result_text:str):
    """Garantiza que el resultado final doble quede visible en el grupo."""
    text=_double_text(state,note) + "\n\n🏁 Batalla terminada.\n\n" + str(result_text)
    edited=False
    if message_id:
        try:
            await context.bot.edit_message_text(chat_id=int(chat_id),message_id=int(message_id),text=text,reply_markup=None)
            edited=True
        except Exception as e:
            if 'not modified' in str(e).lower():edited=True
    if not edited:
        try:
            msg=await context.bot.send_message(chat_id=int(chat_id),text=text,message_thread_id=thread_id)
            await _store_battle_public_message_id(bid,int(msg.message_id))
            return int(msg.message_id)
        except Exception as e:
            print('[PK double public final]',type(e).__name__,e)
            return None
    return int(message_id) if message_id else None


async def _sync_double_private_only(context,bid:int,state:dict,uid:int,note:str|None=None):
    return await _set_private_battle_view(context,bid,uid,_double_private_text(state,uid,note,False),_double_private_markup(bid,state,uid,False),False)


def _double_lead_markup(bid:int,state:dict,uid:int):
    key=str(uid); selected=[int(x) for x in state.setdefault('double_leads',{}).get(key,[])]
    rows=[]
    for i,m in enumerate(state['players'][key]['mons']):
        mark='✅' if i in selected else '⬜'; rows.append([InlineKeyboardButton(f"{mark} {_battle_title_mon(m)} · Nv.{m['level']}",callback_data=f'pk:dlead:{bid}:{i}')])
    if len(selected)==2:rows.append([InlineKeyboardButton('✅ Confirmar pareja inicial',callback_data=f'pk:dleadok:{bid}')])
    return InlineKeyboardMarkup(rows)


def _double_mon_action_markup(bid:int,state:dict,uid:int,pos:int):
    p=state['players'][str(uid)]; idx=p['active'][pos]; mon=p['mons'][idx]; rows=[]
    locked=mon.get('choice_lock') if mon.get('held_item') in ('choice_band','choice_specs','choice_scarf') else None
    for mi,code in enumerate(mon.get('moves',[])):
        if code in MOVES and (not locked or code==locked) and int(mon.get('pp',{}).get(code,MOVES[code][4]))>0:
            name,tp,_,_,pp,_=MOVES[code]; rows.append([InlineKeyboardButton(f"{type_emoji(tp)} {name} · {_battle_type_label(tp)} · PP {int(mon['pp'].get(code,pp))}/{pp}",callback_data=f'pk:dmove:{bid}:{pos}:{mi}')])
    rows.append([InlineKeyboardButton('🔄 Cambiar Pokémon',callback_data=f'pk:dswitchmenu:{bid}:{pos}')])
    return InlineKeyboardMarkup(rows)


def _double_replacement_needed(state:dict,uid:str)->list[int]:
    p=state['players'][uid]; return [pos for pos,idx in enumerate(p.get('active',[])) if p['mons'][idx]['hp']<=0]


def _double_fill_forced_replacements(state:dict):
    need={}
    for uid,p in state['players'].items():
        for pos in list(_double_replacement_needed(state,uid)):
            candidates=[i for i,m in enumerate(p['mons']) if m['hp']>0 and i not in p['active']]
            if len(candidates)==1:p['active'][pos]=candidates[0]
            elif len(candidates)>1:need.setdefault(uid,[]).append(pos)
    state['replacement_needed']=need
    return need


def _resolve_double_round_cursor(c,bid:int,state:dict):
    ids=list(state['players']); choices=state.get('choices',{})
    if any(len(choices.get(uid,{}))<_double_required_actions(state,uid) for uid in ids):return None,[],state
    actions=[]
    for uid in ids:
        p=state['players'][uid]
        for pos in (0,1):
            ch=choices[uid].get(str(pos));
            if not ch:continue
            src=int(ch.get('source',p['active'][pos])); mon=p['mons'][src]
            speed=9999 if ch['type']=='switch' else _effective_speed(mon)+(1000 if ch.get('move')=='quick_attack' else 0)
            if ch['type']=='move' and mon.get('held_item')=='quick_claw' and random.random()<0.20:speed+=5000
            actions.append((speed,random.random(),uid,pos,ch))
    actions.sort(reverse=True); logs=[]
    for _,__,uid,pos,ch in actions:
        if state.get('status')!='active':break
        p=state['players'][uid]; oppid=ids[1] if uid==ids[0] else ids[0]; o=state['players'][oppid]
        if pos>=len(p['active']):continue
        src=int(ch.get('source',p['active'][pos]))
        if p['active'][pos]!=src or p['mons'][src]['hp']<=0:continue
        mon=p['mons'][src]
        if ch['type']=='switch':
            new=int(ch['index'])
            if 0<=new<len(p['mons']) and p['mons'][new]['hp']>0 and new not in p['active']:
                mon['choice_lock']=None; p['active'][pos]=new; logs.append(f"🔄 {p['name']} cambió a {_battle_title_mon(p['mons'][new])}.")
            continue
        code=ch.get('move'); pp=int(mon.get('pp',{}).get(code,0))
        if pp<=0:logs.append(f"⚠️ {_battle_title_mon(mon)} no tenía PP."); continue
        tpos=int(ch.get('target',0)); viable=[i for i,idx in enumerate(o['active']) if o['mons'][idx]['hp']>0]
        if not viable:state['status']='finished'; state['winner']=uid; state['loser']=oppid; break
        if tpos not in viable:tpos=viable[0]
        target=o['mons'][o['active'][tpos]]; mon['pp'][code]=pp-1; logs += _do_move(mon,target,code)
        if target['hp']<=0:target['choice_lock']=None; logs.append(f"💫 {_battle_title_mon(target)} quedó debilitado.")
        if mon['hp']<=0:mon['choice_lock']=None; logs.append(f"💫 {_battle_title_mon(mon)} quedó debilitado.")
        if not any(m['hp']>0 for m in o['mons']):state['status']='finished'; state['winner']=uid; state['loser']=oppid; break
        if not any(m['hp']>0 for m in p['mons']):state['status']='finished'; state['winner']=oppid; state['loser']=uid; break
    if state.get('status')=='active':
        for uid in ids:
            p=state['players'][uid]
            for idx in list(dict.fromkeys(p['active'])):
                mon=p['mons'][idx]
                if mon['hp']>0 and mon.get('status')=='poison':
                    dmg=max(1,mon['max_hp']//8); mon['hp']=max(0,mon['hp']-dmg); logs.append(f"☠️ {_battle_title_mon(mon)} perdió {dmg} HP por veneno.")
                if mon['hp']>0 and mon.get('held_item')=='leftovers' and mon['hp']<mon['max_hp']:
                    heal=max(1,mon['max_hp']//16); old=mon['hp']; mon['hp']=min(mon['max_hp'],mon['hp']+heal); logs.append(f"🍎 Restos: {_battle_title_mon(mon)} recuperó {mon['hp']-old} HP.")
        for uid in ids:
            if not any(m['hp']>0 for m in state['players'][uid]['mons']):
                other=ids[1] if uid==ids[0] else ids[0]; state['status']='finished'; state['winner']=other; state['loser']=uid; break
    state['choices']={}; state['round']=int(state.get('round',1))+1
    if state.get('status')=='active':_double_fill_forced_replacements(state)
    return state.get('winner'),logs,state


async def batalladoblepokemon_command(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type=='private' or not _is_games_topic(update):return await update.effective_message.reply_text('⚔️ Las batallas dobles Pokémon se inician en Juegos y Casino.')
    uid=update.effective_user.id; target=_resolve_target(update,context)
    if target==uid:return await update.effective_message.reply_text('😂 No puedes retarte a ti mismo.')
    if target is None:return await update.effective_message.reply_text('Responde al mensaje de la otra persona con /batalladoblepokemon.')
    conn=_get_connection()
    try:
        c=conn.cursor()
        if _battle_busy_cursor(c,uid) or _battle_busy_cursor(c,target):conn.rollback(); return await update.effective_message.reply_text('⚔️ Uno de los dos ya tiene una batalla pendiente o activa.')
        c.execute("INSERT INTO pokemon_battles_tb(chat_id,thread_id,challenger_id,opponent_id,mode,status,state_json) VALUES(%s,%s,%s,%s,4,'open',%s) RETURNING battle_id",
                  (update.effective_chat.id,getattr(update.effective_message,'message_thread_id',None),uid,target,json.dumps({'battle_kind':'double_pvp','status':'open'}))); bid=int(c.fetchone()[0]); conn.commit()
    except Exception as e:conn.rollback(); print('[PK double create]',type(e).__name__,e); return await update.effective_message.reply_text('No pude crear la batalla doble.')
    finally:_put_connection(conn)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton('⚔️ Aceptar 4v4 doble',callback_data=f'pk:daccept:{bid}')],[InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:dcancel:{bid}')]])
    await update.effective_message.reply_text('⚔️ BATALLA DOBLE POKÉMON · 4v4\n\nDos Pokémon activos por lado y dos de reserva. Las acciones y objetivos se eligen por privado.',reply_markup=kb)


async def _pokemon_extended_callback(update:Update,context:ContextTypes.DEFAULT_TYPE,p:list[str],action:str,uid:int)->bool:
    q=update.callback_query
    # ---- Pokédex 151/151 ----
    if action=='dexclaim':
        conn=_get_connection(); data=None
        try:
            c=conn.cursor(); c.execute("SELECT COUNT(*) FROM pokemon_pokedex_tb WHERE owner_id=%s",(uid,)); dex=int(c.fetchone()[0])
            if dex<151:conn.rollback(); return await q.answer('Todavía no completas 151/151.',show_alert=True) or True
            c.execute("SELECT 1 FROM pokemon_dex_rewards_tb WHERE user_id=%s FOR UPDATE",(uid,))
            if c.fetchone():conn.rollback(); return await q.answer('Ya reclamaste esta recompensa.',show_alert=True) or True
            species=random.choice([144,145,146,150,151]); data=grant_pokemon_with_cursor(c,uid,species,'pokedex_151_legendary_shiny',force_shiny=True)
            c.execute("INSERT INTO pokemon_dex_rewards_tb(user_id,pokemon_id) VALUES(%s,%s)",(uid,int(data['pokemon_id']))); conn.commit()
        except Exception as e:conn.rollback(); print('[PK dex reward]',type(e).__name__,e); return await q.answer('No pude abrir la caja.',show_alert=True) or True
        finally:_put_connection(conn)
        await q.answer('✨ ¡LEGENDARIO SHINY!',show_alert=True)
        try:await q.edit_message_text(f"🎁 CAJA LEGENDARIA SHINY · POKÉDEX 151/151\n\n✨ #{int(data['species_id']):03d} SHINY {data['name']} {_sex_symbol(data.get('sex'))}\n⭐ Nv.{int(data['level'])} · 🧬 IV {int(data['iv_percent'])}% · {data['iv_grade']}\n\n👑 Recompensa única por completar Kanto.")
        except Exception:pass
        return True

    # ---- Zona Safari ----
    if action=='safbuy':
        if q.message.chat.type=='private':return await q.answer('La Zona Safari se usa en Juegos y Casino.',show_alert=True) or True
        conn=_get_connection(); row=None; paid=''
        try:
            c=conn.cursor(); old=_safari_session_cursor(c,uid,True)
            if old:conn.rollback(); await q.answer('Ya tienes tu Safari activo.',show_alert=True); return True
            c.execute("SELECT status FROM pokemon_safari_sessions_tb WHERE user_id=%s AND safari_date=%s",(uid,_today_pokemon_date()))
            if c.fetchone():conn.rollback(); await q.answer('Ya usaste tu entrada Safari de hoy.',show_alert=True); return True
            c.execute("SELECT qty FROM pokemon_items_tb WHERE owner_id=%s AND item_code='safari_ticket' FOR UPDATE",(uid,)); ticket=c.fetchone()
            if ticket and int(ticket[0])>0:
                c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code='safari_ticket'",(uid,)); paid='🎟️ Usaste un Pase Safari.'
            else:
                c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s AND saldo>=%s RETURNING saldo",(SAFARI_PASS_COST,uid,SAFARI_PASS_COST))
                if not c.fetchone():conn.rollback(); await q.answer('No tienes 10,000 PiPesos ni un Pase Safari.',show_alert=True); return True
                paid=f'💰 Pagaste {SAFARI_PASS_COST:,} PiPesos.'
            c.execute("INSERT INTO pokemon_safari_sessions_tb(user_id,chat_id,thread_id,safari_date,balls) VALUES(%s,%s,%s,%s,%s) RETURNING session_id,user_id,chat_id,thread_id,safari_date,status,balls,current_species,current_level,current_shiny,current_ivs_json,current_defeated,created_at,expires_at",(uid,q.message.chat_id,int(getattr(q.message,'message_thread_id',None) or 0),_today_pokemon_date(),SAFARI_START_BALLS)); row=c.fetchone(); conn.commit()
        except Exception as e:conn.rollback(); print('[PK safari buy]',type(e).__name__,e); return await q.answer('No pude abrir el Safari.',show_alert=True) or True
        finally:_put_connection(conn)
        await q.answer('🌿 ¡Entraste al Safari!')
        try:await q.edit_message_text(_safari_text(row)+'\n\n'+paid,reply_markup=_safari_markup(row))
        except Exception:pass
        return True
    if action in ('safexplore','safback','saffight','safskip','safbuyballs','safball'):
        sid=int(p[2]); conn=_get_connection(); row=None; result=None
        try:
            c=conn.cursor(); c.execute("SELECT session_id,user_id,chat_id,thread_id,safari_date,status,balls,current_species,current_level,current_shiny,current_ivs_json,current_defeated,created_at,expires_at FROM pokemon_safari_sessions_tb WHERE session_id=%s FOR UPDATE",(sid,)); row=c.fetchone()
            if not row or int(row[1])!=uid:conn.rollback(); return await q.answer('Ese Safari no es tuyo.',show_alert=True) or True
            if str(row[5])!='active' or row[13]<=datetime.now(timezone.utc):
                c.execute("UPDATE pokemon_safari_sessions_tb SET status='expired',finished_at=NOW() WHERE session_id=%s",(sid,)); conn.commit(); return await q.answer('Tu pase Safari ya terminó.',show_alert=True) or True
            if action=='safexplore':
                if row[7] is not None:conn.rollback(); return await q.answer('Ya tienes un Pokémon enfrente.',show_alert=True) or True
                sp=_safari_pool_species(); slots=_npc_team_slot_ids_cursor(c,uid); levels=[]
                for pid in slots:
                    c.execute("SELECT level FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); rr=c.fetchone()
                    if rr:levels.append(int(rr[0]))
                avg=round(sum(levels)/len(levels)) if levels else _starting_level(sp); bonus=random.randint(6,10) if int(sp) in set(int(x) for x in LEGENDARY_IDS) else random.randint(2,6); level=max(5,min(MAX_LEVEL,avg+bonus)); shiny=(random.randrange(SAFARI_SHINY_DENOMINATOR)==0)
                ivs=None
                for _ in range(20):
                    cand={k:random.randint(SAFARI_IV_MIN,15) for k in ('atk','def','spd','spc')}; cand['hp']=((cand['atk']&1)*8)+((cand['def']&1)*4)+((cand['spd']&1)*2)+(cand['spc']&1)
                    ivs=cand
                    if _iv_percent(cand)>=75:break
                if _iv_percent(ivs)<75:ivs={'atk':15,'def':15,'spd':15,'spc':15,'hp':15}
                c.execute("UPDATE pokemon_safari_sessions_tb SET current_species=%s,current_level=%s,current_shiny=%s,current_ivs_json=%s,current_defeated=FALSE WHERE session_id=%s",(sp,level,shiny,json.dumps(ivs),sid)); conn.commit(); row=list(row); row[7],row[8],row[9],row[10],row[11]=sp,level,shiny,json.dumps(ivs),False; row=tuple(row)
            elif action=='safskip':
                c.execute("UPDATE pokemon_safari_sessions_tb SET current_species=NULL,current_level=NULL,current_shiny=NULL,current_ivs_json=NULL,current_defeated=FALSE WHERE session_id=%s",(sid,)); conn.commit(); row=list(row); row[7]=row[8]=row[9]=row[10]=None; row[11]=False; row=tuple(row)
            elif action=='safbuyballs':
                conn.rollback(); return await q.answer('🔴 Las Safari Balls son limitadas. Cuando se acaban, termina la sesión.',show_alert=True) or True
            elif action=='saffight':
                if row[7] is None or bool(row[11]):conn.rollback(); return await q.answer('No necesitas pelear ahora.',show_alert=True) or True
                markup=_safari_team_markup_cursor(c,uid,sid); conn.rollback(); await q.answer();
                try:await q.edit_message_text(_safari_text(row)+'\n\nElige quién saldrá primero. Durante la pelea podrás cambiar entre tus Pokémon de /equipo:',reply_markup=markup)
                except Exception:pass
                return True
            elif action=='safball':
                if row[7] is None:conn.rollback(); return await q.answer('No tienes un Pokémon enfrente.',show_alert=True) or True
                if int(row[6])<=0:
                    c.execute("UPDATE pokemon_safari_sessions_tb SET status='exhausted',finished_at=NOW() WHERE session_id=%s",(sid,)); conn.commit(); return await q.answer('🔴 Se acabaron tus Safari Balls. Safari terminado.',show_alert=True) or True
                balls=int(row[6])-1; sp=int(row[7]); hp_ratio=0.0 if bool(row[11]) else 1.0; chance=_safari_capture_probability(sp,hp_ratio); caught=random.random()<chance
                end_session=(balls<=0)
                if caught:
                    ivs=json.loads(row[10] or '{}'); data=grant_pokemon_with_cursor(c,uid,sp,f'safari:{sid}',level_override=int(row[8]),shiny_override=bool(row[9]),ivs_override=ivs); _mission_progress_cursor(c,uid,'capture',1)
                    c.execute("UPDATE pokemon_safari_sessions_tb SET balls=%s,current_species=NULL,current_level=NULL,current_shiny=NULL,current_ivs_json=NULL,current_defeated=FALSE,status=%s,finished_at=CASE WHEN %s THEN NOW() ELSE finished_at END WHERE session_id=%s",(balls,'exhausted' if end_session else 'active',end_session,sid)); result=('caught',data,balls,chance,end_session)
                else:
                    if end_session:
                        c.execute("UPDATE pokemon_safari_sessions_tb SET balls=0,status='exhausted',current_species=NULL,current_level=NULL,current_shiny=NULL,current_ivs_json=NULL,current_defeated=FALSE,finished_at=NOW() WHERE session_id=%s",(sid,))
                    else:c.execute("UPDATE pokemon_safari_sessions_tb SET balls=%s WHERE session_id=%s",(balls,sid))
                    result=('escaped_ball',sp,balls,chance,end_session)
                conn.commit(); row=list(row); row[5]='exhausted' if end_session else 'active'; row[6]=balls
                if caught or end_session:row[7]=row[8]=row[9]=row[10]=None; row[11]=False
                row=tuple(row)
            else:conn.rollback()
        except Exception as e:conn.rollback(); print('[PK safari action]',type(e).__name__,e); return await q.answer('No pude actualizar tu Safari.',show_alert=True) or True
        finally:_put_connection(conn)
        if action=='safback':
            await q.answer();
        elif action=='safball' and isinstance(result,tuple) and result[0]=='caught':
            data=result[1]; await q.answer('🎉 ¡Capturado!',show_alert=True)
            try:await q.edit_message_text(f"🌿 SAFARI · ¡CAPTURA!\n\n{'✨ SHINY · ' if data.get('shiny') else ''}#{int(data['species_id']):03d} {data['name']} {_sex_symbol(data.get('sex'))} · Nv.{int(data['level'])}\n🧬 IV {int(data['iv_percent'])}% · {data['iv_grade']}\n🔴 Safari Balls restantes: {int(result[2])}",reply_markup=_safari_markup(row))
            except Exception:pass
            return True
        elif action=='safball' and isinstance(result,tuple):await q.answer('💨 ¡Se salió de la Safari Ball!',show_alert=True)
        else:await q.answer(result if isinstance(result,str) else 'Listo.')
        try:await q.edit_message_text(_safari_text(row),reply_markup=_safari_markup(row))
        except Exception:pass
        return True
    if action=='safpick':
        sid,pid=int(p[2]),int(p[3]); conn=_get_connection(); state=None; bid=None; chat=None
        try:
            c=conn.cursor(); c.execute("SELECT session_id,user_id,chat_id,thread_id,status,current_species,current_level,current_shiny,current_ivs_json,current_defeated,expires_at FROM pokemon_safari_sessions_tb WHERE session_id=%s FOR UPDATE",(sid,)); sr=c.fetchone()
            if not sr or int(sr[1])!=uid:conn.rollback(); return await q.answer('Ese Safari no es tuyo.',show_alert=True) or True
            if str(sr[4])!='active' or sr[10]<=datetime.now(timezone.utc):conn.rollback(); return await q.answer('Tu Safari terminó.',show_alert=True) or True
            if sr[5] is None or bool(sr[9]):conn.rollback(); return await q.answer('Ese encuentro ya cambió.',show_alert=True) or True
            if _battle_busy_cursor(c,uid):conn.rollback(); return await q.answer('Ya tienes una batalla Pokémon pendiente o activa.',show_alert=True) or True
            # Safari usa los 4 espacios actuales de /equipo. El Pokémon elegido aquí
            # solo decide quién sale primero; durante la pelea se puede cambiar normalmente.
            slot_ids=_npc_team_slot_ids_cursor(c,uid)
            if pid not in slot_ids:conn.rollback(); return await q.answer('Ese Pokémon ya no está en tus 4 espacios.',show_alert=True) or True
            ordered_ids=[pid]+[x for x in slot_ids if int(x)!=int(pid)]
            user_mons=[]
            for team_pid in ordered_ids:
                c.execute("SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp,held_item_code,sex FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,int(team_pid))); rr=c.fetchone()
                if rr:user_mons.append(_battle_mon(rr))
            if not user_mons:conn.rollback(); return await q.answer('No pude preparar tu equipo Safari. Revisa /equipo.',show_alert=True) or True
            sp=int(sr[5]); level=int(sr[6]); ivs=json.loads(sr[8] or '{}'); moves=available_moves(sp,level); hp=_stat_value(sp,level,'hp',int(ivs.get('hp',0)))
            bot_mon={'pid':-2_000_000_000-sid,'species':sp,'nickname':None,'level':level,'hp':hp,'max_hp':hp,'moves':moves,'pp':{m:MOVES[m][4] for m in moves if m in MOVES},'status':None,'sleep':0,'stages':{'atk':0,'def':0,'spd':0},'shiny':bool(sr[7]),'ivs':ivs,'held_item':None,'choice_lock':None}
            botid=-2_000_000-sid; safari_mode=len(user_mons); state={'status':'active','battle_kind':'safari','safari_session_id':sid,'safari_user_id':uid,'bot_player_id':botid,'mode':safari_mode,'round':1,'choices':{},'players':{str(uid):{'name':_display_name_cursor(c,uid),'mons':user_mons,'active':0},str(botid):{'name':'Pokémon Safari','mons':[bot_mon],'active':0}}}
            c.execute("INSERT INTO pokemon_battles_tb(chat_id,thread_id,challenger_id,opponent_id,mode,status,state_json) VALUES(%s,%s,%s,%s,%s,'active',%s) RETURNING battle_id",(int(sr[2]),int(sr[3] or 0),uid,botid,safari_mode,json.dumps(state,ensure_ascii=False))); bid=int(c.fetchone()[0]); c.execute("INSERT INTO pokemon_safari_battles_tb(battle_id,session_id,user_id) VALUES(%s,%s,%s)",(bid,sid,uid)); conn.commit(); chat=(int(sr[2]),int(sr[3] or 0))
        except Exception as e:conn.rollback(); print('[PK safari battle]',type(e).__name__,e); return await q.answer('No pude iniciar la pelea Safari.',show_alert=True) or True
        finally:_put_connection(conn)
        await q.answer('⚔️ ¡Comienza la pelea!')
        try:
            msg=await context.bot.send_message(chat[0],_battle_text(state,'🌿 Zona Safari · tu equipo completo está disponible. Puedes cambiar Pokémon y lanzar una Safari Ball cuando quieras; bajar PS mejora la captura.'),message_thread_id=chat[1] or None,reply_markup=_battle_markup(bid)); await _store_battle_public_message_id(bid,msg.message_id); await _sync_single_battle_views(context,bid,state,chat[0],chat[1],msg.message_id,'🌿 Zona Safari · tu equipo completo está disponible. Puedes cambiar Pokémon y lanzar una Safari Ball cuando quieras; bajar PS mejora la captura.')
        except Exception as e:print('[PK safari battle send]',type(e).__name__,e)
        try:await q.edit_message_text(f'⚔️ Batalla Safari iniciada con {len(state["players"][str(uid)]["mons"])} Pokémon disponibles. Puedes cambiar durante el combate; tus acciones se eligen por privado.')
        except Exception:pass
        return True

    # ---- Team Rocket ----
    if action=='rocketfight':
        event_id=int(p[2]); conn=_get_connection(); key=None; mode=2; eid=None; media=(None,None)
        try:
            c=conn.cursor(); c.execute("SELECT chat_id,thread_id,status,stage,expires_at FROM pokemon_rocket_events_tb WHERE event_id=%s FOR UPDATE",(event_id,)); er=c.fetchone()
            if not er or str(er[2])!='active':conn.rollback(); return await q.answer('La invasión ya terminó.',show_alert=True) or True
            if er[4]<=datetime.now(timezone.utc):c.execute("UPDATE pokemon_rocket_events_tb SET status='expired',finished_at=NOW() WHERE event_id=%s",(event_id,)); conn.commit(); return await q.answer('Team Rocket escapó.',show_alert=True) or True
            stage=int(er[3]); key=ROCKET_WAVES[min(stage,3)]; mode=3 if stage>=2 else 2
            if len(_npc_team_slot_ids_cursor(c,uid))<mode:conn.rollback(); return await q.answer(f'Necesitas al menos {mode} Pokémon en /equipo.',show_alert=True) or True
            if _battle_busy_cursor(c,uid):conn.rollback(); return await q.answer('Ya tienes una batalla pendiente.',show_alert=True) or True
            c.execute("INSERT INTO pokemon_npc_encounters_tb(chat_id,thread_id,npc_key,encounter_type,mode,status,claimed_by,selected_json,expires_at,event_ref) VALUES(%s,%s,%s,'normal',%s,'selecting',%s,'[]',%s,%s) RETURNING encounter_id",(int(er[0]),int(er[1] or 0),key,mode,uid,er[4],event_id)); eid=int(c.fetchone()[0]); media=_npc_media_for_key_cursor(c,key); conn.commit()
        except Exception as e:conn.rollback(); print('[PK rocket fight]',type(e).__name__,e); return await q.answer('No pude abrir el combate Rocket.',show_alert=True) or True
        finally:_put_connection(conn)
        conn=_get_connection()
        try:c=conn.cursor(); markup=_npc_selection_markup_cursor(c,uid,eid,mode,[])
        finally:_put_connection(conn)
        try:
            text=f"🚀 INVASIÓN ROCKET · {_npc_label(key)}\nElige {mode} Pokémon de tus 4 y en qué orden saldrán:"
            mt,fid=media
            if mt=='animation' and fid:await context.bot.send_animation(uid,animation=fid,caption=text,reply_markup=markup)
            elif mt=='photo' and fid:await context.bot.send_photo(uid,photo=fid,caption=text,reply_markup=markup)
            else:await context.bot.send_message(uid,text,reply_markup=markup)
            await q.answer('Te mandé la selección por privado.')
        except Exception:await q.answer('Abre primero el privado de PiBot con /start.',show_alert=True)
        return True

    # ---- Incursiones ----
    if action=='raidattack':
        raid_id=int(p[2]); conn=_get_connection(); row=None; markup=None
        try:
            c=conn.cursor(); c.execute(f"SELECT {RAID_SELECT} FROM pokemon_raids_tb WHERE raid_id=%s",(raid_id,)); row=c.fetchone()
            if not row or str(row[7])!='active' or row[10]<=datetime.now(timezone.utc):return await q.answer('La incursión ya no está activa.',show_alert=True) or True
            slots=_npc_team_slot_ids_cursor(c,uid); rows=[]
            for pid in slots:
                c.execute("SELECT species_id,nickname,level,shiny FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); rr=c.fetchone()
                if rr:rows.append([InlineKeyboardButton(f"⚔️ {'✨ ' if rr[3] else ''}{rr[1] or NAMES[int(rr[0])]} · Nv.{int(rr[2])}",callback_data=f'pk:raidmon:{raid_id}:{pid}')])
            markup=InlineKeyboardMarkup(rows) if rows else None
        finally:_put_connection(conn)
        if not markup:return await q.answer('Necesitas Pokémon en /equipo.',show_alert=True) or True
        await q.answer()
        try:await context.bot.send_message(uid,'💥 INCURSIÓN · Elige el Pokémon que atacará:',reply_markup=markup)
        except Exception:return await q.answer('Abre primero el privado de PiBot.',show_alert=True) or True
        return True
    if action=='raidmon':
        raid_id,pid=int(p[2]),int(p[3]); conn=_get_connection(); damage=0; defeated=False; hp=0; top=None; catcher=None; legendary=False; best_eff=1.0; total_damage=0; attacks_now=0; trainer_name=f'Entrenador {uid}'
        try:
            c=conn.cursor(); c.execute(f"SELECT {RAID_SELECT} FROM pokemon_raids_tb WHERE raid_id=%s FOR UPDATE",(raid_id,)); raid=c.fetchone()
            if not raid or str(raid[7])!='active' or raid[10]<=datetime.now(timezone.utc):conn.rollback(); return await q.answer('La incursión terminó.',show_alert=True) or True
            legendary=bool(raid[11])
            if pid not in _npc_team_slot_ids_cursor(c,uid):conn.rollback(); return await q.answer('Ese Pokémon no está en tu equipo.',show_alert=True) or True
            c.execute("SELECT species_id,level,iv_atk,iv_def,iv_spd,iv_spc,iv_hp FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s FOR UPDATE",(uid,pid)); mon=c.fetchone()
            if not mon:conn.rollback(); return await q.answer('Pokémon no disponible.',show_alert=True) or True
            c.execute("SELECT damage,attacks,last_attack_at FROM pokemon_raid_participants_tb WHERE raid_id=%s AND user_id=%s FOR UPDATE",(raid_id,uid)); part=c.fetchone()
            attacks=int(part[1]) if part else 0; last=part[2] if part else None
            if attacks>=RAID_USER_ATTACKS:conn.rollback(); return await q.answer('Ya usaste tus 5 ataques en esta incursión.',show_alert=True) or True
            if last and (datetime.now(timezone.utc)-last).total_seconds()<RAID_ATTACK_COOLDOWN_SECONDS:conn.rollback(); return await q.answer('Espera un minuto antes de volver a atacar.',show_alert=True) or True
            ivpct=round(sum(int(x or 0) for x in mon[2:7])/75*100)
            move_effs=[effectiveness(MOVES[m][1],TYPES.get(int(raid[3]),('Normal',))) for m in available_moves(int(mon[0]),int(mon[1])) if m in MOVES]
            best_eff=max(move_effs) if move_effs else 1.0
            eff_mult=1.25 if best_eff>=2 else (0.90 if best_eff<1 else 1.0)
            damage=max(80,int((int(mon[1])*9+ivpct*2+random.randint(40,160))*eff_mult)); hp=max(0,int(raid[6])-damage); defeated=hp<=0
            # Primero registra ataque/daño para que la selección ponderada incluya el golpe final.
            c.execute("INSERT INTO pokemon_raid_participants_tb(raid_id,user_id,damage,attacks,last_attack_at) VALUES(%s,%s,%s,1,NOW()) ON CONFLICT(raid_id,user_id) DO UPDATE SET damage=pokemon_raid_participants_tb.damage+EXCLUDED.damage,attacks=pokemon_raid_participants_tb.attacks+1,last_attack_at=NOW() RETURNING damage,attacks",(raid_id,uid,damage))
            pr=c.fetchone() or (damage,1); total_damage=int(pr[0]); attacks_now=int(pr[1]); trainer_name=_display_name_cursor(c,uid)
            c.execute("UPDATE pokemon_instances_tb SET friendship=LEAST(255,friendship+1) WHERE pokemon_id=%s",(pid,))
            if defeated:
                c.execute("SELECT user_id,damage FROM pokemon_raid_participants_tb WHERE raid_id=%s ORDER BY damage DESC",(raid_id,)); parts=c.fetchall(); top=int(parts[0][0]) if parts else None
                for puid,_dmg in parts:
                    puid=int(puid); c.execute("UPDATE usuarios_tb SET saldo=saldo+2500 WHERE id_user=%s",(puid,)); grant_item_with_cursor(c,puid,'rare_candy',1)
                    if random.random()<0.10:grant_item_with_cursor(c,puid,'safari_ticket',1)
                if top is not None:grant_item_with_cursor(c,top,'object_box',1)
                # Tanto raids normales como legendarias generan UN solo ejemplar capturable.
                # El derecho se sortea ponderado por daño y el elegido dispone de 3 tiros.
                catcher=_raid_weighted_catcher(parts)
                c.execute("""UPDATE pokemon_raids_tb SET hp=0,status='capture',catcher_id=%s,capture_attempts=0,capture_status='pending',
                             expires_at=NOW()+(%s * INTERVAL '1 second'),finished_at=NULL WHERE raid_id=%s""",(catcher,RAID_LEGENDARY_CAPTURE_SECONDS,raid_id))
            else:
                c.execute("UPDATE pokemon_raids_tb SET hp=%s WHERE raid_id=%s",(hp,raid_id))
            conn.commit()
        except Exception as e:conn.rollback(); print('[PK raid attack]',type(e).__name__,e); return await q.answer('No pude aplicar tu ataque.',show_alert=True) or True
        finally:_put_connection(conn)
        await q.answer(f"💥 -{damage} PS{' · súper eficaz' if best_eff>=2 else ''}",show_alert=True)
        # El detalle del ataque se queda en el panel privado del jugador.
        try:
            await q.edit_message_text(
                f"💥 INCURSIÓN · ATAQUE COMPLETADO\n\n"
                f"Hiciste {damage:,} de daño{' súper eficaz' if best_eff>=2 else ''}.\n"
                f"🔥 Daño total aportado: {total_damage:,}\n"
                f"⚔️ Ataques usados: {attacks_now}/{RAID_USER_ATTACKS}\n"
                f"❤️ PS compartidos del jefe: {hp:,}/{int(raid[5]):,}"
            )
        except Exception:pass
        await _refresh_raid_message(context,raid_id)
        # Toda la elección/ataque ocurre en privado. En el grupo solo aparece el resumen
        # acumulado del entrenador y la tarjeta compartida con los PS ya actualizados.
        try:
            await context.bot.send_message(int(raid[1]),f"⚔️ {trainer_name} acumula {total_damage:,} de daño total en la incursión. · Ataques {attacks_now}/{RAID_USER_ATTACKS}",message_thread_id=(raid[2] or None))
        except Exception:pass
        if defeated and catcher is not None:
            conn=_get_connection(); cname=f'Entrenador {catcher}'
            try:c=conn.cursor(); cname=_display_name_cursor(c,catcher)
            finally:_put_connection(conn)
            title='🌟 ¡INCURSIÓN LEGENDARIA COMPLETADA!' if legendary else '🏆 ¡INCURSIÓN COMPLETADA!'
            text=(f"{title}\n\nTodos los participantes: +2,500 PiPesos +1 Caramelo Raro.\n"
                  f"🥇 Mayor daño: Caja de Objetos Pokémon.\n\n🎯 {cname} fue elegido para intentar capturar a {NAMES[int(raid[3])]}.\n"
                  f"🎲 Tiene {RAID_LEGENDARY_CAPTURE_ATTEMPTS} tiros. Solo un 6 lo captura.")
            try:await context.bot.send_message(int(raid[1]),text,message_thread_id=(raid[2] or None))
            except Exception:pass
            try:
                prefix='🌟 ' if legendary else '💥 '
                await context.bot.send_message(catcher,f"{prefix}Te tocó la oportunidad de capturar a {NAMES[int(raid[3])]} de la incursión.\nTienes {RAID_LEGENDARY_CAPTURE_ATTEMPTS} tiros. Usa el botón de la incursión en Juegos y Casino.")
            except Exception:pass
        return True
    if action=='raidcatch':
        raid_id=int(p[2]); conn=_get_connection(); raid=None
        try:
            c=conn.cursor(); c.execute(f"SELECT {RAID_SELECT} FROM pokemon_raids_tb WHERE raid_id=%s FOR UPDATE",(raid_id,)); raid=c.fetchone()
            if not raid or str(raid[7])!='capture':conn.rollback(); return await q.answer('Esta captura de incursión ya terminó.',show_alert=True) or True
            if int(raid[13] or 0)!=uid:conn.rollback(); return await q.answer('Solo el entrenador elegido puede hacer estos tiros.',show_alert=True) or True
            if raid[10] and raid[10]<=datetime.now(timezone.utc):
                c.execute("UPDATE pokemon_raids_tb SET status='finished',capture_status='escaped',finished_at=NOW() WHERE raid_id=%s",(raid_id,)); conn.commit(); await _refresh_raid_message(context,raid_id); return await q.answer('Se acabó el tiempo de captura.',show_alert=True) or True
            if int(raid[14])>=RAID_LEGENDARY_CAPTURE_ATTEMPTS:conn.rollback(); return await q.answer('Ya usaste tus 3 tiros.',show_alert=True) or True
            if str(raid[15])=='rolling':conn.rollback(); return await q.answer('Ya hay un dado en movimiento.',show_alert=True) or True
            c.execute("UPDATE pokemon_raids_tb SET capture_status='rolling' WHERE raid_id=%s",(raid_id,)); conn.commit()
        except Exception as e:conn.rollback(); print('[PK raid catch prep]',type(e).__name__,e); return await q.answer('No pude preparar el tiro.',show_alert=True) or True
        finally:_put_connection(conn)
        await q.answer('🎲 ¡Lanzando!',show_alert=False)
        try:
            dice=await context.bot.send_dice(chat_id=int(raid[1]),message_thread_id=(raid[2] or None))
            await asyncio.sleep(WILD_DICE_ANIMATION_SECONDS)
            value=int(dice.dice.value)
        except Exception as e:
            conn=_get_connection()
            try:c=conn.cursor(); c.execute("UPDATE pokemon_raids_tb SET capture_status='pending' WHERE raid_id=%s AND status='capture'",(raid_id,)); conn.commit()
            except Exception:conn.rollback()
            finally:_put_connection(conn)
            return True
        caught=False; escaped=False; attempts=0; data=None
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute(f"SELECT {RAID_SELECT} FROM pokemon_raids_tb WHERE raid_id=%s FOR UPDATE",(raid_id,)); cur=c.fetchone()
            if not cur or str(cur[7])!='capture' or int(cur[13] or 0)!=uid:conn.rollback(); return True
            attempts=int(cur[14])+1; caught=(value==RAID_LEGENDARY_DICE_SUCCESS)
            if caught:
                data=grant_pokemon_with_cursor(c,uid,int(cur[3]),f"{'raid_legendary' if bool(cur[11]) else 'raid_normal'}:{raid_id}",level_override=int(cur[4]),shiny_override=bool(cur[12]))
                c.execute("UPDATE pokemon_raids_tb SET status='finished',capture_attempts=%s,capture_status='caught',finished_at=NOW() WHERE raid_id=%s",(attempts,raid_id))
            elif attempts>=RAID_LEGENDARY_CAPTURE_ATTEMPTS:
                escaped=True; c.execute("UPDATE pokemon_raids_tb SET status='finished',capture_attempts=%s,capture_status='escaped',finished_at=NOW() WHERE raid_id=%s",(attempts,raid_id))
            else:
                c.execute("UPDATE pokemon_raids_tb SET capture_attempts=%s,capture_status='pending' WHERE raid_id=%s",(attempts,raid_id))
            conn.commit()
        except Exception as e:conn.rollback(); print('[PK raid catch result]',type(e).__name__,e); return True
        finally:_put_connection(conn)
        await _refresh_raid_message(context,raid_id)
        if caught and data:
            text=(f"🎉 ¡CAPTURA DE INCURSIÓN!\n\n🎲 {value}/6\n"
                  f"{'✨ SHINY · ' if data.get('shiny') else ''}#{int(data['species_id']):03d} {data['name']} {_sex_symbol(data.get('sex'))} · Nv.{int(data['level'])}\n"
                  f"🧬 IV {int(data.get('iv_percent',0))}% · {data.get('iv_grade','')}\n🎮 Ejemplar #{int(data['pokemon_id'])}")
            try:await context.bot.send_message(int(raid[1]),text,message_thread_id=(raid[2] or None))
            except Exception:pass
            try:await context.bot.send_message(uid,text)
            except Exception:pass
        elif escaped:
            try:await context.bot.send_message(int(raid[1]),f"💨 {NAMES[int(raid[3])]} escapó después de los 3 tiros.",message_thread_id=(raid[2] or None))
            except Exception:pass
        else:
            try:await context.bot.send_message(int(raid[1]),f"💨 {NAMES[int(raid[3])]} salió de la Poké Ball.\n🎲 {attempts}/{RAID_LEGENDARY_CAPTURE_ATTEMPTS} tiros usados.",message_thread_id=(raid[2] or None))
            except Exception:pass
        return True
    if action=='egghatch':
        egg_id=int(p[2]); conn=_get_connection(); row=None
        try:
            c=conn.cursor(); c.execute("SELECT owner_id,status,progress FROM pokemon_eggs_tb WHERE egg_id=%s FOR UPDATE",(egg_id,)); row=c.fetchone(); conn.rollback()
        finally:_put_connection(conn)
        if not row or int(row[0])!=uid:return await q.answer('Ese huevo no es tuyo.',show_alert=True) or True
        if str(row[1])!='hatching' or int(row[2])<EGG_PROGRESS_MAX:return await q.answer('Ese huevo todavía no está listo.',show_alert=True) or True
        await q.answer('🥚 ¡Empieza la eclosión!',show_alert=False)
        try:
            if getattr(q.message,'photo',None) or getattr(q.message,'animation',None):await q.edit_message_caption(caption='🥚 El huevo está temblando... ✨',reply_markup=None)
            else:await q.edit_message_text('🥚 El huevo está temblando... ✨',reply_markup=None)
        except Exception:pass
        name=(q.from_user.full_name or q.from_user.first_name or q.from_user.username or f'Entrenador {uid}').strip()
        await _hatch_egg(context,egg_id,q.message.chat_id,getattr(q.message,'message_thread_id',None),name)
        return True
    if action in ('eventhome','eventshop','eventrewards','eventinfo','eventegg'):
        owner=int(p[2]) if len(p)>2 and str(p[2]).isdigit() else uid
        if owner!=uid:return await q.answer('Este menú del evento no es tuyo. Usa /evento.',show_alert=True) or True
        chat_id=q.message.chat_id; thread_id=getattr(q.message,'message_thread_id',None)
        if action=='eventhome':
            await q.answer();
            try:await _send_event_home(context,uid,chat_id,thread_id)
            except Exception:pass
            return True
        if action=='eventshop':
            conn=_get_connection(); bal=0; media=(None,None)
            try:
                c=conn.cursor(); bal=_halloween_wallet_cursor(c,uid); media=_halloween_media_cursor(c,'shop')
            finally:_put_connection(conn)
            await q.answer()
            text=f'🛒 TIENDA HALLOWEEN · {q.from_user.full_name}\n\n🍬 Tienes {bal} Dulces Halloween.\n\nLas cajas Épica y Legendaria son las mismas cajas normales de PiBot, pero aquí se pagan con dulces.'
            kwargs={'reply_markup':_halloween_shop_markup(uid)}
            if thread_id:kwargs['message_thread_id']=thread_id
            if media[0]=='animation' and media[1]:await context.bot.send_animation(chat_id,animation=media[1],caption=text,**kwargs)
            elif media[0]=='photo' and media[1]:await context.bot.send_photo(chat_id,photo=media[1],caption=text,**kwargs)
            else:await context.bot.send_message(chat_id,text,**kwargs)
            return True
        if action=='eventrewards':
            await q.answer(); await context.bot.send_message(chat_id,
                '🎁 RECOMPENSAS HALLOWEEN\n\n'
                f'🎃📦 Caja Pokémon Halloween: Pokémon Gen 1 no legendario, con probabilidad Shiny 1/{HALLOWEEN_BOX_SHINY_DENOMINATOR}.\n'
                f'🎃🥚 Huevo Maldito: especies temáticas; Shiny 1/{HALLOWEEN_EGG_SHINY_DENOMINATOR}.\n'
                '🎃⚡ Pikachu Halloween: exclusivo de la tienda; al comprarlo tiene 80% normal y 20% Shiny.\n'
                '💜🌟 Las cajas normales conservan su roll, Jackpot y XP de temporada.',message_thread_id=thread_id or None)
            return True
        if action=='eventinfo':
            await q.answer(); await context.bot.send_message(chat_id,
                '🎃 CÓMO FUNCIONA\n\n🍬 Durante el evento los Pokémon pueden soltar Dulces Halloween. Los de tipo Fantasma sueltan más.\n'
                '🍬 Hay apariciones automáticas de Dulces Halloween para recoger, un entrenador Halloween diario y un jefe en viernes, sábado y domingo.\n'
                '🥚 Los huevos suben +1.5% por cada mensaje tuyo en los grupos oficiales. Al 100% tú decides cuándo romperlos.\n'
                f'⏳ {_halloween_countdown_text()}',message_thread_id=thread_id or None)
            return True
        if action=='eventegg':
            conn=_get_connection(); rows=[]
            try:c=conn.cursor(); rows=_live_eggs_cursor(c,uid)
            finally:_put_connection(conn)
            await q.answer(); await context.bot.send_message(chat_id,f'🥚 HUEVOS DE {q.from_user.full_name}\n\n'+_eggs_compact_text(rows),reply_markup=_eggs_ready_markup(rows),message_thread_id=thread_id or None); return True
    if action=='eventmediapick':
        try:
            if not is_botmaster(uid):return await q.answer('Solo BotMaster.',show_alert=True) or True
        except Exception:return await q.answer('Solo BotMaster.',show_alert=True) or True
        key=str(p[2])
        if key not in HALLOWEEN_MEDIA_KEYS:return await q.answer('Elemento inválido.',show_alert=True) or True
        context.user_data['pk_wait_halloween_media']=key
        await q.answer(); await q.edit_message_text(f"{HALLOWEEN_MEDIA_KEYS[key]}\n\nAhora envíame una foto o GIF por privado.\nEl nuevo archivo reemplazará al anterior.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('🗑 Quitar actual',callback_data=f'pk:eventmediaremove:{key}')],[InlineKeyboardButton('⬅️ Volver',callback_data='pk:eventmediahome')]])); return True
    if action=='eventmediahome':
        try:
            if not is_botmaster(uid):return await q.answer('Solo BotMaster.',show_alert=True) or True
        except Exception:return await q.answer('Solo BotMaster.',show_alert=True) or True
        context.user_data.pop('pk_wait_halloween_media',None); await q.answer(); await q.edit_message_text('🎃 MULTIMEDIA HALLOWEEN 2026',reply_markup=_halloween_media_markup()); return True
    if action=='eventmediaremove':
        try:
            if not is_botmaster(uid):return await q.answer('Solo BotMaster.',show_alert=True) or True
        except Exception:return await q.answer('Solo BotMaster.',show_alert=True) or True
        key=str(p[2]); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("DELETE FROM pokemon_halloween_media_tb WHERE media_key=%s",(key,))
            if key in ('pikachu_normal','pikachu_shiny'):
                want_shiny=(key=='pikachu_shiny')
                c.execute("UPDATE pokemon_instances_tb SET media_type=NULL,media_file_id=NULL,updated_at=NOW() WHERE obtained_from='halloween_2026_pikachu' AND shiny=%s",(want_shiny,))
            conn.commit()
        except Exception:conn.rollback()
        finally:_put_connection(conn)
        context.user_data.pop('pk_wait_halloween_media',None); await q.answer('Multimedia eliminada.',show_alert=True); return True
    if action=='eventbuy':
        owner=int(p[2]) if len(p)>3 and str(p[2]).isdigit() else uid
        if owner!=uid:return await q.answer('Este menú de compra no es tuyo. Usa /evento.',show_alert=True) or True
        code=str(p[3] if len(p)>3 and str(p[2]).isdigit() else p[2]); item=HALLOWEEN_SHOP.get(code)
        if not item:return await q.answer('Recompensa inválida.',show_alert=True) or True
        if not _halloween_active():return await q.answer('🎃 La tienda Halloween ya está cerrada.',show_alert=True) or True
        conn=_get_connection(); result_text=''; box_result=None; media_key=None; newbal=0
        try:
            c=conn.cursor()
            if code=='cursed_egg' and _egg_slots_used_cursor(c,uid)>=EGG_MAX_ACTIVE:conn.rollback(); return await q.answer(f'Ya tienes ocupados tus {EGG_MAX_ACTIVE} espacios de huevo.',show_alert=True) or True
            if not _halloween_spend_cursor(c,uid,int(item['price'])):conn.rollback(); return await q.answer('No tienes suficientes Dulces Halloween.',show_alert=True) or True
            if code=='rare_candy':grant_item_with_cursor(c,uid,'rare_candy',1); result_text='🍬 Recibiste 1 Caramelo Raro.'
            elif code=='object_box':grant_item_with_cursor(c,uid,'object_box',1); result_text='🎁 Recibiste 1 Caja de Objetos Pokémon. Usa /cajaobjetospokemon.'
            elif code=='cursed_egg':
                eid=_create_cursed_egg_cursor(c,uid,'halloween_shop'); result_text=f'🎃🥚 Recibiste un Huevo Maldito #{eid}. El Pokémon sigue oculto.'; media_key='cursed_egg'
            elif code=='halloween_box':
                data=_grant_halloween_box_cursor(c,uid); result_text=(f"🎃📦 Abriste una Caja Pokémon Halloween.\n\n{'✨ SHINY · ' if data.get('shiny') else ''}#{data['species_id']:03d} {data['name']} {_sex_symbol(data.get('sex'))} · Nv.{data['level']}\n🧬 IV {data['iv_percent']}% · {data['iv_grade']}"); media_key='halloween_box'
            elif code=='halloween_pikachu':
                data=_grant_halloween_pikachu_cursor(c,uid); shiny_prefix='✨ SHINY ✨\n' if data.get('shiny') else ''
                result_text=(f"🎃⚡ ¡PIKACHU HALLOWEEN!\n\n{shiny_prefix}#025 Pikachu Halloween {_sex_symbol(data.get('sex'))} · Nv.{data['level']}\n🧬 IV {data['iv_percent']}% · {data['iv_grade']}\n🎮 Ejemplar #{data['pokemon_id']}"); media_key='pikachu_shiny' if data.get('shiny') else 'pikachu_normal'
            elif code in ('pibot_epic','pibot_legendary'):
                box_result=_grant_normal_pibot_box_cursor(c,uid,'epic' if code=='pibot_epic' else 'legendary'); result_text=f"🎁 Abriste una caja normal de PiBot.\n✨ Te salió: {box_result['label']}"
            newbal=_halloween_wallet_cursor(c,uid); conn.commit()
        except Exception as e:
            conn.rollback(); print('[PK Halloween shop]',type(e).__name__,e); return await q.answer('No pude completar la compra; no se gastaron dulces si falló.',show_alert=True) or True
        finally:_put_connection(conn)
        if box_result:
            try:
                from handlers.season_pass import grant_season_xp
                xp=grant_season_xp(uid,25 if box_result['code']=='epic' else 60,'box')
                if xp and xp.get('granted',0)>0:result_text += f"\n⭐ +{xp['granted']} XP de temporada"
            except Exception:pass
            if box_result.get('gif_bonus'):result_text += '\n🎞️ BONUS: +10 días de GIF de perfil'
            if box_result.get('jackpot_win'):result_text += f"\n🎰 ¡JACKPOT! +{int(box_result['jackpot_win']):,} PiPesos"
            else:result_text += f"\n🎰 Jackpot: {int(box_result.get('jackpot_after',10000)):,} PiPesos"
        result_text += f'\n\n🍬 Dulces restantes: {newbal}'
        await q.answer('Compra completada 🎃',show_alert=True)
        media=(None,None)
        if media_key:
            conn=_get_connection()
            try:c=conn.cursor(); media=_halloween_media_cursor(c,media_key)
            finally:_put_connection(conn)
        try:
            target_chat=q.message.chat_id; target_thread=getattr(q.message,'message_thread_id',None)
            if media[0]=='animation' and media[1]:await context.bot.send_animation(target_chat,animation=media[1],caption=result_text,message_thread_id=target_thread or None)
            elif media[0]=='photo' and media[1]:await context.bot.send_photo(target_chat,photo=media[1],caption=result_text,message_thread_id=target_thread or None)
            else:await context.bot.send_message(target_chat,result_text,message_thread_id=target_thread or None)
        except Exception:pass
        return True
    if action=='eventclaim':
        event_id=int(p[2]); conn=_get_connection(); kind=None; result_text=''; spawn_kind=None; media_key=None
        try:
            c=conn.cursor(); c.execute("SELECT chat_id,thread_id,event_kind,status,(expires_at<=NOW()) FROM pokemon_halloween_events_tb WHERE event_id=%s FOR UPDATE",(event_id,)); er=c.fetchone()
            if not er or str(er[3])!='active' or bool(er[4]):
                if er and str(er[3])=='active':c.execute("UPDATE pokemon_halloween_events_tb SET status='expired',finished_at=NOW() WHERE event_id=%s",(event_id,)); conn.commit()
                else:conn.rollback()
                return await q.answer('Esos dulces ya desaparecieron.',show_alert=True) or True
            # Incluso si quedó una fila vieja de otro tipo antes del deploy, toda aparición sorpresa
            # se convierte en Dulces Halloween. Pikachu Halloween solo existe en la tienda.
            kind='candy'; chat_id=int(er[0]); thread_id=int(er[1] or 0)
            c.execute("UPDATE pokemon_halloween_events_tb SET status='claimed',claimed_by=%s,finished_at=NOW() WHERE event_id=%s",(uid,event_id))
            name=_display_name_cursor(c,uid)
            amount=random.randint(5,15); bal=_halloween_add_candies_cursor(c,uid,amount)
            result_text=f'🍬 {name} encontró {amount} Dulces Halloween.\nTotal: {bal} 🍬'
            conn.commit()
        except Exception as e:
            conn.rollback(); print('[PK Halloween claim]',type(e).__name__,e); return await q.answer('No pude resolver el evento.',show_alert=True) or True
        finally:_put_connection(conn)
        await q.answer('🍬 ¡Dulces recogidos!',show_alert=True)
        try:
            if getattr(q.message,'photo',None) or getattr(q.message,'animation',None):await q.edit_message_caption(caption=result_text,reply_markup=None)
            else:await q.edit_message_text(result_text,reply_markup=None)
        except Exception:pass
        # Las apariciones sorpresa son solo de dulces; se conserva esta rama vacía por compatibilidad.
        if media_key:
            conn2=_get_connection(); media=(None,None)
            try:c2=conn2.cursor(); media=_halloween_media_cursor(c2,media_key)
            finally:_put_connection(conn2)
            try:
                if media[0]=='animation' and media[1]:await context.bot.send_animation(chat_id,animation=media[1],caption=result_text,message_thread_id=thread_id or None)
                elif media[0]=='photo' and media[1]:await context.bot.send_photo(chat_id,photo=media[1],caption=result_text,message_thread_id=thread_id or None)
            except Exception:pass
        if spawn_kind:
            try:await _spawn_halloween_special_npc(context,chat_id,thread_id or None,spawn_kind,True)
            except Exception as e:print('[PK Halloween spawned NPC]',type(e).__name__,e)
        return True
    if action=='breedpage':
        if len(p)>=4: owner,page=int(p[2]),int(p[3])
        else: owner,page=uid,int(p[2])
        if owner!=uid:return await q.answer('Este menú de crianza no es tuyo.',show_alert=True) or True
        await q.answer(); await q.edit_message_text(f'💕 CRIANZA POKÉMON · {q.from_user.full_name}\n\nElige el primer Pokémon:',reply_markup=_breed_first_markup(uid,page)); return True
    if action=='breed1':
        if len(p)>=5: owner,pid= int(p[2]),int(p[3])
        else: owner,pid=uid,int(p[2])
        if owner!=uid:return await q.answer('Este menú de crianza no es tuyo.',show_alert=True) or True
        first=_get_instance(uid,pid)
        if not first:return await q.answer('Ese Pokémon ya no está disponible.',show_alert=True)
        markup=_breed_second_markup(uid,pid)
        if not markup:return await q.answer('No tienes otro Pokémon compatible con este.',show_alert=True)
        await q.answer(); await q.edit_message_text(f"💕 Primer padre: {_pokemon_label(first)}\n\nElige una pareja compatible:",reply_markup=markup); return True
    if action=='breed2':
        if len(p)>=5: owner,a,b=int(p[2]),int(p[3]),int(p[4])
        else: owner,a,b=uid,int(p[2]),int(p[3])
        if owner!=uid:return await q.answer('Este menú de crianza no es tuyo.',show_alert=True) or True
        ra=_get_instance(uid,a); rb=_get_instance(uid,b)
        if not ra or not rb or len(ra)<=17 or len(rb)<=17:return await q.answer('Alguno ya no está disponible.',show_alert=True)
        if not _breeding_compatible(int(ra[1]),str(ra[17]),int(rb[1]),str(rb[17])):return await q.answer('Ya no son compatibles.',show_alert=True)
        offspring=_offspring_species(int(ra[1]),str(ra[17]),int(rb[1]),str(rb[17])); tier=rarity_for(offspring)
        if tier=='legendario':tier='epico'
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(f'🥚 Formar huevo · {BREEDING_COST_PIPESOS:,} PiPesos',callback_data=f'pk:breedgo:{uid}:{a}:{b}')],[InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:breedcancel:{uid}')]])
        await q.answer(); await q.edit_message_text(f"💕 PAREJA COMPATIBLE\n\n1. {_pokemon_label(ra)}\n2. {_pokemon_label(rb)}\n\n🥚 La cría será de la familia #{offspring:03d} {NAMES[offspring]}.\n🧬 Dos DVs se heredarán de los padres; el resto será aleatorio.\n✨ Los padres Shiny mejoran un poco la posibilidad Shiny.\n💰 Coste: {BREEDING_COST_PIPESOS:,} PiPesos.\n⏳ La pareja tardará 30 minutos en producir el huevo.",reply_markup=kb); return True
    if action=='breedcancel':
        owner=int(p[2]) if len(p)>2 else uid
        if owner!=uid:return await q.answer('Este menú de crianza no es tuyo.',show_alert=True) or True
        await q.answer('Crianza cancelada.'); await q.edit_message_text('❌ Crianza cancelada.'); return True
    if action=='breedgo':
        if len(p)>=5: owner,a,b=int(p[2]),int(p[3]),int(p[4])
        else: owner,a,b=uid,int(p[2]),int(p[3])
        if owner!=uid:return await q.answer('Este menú de crianza no es tuyo.',show_alert=True) or True
        conn=_get_connection(); tier='comun'; species=None; breeding_id=None
        try:
            c=conn.cursor()
            if _active_breeding_cursor(c,uid,True):conn.rollback(); await q.answer('Ya tienes una pareja criando en la Guardería.',show_alert=True); return True
            if _egg_slots_used_cursor(c,uid)>=EGG_MAX_ACTIVE:conn.rollback(); await q.answer(f'Ya tienes ocupados tus {EGG_MAX_ACTIVE} espacios de huevo.',show_alert=True); return True
            c.execute("SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp,held_item_code,sex FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id IN (%s,%s) FOR UPDATE",(uid,a,b)); rr={int(x[0]):x for x in c.fetchall()}
            if a not in rr or b not in rr:conn.rollback(); await q.answer('Alguno de los padres ya no está disponible.',show_alert=True); return True
            ra,rb=rr[a],rr[b]
            if not _breeding_compatible(int(ra[1]),str(ra[17]),int(rb[1]),str(rb[17])):conn.rollback(); await q.answer('La pareja ya no es compatible.',show_alert=True); return True
            c.execute("SELECT saldo FROM usuarios_tb WHERE id_user=%s FOR UPDATE",(uid,)); bal=c.fetchone()
            if not bal or int(bal[0])<BREEDING_COST_PIPESOS:conn.rollback(); await q.answer(f'Necesitas {BREEDING_COST_PIPESOS:,} PiPesos.',show_alert=True); return True
            species=_offspring_species(int(ra[1]),str(ra[17]),int(rb[1]),str(rb[17])); tier=rarity_for(species); tier=tier if tier in EGG_TIERS else 'epico'
            ivs=_inherit_ivs(ra,rb); shiny=_egg_shiny_roll(ra,rb)
            c.execute("UPDATE usuarios_tb SET saldo=saldo-%s WHERE id_user=%s",(BREEDING_COST_PIPESOS,uid))
            c.execute("""INSERT INTO pokemon_breedings_tb(owner_id,parent_a,parent_b,parent_a_species,parent_b_species,species_id,egg_tier,shiny,iv_atk,iv_def,iv_spd,iv_spc,ready_at)
                         VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()+INTERVAL '30 minutes') RETURNING breeding_id""",
                      (uid,a,b,int(ra[1]),int(rb[1]),species,tier,shiny,ivs['atk'],ivs['def'],ivs['spd'],ivs['spc']))
            breeding_id=int(c.fetchone()[0]); conn.commit()
        except Exception as e:conn.rollback(); print('[PK breed confirm]',type(e).__name__,e); await q.answer('No pude iniciar la crianza.',show_alert=True); return True
        finally:_put_connection(conn)
        await q.answer('¡Pareja enviada a la Guardería! 💕',show_alert=True)
        await q.edit_message_text(f"🏡 ¡PAREJA EN LA GUARDERÍA!\n\n💕 Tus Pokémon están criando.\n⏳ Tardarán 30 minutos en producir el huevo.\n📩 PiBot te avisará por privado apenas esté listo.\n🥚 El contenido seguirá siendo secreto hasta que eclosione.\n\nPuedes revisar el tiempo con /guarderiapokemon.")
        return True
    if action=='egggiftpick':
        owner,target,egg_id=int(p[2]),int(p[3]),int(p[4])
        if owner!=uid:return await q.answer('Este menú de huevos no es tuyo.',show_alert=True) or True
        conn=_get_connection(); egg=None; target_name=None; target_used=0
        try:
            c=conn.cursor(); egg=_egg_by_id_cursor(c,egg_id); target_name=_display_name_cursor(c,target); target_used=_egg_slots_used_cursor(c,target)
        finally:_put_connection(conn)
        if not egg or int(egg[1])!=uid:return await q.answer('Ese huevo ya no es tuyo.',show_alert=True) or True
        if target_used>=EGG_MAX_ACTIVE:return await q.answer(f'{target_name} ya tiene ocupados sus {EGG_MAX_ACTIVE} espacios.',show_alert=True) or True
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('🎁 Confirmar regalo',callback_data=f'pk:egggift:{egg_id}:{target}')],[InlineKeyboardButton('⬅️ Cancelar',callback_data='pk:egggiftcancel')]])
        await q.answer(); await q.edit_message_text(f"🎁 ¿Regalar {_egg_display_label(egg)} #{egg_id} a {target_name}?\n\n📈 Progreso: {int(egg[5])/100:.1f}%\nEl progreso se conserva.",reply_markup=kb); return True
    if action=='egggiftcancel':
        await q.answer('Regalo cancelado.');
        try:await q.edit_message_text('❌ Regalo de huevo cancelado.')
        except Exception:pass
        return True
    if action=='egggift':
        egg_id,target=int(p[2]),int(p[3]); conn=_get_connection(); target_name=None; tier='comun'; cursed=False
        try:
            c=conn.cursor(); c.execute("SELECT owner_id,egg_tier,status,source FROM pokemon_eggs_tb WHERE egg_id=%s FOR UPDATE",(egg_id,)); er=c.fetchone()
            if not er or int(er[0])!=uid or str(er[2]) not in ('active','hatching'):conn.rollback(); await q.answer('Ese huevo ya no puede regalarse.',show_alert=True); return True
            if _egg_slots_used_cursor(c,target)>=EGG_MAX_ACTIVE:conn.rollback(); await q.answer(f'La otra persona ya tiene ocupados sus {EGG_MAX_ACTIVE} espacios de huevo.',show_alert=True); return True
            tier=str(er[1]); cursed=str(er[3]).startswith('halloween'); target_name=_display_name_cursor(c,target)
            new_source='halloween_regalo' if cursed else 'regalo'
            c.execute("UPDATE pokemon_eggs_tb SET owner_id=%s,source=%s WHERE egg_id=%s",(target,new_source,egg_id)); conn.commit()
        except Exception as e:conn.rollback(); print('[PK egg gift]',type(e).__name__,e); await q.answer('No pude regalarlo.',show_alert=True); return True
        finally:_put_connection(conn)
        label='🎃🥚 Huevo Maldito' if cursed else _egg_tier_label(tier)
        await q.answer('Huevo regalado 🎁',show_alert=True)
        try:await q.edit_message_text(f'🎁 ¡Huevo regalado!\n\n{target_name} recibió {label}. Conservó todo su progreso.')
        except Exception:pass
        try:await context.bot.send_message(target,f'🎁 {q.from_user.full_name} te regaló {label}. Usa /huevos para ver su progreso.')
        except Exception:pass
        return True
    if action=='eggclaim':
        event_id=int(p[2]); conn=_get_connection(); tier='comun'; egg_id=None; name=None; media=(None,None)
        try:
            c=conn.cursor(); c.execute("SELECT chat_id,thread_id,egg_tier,species_id,status,message_id,(expires_at<=NOW()) FROM pokemon_egg_events_tb WHERE event_id=%s FOR UPDATE",(event_id,)); er=c.fetchone()
            if not er or str(er[4])!='active' or bool(er[6]):
                if er and str(er[4])=='active':c.execute("UPDATE pokemon_egg_events_tb SET status='expired',finished_at=NOW() WHERE event_id=%s",(event_id,)); conn.commit()
                else:conn.rollback()
                await q.answer('Ese huevo ya no está disponible.',show_alert=True); return True
            if _egg_slots_used_cursor(c,uid)>=EGG_MAX_ACTIVE:conn.rollback(); await q.answer(f'Ya tienes ocupados tus {EGG_MAX_ACTIVE} espacios de huevo.',show_alert=True); return True
            tier=str(er[2]); species=int(er[3]); egg_id=_create_egg_cursor(c,uid,species,tier,'evento'); name=_display_name_cursor(c,uid); media=_egg_media_cursor(c,tier)
            c.execute("UPDATE pokemon_egg_events_tb SET status='claimed',claimed_by=%s,finished_at=NOW() WHERE event_id=%s",(uid,event_id)); conn.commit()
        except Exception as e:conn.rollback(); print('[PK egg claim]',type(e).__name__,e); await q.answer('No pude recoger el huevo.',show_alert=True); return True
        finally:_put_connection(conn)
        await q.answer('¡Te quedaste el huevo! 🥚',show_alert=True)
        text=f"🎉 {name} encontró {_egg_tier_label(tier)} #{egg_id}.\n💬 Sus mensajes harán subir el progreso hasta que eclosione."
        try:
            if media[0] in ('photo','animation'):await q.edit_message_caption(caption=text,reply_markup=None)
            else:await q.edit_message_text(text,reply_markup=None)
        except Exception:pass
        try:await context.bot.send_message(uid,f'🥚 ¡El huevo ya es tuyo!\n\nUsa /huevos para revisar el progreso. Cada mensaje tuyo en el grupo suma +1.5%.')
        except Exception:pass
        return True
    if action=='eggmediapick':
        try:allowed=is_botmaster(uid)
        except Exception:allowed=False
        if not allowed:await q.answer('Solo BotMaster.',show_alert=True); return True
        key=str(p[2]);
        if key not in ('comun','raro','epico','hatching'):await q.answer('Tipo inválido.',show_alert=True); return True
        context.user_data['pk_wait_egg_media']=key
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('🗑 Quitar actual',callback_data=f'pk:eggmediaremove:{key}')],[InlineKeyboardButton('⬅️ Volver',callback_data='pk:eggmediahome')]])
        await q.answer(); await q.edit_message_text(f"🥚 Seleccionado: {key}.\n\nAhora envíame aquí una FOTO o GIF/animación de Telegram.",reply_markup=kb); return True
    if action=='eggmediahome':
        try:allowed=is_botmaster(uid)
        except Exception:allowed=False
        if not allowed:await q.answer('Solo BotMaster.',show_alert=True); return True
        await q.answer(); await q.edit_message_text('🥚 MULTIMEDIA DE HUEVOS',reply_markup=_egg_media_markup()); return True
    if action=='eggmediaremove':
        try:allowed=is_botmaster(uid)
        except Exception:allowed=False
        if not allowed:await q.answer('Solo BotMaster.',show_alert=True); return True
        key=str(p[2]); conn=_get_connection()
        try:c=conn.cursor(); c.execute("DELETE FROM pokemon_egg_media_tb WHERE egg_key=%s",(key,)); conn.commit()
        except Exception:conn.rollback()
        finally:_put_connection(conn)
        context.user_data.pop('pk_wait_egg_media',None); await q.answer('Multimedia eliminada.',show_alert=True); return True
    if action=='openobjbox':
        reward=_open_object_box(uid); await q.answer('Caja abierta 🎁' if reward else 'No tienes Cajas de Objetos.',show_alert=True)
        if reward:
            try:await q.message.reply_text(f'🎁 CAJA DE OBJETOS POKÉMON\n\nTe salió: {reward}')
            except Exception:pass
        return True
    if action=='npcmediahome':
        try:
            if not is_botmaster(uid):await q.answer('Solo BotMaster.',show_alert=True); return True
        except Exception:await q.answer('Solo BotMaster.',show_alert=True); return True
        await q.answer(); await q.edit_message_text('🎭 MULTIMEDIA POKÉMON\n\nElige una categoría:',reply_markup=_npc_media_home_markup()); return True
    if action=='npcmediacat':
        try:
            if not is_botmaster(uid):await q.answer('Solo BotMaster.',show_alert=True); return True
        except Exception:await q.answer('Solo BotMaster.',show_alert=True); return True
        kind=p[2]; page=int(p[3]); await q.answer(); await q.edit_message_text('👤 Elige el personaje:',reply_markup=_npc_media_category_markup(kind,page)); return True
    if action=='npcmediapick':
        try:
            if not is_botmaster(uid):await q.answer('Solo BotMaster.',show_alert=True); return True
        except Exception:await q.answer('Solo BotMaster.',show_alert=True); return True
        kind,key=p[2],p[3]
        if key not in NPC_ALL:await q.answer('NPC inválido.',show_alert=True); return True
        context.user_data['pk_wait_npc_media']=key
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('🗑 Quitar actual',callback_data=f'pk:npcmediaremove:{kind}:{key}')],[InlineKeyboardButton('⬅️ Volver',callback_data=f'pk:npcmediacat:{kind}:0')]])
        await q.answer(); await q.edit_message_text(f"{_npc_label(key)} seleccionado.\n\nAhora envíame aquí una FOTO o GIF. Se guardará automáticamente por file_id.",reply_markup=kb); return True
    if action=='npcmediaremove':
        try:
            if not is_botmaster(uid):await q.answer('Solo BotMaster.',show_alert=True); return True
        except Exception:await q.answer('Solo BotMaster.',show_alert=True); return True
        kind,key=p[2],p[3]; conn=_get_connection()
        try:c=conn.cursor(); c.execute("DELETE FROM pokemon_npc_media_tb WHERE npc_key=%s",(key,)); conn.commit()
        except Exception:conn.rollback()
        finally:_put_connection(conn)
        context.user_data.pop('pk_wait_npc_media',None); await q.answer('Multimedia eliminada.',show_alert=True); return True
    if action=='npcclaim':
        eid=int(p[2]); conn=_get_connection(); mode=0; key=''; selected=[]
        try:
            c=conn.cursor(); c.execute("SELECT npc_key,mode,status,claimed_by,(expires_at<=NOW()) AS expired FROM pokemon_npc_encounters_tb WHERE encounter_id=%s FOR UPDATE",(eid,)); r=c.fetchone()
            if not r:conn.rollback(); await q.answer('Ese encuentro ya no existe.',show_alert=True); return True
            key,mode,status,claimed=r[0],int(r[1]),str(r[2]),r[3]
            if bool(r[4]) and status in ('active','selecting'):
                c.execute("UPDATE pokemon_npc_encounters_tb SET status='expired',finished_at=NOW() WHERE encounter_id=%s",(eid,)); conn.commit(); await q.answer('⌛ Ese encuentro ya terminó.',show_alert=True); return True
            if status!='active':conn.rollback(); await q.answer('Ese encuentro ya no está disponible.',show_alert=True); return True
            slots=_npc_team_slot_ids_cursor(c,uid)
            if len(slots)<mode:conn.rollback(); await q.answer(f'Necesitas al menos {mode} Pokémon en /equipo.',show_alert=True); return True
            if claimed is not None and int(claimed)!=uid:conn.rollback(); await q.answer('Otro entrenador llegó primero.',show_alert=True); return True
            if _battle_busy_cursor(c,uid):conn.rollback(); await q.answer('Ya tienes una batalla Pokémon pendiente o activa.',show_alert=True); return True
            c.execute("UPDATE pokemon_npc_encounters_tb SET claimed_by=%s,status='selecting',selected_json='[]' WHERE encounter_id=%s",(uid,eid)); conn.commit()
        except Exception as e:conn.rollback(); print('[PK npc claim]',type(e).__name__,e); await q.answer('No pude reservar el encuentro.',show_alert=True); return True
        finally:_put_connection(conn)
        conn=_get_connection()
        try:c=conn.cursor(); markup=_npc_selection_markup_cursor(c,uid,eid,mode,[])
        finally:_put_connection(conn)
        try:await context.bot.send_message(uid,f"⚔️ {_npc_label(str(key))}\nElige {mode} Pokémon de tus 4 y en el orden que quieras usarlos:",reply_markup=markup); await q.answer('Te mandé la selección por privado.')
        except Exception:await q.answer('Abre primero el privado de PiBot con /start.',show_alert=True)
        return True
    if action in ('npcpick','npcstart','npcrelease'):
        eid=int(p[2]); conn=_get_connection(); mode=0; selected=[]; key=''; kind=''; group=None
        try:
            c=conn.cursor(); c.execute("SELECT npc_key,encounter_type,mode,status,claimed_by,selected_json,chat_id,thread_id,message_id,(expires_at<=NOW()) AS expired FROM pokemon_npc_encounters_tb WHERE encounter_id=%s FOR UPDATE",(eid,)); r=c.fetchone()
            if not r or r[4] is None or int(r[4])!=uid:conn.rollback(); await q.answer('Este encuentro no es tuyo.',show_alert=True); return True
            key,kind,mode,status=str(r[0]),str(r[1]),int(r[2]),str(r[3]); selected=[int(x) for x in json.loads(r[5] or '[]')]; group=(int(r[6]),r[7],r[8])
            if bool(r[9]) and status=='selecting':
                c.execute("UPDATE pokemon_npc_encounters_tb SET status='expired',finished_at=NOW() WHERE encounter_id=%s",(eid,)); conn.commit(); await q.answer('⌛ Se acabaron los 10 minutos del encuentro.',show_alert=True); return True
            if status!='selecting':conn.rollback(); await q.answer('La selección ya terminó.',show_alert=True); return True
            if action=='npcrelease':
                c.execute("UPDATE pokemon_npc_encounters_tb SET status='active',claimed_by=NULL,selected_json='[]' WHERE encounter_id=%s",(eid,)); conn.commit(); await q.answer('Encuentro liberado.',show_alert=True); await q.edit_message_text('❌ Selección cancelada. El encuentro volvió a estar disponible.'); return True
            if action=='npcpick':
                pid=int(p[3]); slots=_npc_team_slot_ids_cursor(c,uid)
                if pid not in slots:conn.rollback(); await q.answer('Ese Pokémon ya no está en tu equipo.',show_alert=True); return True
                if pid in selected:selected.remove(pid)
                elif len(selected)<mode:selected.append(pid)
                else:conn.rollback(); await q.answer(f'Ya elegiste {mode}. Quita uno primero.',show_alert=True); return True
                c.execute("UPDATE pokemon_npc_encounters_tb SET selected_json=%s WHERE encounter_id=%s",(json.dumps(selected),eid)); conn.commit()
                conn2=_get_connection()
                try:c2=conn2.cursor(); markup=_npc_selection_markup_cursor(c2,uid,eid,mode,selected)
                finally:_put_connection(conn2)
                await q.answer(); await q.edit_message_text(f"⚔️ {_npc_label(key)}\nElegidos: {len(selected)}/{mode}\nEl orden de selección será el orden de salida.",reply_markup=markup); return True
            if len(selected)!=mode:conn.rollback(); await q.answer(f'Elige exactamente {mode} Pokémon.',show_alert=True); return True
            if _battle_busy_cursor(c,uid):conn.rollback(); await q.answer('Ya tienes otra batalla Pokémon pendiente o activa.',show_alert=True); return True
            user_mons=[]
            for pid in selected:
                c.execute("SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp,held_item_code,sex FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); rr=c.fetchone()
                if not rr:conn.rollback(); await q.answer('Uno de tus Pokémon ya no está disponible.',show_alert=True); return True
                user_mons.append(_battle_mon(rr))
            definition=NPC_ALL[key]; pool=list(definition['pool']); chosen=[]
            if key=='halloween_boss':
                chosen=[92,105,94][:mode]  # Gastly → Marowak → Gengar; Gengar siempre cierra el jefe.
            elif key=='halloween_trainer':
                chosen=[92,93,105][:mode]
            elif key in ROCKET_EVENT_NPCS or key in LEAGUE_NPCS:
                chosen=list(pool[:mode])
            else:
                while len(chosen)<mode:
                    chosen.append(pool[len(chosen)%len(pool)] if kind=='leader' else random.choice(pool))
            # Escalado por Pokémon correspondiente. Rocket/Liga son deliberadamente más difíciles.
            if key=='halloween_boss':level_offsets=[2,3,4]
            elif key=='halloween_trainer':level_offsets=[1,2,3]
            elif key in ('jessie_event','james_event'):level_offsets=[3,4,5]
            elif key=='rocket_exec_event':level_offsets=[2,3,4]
            elif key=='rocket_grunt_event':level_offsets=[1,2,3]
            elif key in LEAGUE_NPCS:level_offsets=[4,5,6]
            else:level_offsets=[0,1,2]
            bot_mons=[_make_npc_mon(sp,max(1,min(MAX_LEVEL,int(user_mons[i]['level'])+random.choice(level_offsets)))) for i,sp in enumerate(chosen)]
            bot_id=-1_000_000-eid
            state={'status':'active','battle_kind':'leader' if kind=='leader' else 'npc','human_user_id':uid,'bot_player_id':bot_id,'npc_encounter_id':eid,'npc_key':key,'mode':mode,'round':1,'choices':{},
                   'players':{str(uid):{'name':_display_name_cursor(c,uid),'mons':user_mons,'active':0},str(bot_id):{'name':definition['name'],'mons':bot_mons,'active':0}}}
            c.execute("INSERT INTO pokemon_battles_tb(chat_id,thread_id,challenger_id,opponent_id,mode,status,state_json,message_id) VALUES(%s,%s,%s,%s,%s,'active',%s,%s) RETURNING battle_id",
                      (group[0],group[1],uid,bot_id,mode,json.dumps(state,ensure_ascii=False),group[2])); bid=int(c.fetchone()[0])
            c.execute("UPDATE pokemon_npc_encounters_tb SET status='battling',battle_id=%s WHERE encounter_id=%s",(bid,eid)); conn.commit()
        except Exception as e:conn.rollback(); print('[PK npc start]',type(e).__name__,e); await q.answer('No pude iniciar el combate.',show_alert=True); return True
        finally:_put_connection(conn)
        await q.answer('¡Combate iniciado!')
        battle_msg=None
        try:battle_msg=await context.bot.send_message(group[0],_battle_text(state,f"{_npc_label(key)} · niveles ajustados a tu equipo"),message_thread_id=group[1],reply_markup=_battle_markup(bid))
        except Exception:pass
        if battle_msg is not None:
            await _store_battle_public_message_id(bid,int(battle_msg.message_id)); group=(group[0],group[1],int(battle_msg.message_id))
        await _sync_single_battle_views(context,bid,state,group[0],group[1],group[2],f"{_npc_label(key)} · niveles ajustados a tu equipo")
        try:await q.edit_message_text('✅ Equipo elegido. La batalla ya está visible en el grupo y en tu panel privado.')
        except Exception:pass
        return True
    if action=='npcbonus':
        bid=int(p[2]); pid=int(p[3]); conn=_get_connection(); notes=[]
        try:
            c=conn.cursor(); c.execute("SELECT user_id,eligible_pokemon_json,claimed_pokemon_id FROM pokemon_leader_bonus_tb WHERE battle_id=%s FOR UPDATE",(bid,)); r=c.fetchone()
            if not r or int(r[0])!=uid:conn.rollback(); await q.answer('Ese bono no es tuyo.',show_alert=True); return True
            if r[2] is not None:conn.rollback(); await q.answer('Ese bono ya fue usado.',show_alert=True); return True
            eligible=[int(x) for x in json.loads(r[1] or '[]')]
            if pid not in eligible:conn.rollback(); await q.answer('Ese Pokémon no era elegible.',show_alert=True); return True
            c.execute("SELECT 1 FROM pokemon_instances_tb WHERE pokemon_id=%s AND owner_id=%s",(pid,uid))
            if not c.fetchone():conn.rollback(); await q.answer('Ese Pokémon ya no te pertenece.',show_alert=True); return True
            notes=_grant_pokemon_xp_cursor(c,pid,LEADER_BONUS_XP); c.execute("UPDATE pokemon_leader_bonus_tb SET claimed_pokemon_id=%s,claimed_at=NOW() WHERE battle_id=%s",(pid,bid)); conn.commit()
        except Exception as e:conn.rollback(); await q.answer('No pude aplicar el bono.',show_alert=True); return True
        finally:_put_connection(conn)
        await q.answer(f'+{LEADER_BONUS_XP} XP aplicado.',show_alert=True)
        try:await q.edit_message_reply_markup(reply_markup=None)
        except Exception:pass
        if notes:
            try:await q.message.reply_text('\n'.join(notes))
            except Exception:pass
        return True
    if action in ('leg','legthrow','legmaster'):
        eid=int(p[2]); conn=_get_connection(); row=None
        try:
            c=conn.cursor(); c.execute("SELECT encounter_id,owner_id,chat_id,thread_id,species_id,level,shiny,attempts,max_attempts,status,message_id,(expires_at<=NOW()) AS expired FROM pokemon_legendary_encounters_tb WHERE encounter_id=%s FOR UPDATE",(eid,)); row=c.fetchone()
            if not row:conn.rollback(); await q.answer('Encuentro no disponible.',show_alert=True); return True
            if int(row[1])!=uid:conn.rollback(); await q.answer('Este encuentro legendario pertenece a otro entrenador.',show_alert=True); return True
            if bool(row[11]) and row[9] in ('active','revealed'):
                c.execute("UPDATE pokemon_legendary_encounters_tb SET status='expired',finished_at=NOW() WHERE encounter_id=%s",(eid,)); conn.commit()
                try:await q.edit_message_text('⌛ El encuentro legendario terminó.\n\n'+_legendary_public_text(row,True),reply_markup=None)
                except Exception:pass
                await q.answer('Llegaste tarde: el encuentro ya expiró.',show_alert=True); return True
            if row[9] not in ('active','revealed'):conn.rollback(); await q.answer('El encuentro ya terminó.',show_alert=True); return True
            if action=='leg':
                c.execute("UPDATE pokemon_legendary_encounters_tb SET status='revealed' WHERE encounter_id=%s",(eid,));
                c.execute("SELECT qty FROM pokemon_items_tb WHERE owner_id=%s AND item_code='master_ball'",(uid,)); mb=c.fetchone(); has=bool(mb and int(mb[0])>0); conn.commit()
                kbrow=[InlineKeyboardButton('🎲 Lanzar Poké Ball',callback_data=f'pk:legthrow:{eid}')]
                if has:kbrow.append(InlineKeyboardButton('🟣 Usar Master Ball',callback_data=f'pk:legmaster:{eid}'))
                await q.answer('¡Legendario revelado!'); await q.edit_message_text(_legendary_public_text(row,True),reply_markup=InlineKeyboardMarkup([kbrow])); return True
            species,level,shiny,attempts,max_attempts=int(row[4]),int(row[5]),bool(row[6]),int(row[7]),int(row[8])
            if action=='legmaster':
                c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code='master_ball' AND qty>0 RETURNING qty",(uid,))
                if not c.fetchone():conn.rollback(); await q.answer('Ya no tienes Master Ball.',show_alert=True); return True
                caught=grant_pokemon_with_cursor(c,uid,species,f'kanto_legendary:{eid}',level_override=level,shiny_override=shiny)
                halloween_candies=_halloween_award_species_cursor(c,uid,[species])
                c.execute("UPDATE pokemon_legendary_encounters_tb SET status='caught',finished_at=NOW() WHERE encounter_id=%s",(eid,)); conn.commit()
                extra=f"\n🎃🍬 +{halloween_candies} Dulces Halloween" if halloween_candies>0 else ''
                await q.answer('🟣 ¡Captura garantizada!',show_alert=True); await q.edit_message_text(f"🟣 MASTER BALL\n\n🎉 ¡Capturaste a #{species:03d} {'✨ SHINY ' if shiny else ''}{NAMES[species]} Nv.{level}!\n{_sex_text(caught.get('sex'))}\n🧬 IV: {caught.get('iv_percent',0)}% · {caught.get('iv_grade','')}\n🎮 Ejemplar #{caught.get('pokemon_id')}{extra}",reply_markup=None); return True
            attempts+=1; c.execute("UPDATE pokemon_legendary_encounters_tb SET attempts=%s WHERE encounter_id=%s",(attempts,eid)); conn.commit()
        except Exception as e:conn.rollback(); print('[PK legendary action]',type(e).__name__,e); await q.answer('No pude preparar la captura.',show_alert=True); return True
        finally:_put_connection(conn)
        await q.answer(f'🎲 Tiro {attempts}/{max_attempts}...')
        try:
            dice=await context.bot.send_dice(chat_id=q.message.chat_id,message_thread_id=getattr(q.message,'message_thread_id',None),emoji='🎲'); value=int(dice.dice.value)
        except Exception as e:
            conn=_get_connection()
            try:
                c=conn.cursor(); c.execute("UPDATE pokemon_legendary_encounters_tb SET attempts=GREATEST(attempts-1,0) WHERE encounter_id=%s AND status='revealed'",(eid,)); conn.commit()
            except Exception:conn.rollback()
            finally:_put_connection(conn)
            print('[PK legendary dice]',type(e).__name__,e)
            try:await context.bot.send_message(q.message.chat_id,'⚠️ Telegram no pudo lanzar el dado. Ese intento no se consumió.',message_thread_id=getattr(q.message,'message_thread_id',None))
            except Exception:pass
            return True
        await asyncio.sleep(WILD_DICE_ANIMATION_SECONDS); threshold=WILD_CATCH_THRESHOLD.get('legendario',6); effect={1:'PÉSIMO',2:'FLOJO',3:'BIEN',4:'MUY BIEN',5:'EXCELENTE',6:'PERFECTO'}[value]
        conn=_get_connection(); caught=None; halloween_candies=0
        try:
            c=conn.cursor(); c.execute("SELECT status,attempts,max_attempts FROM pokemon_legendary_encounters_tb WHERE encounter_id=%s FOR UPDATE",(eid,)); st=c.fetchone()
            if not st or st[0]!='revealed':conn.rollback(); return True
            if value>=threshold:
                caught=grant_pokemon_with_cursor(c,uid,species,f'kanto_legendary:{eid}',level_override=level,shiny_override=shiny); halloween_candies=_halloween_award_species_cursor(c,uid,[species]); c.execute("UPDATE pokemon_legendary_encounters_tb SET status='caught',finished_at=NOW() WHERE encounter_id=%s",(eid,))
            elif attempts>=max_attempts:c.execute("UPDATE pokemon_legendary_encounters_tb SET status='escaped',finished_at=NOW() WHERE encounter_id=%s",(eid,))
            conn.commit()
        except Exception:conn.rollback()
        finally:_put_connection(conn)
        if caught:
            extra=f"\n🎃🍬 +{halloween_candies} Dulces Halloween" if halloween_candies>0 else ''
            await q.edit_message_text(f"🎲 {value}/6 · {effect}\n🎉 ¡Capturaste a #{species:03d} {'✨ SHINY ' if shiny else ''}{NAMES[species]} Nv.{level}!\n{_sex_text(caught.get('sex'))}\n🧬 IV: {caught.get('iv_percent',0)}% · {caught.get('iv_grade','')}\n🎮 Ejemplar #{caught.get('pokemon_id')}{extra}",reply_markup=None); return True
        if attempts>=max_attempts:
            await q.edit_message_text(f"🎲 {value}/6 · {effect}\n❌ Fallaron los {max_attempts} tiros.\n\n#{species:03d} {'✨ SHINY ' if shiny else ''}{NAMES[species]} escapó.",reply_markup=None); return True
        conn=_get_connection()
        try:c=conn.cursor(); c.execute("SELECT qty FROM pokemon_items_tb WHERE owner_id=%s AND item_code='master_ball'",(uid,)); mb=c.fetchone(); has=bool(mb and int(mb[0])>0)
        finally:_put_connection(conn)
        buttons=[InlineKeyboardButton('🎲 Otro intento',callback_data=f'pk:legthrow:{eid}')]
        if has:buttons.append(InlineKeyboardButton('🟣 Usar Master Ball',callback_data=f'pk:legmaster:{eid}'))
        shown=list(row[:11]); shown[7]=attempts
        await q.edit_message_text(f"🎲 {value}/6 · {effect}\n💨 {NAMES[species]} escapó de la Poké Ball.\n\n{_legendary_public_text(shown,True)}",reply_markup=InlineKeyboardMarkup([buttons])); return True
    if action=='dcancel':
        bid=int(p[2]); conn=_get_connection()
        try:c=conn.cursor(); c.execute("UPDATE pokemon_battles_tb SET status='cancelled',finished_at=NOW() WHERE battle_id=%s AND challenger_id=%s AND status='open' RETURNING battle_id",(bid,uid)); ok=c.fetchone(); conn.commit()
        except Exception:conn.rollback(); ok=None
        finally:_put_connection(conn)
        await q.answer('Cancelado.' if ok else 'Ya no se puede cancelar.',show_alert=True); return True
    if action=='daccept':
        bid=int(p[2]); conn=_get_connection(); state=None
        try:
            c=conn.cursor(); c.execute("SELECT challenger_id,opponent_id,status,chat_id,thread_id FROM pokemon_battles_tb WHERE battle_id=%s FOR UPDATE",(bid,)); br=c.fetchone()
            if not br or br[2]!='open':conn.rollback(); await q.answer('Ese reto ya no está disponible.',show_alert=True); return True
            challenger=int(br[0]); invited=int(br[1]) if br[1] is not None else None
            if uid==challenger or (invited is not None and uid!=invited):conn.rollback(); await q.answer('Este reto no te corresponde.',show_alert=True); return True
            c.execute("SELECT 1 FROM pokemon_battles_tb WHERE battle_id<>%s AND status IN ('open','active') AND (challenger_id IN (%s,%s) OR opponent_id IN (%s,%s)) LIMIT 1",(bid,challenger,uid,challenger,uid))
            if c.fetchone():conn.rollback(); await q.answer('Uno de los dos ya entró en otra batalla Pokémon.',show_alert=True); return True
            a=_team_for_battle_cursor(c,challenger,4); b=_team_for_battle_cursor(c,uid,4)
            if not a or not b:conn.rollback(); await q.answer('Los dos necesitan 4 Pokémon ocupando los 4 espacios de /equipo.',show_alert=True); return True
            state={'status':'setup','battle_kind':'double_pvp','mode':4,'round':1,'choices':{},'double_leads':{},'double_ready':{},'players':{str(challenger):{'name':_display_name_cursor(c,challenger),'mons':a,'active':[]},str(uid):{'name':_display_name_cursor(c,uid),'mons':b,'active':[]}}}
            c.execute("UPDATE pokemon_battles_tb SET opponent_id=%s,status='active',state_json=%s,message_id=%s,updated_at=NOW() WHERE battle_id=%s",(uid,json.dumps(state,ensure_ascii=False),q.message.message_id,bid)); conn.commit()
        except Exception as e:conn.rollback(); print('[PK double accept]',type(e).__name__,e); await q.answer('No pude iniciar la preparación.',show_alert=True); return True
        finally:_put_connection(conn)
        await q.answer('¡Aceptada! Revisa tu privado.')
        for player in (int(br[0]),uid):
            try:await context.bot.send_message(player,'⚔️ BATALLA DOBLE · ELIGE LOS 2 QUE SALEN PRIMERO',reply_markup=_double_lead_markup(bid,state,player))
            except Exception:pass
        await q.edit_message_text('⚔️ BATALLA DOBLE 4v4\n\nCada entrenador está eligiendo en privado sus 2 Pokémon iniciales.'); return True
    if action in ('dlead','dleadok'):
        bid=int(p[2]); conn=_get_connection(); state=None; start=False; chat=None
        try:
            c=conn.cursor(); c.execute("SELECT state_json,status,chat_id,thread_id,message_id FROM pokemon_battles_tb WHERE battle_id=%s FOR UPDATE",(bid,)); br=c.fetchone()
            if not br or br[1]!='active':conn.rollback(); await q.answer('Batalla no disponible.',show_alert=True); return True
            state=json.loads(br[0]); key=str(uid)
            if state.get('battle_kind')!='double_pvp' or key not in state['players']:conn.rollback(); await q.answer('No participas.',show_alert=True); return True
            selected=[int(x) for x in state.setdefault('double_leads',{}).get(key,[])]
            if action=='dlead':
                idx=int(p[3]);
                if idx in selected:selected.remove(idx)
                elif len(selected)<2:selected.append(idx)
                else:conn.rollback(); await q.answer('Ya elegiste 2.',show_alert=True); return True
                state['double_leads'][key]=selected
            else:
                if len(selected)!=2:conn.rollback(); await q.answer('Elige exactamente 2.',show_alert=True); return True
                state.setdefault('double_ready',{})[key]=True
                if all(state['double_ready'].get(x) for x in state['players']):
                    for x in state['players']:state['players'][x]['active']=[int(v) for v in state['double_leads'][x]]
                    state['status']='active'; start=True
            c.execute("UPDATE pokemon_battles_tb SET state_json=%s,updated_at=NOW() WHERE battle_id=%s",(json.dumps(state,ensure_ascii=False),bid)); conn.commit(); chat=(int(br[2]),br[3],br[4])
        except Exception as e:conn.rollback(); await q.answer('No pude guardar la selección.',show_alert=True); return True
        finally:_put_connection(conn)
        if start:
            await q.answer('¡Batalla lista!')
            await _sync_double_battle_views(context,bid,state,chat[0],chat[1],chat[2],'Las acciones y objetivos se eligen por privado.')
            try:await q.edit_message_text('✅ Pareja inicial confirmada. La batalla ya está sincronizada en el grupo y en privado.')
            except Exception:pass
        else:
            await q.answer(); await q.edit_message_text('⚔️ Elige 2 Pokémon iniciales:',reply_markup=_double_lead_markup(bid,state,uid))
        return True
    if action=='daction':
        bid=int(p[2]); br=_get_battle(bid)
        if not br or br[6]!='active':await q.answer('La batalla terminó.',show_alert=True); return True
        state=json.loads(br[7]); key=str(uid)
        if state.get('battle_kind')!='double_pvp' or key not in state['players']:await q.answer('No participas.',show_alert=True); return True
        if state.get('replacement_needed',{}).get(key):await q.answer('Primero elige el reemplazo de tu Pokémon debilitado.',show_alert=True); return True
        sent=await _sync_double_private_only(context,bid,state,uid)
        if sent is not None:await q.answer('Tu panel privado está actualizado.')
        else:await q.answer('Abre primero el privado de PiBot con /start.',show_alert=True)
        return True
    if action=='dmon':
        bid=int(p[2]); pos=int(p[3]); br=_get_battle(bid)
        if not br or br[6]!='active':await q.answer('Terminó.',show_alert=True); return True
        state=json.loads(br[7]); key=str(uid)
        if state.get('battle_kind')!='double_pvp' or key not in state.get('players',{}):await q.answer('No participas.',show_alert=True); return True
        if state.get('status')!='active' or state.get('replacement_needed',{}).get(key):await q.answer('Primero completa los reemplazos pendientes.',show_alert=True); return True
        pl=state['players'][key]
        if pos not in (0,1) or pos>=len(pl.get('active',[])) or pl['mons'][pl['active'][pos]]['hp']<=0:await q.answer('Ese Pokémon ya no puede actuar.',show_alert=True); return True
        await q.answer(); await _send_battle_transient(context,bid,uid,'Elige movimiento:',_double_mon_action_markup(bid,state,uid,pos)); return True
    if action=='dmove':
        bid,pos,mi=int(p[2]),int(p[3]),int(p[4]); br=_get_battle(bid)
        if not br or br[6]!='active':await q.answer('Terminó.',show_alert=True); return True
        state=json.loads(br[7]); key=str(uid)
        if state.get('battle_kind')!='double_pvp' or key not in state['players']:await q.answer('No participas.',show_alert=True); return True
        if state.get('status')!='active' or state.get('replacement_needed',{}).get(key):await q.answer('Primero completa los reemplazos pendientes.',show_alert=True); return True
        pstate=state['players'][key]
        if pos not in (0,1) or pos>=len(pstate.get('active',[])):await q.answer('Posición inválida.',show_alert=True); return True
        idx=pstate['active'][pos]; mon=pstate['mons'][idx]
        if mon['hp']<=0:await q.answer('Ese Pokémon está debilitado.',show_alert=True); return True
        if mi<0 or mi>=len(mon['moves']):await q.answer('Movimiento inválido.',show_alert=True); return True
        code=mon['moves'][mi]
        locked=mon.get('choice_lock') if mon.get('held_item') in ('choice_band','choice_specs','choice_scarf') else None
        if locked and code!=locked:await q.answer(f"{_item_name(mon.get('held_item'))} te mantiene usando {MOVES.get(locked,(locked,))[0]}.",show_alert=True); return True
        if int(mon.get('pp',{}).get(code,0))<=0:await q.answer('Sin PP.',show_alert=True); return True
        ids=list(state['players']); opp=ids[1] if key==ids[0] else ids[0]; rows=[]
        for tpos,tidx in enumerate(state['players'][opp]['active']):
            tm=state['players'][opp]['mons'][tidx]
            if tm['hp']>0:rows.append([InlineKeyboardButton(f"🎯 {_battle_title_mon(tm)} · {tm['hp']}/{tm['max_hp']} HP",callback_data=f'pk:dtarget:{bid}:{pos}:{mi}:{tpos}')])
        await q.answer(); await _send_battle_transient(context,bid,uid,f"Objetivo para {MOVES[code][0]}:",InlineKeyboardMarkup(rows)); return True
    if action in ('dtarget','dswitch'):
        bid=int(p[2]); conn=_get_connection(); state=None; final=None; logs=[]; chat=None
        try:
            c=conn.cursor(); c.execute("SELECT state_json,status,chat_id,thread_id,message_id FROM pokemon_battles_tb WHERE battle_id=%s FOR UPDATE",(bid,)); br=c.fetchone()
            if not br or br[1]!='active':conn.rollback(); await q.answer('La batalla terminó.',show_alert=True); return True
            state=json.loads(br[0]); key=str(uid)
            if state.get('battle_kind')!='double_pvp' or key not in state['players']:conn.rollback(); await q.answer('No participas.',show_alert=True); return True
            if state.get('status')!='active':conn.rollback(); await q.answer('La batalla todavía está preparando reemplazos.',show_alert=True); return True
            if action=='dtarget':
                pos,mi,tpos=int(p[3]),int(p[4]),int(p[5]); pl=state['players'][key]; src=pl['active'][pos]; mon=pl['mons'][src]
                if mi<0 or mi>=len(mon['moves']):conn.rollback(); await q.answer('Movimiento inválido.',show_alert=True); return True
                code=mon['moves'][mi]
                locked=mon.get('choice_lock') if mon.get('held_item') in ('choice_band','choice_specs','choice_scarf') else None
                if locked and code!=locked:conn.rollback(); await q.answer(f"{_item_name(mon.get('held_item'))} te mantiene usando {MOVES.get(locked,(locked,))[0]}.",show_alert=True); return True
                if int(mon.get('pp',{}).get(code,0))<=0:conn.rollback(); await q.answer('Sin PP.',show_alert=True); return True
                state.setdefault('choices',{}).setdefault(key,{})[str(pos)]={'type':'move','move':code,'target':tpos,'source':src}
            else:
                pos,new=int(p[3]),int(p[4]); pl=state['players'][key]; src=pl['active'][pos]
                if new in pl['active'] or new<0 or new>=len(pl['mons']) or pl['mons'][new]['hp']<=0:conn.rollback(); await q.answer('Cambio inválido.',show_alert=True); return True
                state.setdefault('choices',{}).setdefault(key,{})[str(pos)]={'type':'switch','index':new,'source':src}
            winner,logs,state=_resolve_double_round_cursor(c,bid,state)
            if winner is not None:final=_finish_battle_cursor(c,bid,state)
            else:c.execute("UPDATE pokemon_battles_tb SET state_json=%s,updated_at=NOW() WHERE battle_id=%s",(json.dumps(state,ensure_ascii=False),bid))
            conn.commit(); chat=(int(br[2]),br[3],br[4])
        except Exception as e:conn.rollback(); print('[PK double action]',type(e).__name__,e); await q.answer('No pude registrar la acción.',show_alert=True); return True
        finally:_put_connection(conn)
        await q.answer('Acción elegida ✅')
        # El selector usado ya no sirve; se borra para no acumular menús por ronda.
        await _delete_battle_transients(context,bid,uid)
        if logs or final:
            await _delete_all_battle_transients(context,bid,state)
        note='\n'.join(logs[-10:]) if logs else 'Esperando las demás acciones…'
        await _sync_double_battle_views(context,bid,state,chat[0],chat[1],chat[2],note,final=bool(final))
        if final:
            try:
                from handlers.season_pass import grant_season_xp
                grant_season_xp(final['winner'],WIN_SEASON_XP,'pokemon_double'); grant_season_xp(final['loser'],LOSS_SEASON_XP,'pokemon_double')
            except Exception:pass
            w=state['players'][str(final['winner'])]['name']; l=state['players'][str(final['loser'])]['name']
            wxp=int(final.get('xp_rewards',{}).get(str(final['winner']),WIN_POKEMON_XP)); lxp=int(final.get('xp_rewards',{}).get(str(final['loser']),LOSS_POKEMON_XP))
            result_text=f"🏆 {w} ganó la batalla doble Pokémon.\n💰 {w}: +{WIN_PIPESOS:,} PiPesos\n💰 {l}: +{LOSS_PIPESOS:,} PiPesos\n🎮 Los 4 Pokémon: ganador +{wxp} XP c/u · rival +{lxp} XP c/u\n📈 Ranking: ±{final['elo']} puntos"
            if final.get('notes'):result_text+='\n'+'\n'.join(final['notes'][:6])
            await _update_double_public_final(context,bid,state,chat[0],chat[1],chat[2],note,result_text)
            await _send_private_battle_result(context,state,result_text,skip_chat_id=chat[0])
        return True
    if action=='dswitchmenu':
        bid,pos=int(p[2]),int(p[3]); br=_get_battle(bid)
        if not br or br[6]!='active':await q.answer('Terminó.',show_alert=True); return True
        state=json.loads(br[7]); key=str(uid)
        if key not in state['players']:await q.answer('No participas.',show_alert=True); return True
        pl=state['players'][key]; rows=[]
        for i,m in enumerate(pl['mons']):
            if i not in pl['active'] and m['hp']>0:rows.append([InlineKeyboardButton(f"🔄 {_battle_title_mon(m)} · {m['hp']}/{m['max_hp']} HP",callback_data=f'pk:dswitch:{bid}:{pos}:{i}')])
        if not rows:await q.answer('No tienes reserva disponible.',show_alert=True); return True
        await q.answer(); await _send_battle_transient(context,bid,uid,'Elige cambio:',InlineKeyboardMarkup(rows)); return True
    if action=='dreplace':
        bid,pos,new=int(p[2]),int(p[3]),int(p[4]); conn=_get_connection(); state=None; chat=None
        try:
            c=conn.cursor(); c.execute("SELECT state_json,status,chat_id,thread_id,message_id FROM pokemon_battles_tb WHERE battle_id=%s FOR UPDATE",(bid,)); br=c.fetchone()
            if not br or br[1]!='active':conn.rollback(); await q.answer('Terminó.',show_alert=True); return True
            state=json.loads(br[0]); key=str(uid); need=state.get('replacement_needed',{}).get(key,[]); pl=state['players'].get(key)
            if pl is None or pos not in need or new in pl['active'] or new<0 or new>=len(pl['mons']) or pl['mons'][new]['hp']<=0:conn.rollback(); await q.answer('Reemplazo inválido.',show_alert=True); return True
            pl['active'][pos]=new; _double_fill_forced_replacements(state); c.execute("UPDATE pokemon_battles_tb SET state_json=%s,updated_at=NOW() WHERE battle_id=%s",(json.dumps(state,ensure_ascii=False),bid)); conn.commit(); chat=(int(br[2]),br[3],br[4])
        except Exception:conn.rollback(); await q.answer('No pude cambiarlo.',show_alert=True); return True
        finally:_put_connection(conn)
        await q.answer('Reemplazo listo ✅')
        await _delete_battle_transients(context,bid,uid)
        try:await q.edit_message_text('✅ Pokémon enviado al campo.')
        except Exception:pass
        await _sync_double_battle_views(context,bid,state,chat[0],chat[1],chat[2],'Reemplazos listos.')
        return True
    if action=='dsurrender':
        bid=int(p[2]); conn=_get_connection(); state=None; final=None; chat=None
        try:
            c=conn.cursor(); c.execute("SELECT state_json,status,chat_id,thread_id,message_id FROM pokemon_battles_tb WHERE battle_id=%s FOR UPDATE",(bid,)); br=c.fetchone()
            if not br or br[1]!='active':conn.rollback(); await q.answer('Ya terminó.',show_alert=True); return True
            state=json.loads(br[0]); key=str(uid)
            if state.get('battle_kind')!='double_pvp' or key not in state['players']:conn.rollback(); await q.answer('No participas.',show_alert=True); return True
            ids=list(state['players']); other=int(ids[1] if key==ids[0] else ids[0]); state['status']='finished'; state['winner']=other; state['loser']=uid; final=_finish_battle_cursor(c,bid,state); conn.commit(); chat=(int(br[2]),br[3],br[4])
        except Exception:conn.rollback(); await q.answer('No pude rendirte.',show_alert=True); return True
        finally:_put_connection(conn)
        await q.answer('Te rendiste.',show_alert=True)
        await _delete_all_battle_transients(context,bid,state)
        await _sync_double_battle_views(context,bid,state,chat[0],chat[1],chat[2],f"🏳 {state['players'][str(uid)]['name']} se rindió.",final=True)
        try:
            from handlers.season_pass import grant_season_xp
            grant_season_xp(final['winner'],WIN_SEASON_XP,'pokemon_double'); grant_season_xp(final['loser'],LOSS_SEASON_XP,'pokemon_double')
        except Exception:pass
        w=state['players'][str(final['winner'])]['name']; l=state['players'][str(final['loser'])]['name']
        wxp=int(final.get('xp_rewards',{}).get(str(final['winner']),WIN_POKEMON_XP)); lxp=int(final.get('xp_rewards',{}).get(str(final['loser']),LOSS_POKEMON_XP))
        result_text=f"🏆 {w} ganó la batalla doble Pokémon.\n💰 {w}: +{WIN_PIPESOS:,} PiPesos\n💰 {l}: +{LOSS_PIPESOS:,} PiPesos\n🎮 Los 4 Pokémon: ganador +{wxp} XP c/u · rival +{lxp} XP c/u\n📈 Ranking: ±{final['elo']} puntos"
        if final.get('notes'):result_text+='\n'+'\n'.join(final['notes'][:6])
        await _update_double_public_final(context,bid,state,chat[0],chat[1],chat[2],f"🏳 {state['players'][str(uid)]['name']} se rindió.",result_text)
        await _send_private_battle_result(context,state,result_text,skip_chat_id=chat[0])
        return True
    return False


async def pokemon_callback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; p=q.data.split(':'); uid=q.from_user.id
    action=p[1]
    if action=='noop':return await q.answer()
    if action in ('learnreplace','learnskip'):
        req=int(p[2]); conn=_get_connection(); result=None
        try:
            c=conn.cursor(); c.execute("""SELECT ml.owner_id,ml.pokemon_id,ml.move_code,ml.status,p.species_id,p.nickname,p.moves_json
                                         FROM pokemon_move_learning_tb ml JOIN pokemon_instances_tb p ON p.pokemon_id=ml.pokemon_id
                                         WHERE ml.request_id=%s FOR UPDATE""",(req,)); row=c.fetchone()
            if not row or int(row[0])!=uid:conn.rollback(); return await q.answer('Ese aprendizaje no es tuyo.',show_alert=True)
            if str(row[3])!='pending':conn.rollback(); return await q.answer('Ese aprendizaje ya fue resuelto.',show_alert=True)
            pid,code,species,nick=int(row[1]),str(row[2]),int(row[4]),row[5]
            try:moves=[str(x) for x in json.loads(row[6] or '[]') if str(x) in MOVES]
            except Exception:moves=[]
            mon_name=nick or NAMES.get(species,'Pokémon'); move_name=MOVES.get(code,(code,))[0]
            if action=='learnskip':
                c.execute("UPDATE pokemon_move_learning_tb SET status='skipped',resolved_at=NOW() WHERE request_id=%s",(req,)); conn.commit(); result=f'❌ {mon_name} no aprendió {move_name}.'
            else:
                idx=int(p[3])
                if not (0<=idx<len(moves)):conn.rollback(); return await q.answer('Ese movimiento ya no está disponible para reemplazar.',show_alert=True)
                if code in moves:
                    c.execute("UPDATE pokemon_move_learning_tb SET status='learned',resolved_at=NOW() WHERE request_id=%s",(req,)); conn.commit(); result=f'📚 {mon_name} ya conocía {move_name}.'
                else:
                    old=moves[idx]; moves[idx]=code
                    c.execute("UPDATE pokemon_instances_tb SET moves_json=%s,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s",(json.dumps(moves[:4],ensure_ascii=False),uid,pid))
                    c.execute("UPDATE pokemon_move_learning_tb SET status='learned',resolved_at=NOW() WHERE request_id=%s",(req,)); conn.commit(); result=f'📚 {mon_name} olvidó {MOVES.get(old,(old,))[0]} y aprendió {move_name}.'
        except Exception as e:
            conn.rollback(); print('[PK level move replace]',type(e).__name__,e); return await q.answer('No pude guardar el movimiento.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Movimiento actualizado ✅',show_alert=True)
        try:await q.edit_message_text(result,reply_markup=None)
        except Exception:pass
        await _notify_pending_move_learning(context,uid)
        return
    if await _pokemon_extended_callback(update,context,p,action,uid):return
    if action=='seasonbox':
        box_id=int(p[2]); _ensure_pokemon_season(); conn=_get_connection(); data=None
        try:
            c=conn.cursor(); c.execute("SELECT owner_id,season_key,placement,opened FROM pokemon_season_boxes_tb WHERE box_id=%s FOR UPDATE",(box_id,)); br=c.fetchone()
            if not br or int(br[0])!=uid:conn.rollback(); return await q.answer('Esa caja no es tuya.',show_alert=True)
            if br[3]:conn.rollback(); return await q.answer('Esa caja ya fue abierta.',show_alert=True)
            species=roll_box_pokemon('legendary')
            gifted=str(br[1]).startswith('regalo:')
            source='gift_box' if gifted else f"season_box:{br[1]}:{br[2]}"
            data=grant_pokemon_with_cursor(c,uid,species,source,force_shiny=True)
            held_drop=_roll_box_held_item('legendary')
            if held_drop:grant_item_with_cursor(c,uid,held_drop,1)
            data['held_drop']=held_drop
            c.execute("UPDATE pokemon_season_boxes_tb SET opened=TRUE,pokemon_id=%s,opened_at=NOW() WHERE box_id=%s",(data['pokemon_id'],box_id)); conn.commit()
        except Exception as e:
            conn.rollback(); print('[PK season box]',type(e).__name__,e); return await q.answer('No pude abrir la caja.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('✨ ¡SHINY garantizado!',show_alert=True)
        if str(br[1]).startswith('regalo:'):box_title='🎁 CAJA POKÉMON DE BIENVENIDA'
        elif str(br[1]).startswith('kanto_complete:'):box_title='🏆 CAJA POKÉMON · KANTO 8/8'
        else:box_title='🎁 CAJA POKÉMON DE TEMPORADA'
        extra=''
        if data.get('held_drop') in HELD_ITEMS:
            x=HELD_ITEMS[data['held_drop']]; extra=f"\n🎁 Objeto equipable: {x['emoji']} {x['name']}"
        return await q.edit_message_text(f"{box_title}\n\n✨ ¡Te salió #{data['species_id']:03d} SHINY {data['name']} {_sex_symbol(data.get('sex'))}!\n⭐ Nv.{data['level']} · 🧬 IV {data['iv_percent']}% · {data['iv_grade']}{extra}\n\nSe agregó a tu colección, no a tu equipo.")
    if action=='tcreate':
        mode=int(p[2])
        try:
            member=await context.bot.get_chat_member(q.message.chat_id,uid); allowed=(member.status in ('administrator','creator')) or is_botmaster(uid)
        except Exception:
            try: allowed=is_botmaster(uid)
            except Exception: allowed=False
        if not allowed:return await q.answer('Solo admins pueden crear torneos.',show_alert=True)
        conn=_get_connection(); tid=None
        try:
            c=conn.cursor(); existing=_tournament_active_cursor(c,q.message.chat_id,getattr(q.message,'message_thread_id',None))
            if existing:conn.rollback(); return await q.answer('Ya hay un torneo abierto aquí.',show_alert=True)
            c.execute("INSERT INTO pokemon_tournaments_tb(chat_id,thread_id,created_by,mode) VALUES(%s,%s,%s,%s) RETURNING tournament_id",(q.message.chat_id,getattr(q.message,'message_thread_id',None),uid,mode)); tid=int(c.fetchone()[0]); conn.commit()
        except Exception as e:conn.rollback(); print('[PK tournament create]',type(e).__name__,e); return await q.answer('No pude crear el torneo.',show_alert=True)
        finally:_put_connection(conn)
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Participar',callback_data=f'pk:tjoin:{tid}'),InlineKeyboardButton('🚪 Salirme',callback_data=f'pk:tleave:{tid}')],[InlineKeyboardButton('📋 Participantes',callback_data=f'pk:tlist:{tid}'),InlineKeyboardButton('🏁 Iniciar',callback_data=f'pk:tstart:{tid}')],[InlineKeyboardButton('❌ Cancelar torneo',callback_data=f'pk:tcancel:{tid}')]])
        await q.answer('Torneo creado.'); return await q.edit_message_text(f'🏆 TORNEO POKÉMON #{tid} · {mode}v{mode}\n\n👥 Inscripciones abiertas. Máximo {TOURNAMENT_MAX_PLAYERS} participantes.',reply_markup=kb)
    if action in {'tjoin','tleave','tlist','tstart','tcancel','tmatch'}:
        tid=int(p[2]); conn=_get_connection(); out=None; text=None
        try:
            c=conn.cursor(); c.execute("SELECT chat_id,thread_id,created_by,mode,status,round_no FROM pokemon_tournaments_tb WHERE tournament_id=%s FOR UPDATE",(tid,)); tr=c.fetchone()
            if not tr:conn.rollback(); return await q.answer('Torneo no encontrado.',show_alert=True)
            chat_id,thread_id,creator,mode,status,round_no=int(tr[0]),tr[1],int(tr[2]),int(tr[3]),tr[4],int(tr[5])
            if action=='tjoin':
                if status!='registration':conn.rollback(); return await q.answer('Las inscripciones ya cerraron.',show_alert=True)
                c.execute("SELECT COUNT(*) FROM pokemon_tournament_players_tb WHERE tournament_id=%s",(tid,)); count=int(c.fetchone()[0])
                if count>=TOURNAMENT_MAX_PLAYERS:conn.rollback(); return await q.answer('El torneo ya está lleno.',show_alert=True)
                if not _team_for_battle_cursor(c,uid,mode):conn.rollback(); return await q.answer(f'Necesitas {mode} Pokémon en los primeros {mode} espacios de tu equipo.',show_alert=True)
                c.execute("INSERT INTO pokemon_tournament_players_tb(tournament_id,user_id) VALUES(%s,%s) ON CONFLICT DO NOTHING",(tid,uid)); conn.commit(); out='✅ Quedaste inscrito.'
            elif action=='tleave':
                if status!='registration':conn.rollback(); return await q.answer('Ya no puedes salir: el torneo comenzó.',show_alert=True)
                c.execute("DELETE FROM pokemon_tournament_players_tb WHERE tournament_id=%s AND user_id=%s",(tid,uid)); conn.commit(); out='🚪 Saliste del torneo.'
            elif action=='tlist':
                if status=='registration':
                    c.execute("SELECT user_id FROM pokemon_tournament_players_tb WHERE tournament_id=%s ORDER BY joined_at",(tid,)); ids=[int(r[0]) for r in c.fetchall()]
                    text=f'📋 PARTICIPANTES · TORNEO #{tid}\n\n'+('\n'.join(f'{i}. {_tournament_name_cursor(c,u)}' for i,u in enumerate(ids,1)) if ids else 'Todavía no hay participantes.')
                else:text=_tournament_round_text_cursor(c,tid)
                conn.commit()
            elif action in ('tstart','tcancel'):
                try:
                    member=await context.bot.get_chat_member(chat_id,uid); allowed=(member.status in ('administrator','creator')) or is_botmaster(uid)
                except Exception:
                    try: allowed=is_botmaster(uid)
                    except Exception: allowed=False
                if not allowed:conn.rollback(); return await q.answer('Solo admins pueden hacer eso.',show_alert=True)
                if action=='tcancel':
                    if status=='finished':conn.rollback(); return await q.answer('El torneo ya terminó.',show_alert=True)
                    c.execute("UPDATE pokemon_tournaments_tb SET status='cancelled',finished_at=NOW() WHERE tournament_id=%s",(tid,))
                    c.execute("UPDATE pokemon_battles_tb SET status='cancelled',finished_at=NOW(),updated_at=NOW() WHERE tournament_match_id IN (SELECT match_id FROM pokemon_tournament_matches_tb WHERE tournament_id=%s) AND status='open'",(tid,))
                    conn.commit(); text=f'❌ Torneo Pokémon #{tid} cancelado.'
                else:
                    if status!='registration':conn.rollback(); return await q.answer('Ese torneo ya comenzó.',show_alert=True)
                    c.execute("SELECT user_id FROM pokemon_tournament_players_tb WHERE tournament_id=%s ORDER BY joined_at",(tid,)); players=[int(r[0]) for r in c.fetchall()]
                    if len(players)<2:conn.rollback(); return await q.answer('Necesitas al menos 2 participantes.',show_alert=True)
                    random.shuffle(players); _create_tournament_round_cursor(c,tid,1,players); c.execute("UPDATE pokemon_tournaments_tb SET status='active',round_no=1,started_at=NOW() WHERE tournament_id=%s",(tid,)); adv=_advance_tournament_cursor(c,tid); conn.commit(); text=_tournament_round_text_cursor(c,tid) if not (adv and adv.get('finished')) else f'👑 Torneo #{tid} finalizado.'
            elif action=='tmatch':
                if status!='active':conn.rollback(); return await q.answer('El torneo no está activo.',show_alert=True)
                c.execute("""SELECT user_a,user_b FROM pokemon_tournament_matches_tb WHERE tournament_id=%s AND round_no=%s AND status='pending' AND (user_a=%s OR user_b=%s) LIMIT 1""",(tid,round_no,uid,uid)); mr=c.fetchone()
                if not mr:conn.rollback(); return await q.answer('No tienes combate pendiente en esta ronda.',show_alert=True)
                rival=int(mr[1]) if int(mr[0])==uid else int(mr[0]); rname=_tournament_name_cursor(c,rival); conn.commit(); text=f'⚔️ Tu rival es {rname}.\n\nResponde a uno de sus mensajes con /batallapokemon. PiBot detectará el torneo y fijará el formato {mode}v{mode}.'
        except Exception as e:
            conn.rollback(); print('[PK tournament cb]',type(e).__name__,e); return await q.answer('No pude actualizar el torneo.',show_alert=True)
        finally:_put_connection(conn)
        if out:return await q.answer(out,show_alert=True)
        await q.answer()
        if text:return await q.message.reply_text(text)
        return
    if action in {'trainercollection','trainerbrag','trainermedia','trainerremovemedia','trainermediacancel'}:
        owner=int(p[2]) if len(p)>2 and str(p[2]).isdigit() else uid
        if uid!=owner:
            return await q.answer('Ese botón pertenece al perfil de otro entrenador.',show_alert=True)
    if action=='trainercollection':
        try:
            await context.bot.send_message(uid,'🎮 TUS POKÉMON\n\nColección privada. Toca uno para administrarlo.',reply_markup=_collection_markup(uid,0))
            return await q.answer('Te mandé tu colección por privado.')
        except Exception:return await q.answer('Abre primero el privado de PiBot con /start.',show_alert=True)
    if action=='trainerbrag':
        pid=_principal_pid(uid)
        if not pid:return await q.answer('Todavía no tienes Pokémon principal.',show_alert=True)
        ok=await _send_brag(context,uid,pid,{'chat_id':q.message.chat_id,'thread_id':getattr(q.message,'message_thread_id',None)})
        return await q.answer('Presumido 😎' if ok else 'No pude publicarlo.',show_alert=True)
    if action=='trainermedia':
        context.user_data['pk_wait_trainer_media']=True
        try:
            await context.bot.send_message(
                uid,
                '📸 FOTO / GIF / VIDEO DE ENTRENADOR\n\nAhora envíame aquí la foto, GIF o video que quieras usar. PiBot detectará el tipo automáticamente.\n\nSolo se guardará para TU perfil de entrenador.',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:trainermediacancel:{uid}')]])
            )
        except Exception:
            context.user_data.pop('pk_wait_trainer_media',None)
            return await q.answer('Abre primero el privado de PiBot con /start.',show_alert=True)
        return await q.answer('📩 Te mandé el botón/proceso al privado.',show_alert=True)
    if action=='trainermediacancel':
        context.user_data.pop('pk_wait_trainer_media',None)
        return await q.answer('Carga cancelada.',show_alert=True)
    if action=='trainerremovemedia':
        conn=_get_connection()
        try:
            c=conn.cursor(); _ensure_trainer_row_cursor(c,uid)
            c.execute("UPDATE pokemon_trainer_tb SET media_type=NULL,media_file_id=NULL,updated_at=NOW() WHERE user_id=%s",(uid,)); conn.commit()
        except Exception as e:
            conn.rollback(); print('[PK trainer media remove]',type(e).__name__,e); return await q.answer('No pude quitarla.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('🗑 Multimedia de entrenador quitada.',show_alert=True)
        try:await _send_trainer_profile(context,uid,uid,controls=True)
        except Exception:pass
        return
    if action=='wild':
        spawn_id=int(p[2]); method=p[3] if len(p)>3 else None; conn=_get_connection(); spawn=None; attempts=0; prepare_only=False; has_master=False; master_mode=False
        try:
            c=conn.cursor()
            c.execute(
                "SELECT chat_id,thread_id,species_id,level,shiny,status,message_id,caught_by, "
                "(created_at <= NOW() - INTERVAL '10 minutes') AS expired "
                "FROM pokemon_wild_spawns_tb WHERE spawn_id=%s FOR UPDATE",
                (spawn_id,),
            )
            spawn=c.fetchone()
            if not spawn:
                conn.rollback(); return await q.answer('Ese Pokémon ya no está disponible.',show_alert=True)
            if bool(spawn[8]) and spawn[5]=='active':
                c.execute("UPDATE pokemon_wild_spawns_tb SET status='expired',finished_at=NOW() WHERE spawn_id=%s",(spawn_id,)); conn.commit()
                try:
                    await q.edit_message_text('⌛ Pasaron 10 minutos y el Pokémon se fue.\n\n'+_wild_reveal_text(int(spawn[2]),int(spawn[3]),bool(spawn[4])),reply_markup=None)
                except Exception:pass
                return await q.answer('Llegaste tarde: ya pasaron los 10 minutos.',show_alert=True)
            if spawn[5]=='throwing':
                conn.rollback()
                if spawn[7] is not None and int(spawn[7])==uid:
                    return await q.answer('🎲 Espera a que termine tu lanzamiento.',show_alert=True)
                return await q.answer('🎯 Otro entrenador ya está intentando atraparlo.',show_alert=True)
            if spawn[5]!='active':
                conn.rollback(); return await q.answer('Ese Pokémon ya se fue o ya fue atrapado.',show_alert=True)
            if int(spawn[0])!=int(q.message.chat_id) or spawn[1] != getattr(q.message,'message_thread_id',None):
                conn.rollback(); return await q.answer('Esta aparición ya no corresponde a este lugar.',show_alert=True)
            claimed_by=spawn[7]
            if claimed_by is not None and int(claimed_by)!=uid:
                conn.rollback(); return await q.answer('🎯 Otro entrenador llegó primero. Este Pokémon ya es su intento.',show_alert=True)
            if claimed_by is None:
                c.execute("UPDATE pokemon_wild_spawns_tb SET caught_by=%s WHERE spawn_id=%s",(uid,spawn_id))
            c.execute("INSERT INTO pokemon_wild_attempts_tb(spawn_id,user_id,attempts) VALUES(%s,%s,0) ON CONFLICT DO NOTHING",(spawn_id,uid))
            c.execute("SELECT attempts FROM pokemon_wild_attempts_tb WHERE spawn_id=%s AND user_id=%s FOR UPDATE",(spawn_id,uid)); attempts=int(c.fetchone()[0])
            c.execute("SELECT qty FROM pokemon_items_tb WHERE owner_id=%s AND item_code='master_ball'",(uid,)); _mb=c.fetchone(); has_master=bool(_mb and int(_mb[0])>0)
            if method is None and has_master:
                prepare_only=True; conn.commit()
            else:
                if method is None:
                    method='ball'
                if method=='master':
                    c.execute("UPDATE pokemon_wild_spawns_tb SET status='throwing' WHERE spawn_id=%s",(spawn_id,))
                    conn.commit(); master_mode=True
                elif method=='ball':
                    if attempts>=WILD_MAX_ATTEMPTS:
                        c.execute("UPDATE pokemon_wild_spawns_tb SET status='escaped',finished_at=NOW() WHERE spawn_id=%s",(spawn_id,)); conn.commit()
                        return await q.answer('❌ Ya gastaste tus 2 tiros y el Pokémon se fue.',show_alert=True)
                    attempts+=1
                    c.execute("UPDATE pokemon_wild_attempts_tb SET attempts=%s WHERE spawn_id=%s AND user_id=%s",(attempts,spawn_id,uid))
                    c.execute("UPDATE pokemon_wild_spawns_tb SET status='throwing' WHERE spawn_id=%s",(spawn_id,))
                    conn.commit()
                else:
                    conn.rollback(); return await q.answer('Acción de captura inválida.',show_alert=True)
        except Exception as e:
            conn.rollback(); print('[PK wild attempt]',type(e).__name__,e); return await q.answer('No pude preparar tu Poké Ball.',show_alert=True)
        finally:_put_connection(conn)
        # El encuentro permanece 100% anónimo mientras todavía exista posibilidad de captura.
        # La identidad (y la broma de Ditto) solo se revela al terminar: captura, segundo fallo o expiración.
        species=int(spawn[2]); level=int(spawn[3]); shiny=bool(spawn[4])
        trainer_name=q.from_user.first_name
        if prepare_only:
            buttons=[InlineKeyboardButton('🎲 Lanzar Poké Ball',callback_data=f'pk:wild:{spawn_id}:ball')]
            if has_master:buttons.append(InlineKeyboardButton('🟣 Usar Master Ball',callback_data=f'pk:wild:{spawn_id}:master'))
            encounter_text=(f"🎯 {trainer_name} tomó el encuentro.\n\n"
                            f"❓ El Pokémon sigue siendo desconocido...\n\n"
                            f"🎲 Tienes {WILD_MAX_ATTEMPTS-attempts} intento(s) disponibles.")
            await q.answer('¡Encuentro reservado!')
            try:await q.edit_message_text(encounter_text,reply_markup=InlineKeyboardMarkup([buttons]))
            except Exception:pass
            return
        if master_mode:
            conn=_get_connection(); caught=None; drop=None; held_drop=None; halloween_candies=0
            try:
                c=conn.cursor(); c.execute("SELECT status,species_id,level,shiny,caught_by FROM pokemon_wild_spawns_tb WHERE spawn_id=%s FOR UPDATE",(spawn_id,)); fresh=c.fetchone()
                if not fresh or fresh[0]!='throwing' or fresh[4] is None or int(fresh[4])!=uid:conn.rollback()
                else:
                    c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code='master_ball' AND qty>0 RETURNING qty",(uid,))
                    if not c.fetchone():
                        c.execute("UPDATE pokemon_wild_spawns_tb SET status='active' WHERE spawn_id=%s AND status='throwing' AND caught_by=%s",(spawn_id,uid)); conn.commit()
                    else:
                        species=int(fresh[1]); level=int(fresh[2]); shiny=bool(fresh[3]); trainer_name=_display_name_cursor(c,uid)
                        caught=grant_pokemon_with_cursor(c,uid,species,f'wild:{spawn_id}',level_override=level,shiny_override=shiny)
                        drop=_roll_wild_drop(species,shiny)
                        if drop:grant_item_with_cursor(c,uid,drop[0],drop[1])
                        held_drop=_roll_wild_held_item(species,shiny)
                        if held_drop:grant_item_with_cursor(c,uid,held_drop,1)
                        _ensure_trainer_row_cursor(c,uid); c.execute("UPDATE pokemon_trainer_tb SET wild_catches=wild_catches+1,updated_at=NOW() WHERE user_id=%s",(uid,)); _mission_progress_cursor(c,uid,'capture',1)
                        if random.random()<0.015:grant_item_with_cursor(c,uid,'safari_ticket',1); caught['secret_drop']='safari_ticket'
                        halloween_candies=_halloween_award_species_cursor(c,uid,[species])
                        c.execute("UPDATE pokemon_wild_spawns_tb SET status='caught',finished_at=NOW() WHERE spawn_id=%s",(spawn_id,)); conn.commit()
            except Exception as e:
                conn.rollback(); print('[PK wild master]',type(e).__name__,e)
                try:
                    c=conn.cursor(); c.execute("UPDATE pokemon_wild_spawns_tb SET status='active' WHERE spawn_id=%s AND status='throwing' AND caught_by=%s",(spawn_id,uid)); conn.commit()
                except Exception:conn.rollback()
            finally:_put_connection(conn)
            if not caught:return await q.answer('No pude completar la Master Ball; no se consumió si la captura no quedó confirmada.',show_alert=True)
            rarity=rarity_for(species); shiny_line='✨ SHINY ✨\n' if shiny else ''
            identity=(f"{shiny_line}{rarity_emoji(rarity)} #{species:03d} {NAMES[species]} · Nv.{level}\n{_types_text(species)}\n⭐ Rareza: {rarity.upper()}")
            if species==132:
                fake_species=_wild_ditto_disguise_species(spawn_id); result=(f"🟣 MASTER BALL\n🎉 ¡Pokémon capturado!\n👀 Parecía ser {NAMES[fake_species]}...\n✨ Espera... algo no cuadra...\n💥 ¡ERA DITTO!\n\n🎉 ¡{trainer_name} atrapó a Ditto!\n\n{identity}\n{_sex_text(caught.get('sex'))}\n🧬 IV: {caught.get('iv_percent',0)}% · {caught.get('iv_grade','')}\n🎮 Ejemplar #{caught.get('pokemon_id')}")
            else:result=(f"🟣 MASTER BALL · ¡CAPTURA GARANTIZADA!\n🎉 ¡{trainer_name} atrapó al Pokémon!\n\n{identity}\n{_sex_text(caught.get('sex'))}\n🧬 IV: {caught.get('iv_percent',0)}% · {caught.get('iv_grade','')}\n🎮 Ejemplar #{caught.get('pokemon_id')}")
            if drop:result += f"\n🎁 Soltó: {_drop_label(drop)}"
            if held_drop in HELD_ITEMS:
                x=HELD_ITEMS[held_drop]; result += f"\n🎒 Objeto equipable: {x['emoji']} {x['name']}"
            if caught.get('secret_drop')=='safari_ticket':result += "\n🎟️ ¡Drop secreto! Encontraste un Pase Safari."
            if halloween_candies>0:result += f"\n🎃🍬 +{halloween_candies} Dulces Halloween"
            await q.answer('🟣 ¡Captura garantizada!',show_alert=True)
            try:await q.edit_message_text(f'🏆 CAPTURADO POR {trainer_name}\n\n{identity}',reply_markup=None)
            except Exception:pass
            return await context.bot.send_message(q.message.chat_id,result,message_thread_id=getattr(q.message,'message_thread_id',None))
        attempt_line=(f"🎲 Tiro {attempts}/{WILD_MAX_ATTEMPTS} en curso..." if attempts<WILD_MAX_ATTEMPTS else "🎲 Último tiro en curso...")
        encounter_text=(f"🎯 {trainer_name} tomó el encuentro.\n\n"
                        f"❓ El Pokémon sigue siendo desconocido...\n\n{attempt_line}")
        await q.answer(f'🎯 Tiro {attempts}/{WILD_MAX_ATTEMPTS}...')
        try:
            await q.edit_message_text(encounter_text,reply_markup=q.message.reply_markup)
        except Exception:
            try:
                await context.bot.send_message(q.message.chat_id,encounter_text,message_thread_id=getattr(q.message,'message_thread_id',None))
            except Exception:
                pass
        try:
            dice_msg=await context.bot.send_dice(chat_id=q.message.chat_id,message_thread_id=getattr(q.message,'message_thread_id',None),emoji='🎲')
            value=int(dice_msg.dice.value)
        except Exception as e:
            # Si Telegram falla al lanzar el dado, no gastamos el tiro.
            conn=_get_connection()
            try:
                c=conn.cursor()
                c.execute("UPDATE pokemon_wild_attempts_tb SET attempts=GREATEST(attempts-1,0) WHERE spawn_id=%s AND user_id=%s",(spawn_id,uid))
                c.execute("UPDATE pokemon_wild_spawns_tb SET status='active' WHERE spawn_id=%s AND status='throwing' AND caught_by=%s",(spawn_id,uid))
                conn.commit()
            except Exception:conn.rollback()
            finally:_put_connection(conn)
            print('[PK wild dice]',type(e).__name__,e); return
        await asyncio.sleep(WILD_DICE_ANIMATION_SECONDS)
        effect={1:'PÉSIMO',2:'FLOJO',3:'BIEN',4:'MUY BIEN',5:'EXCELENTE',6:'PERFECTO'}[value]
        threshold=WILD_CATCH_THRESHOLD[rarity_for(species)]
        if value>=threshold:
            conn=_get_connection(); caught=None; trainer_name=q.from_user.first_name; drop=None; held_drop=None; halloween_candies=0
            try:
                c=conn.cursor(); c.execute("SELECT status,species_id,level,shiny,chat_id,thread_id,message_id,caught_by FROM pokemon_wild_spawns_tb WHERE spawn_id=%s FOR UPDATE",(spawn_id,)); fresh=c.fetchone()
                if not fresh or fresh[0]!='throwing' or fresh[7] is None or int(fresh[7])!=uid:
                    conn.rollback(); fresh=None
                else:
                    species=int(fresh[1]); level=int(fresh[2]); shiny=bool(fresh[3]); trainer_name=_display_name_cursor(c,uid)
                    caught=grant_pokemon_with_cursor(c,uid,species,f'wild:{spawn_id}',level_override=level,shiny_override=shiny)
                    drop=_roll_wild_drop(species,shiny)
                    if drop:grant_item_with_cursor(c,uid,drop[0],drop[1])
                    held_drop=_roll_wild_held_item(species,shiny)
                    if held_drop:grant_item_with_cursor(c,uid,held_drop,1)
                    _ensure_trainer_row_cursor(c,uid); c.execute("UPDATE pokemon_trainer_tb SET wild_catches=wild_catches+1,updated_at=NOW() WHERE user_id=%s",(uid,)); _mission_progress_cursor(c,uid,'capture',1)
                    if random.random()<0.015:grant_item_with_cursor(c,uid,'safari_ticket',1); caught['secret_drop']='safari_ticket'
                    halloween_candies=_halloween_award_species_cursor(c,uid,[species])
                    c.execute("UPDATE pokemon_wild_spawns_tb SET status='caught',finished_at=NOW() WHERE spawn_id=%s",(spawn_id,)); conn.commit()
            except Exception as e:
                conn.rollback(); print('[PK wild catch]',type(e).__name__,e); caught=None
            finally:_put_connection(conn)
            if not caught:
                return await context.bot.send_message(q.message.chat_id,'💨 Ese Pokémon ya no está disponible.',message_thread_id=getattr(q.message,'message_thread_id',None))
            rarity=rarity_for(species)
            shiny_line='✨ SHINY ✨\n' if shiny else ''
            identity=(f"{shiny_line}{rarity_emoji(rarity)} #{species:03d} {NAMES[species]} · Nv.{level}\n"
                      f"{_types_text(species)}\n⭐ Rareza: {rarity.upper()}")
            if species==132:
                # Trampa de Ditto únicamente después de confirmar una captura exitosa.
                fake_species=_wild_ditto_disguise_species(spawn_id)
                result=(f"🎲 {value}/6 · {effect}\n🎉 ¡Pokémon capturado!\n"
                        f"👀 Parecía ser {NAMES[fake_species]}...\n"
                        f"✨ Espera... algo no cuadra...\n💥 ¡ERA DITTO!\n\n"
                        f"🎉 ¡{trainer_name} atrapó a Ditto!\n\n{identity}\n"
                        f"{_sex_text(caught.get('sex'))}\n🧬 IV: {caught.get('iv_percent',0)}% · {caught.get('iv_grade','')}\n🎮 Ejemplar #{caught.get('pokemon_id')}")
            else:
                result=(f"🎲 {value}/6 · {effect}\n🎉 ¡{trainer_name} atrapó al Pokémon misterioso!\n\n{identity}\n"
                        f"{_sex_text(caught.get('sex'))}\n🧬 IV: {caught.get('iv_percent',0)}% · {caught.get('iv_grade','')}\n🎮 Ejemplar #{caught.get('pokemon_id')}")
            if drop:result += f"\n🎁 Soltó: {_drop_label(drop)}"
            if held_drop in HELD_ITEMS:
                x=HELD_ITEMS[held_drop]; result += f"\n🎒 Objeto equipable: {x['emoji']} {x['name']}"
            if caught.get('secret_drop')=='safari_ticket':result += "\n🎟️ ¡Drop secreto! Encontraste un Pase Safari."
            if halloween_candies>0:result += f"\n🎃🍬 +{halloween_candies} Dulces Halloween"
            try:
                await context.bot.edit_message_text(chat_id=q.message.chat_id,message_id=q.message.message_id,text=f'🏆 CAPTURADO POR {trainer_name}\n\n{identity}',reply_markup=None)
            except Exception:pass
            return await context.bot.send_message(q.message.chat_id,result,message_thread_id=getattr(q.message,'message_thread_id',None))
        remaining=WILD_MAX_ATTEMPTS-attempts
        trainer_name=q.from_user.first_name
        conn=_get_connection()
        try:
            c=conn.cursor()
            if remaining<=0:
                c.execute("UPDATE pokemon_wild_spawns_tb SET status='escaped',finished_at=NOW() WHERE spawn_id=%s AND status='throwing' AND caught_by=%s",(spawn_id,uid))
                if random.random()<0.25:
                    c.execute("INSERT INTO pokemon_fugitives_tb(chat_id,thread_id,species_id,level,shiny) VALUES(%s,%s,%s,%s,%s)",(q.message.chat_id,int(getattr(q.message,'message_thread_id',None) or 0),species,min(MAX_LEVEL,level+random.randint(1,3)),shiny))
            else:
                c.execute("UPDATE pokemon_wild_spawns_tb SET status='active' WHERE spawn_id=%s AND status='throwing' AND caught_by=%s",(spawn_id,uid))
            conn.commit()
        except Exception as e:
            conn.rollback(); print('[PK wild miss]',type(e).__name__,e)
        finally:_put_connection(conn)
        if remaining>0:
            text=(f"🎲 {value}/6 · {effect}\n💨 El Pokémon desconocido escapó de la Poké Ball.\n"
                  f"🎯 {trainer_name} tiene 1 último tiro. Nadie más puede intentarlo.")
            conn2=_get_connection(); has_master2=False
            try:
                c2=conn2.cursor(); c2.execute("SELECT qty FROM pokemon_items_tb WHERE owner_id=%s AND item_code='master_ball'",(uid,)); mr=c2.fetchone(); has_master2=bool(mr and int(mr[0])>0)
            finally:_put_connection(conn2)
            buttons=[InlineKeyboardButton('🎲 Último tiro',callback_data=f'pk:wild:{spawn_id}:ball')]
            if has_master2:buttons.append(InlineKeyboardButton('🟣 Usar Master Ball',callback_data=f'pk:wild:{spawn_id}:master'))
            try:
                await context.bot.edit_message_text(
                    chat_id=q.message.chat_id,message_id=q.message.message_id,
                    text=(f"🎯 {trainer_name} tomó el encuentro.\n\n"
                          f"❓ El Pokémon sigue siendo desconocido...\n\n"
                          f"🎲 Queda 1 último tiro."),
                    reply_markup=InlineKeyboardMarkup([buttons])
                )
            except Exception:pass
        else:
            text=(f"🎲 {value}/6 · {effect}\n❌ Fallaron los 2 tiros. El Pokémon escapó.\n\n"
                  f"{_wild_reveal_text(species,level,shiny)}")
            try:
                await context.bot.edit_message_text(chat_id=q.message.chat_id,message_id=q.message.message_id,text=f'❌ Fallaron los 2 tiros. El Pokémon escapó.\n\n{_wild_reveal_text(species,level,shiny)}',reply_markup=None)
            except Exception:pass
        return await context.bot.send_message(q.message.chat_id,text,message_thread_id=getattr(q.message,'message_thread_id',None))
    if action=='gcat':
        if len(p)<5:return await q.answer('Este menú de entrega no es tuyo.',show_alert=True)
        sender=int(p[2])
        if uid!=sender:return await q.answer('Este menú de entrega no es tuyo.',show_alert=True)
        target=int(p[3]); cat=p[4]; conn=_get_connection()
        try:c=conn.cursor(); inv=_transfer_available_cursor(c,uid,cat)
        finally:_put_connection(conn)
        if not inv:return await q.answer('Ya no tienes objetos en esa categoría.',show_alert=True)
        rows=[[InlineKeyboardButton(f'{_transfer_item_label(code)} ×{qty}',callback_data=f'pk:gitem:{sender}:{target}:{code}')] for code,qty in inv[:40]]
        await q.answer(); return await q.edit_message_text(f'🎁 {_transfer_category_label(cat)}\nElige objeto:',reply_markup=InlineKeyboardMarkup(rows))
    if action=='gitem':
        if len(p)<5:return await q.answer('Este menú de entrega no es tuyo.',show_alert=True)
        sender=int(p[2])
        if uid!=sender:return await q.answer('Este menú de entrega no es tuyo.',show_alert=True)
        target=int(p[3]); code=p[4]; cat='box' if code=='pokemon_box' else _inventory_category(code); conn=_get_connection(); available=0
        try:
            c=conn.cursor(); inv=dict(_transfer_available_cursor(c,uid,cat)); available=int(inv.get(code,0))
        finally:_put_connection(conn)
        if available<=0:return await q.answer('Ya no tienes ese objeto disponible.',show_alert=True)
        amounts=list(range(1,min(available,5)+1))
        if available>5:amounts.append(available)
        rows=[]
        for i in range(0,len(amounts),3):rows.append([InlineKeyboardButton(str(n),callback_data=f'pk:gqty:{sender}:{target}:{code}:{n}') for n in amounts[i:i+3]])
        await q.answer(); return await q.edit_message_text(f'🎁 {_transfer_item_label(code)}\nDisponible: {available}\nElige cantidad:',reply_markup=InlineKeyboardMarkup(rows))
    if action=='gqty':
        if len(p)<6:return await q.answer('Este menú de entrega no es tuyo.',show_alert=True)
        sender=int(p[2])
        if uid!=sender:return await q.answer('Este menú de entrega no es tuyo.',show_alert=True)
        target=int(p[3]); code=p[4]; qty=int(p[5]); cat='box' if code=='pokemon_box' else _inventory_category(code); conn=_get_connection(); tid=None; available=0; target_name=f'Usuario {target}'
        try:
            c=conn.cursor(); inv=dict(_transfer_available_cursor(c,uid,cat)); available=int(inv.get(code,0))
            if qty<=0 or qty>available:conn.rollback(); return await q.answer('Cantidad inválida o inventario insuficiente.',show_alert=True)
            target_name=_display_name_cursor(c,target)
            c.execute("INSERT INTO pokemon_item_transfers_tb(sender_id,recipient_id,item_code,qty,category,status) VALUES(%s,%s,%s,%s,%s,'pending') RETURNING transfer_id",(uid,target,code,qty,cat)); tid=int(c.fetchone()[0]); conn.commit()
        except Exception as e:conn.rollback(); print('[PK transfer draft]',type(e).__name__,e); return await q.answer('No pude preparar la entrega.',show_alert=True)
        finally:_put_connection(conn)
        kb=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Confirmar entrega',callback_data=f'pk:gconfirm:{tid}'),InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:gcancel:{tid}')]])
        await q.answer(); return await q.edit_message_text(f'Entregar a {target_name}\nObjeto: {_transfer_item_label(code)}\nCantidad: {qty}\nDisponible al preparar: {available}',reply_markup=kb)
    if action=='gcancel':
        tid=int(p[2]); conn=_get_connection(); ok=False
        try:
            c=conn.cursor(); c.execute("SELECT sender_id,status FROM pokemon_item_transfers_tb WHERE transfer_id=%s FOR UPDATE",(tid,)); tr=c.fetchone()
            if not tr:conn.rollback(); return await q.answer('La entrega ya no estaba pendiente.',show_alert=True)
            if int(tr[0])!=uid:conn.rollback(); return await q.answer('Este menú de entrega no es tuyo.',show_alert=True)
            if tr[1]!='pending':conn.rollback(); return await q.answer('La entrega ya no estaba pendiente.',show_alert=True)
            c.execute("UPDATE pokemon_item_transfers_tb SET status='cancelled',finished_at=NOW() WHERE transfer_id=%s AND sender_id=%s AND status='pending' RETURNING transfer_id",(tid,uid)); ok=bool(c.fetchone()); conn.commit()
        except Exception:conn.rollback()
        finally:_put_connection(conn)
        if not ok:return await q.answer('La entrega ya no estaba pendiente.',show_alert=True)
        await q.answer('Entrega cancelada.'); return await q.edit_message_text('❌ Entrega Pokémon cancelada.')
    if action=='gconfirm':
        tid=int(p[2]); conn=_get_connection(); result=None
        try:
            c=conn.cursor(); c.execute("SELECT sender_id,recipient_id,item_code,qty,category,status FROM pokemon_item_transfers_tb WHERE transfer_id=%s FOR UPDATE",(tid,)); tr=c.fetchone()
            if not tr:conn.rollback(); return await q.answer('Entrega no disponible.',show_alert=True)
            if int(tr[0])!=uid:conn.rollback(); return await q.answer('Este menú de entrega no es tuyo.',show_alert=True)
            if tr[5]!='pending':conn.rollback(); return await q.answer('Esta entrega ya fue procesada.',show_alert=True)
            sender,target,code,qty,cat=int(tr[0]),int(tr[1]),str(tr[2]),int(tr[3]),str(tr[4])
            if sender==target or qty<=0:conn.rollback(); return await q.answer('Entrega inválida.',show_alert=True)
            if cat=='box' and code=='pokemon_box':
                c.execute("SELECT box_id,placement FROM pokemon_season_boxes_tb WHERE owner_id=%s AND opened=FALSE ORDER BY box_id FOR UPDATE",(sender,)); boxes=c.fetchall()[:qty]
                if len(boxes)<qty:conn.rollback(); return await q.answer('Ya no tienes suficientes cajas.',show_alert=True)
                for box_id,placement in boxes:
                    c.execute("UPDATE pokemon_season_boxes_tb SET opened=TRUE,opened_at=NOW() WHERE box_id=%s AND owner_id=%s AND opened=FALSE",(box_id,sender))
                    key=f'transfer:{tid}:{int(box_id)}'
                    c.execute("""INSERT INTO pokemon_season_boxes_tb(owner_id,season_key,placement,opened) VALUES(%s,%s,%s,FALSE)""",(target,key,int(placement)))
            else:
                c.execute("UPDATE pokemon_items_tb SET qty=qty-%s WHERE owner_id=%s AND item_code=%s AND qty>=%s RETURNING qty",(qty,sender,code,qty))
                if not c.fetchone():conn.rollback(); return await q.answer('Ya no tienes suficiente cantidad de ese objeto.',show_alert=True)
                c.execute("""INSERT INTO pokemon_items_tb(owner_id,item_code,qty) VALUES(%s,%s,%s)
                             ON CONFLICT(owner_id,item_code) DO UPDATE SET qty=pokemon_items_tb.qty+EXCLUDED.qty""",(target,code,qty))
            c.execute("UPDATE pokemon_item_transfers_tb SET status='completed',finished_at=NOW() WHERE transfer_id=%s AND status='pending'",(tid,))
            c.execute("UPDATE pokemon_item_transfers_tb SET status='cancelled',finished_at=NOW() WHERE sender_id=%s AND recipient_id=%s AND item_code=%s AND status='pending' AND transfer_id<>%s",(sender,target,code,tid))
            sender_name=_display_name_cursor(c,sender); target_name=_display_name_cursor(c,target); conn.commit(); result=(sender_name,target_name,code,qty)
        except Exception as e:conn.rollback(); print('[PK transfer confirm]',type(e).__name__,e); return await q.answer('No pude completar la entrega.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Entrega completada ✅',show_alert=True)
        return await q.edit_message_text(f'{result[0]} entregó {_transfer_item_label(result[2])} ×{result[3]} a {result[1]}.')

    if action=='releasepage':
        page=int(p[2]); await q.answer(); return await q.edit_message_text('🌿 Elige el Pokémon que quieres liberar:',reply_markup=_release_markup(uid,page))
    if action=='releasepick':
        pid=int(p[2]); page=int(p[3]) if len(p)>3 else 0; row=_get_instance(uid,pid)
        if not row:return await q.answer('Ese Pokémon ya no está en tu colección.',show_alert=True)
        conn=_get_connection(); blocked=False
        try:
            c=conn.cursor(); _ensure_team_row_cursor(c,uid); c.execute("SELECT slot1,slot2,slot3,slot4,principal_pokemon_id FROM pokemon_team_tb WHERE owner_id=%s",(uid,)); team=c.fetchone() or (None,None,None,None,None); blocked=pid in [int(x) for x in team if x is not None]
        finally:_put_connection(conn)
        if blocked:return await q.answer('Primero quítalo del equipo o cambia tu Pokémon principal.',show_alert=True)
        ivpct=_iv_percent(_iv_values(row)); amount=_release_candies(int(row[1]))
        kb=InlineKeyboardMarkup([[InlineKeyboardButton(f'✅ Liberar · +{amount} 🍬',callback_data=f'pk:releaseconfirm:{pid}'),InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:detail:{pid}:{page}')]])
        await q.answer(); return await q.message.reply_text(f"🌿 ¿Liberar a {_pokemon_label(row)}?\n🧬 IV {ivpct}% · {_iv_grade(ivpct)}\n🍬 Recibirás {amount} Caramelo{'s' if amount!=1 else ''} Raro{'s' if amount!=1 else ''}.\n\nEsto es permanente.",reply_markup=kb)
    if action=='releaseconfirm':
        pid=int(p[2]); conn=_get_connection(); result=None
        try:
            c=conn.cursor(); c.execute("""SELECT pokemon_id,species_id,nickname,level,xp,moves_json,media_type,media_file_id,wins,losses,shiny,iv_atk,iv_def,iv_spd,iv_spc,iv_hp,held_item_code,sex FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s FOR UPDATE""",(uid,pid)); row=c.fetchone()
            if not row:conn.rollback(); return await q.answer('Ese Pokémon ya no está en tu colección.',show_alert=True)
            if _battle_busy_cursor(c,uid) or _trade_busy_cursor(c,uid):conn.rollback(); return await q.answer('Termina tu batalla/intercambio antes de liberar Pokémon.',show_alert=True)
            _ensure_team_row_cursor(c,uid); c.execute("SELECT slot1,slot2,slot3,slot4,principal_pokemon_id FROM pokemon_team_tb WHERE owner_id=%s FOR UPDATE",(uid,)); team=c.fetchone() or (None,None,None,None,None)
            if pid in [int(x) for x in team if x is not None]:conn.rollback(); return await q.answer('Primero quítalo del equipo o cambia tu principal.',show_alert=True)
            amount=_release_candies(int(row[1])); shown=row[2] or NAMES[int(row[1])]; held=row[16] if len(row)>16 else None
            if held in HELD_ITEMS:grant_item_with_cursor(c,uid,held,1)
            c.execute("DELETE FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid))
            grant_item_with_cursor(c,uid,'rare_candy',amount)
            _ensure_trainer_row_cursor(c,uid); c.execute("UPDATE pokemon_trainer_tb SET released=released+1,candies_earned=candies_earned+%s,updated_at=NOW() WHERE user_id=%s",(amount,uid)); conn.commit(); result=(shown,amount)
        except Exception as e:
            conn.rollback(); print('[PK release]',type(e).__name__,e)
        finally:_put_connection(conn)
        if not result:return await q.answer('No pude liberarlo.',show_alert=True)
        await q.answer('Pokémon liberado.',show_alert=True)
        try:return await q.edit_message_text(f"🌿 Liberaste a {result[0]}.\n🍬 +{result[1]} Caramelo{'s' if result[1]!=1 else ''} Raro{'s' if result[1]!=1 else ''}.")
        except Exception:return
    if action=='candyup':
        pid=int(p[2]); conn=_get_connection(); notes=[]
        try:
            c=conn.cursor(); c.execute("SELECT species_id,level,xp,nickname FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s FOR UPDATE",(uid,pid)); r=c.fetchone()
            if not r:conn.rollback(); return await q.answer('Pokémon no encontrado.',show_alert=True)
            species,level,xp,nick=int(r[0]),int(r[1]),int(r[2]),r[3]
            if level>=MAX_LEVEL:conn.rollback(); return await q.answer('Ya está en nivel 100.',show_alert=True)
            if not _spend_rare_candies_cursor(c,uid,CANDIES_PER_LEVEL):
                conn.rollback(); return await q.answer('Necesitas 1 Caramelo Raro.',show_alert=True)
            needed=max(1,_xp_floor(level+1)-xp); notes=_grant_pokemon_xp_cursor(c,pid,needed); conn.commit()
        except Exception as e:
            conn.rollback(); print('[PK candy level]',type(e).__name__,e)
        finally:_put_connection(conn)
        return await q.answer('🍬 '+(' · '.join(notes) if notes else 'Subió un nivel.'),show_alert=True)
    if action=='list':
        page=int(p[2]); await q.answer()
        text=f'🎮 TUS POKÉMON\n\nColección privada. Toca uno para administrarlo.'
        if q.message.photo or q.message.animation or q.message.video:
            try:
                await context.bot.send_message(chat_id=q.message.chat.id,text=text,reply_markup=_collection_markup(uid,page))
                await q.message.delete()
                return
            except Exception:
                pass
        return await q.edit_message_text(text,reply_markup=_collection_markup(uid,page))
    if action in ('detail','nickselect','mediaselect','brag'):
        pid=int(p[2]); page=int(p[3]) if len(p)>3 else 0; row=_get_instance(uid,pid)
        if not row:return await q.answer('Ese Pokémon ya no está en tu colección.',show_alert=True)
        if action=='brag':
            target=context.user_data.get('pk_brag_target') or {'chat_id':uid,'thread_id':None}; ok=await _send_brag(context,uid,pid,target); await q.answer('Presumido 😎' if ok else 'No pude publicarlo.',show_alert=True); return
        if action=='nickselect':context.user_data['pk_wait_nick']=pid; await q.answer(); return await q.message.reply_text(f"🏷️ Escribe el nuevo apodo para #{int(row[1]):03d} {NAMES[int(row[1])]} (máx. 24 caracteres). Escribe - para quitarlo.")
        if action=='mediaselect':context.user_data['pk_wait_media']=pid; await q.answer(); return await q.message.reply_text(f"🎞️ Envíame una FOTO, GIF o VIDEO para #{int(row[1]):03d} {row[2] or NAMES[int(row[1])]}. Telegram guardará el archivo; PiBot solo conservará su file_id.")
        species=int(row[1]); level=int(row[3]); moves=json.loads(row[5] or '[]'); move_names=', '.join(MOVES[m][0] for m in moves if m in MOVES)
        shiny_line = "✨ Variante SHINY\n" if len(row)>10 and row[10] else ""
        if level < MAX_LEVEL:
            xp_now=max(int(row[4]),_xp_floor(level)); xp_base=_xp_floor(level); xp_need=_xp_step(level)
            xp_line=f"⭐ XP: {max(0,xp_now-xp_base):,} / {xp_need:,} para Nv.{level+1}\n"
        else:
            xp_line="⭐ XP: NIVEL MÁXIMO\n"
        ivs=_iv_values(row); ivpct=_iv_percent(ivs)
        stats={
            'hp':_stat_value(species,level,'hp',ivs['hp']),
            'atk':_stat_value(species,level,'atk',ivs['atk']),
            'def':_stat_value(species,level,'def',ivs['def']),
            'spc':_stat_value(species,level,'spc',ivs['spc']),
            'spd':_stat_value(species,level,'spd',ivs['spd']),
        }
        principal=_is_principal(uid,pid)
        rare_candies=_candy_total(uid)
        held_code=row[16] if len(row)>16 else None
        held_line=f"🎒 Equipado: {_held_item_text(held_code)}\n"
        principal_line='⭐ Pokémon PRINCIPAL\n' if principal else ''
        txt=(f"{rarity_emoji(rarity_for(species))} {_pokemon_label(row)}\n"
             f"📖 Pokédex: #{species:03d} · 🎮 Ejemplar: #{int(row[0])}\n"
             f"{principal_line}"
             f"{shiny_line}"
             f"{_types_text(species)}\n"
             f"{xp_line}"
             f"🧬 IV: {ivpct}% · {_iv_grade(ivpct)}\n"
             f"📊 PS {stats['hp']} · ATQ {stats['atk']} · DEF {stats['def']} · ESP {stats['spc']} · VEL {stats['spd']}\n"
             f"🔬 DVs: PS {ivs['hp']}/15 · ATQ {ivs['atk']}/15 · DEF {ivs['def']}/15 · ESP {ivs['spc']}/15 · VEL {ivs['spd']}/15\n"
             f"🍬 Caramelos Raros: {rare_candies}\n"
             f"{held_line}"
             f"⚔️ {row[8]}V / {row[9]}D\n"
             f"🎯 Movimientos: {move_names or '—'}\n"
             f"🎞️ Multimedia: {'GIF' if row[6]=='animation' else 'Video' if row[6]=='video' else 'Foto' if row[6]=='photo' else 'Sin asignar'}")
        principal_btn=InlineKeyboardButton('⭐ Principal ✓' if principal else '⭐ Hacer principal',callback_data='pk:noop' if principal else f'pk:setprincipal:{pid}')
        extra_row=[]
        if level<MAX_LEVEL:
            extra_row.append(InlineKeyboardButton(f'🍬 Subir nivel · {rare_candies}',callback_data=f'pk:candyup:{pid}'))
        extra_row.append(InlineKeyboardButton('🌿 Liberar',callback_data=f'pk:releasepick:{pid}:{page}'))
        held_buttons=[InlineKeyboardButton('🎒 Equipar objeto',callback_data=f'pk:holdequipmenu:{pid}:0')]
        if held_code:held_buttons.append(InlineKeyboardButton('🗑 Quitar objeto',callback_data=f'pk:holdremove:{pid}'))
        kb_rows=[[InlineKeyboardButton('🏷️ Apodo',callback_data=f'pk:nickselect:{pid}:{page}'),InlineKeyboardButton('🎞️ Foto/GIF/Video',callback_data=f'pk:mediaselect:{pid}:{page}')],[InlineKeyboardButton('👥 Meter al equipo',callback_data=f'pk:addteam:{pid}'),principal_btn],held_buttons,[InlineKeyboardButton('😎 Presumir aquí',callback_data=f'pk:braghere:{pid}'),InlineKeyboardButton('🗑 Quitar multimedia',callback_data=f'pk:removemedia:{pid}')],extra_row,[InlineKeyboardButton('⬅️ Volver',callback_data=f'pk:list:{page}')]]
        kb=InlineKeyboardMarkup(kb_rows)
        await q.answer()
        # Si ya tiene multimedia, al seleccionarlo se muestra inmediatamente con su ficha.
        if row[7] and row[6] in ('photo','animation','video'):
            try:
                if row[6]=='photo': await context.bot.send_photo(chat_id=q.message.chat.id,photo=row[7],caption=txt,reply_markup=kb)
                elif row[6]=='animation': await context.bot.send_animation(chat_id=q.message.chat.id,animation=row[7],caption=txt,reply_markup=kb)
                else: await context.bot.send_video(chat_id=q.message.chat.id,video=row[7],caption=txt,reply_markup=kb)
                try: await q.message.delete()
                except Exception: pass
                return
            except Exception:
                pass
        return await q.edit_message_text(txt,reply_markup=kb)
    if action=='holdequipmenu':
        pid=int(p[2]); page=int(p[3]) if len(p)>3 else 0; row=_get_instance(uid,pid)
        if not row:return await q.answer('Ese Pokémon ya no está en tu colección.',show_alert=True)
        conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT item_code,qty FROM pokemon_items_tb WHERE owner_id=%s AND qty>0 ORDER BY item_code",(uid,)); inv=[(str(a),int(b)) for a,b in c.fetchall() if str(a) in HELD_ITEMS]
        finally:_put_connection(conn)
        if not inv:return await q.answer('No tienes objetos equipables libres en tu inventario.',show_alert=True)
        pages=max(1,math.ceil(len(inv)/PAGE_SIZE)); page=max(0,min(page,pages-1)); chunk=inv[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
        rows=[]
        for code,qty in chunk:
            x=HELD_ITEMS[code]; rows.append([InlineKeyboardButton(f"{x['emoji']} {x['name']} ×{qty}",callback_data=f'pk:holdequip:{pid}:{code}')])
        nav=[]
        if page>0:nav.append(InlineKeyboardButton('⬅️',callback_data=f'pk:holdequipmenu:{pid}:{page-1}'))
        if page<pages-1:nav.append(InlineKeyboardButton('➡️',callback_data=f'pk:holdequipmenu:{pid}:{page+1}'))
        if nav:rows.append(nav)
        rows.append([InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:detail:{pid}:0')])
        await q.answer(); return await q.message.reply_text('🎒 Elige el objeto equipable:',reply_markup=InlineKeyboardMarkup(rows))
    if action=='holdequip':
        pid=int(p[2]); code=p[3]
        if code not in HELD_ITEMS:return await q.answer('Objeto equipable inválido.',show_alert=True)
        conn=_get_connection(); note=None
        try:
            c=conn.cursor()
            if _battle_busy_cursor(c,uid) or _trade_busy_cursor(c,uid):conn.rollback(); return await q.answer('Termina tu batalla/intercambio antes de cambiar objetos equipados.',show_alert=True)
            c.execute("SELECT held_item_code,species_id,nickname FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s FOR UPDATE",(uid,pid)); mon=c.fetchone()
            if not mon:conn.rollback(); return await q.answer('Ese Pokémon ya no está en tu colección.',show_alert=True)
            old=mon[0]
            if old==code:conn.rollback(); return await q.answer('Ese objeto ya está equipado.',show_alert=True)
            c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code=%s AND qty>0 RETURNING qty",(uid,code))
            if not c.fetchone():conn.rollback(); return await q.answer('Ya no tienes ese objeto libre.',show_alert=True)
            if old in HELD_ITEMS:grant_item_with_cursor(c,uid,old,1)
            c.execute("UPDATE pokemon_instances_tb SET held_item_code=%s,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s",(code,uid,pid)); conn.commit()
            note=f"🎒 {mon[2] or NAMES[int(mon[1])]} equipó {_item_name(code)}."
        except Exception as e:conn.rollback(); print('[PK held equip]',type(e).__name__,e)
        finally:_put_connection(conn)
        return await q.answer(note or 'No pude equiparlo.',show_alert=True)
    if action=='holdremove':
        pid=int(p[2]); conn=_get_connection(); note=None
        try:
            c=conn.cursor()
            if _battle_busy_cursor(c,uid) or _trade_busy_cursor(c,uid):conn.rollback(); return await q.answer('Termina tu batalla/intercambio antes de cambiar objetos equipados.',show_alert=True)
            c.execute("SELECT held_item_code,species_id,nickname FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s FOR UPDATE",(uid,pid)); mon=c.fetchone()
            if not mon:conn.rollback(); return await q.answer('Ese Pokémon ya no está en tu colección.',show_alert=True)
            old=mon[0]
            if old not in HELD_ITEMS:conn.rollback(); return await q.answer('Ese Pokémon no tiene objeto equipado.',show_alert=True)
            c.execute("UPDATE pokemon_instances_tb SET held_item_code=NULL,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); grant_item_with_cursor(c,uid,old,1); conn.commit()
            note=f"🎒 {_item_name(old)} volvió a tu inventario."
        except Exception as e:conn.rollback(); print('[PK held remove]',type(e).__name__,e)
        finally:_put_connection(conn)
        return await q.answer(note or 'No pude quitarlo.',show_alert=True)

    if action=='setprincipal':
        pid=int(p[2]); conn=_get_connection(); name=None
        try:
            c=conn.cursor(); _ensure_team_row_cursor(c,uid)
            c.execute("SELECT species_id,nickname FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); r=c.fetchone()
            if not r:conn.rollback(); return await q.answer('Ese Pokémon ya no está en tu colección.',show_alert=True)
            c.execute("UPDATE pokemon_team_tb SET principal_pokemon_id=%s,updated_at=NOW() WHERE owner_id=%s",(pid,uid)); conn.commit()
            name=r[1] or NAMES[int(r[0])]
        except Exception as e:
            conn.rollback(); print('[PK principal]',type(e).__name__,e); return await q.answer('No pude cambiar tu Pokémon principal.',show_alert=True)
        finally:_put_connection(conn)
        return await q.answer(f'⭐ {name} ahora es tu Pokémon principal.',show_alert=True)
    if action=='removemedia':
        pid=int(p[2]); conn=_get_connection()
        try:c=conn.cursor(); c.execute("UPDATE pokemon_instances_tb SET media_type=NULL,media_file_id=NULL,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); conn.commit()
        except Exception:conn.rollback()
        finally:_put_connection(conn)
        return await q.answer('Multimedia quitada.',show_alert=True)
    if action=='braghere':
        pid=int(p[2]); ok=await _send_brag(context,uid,pid,{'chat_id':q.message.chat_id,'thread_id':q.message.message_thread_id}); return await q.answer('Listo 😎' if ok else 'No pude enviarlo.',show_alert=True)
    if action=='team':
        await q.answer(); return await q.edit_message_text(_team_text(uid),reply_markup=_team_markup(uid))
    if action=='teamslot':
        slot=int(p[2]); page=int(p[3]); mons=_get_owned(uid); pages=max(1,math.ceil(len(mons)/PAGE_SIZE)); page=max(0,min(page,pages-1)); chunk=mons[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
        rows=[[InlineKeyboardButton(_pokemon_label(r)[:50],callback_data=f'pk:setslot:{slot}:{r[0]}')] for r in chunk]
        nav=[]
        if page>0:nav.append(InlineKeyboardButton('⬅️',callback_data=f'pk:teamslot:{slot}:{page-1}'))
        if page<pages-1:nav.append(InlineKeyboardButton('➡️',callback_data=f'pk:teamslot:{slot}:{page+1}'))
        if nav:rows.append(nav)
        rows.append([InlineKeyboardButton('🗑 Vaciar espacio',callback_data=f'pk:setslot:{slot}:0'),InlineKeyboardButton('⬅️ Equipo',callback_data='pk:team')])
        await q.answer(); return await q.edit_message_text(f'👥 Elige Pokémon para el espacio {slot}:',reply_markup=InlineKeyboardMarkup(rows))
    if action=='setslot':
        slot=int(p[2]); pid=int(p[3]); conn=_get_connection()
        try:
            c=conn.cursor(); _ensure_team_row_cursor(c,uid)
            if pid:
                c.execute("SELECT 1 FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid))
                if not c.fetchone():conn.rollback(); return await q.answer('Ese Pokémon no es tuyo.',show_alert=True)
                c.execute("SELECT slot1,slot2,slot3,slot4 FROM pokemon_team_tb WHERE owner_id=%s FOR UPDATE",(uid,)); current=list(c.fetchone())
                # Si ya estaba en otro hueco, lo quitamos para no duplicarlo.
                for i,x in enumerate(current,1):
                    if x==pid:c.execute(f"UPDATE pokemon_team_tb SET slot{i}=NULL WHERE owner_id=%s",(uid,))
            c.execute(f"UPDATE pokemon_team_tb SET slot{slot}=%s,updated_at=NOW() WHERE owner_id=%s",(pid or None,uid)); conn.commit()
        except Exception:conn.rollback(); return await q.answer('No pude cambiar el equipo.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Equipo actualizado.',show_alert=True); return await q.edit_message_text(_team_text(uid),reply_markup=_team_markup(uid))
    if action=='addteam':
        pid=int(p[2]); rows=[[InlineKeyboardButton(f'Espacio {i}',callback_data=f'pk:setslot:{i}:{pid}') for i in range(1,5)],[InlineKeyboardButton('⬅️ Volver',callback_data='pk:list:0')]]
        await q.answer(); return await q.message.reply_text('¿En qué espacio lo quieres?',reply_markup=InlineKeyboardMarkup(rows))
    if action=='items':
        await q.answer(); return await q.edit_message_text(_items_text(uid),reply_markup=_items_markup(uid))
    if action=='useitem':
        code=p[2]; page=int(p[3]); mons=_get_owned(uid); eligible=[]
        for r in mons:
            sid=int(r[1]); level=int(r[3])
            tm_move=TM_ITEMS.get(code,(None,None,None))[2] if code in TM_ITEMS else None
            ok=(_stone_evolution_target(sid,code) is not None) or (code=='link_cable' and sid in TRADE_EVOLUTIONS) or (code=='rare_candy' and level<MAX_LEVEL) or (tm_move is not None and can_learn_tm(sid,tm_move))
            if ok:eligible.append(r)
        if not eligible:return await q.answer('No tienes ningún Pokémon compatible con ese objeto/MT.',show_alert=True)
        pages=max(1,math.ceil(len(eligible)/PAGE_SIZE)); page=max(0,min(page,pages-1)); chunk=eligible[page*PAGE_SIZE:(page+1)*PAGE_SIZE]
        rows=[[InlineKeyboardButton(_pokemon_label(r)[:50],callback_data=f'pk:evolveitem:{code}:{r[0]}')] for r in chunk]
        nav=[]
        if page>0:nav.append(InlineKeyboardButton('⬅️',callback_data=f'pk:useitem:{code}:{page-1}'))
        if page<pages-1:nav.append(InlineKeyboardButton('➡️',callback_data=f'pk:useitem:{code}:{page+1}'))
        if nav:rows.append(nav)
        rows.append([InlineKeyboardButton('⬅️ Objetos',callback_data='pk:items')])
        await q.answer(); return await q.edit_message_text(f'Elige quién usará {ITEMS[code][1]} {ITEMS[code][0]}:',reply_markup=InlineKeyboardMarkup(rows))
    if action=='evolveitem':
        code=p[2]; pid=int(p[3]); conn=_get_connection(); note=None
        try:
            c=conn.cursor(); c.execute("SELECT species_id,nickname,level,moves_json FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s FOR UPDATE",(uid,pid)); r=c.fetchone()
            if not r:conn.rollback(); return await q.answer('Pokémon no encontrado.',show_alert=True)
            sid=int(r[0]); current_level=int(r[2])
            if code in TM_ITEMS:
                move_code=TM_ITEMS[code][2]
                if not can_learn_tm(sid,move_code):
                    conn.rollback(); return await q.answer('Ese Pokémon no es compatible con esa MT.',show_alert=True)
                c.execute("SELECT moves_json FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); mr=c.fetchone()
                try: current_moves=json.loads((mr[0] if mr else '[]') or '[]')
                except Exception: current_moves=[]
                if move_code in current_moves:
                    conn.rollback(); return await q.answer('Ese Pokémon ya conoce ese movimiento.',show_alert=True)
                if len(current_moves)>=4:
                    conn.rollback()
                    rows=[]
                    for idx,mcode in enumerate(current_moves[:4]):
                        mname=MOVES.get(mcode,(mcode,))[0]
                        rows.append([InlineKeyboardButton(f'↪️ Olvidar {mname}',callback_data=f'pk:teachreplace:{code}:{pid}:{idx}')])
                    rows.append([InlineKeyboardButton('❌ Cancelar',callback_data='pk:items')])
                    await q.answer()
                    return await q.message.reply_text(f"📀 {ITEMS[code][0]} enseñará {MOVES[move_code][0]}.\n\n{r[1] or NAMES[sid]} ya conoce 4 movimientos. ¿Cuál quieres olvidar?",reply_markup=InlineKeyboardMarkup(rows))
                c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code=%s AND qty>0 RETURNING qty",(uid,code))
                if not c.fetchone():conn.rollback(); return await q.answer('Ya no tienes esa MT.',show_alert=True)
                current_moves.append(move_code)
                c.execute("UPDATE pokemon_instances_tb SET moves_json=%s,updated_at=NOW() WHERE pokemon_id=%s",(json.dumps(current_moves,ensure_ascii=False),pid))
                conn.commit(); note=f"📀 {r[1] or NAMES[sid]} aprendió {MOVES[move_code][0]}."
            elif code=='rare_candy':
                if current_level>=MAX_LEVEL:conn.rollback(); return await q.answer('Ese Pokémon ya está en nivel 100.',show_alert=True)
                c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code=%s AND qty>0 RETURNING qty",(uid,code))
                if not c.fetchone():conn.rollback(); return await q.answer('Ya no tienes ese objeto.',show_alert=True)
                c.execute("SELECT xp FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid)); xr=c.fetchone(); current_xp=int(xr[0] if xr else _xp_floor(current_level))
                needed=max(0,_xp_floor(current_level+1)-max(current_xp,_xp_floor(current_level)))
                learn_notes=_grant_pokemon_xp_cursor(c,pid,max(1,needed))
                conn.commit(); note='🍬 '+(learn_notes[0] if learn_notes else f'{r[1] or NAMES[sid]} subió de nivel.')
                if len(learn_notes)>1:note+='\n'+'\n'.join(learn_notes[1:])
            else:
                target=_stone_evolution_target(sid,code) if code!='link_cable' else TRADE_EVOLUTIONS.get(sid)
                if not target:conn.rollback(); return await q.answer('Ese objeto no sirve para este Pokémon.',show_alert=True)
                c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code=%s AND qty>0 RETURNING qty",(uid,code))
                if not c.fetchone():conn.rollback(); return await q.answer('Ya no tienes ese objeto.',show_alert=True)
                # Evolucionar no debe borrar movimientos elegidos ni MT aprendidas.
                try: current_moves=[str(x) for x in json.loads(r[3] or '[]') if str(x) in MOVES]
                except Exception: current_moves=[]
                evo_notes=[]
                if len(current_moves)<4:
                    for req,move_code in _species_level_learnset(int(target)):
                        if int(req)>current_level:break
                        if move_code in current_moves:continue
                        _queue_level_move_cursor(c,uid,pid,int(target),r[1],current_moves,move_code,evo_notes)
                        if len(current_moves)>=4:break
                c.execute("UPDATE pokemon_instances_tb SET species_id=%s,moves_json=%s,updated_at=NOW() WHERE pokemon_id=%s",(target,json.dumps(current_moves[:4],ensure_ascii=False),pid))
                c.execute("INSERT INTO pokemon_pokedex_tb(owner_id,species_id,obtained_count) VALUES(%s,%s,1) ON CONFLICT(owner_id,species_id) DO UPDATE SET last_obtained_at=NOW()",(uid,target))
                conn.commit(); note=f'✨ {r[1] or NAMES[sid]} evolucionó a {NAMES[target]}.'
                if evo_notes:note+='\n'+'\n'.join(evo_notes)
        except Exception as e:conn.rollback(); print('[PK evolve]',e)
        finally:_put_connection(conn)
        return await q.answer(note or 'No pude evolucionarlo.',show_alert=True)

    if action=='teachreplace':
        code=p[2]; pid=int(p[3]); idx=int(p[4]);
        if code not in TM_ITEMS:return await q.answer('MT inválida.',show_alert=True)
        conn=_get_connection(); note=None
        try:
            c=conn.cursor(); c.execute("SELECT species_id,nickname,moves_json FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s FOR UPDATE",(uid,pid)); r=c.fetchone()
            if not r:conn.rollback(); return await q.answer('Pokémon no encontrado.',show_alert=True)
            sid=int(r[0]); move_code=TM_ITEMS[code][2]
            if not can_learn_tm(sid,move_code):conn.rollback(); return await q.answer('Ese Pokémon no es compatible con esa MT.',show_alert=True)
            try:moves=json.loads(r[2] or '[]')
            except Exception:moves=[]
            if move_code in moves:conn.rollback(); return await q.answer('Ese Pokémon ya conoce ese movimiento.',show_alert=True)
            if not (0<=idx<len(moves)):conn.rollback(); return await q.answer('Movimiento inválido.',show_alert=True)
            old=moves[idx]; c.execute("UPDATE pokemon_items_tb SET qty=qty-1 WHERE owner_id=%s AND item_code=%s AND qty>0 RETURNING qty",(uid,code))
            if not c.fetchone():conn.rollback(); return await q.answer('Ya no tienes esa MT.',show_alert=True)
            moves[idx]=move_code
            c.execute("UPDATE pokemon_instances_tb SET moves_json=%s,updated_at=NOW() WHERE pokemon_id=%s",(json.dumps(moves,ensure_ascii=False),pid)); conn.commit()
            note=f"📀 {r[1] or NAMES[sid]} olvidó {MOVES.get(old,(old,))[0]} y aprendió {MOVES[move_code][0]}."
        except Exception as e:
            conn.rollback(); print('[PK TM]',type(e).__name__,e)
        finally:_put_connection(conn)
        return await q.answer(note or 'No pude usar esa MT.',show_alert=True)

    # ---- callbacks de intercambio ----
    if action=='tradepick':
        tid=int(p[2]); page=int(p[3]); conn=_get_connection(); allowed=False
        try:
            c=conn.cursor(); c.execute("SELECT user_a,user_b,status FROM pokemon_trades_tb WHERE trade_id=%s",(tid,)); tr=c.fetchone()
            allowed=bool(tr and tr[2] in ('selecting','confirming') and uid in (int(tr[0]),int(tr[1])))
        finally:_put_connection(conn)
        if not allowed:return await q.answer('Ese intercambio no es tuyo o ya terminó.',show_alert=True)
        try:
            await context.bot.send_message(uid,'🔄 Elige el Pokémon que vas a ofrecer. Tu colección sigue siendo privada:',reply_markup=_trade_pick_markup(uid,tid,page))
            return await q.answer('Te mandé tu colección por privado.')
        except Exception:return await q.answer('Abre primero el privado de PiBot con /start.',show_alert=True)
    if action=='tradeoffer':
        tid=int(p[2]); pid=int(p[3]); conn=_get_connection(); summary=None; ready=False; chat_id=None; thread_id=None; msgid=None
        try:
            c=conn.cursor(); c.execute("SELECT user_a,user_b,status,chat_id,thread_id,message_id FROM pokemon_trades_tb WHERE trade_id=%s FOR UPDATE",(tid,)); tr=c.fetchone()
            if not tr or tr[2] not in ('selecting','confirming') or uid not in (int(tr[0]),int(tr[1])):conn.rollback(); return await q.answer('Intercambio no disponible.',show_alert=True)
            c.execute("SELECT 1 FROM pokemon_instances_tb WHERE owner_id=%s AND pokemon_id=%s",(uid,pid))
            if not c.fetchone():conn.rollback(); return await q.answer('Ese Pokémon ya no es tuyo.',show_alert=True)
            col='pokemon_a' if uid==int(tr[0]) else 'pokemon_b'
            c.execute(f"UPDATE pokemon_trades_tb SET {col}=%s,confirm_a=FALSE,confirm_b=FALSE,status='selecting',updated_at=NOW() WHERE trade_id=%s",(pid,tid))
            c.execute("SELECT pokemon_a,pokemon_b FROM pokemon_trades_tb WHERE trade_id=%s",(tid,)); pa,pb=c.fetchone(); ready=bool(pa and pb)
            if ready:c.execute("UPDATE pokemon_trades_tb SET status='confirming',updated_at=NOW() WHERE trade_id=%s",(tid,))
            atext=_trade_mon_text_cursor(c,int(tr[0]),pa); btext=_trade_mon_text_cursor(c,int(tr[1]),pb)
            summary=f'🔄 INTERCAMBIO POKÉMON\n\nJugador A ofrece:\n{atext}\n\nJugador B ofrece:\n{btext}'
            chat_id=int(tr[3]); thread_id=tr[4]; msgid=tr[5]; conn.commit()
        except Exception as e:conn.rollback(); print('[PK trade offer]',type(e).__name__,e); return await q.answer('No pude guardar tu oferta.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Oferta guardada ✅',show_alert=True)
        if ready:
            kb=InlineKeyboardMarkup([[InlineKeyboardButton('✅ Confirmar intercambio',callback_data=f'pk:tradeconfirm:{tid}')],[InlineKeyboardButton('🔄 Cambiar mi Pokémon',callback_data=f'pk:tradepick:{tid}:0'),InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:tradecancel:{tid}')]])
            text=summary+'\n\nAmbos deben confirmar. El intercambio conserva nivel, XP, apodo, foto/GIF/video y condición Shiny.'
        else:
            kb=InlineKeyboardMarkup([[InlineKeyboardButton('🔄 Elegir mi Pokémon',callback_data=f'pk:tradepick:{tid}:0')],[InlineKeyboardButton('❌ Cancelar',callback_data=f'pk:tradecancel:{tid}')]])
            text=summary+'\n\nFalta que la otra persona elija.'
        try:await context.bot.edit_message_text(chat_id=chat_id,message_id=msgid,text=text,reply_markup=kb)
        except Exception:
            try:await context.bot.send_message(chat_id,text,message_thread_id=thread_id,reply_markup=kb)
            except Exception:pass
        return
    if action=='tradecancel':
        tid=int(p[2]); conn=_get_connection(); ok=False
        try:
            c=conn.cursor(); c.execute("UPDATE pokemon_trades_tb SET status='cancelled',finished_at=NOW(),updated_at=NOW() WHERE trade_id=%s AND status IN ('selecting','confirming') AND (user_a=%s OR user_b=%s) RETURNING trade_id",(tid,uid,uid)); ok=bool(c.fetchone()); conn.commit()
        except Exception:conn.rollback()
        finally:_put_connection(conn)
        if not ok:return await q.answer('Ese intercambio ya terminó.',show_alert=True)
        await q.answer('Intercambio cancelado.');
        try:return await q.edit_message_text('❌ Intercambio Pokémon cancelado.')
        except Exception:return
    if action=='tradeconfirm':
        tid=int(p[2]); conn=_get_connection(); finished=False; result_text=None; chat_id=None; thread_id=None; msgid=None
        try:
            c=conn.cursor(); c.execute("SELECT user_a,user_b,pokemon_a,pokemon_b,confirm_a,confirm_b,status,chat_id,thread_id,message_id FROM pokemon_trades_tb WHERE trade_id=%s FOR UPDATE",(tid,)); tr=c.fetchone()
            if not tr or tr[6]!='confirming' or uid not in (int(tr[0]),int(tr[1])):conn.rollback(); return await q.answer('Intercambio no disponible.',show_alert=True)
            ua,ub,pa,pb=int(tr[0]),int(tr[1]),int(tr[2]),int(tr[3])
            if _battle_busy_cursor(c,ua) or _battle_busy_cursor(c,ub):conn.rollback(); return await q.answer('No se puede cerrar un intercambio mientras alguno está en batalla.',show_alert=True)
            if uid==ua:c.execute("UPDATE pokemon_trades_tb SET confirm_a=TRUE,updated_at=NOW() WHERE trade_id=%s",(tid,))
            else:c.execute("UPDATE pokemon_trades_tb SET confirm_b=TRUE,updated_at=NOW() WHERE trade_id=%s",(tid,))
            c.execute("SELECT confirm_a,confirm_b FROM pokemon_trades_tb WHERE trade_id=%s",(tid,)); ca,cb=c.fetchone()
            chat_id=int(tr[7]); thread_id=tr[8]; msgid=tr[9]
            if not (ca and cb):conn.commit(); result_text='✅ Confirmaste. Falta la otra persona.'
            else:
                c.execute("SELECT pokemon_id,owner_id,species_id,nickname,level,shiny,moves_json FROM pokemon_instances_tb WHERE pokemon_id IN (%s,%s) FOR UPDATE",(pa,pb)); rr={int(x[0]):x for x in c.fetchall()}
                if pa not in rr or pb not in rr or int(rr[pa][1])!=ua or int(rr[pb][1])!=ub:conn.rollback(); return await q.answer('Una de las ofertas ya no está disponible.',show_alert=True)
                offered_a=rr[pa][3] or NAMES[int(rr[pa][2])]; offered_b=rr[pb][3] or NAMES[int(rr[pb][2])]
                # Los sacamos de sus equipos viejos para no dejar referencias cruzadas.
                for owner,pid in ((ua,pa),(ub,pb)):
                    for slot in (1,2,3,4):c.execute(f"UPDATE pokemon_team_tb SET slot{slot}=NULL,updated_at=NOW() WHERE owner_id=%s AND slot{slot}=%s",(owner,pid))
                    c.execute("UPDATE pokemon_team_tb SET principal_pokemon_id=NULL,updated_at=NOW() WHERE owner_id=%s AND principal_pokemon_id=%s",(owner,pid))
                c.execute("UPDATE pokemon_instances_tb SET owner_id=%s,updated_at=NOW() WHERE pokemon_id=%s",(ub,pa))
                c.execute("UPDATE pokemon_instances_tb SET owner_id=%s,updated_at=NOW() WHERE pokemon_id=%s",(ua,pb))
                evo_notes=[]
                for new_owner,pid,row in ((ub,pa,rr[pa]),(ua,pb,rr[pb])):
                    oldsid=int(row[2]); target=TRADE_EVOLUTIONS.get(oldsid)
                    finalsid=oldsid
                    if target:
                        finalsid=target
                        try: trade_moves=[str(x) for x in json.loads(row[6] or '[]') if str(x) in MOVES]
                        except Exception: trade_moves=[]
                        fill_notes=[]
                        if len(trade_moves)<4:
                            for req,move_code in _species_level_learnset(int(target)):
                                if int(req)>int(row[4]):break
                                if move_code in trade_moves:continue
                                _queue_level_move_cursor(c,new_owner,pid,int(target),row[3],trade_moves,move_code,fill_notes)
                                if len(trade_moves)>=4:break
                        c.execute("UPDATE pokemon_instances_tb SET species_id=%s,moves_json=%s,updated_at=NOW() WHERE pokemon_id=%s",(target,json.dumps(trade_moves[:4],ensure_ascii=False),pid))
                        evo_notes.append(f"✨ {row[3] or NAMES[oldsid]} evolucionó a {NAMES[target]} por intercambio.")
                        evo_notes.extend(fill_notes)
                    c.execute("""INSERT INTO pokemon_pokedex_tb(owner_id,species_id,obtained_count) VALUES(%s,%s,1)
                                 ON CONFLICT(owner_id,species_id) DO UPDATE SET obtained_count=pokemon_pokedex_tb.obtained_count+1,last_obtained_at=NOW()""",(new_owner,finalsid))
                c.execute("UPDATE pokemon_trades_tb SET status='done',finished_at=NOW(),updated_at=NOW() WHERE trade_id=%s",(tid,)); conn.commit(); finished=True
                result_text=(f'🔄 ¡INTERCAMBIO COMPLETADO!\n\n{offered_a} ↔ {offered_b}\n'
                             'Conservan nivel, XP, apodo, multimedia, Shiny, IV/DVs, estadísticas y objeto equipado.')
        except Exception as e:conn.rollback(); print('[PK trade confirm]',type(e).__name__,e); return await q.answer('No pude completar el intercambio.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Confirmado ✅',show_alert=True)
        if finished:
            # Orden visible solicitado: GIF -> resultado -> evolución por intercambio.
            gif_id=_trade_gif_file_id()
            if gif_id:
                try:await context.bot.send_animation(chat_id=chat_id,animation=gif_id,message_thread_id=thread_id)
                except Exception as e:print('[PK trade gif send]',type(e).__name__,e)
            try:await context.bot.send_message(chat_id,result_text,message_thread_id=thread_id)
            except Exception:pass
            if evo_notes:
                try:await context.bot.send_message(chat_id,'✨ EVOLUCIÓN POR INTERCAMBIO\n\n'+'\n'.join(evo_notes),message_thread_id=thread_id)
                except Exception:pass
            try:await context.bot.edit_message_text(chat_id=chat_id,message_id=msgid,text='✅ Intercambio Pokémon completado.')
            except Exception:pass
        return

    # ---- callbacks de batalla ----
    if action=='cancelchallenge':
        bid=int(p[2]); conn=_get_connection()
        try:
            c=conn.cursor(); c.execute("SELECT tournament_match_id FROM pokemon_battles_tb WHERE battle_id=%s AND challenger_id=%s AND status='open' FOR UPDATE",(bid,uid)); rr=c.fetchone()
            c.execute("UPDATE pokemon_battles_tb SET status='cancelled',updated_at=NOW() WHERE battle_id=%s AND challenger_id=%s AND status='open' RETURNING battle_id",(bid,uid)); ok=c.fetchone()
            if ok and rr and rr[0]:c.execute("UPDATE pokemon_tournament_matches_tb SET battle_id=NULL,status='pending' WHERE match_id=%s AND status='active'",(int(rr[0]),))
            conn.commit()
        except Exception:conn.rollback(); ok=None
        finally:_put_connection(conn)
        if not ok:return await q.answer('Ya no puedes cancelar ese reto.',show_alert=True)
        await q.answer('Reto cancelado.'); return await q.edit_message_text('❌ Reto Pokémon cancelado.')
    if action=='accept':
        bid=int(p[2]); mode=int(p[3]); conn=_get_connection(); state=None
        try:
            c=conn.cursor(); c.execute("SELECT challenger_id,opponent_id,status,chat_id,thread_id FROM pokemon_battles_tb WHERE battle_id=%s FOR UPDATE",(bid,)); br=c.fetchone()
            if not br or br[2]!='open':conn.rollback(); return await q.answer('Ese reto ya no está disponible.',show_alert=True)
            challenger=int(br[0]); invited=int(br[1]) if br[1] is not None else None
            if uid==challenger:conn.rollback(); return await q.answer('El rival debe aceptar.',show_alert=True)
            if invited is not None and uid!=invited:conn.rollback(); return await q.answer('Este reto era para otra persona.',show_alert=True)
            a_slots=_pvp_team_slot_ids_cursor(c,challenger); b_slots=_pvp_team_slot_ids_cursor(c,uid)
            if len(a_slots)<mode or len(b_slots)<mode:conn.rollback(); return await q.answer(f'Los dos necesitan al menos {mode} Pokémon dentro de los 4 espacios de /equipo.',show_alert=True)
            state={'status':'setup','battle_kind':'pvp','mode':mode,'round':1,'choices':{},'pvp_selected':{str(challenger):[],str(uid):[]},'pvp_ready':{},
                   'players':{str(challenger):{'name':_display_name_cursor(c,challenger),'mons':[],'active':0},str(uid):{'name':_display_name_cursor(c,uid),'mons':[],'active':0}}}
            c.execute("UPDATE pokemon_battles_tb SET opponent_id=%s,mode=%s,status='active',state_json=%s,message_id=%s,updated_at=NOW() WHERE battle_id=%s",(uid,mode,json.dumps(state,ensure_ascii=False),q.message.message_id,bid)); conn.commit()
        except Exception as e:conn.rollback(); print('[PK accept setup]',type(e).__name__,e); return await q.answer('No pude preparar la selección de equipo.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('¡Reto aceptado! Elijan sus Pokémon por privado.')
        for player in (challenger,uid):
            conn2=_get_connection()
            try:
                c2=conn2.cursor(); markup=_pvp_selection_markup_cursor(c2,player,bid,mode,[],False)
            finally:_put_connection(conn2)
            try:await context.bot.send_message(player,f'⚔️ BATALLA POKÉMON {mode}v{mode}\n\nElige {mode} Pokémon de tus 4 de /equipo.\nEl orden en que los marques será el orden de salida.',reply_markup=markup)
            except Exception:pass
        try:await q.edit_message_text(_pvp_setup_public_text(state))
        except Exception:pass
        return
    if action in ('pvppick','pvpready'):
        bid=int(p[2]); conn=_get_connection(); state=None; chat=None; start=False
        try:
            c=conn.cursor(); c.execute("SELECT state_json,status,chat_id,thread_id,message_id FROM pokemon_battles_tb WHERE battle_id=%s FOR UPDATE",(bid,)); br=c.fetchone()
            if not br or br[1]!='active':conn.rollback(); return await q.answer('La batalla ya no está disponible.',show_alert=True)
            state=json.loads(br[0]); key=str(uid)
            if state.get('battle_kind')!='pvp' or state.get('status')!='setup' or key not in state.get('players',{}):conn.rollback(); return await q.answer('Esta selección ya terminó.',show_alert=True)
            mode=int(state.get('mode',1)); selected=[int(x) for x in state.setdefault('pvp_selected',{}).get(key,[])]
            if state.setdefault('pvp_ready',{}).get(key):conn.rollback(); return await q.answer('Tu equipo ya está confirmado.',show_alert=True)
            slots=_pvp_team_slot_ids_cursor(c,uid)
            if action=='pvppick':
                pid=int(p[3])
                if pid not in slots:conn.rollback(); return await q.answer('Ese Pokémon ya no está en tus 4 espacios de /equipo.',show_alert=True)
                if pid in selected:selected.remove(pid)
                elif len(selected)<mode:selected.append(pid)
                else:conn.rollback(); return await q.answer(f'Ya elegiste {mode}. Quita uno primero.',show_alert=True)
                state['pvp_selected'][key]=selected
            else:
                if len(selected)!=mode:conn.rollback(); return await q.answer(f'Elige exactamente {mode} Pokémon.',show_alert=True)
                if any(pid not in slots for pid in selected):conn.rollback(); return await q.answer('Tu /equipo cambió. Vuelve a seleccionar.',show_alert=True)
                state['pvp_ready'][key]=True
                if all(state['pvp_ready'].get(k) for k in state['players']):
                    for k in list(state['players']):
                        chosen=[int(x) for x in state['pvp_selected'][k]]
                        mons=_pvp_mons_from_ids_cursor(c,int(k),chosen)
                        if not mons or len(mons)!=mode:conn.rollback(); return await q.answer('Uno de los equipos cambió. Vuelvan a iniciar el reto.',show_alert=True)
                        state['players'][k]['mons']=mons; state['players'][k]['active']=0
                    state['status']='active'; start=True
            c.execute("UPDATE pokemon_battles_tb SET state_json=%s,updated_at=NOW() WHERE battle_id=%s",(json.dumps(state,ensure_ascii=False),bid)); conn.commit(); chat=(int(br[2]),br[3],br[4])
        except Exception as e:conn.rollback(); print('[PK PvP team select]',type(e).__name__,e); return await q.answer('No pude guardar tu selección.',show_alert=True)
        finally:_put_connection(conn)
        if start:
            await q.answer('¡Equipos listos!')
            try:await q.edit_message_text('✅ Equipo confirmado. La batalla ya comenzó.')
            except Exception:pass
            await _sync_single_battle_views(context,bid,state,chat[0],chat[1],chat[2],'Equipos confirmados. Las decisiones se eligen por privado.')
        elif action=='pvpready':
            await q.answer('Equipo confirmado ✅')
            try:await q.edit_message_text('✅ Equipo confirmado. Esperando al rival…')
            except Exception:pass
            try:await context.bot.edit_message_text(chat_id=chat[0],message_id=chat[2],text=_pvp_setup_public_text(state))
            except Exception:pass
        else:
            conn2=_get_connection()
            try:c2=conn2.cursor(); markup=_pvp_selection_markup_cursor(c2,uid,bid,int(state['mode']),selected,False)
            finally:_put_connection(conn2)
            await q.answer(); await q.edit_message_text(f"⚔️ Elige {int(state['mode'])} Pokémon\nElegidos: {len(selected)}/{int(state['mode'])}\nEl orden de selección será el orden de salida.",reply_markup=markup)
        return
    if action=='safbattleball':
        bid=int(p[2]); conn=_get_connection(); state=None; chat=None; result_text=None; session_row=None
        try:
            c=conn.cursor(); c.execute("SELECT state_json,status,chat_id,thread_id,message_id FROM pokemon_battles_tb WHERE battle_id=%s FOR UPDATE",(bid,)); br=c.fetchone()
            if not br or br[1]!='active':conn.rollback(); return await q.answer('La pelea Safari ya terminó.',show_alert=True)
            state=json.loads(br[0]); key=str(uid)
            if state.get('battle_kind')!='safari' or int(state.get('safari_user_id',-1))!=uid or key not in state.get('players',{}):conn.rollback(); return await q.answer('Esta pelea Safari no es tuya.',show_alert=True)
            sid=int(state['safari_session_id']); botkey=str(state.get('bot_player_id')); bot=state['players'].get(botkey)
            if not bot or not bot.get('mons'):conn.rollback(); return await q.answer('El Pokémon Safari ya no está disponible.',show_alert=True)
            target=bot['mons'][bot['active']]
            c.execute("SELECT session_id,user_id,chat_id,thread_id,safari_date,status,balls,current_species,current_level,current_shiny,current_ivs_json,current_defeated,created_at,expires_at FROM pokemon_safari_sessions_tb WHERE session_id=%s FOR UPDATE",(sid,)); sr=c.fetchone()
            if not sr or int(sr[1])!=uid or str(sr[5])!='active' or sr[13]<=datetime.now(timezone.utc):conn.rollback(); return await q.answer('Tu Safari ya terminó.',show_alert=True)
            balls=int(sr[6])
            if balls<=0:
                c.execute("UPDATE pokemon_safari_sessions_tb SET status='exhausted',finished_at=NOW() WHERE session_id=%s",(sid,)); c.execute("UPDATE pokemon_battles_tb SET status='cancelled',finished_at=NOW(),updated_at=NOW() WHERE battle_id=%s",(bid,)); conn.commit(); return await q.answer('🔴 Se acabaron tus Safari Balls.',show_alert=True)
            balls-=1; hp_ratio=float(target.get('hp',0))/max(1,float(target.get('max_hp',1))); chance=_safari_capture_probability(int(target['species']),hp_ratio); caught=random.random()<chance; end_session=(balls<=0)
            if caught:
                data=grant_pokemon_with_cursor(c,uid,int(target['species']),f'safari:{sid}',level_override=int(target['level']),shiny_override=bool(target.get('shiny')),ivs_override=dict(target.get('ivs') or {})); _mission_progress_cursor(c,uid,'capture',1)
                c.execute("UPDATE pokemon_safari_sessions_tb SET balls=%s,current_species=NULL,current_level=NULL,current_shiny=NULL,current_ivs_json=NULL,current_defeated=FALSE,status=%s,finished_at=CASE WHEN %s THEN NOW() ELSE finished_at END WHERE session_id=%s",(balls,'exhausted' if end_session else 'active',end_session,sid))
                state['status']='finished'; state['winner']=uid; state['loser']=int(state.get('bot_player_id'))
                c.execute("UPDATE pokemon_battles_tb SET status='finished',winner_id=%s,state_json=%s,finished_at=NOW(),updated_at=NOW() WHERE battle_id=%s",(uid,json.dumps(state,ensure_ascii=False),bid))
                result_text=(f"🔴 ¡Safari Ball lanzada!\n🎉 ¡CAPTURADO!\n\n{'✨ SHINY · ' if data.get('shiny') else ''}#{int(data['species_id']):03d} {data['name']} {_sex_symbol(data.get('sex'))} · Nv.{int(data['level'])}\n🧬 IV {int(data['iv_percent'])}% · {data['iv_grade']}\n🔴 Safari Balls restantes: {balls}" + ('\n🏁 Se acabaron tus Safari Balls. Safari terminado.' if end_session else ''))
            else:
                if end_session:
                    c.execute("UPDATE pokemon_safari_sessions_tb SET balls=0,status='exhausted',current_species=NULL,current_level=NULL,current_shiny=NULL,current_ivs_json=NULL,current_defeated=FALSE,finished_at=NOW() WHERE session_id=%s",(sid,))
                    state['status']='finished'; c.execute("UPDATE pokemon_battles_tb SET status='cancelled',state_json=%s,finished_at=NOW(),updated_at=NOW() WHERE battle_id=%s",(json.dumps(state,ensure_ascii=False),bid))
                    result_text='🔴 La Safari Ball falló.\n🏁 Era tu última Safari Ball: la sesión terminó.'
                else:
                    c.execute("UPDATE pokemon_safari_sessions_tb SET balls=%s WHERE session_id=%s",(balls,sid)); c.execute("UPDATE pokemon_battles_tb SET state_json=%s,updated_at=NOW() WHERE battle_id=%s",(json.dumps(state,ensure_ascii=False),bid)); result_text=f'🔴 La Safari Ball falló. El Pokémon sigue en combate.\n🔴 Safari Balls restantes: {balls}'
            conn.commit(); chat=(int(br[2]),br[3],br[4])
            c2=conn.cursor(); c2.execute("SELECT session_id,user_id,chat_id,thread_id,safari_date,status,balls,current_species,current_level,current_shiny,current_ivs_json,current_defeated,created_at,expires_at FROM pokemon_safari_sessions_tb WHERE session_id=%s",(sid,)); session_row=c2.fetchone()
        except Exception as e:
            conn.rollback(); print('[PK safari battle ball]',type(e).__name__,e); return await q.answer('No pude lanzar la Safari Ball.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('🎉 ¡Capturado!' if state.get('winner')==uid else ('🏁 Safari terminado.' if state.get('status')=='finished' else '💨 ¡Se salió de la Safari Ball!'),show_alert=bool(state.get('status')=='finished'))
        await _delete_battle_transients(context,bid,uid)
        if state.get('status')=='finished':
            await _sync_single_battle_views(context,bid,state,chat[0],chat[1],chat[2],result_text,final=True)
            await _update_single_public_final(context,bid,state,chat[0],chat[1],chat[2],None,result_text)
            await _send_private_battle_result(context,state,result_text,skip_chat_id=chat[0])
            if session_row:
                try:await context.bot.send_message(int(session_row[2]),_safari_text(session_row),message_thread_id=int(session_row[3] or 0) or None,reply_markup=_safari_markup(session_row))
                except Exception:pass
        else:
            await _sync_single_battle_views(context,bid,state,chat[0],chat[1],chat[2],result_text,final=False)
        return

    if action=='action':
        bid=int(p[2]); br=_get_battle(bid)
        if not br or br[6]!='active':return await q.answer('La batalla ya terminó.',show_alert=True)
        state=json.loads(br[7]); key=str(uid)
        if key not in state['players']:return await q.answer('No participas en esta batalla.',show_alert=True)
        mon=state['players'][key]['mons'][state['players'][key]['active']]
        sent=await _set_private_battle_view(context,bid,uid,_single_private_text(state,uid,None,False),_single_private_markup(bid,state,uid,False),False)
        if sent is not None:await q.answer('Tu panel privado está actualizado.')
        else:return await q.answer('Abre primero el privado de PiBot con /start.',show_alert=True)
        return
    if action in ('move','bswitch','bitem'):
        bid=int(p[2]); conn=_get_connection(); final=None; state=None; logs=[]
        try:
            c=conn.cursor(); c.execute("SELECT state_json,status,chat_id,thread_id,message_id FROM pokemon_battles_tb WHERE battle_id=%s FOR UPDATE",(bid,)); br=c.fetchone()
            if not br or br[1]!='active':conn.rollback(); return await q.answer('La batalla ya terminó.',show_alert=True)
            state=json.loads(br[0]); key=str(uid)
            if key not in state['players']:conn.rollback(); return await q.answer('No participas en esta batalla.',show_alert=True)
            if key in state.get('choices',{}):conn.rollback(); return await q.answer('Ya elegiste en esta ronda.',show_alert=True)
            player=state['players'][key]
            if action=='move':
                idx=int(p[3]); mon=player['mons'][player['active']]
                if idx<0 or idx>=len(mon['moves']):conn.rollback(); return await q.answer('Movimiento inválido.',show_alert=True)
                code=mon['moves'][idx]
                locked=mon.get('choice_lock') if mon.get('held_item') in ('choice_band','choice_specs','choice_scarf') else None
                if locked and code!=locked:conn.rollback(); return await q.answer(f"{_item_name(mon.get('held_item'))} te mantiene usando {MOVES.get(locked,(locked,))[0]}.",show_alert=True)
                if int(mon.get('pp',{}).get(code,0))<=0:conn.rollback(); return await q.answer('Ese movimiento ya no tiene PP.',show_alert=True)
                state.setdefault('choices',{})[key]={'type':'move','move':code}
            elif action=='bswitch':
                idx=int(p[3]);
                if idx<0 or idx>=len(player['mons']) or idx==player['active'] or player['mons'][idx]['hp']<=0:conn.rollback(); return await q.answer('No puedes cambiar a ese Pokémon.',show_alert=True)
                state.setdefault('choices',{})[key]={'type':'switch','index':idx}
            else:
                code=p[3]
                if code not in ITEMS or ITEMS[code][3] not in ('heal','revive'):conn.rollback(); return await q.answer('Ese objeto no se usa en batalla.',show_alert=True)
                state.setdefault('choices',{})[key]={'type':'item','item':code}
            if state.get('battle_kind')=='training' and str(TRAINING_BOT_ID) in state['players'] and str(TRAINING_BOT_ID) not in state.get('choices',{}):
                state.setdefault('choices',{})[str(TRAINING_BOT_ID)]=_training_bot_choice(state)
            elif state.get('battle_kind') in ('npc','leader','safari'):
                bot_key=str(state.get('bot_player_id'))
                if bot_key in state['players'] and bot_key not in state.get('choices',{}):
                    state.setdefault('choices',{})[bot_key]=_npc_bot_choice(state)
            winner,logs,state=_resolve_round_cursor(c,bid,state)
            if winner is not None:
                if state.get('battle_kind')=='training':final=_finish_training_cursor(c,bid,state)
                elif state.get('battle_kind') in ('npc','leader'):final=_finish_npc_battle_cursor(c,bid,state)
                elif state.get('battle_kind')=='safari':final=_finish_safari_battle_cursor(c,bid,state)
                else:final=_finish_battle_cursor(c,bid,state)
            else:
                c.execute("UPDATE pokemon_battles_tb SET state_json=%s,updated_at=NOW() WHERE battle_id=%s",(json.dumps(state,ensure_ascii=False),bid))
            conn.commit(); chat_id=int(br[2]); thread_id=br[3]; msgid=br[4]
        except Exception as e:conn.rollback(); print('[PK action]',type(e).__name__,e); return await q.answer('No pude registrar la acción.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Acción elegida ✅')
        # Borra selectores auxiliares de cambio/objeto usados en esta ronda.
        await _delete_battle_transients(context,bid,uid)
        if logs or final:
            await _delete_all_battle_transients(context,bid,state)
        # Sincroniza el mismo estado en el grupo y en los paneles privados.
        # Las decisiones pendientes nunca se publican; solo se muestran resultados ya resueltos.
        note='\n'.join(logs[-8:]) if logs else 'Esperando la elección del rival…'
        await _sync_single_battle_views(context,bid,state,chat_id,thread_id,msgid,note,final=bool(final))
        if final:
            if final.get('safari'):
                result_text='\n'.join(_safari_result_lines(final))
                await _update_single_public_final(context,bid,state,chat_id,thread_id,msgid,note,result_text)
                await _send_private_battle_result(context,state,result_text,skip_chat_id=chat_id)
                conn2=_get_connection(); srow=None
                try:c2=conn2.cursor(); c2.execute("SELECT session_id,user_id,chat_id,thread_id,safari_date,status,balls,current_species,current_level,current_shiny,current_ivs_json,current_defeated,created_at,expires_at FROM pokemon_safari_sessions_tb WHERE session_id=%s",(int(final['session_id']),)); srow=c2.fetchone()
                finally:_put_connection(conn2)
                if srow:
                    try:await context.bot.send_message(int(srow[2]),_safari_text(srow),message_thread_id=int(srow[3] or 0) or None,reply_markup=_safari_markup(srow))
                    except Exception:pass
                return
            if final.get('training'):
                result_text='\n'.join(_training_result_lines(final))
                await _update_single_public_final(context,bid,state,chat_id,thread_id,msgid,note,result_text)
                await _send_private_battle_result(context,state,result_text,skip_chat_id=chat_id)
                return
            if final.get('npc'):
                result_text='\n'.join(_npc_result_lines(final))
                await _update_single_public_final(context,bid,state,chat_id,thread_id,msgid,note,result_text)
                await _send_private_battle_result(context,state,result_text,skip_chat_id=chat_id)
                if final.get('leader') and final.get('won') and final.get('bonus_pids'):
                    try:await context.bot.send_message(final['uid'],f'⭐ BONO DE LÍDER · +{LEADER_BONUS_XP} XP\nElige uno de los Pokémon que usaste:',reply_markup=_leader_bonus_markup(bid,final['bonus_pids']))
                    except Exception:pass
                if final.get('completion'):
                    try:await _announce_legendary_encounter(context,int(final['completion']['encounter_id']))
                    except Exception as e:print('[PK legendary completion announce]',type(e).__name__,e)
                if final.get('rocket_event'):
                    try:await _refresh_rocket_event_message(context,int(final['rocket_event']['event_id']))
                    except Exception as e:print('[PK rocket refresh]',type(e).__name__,e)
                return
            try:
                from handlers.season_pass import grant_season_xp
                wx=grant_season_xp(final['winner'],WIN_SEASON_XP,'pokemon_battle'); lx=grant_season_xp(final['loser'],LOSS_SEASON_XP,'pokemon_battle')
            except Exception:wx=lx=None
            wname=state['players'][str(final['winner'])]['name']; lname=state['players'][str(final['loser'])]['name']
            wxp=int(final.get('xp_rewards',{}).get(str(final['winner']),WIN_POKEMON_XP)); lxp=int(final.get('xp_rewards',{}).get(str(final['loser']),LOSS_POKEMON_XP))
            lines=[f"🏆 {wname} ganó la batalla Pokémon.",f"💰 {wname}: +{WIN_PIPESOS:,} PiPesos · ⭐ +{WIN_SEASON_XP} XP de temporada",f"💰 {lname}: +{LOSS_PIPESOS:,} PiPesos · ⭐ +{LOSS_SEASON_XP} XP de temporada",f"🎮 Pokémon: ganador +{wxp} XP c/u · rival +{lxp} XP c/u",f"📈 Ranking: ±{final['elo']} puntos"]+final['notes'][:6]
            result_text='\n'.join(lines)
            await _update_single_public_final(context,bid,state,chat_id,thread_id,msgid,note,result_text)
            await _send_private_battle_result(context,state,result_text,skip_chat_id=chat_id)
            tinfo=final.get('tournament')
            if tinfo:
                conn2=None
                try:
                    conn2=_get_connection(); c2=conn2.cursor(); ttext=_tournament_round_text_cursor(c2,int(tinfo['tournament_id'])); conn2.commit()
                    adv=tinfo.get('advance') or {}
                    if adv.get('finished'):
                        champ=state['players'].get(str(adv['champion']),{}).get('name','Campeón')
                        ttext += f"\n\n👑 ¡{champ} es campeón del torneo!"
                    await context.bot.send_message(chat_id,ttext,message_thread_id=thread_id)
                except Exception as e:print('[PK tournament announce]',type(e).__name__,e)
                finally:
                    if conn2 is not None:_put_connection(conn2)
        return
    if action=='bswitchmenu':
        bid=int(p[2]); br=_get_battle(bid)
        if not br or br[6]!='active':return await q.answer('Batalla terminada.',show_alert=True)
        state=json.loads(br[7]); key=str(uid)
        if key not in state['players']:return await q.answer('No participas.',show_alert=True)
        pl=state['players'][key]; rows=[]
        for i,m in enumerate(pl['mons']):
            if i!=pl['active'] and m['hp']>0:rows.append([InlineKeyboardButton(f"🔄 {_battle_title_mon(m)} · {m['hp']}/{m['max_hp']} HP",callback_data=f'pk:bswitch:{bid}:{i}')])
        if not rows:return await q.answer('No tienes otro Pokémon disponible.',show_alert=True)
        await q.answer(); return await _send_battle_transient(context,bid,uid,'Elige cambio para esta ronda:',InlineKeyboardMarkup(rows))
    if action=='bitemmenu':
        bid=int(p[2]); conn=_get_connection()
        try:c=conn.cursor(); c.execute("SELECT item_code,qty FROM pokemon_items_tb WHERE owner_id=%s AND qty>0",(uid,)); inv=c.fetchall()
        finally:_put_connection(conn)
        rows=[]
        for code,qty in inv:
            if code in ITEMS and ITEMS[code][3] in ('heal','revive'):
                name,em,_,_=ITEMS[code]; rows.append([InlineKeyboardButton(f'{em} {name} ×{qty}',callback_data=f'pk:bitem:{bid}:{code}')])
        if not rows:return await q.answer('No tienes objetos utilizables en batalla.',show_alert=True)
        await q.answer(); return await _send_battle_transient(context,bid,uid,'🎒 Elige objeto para esta ronda:',InlineKeyboardMarkup(rows))
    if action=='surrender':
        bid=int(p[2]); conn=_get_connection(); final=None; state=None; chat_id=None; thread_id=None
        try:
            c=conn.cursor(); c.execute("SELECT state_json,status,chat_id,thread_id FROM pokemon_battles_tb WHERE battle_id=%s FOR UPDATE",(bid,)); br=c.fetchone()
            if not br or br[1]!='active':conn.rollback(); return await q.answer('Ya terminó.',show_alert=True)
            state=json.loads(br[0]); key=str(uid)
            if key not in state['players']:conn.rollback(); return await q.answer('No participas.',show_alert=True)
            ids=list(state['players'].keys()); other=int(ids[1] if key==ids[0] else ids[0]); state['status']='finished'; state['winner']=other; state['loser']=uid
            if state.get('battle_kind')=='training':final=_finish_training_cursor(c,bid,state)
            elif state.get('battle_kind') in ('npc','leader'):final=_finish_npc_battle_cursor(c,bid,state)
            elif state.get('battle_kind')=='safari':final=_finish_safari_battle_cursor(c,bid,state)
            else:final=_finish_battle_cursor(c,bid,state)
            conn.commit(); chat_id=int(br[2]); thread_id=br[3]
        except Exception:conn.rollback(); return await q.answer('No pude rendirte.',show_alert=True)
        finally:_put_connection(conn)
        await q.answer('Te rendiste.',show_alert=True)
        await _delete_all_battle_transients(context,bid,state)
        br2=_get_battle(bid); msgid=br2[8] if br2 else None
        await _sync_single_battle_views(context,bid,state,chat_id,thread_id,msgid,f"🏳 {state['players'][str(uid)]['name']} se rindió.",final=True)
        if final.get('safari'):result_text='\n'.join(_safari_result_lines(final))
        elif final.get('training'):result_text='\n'.join(_training_result_lines(final))
        elif final.get('npc'):result_text='\n'.join(_npc_result_lines(final))
        else:result_text=f"🏳 {state['players'][str(uid)]['name']} se rindió.\n🏆 Gana {state['players'][str(final['winner'])]['name']}."
        await _update_single_public_final(context,bid,state,chat_id,thread_id,msgid,f"🏳 {state['players'][str(uid)]['name']} se rindió.",result_text)
        await _send_private_battle_result(context,state,result_text,skip_chat_id=chat_id)
        return

    return await q.answer()


async def pokemon_text_input(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type!='private':return
    pid=context.user_data.get('pk_wait_nick')
    if not pid:return
    txt=(update.effective_message.text or '').strip()
    if not txt:return
    name=None if txt=='-' else txt[:24]
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE pokemon_instances_tb SET nickname=%s,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s RETURNING species_id",(name,update.effective_user.id,pid)); ok=c.fetchone(); conn.commit()
    except Exception:conn.rollback(); ok=None
    finally:_put_connection(conn)
    context.user_data.pop('pk_wait_nick',None)
    await update.effective_message.reply_text(f"🏷️ Apodo {'quitado' if name is None else 'guardado: '+name}." if ok else 'No encontré ese Pokémon.')


async def pokemon_media_input(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type!='private':return
    m=update.effective_message; media_type=None; file_id=None
    if m.animation:media_type='animation'; file_id=m.animation.file_id
    elif m.video:media_type='video'; file_id=m.video.file_id
    elif m.photo:media_type='photo'; file_id=m.photo[-1].file_id

    # Multimedia global de Halloween, configurada por BotMaster desde /imagenesevento.
    event_key=context.user_data.get('pk_wait_halloween_media')
    if event_key:
        try:allowed=is_botmaster(update.effective_user.id)
        except Exception:allowed=False
        if not allowed:
            context.user_data.pop('pk_wait_halloween_media',None); return await m.reply_text('Solo BotMaster puede configurar multimedia de Halloween.')
        if media_type not in ('photo','animation') or not file_id:return await m.reply_text('Envíame una FOTO o un GIF/animación de Telegram.')
        if event_key not in HALLOWEEN_MEDIA_KEYS:
            context.user_data.pop('pk_wait_halloween_media',None); return await m.reply_text('Ese elemento de Halloween ya no existe.')
        conn=_get_connection(); ok=False
        try:
            c=conn.cursor(); c.execute("""INSERT INTO pokemon_halloween_media_tb(media_key,media_type,media_file_id,updated_by)
                                        VALUES(%s,%s,%s,%s)
                                        ON CONFLICT(media_key) DO UPDATE SET media_type=EXCLUDED.media_type,media_file_id=EXCLUDED.media_file_id,updated_by=EXCLUDED.updated_by,updated_at=NOW()""",
                                      (event_key,media_type,file_id,update.effective_user.id))
            # Pikachu Halloween usa arte global: al cambiarlo se actualizan también los ya entregados.
            if event_key in ('pikachu_normal','pikachu_shiny'):
                want_shiny=(event_key=='pikachu_shiny')
                c.execute("UPDATE pokemon_instances_tb SET media_type=%s,media_file_id=%s,updated_at=NOW() WHERE obtained_from='halloween_2026_pikachu' AND shiny=%s",
                          (media_type,file_id,want_shiny))
            conn.commit(); ok=True
        except Exception as e:conn.rollback(); print('[PK Halloween media]',type(e).__name__,e)
        finally:_put_connection(conn)
        context.user_data.pop('pk_wait_halloween_media',None)
        return await m.reply_text(f"✅ {HALLOWEEN_MEDIA_KEYS[event_key]}: {'GIF' if media_type=='animation' else 'imagen'} guardado." if ok else 'No pude guardar la multimedia de Halloween.')

    # Multimedia global de huevos/eclosión, configurada por BotMaster desde /imageneshuevo.
    egg_key=context.user_data.get('pk_wait_egg_media')
    if egg_key:
        try:allowed=is_botmaster(update.effective_user.id)
        except Exception:allowed=False
        if not allowed:
            context.user_data.pop('pk_wait_egg_media',None); return await m.reply_text('Solo BotMaster puede configurar multimedia de huevos.')
        if media_type not in ('photo','animation') or not file_id:return await m.reply_text('Envíame una FOTO o un GIF/animación de Telegram.')
        if egg_key not in ('comun','raro','epico','hatching'):
            context.user_data.pop('pk_wait_egg_media',None); return await m.reply_text('Ese tipo de huevo ya no existe.')
        conn=_get_connection(); ok=False
        try:
            c=conn.cursor(); c.execute("""INSERT INTO pokemon_egg_media_tb(egg_key,media_type,media_file_id,updated_by)
                                        VALUES(%s,%s,%s,%s)
                                        ON CONFLICT(egg_key) DO UPDATE SET media_type=EXCLUDED.media_type,media_file_id=EXCLUDED.media_file_id,updated_by=EXCLUDED.updated_by,updated_at=NOW()""",
                                      (egg_key,media_type,file_id,update.effective_user.id)); conn.commit(); ok=True
        except Exception as e:conn.rollback(); print('[PK egg media]',type(e).__name__,e)
        finally:_put_connection(conn)
        context.user_data.pop('pk_wait_egg_media',None)
        return await m.reply_text(f"✅ {egg_key}: {'GIF' if media_type=='animation' else 'imagen'} guardado." if ok else 'No pude guardar la multimedia del huevo.')

    # Multimedia global de NPC/líder, configurada solo por BotMaster desde /imagenesnpc.
    npc_key=context.user_data.get('pk_wait_npc_media')
    if npc_key:
        try:
            allowed=is_botmaster(update.effective_user.id)
        except Exception:
            allowed=False
        if not allowed:
            context.user_data.pop('pk_wait_npc_media',None)
            return await m.reply_text('Solo BotMaster puede configurar multimedia de NPC.')
        if media_type not in ('photo','animation') or not file_id:
            return await m.reply_text('Envíame una FOTO o un GIF/animación de Telegram.')
        if npc_key not in NPC_ALL:
            context.user_data.pop('pk_wait_npc_media',None)
            return await m.reply_text('Ese NPC ya no existe en el catálogo.')
        conn=_get_connection(); ok=False
        try:
            c=conn.cursor(); c.execute("""INSERT INTO pokemon_npc_media_tb(npc_key,media_type,media_file_id,updated_by)
                                        VALUES(%s,%s,%s,%s)
                                        ON CONFLICT(npc_key) DO UPDATE SET media_type=EXCLUDED.media_type,media_file_id=EXCLUDED.media_file_id,updated_by=EXCLUDED.updated_by,updated_at=NOW()""",
                                      (npc_key,media_type,file_id,update.effective_user.id)); conn.commit(); ok=True
        except Exception as e:
            conn.rollback(); print('[PK NPC media]',type(e).__name__,e)
        finally:_put_connection(conn)
        context.user_data.pop('pk_wait_npc_media',None)
        return await m.reply_text(f"✅ {_npc_label(npc_key)}: {'GIF' if media_type=='animation' else 'imagen'} guardado por file_id." if ok else 'No pude guardar la multimedia del NPC.')

    # Multimedia del perfil de entrenador. Se guarda por user_id; nunca usa la foto de otro usuario.
    if context.user_data.get('pk_wait_trainer_media'):
        if not file_id:return await m.reply_text('Envíame una foto, GIF/animación o video de Telegram.')
        uid=update.effective_user.id; conn=_get_connection(); ok=False
        try:
            c=conn.cursor(); _ensure_trainer_row_cursor(c,uid)
            c.execute("UPDATE pokemon_trainer_tb SET media_type=%s,media_file_id=%s,updated_at=NOW() WHERE user_id=%s",(media_type,file_id,uid)); conn.commit(); ok=True
        except Exception as e:
            conn.rollback(); print('[PK trainer media]',type(e).__name__,e)
        finally:_put_connection(conn)
        context.user_data.pop('pk_wait_trainer_media',None)
        if not ok:return await m.reply_text('No pude guardar la multimedia de tu entrenador.')
        await m.reply_text('✅ Multimedia de entrenador guardada. Así queda TU perfil:')
        try:await _send_trainer_profile(context,uid,uid,controls=True)
        except Exception as e:print('[PK trainer media preview]',type(e).__name__,e)
        return

    pid=context.user_data.get('pk_wait_media')
    if not pid:return
    if not file_id:return await m.reply_text('Envíame una foto, GIF/animación o video de Telegram.')
    conn=_get_connection()
    try:
        c=conn.cursor(); c.execute("UPDATE pokemon_instances_tb SET media_type=%s,media_file_id=%s,updated_at=NOW() WHERE owner_id=%s AND pokemon_id=%s RETURNING species_id",(media_type,file_id,update.effective_user.id,pid)); ok=c.fetchone(); conn.commit()
    except Exception:conn.rollback(); ok=None
    finally:_put_connection(conn)
    context.user_data.pop('pk_wait_media',None)
    await m.reply_text('🎞️ GIF guardado.' if ok and media_type=='animation' else '🎥 Video guardado.' if ok and media_type=='video' else '🖼️ Foto guardada.' if ok else 'No encontré ese Pokémon.')
