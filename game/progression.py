"""
Gestion de la progression : XP, montée de niveau, déblocage de Haki.
"""
from . import haki

XP_PER_LEVEL = 100  # XP nécessaire pour passer au niveau suivant (linéaire, simple)


def xp_required_for_level(level: int) -> int:
    return level * XP_PER_LEVEL


def apply_xp_and_levelup(player: dict) -> str | None:
    """Applique les seuils de montée de niveau et débloque le Haki si atteint.
    Retourne un message à afficher au joueur, ou None s'il n'y a rien de nouveau."""
    messages = []
    leveled_up = False

    while player["xp"] >= xp_required_for_level(player["level"]):
        player["xp"] -= xp_required_for_level(player["level"])
        player["level"] += 1
        player["hp_max"] += 10
        player["hp"] = player["hp_max"]
        leveled_up = True

    if leveled_up:
        messages.append(f"🆙 Niveau supérieur ! {player['name']} est maintenant niveau {player['level']}.")

    unlocked = haki.check_unlocks(player)
    for haki_key in unlocked:
        messages.append(f"🔓 Nouveau pouvoir débloqué : {haki.HAKI_LABELS[haki_key]} !")

    return "\n".join(messages) if messages else None
