from __future__ import annotations

from dataclasses import dataclass

import discord

from music_bot.adapters.inbound.discord.helpers.interaction_data import (
    require_guild,
    require_member,
)
from music_bot.adapters.inbound.discord.ui import Responder


@dataclass(frozen=True, slots=True)
class InteractionContext:
    responder: Responder
    guild: discord.Guild
    member: discord.Member


async def begin_interaction(interaction: discord.Interaction) -> InteractionContext:
    responder: Responder = Responder(interaction)
    guild: discord.Guild = require_guild(interaction)
    member: discord.Member = require_member(interaction)

    await responder.defer()

    return InteractionContext(responder=responder, guild=guild, member=member)
