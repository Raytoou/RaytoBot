"""
Gestion des données persistantes du mini-jeu One Piece.
Tout est sauvegardé dans game/save_data.json (créé automatiquement).
"""
import json
import os
import time

SAVE_FILE = os.path.join(os.path.dirname(__file__), "save_data.json")

# ---------------------------------------------------------------------------
# Structure par défaut d'un joueur
# ---------------------------------------------------------------------------

def new_player(user_id: int, name: str) -> dict:
    return {
        "id": user_id,
        "name": name,
        "level": 1,
        "xp": 0,
        "berrys": 500,
        "hp_max": 100,
        "hp": 100,
        "current_island": "Fuchsia Village",
        "current_sea": "East Blue",
        "visited_islands": ["Fuchsia Village"],
        "devil_fruit": None,
        "devil_fruit_cooldown": 0,
        "log_pose_set": False,
        "log_pose_destination": None,
        "haki": {
            "observation": False,
            "armement": False,
            "conquerant": False,
        },
        "poneglyphs_found": [],
        "inventory": [],
        "crew_id": None,
        "wins": 0,
        "losses": 0,
        "bosses_defeated": 0,
        "bounty": 0,
        "last_explore": 0,
        "cooldown_until": 0,
    }


def new_crew(crew_id: str, name: str, captain_id: int) -> dict:
    return {
        "id": crew_id,
        "name": name,
        "captain": captain_id,
        "members": [captain_id],
        "bounty_total": 0,
    }


# ---------------------------------------------------------------------------
# État global en mémoire (chargé depuis le JSON au démarrage)
# ---------------------------------------------------------------------------

_state = {
    "players": {},   # str(user_id) -> dict
    "crews": {},      # crew_id -> dict
    "next_crew_id": 1,
}


def load():
    global _state
    if not os.path.exists(SAVE_FILE):
        return
    try:
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            _state["players"] = data.get("players", {})
            _state["crews"] = data.get("crews", {})
            _state["next_crew_id"] = data.get("next_crew_id", 1)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[game] Erreur chargement save_data.json : {e}")


def save():
    try:
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(_state, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"[game] Erreur sauvegarde save_data.json : {e}")


def get_player(user_id: int, name: str = "Pirate") -> dict:
    """Récupère un joueur, le crée s'il n'existe pas encore."""
    key = str(user_id)
    if key not in _state["players"]:
        _state["players"][key] = new_player(user_id, name)
        save()
    player = _state["players"][key]

    # Migration douce pour les joueurs créés avant l'ajout de ces champs
    migrated = False
    if "visited_islands" not in player:
        player["visited_islands"] = [player["current_island"]]
        migrated = True
    if "devil_fruit" not in player:
        player["devil_fruit"] = None
        player["devil_fruit_cooldown"] = 0
        migrated = True
    elif isinstance(player["devil_fruit"], str):
        # Nettoyage : supprime les espaces ou crochets parasites qui peuvent
        # venir d'une édition manuelle du JSON (ex: "mera_mera " ou "devil_fruit[mera_mera]")
        cleaned = player["devil_fruit"].strip().strip("[]").removeprefix("devil_fruit:")
        if cleaned != player["devil_fruit"]:
            player["devil_fruit"] = cleaned
            migrated = True
    if "bosses_defeated" not in player:
        player["bosses_defeated"] = 0
        migrated = True
    if "bounty" not in player:
        player["bounty"] = 0
        migrated = True
    if migrated:
        save()

    return player


def update_player(player: dict):
    _state["players"][str(player["id"])] = player
    save()


def get_crew(crew_id) -> dict | None:
    return _state["crews"].get(str(crew_id))


def create_crew(name: str, captain_id: int) -> dict:
    crew_id = str(_state["next_crew_id"])
    _state["next_crew_id"] += 1
    crew = new_crew(crew_id, name, captain_id)
    _state["crews"][crew_id] = crew
    save()
    return crew


def update_crew(crew: dict):
    _state["crews"][str(crew["id"])] = crew
    save()


def now() -> int:
    return int(time.time())


# Charge la sauvegarde dès l'import du module
load()