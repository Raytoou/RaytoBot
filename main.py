import discord
from discord.ext import commands
from discord import app_commands, Interaction
import yt_dlp as youtube_dl
import asyncio
import os
import random
import lyricsgenius
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GENIUS_TOKEN = os.getenv("GENIUS_TOKEN")
genius = lyricsgenius.Genius(GENIUS_TOKEN)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

janga_stock = {}
snipe_message_author = {}
snipe_message_content = {}
snipe_message_attachment = {}
muted_users = {}
dc_users = {}

music_queues = {}

# ----- Liste fixe des IDs avec statut spécial pour la modération -----
MODERATION_BLACKLIST = {
    702504146250760273,
    748323867826585600,
}


def is_protected(member_id: int) -> bool:
    """Vérifie si un membre est protégé contre toute commande de modération."""
    return member_id in MODERATION_BLACKLIST
 
 
def is_authorized(user_id: int) -> bool:
    """Vérifie si l'utilisateur peut utiliser les commandes de modération sans permission Discord."""
    return user_id in MODERATION_BLACKLIST
 
def get_queue(guild_id):
    if guild_id not in music_queues:
        music_queues[guild_id] = []
    return music_queues[guild_id]
 
 
def schedule_prefetch(guild_id):
    """Lance en tâche de fond la résolution yt-dlp du prochain morceau de la
    file, sans bloquer la lecture en cours. Le résultat est stocké directement
    dans l'entrée de la queue (clé 'resolve_task'), pour être réutilisé
    instantanément quand son tour de lecture arrive."""
    queue = get_queue(guild_id)
    if not queue:
        return
    next_entry = queue[0]
    if 'resolve_task' in next_entry or 'stream_url' in next_entry:
        # Déjà en cours de résolution, ou déjà résolu : rien à faire.
        return
    next_entry['resolve_task'] = asyncio.create_task(resolve_entry(next_entry['query']))
 
 
async def get_ready_entry(guild_id):
    """Retire et renvoie le prochain morceau de la file, en s'assurant qu'il
    est résolu (attend la tâche de prefetch si elle est en cours, ou résout
    à la volée si le prefetch n'a pas eu le temps de se déclencher)."""
    queue = get_queue(guild_id)
    if not queue:
        return None
    entry = queue.pop(0)
 
    if 'stream_url' in entry:
        return entry
 
    if 'resolve_task' in entry:
        resolved = await entry['resolve_task']
    else:
        resolved = await resolve_entry(entry['query'])
 
    if not resolved:
        return None
    return resolved
 
async def play_next_async(guild_id, voice_client):
    """Version async de play_next (appelée depuis le callback after)."""
    queue = get_queue(guild_id)
    if not queue or voice_client.is_playing():
        return
 
    entry = await get_ready_entry(guild_id)
    if not entry:
        # Résolution échouée pour ce morceau : on passe directement au suivant.
        await play_next_async(guild_id, voice_client)
        return
 
    # Dès que ce morceau démarre, on lance déjà la résolution du suivant en
    # tâche de fond, pour qu'il soit prêt instantanément à son tour.
    schedule_prefetch(guild_id)
 
    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -filter:a "volume=0.25"'
    }
 
    def after_playing(error):
        if error:
            print(f"Erreur lecture : {error}")
        fut = asyncio.run_coroutine_threadsafe(
            play_next_async(guild_id, voice_client), bot.loop
        )
        try:
            fut.result()
        except Exception as e:
            print(f"Erreur play_next : {e}")
 
    voice_client.play(
        discord.FFmpegOpusAudio(
            entry['stream_url'],
            executable="ffmpeg",
            **ffmpeg_options
        ),
        after=after_playing
    )
    print(f"▶️ Lecture auto : {entry['title']}")
 
 
@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return
    snipe_message_author[message.channel.id] = message.author
    snipe_message_content[message.channel.id] = message.content or "[Message vide]"
    if message.attachments:
        snipe_message_attachment[message.channel.id] = message.attachments[0].url
    else:
        snipe_message_attachment[message.channel.id] = None
    await asyncio.sleep(60)
    snipe_message_author.pop(message.channel.id, None)
    snipe_message_content.pop(message.channel.id, None)
    snipe_message_attachment.pop(message.channel.id, None)
 
 
@bot.tree.command(name="janga", description="Ajoute ou dépense de la Janga dans ton stock")
@app_commands.describe(nombre="Quantité de Janga à ajouter (positive) ou dépenser (négative), entre -1000 et 1000")
@app_commands.rename(nombre="quantité")
async def janga(interaction: Interaction, nombre: app_commands.Range[int, -1000, 1000]):
    user_id = interaction.user.id
    current_stock = janga_stock.get(user_id, 0)
    new_stock = current_stock + nombre
    if new_stock < 0:
        await interaction.response.send_message(
            f"⚠️ Tu ne peux pas dépenser plus de Janga que tu n'en as (stock actuel : {current_stock}).",
            ephemeral=True
        )
        return
    janga_stock[user_id] = new_stock
    action = "ajouté" if nombre >= 0 else "dépensé"
    await interaction.response.send_message(
        f"💊 Tu as {action} {abs(nombre)} Janga.\nStock actuel : {new_stock} pour {interaction.user.mention}."
    )
 
 
@bot.tree.command(name="dc", description="Déconnecte un utilisateur en boucle dès qu'il rejoint un canal vocal.")
@app_commands.describe(member="L'utilisateur à déconnecter en boucle")
async def dc(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.kick_members and not is_authorized(interaction.user.id):
        await interaction.response.send_message("❌ Tu n'as pas la permission de déconnecter des membres.", ephemeral=True)
        return
    if is_protected(member.id):
        await interaction.response.send_message(
            f"🛡️ {member.mention} est protégé par la blacklist de modération, impossible de le déconnecter en boucle.",
            ephemeral=True
        )
        return
    dc_users[member.id] = True
    await interaction.response.send_message(f"😈 {member.mention} sera déconnecté à chaque fois qu'il rejoint un canal vocal.")
 
 
@bot.event
async def on_voice_state_update(member, before, after):
    if member.id in dc_users:
        if after.channel is not None:
            try:
                await member.move_to(None)
            except Exception as e:
                print(f"Erreur lors de la déconnexion de {member.name}: {e}")
 
 
@bot.tree.command(name="stopdc", description="Arrête de déconnecter un utilisateur à chaque fois qu'il rejoint un canal vocal.")
@app_commands.describe(member="L'utilisateur pour arrêter la déconnexion infinie")
async def stopdc(interaction: discord.Interaction, member: discord.Member):
    if member.id in dc_users:
        del dc_users[member.id]
        await interaction.response.send_message(f"✅ La déconnexion de {member.mention} a été arrêtée.")
    else:
        await interaction.response.send_message(f"❌ {member.mention} n'était pas sur la liste des déconnexions infinies.")
 
 
@bot.tree.command(name="mute", description="Mute un utilisateur en vocal et l'empêche d'être démuté.")
@app_commands.describe(member="L'utilisateur à mute")
async def mute(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.mute_members and not is_authorized(interaction.user.id):
        await interaction.response.send_message("❌ Tu n'as pas la permission de mute.", ephemeral=True)
        return
    if is_protected(member.id):
        await interaction.response.send_message(
            f"🛡️ {member.mention} est protégé par la blacklist de modération, impossible de le mute.",
            ephemeral=True
        )
        return
    if not member.voice or not member.voice.channel:
        await interaction.response.send_message("❌ L'utilisateur n'est pas en vocal.", ephemeral=True)
        return
    try:
        await member.edit(mute=True)
    except discord.Forbidden:
        await interaction.response.send_message("❌ Je n'ai pas la permission de mute cet utilisateur.", ephemeral=True)
        return
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
        return
    muted_users[member.id] = True
    await interaction.response.send_message(f"🔇 {member.mention} a été mute vocalement et ne pourra pas être démuté.")
    while member.id in muted_users:
        await asyncio.sleep(1)
        if not member.voice:
            break
        if not member.voice.mute:
            try:
                await member.edit(mute=True)
            except Exception:
                pass
 
 
@bot.tree.command(name="unmute", description="Arrête le mute forcé d'un utilisateur.")
@app_commands.describe(member="L'utilisateur à unmute")
async def unmute(interaction: discord.Interaction, member: discord.Member):
    if not interaction.user.guild_permissions.mute_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission de unmute.", ephemeral=True)
        return
    if member.id in muted_users:
        del muted_users[member.id]
        await member.edit(mute=False)
        await interaction.response.send_message(f"🔊 {member.mention} peut maintenant parler en vocal.")
    else:
        await interaction.response.send_message("❌ Cet utilisateur n'était pas en mute forcé.", ephemeral=True)
 
 
@bot.tree.command(name="ban", description="Bannit un utilisateur du serveur.")
@app_commands.describe(member="L'utilisateur à bannir", reason="Raison du bannissement (optionnel)")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.ban_members and not is_authorized(interaction.user.id):
        await interaction.response.send_message("❌ Tu n'as pas la permission de bannir des membres.", ephemeral=True)
        return
    if is_protected(member.id):
        await interaction.response.send_message(
            f"🛡️ {member.mention} est protégé par la blacklist de modération, impossible de le bannir.",
            ephemeral=True
        )
        return
    try:
        await member.ban(reason=reason or f"Banni par {interaction.user}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ Je n'ai pas la permission de bannir cet utilisateur.", ephemeral=True)
        return
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
        return
    msg = f"🔨 {member.mention} a été banni du serveur."
    if reason:
        msg += f"\n**Raison :** {reason}"
    await interaction.response.send_message(msg)
 
 
@bot.tree.command(name="unban", description="Débannit un utilisateur via son ID Discord.")
@app_commands.describe(user_id="L'ID Discord de l'utilisateur à débannir")
async def unban(interaction: discord.Interaction, user_id: str):
    if not interaction.user.guild_permissions.ban_members and not is_authorized(interaction.user.id):
        await interaction.response.send_message("❌ Tu n'as pas la permission de débannir des membres.", ephemeral=True)
        return
    try:
        uid = int(user_id)
    except ValueError:
        await interaction.response.send_message("❌ L'ID fourni n'est pas valide.", ephemeral=True)
        return
    try:
        user = await bot.fetch_user(uid)
        await interaction.guild.unban(user, reason=f"Débanni par {interaction.user}")
    except discord.NotFound:
        await interaction.response.send_message("❌ Cet utilisateur n'est pas banni ou n'existe pas.", ephemeral=True)
        return
    except discord.Forbidden:
        await interaction.response.send_message("❌ Je n'ai pas la permission de débannir cet utilisateur.", ephemeral=True)
        return
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
        return
    await interaction.response.send_message(f"✅ {user.mention} a été débanni du serveur.")
 
 
@bot.tree.command(name="kick", description="Expulse un utilisateur du serveur.")
@app_commands.describe(member="L'utilisateur à expulser", reason="Raison de l'expulsion (optionnel)")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    if not interaction.user.guild_permissions.kick_members and not is_authorized(interaction.user.id):
        await interaction.response.send_message("❌ Tu n'as pas la permission d'expulser des membres.", ephemeral=True)
        return
    if is_protected(member.id):
        await interaction.response.send_message(
            f"🛡️ {member.mention} est protégé par la blacklist de modération, impossible de l'expulser.",
            ephemeral=True
        )
        return
    try:
        await member.kick(reason=reason or f"Expulsé par {interaction.user}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ Je n'ai pas la permission d'expulser cet utilisateur.", ephemeral=True)
        return
    except Exception as e:
        await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
        return
    msg = f"👢 {member.mention} a été expulsé du serveur."
    if reason:
        msg += f"\n**Raison :** {reason}"
    await interaction.response.send_message(msg)
 
 
@bot.tree.command(name="snipe", description="Récupère le dernier message supprimé dans ce salon.")
async def snipe(interaction: discord.Interaction):
    channel = interaction.channel
    try:
        author = snipe_message_author[channel.id]
        content = snipe_message_content[channel.id]
        attachment = snipe_message_attachment[channel.id]
        embed = discord.Embed(
            title=f"💬 Message supprimé dans #{channel.name}",
            description=content,
            color=discord.Color.red()
        )
        embed.set_footer(text=f"Envoyé par {author}", icon_url=author.avatar.url if author.avatar else None)
        if attachment:
            embed.set_image(url=attachment)
        await interaction.response.defer()
        await interaction.followup.send(embed=embed)
    except KeyError:
        await interaction.response.send_message(
            f"Aucun message supprimé récemment dans #{channel.name}.",
            ephemeral=True
        )
 
 
YDL_OPTS_BASE = {
    'format': 'bestaudio/best',
    'quiet': True,
    'cookiesfrombrowser': ('firefox', 'awbnwx4s.default-release-1781955673208'),
}
 
def _extract_info_sync(query, ydl_opts):
    """Appel bloquant yt-dlp, à lancer dans un thread séparé pour ne pas geler le bot."""
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)
 
 
async def resolve_entry(query):
    """Résout une URL ou un titre en dict {title, stream_url}.
    Une seule extraction complète est faite, qu'il s'agisse d'une recherche
    par titre ou d'une URL directe, pour éviter une double résolution yt-dlp."""
    is_url = "youtube.com" in query or "youtu.be" in query
    search_query = query if is_url else f"ytsearch1:{query}"
 
    ydl_opts = {**YDL_OPTS_BASE, 'noplaylist': True}
 
    try:
        # extract_info est bloquant (réseau + parsing) : on le sort de l'event loop
        # asyncio pour ne pas geler le reste du bot pendant la résolution.
        info = await asyncio.to_thread(_extract_info_sync, search_query, ydl_opts)
    except Exception as e:
        print(f"Erreur résolution yt-dlp : {e}")
        return None
 
    if not info:
        return None
 
    # Une recherche ytsearch1: renvoie un conteneur avec 'entries'
    if 'entries' in info:
        entries = info['entries']
        if not entries:
            return None
        info = entries[0]
 
    if 'url' not in info:
        return None
 
    return {'title': info.get('title', 'Inconnu'), 'stream_url': info['url']}
 
def split_lyrics(lyrics, max_length=2000):
    lines = lyrics.split("\n")
    parts = []
    current_part = ""
    for line in lines:
        if len(current_part) + len(line) + 1 > max_length:
            parts.append(current_part)
            current_part = ""
        current_part += line + "\n"
    if current_part:
        parts.append(current_part)
    return parts
 
 
@bot.tree.command(name="lyrics", description="Affiche les paroles d'une chanson")
async def lyrics(interaction: discord.Interaction, song_title: str):
    await interaction.response.defer()
    try:
        song = genius.search_song(song_title)
        if song:
            lyrics_parts = split_lyrics(song.lyrics)
            for part in lyrics_parts:
                await interaction.followup.send(f"```{part}```")
        else:
            await interaction.followup.send("Paroles non trouvées pour cette chanson.")
    except Exception as e:
        await interaction.followup.send(f"Erreur lors de la commande /lyrics: {e}")
 
 
@bot.tree.command(name="join", description="Rejoins un canal vocal")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message("Vous devez être dans un canal vocal!")
        return
    channel = interaction.user.voice.channel
    if interaction.guild.voice_client is None:
        await channel.connect(self_deaf=True, reconnect=True)
        await interaction.response.send_message(f"Connecté à {channel}")
    else:
        await interaction.guild.voice_client.move_to(channel)
        await interaction.response.send_message(f"Déplacé vers {channel}")
 
 
@bot.tree.command(name="play", description="Joue ou met en file une musique (URL ou titre)")
async def play(interaction: discord.Interaction, query: str):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
 
    if not voice_client:
        if not interaction.user.voice:
            await interaction.response.send_message(
                "❌ Tu dois être dans un canal vocal pour que je puisse te rejoindre.",
                ephemeral=True
            )
            return
        channel = interaction.user.voice.channel
        voice_client = await channel.connect(self_deaf=True, reconnect=True)
    elif interaction.user.voice and voice_client.channel != interaction.user.voice.channel:
        await voice_client.move_to(interaction.user.voice.channel)
 
    await interaction.response.defer()
 
    entry = await resolve_entry(query)
    if not entry:
        await interaction.followup.send("❌ Aucune vidéo trouvée pour ce titre.")
        return
 
    queue = get_queue(interaction.guild.id)
 
    if voice_client.is_playing() or voice_client.is_paused():
        queue.append(entry)
        pos = len(queue)
        schedule_prefetch(interaction.guild.id)
        await interaction.followup.send(f"📋 Ajouté à la file (position {pos}) : **{entry['title']}**")
    else:
        # play the song immediately
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -filter:a "volume=0.25"'
        }
 
        def after_playing(error):
            if error:
                print(f"Erreur lecture : {error}")
            fut = asyncio.run_coroutine_threadsafe(
                play_next_async(interaction.guild.id, voice_client), bot.loop
            )
            try:
                fut.result()
            except Exception as e:
                print(f"Erreur play_next : {e}")
 
        voice_client.play(
            discord.FFmpegOpusAudio(
                entry['stream_url'],
                executable="ffmpeg",
                **ffmpeg_options
            ),
            after=after_playing
        )
        schedule_prefetch(interaction.guild.id)
        await interaction.followup.send(f"▶️ Lecture de : **{entry['title']}**")
 
 
@bot.tree.command(name="queue", description="Affiche la file d'attente musicale")
async def queue_cmd(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    queue = get_queue(interaction.guild.id)
 
    if not queue and (not voice_client or not voice_client.is_playing()):
        await interaction.response.send_message("📭 La file est vide et rien ne joue.")
        return
 
    lines = []
    if voice_client and voice_client.is_playing():
        lines.append("**▶️ En cours de lecture**")
    if queue:
        lines.append(f"\n**📋 File d'attente ({len(queue)} morceau{'x' if len(queue) > 1 else ''}) :**")
        for i, entry in enumerate(queue, 1):
            lines.append(f"`{i}.` {entry['title']}")
    await interaction.response.send_message("\n".join(lines))
 
 
@bot.tree.command(name="remove", description="Supprime un morceau de la file par son numéro")
@app_commands.describe(position="Numéro du morceau à supprimer (voir /queue)")
async def remove(interaction: discord.Interaction, position: app_commands.Range[int, 1, 100]):
    queue = get_queue(interaction.guild.id)
    if position > len(queue):
        await interaction.response.send_message(
            f"❌ Il n'y a que {len(queue)} morceau(x) dans la file.", ephemeral=True
        )
        return
    removed = queue.pop(position - 1)
    task = removed.get('resolve_task')
    if task and not task.done():
        task.cancel()
    await interaction.response.send_message(f"🗑️ Supprimé de la file : **{removed['title']}**")
 
 
@bot.tree.command(name="clearqueue", description="Vide entièrement la file d'attente")
async def clearqueue(interaction: discord.Interaction):
    queue = get_queue(interaction.guild.id)
    if not queue:
        await interaction.response.send_message("La file est déjà vide.", ephemeral=True)
        return
    count = len(queue)
    for entry in queue:
        task = entry.get('resolve_task')
        if task and not task.done():
            task.cancel()
    queue.clear()
    await interaction.response.send_message(f"🗑️ File vidée ({count} morceau{'x' if count > 1 else ''} supprimé{'s' if count > 1 else ''}).")
 
 
@bot.tree.command(name="skip", description="Passe au morceau suivant dans la file")
async def skip(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client and voice_client.is_playing():
        voice_client.stop()  
        await interaction.response.send_message("⏭️ Morceau skipé.")
    else:
        await interaction.response.send_message("Il n'y a aucune musique en cours de lecture.")
 
 
@bot.tree.command(name="leave", description="Quitte le canal vocal et vide la file")
async def leave(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client:
        queue = get_queue(interaction.guild.id)
        for entry in queue:
            task = entry.get('resolve_task')
            if task and not task.done():
                task.cancel()
        queue.clear()
        await voice_client.disconnect()
        await interaction.response.send_message("👋 Déconnecté du canal vocal.")
    else:
        await interaction.response.send_message("Le bot n'est pas dans un canal vocal.")
 
 
class BlackjackView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.player_hand = [self.draw(), self.draw()]
        self.dealer_hand = [self.draw(), self.draw()]
        self.message = None
        self.game_over = False
 
    def draw(self):
        return random.choice([2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11])
 
    def hand_value(self, hand):
        value = sum(hand)
        aces = hand.count(11)
        while value > 21 and aces:
            value -= 10
            aces -= 1
        return value
 
    async def update_message(self):
        text = (
            f"🃏 **Blackjack !**\n\n"
            f"**Tes cartes** : {self.player_hand} = {self.hand_value(self.player_hand)}\n"
            f"**Carte visible du croupier** : {self.dealer_hand[0]}\n\n"
            f"**Choisis ton action :**"
        )
        await self.message.edit(content=text, view=self)
 
    @discord.ui.button(label="🔼 HIT", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game_over or interaction.user != self.ctx.author:
            return
        self.player_hand.append(self.draw())
        if self.hand_value(self.player_hand) > 21:
            await interaction.response.edit_message(
                content=f"💥 Tu as dépassé 21 ! Ta main : {self.player_hand} = {self.hand_value(self.player_hand)}\nCroupier gagne.",
                view=None
            )
            self.game_over = True
        else:
            await interaction.response.defer()
            await self.update_message()
 
    @discord.ui.button(label="🛑 STAND", style=discord.ButtonStyle.danger)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game_over or interaction.user != self.ctx.author:
            return
        while self.hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.draw())
        player = self.hand_value(self.player_hand)
        dealer = self.hand_value(self.dealer_hand)
        result = (
            f"🎲 **Résultat final :**\n\n"
            f"**Ta main** : {self.player_hand} = {player}\n"
            f"**Main du croupier** : {self.dealer_hand} = {dealer}\n\n"
        )
        if dealer > 21 or player > dealer:
            result += "🎉 Tu gagnes !"
        elif player < dealer:
            result += "😞 Tu perds !"
        else:
            result += "🤝 Égalité !"
        await interaction.response.edit_message(content=result, view=None)
        self.game_over = True
 
 
@bot.command()
async def blackjack(ctx):
    view = BlackjackView(ctx)
    msg = await ctx.send("Chargement du jeu...", view=view)
    view.message = msg
    await view.update_message()
 
 
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot connecté en tant que {bot.user}")

@bot.event
async def on_member_join(member):
    welcome_channel = discord.utils.get(member.guild.text_channels, name="bienvenue")
    if welcome_channel:
        await welcome_channel.send(f"{member.mention} https://klipy.com/gifs/welcome-michael-scott")
 
 
async def main():
    async with bot:
        await bot.load_extension("cog_onepiece")
        await bot.start(TOKEN)
 
 
if __name__ == "__main__":
    asyncio.run(main())