from __future__ import annotations

import asyncio
from dataclasses import dataclass

from music_bot.application.contracts.commands.music import PlayUrlCommand
from music_bot.application.contracts.errors import TrackMetadataResolutionError
from music_bot.application.contracts.results.music import PlayUrlResult
from music_bot.application.mappers.music import map_track_to_dto
from music_bot.application.ports.track_source import TrackMetadata, TrackMetadataResolver
from music_bot.domain.music.models import GuildPlayback, Queue, Track

_RESOLVE_TIMEOUT_SECONDS: float = 30.0


@dataclass(frozen=True, slots=True, kw_only=True)
class PlayUrlHandling:
    playback: GuildPlayback
    result: PlayUrlResult


class PlayUrlCommandHandler:
    def __init__(self, *, metadata_resolver: TrackMetadataResolver) -> None:
        self._metadata_resolver: TrackMetadataResolver = metadata_resolver

    async def handle(
        self,
        command: PlayUrlCommand,
        *,
        playback: GuildPlayback | None,
    ) -> PlayUrlHandling:
        # The guild actor processes commands one at a time off a single
        # mailbox — a resolver call that never returns wedges every other
        # command for this guild indefinitely, not just this one. Bound it.
        try:
            metadata: TrackMetadata = await asyncio.wait_for(
                self._metadata_resolver.resolve(source_url=command.url),
                timeout=_RESOLVE_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            raise TrackMetadataResolutionError(
                f"Resolving the track timed out after {_RESOLVE_TIMEOUT_SECONDS:.0f}s"
            ) from exc
        track: Track = Track(
            url=metadata.source_url,
            title=metadata.title,
            requested_by=command.requested_by,
            duration_seconds=metadata.duration_seconds,
        )

        if playback is None:
            playback = GuildPlayback(
                guild_id=command.guild_id,
                queue=Queue((track,)),
            )
        else:
            playback.enqueue(track)

        return PlayUrlHandling(
            playback=playback,
            result=PlayUrlResult(
                track=map_track_to_dto(track),
                queue_size=playback.track_count,
            ),
        )
