from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

from music_bot.adapters.inbound.discord.helpers.interaction_data import (
    require_guild,
    require_member,
)
from music_bot.adapters.inbound.discord.ui import Responder

logger: logging.Logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class InteractionContext:
    responder: Responder
    guild: discord.Guild
    member: discord.Member


async def begin_interaction(interaction: discord.Interaction) -> InteractionContext:
    responder: Responder = Responder(interaction)
    guild: discord.Guild = require_guild(interaction)
    member: discord.Member = require_member(interaction)

    command_name: str = (
        interaction.command.qualified_name if interaction.command is not None else "unknown"
    )
    logger.debug(
        "Discord interaction context resolved interaction_id=%s command=%s guild_id=%s "
        "user_id=%s channel_id=%s",
        interaction.id,
        command_name,
        guild.id,
        member.id,
        interaction.channel_id,
    )

    await responder.defer()

    return InteractionContext(responder=responder, guild=guild, member=member)
