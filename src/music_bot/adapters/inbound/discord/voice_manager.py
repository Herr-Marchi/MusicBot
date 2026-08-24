from __future__ import annotations

import logging
from types import TracebackType
from typing import Self

import discord

from music_bot.adapters.discord import VoiceClientLookup
from music_bot.adapters.inbound.discord.errors import (
    NotInSameVoiceChannelError,
    NotInVoiceError,
    UnsupportedVoiceChannelError,
    VoiceConnectionError,
    VoiceForbiddenError,
    VoiceTimeoutError,
)

logger: logging.Logger = logging.getLogger(__name__)


class VoiceConnectionLease:
    def __init__(self, *, voice_client: discord.VoiceClient, created: bool) -> None:
        self._voice_client: discord.VoiceClient = voice_client
        self._should_rollback: bool = created

    @property
    def voice_client(self) -> discord.VoiceClient:
        return self._voice_client

    def retain(self) -> None:
        self._should_rollback = False
        logger.debug("Voice connection lease retained")

    async def rollback(self) -> None:
        if not self._should_rollback:
            logger.debug("Voice connection lease rollback skipped")
            return

        logger.info("Rolling back newly-created voice connection")
        await _disconnect_voice_client(self._voice_client)
        self._should_rollback = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.rollback()


class DiscordVoiceManager:
    def __init__(self, *, lookup: VoiceClientLookup) -> None:
        self._lookup: VoiceClientLookup = lookup

    async def connect(
        self,
        *,
        guild: discord.Guild,
        member: discord.Member,
    ) -> VoiceConnectionLease:
        logger.info(
            "Voice connect requested guild_id=%s member_id=%s",
            guild.id,
            member.id,
        )
        voice_state: discord.VoiceState | None = member.voice
        if voice_state is None or voice_state.channel is None:
            logger.info(
                "Voice connect rejected member outside voice guild_id=%s member_id=%s",
                guild.id,
                member.id,
            )
            raise NotInVoiceError()

        connectable: discord.abc.Connectable = voice_state.channel
        if not isinstance(connectable, discord.VoiceChannel):
            logger.info(
                "Voice connect rejected unsupported channel guild_id=%s member_id=%s "
                "channel_type=%s",
                guild.id,
                member.id,
                type(connectable).__name__,
            )
            raise UnsupportedVoiceChannelError()

        voice_channel: discord.VoiceChannel = connectable
        voice_protocol: discord.VoiceProtocol | None = guild.voice_client
        created: bool = False

        try:
            if isinstance(voice_protocol, discord.VoiceClient):
                voice_client: discord.VoiceClient = voice_protocol
                if voice_client.channel != voice_channel:
                    # Moving the bot is controlling playback for everyone
                    # already listening only someone in its current
                    # channel may do that
                    logger.info(
                        "Voice connect rejected channel mismatch guild_id=%s member_id=%s "
                        "requested_channel_id=%s current_channel_id=%s",
                        guild.id,
                        member.id,
                        voice_channel.id,
                        voice_client.channel.id,
                    )
                    raise NotInSameVoiceChannelError()
                logger.debug(
                    "Voice connection reused guild_id=%s channel_id=%s",
                    guild.id,
                    voice_channel.id,
                )
            else:
                logger.debug(
                    "Discord voice network connect started guild_id=%s channel_id=%s",
                    guild.id,
                    voice_channel.id,
                )
                voice_client = await voice_channel.connect()
                created = True
        except TimeoutError as exc:
            logger.warning("Discord voice connect timed out guild_id=%s", guild.id)
            raise VoiceTimeoutError() from exc
        except discord.Forbidden as exc:
            logger.warning("Discord voice connect forbidden guild_id=%s", guild.id)
            raise VoiceForbiddenError() from exc
        except (discord.ClientException, discord.HTTPException) as exc:
            logger.warning("Discord voice connect failed guild_id=%s error=%s", guild.id, exc)
            raise VoiceConnectionError() from exc

        logger.info(
            "Voice connection ready guild_id=%s channel_id=%s created=%s",
            guild.id,
            voice_channel.id,
            created,
        )
        return VoiceConnectionLease(voice_client=voice_client, created=created)

    async def disconnect(self, *, guild_id: int) -> None:
        logger.info("Voice disconnect requested guild_id=%s", guild_id)
        voice_client: discord.VoiceClient = self._lookup.require(guild_id)
        await _disconnect_voice_client(voice_client)
        logger.info("Voice disconnected guild_id=%s", guild_id)

    def require_voice_client(self, guild_id: int) -> discord.VoiceClient:
        logger.debug("Requiring voice client guild_id=%s", guild_id)
        return self._lookup.require(guild_id)

    def require_same_channel(
        self,
        *,
        guild_id: int,
        member: discord.Member,
    ) -> discord.VoiceClient:
        logger.debug(
            "Checking member voice channel guild_id=%s member_id=%s",
            guild_id,
            member.id,
        )
        voice_client: discord.VoiceClient = self._lookup.require(guild_id)
        voice_state: discord.VoiceState | None = member.voice
        member_channel: discord.abc.Connectable | None = (
            voice_state.channel if voice_state is not None else None
        )
        if member_channel != voice_client.channel:
            logger.info(
                "Voice channel check rejected guild_id=%s member_id=%s",
                guild_id,
                member.id,
            )
            raise NotInSameVoiceChannelError()

        logger.debug(
            "Voice channel check passed guild_id=%s member_id=%s channel_id=%s",
            guild_id,
            member.id,
            voice_client.channel.id,
        )
        return voice_client


async def _disconnect_voice_client(voice_client: discord.VoiceClient) -> None:
    voice_guild: object | None = getattr(voice_client, "guild", None)
    voice_channel: object | None = getattr(voice_client, "channel", None)
    guild_id: object | None = getattr(voice_guild, "id", None)
    channel_id: object | None = getattr(voice_channel, "id", None)
    try:
        logger.debug(
            "Discord voice network disconnect started guild_id=%s channel_id=%s",
            guild_id,
            channel_id,
        )
        await voice_client.disconnect(force=False)
        logger.debug("Discord voice network disconnect completed guild_id=%s", guild_id)
    except TimeoutError as exc:
        logger.warning("Discord voice disconnect timed out guild_id=%s", guild_id)
        raise VoiceTimeoutError() from exc
    except (discord.ClientException, discord.HTTPException) as exc:
        logger.warning(
            "Discord voice disconnect failed guild_id=%s error=%s",
            guild_id,
            exc,
        )
        raise VoiceConnectionError() from exc
