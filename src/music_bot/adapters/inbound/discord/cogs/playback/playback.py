from __future__ import annotations

from discord import Interaction, VoiceClient, app_commands
from discord.ext import commands

from music_bot.adapters.inbound.discord.cogs.base import BaseCog
from music_bot.adapters.inbound.discord.dependencies import DiscordDependencies
from music_bot.adapters.inbound.discord.helpers import InteractionContext, begin_interaction
from music_bot.application.contracts.commands.music import (
    GetQueueCommand,
    NowPlayingCommand,
    PauseCommand,
    PlayUrlCommand,
    ResumeCommand,
    SetLoopCommand,
    SetVolumeCommand,
    ShuffleCommand,
    SkipCommand,
    StopCommand,
)
from music_bot.application.contracts.dto import TrackDto
from music_bot.application.contracts.results.music import (
    GetQueueResult,
    NowPlayingResult,
    PauseResult,
    PlayUrlResult,
    ResumeResult,
    SetLoopResult,
    SetVolumeResult,
    ShuffleResult,
    SkipResult,
    StopResult,
)


class PlaybackCog(BaseCog, name="Playback"):
    def __init__(self, bot: commands.Bot, deps: DiscordDependencies) -> None:
        super().__init__(bot)
        self.deps: DiscordDependencies = deps

    @app_commands.command(name="play", description="Plays a track, searched by song name/artist")
    @app_commands.describe(query="Song name, artist, or other search text — not a link")
    async def play(self, interaction: Interaction, query: str) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        voice_client: VoiceClient = await self.deps.voice_manager.connect(
            guild=ctx.guild, member=ctx.member
        )

        result: PlayUrlResult = await self.deps.playback_manager.execute(
            PlayUrlCommand(
                guild_id=ctx.guild.id,
                url=query,
                requested_by=ctx.member.id,
            )
        )
        await ctx.responder.success(
            f"Added **{result.track.title}** to position {result.queue_size}."
        )
        if result.queue_size == 1:
            await ctx.responder.announce(
                f"**{result.track.title}**", channel=voice_client.channel, title="Now playing"
            )

    @app_commands.command(name="pause", description="Pauses the current track")
    async def pause(self, interaction: Interaction) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        self.deps.voice_manager.require_same_channel(guild_id=ctx.guild.id, member=ctx.member)

        result: PauseResult = await self.deps.playback_manager.execute(
            PauseCommand(guild_id=ctx.guild.id, requested_by=ctx.member.id)
        )
        if result.paused:
            await ctx.responder.success("Playback paused.")
        else:
            await ctx.responder.info("Playback is already paused.")

    @app_commands.command(name="resume", description="Resumes the current track")
    async def resume(self, interaction: Interaction) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        self.deps.voice_manager.require_same_channel(guild_id=ctx.guild.id, member=ctx.member)

        result: ResumeResult = await self.deps.playback_manager.execute(
            ResumeCommand(guild_id=ctx.guild.id, requested_by=ctx.member.id)
        )
        if result.resumed:
            await ctx.responder.success("Playback resumed.")
        else:
            await ctx.responder.info("Playback is not paused.")

    @app_commands.command(name="skip", description="Skips the current track")
    async def skip(self, interaction: Interaction) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        voice_client: VoiceClient = self.deps.voice_manager.require_same_channel(
            guild_id=ctx.guild.id, member=ctx.member
        )

        result: SkipResult = await self.deps.playback_manager.execute(
            SkipCommand(guild_id=ctx.guild.id, requested_by=ctx.member.id)
        )
        if result.now_playing is None:
            await ctx.responder.success("Skipped the final track.")
        else:
            await ctx.responder.success("Skipped.")
            await ctx.responder.announce(
                f"**{result.now_playing.title}**", channel=voice_client.channel, title="Now playing"
            )

    @app_commands.command(name="stop", description="Stops the current track and clears the queue")
    async def stop(self, interaction: Interaction) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        self.deps.voice_manager.require_same_channel(guild_id=ctx.guild.id, member=ctx.member)

        result: StopResult = await self.deps.playback_manager.execute(
            StopCommand(guild_id=ctx.guild.id, requested_by=ctx.member.id)
        )
        await ctx.responder.success(f"Stopped playback and cleared {result.cleared} track(s).")

    @app_commands.command(name="queue", description="Shows the current queue")
    async def queue(self, interaction: Interaction) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        result: GetQueueResult = await self.deps.playback_manager.execute(
            GetQueueCommand(guild_id=ctx.guild.id, requested_by=ctx.member.id)
        )
        visible_tracks: tuple[TrackDto, ...] = result.tracks[:20]
        lines: list[str] = [
            f"{position}. **{track.title}** — requested by <@{track.requested_by}>"
            for position, track in enumerate(visible_tracks, start=1)
        ]
        hidden_count: int = len(result.tracks) - len(visible_tracks)
        if hidden_count:
            lines.append(f"...and {hidden_count} more track(s).")

        await ctx.responder.info("\n".join(lines), title=f"Queue · {len(result.tracks)} track(s)")

    @app_commands.command(name="nowplaying", description="Shows the currently playing track")
    async def now_playing(self, interaction: Interaction) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        result: NowPlayingResult = await self.deps.playback_manager.execute(
            NowPlayingCommand(guild_id=ctx.guild.id, requested_by=ctx.member.id)
        )
        title: str = "Paused" if result.is_paused else "Now playing"
        await ctx.responder.info(
            f"**{result.track.title}** — requested by <@{result.track.requested_by}>",
            title=title,
        )

    @app_commands.command(name="shuffle", description="Shuffles the entire queue")
    async def shuffle(self, interaction: Interaction) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        self.deps.voice_manager.require_same_channel(guild_id=ctx.guild.id, member=ctx.member)

        result: ShuffleResult = await self.deps.playback_manager.execute(
            ShuffleCommand(guild_id=ctx.guild.id, requested_by=ctx.member.id)
        )
        if result.shuffled:
            await ctx.responder.success(f"Shuffled {result.queue_size} tracks.")
        else:
            await ctx.responder.info("At least two tracks are required to shuffle.")

    @app_commands.command(name="loop", description="Enables or disables looping")
    @app_commands.describe(enabled="Whether the current track should loop")
    async def loop(self, interaction: Interaction, enabled: bool) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        self.deps.voice_manager.require_same_channel(guild_id=ctx.guild.id, member=ctx.member)

        result: SetLoopResult = await self.deps.playback_manager.execute(
            SetLoopCommand(
                guild_id=ctx.guild.id,
                requested_by=ctx.member.id,
                enabled=enabled,
            )
        )
        state: str = "enabled" if result.enabled else "disabled"
        await ctx.responder.success(f"Loop {state}.")

    @app_commands.command(name="volume", description="Sets the playback volume")
    @app_commands.describe(level="Volume percentage from 0 to 100")
    async def volume(
        self,
        interaction: Interaction,
        level: app_commands.Range[int, 0, 100],
    ) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        self.deps.voice_manager.require_same_channel(guild_id=ctx.guild.id, member=ctx.member)

        result: SetVolumeResult = await self.deps.playback_manager.execute(
            SetVolumeCommand(
                guild_id=ctx.guild.id,
                requested_by=ctx.member.id,
                volume=level,
            )
        )
        await ctx.responder.success(f"Volume set to {result.volume}%.")
