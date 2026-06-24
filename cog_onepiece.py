"""
Cog Discord regroupant toutes les commandes du mini-jeu One Piece.
À brancher sur le bot principal via : await bot.add_cog(OnePieceGame(bot))
"""
import discord
from discord import app_commands
from discord.ext import commands

from game import data, haki, world, combat, progression, explore, crew, pve, fruits, bounty


class OnePieceGame(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # Personnage
    # ------------------------------------------------------------------

    @app_commands.command(name="personnage", description="Affiche ta fiche de pirate (ou celle d'un autre joueur).")
    @app_commands.describe(membre="Le membre dont tu veux voir la fiche (optionnel)")
    async def personnage(self, interaction: discord.Interaction, membre: discord.Member = None):
        target = membre or interaction.user
        player = data.get_player(target.id, target.display_name)

        current_bounty = bounty.refresh_bounty(player)
        data.update_player(player)

        embed = discord.Embed(
            title=f"🏴‍☠️ Fiche de {player['name']}",
            description=f"{bounty.bounty_title(current_bounty)} — Prime : **{bounty.format_bounty(current_bounty)}**",
            color=discord.Color.blue()
        )
        embed.add_field(name="Niveau", value=str(player["level"]), inline=True)
        embed.add_field(name="XP", value=f"{player['xp']}/{progression.xp_required_for_level(player['level'])}", inline=True)
        embed.add_field(name="Berrys", value=f"{player['berrys']} 💰", inline=True)
        embed.add_field(name="PV", value=f"{player['hp']}/{player['hp_max']}", inline=True)
        embed.add_field(name="Île actuelle", value=f"{player['current_island']} ({player['current_sea']})", inline=True)
        embed.add_field(name="Victoires / Défaites", value=f"{player['wins']} / {player['losses']}", inline=True)
        embed.add_field(name="Haki", value=haki.haki_summary(player), inline=False)
        embed.add_field(name="Fruit du Démon", value=fruits.fruit_summary(player), inline=False)

        crew_obj = crew.get_player_crew(player)
        embed.add_field(name="Équipage", value=crew_obj["name"] if crew_obj else "Aucun (solitaire)", inline=False)

        if player["poneglyphs_found"]:
            embed.add_field(
                name=f"Poneglyphes trouvés ({len(player['poneglyphs_found'])})",
                value="\n".join(f"📜 {island}" for island in player["poneglyphs_found"]),
                inline=False
            )

        if target.display_avatar:
            embed.set_thumbnail(url=target.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # Exploration
    # ------------------------------------------------------------------

    @app_commands.command(name="explorer", description="Explore l'île où tu te trouves pour gagner XP, Berrys et objets.")
    async def explorer(self, interaction: discord.Interaction):
        player = data.get_player(interaction.user.id, interaction.user.display_name)
        result = explore.explore(player)

        if result["on_cooldown"]:
            await interaction.response.send_message(
                f"⏳ Tu dois encore attendre {result['remaining']}s avant de pouvoir explorer à nouveau.",
                ephemeral=True
            )
            return

        if result["encounter"]:
            enemy = result["enemy"]
            view = pve.PveCombatView(interaction.user.id, enemy)
            embed = view.build_embed()
            await interaction.response.send_message(embed=embed, view=view)
            view.message = await interaction.original_response()
            return

        embed = discord.Embed(
            title=f"🗺️ Exploration de {player['current_island']}",
            description=result["event_text"],
            color=discord.Color.green()
        )
        embed.add_field(name="XP gagnée", value=f"+{result['xp_gain']} ✨", inline=True)
        embed.add_field(name="Berrys gagnés", value=f"+{result['berrys_gain']} 💰", inline=True)

        if result["found_item"]:
            embed.add_field(name="Objet trouvé !", value=f"🎁 {result['found_item']}", inline=False)
        if result.get("found_fruit_key"):
            fruit = fruits.get_fruit(result["found_fruit_key"])
            embed.add_field(
                name="🍈 Fruit du Démon découvert !",
                value=f"{fruit['emoji']} **{fruit['name']}** ({fruit['category']})\nUtilise `/manger_fruit` pour l'identifier précisément et le consommer.",
                inline=False
            )
        if result["poneglyph"]:
            embed.add_field(name="📜 Poneglyphe découvert !", value=result["poneglyph"], inline=False)
        if result["levelup_msg"]:
            embed.add_field(name="Progression", value=result["levelup_msg"], inline=False)

        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # Log Pose / déplacement
    # ------------------------------------------------------------------

    @app_commands.command(name="logpose", description="Active ton Log Pose pour viser une nouvelle île.")
    async def logpose(self, interaction: discord.Interaction):
        player = data.get_player(interaction.user.id, interaction.user.display_name)

        if player["log_pose_set"]:
            await interaction.response.send_message(
                f"🧭 Ton Log Pose pointe déjà vers **{player['log_pose_destination']}**. "
                f"Utilise `/naviguer` pour t'y rendre.",
                ephemeral=True
            )
            return

        destination = world.set_log_pose(player)
        data.update_player(player)
        await interaction.response.send_message(
            f"🧭 Ton Log Pose s'est fixé ! Direction : **{destination}**.\nUtilise `/naviguer` pour y aller."
        )

    @app_commands.command(name="naviguer", description="Navigue vers la destination de ton Log Pose.")
    async def naviguer(self, interaction: discord.Interaction):
        player = data.get_player(interaction.user.id, interaction.user.display_name)
        destination = world.travel_to_destination(player)

        if not destination:
            await interaction.response.send_message(
                "❌ Ton Log Pose n'est pas réglé. Utilise `/logpose` d'abord.",
                ephemeral=True
            )
            return

        data.update_player(player)
        await interaction.response.send_message(
            f"⛵ Tu navigues à travers les flots... Tu arrives à **{destination}** ({player['current_sea']}) !"
        )

    @app_commands.command(name="carte", description="Affiche la carte des mers et îles du jeu.")
    async def carte(self, interaction: discord.Interaction):
        player = data.get_player(interaction.user.id, interaction.user.display_name)
        embed = discord.Embed(title="🗺️ Carte du Monde", color=discord.Color.teal())
        for sea in world.SEA_ORDER:
            islands = world.islands_in_sea(sea)
            lines = []
            for island in islands:
                marker = "📍" if island["name"] == player["current_island"] else "•"
                poneglyph_marker = " 📜" if island["name"] in world.PONEGLYPH_LOCATIONS else ""
                lines.append(f"{marker} {island['name']} (Niv. {island['min_level']}+){poneglyph_marker}")
            embed.add_field(name=sea, value="\n".join(lines), inline=False)
        embed.set_footer(text="📍 = ta position actuelle · 📜 = île avec Poneglyphe")
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # Combat PvP
    # ------------------------------------------------------------------

    @app_commands.command(name="combat", description="Défie un autre pirate en duel, avec mise de Berrys.")
    @app_commands.describe(adversaire="Le membre à défier", mise="Montant de Berrys misés (les deux joueurs doivent l'avoir)")
    async def combat_cmd(self, interaction: discord.Interaction, adversaire: discord.Member, mise: app_commands.Range[int, 0, 100000] = 0):
        if adversaire.id == interaction.user.id:
            await interaction.response.send_message("❌ Tu ne peux pas te défier toi-même.", ephemeral=True)
            return
        if adversaire.bot:
            await interaction.response.send_message("❌ Tu ne peux pas défier un bot.", ephemeral=True)
            return

        challenger = data.get_player(interaction.user.id, interaction.user.display_name)
        opponent = data.get_player(adversaire.id, adversaire.display_name)

        if challenger["berrys"] < mise:
            await interaction.response.send_message("❌ Tu n'as pas assez de Berrys pour cette mise.", ephemeral=True)
            return
        if opponent["berrys"] < mise:
            await interaction.response.send_message(
                f"❌ {adversaire.display_name} n'a pas assez de Berrys pour cette mise.",
                ephemeral=True
            )
            return

        view = combat.CombatView(interaction.user.id, adversaire.id, mise)
        embed = view.build_embed()
        embed.description = f"⚔️ {interaction.user.display_name} défie {adversaire.display_name} en duel !\n💰 Mise : {mise} Berrys"

        await interaction.response.send_message(
            content=f"{adversaire.mention}, tu es défié(e) !",
            embed=embed,
            view=view
        )
        view.message = await interaction.original_response()

    # ------------------------------------------------------------------
    # Équipage
    # ------------------------------------------------------------------

    @app_commands.command(name="equipage_creer", description="Crée ton propre équipage de pirates.")
    @app_commands.describe(nom="Nom de l'équipage")
    async def equipage_creer(self, interaction: discord.Interaction, nom: str):
        player = data.get_player(interaction.user.id, interaction.user.display_name)
        success, message = crew.create_crew(player, nom)
        await interaction.response.send_message(message, ephemeral=not success)

    @app_commands.command(name="equipage_rejoindre", description="Rejoint un équipage existant via son ID.")
    @app_commands.describe(equipage_id="L'ID de l'équipage à rejoindre (visible via /equipage_info)")
    async def equipage_rejoindre(self, interaction: discord.Interaction, equipage_id: str):
        player = data.get_player(interaction.user.id, interaction.user.display_name)
        success, message = crew.join_crew(player, equipage_id)
        await interaction.response.send_message(message, ephemeral=not success)

    @app_commands.command(name="equipage_quitter", description="Quitte ton équipage actuel.")
    async def equipage_quitter(self, interaction: discord.Interaction):
        player = data.get_player(interaction.user.id, interaction.user.display_name)
        success, message = crew.leave_crew(player)
        await interaction.response.send_message(message, ephemeral=not success)

    @app_commands.command(name="equipage_info", description="Affiche les infos de ton équipage (ou celui d'un membre).")
    @app_commands.describe(membre="Le membre dont tu veux voir l'équipage (optionnel)")
    async def equipage_info(self, interaction: discord.Interaction, membre: discord.Member = None):
        target = membre or interaction.user
        player = data.get_player(target.id, target.display_name)
        crew_obj = crew.get_player_crew(player)

        if not crew_obj:
            await interaction.response.send_message(
                f"📭 {target.display_name} ne fait partie d'aucun équipage.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(crew.crew_summary(crew_obj))

    # ------------------------------------------------------------------
    # Haki
    # ------------------------------------------------------------------

    @app_commands.command(name="haki", description="Affiche les Hakis débloqués et les paliers requis.")
    async def haki_cmd(self, interaction: discord.Interaction):
        player = data.get_player(interaction.user.id, interaction.user.display_name)
        embed = discord.Embed(
            title=f"☯️ Haki de {player['name']}",
            description=haki.haki_summary(player),
            color=discord.Color.dark_purple()
        )
        await interaction.response.send_message(embed=embed)

    # ------------------------------------------------------------------
    # Fruits du Démon
    # ------------------------------------------------------------------

    @app_commands.command(name="inventaire", description="Affiche ton inventaire d'objets et Fruits du Démon trouvés.")
    async def inventaire(self, interaction: discord.Interaction):
        player = data.get_player(interaction.user.id, interaction.user.display_name)
        inventory = player.get("inventory", [])

        if not inventory:
            await interaction.response.send_message("📭 Ton inventaire est vide.", ephemeral=True)
            return

        fruit_lines = []
        item_lines = []
        for item in inventory:
            if item.startswith("devil_fruit:"):
                key = item.removeprefix("devil_fruit:")
                fruit = fruits.get_fruit(key)
                if fruit:
                    fruit_lines.append(f"{fruit['emoji']} **{fruit['name']}** ({fruit['category']}) — niv. min. {fruit.get('min_level', 1)}")
                else:
                    fruit_lines.append(f"🍈 Fruit inconnu (`{key}`)")
            else:
                item_lines.append(f"• {item}")

        embed = discord.Embed(
            title=f"🎒 Inventaire de {player['name']}",
            color=discord.Color.orange()
        )
        if fruit_lines:
            embed.add_field(
                name=f"🍈 Fruits du Démon ({len(fruit_lines)})",
                value="\n".join(fruit_lines),
                inline=False
            )
        if item_lines:
            embed.add_field(
                name=f"📦 Objets ({len(item_lines)})",
                value="\n".join(item_lines),
                inline=False
            )
        if fruit_lines:
            embed.set_footer(text="Utilise /manger_fruit pour consommer un Fruit du Démon.")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="manger_fruit", description="Mange un Fruit du Démon trouvé en exploration (remplace ton Fruit actuel).")
    async def manger_fruit(self, interaction: discord.Interaction):
        player = data.get_player(interaction.user.id, interaction.user.display_name)
        fruit_items = [item for item in player["inventory"] if item.startswith("devil_fruit:")]

        if not fruit_items:
            await interaction.response.send_message(
                "📭 Tu n'as aucun Fruit du Démon dans ton inventaire. Explore pour en trouver un !",
                ephemeral=True
            )
            return

        view = FruitSelectView(interaction.user.id, fruit_items)
        await interaction.response.send_message(
            "🍈 Choisis le Fruit du Démon à manger (cela remplacera ton Fruit actuel, si tu en as un) :",
            view=view,
            ephemeral=True
        )

    # ------------------------------------------------------------------
    # Prime et classement
    # ------------------------------------------------------------------

    @app_commands.command(name="prime", description="Affiche ta prime (bounty) actuelle, ou celle d'un autre joueur.")
    @app_commands.describe(membre="Le membre dont tu veux voir la prime (optionnel)")
    async def prime(self, interaction: discord.Interaction, membre: discord.Member = None):
        target = membre or interaction.user
        player = data.get_player(target.id, target.display_name)
        current_bounty = bounty.refresh_bounty(player)
        data.update_player(player)

        embed = discord.Embed(
            title=f"📰 Avis de Recherche — {player['name']}",
            description=f"{bounty.bounty_title(current_bounty)}",
            color=discord.Color.dark_gold()
        )
        embed.add_field(name="Prime", value=f"**{bounty.format_bounty(current_bounty)}**", inline=False)
        embed.add_field(name="Victoires", value=str(player["wins"]), inline=True)
        embed.add_field(name="Boss vaincus", value=str(player.get("bosses_defeated", 0)), inline=True)
        embed.add_field(name="Poneglyphes", value=str(len(player["poneglyphs_found"])), inline=True)
        if target.display_avatar:
            embed.set_thumbnail(url=target.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="classement", description="Affiche le classement des plus grandes primes du serveur.")
    async def classement(self, interaction: discord.Interaction):
        top_players = bounty.leaderboard(limit=10)

        if not top_players:
            await interaction.response.send_message("📭 Aucun pirate enregistré pour l'instant.", ephemeral=True)
            return

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, p in enumerate(top_players):
            rank = medals[i] if i < 3 else f"`#{i+1}`"
            lines.append(f"{rank} **{p['name']}** — {bounty.format_bounty(p.get('bounty', 0))}")

        embed = discord.Embed(
            title="📰 Les Pirates les Plus Recherchés",
            description="\n".join(lines),
            color=discord.Color.dark_gold()
        )
        await interaction.response.send_message(embed=embed)


class FruitSelectView(discord.ui.View):
    """Menu de sélection pour choisir quel Fruit du Démon manger parmi ceux
    trouvés en inventaire."""

    def __init__(self, user_id: int, fruit_items: list[str]):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.add_item(FruitSelect(fruit_items))


class FruitSelect(discord.ui.Select):
    def __init__(self, fruit_items: list[str]):
        options = []
        for item in fruit_items:
            fruit_key = item.removeprefix("devil_fruit:")
            fruit = fruits.get_fruit(fruit_key)
            if not fruit:
                continue
            options.append(discord.SelectOption(
                label=fruit["name"],
                description=fruit["category"],
                emoji=fruit["emoji"],
                value=item
            ))
        super().__init__(placeholder="Choisis un Fruit du Démon...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        player = data.get_player(interaction.user.id, interaction.user.display_name)
        chosen_item = self.values[0]
        fruit_key = chosen_item.removeprefix("devil_fruit:")

        if chosen_item not in player["inventory"]:
            await interaction.response.send_message(
                "❌ Ce Fruit n'est plus dans ton inventaire.", ephemeral=True
            )
            return

        player["inventory"].remove(chosen_item)
        # Les autres Fruits non mangés restent dans l'inventaire, inchangés.
        ok, message = fruits.eat_fruit(player, fruit_key)
        data.update_player(player)

        for child in self.view.children:
            child.disabled = True
        await interaction.response.edit_message(content=message, view=self.view)


async def setup(bot: commands.Bot):
    await bot.add_cog(OnePieceGame(bot))