from __future__ import annotations

from .base import DiscordAdapterError
from .context import NotAMemberError, NotInGuildError
from .voice import (
    NotInSameVoiceChannelError,
    NotInVoiceError,
    UnsupportedVoiceChannelError,
    VoiceConnectionError,
    VoiceForbiddenError,
    VoiceTimeoutError,
)

__all__ = (
    "DiscordAdapterError",
    "NotAMemberError",
    "NotInGuildError",
    "NotInSameVoiceChannelError",
    "NotInVoiceError",
    "UnsupportedVoiceChannelError",
    "VoiceConnectionError",
    "VoiceForbiddenError",
    "VoiceTimeoutError",
)
