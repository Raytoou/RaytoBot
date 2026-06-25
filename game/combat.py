"""
Système de combat PvP au tour par tour, avec boutons Discord interactifs.
Mise de Berrys : le gagnant prend la mise au perdant.
"""
import asyncio
import random
import discord

from . import data, haki, fruits

ACTIONS = ["attack", "haki_strike", "dodge_stance", "item"]


def compute_damage(attacker: dict, base_min=8, base_max=18, nullify_haki: bool = False) -> int:
    raw = random.randint(base_min, base_max)
    if nullify_haki:
        fruit_bonus = fruits.fruit_passive_bonus(attacker)
        return raw + fruit_bonus.get("attack", 0)
    bonus = haki.total_combat_bonus(attacker)
    return raw + bonus["attack"]


class CombatView(discord.ui.View):
    """Vue de combat PvP. challenger = celui qui a lancé /combat, opponent = la cible."""

    def __init__(self, challenger_id: int, opponent_id: int, wager: int):
        super().__init__(timeout=120)
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.wager = wager
        self.message: discord.Message | None = None
        self.finished = False
        self._lock = asyncio.Lock()

        self.p1 = data.get_player(challenger_id)
        self.p2 = data.get_player(opponent_id)

        # HP de combat séparé du HP "stocké" pour ne pas affecter la suite du jeu
        self.hp1 = self.p1["hp_max"]
        self.hp2 = self.p2["hp_max"]

        self.turn = challenger_id  # qui doit jouer
        self.last_log = "⚔️ Le combat commence !"
        self.dodging = {challenger_id: False, opponent_id: False}

        # Effets temporaires déclenchés par certaines actions spéciales de Fruits
        self.frozen = {challenger_id: 0.0, opponent_id: 0.0}  # réduction des dégâts infligés par ce joueur à son prochain tour
        self.guaranteed_dodge_next = {challenger_id: False, opponent_id: False}
        self.haki_nullified = {challenger_id: False, opponent_id: False}  # le bonus de Haki de CE joueur est annulé pour son prochain tour

    # ------------------------------------------------------------------
    def other(self, user_id: int) -> int:
        return self.opponent_id if user_id == self.challenger_id else self.challenger_id

    def player_of(self, user_id: int) -> dict:
        return self.p1 if user_id == self.challenger_id else self.p2

    def hp_of(self, user_id: int) -> int:
        return self.hp1 if user_id == self.challenger_id else self.hp2

    def set_hp(self, user_id: int, value: int):
        if user_id == self.challenger_id:
            self.hp1 = max(0, value)
        else:
            self.hp2 = max(0, value)

    def hp_bar(self, hp: int, hp_max: int, length: int = 12) -> str:
        filled = max(0, min(length, round(length * hp / hp_max)))
        return "🟩" * filled + "⬛" * (length - filled)

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="⚔️ Combat de Pirates",
            description=self.last_log,
            color=discord.Color.red()
        )
        embed.add_field(
            name=f"{self.p1['name']}",
            value=f"{self.hp_bar(self.hp1, self.p1['hp_max'])}\n❤️ {self.hp1}/{self.p1['hp_max']}",
            inline=True
        )
        embed.add_field(
            name=f"{self.p2['name']}",
            value=f"{self.hp_bar(self.hp2, self.p2['hp_max'])}\n❤️ {self.hp2}/{self.p2['hp_max']}",
            inline=True
        )
        if not self.finished:
            current_player = self.player_of(self.turn)
            special = fruits.get_special_action(current_player)
            if special:
                ready = fruits.special_action_ready(current_player)
                status = "prêt" if ready else f"recharge: {current_player.get('devil_fruit_cooldown', 0)} tour(s)"
                embed.add_field(
                    name="🍈 Pouvoir disponible",
                    value=f"{special['label']} ({status})",
                    inline=False
                )
            embed.set_footer(text=f"💰 Mise : {self.wager} Berrys — Au tour de {current_player['name']}")
        return embed

    # ------------------------------------------------------------------
    async def resolve_turn(self, interaction: discord.Interaction, action: str):
        async with self._lock:
            # Revérification sous verrou : si le combat s'est terminé ou que
            # le tour a changé pendant l'attente du verrou (cas de deux clics
            # quasi simultanés), on ignore silencieusement ce second clic.
            if self.finished or interaction.user.id != self.turn:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "⏳ Ce n'est pas (ou plus) ton tour.", ephemeral=True
                    )
                return

            actor_id = interaction.user.id
            target_id = self.other(actor_id)
            actor = self.player_of(actor_id)
            target = self.player_of(target_id)

            # ----------------------------------------------------
            # Action spéciale du Fruit du Démon actif
            # ----------------------------------------------------
            if action == "devil_fruit_action":
                special = fruits.get_special_action(actor)
                if not special:
                    self.last_log = f"❌ {actor['name']} n'a mangé aucun Fruit du Démon !"
                    await self.refresh(interaction)
                    return
                if not fruits.special_action_ready(actor):
                    remaining = actor.get("devil_fruit_cooldown", 0)
                    self.last_log = f"⏳ {special['label']} est encore en recharge ({remaining} tour(s))."
                    await self.refresh(interaction)
                    return

                fruits.trigger_special_action_cooldown(actor)

                if special.get("guaranteed_dodge"):
                    self.guaranteed_dodge_next[actor_id] = True
                    self.last_log = f"{special['label']} — {actor['name']} se met hors de portée, esquive garantie au prochain assaut !"
                elif special.get("freeze_reduction"):
                    self.frozen[actor_id] = special["freeze_reduction"]
                    self.last_log = f"{special['label']} — {target['name']} est ralenti, ses prochains dégâts seront réduits !"
                    self.frozen[target_id] = special["freeze_reduction"]
                else:
                    nullify = special.get("nullify_haki", False)
                    if nullify:
                        self.haki_nullified[target_id] = True
                    dmg = compute_damage(actor, nullify_haki=False)
                    mult = special.get("damage_mult", 1.0)
                    dmg = int(dmg * mult)

                    hits = 1
                    if special.get("double_hit_chance") and random.random() < special["double_hit_chance"]:
                        hits = 2

                    target_frozen = self.frozen.get(target_id, 0.0)
                    if target_frozen:
                        dmg = int(dmg * (1 - target_frozen))
                        self.frozen[target_id] = 0.0

                    total_dmg = dmg * hits
                    new_hp = self.hp_of(target_id) - total_dmg
                    self.set_hp(target_id, new_hp)

                    extra = f" (x{hits} coups !)" if hits > 1 else ""
                    nullify_text = " Le Haki adverse est annulé !" if nullify else ""
                    self.last_log = f"{special['label']} — {actor['name']} frappe {target['name']} pour {total_dmg} dégâts !{extra}{nullify_text}"

                if self.hp_of(target_id) <= 0:
                    await self.end_combat(interaction, winner_id=actor_id, loser_id=target_id)
                    return

                self.dodging[target_id] = False
                self.turn = target_id
                await self.refresh(interaction)
                return

            if action == "attack" or action == "haki_strike":
                actor_nullified = self.haki_nullified.get(actor_id, False)
                self.haki_nullified[actor_id] = False
                dmg = compute_damage(actor, nullify_haki=actor_nullified)
                if action == "haki_strike":
                    if not actor["haki"]["armement"]:
                        self.last_log = f"❌ {actor['name']} n'a pas débloqué le Haki de l'Armement !"
                        await self.refresh(interaction)
                        return
                    dmg = int(dmg * 1.4)

                # Intangibilité Logia : une attaque normale traverse le corps
                # d'un utilisateur de Logia. Seul le Haki de l'Armement ou un
                # autre utilisateur Logia peut passer outre.
                # Note : actor_nullified (Yami Yami) annule le bonus de Haki
                # de l'attaquant mais ne lui donne pas la capacité de toucher un Logia.
                if action == "attack" and fruits.is_logia(target):
                    attacker_has_armement = actor["haki"]["armement"] and not actor_nullified
                    attacker_is_logia = fruits.is_logia(actor)
                    if not attacker_has_armement and not attacker_is_logia:
                        self.last_log = (
                            f"🌫️ L'attaque de {actor['name']} traverse le corps de "
                            f"{target['name']} sans effet ! (Logia — utilise le Haki de l'Armement ou ta Frappe Haki)"
                        )
                        fruits.tick_cooldown(actor)
                        self.turn = target_id
                        await self.refresh(interaction)
                        return

                actor_frozen = self.frozen.get(actor_id, 0.0)
                if actor_frozen:
                    dmg = int(dmg * (1 - actor_frozen))
                    self.frozen[actor_id] = 0.0

                target_bonus = haki.total_combat_bonus(target)
                dodge_roll = random.random()
                target_guaranteed_dodge = self.guaranteed_dodge_next.get(target_id, False)
                self.guaranteed_dodge_next[target_id] = False

                if target_guaranteed_dodge or self.dodging.get(target_id) or dodge_roll < target_bonus["dodge_chance"]:
                    if target_guaranteed_dodge:
                        fruit = fruits.get_fruit(target.get("devil_fruit"))
                        fruit_name = fruit["name"] if fruit else "son Fruit"
                        self.last_log = f"🌀 {target['name']} disparaît en un éclair grâce au **{fruit_name}** — l'attaque passe dans le vide !"
                    elif self.dodging.get(target_id):
                        self.last_log = f"🛡️ {target['name']} était en garde et dévie l'attaque de {actor['name']} !"
                    elif fruits.is_logia(target):
                        fruit = fruits.get_fruit(target.get("devil_fruit"))
                        fruit_name = fruit["name"] if fruit else "son Fruit"
                        self.last_log = f"🌫️ L'attaque de {actor['name']} traverse le corps de {target['name']} — le **{fruit_name}** le rend insaisissable !"
                    else:
                        self.last_log = f"💨 {target['name']} esquive l'attaque de {actor['name']} !"
                else:
                    # Chance de KO instantané via Haki du Conquérant
                    actor_bonus = haki.total_combat_bonus(actor)
                    if not actor_nullified and random.random() < actor_bonus["instant_ko_chance"]:
                        self.set_hp(target_id, 0)
                        self.last_log = f"👑 {actor['name']} déploie le Haki des Rois ! {target['name']} s'effondre, assommé !"
                    else:
                        new_hp = self.hp_of(target_id) - dmg
                        self.set_hp(target_id, new_hp)
                        verb = "frappe avec le Haki de l'Armement" if action == "haki_strike" else "attaque"
                        self.last_log = f"💥 {actor['name']} {verb} {target['name']} pour {dmg} dégâts !"

            elif action == "dodge_stance":
                self.dodging[actor_id] = True
                self.last_log = f"🛡️ {actor['name']} se met en garde, prêt à esquiver."

            elif action == "item":
                heal = 15
                new_hp = min(actor["hp_max"], self.hp_of(actor_id) + heal)
                self.set_hp(actor_id, new_hp)
                self.last_log = f"🍖 {actor['name']} mange et récupère {heal} PV !"

            # Réinitialise la posture d'esquive de l'acteur précédent au tour suivant
            self.dodging[target_id] = False if action != "dodge_stance" else self.dodging.get(target_id, False)

            # Le cooldown de l'action spéciale de Fruit du Démon de l'acteur
            # diminue à chaque tour qu'il joue (y compris s'il ne l'utilise pas)
            fruits.tick_cooldown(actor)

            if self.hp_of(target_id) <= 0:
                await self.end_combat(interaction, winner_id=actor_id, loser_id=target_id)
                return
            if self.hp_of(actor_id) <= 0:
                await self.end_combat(interaction, winner_id=target_id, loser_id=actor_id)
                return

            self.turn = target_id
            await self.refresh(interaction)

    async def refresh(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def end_combat(self, interaction: discord.Interaction, winner_id: int, loser_id: int):
        self.finished = True
        winner = self.player_of(winner_id)
        loser = self.player_of(loser_id)

        actual_wager = min(self.wager, loser["berrys"])
        winner["berrys"] += actual_wager
        loser["berrys"] -= actual_wager
        winner["wins"] += 1
        loser["losses"] += 1

        xp_gain = 25
        winner["xp"] += xp_gain
        from . import progression
        level_up_msg = progression.apply_xp_and_levelup(winner)

        from . import bounty
        old_bounty = winner.get("bounty", 0)
        new_bounty = bounty.refresh_bounty(winner)

        data.update_player(self.p1)
        data.update_player(self.p2)

        embed = self.build_embed()
        embed.title = "🏆 Victoire !"
        embed.color = discord.Color.gold()
        result_text = (
            f"**{winner['name']}** remporte le combat contre **{loser['name']}** !\n"
            f"💰 +{actual_wager} Berrys gagnés (mise du perdant)\n"
            f"✨ +{xp_gain} XP"
        )
        if level_up_msg:
            result_text += f"\n{level_up_msg}"
        if new_bounty > old_bounty:
            result_text += f"\n📰 Ta prime grimpe à {bounty.format_bounty(new_bounty)} !"
        embed.add_field(name="Résultat", value=result_text, inline=False)

        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    # ------------------------------------------------------------------
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in (self.challenger_id, self.opponent_id):
            await interaction.response.send_message("❌ Ce combat ne te concerne pas.", ephemeral=True)
            return False
        if interaction.user.id != self.turn:
            await interaction.response.send_message("⏳ Ce n'est pas ton tour.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚔️ Attaquer", style=discord.ButtonStyle.danger)
    async def attack_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "attack")

    @discord.ui.button(label="✊ Frappe Haki", style=discord.ButtonStyle.primary)
    async def haki_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "haki_strike")

    @discord.ui.button(label="🛡️ Esquive", style=discord.ButtonStyle.secondary)
    async def dodge_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "dodge_stance")

    @discord.ui.button(label="🍖 Soigner", style=discord.ButtonStyle.success)
    async def heal_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "item")

    @discord.ui.button(label="🍈 Pouvoir du Fruit", style=discord.ButtonStyle.primary, row=1)
    async def devil_fruit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._safe_resolve(interaction, "devil_fruit_action")

    async def _safe_resolve(self, interaction: discord.Interaction, action: str):
        """Garde-fou : si resolve_turn lève une exception inattendue, on
        s'assure quand même de répondre à l'interaction Discord pour éviter
        l'erreur 'Cette interaction a échoué' côté utilisateur."""
        try:
            await self.resolve_turn(interaction, action)
        except Exception as e:
            print(f"[combat] Erreur pendant resolve_turn({action}) : {e}")
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