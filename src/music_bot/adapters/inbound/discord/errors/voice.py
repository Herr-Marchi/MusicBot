from __future__ import annotations

from .base import DiscordAdapterError


class NotInVoiceError(DiscordAdapterError):
    def __init__(self) -> None:
        super().__init__("You must be in a voice channel to use this command.")


class NotInSameVoiceChannelError(DiscordAdapterError):
    def __init__(self) -> None:
        super().__init__("You must be in the same voice channel as the bot to do that.")


class UnsupportedVoiceChannelError(DiscordAdapterError):
    def __init__(self) -> None:
        super().__init__("Only standard voice channels are supported.")


class VoiceForbiddenError(DiscordAdapterError):
    def __init__(self) -> None:
        super().__init__("I don't have permission to join/move to that voice channel.")


class VoiceTimeoutError(DiscordAdapterError):
    def __init__(self) -> None:
        super().__init__("Voice connection timed out. Please try again.")


class VoiceConnectionError(DiscordAdapterError):
    def __init__(self) -> None:
        super().__init__("An error occurred while connecting to voice. Please try again.")
