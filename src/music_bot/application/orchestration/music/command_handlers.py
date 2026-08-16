from __future__ import annotations

from collections.abc import Awaitable, Callable

from music_bot.application.contracts.commands.music import (
    GetQueueCommand,
    NowPlayingCommand,
    PauseCommand,
    PlaybackCommand,
    ResumeCommand,
    SetLoopCommand,
    SetVolumeCommand,
    ShuffleCommand,
    SkipCommand,
    StopCommand,
)
from music_bot.application.contracts.results.music import PlaybackResult
from music_bot.application.ports.music_player import GuildPlayer
from music_bot.domain.music.models import GuildPlayback

from .handlers import (
    CommandHandler,
    GetQueueCommandHandler,
    HandlerOutcome,
    NowPlayingCommandHandler,
    PauseCommandHandler,
    ResumeCommandHandler,
    SetLoopCommandHandler,
    SetVolumeCommandHandler,
    ShuffleCommandHandler,
    SkipCommandHandler,
    StopCommandHandler,
)

type RegisteredCommandHandler = Callable[..., Awaitable[HandlerOutcome[PlaybackResult]]]


class PlaybackCommandDispatcher:
    def __init__(
        self,
        *,
        playback: GuildPlayback,
        player: GuildPlayer,
    ) -> None:
        self._handlers: dict[type[PlaybackCommand], RegisteredCommandHandler] = {}

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

    def _register[
        CommandT: PlaybackCommand,
        ResultT: PlaybackResult,
    ](
        self,
        command_type: type[CommandT],
        handler: CommandHandler[CommandT, ResultT],
    ) -> None:
        self._handlers[command_type] = handler.handle

    async def handle(self, command: PlaybackCommand) -> HandlerOutcome[PlaybackResult]:
        command_type: type[PlaybackCommand] = type(command)
        handler: RegisteredCommandHandler | None = self._handlers.get(command_type)
        if handler is None:
            raise LookupError(f"No handler registered for {command_type.__name__}")

        return await handler(command)
