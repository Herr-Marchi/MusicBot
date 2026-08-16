from __future__ import annotations


class PlaybackNotActiveError(Exception):
    pass


class TrackMetadataResolutionError(Exception):
    pass


class PlaylistNotFoundError(Exception):
    pass


class NotPlaylistOwnerError(Exception):
    pass


__all__ = (
    "NotPlaylistOwnerError",
    "PlaybackNotActiveError",
    "PlaylistNotFoundError",
    "TrackMetadataResolutionError",
)
