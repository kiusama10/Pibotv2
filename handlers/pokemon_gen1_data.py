"""Datos compactos para el módulo Pokémon Gen 1 de PiBot.

El módulo usa únicamente especies 1-151 y tipos existentes en la primera
generación. Los combates están adaptados a Telegram/PiBot: no cargan imágenes
ni hacen consultas externas.
"""
from __future__ import annotations

# Pokédex de Kanto, 1-151. El nombre mostrado conserva la forma clásica.
_NAMES = """
Bulbasaur|Ivysaur|Venusaur|Charmander|Charmeleon|Charizard|Squirtle|Wartortle|Blastoise|Caterpie|Metapod|Butterfree|Weedle|Kakuna|Beedrill|Pidgey|Pidgeotto|Pidgeot|Rattata|Raticate|Spearow|Fearow|Ekans|Arbok|Pikachu|Raichu|Sandshrew|Sandslash|Nidoran♀|Nidorina|Nidoqueen|Nidoran♂|Nidorino|Nidoking|Clefairy|Clefable|Vulpix|Ninetales|Jigglypuff|Wigglytuff|Zubat|Golbat|Oddish|Gloom|Vileplume|Paras|Parasect|Venonat|Venomoth|Diglett|Dugtrio|Meowth|Persian|Psyduck|Golduck|Mankey|Primeape|Growlithe|Arcanine|Poliwag|Poliwhirl|Poliwrath|Abra|Kadabra|Alakazam|Machop|Machoke|Machamp|Bellsprout|Weepinbell|Victreebel|Tentacool|Tentacruel|Geodude|Graveler|Golem|Ponyta|Rapidash|Slowpoke|Slowbro|Magnemite|Magneton|Farfetch'd|Doduo|Dodrio|Seel|Dewgong|Grimer|Muk|Shellder|Cloyster|Gastly|Haunter|Gengar|Onix|Drowzee|Hypno|Krabby|Kingler|Voltorb|Electrode|Exeggcute|Exeggutor|Cubone|Marowak|Hitmonlee|Hitmonchan|Lickitung|Koffing|Weezing|Rhyhorn|Rhydon|Chansey|Tangela|Kangaskhan|Horsea|Seadra|Goldeen|Seaking|Staryu|Starmie|Mr. Mime|Scyther|Jynx|Electabuzz|Magmar|Pinsir|Tauros|Magikarp|Gyarados|Lapras|Ditto|Eevee|Vaporeon|Jolteon|Flareon|Porygon|Omanyte|Omastar|Kabuto|Kabutops|Aerodactyl|Snorlax|Articuno|Zapdos|Moltres|Dratini|Dragonair|Dragonite|Mewtwo|Mew
""".strip().split("|")
NAMES = {i + 1: name for i, name in enumerate(_NAMES)}

# Tipos de Gen 1 (sin Acero, Siniestro ni Hada).
_TYPE_ROWS = """
1 Grass Poison
2 Grass Poison
3 Grass Poison
4 Fire
5 Fire
6 Fire Flying
7 Water
8 Water
9 Water
10 Bug
11 Bug
12 Bug Flying
13 Bug Poison
14 Bug Poison
15 Bug Poison
16 Normal Flying
17 Normal Flying
18 Normal Flying
19 Normal
20 Normal
21 Normal Flying
22 Normal Flying
23 Poison
24 Poison
25 Electric
26 Electric
27 Ground
28 Ground
29 Poison
30 Poison
31 Poison Ground
32 Poison
33 Poison
34 Poison Ground
35 Normal
36 Normal
37 Fire
38 Fire
39 Normal
40 Normal
41 Poison Flying
42 Poison Flying
43 Grass Poison
44 Grass Poison
45 Grass Poison
46 Bug Grass
47 Bug Grass
48 Bug Poison
49 Bug Poison
50 Ground
51 Ground
52 Normal
53 Normal
54 Water
55 Water
56 Fighting
57 Fighting
58 Fire
59 Fire
60 Water
61 Water
62 Water Fighting
63 Psychic
64 Psychic
65 Psychic
66 Fighting
67 Fighting
68 Fighting
69 Grass Poison
70 Grass Poison
71 Grass Poison
72 Water Poison
73 Water Poison
74 Rock Ground
75 Rock Ground
76 Rock Ground
77 Fire
78 Fire
79 Water Psychic
80 Water Psychic
81 Electric
82 Electric
83 Normal Flying
84 Normal Flying
85 Normal Flying
86 Water
87 Water Ice
88 Poison
89 Poison
90 Water
91 Water Ice
92 Ghost Poison
93 Ghost Poison
94 Ghost Poison
95 Rock Ground
96 Psychic
97 Psychic
98 Water
99 Water
100 Electric
101 Electric
102 Grass Psychic
103 Grass Psychic
104 Ground
105 Ground
106 Fighting
107 Fighting
108 Normal
109 Poison
110 Poison
111 Ground Rock
112 Ground Rock
113 Normal
114 Grass
115 Normal
116 Water
117 Water
118 Water
119 Water
120 Water
121 Water Psychic
122 Psychic
123 Bug Flying
124 Ice Psychic
125 Electric
126 Fire
127 Bug
128 Normal
129 Water
130 Water Flying
131 Water Ice
132 Normal
133 Normal
134 Water
135 Electric
136 Fire
137 Normal
138 Rock Water
139 Rock Water
140 Rock Water
141 Rock Water
142 Rock Flying
143 Normal
144 Ice Flying
145 Electric Flying
146 Fire Flying
147 Dragon
148 Dragon
149 Dragon Flying
150 Psychic
151 Psychic
""".strip().splitlines()
TYPES = {}
for _row in _TYPE_ROWS:
    _p = _row.split()
    TYPES[int(_p[0])] = tuple(_p[1:])

# Evoluciones por nivel. Las de piedra y las de intercambio van aparte.
LEVEL_EVOLUTIONS = {
    1:(16,2),2:(32,3),4:(16,5),5:(36,6),7:(16,8),8:(36,9),
    10:(7,11),11:(10,12),13:(7,14),14:(10,15),16:(18,17),17:(36,18),
    19:(20,20),21:(20,22),23:(22,24),27:(22,28),29:(16,30),32:(16,33),
    41:(22,42),43:(21,44),46:(24,47),48:(31,49),50:(26,51),52:(28,53),
    54:(33,55),56:(28,57),60:(25,61),63:(16,64),66:(28,67),69:(21,70),
    72:(30,73),74:(25,75),77:(40,78),79:(37,80),81:(30,82),84:(31,85),
    86:(34,87),88:(38,89),92:(25,93),96:(26,97),98:(28,99),100:(30,101),
    104:(28,105),109:(35,110),111:(42,112),116:(32,117),118:(33,119),
    129:(20,130),138:(40,139),140:(40,141),147:(30,148),148:(55,149),
}
STONE_EVOLUTIONS = {
    25:{"thunder_stone":26},35:{"moon_stone":36},37:{"fire_stone":38},
    39:{"moon_stone":40},44:{"leaf_stone":45},58:{"fire_stone":59},
    61:{"water_stone":62},70:{"leaf_stone":71},90:{"water_stone":91},
    102:{"leaf_stone":103},120:{"water_stone":121},
    133:{"water_stone":134,"thunder_stone":135,"fire_stone":136},
    30:{"moon_stone":31},33:{"moon_stone":34},
}
TRADE_EVOLUTIONS = {64:65,67:68,75:76,93:94}

LEGENDARY_IDS = {144,145,146,150,151}
EPIC_IDS = {
    3,6,9,31,34,36,38,40,45,59,62,65,68,71,76,80,82,85,87,89,91,94,
    99,101,103,105,112,113,115,121,123,124,125,126,127,128,130,131,
    134,135,136,139,141,142,143,149,
}
RARE_IDS = {
    2,5,8,12,15,18,20,22,24,26,28,30,33,42,44,47,49,51,53,55,57,61,
    64,67,70,73,75,78,79,81,83,84,86,92,93,95,97,98,100,102,108,109,
    110,111,114,117,119,120,122,132,133,137,138,140,147,148,
}

def rarity_for(species_id:int)->str:
    if species_id in LEGENDARY_IDS:return "legendario"
    if species_id in EPIC_IDS:return "epico"
    if species_id in RARE_IDS:return "raro"
    return "comun"

# Objetos Pokémon. Los de curación se pueden usar en combate y las piedras fuera.
ITEMS = {
    "potion":("Poción","🧪",20,"heal"),
    "super_potion":("Superpoción","🧪",50,"heal"),
    "hyper_potion":("Hiperpoción","🧪",120,"heal"),
    "full_restore":("Restaurar Todo","✨",9999,"heal"),
    "revive":("Revivir","💎",50,"revive"),
    "fire_stone":("Piedra Fuego","🔥",0,"evolution"),
    "water_stone":("Piedra Agua","💧",0,"evolution"),
    "thunder_stone":("Piedra Trueno","⚡",0,"evolution"),
    "leaf_stone":("Piedra Hoja","🍃",0,"evolution"),
    "moon_stone":("Piedra Lunar","🌙",0,"evolution"),
    "link_cable":("Cable Link","🔗",0,"trade_evolution"),
    "rare_candy":("Caramelo Raro","🍬",0,"level"),
}

# Movimientos disponibles en el motor. Todos pertenecen a Gen 1. Se usa la
# división físico/especial por TIPO propia de Gen 1, no la división moderna.
# kind: damage, heal, buff, debuff, fixed, sleep, poison, paralyze, transform.
MOVES = {
    "tackle":("Placaje","Normal",40,100,35,"damage"),
    "scratch":("Arañazo","Normal",40,100,35,"damage"),
    "pound":("Destructor","Normal",40,100,35,"damage"),
    "quick_attack":("Ataque Rápido","Normal",40,100,30,"damage"),
    "body_slam":("Golpe Cuerpo","Normal",85,100,15,"damage"),
    "slash":("Cuchillada","Normal",70,100,20,"damage"),
    "hyper_beam":("Hiperrayo","Normal",150,90,5,"damage"),
    "gust":("Tornado","Flying",40,100,35,"damage"),
    "wing_attack":("Ataque Ala","Flying",60,100,35,"damage"),
    "peck":("Picotazo","Flying",35,100,35,"damage"),
    "drill_peck":("Pico Taladro","Flying",80,100,20,"damage"),
    "vine_whip":("Látigo Cepa","Grass",45,100,25,"damage"),
    "razor_leaf":("Hoja Afilada","Grass",55,95,25,"damage"),
    "mega_drain":("Megaagotar","Grass",40,100,10,"drain"),
    "solar_beam":("Rayo Solar","Grass",120,100,10,"damage"),
    "ember":("Ascuas","Fire",40,100,25,"damage"),
    "fire_spin":("Giro Fuego","Fire",35,85,15,"damage"),
    "flamethrower":("Lanzallamas","Fire",95,100,15,"damage"),
    "fire_blast":("Llamarada","Fire",120,85,5,"damage"),
    "water_gun":("Pistola Agua","Water",40,100,25,"damage"),
    "bubble_beam":("Rayo Burbuja","Water",65,100,20,"damage"),
    "surf":("Surf","Water",95,100,15,"damage"),
    "hydro_pump":("Hidrobomba","Water",120,80,5,"damage"),
    "thunder_shock":("Impactrueno","Electric",40,100,30,"damage"),
    "swift":("Rapidez","Normal",60,100,20,"damage"),
    "thunderbolt":("Rayo","Electric",95,100,15,"damage"),
    "thunder":("Trueno","Electric",120,70,10,"damage"),
    "confusion":("Confusión","Psychic",50,100,25,"damage"),
    "psybeam":("Psicorrayo","Psychic",65,100,20,"damage"),
    "psychic":("Psíquico","Psychic",90,100,10,"damage"),
    "recover":("Recuperación","Normal",0,100,10,"heal"),
    "karate_chop":("Golpe Karate","Fighting",50,100,25,"damage"),
    "low_kick":("Patada Baja","Fighting",50,90,20,"damage"),
    "submission":("Sumisión","Fighting",80,80,25,"damage"),
    "seismic_toss":("Mov. Sísmico","Fighting",0,100,20,"fixed"),
    "poison_sting":("Picotazo Veneno","Poison",15,100,35,"damage"),
    "acid":("Ácido","Poison",40,100,30,"damage"),
    "sludge":("Residuos","Poison",65,100,20,"damage"),
    "toxic":("Tóxico","Poison",0,85,10,"poison"),
    "dig":("Excavar","Ground",100,100,10,"damage"),
    "earthquake":("Terremoto","Ground",100,100,10,"damage"),
    "rock_throw":("Lanzarrocas","Rock",50,65,15,"damage"),
    "rock_slide":("Avalancha","Rock",75,90,10,"damage"),
    "leech_life":("Chupavidas","Bug",20,100,15,"drain"),
    "twineedle":("Doble Ataque","Bug",50,100,20,"damage"),
    "pin_missile":("Pin Misil","Bug",60,85,20,"damage"),
    "lick":("Lengüetazo","Ghost",20,100,30,"damage"),
    "night_shade":("Tinieblas","Ghost",0,100,15,"fixed"),
    "hypnosis":("Hipnosis","Psychic",0,60,20,"sleep"),
    "dream_eater":("Comesueños","Psychic",100,100,15,"damage"),
    "ice_beam":("Rayo Hielo","Ice",95,100,10,"damage"),
    "blizzard":("Ventisca","Ice",120,90,5,"damage"),
    "dragon_rage":("Furia Dragón","Dragon",0,100,10,"fixed40"),
    "slam":("Atizar","Normal",80,75,20,"damage"),
    "harden":("Fortaleza","Normal",0,100,30,"buff_def"),
    "growl":("Gruñido","Normal",0,100,40,"debuff_atk"),
    "agility":("Agilidad","Psychic",0,100,30,"buff_speed"),
    "thunder_wave":("Onda Trueno","Electric",0,100,20,"paralyze"),
    "sleep_powder":("Somnífero","Grass",0,75,15,"sleep"),
    "splash":("Salpicadura","Normal",0,100,40,"nothing"),
    "teleport":("Teletransporte","Psychic",0,100,20,"nothing"),
    "transform":("Transformación","Normal",0,100,10,"transform"),
    "metronome":("Metrónomo","Normal",0,100,10,"metronome"),
}

TYPE_MOVESETS = {
    "Normal":[(1,"tackle"),(10,"quick_attack"),(25,"body_slam"),(45,"hyper_beam")],
    "Fire":[(1,"ember"),(15,"fire_spin"),(30,"flamethrower"),(48,"fire_blast")],
    "Water":[(1,"water_gun"),(15,"bubble_beam"),(30,"surf"),(48,"hydro_pump")],
    "Grass":[(1,"vine_whip"),(14,"razor_leaf"),(28,"mega_drain"),(48,"solar_beam")],
    "Electric":[(1,"thunder_shock"),(16,"swift"),(28,"thunderbolt"),(48,"thunder")],
    "Psychic":[(1,"confusion"),(18,"psybeam"),(32,"psychic"),(48,"recover")],
    "Fighting":[(1,"karate_chop"),(15,"low_kick"),(30,"submission"),(42,"seismic_toss")],
    "Poison":[(1,"poison_sting"),(15,"acid"),(30,"sludge"),(45,"toxic")],
    "Ground":[(1,"tackle"),(18,"dig"),(32,"earthquake"),(48,"body_slam")],
    "Rock":[(1,"rock_throw"),(20,"body_slam"),(32,"rock_slide"),(48,"earthquake")],
    "Flying":[(1,"gust"),(16,"wing_attack"),(30,"drill_peck"),(46,"agility")],
    "Bug":[(1,"leech_life"),(16,"twineedle"),(30,"pin_missile"),(45,"body_slam")],
    "Ghost":[(1,"lick"),(18,"night_shade"),(28,"hypnosis"),(42,"dream_eater")],
    "Ice":[(1,"tackle"),(20,"ice_beam"),(32,"body_slam"),(48,"blizzard")],
    "Dragon":[(1,"dragon_rage"),(18,"slam"),(34,"agility"),(50,"hyper_beam")],
}

# Casos emblemáticos donde un set genérico no representa bien al Pokémon.
SPECIAL_LEARNSETS = {
    10:[(1,"tackle")], 11:[(1,"harden")], 13:[(1,"poison_sting")], 14:[(1,"harden")],
    25:[(1,"thunder_shock"),(9,"growl"),(16,"quick_attack"),(26,"swift"),(33,"agility"),(43,"thunder")],
    26:[(1,"thunder_shock"),(1,"growl"),(1,"quick_attack"),(1,"thunder")],
    63:[(1,"teleport")],
    92:[(1,"lick"),(1,"hypnosis"),(21,"night_shade"),(35,"dream_eater")],
    93:[(1,"lick"),(1,"hypnosis"),(21,"night_shade"),(38,"dream_eater")],
    94:[(1,"lick"),(1,"hypnosis"),(29,"night_shade"),(38,"dream_eater")],
    129:[(1,"splash"),(15,"tackle")],
    130:[(1,"tackle"),(20,"bite" if "bite" in MOVES else "body_slam"),(25,"dragon_rage"),(32,"hydro_pump"),(41,"hyper_beam")],
    132:[(1,"transform")],
    133:[(1,"tackle"),(16,"quick_attack"),(31,"body_slam"),(45,"agility")],
    144:[(1,"ice_beam"),(20,"agility"),(40,"blizzard"),(51,"hyper_beam")],
    145:[(1,"thunder_shock"),(20,"agility"),(40,"thunderbolt"),(51,"thunder")],
    146:[(1,"ember"),(20,"agility"),(40,"flamethrower"),(51,"fire_blast")],
    147:[(1,"wrap" if "wrap" in MOVES else "slam"),(10,"thunder_wave"),(20,"agility"),(30,"dragon_rage")],
    148:[(1,"slam"),(10,"thunder_wave"),(20,"agility"),(35,"dragon_rage")],
    149:[(1,"slam"),(10,"thunder_wave"),(20,"agility"),(35,"dragon_rage"),(55,"hyper_beam")],
    150:[(1,"confusion"),(20,"swift"),(40,"psychic"),(55,"recover"),(63,"agility")],
    151:[(1,"pound"),(10,"transform"),(20,"body_slam"),(30,"metronome"),(40,"psychic")],
}

# Tabla de efectividad de tipos inspirada en Gen 1. Solo se listan cambios a 2,
# 0.5 o 0; lo demás es neutral.
TYPE_CHART = {
    "Normal":{"Rock":0.5,"Ghost":0},
    "Fire":{"Grass":2,"Ice":2,"Bug":2,"Fire":0.5,"Water":0.5,"Rock":0.5,"Dragon":0.5},
    "Water":{"Fire":2,"Ground":2,"Rock":2,"Water":0.5,"Grass":0.5,"Dragon":0.5},
    "Electric":{"Water":2,"Flying":2,"Electric":0.5,"Grass":0.5,"Dragon":0.5,"Ground":0},
    "Grass":{"Water":2,"Ground":2,"Rock":2,"Fire":0.5,"Grass":0.5,"Poison":0.5,"Flying":0.5,"Bug":0.5,"Dragon":0.5},
    "Ice":{"Grass":2,"Ground":2,"Flying":2,"Dragon":2,"Water":0.5,"Ice":0.5},
    "Fighting":{"Normal":2,"Ice":2,"Rock":2,"Poison":0.5,"Flying":0.5,"Psychic":0.5,"Bug":0.5,"Ghost":0},
    "Poison":{"Grass":2,"Bug":2,"Poison":0.5,"Ground":0.5,"Rock":0.5,"Ghost":0.5},
    "Ground":{"Fire":2,"Electric":2,"Poison":2,"Rock":2,"Grass":0.5,"Bug":0.5,"Flying":0},
    "Flying":{"Grass":2,"Fighting":2,"Bug":2,"Electric":0.5,"Rock":0.5},
    "Psychic":{"Fighting":2,"Poison":2,"Psychic":0.5},
    "Bug":{"Grass":2,"Poison":2,"Psychic":2,"Fire":0.5,"Fighting":0.5,"Flying":0.5,"Ghost":0.5},
    "Rock":{"Fire":2,"Ice":2,"Flying":2,"Bug":2,"Fighting":0.5,"Ground":0.5},
    "Ghost":{"Ghost":2,"Normal":0,"Psychic":0},
    "Dragon":{"Dragon":2},
}

PHYSICAL_TYPES={"Normal","Fighting","Flying","Poison","Ground","Rock","Bug","Ghost"}


def species_stage(species_id:int)->int:
    """0 base/sin evolución, 1 intermedio, 2 final; usado solo para balance PiBot."""
    # Si es destino de otra evolución cuenta como evolucionado.
    parents={v[1] for v in LEVEL_EVOLUTIONS.values()} | {v for d in STONE_EVOLUTIONS.values() for v in d.values()} | set(TRADE_EVOLUTIONS.values())
    children=set(LEVEL_EVOLUTIONS) | set(STONE_EVOLUTIONS) | set(TRADE_EVOLUTIONS)
    if species_id not in parents:return 0
    if species_id in children:return 1
    return 2


def battle_base_stats(species_id:int)->dict:
    """Stats ligeros y deterministas para PiBot, escalados por etapa/rareza.

    Los tipos/evoluciones/movimientos son de Kanto; los valores numéricos se
    compactan para que el PvP funcione bien en Telegram sin una ROM/servidor de
    simulación completo.
    """
    stage=species_stage(species_id); r=rarity_for(species_id); ri={"comun":0,"raro":1,"epico":2,"legendario":3}[r]
    seed=species_id
    return {
        "hp":42+stage*16+ri*8+(seed*7%13),
        "atk":44+stage*13+ri*7+(seed*11%15),
        "def":42+stage*12+ri*7+(seed*13%15),
        "spc":44+stage*13+ri*8+(seed*17%15),
        "spd":40+stage*11+ri*7+(seed*19%19),
    }


def available_moves(species_id:int,level:int)->list[str]:
    rows=SPECIAL_LEARNSETS.get(species_id)
    if rows is None:
        rows=[]
        # Un movimiento normal asegura que cualquier Pokémon pueda pelear.
        rows.extend([(1,"tackle"),(12,"quick_attack"),(28,"body_slam")])
        for tp in TYPES.get(species_id,("Normal",)):
            rows.extend(TYPE_MOVESETS.get(tp,[]))
    learned=[]
    for req,code in sorted(rows,key=lambda x:(x[0],x[1])):
        if req<=level and code in MOVES and code not in learned: learned.append(code)
    # Si solo tiene movimientos no ofensivos, Struggle se representa con Placaje.
    if not learned: learned=["tackle"]
    # Conserva los cuatro más recientes/apropiados.
    return learned[-4:]


def effectiveness(move_type:str,target_types:tuple[str,...])->float:
    mult=1.0
    row=TYPE_CHART.get(move_type,{})
    for t in target_types: mult*=float(row.get(t,1.0))
    return mult


def rarity_emoji(rarity:str)->str:
    return {"comun":"⚪","raro":"🔵","epico":"💜","legendario":"🌟"}.get(rarity,"⚪")


def type_emoji(tp:str)->str:
    return {"Fire":"🔥","Water":"💧","Grass":"🍃","Electric":"⚡","Psychic":"🔮","Ice":"❄️","Fighting":"🥊","Poison":"☠️","Ground":"🟤","Rock":"🪨","Flying":"🪽","Bug":"🐛","Ghost":"👻","Dragon":"🐉","Normal":"⚪"}.get(tp,"▫️")


# MT de la Primera Generación disponibles en las cajas de PiBot.
# Solo se incluyen movimientos que ya están soportados por el motor de batalla.
TM_ITEMS = {
    "tm06": ("MT06", "Tóxico", "toxic"),
    "tm08": ("MT08", "Golpe Cuerpo", "body_slam"),
    "tm11": ("MT11", "Rayo Burbuja", "bubble_beam"),
    "tm12": ("MT12", "Pistola Agua", "water_gun"),
    "tm13": ("MT13", "Rayo Hielo", "ice_beam"),
    "tm14": ("MT14", "Ventisca", "blizzard"),
    "tm15": ("MT15", "Hiperrayo", "hyper_beam"),
    "tm17": ("MT17", "Sumisión", "submission"),
    "tm19": ("MT19", "Mov. Sísmico", "seismic_toss"),
    "tm21": ("MT21", "Megaagotar", "mega_drain"),
    "tm22": ("MT22", "Rayo Solar", "solar_beam"),
    "tm24": ("MT24", "Rayo", "thunderbolt"),
    "tm25": ("MT25", "Trueno", "thunder"),
    "tm26": ("MT26", "Terremoto", "earthquake"),
    "tm28": ("MT28", "Excavar", "dig"),
    "tm29": ("MT29", "Psíquico", "psychic"),
    "tm30": ("MT30", "Teletransporte", "teleport"),
    "tm35": ("MT35", "Metrónomo", "metronome"),
    "tm38": ("MT38", "Llamarada", "fire_blast"),
    "tm39": ("MT39", "Rapidez", "swift"),
    "tm42": ("MT42", "Comesueños", "dream_eater"),
    "tm45": ("MT45", "Onda Trueno", "thunder_wave"),
    "tm48": ("MT48", "Avalancha", "rock_slide"),
}

# Las MT son consumibles. La compatibilidad se mantiene conservadora por tipo/
# familia para no permitir combinaciones absurdas dentro del PvP.
for _code, (_tm, _name, _move) in TM_ITEMS.items():
    ITEMS[_code] = (f"{_tm} · {_name}", "📀", 0, "tm")

_TM_TYPE_COMPAT = {
    "toxic": {"Normal","Fire","Water","Grass","Electric","Ice","Fighting","Poison","Ground","Flying","Psychic","Bug","Rock","Ghost","Dragon"},
    "body_slam": {"Normal","Water","Fighting","Ground","Rock","Dragon"},
    "bubble_beam": {"Water","Ice"},
    "water_gun": {"Water","Ice"},
    "ice_beam": {"Water","Ice","Psychic","Dragon"},
    "blizzard": {"Water","Ice","Psychic","Dragon"},
    "hyper_beam": {"Normal","Fire","Water","Grass","Electric","Ice","Fighting","Poison","Ground","Flying","Psychic","Bug","Rock","Ghost","Dragon"},
    "submission": {"Fighting","Normal","Ground","Rock"},
    "seismic_toss": {"Fighting","Normal","Ground","Rock"},
    "mega_drain": {"Grass","Poison","Bug"},
    "solar_beam": {"Grass","Poison"},
    "thunderbolt": {"Electric","Normal","Psychic"},
    "thunder": {"Electric","Normal","Psychic"},
    "earthquake": {"Ground","Rock","Fighting","Normal","Dragon"},
    "dig": {"Ground","Rock","Fighting","Normal"},
    "psychic": {"Psychic","Ghost"},
    "teleport": {"Psychic"},
    "metronome": {"Normal","Psychic"},
    "fire_blast": {"Fire","Dragon"},
    "swift": {"Normal","Electric","Psychic","Flying"},
    "dream_eater": {"Psychic","Ghost"},
    "thunder_wave": {"Electric","Psychic","Normal"},
    "rock_slide": {"Rock","Ground","Fighting"},
}

def can_learn_tm(species_id:int, move_code:str)->bool:
    if move_code not in MOVES:
        return False
    types=set(TYPES.get(int(species_id),("Normal",)))
    allowed=_TM_TYPE_COMPAT.get(move_code)
    if not allowed:
        return False
    # Hiperrayo se reserva a Pokémon evolucionados/finales, legendarios o
    # especies sin evolución que ya son fuertes por diseño.
    if move_code=="hyper_beam":
        return species_stage(int(species_id))>=2 or int(species_id) in LEGENDARY_IDS or int(species_id) in {113,115,123,124,125,126,127,128,131,132,137,142,143}
    return bool(types & allowed)
