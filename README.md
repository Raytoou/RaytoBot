# RaytoBot

Bot Discord musique + modération + mini-jeux, écrit avec `discord.py`.

## Fonctionnalités

- **Musique** : `/join`, `/play`, `/queue`, `/remove`, `/clearqueue`, `/skip`, `/leave` (recherche YouTube ou URL directe, file d'attente par serveur)
- **Paroles** : `/lyrics` (via l'API Genius)
- **Modération** : `/dc`, `/stopdc` (déconnexion vocale en boucle), `/mute`, `/unmute` (mute vocal forcé), `/snipe` (récupère le dernier message supprimé)
- **Fun** : `/janga` (stock virtuel par utilisateur), `!blackjack` (mini-jeu avec boutons)

## Prérequis

- Python 3.10+
- [ffmpeg](https://ffmpeg.org/download.html) accessible localement (le bot utilise un binaire dans un dossier `ffmpeg-*-full_build/bin/ffmpeg.exe` à côté de `main.py` — adapte le chemin dans `main.py` si tu utilises une autre installation)
- Firefox installé sur la machine (yt-dlp récupère les cookies du navigateur via `cookiesfrombrowser`)
- Un token de bot Discord et un token API Genius

## Installation

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Copie `.env.example` en `.env` et renseigne tes tokens :

```
DISCORD_TOKEN=ton_token_discord
GENIUS_TOKEN=ton_token_genius
```

## Lancement

```bash
start.bat
```

ou directement :

```bash
venv\Scripts\python.exe main.py
```

## Notes

- Les intents `message_content`, `guilds` et `voice_states` doivent être activés dans le portail développeur Discord.
- Le fichier `.env` n'est jamais versionné (voir `.gitignore`).
