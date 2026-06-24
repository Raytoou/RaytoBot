"""
Système d'exploration : le joueur explore son île actuelle pour gagner
XP, Berrys, objets, potentiellement trouver un Poneglyphe ou un Fruit du
Démon, ou tomber sur une rencontre hostile (Marine, pirate rival, monstre
marin...).
"""
import random

from . import data, world, progression, enemies, fruits

EXPLORE_COOLDOWN_SECONDS = 60  # anti-spam simple
ENCOUNTER_CHANCE = 0.35  # probabilité de tomber sur un PNJ hostile
DEVIL_FRUIT_CHANCE = 0.04  # probabilité de trouver un Fruit du Démon (rare)

EVENTS = [
    ("🐗 Tu chasses un sanglier sauvage et le revends.", 10, 30),
    ("💰 Tu trouves un petit coffre enterré.", 20, 60),
    ("🍖 Un habitant te remercie pour un service rendu.", 5, 25),
    ("⚓ Tu répares un bateau abandonné et le revends.", 15, 45),
]

ITEMS_FOUND = [
    "Carte au trésor déchirée",
    "Sabre rouillé",
    "Fragment de Vivre Card",
    "Bouteille de saké d'Wano",
]


def explore(player: dict) -> dict:
    """Fait explorer le joueur. Retourne un dict décrivant le résultat
    (pour affichage), et applique les changements sur le joueur.
    Peut retourner une 'rencontre' (encounter=True) au lieu d'un butin
    classique : dans ce cas, c'est à l'appelant de lancer le combat PvE."""
    now = data.now()
    remaining = player["cooldown_until"] - now
    if remaining > 0:
        return {"on_cooldown": True, "remaining": remaining}

    player["cooldown_until"] = now + EXPLORE_COOLDOWN_SECONDS

    if random.random() < ENCOUNTER_CHANCE:
        enemy = enemies.spawn_enemy(player["level"])
        data.update_player(player)  # sauvegarde le cooldown même en cas de rencontre
        return {"on_cooldown": False, "encounter": True, "enemy": enemy}

    event_text, xp_min, xp_max = random.choice(EVENTS)
    xp_gain = random.randint(xp_min, xp_max)
    berrys_gain = random.randint(xp_min, xp_max) * 2

    player["xp"] += xp_gain
    player["berrys"] += berrys_gain

    found_item = None
    found_fruit_key = None

    if random.random() < DEVIL_FRUIT_CHANCE:
        eligible = fruits.eligible_fruits(player["level"])
        if eligible:
            found_fruit_key = random.choice(eligible)
            player["inventory"].append(f"devil_fruit:{found_fruit_key}")
    elif random.random() < 0.15:
        found_item = random.choice(ITEMS_FOUND)
        player["inventory"].append(found_item)

    poneglyph = world.check_poneglyph(player)
    levelup_msg = progression.apply_xp_and_levelup(player)

    data.update_player(player)

    return {
        "on_cooldown": False,
        "encounter": False,
        "event_text": event_text,
        "xp_gain": xp_gain,
        "berrys_gain": berrys_gain,
        "found_item": found_item,
        "found_fruit_key": found_fruit_key,
        "poneglyph": poneglyph,
        "levelup_msg": levelup_msg,
    }