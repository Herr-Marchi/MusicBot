from __future__ import annotations

from dataclasses import dataclass

from music_bot.adapters.inbound.discord.voice_manager import DiscordVoiceManager
from music_bot.application.orchestration.music import GuildPlaybackActorManager
from music_bot.application.orchestration.playlists import PlaylistService


@dataclass(frozen=True, slots=True, kw_only=True)
class DiscordDependencies:
    voice_manager: DiscordVoiceManager
    playback_manager: GuildPlaybackActorManager
    playlist_service: PlaylistService
