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

# Playlist : guild_id -> list of dicts {title, url}
music_queues = {}

def get_queue(guild_id):
    if guild_id not in music_queues:
        music_queues[guild_id] = []
    return music_queues[guild_id]

def play_next(guild_id, voice_client):
    """Joue le prochain morceau dans la file, si elle n'est pas vide."""
    queue = get_queue(guild_id)
    if not queue:
        return

    entry = queue.pop(0)

    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn -filter:a "volume=0.25"'
    }

    def after_playing(error):
        if error:
            print(f"Erreur lecture : {error}")
        # Lance la suivante depuis le thread asyncio
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
            executable="ffmpeg-2026-04-06-git-7fd2be97b9-full_build/bin/ffmpeg.exe",
            **ffmpeg_options
        ),
        after=after_playing
    )

async def play_next_async(guild_id, voice_client):
    """Version async de play_next (appelée depuis le callback after)."""
    queue = get_queue(guild_id)
    if not queue or voice_client.is_playing():
        return

    entry = queue.pop(0)

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
            executable="ffmpeg-2026-04-06-git-7fd2be97b9-full_build/bin/ffmpeg.exe",
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
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission de déconnecter des membres.", ephemeral=True)
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
    if not interaction.user.guild_permissions.mute_members:
        await interaction.response.send_message("❌ Tu n'as pas la permission de mute.", ephemeral=True)
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
    'cookiesfrombrowser': ('firefox',),
    'js_runtimes': {'node': {}},
}

async def search_youtube(query):
    ydl_opts = {**YDL_OPTS_BASE, 'noplaylist': True}
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            requests = ydl.extract_info(f"ytsearch:{query}", download=False)['entries']
        except Exception:
            return None
        return requests[0] if requests else None

async def resolve_entry(query):
    """Résout une URL ou un titre en dict {title, stream_url}."""
    ydl_opts = YDL_OPTS_BASE
    if "youtube.com" not in query and "youtu.be" not in query:
        video = await search_youtube(query)
        if not video:
            return None
        query = video['webpage_url']
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(query, download=False)
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
        await interaction.response.send_message("❌ Le bot n'est pas connecté à un canal vocal.")
        return

    await interaction.response.defer()

    entry = await resolve_entry(query)
    if not entry:
        await interaction.followup.send("❌ Aucune vidéo trouvée pour ce titre.")
        return

    queue = get_queue(interaction.guild.id)

    if voice_client.is_playing() or voice_client.is_paused():
        # add in queue if song already playing
        queue.append(entry)
        pos = len(queue)
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
                executable="ffmpeg-2026-04-06-git-7fd2be97b9-full_build/bin/ffmpeg.exe",
                **ffmpeg_options
            ),
            after=after_playing
        )
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
    await interaction.response.send_message(f"🗑️ Supprimé de la file : **{removed['title']}**")


@bot.tree.command(name="clearqueue", description="Vide entièrement la file d'attente")
async def clearqueue(interaction: discord.Interaction):
    queue = get_queue(interaction.guild.id)
    if not queue:
        await interaction.response.send_message("La file est déjà vide.", ephemeral=True)
        return
    count = len(queue)
    queue.clear()
    await interaction.response.send_message(f"🗑️ File vidée ({count} morceau{'x' if count > 1 else ''} supprimé{'s' if count > 1 else ''}).")


@bot.tree.command(name="skip", description="Passe au morceau suivant dans la file")
async def skip(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client and voice_client.is_playing():
        voice_client.stop()  # déclenche after_playing → play_next_async
        await interaction.response.send_message("⏭️ Morceau skipé.")
    else:
        await interaction.response.send_message("Il n'y a aucune musique en cours de lecture.")


@bot.tree.command(name="leave", description="Quitte le canal vocal et vide la file")
async def leave(interaction: discord.Interaction):
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client:
        get_queue(interaction.guild.id).clear()
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


bot.run(TOKEN)
