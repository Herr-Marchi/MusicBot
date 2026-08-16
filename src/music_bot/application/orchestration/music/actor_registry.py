from __future__ import annotations

import asyncio
from collections.abc import Iterable

from music_bot.application.ports.music import GuildPlaybackRepository
from music_bot.application.ports.music_player import GuildPlayer, GuildPlayerFactory
from music_bot.application.ports.track_source import TrackMetadataResolver
from music_bot.domain.music.models import GuildPlayback

from .guild_playback_actor import GuildPlaybackActor


class GuildPlaybackActorRegistry:
    def __init__(
        self,
        *,
        playback_repository: GuildPlaybackRepository,
        player_factory: GuildPlayerFactory,
        metadata_resolver: TrackMetadataResolver,
    ) -> None:
        self._playback_repository: GuildPlaybackRepository = playback_repository
        self._player_factory: GuildPlayerFactory = player_factory
        self._metadata_resolver: TrackMetadataResolver = metadata_resolver
        self._actors: dict[int, GuildPlaybackActor] = {}

    def get(self, *, guild_id: int) -> GuildPlaybackActor | None:
        return self._actors.get(guild_id)

    async def create_or_restore(self, *, guild_id: int) -> GuildPlaybackActor:
        if guild_id in self._actors:
            raise RuntimeError(f"GuildPlaybackActor already exists for guild {guild_id}")

        playback: GuildPlayback | None = await self._playback_repository.get(guild_id=guild_id)
        if playback is not None and playback.guild_id != guild_id:
            raise ValueError("Restored playback belongs to another guild")

        player: GuildPlayer = self._player_factory(guild_id)
        actor: GuildPlaybackActor = GuildPlaybackActor(
            guild_id=guild_id,
            playback=playback,
            playback_repository=self._playback_repository,
            player=player,
            metadata_resolver=self._metadata_resolver,
            terminated_callback=self._remove_terminated_actor,
        )
        actor.start()
        self._actors[guild_id] = actor
        return actor

    async def remove(self, *, guild_id: int) -> None:
        await self._playback_repository.delete(guild_id=guild_id)

        actor: GuildPlaybackActor | None = self._actors.pop(guild_id, None)
        if actor is not None:
            await actor.close()

    async def shutdown(self) -> None:
        actors: Iterable[GuildPlaybackActor] = self._actors.values()
        await asyncio.gather(*(actor.close() for actor in actors))
        self._actors.clear()

    def _remove_terminated_actor(self, actor: GuildPlaybackActor) -> None:
        if self._actors.get(actor.guild_id) is actor:
            self._actors.pop(actor.guild_id)
