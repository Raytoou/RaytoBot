"""
Système de combat PvE (joueur contre PNJ), avec boutons Discord interactifs.
Inclut l'utilisation active des 3 Hakis :
- Observation : mini-jeu de prédiction de l'action ennemie avant qu'elle ne survienne.
- Armement : frappe renforcée (comme en PvP).
- Conquérant : intimidation pouvant faire fuir un ennemi faible sans combat.
"""
import asyncio
import random
import discord

from . import data, haki, enemies, progression, fruits

# Libellés affichés pour les actions ennemies, utilisés dans le mini-jeu de prédiction
ENEMY_ACTION_LABELS = {
    "attack": "⚔️ Attaque normale",
    "heavy_attack": "💥 Attaque lourde",
    "guard": "🛡️ Garde (réduit les dégâts subis)",
}


def compute_player_damage(player: dict, base_min=8, base_max=18) -> int:
    bonus = haki.total_combat_bonus(player)
    raw = random.randint(base_min, base_max)
    return raw + bonus["attack"]


class PveCombatView(discord.ui.View):
    """Vue de combat contre un PNJ généré aléatoirement à l'exploration."""

    def __init__(self, player_id: int, enemy: dict):
        super().__init__(timeout=120)
        self.player_id = player_id
        self.enemy = enemy
        self.message: discord.Message | None = None
        self.finished = False
        self._lock = asyncio.Lock()

        self.player = data.get_player(player_id)
        self.player_hp = self.player["hp_max"]
        self.enemy_hp = enemy["hp_max"]

        self.last_log = f"{enemy['emoji']} Un **{enemy['name']}** apparaît !"
        self.player_dodging = False
        self.enemy_frozen = 0.0  # réduction des dégâts du prochain coup ennemi (effet glace)

        # Mini-jeu de prédiction (Haki Observation) : si actif, la prochaine
        # action de l'ennemi est révélée avant que le joueur ne choisisse,
        # et il peut "parier" sur une contre-action pour un bonus.
        self.observation_available = self.player["haki"]["observation"]
        self.predicted_action: str | None = None
        self._roll_enemy_intent()

        # Nettoyage de l'interface : on retire les boutons liés à un Haki
        # que le joueur n'a pas encore débloqué, pour ne pas l'encombrer.
        if not self.player["haki"]["conquerant"]:
            self.remove_item(self.intimidate_btn)
        if not self.observation_available:
            self.remove_item(self.predict_attack_btn)
            self.remove_item(self.predict_heavy_btn)
            self.remove_item(self.predict_guard_btn)

        # Bouton de Fruit du Démon : libellé adapté au Fruit actif, ou
        # masqué complètement si le joueur n'en a mangé aucun.
        special = fruits.get_special_action(self.player)
        if special:
            self.devil_fruit_btn.label = special["label"]
        else:
            self.remove_item(self.devil_fruit_btn)

    # ------------------------------------------------------------------
    def _roll_enemy_intent(self):
        """Détermine à l'avance la prochaine action de l'ennemi (utilisée par
        le Haki d'Observation pour la révéler au joueur)."""
        self.next_enemy_action = enemies.enemy_choose_action()

    def hp_bar(self, hp: int, hp_max: int, length: int = 12) -> str:
        filled = max(0, min(length, round(length * hp / hp_max)))
        return "🟩" * filled + "⬛" * (length - filled)

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"{self.enemy['emoji']} Combat contre {self.enemy['name']}" + (" 👑 (BOSS)" if self.enemy["is_boss"] else ""),
            description=self.last_log,
            color=discord.Color.dark_red()
        )
        embed.add_field(
            name=self.player["name"],
            value=f"{self.hp_bar(self.player_hp, self.player['hp_max'])}\n❤️ {self.player_hp}/{self.player['hp_max']}",
            inline=True
        )
        embed.add_field(
            name=self.enemy["name"],
            value=f"{self.hp_bar(self.enemy_hp, self.enemy['hp_max'])}\n❤️ {self.enemy_hp}/{self.enemy['hp_max']}",
            inline=True
        )
        if self.observation_available and not self.finished:
            embed.add_field(
                name="👁️ Haki de l'Observation",
                value=f"Tu perçois la prochaine intention : **{ENEMY_ACTION_LABELS[self.next_enemy_action]}**",
                inline=False
            )
        if not self.finished:
            embed.set_footer(text=f"Récompense potentielle : {self.enemy['xp_reward']} XP, {self.enemy['berrys_reward']} Berrys")
        return embed

    # ------------------------------------------------------------------
    async def resolve_turn(self, interaction: discord.Interaction, action: str):
        async with self._lock:
            if self.finished:
                if not interaction.response.is_done():
                    await interaction.response.send_message("⏳ Ce combat est déjà terminé.", ephemeral=True)
                return

            player = self.player
            bonus = haki.total_combat_bonus(player)

            # --------------------------------------------------------
            # Action spéciale : Intimidation (Haki du Conquérant), peut
            # faire fuir un ennemi faible sans combat.
            # --------------------------------------------------------
            if action == "intimidate":
                if not player["haki"]["conquerant"]:
                    self.last_log = f"❌ {player['name']} n'a pas débloqué le Haki des Rois !"
                    await self.refresh(interaction)
                    return
                hp_ratio = self.enemy_hp / self.enemy["hp_max"]
                flee_chance = 0.5 if not self.enemy["is_boss"] else 0.15
                if hp_ratio < 0.5 and random.random() < flee_chance:
                    self.last_log = f"👑 {player['name']} déploie le Haki des Rois ! {self.enemy['name']} prend la fuite, terrifié !"
                    await self.end_combat(interaction, victory=True, fled=True)
                    return
                else:
                    self.last_log = f"👑 {player['name']} tente d'intimider {self.enemy['name']}, mais il tient bon !"
                    await self._enemy_turn_and_refresh(interaction)
                    return

            # --------------------------------------------------------
            # Action spéciale : Prédiction (Haki de l'Observation), parie
            # sur l'action ennemie déjà révélée pour un gros bonus si juste.
            # --------------------------------------------------------
            if action.startswith("predict_"):
                if not self.observation_available:
                    self.last_log = "❌ Tu n'as pas débloqué le Haki de l'Observation !"
                    await self.refresh(interaction)
                    return
                guessed = action.removeprefix("predict_")
                correct = guessed == self.next_enemy_action
                dmg = compute_player_damage(player)
                if correct:
                    dmg = int(dmg * 1.6)
                    new_hp = max(0, self.enemy_hp - dmg)
                    self.enemy_hp = new_hp
                    self.last_log = (
                        f"👁️ {player['name']} anticipe parfaitement l'action de {self.enemy['name']} "
                        f"et place une frappe critique pour {dmg} dégâts !"
                    )
                else:
                    dmg = int(dmg * 0.6)
                    new_hp = max(0, self.enemy_hp - dmg)
                    self.enemy_hp = new_hp
                    self.last_log = (
                        f"👁️ {player['name']} se trompe dans sa lecture, mais touche quand même "
                        f"{self.enemy['name']} pour {dmg} dégâts."
                    )
                if self.enemy_hp <= 0:
                    await self.end_combat(interaction, victory=True)
                    return
                await self._enemy_turn_and_refresh(interaction)
                return

            # --------------------------------------------------------
            # Action spéciale : Fruit du Démon actif
            # --------------------------------------------------------
            if action == "devil_fruit_action":
                special = fruits.get_special_action(player)
                if not special:
                    self.last_log = f"❌ {player['name']} n'a mangé aucun Fruit du Démon !"
                    await self.refresh(interaction)
                    return
                if not fruits.special_action_ready(player):
                    remaining = player.get("devil_fruit_cooldown", 0)
                    self.last_log = f"⏳ {special['label']} est encore en recharge ({remaining} tour(s))."
                    await self.refresh(interaction)
                    return

                fruits.trigger_special_action_cooldown(player)

                if special.get("guaranteed_dodge"):
                    self.player_dodging = True
                    self.last_log = f"{special['label']} — {player['name']} se met hors de portée, esquive garantie au prochain assaut !"
                    await self._enemy_turn_and_refresh(interaction)
                    return
                elif special.get("freeze_reduction"):
                    self.enemy_frozen = special["freeze_reduction"]
                    self.last_log = f"{special['label']} — {self.enemy['name']} est ralenti, ses prochains dégâts seront réduits !"
                    await self._enemy_turn_and_refresh(interaction)
                    return
                else:
                    dmg = compute_player_damage(player)
                    mult = special.get("damage_mult", 1.0)
                    dmg = int(dmg * mult)

                    hits = 1
                    if special.get("double_hit_chance") and random.random() < special["double_hit_chance"]:
                        hits = 2
                    total_dmg = dmg * hits

                    self.enemy_hp = max(0, self.enemy_hp - total_dmg)
                    extra = f" (x{hits} coups !)" if hits > 1 else ""
                    self.last_log = f"{special['label']} — {player['name']} frappe {self.enemy['name']} pour {total_dmg} dégâts !{extra}"

                if self.enemy_hp <= 0:
                    await self.end_combat(interaction, victory=True)
                    return
                await self._enemy_turn_and_refresh(interaction)
                return

            # --------------------------------------------------------
            # Actions classiques : attaque, frappe Haki, esquive, soin
            # --------------------------------------------------------
            if action == "attack" or action == "haki_strike":
                dmg = compute_player_damage(player)
                if action == "haki_strike":
                    if not player["haki"]["armement"]:
                        self.last_log = f"❌ {player['name']} n'a pas débloqué le Haki de l'Armement !"
                        await self.refresh(interaction)
                        return
                    dmg = int(dmg * 1.4)

                if random.random() < bonus["instant_ko_chance"]:
                    self.enemy_hp = 0
                    self.last_log = f"👑 Le Haki des Rois assomme {self.enemy['name']} instantanément !"
                else:
                    self.enemy_hp = max(0, self.enemy_hp - dmg)
                    verb = "frappe avec le Haki de l'Armement" if action == "haki_strike" else "attaque"
                    self.last_log = f"💥 {player['name']} {verb} {self.enemy['name']} pour {dmg} dégâts !"

                if self.enemy_hp <= 0:
                    await self.end_combat(interaction, victory=True)
                    return
                await self._enemy_turn_and_refresh(interaction)
                return

            if action == "dodge_stance":
                self.player_dodging = True
                self.last_log = f"🛡️ {player['name']} se met en garde."
                await self._enemy_turn_and_refresh(interaction)
                return

            if action == "item":
                heal = 15
                self.player_hp = min(player["hp_max"], self.player_hp + heal)
                self.last_log = f"🍖 {player['name']} mange et récupère {heal} PV !"
                await self._enemy_turn_and_refresh(interaction)
                return

    async def _enemy_turn_and_refresh(self, interaction: discord.Interaction):
        """Joue le tour de l'ennemi, puis rafraîchit l'affichage."""
        fruits.tick_cooldown(self.player)

        enemy_action = self.next_enemy_action if self.observation_available else enemies.enemy_choose_action()

        bonus = haki.total_combat_bonus(self.player)
        was_dodging = self.player_dodging  # mémoriser avant remise à zéro
        self.player_dodging = False
        dodge_roll = random.random()
        dodged = was_dodging or dodge_roll < bonus["dodge_chance"]

        if enemy_action == "guard":
            self.last_log += f"\n🛡️ {self.enemy['name']} se met en garde."
        elif dodged:
            if was_dodging:
                self.last_log += f"\n🛡️ {self.player['name']} était en garde et dévie l'attaque de {self.enemy['name']} !"
            else:
                self.last_log += f"\n💨 {self.player['name']} esquive l'attaque de {self.enemy['name']} !"
        else:
            is_heavy = enemy_action == "heavy_attack"
            dmg = random.randint(self.enemy["dmg_min"], self.enemy["dmg_max"])
            if is_heavy:
                dmg = int(dmg * 1.5)
            if self.enemy_frozen:
                dmg = int(dmg * (1 - self.enemy_frozen))
                self.enemy_frozen = 0.0

            # Intangibilité Logia : les ennemis PNJ n'ont pas de Haki,
            # leurs attaques sont réduites de 40% mais pas annulées (risque conservé en PvE)
            logia_note = ""
            if fruits.is_logia(self.player):
                dmg = int(dmg * 0.6)
                fruit = fruits.get_fruit(self.player.get("devil_fruit", ""))
                fruit_name = fruit["name"] if fruit else "son Fruit"
                logia_note = f" *(le **{fruit_name}** absorbe une partie du coup)*"

            self.player_hp = max(0, self.player_hp - dmg)
            verb = "frappe lourdement" if is_heavy else "attaque"
            self.last_log += f"\n💢 {self.enemy['name']} {verb} {self.player['name']} pour {dmg} dégâts !{logia_note}"

        if self.player_hp <= 0:
            await self.end_combat(interaction, victory=False)
            return

        self._roll_enemy_intent()
        await self.refresh(interaction)

    async def refresh(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def end_combat(self, interaction: discord.Interaction, victory: bool, fled: bool = False):
        self.finished = True
        player = self.player

        embed_color = discord.Color.gold() if victory else discord.Color.greyple()
        result_lines = []

        if victory:
            xp_gain = self.enemy["xp_reward"]
            berrys_gain = self.enemy["berrys_reward"]
            player["xp"] += xp_gain
            player["berrys"] += berrys_gain
            player["wins"] += 1
            if self.enemy["is_boss"] and not fled:
                player["bosses_defeated"] = player.get("bosses_defeated", 0) + 1
            level_up_msg = progression.apply_xp_and_levelup(player)

            from . import bounty
            old_bounty = player.get("bounty", 0)
            new_bounty = bounty.refresh_bounty(player)

            if fled:
                result_lines.append(f"🏃 **{self.enemy['name']}** prend la fuite !")
            else:
                result_lines.append(f"🏆 **{player['name']}** triomphe de **{self.enemy['name']}** !")
            result_lines.append(f"✨ +{xp_gain} XP")
            result_lines.append(f"💰 +{berrys_gain} Berrys")
            if level_up_msg:
                result_lines.append(level_up_msg)
            if new_bounty > old_bounty:
                result_lines.append(f"📰 Ta prime grimpe à {bounty.format_bounty(new_bounty)} !")
            title = "🏆 Victoire !"
        else:
            player["losses"] += 1
            penalty = min(player["berrys"], int(player["berrys"] * 0.1))
            player["berrys"] -= penalty
            result_lines.append(f"💀 **{player['name']}** est vaincu par **{self.enemy['name']}**...")
            if penalty > 0:
                result_lines.append(f"💸 Tu perds {penalty} Berrys en soins d'urgence.")
            title = "💀 Défaite"

        player["hp"] = max(1, self.player_hp) if victory else player["hp_max"]  # remise sur pied après une défaite
        data.update_player(player)

        embed = self.build_embed()
        embed.title = title
        embed.color = embed_color
        embed.add_field(name="Résultat", value="\n".join(result_lines), inline=False)

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    # ------------------------------------------------------------------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("❌ Ce combat ne te concerne pas.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚔️ Attaquer", style=discord.ButtonStyle.danger, row=0)
    async def attack_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "attack")

    @discord.ui.button(label="✊ Frappe Haki", style=discord.ButtonStyle.primary, row=0)
    async def haki_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "haki_strike")

    @discord.ui.button(label="🛡️ Esquive", style=discord.ButtonStyle.secondary, row=0)
    async def dodge_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "dodge_stance")

    @discord.ui.button(label="🍖 Soigner", style=discord.ButtonStyle.success, row=0)
    async def heal_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "item")

    @discord.ui.button(label="👑 Intimider", style=discord.ButtonStyle.secondary, row=1)
    async def intimidate_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "intimidate")

    @discord.ui.button(label="👁️ Parier : Attaque normale", style=discord.ButtonStyle.secondary, row=2)
    async def predict_attack_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "predict_attack")

    @discord.ui.button(label="👁️ Parier : Attaque lourde", style=discord.ButtonStyle.secondary, row=2)
    async def predict_heavy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "predict_heavy_attack")

    @discord.ui.button(label="👁️ Parier : Garde", style=discord.ButtonStyle.secondary, row=2)
    async def predict_guard_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "predict_guard")

    @discord.ui.button(label="🍈 Pouvoir du Fruit", style=discord.ButtonStyle.primary, row=1)
    async def devil_fruit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "devil_fruit_action")

    async def _safe_resolve(self, interaction: discord.Interaction, action: str):
        try:
            await self.resolve_turn(interaction, action)
        except Exception as e:
            print(f"[pve] Erreur pendant resolve_turn({action}) : {e}")
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "⚠️ Une erreur est survenue pendant ce tour. Réessaie.", ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "⚠️ Une erreur est survenue pendant ce tour. Réessaie.", ephemeral=True
                    )
            except discord.HTTPException:
                pass

    async def on_timeout(self):
        if not self.finished and self.message:
            for child in self.children:
                child.disabled = True
            try:
                await self.message.edit(content="⏳ Combat annulé (temps écoulé).", view=self)
            except discord.HTTPException:
                pass