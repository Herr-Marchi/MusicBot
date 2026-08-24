from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from music_bot.adapters.discord import NotConnectedToVoiceError
from music_bot.adapters.inbound.discord.errors import DiscordAdapterError
from music_bot.adapters.inbound.discord.ui import Responder
from music_bot.application.contracts.errors import (
    NotPlaylistOwnerError,
    PlaybackNotActiveError,
    PlaylistNotFoundError,
)
from music_bot.application.ports.track_source import TrackSourceError

logger: logging.Logger = logging.getLogger(__name__)


class BaseCog(commands.Cog, name="BaseCog"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        command_name: str = (
            interaction.command.qualified_name if interaction.command is not None else "unknown"
        )
        logger.info(
            "Discord command started interaction_id=%s command=%s guild_id=%s "
            "user_id=%s channel_id=%s",
            interaction.id,
            command_name,
            interaction.guild_id,
            interaction.user.id,
            interaction.channel_id,
        )
        return True

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        responder: Responder = Responder(interaction)

        root: Exception = error
        if isinstance(error, app_commands.CommandInvokeError):
            root = error.original

        command_name: str = (
            interaction.command.qualified_name if interaction.command is not None else "unknown"
        )
        logger.info(
            "Discord interaction failed interaction_id=%s command=%s guild_id=%s "
            "user_id=%s error=%s",
            interaction.id,
            command_name,
            interaction.guild_id,
            interaction.user.id,
            type(root).__name__,
        )

        if isinstance(root, DiscordAdapterError | NotConnectedToVoiceError):
            await responder.error(str(root))
            return

        if isinstance(root, TrackSourceError):
            await responder.error(str(root), title="Could not resolve track")
            return

        if isinstance(root, PlaybackNotActiveError):
            await responder.info("There is no active playback.")
            return

        if isinstance(root, PlaylistNotFoundError):
            await responder.error("Playlist not found.")
            return

        if isinstance(root, NotPlaylistOwnerError):
            await responder.error("Only the playlist owner can do that.")
            return

        if isinstance(root, TimeoutError):
            await responder.error("Operation timed out. Please try again.")
            return

        if isinstance(root, discord.Forbidden):
            await responder.error("I don't have permission to do that.")
            return

        if isinstance(root, discord.NotFound):
            logger.warning("Discord NotFound while responding: %s", root)
            return

        if isinstance(root, discord.HTTPException):
            logger.warning("Discord HTTPException: %s", root)
            await responder.error("Discord API error occurred. Please try again.")
            return

        if isinstance(root, discord.ClientException):
            logger.warning("Discord ClientException: %s", root)
            await responder.error("Discord client error occurred. Please try again.")
            return

        logger.exception("Unhandled exception in app command", exc_info=root)
        await responder.error("Unexpected error occurred.")
