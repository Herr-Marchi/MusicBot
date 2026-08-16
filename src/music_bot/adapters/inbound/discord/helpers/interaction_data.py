from __future__ import annotations

import discord

from music_bot.adapters.inbound.discord.errors import (
    NotAMemberError,
    NotInGuildError,
)


def require_guild(interaction: discord.Interaction) -> discord.Guild:
    guild: discord.Guild | None = interaction.guild
    if guild is None:
        raise NotInGuildError()

    return guild


def require_member(interaction: discord.Interaction) -> discord.Member:
    member: discord.Member | None = (
        interaction.user if isinstance(interaction.user, discord.Member) else None
    )
    if member is None:
        raise NotAMemberError()

    return member
