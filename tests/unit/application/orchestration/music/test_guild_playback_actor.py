from __future__ import annotations

import asyncio
from typing import cast

import pytest
from tests.fakes import FakeGuildPlayer, FakeTrackSource
from tests.typing_helper import MakePlayUrlCommand, MakeSkipCommand, MakeStopCommand
from tests.unit.application.orchestration.music.conftest import MakeActor

from music_bot.adapters.outbound.in_memory.music import InMemoryGuildPlaybackRepository
from music_bot.application.contracts.commands.music import (
    PlayPlaylistCommand,
    PlayUrlCommand,
    StopCommand,
)
from music_bot.application.contracts.errors import TrackMetadataResolutionError
from music_bot.application.contracts.results.music import (
    PlayPlaylistResult,
    PlayUrlResult,
    SkipResult,
    StopResult,
)
from music_bot.application.orchestration.music.guild_playback_actor import GuildPlaybackActor
from music_bot.application.orchestration.music.handlers import play_url as play_url_module
from music_bot.application.ports.track_source import TrackMetadata
from music_bot.domain.music.models import GuildPlayback


class HangingResolver:
    def __init__(self) -> None:
        self.started: asyncio.Event = asyncio.Event()

    async def resolve(self, *, source_url: str) -> TrackMetadata:
        self.started.set()
        await asyncio.sleep(10)
        raise AssertionError("resolve() should have been abandoned")


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
        playback_repository: InMemoryGuildPlaybackRepository,
        make_play_url_command: MakePlayUrlCommand,
    ) -> None:
        fake_track_source.set_metadata(
            "https://example.com/a.mp3", title="Song A", duration_seconds=180
        )
        command: PlayUrlCommand = make_play_url_command(url="https://example.com/a.mp3")

        result: PlayUrlResult = cast(PlayUrlResult, await running_actor.execute(command))

        assert result.track.title == "Song A"
        assert result.queue_size == 1
        assert fake_player.play_calls == [("https://example.com/a.mp3", 100)]

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
        fake_track_source.fail_resolve_with(TrackMetadataResolutionError("no such video"))

        with pytest.raises(TrackMetadataResolutionError):
            await running_actor.execute(make_play_url_command())

        assert terminated_guild_ids == [running_actor.guild_id]

    async def test_hung_resolver_times_out_instead_of_wedging_the_actor(
        self,
        fake_player: FakeGuildPlayer,
        playback_repository: InMemoryGuildPlaybackRepository,
        terminated_guild_ids: list[int],
        make_play_url_command: MakePlayUrlCommand,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(play_url_module, "_RESOLVE_TIMEOUT_SECONDS", 0.05)
        actor = GuildPlaybackActor(
            guild_id=1,
            playback=None,
            playback_repository=playback_repository,
            player=fake_player,
            metadata_resolver=HangingResolver(),
            terminated_callback=lambda a: terminated_guild_ids.append(a.guild_id),
        )
        actor.start()

        try:
            with pytest.raises(TrackMetadataResolutionError):
                await asyncio.wait_for(actor.execute(make_play_url_command()), timeout=1)
        finally:
            await actor.close()

        assert terminated_guild_ids == [actor.guild_id]


@pytest.mark.unit
class TestPlayPlaylist:
    async def test_fresh_actor_batch_activates_and_starts_playback(
        self,
        running_actor: GuildPlaybackActor,
        fake_player: FakeGuildPlayer,
        fake_track_source: FakeTrackSource,
        playback_repository: InMemoryGuildPlaybackRepository,
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        fake_track_source.set_metadata("https://example.com/b.mp3", title="Song B")
        command = PlayPlaylistCommand(
            guild_id=running_actor.guild_id,
            requested_by=1,
            urls=["https://example.com/a.mp3", "https://example.com/b.mp3"],
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
    ) -> None:
        fake_track_source.set_metadata("https://example.com/a.mp3", title="Song A")
        fake_track_source.set_metadata("https://example.com/b.mp3", title="Song B")
        fake_track_source.set_metadata("https://example.com/c.mp3", title="Song C")
        await running_actor.execute(make_play_url_command(url="https://example.com/a.mp3"))

        command = PlayPlaylistCommand(
            guild_id=running_actor.guild_id,
            requested_by=1,
            urls=["https://example.com/b.mp3", "https://example.com/c.mp3"],
        )
        result: PlayPlaylistResult = cast(PlayPlaylistResult, await running_actor.execute(command))

        assert result.queued_count == 2
        assert result.started_playing is False
        assert fake_player.play_calls == [("https://example.com/a.mp3", 100)]


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
    ) -> None:
        # shutdown() closes every actor concurrently without going through
        # the per-guild lock that normally keeps close() from overlapping an
        # in-flight execute() — so a command can genuinely be mid-processing
        # when close() lands. Without special handling that future is never
        # resolved and whoever called execute() hangs forever.
        resolver = HangingResolver()
        actor = GuildPlaybackActor(
            guild_id=1,
            playback=None,
            playback_repository=playback_repository,
            player=fake_player,
            metadata_resolver=resolver,
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
