from __future__ import annotations

import logging

import discord
from discord import Interaction

from .formatter import format_error, format_info, format_success

logger: logging.Logger = logging.getLogger(__name__)


class Responder:
    def __init__(self, interaction: Interaction) -> None:
        self._interaction: Interaction = interaction

    async def defer(self) -> None:
        if self._interaction.response.is_done():
            logger.debug("Interaction response already done; skip defer")
            return

        try:
            logger.debug("Deferring Discord interaction interaction_id=%s", self._interaction.id)
            await self._interaction.response.defer(ephemeral=True)
            logger.debug("Discord interaction deferred interaction_id=%s", self._interaction.id)
        except (discord.InteractionResponded, discord.NotFound, discord.HTTPException) as exc:
            logger.warning(f"Failed to defer _interaction: {exc}")

    async def success(self, message: str, *, title: str | None = None) -> None:
        embed: discord.Embed = (
            format_success(message) if title is None else format_success(message, title=title)
        )
        logger.debug(
            "Sending success response interaction_id=%s title=%r message_length=%s",
            self._interaction.id,
            title,
            len(message),
        )
        await self._send_private(embed)

    async def info(self, message: str, *, title: str | None = None) -> None:
        embed: discord.Embed = (
            format_info(message) if title is None else format_info(message, title=title)
        )
        logger.debug(
            "Sending info response interaction_id=%s title=%r message_length=%s",
            self._interaction.id,
            title,
            len(message),
        )
        await self._send_private(embed)

    async def error(self, message: str, *, title: str | None = None) -> None:
        embed: discord.Embed = (
            format_error(message) if title is None else format_error(message, title=title)
        )
        logger.debug(
            "Sending error response interaction_id=%s title=%r message_length=%s",
            self._interaction.id,
            title,
            len(message),
        )
        await self._send_private(embed)

    async def announce(
        self,
        message: str,
        *,
        channel: discord.abc.Messageable,
        title: str | None = None,
    ) -> None:
        """Post a message visible to whoever can see `channel`.

        Reserved for events already audible there (a track starting to
        play) and scoped to the voice channel it's playing in, not the
        arbitrary text channel the command happened to be typed in: callers
        pass `voice_client.channel`, not the interaction's own channel.
        """
        embed: discord.Embed = (
            format_info(message) if title is None else format_info(message, title=title)
        )
        try:
            logger.debug(
                "Sending Discord announcement interaction_id=%s channel_id=%s title=%r "
                "message_length=%s",
                self._interaction.id,
                getattr(channel, "id", None),
                title,
                len(message),
            )
            await channel.send(embed=embed)
            logger.debug(
                "Discord announcement sent interaction_id=%s channel_id=%s",
                self._interaction.id,
                getattr(channel, "id", None),
            )
        except discord.HTTPException as exc:
            logger.warning(f"Failed to send public announcement: {exc}")

    async def _send_private(self, embed: discord.Embed) -> None:
        try:
            if not self._interaction.response.is_done():
                await self._interaction.response.send_message(embed=embed, ephemeral=True)
                logger.debug(
                    "Discord initial response sent interaction_id=%s", self._interaction.id
                )
                return

            await self._interaction.followup.send(embed=embed, ephemeral=True)
            logger.debug("Discord follow-up sent interaction_id=%s", self._interaction.id)
        except (discord.InteractionResponded, discord.NotFound, discord.HTTPException) as exc:
            logger.warning(f"Failed to send message: {exc}")
