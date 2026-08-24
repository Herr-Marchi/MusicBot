from __future__ import annotations

import asyncio
from typing import cast

import pytest
from tests.fakes import FakeGuildPlayer, FakeTrackSource, FakeUoWFactory
from tests.typing_helper import MakePlayUrlCommand, MakeSkipCommand, MakeStopCommand
from tests.unit.application.orchestration.music.conftest import MakeActor

from music_bot.adapters.outbound.in_memory.music import InMemoryGuildPlaybackRepository
from music_bot.application.contracts.commands.music import (
    GetQueueCommand,
    NowPlayingCommand,
    PauseCommand,
    PlayPlaylistCommand,
    PlayUrlCommand,
    ResumeCommand,
    SetLoopCommand,
    SetVolumeCommand,
    StopCommand,
)
from music_bot.application.contracts.results.music import (
    GetQueueResult,
    NowPlayingResult,
    PauseResult,
    PlayPlaylistResult,
    PlayUrlResult,
    ResumeResult,
    SetLoopResult,
    SetVolumeResult,
    SkipResult,
    StopResult,
)
from music_bot.application.orchestration.music.guild_playback_actor import GuildPlaybackActor
from music_bot.application.orchestration.music.handlers import PlayUrlCommandHandler
from music_bot.application.orchestration.playlists import PlaylistService
from music_bot.application.orchestration.track_service import TrackService
from music_bot.application.ports.track_source import (
    TrackMetadata,
    TrackSource,
    TrackSourceError,
)
from music_bot.domain.music.models import GuildPlayback
from music_bot.domain.playlists.models import PlaylistAccess


class HangingTrackSource(TrackSource):
    def __init__(self) -> None:
        self.started: asyncio.Event = asyncio.Event()

    async def validate_url(self, *, source_url: str) -> TrackSource:
        return self

    async def _resolve_metadata(self, *, source_url: str) -> TrackMetadata:
        self.started.set()
        await asyncio.sleep(10)
        raise AssertionError("metadata resolution should have been abandoned")

    async def _resolve_stream(self, *, source_url: str) -> str:
        raise AssertionError("stream resolution is not expected")


async def _create_playlist(
    *,
    playlist_service: PlaylistService,
    fake_track_source: FakeTrackSource,
    tracks: list[tuple[str, str]],
) -> str:
    playlist = await playlist_service.create(
        owner_id=1,
        owner_username="owner",
        title="Playlist",
        access=PlaylistAccess.PRIVATE,
    )
    for url, title in tracks:
        fake_track_source.set_metadata(url, title=title)
        await playlist_service.add_track(
            playlist_id=playlist.id,
            requested_by=1,
            url=url,
        )
    return playlist.id


@pytest.mark.unit
class TestGuildPlaybackActorLifecycle:
    async def test_start_twice_raises(self, make_actor: MakeActor) -> None:
        actor: GuildPlaybackActor = make_actor()
        actor.start()

        try:
            with pytest.raises(RuntimeError):
                actor.start()
        finally:
            await actor.close()

    async def test_execute_before_start_raises(
        self,
        make_actor: MakeActor,
        make_play_url_command: MakePlayUrlCommand,
    ) -> None:
        actor: GuildPlaybackActor = make_actor()

        with pytest.raises(RuntimeError):
            await actor.execute(make_play_url_command())

    async def test_close_before_start_is_noop(self, make_actor: MakeActor) -> None:
        actor: GuildPlaybackActor = make_actor()

        await actor.close()

    async def test_execute_wrong_guild_raises(
        self,
        running_actor: GuildPlaybackActor,
        make_play_url_command: MakePlayUrlCommand,
    ) -> None:
        command: PlayUrlCommand = make_play_url_command(guild_id=running_actor.guild_id + 1)

        with pytest.raises(ValueError):
            await running_actor.execute(command)


@pytest.mark.unit
class TestPlayUrl:
    async def test_fresh_actor_activates_starts_playback_and_persists(
        self,
        running_actor: GuildPlaybackActor,
        fake_player: FakeGuildPlayer,
        fake_track_source: FakeTrackSource,
        fake_uow_factory: FakeUoWFactory,
        playback_repository: InMemoryGuildPlaybackRepository,
        make_play_url_command: MakePlayUrlCommand,
    ) -> None:
        fake_track_source.set_metadata(
            "https://example.com/a.mp3", title="Song A", duration_seconds=180
        )
        command: PlayUrlCommand = make_play_url_command(url="https://example.com/a.mp3")
        uow_count_before_play: int = len(fake_uow_factory.uows)

        result: PlayUrlResult = cast(PlayUrlResult, await running_actor.execute(command))

        assert result.track.title == "Song A"
        assert result.queue_size == 1
        assert fake_player.play_calls == [("https://example.com/a.mp3", 100)]
        assert len(fake_uow_factory.uows) == uow_count_before_play + 1
        assert fake_uow_factory.uows[-1].commit_calls == 1

        saved: GuildPlayback | None = await playback_repository.get(guild_id=running_actor.guild_id)
        assert saved is not None
        assert saved.track_count == 1

    async def test_second_track_enqueues_without_restarting_playback(
        self,
        running_actor: GuildPlaybackActor,
        fake_player: FakeGuildPlayer,
        fake_track_source: FakeTrackSource,
        make_play_url_command: MakePlayUrlCommand,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        fake_track_source.set_metadata("https://example.com/b.mp3", title="Song B")

        await running_actor.execute(make_play_url_command(url="https://example.com/a.mp3"))
        result: PlayUrlResult = cast(
            PlayUrlResult,
            await running_actor.execute(make_play_url_command(url="https://example.com/b.mp3")),
        )

        assert result.queue_size == 2
        assert fake_player.play_calls == [("https://example.com/a.mp3", 100)]

    async def test_metadata_failure_on_first_track_terminates_actor(
        self,
        running_actor: GuildPlaybackActor,
        fake_track_source: FakeTrackSource,
        terminated_guild_ids: list[int],
        make_play_url_command: MakePlayUrlCommand,
    ) -> None:
        fake_track_source.fail_resolve_with(TrackSourceError("no such video"))

        with pytest.raises(TrackSourceError):
            await running_actor.execute(make_play_url_command())

        assert terminated_guild_ids == [running_actor.guild_id]

    async def test_hung_resolver_times_out_instead_of_wedging_the_actor(
        self,
        fake_player: FakeGuildPlayer,
        playback_repository: InMemoryGuildPlaybackRepository,
        terminated_guild_ids: list[int],
        make_play_url_command: MakePlayUrlCommand,
        monkeypatch: pytest.MonkeyPatch,
        fake_uow_factory: FakeUoWFactory,
        playlist_service: PlaylistService,
    ) -> None:
        monkeypatch.setattr(PlayUrlCommandHandler, "_RESOLVE_TIMEOUT_SECONDS", 0.05)
        resolver = HangingTrackSource()
        actor = GuildPlaybackActor(
            playback=GuildPlayback(guild_id=1),
            playback_repository=playback_repository,
            player=fake_player,
            playlist_service=playlist_service,
            track_service=TrackService(source=resolver),
            uow_factory=fake_uow_factory,
            terminated_callback=lambda a: terminated_guild_ids.append(a.guild_id),
        )
        actor.start()

        try:
            with pytest.raises(TrackSourceError):
                await asyncio.wait_for(actor.execute(make_play_url_command()), timeout=1)
        finally:
            await actor.close()

        assert terminated_guild_ids == [actor.guild_id]


@pytest.mark.unit
class TestPlayPlaylist:
    async def test_empty_playlist_returns_without_persisting_empty_playback(
        self,
        running_actor: GuildPlaybackActor,
        playlist_service: PlaylistService,
        terminated_guild_ids: list[int],
        playback_repository: InMemoryGuildPlaybackRepository,
    ) -> None:
        playlist = await playlist_service.create(
            owner_id=1,
            owner_username="owner",
            title="Empty",
            access=PlaylistAccess.PRIVATE,
        )

        result = await running_actor.execute(
            PlayPlaylistCommand(
                guild_id=running_actor.guild_id,
                requested_by=1,
                playlist_id=playlist.id,
            )
        )

        assert result.queued_count == 0
        assert terminated_guild_ids == [running_actor.guild_id]
        assert await playback_repository.get(guild_id=running_actor.guild_id) is None

    async def test_fresh_actor_batch_activates_and_starts_playback(
        self,
        running_actor: GuildPlaybackActor,
        fake_player: FakeGuildPlayer,
        fake_track_source: FakeTrackSource,
        playback_repository: InMemoryGuildPlaybackRepository,
        playlist_service: PlaylistService,
    ) -> None:
        playlist_id: str = await _create_playlist(
            playlist_service=playlist_service,
            fake_track_source=fake_track_source,
            tracks=[
                ("https://example.com/a.mp3", "Song A"),
                ("https://example.com/b.mp3", "Song B"),
            ],
        )
        command = PlayPlaylistCommand(
            guild_id=running_actor.guild_id,
            requested_by=1,
            playlist_id=playlist_id,
        )

        result: PlayPlaylistResult = cast(PlayPlaylistResult, await running_actor.execute(command))

        assert result.queued_count == 2
        assert result.started_playing is True
        # only the first track actually started audio — the rest just queued
        assert fake_player.play_calls == [("https://example.com/a.mp3", 100)]

        saved: GuildPlayback | None = await playback_repository.get(guild_id=running_actor.guild_id)
        assert saved is not None
        assert saved.track_count == 2

    async def test_batch_on_active_playback_appends_without_restarting(
        self,
        running_actor: GuildPlaybackActor,
        fake_player: FakeGuildPlayer,
        fake_track_source: FakeTrackSource,
        make_play_url_command: MakePlayUrlCommand,
        playlist_service: PlaylistService,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        await running_actor.execute(make_play_url_command(url="https://example.com/a.mp3"))
        playlist_id: str = await _create_playlist(
            playlist_service=playlist_service,
            fake_track_source=fake_track_source,
            tracks=[
                ("https://example.com/b.mp3", "Song B"),
                ("https://example.com/c.mp3", "Song C"),
            ],
        )

        command = PlayPlaylistCommand(
            guild_id=running_actor.guild_id,
            requested_by=1,
            playlist_id=playlist_id,
        )
        result: PlayPlaylistResult = cast(PlayPlaylistResult, await running_actor.execute(command))

        assert result.queued_count == 2
        assert result.started_playing is False
        assert fake_player.play_calls == [("https://example.com/a.mp3", 100)]

    async def test_failure_after_first_track_preserves_partial_queue(
        self,
        running_actor: GuildPlaybackActor,
        fake_player: FakeGuildPlayer,
        fake_track_source: FakeTrackSource,
        fake_uow_factory: FakeUoWFactory,
        playback_repository: InMemoryGuildPlaybackRepository,
        playlist_service: PlaylistService,
        terminated_guild_ids: list[int],
    ) -> None:
        first_url = "https://example.com/first.mp3"
        broken_url = "https://example.com/broken.mp3"
        playlist_id: str = await _create_playlist(
            playlist_service=playlist_service,
            fake_track_source=fake_track_source,
            tracks=[
                (first_url, "First"),
                (broken_url, "Broken"),
            ],
        )
        fake_uow_factory.track_repository.forget(broken_url)
        fake_track_source.fail_resolve_with(TrackSourceError("broken track"))

        with pytest.raises(TrackSourceError, match="broken track"):
            await running_actor.execute(
                PlayPlaylistCommand(
                    guild_id=running_actor.guild_id,
                    requested_by=1,
                    playlist_id=playlist_id,
                )
            )

        saved = await playback_repository.get(guild_id=running_actor.guild_id)
        assert saved is not None
        assert [track.url for track in saved.tracks] == [first_url]
        assert fake_player.play_calls == [(first_url, 100)]
        assert terminated_guild_ids == []


@pytest.mark.unit
class TestSkip:
    async def test_skip_stops_current_track_and_starts_next(
        self,
        running_actor: GuildPlaybackActor,
        fake_player: FakeGuildPlayer,
        fake_track_source: FakeTrackSource,
        playback_repository: InMemoryGuildPlaybackRepository,
        make_play_url_command: MakePlayUrlCommand,
        make_skip_command: MakeSkipCommand,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        fake_track_source.set_metadata("https://example.com/b.mp3", title="Song B")
        await running_actor.execute(make_play_url_command(url="https://example.com/a.mp3"))
        await running_actor.execute(make_play_url_command(url="https://example.com/b.mp3"))

        result: SkipResult = cast(
            SkipResult,
            await running_actor.execute(make_skip_command(guild_id=running_actor.guild_id)),
        )

        assert result.now_playing is not None
        assert result.now_playing.title == "Song B"
        assert fake_player.stop_calls == 1
        assert fake_player.play_calls[-1] == ("https://example.com/b.mp3", 100)

        saved: GuildPlayback | None = await playback_repository.get(guild_id=running_actor.guild_id)
        assert saved is not None
        assert saved.track_count == 1

    async def test_skip_resumes_paused_playback(
        self,
        running_actor: GuildPlaybackActor,
        fake_track_source: FakeTrackSource,
        playback_repository: InMemoryGuildPlaybackRepository,
        make_play_url_command: MakePlayUrlCommand,
        make_skip_command: MakeSkipCommand,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        fake_track_source.set_metadata("https://example.com/b.mp3", title="Song B")
        await running_actor.execute(make_play_url_command(url="https://example.com/a.mp3"))
        await running_actor.execute(make_play_url_command(url="https://example.com/b.mp3"))
        await running_actor.execute(PauseCommand(guild_id=running_actor.guild_id, requested_by=1))

        await running_actor.execute(make_skip_command(guild_id=running_actor.guild_id))

        saved = await playback_repository.get(guild_id=running_actor.guild_id)
        assert saved is not None
        assert saved.is_paused is False
        assert saved.first_track.title == "Song B"

    async def test_skip_last_track_reports_no_now_playing(
        self,
        running_actor: GuildPlaybackActor,
        fake_track_source: FakeTrackSource,
        make_play_url_command: MakePlayUrlCommand,
        make_skip_command: MakeSkipCommand,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        await running_actor.execute(make_play_url_command(url="https://example.com/a.mp3"))

        result: SkipResult = cast(
            SkipResult,
            await running_actor.execute(make_skip_command(guild_id=running_actor.guild_id)),
        )

        assert result.now_playing is None


@pytest.mark.unit
class TestStop:
    async def test_stop_clears_queue_deletes_persisted_state_and_terminates_actor(
        self,
        running_actor: GuildPlaybackActor,
        fake_player: FakeGuildPlayer,
        fake_track_source: FakeTrackSource,
        playback_repository: InMemoryGuildPlaybackRepository,
        terminated_guild_ids: list[int],
        make_play_url_command: MakePlayUrlCommand,
        make_stop_command: MakeStopCommand,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        await running_actor.execute(make_play_url_command(url="https://example.com/a.mp3"))

        result: StopResult = cast(
            StopResult,
            await running_actor.execute(make_stop_command(guild_id=running_actor.guild_id)),
        )

        assert result.cleared == 1
        assert fake_player.stop_calls == 1

        saved: GuildPlayback | None = await playback_repository.get(guild_id=running_actor.guild_id)
        assert saved is None
        assert terminated_guild_ids == [running_actor.guild_id]


@pytest.mark.unit
class TestPlaybackState:
    async def test_state_commands_update_domain_and_apply_player_effects(
        self,
        running_actor: GuildPlaybackActor,
        fake_player: FakeGuildPlayer,
        fake_track_source: FakeTrackSource,
        playback_repository: InMemoryGuildPlaybackRepository,
        make_play_url_command: MakePlayUrlCommand,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        await running_actor.execute(make_play_url_command())

        paused = await running_actor.execute(
            PauseCommand(guild_id=running_actor.guild_id, requested_by=1)
        )
        resumed = await running_actor.execute(
            ResumeCommand(guild_id=running_actor.guild_id, requested_by=1)
        )
        volume = await running_actor.execute(
            SetVolumeCommand(guild_id=running_actor.guild_id, requested_by=1, volume=40)
        )
        loop = await running_actor.execute(
            SetLoopCommand(guild_id=running_actor.guild_id, requested_by=1, enabled=True)
        )

        assert paused == PauseResult(paused=True)
        assert resumed == ResumeResult(resumed=True)
        assert volume == SetVolumeResult(volume=40)
        assert loop == SetLoopResult(enabled=True)
        assert fake_player.pause_calls == 1
        assert fake_player.resume_calls == 1
        assert fake_player.volume_calls == [40]

        saved = await playback_repository.get(guild_id=running_actor.guild_id)
        assert saved is not None
        assert saved.is_paused is False
        assert saved.volume == 40
        assert saved.loop_current is True

    async def test_queries_read_the_same_domain_state(
        self,
        running_actor: GuildPlaybackActor,
        fake_track_source: FakeTrackSource,
        make_play_url_command: MakePlayUrlCommand,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        await running_actor.execute(make_play_url_command())

        queue = await running_actor.execute(
            GetQueueCommand(guild_id=running_actor.guild_id, requested_by=1)
        )
        now_playing = await running_actor.execute(
            NowPlayingCommand(guild_id=running_actor.guild_id, requested_by=1)
        )

        assert isinstance(queue, GetQueueResult)
        assert [track.title for track in queue.tracks] == ["Song A"]
        assert isinstance(now_playing, NowPlayingResult)
        assert now_playing.track.title == "Song A"
        assert now_playing.is_paused is False


@pytest.mark.unit
class TestTrackFinished:
    async def test_finishing_a_track_starts_the_next_one(
        self,
        running_actor: GuildPlaybackActor,
        fake_player: FakeGuildPlayer,
        fake_track_source: FakeTrackSource,
        make_play_url_command: MakePlayUrlCommand,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        fake_track_source.set_metadata("https://example.com/b.mp3", title="Song B")
        await running_actor.execute(make_play_url_command(url="https://example.com/a.mp3"))
        await running_actor.execute(make_play_url_command(url="https://example.com/b.mp3"))

        fake_player.finish_current_track()
        await asyncio.sleep(0)  # let call_soon_threadsafe's scheduled publish run
        await asyncio.wait_for(running_actor._mailbox.join(), timeout=1)

        assert fake_player.play_calls == [
            ("https://example.com/a.mp3", 100),
            ("https://example.com/b.mp3", 100),
        ]

    async def test_finishing_the_last_track_terminates_the_actor(
        self,
        running_actor: GuildPlaybackActor,
        fake_player: FakeGuildPlayer,
        fake_track_source: FakeTrackSource,
        playback_repository: InMemoryGuildPlaybackRepository,
        terminated_guild_ids: list[int],
        make_play_url_command: MakePlayUrlCommand,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        await running_actor.execute(make_play_url_command(url="https://example.com/a.mp3"))

        fake_player.finish_current_track()
        await asyncio.sleep(0)  # let call_soon_threadsafe's scheduled publish run
        await asyncio.wait_for(running_actor._mailbox.join(), timeout=1)

        assert terminated_guild_ids == [running_actor.guild_id]
        assert await playback_repository.get(guild_id=running_actor.guild_id) is None

    async def test_stale_finished_callback_after_skip_is_ignored(
        self,
        running_actor: GuildPlaybackActor,
        fake_player: FakeGuildPlayer,
        fake_track_source: FakeTrackSource,
        make_play_url_command: MakePlayUrlCommand,
        make_skip_command: MakeSkipCommand,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        fake_track_source.set_metadata("https://example.com/b.mp3", title="Song B")
        await running_actor.execute(make_play_url_command(url="https://example.com/a.mp3"))
        await running_actor.execute(make_play_url_command(url="https://example.com/b.mp3"))

        stale_callback = fake_player.on_finished_callback
        assert stale_callback is not None

        await running_actor.execute(make_skip_command(guild_id=running_actor.guild_id))
        calls_after_skip = list(fake_player.play_calls)

        stale_callback(None)
        await asyncio.sleep(0)  # let call_soon_threadsafe's scheduled publish run
        await asyncio.wait_for(running_actor._mailbox.join(), timeout=1)

        assert fake_player.play_calls == calls_after_skip


@pytest.mark.unit
class TestClose:
    async def test_close_rejects_pending_messages_and_stops_player(
        self,
        make_actor: MakeActor,
        fake_player: FakeGuildPlayer,
    ) -> None:
        actor: GuildPlaybackActor = make_actor()
        actor.start()

        await actor.close()

        assert fake_player.stop_calls == 1

        with pytest.raises(RuntimeError):
            await actor.execute(StopCommand(guild_id=actor.guild_id, requested_by=1))

    async def test_close_during_in_flight_command_resolves_its_future_instead_of_orphaning_it(
        self,
        fake_player: FakeGuildPlayer,
        playback_repository: InMemoryGuildPlaybackRepository,
        terminated_guild_ids: list[int],
        make_play_url_command: MakePlayUrlCommand,
        fake_uow_factory: FakeUoWFactory,
        playlist_service: PlaylistService,
    ) -> None:
        # Lifecycle removal can close an actor while a command is in flight.
        # The command future must still be resolved instead of orphaned.
        resolver = HangingTrackSource()
        actor = GuildPlaybackActor(
            playback=GuildPlayback(guild_id=1),
            playback_repository=playback_repository,
            player=fake_player,
            playlist_service=playlist_service,
            track_service=TrackService(source=resolver),
            uow_factory=fake_uow_factory,
            terminated_callback=lambda a: terminated_guild_ids.append(a.guild_id),
        )
        actor.start()

        execute_task: asyncio.Task[object] = asyncio.create_task(
            actor.execute(make_play_url_command())
        )
        # Wait until the command is genuinely in flight — resolve() has been
        # entered and is stuck — not just sitting in the mailbox, where
        # close()'s own queue-draining would already handle it correctly.
        await asyncio.wait_for(resolver.started.wait(), timeout=1)

        await asyncio.wait_for(actor.close(), timeout=1)

        with pytest.raises(RuntimeError, match="GuildPlaybackActor stopped"):
            await asyncio.wait_for(execute_task, timeout=1)
