from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from music_bot.application.orchestration.playlists import PlaylistService
from music_bot.application.orchestration.track_service import TrackService
from music_bot.application.ports.music import GuildPlaybackRepository
from music_bot.application.ports.music_player import GuildPlayer, GuildPlayerFactory
from music_bot.application.ports.uow import UoWFactory
from music_bot.domain.music.models import GuildPlayback

from .guild_playback_actor import GuildPlaybackActor

logger: logging.Logger = logging.getLogger(__name__)


class GuildPlaybackActorRegistry:
    def __init__(
        self,
        *,
        playback_repository: GuildPlaybackRepository,
        player_factory: GuildPlayerFactory,
        playlist_service: PlaylistService,
        track_service: TrackService,
        uow_factory: UoWFactory,
    ) -> None:
        self._playback_repository: GuildPlaybackRepository = playback_repository
        self._player_factory: GuildPlayerFactory = player_factory
        self._playlist_service: PlaylistService = playlist_service
        self._track_service: TrackService = track_service
        self._uow_factory: UoWFactory = uow_factory
        self._actors: dict[int, GuildPlaybackActor] = {}

    def get(self, *, guild_id: int) -> GuildPlaybackActor | None:
        actor: GuildPlaybackActor | None = self._actors.get(guild_id)
        logger.debug("Playback actor lookup guild_id=%s found=%s", guild_id, actor is not None)
        return actor

    async def create_or_restore(self, *, guild_id: int) -> GuildPlaybackActor:
        logger.info("Playback actor creation started guild_id=%s", guild_id)
        if guild_id in self._actors:
            raise RuntimeError(f"GuildPlaybackActor already exists for guild {guild_id}")

        restored: GuildPlayback | None = await self._playback_repository.get(guild_id=guild_id)
        if restored is not None and restored.guild_id != guild_id:
            raise ValueError("Restored playback belongs to another guild")
        playback: GuildPlayback = restored or GuildPlayback(guild_id=guild_id)
        logger.info(
            "Playback state loaded guild_id=%s restored=%s queue_size=%s "
            "paused=%s volume=%s loop=%s",
            guild_id,
            restored is not None,
            playback.track_count,
            playback.is_paused,
            playback.volume,
            playback.loop_current,
        )

        player: GuildPlayer = self._player_factory(guild_id)
        actor: GuildPlaybackActor = GuildPlaybackActor(
            playback=playback,
            playback_repository=self._playback_repository,
            player=player,
            playlist_service=self._playlist_service,
            track_service=self._track_service,
            uow_factory=self._uow_factory,
            terminated_callback=self._remove_terminated_actor,
        )
        actor.start()
        self._actors[guild_id] = actor
        logger.info("Playback actor registered guild_id=%s", guild_id)
        return actor

    async def remove(self, *, guild_id: int) -> None:
        logger.info("Playback actor removal started guild_id=%s", guild_id)
        await self._playback_repository.delete(guild_id=guild_id)

        actor: GuildPlaybackActor | None = self._actors.pop(guild_id, None)
        if actor is not None:
            await actor.close()
        logger.info(
            "Playback actor removal completed guild_id=%s existed=%s",
            guild_id,
            actor is not None,
        )

    async def shutdown(self) -> None:
        actors: Iterable[GuildPlaybackActor] = self._actors.values()
        logger.info("Playback actor registry shutdown started actor_count=%s", len(self._actors))
        await asyncio.gather(*(actor.close() for actor in actors))
        self._actors.clear()
        logger.info("Playback actor registry shutdown completed")

    def _remove_terminated_actor(self, actor: GuildPlaybackActor) -> None:
        if self._actors.get(actor.guild_id) is actor:
            self._actors.pop(actor.guild_id)
            logger.info("Terminated playback actor unregistered guild_id=%s", actor.guild_id)
