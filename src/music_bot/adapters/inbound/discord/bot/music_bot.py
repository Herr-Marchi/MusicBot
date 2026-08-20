from __future__ import annotations

import logging

import discord
from discord import AllowedMentions, ClientUser, Intents, app_commands
from discord.ext import commands

from music_bot.adapters.discord import VoiceClientLookup
from music_bot.adapters.inbound.discord.cogs import PingCog, PlaybackCog, PlaylistCog, VoiceCog
from music_bot.adapters.inbound.discord.dependencies import DiscordDependencies

logger: logging.Logger = logging.getLogger(__name__)


class MusicBot(commands.Bot):
    def __init__(
        self,
        *,
        intents: Intents,
        dependencies: DiscordDependencies,
        voice_client_lookup: VoiceClientLookup,
        dev_guild_id: int | None = None,
    ) -> None:
        allowed_mentions: AllowedMentions = AllowedMentions(
            everyone=False,
            roles=False,
            users=False,
            replied_user=False,
        )
        super().__init__(command_prefix="!", intents=intents, allowed_mentions=allowed_mentions)

        self.dependencies: DiscordDependencies = dependencies
        self.dev_guild_id: int | None = dev_guild_id
        voice_client_lookup.bind(self)

    async def setup_hook(self) -> None:
        await super().setup_hook()

        await self.add_cog(PingCog(self))
        await self.add_cog(VoiceCog(self, deps=self.dependencies))
        await self.add_cog(PlaybackCog(self, deps=self.dependencies))
        await self.add_cog(PlaylistCog(self, deps=self.dependencies))

        synced: list[app_commands.AppCommand]
        if self.dev_guild_id is not None:
            guild: discord.Object = discord.Object(id=self.dev_guild_id)

            self.tree.clear_commands(guild=guild)
            self.tree.copy_global_to(guild=guild)

            synced = await self.tree.sync(guild=guild)
            logger.info(f"Synced {len(synced)} command(s) to dev guild {self.dev_guild_id}")
        else:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} global command(s)")

    async def on_ready(self) -> None:
        user: ClientUser | None = self.user

        if user is None:
            logger.warning("Logged in, but user is not available yet.")
        else:
            logger.info(f"Logged in as {user} (ID: {user.id})")
