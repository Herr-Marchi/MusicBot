from __future__ import annotations

from contextlib import AsyncExitStack

import discord
from discord import Interaction, app_commands
from discord.ext import commands

from music_bot.adapters.inbound.discord.cogs.base import BaseCog
from music_bot.adapters.inbound.discord.dependencies import DiscordDependencies
from music_bot.adapters.inbound.discord.helpers import InteractionContext, begin_interaction
from music_bot.adapters.inbound.discord.voice_manager import VoiceConnectionLease
from music_bot.application.contracts.commands.music import StopCommand
from music_bot.application.contracts.errors import PlaybackNotActiveError
from music_bot.application.contracts.results.music import StopResult


class VoiceCog(BaseCog, name="Voice"):
    def __init__(self, bot: commands.Bot, deps: DiscordDependencies) -> None:
        super().__init__(bot)
        self.deps: DiscordDependencies = deps

    @app_commands.command(name="join", description="Joins a voice channel")
    async def join(self, interaction: Interaction) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        connection: VoiceConnectionLease = await self.deps.voice_manager.connect(
            guild=ctx.guild,
            member=ctx.member,
        )
        connection.retain()
        voice_client: discord.VoiceClient = connection.voice_client
        await ctx.responder.success(f"Connected to {voice_client.channel.mention}")

    @app_commands.command(name="leave", description="Stops playback and leaves voice")
    async def leave(self, interaction: Interaction) -> None:
        ctx: InteractionContext = await begin_interaction(interaction)
        self.deps.voice_manager.require_same_channel(guild_id=ctx.guild.id, member=ctx.member)
        cleared: int = 0
        async with AsyncExitStack() as cleanup:
            cleanup.push_async_callback(
                self.deps.voice_manager.disconnect,
                guild_id=ctx.guild.id,
            )
            cleanup.push_async_callback(
                self.deps.playback_manager.remove,
                guild_id=ctx.guild.id,
            )
            try:
                result: StopResult = await self.deps.playback_manager.execute(
                    StopCommand(
                        guild_id=ctx.guild.id,
                        requested_by=ctx.member.id,
                    )
                )
                cleared = result.cleared
            except PlaybackNotActiveError:
                pass

        await ctx.responder.success(f"Disconnected and cleared {cleared} tracks")
