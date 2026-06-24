"""
Système de prime (bounty) : calculée à partir des victoires PvP/PvE
cumulées, des Poneglyphes trouvés, et des boss vaincus.
"""
from . import data

BOUNTY_PER_WIN = 500
BOUNTY_PER_BOSS_DEFEATED = 2500
BOUNTY_PER_PONEGLYPH = 5000
BOUNTY_PER_LEVEL = 150


def compute_bounty(player: dict) -> int:
    """Calcule la prime actuelle du joueur à partir de ses statistiques."""
    wins = player.get("wins", 0)
    poneglyphs = len(player.get("poneglyphs_found", []))
    bosses = player.get("bosses_defeated", 0)
    level = player.get("level", 1)

    bounty = (
        wins * BOUNTY_PER_WIN
        + poneglyphs * BOUNTY_PER_PONEGLYPH
        + bosses * BOUNTY_PER_BOSS_DEFEATED
        + level * BOUNTY_PER_LEVEL
    )
    return bounty


def refresh_bounty(player: dict) -> int:
    """Recalcule et stocke la prime à jour sur le joueur. Retourne la
    nouvelle valeur (utile pour détecter une augmentation à annoncer)."""
    new_bounty = compute_bounty(player)
    player["bounty"] = new_bounty
    return new_bounty


def format_bounty(amount: int) -> str:
    """Formate un montant en Berrys à la manière des primes du manga (ex: 100.000.000 ฿)."""
    return f"{amount:,}".replace(",", ".") + " ฿"


def bounty_title(amount: int) -> str:
    """Donne un titre indicatif selon le montant de la prime, pour le fun."""
    if amount >= 1_000_000_000:
        return "👑 Empereur de la Mer"
    if amount >= 100_000_000:
        return "⭐ Légende des Mers"
    if amount >= 10_000_000:
        return "🏴‍☠️ Super Rookie"
    if amount >= 1_000_000:
        return "⚔️ Pirate redouté"
    if amount >= 100_000:
        return "🗡️ Pirate connu"
    return "🌊 Pirate débutant"


def leaderboard(limit: int = 10) -> list[dict]:
    """Retourne les meilleurs joueurs triés par prime décroissante."""
    all_players = list(data._state["players"].values())
    for p in all_players:
        refresh_bounty(p)
    ranked = sorted(all_players, key=lambda p: p.get("bounty", 0), reverse=True)
    return ranked[:limit]
