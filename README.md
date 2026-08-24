# MusicBot

A Discord music bot with per-guild queues, playlists, and Postgres/Redis-backed persistence.

## Commands

### General

| Command | Description |
| --- | --- |
| `/ping` | Shows the bot's Discord gateway latency. |

### Voice

| Command | Description |
| --- | --- |
| `/join` | Joins your current voice channel. |
| `/leave` | Stops playback, clears the queue, and disconnects. |

### Playback

| Command | Description |
| --- | --- |
| `/play <url>` | Queues a track (joins voice automatically if needed). |
| `/pause` / `/resume` | Pauses or resumes the current track. |
| `/skip` | Clears pause state and skips to the next track in the queue. |
| `/stop` | Stops playback and clears the queue. |
| `/queue` | Shows the current queue. |
| `/nowplaying` | Shows what's currently playing. |
| `/shuffle` | Shuffles the queue. |
| `/loop <enabled>` | Enables or disables looping the current track. |
| `/volume <level>` | Sets playback volume (0–100). |

### Playlist

| Command | Description |
| --- | --- |
| `/playlist create <title> <access>` | Creates a new playlist, private or public. |
| `/playlist rename <playlist> <title>` | Renames one of your playlists. |
| `/playlist visibility <playlist> <access>` | Changes a playlist's visibility. |
| `/playlist delete <playlist>` | Deletes one of your playlists. |
| `/playlist mine` | Lists your own playlists. |
| `/playlist show <playlist>` | Shows a playlist's tracks (yours, or a public one). |
| `/playlist add <playlist> <url>` | Adds a track to one of your playlists. |
| `/playlist remove <playlist> <position>` | Removes a track by its position. |
| `/playlist play <playlist>` | Queues every track from a playlist (yours, or a public one). |

Playlists are either **private** (only the owner can see or play them) or
**public** (anyone can see and play them, only the owner can edit them).
Access is enforced server-side regardless of what's shown in Discord's
autocomplete — a playlist's ID alone isn't enough to read a private one.

## Runtime and persistence

- Postgres stores users, playlists, and the track metadata catalog.
- Redis stores active per-guild playback state. Its TTL is controlled by
  `REDIS_PLAYBACK_TTL_SECONDS` and defaults to 24 hours.

`LOG_LEVEL` defaults to `DEBUG`, which includes detailed use-case, persistence,
and voice lifecycle logs. Set it to `INFO` for less verbose runtime output.

## Running with Docker Compose

1. Copy the environment template and fill in your bot token:

   ```bash
   cp .env.example .env
   ```

   At minimum, set `DISCORD_TOKEN` (from the
   [Discord Developer Portal](https://discord.com/developers/applications)).
   `DISCORD_GUILD_ID` is optional — set it during development to sync slash
   commands to one guild instantly instead of waiting for the global sync.

2. Start everything:

   ```bash
   docker compose up --build
   ```

   This starts Postgres, Redis, and the bot. Database migrations run
   automatically on container start.

## Running locally without Docker

Requires Python 3.13+, a running Postgres and Redis, `ffmpeg` on `PATH`, and an
Opus runtime library.

```bash
pip install -e ".[dev]"
cp .env.example .env  # point DATABASE_URL/REDIS_URL at your own instances
alembic upgrade head
python -m music_bot
```

## Development

```bash
ruff format --check .
ruff check .
mypy src tests
pytest -m unit
```

Run `pytest -m integration` for the Postgres and Redis integration tests, or
`pytest` for the complete suite. Integration tests skip when their required
service is unavailable.
