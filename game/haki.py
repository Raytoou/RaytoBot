"""
Système de Haki : Observation, Armement, Conquérant.
Déblocage automatique selon le niveau du joueur.
"""

HAKI_UNLOCK_LEVELS = {
    "observation": 5,
    "armement": 10,
    "conquerant": 20,
}

HAKI_LABELS = {
    "observation": "👁️ Haki de l'Observation",
    "armement": "⚔️ Haki de l'Armement",
    "conquerant": "👑 Haki des Rois (Conquérant)",
}

HAKI_DESCRIPTIONS = {
    "observation": "Perçoit les intentions et la présence des adversaires. Augmente l'esquive en combat.",
    "armement": "Durcit le corps pour frapper et encaisser plus fort. Augmente l'attaque et la défense.",
    "conquerant": "Volonté de conquérant rarissime. Peut assommer les adversaires faibles instantanément.",
}


def check_unlocks(player: dict) -> list[str]:
    """Vérifie et débloque les Hakis atteints par le niveau actuel.
    Retourne la liste des clés de Haki nouvellement débloqués (pour notifier le joueur)."""
    newly_unlocked = []
    for haki_key, required_level in HAKI_UNLOCK_LEVELS.items():
        if player["level"] >= required_level and not player["haki"][haki_key]:
            player["haki"][haki_key] = True
            newly_unlocked.append(haki_key)
    return newly_unlocked


def haki_summary(player: dict) -> str:
    lines = []
    for key in ("observation", "armement", "conquerant"):
        unlocked = player["haki"][key]
        status = "✅" if unlocked else f"🔒 (niveau {HAKI_UNLOCK_LEVELS[key]} requis)"
        lines.append(f"{HAKI_LABELS[key]} — {status}")
    return "\n".join(lines)


def combat_bonus(player: dict) -> dict:
    """Calcule les bonus de combat apportés par les Hakis débloqués."""
    bonus = {"attack": 0, "defense": 0, "dodge_chance": 0.0, "instant_ko_chance": 0.0}
    if player["haki"]["observation"]:
        bonus["dodge_chance"] += 0.10
    if player["haki"]["armement"]:
        bonus["attack"] += 8
        bonus["defense"] += 5
    if player["haki"]["conquerant"]:
        bonus["instant_ko_chance"] += 0.05
    return bonus


def total_combat_bonus(player: dict) -> dict:
    """Combine le bonus de Haki et le bonus passif du Fruit du Démon actif
    (s'il y en a un) en un seul dict prêt à l'emploi pour les calculs de combat."""
    from . import fruits  # import local pour éviter une dépendance circulaire au chargement du module

    bonus = combat_bonus(player)
    fruit_bonus = fruits.fruit_passive_bonus(player)
    for key, value in fruit_bonus.items():
        bonus[key] = bonus.get(key, 0) + value
    return bonus