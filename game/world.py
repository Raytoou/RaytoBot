"""
Carte du monde : mers, îles, Log Pose, et emplacements des Poneglyphes.
"""
import random

# Ordre de progression des mers (Grand Line + New World à la fin)
SEA_ORDER = ["East Blue", "Grand Line", "New World"]

# Îles regroupées par mer, avec un niveau recommandé indicatif
ISLANDS = {
    "East Blue": [
        {"name": "Fuchsia Village", "min_level": 1},
        {"name": "Shells Town", "min_level": 1},
        {"name": "Orange Town", "min_level": 1},
        {"name": "Syrup Village", "min_level": 2},
        {"name": "Baratie", "min_level": 2},
        {"name": "Arlong Park", "min_level": 3},
        {"name": "Loguetown", "min_level": 4},
    ],
    "Grand Line": [
        {"name": "Reverse Mountain", "min_level": 5},
        {"name": "Whisky Peak", "min_level": 5},
        {"name": "Little Garden", "min_level": 6},
        {"name": "Drum Island", "min_level": 7},
        {"name": "Alabasta", "min_level": 8},
        {"name": "Skypiea", "min_level": 9},
        {"name": "Water 7", "min_level": 10},
        {"name": "Enies Lobby", "min_level": 11},
        {"name": "Thriller Bark", "min_level": 12},
        {"name": "Sabaody Archipelago", "min_level": 13},
        {"name": "Marineford", "min_level": 15},
    ],
    "New World": [
        {"name": "Fish-Man Island", "min_level": 16},
        {"name": "Punk Hazard", "min_level": 17},
        {"name": "Dressrosa", "min_level": 18},
        {"name": "Zou", "min_level": 19},
        {"name": "Whole Cake Island", "min_level": 20},
        {"name": "Wano Country", "min_level": 22},
        {"name": "Laugh Tale", "min_level": 25},
    ],
}

# Poneglyphes cachés sur certaines îles spécifiques (clé = nom de l'île)
PONEGLYPH_LOCATIONS = {
    "Little Garden": "Poneglyphe de l'Histoire Oubliée",
    "Alabasta": "Poneglyphe d'Alabasta (Arme Antique)",
    "Skypiea": "Poneglyphe de Shandora",
    "Zou": "Poneglyphe de Zou (Road Poneglyph)",
    "Whole Cake Island": "Poneglyphe de Totto Land (Road Poneglyph)",
    "Wano Country": "Poneglyphe de Wano (Road Poneglyph)",
    "Laugh Tale": "Poneglyphe Final — Rio Poneglyph",
}


def get_island(name: str) -> dict | None:
    for sea, islands in ISLANDS.items():
        for island in islands:
            if island["name"] == name:
                return {**island, "sea": sea}
    return None


def islands_in_sea(sea: str) -> list[dict]:
    return ISLANDS.get(sea, [])


def random_island(sea: str, max_level: int | None = None, exclude: list[str] | None = None) -> dict | None:
    """Tire une île au hasard dans la mer donnée. Retourne None si aucune île
    ne correspond aux critères (toutes exclues, par exemple)."""
    pool = ISLANDS.get(sea, [])
    if max_level is not None:
        filtered = [i for i in pool if i["min_level"] <= max_level]
        pool = filtered or pool
    if exclude:
        pool = [i for i in pool if i["name"] not in exclude]
    if not pool:
        return None
    return random.choice(pool)


def set_log_pose(player: dict) -> str:
    """Définit une destination aléatoire pour le Log Pose, dans la mer actuelle
    ou la suivante si le joueur est assez fort. Ne propose jamais une île déjà
    visitée par le joueur, sauf si vraiment toutes les îles atteignables ont
    déjà été visitées (sinon le Log Pose ne pourrait plus jamais se régler)."""
    current_sea = player["current_sea"]
    sea_index = SEA_ORDER.index(current_sea)
    visited = player.get("visited_islands", [])

    can_advance = False
    if sea_index < len(SEA_ORDER) - 1:
        next_sea = SEA_ORDER[sea_index + 1]
        next_sea_min_level = min(i["min_level"] for i in ISLANDS[next_sea])
        can_advance = player["level"] >= next_sea_min_level

    if can_advance and random.random() < 0.3:
        target_sea = SEA_ORDER[sea_index + 1]
    else:
        target_sea = current_sea

    max_level = player["level"] + 3

    # 1. Île non-visitée dans la mer ciblée
    destination = random_island(target_sea, max_level=max_level, exclude=visited)
    # 2. Repli : île non-visitée dans la mer actuelle (si la mer suivante était épuisée)
    if not destination and target_sea != current_sea:
        destination = random_island(current_sea, max_level=max_level, exclude=visited)
    # 3. Repli : île non-visitée dans n'importe quelle mer déjà accessible
    if not destination:
        for sea in SEA_ORDER[:sea_index + 1]:
            destination = random_island(sea, max_level=max_level, exclude=visited)
            if destination:
                break
    # 4. Dernier recours : tout est visité, on autorise un retour (le joueur
    #    a fini d'explorer ce qui est à sa portée, mieux vaut le laisser
    #    naviguer que de bloquer le Log Pose indéfiniment)
    if not destination:
        destination = random_island(target_sea, max_level=max_level)

    player["log_pose_set"] = True
    player["log_pose_destination"] = destination["name"]
    return destination["name"]


def travel_to_destination(player: dict) -> str | None:
    """Déplace le joueur vers la destination du Log Pose, si défini."""
    if not player["log_pose_set"] or not player["log_pose_destination"]:
        return None
    destination_name = player["log_pose_destination"]
    island = get_island(destination_name)
    if not island:
        return None
    player["current_island"] = destination_name
    player["current_sea"] = island["sea"]
    player["log_pose_set"] = False
    player["log_pose_destination"] = None
    if destination_name not in player.setdefault("visited_islands", []):
        player["visited_islands"].append(destination_name)
    return destination_name


def check_poneglyph(player: dict) -> str | None:
    """Vérifie si l'île actuelle contient un Poneglyphe non encore trouvé par le joueur."""
    island_name = player["current_island"]
    if island_name not in PONEGLYPH_LOCATIONS:
        return None
    if island_name in player["poneglyphs_found"]:
        return None
    poneglyph_name = PONEGLYPH_LOCATIONS[island_name]
    player["poneglyphs_found"].append(island_name)
    return poneglyph_name