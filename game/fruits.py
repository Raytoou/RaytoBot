"""
Système des Fruits du Démon : un seul Fruit actif à la fois par joueur.
En manger un nouveau remplace l'ancien (perd son bonus précédent).
Chaque Fruit donne un bonus passif (stats) + une action active utilisable
en combat (PvP et PvE), via la clé 'special_action' résolue dans combat.py/pve.py.
"""
import random

# Catégories : 'Logia', 'Zoan', 'Paramecia'
DEVIL_FRUITS = {
    "mera_mera": {
        "name": "Mera Mera no Mi",
        "category": "Logia",
        "emoji": "🔥",
        "description": "Permet de générer, contrôler et devenir du feu.",
        "passive": {"attack": 12, "defense": 0, "dodge_chance": 0.08},
        "special_action": {
            "id": "fire_blast",
            "label": "🔥 Brasier",
            "description": "Inflige de lourds dégâts de feu, ignore une partie de la défense adverse.",
            "damage_mult": 1.8,
            "cooldown": 2,
        },
        "min_level": 6,
    },
    "hie_hie": {
        "name": "Hie Hie no Mi",
        "category": "Logia",
        "emoji": "❄️",
        "description": "Permet de générer, contrôler et devenir de la glace.",
        "passive": {"attack": 6, "defense": 8, "dodge_chance": 0.05},
        "special_action": {
            "id": "ice_age",
            "label": "❄️ Ère Glaciaire",
            "description": "Gèle l'adversaire : réduit fortement ses dégâts au prochain tour.",
            "freeze_reduction": 0.6,
            "cooldown": 3,
        },
        "min_level": 8,
    },
    "gomu_gomu": {
        "name": "Gomu Gomu no Mi",
        "category": "Paramecia (Zoan Mythique)",
        "emoji": "🟣",
        "description": "Transforme le corps en caoutchouc.",
        "passive": {"attack": 8, "defense": 4, "dodge_chance": 0.04},
        "special_action": {
            "id": "gear_punch",
            "label": "🟣 Gear Second",
            "description": "Accélère le corps pour un assaut rapide à dégâts élevés.",
            "damage_mult": 1.6,
            "cooldown": 2,
        },
        "min_level": 5,
    },
    "yami_yami": {
        "name": "Yami Yami no Mi",
        "category": "Logia",
        "emoji": "🌑",
        "description": "Permet de contrôler les ténèbres et d'annuler le Haki adverse.",
        "passive": {"attack": 10, "defense": 6, "dodge_chance": 0.0},
        "special_action": {
            "id": "black_hole",
            "label": "🌑 Trou Noir",
            "description": "Annule le bonus de Haki de l'adversaire pour ce tour et inflige des dégâts.",
            "damage_mult": 1.3,
            "nullify_haki": True,
            "cooldown": 3,
        },
        "min_level": 15,
    },
    "ope_ope": {
        "name": "Ope Ope no Mi",
        "category": "Paramecia",
        "emoji": "🔵",
        "description": "Crée une 'Room' permettant de manipuler tout ce qui s'y trouve.",
        "passive": {"attack": 2, "defense": 2, "dodge_chance": 0.10},
        "special_action": {
            "id": "shambles",
            "label": "🔵 Shambles",
            "description": "Échange ta position avec l'adversaire, garantissant une esquive totale ce tour.",
            "guaranteed_dodge": True,
            "cooldown": 3,
        },
        "min_level": 10,
    },
    "zou_zou_neko": {
        "name": "Neko Neko no Mi: Modèle Léopard",
        "category": "Zoan",
        "emoji": "🐆",
        "description": "Transforme le corps en léopard, hybride ou forme complète.",
        "passive": {"attack": 9, "defense": 5, "dodge_chance": 0.06},
        "special_action": {
            "id": "beast_claw",
            "label": "🐆 Griffe Bestiale",
            "description": "Attaque rapide en forme hybride, double chance de toucher deux fois.",
            "damage_mult": 1.2,
            "double_hit_chance": 0.5,
            "cooldown": 2,
        },
        "min_level": 7,
    },
    "magu_magu": {
        "name": "Magu Magu no Mi",
        "category": "Logia",
        "emoji": "🌋",
        "description": "Permet de générer, contrôler et devenir du magma, supérieur au feu.",
        "passive": {"attack": 15, "defense": 4, "dodge_chance": 0.05},
        "special_action": {
            "id": "great_eruption",
            "label": "🌋 Grande Éruption",
            "description": "Déclenche une explosion de magma dévastatrice.",
            "damage_mult": 2.0,
            "cooldown": 4,
        },
        "min_level": 18,
    },
}


def eligible_fruits(player_level: int) -> list[str]:
    """Liste des clés de Fruits que le joueur peut trouver/manger à son niveau."""
    return [key for key, f in DEVIL_FRUITS.items() if f["min_level"] <= player_level]


def get_fruit(fruit_key: str) -> dict | None:
    return DEVIL_FRUITS.get(fruit_key)


def random_fruit_for_level(player_level: int) -> str | None:
    """Tire un Fruit du Démon aléatoire accessible au niveau du joueur."""
    pool = eligible_fruits(player_level)
    if not pool:
        return None
    return random.choice(pool)


def eat_fruit(player: dict, fruit_key: str) -> tuple[bool, str]:
    """Fait manger un Fruit au joueur. Remplace le Fruit déjà actif s'il y en a un."""
    fruit = get_fruit(fruit_key)
    if not fruit:
        return False, "❌ Ce Fruit du Démon n'existe pas."

    previous = player.get("devil_fruit")
    player["devil_fruit"] = fruit_key
    # Réinitialise le cooldown de l'action spéciale à chaque nouveau Fruit mangé
    player["devil_fruit_cooldown"] = 0

    if previous and previous != fruit_key:
        old_fruit = get_fruit(previous)
        old_name = old_fruit["name"] if old_fruit else previous
        return True, (
            f"☠️ En mangeant le **{fruit['name']}**, tu perds les pouvoirs du **{old_name}** "
            f"(un corps ne peut contenir qu'un seul Fruit du Démon) !"
        )
    return True, f"{fruit['emoji']} Tu manges le **{fruit['name']}** ! Tes pouvoirs s'éveillent..."


def fruit_passive_bonus(player: dict) -> dict:
    """Renvoie le bonus de stats passif du Fruit actif du joueur, ou un bonus nul."""
    key = player.get("devil_fruit")
    if not key:
        return {"attack": 0, "defense": 0, "dodge_chance": 0.0}
    fruit = get_fruit(key)
    if not fruit:
        return {"attack": 0, "defense": 0, "dodge_chance": 0.0}
    return fruit["passive"]


def get_special_action(player: dict) -> dict | None:
    """Renvoie la définition de l'action spéciale du Fruit actif, ou None."""
    key = player.get("devil_fruit")
    if not key:
        return None
    fruit = get_fruit(key)
    if not fruit:
        return None
    return fruit["special_action"]


def special_action_ready(player: dict) -> bool:
    """Vérifie si l'action spéciale du Fruit actif est disponible (cooldown écoulé)."""
    return player.get("devil_fruit_cooldown", 0) <= 0


def trigger_special_action_cooldown(player: dict):
    """Met l'action spéciale en cooldown après utilisation."""
    action = get_special_action(player)
    if action:
        player["devil_fruit_cooldown"] = action.get("cooldown", 2)


def tick_cooldown(player: dict):
    """Décrémente le cooldown d'un cran (à appeler une fois par tour de combat)."""
    if player.get("devil_fruit_cooldown", 0) > 0:
        player["devil_fruit_cooldown"] -= 1


def fruit_summary(player: dict) -> str:
    key = player.get("devil_fruit")
    if not key:
        return "Aucun Fruit du Démon mangé pour l'instant."
    fruit = get_fruit(key)
    if not fruit:
        return "Fruit du Démon inconnu (donnée corrompue)."
    action = fruit["special_action"]
    return (
        f"{fruit['emoji']} **{fruit['name']}** ({fruit['category']})\n"
        f"_{fruit['description']}_\n\n"
        f"**Bonus passif** : +{fruit['passive']['attack']} attaque, "
        f"+{fruit['passive']['defense']} défense, "
        f"+{int(fruit['passive']['dodge_chance']*100)}% esquive\n"
        f"**Action active** : {action['label']} — {action['description']}"
    )
