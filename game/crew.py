"""
Système d'équipage : création, rejoindre/quitter, affichage.
"""
from . import data


def get_player_crew(player: dict) -> dict | None:
    if not player.get("crew_id"):
        return None
    return data.get_crew(player["crew_id"])


def create_crew(player: dict, crew_name: str) -> tuple[bool, str]:
    if player.get("crew_id"):
        return False, "❌ Tu fais déjà partie d'un équipage. Quitte-le d'abord avec `/equipage_quitter`."
    crew = data.create_crew(crew_name, player["id"])
    player["crew_id"] = crew["id"]
    data.update_player(player)
    return True, f"🏴‍☠️ L'équipage **{crew_name}** a été créé ! Tu en es le capitaine."


def join_crew(player: dict, crew_id: str) -> tuple[bool, str]:
    if player.get("crew_id"):
        return False, "❌ Tu fais déjà partie d'un équipage. Quitte-le d'abord avec `/equipage_quitter`."
    crew = data.get_crew(crew_id)
    if not crew:
        return False, "❌ Cet équipage n'existe pas."
    if player["id"] in crew["members"]:
        return False, "❌ Tu es déjà membre de cet équipage."
    crew["members"].append(player["id"])
    player["crew_id"] = crew["id"]
    data.update_crew(crew)
    data.update_player(player)
    return True, f"🏴‍☠️ Tu as rejoint l'équipage **{crew['name']}** !"


def leave_crew(player: dict) -> tuple[bool, str]:
    crew = get_player_crew(player)
    if not crew:
        return False, "❌ Tu ne fais partie d'aucun équipage."

    crew["members"].remove(player["id"])
    player["crew_id"] = None

    if not crew["members"]:
        # Équipage vide, on le supprime
        data._state["crews"].pop(str(crew["id"]), None)
        data.save()
    else:
        if crew["captain"] == player["id"]:
            crew["captain"] = crew["members"][0]  # transfert automatique du capitanat
        data.update_crew(crew)

    data.update_player(player)
    return True, "👋 Tu as quitté ton équipage."


def crew_summary(crew: dict) -> str:
    members_lines = []
    for member_id in crew["members"]:
        p = data.get_player(member_id)
        role = "👑 Capitaine" if member_id == crew["captain"] else "⚓ Membre"
        members_lines.append(f"{role} — {p['name']} (Niv. {p['level']})")
    return (
        f"🏴‍☠️ **Équipage : {crew['name']}** (ID `{crew['id']}`)\n\n"
        + "\n".join(members_lines)
    )
