from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import cast

from music_bot.application.contracts.commands.music import (
    GetQueueCommand,
    NowPlayingCommand,
    PauseCommand,
    PlaybackCommand,
    PlayPlaylistCommand,
    PlayUrlCommand,
    ResumeCommand,
    SetLoopCommand,
    SetVolumeCommand,
    ShuffleCommand,
    SkipCommand,
    StopCommand,
)
from music_bot.application.contracts.results.music import PlaybackResult
from music_bot.application.orchestration.playlists import PlaylistService
from music_bot.application.orchestration.track_service import TrackService
from music_bot.application.ports.music_player import GuildPlayer
from music_bot.application.ports.uow import UoWFactory
from music_bot.domain.music.models import GuildPlayback

from .handlers import (
    CommandHandler,
    GetQueueCommandHandler,
    HandlerOutcome,
    NowPlayingCommandHandler,
    PauseCommandHandler,
    PlayPlaylistCommandHandler,
    PlayUrlCommandHandler,
    ResumeCommandHandler,
    SetLoopCommandHandler,
    SetVolumeCommandHandler,
    ShuffleCommandHandler,
    SkipCommandHandler,
    StopCommandHandler,
)

logger: logging.Logger = logging.getLogger(__name__)

type RegisteredCommandHandler = Callable[
    [PlaybackCommand],
    Awaitable[HandlerOutcome[PlaybackResult]],
]


class PlaybackCommandDispatcher:
    def __init__(
        self,
        *,
        playback: GuildPlayback,
        player: GuildPlayer,
        playlist_service: PlaylistService,
        track_service: TrackService,
        uow_factory: UoWFactory,
        start_playback: Callable[[], Awaitable[None]],
    ) -> None:
        self._handlers: dict[type[PlaybackCommand], RegisteredCommandHandler] = {}

        play_url_handler: PlayUrlCommandHandler = PlayUrlCommandHandler(
            playback=playback,
            track_service=track_service,
            uow_factory=uow_factory,
            start_playback=start_playback,
        )
        self._register(PlayUrlCommand, play_url_handler)
        self._register(
            PlayPlaylistCommand,
            PlayPlaylistCommandHandler(
                playlist_service=playlist_service,
                play_url_handler=play_url_handler,
            ),
        )

        self._register(
            StopCommand,
            StopCommandHandler(playback=playback, player=player),
        )
        self._register(
            SkipCommand,
            SkipCommandHandler(
                playback=playback,
                player=player,
            ),
        )
        self._register(
            NowPlayingCommand,
            NowPlayingCommandHandler(playback=playback),
        )
        self._register(
            PauseCommand,
            PauseCommandHandler(playback=playback, player=player),
        )
        self._register(
            ResumeCommand,
            ResumeCommandHandler(playback=playback, player=player),
        )
        self._register(GetQueueCommand, GetQueueCommandHandler(playback=playback))
        self._register(
            ShuffleCommand,
            ShuffleCommandHandler(
                playback=playback,
                player=player,
            ),
        )
        self._register(SetLoopCommand, SetLoopCommandHandler(playback=playback))
        self._register(
            SetVolumeCommand,
            SetVolumeCommandHandler(playback=playback, player=player),
        )
        logger.debug(
            "Playback command dispatcher initialized handlers=%s",
            ",".join(command_type.__name__ for command_type in self._handlers),
        )

    def _register[
        CommandT: PlaybackCommand,
        ResultT: PlaybackResult,
    ](
        self,
        command_type: type[CommandT],
        handler: CommandHandler[CommandT, ResultT],
    ) -> None:
        async def registered(
            command: PlaybackCommand,
        ) -> HandlerOutcome[PlaybackResult]:
            outcome: HandlerOutcome[ResultT] = await handler.handle(cast(CommandT, command))
            return cast(HandlerOutcome[PlaybackResult], outcome)

        self._handlers[command_type] = registered
        logger.debug(
            "Playback command handler registered command=%s handler=%s",
            command_type.__name__,
            type(handler).__name__,
        )

    async def handle(self, command: PlaybackCommand) -> HandlerOutcome[PlaybackResult]:
        command_type: type[PlaybackCommand] = type(command)
        handler: RegisteredCommandHandler | None = self._handlers.get(command_type)
        if handler is None:
            logger.error("Playback command handler missing command=%s", command_type.__name__)
            raise LookupError(f"No handler registered for {command_type.__name__}")

        logger.debug(
            "Playback command dispatch started command=%s guild_id=%s",
            command_type.__name__,
            command.guild_id,
        )
        outcome: HandlerOutcome[PlaybackResult] = await handler(command)
        logger.debug(
            "Playback command dispatch completed command=%s guild_id=%s result=%s "
            "mutated=%s interrupts=%s restart=%s",
            command_type.__name__,
            command.guild_id,
            type(outcome.result).__name__,
            outcome.mutated,
            outcome.interrupts_current_track,
            outcome.restart_playback,
        )
        return outcome
